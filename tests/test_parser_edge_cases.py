"""Edge-case tests for parser modules (Sprint 18.3).

DPI audit P1 #5: 37 parsers with zero dedicated unit tests.
Tests the most critical error paths: missing files, empty files,
corrupted content, and wrong-extension handling. Uses only stdlib
fixtures (no Hypothesis -- not installed).

Every parser must:
  1. Never crash on bad input (return "" or error in details)
  2. Never return None (always str)
  3. Include diagnostic info in parse_with_details()
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# PlainTextParser
# ============================================================================

class TestPlainTextParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.plain_text_parser import PlainTextParser
        return PlainTextParser()

    def test_valid_file(self, parser, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("Hello world", encoding="utf-8")
        text = parser.parse(str(f))
        assert text == "Hello world"

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        text = parser.parse(str(f))
        assert text == ""
        assert isinstance(text, str)

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.txt")
        assert text == ""
        assert "error" in details or "RUNTIME_ERROR" in str(details)

    def test_binary_content(self, parser, tmp_path):
        f = tmp_path / "binary.txt"
        f.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        text = parser.parse(str(f))
        assert isinstance(text, str)

    def test_large_file(self, parser, tmp_path):
        f = tmp_path / "large.txt"
        f.write_text("x" * 100_000, encoding="utf-8")
        text = parser.parse(str(f))
        assert len(text) == 100_000

    def test_mixed_encoding(self, parser, tmp_path):
        f = tmp_path / "mixed.txt"
        f.write_bytes(b"Hello \xe9\xe8\xea world")
        text = parser.parse(str(f))
        assert isinstance(text, str)
        assert "Hello" in text
        assert "world" in text

    def test_details_has_parser_name(self, parser, tmp_path):
        f = tmp_path / "info.txt"
        f.write_text("test", encoding="utf-8")
        _, details = parser.parse_with_details(str(f))
        assert details.get("parser") == "PlainTextParser"

    def test_details_has_length(self, parser, tmp_path):
        f = tmp_path / "len.txt"
        f.write_text("12345", encoding="utf-8")
        text, details = parser.parse_with_details(str(f))
        assert details.get("total_len") == 5


# ============================================================================
# PDFParser
# ============================================================================

class TestPDFParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.pdf_parser import PDFParser
        return PDFParser()

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.pdf")
        assert isinstance(text, str)
        assert text == "" or "error" in str(details).lower()

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_garbage_bytes(self, parser, tmp_path):
        f = tmp_path / "garbage.pdf"
        f.write_bytes(b"NOT A PDF" * 100)
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_truncated_pdf_header(self, parser, tmp_path):
        f = tmp_path / "truncated.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_never_returns_none(self, parser, tmp_path):
        f = tmp_path / "bad.pdf"
        f.write_bytes(os.urandom(512))
        text = parser.parse(str(f))
        assert text is not None
        assert isinstance(text, str)


# ============================================================================
# Office DOCX Parser
# ============================================================================

class TestDocxParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.office_docx_parser import DocxParser
        return DocxParser()

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.docx")
        assert isinstance(text, str)

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.docx"
        f.write_bytes(b"")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_not_a_zip(self, parser, tmp_path):
        f = tmp_path / "notzip.docx"
        f.write_bytes(b"This is not a zip file")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_random_bytes(self, parser, tmp_path):
        f = tmp_path / "random.docx"
        f.write_bytes(os.urandom(1024))
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)


# ============================================================================
# Office XLSX Parser
# ============================================================================

class TestXlsxParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.office_xlsx_parser import XlsxParser
        return XlsxParser()

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.xlsx")
        assert isinstance(text, str)

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.xlsx"
        f.write_bytes(b"")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_random_bytes(self, parser, tmp_path):
        f = tmp_path / "random.xlsx"
        f.write_bytes(os.urandom(1024))
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)


# ============================================================================
# Office PPTX Parser
# ============================================================================

class TestPptxParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.office_pptx_parser import PptxParser
        return PptxParser()

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.pptx")
        assert isinstance(text, str)

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.pptx"
        f.write_bytes(b"")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_random_bytes(self, parser, tmp_path):
        f = tmp_path / "random.pptx"
        f.write_bytes(os.urandom(1024))
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)


# ============================================================================
# HTML Parser
# ============================================================================

class TestHtmlFileParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.html_file_parser import HtmlFileParser
        return HtmlFileParser()

    def test_valid_html(self, parser, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")
        text = parser.parse(str(f))
        assert "Hello" in text

    def test_empty_html(self, parser, tmp_path):
        f = tmp_path / "empty.html"
        f.write_text("", encoding="utf-8")
        text = parser.parse(str(f))
        assert isinstance(text, str)

    def test_broken_html(self, parser, tmp_path):
        f = tmp_path / "broken.html"
        f.write_text("<html><body><p>Unclosed", encoding="utf-8")
        text = parser.parse(str(f))
        assert isinstance(text, str)

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/page.html")
        assert isinstance(text, str)


# ============================================================================
# RTF Parser
# ============================================================================

class TestRtfParser:

    @pytest.fixture
    def parser(self):
        try:
            from src.parsers.rtf_parser import RtfParser
            return RtfParser()
        except ImportError:
            pytest.skip("striprtf not installed")

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/file.rtf")
        assert isinstance(text, str)

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.rtf"
        f.write_text("", encoding="utf-8")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_garbage_content(self, parser, tmp_path):
        f = tmp_path / "garbage.rtf"
        f.write_bytes(os.urandom(256))
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)


# ============================================================================
# EML Parser
# ============================================================================

class TestEmlParser:

    @pytest.fixture
    def parser(self):
        from src.parsers.eml_parser import EmlParser
        return EmlParser()

    def test_missing_file(self, parser):
        text, details = parser.parse_with_details("/nonexistent/mail.eml")
        assert isinstance(text, str)

    def test_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.eml"
        f.write_text("", encoding="utf-8")
        text, details = parser.parse_with_details(str(f))
        assert isinstance(text, str)

    def test_simple_email(self, parser, tmp_path):
        f = tmp_path / "test.eml"
        f.write_text(
            "From: a@b.com\nTo: c@d.com\nSubject: Test\n\nBody text here.",
            encoding="utf-8",
        )
        text = parser.parse(str(f))
        assert isinstance(text, str)
        assert "Body text here" in text or "Test" in text
