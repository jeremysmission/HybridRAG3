# ===================================================================
# WHAT: Test suite aggregator -- confirms all expected test files exist
# WHY:  Acts as a manifest so the quality audit (run_audit.py) can
#       detect if any test file was accidentally deleted or renamed
# HOW:  Lists all expected test file names and checks they exist on disk.
#       Virtual test files are private-only (excluded from Educational
#       sync) so they are checked separately and skipped when absent.
# USAGE: python tests/test_all.py  (or called by run_audit.py)
# ===================================================================

from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent

# Core test files that must exist in ALL repos (private + educational)
EXPECTED_CORE_FILES = [
    "test_config_snapshot.py",
    "test_indexer.py",
    "test_query_engine.py",
    "test_query_cache.py",
    "test_query_classifier.py",
    "test_query_expander.py",
    "test_ollama_router.py",
    "test_pii_scrubber.py",
    "test_cost_tracker.py",
    "test_credential_management.py",
    "test_gui_integration_w4.py",
    "test_bulk_transfer_stress.py",
    "test_phase3_stress.py",
    "test_api_router.py",
    "test_deployment_routing.py",
    "test_provider_proxy.py",
    "test_vllm_router.py",
    "test_eval_tuning_panel.py",
]

# Private-only files (excluded from Educational sync by sync_to_educational.py)
PRIVATE_ONLY_FILES = [
    "virtual_test_framework.py",
    "virtual_test_phase1_foundation.py",
    "virtual_test_phase2_exhaustive.py",
    "virtual_test_phase4_exhaustive.py",
]


def test_all_test_files_present():
    """Verify all expected core test modules exist on disk."""
    missing = []
    for filename in EXPECTED_CORE_FILES:
        path = TEST_DIR / filename
        if not path.exists():
            missing.append(filename)
    assert len(missing) == 0, f"Missing test files: {missing}"


def test_private_test_files_if_available():
    """Check private virtual test files exist (skipped in Educational repo)."""
    # If ANY virtual test file exists, ALL should exist
    present = [f for f in PRIVATE_ONLY_FILES if (TEST_DIR / f).exists()]
    if not present:
        return  # Educational repo -- skip check
    missing = [f for f in PRIVATE_ONLY_FILES if not (TEST_DIR / f).exists()]
    assert len(missing) == 0, f"Partial virtual test set: {missing}"
