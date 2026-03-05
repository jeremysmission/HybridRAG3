# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the grounded query engine stream additional new area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig


def _make_engine():
    config = FakeConfig(mode="offline")
    config.hallucination_guard_enabled = False
    config.hallucination_guard_threshold = 0.80
    config.hallucination_guard_action = "block"

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()

    with patch("src.core.grounded_query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as mock_retriever_cls:
            mock_retriever = MagicMock()
            mock_retriever.search.return_value = [
                SimpleNamespace(
                    score=0.91,
                    text="System serial number is ABC123.",
                    source_path="/docs/manual.txt",
                )
            ]
            mock_retriever.build_context.return_value = "System serial number is ABC123."
            mock_retriever.get_sources.return_value = [
                {"path": "/docs/manual.txt", "chunks": 1, "avg_relevance": 0.91}
            ]
            mock_retriever_cls.return_value = mock_retriever

            from src.core.grounded_query_engine import GroundedQueryEngine
            engine = GroundedQueryEngine(
                config, mock_vector_store, mock_embedder, mock_router
            )

    return engine, mock_router, mock_retriever


def test_stream_empty_raw_answer_returns_error_result_done():
    engine, router, _ = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")

    router.query_stream.return_value = iter([
        {"done": True, "tokens_in": 1, "tokens_out": 0, "model": "phi4-mini", "latency_ms": 5.0},
    ])

    events = list(engine.query_stream("serial?"))
    done = [e for e in events if e.get("done")]

    assert len(done) == 1
    result = done[0]["result"]
    assert result.grounding_blocked is True
    assert result.error is not None
    assert "LLM stream empty" in result.error


def test_stream_retrieval_gate_blocking_no_results():
    engine, _, retriever = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    retriever.search.return_value = []

    events = list(engine.query_stream("unknown query"))
    tokens = [e for e in events if "token" in e]
    done = [e for e in events if e.get("done")]

    assert tokens == []
    assert len(done) == 1
    result = done[0]["result"]
    assert result.grounding_blocked is True
    assert result.grounding_details.get("reason") == "no_search_results"


def test_stream_guard_action_strip_emits_only_supported_claims():
    engine, router, _ = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    engine.guard_action = "strip"
    engine.guard_threshold = 0.80
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(0.25, {
        "claims": [
            {"claim": "System serial number is ABC123.", "verdict": "SUPPORTED"},
            {"claim": "Admin password is swordfish.", "verdict": "REFUTED"},
        ]
    }))

    router.query_stream.return_value = iter([
        {"token": "System serial number is ABC123. Admin password is swordfish."},
        {"done": True, "tokens_in": 12, "tokens_out": 9, "model": "phi4-mini", "latency_ms": 9.0},
    ])

    events = list(engine.query_stream("serial + password?"))
    token_text = "".join(e["token"] for e in events if "token" in e)
    done = [e for e in events if e.get("done")]

    assert "ABC123" in token_text
    assert "swordfish" not in token_text
    assert len(done) == 1
    result = done[0]["result"]
    assert result.grounding_safe is False
    assert result.grounding_blocked is False


def test_stream_guard_action_flag_passes_through_with_low_score():
    engine, router, _ = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    engine.guard_action = "flag"
    engine.guard_threshold = 0.90
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(0.40, {
        "claims": [{"claim": "System serial number is ABC123.", "verdict": "REFUTED"}]
    }))

    router.query_stream.return_value = iter([
        {"token": "System serial number is ABC123."},
        {"done": True, "tokens_in": 8, "tokens_out": 6, "model": "phi4-mini", "latency_ms": 8.0},
    ])

    events = list(engine.query_stream("serial?"))
    token_text = "".join(e["token"] for e in events if "token" in e)
    done = [e for e in events if e.get("done")]

    assert "ABC123" in token_text
    assert len(done) == 1
    result = done[0]["result"]
    assert result.grounding_safe is False
    assert result.grounding_blocked is False
    assert result.answer == "System serial number is ABC123."
