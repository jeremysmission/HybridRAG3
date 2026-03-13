# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the browser dashboard/session area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================

import os
import sys

import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("HYBRIDRAG_DATA_DIR", "D:\\RAG Indexed Data")
os.environ.setdefault("HYBRIDRAG_INDEX_FOLDER", "D:\\RAG Source Data")
os.environ["HYBRIDRAG_DEPLOYMENT_MODE"] = "development"

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

from src.api.browser_session import SESSION_COOKIE_NAME
from src.api.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_browser_login_rate_state():
    from src.api import web_dashboard

    with web_dashboard._LOGIN_RATE_LOCK:
        web_dashboard._LOGIN_RATE_STATE.clear()
    yield
    with web_dashboard._LOGIN_RATE_LOCK:
        web_dashboard._LOGIN_RATE_STATE.clear()


def _swap_conversation_thread_state(tmp_path):
    from src.api.server import state
    from src.api.query_threads import ConversationThreadStore

    original = getattr(state, "conversation_threads", None)
    state.conversation_threads = ConversationThreadStore(str(tmp_path / "query_history.sqlite3"))
    state.conversation_threads.reset()
    return original


def _reset_auth_audit_state() -> None:
    from src.api.server import state

    tracker = getattr(state, "auth_audit", None)
    if tracker is not None:
        tracker.reset()


