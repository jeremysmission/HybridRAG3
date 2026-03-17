# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the routes part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- API Routes (src/api/routes.py)
# ============================================================================
# WHAT: All REST API endpoint handlers for the HybridRAG FastAPI server.
# WHY:  Provides a headless (no GUI) interface for automation, scripts,
#       MCP integrations, and CI/CD pipelines that need to query or
#       index documents programmatically.
# HOW:  Each endpoint is a thin async wrapper around the core pipeline
#       classes (QueryEngine, Indexer, etc.).  Heavy work runs in
#       background threads via asyncio.to_thread() or threading.Thread
#       so the event loop stays responsive.
# USAGE: Endpoints are mounted on the FastAPI app in server.py.
#        Access docs at http://127.0.0.1:8000/docs (Swagger UI).
#
# ENDPOINTS:
#   GET  /health         Fast health check (no pipeline deps)
#   GET  /status         Database stats and mode info
#   GET  /auth/context   Resolved auth and request identity context
#   GET  /activity/queries  Active + recent query activity
#   GET  /activity/query-queue Shared query queue status and capacity
#   GET  /activity/network  Recent network-gate audit activity
#   GET  /config         Current configuration (read-only, no secrets)
#   POST /query          Ask a question about your documents
#   POST /query/stream   Stream answer tokens via Server-Sent Events
#   POST /index          Start indexing (runs in background thread)
#   GET  /index/status   Check indexing progress
#   PUT  /mode           Switch between offline and online mode
#
# INTERNET ACCESS:
#   /query in online mode: YES (API call to configured endpoint)
#   Everything else: NONE
# ============================================================================

from __future__ import annotations

import json
import os
import sqlite3
import time
import threading
import logging
import getpass
import yaml
from pathlib import Path
from collections import deque

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from src.api.models import (
    QueryRequest,
    QueryResponse,
    StatusResponse,
    DashboardSnapshotResponse,
    ConversationThreadListResponse,
    ConversationThreadResponse,
    AdminConsoleSnapshotResponse,
    AdminContentFreshnessResponse,
    AdminStorageProtectionResponse,
    AdminAlertSummaryResponse,
    AdminIndexScheduleResponse,
    AdminIndexScheduleControlResponse,
    AdminRuntimeSafetyResponse,
    AdminAccessPolicyReviewResponse,
    AdminOperatorLogSnapshotResponse,
    AdminAppLogEntryResponse,
    AdminIndexReportEntryResponse,
    AdminSecurityActivityResponse,
    AdminIndexControlResponse,
    AuthContextResponse,
    QueryActivitySummary,
    QueryActivityResponse,
    QueryQueueSummary,
    NetworkActivityResponse,
    IndexingSnapshot,
    IndexScheduleSnapshotResponse,
    LatestIndexRunSummary,
    NetworkAuditSummary,
    HealthResponse,
    IndexRequest,
    IndexStartResponse,
    IndexStatusResponse,
    ConfigResponse,
    ModeRequest,
    ModeResponse,
    ErrorResponse,
    StreamEvent,
    AdminQueryTraceResponse,
    AdminQueryTraceSummaryResponse,
)
from src.api.content_freshness import (
    build_content_freshness_snapshot,
    clear_content_freshness_cache,
)
from src.api.indexing_runtime import start_background_indexing
from src.api.operator_alerts import build_admin_alert_summary
from src.api.storage_protection import build_storage_protection_snapshot
from src.api.access_policy import (
    configured_role_map,
    configured_role_tag_policies,
)
from src.api.auth_identity import (
    api_auth_label,
    proxy_identity_headers_enabled,
    proxy_identity_rotation_enabled,
    proxy_user_headers,
    resolve_request_auth_context,
    trusted_proxy_hosts,
)
from src.api.auth_audit import AuthAuditTracker
from src.api.browser_session import (
    browser_session_enabled,
    browser_session_invalid_before_iso,
    browser_session_rotation_enabled,
    browser_session_secret_source,
    cookie_should_be_secure,
    session_ttl_seconds,
)
from src.api.network_activity import build_network_activity_snapshot
from src.api.query_activity import QueryActivityTracker
from src.api.query_queue import QueryQueueFullError, QueryQueueTracker
from src.api.query_threads import ConversationThreadStore, conversation_history_db_path
from src.core.access_tags import default_document_tags, document_tag_rules
from src.core.query_trace import format_query_trace_text
from src.core.request_access import (
    reset_request_access_context,
    set_request_access_context,
)
from src.security.shared_deployment_auth import (
    resolve_deployment_mode,
    shared_api_auth_required,
    shared_api_auth_source,
    shared_online_enforced,
    shared_online_ready,
)
from src.security.protected_data import (
    ProtectedDataUnavailableError,
    history_encryption_enabled,
    history_encryption_rotation_enabled,
    history_secure_delete_enabled,
    history_encryption_source,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_RATE_LOCK = threading.Lock()
_RATE_STATE = {}


def _enforce_rate_limit(request: Request, scope: str) -> None:
    """Simple in-memory sliding-window limiter for expensive/mutable endpoints."""
    defaults = {
        "query": (30, 60),
        "query_stream": (15, 60),
        "index": (5, 300),
        "mode": (12, 300),
    }
    max_hits, window_s = defaults.get(scope, (30, 60))
    env_max = os.environ.get(f"HYBRIDRAG_RATE_{scope.upper()}_MAX", "").strip()
    env_window = os.environ.get(f"HYBRIDRAG_RATE_{scope.upper()}_WINDOW", "").strip()
    if env_max.isdigit():
        max_hits = max(1, int(env_max))
    if env_window.isdigit():
        window_s = max(1, int(env_window))
    now = time.monotonic()
    host = (
        getattr(getattr(request, "client", None), "host", None)
        or "unknown"
    )
    key = (host, scope)

    with _RATE_LOCK:
        q = _RATE_STATE.get(key)
        if q is None:
            q = deque()
            _RATE_STATE[key] = q
        cutoff = now - window_s
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_hits:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry later.",
            )
        q.append(now)
        # Evict stale and empty buckets (TTL-based, not just size-based)
        if len(_RATE_STATE) > 500:
            stale_keys = [
                k for k, v in _RATE_STATE.items()
                if not v or v[-1] < cutoff
            ]
            for k in stale_keys:
                del _RATE_STATE[k]


# -------------------------------------------------------------------
# Lazy import of shared state (avoids circular imports)
# -------------------------------------------------------------------
def _state():
    """Get the shared AppState singleton.

    Uses a function (not a top-level import) to avoid circular imports --
    server.py imports routes.py, so routes.py cannot import server.py
    at module level.
    """
    from src.api.server import state
    return state


def _version():
    """Get the app version string (same lazy-import pattern as _state)."""
    from src.api.server import APP_VERSION
    return APP_VERSION


def _current_user() -> str:
    """Best-effort user identity for shared deployment status surfaces."""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if user:
        return str(user)
    return str(os.environ.get("USERNAME") or os.environ.get("USER") or "")


