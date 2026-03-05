# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the tk part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Tk Window Utilities (src/gui/tk_utils.py)
# ============================================================================
# WHAT: Helpers for Tk window management on Windows.
# WHY:  Tk Toplevel windows launched from a console .bat often open behind
#       the terminal, making the GUI appear "hung".  Corporate desktops
#       with group policies can make this worse.  These utilities force
#       the window visible, centered, and focused.
# HOW:  withdraw/deiconify cycle, transient binding, topmost toggle,
#       focus_force, and screen-center geometry.
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import tkinter as tk


def force_foreground(win: tk.Toplevel, parent: tk.Tk | None = None) -> None:
    """Make a Toplevel reliably appear in front on Windows.

    Safe to call multiple times.  Never raises -- startup must not
    crash because a cosmetic helper failed.
    """
    try:
        # Ensure window exists and has a normal state
        win.withdraw()
        win.update_idletasks()
        win.deiconify()
        win.update_idletasks()

        # Bind to parent stacking order
        if parent is not None:
            try:
                win.transient(parent)
            except Exception:
                pass

        # Center on screen (prevents off-screen invisible)
        _center_window(win)

        # Raise + Windows focus hacks
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()

        # Release topmost after a beat (prevents always-on-top annoyance)
        win.after(250, lambda: _safe_topmost_off(win))

        # Extra lift after idle (some Windows shells steal focus back)
        win.after(10, win.lift)
        win.after(20, win.focus_force)

    except Exception:
        pass


def _safe_topmost_off(win: tk.Toplevel) -> None:
    """Plain-English: This function handles safe topmost off."""
    try:
        if win.winfo_exists():
            win.attributes("-topmost", False)
    except Exception:
        pass


def _center_window(win: tk.Toplevel) -> None:
    """Plain-English: This function handles center window."""
    try:
        win.update_idletasks()
        w = win.winfo_width() or win.winfo_reqwidth()
        h = win.winfo_height() or win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        win.geometry("+{}+{}".format(x, y))
    except Exception:
        pass
