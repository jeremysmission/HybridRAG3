# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the gui boot part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Hybrid3 GUI Testing -- Headless Boot (src/gui/testing/gui_boot.py)
# ============================================================================
# Boots the full GUI in headless mode for automated testing.
# The app is created, updated once (so all widgets exist), but never
# enters mainloop. This lets test code introspect and invoke widgets.
# ============================================================================
from __future__ import annotations
import os
import sys
import logging

_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def boot_headless():
    """Create the full HybridRAGApp without entering mainloop.

    Returns the app instance with all widgets built and one update()
    cycle completed, ready for introspection.
    """
    os.environ["HYBRIDRAG_HEADLESS"] = "1"

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Boot system (config + creds + gate)
    boot_result = None
    config = None
    try:
        from src.core.boot import boot_hybridrag
        boot_result = boot_hybridrag()
    except Exception:
        pass

    try:
        from src.core.config import load_config
        config = load_config(_project_root)
    except Exception:
        from src.core.config import Config
        config = Config()

    from src.gui.app import HybridRAGApp
    app = HybridRAGApp(boot_result=boot_result, config=config)
    app.update()
    return app


def attach_backends_sync(app, timeout_s=60):
    """Attach GUI backends synchronously for deterministic tests.

    Tooling-only helper. Calls the same backend loader as launch_gui.py
    but runs in-process so tests can immediately invoke buttons.
    Suppresses init-error messageboxes during loading.
    """
    import time
    from tkinter import messagebox as mb_mod
    from src.gui import launch_gui
    from src.gui.helpers.safe_after import drain_ui_queue

    _logger = logging.getLogger("gui_boot_sync")

    # Suppress the init-error messagebox during headless testing
    _orig_warn = mb_mod.showwarning
    mb_mod.showwarning = lambda *a, **kw: None

    try:
        launch_gui._load_backends(app, _logger)

        # Pump the event loop + drain queued callbacks
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                app.update_idletasks()
                app.update()
                drain_ui_queue()
            except Exception:
                break

            # Done once backends are attached
            if app.query_engine is not None or app.indexer is not None:
                break
            time.sleep(0.1)

        # One final pump for any remaining callbacks
        try:
            app.update_idletasks()
            app.update()
            drain_ui_queue()
        except Exception:
            pass

    finally:
        mb_mod.showwarning = _orig_warn
