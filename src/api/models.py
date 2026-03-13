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
    thread_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description="Optional persistent conversation thread ID for saved history.",
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
    thread_id: Optional[str] = None
    turn_index: Optional[int] = None


class QueryActivityEntry(BaseModel):
    """One active or recently completed API query."""
    query_id: str
    question_text: str
    question_preview: str
    mode: str
    transport: str
    client_host: str
    actor: str
    actor_source: str
    actor_role: str
    allowed_doc_tags: List[str]
    document_policy_source: str
    thread_id: Optional[str] = None
    turn_index: Optional[int] = None
    status: str
    started_at: str
    completed_at: Optional[str] = None
    latency_ms: Optional[float] = None
    chunks_used: int
    source_count: int
    answer_preview: Optional[str] = None
    source_paths: List[str]
    denied_hits: int
    error: Optional[str] = None


class QueryActivitySummary(BaseModel):
    """Compact query-activity counters for deployment status surfaces."""
    active_queries: int
    recent_queries: int
    total_completed: int
    total_failed: int
    last_completed_at: Optional[str] = None
    last_error_at: Optional[str] = None


class QueryActivityResponse(BaseModel):
    """Detailed active/recent API query activity."""
    active_queries: int
    total_completed: int
    total_failed: int
    active: List[QueryActivityEntry]
    recent: List[QueryActivityEntry]


class BrowserLoginRequest(BaseModel):
    """POST /auth/login request body."""
    token: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Shared deployment token used to mint a browser session.",
    )


class BrowserAuthResponse(BaseModel):
    """Browser auth/login/logout response."""
    ok: bool
    redirect_to: str
    actor: Optional[str] = None


class QueryQueueSummary(BaseModel):
    """Shared deployment query queue and concurrency snapshot."""
    enabled: bool
    max_concurrent: int
    max_queue: int
    active_queries: int
    waiting_queries: int
    available_slots: Optional[int] = None
    saturated: bool
    max_waiting_seen: int
    total_started: int
    total_completed: int
    total_rejected: int
    last_started_at: Optional[str] = None
    last_completed_at: Optional[str] = None
    last_rejected_at: Optional[str] = None


class AuthContextResponse(BaseModel):
    """Resolved request auth and actor context for shared deployments."""
    auth_required: bool
    auth_mode: str
    actor: str
    actor_source: str
    actor_role: str
    actor_role_source: str
    allowed_doc_tags: List[str]
    document_policy_source: str
    client_host: str
    session_cookie_active: bool
    session_issued_at: Optional[str] = None
    session_expires_at: Optional[str] = None
    session_ttl_seconds: Optional[int] = None
    session_seconds_remaining: Optional[int] = None
    proxy_identity_trusted: bool
    trusted_proxy_identity_headers: List[str]


class NetworkAuditEntryResponse(BaseModel):
    """One recent network-gate audit record."""
    timestamp: float
    timestamp_iso: str
    url: str
    host: str
    purpose: str
    mode: str
    allowed: bool
    reason: str
    caller: str


class NetworkAuditSummary(BaseModel):
    """Deployment-facing summary of recent network-gate activity."""
    mode: str
    total_checks: int
    allowed: int
    denied: int
    allowed_hosts: List[str]
    unique_hosts_contacted: List[str]


class NetworkActivityResponse(BaseModel):
    """Detailed recent network-gate activity for shared deployment dashboards."""
    mode: str
    total_checks: int
    allowed: int
    denied: int
    allowed_hosts: List[str]
    unique_hosts_contacted: List[str]
    entries: List[NetworkAuditEntryResponse]


class IndexingSnapshot(BaseModel):
    """Live in-memory indexing status for shared deployment surfaces."""
    active: bool
    files_processed: int
    files_total: int
    files_skipped: int
    files_errored: int
    current_file: str
    elapsed_seconds: float
    progress_pct: float


class LatestIndexRunSummary(BaseModel):
    """Most recent persisted indexing run metadata, if available."""
    run_id: str
    status: str
    started_at: str
    finished_at: Optional[str] = None
    host: str
    user: str
    profile: str


