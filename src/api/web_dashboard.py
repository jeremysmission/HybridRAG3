from __future__ import annotations
import os
import threading
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.api.auth_identity import (
    api_token_matches,
    api_auth_label,
    configured_api_auth_token,
    resolve_request_auth_context,
)
from src.api.auth_audit import record_auth_event
from src.api.browser_session import (
    SESSION_COOKIE_NAME,
    cookie_should_be_secure,
    create_browser_session,
    parse_browser_session,
    session_ttl_seconds,
)
from src.api.deployment_dashboard import (
    build_admin_console_html,
    build_dashboard_page_html,
    build_login_page_html,
)
from src.api.models import (
    AdminConsoleSnapshotResponse,
    AdminContentFreshnessResponse,
    AdminIndexControlResponse,
    AdminIndexScheduleControlResponse,
    AdminQueryTraceResponse,
    BrowserAuthResponse,
    BrowserLoginRequest,
    DashboardSnapshotResponse,
)
from src.api.routes import (
    _build_admin_console_snapshot,
    _build_admin_query_trace_response_by_id,
    _build_dashboard_snapshot,
    _refresh_admin_content_freshness_response,
    _require_shared_online_mode,
    _request_admin_reindex_if_stale,
    _request_admin_index_stop,
    _set_admin_index_schedule_enabled,
)
from src.security.shared_deployment_auth import resolve_deployment_mode


router = APIRouter()

_LOGIN_RATE_LOCK = threading.Lock()
_LOGIN_RATE_STATE: dict[str, deque[float]] = {}


def _login_rate_limit(request: Request) -> None:
    """Throttle repeated browser login attempts from the same host."""
    max_hits = 8
    window_s = 300
    raw_max = (os.environ.get("HYBRIDRAG_RATE_LOGIN_MAX") or "").strip()
    raw_window = (os.environ.get("HYBRIDRAG_RATE_LOGIN_WINDOW") or "").strip()
    if raw_max.isdigit():
        max_hits = max(1, int(raw_max))
    if raw_window.isdigit():
        window_s = max(30, int(raw_window))

    host = str(getattr(getattr(request, "client", None), "host", None) or "unknown")
    now = time.monotonic()
    with _LOGIN_RATE_LOCK:
        entries = _LOGIN_RATE_STATE.get(host)
        if entries is None:
            entries = deque()
            _LOGIN_RATE_STATE[host] = entries
        cutoff = now - window_s
        while entries and entries[0] < cutoff:
            entries.popleft()
        if len(entries) >= max_hits:
            record_auth_event(
                request,
                event="login_rate_limited",
                outcome="rate_limited",
                detail="Too many browser login attempts from the same host.",
            )
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        entries.append(now)


def _deployment_mode() -> str:
    from src.api.server import state

    return resolve_deployment_mode(getattr(state, "config", None))


