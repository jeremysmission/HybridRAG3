# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the content freshness area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Source-folder mtimes and latest index-run timestamps.
# Outputs: Assertions over the freshness/drift snapshot returned to operators.
# Safety notes: Uses temp directories only; does not touch the live indexed corpus.
# ============================

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from src.api.content_freshness import (
    build_content_freshness_snapshot,
    clear_content_freshness_cache,
)


def _touch(path: Path, *, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sample", encoding="utf-8")
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def test_content_freshness_marks_missing_index_run_as_stale(tmp_path):
    source_dir = tmp_path / "source"
    _touch(source_dir / "one.md", when=datetime(2026, 3, 13, 5, 0, tzinfo=timezone.utc))

    snapshot = build_content_freshness_snapshot(
        str(source_dir),
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    assert snapshot["source_exists"] is True
    assert snapshot["total_indexable_files"] == 1
    assert snapshot["files_newer_than_index"] == 1
    assert snapshot["stale"] is True
    assert "no completed index run" in snapshot["summary"].lower()


def test_content_freshness_detects_newer_files_than_last_index(tmp_path):
    source_dir = tmp_path / "source"
    base = datetime(2026, 3, 13, 4, 0, tzinfo=timezone.utc)
    _touch(source_dir / "old.md", when=base - timedelta(hours=2))
    _touch(source_dir / "new.md", when=base + timedelta(hours=1))

    snapshot = build_content_freshness_snapshot(
        str(source_dir),
        latest_index_started_at="2026-03-13T04:00:00Z",
        latest_index_finished_at="2026-03-13T04:15:00Z",
        latest_index_status="completed",
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    assert snapshot["total_indexable_files"] == 2
    assert snapshot["files_newer_than_index"] == 1
    assert snapshot["stale"] is True
    assert snapshot["latest_source_path"].endswith("new.md")


def test_content_freshness_reports_fresh_when_sources_are_older_than_index(tmp_path):
    source_dir = tmp_path / "source"
    _touch(source_dir / "doc.md", when=datetime(2026, 3, 13, 1, 0, tzinfo=timezone.utc))

    snapshot = build_content_freshness_snapshot(
        str(source_dir),
        latest_index_started_at="2026-03-13T02:00:00Z",
        latest_index_finished_at="2026-03-13T02:30:00Z",
        latest_index_status="completed",
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    assert snapshot["files_newer_than_index"] == 0
    assert snapshot["stale"] is False
    assert "up to date" in snapshot["summary"].lower()


def test_content_freshness_marks_failed_last_run_as_stale(tmp_path):
    source_dir = tmp_path / "source"
    _touch(source_dir / "doc.md", when=datetime(2026, 3, 13, 1, 0, tzinfo=timezone.utc))

    snapshot = build_content_freshness_snapshot(
        str(source_dir),
        latest_index_started_at="2026-03-13T02:00:00Z",
        latest_index_finished_at="2026-03-13T02:30:00Z",
        latest_index_status="failed",
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    assert snapshot["files_newer_than_index"] == 0
    assert snapshot["stale"] is True
    assert "status is failed" in snapshot["summary"].lower()


def test_content_freshness_marks_old_successful_run_as_stale(tmp_path):
    source_dir = tmp_path / "source"
    _touch(source_dir / "doc.md", when=datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc))

    snapshot = build_content_freshness_snapshot(
        str(source_dir),
        latest_index_started_at="2020-01-01T00:00:00Z",
        latest_index_finished_at="2020-01-01T00:30:00Z",
        latest_index_status="completed",
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=1,
    )

    assert snapshot["files_newer_than_index"] == 0
    assert snapshot["stale"] is True
    assert snapshot["freshness_age_hours"] is not None
    assert "hours old" in snapshot["summary"].lower()


def test_content_freshness_cache_can_be_cleared_for_immediate_recheck(tmp_path):
    source_dir = tmp_path / "source"
    base = datetime(2026, 3, 13, 4, 0, tzinfo=timezone.utc)
    clear_content_freshness_cache()
    _touch(source_dir / "one.md", when=base)

    first = build_content_freshness_snapshot(
        str(source_dir),
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    _touch(source_dir / "two.md", when=base + timedelta(minutes=5))

    cached = build_content_freshness_snapshot(
        str(source_dir),
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )
    assert cached["total_indexable_files"] == 1
    assert cached["latest_source_path"].endswith("one.md")

    clear_content_freshness_cache()
    refreshed = build_content_freshness_snapshot(
        str(source_dir),
        supported_extensions=[".md"],
        excluded_dirs=[],
        warn_after_hours=24,
    )

    assert first["total_indexable_files"] == 1
    assert refreshed["total_indexable_files"] == 2
    assert refreshed["files_newer_than_index"] == 2
    assert refreshed["latest_source_path"].endswith("two.md")
