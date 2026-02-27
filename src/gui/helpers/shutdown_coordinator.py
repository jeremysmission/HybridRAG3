# ============================================================================
# AppShutdownCoordinator -- centralized thread stop + timer cancel for clean
# GUI shutdown.
#
# Problem: daemon threads call widget.after() after destroy(), printing
# RuntimeError/TclError to the console during demos.
#
# Solution: before destroy(), signal all registered threads to stop and
# join them briefly (bounded, never freezes).  Cancel all registered
# tkinter timer IDs so no callbacks fire on dead widgets.
# ============================================================================

import threading
import logging

logger = logging.getLogger(__name__)


class AppShutdownCoordinator:
    """Tiny coordinator that tracks background threads and timers for cleanup."""

    def __init__(self):
        self._threads = []      # [(name, thread, stop_event_or_None)]
        self._shutting_down = threading.Event()

    @property
    def is_shutting_down(self):
        return self._shutting_down.is_set()

    def register_thread(self, name, thread, stop_event=None):
        """Register a background thread for shutdown tracking."""
        self._threads.append((name, thread, stop_event))

    def request_shutdown(self, widget=None, timer_ids=None):
        """Signal all threads to stop, cancel timers, join briefly.

        Parameters
        ----------
        widget : tk widget or None
            Used to call after_cancel on timer IDs.
        timer_ids : list of (timer_id_or_None) or None
            tkinter after-IDs to cancel before destroy.
        """
        self._shutting_down.set()

        # Cancel tkinter timers
        for tid in (timer_ids or []):
            if tid is not None:
                try:
                    widget.after_cancel(tid)
                except Exception:
                    pass

        # Signal stop events
        for name, thread, stop_event in self._threads:
            if stop_event is not None:
                stop_event.set()

        # Join threads with bounded timeout (never freeze)
        remaining = 2.0  # total budget
        for name, thread, _ in self._threads:
            if thread is not None and thread.is_alive():
                thread.join(timeout=min(0.3, remaining))
                remaining -= 0.3
                if remaining <= 0:
                    break
                if thread.is_alive():
                    logger.debug("Shutdown: thread '%s' still alive, skipping", name)
