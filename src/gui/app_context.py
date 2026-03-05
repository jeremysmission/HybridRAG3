# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the app context part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Singleton access point for the GUI Controller instance
from __future__ import annotations
from src.gui.core.paths import AppPaths
from src.gui.core.controller import Controller

_controller = None


def get_controller() -> Controller:
    """Return the module-level Controller singleton, creating it on first call."""
    global _controller
    if _controller is None:
        _controller = Controller(AppPaths.default())
    return _controller
