# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the content freshness part of the application runtime.
# What to read first: Start at build_content_freshness_snapshot(), then read the small file-walk helpers.
# Inputs: Source-folder paths, latest index-run timestamps, and indexer file filters.
# Outputs: A cached freshness/drift snapshot for operator-facing API/browser surfaces.
# Safety notes: This module only reads metadata (directory walk + mtimes); it does not open file contents.
# ============================

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, Optional


_CACHE_LOCK = threading.Lock()
_CACHE_KEY = None
_CACHE_VALUE = None
_CACHE_TS = 0.0
_CACHE_TTL_SECONDS = 30.0


def clear_content_freshness_cache() -> None:
    """Invalidate the cached freshness snapshot for an immediate recheck."""
    with _CACHE_LOCK:
        global _CACHE_KEY, _CACHE_VALUE, _CACHE_TS
        _CACHE_KEY = None
        _CACHE_VALUE = None
        _CACHE_TS = 0.0


def _parse_iso8601(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalized_extensions(values: Optional[Iterable[str]]) -> Optional[set[str]]:
    if not values:
        return None
    normalized = {
        str(value or "").strip().lower()
        for value in values
        if str(value or "").strip()
    }
    return normalized or None


def _normalized_excluded_dirs(values: Optional[Iterable[str]]) -> set[str]:
    if not values:
        return set()
    return {
        str(value or "").strip().lower()
        for value in values
        if str(value or "").strip()
    }


def build_content_freshness_snapshot(
    source_folder: str,
    *,
    latest_index_started_at: str = "",
    latest_index_finished_at: str = "",
    latest_index_status: str = "",
    supported_extensions: Optional[Iterable[str]] = None,
    excluded_dirs: Optional[Iterable[str]] = None,
    warn_after_hours: int = 24,
) -> dict[str, object]:
    """Build a cached operator-facing freshness/drift snapshot."""
    supported = _normalized_extensions(supported_extensions)
    excluded = _normalized_excluded_dirs(excluded_dirs)
    cache_key = (
        str(source_folder or ""),
        str(latest_index_started_at or ""),
        str(latest_index_finished_at or ""),
        str(latest_index_status or ""),
        tuple(sorted(supported or set())),
        tuple(sorted(excluded)),
        int(max(1, warn_after_hours)),
    )
    now_ts = time.time()
    with _CACHE_LOCK:
        global _CACHE_KEY, _CACHE_VALUE, _CACHE_TS
        if (
            _CACHE_KEY == cache_key
            and _CACHE_VALUE is not None
            and (now_ts - _CACHE_TS) < _CACHE_TTL_SECONDS
        ):
            return dict(_CACHE_VALUE)

    source_path = str(source_folder or "")
    source_exists = bool(source_path) and os.path.isdir(source_path)
    latest_index_dt = _parse_iso8601(latest_index_finished_at) or _parse_iso8601(latest_index_started_at)
    latest_source_dt: Optional[datetime] = None
    latest_source_path = ""
    total_indexable_files = 0
    files_newer_than_index = 0

    if source_exists:
        for root, dirs, files in os.walk(source_path):
            dirs[:] = [
                dirname
                for dirname in dirs
                if dirname.lower() not in excluded
            ]
            for filename in files:
                full_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                if supported is not None and ext not in supported:
                    continue
                try:
                    stat_result = os.stat(full_path)
                except OSError:
                    continue
                file_dt = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
                total_indexable_files += 1
                if latest_source_dt is None or file_dt > latest_source_dt:
                    latest_source_dt = file_dt
                    latest_source_path = full_path
                if latest_index_dt is None or file_dt > latest_index_dt:
                    files_newer_than_index += 1

    freshness_age_hours = None
    if latest_index_dt is not None:
        freshness_age_hours = round(
            max(0.0, (datetime.fromtimestamp(now_ts, tz=timezone.utc) - latest_index_dt).total_seconds()) / 3600.0,
            1,
        )

    stale = False
    summary = "Freshness state unavailable."
    normalized_status = str(latest_index_status or "").strip().lower()
    warn_after_hours = int(max(1, warn_after_hours))
    if not source_exists:
        stale = True
        summary = "Source folder is missing or not accessible."
    elif total_indexable_files == 0:
        stale = False
        summary = "No indexable source files found."
    elif latest_index_dt is None:
        stale = True
        summary = f"{total_indexable_files} indexable files found and no completed index run is recorded."
    elif files_newer_than_index > 0:
        stale = True
        summary = f"{files_newer_than_index} files changed after the last index run."
    elif normalized_status and normalized_status not in ("finished", "completed", "success"):
        stale = True
        summary = f"Last index run status is {normalized_status}."
    elif freshness_age_hours is not None and freshness_age_hours > warn_after_hours:
        stale = True
        summary = f"Last index run is {freshness_age_hours} hours old."
    else:
        summary = "Indexed content is up to date with the current source tree."

    snapshot = {
        "source_folder": source_path,
        "source_exists": source_exists,
        "total_indexable_files": total_indexable_files,
        "latest_source_update_at": _iso_or_none(latest_source_dt),
        "latest_source_path": latest_source_path,
        "last_index_started_at": str(latest_index_started_at or "") or None,
        "last_index_finished_at": str(latest_index_finished_at or "") or None,
        "last_index_status": str(latest_index_status or ""),
        "files_newer_than_index": files_newer_than_index,
        "freshness_age_hours": freshness_age_hours,
        "warn_after_hours": warn_after_hours,
        "stale": stale,
        "summary": summary,
    }
    with _CACHE_LOCK:
        _CACHE_KEY = cache_key
        _CACHE_VALUE = dict(snapshot)
        _CACHE_TS = now_ts
    return snapshot
