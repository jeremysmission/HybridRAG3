# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the models part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- API Pydantic Models (src/api/models.py)
# ============================================================================
# WHAT: Request/response schemas for every FastAPI endpoint.
# WHY:  Pydantic models enforce data validation at the API boundary.
#       Invalid requests get clear error messages before any pipeline
#       code runs.  Response models ensure the client always gets a
#       consistent JSON shape, even on errors.
# HOW:  Each endpoint has a paired Request and Response model.  FastAPI
#       auto-generates OpenAPI docs from these (visible at /docs).
# USAGE: Imported by routes.py.  Not used directly by end users.
#
# INTERNET ACCESS: NONE
# ============================================================================

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------

class QueryRequest(BaseModel):
    """POST /query request body."""
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask about your documents.",
    )


class IndexRequest(BaseModel):
    """POST /index request body (optional override)."""
    source_folder: Optional[str] = Field(
        None,
        description="Override source folder path. Uses config default if omitted.",
    )


# -------------------------------------------------------------------
# Response models
# -------------------------------------------------------------------

class QueryResponse(BaseModel):
    """POST /query response."""
    answer: str
    sources: List[Dict[str, Any]]
    chunks_used: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    mode: str
    error: Optional[str] = None


class StatusResponse(BaseModel):
    """GET /status response."""
    status: str
    mode: str
    chunk_count: int
    source_count: int
    database_path: str
    embedding_model: str
    ollama_model: str


class HealthResponse(BaseModel):
    """GET /health response."""
    status: str
    version: str


class IndexStatusResponse(BaseModel):
    """GET /index/status response."""
    indexing_active: bool
    files_processed: int
    files_total: int
    files_skipped: int
    files_errored: int
    current_file: str
    elapsed_seconds: float


class IndexStartResponse(BaseModel):
    """POST /index response."""
    message: str
    source_folder: str


class ConfigResponse(BaseModel):
    """GET /config response."""
    mode: str
    embedding_model: str
    embedding_dimension: int
    embedding_batch_size: int
    chunk_size: int
    chunk_overlap: int
    ollama_model: str
    ollama_base_url: str
    api_model: str
    api_endpoint_configured: bool
    top_k: int
    min_score: float
    hybrid_search: bool
    reranker_enabled: bool


class ModeRequest(BaseModel):
    """PUT /mode request body."""
    mode: str = Field(
        ...,
        pattern="^(offline|online)$",
        description="'offline' for Ollama or 'online' for API.",
    )


class ModeResponse(BaseModel):
    """PUT /mode response."""
    mode: str
    message: str


class StreamEvent(BaseModel):
    """One SSE event from POST /query/stream."""
    event: str = Field(
        ...,
        description="Event type: 'phase', 'token', 'done', or 'error'.",
    )
    data: str = Field(
        "",
        description="Event payload (token text, phase name, or JSON metadata).",
    )


class ErrorResponse(BaseModel):
    """Generic error response."""
    error: str
    detail: Optional[str] = None
