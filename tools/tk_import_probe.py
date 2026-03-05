# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the tk import probe operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from __future__ import annotations
import sys, tkinter as tk
import _tkinter
print("exe:", sys.executable)
print("_tkinter file:", getattr(_tkinter, "__file__", None))
print("tcl_version:", tk.Tcl().eval("info patchlevel"))
print("tk_library:", tk.Tcl().eval("set tk_library"))