def _query_activity_tracker() -> QueryActivityTracker:
    """Get or lazily create the shared query-activity tracker."""
    s = _state()
    tracker = getattr(s, "query_activity", None)
    if tracker is None:
        tracker = QueryActivityTracker.from_env()
        s.query_activity = tracker
    return tracker


def _auth_audit_tracker() -> AuthAuditTracker:
    """Get or lazily create the shared auth/security audit tracker."""
    s = _state()
    tracker = getattr(s, "auth_audit", None)
    if tracker is None:
        tracker = AuthAuditTracker.from_env()
        s.auth_audit = tracker
    return tracker


def _query_queue_tracker() -> QueryQueueTracker:
    """Get or lazily create the shared query queue tracker."""
    s = _state()
    tracker = getattr(s, "query_queue", None)
    if tracker is None:
        tracker = QueryQueueTracker.from_env()
        s.query_queue = tracker
    return tracker


def _conversation_thread_store() -> ConversationThreadStore:
    """Get or lazily create the persistent conversation-history store."""
    s = _state()
    store = getattr(s, "conversation_threads", None)
    if store is None:
        config = getattr(s, "config", None)
        database_path = str(getattr(getattr(config, "paths", None), "database", "") or "")
        if not database_path:
            raise HTTPException(status_code=503, detail="Conversation history is not initialized")
        store = ConversationThreadStore.from_database_path(database_path)
        s.conversation_threads = store
    return store


def _require_conversation_thread(thread_id: str | None) -> str | None:
    """Validate an existing conversation-thread target when one is provided."""
    key = str(thread_id or "").strip()
    if not key:
        return None
    if not _conversation_thread_store().thread_exists(key):
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    return key


