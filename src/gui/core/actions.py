# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the actions part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Immutable dataclass definitions for GUI action commands
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ImportSourceAction:
    """Plain-English: This class groups logic for importsourceaction."""
    source_folder: str


@dataclass(frozen=True)
class IndexAction:
    """Plain-English: This class groups logic for indexaction."""
    pass


@dataclass(frozen=True)
class QueryAction:
    """Plain-English: This class groups logic for queryaction."""
    query: str
    top_k: int = 5


@dataclass(frozen=True)
class ExportCsvAction:
    """Plain-English: This class groups logic for exportcsvaction."""
    kind: str  # "cost" | "eval"
    suggested_name: str = ""


@dataclass(frozen=True)
class SaveNoteAction:
    """Plain-English: This class groups logic for savenoteaction."""
    note_id: str
    content: str
