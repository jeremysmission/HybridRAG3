# ============================================================================
# HybridRAG -- Filesystem Edge Case Regression Tests
# ============================================================================
# Destructive QA: tries to BREAK the bulk transfer engine by targeting
# each of the 11 recent fixes with adversarial filesystem scenarios.
#
# Run: python -m pytest tests/retest_filesystem_edges.py -v
# ============================================================================

import hashlib
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest import mock

import pytest

# Ensure project root is importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tools.bulk_transfer_v2 import (
    BulkTransferV2,
    TransferConfig,
    TransferStats,
    _ALWAYS_SKIP,
    _hash_file,
    _can_read_file,
    _buffered_copy,
    _stat_with_timeout,
)
from src.tools.transfer_manifest import TransferManifest
from src.tools.transfer_staging import StagingManager


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tmp_dirs(tmp_path):
    """Create source and destination directories for each test."""
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    dst.mkdir()
    return src, dst


def _make_file(path, size=200, content=None):
    """Create a test file with specified size or content."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        p.write_bytes(content)
    else:
        p.write_bytes(os.urandom(size))
    return p


def _sha256(path):
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(131072), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_transfer(src, dst, **kwargs):
    """Run a minimal bulk transfer and return (engine, stats)."""
    cfg = TransferConfig(
        source_paths=[str(src)],
        dest_path=str(dst),
        workers=kwargs.pop("workers", 1),
        resume=kwargs.pop("resume", False),
        deduplicate=kwargs.pop("deduplicate", True),
        verify_copies=kwargs.pop("verify_copies", True),
        min_file_size=kwargs.pop("min_file_size", 1),
        max_file_size=kwargs.pop("max_file_size", 500_000_000),
    )
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    engine = BulkTransferV2(cfg)
    stats = engine.run()
    return engine, stats


# ============================================================================
# Test 1: Surrogate filename -- encoding check BEFORE record_source_file
# ============================================================================

class TestSurrogateFilename:
    """
    Fix #1: encoding check now happens BEFORE record_source_file so SQLite
    never sees a surrogate string. The path gets sanitized with errors="replace".
    """

    def test_surrogate_in_filename_no_sqlite_crash(self, tmp_dirs):
        """
        Simulate a file with a name that fails UTF-8 encoding.
        The engine should sanitize the path and record it in the manifest
        (not crash). The file should be skipped with reason 'encoding_issue'.
        """
        src, dst = tmp_dirs

        # Create a normal .txt file
        good_file = _make_file(src / "normal.txt", 300)

        # We cannot create a true surrogate filename on Windows NTFS,
        # so we mock the discovery to inject one. We patch _walk_source
        # to yield a filename that fails .encode("utf-8").
        original_walk = os.walk

        # Create a file with a "bad" name that we'll intercept
        bad_name = "bad\udcff_report.txt"  # Contains a surrogate
        bad_full = os.path.join(str(src), bad_name)

        # Patch os.walk to yield the bad filename alongside the real one
        def fake_walk(top, **kw):
            for dirpath, dirnames, filenames in original_walk(top, **kw):
                # Inject surrogate filename
                if dirpath == str(src):
                    filenames = list(filenames) + [bad_name]
                yield dirpath, dirnames, filenames

        # Also need to mock os.stat for the bad path
        original_stat = os.stat
        fake_stat_result = original_stat(str(good_file))

        def patched_stat(path, *args, **kwargs):
            if bad_name in str(path):
                return fake_stat_result
            return original_stat(path, *args, **kwargs)

        with mock.patch("os.walk", side_effect=fake_walk):
            with mock.patch(
                "src.tools.bulk_transfer_v2._stat_with_timeout",
                side_effect=patched_stat,
            ):
                engine, stats = _run_transfer(src, dst)

        # The engine should NOT have crashed
        assert stats.files_skipped_encoding >= 1, (
            "Surrogate filename should be counted as encoding skip"
        )

        # Check the manifest DB -- the sanitized path should be present
        db_path = os.path.join(str(dst), "_transfer_manifest.db")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT source_path, encoding_issue FROM source_manifest "
            "WHERE encoding_issue=1"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, "Encoding-issue file should appear in manifest"
        # The path should NOT contain surrogates (it should be sanitized)
        for row_path, _ in rows:
            try:
                row_path.encode("utf-8")
            except UnicodeEncodeError:
                pytest.fail(
                    f"Manifest contains unsanitized surrogate path: {row_path!r}"
                )


# ============================================================================
# Test 2: _ALWAYS_SKIP actively blocks .exe, .dll, .mp4
# ============================================================================

class TestAlwaysSkip:
    """
    Fix #3: _ALWAYS_SKIP is now actively checked (not dead code).
    Files with these extensions get reason='always_skip' in skipped_files.
    """

    @pytest.mark.parametrize("ext", [".exe", ".dll", ".mp4"])
    def test_always_skip_extensions(self, tmp_dirs, ext):
        src, dst = tmp_dirs
        _make_file(src / f"malware{ext}", 300)
        _make_file(src / "legit.txt", 300)

        engine, stats = _run_transfer(src, dst)

        # The blocked extension should be skipped
        assert stats.files_skipped_ext >= 1, (
            f"Extension {ext} should be skipped"
        )

        # Verify the reason in the DB
        db_path = os.path.join(str(dst), "_transfer_manifest.db")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT reason FROM skipped_files WHERE reason='always_skip'"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, (
            f"{ext} should produce always_skip reason in skipped_files table"
        )

    def test_always_skip_set_completeness(self):
        """Verify the ALWAYS_SKIP set contains all expected dangerous extensions."""
        expected = {".exe", ".dll", ".sys", ".msi", ".cab", ".iso",
                    ".mp4", ".mp3", ".avi", ".mkv", ".wav", ".flac", ".pst"}
        assert expected == _ALWAYS_SKIP, (
            f"_ALWAYS_SKIP mismatch: missing={expected - _ALWAYS_SKIP}, "
            f"extra={_ALWAYS_SKIP - expected}"
        )


# ============================================================================
# Test 3: TOCTOU race in promote_to_verified -- 8 threads, same dest
# ============================================================================

class TestTOCTOURace:
    """
    Fix #5: threading.Lock in promote_to_verified prevents two threads
    from both seeing exists()=False and overwriting each other.
    """

    def test_8_threads_promote_same_dest_no_data_loss(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))

        # Create 8 .tmp files in incoming, each with unique content
        files = []
        contents = []
        for i in range(8):
            content = f"unique_content_{i}_{os.urandom(16).hex()}".encode()
            rel = "shared/report.txt"
            tmp = staging.incoming_path(rel)
            # Each gets a unique tmp name (because incoming_path appends .tmp)
            actual = tmp.parent / f"report_{i}.txt.tmp"
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(content)
            files.append(actual)
            contents.append(content)

        # All 8 threads promote to the SAME relative path concurrently
        results = [None] * 8
        barrier = threading.Barrier(8)

        def promote(idx):
            barrier.wait()  # Force simultaneous promotion
            results[idx] = staging.promote_to_verified(
                files[idx], "shared/report.txt"
            )

        threads = [threading.Thread(target=promote, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # ALL 8 files must be preserved (no overwrites)
        final_paths = [r for r in results if r is not None]
        assert len(final_paths) == 8, (
            f"Expected 8 promoted files, got {len(final_paths)}"
        )

        # All paths must be unique
        path_set = set(str(p) for p in final_paths)
        assert len(path_set) == 8, (
            f"Expected 8 unique paths, got {len(path_set)} -- data loss via overwrite!"
        )

        # All content must be recoverable
        recovered = set()
        for p in final_paths:
            recovered.add(Path(p).read_bytes())
        assert len(recovered) == 8, (
            "Some file contents were lost during concurrent promotion"
        )


# ============================================================================
# Test 4: os.replace() works even if dest somehow already exists
# ============================================================================

class TestOsReplace:
    """
    Fix #4: os.replace() instead of os.rename() -- works even when dest exists.
    The collision handler (_1, _2 suffix) also prevents silent overwrite.
    """

    def test_replace_with_preexisting_dest(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))

        # Pre-create a file at the verified destination
        preexisting = staging.verified / "docs" / "readme.txt"
        preexisting.parent.mkdir(parents=True, exist_ok=True)
        preexisting.write_bytes(b"old content that must survive")

        # Now promote a new file to the same relative path
        tmp = staging.incoming_path("docs/readme.txt")
        tmp.write_bytes(b"new content from transfer")

        final = staging.promote_to_verified(tmp, "docs/readme.txt")

        # The original must still exist
        assert preexisting.exists(), "Pre-existing file was destroyed!"
        assert preexisting.read_bytes() == b"old content that must survive"

        # The new file should have gotten a _1 suffix
        assert final.exists()
        assert final.read_bytes() == b"new content from transfer"
        assert "_1" in final.name or final != preexisting, (
            "New file should have collision suffix"
        )


# ============================================================================
# Test 5: Resume-skipped files appear in skipped_files table (zero-gap)
# ============================================================================

class TestResumeSkipZeroGap:
    """
    Fix #6: When a file is skipped because it was already_transferred
    in a previous run, it must be logged in skipped_files so the
    zero-gap verification report adds up.
    """

    def test_resume_skip_logged_in_skipped_files(self, tmp_dirs):
        src, dst = tmp_dirs
        _make_file(src / "report.txt", 500)

        # Run 1: transfer everything
        _run_transfer(src, dst, resume=False)

        # Run 2: with resume=True, it should skip report.txt
        engine2, stats2 = _run_transfer(src, dst, resume=True)

        assert stats2.files_skipped_unchanged >= 1, (
            "Resume run should skip already-transferred file"
        )

        # Verify the skip is in the DB
        db_path = os.path.join(str(dst), "_transfer_manifest.db")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT reason FROM skipped_files WHERE reason='already_transferred'"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, (
            "Resume-skipped file must appear in skipped_files table "
            "(zero-gap fix)"
        )


# ============================================================================
# Test 6: Delta analysis uses full source_manifest, not filtered queue
# ============================================================================

class TestDeltaAnalysisFullManifest:
    """
    Fix #7: Delta analysis compares against the FULL source_manifest
    (all discovered files) rather than just the transfer queue. This means
    deletion detection works for ALL file types, even non-RAG ones.
    """

    def test_delta_detects_deletion_of_non_rag_file(self, tmp_dirs):
        src, dst = tmp_dirs
        # Run 1: source has a .txt and a .xyz (unsupported)
        _make_file(src / "keep.txt", 300)
        _make_file(src / "data.xyz", 300)

        engine1, stats1 = _run_transfer(src, dst, resume=False)

        # Both should be in the manifest (even .xyz which is unsupported)
        db_path = os.path.join(str(dst), "_transfer_manifest.db")
        conn = sqlite3.connect(db_path)
        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM source_manifest WHERE run_id=?",
            (engine1.run_id,),
        ).fetchone()[0]
        conn.close()
        assert manifest_count == 2, (
            "Both files (including unsupported .xyz) should be in manifest"
        )

        # Sleep 1.1s so the next run gets a different run_id
        # (run_id is timestamp at second resolution: %Y%m%d_%H%M%S)
        time.sleep(1.1)

        # Run 2: delete the .xyz from source
        os.remove(str(src / "data.xyz"))
        engine2, stats2 = _run_transfer(src, dst, resume=False)

        # Delta should detect the deletion
        assert stats2.files_delta_deleted >= 1, (
            "Delta analysis should detect deletion of .xyz file "
            "even though it was never in the transfer queue"
        )


# ============================================================================
# Test 7: Dedup race -- 4 threads with same hash, only 1 copy
# ============================================================================

class TestDedupRace:
    """
    Fix #8: In-memory _dedup_seen set with lock prevents multiple threads
    from all bypassing find_by_hash() simultaneously.
    """

    def test_4_threads_same_content_only_1_copy(self, tmp_dirs):
        src, dst = tmp_dirs

        # Create 4 files with IDENTICAL content in different directories
        content = b"IDENTICAL_PAYLOAD_" + os.urandom(200)
        for i in range(4):
            subdir = src / f"dir{i}"
            _make_file(subdir / "same.txt", content=content)

        engine, stats = _run_transfer(src, dst, workers=4, deduplicate=True)

        # Only 1 should be copied, 3 should be deduplicated
        assert stats.files_copied == 1, (
            f"Expected 1 copy, got {stats.files_copied}"
        )
        assert stats.files_deduplicated == 3, (
            f"Expected 3 deduplicated, got {stats.files_deduplicated}"
        )


# ============================================================================
# Test 8: safe_path used for all manifest calls when encoding_issue=True
# ============================================================================

class TestSafePathManifestCalls:
    """
    Fix #9: When encoding_issue=True, ALL manifest calls must use the
    sanitized safe_path, not the raw path with surrogates.
    """

    def test_safe_path_used_for_skip_and_source_record(self, tmp_dirs):
        src, dst = tmp_dirs
        _make_file(src / "normal.txt", 300)

        # Intercept record_source_file and record_skip to verify
        # they receive sanitized paths (no surrogates).
        recorded_paths = {"source": [], "skip": []}

        original_walk = os.walk
        bad_name = "report_\udcfe.txt"
        bad_full = os.path.join(str(src), bad_name)

        def fake_walk(top, **kw):
            for dirpath, dirnames, filenames in original_walk(top, **kw):
                if dirpath == str(src):
                    filenames = list(filenames) + [bad_name]
                yield dirpath, dirnames, filenames

        original_stat = os.stat
        fake_result = original_stat(str(src / "normal.txt"))

        def patched_stat(path, *args, **kwargs):
            if bad_name.encode("utf-8", errors="replace").decode("utf-8") in str(path) or "\udcfe" in str(path):
                return fake_result
            return original_stat(path, *args, **kwargs)

        original_record_source = TransferManifest.record_source_file
        original_record_skip = TransferManifest.record_skip

        def track_source(self_m, run_id, source_path, **kw):
            recorded_paths["source"].append(source_path)
            return original_record_source(self_m, run_id, source_path, **kw)

        def track_skip(self_m, run_id, source_path, *a, **kw):
            recorded_paths["skip"].append(source_path)
            return original_record_skip(self_m, run_id, source_path, *a, **kw)

        with mock.patch("os.walk", side_effect=fake_walk), \
             mock.patch("src.tools.bulk_transfer_v2._stat_with_timeout",
                        side_effect=patched_stat), \
             mock.patch.object(TransferManifest, "record_source_file",
                               side_effect=track_source, autospec=True), \
             mock.patch.object(TransferManifest, "record_skip",
                               side_effect=track_skip, autospec=True):
            _run_transfer(src, dst)

        # Verify NO path contains surrogates
        all_paths = recorded_paths["source"] + recorded_paths["skip"]
        for p in all_paths:
            try:
                p.encode("utf-8")
            except UnicodeEncodeError:
                pytest.fail(
                    f"Manifest received unsanitized surrogate path: {p!r}"
                )


# ============================================================================
# Test 9: Transfer manifest close() with pending writes doesn't crash
# ============================================================================

class TestManifestCloseWithPending:
    """
    Fix #10: close() uses try/finally so even if commit() raises,
    the connection still closes cleanly.
    """

    def test_close_with_pending_writes_no_crash(self, tmp_path):
        db_path = str(tmp_path / "test_manifest.db")
        manifest = TransferManifest(db_path)
        manifest.start_run("test_run", ["/src"], "/dst")

        # Write some records WITHOUT flushing
        for i in range(10):
            manifest.record_source_file(
                "test_run", f"/src/file_{i}.txt",
                file_size=100, extension=".txt",
            )

        # Pending writes should be > 0 (we wrote 10 without hitting 50)
        assert manifest._pending_writes > 0, (
            "Expected pending writes before close"
        )

        # close() should NOT crash
        manifest.close()

        # Re-open and verify data was committed
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM source_manifest WHERE run_id='test_run'"
        ).fetchone()[0]
        conn.close()

        assert count == 10, f"Expected 10 records after close(), got {count}"

    def test_close_after_connection_error_no_crash(self, tmp_path):
        """
        If the connection is in a bad state, close() should still succeed
        (try/finally ensures conn.close() runs even if commit() throws).
        We simulate this by patching the manifest's close method to use
        a wrapper that makes commit() fail, verifying the try/finally
        still calls conn.close().
        """
        db_path = str(tmp_path / "test_manifest2.db")
        manifest = TransferManifest(db_path)
        manifest.start_run("run2", ["/src"], "/dst")
        manifest.record_source_file("run2", "/src/a.txt", file_size=100)

        # sqlite3.Connection.commit is read-only, so we cannot monkey-patch
        # it directly. Instead, replace conn with a wrapper that raises on
        # commit() but still delegates close().
        real_conn = manifest.conn

        class FakeConn:
            """Proxy that makes commit() raise once, then delegates."""
            def __init__(self, real):
                self._real = real
                self._commit_calls = 0

            def commit(self):
                self._commit_calls += 1
                if self._commit_calls == 1:
                    raise sqlite3.OperationalError(
                        "disk I/O error (simulated)"
                    )
                self._real.commit()

            def close(self):
                self._real.close()

            def __getattr__(self, name):
                return getattr(self._real, name)

        manifest.conn = FakeConn(real_conn)

        # close() must not raise even though commit() throws
        manifest.close()


# ============================================================================
# Test 10: Quarantine collision -- 3 files quarantined to same dest_rel
# ============================================================================

class TestQuarantineCollision:
    """
    Fix: quarantine_file uses the same collision-avoidance (_1, _2 suffix)
    as promote_to_verified.
    """

    def test_3_files_quarantined_to_same_rel_all_preserved(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))

        quarantined_paths = []
        for i in range(3):
            content = f"quarantine_content_{i}".encode()
            tmp = staging.incoming / "docs" / f"report_{i}.txt.tmp"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(content)

            dest = staging.quarantine_file(
                tmp, "docs/report.txt",
                reason=f"Hash mismatch #{i}"
            )
            quarantined_paths.append(dest)

        # All 3 must exist as separate files
        assert len(quarantined_paths) == 3
        for p in quarantined_paths:
            assert p.exists(), f"Quarantined file missing: {p}"

        # All paths must be unique
        path_set = set(str(p) for p in quarantined_paths)
        assert len(path_set) == 3, (
            f"Expected 3 unique quarantine paths, got {len(path_set)}"
        )

        # Verify content integrity
        contents = set()
        for p in quarantined_paths:
            contents.add(p.read_bytes())
        assert len(contents) == 3, "Some quarantine content was lost"


# ============================================================================
# Test 11: UnicodeEncodeError in _walk_source is caught
# ============================================================================

class TestWalkSourceUnicodeError:
    """
    Fix #2: UnicodeEncodeError added to _walk_source exception handler
    so the walk doesn't crash on encoding issues.
    """

    def test_unicode_encode_error_caught_in_walk(self, tmp_dirs):
        src, dst = tmp_dirs
        _make_file(src / "good.txt", 300)

        # Patch _process_discovery to throw UnicodeEncodeError for the
        # second file it encounters
        call_count = [0]
        original_process = BulkTransferV2._process_discovery

        def bombing_process(self_eng, full, source_root, queue):
            call_count[0] += 1
            if call_count[0] == 2:
                # UnicodeEncodeError(encoding, object, start, end, reason)
                # 'object' must be str (the string that failed to encode)
                raise UnicodeEncodeError(
                    "utf-8", "\udcff", 0, 1,
                    "surrogates not allowed"
                )
            return original_process(self_eng, full, source_root, queue)

        # Add a second file that will trigger the bomb
        _make_file(src / "also_good.txt", 300)

        with mock.patch.object(
            BulkTransferV2, "_process_discovery",
            side_effect=bombing_process, autospec=True,
        ):
            engine, stats = _run_transfer(src, dst)

        # Walk must NOT crash -- at least one file should be processed
        assert stats.files_discovered >= 2, (
            "Walk should have discovered both files (even if one errored)"
        )
        assert stats.files_skipped_inaccessible >= 1, (
            "UnicodeEncodeError should be counted as inaccessible"
        )


# ============================================================================
# Test 12: cleanup_incoming removes .tmp files
# ============================================================================

class TestCleanupIncoming:
    """
    Verify that cleanup_incoming() finds and removes all .tmp files
    from the incoming directory, including nested ones.
    """

    def test_cleanup_removes_all_tmp_files(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))

        # Scatter .tmp files at various depths
        (staging.incoming / "a.txt.tmp").write_bytes(b"leftover1")
        nested = staging.incoming / "deep" / "nested" / "dir"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "b.pdf.tmp").write_bytes(b"leftover2")
        (staging.incoming / "c.docx.tmp").write_bytes(b"leftover3")

        # Also place a NON-.tmp file that should NOT be deleted
        (staging.incoming / "legit_file.txt").write_bytes(b"keep me")

        count = staging.cleanup_incoming()

        assert count == 3, f"Expected 3 .tmp files removed, got {count}"

        # Verify .tmp files are gone
        remaining = list(staging.incoming.rglob("*.tmp"))
        assert len(remaining) == 0, f"Leftover .tmp files: {remaining}"

        # Verify non-.tmp file survived
        assert (staging.incoming / "legit_file.txt").exists(), (
            "cleanup_incoming deleted a non-.tmp file!"
        )

    def test_cleanup_returns_zero_on_empty_incoming(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))
        count = staging.cleanup_incoming()
        assert count == 0


# ============================================================================
# BONUS: idx_skipped_run index exists
# ============================================================================

class TestMissingIndex:
    """
    Fix #11: idx_skipped_run index was missing, now added.
    """

    def test_idx_skipped_run_index_exists(self, tmp_path):
        db_path = str(tmp_path / "test_idx.db")
        manifest = TransferManifest(db_path)

        # Query SQLite's index list
        rows = manifest.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        manifest.close()

        index_names = {r[0] for r in rows}
        assert "idx_skipped_run" in index_names, (
            f"idx_skipped_run index is missing! Found: {index_names}"
        )


# ============================================================================
# BONUS: Concurrent quarantine (threaded, like TOCTOU test but for quarantine)
# ============================================================================

class TestConcurrentQuarantine:
    """
    Threaded quarantine: 8 threads quarantine to the same dest_rel.
    """

    def test_8_threads_quarantine_same_dest_all_preserved(self, tmp_path):
        staging = StagingManager(str(tmp_path / "stage"))

        files = []
        contents = []
        for i in range(8):
            content = f"quar_content_{i}_{os.urandom(8).hex()}".encode()
            tmp = staging.incoming / "shared" / f"quar_{i}.tmp"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(content)
            files.append(tmp)
            contents.append(content)

        results = [None] * 8
        barrier = threading.Barrier(8)

        def do_quarantine(idx):
            barrier.wait()
            results[idx] = staging.quarantine_file(
                files[idx], "shared/data.bin",
                reason=f"Test reason {idx}",
            )

        threads = [
            threading.Thread(target=do_quarantine, args=(i,))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        final_paths = [r for r in results if r is not None]
        assert len(final_paths) == 8, (
            f"Expected 8 quarantined files, got {len(final_paths)}"
        )

        # All unique
        path_set = set(str(p) for p in final_paths)
        assert len(path_set) == 8

        # All content recoverable
        recovered = set()
        for p in final_paths:
            recovered.add(Path(p).read_bytes())
        assert len(recovered) == 8


# ============================================================================
# BONUS: End-to-end zero-gap verification
# ============================================================================

class TestZeroGapEndToEnd:
    """
    After a transfer with mixed file types (some copied, some skipped),
    the verification report must show GAP=0.
    """

    def test_zero_gap_with_mixed_file_types(self, tmp_dirs):
        src, dst = tmp_dirs

        # Create a variety of file types
        _make_file(src / "doc.txt", 300)       # Will be copied
        _make_file(src / "sheet.csv", 300)     # Will be copied
        _make_file(src / "virus.exe", 300)     # Will be always_skip
        _make_file(src / "movie.mp4", 300)     # Will be always_skip
        _make_file(src / "unknown.xyz", 300)   # Will be unsupported_extension
        _make_file(src / "tiny.txt", 10)       # Will be too_small (min=100)

        engine, stats = _run_transfer(
            src, dst, min_file_size=100, resume=False,
        )

        # Check the verification report for ZERO-GAP
        db_path = os.path.join(str(dst), "_transfer_manifest.db")
        conn = sqlite3.connect(db_path)

        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM source_manifest WHERE run_id=?",
            (engine.run_id,),
        ).fetchone()[0]

        transfer_count = conn.execute(
            "SELECT COUNT(*) FROM transfer_log WHERE run_id=?",
            (engine.run_id,),
        ).fetchone()[0]

        skip_count = conn.execute(
            "SELECT COUNT(*) FROM skipped_files WHERE run_id=?",
            (engine.run_id,),
        ).fetchone()[0]

        conn.close()

        accounted = transfer_count + skip_count
        gap = manifest_count - accounted
        assert gap == 0, (
            f"ZERO-GAP VIOLATED: manifest={manifest_count}, "
            f"transferred={transfer_count}, skipped={skip_count}, gap={gap}"
        )
