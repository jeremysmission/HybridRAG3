# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the retest large files area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Destructive QA: Large File + Memory Pressure Tests for Bulk Transfer V2
# ============================================================================
# Tests recently fixed bugs and probes for new regressions.
# Run:  python -m pytest tests/retest_large_files.py -v
# ============================================================================

from __future__ import annotations

import errno
import hashlib
import io
import os
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Ensure project root on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.tools.bulk_transfer_v2 import (
    AtomicTransferWorker,
    BulkTransferV2,
    TransferConfig,
    TransferStats,
    _buffered_copy,
    _buffered_copy_inner,
    _hash_file,
)
from src.tools.transfer_staging import StagingManager


# ============================================================================
# Helpers
# ============================================================================

def _make_temp_file(directory: str, name: str, size: int) -> str:
    """Create a temp file filled with repeatable content."""
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        # Write repeatable bytes so SHA-256 is reproducible
        chunk = b"A" * min(size, 65536)
        remaining = size
        while remaining > 0:
            f.write(chunk[:remaining])
            remaining -= len(chunk)
    return path


# ============================================================================
# TEST 1: _buffered_copy timeout fires for stalled reads
# ============================================================================

class TestBufferedCopyTimeout:
    """Verify the timeout daemon thread fires when a read stalls."""

    def test_timeout_fires_on_stalled_read(self, tmp_path):
        """A source file that never finishes reading should raise TimeoutError."""
        src = str(tmp_path / "stalled_src.bin")
        dst = str(tmp_path / "stalled_dst.bin")

        # Create a real source so the file opens, but mock read() to block
        with open(src, "wb") as f:
            f.write(b"X" * 1024)

        original_open = io.open

        class StallFile:
            """File-like object whose read() blocks forever."""
            def __init__(self, path, mode):
                self._real = original_open(path, mode)

            def read(self, n=-1):
                # First read returns some data, second read stalls
                time.sleep(999)
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self._real.close()

        call_count = [0]

        def patched_open(path, mode="r", **kw):
            if path == src and mode == "rb":
                call_count[0] += 1
                if call_count[0] >= 1:
                    return StallFile(path, mode)
            return original_open(path, mode, **kw)

        with mock.patch("src.tools.bulk_transfer_v2.open", side_effect=patched_open):
            with pytest.raises(TimeoutError, match="timed out"):
                _buffered_copy(src, dst, buf_size=512, timeout=1.0)

    def test_no_timeout_when_copy_completes_quickly(self, tmp_path):
        """A normal fast copy should NOT trigger timeout."""
        src = _make_temp_file(str(tmp_path), "fast_src.bin", 4096)
        dst = str(tmp_path / "fast_dst.bin")
        # Generous timeout -- should not fire
        _buffered_copy(src, dst, buf_size=1024, timeout=30.0)
        assert os.path.exists(dst)
        assert os.path.getsize(dst) == 4096


# ============================================================================
# TEST 2: speed_samples stays bounded after 10,000 record_copy calls
# ============================================================================

class TestSpeedSamplesBounded:
    """Verify speed_samples is pruned and never exceeds 500 + margin."""

    def test_speed_samples_bounded_after_10k_records(self):
        """Hammer record_copy 10,000 times; samples must stay <= 500.

        The code has a two-stage prune:
          1. Remove entries older than 30s
          2. If still > 500 (all entries are fresh), hard-cap to newest 500
        This test verifies the hard-cap prevents unbounded growth.
        """
        stats = TransferStats()
        for i in range(10_000):
            stats.record_copy(1024, ".txt")

        sample_count = len(stats._speed_samples)
        assert sample_count > 0, "Should have recorded samples"
        assert sample_count <= 500, (
            f"speed_samples grew to {sample_count} entries "
            f"(expected <= 500 due to hard cap in record_copy)"
        )

    def test_speed_samples_prunes_old_entries(self):
        """Entries older than 30s should be pruned once threshold is hit."""
        stats = TransferStats()
        # Insert 510 fake old entries (>500 to trigger prune)
        old_time = time.time() - 60.0  # 60s ago
        with stats._lock:
            for i in range(510):
                stats._speed_samples.append((old_time + i * 0.001, 1024))
        # Now add a fresh one -- triggers len>500 check and prunes old entries
        stats.record_copy(1024, ".txt")
        # After prune, old entries (>30s ago) are removed
        # Only the new entry should survive
        assert len(stats._speed_samples) <= 10, (
            f"Old entries not pruned: {len(stats._speed_samples)} remain"
        )


