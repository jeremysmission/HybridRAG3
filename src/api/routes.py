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
import time
import threading
import logging
import hmac
import yaml
from pathlib import Path
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from src.api.models import (
    QueryRequest,
    QueryResponse,
    StatusResponse,
    HealthResponse,
    IndexRequest,
    IndexStartResponse,
    IndexStatusResponse,
    ConfigResponse,
    ModeRequest,
    ModeResponse,
    ErrorResponse,
    StreamEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_RATE_LOCK = threading.Lock()
_RATE_STATE = {}


def _require_api_auth(request: Request) -> None:
    """Optional token auth: enforced only when HYBRIDRAG_API_AUTH_TOKEN is set."""
    expected = (os.environ.get("HYBRIDRAG_API_AUTH_TOKEN") or "").strip()
    if not expected:
        return

    auth_header = (request.headers.get("authorization") or "").strip()
    api_key_header = (request.headers.get("x-api-key") or "").strip()

    provided = ""
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
    elif api_key_header:
        provided = api_key_header

    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


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

    return StatusResponse(
        status="ok",
        mode=s.config.mode,
        chunk_count=stats.get("chunk_count", 0),
        source_count=stats.get("source_count", 0),
        database_path=s.config.paths.database,
        embedding_model=s.config.embedding.model_name,
        ollama_model=s.config.ollama.model,
    )


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
    s = _state()
    if not s.config:
        raise HTTPException(status_code=503, detail="Server not initialized")

    from src.core.retriever import RERANKER_AVAILABLE

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
        reranker_backend_available=bool(RERANKER_AVAILABLE),
    )


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
    _require_api_auth(request)
    _enforce_rate_limit(request, "query")

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
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(s.query_engine.query, req.question),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504, detail="Query timed out. Try a shorter question or check LLM status."
        )
    except Exception as e:
        logger.error("Query execution failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Query execution failed")

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
    _require_api_auth(request)
    _enforce_rate_limit(request, "query_stream")

    if not hasattr(s.query_engine, "query_stream"):
        raise HTTPException(status_code=501, detail="Streaming not supported")

    def _generate():
        try:
            for chunk in s.query_engine.query_stream(req.question):
                if "phase" in chunk:
                    yield "event: phase\ndata: {}\n\n".format(chunk["phase"])
                elif "token" in chunk:
                    yield "event: token\ndata: {}\n\n".format(
                        chunk["token"].replace("\n", "\ndata: ")
                    )
                elif chunk.get("done"):
                    result = chunk.get("result")
                    if result:
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
                        })
                        yield "event: done\ndata: {}\n\n".format(payload)
        except Exception as e:
            logger.error("Streaming query failed: %s", e, exc_info=True)
            yield "event: error\ndata: Internal server error\n\n"

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
    _require_api_auth(request)
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

    # Race-safe check: acquire lock BEFORE reading indexing_active.
    # Without the lock, two simultaneous requests could both see False
    # and both start indexing threads.
    with s.indexing_lock:
        if s.indexing_active:
            raise HTTPException(
                status_code=409,
                detail="Indexing is already in progress. Check GET /index/status.",
            )
        # Mark active inside the lock so no other request can slip through
        s.indexing_active = True
        s.indexing_stop_event.clear()

    def _run_indexing():
        from src.api.server import APIProgressCallback
        from src.core.chunker import Chunker
        from src.core.indexer import Indexer
        try:
            # indexing_active already set True under lock by the endpoint handler
            s.index_progress.update({
                "files_processed": 0,
                "files_total": 0,
                "files_skipped": 0,
                "files_errored": 0,
                "current_file": "",
                "start_time": time.time(),
            })

            chunker = Chunker(s.config.chunking)
            indexer = Indexer(s.config, s.vector_store, s.embedder, chunker)
            callback = APIProgressCallback()
            indexer.index_folder(
                source_folder,
                callback,
                stop_flag=s.indexing_stop_event,
            )
            # NOTE: Do NOT call indexer.close() here. The indexer holds
            # shared references to s.vector_store and s.embedder. Closing
            # them would destroy the server-wide instances and crash all
            # subsequent queries until restart.
        except Exception as e:
            logger.error("[FAIL] Indexing error: %s", e, exc_info=True)
        finally:
            s.indexing_active = False

    # Daemonized worker avoids process hang on shutdown if a parser/model call
    # is blocked despite cooperative stop signaling.
    thread = threading.Thread(target=_run_indexing, daemon=True)
    s.indexing_thread = thread
    thread.start()

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
    p = s.index_progress
    elapsed = time.time() - p["start_time"] if p["start_time"] else 0.0

    return IndexStatusResponse(
        indexing_active=s.indexing_active,
        files_processed=p["files_processed"],
        files_total=p["files_total"],
        files_skipped=p["files_skipped"],
        files_errored=p["files_errored"],
        current_file=p["current_file"],
        elapsed_seconds=round(elapsed, 1),
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
    _require_api_auth(request)
    _enforce_rate_limit(request, "mode")

    new_mode = req.mode

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
