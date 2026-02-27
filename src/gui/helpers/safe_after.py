# ============================================================================
# safe_after -- schedule tkinter callbacks that survive widget destruction.
#
# Background threads that call widget.after() can race with app shutdown.
# If destroy() has already been called, after() raises RuntimeError or
# TclError.  This helper swallows those silently so daemon threads exit
# cleanly without printing tracebacks to the console.
# ============================================================================

import logging

logger = logging.getLogger(__name__)


def safe_after(widget, ms, fn, *args):
    """Schedule fn on the tkinter main thread, ignoring destroyed widgets.

    Returns the after-ID on success, or None if the widget is already gone.
    """
    try:
        return widget.after(ms, fn, *args)
    except (RuntimeError, Exception):
        # RuntimeError: "main thread is not in main loop"
        # TclError: "application has been destroyed"
        return None
