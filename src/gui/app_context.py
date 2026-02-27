# Singleton access point for the GUI Controller instance
from __future__ import annotations
from src.gui.core.paths import AppPaths
from src.gui.core.controller import Controller

_controller = None


def get_controller() -> Controller:
    """Return the module-level Controller singleton, creating it on first call."""
    global _controller
    if _controller is None:
        _controller = Controller(AppPaths.default())
    return _controller
