# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies boot-summary pending-state behavior and protects against regressions.
# What to read first: Start at the top-level test functions.
# Inputs: Lightweight BootResult instances only.
# Outputs: Assertions about summary text.
# Safety notes: No I/O or network.
# ============================

from src.core.boot import BootResult


def test_boot_summary_shows_pending_when_offline_probe_is_pending():
    result = BootResult(
        success=True,
        online_available=False,
        offline_available=False,
        offline_probe_pending=True,
    )

    summary = result.summary()

    assert "Overall:  PENDING" in summary
    assert "Offline:  PENDING" in summary


def test_boot_summary_shows_ready_when_offline_is_available():
    result = BootResult(
        success=True,
        online_available=False,
        offline_available=True,
        offline_probe_pending=False,
    )

    summary = result.summary()

    assert "Overall:  READY" in summary
    assert "Offline:  AVAILABLE" in summary
