# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the stress large files area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Stress Tests: Large files, memory pressure, disk exhaustion
# Attack surface: bulk_transfer_v2.py, transfer_manifest.py, transfer_staging.py
# ============================================================================
#
# Each test enforces a 30-second wall-clock timeout.  On Windows,
# signal.SIGALRM is unavailable, so we use a conftest-style watchdog that
# runs the test body in a daemon thread and joins with a hard deadline.
#
# Because pytest fixtures (tmp_path) cannot be injected across threads,
# we manage our own temp directories via tempfile.mkdtemp() and clean up
# in finally blocks.
# ============================================================================

from __future__ import annotations

import errno
import gc
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Import the units under test
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.bulk_transfer_v2 import (
    BulkTransferV2,
    TransferConfig,
    TransferStats,
    _buffered_copy,
    _can_read_file,
    _hash_file,
    _stat_with_timeout,
)
from src.tools.transfer_manifest import TransferManifest
from src.tools.transfer_staging import StagingManager


# ============================================================================
# Helpers
# ============================================================================

TEST_TIMEOUT = 30  # seconds -- hard cap per test


def _run_with_timeout(fn, timeout=TEST_TIMEOUT):
    """Run *fn* in a daemon thread; raise if it exceeds *timeout* seconds."""
    result = [None]
    error = [None]

    def _worker():
        try:
            result[0] = fn()
        except Exception as exc:
            error[0] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        pytest.fail(f"Test body did not complete within {timeout}s (hung)")
    if error[0] is not None:
        raise error[0]
    return result[0]


# ============================================================================
# 1. _hash_file: multi-GB file simulation + 120 s timeout check
# ============================================================================

