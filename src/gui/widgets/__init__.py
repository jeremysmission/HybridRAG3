# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the init part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
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
