# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the path io part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Cross-platform path helpers for file IO
# FILE: src/tools/path_io.py
# ============================================================================

from __future__ import annotations

import os


def to_io_path(path: str) -> str:
    """
    Convert to an OS-usable IO path.

    On Windows, returns extended-length path form (\\\\?\\...) so the
    transfer pipeline can preserve full folder/file names beyond MAX_PATH.
    """
    if os.name != "nt":
        return path
    if not path:
        return path
    p = str(path)
    if p.startswith("\\\\?\\"):
        return p
    # UNC path: \\server\share\... -> \\?\UNC\server\share\...
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p.lstrip("\\")
    # Local path: C:\... -> \\?\C:\...
    return "\\\\?\\" + os.path.abspath(p)

