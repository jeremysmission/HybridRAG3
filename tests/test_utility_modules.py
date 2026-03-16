"""Unit tests for ocr_cleanup, chunk_ids, and file_validator utility modules."""

import os
import tempfile
from pathlib import Path

import pytest

from src.core.ocr_cleanup import clean_ocr_text, score_text_quality
from src.core.chunk_ids import make_chunk_id
from src.core.file_validator import FileValidator


# ── TestOcrCleanup ──────────────────────────────────────────────────────────

class TestOcrCleanup:
    """Tests for src/core/ocr_cleanup.py"""

    def test_empty_input_returns_empty(self):
        assert clean_ocr_text("") == ""
        assert clean_ocr_text(None) is None

    def test_control_char_removal(self):
        assert "\x00" not in clean_ocr_text("hello\x00world")
        assert "\x07" not in clean_ocr_text("bell\x07char")

    def test_crlf_normalized_to_lf(self):
        result = clean_ocr_text("line1\r\nline2\rline3")
        assert "\r" not in result
        assert "line1\nline2\nline3" == result

    def test_unicode_smart_quotes_normalized(self):
        result = clean_ocr_text("\u201cHello\u201d \u2018world\u2019")
        assert result == '"Hello" \'world\''

    def test_unicode_dashes_normalized(self):
        assert "--" in clean_ocr_text("value\u2014here")
        assert "-" in clean_ocr_text("pages 1\u20135")

    def test_bom_and_zero_width_removed(self):
        result = clean_ocr_text("\ufeffhello\u200bworld")
        assert result == "helloworld"

    def test_broken_hyphenation_rejoined(self):
        result = clean_ocr_text("calibra-\ntion process")
        assert "calibration" in result

    def test_broken_hyphen_preserves_uppercase(self):
        result = clean_ocr_text("self-\nAwareness")
        assert "self-" in result or "self-\nAwareness" in result

    def test_trailing_whitespace_stripped(self):
        result = clean_ocr_text("hello   \nworld  ")
        assert "hello\nworld" == result

    def test_excessive_blank_lines_collapsed(self):
        result = clean_ocr_text("a\n\n\n\n\n\nb")
        assert result.count("\n") <= 3

    def test_missing_space_after_period(self):
        result = clean_ocr_text("word.Another sentence")
        assert "word. Another" in result

    def test_missing_space_not_applied_to_numbers(self):
        result = clean_ocr_text("value is 3.14 exactly")
        assert "3.14" in result

    def test_internal_multi_space_collapsed(self):
        result = clean_ocr_text("hello    world")
        assert result == "hello world"

    def test_quality_score_clean_text(self):
        clean = "This is a well-formed paragraph with proper sentences. " * 5
        score = score_text_quality(clean)
        assert score >= 70

    def test_quality_score_empty(self):
        assert score_text_quality("") == 0
        assert score_text_quality("   ") == 0

    def test_quality_score_garbage_low(self):
        # Single non-alpha chars on short lines = low alpha, short words, short lines
        garbage = "\n".join(["# !" * 3] * 50)
        score = score_text_quality(garbage)
        assert score < 50


# ── TestChunkIds ────────────────────────────────────────────────────────────

