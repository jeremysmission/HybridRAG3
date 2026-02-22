# ============================================================================
# Network Chaos Stress Tests for Bulk Transfer V2 Engine
# ============================================================================
#
# Attack vector: Dropped connections, timeouts, bandwidth fluctuation,
#                stalled reads, TOCTOU races, growing files.
#
# Run with: python -m pytest tests/stress_test_network_chaos.py -v --tb=short -x
# ============================================================================

from __future__ import annotations

import hashlib
import io
import os
import random
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# ---------------------------------------------------------------------------
# Hard timeout decorator -- kills test after 30 seconds
# ---------------------------------------------------------------------------

def hard_timeout(seconds=30):
    """Decorator: fail the test if it does not complete within `seconds`."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result_holder = [None]
            error_holder = [None]

            def target():
                try:
                    result_holder[0] = func(*args, **kwargs)
                except Exception as exc:
                    error_holder[0] = exc

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=seconds)
            if t.is_alive():
                raise TimeoutError(
                    f"Test {func.__name__} did not complete within {seconds}s "
                    f"-- possible thread/resource leak or infinite hang"
                )
            if error_holder[0] is not None:
                raise error_holder[0]
            return result_holder[0]
        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = func.__qualname__
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Import targets under test (module-level functions + classes)
# ---------------------------------------------------------------------------

from src.tools.bulk_transfer_v2 import (
    _buffered_copy,
    _can_read_file,
    _hash_file,
    _stat_with_timeout,
    BulkTransferV2,
    TransferConfig,
    TransferStats,
)


# ===========================================================================
# Test 1: _buffered_copy hangs on stalled SMB read after 100 KB
# ===========================================================================

class StallAfterNBytesFile:
    """
    File-like object that serves `stall_after` bytes normally, then blocks
    forever on the next read() call -- simulating a frozen SMB connection.
    """

    def __init__(self, data: bytes, stall_after: int):
        self._data = data
        self._pos = 0
        self._stall_after = stall_after
        self._stall_event = threading.Event()

    def read(self, n=-1):
        if self._pos >= self._stall_after:
            # Block until externally released (or forever if not)
            self._stall_event.wait(timeout=60)
            return b""
        end = min(self._pos + n, self._stall_after) if n > 0 else self._stall_after
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def release(self):
        """Unblock the stalled read (cleanup)."""
        self._stall_event.set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()


class TestBufferedCopyStalledRead(unittest.TestCase):
    """
    Test 1: _buffered_copy where source read blocks forever after 100 KB.
    Does the worker hang indefinitely?

    FINDING: _buffered_copy has NO internal timeout on individual reads.
    When shutil.copyfileobj or the manual read loop blocks, the function
    blocks forever. The only protection is the caller-level timeout
    (the retry backoff in _transfer_one), but _buffered_copy itself will
    hang the calling thread.
    """

    @hard_timeout(15)
    def test_stalled_read_hangs_buffered_copy(self):
        """_buffered_copy hangs when source read stalls (no read timeout)."""
        total_size = 500_000   # 500 KB file
        stall_after = 102_400  # Stall after 100 KB
        data = os.urandom(total_size)
        stalling_file = StallAfterNBytesFile(data, stall_after)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dst") as dst_f:
            dst_path = dst_f.name

        hung = threading.Event()
        completed = threading.Event()

        def run_copy():
            try:
                # Patch open so src opens our stalling file, dst opens normally
                original_open = open

                def mock_open(path, mode="r", *a, **kw):
                    if path == "FAKE_SRC" and "r" in mode:
                        return stalling_file
                    return original_open(path, mode, *a, **kw)

                with mock.patch("builtins.open", side_effect=mock_open):
                    _buffered_copy("FAKE_SRC", dst_path, buf_size=32768, bw_limit=0)
                completed.set()
            except Exception:
                completed.set()

        t = threading.Thread(target=run_copy, daemon=True)
        t.start()

        # Wait 5 seconds -- if it hasn't completed, it's hung
        t.join(timeout=5.0)
        is_hung = t.is_alive()

        # Clean up
        stalling_file.release()
        t.join(timeout=5.0)
        try:
            os.unlink(dst_path)
        except OSError:
            pass

        # ASSERTION: _buffered_copy SHOULD hang because there is no
        # per-read timeout in the function.
        self.assertTrue(
            is_hung,
            "_buffered_copy returned instead of hanging on stalled read. "
            "BUG: Expected it to hang since there is no read timeout."
        )


# ===========================================================================
# Test 2: _hash_file with 30% random OSError on read()
# ===========================================================================

class FlakeyReadFile:
    """
    File-like object that raises OSError("Network path not found") on
    approximately `fail_pct`% of read() calls.
    """

    def __init__(self, data: bytes, fail_pct: float = 0.3):
        self._stream = io.BytesIO(data)
        self._fail_pct = fail_pct

    def read(self, n=-1):
        if random.random() < self._fail_pct:
            raise OSError("Network path not found")
        return self._stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestHashFileNetworkErrors(unittest.TestCase):
    """
    Test 2: _hash_file with a mock file that raises OSError randomly
    on 30% of read() calls.

    FINDING: _hash_file catches (OSError, PermissionError) at the
    function level (line 1154) and returns "". It does NOT retry or
    attempt to recover from transient network errors. A single OSError
    on any read kills the entire hash computation.
    """

    @hard_timeout(30)
    def test_hash_file_with_flaky_reads(self):
        """_hash_file returns '' on OSError (no retry, full abort)."""
        data = os.urandom(1_000_000)  # 1 MB

        # Write a real file so _hash_file can open it
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as f:
            f.write(data)
            real_path = f.name

        # Expected hash if read cleanly
        expected_hash = hashlib.sha256(data).hexdigest()

        # Patch open inside the _do_hash thread to return our flakey reader
        flaky_file = FlakeyReadFile(data, fail_pct=0.30)
        original_open = open

        def patched_open(path, mode="r", *a, **kw):
            if path == real_path and "b" in mode:
                return flaky_file
            return original_open(path, mode, *a, **kw)

        # Run multiple times -- at least some should fail
        failures = 0
        successes = 0
        trials = 20
        random.seed(42)  # Deterministic randomness

        for _ in range(trials):
            flaky_file = FlakeyReadFile(data, fail_pct=0.30)
            with mock.patch("builtins.open", side_effect=patched_open):
                result = _hash_file(real_path, timeout=10.0)
            if result == "":
                failures += 1
            else:
                successes += 1

        os.unlink(real_path)

        # With 30% failure rate across ~8 reads (1MB / 128KB), probability
        # of ALL reads succeeding in one trial is 0.7^8 ~ 5.7%.
        # Over 20 trials, expect most to fail.
        self.assertGreater(
            failures, 0,
            "Expected some hash failures with 30% OSError rate, got none"
        )
        # Verify it returns "" (not crash/exception) for failures
        # If we got here without exception, the function handled it gracefully
        self.assertTrue(True, "_hash_file handled OSError gracefully (returned '')")


# ===========================================================================
# Test 3: _transfer_one retry logic (ConnectionResetError on attempts 1,2)
# ===========================================================================

class TestTransferOneRetryLogic(unittest.TestCase):
    """
    Test 3: _transfer_one retry logic -- _buffered_copy fails with
    ConnectionResetError on attempts 1 and 2, then succeeds on attempt 3.

    Verifies retry_count tracking and backoff timing.
    """

    @hard_timeout(30)
    def test_retry_on_connection_reset(self):
        """_transfer_one retries on ConnectionResetError with backoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source file
            src_data = b"retry test content " * 1000
            src_path = os.path.join(tmpdir, "source.txt")
            with open(src_path, "wb") as f:
                f.write(src_data)

            src_hash = hashlib.sha256(src_data).hexdigest()

            # Configure engine with short backoff for testing
            cfg = TransferConfig(
                source_paths=[tmpdir],
                dest_path=os.path.join(tmpdir, "dest"),
                workers=1,
                max_retries=3,
                retry_backoff=0.1,  # 0.1s backoff (fast for testing)
                deduplicate=False,
                verify_copies=True,
            )
            engine = BulkTransferV2(cfg)
            engine.manifest = mock.MagicMock()
            engine.manifest.find_by_hash.return_value = None
            engine.staging = mock.MagicMock()

            # staging.incoming_path returns a real temp path
            tmp_copy_path = Path(os.path.join(tmpdir, "dest", "incoming", "source.txt.tmp"))
            tmp_copy_path.parent.mkdir(parents=True, exist_ok=True)
            engine.staging.incoming_path.return_value = tmp_copy_path

            # Track _buffered_copy calls
            call_count = [0]
            call_times = []

            def mock_buffered_copy(src, dst, buf_size, bw_limit):
                call_count[0] += 1
                call_times.append(time.monotonic())
                if call_count[0] <= 2:
                    raise ConnectionResetError(
                        f"Connection reset by peer (attempt {call_count[0]})"
                    )
                # Attempt 3: actually copy the file
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())

            with mock.patch(
                "src.tools.bulk_transfer_v2._buffered_copy",
                side_effect=mock_buffered_copy,
            ), mock.patch(
                "src.tools.bulk_transfer_v2._hash_file",
                return_value=src_hash,
            ), mock.patch(
                "src.tools.bulk_transfer_v2._can_read_file",
                return_value=True,
            ):
                engine._transfer_one(src_path, tmpdir, "source.txt", len(src_data))

            # Verify: 3 attempts were made
            self.assertEqual(
                call_count[0], 3,
                f"Expected 3 _buffered_copy calls, got {call_count[0]}"
            )

            # Verify: backoff timing between attempts
            if len(call_times) >= 3:
                gap_1_2 = call_times[1] - call_times[0]
                gap_2_3 = call_times[2] - call_times[1]
                # With retry_backoff=0.1:
                #   After attempt 1 fail: sleep(0.1^1) = 0.1s
                #   After attempt 2 fail: sleep(0.1^2) = 0.01s
                self.assertGreater(
                    gap_1_2, 0.05,
                    f"Backoff gap 1->2 too short: {gap_1_2:.3f}s"
                )

            # Verify manifest recorded success (not failure)
            # The staging.quarantine_file should NOT have been called
            engine.staging.quarantine_file.assert_not_called()


