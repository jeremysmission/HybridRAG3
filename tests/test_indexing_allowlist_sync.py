"""
Guardrail tests: prevent parser-registry/allowlist drift.

WHY:
    We previously had parser modules registered in src/parsers/registry.py
    that were silently filtered out by IndexingConfig.supported_extensions.
    These tests fail fast if those two sources of truth diverge again.
"""

from src.core.config import IndexingConfig, load_config
from src.parsers.registry import REGISTRY
from unittest.mock import MagicMock
from pathlib import Path
import tempfile


def _norm(exts):
    """Normalize extensions for stable set comparison."""
    return {str(e).strip().lower() for e in exts if str(e).strip()}


def test_indexing_allowlist_matches_registry_defaults():
    """
    Default IndexingConfig allowlist must exactly match parser registry.
    """
    cfg_exts = _norm(IndexingConfig().supported_extensions)
    reg_exts = _norm(REGISTRY.supported_extensions())
    assert cfg_exts == reg_exts, (
        "Indexing allowlist drifted from parser registry.\n"
        f"Missing from config: {sorted(reg_exts - cfg_exts)}\n"
        f"Extra in config: {sorted(cfg_exts - reg_exts)}"
    )


def test_loaded_config_allowlist_matches_registry():
    """
    Loaded project config should remain in sync with parser registry.
    """
    cfg = load_config(".")
    cfg_exts = _norm(cfg.indexing.supported_extensions)
    reg_exts = _norm(REGISTRY.supported_extensions())
    assert cfg_exts == reg_exts, (
        "Loaded config indexing.supported_extensions drifted from registry.\n"
        f"Missing from config: {sorted(reg_exts - cfg_exts)}\n"
        f"Extra in config: {sorted(cfg_exts - reg_exts)}"
    )


def test_indexer_discovers_registry_formats_via_allowlist():
    """
    Integration guard: indexer discovery must include formats that previously
    drifted out of the config allowlist.
    """
    base_tmp = Path("output") / "pytest_tmp"
    base_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="allowlist_sync_", dir=str(base_tmp)) as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_exts = [".dxf", ".stp", ".pcap", ".msg", ".vsdx"]
        for ext in test_exts:
            (tmp_path / f"sample{ext}").write_text("x", encoding="utf-8")
        # Control file: this extension should remain excluded by allowlist.
        (tmp_path / "ignore.exe").write_text("x", encoding="utf-8")

        class _Cfg:
            pass

        cfg = _Cfg()
        cfg.indexing = IndexingConfig()

        from src.core.indexer import Indexer
        idx = Indexer(cfg, MagicMock(), MagicMock(), MagicMock())
        idx._process_single_file = lambda _: (0, "synthetic-skip", False)

        result = idx.index_folder(str(tmp_path))
        assert result["total_files_scanned"] == len(test_exts), (
            "Indexer discovery failed to include expected registry-backed formats."
        )
        assert result["total_files_skipped"] == len(test_exts)