def _record_completed_conversation_turn(
    *,
    thread_id: str | None,
    question: str,
    result,
    transport: str,
    actor: str,
    actor_source: str,
    actor_role: str,
    allowed_doc_tags: list[str],
    document_policy_source: str,
) -> tuple[str | None, int | None]:
    try:
        saved = _conversation_thread_store().record_completed_turn(
            thread_id=thread_id,
            question=question,
            result=result,
            transport=transport,
            actor=actor,
            actor_source=actor_source,
            actor_role=actor_role,
            allowed_doc_tags=allowed_doc_tags,
            document_policy_source=document_policy_source,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    except Exception as exc:
        logger.error("Conversation thread persistence failed: %s", exc, exc_info=True)
        return thread_id, None
    return str(saved.get("thread_id") or "") or None, int(saved.get("turn_index") or 0) or None


def _record_failed_conversation_turn(
    *,
    thread_id: str | None,
    question: str,
    error: str,
    mode: str,
    transport: str,
    actor: str,
    actor_source: str,
    actor_role: str,
    allowed_doc_tags: list[str],
    document_policy_source: str,
    latency_ms: float | None = None,
) -> tuple[str | None, int | None]:
    try:
        saved = _conversation_thread_store().record_failed_turn(
            thread_id=thread_id,
            question=question,
            error=error,
            mode=mode,
            transport=transport,
            actor=actor,
            actor_source=actor_source,
            actor_role=actor_role,
            allowed_doc_tags=allowed_doc_tags,
            document_policy_source=document_policy_source,
            latency_ms=latency_ms,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    except Exception as exc:
        logger.error("Conversation thread persistence failed: %s", exc, exc_info=True)
        return thread_id, None
    return str(saved.get("thread_id") or "") or None, int(saved.get("turn_index") or 0) or None


def _build_effective_query_text(question: str, thread_id: str | None) -> str:
    """Expand follow-up questions with bounded prior-thread context."""
    if not thread_id:
        return str(question or "")
    try:
        return _conversation_thread_store().build_follow_up_query(thread_id, question)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    except ProtectedDataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Conversation follow-up context build failed: %s", exc, exc_info=True)
        return str(question or "")


def _build_indexing_snapshot(s) -> IndexingSnapshot:
    """Build a consistent indexing snapshot from shared app state."""
    lock = getattr(s, "indexing_lock", None)
    if lock is not None:
        with lock:
            progress = dict(getattr(s, "index_progress", {}) or {})
            indexing_active = bool(getattr(s, "indexing_active", False))
    else:
        progress = dict(getattr(s, "index_progress", {}) or {})
        indexing_active = bool(getattr(s, "indexing_active", False))

    files_processed = int(progress.get("files_processed", 0) or 0)
    files_total = int(progress.get("files_total", 0) or 0)
    files_skipped = int(progress.get("files_skipped", 0) or 0)
    files_errored = int(progress.get("files_errored", 0) or 0)
    current_file = str(progress.get("current_file", "") or "")
    start_time = float(progress.get("start_time", 0.0) or 0.0)
    elapsed = time.time() - start_time if start_time else 0.0
    progress_pct = 0.0
    if files_total > 0:
        progress_pct = min(100.0, round((files_processed / files_total) * 100.0, 1))

    return IndexingSnapshot(
        active=indexing_active,
        files_processed=files_processed,
        files_total=files_total,
        files_skipped=files_skipped,
        files_errored=files_errored,
        current_file=current_file,
        elapsed_seconds=round(elapsed, 1),
        progress_pct=progress_pct,
    )


def _read_latest_index_run_summary(db_path: str) -> LatestIndexRunSummary | None:
    """Read the most recent persisted index run from the shared SQLite DB."""
    if not db_path or not os.path.exists(db_path):
        return None

    try:
        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                """
                SELECT run_id, status, started_at, finished_at, host, user, profile
                FROM index_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None

    if not row:
        return None

    return LatestIndexRunSummary(
        run_id=str(row[0] or ""),
        status=str(row[1] or ""),
        started_at=str(row[2] or ""),
        finished_at=str(row[3] or "") or None,
        host=str(row[4] or ""),
        user=str(row[5] or ""),
        profile=str(row[6] or ""),
    )


def _build_index_schedule_snapshot(s) -> IndexScheduleSnapshotResponse:
    """Build the recurring indexing scheduler snapshot for status surfaces."""
    tracker = getattr(s, "index_schedule", None)
    indexing_active = bool(getattr(s, "indexing_active", False))
    if tracker is None:
        return IndexScheduleSnapshotResponse(
            enabled=False,
            interval_seconds=0,
            source_folder="",
            indexing_active=indexing_active,
            due_now=False,
            next_run_at=None,
            last_started_at=None,
            last_finished_at=None,
            last_status="disabled",
            last_error="",
            last_trigger="",
            total_runs=0,
            total_success=0,
            total_failed=0,
        )
    return IndexScheduleSnapshotResponse(
        **tracker.snapshot(indexing_active=indexing_active)
    )


def _build_status_response() -> StatusResponse:
    """Build the shared status payload used by API and browser surfaces."""
    s = _state()
    if not s.vector_store or not s.config:
        raise HTTPException(status_code=503, detail="Server not initialized")

    try:
        stats = s.vector_store.get_stats()
    except Exception as e:
        logger.error("Failed to get stats: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve database stats"
        )

    from src.core.network_gate import get_gate

    gate_summary = get_gate().get_audit_summary()
    indexing = _build_indexing_snapshot(s)
    latest_index_run = _read_latest_index_run_summary(s.config.paths.database)
    query_activity = QueryActivitySummary(**_query_activity_tracker().summary())
    query_queue = QueryQueueSummary(**_query_queue_tracker().snapshot())
    index_schedule = _build_index_schedule_snapshot(s)

    return StatusResponse(
        status="ok",
        mode=s.config.mode,
        chunk_count=stats.get("chunk_count", 0),
        source_count=stats.get("source_count", 0),
        database_path=s.config.paths.database,
        embedding_model=s.config.embedding.model_name,
        ollama_model=s.config.ollama.model,
        deployment_mode=resolve_deployment_mode(s.config),
        current_user=_current_user(),
        api_auth_required=shared_api_auth_required(),
        indexing_active=indexing.active,
        indexing=indexing,
        query_activity=query_activity,
        query_queue=query_queue,
        network_audit=NetworkAuditSummary(
            mode=str(gate_summary.get("mode", "")),
            total_checks=int(gate_summary.get("total_checks", 0) or 0),
            allowed=int(gate_summary.get("allowed", 0) or 0),
            denied=int(gate_summary.get("denied", 0) or 0),
            allowed_hosts=list(gate_summary.get("allowed_hosts", []) or []),
            unique_hosts_contacted=list(gate_summary.get("unique_hosts_contacted", []) or []),
        ),
        latest_index_run=latest_index_run,
        index_schedule=index_schedule,
    )


def _build_auth_context_response(request: Request) -> AuthContextResponse:
    """Build the shared auth-context payload for API and browser surfaces."""
    context = resolve_request_auth_context(request)
    return AuthContextResponse(
        auth_required=context.auth_required,
        auth_mode=context.auth_mode,
        actor=context.actor,
        actor_source=context.actor_source,
        actor_role=context.actor_role,
        actor_role_source=context.actor_role_source,
        allowed_doc_tags=list(context.allowed_doc_tags),
        document_policy_source=context.document_policy_source,
        client_host=context.client_host,
        session_cookie_active=context.session_cookie_active,
        session_issued_at=context.session_issued_at,
        session_expires_at=context.session_expires_at,
        session_ttl_seconds=context.session_ttl_seconds,
        session_seconds_remaining=context.session_seconds_remaining,
        proxy_identity_trusted=context.proxy_identity_trusted,
        trusted_proxy_identity_headers=list(context.trusted_proxy_identity_headers),
    )


def _build_query_activity_response() -> QueryActivityResponse:
    """Build the detailed shared query-activity payload."""
    return QueryActivityResponse(**_query_activity_tracker().snapshot())


def _request_retrieval_access_context(context) -> dict[str, object]:
    """Project request auth into the core retrieval access context shape."""
    return {
        "actor": context.actor,
        "actor_source": context.actor_source,
        "actor_role": context.actor_role,
        "allowed_doc_tags": tuple(context.allowed_doc_tags),
        "document_policy_source": context.document_policy_source,
    }


def _build_config_response() -> ConfigResponse:
    """Build the shared config payload used by API and admin browser surfaces."""
    s = _state()
    if not s.config:
        raise HTTPException(status_code=503, detail="Server not initialized")

    from src.core.retriever import is_reranker_available

    c = s.config
    effective_reranker_enabled = bool(
        getattr(getattr(getattr(s, "query_engine", None), "retriever", None), "reranker_enabled", False)
    )
    return ConfigResponse(
        mode=c.mode,
        embedding_model=c.embedding.model_name,
        embedding_dimension=c.embedding.dimension,
        embedding_batch_size=c.embedding.batch_size,
        chunk_size=c.chunking.chunk_size,
        chunk_overlap=c.chunking.overlap,
        ollama_model=c.ollama.model,
        ollama_base_url=c.ollama.base_url,
        api_model=c.api.model,
        api_endpoint_configured=bool(c.api.endpoint),
        top_k=c.retrieval.top_k,
        min_score=c.retrieval.min_score,
        hybrid_search=c.retrieval.hybrid_search,
        reranker_enabled=effective_reranker_enabled,
        reranker_backend_available=is_reranker_available(c),
    )


def _trace_decision_path(trace: dict | None) -> str:
    decision = trace.get("decision", {}) if isinstance(trace, dict) else {}
    if not isinstance(decision, dict):
        return ""
    return str(decision.get("path", "") or "")


def _trace_final_hit_count(trace: dict | None) -> int:
    retrieval = trace.get("retrieval", {}) if isinstance(trace, dict) else {}
    if not isinstance(retrieval, dict):
        return 0
    counts = retrieval.get("counts", {})
    if not isinstance(counts, dict):
        return 0
    return int(counts.get("final_hits", 0) or 0)


def _recent_admin_query_traces() -> list[dict]:
    s = _state()
    query_engine = getattr(s, "query_engine", None)
    traces = getattr(query_engine, "recent_query_traces", None)
    if traces:
        return [trace for trace in list(traces) if isinstance(trace, dict)]

    latest = getattr(query_engine, "last_query_trace", None)
    if isinstance(latest, dict):
        return [latest]
    return []


def _build_admin_query_trace_response(trace: dict | None = None) -> AdminQueryTraceResponse:
    """Build an Admin-console query-trace payload."""
    if trace is None:
        s = _state()
        trace = getattr(getattr(s, "query_engine", None), "last_query_trace", None)
    if not trace:
        return AdminQueryTraceResponse(
            available=False,
            formatted_text=format_query_trace_text(None),
        )

    return AdminQueryTraceResponse(
        available=True,
        trace_id=str(trace.get("trace_id", "") or ""),
        captured_at=str(trace.get("captured_at", "") or "") or None,
        query=str(trace.get("query", "") or ""),
        decision_path=_trace_decision_path(trace),
        mode=str(trace.get("mode", "") or ""),
        active_profile=str(trace.get("active_profile", "") or ""),
        stream=bool(trace.get("stream", False)),
        final_hit_count=_trace_final_hit_count(trace),
        formatted_text=format_query_trace_text(trace),
        payload=trace,
    )


def _build_admin_query_trace_summary_response(trace: dict) -> AdminQueryTraceSummaryResponse:
    """Build one compact Admin-console trace-list entry."""
    return AdminQueryTraceSummaryResponse(
        trace_id=str(trace.get("trace_id", "") or ""),
        captured_at=str(trace.get("captured_at", "") or "") or None,
        query=str(trace.get("query", "") or ""),
        decision_path=_trace_decision_path(trace),
        mode=str(trace.get("mode", "") or ""),
        active_profile=str(trace.get("active_profile", "") or ""),
        stream=bool(trace.get("stream", False)),
        final_hit_count=_trace_final_hit_count(trace),
    )


def _build_recent_admin_query_trace_summaries(limit: int = 12) -> list[AdminQueryTraceSummaryResponse]:
    traces = _recent_admin_query_traces()
    if limit > 0:
        traces = traces[-limit:]
    return [
        _build_admin_query_trace_summary_response(trace)
        for trace in reversed(traces)
    ]


def _build_admin_query_trace_response_by_id(trace_id: str) -> AdminQueryTraceResponse:
    for trace in reversed(_recent_admin_query_traces()):
        if str(trace.get("trace_id", "") or "") == str(trace_id or ""):
            return _build_admin_query_trace_response(trace)
    raise HTTPException(status_code=404, detail="Query trace not found")


def _build_dashboard_snapshot(
    request: Request,
    *,
    network_limit: int = 8,
) -> DashboardSnapshotResponse:
    """Build the aggregated dashboard snapshot used by the browser console."""
    return DashboardSnapshotResponse(
        status=_build_status_response(),
        auth=_build_auth_context_response(request),
        queries=_build_query_activity_response(),
        network=NetworkActivityResponse(**build_network_activity_snapshot(network_limit)),
    )


def _build_conversation_thread_list_response(limit: int = 20) -> ConversationThreadListResponse:
    """Build the shared conversation-history listing payload."""
    try:
        payload = _conversation_thread_store().list_threads(limit=limit)
    except ProtectedDataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return ConversationThreadListResponse(**payload)


def _build_conversation_thread_response(thread_id: str) -> ConversationThreadResponse:
    """Build one persisted conversation thread with all stored turns."""
    try:
        payload = _conversation_thread_store().get_thread(thread_id)
    except ProtectedDataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if payload is None:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    return ConversationThreadResponse(**payload)


def _build_conversation_thread_export_response(thread_id: str) -> JSONResponse:
    """Return a downloadable JSON export of one persisted conversation thread."""
    try:
        payload = _conversation_thread_store().get_thread(thread_id)
    except ProtectedDataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if payload is None:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": (
                f'attachment; filename="hybridrag_thread_{str(thread_id or "").strip()}.json"'
            ),
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _shared_online_mode_enforced() -> bool:
    s = _state()
    return shared_online_enforced(getattr(s, "config", None))


def _shared_online_mode_ready() -> bool:
    s = _state()
    return shared_online_ready(getattr(s, "config", None))


def _require_shared_online_mode() -> None:
    """Fail closed when shared deployment traffic tries to use offline mode."""
    if _shared_online_mode_enforced() and not _shared_online_mode_ready():
        raise HTTPException(
            status_code=503,
            detail="Shared deployment access requires online mode. Switch the workstation back to online mode for shared use.",
        )


def _reject_shared_offline_mode_switch(new_mode: str) -> None:
    """Prevent the shared API surface from downgrading itself into offline mode."""
    if str(new_mode or "").strip().lower() == "offline" and _shared_online_mode_enforced():
        raise HTTPException(
            status_code=409,
            detail="Shared deployment mode switching cannot enter offline mode. Use a local admin workflow instead.",
        )


def _build_admin_runtime_safety_response(request: Request) -> AdminRuntimeSafetyResponse:
    """Build the operator-facing runtime safety summary for the Admin console."""
    s = _state()
    config = getattr(s, "config", None)
    query_cfg = getattr(config, "query", None)
    paths_cfg = getattr(config, "paths", None)
    return AdminRuntimeSafetyResponse(
        deployment_mode=resolve_deployment_mode(config),
        shared_online_enforced=_shared_online_mode_enforced(),
        shared_online_ready=_shared_online_mode_ready(),
        active_profile=str(getattr(config, "active_profile", "") or ""),
        grounding_bias=int(getattr(query_cfg, "grounding_bias", 0) or 0),
        allow_open_knowledge=bool(getattr(query_cfg, "allow_open_knowledge", False)),
        api_auth_required=shared_api_auth_required(),
        api_auth_source=shared_api_auth_source(),
        api_auth_label=api_auth_label(),
        browser_sessions_enabled=browser_session_enabled(),
        browser_session_secret_source=browser_session_secret_source(),
        browser_session_rotation_enabled=browser_session_rotation_enabled(),
        browser_session_ttl_seconds=session_ttl_seconds(),
        browser_session_invalid_before=browser_session_invalid_before_iso(),
        browser_session_secure_cookie=cookie_should_be_secure(
            str(getattr(getattr(request, "url", None), "scheme", "") or "")
        ),
        trusted_proxy_identity_enabled=proxy_identity_headers_enabled(),
        proxy_identity_secret_rotation_enabled=proxy_identity_rotation_enabled(),
        history_encryption_enabled=history_encryption_enabled(),
        history_encryption_source=history_encryption_source(),
        history_encryption_rotation_enabled=history_encryption_rotation_enabled(),
        history_secure_delete_enabled=history_secure_delete_enabled(),
        history_database_path=conversation_history_db_path(
            str(getattr(paths_cfg, "database", "") or "")
        ),
        trusted_proxy_hosts=list(trusted_proxy_hosts()),
        trusted_proxy_user_headers=list(proxy_user_headers()),
        source_folder=str(getattr(paths_cfg, "source_folder", "") or ""),
        database_path=str(getattr(paths_cfg, "database", "") or ""),
    )


def _trace_denied_hit_count(trace: dict | None) -> int:
    retrieval = trace.get("retrieval", {}) if isinstance(trace, dict) else {}
    if not isinstance(retrieval, dict):
        return 0
    access_control = retrieval.get("access_control", {})
    if not isinstance(access_control, dict):
        return 0
    return int(access_control.get("denied_hits", 0) or 0)


def _build_admin_access_policy_review_response() -> AdminAccessPolicyReviewResponse:
    """Build the operator-facing access-policy summary for the Admin console."""
    role_map = configured_role_map()
    role_tag_policies = configured_role_tag_policies()
    doc_rules = document_tag_rules()
    denied_traces = [
        trace for trace in _recent_admin_query_traces()
        if _trace_denied_hit_count(trace) > 0
    ]
    latest_denied = denied_traces[-1] if denied_traces else {}
    return AdminAccessPolicyReviewResponse(
        default_document_tags=list(default_document_tags()),
        role_map=[
            f"{actor} -> {role}"
            for actor, role in sorted(role_map.items())
        ],
        role_tag_policies=[
            f"{role}: {', '.join(tags)}"
            for role, tags in sorted(role_tag_policies.items())
        ],
        document_tag_rules=[
            f"{pattern}: {', '.join(tags)}"
            for pattern, tags in doc_rules
        ],
        recent_denied_traces=len(denied_traces),
        latest_denied_trace_id=str(latest_denied.get("trace_id", "") or "") or None,
        latest_denied_query=str(latest_denied.get("query", "") or ""),
    )


def _build_admin_index_schedule_response() -> AdminIndexScheduleResponse:
    """Build the operator-facing scheduled indexing snapshot."""
    s = _state()
    return AdminIndexScheduleResponse(
        **_build_index_schedule_snapshot(s).model_dump()
    )


def _build_admin_content_freshness_response() -> AdminContentFreshnessResponse:
    """Build the operator-facing freshness/drift snapshot for source content."""
    s = _state()
    config = getattr(s, "config", None)
    paths_cfg = getattr(config, "paths", None)
    indexing_cfg = getattr(config, "indexing", None)
    db_path = str(getattr(paths_cfg, "database", "") or "")
    latest_index_run = _read_latest_index_run_summary(db_path) if db_path else None
    warn_after_hours = 24
    raw_warn = str(os.environ.get("HYBRIDRAG_INDEX_FRESHNESS_WARN_HOURS", "") or "").strip()
    if raw_warn.isdigit():
        warn_after_hours = max(1, int(raw_warn))
    return AdminContentFreshnessResponse(
        **build_content_freshness_snapshot(
            str(getattr(paths_cfg, "source_folder", "") or ""),
            latest_index_started_at=str(getattr(latest_index_run, "started_at", "") or ""),
            latest_index_finished_at=str(getattr(latest_index_run, "finished_at", "") or ""),
            latest_index_status=str(getattr(latest_index_run, "status", "") or ""),
            supported_extensions=list(getattr(indexing_cfg, "supported_extensions", []) or []),
            excluded_dirs=list(getattr(indexing_cfg, "excluded_dirs", []) or []),
            warn_after_hours=warn_after_hours,
        )
    )


def _refresh_admin_content_freshness_response() -> AdminContentFreshnessResponse:
    """Force a fresh source-tree scan for the operator freshness snapshot."""
    clear_content_freshness_cache()
    return _build_admin_content_freshness_response()


def _build_admin_storage_protection_response() -> AdminStorageProtectionResponse:
    """Build the operator-facing protected-storage snapshot."""
    s = _state()
    config = getattr(s, "config", None)
    paths_cfg = getattr(config, "paths", None)
    return AdminStorageProtectionResponse(
        **build_storage_protection_snapshot(
            str(getattr(paths_cfg, "database", "") or "")
        )
    )


def _build_admin_alert_summary_response(
    *,
    dashboard_status,
    runtime_safety,
    index_schedule,
    freshness,
    security_activity,
    access_policy,
    storage_protection,
) -> AdminAlertSummaryResponse:
    """Build the operator-facing alert summary for the Admin console."""
    return AdminAlertSummaryResponse(
        **build_admin_alert_summary(
            dashboard_status=dashboard_status.model_dump(),
            runtime_safety=runtime_safety.model_dump(),
            index_schedule=index_schedule.model_dump(),
            freshness=freshness.model_dump(),
            security_activity=security_activity.model_dump(),
            access_policy=access_policy.model_dump(),
            storage_protection=storage_protection.model_dump(),
        )
    )


def _build_admin_security_activity_response(limit: int = 12) -> AdminSecurityActivityResponse:
    """Build the operator-facing security activity snapshot."""
    return AdminSecurityActivityResponse(
        **_auth_audit_tracker().snapshot(limit=limit)
    )


def _repo_root_path() -> Path:
    return Path(__file__).resolve().parents[2]


def _logs_dir_path() -> Path:
    return _repo_root_path() / "logs"


def _tail_text_lines(path: Path, limit: int) -> list[str]:
    if limit <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\r\n") for line in handle.readlines()[-limit:]]
    except OSError:
        return []


def _summarize_log_payload(payload: dict[str, object]) -> str:
    candidates = (
        payload.get("error"),
        payload.get("detail"),
        payload.get("query"),
        payload.get("action"),
        payload.get("mode"),
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text[:140]
    return ""


def _build_operator_log_snapshot(
    *,
    app_limit: int = 8,
    index_limit: int = 6,
) -> AdminOperatorLogSnapshotResponse:
    """Build a compact operator log snapshot from repo-local log artifacts."""
    log_dir = _logs_dir_path()
    app_entries: list[AdminAppLogEntryResponse] = []
    app_log_file = ""
    app_log_paths = sorted(
        log_dir.glob("app_*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if app_log_paths:
        active_log = app_log_paths[0]
        app_log_file = active_log.name
        for raw_line in reversed(_tail_text_lines(active_log, app_limit)):
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            app_entries.append(
                AdminAppLogEntryResponse(
                    timestamp=str(payload.get("timestamp", "") or ""),
                    event=str(payload.get("event", "") or ""),
                    summary=_summarize_log_payload(payload),
                    log_file=active_log.name,
                )
            )

    index_reports = [
        AdminIndexReportEntryResponse(
            file_name=path.name,
            modified_at=time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.localtime(path.stat().st_mtime),
            ),
            size_bytes=int(path.stat().st_size),
        )
        for path in sorted(
            log_dir.glob("index_report_*.txt"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: max(0, index_limit)]
    ]

    return AdminOperatorLogSnapshotResponse(
        app_log_file=app_log_file,
        app_log_entries=app_entries,
        index_reports=index_reports,
    )


def _build_admin_console_snapshot(
    request: Request,
    *,
    network_limit: int = 20,
) -> AdminConsoleSnapshotResponse:
    """Build the aggregated snapshot used by the Admin browser console."""
    dashboard = _build_dashboard_snapshot(request, network_limit=network_limit)
    config = _build_config_response()
    runtime_safety = _build_admin_runtime_safety_response(request)
    access_policy = _build_admin_access_policy_review_response()
    index_schedule = _build_admin_index_schedule_response()
    freshness = _build_admin_content_freshness_response()
    storage_protection = _build_admin_storage_protection_response()
    security_activity = _build_admin_security_activity_response()
    alerts = _build_admin_alert_summary_response(
        dashboard_status=dashboard.status,
        runtime_safety=runtime_safety,
        index_schedule=index_schedule,
        freshness=freshness,
        security_activity=security_activity,
        access_policy=access_policy,
        storage_protection=storage_protection,
    )
    return AdminConsoleSnapshotResponse(
        dashboard=dashboard,
        config=config,
        runtime_safety=runtime_safety,
        access_policy=access_policy,
        index_schedule=index_schedule,
        freshness=freshness,
        storage_protection=storage_protection,
        alerts=alerts,
        security_activity=security_activity,
        operator_logs=_build_operator_log_snapshot(),
        latest_query_trace=_build_admin_query_trace_response(),
        recent_query_traces=_build_recent_admin_query_trace_summaries(),
    )


def _request_admin_index_stop() -> AdminIndexControlResponse:
    """Signal the shared indexing worker to stop."""
    s = _state()
    thread = getattr(s, "indexing_thread", None)
    active = bool(getattr(s, "indexing_active", False))
    thread_alive = bool(thread and thread.is_alive())
    if not active and not thread_alive:
        raise HTTPException(status_code=409, detail="No active indexing job to stop.")

    s.indexing_stop_event.set()
    return AdminIndexControlResponse(
        ok=True,
        message="Stop requested for the active indexing job.",
        indexing_active=active or thread_alive,
        stop_requested=True,
    )


def _request_admin_reindex_if_stale() -> AdminIndexControlResponse:
    """Start a maintenance reindex only when the source tree is stale."""
    s = _state()
    freshness = _build_admin_content_freshness_response()
    if not freshness.source_exists:
        raise HTTPException(
            status_code=409,
            detail="Configured source folder is missing or not accessible.",
        )

    active = bool(getattr(s, "indexing_active", False))
    thread = getattr(s, "indexing_thread", None)
    thread_alive = bool(thread and thread.is_alive())
    if active or thread_alive:
        return AdminIndexControlResponse(
            ok=True,
            message="Indexing is already active; no maintenance run was started.",
            indexing_active=True,
            stop_requested=False,
        )

    if not freshness.stale:
        return AdminIndexControlResponse(
            ok=True,
            message="Content is already fresh; no maintenance run was started.",
            indexing_active=False,
            stop_requested=False,
        )

    started = start_background_indexing(
        s,
        freshness.source_folder,
        trigger="maintenance",
    )
    if not started:
        raise HTTPException(
            status_code=409,
            detail="Unable to start a maintenance indexing run right now.",
        )

    return AdminIndexControlResponse(
        ok=True,
        message="Freshness maintenance run started.",
        indexing_active=True,
        stop_requested=False,
    )


def _set_admin_index_schedule_enabled(enabled: bool) -> AdminIndexScheduleControlResponse:
    """Pause or resume the recurring indexing schedule."""
    s = _state()
    tracker = getattr(s, "index_schedule", None)
    if tracker is None:
        raise HTTPException(status_code=503, detail="Index schedule is not initialized.")
    if enabled:
        tracker.resume()
        snapshot = tracker.snapshot(indexing_active=bool(getattr(s, "indexing_active", False)))
        return AdminIndexScheduleControlResponse(
            ok=True,
            enabled=True,
            last_status=str(snapshot.get("last_status", "") or ""),
            next_run_at=snapshot.get("next_run_at"),
            message="Recurring index schedule resumed.",
        )
    tracker.pause()
    return AdminIndexScheduleControlResponse(
        ok=True,
        enabled=False,
        last_status="paused",
        next_run_at=None,
        message="Recurring index schedule paused.",
    )


# -------------------------------------------------------------------
# GET /health
# -------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse)
async def health():
    """Fast health check. Returns 200 if the server process is alive.

    This endpoint has zero dependencies -- it does not check the database,
    embedder, or LLM.  Use GET /status for a deeper readiness check.
    Useful for load balancer health probes and uptime monitors.
    """
    return HealthResponse(status="ok", version=_version())


# -------------------------------------------------------------------
# GET /status
# -------------------------------------------------------------------
@router.get("/status", response_model=StatusResponse)
async def status():
    """Database stats, current mode, and component status.

    Returns chunk count, source count, embedding model name, and
    current mode (offline/online).  Returns 503 if the server has
    not finished initializing.
    """
    return _build_status_response()


# -------------------------------------------------------------------
# GET /auth/context
# -------------------------------------------------------------------
@router.get("/auth/context", response_model=AuthContextResponse)
async def auth_context(request: Request):
    """Return resolved auth and actor context for the current request."""
    return _build_auth_context_response(request)


# -------------------------------------------------------------------
# GET /activity/query-queue
# -------------------------------------------------------------------
@router.get("/activity/query-queue", response_model=QueryQueueSummary)
async def query_queue_activity(request: Request):
    """Return shared query queue and concurrency status for dashboards."""
    resolve_request_auth_context(request)
    return QueryQueueSummary(**_query_queue_tracker().snapshot())


# -------------------------------------------------------------------
# GET /activity/queries
# -------------------------------------------------------------------
@router.get("/activity/queries", response_model=QueryActivityResponse)
async def query_activity(request: Request):
    """Return active and recent query activity for shared deployment dashboards."""
    resolve_request_auth_context(request)
    return _build_query_activity_response()


# -------------------------------------------------------------------
# GET /history/threads
# -------------------------------------------------------------------
@router.get("/history/threads", response_model=ConversationThreadListResponse)
async def conversation_threads(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return the persisted shared conversation-thread history."""
    resolve_request_auth_context(request)
    _require_shared_online_mode()
    return _build_conversation_thread_list_response(limit=limit)


# -------------------------------------------------------------------
# GET /history/threads/{thread_id}
# -------------------------------------------------------------------
@router.get("/history/threads/{thread_id}", response_model=ConversationThreadResponse)
async def conversation_thread_detail(request: Request, thread_id: str):
    """Return one persisted conversation thread with all saved turns."""
    resolve_request_auth_context(request)
    _require_shared_online_mode()
    return _build_conversation_thread_response(thread_id)


# -------------------------------------------------------------------
# GET /history/threads/{thread_id}/export
# -------------------------------------------------------------------
@router.get("/history/threads/{thread_id}/export")
async def conversation_thread_export(request: Request, thread_id: str):
    """Return a downloadable JSON export for one persisted conversation thread."""
    resolve_request_auth_context(request)
    _require_shared_online_mode()
    return _build_conversation_thread_export_response(thread_id)


# -------------------------------------------------------------------
# GET /activity/network
# -------------------------------------------------------------------
@router.get("/activity/network", response_model=NetworkActivityResponse)
async def network_activity(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return recent detailed network-gate audit entries for shared dashboards."""
    resolve_request_auth_context(request)
    return NetworkActivityResponse(**build_network_activity_snapshot(limit))


# -------------------------------------------------------------------
# GET /config
# -------------------------------------------------------------------
@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """Return current configuration (read-only, no secrets).

    Exposes retrieval parameters, model names, chunk sizes, and mode.
    API keys and endpoints are NOT included -- only a boolean flag
    indicating whether an endpoint is configured.
    """
    return _build_config_response()


# -------------------------------------------------------------------
# POST /query
# -------------------------------------------------------------------
@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request):
    """
    Ask a question about your indexed documents.

    Returns the AI-generated answer with source citations,
    chunk count, token usage, cost, and latency.
    """
    import asyncio

    s = _state()
    if not s.query_engine:
        raise HTTPException(status_code=503, detail="Query engine not initialized")
    context = resolve_request_auth_context(request)
    _require_shared_online_mode()
    _enforce_rate_limit(request, "query")
    thread_id = _require_conversation_thread(req.thread_id)
    effective_question = _build_effective_query_text(req.question, thread_id)
    history_kwargs = {
        "actor": context.actor,
        "actor_source": context.actor_source,
        "actor_role": context.actor_role,
        "allowed_doc_tags": list(context.allowed_doc_tags),
        "document_policy_source": context.document_policy_source,
    }
    queue = _query_queue_tracker()
    try:
        await asyncio.to_thread(queue.acquire)
    except QueryQueueFullError:
        raise HTTPException(status_code=503, detail="Query queue is full. Retry later.")
    activity = _query_activity_tracker().start(
        question=req.question,
        mode=str(getattr(s.config, "mode", "")),
        transport="sync",
        client_host=context.client_host,
        actor=context.actor,
        actor_source=context.actor_source,
        actor_role=context.actor_role,
        allowed_doc_tags=list(context.allowed_doc_tags),
        document_policy_source=context.document_policy_source,
        thread_id=thread_id,
    )

    # Timeout: prevent hung LLM calls from blocking indefinitely.
    # Online mode uses api.timeout_seconds (default 60s);
    # Offline mode uses ollama.timeout_seconds (default 600s).
    # Capped at 600s as an absolute ceiling.
    if getattr(s.config, "mode", "offline") == "online":
        timeout_sec = min(
            getattr(getattr(s.config, "api", None), "timeout_seconds", 60),
            600,
        )
    else:
        timeout_sec = min(
            getattr(getattr(s.config, "ollama", None), "timeout_seconds", 600),
            600,
        )
    access_token = set_request_access_context(_request_retrieval_access_context(context))
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(s.query_engine.query, effective_question),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        saved_thread_id, saved_turn_index = _record_failed_conversation_turn(
            thread_id=thread_id,
            question=req.question,
            error="query_timeout",
            mode=str(getattr(s.config, "mode", "")),
            transport="sync",
            **history_kwargs,
        )
        if saved_thread_id:
            activity.set_thread_context(saved_thread_id, saved_turn_index)
        activity.finish_error("query_timeout", mode=str(getattr(s.config, "mode", "")))
        raise HTTPException(
            status_code=504, detail="Query timed out. Try a shorter question or check LLM status."
        )
    except Exception as e:
        saved_thread_id, saved_turn_index = _record_failed_conversation_turn(
            thread_id=thread_id,
            question=req.question,
            error=f"{type(e).__name__}: {e}",
            mode=str(getattr(s.config, "mode", "")),
            transport="sync",
            **history_kwargs,
        )
        if saved_thread_id:
            activity.set_thread_context(saved_thread_id, saved_turn_index)
        activity.finish_error(
            f"{type(e).__name__}: {e}",
            mode=str(getattr(s.config, "mode", "")),
        )
        logger.error("Query execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Query execution failed")
    finally:
        reset_request_access_context(access_token)
        queue.release()

    # Record cost event for PM dashboard (mirrors GUI query_panel behavior)
    try:
        from src.core.cost_tracker import get_cost_tracker
        tracker = get_cost_tracker()
        model = getattr(
            getattr(s.config, "ollama" if result.mode == "offline" else "api", None),
            "model", "",
        ) or ""
        tracker.record(
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            model=model,
            mode=result.mode,
            profile="api",
            latency_ms=result.latency_ms,
        )
    except Exception as e:
        logger.debug("Cost event emit failed: %s", e)

    # Degrade gracefully when backend query fails: keep endpoint usable
    # and return a structured response with the error populated.
    if result.error:
        logger.warning("Query returned error: %s", result.error)
        if not result.answer:
            result.answer = (
                "Query backend unavailable right now. "
                "Try again after verifying model/API connectivity."
            )
    saved_thread_id, saved_turn_index = _record_completed_conversation_turn(
        thread_id=thread_id,
        question=req.question,
        result=result,
        transport="sync",
        **history_kwargs,
    )
    if saved_thread_id:
        activity.set_thread_context(saved_thread_id, saved_turn_index)
    activity.finish_result(result)

    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        chunks_used=result.chunks_used,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        mode=result.mode,
        error=result.error,
        thread_id=saved_thread_id,
        turn_index=saved_turn_index,
    )


# -------------------------------------------------------------------
# POST /query/stream  (Server-Sent Events)
# -------------------------------------------------------------------
@router.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request):
    """
    Stream a query response as Server-Sent Events.

    Event types:
      event: phase   -- data is the current phase name
      event: token   -- data is a partial text token
      event: done    -- data is JSON with full QueryResponse fields
      event: error   -- data is the error message
    """
    s = _state()
    if not s.query_engine:
        raise HTTPException(status_code=503, detail="Query engine not initialized")
    import asyncio

    context = resolve_request_auth_context(request)
    _require_shared_online_mode()
    _enforce_rate_limit(request, "query_stream")
    thread_id = _require_conversation_thread(req.thread_id)
    effective_question = _build_effective_query_text(req.question, thread_id)
    history_kwargs = {
        "actor": context.actor,
        "actor_source": context.actor_source,
        "actor_role": context.actor_role,
        "allowed_doc_tags": list(context.allowed_doc_tags),
        "document_policy_source": context.document_policy_source,
    }
    queue = _query_queue_tracker()
    try:
        await asyncio.to_thread(queue.acquire)
    except QueryQueueFullError:
        raise HTTPException(status_code=503, detail="Query queue is full. Retry later.")
    activity = _query_activity_tracker().start(
        question=req.question,
        mode=str(getattr(s.config, "mode", "")),
        transport="stream",
        client_host=context.client_host,
        actor=context.actor,
        actor_source=context.actor_source,
        actor_role=context.actor_role,
        allowed_doc_tags=list(context.allowed_doc_tags),
        document_policy_source=context.document_policy_source,
        thread_id=thread_id,
    )

    if not hasattr(s.query_engine, "query_stream"):
        activity.finish_error(
            "streaming_not_supported",
            mode=str(getattr(s.config, "mode", "")),
        )
        raise HTTPException(status_code=501, detail="Streaming not supported")

    def _generate():
        final_result = None
        persisted_thread_id = None
        persisted_turn_index = None
        stream_iter = iter(s.query_engine.query_stream(effective_question))
        try:
            while True:
                access_token = set_request_access_context(_request_retrieval_access_context(context))
                try:
                    chunk = next(stream_iter)
                except StopIteration:
                    break
                finally:
                    reset_request_access_context(access_token)
                if "phase" in chunk:
                    yield "event: phase\ndata: {}\n\n".format(chunk["phase"])
                elif "token" in chunk:
                    yield "event: token\ndata: {}\n\n".format(
                        chunk["token"].replace("\n", "\ndata: ")
                    )
                elif chunk.get("done"):
                    result = chunk.get("result")
                    if result:
                        final_result = result
                        if persisted_thread_id is None:
                            persisted_thread_id, persisted_turn_index = _record_completed_conversation_turn(
                                thread_id=thread_id,
                                question=req.question,
                                result=final_result,
                                transport="stream",
                                **history_kwargs,
                            )
                            if persisted_thread_id:
                                activity.set_thread_context(
                                    persisted_thread_id,
                                    persisted_turn_index,
                                )
                        payload = json.dumps({
                            "answer": result.answer,
                            "sources": result.sources,
                            "chunks_used": result.chunks_used,
                            "tokens_in": result.tokens_in,
                            "tokens_out": result.tokens_out,
                            "cost_usd": result.cost_usd,
                            "latency_ms": result.latency_ms,
                            "mode": result.mode,
                            "error": result.error,
                            "thread_id": persisted_thread_id,
                            "turn_index": persisted_turn_index,
                        })
                        yield "event: done\ndata: {}\n\n".format(payload)
            if final_result is not None:
                activity.finish_result(final_result)
            else:
                saved_thread_id, saved_turn_index = _record_failed_conversation_turn(
                    thread_id=thread_id,
                    question=req.question,
                    error="stream_finished_without_result",
                    mode=str(getattr(s.config, "mode", "")),
                    transport="stream",
                    **history_kwargs,
                )
                if saved_thread_id:
                    activity.set_thread_context(saved_thread_id, saved_turn_index)
                activity.finish_error(
                    "stream_finished_without_result",
                    mode=str(getattr(s.config, "mode", "")),
                )
                yield "event: error\ndata: Stream ended without final result\n\n"
        except Exception as e:
            saved_thread_id, saved_turn_index = _record_failed_conversation_turn(
                thread_id=thread_id,
                question=req.question,
                error=f"{type(e).__name__}: {e}",
                mode=str(getattr(s.config, "mode", "")),
                transport="stream",
                **history_kwargs,
            )
            if saved_thread_id:
                activity.set_thread_context(saved_thread_id, saved_turn_index)
            activity.finish_error(
                f"{type(e).__name__}: {e}",
                mode=str(getattr(s.config, "mode", "")),
            )
            logger.error("Streaming query failed: %s", e, exc_info=True)
            yield "event: error\ndata: Internal server error\n\n"
        finally:
            queue.release()

    return StreamingResponse(
        iterate_in_threadpool(_generate()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# -------------------------------------------------------------------
# POST /index
# -------------------------------------------------------------------
@router.post("/index", response_model=IndexStartResponse)
async def start_indexing(request: Request, req: IndexRequest = None):
    """
    Start document indexing in a background thread.

    If indexing is already running, returns 409 Conflict.
    Check progress with GET /index/status.
    """
    s = _state()
    if not s.config or not s.vector_store or not s.embedder:
        raise HTTPException(status_code=503, detail="Server not initialized")
    resolve_request_auth_context(request)
    _enforce_rate_limit(request, "index")

    # Validate source folder BEFORE acquiring lock so validation
    # failures don't leave indexing_active stuck True.
    source_folder = (
        req.source_folder if req and req.source_folder
        else s.config.paths.source_folder
    )

    if not source_folder or not os.path.isdir(source_folder):
        logger.warning("Index request for missing folder: %s", source_folder)
        raise HTTPException(
            status_code=400,
            detail="Source folder not found or not accessible",
        )

    # Path traversal prevention: the requested folder must be within
    # the configured source directory.  This blocks "../../../etc/passwd"
    # style attacks via the source_folder parameter.
    # SECURITY: use os.sep suffix to prevent prefix collision
    # (e.g. D:\data_evil passing for allowed root D:\data).
    allowed_root = os.path.realpath(s.config.paths.source_folder)
    requested = os.path.realpath(source_folder)
    if requested != allowed_root and not requested.startswith(allowed_root + os.sep):
        raise HTTPException(
            status_code=403,
            detail="Source folder must be within the configured source directory.",
        )

    if not start_background_indexing(s, source_folder):
        raise HTTPException(
            status_code=409,
            detail="Indexing is already in progress. Check GET /index/status.",
        )

    return IndexStartResponse(
        message="Indexing started in background. Check GET /index/status.",
        source_folder=source_folder,
    )


# -------------------------------------------------------------------
# GET /index/status
# -------------------------------------------------------------------
@router.get("/index/status", response_model=IndexStatusResponse)
async def index_status():
    """Check the progress of a running indexing job.

    Returns file counts (processed, skipped, errored), current file name,
    and elapsed time.  Safe to poll repeatedly -- this is a read-only
    check against in-memory counters updated by the indexing callback.
    """
    s = _state()
    snapshot = _build_indexing_snapshot(s)

    return IndexStatusResponse(
        indexing_active=snapshot.active,
        files_processed=snapshot.files_processed,
        files_total=snapshot.files_total,
        files_skipped=snapshot.files_skipped,
        files_errored=snapshot.files_errored,
        current_file=snapshot.current_file,
        elapsed_seconds=snapshot.elapsed_seconds,
    )


# -------------------------------------------------------------------
# PUT /mode
# -------------------------------------------------------------------
@router.put("/mode", response_model=ModeResponse)
async def set_mode(req: ModeRequest, request: Request):
    """
    Switch between offline (Ollama) and online (API) mode.

    Changes take effect immediately. The YAML config file is
    also updated so the change persists across restarts.
    """
    s = _state()
    if not s.config:
        raise HTTPException(status_code=503, detail="Server not initialized")
    resolve_request_auth_context(request)
    _enforce_rate_limit(request, "mode")

    new_mode = req.mode
    _reject_shared_offline_mode_switch(new_mode)

    # Validate online mode requirements
    if new_mode == "online" and not s.config.api.endpoint:
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to online mode: API endpoint not configured. "
                   "Use rag-store-endpoint to set it first.",
        )

    # Build new router with a config copy so concurrent readers never
    # see new_mode until the swap is complete (no transient partial state).
    import copy
    from src.core.llm_router import LLMRouter
    from src.core.config_authority import set_runtime_active_mode
    from src.core.query_engine import refresh_query_engine_runtime
    from src.gui.helpers.mode_tuning import apply_mode_settings_to_config
    old_router = getattr(s, "llm_router", None)
    build_config = copy.copy(s.config)
    build_config.mode = new_mode
    apply_mode_settings_to_config(build_config, new_mode)
    try:
        new_router = LLMRouter(build_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Router creation failed: {e}")

    # All succeeded -- atomic swap: router first, then mode
    s.llm_router = new_router
    s.query_engine.llm_router = new_router
    s.config.mode = new_mode
    apply_mode_settings_to_config(s.config, new_mode)
    set_runtime_active_mode(new_mode)
    refresh_query_engine_runtime(s.query_engine, clear_caches=True)
    if old_router and hasattr(old_router, "close"):
        old_router.close()

    # Reconfigure network gate to match new mode
    try:
        from src.core.network_gate import configure_gate
        if new_mode == "online":
            from src.security.credentials import resolve_credentials
            creds = resolve_credentials()
            configure_gate(
                mode="online",
                api_endpoint=creds.endpoint or "",
                allowed_prefixes=getattr(
                    getattr(s.config, "api", None),
                    "allowed_endpoint_prefixes", [],
                ) if s.config else [],
            )
        else:
            configure_gate(mode="offline")
    except Exception as e:
        logger.warning("Gate reconfiguration failed: %s", e)

    # Invalidate deployment cache so model list reflects new mode
    from src.core.llm_router import invalidate_deployment_cache
    invalidate_deployment_cache()

    # Persist to YAML
    _update_yaml_mode(new_mode)

    return ModeResponse(
        mode=new_mode,
        message=f"Switched to {new_mode} mode.",
    )


# -------------------------------------------------------------------
# Helper: update mode in YAML config
# -------------------------------------------------------------------
def _update_yaml_mode(new_mode: str) -> None:
    """Write mode change to the primary config authority."""
    from src.core.config import save_config_field
    save_config_field("mode", new_mode)
