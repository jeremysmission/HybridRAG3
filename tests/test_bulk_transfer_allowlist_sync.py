# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the bulk transfer allowlist sync area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Guardrail test for bulk transfer discovery extension allowlist.
# WHY:  Prevent drift where downloader skips parser-supported formats.
# HOW:  Compares bulk_transfer_v2 extension set to parser registry.
# ===================================================================

from src.parsers.registry import REGISTRY
from src.tools.bulk_transfer_v2 import _RAG_EXTENSIONS


def _norm(exts):
    return {
        str(ext).strip().lower()
        for ext in exts
        if str(ext).strip().startswith(".")
    }


def test_bulk_transfer_allowlist_matches_registry():
    """Downloader discovery allowlist must match parser registry exactly."""
    bulk_exts = _norm(_RAG_EXTENSIONS)
    reg_exts = _norm(REGISTRY.supported_extensions())
    assert bulk_exts == reg_exts, (
        "bulk_transfer_v2 extension allowlist drifted from parser registry.\n"
        f"Missing in downloader: {sorted(reg_exts - bulk_exts)}\n"
        f"Extra in downloader: {sorted(bulk_exts - reg_exts)}"
    )
