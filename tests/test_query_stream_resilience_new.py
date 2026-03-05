# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the query stream resilience new area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from unittest.mock import MagicMock, patch

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeLLMResponse


def _make_engine(config=None):
    if config is None:
        config = FakeConfig(mode="offline")

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_llm_router = MagicMock()

    with patch("src.core.query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as mock_retriever_cls:
            mock_retriever = MagicMock()
            mock_retriever.search.return_value = [
                {
                    "chunk_id": "c1",
                    "text": "A" * 5000,
                    "score": 0.95,
                    "source_path": "/docs/spec.txt",
                }
            ]
            mock_retriever.build_context.return_value = "A" * 5000
            mock_retriever.get_sources.return_value = [
                {"path": "/docs/spec.txt", "chunks": 1, "avg_relevance": 0.95}
            ]
            mock_retriever_cls.return_value = mock_retriever

            from src.core.query_engine import QueryEngine
            engine = QueryEngine(
                config, mock_vector_store, mock_embedder, mock_llm_router
            )

    return engine, mock_llm_router


def test_stream_uses_context_trim_before_prompt():
    config = FakeConfig(mode="offline")
    config.ollama.context_window = 1024
    config.ollama.num_predict = 256
    engine, router = _make_engine(config=config)
    router.query_stream.return_value = iter(
        [{"token": "ok"}, {"done": True, "tokens_in": 1, "tokens_out": 1}]
    )

    with patch.object(
        engine, "_trim_context_to_fit", wraps=engine._trim_context_to_fit
    ) as trim_spy:
        list(engine.query_stream("what is this?"))

    assert trim_spy.called is True
    assert router.query_stream.called is True


def test_stream_empty_generator_falls_back_to_non_stream_query():
    engine, router = _make_engine()
    router.query_stream.return_value = iter([])
    router.query.return_value = FakeLLMResponse(
        text="Recovered via fallback query.",
        tokens_in=20,
        tokens_out=5,
        model="phi4-mini",
        latency_ms=10.0,
    )

    events = list(engine.query_stream("fallback test"))
    tokens = [e["token"] for e in events if "token" in e]
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    assert "Recovered via fallback query." in "".join(tokens)
    assert done[0]["result"].answer == "Recovered via fallback query."
    assert router.query.called is True


def test_stream_exception_keeps_sources_and_chunk_count():
    engine, router = _make_engine()
    router.query_stream.side_effect = TimeoutError("timed out")

    events = list(engine.query_stream("timeout test"))
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    result = done[0]["result"]
    assert result.error is not None
    assert "TimeoutError" in result.error
    assert result.chunks_used == 1
    assert len(result.sources) == 1
