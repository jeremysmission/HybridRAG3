# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the query engine online streaming new area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
import pytest
from unittest.mock import MagicMock, patch

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeLLMResponse


def _make_engine(config=None):
    if config is None:
        config = FakeConfig(mode="online")

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_llm_router = MagicMock()

    with patch("src.core.query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as MockRetriever:
            mock_retriever_instance = MagicMock()
            mock_retriever_instance.search.return_value = [
                {
                    "chunk_id": "abc123",
                    "text": "Spec says nominal voltage is 12V.",
                    "score": 0.92,
                    "source_path": "/docs/spec.md",
                }
            ]
            mock_retriever_instance.build_context.return_value = (
                "Spec says nominal voltage is 12V."
            )
            mock_retriever_instance.get_sources.return_value = [
                {"path": "/docs/spec.md", "chunks": 1, "avg_relevance": 0.92}
            ]
            MockRetriever.return_value = mock_retriever_instance

            from src.core.query_engine import QueryEngine
            engine = QueryEngine(
                config, mock_vector_store, mock_embedder, mock_llm_router
            )

    return engine, mock_llm_router


def test_online_query_success_path_covered():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)
    router.query.return_value = FakeLLMResponse(
        text="Nominal voltage is 12V.",
        tokens_in=120,
        tokens_out=20,
        model="gpt-3.5-turbo",
        latency_ms=210.0,
    )

    result = engine.query("What is nominal voltage?")

    assert result.mode == "online"
    assert result.error is None
    assert result.answer == "Nominal voltage is 12V."
    assert result.tokens_in == 120
    assert result.tokens_out == 20
    assert result.cost_usd > 0.0


def test_online_query_failure_when_api_returns_none():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)
    router.query.return_value = None

    result = engine.query("Will this fail?")

    assert result.mode == "online"
    assert result.error == "LLM call failed"
    assert "Error calling LLM" in result.answer


def test_stream_single_token_behavior():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)
    router.query_stream.return_value = iter([
        {"token": "single-token"},
        {"done": True, "tokens_in": 10, "tokens_out": 1, "model": "gpt-3.5-turbo", "latency_ms": 50.0},
    ])

    events = list(engine.query_stream("stream once"))
    tokens = [e["token"] for e in events if "token" in e]
    done = [e for e in events if e.get("done")]

    assert tokens == ["single-token"]
    assert len(done) == 1
    assert done[0]["result"].answer == "single-token"


def test_stream_empty_tokens_yields_fallback_message_token():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)
    router.query_stream.return_value = iter([
        {"done": True, "tokens_in": 0, "tokens_out": 0, "model": "gpt-3.5-turbo", "latency_ms": 20.0},
    ])

    events = list(engine.query_stream("empty stream"))
    tokens = [e["token"] for e in events if "token" in e]
    done = [e for e in events if e.get("done")]

    assert len(tokens) == 1
    assert tokens[0] == "Error calling LLM. Please try again."
    assert len(done) == 1
    assert done[0]["result"].answer == "Error calling LLM. Please try again."


def test_stream_generator_exception_returns_done_with_error():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)

    def broken_stream(_prompt):
        raise RuntimeError("stream exploded")
        yield  # pragma: no cover

    router.query_stream.side_effect = broken_stream

    events = list(engine.query_stream("boom"))
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    assert "RuntimeError" in done[0]["result"].error
    assert "stream exploded" in done[0]["result"].answer


def test_stream_timeout_returns_done_with_timeout_error():
    config = FakeConfig(mode="online")
    engine, router = _make_engine(config=config)

    def timeout_stream(_prompt):
        raise TimeoutError("timed out waiting for upstream")
        yield  # pragma: no cover

    router.query_stream.side_effect = timeout_stream

    events = list(engine.query_stream("timeout"))
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    assert "TimeoutError" in done[0]["result"].error
    assert "timed out" in done[0]["result"].answer.lower()


def test_api_router_init_failure_sets_client_none_and_query_returns_none():
    config = FakeConfig(mode="online")
    config.api.endpoint = "https://openrouter.ai/api/v1"

    mock_gate = MagicMock()
    mock_gate.check_allowed.return_value = None

    with patch("src.core.llm_router.get_gate", return_value=mock_gate), \
            patch("src.core.llm_router.get_app_logger") as mock_logger, \
            patch("openai.OpenAI", side_effect=RuntimeError("client init failed")), \
            patch("openai.AzureOpenAI"):
        mock_logger.return_value = MagicMock()
        from src.core.llm_router import APIRouter
        router = APIRouter(config, "test-key", "https://openrouter.ai/api/v1")

    assert router.client is None
    assert router.query("hello") is None
