# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the operator alerts area and protects against regressions.
# What to read first: Start at build_admin_alert_summary(), then follow the alert rules downward.
# Inputs: Existing status/runtime/schedule/freshness snapshots.
# Outputs: Assertions over the alert summary shown in the Admin browser console.
# Safety notes: Pure function tests only; no filesystem or network access.
# ============================

from src.api.operator_alerts import build_admin_alert_summary


def test_operator_alert_summary_reports_shared_offline_and_source_drift():
    summary = build_admin_alert_summary(
        dashboard_status={
            "query_queue": {
                "enabled": True,
                "saturated": True,
            }
        },
        runtime_safety={
            "shared_online_enforced": True,
            "shared_online_ready": False,
        },
        index_schedule={
            "enabled": True,
            "due_now": True,
            "indexing_active": False,
            "last_status": "idle",
        },
        freshness={
            "source_exists": True,
            "stale": True,
            "files_newer_than_index": 3,
            "last_index_finished_at": "2026-03-13T04:15:00Z",
            "last_index_status": "completed",
            "summary": "3 files changed after the last index run.",
        },
    )

    codes = {item["code"] for item in summary["items"]}
    assert summary["total"] == 4
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 3
    assert "shared_offline_blocked" in codes
    assert "query_queue_saturated" in codes
    assert "source_drift" in codes
    assert "schedule_due" in codes


def test_operator_alert_summary_reports_no_alerts_for_healthy_state():
    summary = build_admin_alert_summary(
        dashboard_status={
            "query_queue": {
                "enabled": True,
                "saturated": False,
            }
        },
        runtime_safety={
            "shared_online_enforced": True,
            "shared_online_ready": True,
        },
        index_schedule={
            "enabled": True,
            "due_now": False,
            "indexing_active": False,
            "last_status": "completed",
        },
        freshness={
            "source_exists": True,
            "stale": False,
            "files_newer_than_index": 0,
            "last_index_finished_at": "2026-03-13T04:15:00Z",
            "last_index_status": "completed",
            "summary": "Indexed content is up to date with the current source tree.",
        },
    )

    assert summary["total"] == 0
    assert summary["error_count"] == 0
    assert summary["warning_count"] == 0
    assert summary["items"] == []


def test_operator_alert_summary_reports_denied_admin_access_activity():
    summary = build_admin_alert_summary(
        dashboard_status={
            "query_queue": {
                "enabled": True,
                "saturated": False,
            }
        },
        runtime_safety={
            "shared_online_enforced": True,
            "shared_online_ready": True,
        },
        index_schedule={
            "enabled": False,
            "due_now": False,
            "indexing_active": False,
            "last_status": "completed",
        },
        freshness={
            "source_exists": True,
            "stale": False,
            "files_newer_than_index": 0,
            "last_index_finished_at": "2026-03-13T04:15:00Z",
            "last_index_status": "completed",
            "summary": "Indexed content is up to date with the current source tree.",
        },
        security_activity={
            "recent_failures": 1,
            "recent_rate_limited": 0,
            "recent_proxy_rejections": 0,
            "entries": [
                {
                    "event": "admin_access_denied",
                    "outcome": "denied",
                    "client_host": "127.0.0.1",
                    "path": "/admin/data",
                    "detail": "actor_role=reviewer",
                }
            ],
        },
        access_policy={
            "recent_denied_traces": 0,
        },
    )

    codes = {item["code"] for item in summary["items"]}
    assert "admin_access_denied" in codes


def test_operator_alert_summary_reports_security_anomalies(monkeypatch):
    monkeypatch.setenv("HYBRIDRAG_AUTH_ANOMALY_THRESHOLD", "3")
    monkeypatch.setenv("HYBRIDRAG_LOGIN_RATE_ALERT_THRESHOLD", "2")
    monkeypatch.setenv("HYBRIDRAG_ACCESS_DENIED_ALERT_THRESHOLD", "2")

    summary = build_admin_alert_summary(
        dashboard_status={
            "query_queue": {
                "enabled": True,
                "saturated": False,
            }
        },
        runtime_safety={
            "shared_online_enforced": True,
            "shared_online_ready": True,
        },
        index_schedule={
            "enabled": False,
            "due_now": False,
            "indexing_active": False,
            "last_status": "completed",
        },
        freshness={
            "source_exists": True,
            "stale": False,
            "files_newer_than_index": 0,
            "last_index_finished_at": "2026-03-13T04:15:00Z",
            "last_index_status": "completed",
            "summary": "Indexed content is up to date.",
        },
        security_activity={
            "recent_failures": 4,
            "recent_rate_limited": 2,
            "recent_proxy_rejections": 1,
        },
        access_policy={
            "recent_denied_traces": 3,
        },
    )

    codes = {item["code"] for item in summary["items"]}
    assert "auth_failure_spike" in codes
    assert "login_rate_limited" in codes
    assert "proxy_identity_rejected" in codes
    assert "access_denied_spike" in codes


def test_operator_alert_summary_reports_unprotected_required_storage():
    summary = build_admin_alert_summary(
        dashboard_status={
            "query_queue": {
                "enabled": False,
                "saturated": False,
            }
        },
        runtime_safety={
            "shared_online_enforced": False,
            "shared_online_ready": True,
        },
        index_schedule={
            "enabled": False,
            "due_now": False,
            "indexing_active": False,
            "last_status": "completed",
        },
        freshness={
            "source_exists": True,
            "stale": False,
            "files_newer_than_index": 0,
            "last_index_finished_at": "2026-03-13T04:15:00Z",
            "last_index_status": "completed",
            "summary": "Indexed content is up to date.",
        },
        storage_protection={
            "required": True,
            "unprotected_paths": [
                r"D:\HybridRAG3\data\hybridrag.sqlite3",
            ],
            "summary": "Protected storage is required and one tracked data path is outside the configured roots.",
        },
    )

    assert summary["total"] == 1
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 0
    assert summary["items"][0]["code"] == "protected_storage_unprotected_paths"
