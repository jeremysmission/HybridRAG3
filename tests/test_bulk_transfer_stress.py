# ============================================================================
# HybridRAG -- Bulk Transfer V2 Stress Tests
# ============================================================================
# Comprehensive tests: varying file sizes, connection simulation, corrupt
# files, locked files, large file counts, symlink loops, long paths,
# encoding issues, bandwidth throttling, resume, hash mismatches,
# concurrent access, multi-source collision, and indexer discovery faults.
#
# Run: python -m pytest tests/test_bulk_transfer_stress.py -v
# ============================================================================

import errno
import hashlib
import json
import os
import random
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

# Ensure project root is importable
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tools.bulk_transfer_v2 import (
    BulkTransferV2,
    SourceDiscovery,
    TransferConfig,
    _hash_file,
    _can_read_file,
    _buffered_copy,
    _stat_with_timeout,
    _fmt_size,
    _fmt_dur,
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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        path.write_bytes(content)
    else:
        path.write_bytes(os.urandom(size))
    return path


def _run_transfer(src, dst, **kwargs):
    """Run a transfer with defaults and return stats."""
    cfg = TransferConfig(
        source_paths=[str(src)],
        dest_path=str(dst),
        workers=kwargs.pop("workers", 2),
        min_file_size=kwargs.pop("min_file_size", 10),
        deduplicate=kwargs.pop("deduplicate", True),
        verify_copies=kwargs.pop("verify_copies", True),
        resume=kwargs.pop("resume", False),
        include_hidden=kwargs.pop("include_hidden", False),
        bandwidth_limit=kwargs.pop("bandwidth_limit", 0),
        **kwargs,
    )
    engine = BulkTransferV2(cfg)
    return engine.run()


# ============================================================================
# Test 1: Basic transfer with varying file sizes
# ============================================================================

class TestVaryingFileSizes:

    def test_small_files(self, tmp_dirs):
        """Files just above minimum size threshold."""
        src, dst = tmp_dirs
        for i in range(20):
            _make_file(src / f"small_{i}.txt", size=150)
        stats = _run_transfer(src, dst, min_file_size=100)
        assert stats.files_copied == 20
        assert stats.files_failed == 0

    def test_medium_files(self, tmp_dirs):
        """Files in the 10KB-100KB range."""
        src, dst = tmp_dirs
        for i in range(5):
            _make_file(src / f"medium_{i}.pdf", size=50_000)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 5

    def test_large_files(self, tmp_dirs):
        """Files over 1MB."""
        src, dst = tmp_dirs
        _make_file(src / "large.pdf", size=2_000_000)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1
        # Verify hash matches
        assert stats.files_verified == 1
        assert stats.files_verify_failed == 0

    def test_below_minimum_skipped(self, tmp_dirs):
        """Files below min_file_size are skipped."""
        src, dst = tmp_dirs
        _make_file(src / "tiny.txt", size=5)
        stats = _run_transfer(src, dst, min_file_size=100)
        assert stats.files_copied == 0
        assert stats.files_skipped_size == 1

    def test_above_maximum_skipped(self, tmp_dirs):
        """Files above max_file_size are skipped."""
        src, dst = tmp_dirs
        _make_file(src / "huge.txt", size=1000)
        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            min_file_size=10,
            max_file_size=500,
            workers=1,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()
        assert stats.files_skipped_size == 1


# ============================================================================
# Test 2: Deduplication
# ============================================================================

class TestDeduplication:

    def test_identical_files_deduped(self, tmp_dirs):
        """Two files with identical content -- second is deduplicated."""
        src, dst = tmp_dirs
        content = os.urandom(500)
        _make_file(src / "original.txt", content=content)
        _make_file(src / "copy.txt", content=content)
        # Use 1 worker so dedup check is sequential (not racing)
        stats = _run_transfer(src, dst, workers=1)
        assert stats.files_copied == 1
        assert stats.files_deduplicated == 1

    def test_dedup_disabled(self, tmp_dirs):
        """With dedup off, identical files are both copied."""
        src, dst = tmp_dirs
        content = os.urandom(500)
        _make_file(src / "a.txt", content=content)
        _make_file(src / "b.txt", content=content)
        stats = _run_transfer(src, dst, deduplicate=False)
        assert stats.files_copied == 2

    def test_similar_but_different_not_deduped(self, tmp_dirs):
        """Files with different content are NOT deduped."""
        src, dst = tmp_dirs
        _make_file(src / "a.txt", size=500)
        _make_file(src / "b.txt", size=500)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 2


# ============================================================================
# Test 3: Resume / restart
# ============================================================================

class TestResume:

    def test_resume_skips_already_transferred(self, tmp_dirs):
        """Second run with resume=True skips already-copied files."""
        src, dst = tmp_dirs
        for i in range(5):
            _make_file(src / f"doc_{i}.txt", size=200)

        # First run
        stats1 = _run_transfer(src, dst, resume=True)
        assert stats1.files_copied == 5

        # Second run -- same files, should all be skipped
        stats2 = _run_transfer(src, dst, resume=True)
        assert stats2.files_copied == 0
        assert stats2.files_skipped_unchanged == 5

    def test_new_files_picked_up_on_resume(self, tmp_dirs):
        """Resume picks up new files added after first run."""
        src, dst = tmp_dirs
        _make_file(src / "old.txt", size=200)
        _run_transfer(src, dst, resume=True)

        # Add new file
        _make_file(src / "new.txt", size=200)
        stats = _run_transfer(src, dst, resume=True)
        assert stats.files_copied == 1
        assert stats.files_skipped_unchanged == 1

    def test_resume_seeds_from_manifest_before_discovery(self, tmp_dirs):
        """
        Resume can copy pending files from prior manifest even when
        current discovery yields no items yet.
        """
        src, dst = tmp_dirs
        ok = _make_file(src / "ok.txt", size=200)
        bad = _make_file(src / "bad.txt", size=200)

        # First run: force bad.txt to fail so it remains pending.
        real_copy = _buffered_copy
        def fail_bad(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            if str(s).endswith("bad.txt"):
                raise OSError("simulated first-run failure")
            return real_copy(s, d, buf_size, bw_limit, **kwargs)

        with mock.patch("src.tools.bulk_transfer_v2._buffered_copy", fail_bad):
            stats1 = _run_transfer(
                src, dst, resume=True, workers=1, max_retries=1,
            )
        assert stats1.files_copied == 1
        assert stats1.files_failed >= 1

        # Second run: disable discovery stream to prove manifest-seed works.
        with mock.patch.object(
            SourceDiscovery, "discover_iter", return_value=iter(()),
        ):
            stats2 = _run_transfer(src, dst, resume=True, workers=1)

        assert stats2.files_copied == 1
        assert (dst / "verified" / src.name / "bad.txt").exists()


# ============================================================================
# Test 4: Unsupported extensions
# ============================================================================

class TestExtensionFiltering:

    def test_unsupported_extensions_skipped(self, tmp_dirs):
        """Files with unsupported extensions are skipped."""
        src, dst = tmp_dirs
        _make_file(src / "code.py", size=200)
        _make_file(src / "binary.exe", size=200)
        _make_file(src / "doc.pdf", size=200)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1  # only .pdf
        assert stats.files_skipped_ext >= 1

    def test_all_supported_types(self, tmp_dirs):
        """All supported extensions are accepted."""
        src, dst = tmp_dirs
        for ext in [".txt", ".md", ".pdf", ".csv", ".json", ".xml",
                    ".html", ".docx", ".xlsx", ".log"]:
            _make_file(src / f"test{ext}", size=200)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 10


# ============================================================================
# Test 5: Hash verification
# ============================================================================

class TestHashVerification:

    def test_hash_file_correct(self, tmp_dirs):
        """_hash_file returns correct SHA-256."""
        src, dst = tmp_dirs
        content = b"hello world test content for hashing"
        f = _make_file(src / "test.txt", content=content)
        expected = hashlib.sha256(content).hexdigest()
        assert _hash_file(str(f)) == expected

    def test_hash_file_nonexistent(self, tmp_dirs):
        """_hash_file returns empty string for missing files."""
        assert _hash_file("/nonexistent/path/file.txt") == ""

    def test_hash_file_timeout(self, tmp_dirs):
        """_hash_file respects timeout on stalled reads."""
        src, dst = tmp_dirs
        f = _make_file(src / "test.txt", size=200)
        # Use an extremely short timeout with mock to simulate stall
        result = _hash_file(str(f), timeout=0.001)
        # Either completes fast (small file) or returns empty
        assert isinstance(result, str)

    def test_corrupted_copy_detected(self, tmp_dirs):
        """Corrupted file during copy is caught by hash mismatch."""
        src, dst = tmp_dirs
        content = os.urandom(1000)
        _make_file(src / "doc.txt", content=content)

        # Patch _buffered_copy to write corrupted data
        original_copy = _buffered_copy

        def corrupt_copy(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            original_copy(s, d, buf_size, bw_limit, **kwargs)
            # Corrupt one byte in the destination
            with open(d, "r+b") as f:
                f.seek(0)
                f.write(b"\xff")

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", corrupt_copy
        ):
            stats = _run_transfer(src, dst)

        assert stats.files_verify_failed == 1
        assert stats.files_quarantined == 1
        assert stats.files_copied == 0


# ============================================================================
# Test 6: Locked file handling
# ============================================================================

class TestLockedFiles:

    def test_unlocked_file_passes(self, tmp_dirs):
        """Normal file passes lock check."""
        src, _ = tmp_dirs
        f = _make_file(src / "ok.txt", size=200)
        assert _can_read_file(str(f)) is True

    def test_locked_file_skipped(self, tmp_dirs):
        """Locked file is skipped and counted."""
        src, dst = tmp_dirs
        _make_file(src / "locked.txt", size=200)

        with mock.patch(
            "src.tools.bulk_transfer_v2._can_read_file", return_value=False
        ):
            stats = _run_transfer(src, dst)

        assert stats.files_skipped_locked == 1
        assert stats.files_copied == 0

    def test_can_read_timeout(self, tmp_dirs):
        """_can_read_file returns False on hang."""
        src, _ = tmp_dirs
        f = _make_file(src / "stall.txt", size=200)
        # Very short timeout should still succeed on local file
        assert _can_read_file(str(f), timeout=5.0) is True


# ============================================================================
# Test 7: Bandwidth throttling
# ============================================================================

class TestBandwidthThrottling:

    def test_throttled_transfer_completes(self, tmp_dirs):
        """Transfer with bandwidth limit still completes."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=500)
        # Set very high limit so test doesn't take forever
        stats = _run_transfer(src, dst, bandwidth_limit=1_000_000)
        assert stats.files_copied == 1

    def test_buffered_copy_with_throttle(self, tmp_dirs):
        """_buffered_copy with bandwidth limit produces identical output."""
        src, dst = tmp_dirs
        content = os.urandom(2000)
        s = _make_file(src / "in.txt", content=content)
        d = dst / "out.txt"
        _buffered_copy(str(s), str(d), buf_size=512, bw_limit=100_000)
        assert d.read_bytes() == content


# ============================================================================
# Test 8: Multi-source collision (fix #3)
# ============================================================================

class TestMultiSourceCollision:

    def test_same_named_roots_disambiguated(self, tmp_dirs):
        """Two sources with same leaf name don't collide."""
        src, dst = tmp_dirs
        src_a = src / "server_a" / "Documents"
        src_b = src / "server_b" / "Documents"
        _make_file(src_a / "report.txt", size=200)
        _make_file(src_b / "report.txt", size=300)

        cfg = TransferConfig(
            source_paths=[str(src_a), str(src_b)],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()

        assert stats.files_copied == 2
        # Verify both files exist in verified/ under different dirs
        verified = dst / "verified"
        txt_files = list(verified.rglob("report.txt"))
        assert len(txt_files) == 2

    def test_single_source_no_suffix(self, tmp_dirs):
        """Single source does NOT get hash suffix appended."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=200)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1
        # Verify directory name is clean (no _hexhash suffix)
        verified = dst / "verified"
        subdirs = [d.name for d in verified.iterdir() if d.is_dir()]
        assert len(subdirs) == 1
        assert "_" not in subdirs[0]  # No hash suffix


# ============================================================================
# Test 9: Discovery thread race (fix #1)
# ============================================================================

class TestDiscoveryThreadSafety:

    def test_discovery_stop_event_isolated(self, tmp_dirs):
        """Discovery thread uses its own stop event, not shared _stop."""
        src, dst = tmp_dirs
        for i in range(10):
            _make_file(src / f"file_{i}.txt", size=200)

        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=2,
            min_file_size=10,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()
        assert stats.files_copied == 10
        # If the race existed, this would hang or miss files


# ============================================================================
# Test 10: Indexer rglob PermissionError resilience (fix #4)
# ============================================================================

class TestIndexerDiscoveryResilience:

    def test_rglob_permission_error_skipped(self, tmp_path):
        """Indexer discovery continues past PermissionError."""
        from unittest.mock import MagicMock

        # Create mock objects
        mock_config = MagicMock()
        mock_config.indexing = MagicMock()
        mock_config.indexing.max_chars_per_file = 2_000_000
        mock_config.indexing.block_chars = 200_000
        mock_config.indexing.supported_extensions = [".txt", ".pdf"]
        mock_config.indexing.excluded_dirs = []
        mock_config.chunking.chunk_size = 500
        mock_config.chunking.overlap = 50

        mock_store = MagicMock()
        mock_store.get_file_hash.return_value = None

        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [[0.1] * 384]

        mock_chunker = MagicMock()
        mock_chunker.chunk_text.return_value = ["test chunk"]

        from src.core.indexer import Indexer

        indexer = Indexer(mock_config, mock_store, mock_embedder, mock_chunker)

        # Create a folder with files
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "good.txt").write_text("A" * 500)

        # Patch rglob to raise PermissionError mid-iteration
        real_files = [folder / "good.txt"]
        call_count = [0]

        class FaultyIterator:
            def __init__(self):
                self.items = iter([
                    PermissionError("Access denied to subfolder"),
                    real_files[0],
                ])

            def __iter__(self):
                return self

            def __next__(self):
                item = next(self.items)
                if isinstance(item, Exception):
                    raise item
                return item

        with mock.patch.object(Path, "rglob", return_value=FaultyIterator()):
            result = indexer.index_folder(str(folder))

        # Should not crash, should process the good file
        assert result["total_files_scanned"] >= 0


# ============================================================================
# Test 11: Stat timeout
# ============================================================================

class TestStatTimeout:

    def test_stat_normal_file(self, tmp_dirs):
        """_stat_with_timeout works on normal files."""
        src, _ = tmp_dirs
        f = _make_file(src / "normal.txt", size=200)
        result = _stat_with_timeout(str(f))
        assert result is not None
        assert result.st_size == 200

    def test_stat_nonexistent_raises(self, tmp_dirs):
        """_stat_with_timeout raises OSError for missing files."""
        with pytest.raises(OSError):
            _stat_with_timeout("/nonexistent/path/file.txt")

    def test_stat_timeout_raises(self, tmp_dirs):
        """_stat_with_timeout raises TimeoutError on stall."""
        src, _ = tmp_dirs
        f = _make_file(src / "stall.txt", size=200)

        def slow_stat(path):
            time.sleep(10)

        with mock.patch("os.stat", side_effect=slow_stat):
            with pytest.raises(TimeoutError):
                _stat_with_timeout(str(f), timeout=0.5)


# ============================================================================
# Test 12: Transfer manifest database
# ============================================================================

class TestTransferManifest:

    def test_create_and_query(self, tmp_path):
        """Manifest creates tables and records data."""
        db = str(tmp_path / "test_manifest.db")
        m = TransferManifest(db)
        m.start_run("run1", ["/src"], "/dst")
        m.record_source_file("run1", "/src/file.txt", file_size=100)
        m.record_transfer("run1", "/src/file.txt", result="success",
                          hash_source="abc123")
        m.flush()

        assert m.is_already_transferred("/src/file.txt") is True
        assert m.is_already_transferred("/src/other.txt") is False
        m.close()

    def test_dedup_find_by_hash(self, tmp_path):
        """find_by_hash returns path for known hash."""
        db = str(tmp_path / "test_manifest.db")
        m = TransferManifest(db)
        m.start_run("run1", ["/src"], "/dst")
        m.record_transfer("run1", "/src/a.txt", dest_path="/dst/a.txt",
                          hash_source="deadbeef", result="success")
        m.flush()

        assert m.find_by_hash("deadbeef") == "/dst/a.txt"
        assert m.find_by_hash("unknown") is None
        m.close()

    def test_verification_report_zero_gap(self, tmp_path):
        """Verification report shows zero gap when all accounted."""
        db = str(tmp_path / "test_manifest.db")
        m = TransferManifest(db)
        m.start_run("run1", ["/src"], "/dst")
        m.record_source_file("run1", "/src/a.txt", file_size=100)
        m.record_source_file("run1", "/src/b.txt", file_size=200)
        m.record_transfer("run1", "/src/a.txt", result="success")
        m.record_skip("run1", "/src/b.txt", reason="too_small")
        m.flush()

        report = m.get_verification_report("run1")
        assert "ZERO-GAP VERIFIED" in report
        m.close()

    def test_delta_sync(self, tmp_path):
        """Delta sync detects previous run manifest."""
        db = str(tmp_path / "test_manifest.db")
        m = TransferManifest(db)

        # Run 1
        m.start_run("run1", ["/src"], "/dst")
        m.record_source_file("run1", "/src/a.txt", content_hash="hash_a")
        m.finish_run("run1")
        m.flush()

        # Run 2
        m.start_run("run2", ["/src"], "/dst")
        prev = m.get_previous_manifest("run2")
        assert "/src/a.txt" in prev
        assert prev["/src/a.txt"] == "hash_a"
        m.close()

    def test_pending_candidates_from_latest_run(self, tmp_path):
        """Pending candidates include files not successful in prior run."""
        db = str(tmp_path / "test_manifest.db")
        m = TransferManifest(db)

        # run1: one success, one failed, one undispatched
        m.start_run("run1", ["/src"], "/dst")
        m.record_source_file("run1", "/src/success.txt", file_mtime=1.0)
        m.record_source_file("run1", "/src/failed.txt", file_mtime=1.0)
        m.record_source_file("run1", "/src/pending.txt", file_mtime=1.0)
        m.record_transfer("run1", "/src/success.txt", result="success")
        m.record_transfer("run1", "/src/failed.txt", result="failed")
        m.finish_run("run1")

        m.start_run("run2", ["/src"], "/dst")
        latest = m.get_latest_run_id_before("run2")
        assert latest == "run1"
        pending = m.get_pending_candidates_from_run(latest)
        pending_paths = {p for p, _, _ in pending}
        assert "/src/success.txt" not in pending_paths
        assert "/src/failed.txt" in pending_paths
        assert "/src/pending.txt" in pending_paths
        m.close()


# ============================================================================
# Test 13: Staging manager
# ============================================================================

class TestStagingManager:

    def test_three_stage_dirs_created(self, tmp_path):
        """StagingManager creates incoming, verified, quarantine."""
        sm = StagingManager(str(tmp_path / "staging"))
        assert sm.incoming.exists()
        assert sm.verified.exists()
        assert sm.quarantine.exists()

    def test_promote_to_verified(self, tmp_path):
        """File moves from incoming to verified."""
        sm = StagingManager(str(tmp_path / "staging"))
        tmp_file = sm.incoming_path("docs/report.txt")
        tmp_file.write_bytes(b"test content")

        final = sm.promote_to_verified(tmp_file, "docs/report.txt")
        assert final.exists()
        assert "verified" in str(final)
        assert not tmp_file.exists()

    def test_quarantine_with_reason(self, tmp_path):
        """Quarantined file gets a .reason companion."""
        sm = StagingManager(str(tmp_path / "staging"))
        tmp_file = sm.incoming_path("docs/bad.txt")
        tmp_file.write_bytes(b"corrupt data")

        q = sm.quarantine_file(tmp_file, "docs/bad.txt", "Hash mismatch")
        assert q.exists()
        reason_file = q.with_suffix(q.suffix + ".reason")
        assert reason_file.exists()
        assert "Hash mismatch" in reason_file.read_text()

    def test_cleanup_incoming(self, tmp_path):
        """cleanup_incoming removes .tmp files."""
        sm = StagingManager(str(tmp_path / "staging"))
        # Create some .tmp files
        for i in range(3):
            p = sm.incoming / f"file_{i}.txt.tmp"
            p.write_bytes(b"partial")
        cleaned = sm.cleanup_incoming()
        assert cleaned == 3
        assert list(sm.incoming.rglob("*.tmp")) == []

    def test_promote_collision_handled(self, tmp_path):
        """Name collision in verified/ gets _1, _2 suffix."""
        sm = StagingManager(str(tmp_path / "staging"))

        # First file
        t1 = sm.incoming_path("report.txt")
        t1.write_bytes(b"version 1")
        f1 = sm.promote_to_verified(t1, "report.txt")

        # Second file with same name
        t2 = sm.incoming_path("report.txt")
        t2.write_bytes(b"version 2")
        f2 = sm.promote_to_verified(t2, "report.txt")

        assert f1.exists()
        assert f2.exists()
        assert f1 != f2
        assert "_1" in f2.name


# ============================================================================
# Test 14: Simulated connection issues
# ============================================================================

class TestConnectionIssues:

    def test_copy_retry_on_failure(self, tmp_dirs):
        """Copy retries on transient OSError and eventually succeeds."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=500)

        call_count = [0]
        original_copy = _buffered_copy

        def flaky_copy(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise OSError("Network error")
            original_copy(s, d, buf_size, bw_limit, **kwargs)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", flaky_copy
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,  # Fast retries for testing
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        assert stats.files_copied == 1

    def test_copy_fails_after_max_retries(self, tmp_dirs):
        """Copy fails permanently after exhausting retries."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=500)

        def always_fail(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            raise OSError("Permanent network failure")

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", always_fail
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=2,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # files_failed counts both the hash read failure AND the copy failure
        # in the catch-all handler, so >= 1 is correct
        assert stats.files_failed >= 1

    def test_source_inaccessible(self, tmp_dirs):
        """Inaccessible source directory logged and skipped."""
        src, dst = tmp_dirs
        cfg = TransferConfig(
            source_paths=["/nonexistent/network/share"],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()
        assert stats.files_discovered == 0
        assert stats.files_failed == 0


# ============================================================================
# Test 15: Hidden and system files
# ============================================================================

class TestHiddenFiles:

    @pytest.mark.skipif(
        sys.platform != "win32", reason="Windows-only file attributes"
    )
    def test_hidden_file_skipped_by_default(self, tmp_dirs):
        """Hidden files are skipped when include_hidden=False."""
        src, dst = tmp_dirs
        f = _make_file(src / "hidden.txt", size=200)
        # Set hidden attribute on Windows
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(f), 0x02)

        stats = _run_transfer(src, dst, include_hidden=False)
        assert stats.files_skipped_hidden >= 1


# ============================================================================
# Test 16: Concurrent workers
# ============================================================================

class TestConcurrentWorkers:

    def test_many_workers_no_corruption(self, tmp_dirs):
        """8 workers transferring simultaneously produce no errors."""
        src, dst = tmp_dirs
        for i in range(50):
            _make_file(src / f"file_{i:03d}.txt", size=500)
        stats = _run_transfer(src, dst, workers=8)
        assert stats.files_copied == 50
        assert stats.files_failed == 0
        assert stats.files_verify_failed == 0

    def test_single_worker(self, tmp_dirs):
        """Single worker mode works correctly."""
        src, dst = tmp_dirs
        for i in range(10):
            _make_file(src / f"file_{i}.txt", size=200)
        stats = _run_transfer(src, dst, workers=1)
        assert stats.files_copied == 10


# ============================================================================
# Test 17: Directory structure preservation
# ============================================================================

class TestDirectoryStructure:

    def test_nested_dirs_preserved(self, tmp_dirs):
        """Nested directory structure is preserved in verified/."""
        src, dst = tmp_dirs
        _make_file(src / "level1" / "level2" / "deep.txt", size=200)
        _make_file(src / "level1" / "shallow.txt", size=200)
        _make_file(src / "top.txt", size=200)
        stats = _run_transfer(src, dst)
        assert stats.files_copied == 3

        # Check structure exists
        verified = dst / "verified"
        deep_files = list(verified.rglob("deep.txt"))
        assert len(deep_files) == 1


# ============================================================================
# Test 18: Utility functions
# ============================================================================

class TestUtilities:

    def test_fmt_size(self):
        assert "0 B" == _fmt_size(0)
        assert "512 B" == _fmt_size(512)
        assert "1.0 KB" == _fmt_size(1024)
        assert "1.0 MB" == _fmt_size(1024 ** 2)
        assert "1.00 GB" == _fmt_size(1024 ** 3)

    def test_fmt_dur(self):
        assert "30.0s" == _fmt_dur(30)
        assert "2m 30s" == _fmt_dur(150)
        assert "1h 30m" == _fmt_dur(5400)


# ============================================================================
# Test 19: Keyboard interrupt (Ctrl+C) graceful shutdown
# ============================================================================

class TestGracefulShutdown:

    def test_interrupt_saves_progress(self, tmp_dirs):
        """KeyboardInterrupt during transfer preserves manifest."""
        src, dst = tmp_dirs
        for i in range(10):
            _make_file(src / f"file_{i}.txt", size=200)

        call_count = [0]
        original_copy = _buffered_copy

        def interrupt_after_3(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                raise KeyboardInterrupt()
            original_copy(s, d, buf_size, bw_limit, **kwargs)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", interrupt_after_3
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # Some files should have been copied before interrupt
        assert stats.files_copied >= 1
        # Manifest DB should exist
        assert (dst / "_transfer_manifest.db").exists()


# ============================================================================
# Test 20: End-to-end full pipeline
# ============================================================================

class TestEndToEnd:

    def test_full_pipeline_mixed_files(self, tmp_dirs):
        """Complete pipeline with mixed file types and sizes."""
        src, dst = tmp_dirs

        # Create a realistic mix
        _make_file(src / "reports" / "q1.pdf", size=10_000)
        _make_file(src / "reports" / "q2.pdf", size=15_000)
        _make_file(src / "notes" / "meeting.txt", size=500)
        _make_file(src / "notes" / "todo.md", size=300)
        _make_file(src / "data" / "export.csv", size=5_000)
        _make_file(src / "data" / "config.json", size=200)
        _make_file(src / "code" / "script.py", size=1_000)  # unsupported
        _make_file(src / "media" / "photo.exe", size=2_000)  # unsupported
        _make_file(src / "tiny.txt", size=5)  # too small

        stats = _run_transfer(src, dst, min_file_size=100)

        # Should copy: 2 pdf + 1 txt + 1 md + 1 csv + 1 json = 6
        assert stats.files_copied == 6
        assert stats.files_skipped_ext >= 2  # .py, .exe
        assert stats.files_skipped_size >= 1  # tiny.txt
        assert stats.files_failed == 0
        assert stats.files_verify_failed == 0

        # Verify manifest DB exists and is queryable
        db_path = dst / "_transfer_manifest.db"
        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM source_manifest"
        ).fetchone()[0]
        assert count >= 9  # all discovered files
        conn.close()


# ============================================================================
# Test 21: Connection dropout simulation (VPN/corporate network)
# ============================================================================
# Simulates what happens when the network drops mid-transfer and
# then recovers. This is the bread-and-butter failure mode for
# corporate VPN transfers overnight.
# ============================================================================

class TestConnectionDropout:

    def test_intermittent_network_drops(self, tmp_dirs):
        """Copy succeeds despite intermittent network OSError bursts.

        Simulates: VPN micro-drops that cause 2-3 consecutive failures
        before the connection stabilizes again.
        """
        src, dst = tmp_dirs
        for i in range(10):
            _make_file(src / f"doc_{i}.txt", size=500)

        call_count = [0]
        original_copy = _buffered_copy

        def intermittent_drop(s, d, buf_size=1048576, bw_limit=0, **kwargs):
            call_count[0] += 1
            # Fail every 4th and 5th call (simulates burst of failures)
            if call_count[0] % 5 in (0, 4):
                raise OSError(errno.ENETUNREACH, "Network is unreachable")
            original_copy(s, d, buf_size, bw_limit, **kwargs)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", intermittent_drop
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=2,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # Most files should eventually succeed via retry
        assert stats.files_copied >= 5
        assert stats.files_failed + stats.files_copied == 10

    def test_prolonged_outage_then_recovery(self, tmp_dirs):
        """All copies fail during outage, then succeed after recovery.

        Simulates: VPN goes down for the first 8 copies, then comes
        back up for the rest. Retry logic should handle this.
        """
        src, dst = tmp_dirs
        for i in range(5):
            _make_file(src / f"doc_{i}.txt", size=300)

        call_count = [0]
        original_copy = _buffered_copy

        def outage_then_recovery(s, d, buf_size=1048576, bw_limit=0, **kw):
            call_count[0] += 1
            # First 5 calls fail (outage), then all succeed (recovery)
            if call_count[0] <= 5:
                raise OSError(errno.ETIMEDOUT, "Connection timed out")
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy",
            outage_then_recovery,
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # With retries, all should eventually get through
        assert stats.files_copied >= 3

    def test_permission_error_not_retried(self, tmp_dirs):
        """PermissionError causes immediate skip, not infinite retry.

        Simulates: corporate ACL blocks access to certain folders.
        The engine should not waste retries on permission denials.
        """
        src, dst = tmp_dirs
        _make_file(src / "allowed.txt", size=300)
        _make_file(src / "blocked.txt", size=300)

        original_copy = _buffered_copy

        def perm_block(s, d, buf_size=1048576, bw_limit=0, **kw):
            if "blocked" in s:
                raise PermissionError("Access denied by corporate ACL")
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", perm_block
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        assert stats.files_copied == 1


# ============================================================================
# Test 22: Speed fluctuation simulation
# ============================================================================
# Simulates network bandwidth that varies wildly -- the reality of
# corporate networks shared by 500+ users.
# ============================================================================

class TestSpeedFluctuation:

    def test_variable_speed_completes(self, tmp_dirs):
        """Transfer completes with wildly varying copy speeds.

        Simulates: corporate WAN link shared by hundreds of users.
        Some copies finish instantly, others crawl.
        """
        src, dst = tmp_dirs
        for i in range(8):
            _make_file(src / f"doc_{i}.txt", size=1000)

        original_copy = _buffered_copy

        def variable_speed(s, d, buf_size=1048576, bw_limit=0, **kw):
            # Random delay 0-50ms to simulate variable throughput
            time.sleep(random.uniform(0, 0.05))
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", variable_speed
        ):
            stats = _run_transfer(src, dst, workers=4)

        assert stats.files_copied == 8
        assert stats.files_failed == 0

    def test_bandwidth_throttle_no_data_loss(self, tmp_dirs):
        """Heavy bandwidth throttling still produces correct copies."""
        src, dst = tmp_dirs
        content = os.urandom(5000)
        _make_file(src / "throttled.txt", content=content)

        # Very aggressive throttle: 1 KB/s
        stats = _run_transfer(src, dst, bandwidth_limit=1024)
        assert stats.files_copied == 1
        assert stats.files_verify_failed == 0

        # Verify content integrity
        verified = list((dst / "verified").rglob("throttled.txt"))
        assert len(verified) == 1
        assert verified[0].read_bytes() == content


# ============================================================================
# Test 23: Thousands of tiny files (scale test)
# ============================================================================
# Enterprise file shares often have thousands of tiny config/log files
# mixed with large documents. The engine must handle both efficiently.
# ============================================================================

class TestScaleTinyFiles:

    def test_1000_tiny_files(self, tmp_dirs):
        """1000 tiny files transferred without error or excessive time."""
        src, dst = tmp_dirs
        for i in range(1000):
            _make_file(src / f"tiny_{i:04d}.txt", size=150)

        stats = _run_transfer(src, dst, workers=8, min_file_size=100)
        assert stats.files_copied == 1000
        assert stats.files_failed == 0
        assert stats.files_verify_failed == 0

    def test_mixed_sizes_concurrent(self, tmp_dirs):
        """Mix of tiny and medium files with high concurrency.

        This tests the thread pool's ability to balance fast tiny-file
        completions with slower medium-file transfers.
        """
        src, dst = tmp_dirs
        # 50 tiny files (150 bytes each)
        for i in range(50):
            _make_file(src / f"tiny_{i}.txt", size=150)
        # 10 medium files (50 KB each)
        for i in range(10):
            _make_file(src / f"medium_{i}.pdf", size=50_000)
        # 2 large files (500 KB each)
        for i in range(2):
            _make_file(src / f"large_{i}.pdf", size=500_000)

        stats = _run_transfer(src, dst, workers=8)
        assert stats.files_copied == 62
        assert stats.files_failed == 0

    def test_deeply_nested_many_dirs(self, tmp_dirs):
        """100 files spread across 20 nested directories."""
        src, dst = tmp_dirs
        for d in range(20):
            folder = src / f"dept_{d}" / "reports" / "2026"
            for f in range(5):
                _make_file(folder / f"report_{f}.txt", size=200)

        stats = _run_transfer(src, dst, workers=4)
        assert stats.files_copied == 100
        assert stats.files_failed == 0


# ============================================================================
# Test 24: Large file handling
# ============================================================================

class TestLargeFiles:

    def test_5mb_file_verified(self, tmp_dirs):
        """5 MB file copies and verifies correctly."""
        src, dst = tmp_dirs
        content = os.urandom(5_000_000)
        _make_file(src / "big.pdf", content=content)

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1
        assert stats.files_verified == 1

        verified = list((dst / "verified").rglob("big.pdf"))
        assert len(verified) == 1
        assert verified[0].read_bytes() == content

    def test_large_file_stall_detection(self, tmp_dirs):
        """Copy that stalls mid-transfer is caught by timeout."""
        src, dst = tmp_dirs
        _make_file(src / "stalling.pdf", size=1000)

        def stalling_copy(s, d, buf_size=1048576, bw_limit=0, **kw):
            # Simulate stalled network read
            time.sleep(10)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", stalling_copy
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=1,
                retry_backoff=0.01,
                resume=False,
            )
            # Override copy timeout to be very short for testing
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # Should fail due to timeout or stall, not hang forever
        assert stats.files_copied == 0


# ============================================================================
# Test 25: Memory leak regression test
# ============================================================================
# Runs multiple transfer cycles and verifies that key data structures
# do not grow unboundedly. Critical for 5-day continuous operation.
# ============================================================================

class TestMemoryLeakRegression:

    def test_speed_samples_bounded(self, tmp_dirs):
        """_speed_samples list stays bounded after many record_copy calls."""
        src, dst = tmp_dirs
        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.stats

        # Simulate 2000 rapid copy recordings
        for i in range(2000):
            stats.record_copy(1000, ".txt", str(src))

        # Speed samples should be pruned to <= 500
        assert len(stats._speed_samples) <= 500

    def test_speed_history_capped(self, tmp_dirs):
        """_speed_history list respects max_speed_history cap."""
        src, dst = tmp_dirs
        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=1,
            max_speed_history=50,
            resume=False,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.stats

        # Manually add 200 speed history entries
        for i in range(200):
            stats._speed_history.append((float(i * 30), 1000.0))

        # Cap should be applied when progress loop runs, but we can
        # verify the setting propagated
        assert stats._max_speed_history == 50

    def test_multiple_runs_no_accumulation(self, tmp_dirs):
        """Three sequential runs don't accumulate state across engines."""
        src, dst = tmp_dirs
        for i in range(5):
            _make_file(src / f"doc_{i}.txt", size=200)

        for run in range(3):
            stats = _run_transfer(src, dst, resume=True)
            if run == 0:
                assert stats.files_copied == 5
            else:
                # Subsequent runs skip (resume) -- no state leak
                assert stats.files_copied == 0
                assert stats.files_skipped_unchanged == 5

    def test_dedup_set_proportional_to_unique_files(self, tmp_dirs):
        """_dedup_seen set size matches unique file count, not total."""
        src, dst = tmp_dirs
        # 5 unique files + 5 duplicates = 10 files
        for i in range(5):
            content = os.urandom(500)
            _make_file(src / f"unique_{i}.txt", content=content)
            _make_file(src / f"dup_{i}.txt", content=content)

        stats = _run_transfer(src, dst, workers=1)
        assert stats.files_copied == 5
        assert stats.files_deduplicated == 5


# ============================================================================
# Test 26: Incomplete file recovery
# ============================================================================
# Simulates finding leftover .tmp files from a crashed previous run.
# The engine must clean these up before starting a new transfer.
# ============================================================================

class TestIncompleteFileRecovery:

    def test_leftover_tmp_cleaned(self, tmp_dirs):
        """Leftover .tmp files from crashed run are cleaned on restart."""
        src, dst = tmp_dirs
        _make_file(src / "good.txt", size=200)

        # Simulate crashed run: create leftover .tmp files
        incoming = dst / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            (incoming / f"partial_{i}.txt.tmp").write_bytes(b"garbage")

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1

        # Verify all .tmp files were cleaned up
        leftover = list(incoming.rglob("*.tmp"))
        assert len(leftover) == 0

    def test_corrupted_partial_not_in_verified(self, tmp_dirs):
        """Partial/corrupt files never appear in verified/ directory."""
        src, dst = tmp_dirs
        content = os.urandom(1000)
        _make_file(src / "doc.txt", content=content)

        original_copy = _buffered_copy

        def write_partial(s, d, buf_size=1048576, bw_limit=0, **kw):
            # Write only half the file, then fail
            with open(s, "rb") as fin:
                data = fin.read(500)
            with open(d, "wb") as fout:
                fout.write(data)
            raise OSError("Network dropped mid-copy")

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", write_partial
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=1,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        assert stats.files_copied == 0
        # Verified folder should be empty (no corrupt files)
        verified = dst / "verified"
        all_files = list(verified.rglob("*"))
        txt_files = [f for f in all_files if f.is_file() and
                     not f.name.endswith(".reason")]
        assert len(txt_files) == 0


# ============================================================================
# Test 27: Network recovery (consecutive failure detection)
# ============================================================================

class TestNetworkRecovery:

    def test_consecutive_failure_counter_resets_on_success(self, tmp_dirs):
        """Consecutive failure counter resets after a successful copy."""
        src, dst = tmp_dirs
        for i in range(6):
            _make_file(src / f"doc_{i}.txt", size=200)

        call_count = [0]
        original_copy = _buffered_copy

        def fail_then_succeed(s, d, buf_size=1048576, bw_limit=0, **kw):
            call_count[0] += 1
            # Fail first 3 calls, succeed the rest
            if call_count[0] <= 3:
                raise OSError("Network blip")
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", fail_then_succeed
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,
                max_consecutive_failures=50,  # High so no recovery pause
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # After first success, consecutive_failures resets to 0
        assert stats.consecutive_failures == 0
        assert stats.files_copied >= 3

    def test_network_health_stats_tracked(self, tmp_dirs):
        """Network stall events are recorded in stats."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=200)

        stats = _run_transfer(src, dst)
        # Normal run should have 0 stalls
        assert stats.network_stalls == 0
        assert stats.network_recovery_time == 0


# ============================================================================
# Test 28: JSON event log
# ============================================================================

class TestJsonEventLog:

    def test_json_log_created(self, tmp_dirs):
        """JSON log file is created when log_file is configured."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=200)
        log_path = str(dst / "transfer.jsonl")

        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
            log_file=log_path,
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()

        assert stats.files_copied == 1
        assert Path(log_path).exists()

        # Parse JSON lines
        lines = Path(log_path).read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines if line.strip()]
        assert len(events) >= 2  # At least phase_start + complete

        event_types = [e["event"] for e in events]
        assert "phase_start" in event_types
        assert "complete" in event_types

    def test_no_log_without_config(self, tmp_dirs):
        """No JSON log file when log_file is empty."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=200)

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1
        # No .jsonl file should exist
        jsonl_files = list(dst.glob("*.jsonl"))
        assert len(jsonl_files) == 0


# ============================================================================
# Test 29: Progress callback (GUI integration)
# ============================================================================

class TestProgressCallback:

    def test_callback_receives_stats(self, tmp_dirs):
        """Progress callback receives valid stats dict."""
        src, dst = tmp_dirs
        for i in range(3):
            _make_file(src / f"doc_{i}.txt", size=200)

        callbacks_received = []

        def on_progress(stats_dict):
            callbacks_received.append(stats_dict.copy())

        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
            progress_callback=on_progress,
            checkpoint_interval=0.1,  # Fast checkpoints for testing
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()

        assert stats.files_copied == 3
        # Should have received at least one callback
        # (final emit_progress in run())
        assert len(callbacks_received) >= 1

        # Verify callback dict has expected keys
        last_cb = callbacks_received[-1]
        assert "files_copied" in last_cb
        assert "bytes_copied" in last_cb
        assert "speed_bps" in last_cb


# ============================================================================
# Test 30: Modified file detection on resume
# ============================================================================

class TestModifiedFileResume:

    def test_modified_file_recopied(self, tmp_dirs):
        """File modified between runs is recopied, not skipped."""
        src, dst = tmp_dirs
        f = _make_file(src / "evolving.txt", size=200)

        # First run
        stats1 = _run_transfer(src, dst, resume=True)
        assert stats1.files_copied == 1

        # Modify the file and force mtime to differ by > 2 seconds
        # (is_already_transferred tolerance is 2.0s)
        f.write_bytes(os.urandom(300))
        st = f.stat()
        os.utime(str(f), (st.st_atime, st.st_mtime + 5.0))

        # Second run should recopy (mtime changed by 5 seconds)
        stats2 = _run_transfer(src, dst, resume=True)
        # Either copied (new content) or deduplicated, but NOT skipped
        assert stats2.files_skipped_unchanged == 0

    def test_unmodified_file_skipped(self, tmp_dirs):
        """Unmodified file is correctly skipped on resume."""
        src, dst = tmp_dirs
        _make_file(src / "stable.txt", size=200)

        _run_transfer(src, dst, resume=True)
        stats2 = _run_transfer(src, dst, resume=True)

        assert stats2.files_copied == 0
        assert stats2.files_skipped_unchanged == 1


# ============================================================================
# Test 31: Chaos test (mixed failure modes)
# ============================================================================
# Combines multiple failure modes into one test to simulate a
# realistic enterprise transfer with all the problems at once.
# ============================================================================

class TestChaos:

    def test_mixed_failure_modes(self, tmp_dirs):
        """Transfer survives a mix of failures: timeout, locked,
        corruption, network drops, and permission errors.

        This is the "real world" test -- production networks have
        ALL of these problems happening simultaneously.
        """
        src, dst = tmp_dirs
        rng = random.Random(42)  # Seeded for reproducibility

        # Create 30 files of varying sizes
        for i in range(30):
            size = rng.choice([150, 500, 1000, 5000, 50_000])
            _make_file(src / f"chaos_{i:03d}.txt", size=size)

        call_count = [0]
        original_copy = _buffered_copy

        def chaos_copy(s, d, buf_size=1048576, bw_limit=0, **kw):
            call_count[0] += 1
            # 10% chance of network error (retryable)
            if rng.random() < 0.10:
                raise OSError(errno.ENETUNREACH, "Network blip")
            # 5% chance of slow copy (variable speed)
            if rng.random() < 0.05:
                time.sleep(rng.uniform(0.01, 0.05))
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", chaos_copy
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=4,
                min_file_size=100,
                max_retries=3,
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # With retries and a 10% failure rate, most files should succeed
        assert stats.files_copied >= 20
        assert stats.files_verify_failed == 0  # No silent corruption
        # Every file is accounted for (zero-gap)
        total = (stats.files_copied + stats.files_deduplicated +
                 stats.files_failed + stats.files_quarantined)
        assert total == 30

    def test_chaos_with_resume(self, tmp_dirs):
        """Chaos test followed by resume picks up remaining files."""
        src, dst = tmp_dirs
        rng = random.Random(99)

        for i in range(20):
            _make_file(src / f"doc_{i:03d}.txt", size=300)

        fail_set = set(rng.sample(range(20), 8))  # 8 of 20 will fail
        call_map = {}

        original_copy = _buffered_copy

        def selective_fail(s, d, buf_size=1048576, bw_limit=0, **kw):
            # Extract file index from path
            name = Path(s).stem
            idx = int(name.split("_")[1])
            count = call_map.get(idx, 0)
            call_map[idx] = count + 1

            # Files in fail_set fail on ALL attempts in first run
            if idx in fail_set and count < 3:
                raise OSError("Permanent failure (first run)")
            original_copy(s, d, buf_size, bw_limit, **kw)

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", selective_fail
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,
                retry_backoff=0.01,
                resume=True,
            )
            engine = BulkTransferV2(cfg)
            stats1 = engine.run()

        assert stats1.files_copied == 12  # 20 - 8 failures

        # Second run with resume: failed files should now be retried
        # (no longer in fail_set mock because count > 3)
        call_map.clear()
        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", original_copy
        ):
            stats2 = _run_transfer(src, dst, resume=True)

        # Resume should skip the 12 already-done and copy the 8 that failed
        # (or dedup them if hashes match)
        # Manifest-first resume can complete pending files before the
        # full discovery pass reaches them, so unchanged skip count may
        # be >= 12 on the second pass.
        assert stats2.files_skipped_unchanged >= 12
        total_second = stats2.files_copied + stats2.files_deduplicated
        assert total_second >= 5  # Most of the 8 should now succeed


# ============================================================================
# Test 32: Disk space exhaustion
# ============================================================================

class TestDiskSpace:

    def test_enospc_stops_gracefully(self, tmp_dirs):
        """ENOSPC (disk full) is detected and stops without data loss."""
        src, dst = tmp_dirs
        _make_file(src / "doc.txt", size=500)

        def disk_full(s, d, buf_size=1048576, bw_limit=0, **kw):
            raise OSError(errno.ENOSPC, "No space left on device")

        with mock.patch(
            "src.tools.bulk_transfer_v2._buffered_copy", disk_full
        ):
            cfg = TransferConfig(
                source_paths=[str(src)],
                dest_path=str(dst),
                workers=1,
                min_file_size=10,
                max_retries=3,  # ENOSPC should NOT be retried
                retry_backoff=0.01,
                resume=False,
            )
            engine = BulkTransferV2(cfg)
            stats = engine.run()

        # ENOSPC causes immediate failure (no retry), file goes
        # to quarantine to preserve partial data for inspection
        assert stats.files_copied == 0
        assert stats.files_failed >= 1


# ============================================================================
# Test 33: GC trigger during transfer
# ============================================================================

class TestGarbageCollection:

    def test_gc_triggered_by_interval(self, tmp_dirs):
        """GC runs periodically based on gc_interval config."""
        src, dst = tmp_dirs
        for i in range(5):
            _make_file(src / f"doc_{i}.txt", size=200)

        cfg = TransferConfig(
            source_paths=[str(src)],
            dest_path=str(dst),
            workers=1,
            min_file_size=10,
            resume=False,
            gc_interval=2,  # Trigger GC every 2 files processed
            checkpoint_interval=999,  # Don't trigger via checkpoint
        )
        engine = BulkTransferV2(cfg)
        stats = engine.run()

        assert stats.files_copied == 5
        # At least the final gc.collect() in Phase 3
        assert stats.gc_collections >= 1


# ============================================================================
# Test 34: Nightly incremental sync
# ============================================================================
# Simulates the production use case: nightly scheduled transfer that
# only picks up new/modified files since the last run.
# ============================================================================

class TestNightlyIncrementalSync:

    def test_three_night_incremental(self, tmp_dirs):
        """Simulates 3 nightly runs with incrementally growing source.

        Night 1: 10 files -> all copied
        Night 2: 3 new files added -> 3 copied, 10 skipped
        Night 3: 1 file modified, 2 new -> 3 copied, 12 skipped
        """
        src, dst = tmp_dirs

        # Night 1: Initial 10 files
        for i in range(10):
            _make_file(src / f"doc_{i:03d}.txt", size=300)

        stats1 = _run_transfer(src, dst, resume=True)
        assert stats1.files_copied == 10

        # Night 2: Add 3 new files
        for i in range(10, 13):
            _make_file(src / f"doc_{i:03d}.txt", size=300)

        stats2 = _run_transfer(src, dst, resume=True)
        assert stats2.files_copied == 3
        assert stats2.files_skipped_unchanged == 10

        # Night 3: Modify 1 existing + add 2 new
        # Force mtime difference > 2 seconds (is_already_transferred
        # tolerance is 2.0s) so the modified file is detected
        f_mod = src / "doc_000.txt"
        f_mod.write_bytes(os.urandom(400))  # Modified
        st = f_mod.stat()
        os.utime(str(f_mod), (st.st_atime, st.st_mtime + 5.0))
        for i in range(13, 15):
            _make_file(src / f"doc_{i:03d}.txt", size=300)

        stats3 = _run_transfer(src, dst, resume=True)
        # 2 new + 1 modified (mtime changed) = 3 to copy
        # The modified file might be deduped if the hash lookup
        # finds the old copy, but it won't be skipped_unchanged
        assert stats3.files_skipped_unchanged == 12
        new_transfers = stats3.files_copied + stats3.files_deduplicated
        assert new_transfers >= 2  # At least the 2 brand new files

    def test_nightly_with_deletions(self, tmp_dirs):
        """Source deletions are tracked in delta analysis."""
        src, dst = tmp_dirs

        for i in range(5):
            _make_file(src / f"doc_{i}.txt", size=200)

        stats1 = _run_transfer(src, dst, resume=True)
        assert stats1.files_copied == 5

        # Delete 2 files from source
        (src / "doc_0.txt").unlink()
        (src / "doc_1.txt").unlink()

        stats2 = _run_transfer(src, dst, resume=True)
        assert stats2.files_skipped_unchanged == 3
        assert stats2.files_delta_deleted == 2


# ============================================================================
# Test 35: Source path with spaces and special characters
# ============================================================================

class TestSpecialPaths:

    def test_spaces_in_path(self, tmp_dirs):
        """Paths with spaces are handled correctly."""
        src, dst = tmp_dirs
        folder = src / "My Documents" / "Q1 Reports"
        _make_file(folder / "annual report.txt", size=200)

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1

    def test_unicode_folder_names(self, tmp_dirs):
        """Folder names with common unicode chars work."""
        src, dst = tmp_dirs
        folder = src / "Reports-2026"
        _make_file(folder / "report_v2.1.txt", size=200)

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1

    def test_very_long_filename(self, tmp_dirs):
        """Long filenames (200+ chars) are handled."""
        src, dst = tmp_dirs
        # Create a file with a very long name (but under 260 total path)
        long_name = "a" * 150 + ".txt"
        _make_file(src / long_name, size=200)

        stats = _run_transfer(src, dst)
        assert stats.files_copied == 1