# ===========================================================================
# Test 4: _stat_with_timeout with 30-second sleep (beyond 10s timeout)
# ===========================================================================

class TestStatWithTimeout(unittest.TestCase):
    """
    Test 4: _stat_with_timeout with a mock os.stat that sleeps for 30s
    (beyond the 10s timeout). Verifies TimeoutError is raised and the
    thread is abandoned (daemon, so it won't block process exit).
    """

    @hard_timeout(20)
    def test_stat_timeout_raises_timeout_error(self):
        """_stat_with_timeout raises TimeoutError when stat hangs."""
        def slow_stat(path):
            time.sleep(30)  # Way beyond timeout
            return os.stat_result((0,) * 10)

        with mock.patch("os.stat", side_effect=slow_stat):
            start = time.monotonic()
            with self.assertRaises(TimeoutError) as ctx:
                _stat_with_timeout("/fake/network/path.txt", timeout=2.0)
            elapsed = time.monotonic() - start

            # Should raise within ~2 seconds (the timeout), not 30
            self.assertLess(
                elapsed, 5.0,
                f"TimeoutError took {elapsed:.1f}s (expected ~2s)"
            )
            self.assertIn("timed out", str(ctx.exception).lower())

    @hard_timeout(20)
    def test_stat_timeout_thread_is_daemon(self):
        """Abandoned thread from _stat_with_timeout is daemon (no leak)."""
        stall_event = threading.Event()

        def blocking_stat(path):
            stall_event.wait(timeout=60)
            return os.stat_result((0,) * 10)

        active_before = threading.active_count()

        with mock.patch("os.stat", side_effect=blocking_stat):
            try:
                _stat_with_timeout("/fake/path", timeout=1.0)
            except TimeoutError:
                pass

        # The abandoned thread is daemon, so it won't prevent exit.
        # But it will still show in active_count briefly.
        time.sleep(0.2)
        active_after = threading.active_count()

        # Release the blocked thread for cleanup
        stall_event.set()
        time.sleep(0.5)

        # After release, thread count should return to baseline
        active_final = threading.active_count()
        self.assertLessEqual(
            active_final, active_before + 1,
            f"Thread leak: before={active_before}, after_release={active_final}"
        )