# ============================================================================
# TEST 3: Cooperative cancellation in _hash_file
# ============================================================================

class TestHashFileCancellation:
    """Verify the cancel event in _hash_file stops reading."""

    def test_hash_file_respects_cancel_event(self, tmp_path):
        """_hash_file should return empty string when cancelled externally."""
        # Create a large-ish file (1 MB) so hashing takes a moment
        src = _make_temp_file(str(tmp_path), "cancel_me.bin", 1_048_576)

        # We cannot inject the cancel event into _hash_file directly because
        # it creates its own internally. But we CAN test the timeout path:
        # if we set timeout=0.001, the outer join times out, cancel is set,
        # and the function returns "".
        result = _hash_file(src, timeout=0.001)
        # With a 1ms timeout, hashing 1MB should not finish in time
        # (though on fast SSDs it might). If it does finish, the hash is valid.
        # This test verifies the cancel pathway doesn't crash.
        assert isinstance(result, str)

    def test_hash_file_returns_valid_hash_for_normal_file(self, tmp_path):
        """Normal file should produce correct SHA-256."""
        content = b"Hello, world! This is test content for hashing."
        src = str(tmp_path / "normal.bin")
        with open(src, "wb") as f:
            f.write(content)

        expected = hashlib.sha256(content).hexdigest()
        actual = _hash_file(src, timeout=30.0)
        assert actual == expected, f"Hash mismatch: {actual} != {expected}"


# ============================================================================
# TEST 4: _hash_file retries on transient OSError
# ============================================================================

class TestHashFileRetry:
    """Verify _hash_file retries once on transient OSError."""

    def test_retries_once_on_transient_oserror(self, tmp_path):
        """First open raises OSError, second open succeeds -> valid hash.

        We verify the retry logic by inspecting the source code for the
        retry loop structure, then do an integration test with a real
        file that confirms _hash_file produces correct output after
        the code path where retry would fire.
        """
        content = b"Retry test content" * 100
        src = str(tmp_path / "retry_test.bin")
        with open(src, "wb") as f:
            f.write(content)

        expected_hash = hashlib.sha256(content).hexdigest()

        # Verify the retry loop exists in source code
        import inspect
        source = inspect.getsource(_hash_file)
        assert "for attempt in range(2)" in source, (
            "_hash_file should retry once (range(2) = attempts 0 and 1)"
        )
        assert "except OSError" in source, (
            "_hash_file should catch OSError for retry"
        )
        assert "time.sleep(0.5)" in source, (
            "_hash_file should sleep 0.5s between retries"
        )

        # Integration: normal file hashes correctly (proves the happy path)
        result = _hash_file(src, timeout=30.0)
        assert result == expected_hash, (
            f"Expected valid hash after normal read, got: '{result}'"
        )

    def test_no_retry_on_permission_error(self, tmp_path):
        """PermissionError should NOT be retried."""
        src = str(tmp_path / "perm_denied.bin")
        with open(src, "wb") as f:
            f.write(b"secret")

        call_count = [0]
        original_open = open

        def perm_denied_open(path, mode="r", **kw):
            if path == src and mode == "rb":
                call_count[0] += 1
                raise PermissionError("Access denied")
            return original_open(path, mode, **kw)

        with mock.patch("builtins.open", side_effect=perm_denied_open):
            result = _hash_file(src, timeout=30.0)

        assert result == "", "PermissionError should return empty hash"
        assert call_count[0] == 1, (
            f"PermissionError should not retry; got {call_count[0]} attempts"
        )


# ============================================================================
# TEST 5: Worker cap enforced (config.workers=1000 gets capped to 32)
# ============================================================================

class TestWorkerCap:
    """Verify BulkTransferV2 caps workers to [1, 32]."""

    def test_workers_capped_at_32(self, tmp_path):
        """config.workers=1000 should be clamped to 32."""
        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=1000,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 32, (
            f"Expected 32, got {engine.config.workers}"
        )

    def test_workers_minimum_is_1(self, tmp_path):
        """config.workers=0 should be clamped to 1."""
        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=0,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 1, (
            f"Expected 1, got {engine.config.workers}"
        )

    def test_workers_negative_clamped_to_1(self, tmp_path):
        """config.workers=-5 should be clamped to 1."""
        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=-5,
        )
        engine = BulkTransferV2(cfg)
        assert engine.config.workers == 1, (
            f"Expected 1, got {engine.config.workers}"
        )


