# QueryPanel runtime binder coordinator for query execution/render concerns.
from __future__ import annotations

from src.gui.panels.query_panel_query_flow_runtime import (
    bind_query_panel_query_flow_runtime_methods,
)
from src.gui.panels.query_panel_query_render_runtime import (
    bind_query_panel_query_render_runtime_methods,
)


def bind_query_panel_query_runtime_methods(cls):
    """Bind all query runtime methods."""
    bind_query_panel_query_flow_runtime_methods(cls)
    bind_query_panel_query_render_runtime_methods(cls)
