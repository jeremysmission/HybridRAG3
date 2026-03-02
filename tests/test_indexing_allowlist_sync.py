"""
Guardrail tests: prevent parser-registry/allowlist drift.

WHY:
    We previously had parser modules registered in src/parsers/registry.py
    that were silently filtered out by IndexingConfig.supported_extensions.
    These tests fail fast if those two sources of truth diverge again.
"""

from src.core.config import IndexingConfig, load_config
from src.parsers.registry import REGISTRY


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

