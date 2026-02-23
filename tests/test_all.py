# ===================================================================
# WHAT: Test suite aggregator -- confirms all expected test files exist
# WHY:  Acts as a manifest so the quality audit (run_audit.py) can
#       detect if any test file was accidentally deleted or renamed
# HOW:  Lists all expected test file names and checks they exist on disk
# USAGE: python tests/test_all.py  (or called by run_audit.py)
# ===================================================================

from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent

EXPECTED_TEST_FILES = [
    "virtual_test_framework.py",
    "virtual_test_phase1_foundation.py",
    "virtual_test_phase2_exhaustive.py",
    "virtual_test_phase4_exhaustive.py",
]


def test_all_test_files_present():
    """Verify all expected test modules exist on disk."""
    missing = []
    for filename in EXPECTED_TEST_FILES:
        path = TEST_DIR / filename
        if not path.exists():
            missing.append(filename)
    assert len(missing) == 0, f"Missing test files: {missing}"