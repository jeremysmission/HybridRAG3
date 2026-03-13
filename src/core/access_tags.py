# === NON-PROGRAMMER GUIDE ===
# Purpose: Classifies indexed documents into normalized access tags.
# What to read first: Start at resolve_document_access_tags() and then the small parsing helpers below it.
# Inputs: Source file paths plus environment tag rules.
# Outputs: Normalized document access tags and the source of that classification.
# Safety notes: Defaults stay conservative and deterministic when no explicit rule matches.
# ============================
# ============================================================================
# HybridRAG -- Document Access Tags (src/core/access_tags.py) RevA
# ============================================================================

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass


_DEFAULT_DOCUMENT_TAGS = ("shared",)


@dataclass(frozen=True)
class ResolvedDocumentTags:
    """Resolved document tags for one indexed source file."""

    access_tags: tuple[str, ...]
    access_tag_source: str
    matched_rules: tuple[str, ...]


def resolve_document_access_tags(source_path: str) -> ResolvedDocumentTags:
    """Classify one source file into normalized access tags."""
    default_tags = default_document_tags()
    normalized_path = _normalize_path(source_path)
    matched_rules: list[str] = []
    combined_tags = list(default_tags)

    for pattern, rule_tags in document_tag_rules():
        if _path_matches(normalized_path, pattern):
            matched_rules.append(pattern)
            combined_tags.extend(rule_tags)

    if matched_rules:
        return ResolvedDocumentTags(
            access_tags=normalize_access_tags(combined_tags) or default_tags,
            access_tag_source="document_tag_rules:" + "|".join(matched_rules),
            matched_rules=tuple(matched_rules),
        )

    return ResolvedDocumentTags(
        access_tags=default_tags,
        access_tag_source="default_document_tags",
        matched_rules=(),
    )


def default_document_tags() -> tuple[str, ...]:
    """Return the default access tags for documents without an explicit rule."""
    raw = (os.environ.get("HYBRIDRAG_DEFAULT_DOCUMENT_TAGS") or "").strip()
    return normalize_access_tags(raw) or _DEFAULT_DOCUMENT_TAGS


def document_tag_rules() -> list[tuple[str, tuple[str, ...]]]:
    """Return configured path-pattern rules and their normalized access tags."""
    raw = (os.environ.get("HYBRIDRAG_DOCUMENT_TAG_RULES") or "").strip()
    if not raw:
        return []
    rules: list[tuple[str, tuple[str, ...]]] = []
    for entry in _split_entries(raw):
        pattern, tags_raw = _split_assignment(entry)
        normalized_pattern = _normalize_path(pattern)
        normalized_tags = normalize_access_tags(tags_raw)
        if normalized_pattern and normalized_tags:
            rules.append((normalized_pattern, normalized_tags))
    return rules


def normalize_access_tags(raw_value) -> tuple[str, ...]:
    """Normalize tag input from strings or iterables into a unique tuple."""
    if raw_value is None:
        return ()
    if isinstance(raw_value, str):
        tokens = re.split(r"[\s,]+", raw_value.strip())
    else:
        tokens = []
        for item in raw_value:
            tokens.extend(re.split(r"[\s,]+", str(item or "").strip()))

    deduped: list[str] = []
    for token in tokens:
        raw_token = str(token or "").strip().lower()
        if raw_token == "*":
            return ("*",)
        cleaned = re.sub(r"[^a-z0-9_.:-]+", "-", raw_token).strip("-")
        if not cleaned:
            continue
        if cleaned not in deduped:
            deduped.append(cleaned)
    return tuple(deduped)


def serialize_access_tags(tags) -> str:
    """Serialize normalized tags for storage in SQLite text columns."""
    normalized = normalize_access_tags(tags) or default_document_tags()
    return ",".join(normalized)


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


def _normalize_path(value: str | None) -> str:
    return str(value or "").strip().replace("\\", "/").lower()


def _path_matches(normalized_path: str, normalized_pattern: str) -> bool:
    if not normalized_path or not normalized_pattern:
        return False
    basename = normalized_path.rsplit("/", 1)[-1]
    return (
        fnmatch.fnmatch(normalized_path, normalized_pattern)
        or fnmatch.fnmatch(basename, normalized_pattern)
    )
