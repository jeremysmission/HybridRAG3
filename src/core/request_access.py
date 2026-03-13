# === NON-PROGRAMMER GUIDE ===
# Purpose: Carries per-request shared access context into core retrieval code.
# What to read first: Start at set_request_access_context() and get_request_access_context().
# Inputs: Actor identity, role, and allowed document tags from the API layer.
# Outputs: A normalized request-scoped access context for retrievers and traces.
# Safety notes: Uses ContextVar so concurrent requests do not leak identity or policy into each other.
# ============================
# ============================================================================
# HybridRAG -- Request Access Context (src/core/request_access.py) RevA
# ============================================================================

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from .access_tags import normalize_access_tags


_REQUEST_ACCESS_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "hybridrag_request_access_context",
    default=None,
)


def set_request_access_context(context: dict[str, Any] | None) -> Token:
    """Store normalized request access metadata for the current execution context."""
    return _REQUEST_ACCESS_CONTEXT.set(_normalize_access_context(context))


def reset_request_access_context(token: Token) -> None:
    """Restore the prior request access metadata."""
    _REQUEST_ACCESS_CONTEXT.reset(token)


def get_request_access_context() -> dict[str, Any]:
    """Return the current normalized request access context, or an empty dict."""
    return dict(_REQUEST_ACCESS_CONTEXT.get() or {})


def _normalize_access_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    return {
        "actor": str(context.get("actor", "") or "").strip(),
        "actor_source": str(context.get("actor_source", "") or "").strip(),
        "actor_role": str(context.get("actor_role", "") or "").strip().lower(),
        "allowed_doc_tags": normalize_access_tags(context.get("allowed_doc_tags", ())),
        "document_policy_source": str(
            context.get("document_policy_source", "") or ""
        ).strip(),
    }