class IndexScheduleSnapshotResponse(BaseModel):
    """Recurring indexing scheduler snapshot for shared status surfaces."""
    enabled: bool
    interval_seconds: int
    source_folder: str
    indexing_active: bool
    due_now: bool
    next_run_at: Optional[str] = None
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_status: str
    last_error: str = ""
    last_trigger: str = ""
    total_runs: int
    total_success: int
    total_failed: int


class StatusResponse(BaseModel):
    """GET /status response."""
    status: str
    mode: str
    chunk_count: int
    source_count: int
    database_path: str
    embedding_model: str
    ollama_model: str
    deployment_mode: str
    current_user: str
    api_auth_required: bool
    indexing_active: bool
    indexing: IndexingSnapshot
    query_activity: QueryActivitySummary
    query_queue: QueryQueueSummary
    network_audit: NetworkAuditSummary
    latest_index_run: Optional[LatestIndexRunSummary] = None
    index_schedule: IndexScheduleSnapshotResponse


class DashboardSnapshotResponse(BaseModel):
    """Aggregated shared-console snapshot for browser dashboards."""
    status: StatusResponse
    auth: AuthContextResponse
    queries: QueryActivityResponse
    network: NetworkActivityResponse


class ConversationThreadSummaryResponse(BaseModel):
    """One persisted conversation-thread summary."""
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    created_by_actor: str
    created_by_source: str
    created_by_role: str
    last_actor: str
    last_actor_source: str
    last_actor_role: str
    turn_count: int
    last_question_preview: str
    last_answer_preview: Optional[str] = None
    last_mode: str
    last_status: str


class ConversationTurnResponse(BaseModel):
    """One persisted conversation turn inside a thread."""
    thread_id: str
    turn_index: int
    created_at: str
    completed_at: Optional[str] = None
    question_text: str
    question_preview: str
    answer_text: Optional[str] = None
    answer_preview: Optional[str] = None
    mode: str
    transport: str
    actor: str
    actor_source: str
    actor_role: str
    allowed_doc_tags: List[str]
    document_policy_source: str
    status: str
    latency_ms: Optional[float] = None
    chunks_used: int
    source_count: int
    source_paths: List[str]
    sources: List[Dict[str, Any]]
    denied_hits: int
    error: Optional[str] = None


class ConversationThreadListResponse(BaseModel):
    """Listing payload for persisted conversation history."""
    total_threads: int
    max_threads: int
    max_turns_per_thread: int
    threads: List[ConversationThreadSummaryResponse]


class ConversationThreadResponse(BaseModel):
    """Detailed persisted conversation thread with all stored turns."""
    thread: ConversationThreadSummaryResponse
    turns: List[ConversationTurnResponse]


class AdminQueryTraceResponse(BaseModel):
    """Latest retrieval/query trace snapshot for the Admin web console."""
    available: bool
    trace_id: str = ""
    captured_at: Optional[str] = None
    query: str = ""
    decision_path: str = ""
    mode: str = ""
    active_profile: str = ""
    stream: bool = False
    final_hit_count: int = 0
    formatted_text: str = ""
    payload: Optional[Dict[str, Any]] = None


class AdminQueryTraceSummaryResponse(BaseModel):
    """Compact Admin-console listing entry for a captured query trace."""
    trace_id: str
    captured_at: Optional[str] = None
    query: str = ""
    decision_path: str = ""
    mode: str = ""
    active_profile: str = ""
    stream: bool = False
    final_hit_count: int = 0


class AdminRuntimeSafetyResponse(BaseModel):
    """Operator-facing runtime safety and profile boundary summary."""
    deployment_mode: str
    shared_online_enforced: bool
    shared_online_ready: bool
    active_profile: str
    grounding_bias: int
    allow_open_knowledge: bool
    api_auth_required: bool
    api_auth_source: str
    api_auth_label: str
    browser_sessions_enabled: bool
    browser_session_secret_source: str
    browser_session_rotation_enabled: bool
    browser_session_ttl_seconds: int
    browser_session_invalid_before: Optional[str] = None
    browser_session_secure_cookie: bool
    trusted_proxy_identity_enabled: bool
    proxy_identity_secret_rotation_enabled: bool
    history_encryption_enabled: bool
    history_encryption_source: str
    history_encryption_rotation_enabled: bool
    history_secure_delete_enabled: bool
    history_database_path: str
    trusted_proxy_hosts: List[str]
    trusted_proxy_user_headers: List[str]
    source_folder: str
    database_path: str


