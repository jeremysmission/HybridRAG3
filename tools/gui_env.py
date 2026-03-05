# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the gui env operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Headless safety layer for GUI tests.

Provides display detection and safe Tk initialization so that
GUI-related tests skip cleanly in headless (CI/SSH) environments
instead of crashing with TclError.

Usage in pytest:
    from tools.gui_env import has_display
    pytestmark = pytest.mark.skipif(not has_display(), reason="requires display")

Usage in scripts:
    from tools.gui_env import safe_tk_init
    root = safe_tk_init()
    if root is None:
        print("No display available")
        sys.exit(0)
"""
from __future__ import annotations

import os
import sys
import functools

_display_cache: bool | None = None


def has_display() -> bool:
    """Return True if a Tk display can be created.

    Caches result after first call. Safe to call repeatedly.
    """
    global _display_cache
    if _display_cache is not None:
        return _display_cache

    # Fast pre-checks
    if sys.platform != "win32":
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            _display_cache = False
            return False

    # Actually try to create a Tk instance
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        _display_cache = True
    except Exception:
        _display_cache = False

    return _display_cache


def safe_tk_init():
    """Create and return a Tk root if display is available.

    Returns None if no display. Caller is responsible for
    destroying the returned root.
    """
    if not has_display():
        return None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception:
        return None


def skip_without_display(reason="requires display"):
    """Pytest skip decorator for tests requiring a display."""
    import pytest
    return pytest.mark.skipif(not has_display(), reason=reason)
