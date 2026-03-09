# ============================================================================
# HybridRAG v3 -- Tuning Tab (src/gui/panels/tuning_tab.py)           RevC
# ============================================================================
# WHAT: Thin wrapper around the extracted tuning runtime/editor methods.
# WHY:  Keep the public `TuningTab` surface stable while keeping the class
#       body small enough for review and maintenance.
# HOW:  `tuning_tab_runtime.py` owns the UI behavior; this file only creates
#       the frame, bootstraps shared state, and binds the extracted methods.
# ============================================================================

import subprocess
import tkinter as tk

from src.gui.helpers.mode_tuning import ModeTuningStore
from src.gui.theme import current_theme
from src.gui.panels.tuning_tab_runtime import (
    SAFE_DEFAULTS,
    _detect_hardware_class,
    bind_tuning_tab_runtime_methods,
)


class TuningTab(tk.Frame):
    """Retrieval/LLM tuning with per-setting defaults and live admin controls."""

    def __init__(self, parent, config, app_ref, enable_mode_store=True):
        theme = current_theme()
        super().__init__(parent, bg=theme["panel_bg"])
        self.config = config
        self._app = app_ref
        self._mode_store_enabled = bool(enable_mode_store)

        self._hw_class, self._vram_gb, self._ram_gb = _detect_hardware_class()
        self._safe = SAFE_DEFAULTS.get(self._hw_class, SAFE_DEFAULTS["desktop_power"])
        self._mode_store = ModeTuningStore()
        self._syncing = False

        self._default_vars = {}
        self._scales = {}
        self._check_widgets = {}

        self._last_popup_key = None
        self._mode_banner_var = tk.StringVar(value="")
        self._mode_status_var = tk.StringVar(value="")
        self._editor_mode_var = tk.StringVar(
            value="online" if str(getattr(config, "mode", "offline")).lower() == "online" else "offline"
        )

        self._build_mode_banner(theme)
        self._build_editor_columns(theme)
        self._build_profile_section(theme)
        self._build_reset_button(theme)
        self._legacy_defaults = self._display_values_from_config()
        self._sync_sliders_to_config()


bind_tuning_tab_runtime_methods(TuningTab)
