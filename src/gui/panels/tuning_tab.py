# ============================================================================
# HybridRAG v3 -- Tuning Tab (src/gui/panels/tuning_tab.py)           RevA
# ============================================================================
# WHAT: Retrieval and LLM parameter sliders, hardware profile switcher,
#       and ranked model table -- the performance tuning cockpit.
# WHY:  Admins need to adjust search sensitivity (top_k, min_score),
#       LLM behavior (temperature, timeout), and switch between hardware
#       profiles (laptop vs workstation) without editing config files.
#       Live sliders make it easy to experiment and see results instantly.
# HOW:  Each slider writes directly to the live config object on change,
#       so the next query immediately uses the new value.  Profile
#       switching runs _profile_switch.py as a subprocess, then reloads
#       config and resets backends -- the user sees a brief "Switching..."
#       status, then the new profile takes effect.
# USAGE: Embedded inside SettingsView notebook as the "Tuning" tab.
#
# Sections:
#   1. Retrieval Settings (top_k, min_score, hybrid_search, reranker)
#   2. LLM Settings (max_tokens, temperature, timeout)
#   3. Profile & Model Ranking (dropdown, apply, model table)
#   4. Reset to Defaults
#
# INTERNET ACCESS: NONE (profile switch runs a local subprocess)
# ============================================================================

import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import os
import threading
import logging

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.settings_view import (
    _load_profile_names, _detect_profile_name, _build_ranking_text, _theme_widget,
)

logger = logging.getLogger(__name__)