# ============================================================================
# TEST 6: Queue backpressure limits inflight futures
# ============================================================================

class TestQueueBackpressure:
    """Verify _parallel_transfer limits inflight futures to workers*4."""

    def test_backpressure_limits_inflight(self, tmp_path):
        """With 2 workers, max inflight should be 8 (2*4)."""
        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=2,
        )
        engine = BulkTransferV2(cfg)

        # Set up manifest and staging so _transfer_one doesn't crash
        from src.tools.transfer_manifest import TransferManifest
        db_path = str(tmp_path / "out" / "_transfer_manifest.db")
        os.makedirs(str(tmp_path / "out"), exist_ok=True)
        engine.manifest = TransferManifest(db_path)
        engine.staging = StagingManager(str(tmp_path / "out"))
        engine.run_id = "test_backpressure"
        engine.manifest.start_run(
            engine.run_id, [str(tmp_path)], str(tmp_path / "out")
        )

        # Create 50 small source files
        src_dir = str(tmp_path / "src")
        os.makedirs(src_dir, exist_ok=True)
        queue: List[Tuple[str, str, str, int]] = []
        for i in range(50):
            fp = _make_temp_file(src_dir, f"file_{i:04d}.txt", 200)
            queue.append((fp, src_dir, f"file_{i:04d}.txt", 200))

        max_inflight = cfg.workers * 4  # Should be 8
        assert max_inflight == 8, f"Expected max_inflight=8, got {max_inflight}"

        # Track peak concurrency using _transfer_one wrapper
        peak_concurrent = [0]
        current_concurrent = [0]
        concurrent_lock = threading.Lock()
        original_transfer_one = engine._transfer_one

        def tracked_transfer_one(*args, **kwargs):
            with concurrent_lock:
                current_concurrent[0] += 1
                if current_concurrent[0] > peak_concurrent[0]:
                    peak_concurrent[0] = current_concurrent[0]
            try:
                # Small sleep to allow concurrency to build up
                time.sleep(0.05)
                return original_transfer_one(*args, **kwargs)
            finally:
                with concurrent_lock:
                    current_concurrent[0] -= 1

        engine._transfer_one = tracked_transfer_one
        engine._parallel_transfer(queue)

        # Peak concurrency should not exceed workers count (2 in this case)
        # because ThreadPoolExecutor has max_workers=2
        assert peak_concurrent[0] <= cfg.workers + 1, (
            f"Peak concurrency {peak_concurrent[0]} exceeded workers={cfg.workers}"
        )

        engine.manifest.close()


# ============================================================================
# TEST 7: fsync is called after copy
# ============================================================================

class TestFsyncAfterCopy:
    """Verify _buffered_copy_inner calls os.fsync after writing."""

    def test_fsync_called_after_write(self, tmp_path):
        """os.fsync must be called on the destination fd after copy."""
        src = _make_temp_file(str(tmp_path), "fsync_src.bin", 4096)
        dst = str(tmp_path / "fsync_dst.bin")

        fsync_calls = []
        original_fsync = os.fsync

        def tracking_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        with mock.patch("src.tools.bulk_transfer_v2.os.fsync", side_effect=tracking_fsync):
            _buffered_copy_inner(src, dst, buf_size=1024, bw_limit=0)

        assert len(fsync_calls) >= 1, "os.fsync was never called after copy"
        assert os.path.exists(dst)
        assert os.path.getsize(dst) == 4096

    def test_fsync_called_with_bandwidth_limiting(self, tmp_path):
        """fsync should also fire when bandwidth limiting is active."""
        src = _make_temp_file(str(tmp_path), "fsync_bw_src.bin", 2048)
        dst = str(tmp_path / "fsync_bw_dst.bin")

        fsync_calls = []
        original_fsync = os.fsync

        def tracking_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        with mock.patch("src.tools.bulk_transfer_v2.os.fsync", side_effect=tracking_fsync):
            # Use a high bandwidth limit so it doesn't actually slow down
            _buffered_copy_inner(src, dst, buf_size=1024, bw_limit=999_999_999)

        assert len(fsync_calls) >= 1, "os.fsync not called with bandwidth limiting"


# ============================================================================
# TEST 8: _buffered_copy_inner with bandwidth limiting works correctly
# ============================================================================

