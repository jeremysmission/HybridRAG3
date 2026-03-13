# === NON-PROGRAMMER GUIDE ===
# Purpose: Resolves shared-deployment actor roles and document-tag policy for API requests.
# What to read first: Start at resolve_role_policy() and then read the small parsing helpers below it.
# Inputs: Actor identity strings plus environment policy settings.
# Outputs: A normalized role plus the allowed document tags for that role.
# Safety notes: Keep parsing deterministic and fail closed to conservative defaults.
# ============================
# ============================================================================
# HybridRAG -- Shared Access Policy Resolver (src/api/access_policy.py) RevA
# ============================================================================

from __future__ import annotations

import os
import re
from dataclasses import dataclass


_DEFAULT_ROLE = "viewer"


@dataclass(frozen=True)
class ResolvedRolePolicy:
    """Resolved actor role plus document-tag access scope."""

    actor_role: str
    actor_role_source: str
    allowed_doc_tags: tuple[str, ...]
    document_policy_source: str


def resolve_role_policy(actor: str, actor_source: str) -> ResolvedRolePolicy:
    """Resolve the effective shared-deployment role and document-tag scope."""
    _ = actor_source  # Reserved for future source-aware policy fallbacks.
    normalized_actor = _normalize_identity(actor)
    role = _role_map().get(normalized_actor, "")
    if role:
        role_source = f"role_map:{normalized_actor}"
    else:
        role = default_role()
        role_source = "default_role"
    allowed_doc_tags, document_policy_source = _allowed_doc_tags_for_role(role)
    return ResolvedRolePolicy(
        actor_role=role,
        actor_role_source=role_source,
        allowed_doc_tags=allowed_doc_tags,
        document_policy_source=document_policy_source,
    )


def default_role() -> str:
    """Return the fallback role when no actor-specific mapping is configured."""
    return _normalize_role(os.environ.get("HYBRIDRAG_DEFAULT_ROLE")) or _DEFAULT_ROLE


def configured_role_map() -> dict[str, str]:
    """Return the normalized actor-to-role policy map."""
    return dict(_role_map())


def configured_role_tag_policies() -> dict[str, tuple[str, ...]]:
    """Return the normalized role-to-document-tag policy map."""
    return dict(_role_tags_map())


def _role_map() -> dict[str, str]:
    raw = (os.environ.get("HYBRIDRAG_ROLE_MAP") or "").strip()
    if not raw:
        return {}
    mapping: dict[str, str] = {}
    for entry in _split_entries(raw):
        key, value = _split_assignment(entry)
        normalized_key = _normalize_identity(key)
        normalized_role = _normalize_role(value)
        if normalized_key and normalized_role:
            mapping[normalized_key] = normalized_role
    return mapping


def _role_tags_map() -> dict[str, tuple[str, ...]]:
    raw = (os.environ.get("HYBRIDRAG_ROLE_TAGS") or "").strip()
    if not raw:
        return {}
    mapping: dict[str, tuple[str, ...]] = {}
    for entry in _split_entries(raw):
        key, value = _split_assignment(entry)
        normalized_role = _normalize_role(key)
        tags = _normalize_tags(value)
        if normalized_role and tags:
            mapping[normalized_role] = tags
    return mapping


def _allowed_doc_tags_for_role(role: str) -> tuple[tuple[str, ...], str]:
    configured = _role_tags_map().get(role)
    if configured:
        return configured, f"role_tags:{role}"
    if role == "admin":
        return ("*",), "default_policy:admin"
    if role in {"viewer", "guest", "anonymous"}:
        return ("shared",), "default_policy:shared"
    return ("shared", role), "default_policy:shared+role"


def _split_entries(raw: str) -> list[str]:
    return [
        entry.strip()
        for entry in re.split(r"[;\r\n]+", raw)
        if entry.strip()
    ]


def _split_assignment(entry: str) -> tuple[str, str]:
    if "=" in entry:
        key, value = entry.split("=", 1)
        return key.strip(), value.strip()
    if ":" in entry:
        key, value = entry.split(":", 1)
        return key.strip(), value.strip()
    return entry.strip(), ""


def _normalize_identity(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_role(value: str | None) -> str:
    role = str(value or "").strip().lower()
    role = re.sub(r"[^a-z0-9_.:-]+", "-", role)
    return role.strip("-")


def _normalize_tags(raw_value: str | None) -> tuple[str, ...]:
    tokens = [
        token.strip().lower()
        for token in re.split(r"[\s,]+", str(raw_value or "").strip())
        if token.strip()
    ]
    if not tokens:
        return ()
    if "*" in tokens:
        return ("*",)
    deduped: list[str] = []
    for token in tokens:
        cleaned = re.sub(r"[^a-z0-9_.:-]+", "-", token).strip("-")
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return tuple(deduped)
