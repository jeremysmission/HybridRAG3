# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the fastapi server area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Tests for the FastAPI REST API server endpoints (/health,
#       /query, /index, /config, /status, /mode)
# WHY:  The REST API is the integration point for external tools,
#       dashboards, and MCP clients. Each endpoint must return correct
#       status codes and JSON structure even when backends fail.
# HOW:  Uses FastAPI TestClient (in-process, no live server needed).
#       TestClient MUST be used with `with` context manager for the
#       lifespan to execute properly.
# USAGE: pytest tests/test_fastapi_server.py -v
# ===================================================================

import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment before any imports
os.environ.setdefault("HYBRIDRAG_DATA_DIR", "D:\\RAG Indexed Data")
os.environ.setdefault("HYBRIDRAG_INDEX_FOLDER", "D:\\RAG Source Data")
# RETIRED (Session 15): HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE no longer needed
# HuggingFace/torch removed. Embeddings served by Ollama.

from fastapi.testclient import TestClient
from src.api.server import app


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with lifespan context."""
    with TestClient(app) as c:
        yield c


# -------------------------------------------------------------------
# Health endpoint
# -------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_has_version(self, client):
        r = client.get("/health")
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data


# -------------------------------------------------------------------
# Status endpoint
# -------------------------------------------------------------------

class TestStatus:
    def test_status_returns_200(self, client):
        r = client.get("/status")
        assert r.status_code == 200

    def test_status_has_chunk_count(self, client):
        r = client.get("/status")
        data = r.json()
        assert "chunk_count" in data
        assert isinstance(data["chunk_count"], int)
        assert data["chunk_count"] >= 0

    def test_status_has_mode(self, client):
        r = client.get("/status")
        data = r.json()
        assert data["mode"] in ("offline", "online")

    def test_status_has_source_count(self, client):
        r = client.get("/status")
        data = r.json()
        assert "source_count" in data
        assert isinstance(data["source_count"], int)


# -------------------------------------------------------------------
# Config endpoint
# -------------------------------------------------------------------

class TestConfig:
    def test_config_returns_200(self, client):
        r = client.get("/config")
        assert r.status_code == 200

    def test_config_has_embedding_model(self, client):
        r = client.get("/config")
        data = r.json()
        assert "embedding_model" in data
        assert isinstance(data["embedding_model"], str)
        assert "embedding_dimension" in data
        assert isinstance(data["embedding_dimension"], int)

    def test_config_has_retrieval_settings(self, client):
        r = client.get("/config")
        data = r.json()
        assert "top_k" in data
        assert "min_score" in data
        assert "hybrid_search" in data


# -------------------------------------------------------------------
# Index status endpoint
# -------------------------------------------------------------------

class TestIndexStatus:
    def test_index_status_returns_200(self, client):
        r = client.get("/index/status")
        assert r.status_code == 200

    def test_index_status_not_active_by_default(self, client):
        r = client.get("/index/status")
        data = r.json()
        assert data["indexing_active"] is False


# -------------------------------------------------------------------
# Query endpoint
# -------------------------------------------------------------------

class TestQuery:
    def test_query_rejects_empty_question(self, client):
        r = client.post("/query", json={"question": ""})
        assert r.status_code == 422

    def test_query_rejects_missing_question(self, client):
        r = client.post("/query", json={})
        assert r.status_code == 422

    def test_query_accepts_valid_question(self, client):
        # Hermetic: mock query path so this test never depends on live LLM availability.
        from src.api.server import state
        from src.core.query_engine import QueryResult

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="HybridRAG is a local-first retrieval-augmented QA system.",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.91}],
                chunks_used=1,
                tokens_in=12,
                tokens_out=20,
                cost_usd=0.0,
                latency_ms=3.0,
                mode="offline",
                error=None,
            )
            r = client.post("/query", json={"question": "What is HybridRAG?"})
            assert r.status_code == 200
            data = r.json()
            assert "answer" in data
            assert "sources" in data
            assert "chunks_used" in data
            assert "latency_ms" in data
        finally:
            state.query_engine.query = original


# -------------------------------------------------------------------
# Mode endpoint
# -------------------------------------------------------------------

class TestMode:
    def test_mode_rejects_invalid(self, client):
        r = client.put("/mode", json={"mode": "turbo"})
        assert r.status_code == 422

    def test_mode_switch_to_offline(self, client):
        r = client.put("/mode", json={"mode": "offline"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "offline"


# -------------------------------------------------------------------
# Index start endpoint
# -------------------------------------------------------------------

class TestIndexStart:
    def test_index_rejects_bad_folder(self, client):
        r = client.post("/index", json={"source_folder": "/nonexistent/path"})
        assert r.status_code == 400


# -------------------------------------------------------------------
# Security controls (auth + rate limiting)
# -------------------------------------------------------------------

class TestSecurityControls:
    def test_query_auth_token_enforced_when_configured(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="ok", sources=[], chunks_used=0,
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                latency_ms=1.0, mode="offline", error=None,
            )
            denied = client.post("/query", json={"question": "x"})
            assert denied.status_code == 401

            allowed = client.post(
                "/query",
                json={"question": "x"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
        finally:
            state.query_engine.query = original
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_query_rate_limit_enforced(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        monkeypatch.setenv("HYBRIDRAG_RATE_QUERY_MAX", "1")
        monkeypatch.setenv("HYBRIDRAG_RATE_QUERY_WINDOW", "60")
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="ok", sources=[], chunks_used=0,
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                latency_ms=1.0, mode="offline", error=None,
            )
            first = client.post("/query", json={"question": "x"})
            assert first.status_code == 200
            second = client.post("/query", json={"question": "x"})
            assert second.status_code == 429
        finally:
            state.query_engine.query = original
            monkeypatch.delenv("HYBRIDRAG_RATE_QUERY_MAX", raising=False)
            monkeypatch.delenv("HYBRIDRAG_RATE_QUERY_WINDOW", raising=False)
