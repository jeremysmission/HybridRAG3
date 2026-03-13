from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from src.core.config import load_config
from src.core.index_qc import inspect_index_database
from src.tools.demo_rehearsal_pack import default_demo_validation_report_dir


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")
_CONNECTOR_PATTERN = re.compile(r"\s+(?:or|plus|and)\s+", flags=re.IGNORECASE)
_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "plus",
    "to",
    "of",
    "for",
    "with",
    "in",
    "on",
    "by",
    "at",
    "from",
    "section",
    "table",
    "covering",
    "tied",
}


def resolve_demo_rehearsal_db_path(
    *,
    project_root: str | Path = ".",
    database_path: str | Path | None = None,
) -> Path:
    if database_path:
        return Path(database_path).expanduser().resolve()

    config = load_config(str(project_root))
    db_path = str(getattr(config.paths, "database", "") or "").strip()
    if not db_path:
        raise ValueError(
            "No database path configured. Set paths.database or pass --db."
        )
    return Path(db_path).expanduser().resolve()


def audit_demo_rehearsal_pack(
    pack: dict[str, Any],
    *,
    db_path: str | Path,
) -> dict[str, Any]:
    db_file = Path(db_path).expanduser().resolve()
    stats = inspect_index_database(db_file)
    if not stats.get("ok"):
        return {
            "ok": False,
            "timestamp": datetime.now().isoformat(),
            "pack": {
                "path": pack.get("_path", ""),
                "pack_id": pack.get("pack_id", ""),
                "title": pack.get("title", ""),
            },
            "index": {
                "db_path": str(db_file),
                "ok": False,
                "summary": stats.get("reason", "could not inspect database"),
                "chunk_count": 0,
                "source_count": 0,
            },
            "summary": {
                "questions": len(pack.get("questions", [])),
                "checks": 0,
                "passed": 0,
                "failed": 1,
            },
            "questions": [],
        }

    sources_by_basename = _index_sources_by_basename(stats.get("sources", []))
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        questions: list[dict[str, Any]] = []
        total_checks = 0
        passed_checks = 0
        failed_checks = 0

        for question in pack.get("questions", []):
            preferred_paths = {
                str(item.get("target", "")).strip().lower()
                for item in question.get("expected_evidence", [])
                if str(item.get("kind", "")).strip() == "path"
            }
            checks: list[dict[str, Any]] = []
            for item in question.get("expected_evidence", []):
                total_checks += 1
                kind = str(item.get("kind", "")).strip()
                if kind == "path":
                    result = _audit_path_target(item, sources_by_basename)
                elif kind == "citation_target":
                    result = _audit_citation_target(
                        conn,
                        item,
                        preferred_paths=preferred_paths,
                    )
                else:
                    result = {
                        "kind": kind,
                        "target": str(item.get("target", "")),
                        "ok": False,
                        "detail": "unsupported expected_evidence kind",
                        "matches": [],
                    }

                checks.append(result)
                if result["ok"]:
                    passed_checks += 1
                else:
                    failed_checks += 1

            questions.append(
                {
                    "id": str(question.get("id", "")),
                    "title": str(question.get("title", "")),
                    "preferred_mode": str(question.get("preferred_mode", "")),
                    "ok": all(item["ok"] for item in checks),
                    "checks": checks,
                }
            )
    finally:
        conn.close()

    return {
        "ok": failed_checks == 0,
        "timestamp": datetime.now().isoformat(),
        "pack": {
            "path": pack.get("_path", ""),
            "pack_id": pack.get("pack_id", ""),
            "title": pack.get("title", ""),
        },
        "index": {
            "db_path": str(db_file),
            "ok": True,
            "summary": "index inspected successfully",
            "chunk_count": int(stats.get("chunk_count", 0) or 0),
            "source_count": int(stats.get("source_count", 0) or 0),
        },
        "summary": {
            "questions": len(questions),
            "checks": total_checks,
            "passed": passed_checks,
            "failed": failed_checks,
        },
        "questions": questions,
    }


