# === NON-PROGRAMMER GUIDE ===
# Purpose: Shared quality-control helpers for HybridRAG index validation.
# What to read first: Start at inspect_index_database(), then detect_index_contamination().
# Inputs: Index database path, embeddings cache path, and optional expected source root.
# Outputs: Read-only QC summaries and optional fingerprint manifests.
# Safety notes: This module never modifies the index.
# ============================

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


_CONTAMINATION_MARKERS = {
    "test_or_demo_artifact": (
        "testing_addon_pack",
        "test_addon_pack",
        "unanswerable_question",
        "_demo_doc",
        "demo_doc.",
        ".tmp_gui_demo",
        "smoke_test",
        "_pipeline_test_doc",
        "test_harness",
        "test_fixture",
    ),
    "golden_seed_file": (
        "golden_seed",
        "golden_seeds",
    ),
    "zip_bundle": (
        ".zip",
        ".tar.gz",
    ),
}


def _normalize_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).resolve()).lower()
    except Exception:
        return str(Path(raw)).lower()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def inspect_index_database(db_path: Path) -> dict[str, Any]:
    db_file = Path(db_path)
    try:
        conn = sqlite3.connect(str(db_file))
    except Exception as exc:
        return {"ok": False, "reason": f"could not open SQLite database: {exc}"}

    try:
        chunk_count = int(
            conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] or 0
        )
        rows = conn.execute(
            """
            SELECT source_path, COUNT(*) AS chunk_count
            FROM chunks
            GROUP BY source_path
            ORDER BY source_path
            """
        ).fetchall()
    except Exception as exc:
        return {"ok": False, "reason": f"database query failed: {exc}"}
    finally:
        conn.close()

    source_rows: list[dict[str, Any]] = []
    basenames: set[str] = set()
    for row in rows:
        source_path = str(row[0] or "").strip()
        basename = Path(source_path).name.strip().lower() if source_path else ""
        if basename:
            basenames.add(basename)
        source_rows.append(
            {
                "source_path": source_path,
                "basename": basename,
                "chunk_count": int(row[1] or 0),
            }
        )

    return {
        "ok": True,
        "chunk_count": chunk_count,
        "source_count": len(source_rows),
        "basenames": basenames,
        "sources": source_rows,
    }


def detect_index_contamination(
    db_path: Path,
    *,
    source_root: str = "",
) -> dict[str, Any]:
    stats = inspect_index_database(Path(db_path))
    if not stats.get("ok"):
        return {
            "ok": False,
            "level": "FAIL",
            "summary": stats.get("reason", "could not inspect index"),
            "suspicious_count": 0,
            "temp_path_count": 0,
            "outside_root_count": 0,
            "suspicious_sources": [],
        }

    normalized_root = _normalize_path(source_root)
    root_path = Path(normalized_root) if normalized_root else None
    suspicious_sources: list[dict[str, Any]] = []
    temp_count = 0
    outside_root_count = 0

    for row in stats["sources"]:
        source_path = str(row["source_path"] or "")
        normalized_source = _normalize_path(source_path)
        flags: list[str] = []

        if normalized_source.startswith("\\\\?\\"):
            normalized_source = normalized_source[4:]

        # Determine if the file lives under source_root first so we can
        # skip the temp-path heuristic for legitimate source files (the
        # source_root itself may reside inside a temp directory).
        inside_root = False
        if root_path is not None and source_path:
            source_obj = Path(source_path)
            if source_obj.is_absolute():
                if _is_relative_to(source_obj, root_path):
                    inside_root = True
                else:
                    flags.append("outside_source_root")
                    outside_root_count += 1

        if (
            not inside_root
            and normalized_source
            and "\\appdata\\local\\temp\\" in normalized_source
        ):
            flags.append("temp_path")
            temp_count += 1
        for flag_name, markers in _CONTAMINATION_MARKERS.items():
            if any(marker in normalized_source for marker in markers):
                flags.append(flag_name)
        if (
            not inside_root
            and normalized_source
            and (
                "\\temp\\" in normalized_source
                or "/temp/" in normalized_source
                or "\\tmp\\" in normalized_source
                or "/tmp/" in normalized_source
            )
            and "temp_path" not in flags
        ):
            flags.append("temp_or_pipeline_doc")

        if flags:
            suspicious_sources.append(
                {
                    "source_path": source_path,
                    "basename": row["basename"],
                    "chunk_count": row["chunk_count"],
                    "flags": flags,
                }
            )

    if suspicious_sources:
        summary = (
            f"index contamination detected: {len(suspicious_sources)} suspicious source paths"
        )
        if temp_count:
            summary += f" ({temp_count} temp)"
        if outside_root_count:
            summary += f" ({outside_root_count} outside source root)"
        level = "FAIL"
    else:
        summary = "index source paths look clean"
        level = "PASS"

    return {
        "ok": True,
        "level": level,
        "summary": summary,
        "suspicious_count": len(suspicious_sources),
        "temp_path_count": temp_count,
        "outside_root_count": outside_root_count,
        "suspicious_sources": suspicious_sources,
    }


def collect_index_artifacts(db_path: Path, embeddings_cache: Path | None = None) -> list[Path]:
    artifacts: list[Path] = []
    db_file = Path(db_path)
    if db_file.exists():
        artifacts.append(db_file)
    if embeddings_cache:
        cache_root = Path(embeddings_cache)
        if cache_root.exists():
            artifacts.extend(sorted(p for p in cache_root.rglob("*") if p.is_file()))
    return sorted({p.resolve() for p in artifacts}, key=lambda p: str(p).lower())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_index_fingerprint(
    db_path: Path,
    embeddings_cache: Path | None = None,
) -> dict[str, Any]:
    artifacts = collect_index_artifacts(db_path, embeddings_cache)
    combined = hashlib.sha256()
    files: list[dict[str, Any]] = []

    for artifact in artifacts:
        file_hash = _sha256_file(artifact)
        stat = artifact.stat()
        record = {
            "path": str(artifact),
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": file_hash,
        }
        files.append(record)
        combined.update(record["path"].encode("utf-8", errors="ignore"))
        combined.update(str(record["size_bytes"]).encode("ascii"))
        combined.update(str(record["mtime_ns"]).encode("ascii"))
        combined.update(file_hash.encode("ascii"))

    return {
        "artifact_count": len(files),
        "combined_sha256": combined.hexdigest(),
        "files": files,
    }


def compare_fingerprints(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_map = {item["path"]: item for item in current.get("files", [])}
    baseline_map = {item["path"]: item for item in baseline.get("files", [])}

    added = sorted(path for path in current_map if path not in baseline_map)
    removed = sorted(path for path in baseline_map if path not in current_map)
    changed = sorted(
        path
        for path in current_map
        if path in baseline_map
        and current_map[path].get("sha256") != baseline_map[path].get("sha256")
    )

    return {
        "matches": (
            current.get("combined_sha256", "") == baseline.get("combined_sha256", "")
        ),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def write_fingerprint(path: Path, fingerprint: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")


def load_fingerprint(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
