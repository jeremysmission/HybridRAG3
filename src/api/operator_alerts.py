# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the operator alerts part of the application runtime.
# What to read first: Start at build_admin_alert_summary(), then read _alert().
# Inputs: Existing Admin/status snapshots (schedule, freshness, queue, runtime safety).
# Outputs: A compact alert summary for the Admin browser console.
# Safety notes: This module only derives alerts from already-computed state; it does not perform I/O.
# ============================

from __future__ import annotations

import os


def _alert(severity: str, code: str, message: str, action: str = "") -> dict[str, str]:
    return {
        "severity": str(severity or ""),
        "code": str(code or ""),
        "message": str(message or ""),
        "action": str(action or ""),
    }


def build_admin_alert_summary(
    *,
    dashboard_status: dict[str, object],
    runtime_safety: dict[str, object],
    index_schedule: dict[str, object],
    freshness: dict[str, object],
    security_activity: dict[str, object] | None = None,
    access_policy: dict[str, object] | None = None,
    storage_protection: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build operator alerts from the current shared runtime surfaces."""
    items: list[dict[str, str]] = []
    security = security_activity if isinstance(security_activity, dict) else {}
    policy = access_policy if isinstance(access_policy, dict) else {}
    storage = storage_protection if isinstance(storage_protection, dict) else {}

    queue = dashboard_status.get("query_queue", {}) if isinstance(dashboard_status, dict) else {}
    if runtime_safety.get("shared_online_enforced") and not runtime_safety.get("shared_online_ready"):
        items.append(
            _alert(
                "error",
                "shared_offline_blocked",
                "Shared deployment is enforced, but runtime mode is offline.",
                "Return the workstation to online mode before reopening shared access.",
            )
        )

    if queue.get("enabled") and queue.get("saturated"):
        items.append(
            _alert(
                "warning",
                "query_queue_saturated",
                "Shared query queue is saturated.",
                "Reduce incoming load or wait for active queries to clear.",
            )
        )

    unprotected_paths = list(storage.get("unprotected_paths", []) or [])
    if unprotected_paths:
        required = bool(storage.get("required"))
        items.append(
            _alert(
                "error" if required else "warning",
                "protected_storage_unprotected_paths",
                str(storage.get("summary", "") or "Tracked data paths are not fully protected."),
                "Move the data files under HYBRIDRAG_PROTECTED_STORAGE_ROOTS or relax the requirement before startup.",
            )
        )

    if not freshness.get("source_exists"):
        items.append(
            _alert(
                "error",
                "source_missing",
                "Configured source folder is missing or not accessible.",
                "Restore the source path or update the configured indexing folder.",
            )
        )
    elif freshness.get("stale"):
        newer = int(freshness.get("files_newer_than_index", 0) or 0)
        if not freshness.get("last_index_finished_at"):
            items.append(
                _alert(
                    "warning",
                    "never_indexed",
                    "Indexable source files exist, but no completed index run is recorded.",
                    "Run indexing before relying on shared answers.",
                )
            )
        elif newer > 0:
            items.append(
                _alert(
                    "warning",
                    "source_drift",
                    f"{newer} source files changed after the last completed index run.",
                    "Run indexing to bring the database back in sync with the source tree.",
                )
            )
        else:
            items.append(
                _alert(
                    "warning",
                    "freshness_stale",
                    str(freshness.get("summary", "") or "Indexed content is stale."),
                    "Review the freshness window or trigger a maintenance run.",
                )
            )

    last_index_status = str(freshness.get("last_index_status", "") or "").strip().lower()
    if last_index_status and last_index_status not in ("finished", "completed", "success", "running", "stopped"):
        items.append(
            _alert(
                "error",
                "index_run_failed",
                f"Last recorded index run status is {last_index_status}.",
                "Inspect the most recent index report and rerun indexing after the root cause is fixed.",
            )
        )

    if index_schedule.get("enabled"):
        schedule_status = str(index_schedule.get("last_status", "") or "").strip().lower()
        if schedule_status == "failed":
            items.append(
                _alert(
                    "error",
                    "schedule_failed",
                    "Scheduled indexing recorded a failed run.",
                    "Check the index report, source path, and embedding/runtime dependencies.",
                )
            )
        elif index_schedule.get("due_now") and not index_schedule.get("indexing_active"):
            items.append(
                _alert(
                    "warning",
                    "schedule_due",
                    "Scheduled indexing is due now but no run is active.",
                    "Verify that the schedule loop is running and the source path is reachable.",
                )
            )

    auth_threshold = _env_positive_int("HYBRIDRAG_AUTH_ANOMALY_THRESHOLD", 5)
    auth_failures = int(security.get("recent_failures", 0) or 0)
    if auth_failures >= auth_threshold:
        items.append(
            _alert(
                "warning",
                "auth_failure_spike",
                f"{auth_failures} denied auth events were recorded in the recent security window.",
                "Review recent security activity and rotate shared secrets if the source is not expected.",
            )
        )

    proxy_rejections = int(security.get("recent_proxy_rejections", 0) or 0)
    if proxy_rejections > 0:
        items.append(
            _alert(
                "warning",
                "proxy_identity_rejected",
                f"{proxy_rejections} proxy-identity requests were rejected in the recent security window.",
                "Verify reverse-proxy host boundaries and shared proxy proof secrets.",
            )
        )

    rate_limited = int(security.get("recent_rate_limited", 0) or 0)
    if rate_limited >= _env_positive_int("HYBRIDRAG_LOGIN_RATE_ALERT_THRESHOLD", 2):
        items.append(
            _alert(
                "warning",
                "login_rate_limited",
                f"{rate_limited} browser login attempts hit the rate limiter in the recent security window.",
                "Check for repeated sign-in failures or brute-force probes from the listed hosts.",
            )
        )

    admin_denied = sum(
        1
        for item in list(security.get("entries", []) or [])
        if str(item.get("event", "") or "") == "admin_access_denied"
    )
    if admin_denied > 0:
        items.append(
            _alert(
                "warning",
                "admin_access_denied",
                f"{admin_denied} non-admin requests hit the Admin console in the recent security window.",
                "Review role mappings and confirm the denied actor or host is expected.",
            )
        )

    denied_threshold = _env_positive_int("HYBRIDRAG_ACCESS_DENIED_ALERT_THRESHOLD", 3)
    recent_denied = int(policy.get("recent_denied_traces", 0) or 0)
    if recent_denied >= denied_threshold:
        items.append(
            _alert(
                "warning",
                "access_denied_spike",
                f"{recent_denied} denied retrieval traces were captured recently.",
                "Review role/tag policy mappings and confirm the denied requests are expected.",
            )
        )

    error_count = sum(1 for item in items if item["severity"] == "error")
    warning_count = sum(1 for item in items if item["severity"] == "warning")
    return {
        "total": len(items),
        "error_count": error_count,
        "warning_count": warning_count,
        "items": items,
    }


def _env_positive_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return max(1, int(default))