class AdminAccessPolicyReviewResponse(BaseModel):
    """Operator-facing summary of the active document access policy."""
    default_document_tags: List[str]
    role_map: List[str]
    role_tag_policies: List[str]
    document_tag_rules: List[str]
    recent_denied_traces: int
    latest_denied_trace_id: Optional[str] = None
    latest_denied_query: str = ""


class AdminAppLogEntryResponse(BaseModel):
    """One recent structured app-log event for the Admin console."""
    timestamp: str
    event: str
    summary: str
    log_file: str


class AdminIndexReportEntryResponse(BaseModel):
    """One recent index-report artifact for the Admin console."""
    file_name: str
    modified_at: str
    size_bytes: int


class AdminOperatorLogSnapshotResponse(BaseModel):
    """Compact operator log snapshot for the Admin console."""
    app_log_file: str = ""
    app_log_entries: List[AdminAppLogEntryResponse]
    index_reports: List[AdminIndexReportEntryResponse]


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
    reranker_backend_available: bool = False


class AdminIndexScheduleResponse(IndexScheduleSnapshotResponse):
    """Operator-facing scheduled-index runner snapshot."""


class AdminIndexScheduleControlResponse(BaseModel):
    """Admin action response for pausing or resuming the recurring schedule."""
    ok: bool
    enabled: bool
    last_status: str
    next_run_at: Optional[str] = None
    message: str


class AdminContentFreshnessResponse(BaseModel):
    """Operator-facing content freshness and source drift snapshot."""
    source_folder: str
    source_exists: bool
    total_indexable_files: int
    latest_source_update_at: Optional[str] = None
    latest_source_path: str = ""
    last_index_started_at: Optional[str] = None
    last_index_finished_at: Optional[str] = None
    last_index_status: str = ""
    files_newer_than_index: int
    freshness_age_hours: Optional[float] = None
    warn_after_hours: int
    stale: bool
    summary: str


class AdminStorageProtectionResponse(BaseModel):
    """Operator-facing protected-storage posture for persisted data paths."""
    mode: str
    required: bool
    roots: List[str]
    tracked_paths: List[str]
    protected_paths: List[str]
    unprotected_paths: List[str]
    all_paths_protected: bool
    summary: str


class AdminAlertEntryResponse(BaseModel):
    """One operator-facing alert item for the Admin console."""
    severity: str
    code: str
    message: str
    action: str = ""


class AdminAlertSummaryResponse(BaseModel):
    """Compact operator alert summary for the Admin console."""
    total: int
    error_count: int
    warning_count: int
    items: List[AdminAlertEntryResponse]


class AdminSecurityActivityEntryResponse(BaseModel):
    """One recent auth/access-control security event for the Admin console."""
    timestamp_iso: str
    event: str
    outcome: str
    client_host: str
    path: str
    actor: str = ""
    detail: str = ""


class AdminSecurityActivityResponse(BaseModel):
    """Compact security activity snapshot for the Admin console."""
    window_seconds: int
    recent_total: int
    recent_failures: int
    recent_rate_limited: int
    recent_proxy_rejections: int
    latest_event_at: Optional[str] = None
    unique_hosts: List[str]
    entries: List[AdminSecurityActivityEntryResponse]


class AdminConsoleSnapshotResponse(BaseModel):
    """Aggregated operator-facing snapshot for the Admin web console."""
    dashboard: DashboardSnapshotResponse
    config: ConfigResponse
    runtime_safety: AdminRuntimeSafetyResponse
    access_policy: AdminAccessPolicyReviewResponse
    index_schedule: AdminIndexScheduleResponse
    freshness: AdminContentFreshnessResponse
    storage_protection: AdminStorageProtectionResponse
    alerts: AdminAlertSummaryResponse
    security_activity: AdminSecurityActivityResponse
    operator_logs: AdminOperatorLogSnapshotResponse
    latest_query_trace: AdminQueryTraceResponse
    recent_query_traces: List[AdminQueryTraceSummaryResponse]


class AdminIndexControlResponse(BaseModel):
    """Admin-console indexing action response."""
    ok: bool
    message: str
    indexing_active: bool
    stop_requested: bool


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
