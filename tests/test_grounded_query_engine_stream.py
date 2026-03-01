# ============================================================================
# Tests for GroundedQueryEngine.query_stream() guard behavior
# ============================================================================

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
            mock_retriever.build_context.return_value = (
                "System serial number is ABC123."
            )
            mock_retriever.get_sources.return_value = [
                {"path": "/docs/manual.txt", "chunks": 1, "avg_relevance": 0.91}
            ]
            mock_retriever_cls.return_value = mock_retriever

            from src.core.grounded_query_engine import GroundedQueryEngine
            engine = GroundedQueryEngine(
                config, mock_vector_store, mock_embedder, mock_router
            )

    return engine, mock_router


def test_stream_blocks_unverified_raw_tokens():
    engine, mock_router = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    engine.guard_action = "block"
    engine.guard_threshold = 0.80
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(
        return_value=(0.10, {"claims": [{"claim": "bad", "verdict": "REFUTED"}]})
    )

    # Raw stream contains unsafe text that should never be surfaced directly.
    mock_router.query_stream.return_value = iter(
        [
            {"token": "UNSAFE_SERIAL=ZZZ999"},
            {"done": True, "tokens_in": 10, "tokens_out": 5, "model": "phi4-mini"},
        ]
    )

    events = list(engine.query_stream("What is my serial number?"))
    token_text = "".join(e["token"] for e in events if "token" in e)
    done = next(e for e in events if e.get("done"))
    result = done["result"]

    assert "UNSAFE_SERIAL" not in token_text
    assert result.grounding_blocked is True
    assert "cannot provide a fully verified answer" in result.answer


def test_stream_emits_answer_when_verification_passes():
    engine, mock_router = _make_engine()
    engine.guard_enabled = True
    engine._guard_available = True
    engine.guard_action = "block"
    engine.guard_threshold = 0.80
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(
        return_value=(1.0, {"claims": [{"claim": "ok", "verdict": "SUPPORTED"}]})
    )

    mock_router.query_stream.return_value = iter(
        [
            {"token": "System "},
            {"token": "serial "},
            {"token": "number "},
            {"token": "is "},
            {"token": "ABC123."},
            {"done": True, "tokens_in": 10, "tokens_out": 5, "model": "phi4-mini"},
        ]
    )

    events = list(engine.query_stream("What is my serial number?"))
    token_text = "".join(e["token"] for e in events if "token" in e)
    done = next(e for e in events if e.get("done"))
    result = done["result"]

    assert "ABC123" in token_text
    assert result.grounding_blocked is False
    assert result.grounding_safe is True