class TestWebDashboard:
    def test_dashboard_returns_html_in_open_mode(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        response = client.get("/dashboard")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HybridRAG Shared Console" in response.text
        assert "Ask the shared deployment" in response.text
        assert "/dashboard/data" in response.text
        assert "Stream response" in response.text
        assert "/query/stream" in response.text
        assert "Latest recent query" in response.text
        assert "Conversation threads" in response.text
        assert "Selected thread" in response.text
        assert "New thread" in response.text
        assert "Export thread" in response.text
        assert "/history/threads" in response.text
        assert "Reuse" in response.text
        assert "Session expiry" in response.text
        assert "Time remaining" in response.text

    def test_dashboard_redirects_to_login_when_token_required(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        response = client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_dashboard_redirects_to_login_when_keyring_token_required(self, client, monkeypatch):
        from src.security import shared_deployment_auth as shared_auth

        client.cookies.clear()
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
            response = client.get("/dashboard", follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/auth/login"
        finally:
            shared_auth.invalidate_shared_auth_cache()

    def test_login_page_renders_when_shared_token_is_required(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")

        response = client.get("/auth/login")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ops-dashboard" in response.text

    def test_login_accepts_keyring_backed_shared_token(self, client, monkeypatch):
        from src.api.server import state
        from src.security import shared_deployment_auth as shared_auth

        client.cookies.clear()
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
        monkeypatch.setattr(state.config, "mode", "online")
        shared_auth.invalidate_shared_auth_cache()
        try:
            login = client.post("/auth/login", json={"token": "keyring-token"})
            assert login.status_code == 200
            assert SESSION_COOKIE_NAME in client.cookies

            response = client.get("/dashboard/data")
            assert response.status_code == 200
            data = response.json()
            assert data["auth"]["auth_mode"] == "session"
            assert data["auth"]["actor"] == "ops-dashboard"
        finally:
            shared_auth.invalidate_shared_auth_cache()

    def test_login_sets_session_cookie_and_enables_protected_endpoints(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "ops-dashboard")
        monkeypatch.setattr(state.config, "mode", "online")

        login = client.post("/auth/login", json={"token": "test-token"})

        assert login.status_code == 200
        assert login.json()["actor"] == "ops-dashboard"
        assert SESSION_COOKIE_NAME in client.cookies

        context = client.get("/auth/context")
        assert context.status_code == 200
        assert context.json()["auth_mode"] == "session"
        assert context.json()["actor"] == "ops-dashboard"
        assert context.json()["actor_source"] == "session_cookie"

        activity = client.get("/activity/queries")
        assert activity.status_code == 200

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Deployment dashboard" in dashboard.text

    def test_login_accepts_previous_api_token_during_rotation(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "current-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS", "previous-token")

        login = client.post("/auth/login", json={"token": "previous-token"})

        assert login.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies

    def test_invalid_login_is_recorded_in_admin_security_activity(self, client, monkeypatch):
        client.cookies.clear()
        _reset_auth_audit_state()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-token=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        denied = client.post("/auth/login", json={"token": "wrong-token"})
        assert denied.status_code == 401

        response = client.get(
            "/admin/data",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        security = response.json()["security_activity"]
        assert security["recent_total"] >= 1
        assert security["recent_failures"] >= 1
        assert security["entries"][0]["event"] == "invalid_login"
        assert security["entries"][0]["path"] == "/auth/login"

    def test_admin_data_denies_non_admin_and_records_security_activity(self, client, monkeypatch):
        client.cookies.clear()
        _reset_auth_audit_state()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=reviewer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "reviewer=shared")

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200

        denied = client.get("/admin/data")
        assert denied.status_code == 403

        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        allowed = client.get("/admin/data")
        assert allowed.status_code == 200
        security = allowed.json()["security_activity"]
        assert security["recent_failures"] >= 1
        assert security["entries"][0]["event"] == "admin_access_denied"
        assert security["entries"][0]["path"] == "/admin/data"

    def test_dashboard_can_bootstrap_browser_session_from_header_auth(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "online")

        response = client.get(
            "/dashboard",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies

        context = client.get("/auth/context")
        assert context.status_code == 200
        assert context.json()["auth_mode"] == "session"
        assert context.json()["actor"] == "shared-dashboard"

    def test_dashboard_data_returns_aggregated_snapshot(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        response = client.get("/dashboard/data")

        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"status", "auth", "queries", "network"}
        assert data["status"]["status"] == "ok"
        assert data["auth"]["auth_mode"] == "open"
        assert "query_queue" in data["status"]
        assert "entries" in data["network"]
        assert "recent" in data["queries"]
        assert "answer_preview" in data["queries"]["recent"][0] if data["queries"]["recent"] else True
        assert "question_text" in data["queries"]["recent"][0] if data["queries"]["recent"] else True

    def test_dashboard_data_uses_browser_session_auth(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=reviewer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "reviewer=shared,review")
        monkeypatch.setattr(state.config, "mode", "online")

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200

        response = client.get("/dashboard/data")

        assert response.status_code == 200
        data = response.json()
        assert data["auth"]["auth_mode"] == "session"
        assert data["auth"]["actor"] == "shared-dashboard"
        assert data["auth"]["actor_role"] == "reviewer"
        assert data["auth"]["allowed_doc_tags"] == ["shared", "review"]
        assert data["auth"]["session_cookie_active"] is True
        assert data["auth"]["session_issued_at"]
        assert data["auth"]["session_expires_at"]
        assert data["auth"]["session_seconds_remaining"] is not None

    def test_dashboard_data_accepts_session_cookie_signed_with_previous_secret(self, client, monkeypatch):
        from src.api.browser_session import create_browser_session
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET", "old-session-secret")
        monkeypatch.setattr(state.config, "mode", "online")

        legacy_cookie = create_browser_session(actor="shared-dashboard")

        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET", "new-session-secret")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS", "old-session-secret")
        client.cookies.set(SESSION_COOKIE_NAME, legacy_cookie)

        response = client.get("/dashboard/data")

        assert response.status_code == 200
        data = response.json()
        assert data["auth"]["auth_mode"] == "session"
        assert data["auth"]["actor"] == "shared-dashboard"

    def test_dashboard_data_requires_auth_when_token_configured(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        response = client.get("/dashboard/data")

        assert response.status_code == 401

    def test_dashboard_rejects_offline_mode_for_shared_deployment(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "offline")

        response = client.get(
            "/dashboard",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 503
        assert "requires online mode" in response.json()["detail"]

    def test_dashboard_data_rejects_offline_mode_for_shared_deployment(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "offline")

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200

        response = client.get("/dashboard/data")

        assert response.status_code == 503
        assert "requires online mode" in response.json()["detail"]

    def test_admin_console_returns_html_in_open_mode(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        response = client.get("/admin")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Unified Admin Console" in response.text
        assert "/admin/data" in response.text
        assert "Start indexing" in response.text
        assert "Reindex if stale" in response.text
        assert "Recheck freshness" in response.text
        assert "/admin/index/stop" in response.text
        assert "/admin/index/reindex-if-stale" in response.text
        assert "/admin/freshness/recheck" in response.text
        assert "Runtime safety" in response.text
        assert "Data protection" in response.text
        assert "Policy review" in response.text
        assert "Index schedule" in response.text
        assert "Freshness and drift" in response.text
        assert "Active alerts" in response.text
        assert "Pause schedule" in response.text
        assert "Resume schedule" in response.text
        assert "Operator logs" in response.text
        assert "Conversation history" in response.text
        assert "Export thread" in response.text
        assert "/history/threads" in response.text

    def test_admin_console_redirects_to_login_when_token_required(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        response = client.get("/admin", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login"

    def test_admin_data_returns_operator_snapshot(self, client, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import (
            AdminAppLogEntryResponse,
            AdminIndexReportEntryResponse,
            AdminOperatorLogSnapshotResponse,
        )
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        original = getattr(state.query_engine, "last_query_trace", None)
        original_recent = getattr(state.query_engine, "recent_query_traces", None)
        try:
            state.query_engine.last_query_trace = {
                "trace_id": "trace-latest",
                "captured_at": "2026-03-12T22:10:00-06:00",
                "query": "Why was this answer chosen?",
                "mode": "online",
                "active_profile": "balanced",
                "stream": False,
                "decision": {"path": "answer"},
                "retrieval": {"counts": {"final_hits": 1}},
            }
            state.query_engine.recent_query_traces = [
                {
                    "trace_id": "trace-older",
                    "captured_at": "2026-03-12T22:08:00-06:00",
                    "query": "Show the previous trace",
                    "mode": "offline",
                    "active_profile": "strict",
                    "stream": True,
                    "decision": {"path": "stream_answer"},
                    "retrieval": {"counts": {"final_hits": 2}},
                },
                state.query_engine.last_query_trace,
            ]
            monkeypatch.setattr(
                api_routes,
                "_build_operator_log_snapshot",
                lambda **_kwargs: AdminOperatorLogSnapshotResponse(
                    app_log_file="app_2026-03-12.log",
                    app_log_entries=[
                        AdminAppLogEntryResponse(
                            timestamp="2026-03-12T22:44:00",
                            event="query_complete",
                            summary="What changed in Sprint 7?",
                            log_file="app_2026-03-12.log",
                        )
                    ],
                    index_reports=[
                        AdminIndexReportEntryResponse(
                            file_name="index_report_2026-03-12_224800.txt",
                            modified_at="2026-03-12T22:48:00",
                            size_bytes=1935,
                        )
                    ],
                ),
            )

            response = client.get("/admin/data")

            assert response.status_code == 200
            data = response.json()
            assert set(data) == {
                "dashboard",
                "config",
                "runtime_safety",
                "access_policy",
                "index_schedule",
                "freshness",
                "storage_protection",
                "alerts",
                "security_activity",
                "operator_logs",
                "latest_query_trace",
                "recent_query_traces",
            }
            assert data["dashboard"]["status"]["status"] == "ok"
            assert data["config"]["mode"] in ("offline", "online")
            assert data["runtime_safety"]["deployment_mode"] in ("development", "production")
            assert data["runtime_safety"]["source_folder"]
            assert data["runtime_safety"]["database_path"]
            assert data["access_policy"]["default_document_tags"] == ["shared"]
            assert data["access_policy"]["recent_denied_traces"] == 0
            assert data["index_schedule"]["enabled"] is False
            assert isinstance(data["freshness"]["stale"], bool)
            assert data["freshness"]["source_folder"]
            assert data["storage_protection"]["mode"] in ("disabled", "advisory", "required")
            assert isinstance(data["storage_protection"]["tracked_paths"], list)
            assert isinstance(data["storage_protection"]["unprotected_paths"], list)
            assert isinstance(data["alerts"]["total"], int)
            assert isinstance(data["security_activity"]["recent_total"], int)
            assert data["operator_logs"]["app_log_file"] == "app_2026-03-12.log"
            assert data["operator_logs"]["app_log_entries"][0]["event"] == "query_complete"
            assert data["operator_logs"]["index_reports"][0]["file_name"] == "index_report_2026-03-12_224800.txt"
            assert data["latest_query_trace"]["available"] is True
            assert data["latest_query_trace"]["trace_id"] == "trace-latest"
            assert data["latest_query_trace"]["query"] == "Why was this answer chosen?"
            assert data["latest_query_trace"]["decision_path"] == "answer"
            assert data["latest_query_trace"]["mode"] == "online"
            assert data["latest_query_trace"]["final_hit_count"] == 1
            assert "Latest Query Trace" in data["latest_query_trace"]["formatted_text"]
            assert [item["trace_id"] for item in data["recent_query_traces"]] == [
                "trace-latest",
                "trace-older",
            ]
        finally:
            state.query_engine.last_query_trace = original
            state.query_engine.recent_query_traces = original_recent

    def test_admin_trace_detail_returns_selected_trace(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        original_recent = getattr(state.query_engine, "recent_query_traces", None)
        original = getattr(state.query_engine, "last_query_trace", None)
        try:
            state.query_engine.recent_query_traces = [
                {
                    "trace_id": "trace-1",
                    "captured_at": "2026-03-12T22:01:00-06:00",
                    "query": "First operator trace",
                    "mode": "offline",
                    "active_profile": "strict",
                    "stream": False,
                    "decision": {"path": "answer"},
                    "retrieval": {"counts": {"final_hits": 1}},
                },
                {
                    "trace_id": "trace-2",
                    "captured_at": "2026-03-12T22:02:00-06:00",
                    "query": "Second operator trace",
                    "mode": "online",
                    "active_profile": "balanced",
                    "stream": True,
                    "decision": {"path": "stream_answer"},
                    "retrieval": {"counts": {"final_hits": 3}},
                },
            ]
            state.query_engine.last_query_trace = state.query_engine.recent_query_traces[-1]

            response = client.get("/admin/traces/trace-1")

            assert response.status_code == 200
            data = response.json()
            assert data["available"] is True
            assert data["trace_id"] == "trace-1"
            assert data["query"] == "First operator trace"
            assert data["decision_path"] == "answer"
            assert data["final_hit_count"] == 1
        finally:
            state.query_engine.recent_query_traces = original_recent
            state.query_engine.last_query_trace = original

    def test_admin_trace_detail_requires_known_trace_id(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)

        response = client.get("/admin/traces/missing-trace")

        assert response.status_code == 404

    def test_admin_data_uses_browser_session_auth(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200

        response = client.get("/admin/data")

        assert response.status_code == 200
        data = response.json()
        assert data["dashboard"]["auth"]["auth_mode"] == "session"
        assert data["dashboard"]["auth"]["actor"] == "shared-dashboard"
        assert data["runtime_safety"]["api_auth_required"] is True
        assert data["runtime_safety"]["api_auth_label"] == "shared-dashboard"

    def test_admin_data_reports_runtime_safety_boundaries(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "operator-token")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "operator-token=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET", "browser-current")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS", "browser-old")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS", "1")
        monkeypatch.setenv("HYBRIDRAG_TRUSTED_PROXY_HOSTS", "proxy-a,proxy-b")
        monkeypatch.setenv("HYBRIDRAG_PROXY_USER_HEADERS", "x-forwarded-user;x-auth-request-user")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET", "proxy-current")
        monkeypatch.setenv("HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS", "proxy-old")
        monkeypatch.setenv("HYBRIDRAG_BROWSER_SESSION_TTL_SECONDS", "900")
        monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-current")
        monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS", "history-old")

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200

        response = client.get("/admin/data")

        assert response.status_code == 200
        data = response.json()
        safety = data["runtime_safety"]
        assert safety["shared_online_enforced"] is True
        assert safety["shared_online_ready"] is False
        assert safety["api_auth_required"] is True
        assert safety["api_auth_source"] == "env:HYBRIDRAG_API_AUTH_TOKEN"
        assert safety["api_auth_label"] == "operator-token"
        assert safety["browser_sessions_enabled"] is True
        assert safety["browser_session_secret_source"] == "browser_session_secret"
        assert safety["browser_session_rotation_enabled"] is True
        assert safety["browser_session_ttl_seconds"] == 900
        assert safety["browser_session_invalid_before"]
        assert safety["browser_session_secure_cookie"] is False
        assert safety["trusted_proxy_identity_enabled"] is True
        assert safety["proxy_identity_secret_rotation_enabled"] is True
        assert safety["history_encryption_enabled"] is True
        assert safety["history_encryption_source"] == "env:HYBRIDRAG_HISTORY_ENCRYPTION_KEY"
        assert safety["history_encryption_rotation_enabled"] is True
        assert safety["history_secure_delete_enabled"] is True
        assert safety["history_database_path"].endswith("hybridrag_query_history.sqlite3")
        assert safety["trusted_proxy_hosts"] == ["proxy-a", "proxy-b"]
        assert safety["trusted_proxy_user_headers"] == [
            "x-forwarded-user",
            "x-auth-request-user",
        ]

    def test_admin_data_reports_storage_protection_snapshot(self, client, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import AdminStorageProtectionResponse

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.setattr(
            api_routes,
            "_build_admin_storage_protection_response",
            lambda: AdminStorageProtectionResponse(
                mode="required",
                required=True,
                roots=[r"D:\HybridRAG3\data\protected"],
                tracked_paths=[
                    r"D:\HybridRAG3\data\protected\hybridrag.sqlite3",
                    r"D:\HybridRAG3\data\protected\hybridrag_query_history.sqlite3",
                ],
                protected_paths=[r"D:\HybridRAG3\data\protected\hybridrag_query_history.sqlite3"],
                unprotected_paths=[r"D:\HybridRAG3\data\protected\hybridrag.sqlite3"],
                all_paths_protected=False,
                summary="Protected storage is required and one tracked path is outside the configured roots.",
            ),
        )

        response = client.get("/admin/data")

        assert response.status_code == 200
        data = response.json()["storage_protection"]
        assert data["mode"] == "required"
        assert data["required"] is True
        assert data["roots"] == [r"D:\HybridRAG3\data\protected"]
        assert len(data["tracked_paths"]) == 2
        assert data["protected_paths"] == [r"D:\HybridRAG3\data\protected\hybridrag_query_history.sqlite3"]
        assert data["unprotected_paths"] == [r"D:\HybridRAG3\data\protected\hybridrag.sqlite3"]
        assert data["all_paths_protected"] is False
        assert "required" in data["summary"].lower()

    def test_admin_data_reports_access_policy_review(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "alice=restricted-reader;bob=admin")
        monkeypatch.setenv(
            "HYBRIDRAG_ROLE_TAGS",
            "restricted-reader=shared,restricted;admin=*",
        )
        monkeypatch.setenv(
            "HYBRIDRAG_DOCUMENT_TAG_RULES",
            "*/restricted/*=restricted;*.cad=design",
        )

        original_recent = getattr(state.query_engine, "recent_query_traces", None)
        original = getattr(state.query_engine, "last_query_trace", None)
        try:
            state.query_engine.recent_query_traces = [
                {
                    "trace_id": "trace-allow",
                    "captured_at": "2026-03-12T22:01:00-06:00",
                    "query": "Show the shared procedure",
                    "mode": "online",
                    "active_profile": "balanced",
                    "stream": False,
                    "decision": {"path": "answer"},
                    "retrieval": {
                        "counts": {"final_hits": 1, "denied_hits": 0},
                        "access_control": {"denied_hits": 0},
                    },
                },
                {
                    "trace_id": "trace-denied",
                    "captured_at": "2026-03-12T22:02:00-06:00",
                    "query": "Show the restricted spec",
                    "mode": "online",
                    "active_profile": "balanced",
                    "stream": False,
                    "decision": {"path": "access_denied_no_results"},
                    "retrieval": {
                        "counts": {"final_hits": 0, "denied_hits": 1},
                        "access_control": {"denied_hits": 1},
                    },
                },
            ]
            state.query_engine.last_query_trace = state.query_engine.recent_query_traces[-1]

            response = client.get("/admin/data")

            assert response.status_code == 200
            policy = response.json()["access_policy"]
            assert policy["default_document_tags"] == ["shared"]
            assert "alice -> restricted-reader" in policy["role_map"]
            assert "bob -> admin" in policy["role_map"]
            assert "restricted-reader: shared, restricted" in policy["role_tag_policies"]
            assert "admin: *" in policy["role_tag_policies"]
            assert "*/restricted/*: restricted" in policy["document_tag_rules"]
            assert "*.cad: design" in policy["document_tag_rules"]
            assert policy["recent_denied_traces"] == 1
            assert policy["latest_denied_trace_id"] == "trace-denied"
            assert policy["latest_denied_query"] == "Show the restricted spec"
        finally:
            state.query_engine.recent_query_traces = original_recent
            state.query_engine.last_query_trace = original

    def test_admin_data_reports_index_schedule(self, client, monkeypatch):
        from src.api.index_schedule import IndexScheduleTracker
        from src.api.server import state

        client.cookies.clear()
        original_schedule = getattr(state, "index_schedule", None)
        try:
            schedule = IndexScheduleTracker(interval_seconds=900, source_folder=r"D:\HybridRAG3\data\source")
            schedule.note_run_started(now=100.0)
            schedule.note_run_finished(success=False, error="Network share unavailable", now=120.0)
            state.index_schedule = schedule

            response = client.get("/admin/data")

            assert response.status_code == 200
            snapshot = response.json()["index_schedule"]
            assert snapshot["enabled"] is True
            assert snapshot["interval_seconds"] == 900
            assert snapshot["last_status"] == "failed"
            assert snapshot["last_error"] == "Network share unavailable"
            assert snapshot["total_runs"] == 1
            assert snapshot["total_failed"] == 1
            assert snapshot["source_folder"] == r"D:\HybridRAG3\data\source"
        finally:
            state.index_schedule = original_schedule

    def test_admin_can_pause_and_resume_index_schedule(self, client, monkeypatch):
        from src.api.index_schedule import IndexScheduleTracker
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        original_schedule = getattr(state, "index_schedule", None)
        try:
            state.index_schedule = IndexScheduleTracker(
                interval_seconds=900,
                source_folder=r"D:\HybridRAG3\data\source",
            )

            paused = client.post("/admin/index-schedule/pause")
            assert paused.status_code == 200
            assert paused.json()["enabled"] is False
            assert paused.json()["last_status"] == "paused"

            resumed = client.post("/admin/index-schedule/resume")
            assert resumed.status_code == 200
            assert resumed.json()["enabled"] is True
            assert resumed.json()["last_status"] == "idle"
            assert resumed.json()["next_run_at"]
        finally:
            state.index_schedule = original_schedule

    def test_admin_data_reports_freshness_snapshot(self, client, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import AdminContentFreshnessResponse

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
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
                freshness_age_hours=2.5,
                warn_after_hours=24,
                stale=True,
                summary="2 files changed after the last index run.",
            ),
        )

        response = client.get("/admin/data")

        assert response.status_code == 200
        freshness = response.json()["freshness"]
        assert freshness["source_exists"] is True
        assert freshness["total_indexable_files"] == 12
        assert freshness["files_newer_than_index"] == 2
        assert freshness["stale"] is True
        assert freshness["summary"] == "2 files changed after the last index run."

    def test_admin_data_returns_operator_log_snapshot(self, client, monkeypatch):
        from src.api import routes as api_routes
        from src.api.models import (
            AdminAppLogEntryResponse,
            AdminIndexReportEntryResponse,
            AdminOperatorLogSnapshotResponse,
        )

        client.cookies.clear()
        monkeypatch.delenv("HYBRIDRAG_API_AUTH_TOKEN", raising=False)
        monkeypatch.setattr(
            api_routes,
            "_build_operator_log_snapshot",
            lambda **_kwargs: AdminOperatorLogSnapshotResponse(
                app_log_file="app_2026-03-12.log",
                app_log_entries=[
                    AdminAppLogEntryResponse(
                        timestamp="2026-03-12T22:50:00",
                        event="index_complete",
                        summary="Indexed 12 files",
                        log_file="app_2026-03-12.log",
                    )
                ],
                index_reports=[
                    AdminIndexReportEntryResponse(
                        file_name="index_report_2026-03-12_224800.txt",
                        modified_at="2026-03-12T22:48:00",
                        size_bytes=1935,
                    )
                ],
            ),
        )

        response = client.get("/admin/data")

        assert response.status_code == 200
        data = response.json()
        assert data["operator_logs"]["app_log_file"] == "app_2026-03-12.log"
        assert data["operator_logs"]["app_log_entries"][0]["summary"] == "Indexed 12 files"
        assert data["operator_logs"]["index_reports"][0]["size_bytes"] == 1935

    def test_admin_data_requires_auth_when_token_configured(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        response = client.get("/admin/data")

        assert response.status_code == 401

    def test_admin_trace_detail_requires_auth_when_token_configured(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        response = client.get("/admin/traces/trace-1")

        assert response.status_code == 401

    def test_admin_index_stop_uses_browser_session_auth(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")

        original_active = state.indexing_active
        original_thread = state.indexing_thread
        was_set = state.indexing_stop_event.is_set()
        try:
            state.indexing_active = True
            state.indexing_thread = None
            state.indexing_stop_event.clear()

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200
            assert SESSION_COOKIE_NAME in client.cookies

            response = client.post("/admin/index/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert data["stop_requested"] is True
            assert state.indexing_stop_event.is_set() is True
        finally:
            state.indexing_active = original_active
            state.indexing_thread = original_thread
            if was_set:
                state.indexing_stop_event.set()
            else:
                state.indexing_stop_event.clear()

    def test_admin_reindex_if_stale_uses_browser_session_auth(self, client, monkeypatch):
        from src.api.models import AdminIndexControlResponse
        from src.api import web_dashboard as dashboard_routes

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
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

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies

        response = client.post("/admin/index/reindex-if-stale")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["stop_requested"] is False
        assert data["message"] == "Freshness maintenance run started."

    def test_admin_freshness_recheck_uses_browser_session_auth(self, client, monkeypatch):
        from src.api.models import AdminContentFreshnessResponse
        from src.api import web_dashboard as dashboard_routes

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
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

        login = client.post("/auth/login", json={"token": "test-token"})
        assert login.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies

        response = client.post("/admin/freshness/recheck")

        assert response.status_code == 200
        data = response.json()
        assert data["source_exists"] is True
        assert data["files_newer_than_index"] == 3
        assert data["summary"] == "3 files changed after the last index run."

    def test_browser_session_can_submit_query_without_header_token(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=reviewer")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "reviewer=shared,review")
        monkeypatch.setattr(state.config, "mode", "online")

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Shared dashboard answer",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.93}],
                chunks_used=1,
                tokens_in=8,
                tokens_out=12,
                cost_usd=0.0,
                latency_ms=4.0,
                mode="online",
                error=None,
            )

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200
            assert SESSION_COOKIE_NAME in client.cookies

            query = client.post("/query", json={"question": "Use browser session auth"})
            assert query.status_code == 200
            data = query.json()
            assert data["answer"] == "Shared dashboard answer"
            assert data["sources"][0]["path"] == "README.md"

            snapshot = client.get("/dashboard/data")
            assert snapshot.status_code == 200
            recent = snapshot.json()["queries"]["recent"][0]
            assert recent["question_text"] == "Use browser session auth"
            assert recent["actor_role"] == "reviewer"
            assert recent["allowed_doc_tags"] == ["shared", "review"]
            assert recent["document_policy_source"] == "role_tags:reviewer"
            assert recent["answer_preview"] == "Shared dashboard answer"
            assert recent["source_paths"] == ["README.md"]
            assert recent["denied_hits"] == 0
        finally:
            state.query_engine.query = original

    def test_browser_session_can_read_conversation_history(self, client, monkeypatch, tmp_path):
        from src.api.server import state
        from src.core.query_engine import QueryResult

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "online")

        original_threads = _swap_conversation_thread_state(tmp_path)
        original_query = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Saved browser answer",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.93}],
                chunks_used=1,
                tokens_in=8,
                tokens_out=12,
                cost_usd=0.0,
                latency_ms=4.0,
                mode="online",
                error=None,
            )

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200

            query = client.post("/query", json={"question": "Persist browser history"})
            assert query.status_code == 200
            thread_id = query.json()["thread_id"]
            assert thread_id

            history = client.get("/history/threads")
            assert history.status_code == 200
            assert history.json()["max_threads"] >= 1
            assert history.json()["max_turns_per_thread"] >= 1
            history_ids = [item["thread_id"] for item in history.json()["threads"]]
            assert thread_id in history_ids

            detail = client.get(f"/history/threads/{thread_id}")
            assert detail.status_code == 200
            assert detail.json()["turns"][0]["answer_text"] == "Saved browser answer"
            assert detail.json()["turns"][0]["actor"] == "shared-dashboard"
        finally:
            state.query_engine.query = original_query
            state.conversation_threads = original_threads

    def test_browser_session_query_rejects_offline_mode_for_shared_deployment(self, client, monkeypatch):
        from src.api.server import state

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "offline")

        original = state.query_engine.query
        try:
            def _should_not_run(_question):
                raise AssertionError("query engine should not run while shared deployment is offline")

            state.query_engine.query = _should_not_run

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200

            response = client.post("/query", json={"question": "Use browser session auth"})

            assert response.status_code == 503
            assert "requires online mode" in response.json()["detail"]
        finally:
            state.query_engine.query = original

    def test_browser_session_rejected_mode_downgrade_keeps_shared_queries_online(self, client, monkeypatch):
        from src.api.server import state
        from src.api import routes as api_routes
        from src.core.query_engine import QueryResult

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "online")
        with api_routes._RATE_LOCK:
            api_routes._RATE_STATE.clear()

        original = state.query_engine.query
        try:
            state.query_engine.query = lambda _q: QueryResult(
                answer="Still serving shared traffic",
                sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.93}],
                chunks_used=1,
                tokens_in=5,
                tokens_out=7,
                cost_usd=0.0,
                latency_ms=2.0,
                mode="online",
                error=None,
            )

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200

            downgrade = client.put("/mode", json={"mode": "offline"})
            assert downgrade.status_code == 409
            assert state.config.mode == "online"

            query = client.post("/query", json={"question": "Are we still online?"})
            assert query.status_code == 200
            assert query.json()["answer"] == "Still serving shared traffic"
        finally:
            state.query_engine.query = original

    def test_browser_session_can_submit_streaming_query_without_header_token(self, client, monkeypatch):
        from src.api.server import state
        from src.core.query_engine import QueryResult

        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setattr(state.config, "mode", "online")

        original = state.query_engine.query_stream
        try:
            def _fake_stream(_q):
                yield {"phase": "searching"}
                yield {"token": "Shared "}
                yield {"token": "stream"}
                yield {
                    "done": True,
                    "result": QueryResult(
                        answer="Shared stream",
                        sources=[{"path": "README.md", "chunks": 1, "avg_relevance": 0.93}],
                        chunks_used=1,
                        tokens_in=7,
                        tokens_out=9,
                        cost_usd=0.0,
                        latency_ms=3.0,
                        mode="online",
                        error=None,
                    ),
                }

            state.query_engine.query_stream = _fake_stream

            login = client.post("/auth/login", json={"token": "test-token"})
            assert login.status_code == 200
            assert SESSION_COOKIE_NAME in client.cookies

            query = client.post("/query/stream", json={"question": "Use browser streaming auth"})
            assert query.status_code == 200
            assert "event: phase" in query.text
            assert "event: token" in query.text
            assert "event: done" in query.text
            assert '"thread_id"' in query.text
        finally:
            state.query_engine.query_stream = original

    def test_logout_clears_session_cookie(self, client, monkeypatch):
        client.cookies.clear()
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")

        client.post("/auth/login", json={"token": "test-token"})
        assert SESSION_COOKIE_NAME in client.cookies

        logout = client.post("/auth/logout")

        assert logout.status_code == 200
        assert logout.json()["redirect_to"] == "/auth/login"
        assert SESSION_COOKIE_NAME not in client.cookies

        denied = client.get("/auth/context")
        assert denied.status_code == 401
