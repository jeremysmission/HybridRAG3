# ============================================================================
# safe_after -- schedule tkinter callbacks that survive widget destruction.
#
# Background threads that call widget.after() can race with app shutdown
# or headless mode (no mainloop).  Instead of silently dropping callbacks,
# this module enqueues them into a thread-safe queue that the main thread
# drains during update() pumping.
#
# Usage:
#   from src.gui.helpers.safe_after import safe_after, drain_ui_queue
#
#   # Background thread:
#   safe_after(widget, 0, callback, arg1, arg2)
#
#   # Main-thread pump loop (harness or app):
#   root.update_idletasks()
#   root.update()
#   drain_ui_queue()
# ============================================================================

import logging
import os
import queue as _queue_mod

logger = logging.getLogger(__name__)

# Thread-safe queue for callbacks scheduled from background threads.
# Drained by drain_ui_queue() on the main thread during pump loops.
_ui_queue = _queue_mod.Queue()


def _enqueue(fn, args):
    """Enqueue a callback for main-thread drain."""
    if args:
        _ui_queue.put(lambda: fn(*args))
    else:
        _ui_queue.put(fn)


def safe_after(widget, ms, fn, *args):
    """Schedule fn on the tkinter main thread.

    Normal GUI mode: uses widget.after() (processed by mainloop).
    Headless mode (HYBRIDRAG_HEADLESS=1): always enqueues to a
    thread-safe queue, drained by drain_ui_queue() during pump loops.
    This avoids the unreliable after() path where bg-thread calls
    may "succeed" but callbacks never fire without mainloop.

    Returns the after-ID on success, or None if enqueued/dropped.
    """
    # In headless mode, always queue -- after() is unreliable
    if os.environ.get("HYBRIDRAG_HEADLESS") == "1":
        _enqueue(fn, args)
        return None

    try:
        return widget.after(ms, fn, *args)
    except RuntimeError:
        # "main thread is not in main loop" -- enqueue for drain
        _enqueue(fn, args)
        return None
    except Exception:
        # TclError: "application has been destroyed" -- truly gone,
        # no point queueing since there's no UI to update.
        return None


def drain_ui_queue():
    """Drain pending UI callbacks on the main thread.

    Call this after root.update() in any pump loop (harness, boot,
    or manual event processing). Safe to call when the queue is empty.
    """
    while True:
        try:
            fn = _ui_queue.get_nowait()
        except _queue_mod.Empty:
            break
        try:
            fn()
        except Exception as exc:
            logger.debug("drain_ui_queue callback failed: %s", exc)