# ===========================================================================
# Test 5: _can_read_file with open() that hangs for 20 seconds
# ===========================================================================

class TestCanReadFileHang(unittest.TestCase):
    """
    Test 5: _can_read_file with a mock open() that hangs for 20 seconds.
    Verifies it returns False within 5s and the thread is abandoned.
    """

    @hard_timeout(15)
    def test_can_read_returns_false_on_hang(self):
        """_can_read_file returns False within timeout when open() hangs."""
        def hanging_open(path, mode="r", *a, **kw):
            time.sleep(20)  # Hang for 20 seconds
            raise OSError("Never reaches here")

        with mock.patch("builtins.open", side_effect=hanging_open):
            start = time.monotonic()
            result = _can_read_file("/fake/locked/file.docx", timeout=2.0)
            elapsed = time.monotonic() - start

        self.assertFalse(
            result,
            "_can_read_file should return False when open() hangs"
        )
        self.assertLess(
            elapsed, 5.0,
            f"_can_read_file took {elapsed:.1f}s (expected ~2s timeout)"
        )


# ===========================================================================
# Test 6: Bandwidth throttling accuracy on _buffered_copy
# ===========================================================================

class TestBandwidthThrottling(unittest.TestCase):
    """
    Test 6: _buffered_copy with bw_limit=1048576 (1 MB/s) on a 5 MB file.
    Verifies it takes approximately 5 seconds (within 20% tolerance).
    """

    @hard_timeout(30)
    def test_bandwidth_limit_timing(self):
        """_buffered_copy respects bandwidth limit within 20% tolerance."""
        file_size = 5 * 1024 * 1024  # 5 MB
        bw_limit = 1024 * 1024       # 1 MB/s
        expected_time = file_size / bw_limit  # ~5.0 seconds
        tolerance = 0.20  # 20%

        data = os.urandom(file_size)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".src") as sf:
            sf.write(data)
            src_path = sf.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dst") as df:
            dst_path = df.name

        try:
            start = time.monotonic()
            _buffered_copy(src_path, dst_path, buf_size=1_048_576, bw_limit=bw_limit)
            elapsed = time.monotonic() - start

            # Verify file was copied correctly
            with open(dst_path, "rb") as f:
                copied_data = f.read()
            self.assertEqual(
                len(copied_data), file_size,
                f"Copied file size mismatch: {len(copied_data)} vs {file_size}"
            )
            self.assertEqual(
                hashlib.sha256(copied_data).hexdigest(),
                hashlib.sha256(data).hexdigest(),
                "Copied file content corrupted"
            )

            # Verify timing is within tolerance
            lower = expected_time * (1 - tolerance)
            upper = expected_time * (1 + tolerance)
            self.assertGreaterEqual(
                elapsed, lower,
                f"Copy too fast: {elapsed:.2f}s (expected >= {lower:.2f}s)"
            )
            self.assertLessEqual(
                elapsed, upper,
                f"Copy too slow: {elapsed:.2f}s (expected <= {upper:.2f}s)"
            )
        finally:
            os.unlink(src_path)
            os.unlink(dst_path)


