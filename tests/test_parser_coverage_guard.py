# ============================================================================
# Parser Coverage Guard Tests
# ============================================================================
# Added: 2026-03-02
# WHY: On 2026-03-01 we discovered a triple-layer silent failure where:
#   1. The indexer config allowlist had only 24 of 63 registered extensions
#   2. 9 parser dependencies were missing from requirements
#   3. OCR system binaries were missing on work laptop
# These tests prevent that from ever happening again.
#
# WHAT THESE TESTS DO:
#   - Verify config allowlist matches parser registry (no drift)
#   - Verify all parser dependencies are importable
#   - Verify every registered extension has a working parser class
#   - Verify OCR wrapper packages are importable
#
# INTERNET ACCESS: NONE
# ============================================================================

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestConfigRegistrySync:
    """Guard against config allowlist drifting from parser registry."""

    def test_config_extensions_match_registry(self):
        """CI GUARD: config.supported_extensions must match REGISTRY.supported_extensions().

        If this test fails, someone added a parser to registry.py but forgot to
        add the extension to config.py IndexingConfig.supported_extensions.
        See: docs/cross_ai_collabs/003_parser_coverage_gap_analysis.md
        """
        from src.core.config import IndexingConfig
        from src.parsers.registry import REGISTRY

        config_exts = set(IndexingConfig().supported_extensions)
        registry_exts = set(REGISTRY.supported_extensions())

        missing_from_config = registry_exts - config_exts
        extra_in_config = config_exts - registry_exts

        assert not missing_from_config, (
            f"Extensions in registry but NOT in config allowlist: {sorted(missing_from_config)}\n"
            f"Fix: Add these to IndexingConfig.supported_extensions in src/core/config.py"
        )
        assert not extra_in_config, (
            f"Extensions in config but NOT in registry: {sorted(extra_in_config)}\n"
            f"Fix: Either add a parser to registry.py or remove from config.py"
        )

    def test_indexer_fallback_uses_registry(self):
        """Verify indexer falls back to registry when config has no extensions."""
        from src.parsers.registry import REGISTRY
        from unittest.mock import MagicMock

        # Simulate config whose .indexing has no supported_extensions attribute
        fake_indexing = MagicMock(spec=[])
        fake_indexing.max_chars_per_file = 5_000_000
        fake_indexing.block_chars = 500_000
        fake_indexing.excluded_dirs = [".git"]

        fake_config = MagicMock()
        fake_config.indexing = fake_indexing

        from src.core.indexer import Indexer
        from unittest.mock import patch

        with patch("src.core.indexer.FileValidator"):
            indexer = Indexer(
                config=fake_config,
                vector_store=MagicMock(),
                embedder=MagicMock(),
                chunker=MagicMock(),
            )

        # Indexer should have fallen back to full registry
        assert indexer._supported_extensions == set(REGISTRY.supported_extensions())


class TestParserDependencies:
    """Guard against missing parser dependencies (the silent-skip problem)."""

    # Each tuple: (import_name, pip_package, file_types_affected)
    REQUIRED_PARSER_DEPS = [
        ("olefile", "olefile", ".doc, .msg"),
        ("ezdxf", "ezdxf", ".dxf"),
        ("Evtx", "python-evtx", ".evtx"),
        ("oxmsg", "python-oxmsg", ".msg"),
        ("dpkt", "dpkt", ".pcap, .pcapng"),
        ("psd_tools", "psd-tools", ".psd"),
        ("striprtf", "striprtf", ".rtf"),
        ("stl", "numpy-stl", ".stl"),
        ("vsdx", "vsdx", ".vsdx"),
    ]

    OCR_DEPS = [
        ("pytesseract", "pytesseract", "scanned PDFs, images"),
        ("pdf2image", "pdf2image", "PDF OCR pipeline"),
        ("PIL", "Pillow", "image processing"),
        ("pdfplumber", "pdfplumber", "PDF fallback extraction"),
    ]

    @pytest.mark.parametrize(
        "module_name,pip_name,file_types",
        REQUIRED_PARSER_DEPS,
        ids=[d[1] for d in REQUIRED_PARSER_DEPS],
    )
    def test_parser_dep_importable(self, module_name, pip_name, file_types):
        """Each parser dependency must be importable.

        If this fails, run: pip install {pip_name}
        Without it, {file_types} files silently return empty text.
        """
        try:
            __import__(module_name)
        except ImportError:
            pytest.fail(
                f"Parser dependency '{pip_name}' not installed!\n"
                f"  Affected file types: {file_types}\n"
                f"  Fix: pip install {pip_name}\n"
                f"  See: docs/cross_ai_collabs/003_parser_coverage_gap_analysis.md"
            )

    @pytest.mark.parametrize(
        "module_name,pip_name,file_types",
        OCR_DEPS,
        ids=[d[1] for d in OCR_DEPS],
    )
    def test_ocr_dep_importable(self, module_name, pip_name, file_types):
        """OCR wrapper packages must be importable.

        Note: The actual OCR binaries (tesseract, poppler) are system-level
        installs and can't be tested via import. This only checks the Python
        wrapper packages.
        """
        try:
            __import__(module_name)
        except ImportError:
            pytest.fail(
                f"OCR dependency '{pip_name}' not installed!\n"
                f"  Affected: {file_types}\n"
                f"  Fix: pip install {pip_name}"
            )


class TestParserRegistryIntegrity:
    """Verify every registered extension has a functioning parser class."""

    def test_all_registered_parsers_instantiate(self):
        """Every parser class in the registry must be instantiable."""
        from src.parsers.registry import REGISTRY

        failures = []
        for ext in REGISTRY.supported_extensions():
            info = REGISTRY.get(ext)
            try:
                parser = info.parser_cls()
                assert hasattr(parser, "parse"), f"{ext}: parser has no parse() method"
                assert hasattr(parser, "parse_with_details"), f"{ext}: parser has no parse_with_details()"
            except Exception as e:
                failures.append(f"{ext} ({info.name}): {type(e).__name__}: {e}")

        assert not failures, (
            f"Parser instantiation failures:\n" + "\n".join(f"  - {f}" for f in failures)
        )

    def test_registry_has_minimum_extensions(self):
        """Registry must have at least 60 extensions (sanity check)."""
        from src.parsers.registry import REGISTRY

        count = len(REGISTRY.supported_extensions())
        assert count >= 60, (
            f"Registry only has {count} extensions (expected >= 60). "
            f"Did someone accidentally remove parsers?"
        )

    def test_no_duplicate_extensions(self):
        """No extension should be registered twice."""
        from src.parsers.registry import REGISTRY

        exts = REGISTRY.supported_extensions()
        assert len(exts) == len(set(exts)), (
            f"Duplicate extensions found: "
            f"{[e for e in exts if exts.count(e) > 1]}"
        )
