# In-memory registry tracking file download records and their statuses
from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DownloadRecord:
    job_id: str
    kind: str
    path: str
    status: str  # "pending"|"complete"|"failed"
    meta: Dict[str, Any]


class DownloadsRegistry:
    def __init__(self) -> None:
        self._items: List[DownloadRecord] = []

    def register(self, job_id: str, kind: str, path: str, status: str, **meta: Any) -> None:
        self._items.append(DownloadRecord(job_id=job_id, kind=kind, path=path, status=status, meta=dict(meta)))

    def update_status(self, job_id: str, status: str, **meta: Any) -> None:
        for it in self._items:
            if it.job_id == job_id:
                it.status = status
                it.meta.update(meta)
                return

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for it in self._items:
            d = asdict(it)
            d["exists"] = os.path.exists(it.path)
            out.append(d)
        return out

    def last(self) -> Optional[Dict[str, Any]]:
        return self.list()[-1] if self._items else None