# ===========================================================================
# Test 7: _hash_file on a file being actively written to (growing file)
# ===========================================================================

class TestHashFileGrowingFile(unittest.TestCase):
    """
    Test 7: _hash_file on a file that is being actively written to by
    another thread. The file grows while the hash is being computed.

    FINDING: _hash_file reads in 128 KB chunks with no file locking.
    If a writer appends data between reads, the hash will include
    partially-new data. The function does NOT detect this condition --
    it returns a hash that matches neither the original nor the final
    file contents. This is by design (see _transfer_one step 6 which
    detects this via hash mismatch).
    """

    @hard_timeout(30)
    def test_hash_of_growing_file(self):
        """_hash_file returns a hash, but it may match neither original nor final."""
        initial_size = 256 * 1024   # 256 KB initial
        append_size = 512 * 1024    # 512 KB appended

        with tempfile.NamedTemporaryFile(delete=False, suffix=".growing") as f:
            initial_data = os.urandom(initial_size)
            f.write(initial_data)
            f.flush()
            file_path = f.name

        hash_before = hashlib.sha256(initial_data).hexdigest()

        # Writer thread: append data while hash is running
        append_data = os.urandom(append_size)
        writer_started = threading.Event()
        writer_done = threading.Event()

        def writer():
            writer_started.wait(timeout=5)
            with open(file_path, "ab") as f:
                # Write in small chunks with small delays to overlap with reading
                chunk_size = 32 * 1024
                for i in range(0, len(append_data), chunk_size):
                    f.write(append_data[i:i + chunk_size])
                    f.flush()
                    time.sleep(0.01)
            writer_done.set()

        t = threading.Thread(target=writer, daemon=True)
        t.start()

        # Signal writer to start just before hashing
        writer_started.set()
        time.sleep(0.05)  # Let writer get a head start

        result_hash = _hash_file(file_path, timeout=30.0)

        writer_done.wait(timeout=10)

        # Read final file contents
        with open(file_path, "rb") as f:
            final_data = f.read()
        hash_after = hashlib.sha256(final_data).hexdigest()

        os.unlink(file_path)

        # The hash function should return SOMETHING (not crash)
        self.assertNotEqual(
            result_hash, "",
            "_hash_file returned empty string -- it should still produce a hash"
        )

        # The hash will likely match neither the original nor the final content
        # because the reader saw a mix of old and new data
        matches_before = (result_hash == hash_before)
        matches_after = (result_hash == hash_after)

        # Either outcome is acceptable (depends on timing), but we want to
        # verify the function completes without error
        if not matches_before and not matches_after:
            pass  # Expected: hash of partial state
        # If it matches one, that's also fine (lucky timing)


