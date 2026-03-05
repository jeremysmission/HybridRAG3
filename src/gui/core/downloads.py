# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the downloads part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# In-memory registry tracking file download records and their statuses
from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DownloadRecord:
    """Plain-English: This class groups logic for downloadrecord."""
    job_id: str
    kind: str
    path: str
    status: str  # "pending"|"complete"|"failed"
    meta: Dict[str, Any]


class DownloadsRegistry:
    """Plain-English: This class groups logic for downloadsregistry."""
    def __init__(self) -> None:
        """Plain-English: This function handles init."""
        self._items: List[DownloadRecord] = []

    def register(self, job_id: str, kind: str, path: str, status: str, **meta: Any) -> None:
        """Plain-English: This function handles register."""
        self._items.append(DownloadRecord(job_id=job_id, kind=kind, path=path, status=status, meta=dict(meta)))

    def update_status(self, job_id: str, status: str, **meta: Any) -> None:
        """Plain-English: This function handles update status."""
        for it in self._items:
            if it.job_id == job_id:
                it.status = status
                it.meta.update(meta)
                return

    def list(self) -> List[Dict[str, Any]]:
        """Plain-English: This function handles list."""
        out = []
        for it in self._items:
            d = asdict(it)
            d["exists"] = os.path.exists(it.path)
            out.append(d)
        return out

    def last(self) -> Optional[Dict[str, Any]]:
        """Plain-English: This function handles last."""
        return self.list()[-1] if self._items else None
