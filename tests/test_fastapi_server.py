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
import sqlite3
import sys
import time
import threading
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment before any imports
os.environ.setdefault("HYBRIDRAG_DATA_DIR", "D:\\RAG Indexed Data")
os.environ.setdefault("HYBRIDRAG_INDEX_FOLDER", "D:\\RAG Source Data")
os.environ["HYBRIDRAG_DEPLOYMENT_MODE"] = "development"
# RETIRED (Session 15): HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE no longer needed
# HuggingFace/torch removed. Embeddings served by Ollama.

from fastapi.testclient import TestClient
from src.api.server import app
from src.security.protected_data import HISTORY_PROTECTED_PREFIX


def _reset_query_activity_state() -> None:
    from src.api.server import state

    tracker = getattr(state, "query_activity", None)
    if tracker is not None:
        tracker.reset()


def _reset_network_audit_state(mode: str = "offline") -> None:
    from src.core.network_gate import get_gate

    gate = get_gate()
    gate.configure(mode)
    gate.clear_audit_log()


def _reset_query_queue_state(max_concurrent: int = 0, max_queue: int = 0) -> None:
    from src.api.server import state
    from src.api.query_queue import QueryQueueTracker

    state.query_queue = QueryQueueTracker(
        max_concurrent=max_concurrent,
        max_queue=max_queue,
    )
    state.query_queue.reset()


def _reset_auth_audit_state() -> None:
    from src.api.server import state

    tracker = getattr(state, "auth_audit", None)
    if tracker is not None:
        tracker.reset()


def _swap_conversation_thread_state(tmp_path):
    from src.api.server import state
    from src.api.query_threads import ConversationThreadStore

    original = getattr(state, "conversation_threads", None)
    state.conversation_threads = ConversationThreadStore(str(tmp_path / "query_history.sqlite3"))
    state.conversation_threads.reset()
    return original


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

    def test_status_exposes_deployment_identity(self, client):
        r = client.get("/status")
        data = r.json()
        assert data["deployment_mode"] == "development"
        assert isinstance(data["current_user"], str)
        assert data["current_user"]

    def test_status_exposes_auth_and_index_activity(self, client):
        r = client.get("/status")
        data = r.json()
        assert data["api_auth_required"] is False
        assert data["indexing_active"] is False
        assert data["indexing"]["active"] is False
        assert data["indexing"]["progress_pct"] == 0.0

    def test_status_reports_keyring_backed_shared_auth_requirement(self, client, monkeypatch):
        from src.security import shared_deployment_auth as shared_auth

        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", raising=False)
        monkeypatch.setattr(
            shared_auth,
            "_read_keyring",
            lambda name: "keyring-token"
            if name == shared_auth.SHARED_API_AUTH_TOKEN_KEYRING_NAME
            else None,
        )
        shared_auth.invalidate_shared_auth_cache()
        try:
            r = client.get("/status")
            data = r.json()
            assert data["api_auth_required"] is True
        finally:
            shared_auth.invalidate_shared_auth_cache()

    def test_status_exposes_network_audit_summary(self, client):
        r = client.get("/status")
        data = r.json()
        assert "network_audit" in data
        summary = data["network_audit"]
        assert summary["mode"] in ("offline", "online", "admin")
        assert isinstance(summary["total_checks"], int)
        assert isinstance(summary["allowed"], int)
        assert isinstance(summary["denied"], int)
        assert isinstance(summary["allowed_hosts"], list)
        assert isinstance(summary["unique_hosts_contacted"], list)

    def test_status_exposes_query_activity_summary(self, client):
        _reset_query_activity_state()
        _reset_query_queue_state()

        r = client.get("/status")
        data = r.json()
        summary = data["query_activity"]
        assert summary["active_queries"] == 0
        assert summary["recent_queries"] == 0
        assert summary["total_completed"] == 0
        assert summary["total_failed"] == 0
        assert summary["last_completed_at"] is None
        assert summary["last_error_at"] is None

    def test_status_exposes_query_queue_summary(self, client):
        _reset_query_queue_state(max_concurrent=2, max_queue=5)

        r = client.get("/status")
        data = r.json()
        summary = data["query_queue"]
        assert summary["enabled"] is True
        assert summary["max_concurrent"] == 2
        assert summary["max_queue"] == 5
        assert summary["active_queries"] == 0
        assert summary["waiting_queries"] == 0
        assert summary["available_slots"] == 2
        assert summary["saturated"] is False
        assert summary["total_started"] == 0
        assert summary["total_completed"] == 0
        assert summary["total_rejected"] == 0

    def test_server_uses_grounded_query_engine_runtime(self, client):
        from src.api.server import state
        from src.core.grounded_query_engine import GroundedQueryEngine

        assert isinstance(state.query_engine, GroundedQueryEngine)

    def test_status_exposes_live_indexing_snapshot(self, client):
        from src.api.server import state

        original_active = state.indexing_active
        original_progress = dict(state.index_progress)
        try:
            state.indexing_active = True
            state.index_progress.update(
                {
                    "files_processed": 3,
                    "files_total": 6,
                    "files_skipped": 1,
                    "files_errored": 0,
                    "current_file": "demo.pdf",
                    "start_time": time.time() - 12.6,
                }
            )
            r = client.get("/status")
            data = r.json()
            snapshot = data["indexing"]
            assert data["indexing_active"] is True
            assert snapshot["active"] is True
            assert snapshot["files_processed"] == 3
            assert snapshot["files_total"] == 6
            assert snapshot["files_skipped"] == 1
            assert snapshot["files_errored"] == 0
            assert snapshot["current_file"] == "demo.pdf"
            assert snapshot["progress_pct"] == 50.0
            assert snapshot["elapsed_seconds"] >= 12.0
        finally:
            state.indexing_active = original_active
            state.index_progress.clear()
            state.index_progress.update(original_progress)

    def test_status_exposes_latest_index_run_summary(self, client, monkeypatch):
        from src.api.models import LatestIndexRunSummary
        from src.api import routes as api_routes

        monkeypatch.setattr(
            api_routes,
            "_read_latest_index_run_summary",
            lambda _db_path: LatestIndexRunSummary(
                run_id="run-123",
                status="finished",
                started_at="2026-03-12T20:00:00Z",
                finished_at="2026-03-12T20:05:00Z",
                host="workstation",
                user="jerem",
                profile="demo",
            ),
        )

        r = client.get("/status")
        data = r.json()
        latest = data["latest_index_run"]
        assert latest["run_id"] == "run-123"
        assert latest["status"] == "finished"
        assert latest["host"] == "workstation"
        assert latest["profile"] == "demo"

    def test_status_exposes_index_schedule_summary(self, client):
        r = client.get("/status")
        data = r.json()
        summary = data["index_schedule"]
        assert isinstance(summary["enabled"], bool)
        assert isinstance(summary["interval_seconds"], int)
        assert isinstance(summary["source_folder"], str)
        assert isinstance(summary["indexing_active"], bool)
        assert isinstance(summary["due_now"], bool)
        assert isinstance(summary["last_status"], str)
        assert isinstance(summary["last_error"], str)
        assert isinstance(summary["last_trigger"], str)
        assert isinstance(summary["total_runs"], int)
        assert isinstance(summary["total_success"], int)
        assert isinstance(summary["total_failed"], int)


