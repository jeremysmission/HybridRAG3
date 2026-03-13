from __future__ import annotations

import os
import time
import uuid
import threading
from collections import deque
from datetime import datetime
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _compact_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _text_preview(value: str, max_len: int = 160) -> str:
    compact = _compact_text(value)
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


class QueryActivityHandle:
    """Single-query lifecycle handle returned by QueryActivityTracker.start()."""

    __slots__ = ("_tracker", "_query_id", "_started_monotonic", "_closed")

    def __init__(
        self,
        tracker: "QueryActivityTracker",
        query_id: str,
        started_monotonic: float,
    ) -> None:
        self._tracker = tracker
        self._query_id = query_id
        self._started_monotonic = started_monotonic
        self._closed = False

    def finish_result(self, result: Any) -> None:
        if self._closed:
            return
        self._closed = True
        self._tracker.finish_result(
            self._query_id,
            result,
            started_monotonic=self._started_monotonic,
        )

    def finish_error(
        self,
        error: str,
        *,
        mode: str = "",
        latency_ms: Optional[float] = None,
    ) -> None:
        if self._closed:
            return
        self._closed = True
        self._tracker.finish_error(
            self._query_id,
            error,
            mode=mode,
            latency_ms=latency_ms,
            started_monotonic=self._started_monotonic,
        )

    @property
    def query_id(self) -> str:
        return self._query_id

    def set_thread_context(
        self,
        thread_id: Optional[str],
        turn_index: Optional[int] = None,
    ) -> None:
        self._tracker.set_thread_context(
            self._query_id,
            thread_id=thread_id,
            turn_index=turn_index,
        )