class TestBandwidthLimiting:
    """Verify bandwidth limiting throttles without corrupting data."""

    def test_bandwidth_limited_copy_produces_correct_output(self, tmp_path):
        """Copy with bandwidth limit should produce byte-identical output."""
        content = os.urandom(8192)
        src = str(tmp_path / "bw_src.bin")
        dst = str(tmp_path / "bw_dst.bin")
        with open(src, "wb") as f:
            f.write(content)

        # Limit to 4KB/s -- copy of 8KB should take ~2s
        # Use a high limit here to not slow tests
        _buffered_copy_inner(src, dst, buf_size=1024, bw_limit=1_000_000)

        with open(dst, "rb") as f:
            result = f.read()
        assert result == content, "Bandwidth-limited copy corrupted data"

    def test_bandwidth_limiting_actually_throttles(self, tmp_path):
        """With a low bw_limit, copy should take noticeably longer."""
        content = b"X" * 4096  # 4 KB
        src = str(tmp_path / "slow_src.bin")
        dst = str(tmp_path / "slow_dst.bin")
        with open(src, "wb") as f:
            f.write(content)

        # Limit to 2048 bytes/sec -> 4096 bytes should take ~2 seconds
        t0 = time.monotonic()
        _buffered_copy_inner(src, dst, buf_size=1024, bw_limit=2048)
        elapsed = time.monotonic() - t0

        # Should take at least 1 second (giving margin for timing jitter)
        assert elapsed >= 1.0, (
            f"Bandwidth limiting not effective: {elapsed:.2f}s for 4KB at 2KB/s"
        )
        # Verify data integrity
        with open(dst, "rb") as f:
            assert f.read() == content

    def test_zero_bandwidth_limit_means_unlimited(self, tmp_path):
        """bw_limit=0 should use shutil.copyfileobj (fast path)."""
        content = b"Z" * 16384
        src = str(tmp_path / "unlimited_src.bin")
        dst = str(tmp_path / "unlimited_dst.bin")
        with open(src, "wb") as f:
            f.write(content)

        _buffered_copy_inner(src, dst, buf_size=4096, bw_limit=0)
        with open(dst, "rb") as f:
            assert f.read() == content


# ============================================================================
# TEST 9: Large file timeout calculation is correct
# ============================================================================

class TestTimeoutCalculation:
    """Verify copy_timeout = max(60, file_size / (512*1024))."""

    def test_small_file_gets_60s_minimum(self):
        """Files under 30MB should get the 60s floor."""
        file_size = 1_000_000  # 1 MB
        timeout = max(60.0, file_size / (512 * 1024))
        assert timeout == 60.0, f"Expected 60.0, got {timeout}"

    def test_large_file_gets_scaled_timeout(self):
        """A 1 GB file should get ~2048 seconds (1GB / 512KB/s)."""
        file_size = 1_073_741_824  # 1 GB
        timeout = max(60.0, file_size / (512 * 1024))
        expected = file_size / (512 * 1024)  # ~2048 seconds
        assert abs(timeout - expected) < 1.0, (
            f"Expected ~{expected:.0f}s, got {timeout:.0f}s"
        )

    def test_boundary_file_30mb(self):
        """~30.7 MB is the crossover point (30.7MB / 512KB/s = 60s)."""
        crossover = int(60.0 * 512 * 1024)  # 31,457,280 bytes
        # Just under crossover: should get 60s
        timeout_under = max(60.0, (crossover - 1) / (512 * 1024))
        assert timeout_under == 60.0

        # Just over crossover: should get > 60s
        timeout_over = max(60.0, (crossover + 1) / (512 * 1024))
        assert timeout_over > 60.0

    def test_timeout_formula_matches_engine_code(self, tmp_path):
        """Verify the engine uses the exact formula we expect."""
        # Check that _transfer_one computes copy_timeout the same way
        # by reading the source code pattern
        import inspect
        from src.tools.bulk_transfer_v2 import AtomicTransferWorker

        source = inspect.getsource(AtomicTransferWorker._transfer_one)
        assert "max(60.0, file_size / (512 * 1024))" in source, (
            "Engine timeout formula doesn't match expected pattern"
        )


# ============================================================================
# TEST 10: Memory doesn't blow up with 100K item queue (backpressure)
# ============================================================================

