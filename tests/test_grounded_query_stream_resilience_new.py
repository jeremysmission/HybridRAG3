# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the grounded query stream resilience new area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeLLMResponse


def _make_engine():
    config = FakeConfig(mode="offline")
    config.hallucination_guard_enabled = True
    config.hallucination_guard_threshold = 0.80
    config.hallucination_guard_action = "flag"

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()

    with patch("src.core.grounded_query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as mock_retriever_cls:
            mock_retriever = MagicMock()
            mock_retriever.search.return_value = [
                SimpleNamespace(
                    score=0.92,
                    text="The threshold is 42.",
                    source_path="/docs/manual.txt",
                )
            ]
            mock_retriever.build_context.return_value = "X" * 6000
            mock_retriever.get_sources.return_value = [
                {"path": "/docs/manual.txt", "chunks": 1, "avg_relevance": 0.92}
            ]
            mock_retriever_cls.return_value = mock_retriever

            from src.core.grounded_query_engine import GroundedQueryEngine
            engine = GroundedQueryEngine(
                config, mock_vector_store, mock_embedder, mock_router
            )

    engine.guard_enabled = True
    engine._guard_available = True
    return engine, mock_router


def test_grounded_stream_uses_context_trim_before_prompt():
    engine, router = _make_engine()
    engine.config.ollama.context_window = 1024
    engine.config.ollama.num_predict = 256
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(1.0, {"claims": []}))
    engine._apply_guard_action = MagicMock(return_value=("ok", False))
    router.query_stream.return_value = iter(
        [{"token": "raw"}, {"done": True, "tokens_in": 1, "tokens_out": 1}]
    )

    with patch.object(
        engine, "_trim_context_to_fit", wraps=engine._trim_context_to_fit
    ) as trim_spy:
        list(engine.query_stream("trim please"))

    assert trim_spy.called is True


def test_grounded_stream_empty_generator_falls_back_to_non_stream_query():
    engine, router = _make_engine()
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(0.9, {"claims": []}))
    engine._apply_guard_action = MagicMock(return_value=("Guarded fallback answer.", False))
    router.query_stream.return_value = iter([])
    router.query.return_value = FakeLLMResponse(
        text="raw fallback answer",
        tokens_in=10,
        tokens_out=4,
        model="phi4-mini",
        latency_ms=8.0,
    )

    events = list(engine.query_stream("fallback please"))
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    assert done[0]["result"].error is None
    assert done[0]["result"].answer == "Guarded fallback answer."
    assert router.query.called is True
