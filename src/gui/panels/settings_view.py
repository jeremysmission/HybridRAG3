# ============================================================================
# HybridRAG v3 -- Settings View (src/gui/panels/settings_view.py)    RevA
# ============================================================================
# WHAT: Two-tab settings coordinator (Tuning + API & Admin).
# WHY:  Admins need a single place to adjust retrieval parameters, switch
#       hardware profiles, manage API credentials, and set defaults.
#       This view combines those into one notebook so everything is
#       reachable from a single NavBar click.
# HOW:  A thin coordinator class that creates two tab objects (TuningTab
#       and ApiAdminTab) inside a ttk.Notebook.  Public attributes like
#       topk_var, temp_var are proxied via @property so existing test
#       code and other panels can access them without knowing about the
#       two-tab split.
# USAGE: Navigate via NavBar > Settings, or Admin > Admin Settings.
#
# Module-level helpers (_load_profile_names, _detect_profile_name,
# _build_ranking_text, _theme_widget) are kept here because TuningTab
# imports them from this module.
#
# INTERNET ACCESS: Depends on tab.
#   Tuning: NONE
#   API & Admin: one GET to /models (optional, user-initiated)
# ============================================================================

import tkinter as tk
from tkinter import ttk
import os
import logging

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover

logger = logging.getLogger(__name__)


# ====================================================================
# Module-level helpers (imported by tuning_tab.py -- do not remove)
# ====================================================================