class QueryActivityTracker:
    """Thread-safe in-memory recent query activity tracker for API surfaces."""

    def __init__(self, max_entries: int = 20) -> None:
        self.max_entries = max(1, int(max_entries or 20))
        self._lock = threading.Lock()
        self._active: dict[str, dict[str, Any]] = {}
        self._recent: deque[dict[str, Any]] = deque(maxlen=self.max_entries)
        self._total_completed = 0
        self._total_failed = 0
        self._last_completed_at: Optional[str] = None
        self._last_error_at: Optional[str] = None

    @classmethod
    def from_env(cls) -> "QueryActivityTracker":
        raw = (os.environ.get("HYBRIDRAG_QUERY_ACTIVITY_MAX") or "").strip()
        if raw.isdigit():
            return cls(max_entries=int(raw))
        return cls()

    def reset(self) -> None:
        with self._lock:
            self._active.clear()
            self._recent.clear()
            self._total_completed = 0
            self._total_failed = 0
            self._last_completed_at = None
            self._last_error_at = None

    def start(
        self,
        *,
        question: str,
        mode: str,
        transport: str,
        client_host: str,
        actor: str,
        actor_source: str,
        actor_role: str,
        allowed_doc_tags: list[str],
        document_policy_source: str,
        thread_id: Optional[str] = None,
    ) -> QueryActivityHandle:
        query_id = uuid.uuid4().hex[:12]
        entry = {
            "query_id": query_id,
            "question_text": _compact_text(question),
            "question_preview": _text_preview(question),
            "mode": str(mode or ""),
            "transport": str(transport or "sync"),
            "client_host": str(client_host or ""),
            "actor": str(actor or "anonymous"),
            "actor_source": str(actor_source or "anonymous"),
            "actor_role": str(actor_role or "viewer"),
            "allowed_doc_tags": list(allowed_doc_tags or []),
            "document_policy_source": str(document_policy_source or ""),
            "thread_id": str(thread_id or "").strip() or None,
            "turn_index": None,
            "status": "active",
            "started_at": _now_iso(),
            "completed_at": None,
            "latency_ms": None,
            "chunks_used": 0,
            "source_count": 0,
            "answer_preview": None,
            "source_paths": [],
            "denied_hits": 0,
            "error": None,
        }
        with self._lock:
            self._active[query_id] = entry
        return QueryActivityHandle(self, query_id, time.monotonic())

    def set_thread_context(
        self,
        query_id: str,
        *,
        thread_id: Optional[str],
        turn_index: Optional[int] = None,
    ) -> None:
        with self._lock:
            entry = self._active.get(query_id)
            if entry is None:
                for recent in self._recent:
                    if recent.get("query_id") == query_id:
                        entry = recent
                        break
            if entry is None:
                return
            entry["thread_id"] = str(thread_id or "").strip() or None
            entry["turn_index"] = None if turn_index is None else int(turn_index)

    def finish_result(
        self,
        query_id: str,
        result: Any,
        *,
        started_monotonic: float,
    ) -> None:
        latency_ms = getattr(result, "latency_ms", None)
        if latency_ms is None:
            latency_ms = (time.monotonic() - started_monotonic) * 1000.0
        error = str(getattr(result, "error", "") or "").strip()
        debug_trace = getattr(result, "debug_trace", None) or {}
        retrieval = debug_trace.get("retrieval", {}) if isinstance(debug_trace, dict) else {}
        access_control = (
            retrieval.get("access_control", {}) if isinstance(retrieval, dict) else {}
        )
        self._finish(
            query_id,
            status="error" if error else "completed",
            mode=str(getattr(result, "mode", "") or ""),
            latency_ms=float(latency_ms),
            chunks_used=int(getattr(result, "chunks_used", 0) or 0),
            source_count=len(getattr(result, "sources", []) or []),
            answer_preview=_text_preview(getattr(result, "answer", "") or "", max_len=280) or None,
            source_paths=[
                str(source.get("path") or "").strip()
                for source in (getattr(result, "sources", []) or [])
                if str(source.get("path") or "").strip()
            ][:4],
            denied_hits=int(access_control.get("denied_hits", 0) or 0),
            error=error or None,
        )

    def finish_error(
        self,
        query_id: str,
        error: str,
        *,
        mode: str,
        latency_ms: Optional[float],
        started_monotonic: float,
    ) -> None:
        effective_latency = latency_ms
        if effective_latency is None:
            effective_latency = (time.monotonic() - started_monotonic) * 1000.0
        self._finish(
            query_id,
            status="error",
            mode=mode,
            latency_ms=float(effective_latency),
            chunks_used=0,
            source_count=0,
            answer_preview=None,
            source_paths=[],
            denied_hits=0,
            error=str(error or "").strip() or "query_failed",
        )

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_queries": len(self._active),
                "recent_queries": len(self._recent),
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "last_completed_at": self._last_completed_at,
                "last_error_at": self._last_error_at,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = [dict(entry) for entry in self._active.values()]
            recent = [dict(entry) for entry in self._recent]
            return {
                "active_queries": len(active),
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "active": active,
                "recent": recent,
            }

    def _finish(
        self,
        query_id: str,
        *,
        status: str,
        mode: str,
        latency_ms: float,
        chunks_used: int,
        source_count: int,
        answer_preview: Optional[str],
        source_paths: list[str],
        denied_hits: int,
        error: Optional[str],
    ) -> None:
        completed_at = _now_iso()
        with self._lock:
            entry = self._active.pop(query_id, None)
            if entry is None:
                return
            entry["status"] = status
            if mode:
                entry["mode"] = mode
            entry["completed_at"] = completed_at
            entry["latency_ms"] = round(float(latency_ms), 2)
            entry["chunks_used"] = max(0, int(chunks_used))
            entry["source_count"] = max(0, int(source_count))
            entry["answer_preview"] = answer_preview or None
            entry["source_paths"] = list(source_paths or [])
            entry["denied_hits"] = max(0, int(denied_hits or 0))
            entry["error"] = error or None
            self._recent.appendleft(entry)
            if status == "error":
                self._total_failed += 1
                self._last_error_at = completed_at
            else:
                self._total_completed += 1
                self._last_completed_at = completed_at
