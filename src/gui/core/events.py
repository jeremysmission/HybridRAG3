# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the events part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Structured GUI event dataclass and factory for diagnostics logging
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

def _now_iso() -> str:
    """Plain-English: This function handles now iso."""
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class GuiEvent:
    """Plain-English: This class groups logic for guievent."""
    event: str
    timestamp: str
    run_id: str
    job_id: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Plain-English: This function handles to dict."""
        d = asdict(self)
        if d["data"] is None:
            d["data"] = {}
        return d

def make_event(event: str, run_id: str, job_id: Optional[str] = None, message: str = "", **data: Any) -> GuiEvent:
    """Plain-English: This function handles make event."""
    return GuiEvent(event=event, timestamp=_now_iso(), run_id=run_id, job_id=job_id, message=message, data=dict(data))
