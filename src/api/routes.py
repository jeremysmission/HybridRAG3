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
import yaml
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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
        raise HTTPException(
            status_code=500, detail=f"Failed to get stats: {e}"
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

    c = s.config
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
        reranker_enabled=c.retrieval.reranker_enabled,
    )


# -------------------------------------------------------------------
# POST /query
# -------------------------------------------------------------------
@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """
    Ask a question about your indexed documents.

    Returns the AI-generated answer with source citations,
    chunk count, token usage, cost, and latency.
    """
    import asyncio

    s = _state()
    if not s.query_engine:
        raise HTTPException(status_code=503, detail="Query engine not initialized")

    result = await asyncio.to_thread(s.query_engine.query, req.question)

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
async def query_stream(req: QueryRequest):
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
            yield "event: error\ndata: {}\n\n".format(str(e))

    return StreamingResponse(
        _generate(),
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
async def start_indexing(req: IndexRequest = None):
    """
    Start document indexing in a background thread.

    If indexing is already running, returns 409 Conflict.
    Check progress with GET /index/status.
    """
    s = _state()
    if not s.config or not s.vector_store or not s.embedder:
        raise HTTPException(status_code=503, detail="Server not initialized")

    if s.indexing_active:
        raise HTTPException(
            status_code=409,
            detail="Indexing is already in progress. Check GET /index/status.",
        )

    source_folder = (
        req.source_folder if req and req.source_folder
        else s.config.paths.source_folder
    )

    if not source_folder or not os.path.isdir(source_folder):
        raise HTTPException(
            status_code=400,
            detail=f"Source folder not found: {source_folder}",
        )

    # Path traversal prevention: the requested folder must be within
    # the configured source directory.  This blocks "../../../etc/passwd"
    # style attacks via the source_folder parameter.
    allowed_root = os.path.realpath(s.config.paths.source_folder)
    requested = os.path.realpath(source_folder)
    if not requested.startswith(allowed_root):
        raise HTTPException(
            status_code=403,
            detail="Source folder must be within the configured source directory.",
        )

    def _run_indexing():
        from src.api.server import APIProgressCallback
        from src.core.chunker import Chunker
        from src.core.indexer import Indexer
        try:
            with s.indexing_lock:
                if s.indexing_active:
                    return
                s.indexing_active = True
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
            indexer.index_folder(source_folder, callback)
            indexer.close()
        except Exception as e:
            logger.error("[FAIL] Indexing error: %s", e)
        finally:
            s.indexing_active = False

    thread = threading.Thread(target=_run_indexing, daemon=True)
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
async def set_mode(req: ModeRequest):
    """
    Switch between offline (Ollama) and online (API) mode.

    Changes take effect immediately. The YAML config file is
    also updated so the change persists across restarts.
    """
    s = _state()
    if not s.config:
        raise HTTPException(status_code=503, detail="Server not initialized")

    new_mode = req.mode

    # Validate online mode requirements
    if new_mode == "online" and not s.config.api.endpoint:
        raise HTTPException(
            status_code=400,
            detail="Cannot switch to online mode: API endpoint not configured. "
                   "Use rag-store-endpoint to set it first.",
        )

    # Update in-memory config
    s.config.mode = new_mode

    # Rebuild LLM router with new mode
    from src.core.llm_router import LLMRouter
    s.llm_router = LLMRouter(s.config)
    s.query_engine.llm_router = s.llm_router

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
    """Write mode change to config/default_config.yaml."""
    _project_root = Path(__file__).resolve().parent.parent.parent
    config_path = _project_root / "config" / "default_config.yaml"
    if not config_path.exists():
        return

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data["mode"] = new_mode

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