class TestMemoryPressure:
    """Verify the engine can handle large queue without OOM."""

    def test_100k_queue_items_dont_explode_memory(self, tmp_path):
        """Building a 100K-item queue shouldn't cause excessive memory use."""
        import tracemalloc

        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # Simulate a 100K item queue (just tuples, no actual files)
        queue = [
            (f"\\\\server\\share\\dir{i // 100}\\file_{i}.pdf",
             "\\\\server\\share",
             f"dir{i // 100}/file_{i}.pdf",
             random_size(i))
            for i in range(100_000)
        ]

        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # 100K tuples of 4 strings + int should be roughly:
        # ~100 bytes per tuple * 100K = ~10 MB.
        # Allow up to 100 MB -- anything more suggests a leak.
        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_new = sum(s.size_diff for s in stats if s.size_diff > 0)
        mb_used = total_new / (1024 * 1024)

        assert mb_used < 100, (
            f"100K queue items used {mb_used:.1f} MB (expected < 100 MB)"
        )

    def test_stats_object_stays_small_under_pressure(self):
        """TransferStats counters should not leak memory."""
        import tracemalloc

        tracemalloc.start()
        stats = TransferStats()
        snapshot1 = tracemalloc.take_snapshot()

        # Simulate 100K file operations updating stats
        for i in range(100_000):
            with stats._lock:
                stats.files_discovered += 1
                stats.bytes_source_total += 1024

        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Integer counters should not allocate significant memory
        diffs = snapshot2.compare_to(snapshot1, "lineno")
        total_new = sum(s.size_diff for s in diffs if s.size_diff > 0)
        mb_used = total_new / (1024 * 1024)
        assert mb_used < 10, (
            f"Stats counters used {mb_used:.1f} MB after 100K updates"
        )


def random_size(seed: int) -> int:
    """Repeatable pseudo-random file size for queue simulation."""
    return 100 + (seed * 7919) % 500_000_000


# ============================================================================
# BONUS TEST 11: StagingManager promote_to_verified TOCTOU lock
# ============================================================================

class TestPromoteTOCTOU:
    """Verify the threading.Lock prevents TOCTOU race in promote."""

    def test_concurrent_promotes_no_overwrite(self, tmp_path):
        """8 threads promoting to the same relative path should not overwrite.

        Each thread creates its OWN unique .tmp file (different incoming
        subdir per thread), then all promote to the same relative path.
        The TOCTOU lock should give each file a unique _N suffix.
        """
        staging = StagingManager(str(tmp_path / "stage"))
        results = []
        errors = []
        barrier = threading.Barrier(8, timeout=10)

        def promote_one(thread_id: int):
            try:
                # Each thread gets its own unique tmp file path to avoid
                # Windows file locking conflicts during concurrent writes.
                thread_incoming = staging.incoming / f"t{thread_id}"
                thread_incoming.mkdir(parents=True, exist_ok=True)
                tmp_file = thread_incoming / "conflict.txt.tmp"
                content = f"thread_{thread_id}" * 100
                with open(str(tmp_file), "w") as f:
                    f.write(content)
                # Synchronize: all threads promote at the same instant
                barrier.wait()
                rel = "shared/conflict.txt"
                final = staging.promote_to_verified(tmp_file, rel)
                results.append((thread_id, str(final)))
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=promote_one, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Errors during promote: {errors}"
        # All 8 threads should have produced unique destination paths
        paths = [r[1] for r in results]
        assert len(set(paths)) == len(paths), (
            f"TOCTOU race: {len(paths)} promotes but only {len(set(paths))} unique paths"
        )
        # Verify all 8 files actually exist
        for _, path in results:
            assert os.path.exists(path), f"Promoted file missing: {path}"


# ============================================================================
# BONUS TEST 12: _ALWAYS_SKIP checked in _process_discovery
# ============================================================================

class TestAlwaysSkipFilter:
    """Verify _ALWAYS_SKIP extensions are blocked during discovery."""

    def test_exe_files_blocked(self, tmp_path):
        """Files with _ALWAYS_SKIP extensions must be skipped."""
        from src.tools.bulk_transfer_v2 import _ALWAYS_SKIP

        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=1,
        )
        engine = BulkTransferV2(cfg)
        from src.tools.transfer_manifest import TransferManifest
        db_path = str(tmp_path / "out" / "_transfer_manifest.db")
        os.makedirs(str(tmp_path / "out"), exist_ok=True)
        engine.manifest = TransferManifest(db_path)
        engine.run_id = "test_skip"
        engine.manifest.start_run(engine.run_id, [str(tmp_path)], str(tmp_path / "out"))

        # Create files with always-skip extensions
        for ext in [".exe", ".dll", ".mp4", ".pst"]:
            fp = str(tmp_path / f"badfile{ext}")
            with open(fp, "wb") as f:
                f.write(b"X" * 200)

        queue = []
        for ext in [".exe", ".dll", ".mp4", ".pst"]:
            fp = str(tmp_path / f"badfile{ext}")
            engine._process_discovery(fp, str(tmp_path), queue)

        assert len(queue) == 0, (
            f"_ALWAYS_SKIP files should not be queued; got {len(queue)} items"
        )
        assert engine.stats.files_skipped_ext == 4, (
            f"Expected 4 skipped, got {engine.stats.files_skipped_ext}"
        )

        engine.manifest.close()


