# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the index schedule part of the application runtime.
# What to read first: Start at IndexScheduleTracker, then read maybe_launch_scheduled_index().
# Inputs: Environment schedule settings, current time, and a callback that can launch indexing.
# Outputs: Snapshot dicts for API/UI surfaces plus start decisions for due scheduled runs.
# Safety notes: The scheduler only runs when explicitly enabled or when an interval is provided.
# ============================

from __future__ import annotations

import inspect
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _safe_positive_int(raw: object, default: int) -> int:
    value = str(raw or "").strip()
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    raise TypeError(f"Unsupported schedule timestamp type: {type(value)!r}")


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _accepts_keyword(func: Callable[..., object], name: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == name and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return True
    return False


@dataclass
class IndexScheduleTracker:
    """Mutable schedule state for recurring indexing runs."""

    interval_seconds: int = 0
    source_folder: str = ""
    enabled: Optional[bool] = None
    created_at: Optional[datetime] = None
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    last_status: str = ""
    last_error: str = ""
    last_trigger: str = ""
    total_runs: int = 0
    total_success: int = 0
    total_failed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.interval_seconds = max(0, int(self.interval_seconds or 0))
        self.source_folder = str(self.source_folder or "").strip()
        self.created_at = _coerce_datetime(self.created_at) or _utc_now()
        self.last_started_at = _coerce_datetime(self.last_started_at)
        self.last_finished_at = _coerce_datetime(self.last_finished_at)
        if self.enabled is None:
            self.enabled = self.interval_seconds > 0
        else:
            self.enabled = bool(self.enabled)
        if not self.last_status:
            self.last_status = "idle" if self.enabled else "disabled"

    @classmethod
    def from_env(cls, source_folder: str = "") -> "IndexScheduleTracker":
        raw_enabled = (os.environ.get("HYBRIDRAG_INDEX_SCHEDULE_ENABLED") or "").strip()
        raw_seconds = (os.environ.get("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_SECONDS") or "").strip()
        raw_minutes = (os.environ.get("HYBRIDRAG_INDEX_SCHEDULE_INTERVAL_MINUTES") or "").strip()

        if raw_seconds.isdigit():
            interval_seconds = max(1, int(raw_seconds))
        elif raw_minutes.isdigit():
            interval_seconds = max(1, int(raw_minutes)) * 60
        elif raw_enabled and _truthy_env("HYBRIDRAG_INDEX_SCHEDULE_ENABLED"):
            interval_seconds = 240 * 60
        else:
            interval_seconds = 0

        if raw_enabled:
            enabled = _truthy_env("HYBRIDRAG_INDEX_SCHEDULE_ENABLED")
        else:
            enabled = interval_seconds > 0

        source_override = (os.environ.get("HYBRIDRAG_INDEX_SCHEDULE_SOURCE_FOLDER") or "").strip()
        return cls(
            interval_seconds=interval_seconds,
            source_folder=source_override or str(source_folder or ""),
            enabled=enabled,
        )

    def next_run_at(self) -> Optional[datetime]:
        if not self.enabled or self.interval_seconds <= 0:
            return None
        with self._lock:
            anchor = self.last_started_at or self.last_finished_at or self.created_at
            return anchor + timedelta(seconds=self.interval_seconds)

    def due_now(self, *, now: object = None) -> bool:
        due_at = self.next_run_at()
        if due_at is None:
            return False
        current = _coerce_datetime(now) or _utc_now()
        return current >= due_at

    def note_run_started(self, *, trigger: str = "scheduled", now: object = None) -> None:
        self.record_run_started(
            trigger=trigger,
            source_folder=self.source_folder,
            now=now,
        )

    def note_run_finished(
        self,
        *,
        success: bool,
        error: str = "",
        trigger: str = "scheduled",
        now: object = None,
    ) -> None:
        self.record_run_finished(
            success=success,
            error=error,
            trigger=trigger,
            now=now,
        )

    def record_run_started(
        self,
        *,
        trigger: str,
        source_folder: str,
        now: object = None,
    ) -> None:
        if not self.enabled:
            return
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            self.source_folder = str(source_folder or self.source_folder or "").strip()
            self.last_started_at = current
            self.last_status = "running"
            self.last_error = ""
            self.last_trigger = str(trigger or "")
            self.total_runs += 1

    def record_run_finished(
        self,
        *,
        success: bool,
        error: str = "",
        trigger: str = "",
        stopped: bool = False,
        now: object = None,
    ) -> None:
        if not self.enabled:
            return
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            self.last_finished_at = current
            if trigger:
                self.last_trigger = str(trigger)
            self.last_error = "" if success and not stopped else str(error or "")
            if stopped:
                self.last_status = "stopped"
                return
            if success:
                self.last_status = "completed"
                self.total_success += 1
            else:
                self.last_status = "failed"
                self.total_failed += 1

    def record_attempt_outcome(
        self,
        *,
        status: str,
        error: str = "",
        trigger: str = "scheduled",
        now: object = None,
    ) -> None:
        if not self.enabled:
            return
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            self.last_finished_at = current
            self.last_status = str(status or "")
            self.last_error = str(error or "")
            self.last_trigger = str(trigger or "")

    def pause(self, *, now: object = None) -> None:
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            self.enabled = False
            self.last_finished_at = current
            self.last_status = "paused"
            self.last_error = ""
            self.last_trigger = "admin_pause"

    def resume(self, *, now: object = None, interval_seconds: int | None = None) -> None:
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            if interval_seconds is not None:
                self.interval_seconds = max(1, int(interval_seconds))
            elif self.interval_seconds <= 0:
                self.interval_seconds = 240 * 60
            self.enabled = True
            self.last_finished_at = current
            self.last_status = "idle"
            self.last_error = ""
            self.last_trigger = "admin_resume"

    def snapshot(
        self,
        *,
        indexing_active: bool = False,
        now: object = None,
    ) -> dict[str, object]:
        current = _coerce_datetime(now) or _utc_now()
        with self._lock:
            if not self.enabled or self.interval_seconds <= 0:
                next_run = None
            else:
                anchor = self.last_started_at or self.last_finished_at or self.created_at
                next_run = anchor + timedelta(seconds=self.interval_seconds)
            due_now = bool(
                self.enabled
                and not indexing_active
                and next_run is not None
                and current >= next_run
            )
            return {
                "enabled": bool(self.enabled),
                "interval_seconds": int(self.interval_seconds),
                "source_folder": str(self.source_folder or ""),
                "indexing_active": bool(indexing_active),
                "due_now": due_now,
                "next_run_at": _iso_or_none(next_run),
                "last_started_at": _iso_or_none(self.last_started_at),
                "last_finished_at": _iso_or_none(self.last_finished_at),
                "last_status": str(self.last_status or ""),
                "last_error": str(self.last_error or ""),
                "last_trigger": str(self.last_trigger or ""),
                "total_runs": int(self.total_runs),
                "total_success": int(self.total_success),
                "total_failed": int(self.total_failed),
            }


def maybe_launch_scheduled_index(
    state: Any,
    start_indexing: Callable[..., bool],
    *,
    now: object = None,
) -> bool:
    """Launch a due scheduled index run by reusing the shared worker."""
    tracker = getattr(state, "index_schedule", None)
    if tracker is None or not getattr(tracker, "enabled", False):
        return False

    current = _coerce_datetime(now) or _utc_now()
    if bool(getattr(state, "indexing_active", False)):
        if tracker.due_now(now=current):
            tracker.record_attempt_outcome(
                status="busy",
                error="Indexing is already in progress.",
                trigger="scheduled",
                now=current,
            )
        return False

    if not tracker.due_now(now=current):
        return False

    source_folder = str(
        getattr(tracker, "source_folder", "")
        or getattr(getattr(getattr(state, "config", None), "paths", None), "source_folder", "")
        or ""
    ).strip()
    if not source_folder or not os.path.isdir(source_folder):
        tracker.record_run_started(
            trigger="scheduled",
            source_folder=source_folder,
            now=current,
        )
        tracker.record_run_finished(
            success=False,
            error="Scheduled source folder not found or not accessible",
            trigger="scheduled",
            now=current,
        )
        return False

    supports_trigger = _accepts_keyword(start_indexing, "trigger")
    supports_on_complete = _accepts_keyword(start_indexing, "on_complete")

    if supports_trigger:
        before_runs = tracker.total_runs
        started = bool(start_indexing(source_folder, trigger="scheduled"))
        if started and tracker.total_runs == before_runs:
            tracker.record_run_started(
                trigger="scheduled",
                source_folder=source_folder,
                now=current,
            )
        return started

    tracker.record_run_started(
        trigger="scheduled",
        source_folder=source_folder,
        now=current,
    )

    completion = None
    if supports_on_complete:
        completion = lambda success, error: tracker.record_run_finished(
            success=bool(success),
            error=str(error or ""),
            trigger="scheduled",
        )

    started = bool(start_indexing(source_folder, on_complete=completion))
    if started:
        return True

    tracker.record_run_finished(
        success=False,
        error="Scheduled indexing launch was rejected",
        trigger="scheduled",
        now=current,
    )
    return False
