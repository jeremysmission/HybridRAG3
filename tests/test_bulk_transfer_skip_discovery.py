# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the bulk transfer skip discovery area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
import sqlite3
import threading
from pathlib import Path

from src.tools.bulk_transfer_v2 import (
    AtomicTransferWorker,
    BulkTransferV2,
    SourceDiscovery,
    TransferConfig,
    TransferStats,
)
from src.tools.transfer_manifest import TransferManifest


def _seed_previous_run(dest_root: Path, source_path: Path, *, result: str = "failed") -> Path:
    db_path = dest_root / "_transfer_manifest.db"
    manifest = TransferManifest(str(db_path))
    previous_run = "20260310_000000_000000"
    try:
        stat_result = source_path.stat()
        manifest.start_run(previous_run, [str(source_path.parent)], str(dest_root))
        manifest.record_source_file(
            previous_run,
            str(source_path),
            file_size=stat_result.st_size,
            file_mtime=stat_result.st_mtime,
            file_ctime=getattr(stat_result, "st_ctime", 0.0),
            extension=source_path.suffix.lower(),
            is_accessible=True,
            path_length=len(str(source_path)),
        )
        if result:
            manifest.record_transfer(previous_run, str(source_path), result=result)
        manifest.finish_run(previous_run)
        manifest.flush()
    finally:
        manifest.close()
    return db_path


def _run_table_count(db_path: Path, table: str, run_id: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE run_id=?",
            (run_id,),
        ).fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        conn.close()


def _run_result_counts(db_path: Path, run_id: str, *, table: str, field: str) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            f"SELECT {field}, COUNT(*) FROM {table} WHERE run_id=? GROUP BY {field}",
            (run_id,),
        ).fetchall()
        return {str(key): int(count or 0) for key, count in rows}
    finally:
        conn.close()


def test_skip_full_discovery_uses_resume_seed_only(tmp_path, monkeypatch):
    """
    When skip_full_discovery=True, engine should not run source crawl.
    It should transfer only resume-seeded candidates.
    """
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()
    sample = src_root / "seed.txt"
    sample.write_text("hello", encoding="utf-8")

    seeded_item = (str(sample), str(src_root), sample.name, sample.stat().st_size)
    seen = {"items": []}

    def fake_resume_seed_iter(self):
        yield seeded_item

    def fake_discover_iter(self):
        raise AssertionError("discover_iter should not run when skip_full_discovery=True")

    def fake_transfer(self, queue):
        seen["items"] = list(queue)
        self.stats.files_copied = len(seen["items"])

    monkeypatch.setattr(SourceDiscovery, "resume_seed_iter", fake_resume_seed_iter)
    monkeypatch.setattr(SourceDiscovery, "discover_iter", fake_discover_iter)
    monkeypatch.setattr(AtomicTransferWorker, "transfer", fake_transfer)

    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(dst_root),
        workers=1,
        skip_full_discovery=True,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()

    assert len(seen["items"]) == 1
    assert seen["items"][0][0] == str(sample)
    assert stats.files_copied == 1


def test_skip_full_discovery_falls_back_when_no_seed(tmp_path, monkeypatch):
    """
    If skip_full_discovery is enabled but resume seed is empty, engine should
    fall back to live discovery instead of doing a no-op run.
    """
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()
    sample = src_root / "fallback.txt"
    sample.write_text("hello", encoding="utf-8")

    seen = {"items": []}

    def fake_resume_seed_iter(self):
        if False:
            yield None

    def fake_discover_iter(self):
        yield (str(sample), str(src_root), sample.name, sample.stat().st_size)

    def fake_transfer(self, queue):
        seen["items"] = list(queue)
        self.stats.files_copied = len(seen["items"])

    monkeypatch.setattr(SourceDiscovery, "resume_seed_iter", fake_resume_seed_iter)
    monkeypatch.setattr(SourceDiscovery, "discover_iter", fake_discover_iter)
    monkeypatch.setattr(AtomicTransferWorker, "transfer", fake_transfer)

    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(dst_root),
        workers=1,
        skip_full_discovery=True,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()

    assert len(seen["items"]) == 1
    assert seen["items"][0][0] == str(sample)
    assert stats.files_copied == 1


class _ManifestDouble:
    def __init__(self, successful_mtimes=None):
        self.successful_mtimes = successful_mtimes or {}
        self.recorded = []
        self.skips = []

    def get_successful_transfer_mtimes(self):
        return dict(self.successful_mtimes)

    def record_source_file(self, *args, **kwargs):
        self.recorded.append((args, kwargs))

    def record_skip(self, *args, **kwargs):
        self.skips.append((args, kwargs))

    def is_already_transferred(self, *args, **kwargs):
        raise AssertionError(
            "resume skip cache should avoid per-file is_already_transferred queries"
        )