def write_demo_rehearsal_audit_report(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    report_dir = default_demo_validation_report_dir(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    report_path = report_dir / "{}_demo_rehearsal_audit.json".format(stamp)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def _index_sources_by_basename(
    sources: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in sources:
        basename = str(row.get("basename", "") or "").strip().lower()
        if not basename:
            continue
        index.setdefault(basename, []).append(
            {
                "source_path": str(row.get("source_path", "")),
                "chunk_count": int(row.get("chunk_count", 0) or 0),
            }
        )
    return index


def _audit_path_target(
    item: dict[str, Any],
    sources_by_basename: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    target = str(item.get("target", "")).strip()
    key = target.lower()
    matches = list(sources_by_basename.get(key, []))
    if matches:
        detail = "{} indexed source match(es)".format(len(matches))
    else:
        detail = "target file not found in indexed source paths"
    return {
        "kind": "path",
        "target": target,
        "ok": bool(matches),
        "detail": detail,
        "matches": matches,
    }


def _audit_citation_target(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    preferred_paths: set[str],
) -> dict[str, Any]:
    target = str(item.get("target", "")).strip()
    exact_phrase = _normalize_text(target)
    terms = _meaningful_terms(target)
    required_terms = _required_term_count(len(terms))
    rows = _candidate_rows_for_terms(
        conn,
        terms or [exact_phrase],
        preferred_paths=preferred_paths,
    )

    matches: list[dict[str, Any]] = []
    for row in rows:
        source_path = str(row["source_path"] or "")
        basename = Path(source_path).name.strip().lower()
        raw_text = str(row["text"] or "")
        normalized_text = _normalize_text(raw_text)
        exact_match = bool(exact_phrase and exact_phrase in normalized_text)
        matched_terms = [term for term in terms if term and term in normalized_text]
        if not exact_match and len(matched_terms) < required_terms:
            continue
        matches.append(
            {
                "source_path": source_path,
                "chunk_index": int(row["chunk_index"] or 0),
                "matched_terms": matched_terms,
                "matched_term_count": len(matched_terms),
                "required_term_count": required_terms,
                "exact_phrase_match": exact_match,
                "preferred_source_match": basename in preferred_paths,
                "preview": _preview_text(raw_text, matched_terms, exact_phrase),
            }
        )

    matches.sort(
        key=lambda record: (
            not bool(record["exact_phrase_match"]),
            not bool(record["preferred_source_match"]),
            -int(record["matched_term_count"]),
            str(record["source_path"]).lower(),
            int(record["chunk_index"]),
        )
    )
    matches = matches[:5]

    if matches:
        best = matches[0]
        detail = (
            "matched {} term(s) in {} chunk {}".format(
                best["matched_term_count"],
                Path(best["source_path"]).name or best["source_path"],
                best["chunk_index"],
            )
        )
    else:
        detail = "citation phrase not found in indexed chunk text"

    return {
        "kind": "citation_target",
        "target": target,
        "ok": bool(matches),
        "detail": detail,
        "required_term_count": required_terms,
        "matches": matches,
    }


def _candidate_rows_for_terms(
    conn: sqlite3.Connection,
    terms: list[str],
    *,
    preferred_paths: set[str] | None = None,
) -> list[sqlite3.Row]:
    cleaned = [str(term or "").strip().lower() for term in terms if str(term or "").strip()]
    if not cleaned:
        return []
    rows: list[sqlite3.Row] = []
    seen: set[tuple[str, int]] = set()

    if preferred_paths:
        preferred_rows = _query_candidate_rows(
            conn,
            cleaned,
            preferred_paths=preferred_paths,
            limit=100,
        )
        for row in preferred_rows:
            key = (str(row["source_path"] or ""), int(row["chunk_index"] or 0))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    if len(rows) < 25:
        fallback_rows = _query_candidate_rows(conn, cleaned, limit=250)
        for row in fallback_rows:
            key = (str(row["source_path"] or ""), int(row["chunk_index"] or 0))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    return rows


def _query_candidate_rows(
    conn: sqlite3.Connection,
    cleaned_terms: list[str],
    *,
    preferred_paths: set[str] | None = None,
    limit: int = 250,
) -> list[sqlite3.Row]:
    text_clause = " OR ".join("instr(lower(text), ?) > 0" for _ in cleaned_terms)
    params: list[Any] = list(cleaned_terms)
    where_parts = ["({})".format(text_clause)]

    if preferred_paths:
        basenames = sorted(
            str(path or "").strip().lower()
            for path in preferred_paths
            if str(path or "").strip()
        )
        if basenames:
            path_clause = " OR ".join("lower(source_path) LIKE ?" for _ in basenames)
            where_parts.insert(0, "({})".format(path_clause))
            params = ["%{}".format(name) for name in basenames] + params

    query = """
        SELECT source_path, chunk_index, text
        FROM chunks
        WHERE {}
        LIMIT {}
    """.format(" AND ".join(where_parts), int(limit))
    return list(conn.execute(query, params).fetchall())


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _meaningful_terms(target: str) -> list[str]:
    phrases = _CONNECTOR_PATTERN.split(str(target or "").strip())
    ordered_terms: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        for token in _TOKEN_PATTERN.findall(phrase.lower()):
            if token in _STOP_WORDS:
                continue
            if len(token) == 1 and not token.isdigit():
                continue
            if token in seen:
                continue
            seen.add(token)
            ordered_terms.append(token)
    return ordered_terms


def _required_term_count(term_count: int) -> int:
    if term_count <= 0:
        return 1
    if term_count <= 2:
        return term_count
    return max(3, min(term_count, int(math.ceil(term_count * 0.6))))


def _preview_text(text: str, matched_terms: list[str], exact_phrase: str) -> str:
    raw_text = " ".join(str(text or "").split())
    lower_text = raw_text.lower()
    anchor = exact_phrase
    if not anchor and matched_terms:
        anchor = matched_terms[0]
    if anchor:
        offset = lower_text.find(anchor)
    else:
        offset = 0
    if offset < 0:
        offset = 0
    start = max(0, offset - 40)
    end = min(len(raw_text), offset + 120)
    snippet = raw_text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(raw_text):
        snippet = snippet + "..."
    return snippet
