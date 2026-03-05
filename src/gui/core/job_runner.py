# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the job runner part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Background thread job runner with event emission and error handling
from __future__ import annotations
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from .events import make_event
from .diagnostics import Diagnostics


@dataclass(frozen=True)
class JobHandle:
    """Plain-English: This class groups logic for jobhandle."""
    job_id: str
    name: str


class JobRunner:
    """Plain-English: This class groups logic for jobrunner."""
    def __init__(self, diag: Diagnostics, emit: Callable[[object], None]) -> None:
        """Plain-English: This function handles init."""
        self._diag = diag
        self._emit = emit

    def run_bg(self, name: str, fn: Callable[[], None]) -> JobHandle:
        """Plain-English: This function handles run bg."""
        job_id = str(uuid.uuid4())
        handle = JobHandle(job_id=job_id, name=name)

        def _target() -> None:
            """Plain-English: This function handles target."""
            self._emit(make_event("job_started", self._diag.run_id, job_id=job_id, message=name))
            try:
                fn()
                self._emit(make_event("job_completed", self._diag.run_id, job_id=job_id, message=name))
            except Exception as e:
                err_path = self._diag.write_error(f"job_{job_id}", e)
                self._emit(make_event("job_failed", self._diag.run_id, job_id=job_id, message=str(e), error_path=err_path))

        t = threading.Thread(target=_target, name=f"job:{name}", daemon=True)
        t.start()
        return handle
