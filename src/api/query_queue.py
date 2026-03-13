from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class QueryQueueFullError(RuntimeError):
    """Raised when the shared query queue is saturated."""


class QueryQueueTracker:
    """Thread-safe shared query admission and queue visibility tracker."""

    def __init__(self, max_concurrent: int = 0, max_queue: int = 0) -> None:
        self.max_concurrent = max(0, int(max_concurrent or 0))
        self.max_queue = max(0, int(max_queue or 0))
        self.enabled = self.max_concurrent > 0
        self._condition = threading.Condition()
        self._active = 0
        self._waiting = 0
        self._max_waiting_seen = 0
        self._total_started = 0
        self._total_completed = 0
        self._total_rejected = 0
        self._last_started_at: Optional[str] = None
        self._last_completed_at: Optional[str] = None
        self._last_rejected_at: Optional[str] = None

    @classmethod
    def from_env(cls) -> "QueryQueueTracker":
        raw_concurrent = (os.environ.get("HYBRIDRAG_QUERY_CONCURRENCY_MAX") or "").strip()
        raw_queue = (os.environ.get("HYBRIDRAG_QUERY_QUEUE_MAX") or "").strip()

        max_concurrent = int(raw_concurrent) if raw_concurrent.isdigit() else 0
        if raw_queue.isdigit():
            max_queue = int(raw_queue)
        elif max_concurrent > 0:
            max_queue = max_concurrent * 2
        else:
            max_queue = 0
        return cls(max_concurrent=max_concurrent, max_queue=max_queue)

    def reset(self) -> None:
        with self._condition:
            self._active = 0
            self._waiting = 0
            self._max_waiting_seen = 0
            self._total_started = 0
            self._total_completed = 0
            self._total_rejected = 0
            self._last_started_at = None
            self._last_completed_at = None
            self._last_rejected_at = None

    def acquire(self) -> None:
        """Reserve a shared query slot, waiting in the bounded queue if needed."""
        with self._condition:
            if not self.enabled:
                self._active += 1
                self._mark_started_locked()
                return

            if self._active < self.max_concurrent:
                self._active += 1
                self._mark_started_locked()
                return

            if self._waiting >= self.max_queue:
                self._total_rejected += 1
                self._last_rejected_at = _now_iso()
                raise QueryQueueFullError("Query queue is full")

            self._waiting += 1
            self._max_waiting_seen = max(self._max_waiting_seen, self._waiting)
            try:
                while self._active >= self.max_concurrent:
                    self._condition.wait()
                self._waiting -= 1
                self._active += 1
                self._mark_started_locked()
            except BaseException:
                self._waiting = max(0, self._waiting - 1)
                raise

    def release(self) -> None:
        """Release one active shared query slot."""
        with self._condition:
            if self._active <= 0:
                return
            self._active -= 1
            self._total_completed += 1
            self._last_completed_at = _now_iso()
            self._condition.notify()

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            available_slots: Optional[int]
            saturated = False
            if self.enabled:
                available_slots = max(0, self.max_concurrent - self._active)
                saturated = self._active >= self.max_concurrent
            else:
                available_slots = None

            return {
                "enabled": self.enabled,
                "max_concurrent": self.max_concurrent,
                "max_queue": self.max_queue,
                "active_queries": self._active,
                "waiting_queries": self._waiting,
                "available_slots": available_slots,
                "saturated": saturated,
                "max_waiting_seen": self._max_waiting_seen,
                "total_started": self._total_started,
                "total_completed": self._total_completed,
                "total_rejected": self._total_rejected,
                "last_started_at": self._last_started_at,
                "last_completed_at": self._last_completed_at,
                "last_rejected_at": self._last_rejected_at,
            }

    def _mark_started_locked(self) -> None:
        self._total_started += 1
        self._last_started_at = _now_iso()
