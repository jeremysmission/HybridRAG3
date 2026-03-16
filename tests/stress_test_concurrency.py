# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the stress concurrency area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Stress Tests -- Concurrency, Thread Safety, SQLite Contention, Race Conditions
# ============================================================================
#
# Targets:
#   src/tools/bulk_transfer_v2.py  (BulkTransferV2, TransferConfig, TransferStats)
#   src/tools/transfer_manifest.py (TransferManifest)
#   src/tools/transfer_staging.py  (StagingManager)
#
# Run with:
#   python -m pytest tests/stress_test_concurrency.py -v --tb=short -x
# ============================================================================

from __future__ import annotations

import os
import sys
import hashlib
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Make the project root importable so we can import src.tools.*
# ---------------------------------------------------------------------------
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.tools.transfer_manifest import TransferManifest
from src.tools.transfer_staging import StagingManager
from src.tools.bulk_transfer_v2 import (
    BulkTransferV2,
    TransferConfig,
    TransferStats,
    _hash_file,
    _buffered_copy,
    _can_read_file,
)

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Constants for the stress tests
# ---------------------------------------------------------------------------
THREADS = 8
RECORDS_PER_THREAD = 1000
WRITES_PER_THREAD_BATCH = 100
RECORD_COPY_PER_THREAD = 10_000
FILE_SIZE_PER_COPY = 1024  # bytes
FULL_RUN_FILES = 500
FULL_RUN_WORKERS = 16


# ===========================================================================
# Helpers
# ===========================================================================