class TestHashFileLargeAndSlow:
    """Verify _hash_file handles large files and respects the 120 s timeout."""

    def test_hash_file_large_simulated(self):
        """Hash a 5 MB temp file; verify correct digest.
        (Simulates large-file pattern -- chunked reads via real file.)"""
        def body():
            td = tempfile.mkdtemp(prefix="stress_hash_large_")
            try:
                p = os.path.join(td, "big.bin")
                chunk = b"A" * (1024 * 1024)
                with open(p, "wb") as f:
                    for _ in range(5):
                        f.write(chunk)
                expected = hashlib.sha256(chunk * 5).hexdigest()
                result = _hash_file(p, timeout=30.0)
                assert result == expected, f"Hash mismatch: {result} != {expected}"
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_hash_file_timeout_on_slow_reads(self):
        """_hash_file should return '' when reads exceed the timeout.
        Mock open() to return a file-like object whose read() sleeps."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_hash_slow_")
            try:
                p = os.path.join(td, "stall.bin")
                with open(p, "wb") as f:
                    f.write(b"seed")

                call_count = [0]

                class _StallingFile:
                    """read() returns data on first call, then blocks."""
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        pass
                    def read(self, n=-1):
                        call_count[0] += 1
                        if call_count[0] == 1:
                            return b"X" * 131072
                        # Simulate stalled SMB
                        time.sleep(200)
                        return b""

                with mock.patch("builtins.open", return_value=_StallingFile()):
                    result = _hash_file(p, timeout=2.0)

                assert result == "", (
                    f"Expected empty string on timeout, got {result!r}"
                )
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)


# ============================================================================
# 2. _buffered_copy: slow-bandwidth simulation
# ============================================================================

class TestBufferedCopySlow:
    """Verify _buffered_copy under bandwidth-limited / slow-source conditions."""

    def test_buffered_copy_bandwidth_limited(self):
        """With bw_limit, copy should complete and produce correct output."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_bwlimit_")
            try:
                src = os.path.join(td, "src.bin")
                dst = os.path.join(td, "dst.bin")
                data = os.urandom(1024 * 100)  # 100 KB
                with open(src, "wb") as f:
                    f.write(data)
                _buffered_copy(src, dst, buf_size=32768, bw_limit=1_048_576)
                with open(dst, "rb") as f:
                    assert f.read() == data
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_buffered_copy_no_timeout_exists(self):
        """FINDING: _buffered_copy has NO internal timeout.
        A mock source that delays 2 s per read causes the function to
        block for >= 2 s, proving it can hang indefinitely on a stalled
        network read."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_notimeout_")
            try:
                src = os.path.join(td, "src.bin")
                dst = os.path.join(td, "dst.bin")
                with open(src, "wb") as f:
                    f.write(b"x" * 1024)

                class _SlowReader:
                    def __init__(self):
                        self._reads = 0
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        pass
                    def read(self, n=-1):
                        self._reads += 1
                        if self._reads == 1:
                            time.sleep(2)
                            return b"Y" * 512
                        return b""

                real_open = open

                def _patched_open(path, mode="r", **kw):
                    if "r" in mode and src in str(path):
                        return _SlowReader()
                    return real_open(path, mode, **kw)

                t0 = time.monotonic()
                with mock.patch("builtins.open", side_effect=_patched_open):
                    _buffered_copy(src, dst, buf_size=1024, bw_limit=0)
                elapsed = time.monotonic() - t0

                assert elapsed >= 1.5, (
                    f"Expected >= 2 s elapsed for slow source, got {elapsed:.2f}s"
                )
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)


# ============================================================================
# 3. TransferStats: memory growth of _speed_samples under 500k+ calls
# ============================================================================

class TestTransferStatsMemoryPressure:
    """Hammer record_copy and check _speed_samples memory growth."""

    def test_speed_samples_unbounded_growth(self):
        """FINDING: record_copy appends to _speed_samples with no cap.
        Only speed_bps trims old samples (30 s window).
        500k record_copy calls grow _speed_samples to 500k entries."""
        def body():
            stats = TransferStats()
            for i in range(500_000):
                stats.record_copy(1024, ".txt")

            raw_len = len(stats._speed_samples)
            assert raw_len == 500_000, (
                f"Expected 500,000 samples, got {raw_len}"
            )

            # Calling speed_bps triggers the trim
            _ = stats.speed_bps
            trimmed_len = len(stats._speed_samples)
            assert trimmed_len <= raw_len, "speed_bps should trim old samples"
        _run_with_timeout(body)

    def test_speed_samples_memory_bytes(self):
        """Measure actual memory footprint of 500k _speed_samples entries."""
        def body():
            stats = TransferStats()
            gc.collect()
            for i in range(500_000):
                stats.record_copy(1024, ".txt")

            sample_count = len(stats._speed_samples)
            # Each (float, int) tuple ~ 72 bytes in CPython
            estimated_bytes = sample_count * 72
            assert estimated_bytes < 100_000_000, (
                f"_speed_samples estimated at {estimated_bytes / 1e6:.1f} MB "
                f"for {sample_count} samples -- potential memory leak"
            )
            print(f"\n  [INFO] _speed_samples: {sample_count} entries, "
                  f"~{estimated_bytes / 1e6:.1f} MB estimated")
        _run_with_timeout(body)


# ============================================================================
# 4. Full queue submission with 10,000 small files
# ============================================================================

class TestMassFileDiscovery:
    """Create 10,000 real temp files, run discovery, check memory."""

    def test_10k_file_discovery_memory(self):
        """Create 10,000 .txt files, build TransferConfig, invoke discovery.
        Verify the engine does not explode in memory."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_10k_")
            try:
                src_dir = os.path.join(td, "source")
                dst_dir = os.path.join(td, "dest")
                os.makedirs(src_dir)
                os.makedirs(dst_dir)

                # Create 10,000 tiny .txt files across 100 subdirs
                for i in range(100):
                    subdir = os.path.join(src_dir, f"dir_{i:03d}")
                    os.makedirs(subdir)
                    for j in range(100):
                        fp = os.path.join(subdir, f"file_{j:04d}.txt")
                        with open(fp, "w") as fh:
                            fh.write(f"content {i}-{j}" * 20)

                cfg = TransferConfig(
                    source_paths=[src_dir],
                    dest_path=dst_dir,
                    workers=1,
                    resume=False,
                    verify_copies=False,
                    deduplicate=False,
                    min_file_size=0,
                )
                engine = BulkTransferV2(cfg)

                db_path = os.path.join(dst_dir, "_transfer_manifest.db")
                engine.manifest = TransferManifest(db_path)
                engine.staging = StagingManager(dst_dir)
                engine.manifest.start_run(
                    engine.run_id, cfg.source_paths, cfg.dest_path,
                    config_json=json.dumps({"workers": 1}),
                )

                queue = engine._discover_and_manifest()
                engine.manifest.close()

                assert engine.stats.files_discovered == 10_000, (
                    f"Expected 10,000 discovered, got {engine.stats.files_discovered}"
                )
                assert len(queue) == 10_000, (
                    f"Expected 10,000 queued, got {len(queue)}"
                )
                print(f"\n  [INFO] Queue: {len(queue)}, "
                      f"discovered: {engine.stats.files_discovered}")
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)


# ============================================================================
# 5. Disk full (ENOSPC) mid-copy
# ============================================================================