class TuningTab(tk.Frame):
    """
    Retrieval/LLM tuning sliders, profile/model ranking, and reset.

    Embeddable Frame -- placed inside the Settings notebook Tuning tab.
    """

    def __init__(self, parent, config, app_ref):
        """Create the tuning tab with all slider sections.

        Args:
            parent: Parent tk widget (the SettingsView notebook).
            config: Live config object -- sliders read from and write to this.
            app_ref: Reference to HybridRAGApp for backend reset after profile switch.
        """
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref

        # Snapshot current values so Reset can restore them
        self._original_values = self._capture_values()

        # Build sections
        self._build_retrieval_section(t)
        self._build_llm_section(t)
        self._build_profile_section(t)
        self._build_reset_button(t)

    def _capture_values(self):
        """Capture current config values for reset."""
        retrieval = getattr(self.config, "retrieval", None)
        api = getattr(self.config, "api", None)
        return {
            "top_k": getattr(retrieval, "top_k", 8) if retrieval else 8,
            "min_score": getattr(retrieval, "min_score", 0.20) if retrieval else 0.20,
            "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
            "reranker_enabled": getattr(retrieval, "reranker_enabled", False) if retrieval else False,
            "max_tokens": getattr(api, "max_tokens", 2048) if api else 2048,
            "temperature": getattr(api, "temperature", 0.1) if api else 0.1,
            "timeout_seconds": getattr(api, "timeout_seconds", 30) if api else 30,
        }

    def get_profile_options(self):
        """Return the list of available profile names (public testing API)."""
        return list(self.profile_dropdown["values"])

    # ----------------------------------------------------------------
    # RETRIEVAL SETTINGS
    # ----------------------------------------------------------------

    def _build_retrieval_section(self, t):
        """Build retrieval settings section."""
        frame = tk.LabelFrame(self, text="Retrieval Settings", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"],
                               font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=(8, 4))
        self._retrieval_frame = frame

        retrieval = getattr(self.config, "retrieval", None)

        # top_k slider
        row_tk = tk.Frame(frame, bg=t["panel_bg"])
        row_tk.pack(fill=tk.X, pady=4)
        self._topk_label = tk.Label(
            row_tk, text="top_k:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._topk_label.pack(side=tk.LEFT)
        self.topk_var = tk.IntVar(
            value=getattr(retrieval, "top_k", 8) if retrieval else 8
        )
        self.topk_scale = tk.Scale(
            row_tk, from_=1, to=50, orient=tk.HORIZONTAL,
            variable=self.topk_var, command=lambda v: self._on_retrieval_change(),
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        self.topk_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # min_score slider
        row_ms = tk.Frame(frame, bg=t["panel_bg"])
        row_ms.pack(fill=tk.X, pady=4)
        self._minscore_label = tk.Label(
            row_ms, text="min_score:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._minscore_label.pack(side=tk.LEFT)
        self.minscore_var = tk.DoubleVar(
            value=getattr(retrieval, "min_score", 0.20) if retrieval else 0.20
        )
        self.minscore_scale = tk.Scale(
            row_ms, from_=0.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
            variable=self.minscore_var, command=lambda v: self._on_retrieval_change(),
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        self.minscore_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Hybrid search toggle
        row_hs = tk.Frame(frame, bg=t["panel_bg"])
        row_hs.pack(fill=tk.X, pady=4)
        self._hybrid_label = tk.Label(
            row_hs, text="Hybrid search:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._hybrid_label.pack(side=tk.LEFT)
        self.hybrid_var = tk.BooleanVar(
            value=getattr(retrieval, "hybrid_search", True) if retrieval else True
        )
        self._hybrid_cb = tk.Checkbutton(
            row_hs, variable=self.hybrid_var,
            command=self._on_retrieval_change,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT,
        )
        self._hybrid_cb.pack(side=tk.LEFT)

        # Reranker toggle
        row_rr = tk.Frame(frame, bg=t["panel_bg"])
        row_rr.pack(fill=tk.X, pady=4)
        self._reranker_label = tk.Label(
            row_rr, text="Reranker:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._reranker_label.pack(side=tk.LEFT)
        self.reranker_var = tk.BooleanVar(
            value=getattr(retrieval, "reranker_enabled", False) if retrieval else False
        )
        self._reranker_cb = tk.Checkbutton(
            row_rr, variable=self.reranker_var,
            command=self._on_retrieval_change,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT,
        )
        self._reranker_cb.pack(side=tk.LEFT)

    def _on_retrieval_change(self):
        """Write retrieval settings to config immediately."""
        retrieval = getattr(self.config, "retrieval", None)
        if retrieval:
            retrieval.top_k = self.topk_var.get()
            retrieval.min_score = self.minscore_var.get()
            retrieval.hybrid_search = self.hybrid_var.get()
            retrieval.reranker_enabled = self.reranker_var.get()

    # ----------------------------------------------------------------
    # LLM SETTINGS
    # ----------------------------------------------------------------

    def _build_llm_section(self, t):
        """Build LLM settings section."""
        frame = tk.LabelFrame(self, text="LLM Settings", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"],
                               font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._llm_frame = frame

        api = getattr(self.config, "api", None)

        # Max tokens slider
        row_mt = tk.Frame(frame, bg=t["panel_bg"])
        row_mt.pack(fill=tk.X, pady=4)
        self._maxtokens_label = tk.Label(
            row_mt, text="Max tokens:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._maxtokens_label.pack(side=tk.LEFT)
        self.maxtokens_var = tk.IntVar(
            value=getattr(api, "max_tokens", 2048) if api else 2048
        )
        self.maxtokens_scale = tk.Scale(
            row_mt, from_=256, to=4096, orient=tk.HORIZONTAL,
            variable=self.maxtokens_var, command=lambda v: self._on_llm_change(),
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        self.maxtokens_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Temperature slider
        row_temp = tk.Frame(frame, bg=t["panel_bg"])
        row_temp.pack(fill=tk.X, pady=4)
        self._temp_label = tk.Label(
            row_temp, text="Temperature:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._temp_label.pack(side=tk.LEFT)
        self.temp_var = tk.DoubleVar(
            value=getattr(api, "temperature", 0.1) if api else 0.1
        )
        self.temp_scale = tk.Scale(
            row_temp, from_=0.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
            variable=self.temp_var, command=lambda v: self._on_llm_change(),
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        self.temp_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Timeout slider
        row_to = tk.Frame(frame, bg=t["panel_bg"])
        row_to.pack(fill=tk.X, pady=4)
        self._timeout_label = tk.Label(
            row_to, text="Timeout (s):", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._timeout_label.pack(side=tk.LEFT)
        self.timeout_var = tk.IntVar(
            value=getattr(api, "timeout_seconds", 30) if api else 30
        )
        self.timeout_scale = tk.Scale(
            row_to, from_=10, to=120, orient=tk.HORIZONTAL,
            variable=self.timeout_var, command=lambda v: self._on_llm_change(),
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        self.timeout_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _on_llm_change(self):
        """Write LLM settings to config immediately."""
        api = getattr(self.config, "api", None)
        if api:
            api.max_tokens = self.maxtokens_var.get()
            api.temperature = self.temp_var.get()
            api.timeout_seconds = self.timeout_var.get()

    # ----------------------------------------------------------------
    # PERFORMANCE PROFILE
    # ----------------------------------------------------------------

    def _build_profile_section(self, t):
        """Build performance profile section with ranked model table."""
        frame = tk.LabelFrame(self, text="Profile & Model Ranking", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"],
                               font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._profile_frame = frame

        # Profile selector row
        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X, pady=4)

        self._profile_label = tk.Label(
            row, text="Profile:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT)
        self._profile_label.pack(side=tk.LEFT)

        profile_names = _load_profile_names()
        self.profile_var = tk.StringVar(value="desktop_power")
        self.profile_dropdown = ttk.Combobox(
            row, textvariable=self.profile_var, values=profile_names,
            state="readonly", width=20, font=FONT,
        )
        self.profile_dropdown.pack(side=tk.LEFT, padx=(8, 0))

        self.profile_apply_btn = tk.Button(
            row, text="Apply", command=self._on_profile_change, width=8,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=6, pady=2,
            activebackground=t["accent_hover"],
            activeforeground=t["accent_fg"],
        )
        self.profile_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Profile info line
        self.profile_info_label = tk.Label(
            frame, text="", anchor=tk.W, fg=t["fg"],
            bg=t["panel_bg"], font=FONT_SMALL,
        )
        self.profile_info_label.pack(fill=tk.X, pady=(2, 0))

        self.profile_status_label = tk.Label(
            frame, text="", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT,
        )
        self.profile_status_label.pack(fill=tk.X, pady=2)

        # Ranked model table (read-only text widget)
        self.model_table = tk.Text(
            frame, height=12, wrap=tk.NONE, state=tk.DISABLED,
            font=("Consolas", 9), bg=t["input_bg"], fg=t["input_fg"],
            relief=tk.FLAT, bd=2,
        )
        self.model_table.pack(fill=tk.X, pady=(4, 2))

        # Load current profile and show ranking
        self._detect_current_profile()
        self._refresh_profile_info()
        self._refresh_model_table()

    def _detect_current_profile(self):
        """Infer current profile from config by matching embedding model."""
        self.profile_var.set(_detect_profile_name(self.config))

    def _refresh_profile_info(self):
        """Show embedder + LLM info for the currently detected profile."""
        embed = getattr(self.config, "embedding", None)
        ollama = getattr(self.config, "ollama", None)
        model_name = getattr(embed, "model_name", "?") if embed else "?"
        dim = getattr(embed, "dimension", "?") if embed else "?"
        device = getattr(embed, "device", "?") if embed else "?"
        llm = getattr(ollama, "model", "?") if ollama else "?"
        self.profile_info_label.config(
            text="Embedder: {} ({}d, {})  |  LLM: {}".format(
                model_name, dim, device, llm
            ),
        )

    def _refresh_model_table(self):
        """Populate the ranked model table for the current profile."""
        text = _build_ranking_text(self.profile_var.get())
        self.model_table.config(state=tk.NORMAL)
        self.model_table.delete("1.0", tk.END)
        self.model_table.insert("1.0", text)
        self.model_table.config(state=tk.DISABLED)

    def _on_profile_change(self, event=None):
        """Apply profile switch in a background thread."""
        t = current_theme()
        profile = self.profile_var.get()

        self.profile_apply_btn.config(state=tk.DISABLED)
        self.profile_status_label.config(
            text="Switching to {}...".format(profile), fg=t["gray"],
        )

        threading.Thread(
            target=self._do_profile_switch,
            args=(profile,),
            daemon=True,
        ).start()

    def _do_profile_switch(self, profile):
        """Background thread: run subprocess, reload config, reset backends."""
        from src.gui.helpers.safe_after import safe_after
        root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")

        old_embed_model = getattr(
            getattr(self.config, "embedding", None), "model_name", ""
        )

        try:
            proc = subprocess.run(
                [sys.executable,
                 os.path.join(root, "scripts", "_profile_switch.py"),
                 profile],
                capture_output=True, text=True, timeout=10,
                cwd=root,
            )
            if proc.returncode != 0:
                safe_after(self, 0, self._profile_switch_failed,
                           proc.stderr.strip()[:80])
                return
        except Exception as e:
            safe_after(self, 0, self._profile_switch_failed, str(e)[:80])
            return

        try:
            from src.core.config import load_config
            new_config = load_config(root)
        except Exception as e:
            safe_after(self, 0, self._profile_switch_failed,
                       "Config reload: {}".format(str(e)[:60]))
            return

        new_config.mode = self.config.mode

        # Reconfigure network gate to match preserved mode (prevents desync)
        try:
            from src.core.network_gate import configure_gate
            configure_gate(mode=new_config.mode)
        except Exception:
            pass

        new_embed_model = getattr(
            getattr(new_config, "embedding", None), "model_name", ""
        )
        embedding_changed = (
            old_embed_model
            and new_embed_model
            and old_embed_model != new_embed_model
        )

        if embedding_changed:
            try:
                from src.gui.launch_gui import clear_embedder_cache
                clear_embedder_cache()
                logger.info("Embedder cache cleared (model changed)")
            except Exception as e:
                logger.warning("Could not clear embedder cache: %s", e)

        safe_after(self, 0, self._profile_switch_done,
                   new_config, profile, embedding_changed,
                   old_embed_model, new_embed_model)

    def _profile_switch_done(self, new_config, profile, embedding_changed,
                             old_embed_model, new_embed_model):
        """Main-thread callback after background profile switch succeeds."""
        t = current_theme()

        if embedding_changed:
            from tkinter import messagebox
            messagebox.showwarning(
                "Re-Index Required",
                "Embedding model changed:\n\n"
                "  Old: {}\n"
                "  New: {}\n\n"
                "Existing vectors are INCOMPATIBLE with the\n"
                "new model. You MUST re-index all documents\n"
                "before querying.\n\n"
                "Use the Index panel to start a new index.".format(
                    old_embed_model, new_embed_model,
                ),
            )

        self.config = new_config
        try:
            if hasattr(self._app, "reload_config"):
                self._app.reload_config(new_config)

            if hasattr(self._app, "reset_backends"):
                self._app.reset_backends()
        except Exception as e:
            logger.warning("Profile apply failed during backend reset: %s", e)
            safe_after(self, 0, self._profile_switch_failed,
                       "Backend reset: {}".format(str(e)[:60]))
            return

        self._refresh_profile_info()
        self._refresh_model_table()
        self._sync_sliders_to_config()

        status_parts = ["[OK] Switched to {}".format(profile)]
        if embedding_changed:
            status_parts.append("-- RE-INDEX REQUIRED")
        self.profile_status_label.config(
            text=" ".join(status_parts), fg=t["green"],
        )
        self.profile_apply_btn.config(state=tk.NORMAL)

    def _profile_switch_failed(self, error_msg):
        """Main-thread callback when profile switch fails."""
        t = current_theme()
        self.profile_status_label.config(
            text="[FAIL] {}".format(error_msg), fg=t["red"],
        )
        self.profile_apply_btn.config(state=tk.NORMAL)

    def _sync_sliders_to_config(self):
        """Sync slider values to match the newly loaded config."""
        retrieval = getattr(self.config, "retrieval", None)
        api = getattr(self.config, "api", None)
        if retrieval:
            self.topk_var.set(getattr(retrieval, "top_k", 8))
            self.minscore_var.set(getattr(retrieval, "min_score", 0.20))
            self.hybrid_var.set(getattr(retrieval, "hybrid_search", True))
            self.reranker_var.set(getattr(retrieval, "reranker_enabled", False))
        if api:
            self.maxtokens_var.set(getattr(api, "max_tokens", 2048))
            self.temp_var.set(getattr(api, "temperature", 0.1))
            self.timeout_var.set(getattr(api, "timeout_seconds", 30))

    # ----------------------------------------------------------------
    # RESET TO DEFAULTS
    # ----------------------------------------------------------------

    def _build_reset_button(self, t):
        """Build Reset to Defaults button."""
        btn_frame = tk.Frame(self, bg=t["panel_bg"])
        btn_frame.pack(fill=tk.X, padx=16, pady=16)
        self._reset_frame = btn_frame

        self._reset_btn = tk.Button(
            btn_frame, text="Reset to Defaults", command=self._on_reset,
            width=16, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
        )
        self._reset_btn.pack(side=tk.LEFT)
        bind_hover(self._reset_btn)

    def _on_reset(self):
        """Reset all sliders to original values."""
        orig = self._original_values
        self.topk_var.set(orig["top_k"])
        self.minscore_var.set(orig["min_score"])
        self.hybrid_var.set(orig["hybrid_search"])
        self.reranker_var.set(orig["reranker_enabled"])
        self.maxtokens_var.set(orig["max_tokens"])
        self.temp_var.set(orig["temperature"])
        self.timeout_var.set(orig["timeout_seconds"])

        self._on_retrieval_change()
        self._on_llm_change()

    # ----------------------------------------------------------------
    # THEME
    # ----------------------------------------------------------------

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["panel_bg"])

        for frame_attr in ("_retrieval_frame", "_llm_frame", "_profile_frame"):
            frame = getattr(self, frame_attr, None)
            if frame:
                frame.configure(bg=t["panel_bg"], fg=t["accent"])
                for child in frame.winfo_children():
                    _theme_widget(child, t)

        if hasattr(self, "_reset_frame"):
            self._reset_frame.configure(bg=t["panel_bg"])
            self._reset_btn.configure(
                bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
