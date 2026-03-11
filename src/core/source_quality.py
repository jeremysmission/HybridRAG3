from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


_ENCODED_BLOB_RE = re.compile(r"[A-Za-z0-9+/=_-]{120,}")
_NAV_SIGNALS = (
    "theme auto light dark",
    "table of contents",
    "previous topic",
    "next topic",
    "report a bug",
    "show source",
    "navigation",
)
_SERVE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".md",
    ".pdf",
    ".rst",
    ".rst.txt",
    ".txt",
}
_HTML_EXTENSIONS = {
    ".htm",
    ".html",
}


def ensure_source_quality_schema(conn) -> None:
    """Create additive source-quality metadata tables if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_quality (
            source_path         TEXT PRIMARY KEY,
            source_type         TEXT NOT NULL DEFAULT '',
            retrieval_tier      TEXT NOT NULL DEFAULT 'serve',
            quality_score       REAL NOT NULL DEFAULT 0.0,
            is_html_capture     INTEGER NOT NULL DEFAULT 0,
            is_saved_resource   INTEGER NOT NULL DEFAULT 0,
            is_boilerplate      INTEGER NOT NULL DEFAULT 0,
            has_missing_path    INTEGER NOT NULL DEFAULT 0,
            has_encoded_blob    INTEGER NOT NULL DEFAULT 0,
            flags_json          TEXT NOT NULL DEFAULT '[]',
            updated_at          TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_quality_tier "
        "ON source_quality(retrieval_tier);"
    )
    conn.commit()


def assess_source_quality(source_path: str, sample_text: str = "") -> dict:
    """Score a source for answer-serving retrieval without deleting raw data."""
    path_text = str(source_path or "").strip()
    sample = str(sample_text or "")
    low_path = path_text.lower()
    low_sample = sample.lower()
    flags: list[str] = []

    source_type = _detect_source_type(path_text)
    quality_score = _baseline_quality(source_type)
    has_missing_path = not path_text
    is_html_capture = source_type in {"html", "htm"}
    is_saved_resource = (
        low_path.endswith("saved_resource.html")
        or "\\_files\\" in low_path
        or "/_files/" in low_path
    )
    has_encoded_blob = bool(_ENCODED_BLOB_RE.search(sample))
    is_boilerplate = _has_navigation_boilerplate(low_sample)

    if has_missing_path:
        flags.append("missing_source_path")
        quality_score -= 0.75
    if is_html_capture:
        flags.append("html_capture")
        quality_score -= 0.05
    if is_saved_resource:
        flags.append("saved_resource_capture")
        quality_score -= 0.60
    if "[archive_member=" in low_sample:
        flags.append("archive_wrapper_text")
        quality_score -= 0.08
    if has_encoded_blob:
        flags.append("encoded_blob")
        quality_score -= 0.45
    if is_boilerplate:
        flags.append("navigation_boilerplate")
        quality_score -= 0.18
    if len(sample.strip()) < 80:
        flags.append("low_text_signal")
        quality_score -= 0.08

    quality_score = max(0.0, min(1.0, quality_score))
    retrieval_tier = _resolve_retrieval_tier(
        quality_score=quality_score,
        has_missing_path=has_missing_path,
        is_saved_resource=is_saved_resource,
        has_encoded_blob=has_encoded_blob,
    )

    return {
        "source_path": path_text,
        "source_type": source_type,
        "retrieval_tier": retrieval_tier,
        "quality_score": float(quality_score),
        "is_html_capture": int(is_html_capture),
        "is_saved_resource": int(is_saved_resource),
        "is_boilerplate": int(is_boilerplate),
        "has_missing_path": int(has_missing_path),
        "has_encoded_blob": int(has_encoded_blob),
        "flags_json": json.dumps(flags, sort_keys=True),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_source_quality_map(conn, source_paths: Iterable[str]) -> dict[str, dict]:
    """Return existing quality metadata keyed by source_path."""
    cleaned = [str(path or "").strip() for path in source_paths]
    if not cleaned:
        return {}
    placeholders = ",".join("?" for _ in cleaned)
    rows = conn.execute(
        f"""
        SELECT source_path, source_type, retrieval_tier, quality_score,
               is_html_capture, is_saved_resource, is_boilerplate,
               has_missing_path, has_encoded_blob, flags_json, updated_at
        FROM source_quality
        WHERE source_path IN ({placeholders})
        """,
        cleaned,
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        result[str(row[0] or "")] = {
            "source_path": str(row[0] or ""),
            "source_type": str(row[1] or ""),
            "retrieval_tier": str(row[2] or "serve"),
            "quality_score": float(row[3] or 0.0),
            "is_html_capture": int(row[4] or 0),
            "is_saved_resource": int(row[5] or 0),
            "is_boilerplate": int(row[6] or 0),
            "has_missing_path": int(row[7] or 0),
            "has_encoded_blob": int(row[8] or 0),
            "flags_json": str(row[9] or "[]"),
            "updated_at": str(row[10] or ""),
        }
    return result


def upsert_source_quality_records(conn, records: Iterable[dict]) -> None:
    """Insert or replace source-quality rows."""
    rows = []
    for record in records:
        rows.append(
            (
                str(record.get("source_path", "") or ""),
                str(record.get("source_type", "") or ""),
                str(record.get("retrieval_tier", "serve") or "serve"),
                float(record.get("quality_score", 0.0) or 0.0),
                int(record.get("is_html_capture", 0) or 0),
                int(record.get("is_saved_resource", 0) or 0),
                int(record.get("is_boilerplate", 0) or 0),
                int(record.get("has_missing_path", 0) or 0),
                int(record.get("has_encoded_blob", 0) or 0),
                str(record.get("flags_json", "[]") or "[]"),
                str(record.get("updated_at", "") or ""),
            )
        )
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO source_quality (
            source_path, source_type, retrieval_tier, quality_score,
            is_html_capture, is_saved_resource, is_boilerplate,
            has_missing_path, has_encoded_blob, flags_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def ensure_source_quality_map(
    conn,
    source_samples: Mapping[str, str],
) -> dict[str, dict]:
    """Fetch quality rows and backfill missing ones from source samples."""
    existing = fetch_source_quality_map(conn, source_samples.keys())
    missing_records = []
    for source_path, sample_text in source_samples.items():
        cleaned = str(source_path or "").strip()
        if cleaned not in existing:
            record = assess_source_quality(cleaned, sample_text)
            existing[cleaned] = record
            missing_records.append(record)
    if missing_records:
        upsert_source_quality_records(conn, missing_records)
    return existing


def _detect_source_type(source_path: str) -> str:
    if not source_path:
        return "unknown"
    low_path = source_path.lower()
    if low_path.endswith(".rst.txt"):
        return "rst_txt"
    suffix = Path(source_path).suffix.lower().lstrip(".")
    return suffix or "unknown"


def _baseline_quality(source_type: str) -> float:
    if source_type in {"doc", "docx", "md", "pdf", "rst", "rst_txt", "txt"}:
        return 0.92
    if source_type in {"html", "htm"}:
        return 0.62
    if source_type == "unknown":
        return 0.40
    return 0.78


def _has_navigation_boilerplate(low_sample: str) -> bool:
    matches = sum(1 for signal in _NAV_SIGNALS if signal in low_sample)
    return matches >= 2


def _resolve_retrieval_tier(
    *,
    quality_score: float,
    has_missing_path: bool,
    is_saved_resource: bool,
    has_encoded_blob: bool,
) -> str:
    if has_missing_path or is_saved_resource or has_encoded_blob:
        return "suspect"
    if quality_score >= 0.75:
        return "serve"
    return "archive"