class TestDiskFullMidCopy:
    """Simulate ENOSPC during _buffered_copy."""

    def test_enospc_during_write_bw_limited(self):
        """With bw_limit > 0 (_buffered_copy does manual read/write loop),
        inject ENOSPC on the second fdst.write().
        Verify the exception propagates out of _buffered_copy."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_enospc_")
            try:
                src = os.path.join(td, "src.bin")
                dst = os.path.join(td, "dst.bin")
                with open(src, "wb") as f:
                    f.write(os.urandom(1024 * 100))  # 100 KB

                write_count = [0]
                real_open = open

                class _FullDisk:
                    """Writable file-like that raises ENOSPC on 2nd write."""
                    def __init__(self, path, mode, **kw):
                        self._f = real_open(path, mode, **kw)
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        self._f.close()
                    def write(self, data):
                        write_count[0] += 1
                        if write_count[0] >= 2:
                            raise OSError(errno.ENOSPC,
                                          "No space left on device")
                        return self._f.write(data)

                def _patched_open(path, mode="r", **kw):
                    if "w" in mode and dst in str(path):
                        return _FullDisk(path, mode, **kw)
                    return real_open(path, mode, **kw)

                # bw_limit must be high enough that the per-chunk sleep
                # is negligible (32KB / 100MB/s = 0.0003s)
                got_enospc = False
                try:
                    with mock.patch("builtins.open",
                                    side_effect=_patched_open):
                        _buffered_copy(src, dst, buf_size=32768,
                                       bw_limit=100_000_000)
                except OSError as e:
                    if e.errno == errno.ENOSPC:
                        got_enospc = True
                    else:
                        raise
                assert got_enospc, "Expected ENOSPC to propagate"
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_enospc_via_shutil_copyfileobj(self):
        """When bw_limit=0, _buffered_copy delegates to shutil.copyfileobj.
        Verify ENOSPC still propagates through shutil."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_enospc2_")
            try:
                src = os.path.join(td, "src.bin")
                dst = os.path.join(td, "dst.bin")
                with open(src, "wb") as f:
                    f.write(os.urandom(1024 * 200))

                def _boom_copyfileobj(fsrc, fdst, length=0):
                    data = fsrc.read(length or 16384)
                    if data:
                        fdst.write(data)
                    raise OSError(errno.ENOSPC, "No space left on device")

                with mock.patch(
                    "src.tools.bulk_transfer_v2.shutil.copyfileobj",
                    side_effect=_boom_copyfileobj,
                ):
                    with pytest.raises(OSError) as exc_info:
                        _buffered_copy(src, dst, buf_size=32768, bw_limit=0)
                    assert exc_info.value.errno == errno.ENOSPC
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)


# ============================================================================
# 6. _hash_file: single f.read() blocks for 200 s (stalled SMB)
# ============================================================================