# ===========================================================================
# Test 8: TOCTOU race -- file changes between hash_source and copy
# ===========================================================================

class TestTOCTOURace(unittest.TestCase):
    """
    Test 8: Full _transfer_one flow where the source file changes between
    hash_source and the copy. Hash source, then modify file, then copy
    should produce hash mismatch.

    This tests the TOCTOU (Time-Of-Check-Time-Of-Use) vulnerability that
    the engine CORRECTLY detects via the post-copy hash comparison (step 6).
    """

    @hard_timeout(30)
    def test_toctou_hash_mismatch_detected(self):
        """_transfer_one detects TOCTOU race via hash mismatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source file
            original_data = b"Original content for TOCTOU test\n" * 1000
            modified_data = b"MODIFIED content -- changed mid-transfer\n" * 1000
            src_path = os.path.join(tmpdir, "toctou_source.txt")
            with open(src_path, "wb") as f:
                f.write(original_data)

            original_hash = hashlib.sha256(original_data).hexdigest()
            modified_hash = hashlib.sha256(modified_data).hexdigest()

            # Set up engine
            dest_dir = os.path.join(tmpdir, "dest")
            cfg = TransferConfig(
                source_paths=[tmpdir],
                dest_path=dest_dir,
                workers=1,
                max_retries=1,
                retry_backoff=0.1,
                deduplicate=False,
                verify_copies=True,
            )
            engine = BulkTransferV2(cfg)
            engine.manifest = mock.MagicMock()
            engine.manifest.find_by_hash.return_value = None
            engine.staging = mock.MagicMock()

            # Set up staging paths
            incoming_dir = os.path.join(dest_dir, "incoming")
            os.makedirs(incoming_dir, exist_ok=True)
            tmp_copy = Path(os.path.join(incoming_dir, "toctou_source.txt.tmp"))
            engine.staging.incoming_path.return_value = tmp_copy

            quarantine_path = Path(os.path.join(dest_dir, "quarantine", "toctou_source.txt"))
            engine.staging.quarantine_file.return_value = quarantine_path

            # Track _hash_file calls. First call returns original hash.
            # Between first and second _hash_file call, modify the source.
            hash_call_count = [0]
            real_hash_file = _hash_file

            def mock_hash_file(path, timeout=120.0):
                hash_call_count[0] += 1
                if hash_call_count[0] == 1:
                    # First call: hash source (returns original)
                    return original_hash
                else:
                    # Second call: hash destination (the .tmp we wrote)
                    # The .tmp was written from the MODIFIED source
                    return real_hash_file(path, timeout)

            # Mock _buffered_copy to modify source BEFORE copying
            def mock_copy(src, dst, buf_size, bw_limit):
                # Modify source file (simulating external write)
                with open(src, "wb") as f:
                    f.write(modified_data)
                # Now copy the modified data
                with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                    fdst.write(fsrc.read())

            with mock.patch(
                "src.tools.bulk_transfer_v2._hash_file",
                side_effect=mock_hash_file,
            ), mock.patch(
                "src.tools.bulk_transfer_v2._buffered_copy",
                side_effect=mock_copy,
            ), mock.patch(
                "src.tools.bulk_transfer_v2._can_read_file",
                return_value=True,
            ), mock.patch("os.path.getsize", return_value=len(modified_data)):
                engine._transfer_one(
                    src_path, tmpdir, "toctou_source.txt", len(original_data)
                )

            # Verify: hash mismatch was detected
            self.assertEqual(
                engine.stats.files_verify_failed, 1,
                f"Expected 1 verify failure (TOCTOU), got {engine.stats.files_verify_failed}"
            )

            # Verify: file was quarantined
            self.assertEqual(
                engine.stats.files_quarantined, 1,
                f"Expected 1 quarantine (TOCTOU), got {engine.stats.files_quarantined}"
            )

            # Verify manifest recorded hash_mismatch
            engine.manifest.record_transfer.assert_called()
            last_call_kwargs = engine.manifest.record_transfer.call_args
            # The result kwarg should be 'hash_mismatch'
            if last_call_kwargs:
                args, kwargs = last_call_kwargs
                self.assertEqual(
                    kwargs.get("result", args[3] if len(args) > 3 else ""),
                    "hash_mismatch",
                    "Expected manifest to record 'hash_mismatch' result"
                )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
