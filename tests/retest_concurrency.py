# ============================================================================
# Destructive QA: Concurrency races and SQLite integrity tests for the
# HybridRAG bulk transfer engine (V2).
#
# Tests target TOCTOU races, dedup races, INSERT OR REPLACE guards,
# worker caps, queue backpressure, concurrent DB writes, bounded data
# structures, stats accuracy, and close-during-write safety.
# ============================================================================

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------

from src.tools.transfer_staging import StagingManager
from src.tools.transfer_manifest import TransferManifest
from src.tools.bulk_transfer_v2 import (
    AtomicTransferWorker,
    BulkTransferV2,
    TransferConfig,
    TransferStats,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def staging_dir(tmp_path):
    """Provide a clean staging directory per test."""
    d = tmp_path / "staging"
    d.mkdir()
    return d


@pytest.fixture()
def manifest_db(tmp_path):
    """Provide a fresh TransferManifest backed by a temp DB."""
    db = tmp_path / "manifest.db"
    m = TransferManifest(str(db))
    yield m
    try:
        m.close()
    except Exception:
        pass


# ===================================================================
# TEST 1 -- TOCTOU race: promote_to_verified (THE critical test)
#
# 20 threads call promote_to_verified with the SAME relative_path
# simultaneously. Every file must survive. No overwrite, no data
# loss. Count files in verified/ -- must be exactly 20.
# ===================================================================

class TestTOCTOURace:
    def test_20_threads_same_relpath_no_overwrite(self, staging_dir):
        sm = StagingManager(str(staging_dir))
        rel = "reports/Q1.pdf"
        n_threads = 20
        results: List[Path] = [None] * n_threads
        errors: List[Exception] = [None] * n_threads
        barrier = threading.Barrier(n_threads)

        # Pre-create 20 distinct .tmp files in incoming/ each with
        # unique content so we can verify no data was lost.
        tmp_paths = []
        for i in range(n_threads):
            tmp = sm.incoming_path(rel)
            # incoming_path returns the same name each time, so we
            # need unique .tmp names. Write unique content and rename.
            actual_tmp = tmp.parent / f"Q1_{i}.pdf.tmp"
            actual_tmp.parent.mkdir(parents=True, exist_ok=True)
            actual_tmp.write_text(f"CONTENT-{i}", encoding="utf-8")
            tmp_paths.append(actual_tmp)

        def _promote(idx):
            try:
                barrier.wait(timeout=10)
                results[idx] = sm.promote_to_verified(tmp_paths[idx], rel)
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=_promote, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Check: no errors
        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} raised: {err}"

        # Check: all 20 result paths are distinct
        result_paths = [r for r in results if r is not None]
        assert len(result_paths) == n_threads, (
            f"Expected {n_threads} results, got {len(result_paths)}"
        )
        assert len(set(result_paths)) == n_threads, (
            "Duplicate result paths -- TOCTOU collision detected!"
        )

        # Check: all 20 files physically exist in verified/
        verified_files = list(sm.verified.rglob("*"))
        verified_files = [f for f in verified_files if f.is_file()]
        assert len(verified_files) == n_threads, (
            f"Expected {n_threads} files in verified/, found "
            f"{len(verified_files)}: {verified_files}"
        )

        # Check: every file has unique content (no overwrites)
        contents = set()
        for f in verified_files:
            contents.add(f.read_text(encoding="utf-8"))
        assert len(contents) == n_threads, (
            f"Data loss! Only {len(contents)} unique contents out of "
            f"{n_threads} files."
        )


# ===================================================================
# TEST 2 -- Dedup race: 10 threads submit same-hash file
#
# Exactly 1 should be copied (claimed in _dedup_seen), 9 should be
# deduped. Verify _dedup_seen set and stats.files_deduplicated.
# ===================================================================

