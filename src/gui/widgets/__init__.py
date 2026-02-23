# ============================================================================
# HybridRAG v3 -- GUI Widget Package (src/gui/widgets/__init__.py)
# ============================================================================
# WHAT: Reusable custom widgets for the HybridRAG GUI.
# WHY:  Standard tk.Button cannot draw rounded corners.  Custom widgets
#       live here so they can be imported from any panel without circular
#       dependencies.
# ============================================================================
from src.gui.widgets.rounded_button import RoundedButton

__all__ = ["RoundedButton"]
