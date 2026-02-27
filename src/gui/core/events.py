from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class GuiEvent:
    event: str
    timestamp: str
    run_id: str
    job_id: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["data"] is None:
            d["data"] = {}
        return d

def make_event(event: str, run_id: str, job_id: Optional[str] = None, message: str = "", **data: Any) -> GuiEvent:
    return GuiEvent(event=event, timestamp=_now_iso(), run_id=run_id, job_id=job_id, message=message, data=dict(data))
