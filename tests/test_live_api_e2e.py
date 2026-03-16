"""Live API end-to-end tests for Sprint 17 -- GPT-4o via OpenRouter.

These tests make REAL API calls and cost real tokens.
They are gated behind RUN_LIVE_API_TESTS=1 so they never run in CI
or during normal regression.

Usage:
    RUN_LIVE_API_TESTS=1 .venv/Scripts/python.exe -m pytest tests/test_live_api_e2e.py -v
"""

import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LIVE = os.getenv("RUN_LIVE_API_TESTS", "0") == "1"
SKIP_REASON = "Set RUN_LIVE_API_TESTS=1 to run live API tests (costs real tokens)"


def _resolve_creds():
    """Resolve API credentials; returns (creds, skip_reason_or_None)."""
    from src.security.credentials import resolve_credentials
    creds = resolve_credentials(use_cache=True)
    if not getattr(creds, "has_key", False):
        return creds, "No API key configured"
    if not getattr(creds, "endpoint", ""):
        return creds, "No API endpoint configured"
    return creds, None


def _make_online_config():
    """Build a real Config object in online mode."""
    from src.core.config import load_config
    config = load_config()
    config.mode = "online"
    return config


def _make_query_engine(config, creds):
    """Build a real QueryEngine wired to the live API."""
    from src.core.vector_store import VectorStore
    from src.core.embedder import Embedder
    from src.core.retriever import Retriever
    from src.core.query_engine import QueryEngine
    from src.core.llm_router import LLMRouter
    from src.core.network_gate import configure_gate

    configure_gate(
        mode="online",
        api_endpoint=creds.endpoint or "",
        allowed_prefixes=[],
    )

    vs = VectorStore(config)
    embedder = Embedder(config)
    retriever = Retriever(vs, embedder, config)
    router = LLMRouter(config, credentials=creds)
    engine = QueryEngine(config, retriever, router)
    return engine


# ============================================================================
# 17.2 -- Online Query Engine E2E
# ============================================================================

class TestOnlineQueryE2E:
    """Real GPT-4o query through the full RAG pipeline."""

    @pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
    def test_online_query_returns_real_answer(self):
        """Full pipeline: retrieve -> build prompt -> call GPT-4o -> answer."""
        creds, skip = _resolve_creds()
        if skip:
            pytest.skip(skip)

        config = _make_online_config()
        engine = _make_query_engine(config, creds)

        result = engine.query("What is the operating frequency range?")

        # Answer should exist and be substantive
        assert result.answer, "Expected a non-empty answer"
        assert len(result.answer) > 20, "Answer too short to be real"
        assert result.error is None or result.error == ""

        # Token accounting should be populated for online queries
        assert result.tokens_in > 0, "Expected nonzero tokens_in"
        assert result.tokens_out > 0, "Expected nonzero tokens_out"

        # Cost should be populated
        assert result.cost_usd > 0, "Expected nonzero cost_usd"

        # Should have used indexed chunks
        assert result.chunks_used > 0, "Expected chunks from index"

        # Mode should be online
        assert result.mode == "online"

        # Latency should be reasonable (under 60s)
        assert result.latency_ms < 60000, "Query took too long"

    @pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
    def test_online_query_has_sources(self):
        """Online query should return source citations from the index."""
        creds, skip = _resolve_creds()
        if skip:
            pytest.skip(skip)

        config = _make_online_config()
        engine = _make_query_engine(config, creds)

        result = engine.query("What are the calibration intervals?")

        assert result.sources, "Expected source citations"
        assert len(result.sources) >= 1
        # Each source should have a path
        for src in result.sources:
            assert "path" in src
            assert src["path"], "Source path should not be empty"


# ============================================================================
# 17.3 -- Cost Tracker Live Validation
# ============================================================================

class TestCostTrackerLive:
    """Verify cost tracker records real API events accurately."""

    @pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
    def test_cost_event_recorded_after_query(self):
        """A real online query should emit a cost event to the tracker."""
        creds, skip = _resolve_creds()
        if skip:
            pytest.skip(skip)

        from src.core.cost_tracker import get_cost_tracker

        config = _make_online_config()
        engine = _make_query_engine(config, creds)
        tracker = get_cost_tracker()

        # Record baseline
        before = tracker.get_summary()
        before_count = before.get("total_queries", 0)

        result = engine.query("How do leaders and managers differ?")

        # Cost from the query result
        assert result.cost_usd > 0, "Expected nonzero cost from API"
        assert result.tokens_in > 0
        assert result.tokens_out > 0

        # GPT-4o pricing sanity: input ~$2.50/1M, output ~$10/1M
        # A typical query uses ~2000 tokens in, ~200 out
        # Expected cost range: $0.001 - $0.05
        assert result.cost_usd < 0.10, "Cost suspiciously high"


# ============================================================================
# 17.4 -- FastAPI /query Live Smoke
# ============================================================================

class TestFastAPILiveSmoke:
    """Verify /query endpoint works with real API backend."""

    @pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
    def test_query_endpoint_returns_real_answer(self):
        """POST /query with a real question returns a real answer."""
        creds, skip = _resolve_creds()
        if skip:
            pytest.skip(skip)

        from src.api.server import app
        from src.api import state as api_state
        from src.core.config import load_config
        from src.core.network_gate import configure_gate
        from fastapi.testclient import TestClient

        config = load_config()
        config.mode = "online"
        api_state.config = config

        configure_gate(
            mode="online",
            api_endpoint=creds.endpoint or "",
            allowed_prefixes=[],
        )

        with TestClient(app) as client:
            resp = client.post("/query", json={
                "question": "What is the operating frequency range?",
            }, timeout=120)

            assert resp.status_code == 200
            data = resp.json()
            assert data.get("answer"), "Expected non-empty answer"
            assert data.get("chunks_used", 0) > 0
            assert data.get("mode") == "online"

    @pytest.mark.skipif(not LIVE, reason=SKIP_REASON)
    def test_status_reports_online_mode(self):
        """GET /status shows online mode when configured."""
        from src.api.server import app
        from src.api import state as api_state
        from src.core.config import load_config
        from fastapi.testclient import TestClient

        config = load_config()
        config.mode = "online"
        api_state.config = config

        with TestClient(app) as client:
            resp = client.get("/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("mode") == "online"
