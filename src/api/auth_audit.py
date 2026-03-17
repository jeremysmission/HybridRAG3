from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

from fastapi import Request

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class AuthAuditTracker:
    """Thread-safe in-memory security activity tracker for auth/access events."""

    def __init__(
        self,
        *,
        max_entries: int = 80,
        window_seconds: int = 600,
    ) -> None:
        self.max_entries = max(10, int(max_entries or 80))
        self.window_seconds = max(60, int(window_seconds or 600))
        self._lock = threading.Lock()
        self._entries: deque[dict[str, object]] = deque(maxlen=self.max_entries)

    @classmethod
    def from_env(cls) -> "AuthAuditTracker":
        raw_max = (os.environ.get("HYBRIDRAG_AUTH_AUDIT_MAX") or "").strip()
        raw_window = (os.environ.get("HYBRIDRAG_AUTH_AUDIT_WINDOW_SECONDS") or "").strip()
        return cls(
            max_entries=int(raw_max) if raw_max.isdigit() else 80,
            window_seconds=int(raw_window) if raw_window.isdigit() else 600,
        )

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()

    def record(
        self,
        *,
        event: str,
        outcome: str,
        client_host: str,
        path: str,
        detail: str = "",
        actor: str = "",
    ) -> None:
        entry = {
            "timestamp": float(time.time()),
            "timestamp_iso": _now_iso(),
            "event": str(event or ""),
            "outcome": str(outcome or ""),
            "client_host": str(client_host or "unknown"),
            "path": str(path or ""),
            "detail": str(detail or ""),
            "actor": str(actor or ""),
        }
        with self._lock:
            self._entries.appendleft(entry)

    def snapshot(self, limit: int = 12) -> dict[str, object]:
        effective_limit = max(1, min(int(limit or 12), self.max_entries))
        cutoff = time.time() - float(self.window_seconds)
        with self._lock:
            entries = [dict(item) for item in list(self._entries)[:effective_limit]]
            recent_window = [
                dict(item)
                for item in self._entries
                if float(item.get("timestamp", 0.0) or 0.0) >= cutoff
            ]

        return {
            "window_seconds": self.window_seconds,
            "recent_total": len(recent_window),
            "recent_failures": sum(
                1 for item in recent_window if str(item.get("outcome", "") or "") == "denied"
            ),
            "recent_rate_limited": sum(
                1
                for item in recent_window
                if str(item.get("outcome", "") or "") == "rate_limited"
            ),
            "recent_proxy_rejections": sum(
                1
                for item in recent_window
                if str(item.get("event", "") or "") == "proxy_identity_rejected"
            ),
            "latest_event_at": str(entries[0].get("timestamp_iso", "") or "") if entries else None,
            "unique_hosts": sorted(
                {
                    str(item.get("client_host", "") or "")
                    for item in recent_window
                    if str(item.get("client_host", "") or "").strip()
                }
            ),
            "entries": entries,
        }


def record_auth_event(
    request: Request,
    *,
    event: str,
    outcome: str,
    detail: str = "",
    actor: str = "",
) -> None:
    """Best-effort recorder for security activity without making callers own state wiring."""
    try:
        from src.api.server import state
    except Exception as e:
        logger.warning(
            "[SECURITY] Auth event recording unavailable — %s event for %s lost: %s",
            event, outcome, e,
        )
        return

    tracker = getattr(state, "auth_audit", None)
    if tracker is None:
        tracker = AuthAuditTracker.from_env()
        state.auth_audit = tracker
    tracker.record(
        event=event,
        outcome=outcome,
        client_host=str(getattr(getattr(request, "client", None), "host", None) or "unknown"),
        path=str(getattr(getattr(request, "url", None), "path", "") or ""),
        detail=detail,
        actor=actor,
    )
