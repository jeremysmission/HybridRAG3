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
    job_id: str
    name: str


class JobRunner:
    def __init__(self, diag: Diagnostics, emit: Callable[[object], None]) -> None:
        self._diag = diag
        self._emit = emit

    def run_bg(self, name: str, fn: Callable[[], None]) -> JobHandle:
        job_id = str(uuid.uuid4())
        handle = JobHandle(job_id=job_id, name=name)

        def _target() -> None:
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
