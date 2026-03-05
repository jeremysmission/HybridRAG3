# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the thread guard operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Thread safety guard for Tkinter GUI operations.

Tkinter is NOT thread-safe. All widget operations (config, pack,
grid, destroy, etc.) MUST happen on the main thread. Background
work (LLM calls, indexing, network) should run in worker threads
and post results back via root.after().

This module provides:
  - GuiThreadGuard: tracks main thread, asserts UI calls are safe
  - check_thread_safety: decorator for UI-touching methods
  - ThreadingViolation: explicit exception for violations

Usage:
    from tools.thread_guard import guard

    @guard.check
    def update_label(self):
        self.label.config(text="new")  # Safe: guard verified main thread

Selftest:
    python tools/thread_guard.py
"""
from __future__ import annotations

import threading
import functools
import logging

logger = logging.getLogger(__name__)


class ThreadingViolation(RuntimeError):
    """Raised when a UI operation happens outside the main thread."""
    pass


class GuiThreadGuard:
    """Tracks main thread and enforces UI-thread-only access."""

    def __init__(self):
        self._main_thread_id: int | None = None
        self._violations: list[dict] = []
        self._enabled = True

    def register_main_thread(self):
        """Call once from the main thread during app startup."""
        self._main_thread_id = threading.current_thread().ident
        logger.debug("GuiThreadGuard: main thread = %s", self._main_thread_id)

    def assert_main_thread(self, context: str = ""):
        """Raise ThreadingViolation if not on main thread."""
        if not self._enabled:
            return
        if self._main_thread_id is None:
            # Not yet registered -- skip check
            return
        current = threading.current_thread().ident
        if current != self._main_thread_id:
            violation = {
                "context": context,
                "thread_id": current,
                "thread_name": threading.current_thread().name,
                "main_thread_id": self._main_thread_id,
            }
            self._violations.append(violation)
            msg = (
                "UI operation on non-main thread: {} "
                "(current={}, main={})"
            ).format(context, current, self._main_thread_id)
            raise ThreadingViolation(msg)

    def check(self, func):
        """Decorator: assert main thread before calling func."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            self.assert_main_thread(
                context="{}.{}".format(
                    func.__qualname__, func.__name__
                ) if hasattr(func, "__qualname__") else func.__name__
            )
            return func(*args, **kwargs)
        return wrapper

    @property
    def violations(self) -> list[dict]:
        """Return list of recorded violations."""
        return list(self._violations)

    def reset(self):
        """Clear violation history."""
        self._violations.clear()

    def disable(self):
        """Disable thread checking (for tests that intentionally test threading)."""
        self._enabled = False

    def enable(self):
        """Re-enable thread checking."""
        self._enabled = True


# Module-level singleton
guard = GuiThreadGuard()


def selftest() -> int:
    """Run thread guard selftest. Returns 0 on pass, 1 on fail."""
    failures = []

    # 1. Register main thread
    guard.register_main_thread()
    print("[OK] Main thread registered: {}".format(guard._main_thread_id))

    # 2. Assert main thread passes on main thread
    try:
        guard.assert_main_thread("selftest_main")
        print("[OK] assert_main_thread passes on main thread")
    except ThreadingViolation:
        failures.append("assert_main_thread raised on main thread")

    # 3. Assert main thread fails on worker thread
    violation_caught = threading.Event()
    def worker():
        try:
            guard.assert_main_thread("selftest_worker")
        except ThreadingViolation:
            violation_caught.set()

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)

    if violation_caught.is_set():
        print("[OK] ThreadingViolation caught on worker thread")
    else:
        failures.append("ThreadingViolation NOT raised on worker thread")

    # 4. Check decorator
    @guard.check
    def dummy_ui_op():
        return "ok"

    try:
        result = dummy_ui_op()
        if result == "ok":
            print("[OK] @guard.check passes on main thread")
        else:
            failures.append("@guard.check returned wrong value")
    except ThreadingViolation:
        failures.append("@guard.check raised on main thread")

    # 5. Violations recorded
    if len(guard.violations) >= 1:
        print("[OK] {} violation(s) recorded".format(len(guard.violations)))
    else:
        failures.append("No violations recorded")

    guard.reset()

    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All thread guard checks passed")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(selftest())