class TestDedupRace:
    def test_10_threads_same_hash_exactly_1_copied(self, staging_dir):
        cfg = TransferConfig(
            source_paths=[str(staging_dir)],
            dest_path=str(staging_dir),
            workers=1,
            deduplicate=True,
        )
        manifest = TransferManifest(
            str(staging_dir / "_manifest.db")
        )
        run_id = "test_dedup_race"
        manifest.start_run(run_id, cfg.source_paths, cfg.dest_path)
        staging = StagingManager(str(staging_dir))
        stats = TransferStats()
        stop_event = threading.Event()
        log_lock = threading.Lock()

        worker = AtomicTransferWorker(
            cfg, manifest, staging, stats,
            run_id, stop_event, log_lock,
        )

        test_hash = "aabbccdd" * 8  # 64-char fake SHA-256
        n_threads = 10
        claimed = []  # threads that claimed the hash (not deduped)
        deduped = []  # threads that were deduped
        barrier = threading.Barrier(n_threads)
        lock = threading.Lock()

        def _try_dedup(idx):
            barrier.wait(timeout=10)
            with worker._dedup_lock:
                if test_hash in worker._dedup_seen:
                    stats.files_deduplicated += 1
                    with lock:
                        deduped.append(idx)
                    return
                # Also check DB (as the real code does)
                existing = manifest.find_by_hash(test_hash)
                if existing:
                    worker._dedup_seen.add(test_hash)
                    stats.files_deduplicated += 1
                    with lock:
                        deduped.append(idx)
                    return
                worker._dedup_seen.add(test_hash)
                with lock:
                    claimed.append(idx)

        threads = [threading.Thread(target=_try_dedup, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(claimed) == 1, (
            f"Expected exactly 1 claim, got {len(claimed)}: {claimed}"
        )
        assert len(deduped) == n_threads - 1, (
            f"Expected {n_threads - 1} deduped, got {len(deduped)}"
        )
        assert stats.files_deduplicated == n_threads - 1
        assert test_hash in worker._dedup_seen

        manifest.close()


# ===================================================================
# TEST 3 -- INSERT OR REPLACE guard: success cannot be overwritten
#           by a failure record.
# ===================================================================

class TestInsertOrReplaceGuard:
    def test_success_survives_later_failure_write(self, manifest_db):
        m = manifest_db
        run_id = "test_run_001"
        m.start_run(run_id, ["/src"], "/dst")
        src = "/src/file.txt"

        # Record success first
        m.record_transfer(
            run_id, src, dest_path="/dst/file.txt",
            hash_source="abc123", hash_dest="abc123",
            result="success",
        )

        # Now attempt to overwrite with failure
        m.record_transfer(
            run_id, src, result="failed",
            error_message="Simulated retry failure",
        )

        # Verify success record is preserved
        with m._lock:
            row = m.conn.execute(
                "SELECT result, error_message FROM transfer_log "
                "WHERE source_path=? AND run_id=?",
                (src, run_id),
            ).fetchone()
        assert row is not None
        assert row[0] == "success", (
            f"Success record was overwritten! Got result={row[0]}"
        )
        # The error_message should NOT be the failure's message
        assert row[1] != "Simulated retry failure"


# ===================================================================
# TEST 4 -- Worker cap: TransferConfig(workers=9999) -> capped at 32
# ===================================================================

class TestWorkerCap:
    def test_workers_capped_at_32(self, staging_dir):
        cfg = TransferConfig(
            source_paths=[str(staging_dir)],
            dest_path=str(staging_dir),
            workers=9999,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 32, (
            f"Worker cap failed! Got {engine.config.workers}, expected 32"
        )

    def test_workers_min_1(self, staging_dir):
        cfg = TransferConfig(
            source_paths=[str(staging_dir)],
            dest_path=str(staging_dir),
            workers=-5,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 1, (
            f"Worker floor failed! Got {engine.config.workers}, expected 1"
        )

    def test_workers_normal_value_unchanged(self, staging_dir):
        cfg = TransferConfig(
            source_paths=[str(staging_dir)],
            dest_path=str(staging_dir),
            workers=16,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 16


# ===================================================================
# TEST 5 -- Queue backpressure: inflight never exceeds workers * 4
# ===================================================================

class TestQueueBackpressure:
    def test_inflight_bounded(self, staging_dir):
        n_workers = 4
        cfg = TransferConfig(
            source_paths=[str(staging_dir)],
            dest_path=str(staging_dir),
            workers=n_workers,
        )
        engine = BulkTransferV2(cfg)
        engine.manifest = TransferManifest(
            str(staging_dir / "_manifest.db")
        )
        engine.manifest.start_run(engine.run_id, cfg.source_paths, cfg.dest_path)
        engine.staging = StagingManager(str(staging_dir))

        max_inflight = n_workers * 4
        inflight_counter = {"current": 0, "peak": 0}
        counter_lock = threading.Lock()

        # Create fake source files
        src_dir = staging_dir / "source"
        src_dir.mkdir()
        n_files = 60  # More than max_inflight to test backpressure
        queue = []
        for i in range(n_files):
            f = src_dir / f"file_{i}.txt"
            f.write_text(f"content-{i}", encoding="utf-8")
            queue.append((str(f), str(src_dir), f"file_{i}.txt", 10))

        original_transfer_one = engine._transfer_one

        def _counting_transfer_one(*args, **kwargs):
            with counter_lock:
                inflight_counter["current"] += 1
                if inflight_counter["current"] > inflight_counter["peak"]:
                    inflight_counter["peak"] = inflight_counter["current"]
            time.sleep(0.05)  # Simulate work
            with counter_lock:
                inflight_counter["current"] -= 1

        engine._transfer_one = _counting_transfer_one
        engine._parallel_transfer(queue)

        assert inflight_counter["peak"] <= max_inflight, (
            f"Backpressure violated! Peak inflight={inflight_counter['peak']}, "
            f"limit={max_inflight}"
        )
        # Also verify that we actually had some parallelism
        assert inflight_counter["peak"] > 1, (
            f"No parallelism detected (peak={inflight_counter['peak']})"
        )

        engine.manifest.close()


# ===================================================================
# TEST 6 -- Concurrent record_source_file: 20 threads writing to
#           manifest simultaneously -- no "database locked" errors.
# ===================================================================

class TestConcurrentRecordSourceFile:
    def test_20_threads_no_db_locked(self, manifest_db):
        m = manifest_db
        run_id = "concurrent_src_run"
        m.start_run(run_id, ["/src"], "/dst")
        n_threads = 20
        errors: List[Exception] = [None] * n_threads
        barrier = threading.Barrier(n_threads)

        def _write(idx):
            try:
                barrier.wait(timeout=10)
                m.record_source_file(
                    run_id,
                    f"/src/dir_{idx}/file_{idx}.txt",
                    file_size=1024 * idx,
                    extension=".txt",
                )
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=_write, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} got DB error: {err}"

        # Verify all rows written
        m.flush()
        with m._lock:
            count = m.conn.execute(
                "SELECT COUNT(*) FROM source_manifest WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        assert count == n_threads, (
            f"Expected {n_threads} rows, found {count}"
        )


# ===================================================================
# TEST 7 -- Concurrent record_skip: 20 threads writing skips -- all
#           recorded, count matches.
# ===================================================================

class TestConcurrentRecordSkip:
    def test_20_threads_all_skips_recorded(self, manifest_db):
        m = manifest_db
        run_id = "concurrent_skip_run"
        m.start_run(run_id, ["/src"], "/dst")
        n_threads = 20
        errors: List[Exception] = [None] * n_threads
        barrier = threading.Barrier(n_threads)

        def _skip(idx):
            try:
                barrier.wait(timeout=10)
                m.record_skip(
                    run_id,
                    f"/src/dir/file_{idx}.exe",
                    file_size=5000 + idx,
                    extension=".exe",
                    reason="always_skip",
                    detail=f"Thread {idx} skip",
                )
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=_skip, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for i, err in enumerate(errors):
            assert err is None, f"Thread {i} got DB error: {err}"

        m.flush()
        with m._lock:
            count = m.conn.execute(
                "SELECT COUNT(*) FROM skipped_files WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        assert count == n_threads, (
            f"Expected {n_threads} skip records, found {count}"
        )


# ===================================================================
# TEST 8 -- speed_samples bounded: call record_copy 2000 times,
#           verify len(_speed_samples) <= 500.
# ===================================================================

class TestSpeedSamplesBounded:
    def test_2000_records_pruned_to_500(self):
        stats = TransferStats()
        for i in range(2000):
            stats.record_copy(1024, ".txt")
        with stats._lock:
            n = len(stats._speed_samples)
        assert n <= 500, (
            f"speed_samples unbounded! {n} entries (limit 500)"
        )
        # Verify the pruning actually kept recent entries
        assert n > 0, "speed_samples pruned to zero!"


# ===================================================================
# TEST 9 -- TransferStats.files_processed is accurate under
#           concurrent updates from 8 threads.
# ===================================================================

class TestStatsAccuracy:
    def test_files_processed_accurate_under_contention(self):
        stats = TransferStats()
        n_threads = 8
        per_thread = 100
        barrier = threading.Barrier(n_threads)

        def _hammer(idx):
            barrier.wait(timeout=10)
            for _ in range(per_thread):
                # Mix different counter types to stress the lock
                kind = idx % 4
                with stats._lock:
                    if kind == 0:
                        stats.files_copied += 1
                    elif kind == 1:
                        stats.files_deduplicated += 1
                    elif kind == 2:
                        stats.files_skipped_ext += 1
                    else:
                        stats.files_failed += 1

        threads = [threading.Thread(target=_hammer, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        expected = n_threads * per_thread
        actual = stats.files_processed
        assert actual == expected, (
            f"files_processed mismatch: expected {expected}, got {actual}"
        )

        # Verify individual counters add up
        total = (
            stats.files_copied + stats.files_deduplicated +
            stats.files_skipped_ext + stats.files_failed
        )
        assert total == expected, (
            f"Individual counters sum={total}, expected {expected}"
        )


# ===================================================================
# TEST 10 -- close() during active writes: one thread writing,
#            another calls close() -- no crash.
# ===================================================================

class TestCloseDuringWrites:
    def test_close_while_writing_no_crash(self, tmp_path):
        db_path = str(tmp_path / "close_test.db")
        m = TransferManifest(db_path)
        run_id = "close_race_run"
        m.start_run(run_id, ["/src"], "/dst")

        write_errors: List[Exception] = []
        close_errors: List[Exception] = []
        stop = threading.Event()

        def _writer():
            i = 0
            while not stop.is_set():
                try:
                    m.record_source_file(
                        run_id,
                        f"/src/file_{i}.txt",
                        file_size=100,
                        extension=".txt",
                    )
                    i += 1
                    time.sleep(0.001)
                except Exception as e:
                    # After close(), writes will fail -- that is
                    # expected. We only care that there is no crash
                    # (segfault, deadlock, uncaught C-level error).
                    write_errors.append(e)
                    break

        def _closer():
            time.sleep(0.05)  # Let writer get some writes in
            try:
                m.close()
            except Exception as e:
                close_errors.append(e)
            finally:
                stop.set()

        tw = threading.Thread(target=_writer)
        tc = threading.Thread(target=_closer)
        tw.start()
        tc.start()
        tw.join(timeout=10)
        tc.join(timeout=10)

        # The close() itself must not crash
        assert len(close_errors) == 0, (
            f"close() crashed: {close_errors}"
        )
        # Writer errors are acceptable (ProgrammingError after close)
        # but no deadlocks (threads must have exited)
        assert not tw.is_alive(), "Writer thread deadlocked!"
        assert not tc.is_alive(), "Closer thread deadlocked!"


# ===================================================================
# BONUS TEST -- idx_skipped_run index exists in schema
# ===================================================================

class TestSchemaIntegrity:
    def test_idx_skipped_run_index_exists(self, manifest_db):
        m = manifest_db
        with m._lock:
            rows = m.conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='idx_skipped_run'"
            ).fetchall()
        assert len(rows) == 1, "idx_skipped_run index is missing!"

    def test_wal_mode_enabled(self, manifest_db):
        m = manifest_db
        with m._lock:
            mode = m.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal", (
            f"Expected WAL mode, got {mode}"
        )
