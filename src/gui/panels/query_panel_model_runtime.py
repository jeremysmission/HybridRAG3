# QueryPanel runtime binder coordinator for model/use-case concerns.
from __future__ import annotations

from src.gui.panels.query_panel_model_selection_runtime import (
    bind_query_panel_model_selection_runtime_methods,
)
from src.gui.panels.query_panel_use_case_runtime import (
    bind_query_panel_use_case_runtime_methods,
)


def bind_query_panel_model_runtime_methods(cls):
    """Bind all model/use-case runtime methods."""
    bind_query_panel_model_selection_runtime_methods(cls)
    bind_query_panel_use_case_runtime_methods(cls)
