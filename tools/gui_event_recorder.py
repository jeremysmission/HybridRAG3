"""GUI Event Recorder -- wraps callbacks to log execution.

Records every GUI callback invocation with timing, state, and
result information. Output is a JSON file suitable for replay
testing and troubleshooting.

Usage:
    recorder = GuiEventRecorder(config)
    wrapped = recorder.wrap_callback("query", "Ask button", "_on_ask", original_fn)
    # ... bind wrapped instead of original_fn ...
    recorder.save("output/gui_events_20260227.json")
"""
from __future__ import annotations

import json
import time
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class GuiEventRecorder:
    """Records GUI callback events with timing and state."""

    def __init__(self, config=None):
        self.config = config
        self.events: list[dict] = []

    def _snapshot_state(self) -> dict:
        """Capture current system state for the event record."""
        state = {"mode": "unknown", "model": "unknown"}
        try:
            if self.config:
                state["mode"] = getattr(self.config, "mode", "unknown") or "unknown"
                ollama = getattr(self.config, "ollama", None)
                if ollama:
                    state["model"] = getattr(ollama, "model", "unknown") or "unknown"
        except Exception:
            pass
        return state

    def wrap_callback(self, panel: str, control: str, handler: str, fn):
        """Return a wrapped version of fn that records the call."""
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "panel": panel,
                "control": control,
                "handler": handler,
                "state": self._snapshot_state(),
                "result": "success",
                "error": None,
                "duration_ms": 0,
            }
            try:
                result = fn(*args, **kwargs)
                event["result"] = "success"
                return result
            except Exception as e:
                event["result"] = "fail"
                event["error"] = str(e)
                raise
            finally:
                event["duration_ms"] = round(
                    (time.perf_counter() - start) * 1000, 2)
                self.events.append(event)
        return wrapper

    def save(self, path: str | Path) -> None:
        """Write recorded events to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.events, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[OK] Saved %d events to %s", len(self.events), p)

    @staticmethod
    def load(path: str | Path) -> list[dict]:
        """Read events from a JSON file."""
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def summary(self) -> dict:
        """Return summary statistics."""
        total = len(self.events)
        passed = sum(1 for e in self.events if e["result"] == "success")
        failed = total - passed
        durations = [e["duration_ms"] for e in self.events]
        return {
            "total_events": total,
            "passed": passed,
            "failed": failed,
            "avg_duration_ms": round(sum(durations) / max(total, 1), 2),
            "max_duration_ms": max(durations) if durations else 0,
            "panels_touched": list(set(e["panel"] for e in self.events)),
        }

    def clear(self):
        """Clear all recorded events."""
        self.events.clear()


def selftest() -> int:
    """Quick selftest of the recorder."""
    failures = []

    rec = GuiEventRecorder()

    # Wrap a passing function
    def good_fn():
        return 42

    wrapped = rec.wrap_callback("test", "button", "good_fn", good_fn)
    result = wrapped()
    if result != 42:
        failures.append("Wrapped function returned wrong value")

    # Wrap a failing function
    def bad_fn():
        raise ValueError("test error")

    wrapped_bad = rec.wrap_callback("test", "button", "bad_fn", bad_fn)
    try:
        wrapped_bad()
        failures.append("bad_fn did not raise")
    except ValueError:
        pass

    # Check events recorded
    if len(rec.events) != 2:
        failures.append("Expected 2 events, got {}".format(len(rec.events)))
    else:
        if rec.events[0]["result"] != "success":
            failures.append("Event 0 should be success")
        if rec.events[1]["result"] != "fail":
            failures.append("Event 1 should be fail")
        if rec.events[1]["error"] != "test error":
            failures.append("Event 1 error mismatch")
        print("[OK] Events recorded correctly")

    # Summary
    s = rec.summary()
    if s["total_events"] == 2 and s["passed"] == 1 and s["failed"] == 1:
        print("[OK] Summary correct")
    else:
        failures.append("Summary incorrect: {}".format(s))

    # Save/load roundtrip
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = f.name
    try:
        rec.save(tmp)
        loaded = GuiEventRecorder.load(tmp)
        if len(loaded) == 2:
            print("[OK] Save/load roundtrip")
        else:
            failures.append("Load returned {} events".format(len(loaded)))
    finally:
        os.unlink(tmp)

    if failures:
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All event recorder checks passed")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(selftest())
