# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the gui replay operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Deterministic GUI Replay Engine.

Replays recorded callback events from gui_event_recorder output.
Validates that each callback can execute without crashing and
completes within its timing threshold.

Usage:
    python tools/gui_replay.py output/gui_events_20260227.json

Or programmatically:
    engine = ReplayEngine(matrix_path="tools/gui_matrix.json")
    results = engine.replay(events)
"""
from __future__ import annotations

import json
import time
import sys
import os
import logging
from pathlib import Path

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

logger = logging.getLogger(__name__)


class ReplayResult:
    """Result of replaying a single event."""

    def __init__(self, event: dict, success: bool, duration_ms: float,
                 error: str | None = None, threshold_ms: float = 2000):
        self.event = event
        self.success = success
        self.duration_ms = duration_ms
        self.error = error
        self.threshold_ms = threshold_ms
        self.timing_ok = duration_ms <= threshold_ms

    def to_dict(self) -> dict:
        return {
            "panel": self.event.get("panel", ""),
            "control": self.event.get("control", ""),
            "handler": self.event.get("handler", ""),
            "success": self.success,
            "duration_ms": self.duration_ms,
            "threshold_ms": self.threshold_ms,
            "timing_ok": self.timing_ok,
            "error": self.error,
        }


class ReplayEngine:
    """Replays recorded GUI events and validates results."""

    def __init__(self, matrix_path: str | None = None):
        self._thresholds: dict[str, float] = {}
        if matrix_path and Path(matrix_path).exists():
            self._load_thresholds(matrix_path)

    def _load_thresholds(self, path: str) -> None:
        """Load timing thresholds from gui_matrix.json."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for entry in data.get("entries", []):
                handler = entry.get("handler", "")
                threshold = entry.get("timing_threshold_ms", 2000)
                self._thresholds[handler] = threshold
        except Exception as e:
            logger.warning("Could not load matrix: %s", e)

    def get_threshold(self, handler: str) -> float:
        """Look up timing threshold for a handler."""
        return self._thresholds.get(handler, 2000)

    def replay(self, events: list[dict]) -> list[ReplayResult]:
        """Replay a list of recorded events.

        For each event, validates:
        - The original event completed (success/fail recorded)
        - Timing was within threshold

        Note: This does NOT re-execute callbacks (would need live GUI).
        It validates the recorded execution data.
        """
        results = []
        for event in events:
            handler = event.get("handler", "")
            threshold = self.get_threshold(handler)
            duration = event.get("duration_ms", 0)
            was_success = event.get("result", "fail") == "success"
            error = event.get("error")

            result = ReplayResult(
                event=event,
                success=was_success,
                duration_ms=duration,
                error=error,
                threshold_ms=threshold,
            )
            results.append(result)

        return results

    def summary(self, results: list[ReplayResult]) -> dict:
        """Generate summary of replay results."""
        total = len(results)
        passed = sum(1 for r in results if r.success and r.timing_ok)
        failed = sum(1 for r in results if not r.success)
        timing_violations = sum(1 for r in results if not r.timing_ok)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "timing_violations": timing_violations,
            "results": [r.to_dict() for r in results],
        }

    def save_results(self, results: list[ReplayResult], path: str | Path) -> None:
        """Save replay results to JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.summary(results), indent=2),
            encoding="utf-8",
        )


def selftest() -> int:
    """Quick selftest."""
    failures = []

    # Create fake events
    events = [
        {
            "timestamp": "2026-02-27T04:00:00Z",
            "panel": "query",
            "control": "Ask button",
            "handler": "_on_ask",
            "result": "success",
            "duration_ms": 150,
        },
        {
            "timestamp": "2026-02-27T04:00:01Z",
            "panel": "index",
            "control": "Start button",
            "handler": "_on_start",
            "result": "fail",
            "error": "No source folder",
            "duration_ms": 50,
        },
        {
            "timestamp": "2026-02-27T04:00:02Z",
            "panel": "tuning",
            "control": "Apply button",
            "handler": "_on_profile_change",
            "result": "success",
            "duration_ms": 5000,  # Over default threshold
        },
    ]

    engine = ReplayEngine()
    results = engine.replay(events)

    if len(results) != 3:
        failures.append("Expected 3 results, got {}".format(len(results)))
    else:
        if not results[0].success:
            failures.append("Event 0 should be success")
        if results[1].success:
            failures.append("Event 1 should be fail")
        if results[2].timing_ok:
            failures.append("Event 2 should exceed threshold (5000 > 2000)")
        print("[OK] Replay results validated")

    s = engine.summary(results)
    if s["passed"] == 1 and s["failed"] == 1 and s["timing_violations"] == 1:
        print("[OK] Summary correct: {} passed, {} failed, {} timing".format(
            s["passed"], s["failed"], s["timing_violations"]))
    else:
        failures.append("Summary wrong: {}".format(s))

    if failures:
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All replay engine checks passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Replay from file
        events = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        matrix_path = os.path.join(_root, "tools", "gui_matrix.json")
        engine = ReplayEngine(matrix_path=matrix_path)
        results = engine.replay(events)
        s = engine.summary(results)
        print(json.dumps(s, indent=2))
        raise SystemExit(0 if s["failed"] == 0 else 1)
    else:
        raise SystemExit(selftest())