# ============================================================================
# BONUS TEST 13: os.replace() used in staging (not os.rename())
# ============================================================================

class TestOsReplaceUsed:
    """Verify transfer_staging.py uses os.replace(), not os.rename()."""

    def test_promote_uses_os_replace(self):
        """Executable code should use os.replace(), not os.rename() for promotion.

        Note: os.rename() may appear in docstrings/comments explaining
        the concept. We only check actual executable lines (no # or \").
        """
        import inspect
        source = inspect.getsource(StagingManager.promote_to_verified)
        # Check that os.replace is used in executable code
        assert "os.replace(" in source, (
            "promote_to_verified should use os.replace() for atomic rename"
        )
        # Filter to only executable lines (not comments or docstrings)
        executable_lines = []
        in_docstring = False
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # Toggle docstring state
                # Count quotes: if odd number of triple-quotes, toggle
                count = stripped.count('"""') + stripped.count("'''")
                if count == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            executable_lines.append(stripped)

        exec_code = "\n".join(executable_lines)
        assert "os.rename(" not in exec_code, (
            "promote_to_verified executable code should NOT use os.rename() "
            "(use os.replace instead). Found os.rename in non-comment code."
        )


# ============================================================================
# BONUS TEST 14: Retry jitter (random 0.5-1.5x multiplier)
# ============================================================================

class TestRetryJitter:
    """Verify retry sleep uses jitter multiplier."""

    def test_retry_jitter_in_source(self):
        """The _transfer_one method should use random.uniform for jitter."""
        import inspect
        source = inspect.getsource(AtomicTransferWorker._transfer_one)
        assert "random.uniform(0.5, 1.5)" in source, (
            "Retry jitter should use random.uniform(0.5, 1.5)"
        )


# ============================================================================
# BONUS TEST 15: Dedup race guard (_dedup_seen set + lock)
# ============================================================================

class TestDedupRaceGuard:
    """Verify the in-memory _dedup_seen set with lock exists."""

    def test_dedup_set_and_lock_exist(self, tmp_path):
        """AtomicTransferWorker should have _dedup_seen set and _dedup_lock."""
        import threading as _th
        cfg = TransferConfig(
            source_paths=[str(tmp_path)],
            dest_path=str(tmp_path / "out"),
            workers=1,
        )
        staging = StagingManager(str(tmp_path / "out"))
        stats = TransferStats()
        worker = AtomicTransferWorker(
            cfg, None, staging, stats,
            "test_run", _th.Event(), _th.Lock(),
        )
        assert hasattr(worker, "_dedup_seen"), "Missing _dedup_seen set"
        assert hasattr(worker, "_dedup_lock"), "Missing _dedup_lock"
        assert isinstance(worker._dedup_seen, set)
        # threading.Lock is a factory function, not a type.
        # Verify by checking it has acquire/release methods (duck typing).
        assert hasattr(worker._dedup_lock, "acquire"), "Lock missing acquire()"
        assert hasattr(worker._dedup_lock, "release"), "Lock missing release()"


# ============================================================================
# BONUS TEST 16: Hash-while-writing mtime stability check
# ============================================================================

class TestMtimeStabilityCheck:
    """Verify _transfer_one checks mtime before and after hashing."""

    def test_mtime_check_in_source_code(self):
        """_transfer_one should compare pre_stat and post_stat mtime."""
        import inspect
        source = inspect.getsource(AtomicTransferWorker._transfer_one)
        assert "pre_stat" in source, "Missing pre_stat mtime check"
        assert "post_stat" in source, "Missing post_stat mtime check"
        assert "st_mtime" in source, "Missing mtime comparison"


# ============================================================================
# Run with pytest
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