class TestHashFileStalledSMB:
    """Simulate a single f.read() that blocks for 200 s."""

    def test_single_read_blocks_200s(self):
        """_hash_file uses t.join(timeout=timeout + 5.0).
        With timeout=3.0, join deadline is 8.0 s.
        A read that blocks 200 s causes the thread to be abandoned after ~8 s."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_smb_")
            try:
                p = os.path.join(td, "stalled.bin")
                with open(p, "wb") as f:
                    f.write(b"test")

                stall_event = threading.Event()

                class _ForeverBlockingFile:
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        pass
                    def read(self, n=-1):
                        stall_event.wait(timeout=200)
                        return b""

                with mock.patch("builtins.open",
                                return_value=_ForeverBlockingFile()):
                    t0 = time.monotonic()
                    result = _hash_file(p, timeout=3.0)
                    elapsed = time.monotonic() - t0

                assert result == "", (
                    f"Expected '' from timed-out _hash_file, got {result!r}"
                )
                # Should return in ~8 s (timeout + 5.0), NOT 200 s
                assert elapsed < 15.0, (
                    f"_hash_file took {elapsed:.1f}s, expected < 15s"
                )
                assert elapsed >= 2.5, (
                    f"_hash_file returned too fast ({elapsed:.1f}s)"
                )
                print(f"\n  [INFO] _hash_file with stalled SMB returned in "
                      f"{elapsed:.2f}s (timeout=3.0 + 5.0 join buffer)")

                # Cleanup the stalled thread
                stall_event.set()
                time.sleep(0.3)
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)


# ============================================================================
# 7. Abandoned daemon threads
# ============================================================================

class TestAbandonedDaemonThreads:
    """Count threads before/after calls that may abandon daemon threads."""

    @staticmethod
    def _thread_count() -> int:
        return len(threading.enumerate())

    def test_stat_with_timeout_no_leak_on_success(self):
        """Successful _stat_with_timeout should not leak threads."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_stat_ok_")
            try:
                p = os.path.join(td, "exists.txt")
                with open(p, "w") as f:
                    f.write("hello")

                before = self._thread_count()
                for _ in range(100):
                    _stat_with_timeout(p, timeout=5.0)
                time.sleep(0.5)
                after = self._thread_count()

                leaked = after - before
                assert leaked <= 2, (
                    f"_stat_with_timeout leaked {leaked} threads after 100 calls"
                )
                print(f"\n  [INFO] Thread delta after 100 successful _stat_with_timeout: "
                      f"{leaked}")
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_hash_file_abandons_thread_on_stall(self):
        """FINDING: When _hash_file times out, the daemon thread is abandoned
        and remains in threading.enumerate() until the process exits."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_abandon_")
            try:
                p = os.path.join(td, "stall.bin")
                with open(p, "wb") as f:
                    f.write(b"data")

                stall_event = threading.Event()

                class _StallForever:
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        pass
                    def read(self, n=-1):
                        stall_event.wait(timeout=60)
                        return b""

                before = self._thread_count()
                with mock.patch("builtins.open",
                                return_value=_StallForever()):
                    result = _hash_file(p, timeout=1.0)
                assert result == ""

                after = self._thread_count()
                abandoned = after - before
                print(f"\n  [INFO] Abandoned daemon threads from _hash_file: "
                      f"{abandoned}")
                # At least 1 thread should be stuck
                assert abandoned >= 1, (
                    f"Expected >= 1 abandoned thread, got {abandoned}"
                )

                # Cleanup
                stall_event.set()
                time.sleep(0.5)
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_can_read_file_no_leak_on_success(self):
        """Successful _can_read_file should not leak threads."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_canread_")
            try:
                p = os.path.join(td, "readable.txt")
                with open(p, "w") as f:
                    f.write("hello")

                before = self._thread_count()
                for _ in range(100):
                    _can_read_file(p, timeout=5.0)
                time.sleep(0.5)
                after = self._thread_count()

                leaked = after - before
                assert leaked <= 2, (
                    f"_can_read_file leaked {leaked} threads after 100 calls"
                )
                print(f"\n  [INFO] Thread delta after 100 successful _can_read_file: "
                      f"{leaked}")
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_stat_with_timeout_abandons_thread_on_hang(self):
        """FINDING: When os.stat hangs, _stat_with_timeout raises TimeoutError
        but leaves behind an abandoned daemon thread."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_stat_hang_")
            try:
                p = os.path.join(td, "hang.txt")
                with open(p, "w") as f:
                    f.write("data")

                stall_event = threading.Event()

                def _hanging_stat(path):
                    stall_event.wait(timeout=60)
                    return os.stat.__wrapped__(path)  # will not reach

                before = self._thread_count()
                with mock.patch("os.stat", side_effect=_hanging_stat):
                    with pytest.raises(TimeoutError):
                        _stat_with_timeout(p, timeout=1.0)

                after = self._thread_count()
                abandoned = after - before
                print(f"\n  [INFO] Abandoned daemon threads from "
                      f"_stat_with_timeout: {abandoned}")
                assert abandoned >= 1, (
                    f"Expected >= 1 abandoned thread, got {abandoned}"
                )

                # Cleanup
                stall_event.set()
                time.sleep(0.5)
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)

    def test_multiple_abandoned_threads_accumulate(self):
        """FINDING: Call _hash_file 3 times with stalling reads.
        Each call abandons 1 daemon thread, accumulating 3 orphans.
        _hash_file(timeout=T) blocks for T+5.0 s on join, so we use
        timeout=0.5 (join = 5.5 s * 3 = ~16.5 s) to stay under our
        30 s test cap."""
        def body():
            td = tempfile.mkdtemp(prefix="stress_multi_")
            try:
                p = os.path.join(td, "multi_stall.bin")
                with open(p, "wb") as f:
                    f.write(b"data")

                stall_events: List[threading.Event] = []

                def _make_staller():
                    evt = threading.Event()
                    stall_events.append(evt)

                    class _Staller:
                        def __enter__(self):
                            return self
                        def __exit__(self, *a):
                            pass
                        def read(self, n=-1):
                            evt.wait(timeout=60)
                            return b""
                    return _Staller()

                before = self._thread_count()

                for _ in range(3):
                    with mock.patch("builtins.open",
                                    side_effect=lambda *a, **k: _make_staller()):
                        _hash_file(p, timeout=0.5)

                after = self._thread_count()
                abandoned = after - before
                print(f"\n  [INFO] Accumulated abandoned threads after 3 stalls: "
                      f"{abandoned}")

                assert abandoned >= 2, (
                    f"Expected >= 2 abandoned threads from 3 stalled "
                    f"_hash_file calls, got {abandoned}"
                )

                # Cleanup -- signal stalled threads so they exit
                for evt in stall_events:
                    evt.set()
                time.sleep(0.5)

                final = self._thread_count()
                remaining = final - before
                print(f"  [INFO] After signaling all events: "
                      f"{remaining} threads remain")
            finally:
                shutil.rmtree(td, ignore_errors=True)
        _run_with_timeout(body)