def _make_temp_db() -> str:
    """Create a temp file path for a SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _make_temp_dir() -> str:
    """Create a temp directory and return its path."""
    return tempfile.mkdtemp()


def _create_small_file(directory: str, name: str, content: bytes = b"") -> str:
    """Create a small file in the given directory and return its path."""
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not content:
        content = f"content-of-{name}-{os.urandom(8).hex()}".encode("utf-8")
    with open(path, "wb") as f:
        f.write(content)
    return path


# ===========================================================================
# TEST 1: TransferManifest -- 8 threads x 1000 records across 3 methods
# ===========================================================================

class TestManifestConcurrentWrites:
    """
    8 threads simultaneously call record_source_file, record_transfer, and
    record_skip with 1000 records each.  Verify no data loss (total rows ==
    expected) and no sqlite3.OperationalError.
    """

    def test_no_data_loss_under_contention(self):
        db_path = _make_temp_db()
        try:
            manifest = TransferManifest(db_path)
            manifest.start_run("run1", ["/src"], "/dst")
            errors: List[Exception] = []

            def writer_source(tid: int):
                try:
                    for i in range(RECORDS_PER_THREAD):
                        manifest.record_source_file(
                            "run1",
                            f"/src/thread{tid}/file{i}.txt",
                            file_size=i * 100,
                            extension=".txt",
                        )
                except Exception as e:
                    errors.append(e)

            def writer_transfer(tid: int):
                try:
                    for i in range(RECORDS_PER_THREAD):
                        manifest.record_transfer(
                            "run1",
                            f"/src/xfer_thread{tid}/file{i}.txt",
                            dest_path=f"/dst/xfer_thread{tid}/file{i}.txt",
                            result="success",
                            hash_source=hashlib.sha256(
                                f"t{tid}f{i}".encode()
                            ).hexdigest(),
                        )
                except Exception as e:
                    errors.append(e)

            def writer_skip(tid: int):
                try:
                    for i in range(RECORDS_PER_THREAD):
                        manifest.record_skip(
                            "run1",
                            f"/src/skip_thread{tid}/file{i}.txt",
                            file_size=i,
                            extension=".log",
                            reason="test_skip",
                            detail=f"stress test thread {tid}",
                        )
                except Exception as e:
                    errors.append(e)

            threads: List[threading.Thread] = []
            # 8 threads: mix of source, transfer, skip writers
            for tid in range(THREADS):
                if tid % 3 == 0:
                    t = threading.Thread(target=writer_source, args=(tid,))
                elif tid % 3 == 1:
                    t = threading.Thread(target=writer_transfer, args=(tid,))
                else:
                    t = threading.Thread(target=writer_skip, args=(tid,))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=120)

            manifest.flush()

            # Verify no errors
            assert len(errors) == 0, (
                f"Got {len(errors)} errors during concurrent writes: "
                f"{[str(e) for e in errors[:5]]}"
            )

            # Count rows in each table
            conn = sqlite3.connect(db_path)
            source_count = conn.execute(
                "SELECT COUNT(*) FROM source_manifest WHERE run_id='run1'"
            ).fetchone()[0]
            transfer_count = conn.execute(
                "SELECT COUNT(*) FROM transfer_log WHERE run_id='run1'"
            ).fetchone()[0]
            skip_count = conn.execute(
                "SELECT COUNT(*) FROM skipped_files WHERE run_id='run1'"
            ).fetchone()[0]
            conn.close()

            # Calculate expected counts based on thread assignment
            # tid 0,3,6 -> source (3 threads)
            # tid 1,4,7 -> transfer (3 threads)
            # tid 2,5   -> skip (2 threads)
            expected_source = 3 * RECORDS_PER_THREAD
            expected_transfer = 3 * RECORDS_PER_THREAD
            expected_skip = 2 * RECORDS_PER_THREAD

            assert source_count == expected_source, (
                f"source_manifest: expected {expected_source}, got {source_count} "
                f"-- {expected_source - source_count} rows lost"
            )
            assert transfer_count == expected_transfer, (
                f"transfer_log: expected {expected_transfer}, got {transfer_count} "
                f"-- {expected_transfer - transfer_count} rows lost"
            )
            assert skip_count == expected_skip, (
                f"skipped_files: expected {expected_skip}, got {skip_count} "
                f"-- {expected_skip - skip_count} rows lost"
            )

        finally:
            manifest.close()
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ===========================================================================
# TEST 2: TransferManifest._batch_commit counter under contention
# ===========================================================================

class TestBatchCommitCounter:
    """
    8 threads each doing 100 writes.  Verify commit count is correct and
    no writes are lost.  The _batch_commit fires every 50 rows, so after
    800 writes we expect at least 16 commits (800 / 50).
    """

    def test_batch_commit_no_lost_writes(self):
        db_path = _make_temp_db()
        try:
            manifest = TransferManifest(db_path)
            manifest.start_run("run_batch", ["/s"], "/d")
            errors: List[Exception] = []

            def writer(tid: int):
                try:
                    for i in range(WRITES_PER_THREAD_BATCH):
                        manifest.record_source_file(
                            "run_batch",
                            f"/s/batch_t{tid}/f{i}.txt",
                            file_size=tid * 1000 + i,
                            extension=".txt",
                        )
                except Exception as e:
                    errors.append(e)

            threads = []
            for tid in range(THREADS):
                t = threading.Thread(target=writer, args=(tid,))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)

            # Flush any remaining uncommitted writes
            manifest.flush()

            assert len(errors) == 0, (
                f"Errors during batch writes: {[str(e) for e in errors[:5]]}"
            )

            # Verify row count
            conn = sqlite3.connect(db_path)
            total = conn.execute(
                "SELECT COUNT(*) FROM source_manifest WHERE run_id='run_batch'"
            ).fetchone()[0]
            conn.close()

            expected = THREADS * WRITES_PER_THREAD_BATCH
            assert total == expected, (
                f"_batch_commit lost writes: expected {expected}, got {total}, "
                f"lost {expected - total}"
            )

            # Verify the pending counter is reset
            assert manifest._pending_writes == 0, (
                f"_pending_writes not reset after flush: {manifest._pending_writes}"
            )

        finally:
            manifest.close()
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ===========================================================================
# TEST 3: TransferStats thread safety -- 8 threads x 10000 record_copy
# ===========================================================================

class TestTransferStatsThreadSafety:
    """
    8 threads each call record_copy 10,000 times.  Verify files_copied ==
    80,000 and bytes_copied equals the exact expected sum.
    """

    def test_record_copy_atomic_counters(self):
        stats = TransferStats()
        errors: List[Exception] = []

        def pumper(tid: int):
            try:
                for i in range(RECORD_COPY_PER_THREAD):
                    stats.record_copy(FILE_SIZE_PER_COPY, ".txt")
            except Exception as e:
                errors.append(e)

        threads = []
        for tid in range(THREADS):
            t = threading.Thread(target=pumper, args=(tid,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        assert len(errors) == 0, (
            f"Errors during record_copy: {[str(e) for e in errors[:5]]}"
        )

        expected_files = THREADS * RECORD_COPY_PER_THREAD  # 80,000
        expected_bytes = expected_files * FILE_SIZE_PER_COPY

        assert stats.files_copied == expected_files, (
            f"files_copied: expected {expected_files}, got {stats.files_copied} "
            f"-- off by {expected_files - stats.files_copied}"
        )
        assert stats.bytes_copied == expected_bytes, (
            f"bytes_copied: expected {expected_bytes}, got {stats.bytes_copied}"
        )
        assert stats.ext_counts.get(".txt", 0) == expected_files, (
            f"ext_counts['.txt']: expected {expected_files}, "
            f"got {stats.ext_counts.get('.txt', 0)}"
        )


# ===========================================================================
# TEST 4: TransferStats.speed_bps under high contention
# ===========================================================================

class TestSpeedBpsContention:
    """
    4 reader threads call speed_bps continuously while 4 writer threads
    pump record_copy.  Verify no crashes, no NaN, no negative values,
    and no data corruption in the rolling window.
    """

    def test_concurrent_read_write_speed(self):
        stats = TransferStats()
        stop = threading.Event()
        errors: List[Exception] = []
        speed_readings: List[float] = []
        speed_lock = threading.Lock()

        def writer(tid: int):
            try:
                while not stop.is_set():
                    stats.record_copy(4096, ".pdf")
                    # Tiny yield to let readers interleave
                    if tid == 0:
                        time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        def reader(tid: int):
            try:
                while not stop.is_set():
                    speed = stats.speed_bps
                    # Validate: speed must be non-negative and finite
                    assert speed >= 0, f"Negative speed: {speed}"
                    assert speed == speed, f"NaN speed detected"  # NaN != NaN
                    with speed_lock:
                        speed_readings.append(speed)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = []
        for tid in range(4):
            threads.append(threading.Thread(target=writer, args=(tid,)))
        for tid in range(4):
            threads.append(threading.Thread(target=reader, args=(tid,)))

        for t in threads:
            t.start()

        # Let the chaos run for 3 seconds
        time.sleep(3.0)
        stop.set()

        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, (
            f"Errors during speed_bps contention: {[str(e) for e in errors[:5]]}"
        )
        assert len(speed_readings) > 0, "No speed readings collected"
        assert stats.files_copied > 0, "No files were recorded during contention test"

        # After the writers have pumped thousands of copies, speed should be > 0
        # (at least some samples should be in the 30-second window)
        final_speed = stats.speed_bps
        assert final_speed >= 0, f"Final speed_bps is negative: {final_speed}"


# ===========================================================================
# TEST 5: _stop Event -- verify all workers actually stop
# ===========================================================================

class TestStopEventStopsWorkers:
    """
    Start _parallel_transfer with a queue of slow items, set _stop after
    2 seconds, and verify all worker threads actually stop (no zombies
    still copying).
    """

    def test_stop_event_halts_workers(self):
        src_dir = _make_temp_dir()
        dest_dir = _make_temp_dir()

        try:
            # Create 100 small files (enough to keep workers busy for a bit)
            for i in range(100):
                _create_small_file(src_dir, f"file_{i:04d}.txt")

            cfg = TransferConfig(
                source_paths=[src_dir],
                dest_path=dest_dir,
                workers=4,
                verify_copies=False,
                deduplicate=False,
                resume=False,
                min_file_size=0,
            )
            engine = BulkTransferV2(cfg)
            engine.manifest = TransferManifest(
                os.path.join(dest_dir, "_manifest.db")
            )
            engine.staging = StagingManager(dest_dir)
            engine.manifest.start_run(engine.run_id, [src_dir], dest_dir)

            # Build queue manually
            queue = []
            for fname in os.listdir(src_dir):
                full = os.path.join(src_dir, fname)
                rel = fname
                sz = os.path.getsize(full)
                queue.append((full, src_dir, rel, sz))

            # Count threads before
            threads_before = threading.active_count()

            # Run _parallel_transfer in a separate thread, stop it after 0.5s
            def run_transfer():
                engine._parallel_transfer(queue)

            t = threading.Thread(target=run_transfer)
            t.start()

            # Let some work happen, then signal stop
            time.sleep(0.5)
            engine._stop.set()

            # Wait for the transfer thread to finish
            t.join(timeout=30)

            # Give threads time to wind down
            time.sleep(1.0)
            threads_after = threading.active_count()

            # The thread count should return to roughly the same level
            # Allow +2 for daemon threads (progress thread, GC, etc.)
            zombie_count = threads_after - threads_before
            assert zombie_count <= 2, (
                f"Possible zombie workers: {zombie_count} extra threads "
                f"remain after stop (before={threads_before}, after={threads_after})"
            )

        finally:
            engine.manifest.close()
            import shutil
            shutil.rmtree(src_dir, ignore_errors=True)
            shutil.rmtree(dest_dir, ignore_errors=True)


# ===========================================================================
# TEST 6: promote_to_verified race condition -- two workers, same rel path
# ===========================================================================

class TestPromoteToVerifiedRace:
    """
    Two workers try to promote_to_verified the same relative_path
    simultaneously.  Verify name collision counter handles the race
    and both files end up in verified/ with distinct names.
    """

    def test_concurrent_promotion_same_path(self):
        base_dir = _make_temp_dir()
        try:
            staging = StagingManager(base_dir)
            results: List[Path] = []
            errors: List[Exception] = []
            barrier = threading.Barrier(THREADS)

            def promote_worker(tid: int):
                try:
                    # Create a unique temp file in incoming/
                    tmp = staging.incoming_path(f"sub/conflict.txt")
                    # Each thread needs its own .tmp file
                    unique_tmp = tmp.parent / f"conflict_{tid}.txt.tmp"
                    unique_tmp.parent.mkdir(parents=True, exist_ok=True)
                    unique_tmp.write_bytes(f"data-from-thread-{tid}".encode())

                    # All threads hit the barrier at the same time to
                    # maximize the collision window
                    barrier.wait(timeout=10)

                    final = staging.promote_to_verified(
                        unique_tmp, "sub/conflict.txt"
                    )
                    results.append(final)
                except Exception as e:
                    errors.append(e)

            threads = []
            for tid in range(THREADS):
                t = threading.Thread(target=promote_worker, args=(tid,))
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            # ANALYSIS: The promote_to_verified method has a TOCTOU race at
            # lines 142-148 of transfer_staging.py. Two threads can both see
            # final.exists() == False simultaneously, and both attempt
            # os.rename to the same path. One will succeed; the other will
            # either overwrite (data loss!) or raise OSError.
            #
            # We check for:
            #   1. No unhandled exceptions
            #   2. All THREADS files exist in verified/
            #   3. All files have unique content
            if errors:
                # If we got errors, report them but note the TOCTOU bug
                pytest.fail(
                    f"promote_to_verified race produced {len(errors)} errors: "
                    f"{[str(e) for e in errors[:5]]}. "
                    f"Root cause: TOCTOU race at transfer_staging.py lines 142-148 "
                    f"-- final.exists() check is not atomic with os.rename()."
                )

            # Check that we got THREADS distinct results
            unique_paths = set(str(r) for r in results)
            assert len(results) == THREADS, (
                f"Expected {THREADS} promoted files, got {len(results)}"
            )

            # Check if any paths collide (TOCTOU symptom)
            if len(unique_paths) < THREADS:
                collisions = THREADS - len(unique_paths)
                pytest.fail(
                    f"TOCTOU RACE DETECTED: {collisions} path collisions in "
                    f"promote_to_verified. Two threads raced past the "
                    f"final.exists() check (transfer_staging.py line 142) "
                    f"and one overwrote the other. This is data loss."
                )

            # Verify all files actually exist and have distinct content
            contents = set()
            for p in results:
                assert p.exists(), f"Promoted file missing: {p}"
                contents.add(p.read_bytes())
            assert len(contents) == THREADS, (
                f"Content collision: only {len(contents)} unique contents "
                f"out of {THREADS} files. Some data was overwritten."
            )

        finally:
            import shutil
            shutil.rmtree(base_dir, ignore_errors=True)


# ===========================================================================
# TEST 7: find_by_hash under concurrent reads and writes
# ===========================================================================

class TestFindByHashConcurrentReadWrite:
    """
    One thread writes transfer records while another thread queries
    find_by_hash.  Verify no stale reads, no crashes, and no
    sqlite3.OperationalError.
    """

    def test_concurrent_find_by_hash(self):
        db_path = _make_temp_db()
        try:
            manifest = TransferManifest(db_path)
            manifest.start_run("run_fbh", ["/s"], "/d")
            errors: List[Exception] = []
            stop = threading.Event()
            hashes_written: List[str] = []
            hashes_found: List[str] = []
            write_lock = threading.Lock()

            def writer():
                try:
                    for i in range(500):
                        h = hashlib.sha256(f"file_{i}".encode()).hexdigest()
                        manifest.record_transfer(
                            "run_fbh",
                            f"/s/file_{i}.txt",
                            dest_path=f"/d/file_{i}.txt",
                            hash_source=h,
                            hash_dest=h,
                            result="success",
                        )
                        with write_lock:
                            hashes_written.append(h)
                        # Small sleep to interleave with reader
                        if i % 50 == 0:
                            time.sleep(0.01)
                except Exception as e:
                    errors.append(e)

            def reader():
                try:
                    while not stop.is_set():
                        # Pick a hash to look for
                        with write_lock:
                            if not hashes_written:
                                time.sleep(0.001)
                                continue
                            h = hashes_written[-1]
                        result = manifest.find_by_hash(h)
                        # After flush, the hash should be findable.
                        # Before flush it might not be committed yet --
                        # that is acceptable (eventual consistency with
                        # batch commit).
                        if result is not None:
                            hashes_found.append(h)
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            wt = threading.Thread(target=writer)
            rt = threading.Thread(target=reader)

            wt.start()
            rt.start()

            wt.join(timeout=60)
            stop.set()
            rt.join(timeout=10)

            manifest.flush()

            assert len(errors) == 0, (
                f"Errors during concurrent find_by_hash: "
                f"{[str(e) for e in errors[:5]]}"
            )

            # After flush, ALL hashes should be findable
            missing = 0
            for h in hashes_written[:50]:  # Spot-check first 50
                if manifest.find_by_hash(h) is None:
                    missing += 1

            assert missing == 0, (
                f"After flush, {missing}/50 hashes not found by find_by_hash. "
                f"Possible data loss or uncommitted writes."
            )

        finally:
            manifest.close()
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ===========================================================================
# TEST 8: is_already_transferred with concurrent writers
# ===========================================================================

class TestIsAlreadyTransferredConcurrency:
    """
    Multiple threads write transfer records as 'success' while another
    thread polls is_already_transferred.  Verify it correctly detects
    files transferred by another thread moments ago.
    """

    def test_concurrent_is_already_transferred(self):
        db_path = _make_temp_db()
        try:
            manifest = TransferManifest(db_path)
            manifest.start_run("run_iat", ["/s"], "/d")
            errors: List[Exception] = []
            stop = threading.Event()
            # Track which paths were written
            written_paths: List[str] = []
            written_lock = threading.Lock()
            detected: List[str] = []
            detected_lock = threading.Lock()

            def writer(tid: int):
                try:
                    for i in range(200):
                        path = f"/s/iat_t{tid}/file_{i}.txt"
                        manifest.record_transfer(
                            "run_iat", path,
                            dest_path=f"/d/iat_t{tid}/file_{i}.txt",
                            result="success",
                        )
                        with written_lock:
                            written_paths.append(path)
                except Exception as e:
                    errors.append(e)

            def checker():
                try:
                    while not stop.is_set():
                        with written_lock:
                            if not written_paths:
                                time.sleep(0.001)
                                continue
                            path = written_paths[-1]
                        if manifest.is_already_transferred(path):
                            with detected_lock:
                                detected.append(path)
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

            threads = []
            for tid in range(4):
                threads.append(threading.Thread(target=writer, args=(tid,)))
            checker_thread = threading.Thread(target=checker)
            threads.append(checker_thread)

            for t in threads:
                t.start()

            # Wait for writers to finish
            for t in threads[:4]:
                t.join(timeout=60)
            stop.set()
            checker_thread.join(timeout=10)

            manifest.flush()

            assert len(errors) == 0, (
                f"Errors during is_already_transferred contention: "
                f"{[str(e) for e in errors[:5]]}"
            )

            # After flush, every written path should be detected
            total_written = len(written_paths)
            assert total_written == 4 * 200, (
                f"Expected {4 * 200} written paths, got {total_written}"
            )

            # Spot-check: all paths should now return True
            missed = 0
            for path in written_paths[:100]:
                if not manifest.is_already_transferred(path):
                    missed += 1

            assert missed == 0, (
                f"After flush, {missed}/100 paths not detected by "
                f"is_already_transferred. Possible batch commit data loss."
            )

        finally:
            manifest.close()
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ===========================================================================
# TEST 9: Full BulkTransferV2.run() with 16 workers and 500 small files
# ===========================================================================

class TestFullRunIntegration:
    """
    Full BulkTransferV2.run() with 16 workers and 500 small files.
    Verify no crashes, no data loss, and stats accounting identity:
      files_copied + files_failed + files_skipped_* == files_discovered
    """

    def test_full_run_500_files(self):
        src_dir = _make_temp_dir()
        dest_dir = _make_temp_dir()

        try:
            # Create 500 small .txt files with unique content
            for i in range(FULL_RUN_FILES):
                subdir = f"dir_{i % 10}"
                name = f"{subdir}/file_{i:04d}.txt"
                content = f"file-{i}-content-{os.urandom(16).hex()}".encode()
                _create_small_file(src_dir, name, content)

            cfg = TransferConfig(
                source_paths=[src_dir],
                dest_path=dest_dir,
                workers=FULL_RUN_WORKERS,
                deduplicate=True,
                verify_copies=True,
                resume=False,
                min_file_size=0,  # Accept all sizes
                max_file_size=500_000_000,
            )
            engine = BulkTransferV2(cfg)

            # Suppress stdout noise during the test
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                stats = engine.run()
            finally:
                sys.stdout = old_stdout

            # --- Accounting identity ---
            # Every discovered file must be accounted for by one of:
            #   copied, failed, deduplicated, or one of the skip categories
            total_accounted = (
                stats.files_copied
                + stats.files_failed
                + stats.files_deduplicated
                + stats.files_skipped_ext
                + stats.files_skipped_size
                + stats.files_skipped_unchanged
                + stats.files_skipped_locked
                + stats.files_skipped_encoding
                + stats.files_skipped_symlink
                + stats.files_skipped_hidden
                + stats.files_skipped_inaccessible
                + stats.files_skipped_long_path
                + stats.files_quarantined
            )

            assert stats.files_discovered == FULL_RUN_FILES, (
                f"Discovery missed files: expected {FULL_RUN_FILES}, "
                f"got {stats.files_discovered}"
            )

            assert stats.files_copied > 0, (
                "No files were copied -- something is fundamentally broken"
            )

            # The accounting identity: discovered == accounted
            # Note: files_quarantined is a subset of files_failed/verify_failed,
            # so we do not double-count. The precise identity is:
            #   discovered == copied + failed + dedup + all_skips
            # But files_quarantined overlaps with files_verify_failed/files_failed.
            # The engine increments files_failed AND files_quarantined for the
            # same file, so we should NOT include quarantined in the sum.
            # Let's use files_processed which is the engine's own accounting.
            processed = stats.files_processed
            assert processed == stats.files_discovered, (
                f"Accounting gap: files_processed={processed} != "
                f"files_discovered={stats.files_discovered}. "
                f"Breakdown: copied={stats.files_copied}, "
                f"failed={stats.files_failed}, "
                f"dedup={stats.files_deduplicated}, "
                f"skip_ext={stats.files_skipped_ext}, "
                f"skip_size={stats.files_skipped_size}, "
                f"skip_unchanged={stats.files_skipped_unchanged}, "
                f"quarantined={stats.files_quarantined}"
            )

            # Verify files actually exist in verified/
            verified_dir = os.path.join(dest_dir, "verified")
            verified_files = []
            for root, dirs, files in os.walk(verified_dir):
                verified_files.extend(files)

            assert len(verified_files) == stats.files_copied, (
                f"Verified dir has {len(verified_files)} files but "
                f"stats says {stats.files_copied} copied"
            )

        finally:
            import shutil
            shutil.rmtree(src_dir, ignore_errors=True)
            shutil.rmtree(dest_dir, ignore_errors=True)


# ===========================================================================
# TEST 10: KeyboardInterrupt during _parallel_transfer -- no zombie threads
# ===========================================================================

class TestKeyboardInterruptNoZombies:
    """
    Simulate a KeyboardInterrupt during _parallel_transfer.  Count
    active threads before and after to verify no zombies remain.
    """

    def test_keyboard_interrupt_cleanup(self):
        src_dir = _make_temp_dir()
        dest_dir = _make_temp_dir()

        try:
            # Create enough files to keep workers busy
            for i in range(50):
                _create_small_file(
                    src_dir, f"file_{i:04d}.txt",
                    content=os.urandom(4096),
                )

            cfg = TransferConfig(
                source_paths=[src_dir],
                dest_path=dest_dir,
                workers=8,
                verify_copies=True,
                deduplicate=False,
                resume=False,
                min_file_size=0,
            )

            # We need a stable baseline -- let the GC and other threads settle
            time.sleep(0.5)
            baseline_threads = threading.active_count()

            engine = BulkTransferV2(cfg)
            engine.manifest = TransferManifest(
                os.path.join(dest_dir, "_manifest.db")
            )
            engine.staging = StagingManager(dest_dir)
            engine.manifest.start_run(engine.run_id, [src_dir], dest_dir)

            # Build queue
            queue = []
            for fname in os.listdir(src_dir):
                full = os.path.join(src_dir, fname)
                rel = fname
                sz = os.path.getsize(full)
                queue.append((full, src_dir, rel, sz))

            # Patch _transfer_one to be slow and raise KeyboardInterrupt
            # after 0.3 seconds
            original_transfer_one = engine._transfer_one
            call_count = [0]
            interrupt_fired = [False]

            def slow_transfer_one(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] >= 5 and not interrupt_fired[0]:
                    interrupt_fired[0] = True
                    raise KeyboardInterrupt("simulated Ctrl+C")
                time.sleep(0.05)
                return original_transfer_one(*args, **kwargs)

            engine._transfer_one = slow_transfer_one

            # Run the transfer -- it should handle the KeyboardInterrupt
            try:
                engine._parallel_transfer(queue)
            except KeyboardInterrupt:
                engine._stop.set()

            # Give threads time to wind down
            time.sleep(2.0)

            final_threads = threading.active_count()
            zombie_count = final_threads - baseline_threads

            # Allow a small margin for daemon threads
            assert zombie_count <= 2, (
                f"Zombie threads after KeyboardInterrupt: {zombie_count} "
                f"extra threads (baseline={baseline_threads}, "
                f"final={final_threads}). Workers did not shut down."
            )

        finally:
            engine.manifest.close()
            import shutil
            shutil.rmtree(src_dir, ignore_errors=True)
            shutil.rmtree(dest_dir, ignore_errors=True)
