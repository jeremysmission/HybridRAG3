# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies the new retrieval/query debug trace payload and protects against regressions.
# What to read first: Start at the helper builders, then the three top-level tests.
# Inputs: Mocked QueryEngine and GroundedQueryEngine dependencies only.
# Outputs: Assertions on result.debug_trace and engine.last_query_trace.
# Safety notes: No network, GPU, or real index required.
# ============================

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeLLMResponse


def _make_query_engine(config=None):
    if config is None:
        config = FakeConfig(mode="offline")

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()
    mock_router.query.return_value = FakeLLMResponse(
        text="Nominal voltage is 12V.",
        tokens_in=120,
        tokens_out=18,
        model="phi4-mini",
        latency_ms=210.0,
    )

    with patch("src.core.query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as retriever_cls:
            retriever = MagicMock()
            retriever.search.return_value = [
                SimpleNamespace(
                    score=0.92,
                    source_path="/docs/spec.md",
                    chunk_index=1,
                    text="Nominal voltage is 12V.",
                )
            ]
            retriever.get_sources.return_value = [
                {"path": "/docs/spec.md", "chunks": 1, "avg_relevance": 0.92}
            ]
            retriever.build_context.return_value = (
                "[Source 1] /docs/spec.md (chunk 1, score=0.920)\nNominal voltage is 12V."
            )
            retriever.last_search_trace = {
                "counts": {
                    "raw_hits": 1,
                    "post_rerank_hits": 1,
                    "post_filter_hits": 1,
                    "post_augment_hits": 1,
                    "final_hits": 1,
                    "dropped_hits": 0,
                },
                "hits": {
                    "raw": [],
                    "post_rerank": [],
                    "post_filter": [],
                    "post_augment": [],
                    "final": [
                        {
                            "rank": 1,
                            "stage": "final",
                            "reason": "",
                            "score": 0.92,
                            "source_file": "spec.md",
                            "source_path": "/docs/spec.md",
                            "chunk_index": 1,
                            "text": "Nominal voltage is 12V.",
                            "text_chars": 24,
                            "text_truncated": False,
                        }
                    ],
                    "dropped": [],
                },
                "source_path_flags": {
                    "expected_source_root": "",
                    "suspicious_count": 0,
                    "suspicious_sources": [],
                },
            }
            retriever_cls.return_value = retriever

            from src.core.query_engine import QueryEngine

            engine = QueryEngine(
                config, mock_vector_store, mock_embedder, mock_router
            )

    return engine, retriever, mock_router


def _make_grounded_engine():
    config = FakeConfig(mode="offline")
    config.query.allow_open_knowledge = False
    config.hallucination_guard_enabled = False
    config.hallucination_guard_threshold = 0.80
    config.hallucination_guard_action = "block"

    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()

    with patch("src.core.grounded_query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as retriever_cls:
            retriever = MagicMock()
            retriever.search.return_value = []
            retriever.last_search_trace = {
                "counts": {
                    "raw_hits": 0,
                    "post_rerank_hits": 0,
                    "post_filter_hits": 0,
                    "post_augment_hits": 0,
                    "final_hits": 0,
                    "dropped_hits": 0,
                },
                "hits": {
                    "raw": [],
                    "post_rerank": [],
                    "post_filter": [],
                    "post_augment": [],
                    "final": [],
                    "dropped": [],
                },
                "source_path_flags": {
                    "expected_source_root": "",
                    "suspicious_count": 0,
                    "suspicious_sources": [],
                },
            }
            retriever_cls.return_value = retriever

            from src.core.grounded_query_engine import GroundedQueryEngine

            engine = GroundedQueryEngine(
                config, mock_vector_store, mock_embedder, mock_router
            )

    return engine


def test_query_attaches_debug_trace_on_success():
    engine, _, _ = _make_query_engine()
    engine.config.ollama.top_p = 0.82
    engine.config.ollama.seed = 13

    result = engine.query("What is nominal voltage?")

    assert result.debug_trace is not None
    assert result.debug_trace["decision"]["path"] == "answer"
    assert result.debug_trace["mode"] == "offline"
    assert result.debug_trace["settings"]["backend"]["name"] == "ollama"
    assert abs(result.debug_trace["settings"]["backend"]["top_p"] - 0.82) < 1e-9
    assert result.debug_trace["settings"]["backend"]["seed"] == 13
    assert result.debug_trace["retrieval"]["counts"]["final_hits"] == 1
    assert result.debug_trace["retrieval"]["hits"]["final"][0]["source_file"] == "spec.md"
    assert "12V" in result.debug_trace["retrieval"]["hits"]["final"][0]["text"]
    assert engine.last_query_trace["decision"]["path"] == "answer"


def test_query_trace_includes_document_policy_source_from_request_context():
    from src.core.request_access import reset_request_access_context, set_request_access_context

    engine, _, _ = _make_query_engine()
    token = set_request_access_context(
        {
            "actor": "alice",
            "actor_source": "api_token",
            "actor_role": "engineer",
            "allowed_doc_tags": ("shared", "engineering"),
            "document_policy_source": "role_tags:engineer",
        }
    )
    try:
        result = engine.query("What is nominal voltage?")
    finally:
        reset_request_access_context(token)

    assert result.debug_trace["access"]["actor"] == "alice"
    assert result.debug_trace["access"]["actor_role"] == "engineer"
    assert result.debug_trace["access"]["document_policy_source"] == "role_tags:engineer"


def test_query_stream_attaches_debug_trace_on_success():
    engine, _, router = _make_query_engine(FakeConfig(mode="online"))
    engine.config.api.top_p = 0.91
    engine.config.api.presence_penalty = 0.3
    engine.config.api.frequency_penalty = 0.15
    router.query_stream.return_value = iter(
        [
            {"token": "Nominal voltage is 12V."},
            {
                "done": True,
                "tokens_in": 64,
                "tokens_out": 8,
                "model": "gpt-4o",
                "latency_ms": 90.0,
            },
        ]
    )

    events = list(engine.query_stream("What is nominal voltage?"))
    result = [e["result"] for e in events if e.get("done")][0]

    assert result.debug_trace is not None
    assert result.debug_trace["stream"] is True
    assert result.debug_trace["decision"]["path"] == "stream_answer"
    assert result.debug_trace["settings"]["backend"]["name"] == "api"
    assert abs(result.debug_trace["settings"]["backend"]["top_p"] - 0.91) < 1e-9
    assert abs(result.debug_trace["settings"]["backend"]["presence_penalty"] - 0.3) < 1e-9
    assert abs(result.debug_trace["settings"]["backend"]["frequency_penalty"] - 0.15) < 1e-9
    assert result.debug_trace["llm"]["model"] == "gpt-4o"


def test_grounded_retrieval_gate_block_attaches_trace():
    engine = _make_grounded_engine()
    engine.guard_enabled = True
    engine._guard_available = True

    result = engine.query("What is the hidden password?")

    assert result.debug_trace is not None
    assert result.debug_trace["decision"]["path"] == "retrieval_gate_blocked"
    assert result.debug_trace["grounding"]["blocked"] is True
    assert result.debug_trace["retrieval"]["counts"]["final_hits"] == 0


def test_query_trace_history_keeps_recent_entries():
    engine, _, _ = _make_query_engine()
    engine.query_trace_history_limit = 2

    first = engine.query("First question?")
    second = engine.query("Second question?")
    third = engine.query("Third question?")

    assert first.debug_trace["trace_id"]
    assert second.debug_trace["trace_id"]
    assert third.debug_trace["trace_id"]
    assert engine.last_query_trace["trace_id"] == third.debug_trace["trace_id"]
    assert [trace["query"] for trace in engine.recent_query_traces] == [
        "Second question?",
        "Third question?",
    ]
