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
