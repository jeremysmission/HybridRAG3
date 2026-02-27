from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ImportSourceAction:
    source_folder: str


@dataclass(frozen=True)
class IndexAction:
    pass


@dataclass(frozen=True)
class QueryAction:
    query: str
    top_k: int = 5


@dataclass(frozen=True)
class ExportCsvAction:
    kind: str  # "cost" | "eval"
    suggested_name: str = ""


@dataclass(frozen=True)
class SaveNoteAction:
    note_id: str
    content: str
