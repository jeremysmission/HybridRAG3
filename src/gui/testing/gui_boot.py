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
