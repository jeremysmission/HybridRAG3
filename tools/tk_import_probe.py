from __future__ import annotations
import sys, tkinter as tk
import _tkinter
print("exe:", sys.executable)
print("_tkinter file:", getattr(_tkinter, "__file__", None))
print("tcl_version:", tk.Tcl().eval("info patchlevel"))
print("tk_library:", tk.Tcl().eval("set tk_library"))