def _set_session_cookie(response: JSONResponse | HTMLResponse, request: Request, *, actor: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_browser_session(actor=actor, actor_source="session_cookie"),
        max_age=session_ttl_seconds(),
        httponly=True,
        secure=cookie_should_be_secure(getattr(getattr(request, "url", None), "scheme", "")),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def _require_admin_console_access(request: Request):
    """Require the admin role for Admin web routes when shared auth is active."""
    context = resolve_request_auth_context(request)
    if configured_api_auth_token() and str(context.actor_role or "").strip().lower() != "admin":
        record_auth_event(
            request,
            event="admin_access_denied",
            outcome="denied",
            detail=f"actor_role={context.actor_role or 'unknown'}",
            actor=context.actor,
        )
        raise HTTPException(status_code=403, detail="Admin role required.")
    return context


@router.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page(request: Request):
    """Render the browser login page for shared deployments."""
    if not configured_api_auth_token():
        return RedirectResponse(url="/dashboard", status_code=303)

    try:
        resolve_request_auth_context(request)
    except HTTPException:
        return HTMLResponse(
            build_login_page_html(
                deployment_mode=_deployment_mode(),
                auth_label=api_auth_label(),
            ),
            headers={"Cache-Control": "no-store"},
        )

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/auth/login", response_model=BrowserAuthResponse)
async def auth_login(request: Request, payload: BrowserLoginRequest):
    """Validate the shared browser token and mint an HTTP-only session cookie."""
    expected = configured_api_auth_token()
    if not expected:
        raise HTTPException(
            status_code=400,
            detail="Browser login is disabled because HYBRIDRAG_API_AUTH_TOKEN is not configured.",
        )

    _login_rate_limit(request)
    if not api_token_matches(payload.token):
        record_auth_event(
            request,
            event="invalid_login",
            outcome="denied",
            detail="Browser login used an invalid shared token.",
            actor=api_auth_label(),
        )
        raise HTTPException(status_code=401, detail="Invalid shared token.")

    actor = api_auth_label()
    response = JSONResponse(
        {
            "ok": True,
            "redirect_to": "/dashboard",
            "actor": actor,
        }
    )
    _set_session_cookie(response, request, actor=actor)
    return response


@router.post("/auth/logout", response_model=BrowserAuthResponse)
async def auth_logout():
    """Clear the browser session cookie."""
    redirect_to = "/auth/login" if configured_api_auth_token() else "/dashboard"
    response = JSONResponse(
        {
            "ok": True,
            "redirect_to": redirect_to,
            "actor": None,
        }
    )
    _clear_session_cookie(response)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the shared deployment dashboard shell."""
    auth_required = bool(configured_api_auth_token())
    context = None
    if auth_required:
        try:
            context = resolve_request_auth_context(request)
        except HTTPException:
            return RedirectResponse(url="/auth/login", status_code=303)
    else:
        try:
            context = resolve_request_auth_context(request)
        except HTTPException:
            context = None

    _require_shared_online_mode()
    response = HTMLResponse(
        build_dashboard_page_html(),
        headers={"Cache-Control": "no-store"},
    )
    if context and auth_required and parse_browser_session(request.cookies.get(SESSION_COOKIE_NAME)) is None:
        if context.auth_mode in ("api_token", "token+proxy_header"):
            _set_session_cookie(response, request, actor=context.actor)
    return response


@router.get("/dashboard/data", response_model=DashboardSnapshotResponse)
async def dashboard_data(request: Request):
    """Return the aggregated shared-console snapshot for browser clients."""
    resolve_request_auth_context(request)
    _require_shared_online_mode()
    return _build_dashboard_snapshot(request, network_limit=8)


@router.get("/admin", response_class=HTMLResponse)
async def admin_console(request: Request):
    """Serve the first Admin web-console shell."""
    auth_required = bool(configured_api_auth_token())
    context = None
    if auth_required:
        try:
            context = _require_admin_console_access(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse(url="/auth/login", status_code=303)
            raise
    else:
        try:
            context = resolve_request_auth_context(request)
        except HTTPException:
            context = None

    response = HTMLResponse(
        build_admin_console_html(),
        headers={"Cache-Control": "no-store"},
    )
    if context and auth_required and parse_browser_session(request.cookies.get(SESSION_COOKIE_NAME)) is None:
        if context.auth_mode in ("api_token", "token+proxy_header"):
            _set_session_cookie(response, request, actor=context.actor)
    return response


@router.get("/admin/data", response_model=AdminConsoleSnapshotResponse)
async def admin_console_data(request: Request):
    """Return the aggregated operator-facing snapshot for the Admin web console."""
    _require_admin_console_access(request)
    return _build_admin_console_snapshot(request, network_limit=20)


@router.post("/admin/index/stop", response_model=AdminIndexControlResponse)
async def admin_stop_indexing(request: Request):
    """Request cooperative stop for the active indexing job."""
    _require_admin_console_access(request)
    return _request_admin_index_stop()


@router.post("/admin/index/reindex-if-stale", response_model=AdminIndexControlResponse)
async def admin_reindex_if_stale(request: Request):
    """Start a maintenance reindex when freshness checks show drift."""
    _require_admin_console_access(request)
    return _request_admin_reindex_if_stale()


@router.post("/admin/freshness/recheck", response_model=AdminContentFreshnessResponse)
async def admin_recheck_freshness(request: Request):
    """Force an immediate freshness recheck without waiting for cache expiry."""
    _require_admin_console_access(request)
    return _refresh_admin_content_freshness_response()


@router.post("/admin/index-schedule/pause", response_model=AdminIndexScheduleControlResponse)
async def admin_pause_index_schedule(request: Request):
    """Pause the recurring indexing schedule without blocking manual indexing."""
    _require_admin_console_access(request)
    return _set_admin_index_schedule_enabled(False)


@router.post("/admin/index-schedule/resume", response_model=AdminIndexScheduleControlResponse)
async def admin_resume_index_schedule(request: Request):
    """Resume the recurring indexing schedule after an operator pause."""
    _require_admin_console_access(request)
    return _set_admin_index_schedule_enabled(True)


@router.get("/admin/traces/{trace_id}", response_model=AdminQueryTraceResponse)
async def admin_trace_detail(trace_id: str, request: Request):
    """Return one captured query trace for the Admin web console."""
    _require_admin_console_access(request)
    return _build_admin_query_trace_response_by_id(trace_id)