# -------------------------------------------------------------------
# Auth context endpoint
# -------------------------------------------------------------------

class TestAuthContext:
    def test_auth_context_defaults_to_open_anonymous(self, client):
        response = client.get("/auth/context")
        assert response.status_code == 200
        data = response.json()
        assert data["auth_required"] is False
        assert data["auth_mode"] == "open"
        assert data["actor"] == "anonymous"
        assert data["actor_source"] == "anonymous"
        assert data["actor_role"] == "viewer"
        assert data["actor_role_source"] == "default_role"
        assert data["allowed_doc_tags"] == ["shared"]
        assert data["document_policy_source"] == "default_policy:shared"
        assert isinstance(data["client_host"], str)
        assert data["client_host"]
        assert data["session_cookie_active"] is False
        assert data["session_issued_at"] is None
        assert data["session_expires_at"] is None
        assert data["session_ttl_seconds"] is None
        assert data["session_seconds_remaining"] is None
        assert data["proxy_identity_trusted"] is False
        assert data["trusted_proxy_identity_headers"] == []

    def test_auth_context_enforces_token_and_uses_label(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "ops-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        denied = client.get("/auth/context")
        assert denied.status_code == 401

        allowed = client.get(
            "/auth/context",
            headers={"Authorization": "Bearer test-token"},
        )
        assert allowed.status_code == 200
        data = allowed.json()
        assert data["auth_required"] is True
        assert data["auth_mode"] == "api_token"
        assert data["actor"] == "ops-dashboard"
        assert data["actor_source"] == "api_token"
        assert data["actor_role"] == "admin"
        assert data["actor_role_source"] == "role_map:ops-dashboard"
        assert data["allowed_doc_tags"] == ["*"]
        assert data["document_policy_source"] == "role_tags:admin"
        assert data["session_cookie_active"] is False
        assert data["session_issued_at"] is None
        assert data["session_expires_at"] is None
        assert data["session_seconds_remaining"] is None

    def test_auth_context_accepts_previous_api_token_during_rotation(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "current-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", "previous-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")

        allowed = client.get(
            "/auth/context",
            headers={"Authorization": "Bearer previous-token"},
        )

        assert allowed.status_code == 200
        data = allowed.json()
        assert data["auth_required"] is True
        assert data["auth_mode"] == "api_token"
        assert data["actor"] == "ops-dashboard"

    def test_auth_context_does_not_treat_previous_token_without_current_primary_as_authenticated(
        self, client, monkeypatch
    ):
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", "previous-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")

        response = client.get(
            "/auth/context",
            headers={"Authorization": "Bearer previous-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auth_required"] is False
        assert data["auth_mode"] == "open"
        assert data["actor"] == "anonymous"
        assert data["actor_source"] == "anonymous"

    def test_auth_context_accepts_keyring_backed_shared_api_token(self, client, monkeypatch):
        from src.security import shared_deployment_auth as shared_auth

        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", raising=False)
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")
        monkeypatch.setattr(
            shared_auth,
            "_read_keyring",
            lambda name: "keyring-token"
            if name == shared_auth.SHARED_API_AUTH_TOKEN_KEYRING_NAME
            else None,
        )
        shared_auth.invalidate_shared_auth_cache()
        try:
            denied = client.get("/auth/context")
            assert denied.status_code == 401

            allowed = client.get(
                "/auth/context",
                headers={"Authorization": "Bearer keyring-token"},
            )
            assert allowed.status_code == 200
            data = allowed.json()
            assert data["auth_required"] is True
            assert data["auth_mode"] == "api_token"
            assert data["actor"] == "ops-dashboard"
        finally:
            shared_auth.invalidate_shared_auth_cache()

    def test_production_startup_rejects_previous_token_without_current_primary(self, monkeypatch):
        from types import SimpleNamespace
        from src.api import server as api_server
        from src.security import shared_deployment_auth as shared_auth

        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", "previous-token")
        monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
        monkeypatch.setattr(
            api_server,
            "load_config",
            lambda _root: SimpleNamespace(
                mode="online",
                security=SimpleNamespace(deployment_mode="production"),
            ),
        )
        monkeypatch.setattr(api_server, "set_runtime_active_mode", lambda _mode: None)
        shared_auth.invalidate_shared_auth_cache()

        try:
            with pytest.raises(RuntimeError, match="no shared API token is configured"):
                with TestClient(app):
                    pass
        finally:
            shared_auth.invalidate_shared_auth_cache()

    def test_auth_context_ignores_proxy_identity_headers_when_not_trusted(self, client):
        response = client.get(
            "/auth/context",
            headers={"X-Forwarded-User": "alice"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_mode"] == "open"
        assert data["actor"] == "anonymous"
        assert data["actor_source"] == "anonymous"

    def test_auth_context_includes_browser_session_expiry(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=reviewer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "reviewer=shared,review")

        try:
            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200

            response = client.get("/auth/context")
            assert response.status_code == 200
            data = response.json()
            assert data["auth_mode"] == "session"
            assert data["session_cookie_active"] is True
            assert data["actor_role"] == "reviewer"
            assert data["actor_role_source"] == "role_map:shared-dashboard"
            assert data["allowed_doc_tags"] == ["shared", "review"]
            assert data["document_policy_source"] == "role_tags:reviewer"
            assert data["session_issued_at"]
            assert data["session_expires_at"]
            assert data["session_ttl_seconds"] >= 300
            assert 0 <= data["session_seconds_remaining"] <= data["session_ttl_seconds"]
        finally:
            client.cookies.clear()

    def test_auth_context_rejects_browser_session_before_invalidation_cutoff(self, client, monkeypatch):
        from src.api import browser_session
        from src.api.browser_session import SESSION_COOKIE_NAME, create_browser_session

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET", "browser-secret")
        monkeypatch.setattr(browser_session.time, "time", lambda: 1_700_000_000)
        stale_cookie = create_browser_session(actor="stale-user", actor_source="session_cookie")
        client.cookies.set(SESSION_COOKIE_NAME, stale_cookie)

        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE", "1700000001")
        monkeypatch.setattr(browser_session.time, "time", lambda: 1_700_000_010)

        response = client.get("/auth/context")

        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"

    def test_auth_context_rejects_proxy_identity_headers_without_proxy_secret(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "testclient")
        response = client.get(
            "/auth/context",
            headers={"X-Forwarded-User": "alice"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_required"] is False
        assert data["auth_mode"] == "open"
        assert data["actor"] == "anonymous"
        assert data["actor_source"] == "anonymous"
        assert data["proxy_identity_trusted"] is False
        assert data["trusted_proxy_identity_headers"] == []

    def test_auth_context_accepts_trusted_proxy_identity_headers_with_proxy_secret(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "testclient")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET", "proxy-secret")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "alice=engineer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "engineer=shared,engineering")
        response = client.get(
            "/auth/context",
            headers={
                "X-Forwarded-User": "alice",
                "X-HybridRAG-Proxy-Secret": "proxy-secret",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_required"] is False
        assert data["auth_mode"] == "proxy_header"
        assert data["actor"] == "alice"
        assert data["actor_source"] == "proxy_header:x-forwarded-user"
        assert data["actor_role"] == "engineer"
        assert data["actor_role_source"] == "role_map:alice"
        assert data["allowed_doc_tags"] == ["shared", "engineering"]
        assert data["document_policy_source"] == "role_tags:engineer"
        assert data["proxy_identity_trusted"] is True
        assert "x-forwarded-user" in data["trusted_proxy_identity_headers"]

    def test_auth_context_accepts_previous_proxy_identity_secret_during_rotation(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "testclient")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET", "proxy-secret-new")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS", "proxy-secret-old")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "alice=engineer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "engineer=shared,engineering")

        response = client.get(
            "/auth/context",
            headers={
                "X-Forwarded-User": "alice",
                "X-HybridRAG-Proxy-Secret": "proxy-secret-old",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auth_mode"] == "proxy_header"
        assert data["actor"] == "alice"
        assert data["proxy_identity_trusted"] is True

    def test_auth_context_ignores_proxy_identity_headers_from_untrusted_client(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "127.0.0.1")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET", "proxy-secret")
        response = client.get(
            "/auth/context",
            headers={
                "X-Forwarded-User": "mallory",
                "X-HybridRAG-Proxy-Secret": "proxy-secret",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auth_mode"] == "open"
        assert data["actor"] == "anonymous"
        assert data["actor_source"] == "anonymous"
        assert data["proxy_identity_trusted"] is False
        assert data["trusted_proxy_identity_headers"] == []

    def test_admin_data_reports_recent_unauthorized_request_in_security_activity(self, client, monkeypatch):
        client.cookies.clear()
        _reset_auth_audit_state()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_LABEL", raising=False)
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-token=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        denied = client.get("/auth/context")
        assert denied.status_code == 401

        response = client.get(
            "/admin/data",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        security = response.json()["security_activity"]
        assert security["recent_total"] >= 1
        assert security["recent_failures"] >= 1
        assert security["entries"][0]["event"] == "unauthorized_request"
        assert security["entries"][0]["path"] == "/auth/context"


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

        _reset_query_queue_state()
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

    def test_query_sets_request_access_context_for_engine(self, client, monkeypatch):
        from src.api import routes as api_routes
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.core.request_access import get_request_access_context

        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=restricted-reader")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "restricted-reader=shared,restricted")
        monkeypatch.setattr(state.config, "mode", "online")

        captured = {}
        original = state.query_engine.query
        try:
            def _fake_query(_question):
                captured.update(get_request_access_context())
                return QueryResult(
                    answer="ok",
                    sources=[],
                    chunks_used=0,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=1.0,
                    mode="online",
                    error=None,
                )

            state.query_engine.query = _fake_query
            response = client.post(
                "/query",
                json={"question": "Who can see this?"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 200
            assert captured["actor"] == "shared-dashboard"
            assert captured["actor_role"] == "restricted-reader"
            assert captured["allowed_doc_tags"] == ("shared", "restricted")
        finally:
            state.query_engine.query = original


class TestQueryActivity:
    def test_activity_endpoint_records_sync_query(self, client):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

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
            query_response = client.post("/query", json={"question": "What is HybridRAG?"})
            assert query_response.status_code == 200

            activity_response = client.get("/activity/queries")
            assert activity_response.status_code == 200
            data = activity_response.json()
            assert data["active_queries"] == 0
            assert data["total_completed"] == 1
            assert data["total_failed"] == 0
            entry = data["recent"][0]
            assert entry["question_text"] == "What is HybridRAG?"
            assert entry["question_preview"] == "What is HybridRAG?"
            assert entry["transport"] == "sync"
            assert entry["actor"] == "anonymous"
            assert entry["actor_source"] == "anonymous"
            assert entry["actor_role"] == "viewer"
            assert entry["allowed_doc_tags"] == ["shared"]
            assert entry["document_policy_source"] == "default_policy:shared"
            assert entry["status"] == "completed"
            assert entry["source_count"] == 1
            assert entry["chunks_used"] == 1
            assert entry["answer_preview"] == "HybridRAG is a local-first retrieval-augmented QA system."
            assert entry["source_paths"] == ["README.md"]
            assert entry["denied_hits"] == 0
            assert entry["error"] is None
            assert entry["completed_at"]
        finally:
            state.query_engine.query = original
            _reset_query_activity_state()

    def test_activity_endpoint_records_stream_query(self, client):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query_stream
        try:
            def _fake_stream(_q):
                yield {"phase": "searching"}
                yield {"token": "Answer part"}
                yield {
                    "done": True,
                    "result": QueryResult(
                        answer="Answer part",
                        sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.91}],
                        chunks_used=1,
                        tokens_in=10,
                        tokens_out=11,
                        cost_usd=0.0,
                        latency_ms=5.0,
                        mode="offline",
                        error=None,
                    ),
                }

            state.query_engine.query_stream = _fake_stream
            stream_response = client.post("/query/stream", json={"question": "Stream this"})
            assert stream_response.status_code == 200
            assert "event: done" in stream_response.text
            assert '"thread_id"' in stream_response.text

            activity_response = client.get("/activity/queries")
            assert activity_response.status_code == 200
            data = activity_response.json()
            assert data["active_queries"] == 0
            assert data["total_completed"] == 1
            entry = data["recent"][0]
            assert entry["question_text"] == "Stream this"
            assert entry["question_preview"] == "Stream this"
            assert entry["transport"] == "stream"
            assert entry["actor"] == "anonymous"
            assert entry["actor_source"] == "anonymous"
            assert entry["actor_role"] == "viewer"
            assert entry["allowed_doc_tags"] == ["shared"]
            assert entry["document_policy_source"] == "default_policy:shared"
            assert entry["status"] == "completed"
            assert entry["source_count"] == 1
            assert entry["chunks_used"] == 1
            assert entry["answer_preview"] == "Answer part"
            assert entry["source_paths"] == ["README.md"]
            assert entry["denied_hits"] == 0
        finally:
            state.query_engine.query_stream = original
            _reset_query_activity_state()

    def test_activity_endpoint_records_request_policy_and_denied_hit_count(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.core.request_access import get_request_access_context
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=reviewer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "reviewer=shared,review")
        monkeypatch.setattr(state.config, "mode", "online")

        original = state.query_engine.query
        captured = {}
        try:
            def _query(_q):
                captured.update(get_request_access_context())
                return QueryResult(
                    answer="Reviewed answer",
                    sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.91}],
                    chunks_used=1,
                    tokens_in=9,
                    tokens_out=14,
                    cost_usd=0.0,
                    latency_ms=4.0,
                    mode="online",
                    error=None,
                    debug_trace={
                        "retrieval": {
                            "access_control": {
                                "enabled": True,
                                "authorized_hits": 1,
                                "denied_hits": 2,
                            }
                        }
                    },
                )

            state.query_engine.query = _query
            query_response = client.post(
                "/query",
                json={"question": "What is review-only?"},
                headers={"Authorization": "Bearer test-token"},
            )
            assert query_response.status_code == 200
            assert captured["actor"] == "shared-dashboard"
            assert captured["actor_role"] == "reviewer"
            assert captured["allowed_doc_tags"] == ("shared", "review")
            assert captured["document_policy_source"] == "role_tags:reviewer"

            activity_response = client.get(
                "/activity/queries",
                headers={"Authorization": "Bearer test-token"},
            )
            assert activity_response.status_code == 200
            entry = activity_response.json()["recent"][0]
            assert entry["actor_role"] == "reviewer"
            assert entry["allowed_doc_tags"] == ["shared", "review"]
            assert entry["document_policy_source"] == "role_tags:reviewer"
            assert entry["denied_hits"] == 2
        finally:
            state.query_engine.query = original
            _reset_query_activity_state()

    def test_activity_endpoint_records_failed_query(self, client):
        from src.api.server import state
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query
        try:
            def _boom(_q):
                raise RuntimeError("boom")

            state.query_engine.query = _boom
            query_response = client.post("/query", json={"question": "Will this fail?"})
            assert query_response.status_code == 502

            activity_response = client.get("/activity/queries")
            assert activity_response.status_code == 200
            data = activity_response.json()
            assert data["active_queries"] == 0
            assert data["total_completed"] == 0
            assert data["total_failed"] == 1
            entry = data["recent"][0]
            assert entry["question_text"] == "Will this fail?"
            assert entry["question_preview"] == "Will this fail?"
            assert entry["transport"] == "sync"
            assert entry["actor"] == "anonymous"
            assert entry["actor_source"] == "anonymous"
            assert entry["actor_role"] == "viewer"
            assert entry["allowed_doc_tags"] == ["shared"]
            assert entry["document_policy_source"] == "default_policy:shared"
            assert entry["status"] == "error"
            assert entry["answer_preview"] is None
            assert entry["source_paths"] == []
            assert entry["denied_hits"] == 0
            assert "RuntimeError: boom" in entry["error"]
            assert entry["completed_at"]
        finally:
            state.query_engine.query = original
            _reset_query_activity_state()

    def test_activity_endpoint_ignores_spoofed_proxy_actor_without_proxy_secret(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "testclient")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=operator")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "operator=shared,ops")
        monkeypatch.setattr(state.config, "mode", "online")

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="ok",
                sources=[],
                chunks_used=0,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=2.0,
                mode="offline",
                error=None,
            )
            query_response = client.post(
                "/query",
                json={"question": "Who ran this?"},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Forwarded-User": "alice",
                },
            )
            assert query_response.status_code == 200

            activity_response = client.get(
                "/activity/queries",
                headers={"Authorization": "Bearer test-token"},
            )
            assert activity_response.status_code == 200
            data = activity_response.json()
            entry = data["recent"][0]
            assert entry["question_text"] == "Who ran this?"
            assert entry["actor"] == "shared-dashboard"
            assert entry["actor_source"] == "api_token"
            assert entry["actor_role"] == "operator"
            assert entry["allowed_doc_tags"] == ["shared", "ops"]
            assert entry["document_policy_source"] == "role_tags:operator"
            assert entry["answer_preview"] == "ok"
            assert entry["source_paths"] == []
            assert entry["denied_hits"] == 0
        finally:
            state.query_engine.query = original
            _reset_query_activity_state()

    def test_activity_endpoint_records_trusted_proxy_actor_with_proxy_secret(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "testclient")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET", "proxy-secret")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "alice=engineer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "engineer=shared,engineering")
        monkeypatch.setattr(state.config, "mode", "online")

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="ok",
                sources=[],
                chunks_used=0,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=2.0,
                mode="offline",
                error=None,
            )
            query_response = client.post(
                "/query",
                json={"question": "Who ran this?"},
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Forwarded-User": "alice",
                    "X-HybridRAG-Proxy-Secret": "proxy-secret",
                },
            )
            assert query_response.status_code == 200

            activity_response = client.get(
                "/activity/queries",
                headers={"Authorization": "Bearer test-token"},
            )
            assert activity_response.status_code == 200
            data = activity_response.json()
            entry = data["recent"][0]
            assert entry["question_text"] == "Who ran this?"
            assert entry["actor"] == "alice"
            assert entry["actor_source"] == "proxy_header:x-forwarded-user"
            assert entry["actor_role"] == "engineer"
            assert entry["allowed_doc_tags"] == ["shared", "engineering"]
            assert entry["document_policy_source"] == "role_tags:engineer"
            assert entry["answer_preview"] == "ok"
            assert entry["source_paths"] == []
            assert entry["denied_hits"] == 0
        finally:
            state.query_engine.query = original
            _reset_query_activity_state()


class TestConversationHistory:
    def test_query_creates_persisted_conversation_thread_and_history_endpoints(self, client, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="History answer",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.9}],
                chunks_used=1,
                tokens_in=4,
                tokens_out=6,
                cost_usd=0.0,
                latency_ms=2.5,
                mode="offline",
                error=None,
            )

            query_response = client.post("/query", json={"question": "Start a saved thread"})
            assert query_response.status_code == 200
            payload = query_response.json()
            assert payload["thread_id"]
            assert payload["turn_index"] == 1

            activity_response = client.get("/activity/queries")
            assert activity_response.status_code == 200
            recent = activity_response.json()["recent"][0]
            assert recent["thread_id"] == payload["thread_id"]
            assert recent["turn_index"] == 1

            history_response = client.get("/history/threads")
            assert history_response.status_code == 200
            history = history_response.json()
            assert history["total_threads"] == 1
            assert history["max_threads"] >= 1
            assert history["max_turns_per_thread"] >= 1
            assert history["threads"][0]["thread_id"] == payload["thread_id"]
            assert history["threads"][0]["turn_count"] == 1
            assert history["threads"][0]["last_status"] == "completed"

            detail_response = client.get(f"/history/threads/{payload['thread_id']}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["thread"]["thread_id"] == payload["thread_id"]
            assert detail["turns"][0]["question_text"] == "Start a saved thread"
            assert detail["turns"][0]["answer_text"] == "History answer"
            assert detail["turns"][0]["source_paths"] == ["README.md"]
            assert detail["turns"][0]["sources"][0]["path"] == "README.md"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_query_can_append_to_existing_conversation_thread(self, client, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda question: QueryResult(
                answer=f"Answer for {question}",
                sources=[],
                chunks_used=0,
                tokens_in=3,
                tokens_out=5,
                cost_usd=0.0,
                latency_ms=1.5,
                mode="offline",
                error=None,
            )

            first = client.post("/query", json={"question": "Thread opener"})
            assert first.status_code == 200
            thread_id = first.json()["thread_id"]
            assert thread_id

            second = client.post(
                "/query",
                json={"question": "Thread follow-up", "thread_id": thread_id},
            )
            assert second.status_code == 200
            second_payload = second.json()
            assert second_payload["thread_id"] == thread_id
            assert second_payload["turn_index"] == 2

            detail_response = client.get(f"/history/threads/{thread_id}")
            assert detail_response.status_code == 200
            turns = detail_response.json()["turns"]
            assert [turn["question_text"] for turn in turns] == [
                "Thread opener",
                "Thread follow-up",
            ]
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_follow_up_query_uses_prior_thread_context(self, client, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda question: QueryResult(
                answer=f"Answer for {question}",
                sources=[],
                chunks_used=0,
                tokens_in=3,
                tokens_out=5,
                cost_usd=0.0,
                latency_ms=1.5,
                mode="offline",
                error=None,
            )

            first = client.post("/query", json={"question": "Original thread question"})
            assert first.status_code == 200
            thread_id = first.json()["thread_id"]
            assert thread_id

            captured = {}

            def _capture(question):
                captured["question"] = question
                return QueryResult(
                    answer="Follow-up answer",
                    sources=[],
                    chunks_used=0,
                    tokens_in=4,
                    tokens_out=6,
                    cost_usd=0.0,
                    latency_ms=2.0,
                    mode="offline",
                    error=None,
                )

            state.query_engine.query = _capture
            second = client.post(
                "/query",
                json={"question": "What changed next?", "thread_id": thread_id},
            )
            assert second.status_code == 200
            assert "Conversation context from the same thread:" in captured["question"]
            assert "Original thread question" in captured["question"]
            assert "What changed next?" in captured["question"]
            assert "Answer the current follow-up using retrieved corpus evidence." in captured["question"]

            detail = client.get(f"/history/threads/{thread_id}")
            assert detail.status_code == 200
            assert detail.json()["turns"][1]["question_text"] == "What changed next?"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_follow_up_stream_query_uses_prior_thread_context(self, client, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        original_stream = state.query_engine.query_stream
        try:
            state.query_engine.query = lambda question: QueryResult(
                answer=f"Answer for {question}",
                sources=[],
                chunks_used=0,
                tokens_in=3,
                tokens_out=5,
                cost_usd=0.0,
                latency_ms=1.5,
                mode="offline",
                error=None,
            )

            first = client.post("/query", json={"question": "Start stream thread"})
            assert first.status_code == 200
            thread_id = first.json()["thread_id"]
            assert thread_id

            captured = {}

            def _fake_stream(question):
                captured["question"] = question
                yield {"phase": "searching"}
                yield {
                    "done": True,
                    "result": QueryResult(
                        answer="Stream follow-up answer",
                        sources=[],
                        chunks_used=0,
                        tokens_in=4,
                        tokens_out=6,
                        cost_usd=0.0,
                        latency_ms=2.0,
                        mode="offline",
                        error=None,
                    ),
                }

            state.query_engine.query_stream = _fake_stream
            second = client.post(
                "/query/stream",
                json={"question": "Keep streaming", "thread_id": thread_id},
            )
            assert second.status_code == 200
            assert "event: done" in second.text
            assert '"thread_id"' in second.text
            assert "Start stream thread" in captured["question"]
            assert "Keep streaming" in captured["question"]
        finally:
            state.query_engine.query = original_query
            state.query_engine.query_stream = original_stream
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_query_rejects_unknown_conversation_thread_id(self, client, tmp_path):
        from src.api.server import state
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            def _should_not_run(_question):
                raise AssertionError("query engine should not run for unknown thread ids")

            state.query_engine.query = _should_not_run
            response = client.post(
                "/query",
                json={"question": "Missing thread", "thread_id": "missing-thread"},
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Conversation thread not found"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_failed_query_is_persisted_in_conversation_history(self, client, tmp_path):
        from src.api.server import state
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            def _boom(_question):
                raise RuntimeError("boom")

            state.query_engine.query = _boom
            response = client.post("/query", json={"question": "Record the failure"})
            assert response.status_code == 502

            history = client.get("/history/threads")
            assert history.status_code == 200
            thread_id = history.json()["threads"][0]["thread_id"]
            assert history.json()["threads"][0]["last_status"] == "error"

            detail = client.get(f"/history/threads/{thread_id}")
            assert detail.status_code == 200
            turn = detail.json()["turns"][0]
            assert turn["status"] == "error"
            assert "RuntimeError: boom" in turn["error"]
            assert turn["question_text"] == "Record the failure"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_conversation_history_export_endpoint_returns_attachment(self, client, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Export me",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.9}],
                chunks_used=1,
                tokens_in=4,
                tokens_out=6,
                cost_usd=0.0,
                latency_ms=2.5,
                mode="offline",
                error=None,
            )
            query_response = client.post("/query", json={"question": "Export this thread"})
            assert query_response.status_code == 200
            thread_id = query_response.json()["thread_id"]
            assert thread_id

            export_response = client.get(f"/history/threads/{thread_id}/export")
            assert export_response.status_code == 200
            assert "attachment;" in export_response.headers["content-disposition"]
            payload = export_response.json()
            assert payload["thread"]["thread_id"] == thread_id
            assert payload["turns"][0]["question_text"] == "Export this thread"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_query_persists_encrypted_conversation_history_when_key_configured(self, client, monkeypatch, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-secret")

        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        db_path = tmp_path / "query_history.sqlite3"
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Encrypted answer",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.9}],
                chunks_used=1,
                tokens_in=4,
                tokens_out=6,
                cost_usd=0.0,
                latency_ms=2.5,
                mode="online",
                error=None,
            )
            query_response = client.post("/query", json={"question": "Encrypt this thread"})
            assert query_response.status_code == 200
            thread_id = query_response.json()["thread_id"]
            assert thread_id

            con = sqlite3.connect(str(db_path))
            try:
                row = con.execute(
                    """
                    SELECT question_text, answer_text, source_paths_json, sources_json
                    FROM conversation_turns
                    WHERE thread_id = ? AND turn_index = 1
                    """,
                    (thread_id,),
                ).fetchone()
            finally:
                con.close()

            assert row is not None
            assert str(row[0]).startswith(HISTORY_PROTECTED_PREFIX)
            assert str(row[1]).startswith(HISTORY_PROTECTED_PREFIX)
            assert str(row[2]).startswith(HISTORY_PROTECTED_PREFIX)
            assert str(row[3]).startswith(HISTORY_PROTECTED_PREFIX)
            assert "Encrypt this thread" not in str(row[0])
            assert "Encrypted answer" not in str(row[1])

            detail_response = client.get(f"/history/threads/{thread_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["turns"][0]["question_text"] == "Encrypt this thread"
            assert detail["turns"][0]["answer_text"] == "Encrypted answer"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()

    def test_history_endpoint_reports_encrypted_data_without_key(self, client, monkeypatch, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state()
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()
        monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-secret")

        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Encrypted answer",
                sources=[],
                chunks_used=0,
                tokens_in=4,
                tokens_out=6,
                cost_usd=0.0,
                latency_ms=2.5,
                mode="online",
                error=None,
            )
            query_response = client.post("/query", json={"question": "Lock this history"})
            assert query_response.status_code == 200

            monkeypatch.delenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", raising=False)
            monkeypatch.delenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS", raising=False)

            history_response = client.get("/history/threads")
            assert history_response.status_code == 503
            assert "encrypted at rest" in history_response.json()["detail"]
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads
            _reset_query_activity_state()


class TestNetworkActivity:
    def test_network_activity_endpoint_returns_recent_entries(self, client):
        from src.core.network_gate import NetworkBlockedError, get_gate

        _reset_network_audit_state()
        gate = get_gate()

        gate.check_allowed(
            "http://127.0.0.1:11434/api/generate",
            purpose="ollama_query",
            caller="pytest",
        )
        with pytest.raises(NetworkBlockedError):
            gate.check_allowed(
                "https://example.com/v1/chat/completions",
                purpose="api_query",
                caller="pytest",
            )

        response = client.get("/activity/network?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "offline"
        assert data["total_checks"] == 2
        assert data["allowed"] == 1
        assert data["denied"] == 1
        assert data["unique_hosts_contacted"] == ["127.0.0.1"]
        assert len(data["entries"]) == 2
        newest = data["entries"][0]
        assert newest["host"] == "example.com"
        assert newest["allowed"] is False
        assert newest["reason"] == "offline_blocks_internet"
        assert newest["caller"] == "pytest"
        assert newest["timestamp_iso"]
        older = data["entries"][1]
        assert older["host"] == "127.0.0.1"
        assert older["allowed"] is True

    def test_network_activity_endpoint_honors_limit(self, client):
        from src.core.network_gate import get_gate

        _reset_network_audit_state()
        gate = get_gate()
        gate.check_allowed("http://127.0.0.1:11434/api/generate", purpose="one", caller="pytest")
        gate.check_allowed("http://localhost:11434/api/tags", purpose="two", caller="pytest")

        response = client.get("/activity/network?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert data["total_checks"] == 2
        assert len(data["entries"]) == 1
        assert data["entries"][0]["purpose"] == "two"


class TestQueryQueue:
    def test_query_queue_endpoint_returns_summary(self, client):
        _reset_query_queue_state(max_concurrent=3, max_queue=4)

        response = client.get("/activity/query-queue")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["max_concurrent"] == 3
        assert data["max_queue"] == 4
        assert data["active_queries"] == 0
        assert data["waiting_queries"] == 0
        assert data["available_slots"] == 3
        assert data["saturated"] is False

    def test_query_queue_endpoint_reflects_active_query(self, client):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_activity_state()
        _reset_query_queue_state(max_concurrent=1, max_queue=1)
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        entered = threading.Event()
        release = threading.Event()
        result_holder = {}

        original = state.query_engine.query
        try:
            def _blocked_query(_q):
                entered.set()
                release.wait(timeout=5.0)
                return QueryResult(
                    answer="ok",
                    sources=[],
                    chunks_used=0,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=1.0,
                    mode="offline",
                    error=None,
                )

            state.query_engine.query = _blocked_query

            def _run_request():
                result_holder["response"] = client.post("/query", json={"question": "Hold"})

            thread = threading.Thread(target=_run_request, daemon=True)
            thread.start()
            assert entered.wait(timeout=5.0)

            queue_response = client.get("/activity/query-queue")
            assert queue_response.status_code == 200
            data = queue_response.json()
            assert data["active_queries"] == 1
            assert data["available_slots"] == 0
            assert data["saturated"] is True

            release.set()
            thread.join(timeout=5.0)
            assert result_holder["response"].status_code == 200
        finally:
            release.set()
            state.query_engine.query = original
            _reset_query_activity_state()
            _reset_query_queue_state()


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

    def test_mode_rejects_offline_switch_for_shared_deployment(self, client, monkeypatch):
        from src.api.server import state
        from src.api import routes as api_routes

        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setattr(state.config, "mode", "online")
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        persisted_modes = []
        monkeypatch.setattr(api_routes, "_update_yaml_mode", lambda mode: persisted_modes.append(mode))

        response = client.put(
            "/mode",
            json={"mode": "offline"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 409
        assert "cannot enter offline mode" in response.json()["detail"]
        assert state.config.mode == "online"
        assert persisted_modes == []

    def test_mode_switch_updates_live_mode_env(self, client, monkeypatch):
        from src.api.server import state
        from src.api import routes as api_routes

        monkeypatch.delenv("HYBRIDRAG_ACTIVE_MODE", raising=False)
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        persisted_modes = []
        monkeypatch.setattr(api_routes, "_update_yaml_mode", lambda mode: persisted_modes.append(mode))

        original_mode = state.config.mode
        original_endpoint = state.config.api.endpoint
        try:
            state.config.mode = "offline"
            state.config.api.endpoint = "https://example.test/v1/chat/completions"

            online = client.put("/mode", json={"mode": "online"})
            assert online.status_code == 200
            assert os.environ["HYBRIDRAG_ACTIVE_MODE"] == "online"

            with api_routes._RATE_LOCK:
                api_routes._RATE_STATE.clear()

            offline = client.put("/mode", json={"mode": "offline"})
            assert offline.status_code == 200
            assert os.environ["HYBRIDRAG_ACTIVE_MODE"] == "offline"
            assert persisted_modes == ["online", "offline"]
        finally:
            state.config.mode = original_mode
            state.config.api.endpoint = original_endpoint
            monkeypatch.delenv("HYBRIDRAG_ACTIVE_MODE", raising=False)


# -------------------------------------------------------------------
# Index start endpoint
# -------------------------------------------------------------------

class TestIndexStart:
    def test_index_rejects_bad_folder(self, client):
        r = client.post("/index", json={"source_folder": "/nonexistent/path"})
        assert r.status_code == 400


class TestAdminIndexControl:
    def test_admin_index_stop_returns_conflict_when_idle(self, client):
        from src.api.server import state

        original_active = state.indexing_active
        original_thread = state.indexing_thread
        was_set = state.indexing_stop_event.is_set()
        try:
            state.indexing_active = False
            state.indexing_thread = None
            state.indexing_stop_event.clear()

            response = client.post("/admin/index/stop")

            assert response.status_code == 409
            assert response.json()["detail"] == "No active indexing job to stop."
            assert state.indexing_stop_event.is_set() is False
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread
            if was_set:
                state.indexing_stop_event.set()
            else:
                state.indexing_stop_event.clear()

    def test_admin_freshness_recheck_forces_immediate_snapshot_refresh(self, client, monkeypatch):
        from src.api import web_dashboard as dashboard_routes
        from src.api.models import AdminContentFreshnessResponse

        monkeypatch.setattr(
            dashboard_routes,
            "_refresh_admin_content_freshness_response",
            lambda: AdminContentFreshnessResponse(
                source_folder=r"D:\HybridRAG3\data\source",
                source_exists=True,
                total_indexable_files=14,
                latest_source_update_at="2026-03-13T05:40:00Z",
                latest_source_path=r"D:\HybridRAG3\data\source\latest.pdf",
                last_index_started_at="2026-03-13T04:00:00Z",
                last_index_finished_at="2026-03-13T04:15:00Z",
                last_index_status="completed",
                files_newer_than_index=3,
                freshness_age_hours=1.8,
                warn_after_hours=24,
                stale=True,
                summary="3 files changed after the last index run.",
            ),
        )

        response = client.post("/admin/freshness/recheck")

        assert response.status_code == 200
        data = response.json()
        assert data["total_indexable_files"] == 14
        assert data["files_newer_than_index"] == 3
        assert data["stale"] is True
        assert data["summary"] == "3 files changed after the last index run."

    def test_admin_reindex_if_stale_starts_maintenance_run(self, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import AdminContentFreshnessResponse
        from src.api.server import state

        original_active = state.indexing_active
        original_thread = state.indexing_thread
        try:
            state.indexing_active = False
            state.indexing_thread = None
            monkeypatch.setattr(
                api_routes,
                "_build_admin_content_freshness_response",
                lambda: AdminContentFreshnessResponse(
                    source_folder=r"D:\HybridRAG3\data\source",
                    source_exists=True,
                    total_indexable_files=12,
                    latest_source_update_at="2026-03-13T05:30:00Z",
                    latest_source_path=r"D:\HybridRAG3\data\source\latest.pdf",
                    last_index_started_at="2026-03-13T04:00:00Z",
                    last_index_finished_at="2026-03-13T04:15:00Z",
                    last_index_status="completed",
                    files_newer_than_index=2,
                    freshness_age_hours=1.5,
                    warn_after_hours=24,
                    stale=True,
                    summary="2 files changed after the last index run.",
                ),
            )

            captured = {}

            def _fake_start(_state, source_folder, *, on_complete=None, trigger="manual"):
                captured["source_folder"] = source_folder
                captured["trigger"] = trigger
                captured["has_callback"] = on_complete is not None
                return True

            monkeypatch.setattr(api_routes, "start_background_indexing", _fake_start)

            response = api_routes._request_admin_reindex_if_stale()

            assert response.ok is True
            assert response.indexing_active is True
            assert response.stop_requested is False
            assert response.message == "Freshness maintenance run started."
            assert captured["source_folder"] == r"D:\HybridRAG3\data\source"
            assert captured["trigger"] == "maintenance"
            assert captured["has_callback"] is False
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread

    def test_admin_reindex_if_stale_returns_noop_when_content_is_fresh(self, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import AdminContentFreshnessResponse
        from src.api.server import state

        original_active = state.indexing_active
        original_thread = state.indexing_thread
        try:
            state.indexing_active = False
            state.indexing_thread = None
            monkeypatch.setattr(
                api_routes,
                "_build_admin_content_freshness_response",
                lambda: AdminContentFreshnessResponse(
                    source_folder=r"D:\HybridRAG3\data\source",
                    source_exists=True,
                    total_indexable_files=12,
                    latest_source_update_at="2026-03-13T05:30:00Z",
                    latest_source_path=r"D:\HybridRAG3\data\source\latest.pdf",
                    last_index_started_at="2026-03-13T04:00:00Z",
                    last_index_finished_at="2026-03-13T04:15:00Z",
                    last_index_status="completed",
                    files_newer_than_index=0,
                    freshness_age_hours=0.5,
                    warn_after_hours=24,
                    stale=False,
                    summary="Indexed content is up to date with the current source tree.",
                ),
            )
            monkeypatch.setattr(
                api_routes,
                "start_background_indexing",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("maintenance run should not start when content is already fresh")
                ),
            )

            response = api_routes._request_admin_reindex_if_stale()

            assert response.ok is True
            assert response.indexing_active is False
            assert response.stop_requested is False
            assert response.message == "Content is already fresh; no maintenance run was started."
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread

    def test_admin_freshness_recheck_helper_clears_cache_before_rebuild(self, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import AdminContentFreshnessResponse

        calls = []

        monkeypatch.setattr(
            api_routes,
            "clear_content_freshness_cache",
            lambda: calls.append("clear"),
        )
        monkeypatch.setattr(
            api_routes,
            "_build_admin_content_freshness_response",
            lambda: calls.append("build") or AdminContentFreshnessResponse(
                source_folder=r"D:\HybridRAG3\data\source",
                source_exists=True,
                total_indexable_files=12,
                latest_source_update_at="2026-03-13T05:30:00Z",
                latest_source_path=r"D:\HybridRAG3\data\source\latest.pdf",
                last_index_started_at="2026-03-13T04:00:00Z",
                last_index_finished_at="2026-03-13T04:15:00Z",
                last_index_status="completed",
                files_newer_than_index=2,
                freshness_age_hours=1.5,
                warn_after_hours=24,
                stale=True,
                summary="2 files changed after the last index run.",
            ),
        )

        response = api_routes._refresh_admin_content_freshness_response()

        assert calls == ["clear", "build"]
        assert response.files_newer_than_index == 2
        assert response.summary == "2 files changed after the last index run."

    def test_admin_index_stop_sets_stop_event_for_active_job(self, client):
        from src.api.server import state

        original_active = state.indexing_active
        original_thread = state.indexing_thread
        was_set = state.indexing_stop_event.is_set()
        try:
            state.indexing_active = True
            state.indexing_thread = None
            state.indexing_stop_event.clear()

            response = client.post("/admin/index/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["stop_requested"] is True
            assert data["indexing_active"] is True
            assert state.indexing_stop_event.is_set() is True
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread
            if was_set:
                state.indexing_stop_event.set()
            else:
                state.indexing_stop_event.clear()


class TestStatusHelpers:
    def test_read_latest_index_run_summary_returns_none_without_table(self, tmp_path):
        from src.api import routes as api_routes

        db_path = tmp_path / "empty.sqlite3"
        sqlite3.connect(str(db_path)).close()

        assert api_routes._read_latest_index_run_summary(str(db_path)) is None

    def test_read_latest_index_run_summary_reads_latest_row(self, tmp_path):
        from src.api import routes as api_routes

        db_path = tmp_path / "runs.sqlite3"
        con = sqlite3.connect(str(db_path))
        try:
            con.execute(
                """
                CREATE TABLE index_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    host TEXT NOT NULL,
                    user TEXT NOT NULL,
                    project_root TEXT,
                    data_dir TEXT,
                    source_dir TEXT,
                    profile TEXT,
                    notes TEXT
                )
                """
            )
            con.execute(
                """
                INSERT INTO index_runs (
                    run_id, created_at, started_at, finished_at, status,
                    host, user, project_root, data_dir, source_dir, profile, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-001",
                    "2026-03-12T19:00:00Z",
                    "2026-03-12T19:00:00Z",
                    "2026-03-12T19:10:00Z",
                    "finished",
                    "node-a",
                    "alice",
                    "",
                    "",
                    "",
                    "baseline",
                    "",
                ),
            )
            con.execute(
                """
                INSERT INTO index_runs (
                    run_id, created_at, started_at, finished_at, status,
                    host, user, project_root, data_dir, source_dir, profile, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run-002",
                    "2026-03-12T20:00:00Z",
                    "2026-03-12T20:00:00Z",
                    None,
                    "running",
                    "node-b",
                    "bob",
                    "",
                    "",
                    "",
                    "demo",
                    "",
                ),
            )
            con.commit()
        finally:
            con.close()

        latest = api_routes._read_latest_index_run_summary(str(db_path))
        assert latest is not None
        assert latest.run_id == "run-002"
        assert latest.status == "running"
        assert latest.host == "node-b"
        assert latest.user == "bob"
        assert latest.profile == "demo"
        assert latest.finished_at is None


# -------------------------------------------------------------------
# Security controls (auth + rate limiting)
# -------------------------------------------------------------------

class TestSecurityControls:
    def test_query_auth_token_enforced_when_configured(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_queue_state()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setattr(state.config, "mode", "online")
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

    def test_query_rejects_offline_mode_when_shared_deployment_enabled(self, client, monkeypatch):
        from src.api.server import state
        from src.api import routes as api_routes

        _reset_query_queue_state()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setattr(state.config, "mode", "offline")
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query
        try:
            def _should_not_run(_question):
                raise AssertionError("query engine should not run while shared deployment is offline")

            state.query_engine.query = _should_not_run

            response = client.post(
                "/query",
                json={"question": "x"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 503
            assert "requires online mode" in response.json()["detail"]
        finally:
            state.query_engine.query = original
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_query_activity_auth_token_enforced_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        try:
            denied = client.get("/activity/queries")
            assert denied.status_code == 401

            allowed = client.get(
                "/activity/queries",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
        finally:
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_network_activity_auth_token_enforced_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        try:
            denied = client.get("/activity/network")
            assert denied.status_code == 401

            allowed = client.get(
                "/activity/network",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
        finally:
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_query_queue_auth_token_enforced_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        try:
            denied = client.get("/activity/query-queue")
            assert denied.status_code == 401

            allowed = client.get(
                "/activity/query-queue",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
        finally:
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_admin_index_stop_auth_token_enforced_when_configured(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        original_active = state.indexing_active
        original_thread = state.indexing_thread
        was_set = state.indexing_stop_event.is_set()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-admin=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        try:
            state.indexing_active = True
            state.indexing_thread = None
            state.indexing_stop_event.clear()

            denied = client.post("/admin/index/stop")
            assert denied.status_code == 401

            allowed = client.post(
                "/admin/index/stop",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
            assert allowed.json()["stop_requested"] is True
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread
            if was_set:
                state.indexing_stop_event.set()
            else:
                state.indexing_stop_event.clear()
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_admin_reindex_if_stale_auth_token_enforced_when_configured(self, client, monkeypatch):
        from src.api.models import AdminIndexControlResponse
        from src.api import web_dashboard as dashboard_routes

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-admin=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        monkeypatch.setattr(
            dashboard_routes,
            "_request_admin_reindex_if_stale",
            lambda: AdminIndexControlResponse(
                ok=True,
                message="Freshness maintenance run started.",
                indexing_active=True,
                stop_requested=False,
            ),
        )
        try:
            denied = client.post("/admin/index/reindex-if-stale")
            assert denied.status_code == 401

            allowed = client.post(
                "/admin/index/reindex-if-stale",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
            assert allowed.json()["message"] == "Freshness maintenance run started."
        finally:
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_admin_freshness_recheck_auth_token_enforced_when_configured(self, client, monkeypatch):
        from src.api.models import AdminContentFreshnessResponse
        from src.api import web_dashboard as dashboard_routes

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-admin=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        monkeypatch.setattr(
            dashboard_routes,
            "_refresh_admin_content_freshness_response",
            lambda: AdminContentFreshnessResponse(
                source_folder=r"D:\HybridRAG3\data\source",
                source_exists=True,
                total_indexable_files=14,
                latest_source_update_at="2026-03-13T05:40:00Z",
                latest_source_path=r"D:\HybridRAG3\data\source\latest.pdf",
                last_index_started_at="2026-03-13T04:00:00Z",
                last_index_finished_at="2026-03-13T04:15:00Z",
                last_index_status="completed",
                files_newer_than_index=3,
                freshness_age_hours=1.8,
                warn_after_hours=24,
                stale=True,
                summary="3 files changed after the last index run.",
            ),
        )
        try:
            denied = client.post("/admin/freshness/recheck")
            assert denied.status_code == 401

            allowed = client.post(
                "/admin/freshness/recheck",
                headers={"Authorization": "Bearer test-token"},
            )
            assert allowed.status_code == 200
            assert allowed.json()["summary"] == "3 files changed after the last index run."
        finally:
            monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

    def test_query_rate_limit_enforced(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult
        from src.api import routes as api_routes

        _reset_query_queue_state()
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


def test_admin_schedule_snapshot_reports_current_runner_state(client):
    from src.api.index_schedule import IndexScheduleTracker
    from src.api import routes as api_routes
    from src.api.server import state

    original_schedule = getattr(state, "index_schedule", None)
    original_active = state.indexing_active
    try:
        schedule = IndexScheduleTracker(interval_seconds=600, source_folder=r"D:\HybridRAG3\data\source")
        schedule.note_run_started(now=200.0)
        schedule.note_run_finished(success=True, now=240.0)
        state.index_schedule = schedule
        state.indexing_active = False

        snapshot = api_routes._build_admin_index_schedule_response()

        assert snapshot.enabled is True
        assert snapshot.interval_seconds == 600
        assert snapshot.last_status == "completed"
        assert snapshot.total_runs == 1
        assert snapshot.total_success == 1
        assert snapshot.total_failed == 0
        assert snapshot.source_folder == r"D:\HybridRAG3\data\source"
        assert snapshot.next_run_at is not None
    finally:
        state.index_schedule = original_schedule
        state.indexing_active = original_active


def test_admin_freshness_snapshot_reports_changed_files(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from src.api import routes as api_routes
    from src.api.models import LatestIndexRunSummary

    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    older = source_dir / "older.md"
    newer = source_dir / "newer.md"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    os.utime(older, (datetime(2026, 3, 13, 1, 0, tzinfo=timezone.utc).timestamp(),) * 2)
    os.utime(newer, (datetime(2026, 3, 13, 5, 0, tzinfo=timezone.utc).timestamp(),) * 2)

    fake_state = SimpleNamespace(
        config=SimpleNamespace(
            paths=SimpleNamespace(source_folder=str(source_dir), database=":memory:"),
            indexing=SimpleNamespace(supported_extensions=[".md"], excluded_dirs=[]),
        )
    )
    monkeypatch.setattr(api_routes, "_state", lambda: fake_state)
    monkeypatch.setattr(
        api_routes,
        "_read_latest_index_run_summary",
        lambda _db_path: LatestIndexRunSummary(
            run_id="run-1",
            status="finished",
            started_at="2026-03-13T04:00:00Z",
            finished_at="2026-03-13T04:15:00Z",
            host="workstation",
            user="jerem",
            profile="shared",
        ),
    )
    monkeypatch.setenv("HYBRIDRAG_INDEX_FRESHNESS_WARN_HOURS", "12")

    snapshot = api_routes._build_admin_content_freshness_response()

    assert snapshot.source_exists is True
    assert snapshot.source_folder == str(source_dir)
    assert snapshot.total_indexable_files == 2
    assert snapshot.files_newer_than_index == 1
    assert snapshot.warn_after_hours == 12
    assert snapshot.stale is True
    assert snapshot.latest_source_path.endswith("newer.md")
    assert "changed after the last index run" in snapshot.summary