def _load_profile_names():
    """Read profile names from profiles.yaml.

    Returns a list like ['laptop_safe', 'desktop_power', 'server_max'].
    Falls back to hardcoded defaults if the file is missing or unreadable.
    """
    try:
        import yaml
        root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
        path = os.path.join(root, "config", "profiles.yaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return list(data.keys())
    except Exception:
        pass
    return ["laptop_safe", "desktop_power", "server_max"]


def _detect_profile_name(config):
    """Return the best-matching profile name for the given config.

    Compares the current embedding model + device + LLM model against
    each profile in profiles.yaml.  This lets us show the user which
    profile they are actually running, even if they never explicitly
    selected one.
    """
    try:
        import yaml
        root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
        path = os.path.join(root, "config", "profiles.yaml")
        with open(path, "r", encoding="utf-8") as f:
            profiles_data = yaml.safe_load(f) or {}

        current_model = getattr(
            getattr(config, "embedding", None), "model_name", ""
        )
        current_device = getattr(
            getattr(config, "embedding", None), "device", "cpu"
        )

        for name, pdata in profiles_data.items():
            p_model = pdata.get("embedding", {}).get("model_name", "")
            p_device = pdata.get("embedding", {}).get("device", "cpu")
            if p_model == current_model and p_device == current_device:
                return name

        current_llm = getattr(
            getattr(config, "ollama", None), "model", ""
        )
        for name, pdata in profiles_data.items():
            p_llm = pdata.get("ollama", {}).get("model", "")
            p_device = pdata.get("embedding", {}).get("device", "cpu")
            if p_llm == current_llm and p_device == current_device:
                return name
    except Exception:
        pass
    return "laptop_safe"


def _build_ranking_text(profile):
    """Build the ranked model table text for a given profile.

    Returns a formatted text table showing the #1 and #2 models
    for each use case, ready to insert into a tk.Text widget.
    """
    try:
        from scripts._model_meta import (
            get_profile_ranking_table, USE_CASES,
        )

        table = get_profile_ranking_table(profile)
        lines = []
        lines.append(
            "  {:<22s} {:<22s} {}".format(
                "Use Case", "#1 (default)", "#2 (fallback)")
        )
        lines.append(
            "  {:<22s} {:<22s} {}".format("-" * 22, "-" * 22, "-" * 22)
        )

        display_order = [
            "sw", "eng", "sys", "draft", "log", "pm", "fe", "cyber", "gen",
        ]
        for uc_key in display_order:
            if uc_key not in table:
                continue
            ranked = table[uc_key]
            label = USE_CASES[uc_key]["label"]
            col1 = ranked[0]["model"] if len(ranked) > 0 else "---"
            col2 = ranked[1]["model"] if len(ranked) > 1 else "---"
            lines.append(
                "  {:<22s} {:<22s} {}".format(label, col1, col2)
            )

        return "\n".join(lines)
    except Exception as e:
        return "  [WARN] Could not load rankings: {}".format(e)


def _theme_widget(widget, t):
    """Recursively apply theme to a widget and its children."""
    try:
        wclass = widget.winfo_class()
        if wclass == "Frame":
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Scale":
            widget.configure(
                bg=t["panel_bg"], fg=t["fg"],
                troughcolor=t["input_bg"])
        elif wclass == "Checkbutton":
            widget.configure(
                bg=t["panel_bg"], fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"])
        elif wclass == "Text":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


class SettingsView(tk.Frame):
    """
    Admin settings coordinator with a two-tab Notebook:
      - Tuning:     retrieval/LLM sliders, profile/model ranking, reset
      - API & Admin: credentials, online model selection, admin defaults

    Preserves all public attributes from the original monolithic class
    (topk_var, temp_var, etc.) via delegation to the TuningTab.
    """

    def __init__(self, parent, config, app_ref):
        t = current_theme()
        super().__init__(parent, bg=t["bg"])
        self.config = config
        self._app = app_ref

        # Build notebook with two tabs
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Tuning (existing functionality)
        from src.gui.panels.tuning_tab import TuningTab
        self._tuning_tab = TuningTab(self._notebook, config=config, app_ref=app_ref)
        self._notebook.add(self._tuning_tab, text="  Tuning  ")

        # Tab 2: API & Admin (new functionality)
        from src.gui.panels.api_admin_tab import ApiAdminTab
        self._api_admin_tab = ApiAdminTab(self._notebook, config=config, app_ref=app_ref)
        self._notebook.add(self._api_admin_tab, text="  API & Admin  ")

    # ----------------------------------------------------------------
    # PUBLIC ATTRIBUTE PROXIES (backward compatibility)
    # ----------------------------------------------------------------
    # Tests and external code access topk_var, temp_var, etc. directly.
    # These properties delegate to the TuningTab so nothing breaks.

    @property
    def topk_var(self):
        return self._tuning_tab.topk_var

    @property
    def minscore_var(self):
        return self._tuning_tab.minscore_var

    @property
    def hybrid_var(self):
        return self._tuning_tab.hybrid_var

    @property
    def reranker_var(self):
        return self._tuning_tab.reranker_var

    @property
    def maxtokens_var(self):
        return self._tuning_tab.maxtokens_var

    @property
    def temp_var(self):
        return self._tuning_tab.temp_var

    @property
    def timeout_var(self):
        return self._tuning_tab.timeout_var

    @property
    def profile_var(self):
        return self._tuning_tab.profile_var

    @property
    def profile_dropdown(self):
        return self._tuning_tab.profile_dropdown

    @property
    def profile_apply_btn(self):
        return self._tuning_tab.profile_apply_btn

    @property
    def profile_info_label(self):
        return self._tuning_tab.profile_info_label

    @property
    def profile_status_label(self):
        return self._tuning_tab.profile_status_label

    @property
    def model_table(self):
        return self._tuning_tab.model_table

    # ----------------------------------------------------------------
    # DELEGATED METHODS (backward compatibility)
    # ----------------------------------------------------------------

    def _on_retrieval_change(self):
        self._tuning_tab._on_retrieval_change()

    def _on_llm_change(self):
        self._tuning_tab._on_llm_change()

    def _on_profile_change(self, event=None):
        self._tuning_tab._on_profile_change(event)

    def _on_reset(self):
        """Delegate the 'Reset to Defaults' action to the TuningTab."""
        self._tuning_tab._on_reset()

    def _sync_sliders_to_config(self):
        self._tuning_tab._sync_sliders_to_config()

    def _capture_values(self):
        return self._tuning_tab._capture_values()

    # ----------------------------------------------------------------
    # CREDENTIAL STATUS REFRESH
    # ----------------------------------------------------------------

    def refresh_credential_status(self):
        """Refresh the API & Admin tab credential display."""
        if hasattr(self, "_api_admin_tab"):
            self._api_admin_tab._refresh_credential_status()

    # ----------------------------------------------------------------
    # THEME
    # ----------------------------------------------------------------

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["bg"])
        self._tuning_tab.apply_theme(t)
        self._api_admin_tab.apply_theme(t)