def test_process_discovery_uses_preloaded_resume_skip_map(tmp_path):
    src_root = tmp_path / "src"
    src_root.mkdir()
    sample = src_root / "already.txt"
    sample.write_text("x" * 200, encoding="utf-8")
    manifest = _ManifestDouble(
        {str(sample): sample.stat().st_mtime}
    )
    stats = TransferStats()
    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(tmp_path / "dst"),
        workers=1,
        resume=True,
        extensions={".txt"},
    )
    discovery = SourceDiscovery(
        cfg, manifest, stats, "run1", threading.Lock(), threading.Event()
    )

    queue = []
    discovery._process_discovery(str(sample), str(src_root), queue)

    assert queue == []
    assert stats.files_skipped_unchanged == 1
    assert len(manifest.recorded) == 1
    assert len(manifest.skips) == 1
    assert manifest.skips[0][0][4] == "already_transferred"


def test_process_discovery_skips_stat_for_unsupported_extension(tmp_path, monkeypatch):
    src_root = tmp_path / "src"
    src_root.mkdir()
    sample = src_root / "ignored.exe"
    sample.write_text("x" * 200, encoding="utf-8")
    manifest = _ManifestDouble()
    stats = TransferStats()
    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(tmp_path / "dst"),
        workers=1,
        extensions={".txt"},
    )
    discovery = SourceDiscovery(
        cfg, manifest, stats, "run1", threading.Lock(), threading.Event()
    )

    def fail_stat(_path, timeout=5.0):
        raise AssertionError("unsupported extensions should be rejected before stat()")

    monkeypatch.setattr("src.tools.bulk_transfer_v2._stat_with_timeout", fail_stat)

    queue = []
    discovery._process_discovery(str(sample), str(src_root), queue)

    assert queue == []
    assert stats.files_skipped_ext == 1
    assert len(manifest.recorded) == 1
    assert len(manifest.skips) == 1
    assert manifest.skips[0][0][4] == "always_skip"


def test_skip_full_discovery_seeded_locked_file_records_current_run_manifest(
    tmp_path, monkeypatch, capsys,
):
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()
    sample = src_root / "seed_locked.txt"
    sample.write_text("x" * 200, encoding="utf-8")
    db_path = _seed_previous_run(dst_root, sample, result="failed")

    def fail_discover_iter(self):
        raise AssertionError(
            "discover_iter should not run when skip_full_discovery uses seeded candidates"
        )

    monkeypatch.setattr(SourceDiscovery, "discover_iter", fail_discover_iter)
    monkeypatch.setattr("src.tools.bulk_transfer_v2._can_read_file", lambda _path, timeout=5.0: False)

    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(dst_root),
        workers=1,
        resume=True,
        skip_full_discovery=True,
        max_retries=1,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()
    output = capsys.readouterr().out

    assert stats.files_skipped_locked == 1
    assert stats.files_manifest == 1
    assert stats.files_delta_deleted == 0
    assert _run_table_count(db_path, "source_manifest", engine.run_id) == 1
    assert _run_result_counts(
        db_path, engine.run_id, table="transfer_log", field="result"
    ) == {"locked": 1}
    assert _run_result_counts(
        db_path, engine.run_id, table="skipped_files", field="reason"
    ) == {"locked": 1}
    assert "ZERO-GAP VERIFIED" in output
    assert "Delta: 0 new, 0 deleted" in output


def test_skip_full_discovery_seeded_success_updates_manifest_totals(
    tmp_path, monkeypatch, capsys,
):
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()
    sample = src_root / "seed_success.txt"
    sample.write_text("x" * 200, encoding="utf-8")
    db_path = _seed_previous_run(dst_root, sample, result="failed")

    def fail_discover_iter(self):
        raise AssertionError(
            "discover_iter should not run when skip_full_discovery uses seeded candidates"
        )

    monkeypatch.setattr(SourceDiscovery, "discover_iter", fail_discover_iter)

    cfg = TransferConfig(
        source_paths=[str(src_root)],
        dest_path=str(dst_root),
        workers=1,
        resume=True,
        skip_full_discovery=True,
        max_retries=1,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()
    output = capsys.readouterr().out

    assert stats.files_copied == 1
    assert stats.files_manifest == 1
    assert stats.files_delta_deleted == 0
    assert _run_table_count(db_path, "source_manifest", engine.run_id) == 1
    assert _run_result_counts(
        db_path, engine.run_id, table="transfer_log", field="result"
    ) == {"success": 1}
    assert "ZERO-GAP VERIFIED" in output
    assert "Source manifest:         1" in output