class TestChunkIds:
    """Tests for src/core/chunk_ids.py"""

    PATH = "D:/docs/manual.pdf"
    MTIME = 1700000000000000000
    TEXT = "The quick brown fox jumps over the lazy dog."

    def test_returns_64_char_hex(self):
        cid = make_chunk_id(self.PATH, self.MTIME, 0, 100, self.TEXT)
        assert len(cid) == 64
        assert all(c in "0123456789abcdef" for c in cid)

    def test_deterministic_same_input(self):
        a = make_chunk_id(self.PATH, self.MTIME, 0, 100, self.TEXT)
        b = make_chunk_id(self.PATH, self.MTIME, 0, 100, self.TEXT)
        assert a == b

    def test_different_path_different_id(self):
        a = make_chunk_id("fileA.pdf", self.MTIME, 0, 100, self.TEXT)
        b = make_chunk_id("fileB.pdf", self.MTIME, 0, 100, self.TEXT)
        assert a != b

    def test_different_mtime_different_id(self):
        a = make_chunk_id(self.PATH, 1000, 0, 100, self.TEXT)
        b = make_chunk_id(self.PATH, 2000, 0, 100, self.TEXT)
        assert a != b

    def test_different_offsets_different_id(self):
        a = make_chunk_id(self.PATH, self.MTIME, 0, 100, self.TEXT)
        b = make_chunk_id(self.PATH, self.MTIME, 100, 200, self.TEXT)
        assert a != b

    def test_different_text_different_id(self):
        a = make_chunk_id(self.PATH, self.MTIME, 0, 100, "alpha")
        b = make_chunk_id(self.PATH, self.MTIME, 0, 100, "bravo")
        assert a != b

    def test_path_normalization_backslash(self):
        a = make_chunk_id("D:\\docs\\file.pdf", self.MTIME, 0, 10, "x")
        b = make_chunk_id("D:/docs/file.pdf", self.MTIME, 0, 10, "x")
        assert a == b

    def test_path_normalization_case(self):
        a = make_chunk_id("D:/Docs/File.PDF", self.MTIME, 0, 10, "x")
        b = make_chunk_id("d:/docs/file.pdf", self.MTIME, 0, 10, "x")
        assert a == b

    def test_empty_text_handled(self):
        cid = make_chunk_id(self.PATH, self.MTIME, 0, 0, "")
        assert len(cid) == 64

    def test_none_text_handled(self):
        cid = make_chunk_id(self.PATH, self.MTIME, 0, 0, None)
        assert len(cid) == 64


# ── TestFileValidator ───────────────────────────────────────────────────────

class TestFileValidator:
    """Tests for src/core/file_validator.py"""

    def setup_method(self):
        self.validator = FileValidator(excluded_dirs={"__pycache__", ".git"})

    def test_zero_byte_file_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"")
            path = Path(f.name)
        try:
            reason = self.validator.preflight_check(path)
            assert reason is not None
            assert "Zero-byte" in reason
        finally:
            os.unlink(path)

    def test_office_temp_lock_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "~$document.docx"
            p.write_bytes(b"lock data")
            reason = self.validator.preflight_check(p)
            assert reason is not None
            assert "lock" in reason.lower()

    def test_valid_text_file_accepted(self):
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w"
        ) as f:
            f.write("Hello world, this is valid content.\n" * 10)
            path = Path(f.name)
        try:
            reason = self.validator.preflight_check(path)
            assert reason is None
        finally:
            os.unlink(path)

    def test_pdf_missing_header_rejected(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as f:
            f.write(b"NOT A PDF FILE CONTENTS HERE")
            path = Path(f.name)
        try:
            reason = self.validator.preflight_check(path)
            assert reason is not None
            assert "PDF" in reason
        finally:
            os.unlink(path)

    def test_too_small_pdf_rejected(self):
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as f:
            f.write(b"%PDF-1.4\n%%EOF")
            path = Path(f.name)
        try:
            reason = self.validator.preflight_check(path)
            assert reason is not None
            assert "small" in reason.lower() or "Too small" in reason
        finally:
            os.unlink(path)

    def test_validate_text_accepts_clean(self):
        good = "This is a normal English sentence with proper words." * 3
        assert self.validator.validate_text(good) is True

    def test_validate_text_rejects_short(self):
        assert self.validator.validate_text("hi") is False
        assert self.validator.validate_text("") is False

    def test_validate_text_rejects_binary(self):
        binary = "\x00\x01\x02\x03\xff" * 100
        assert self.validator.validate_text(binary) is False

    def test_excluded_dir_detected(self):
        p = Path("D:/project/__pycache__/module.pyc")
        assert self.validator.is_excluded(p) is True

    def test_non_excluded_dir_passes(self):
        p = Path("D:/project/src/main.py")
        assert self.validator.is_excluded(p) is False

    def test_excluded_dir_case_insensitive(self):
        p = Path("D:/project/__PYCACHE__/module.pyc")
        assert self.validator.is_excluded(p) is True
