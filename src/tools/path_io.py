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

