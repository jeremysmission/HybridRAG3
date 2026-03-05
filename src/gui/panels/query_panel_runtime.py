# QueryPanel runtime binder coordinator (modular split).
from __future__ import annotations

from src.gui.panels.query_panel_model_runtime import (
    bind_query_panel_model_runtime_methods,
)
from src.gui.panels.query_panel_query_runtime import (
    bind_query_panel_query_runtime_methods,
)


def bind_query_panel_runtime_methods(cls):
    """Bind all extracted QueryPanel runtime methods."""
    bind_query_panel_model_runtime_methods(cls)
    bind_query_panel_query_runtime_methods(cls)
