# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the paths part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Application path configuration for downloads, diagnostics, and run folders
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@dataclass
class AppPaths:
    """Plain-English: This class groups logic for apppaths."""
    downloads_root: str
    diagnostics_root: str

    def new_run_folder(self, run_id: str) -> str:
        """Plain-English: This function handles new run folder."""
        path = os.path.join(self.diagnostics_root, run_id)
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def default(cls) -> AppPaths:
        """Plain-English: This function handles default."""
        return cls(
            downloads_root=os.path.join(_PROJECT_ROOT, "output", "downloads"),
            diagnostics_root=os.path.join(_PROJECT_ROOT, "output", "diagnostics"),
        )


def dated_download_dir(root: str) -> str:
    """Plain-English: This function handles dated download dir."""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(root, today)


def make_download_filename(name: str, ext: str) -> str:
    """Plain-English: This function handles make download filename."""
    ts = datetime.now().strftime("%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_")
    return f"{safe_name}_{ts}.{ext}"
