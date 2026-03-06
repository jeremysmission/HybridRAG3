# ============================================================================
# HybridRAG v3 -- Tuning Tab (src/gui/panels/tuning_tab.py)           RevB
# ============================================================================
# WHAT: Retrieval and LLM parameter sliders with per-setting "Default"
#       checkboxes, hardware-aware latency warnings, and profile switcher.
# WHY:  Admins need live tuning AND a safe demo-day mode. Default checkboxes
#       lock each setting to a hardware-appropriate value; unchecking unlocks
#       custom tuning. Warning popups fire when a change would cause
#       unrealistic wait times on the detected hardware class.
# HOW:  Reads config/system_profile.json (written by system_diagnostic.py)
#       to detect VRAM and RAM. Each slider/toggle has a paired Default
#       checkbox. When Default is checked, the control is disabled and the
#       value is forced to the safe baseline for the hardware class.
# USAGE: Embedded inside SettingsView notebook as the "Tuning" tab.
# INTERNET ACCESS: NONE
# ============================================================================

import json
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
import threading
import logging

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.helpers.safe_after import safe_after
from src.gui.helpers.mode_tuning import ModeTuningStore
from src.gui.panels.settings_view import (
    _load_profile_names, _detect_profile_name, _build_ranking_text, _theme_widget,
)

logger = logging.getLogger(__name__)

# Hardware-safe defaults per profile class.
# These are the "demo-day safe" values that avoid latency surprises.
SAFE_DEFAULTS = {
    'laptop_safe': {
        'top_k': 5, 'min_score': 0.10, 'hybrid_search': True,
        'reranker_enabled': False, 'reranker_top_n': 20,
        'context_window': 4096, 'num_predict': 512,
        'max_tokens': 16384, 'temperature': 0.05, 'timeout_seconds': 180,
    },
    'desktop_power': {
        'top_k': 5, 'min_score': 0.10, 'hybrid_search': True,
        'reranker_enabled': False, 'reranker_top_n': 20,
        'context_window': 4096, 'num_predict': 512,
        'max_tokens': 16384, 'temperature': 0.05, 'timeout_seconds': 180,
    },
    'server_max': {
        'top_k': 10, 'min_score': 0.10, 'hybrid_search': True,
        'reranker_enabled': False, 'reranker_top_n': 30,
        'context_window': 4096, 'num_predict': 512,
        'max_tokens': 16384, 'temperature': 0.05, 'timeout_seconds': 180,
    },
}


def _detect_hardware_class():
    """Read system_profile.json, falling back to live nvidia-smi + psutil probe."""
    root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
    path = os.path.join(root, "config", "system_profile.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        hw = data.get("hardware", {})
        vram = hw.get("gpu_vram_gb", 0.0)
        ram = hw.get("ram_gb", 0.0)
        profile = data.get("profile", {}).get("recommended_profile", "desktop_power")
        if vram > 0 or ram > 0:
            return profile, vram, ram
    except Exception:
        pass

    # Live probe fallback when system_profile.json is missing or empty.
    vram = 0.0
    ram = 0.0
    try:
        import psutil
        ram = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        import subprocess as _sp
        out = _sp.run(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0:
            vram = round(float(out.stdout.strip().splitlines()[0]) / 1024, 1)
    except Exception:
        pass

    if vram >= 24:
        profile = "server_max"
    elif vram >= 8:
        profile = "desktop_power"
    else:
        profile = "laptop_safe"
    return profile, vram, ram


# Approximate model weights and KV cache cost for VRAM overflow detection.
_MODEL_SPECS = {
    "phi4-mini":        {"weight_gb": 2.3, "kv_per_1k_mb": 150, "gpu_tok_s": 45},
    "phi4:14b-q4_K_M":  {"weight_gb": 9.1, "kv_per_1k_mb": 400, "gpu_tok_s": 20},
    "mistral:7b":       {"weight_gb": 4.1, "kv_per_1k_mb": 200, "gpu_tok_s": 35},
    "mistral-nemo:12b": {"weight_gb": 7.1, "kv_per_1k_mb": 350, "gpu_tok_s": 22},
    "gemma3:4b":        {"weight_gb": 3.3, "kv_per_1k_mb": 150, "gpu_tok_s": 40},
}


def _vram_overflows(model_name, ctx_window, vram_gb):
    """True if model + KV cache at ctx_window exceeds available VRAM."""
    if vram_gb <= 0:
        return True
    spec = _MODEL_SPECS.get(model_name, _MODEL_SPECS.get("phi4:14b-q4_K_M"))
    kv_gb = (ctx_window / 1000) * spec["kv_per_1k_mb"] / 1024
    return (spec["weight_gb"] + kv_gb) > vram_gb * 0.95


def _estimate_query_seconds(top_k, ctx_window, num_predict, vram_gb,
                            model_name="phi4:14b-q4_K_M"):
    """Estimate query time in seconds for given settings and hardware."""
    spec = _MODEL_SPECS.get(model_name, _MODEL_SPECS.get("phi4:14b-q4_K_M"))
    chunk_tokens = 300
    prompt_tokens = 520 + top_k * chunk_tokens
    output_tokens = min(num_predict, 200)
    overflow = _vram_overflows(model_name, ctx_window, vram_gb)
    if overflow:
        prompt_rate = max(spec["gpu_tok_s"] // 5, 3)
        gen_rate = max(spec["gpu_tok_s"] // 8, 2)
    else:
        prompt_rate = spec["gpu_tok_s"] * 3  # prompt eval ~3x gen speed
        gen_rate = spec["gpu_tok_s"]
    return prompt_tokens / prompt_rate + output_tokens / gen_rate


def _run_profile_switch(tab, profile):
    """Background thread: run subprocess, reload config, reset backends."""
    root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
    old_embed = getattr(getattr(tab.config, "embedding", None), "model_name", "")

    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "_profile_switch.py"), profile],
            capture_output=True, text=True, timeout=10, cwd=root)
        if proc.returncode != 0:
            safe_after(tab, 0, tab._profile_switch_failed, proc.stderr.strip()[:80])
            return
    except Exception as e:
        safe_after(tab, 0, tab._profile_switch_failed, str(e)[:80])
        return

    try:
        from src.core.config import load_config
        new_config = load_config(root)
    except Exception as e:
        safe_after(tab, 0, tab._profile_switch_failed,
                   "Config reload: {}".format(str(e)[:60]))
        return

    new_config.mode = tab.config.mode
    try:
        from src.core.network_gate import configure_gate
        if new_config.mode == "online":
            configure_gate(
                mode="online",
                api_endpoint=getattr(
                    getattr(new_config, "api", None), "endpoint", "") or "",
                allowed_prefixes=getattr(
                    getattr(new_config, "api", None),
                    "allowed_endpoint_prefixes", []))
        else:
            configure_gate(mode=new_config.mode)
    except Exception:
        pass

    new_embed = getattr(getattr(new_config, "embedding", None), "model_name", "")
    embed_changed = old_embed and new_embed and old_embed != new_embed
    if embed_changed:
        try:
            from src.gui.launch_gui import clear_embedder_cache
            clear_embedder_cache()
        except Exception as e:
            logger.warning("Could not clear embedder cache: %s", e)

    safe_after(tab, 0, tab._profile_switch_done,
               new_config, profile, embed_changed, old_embed, new_embed)


class TuningTab(tk.Frame):
    """Retrieval/LLM tuning with per-setting Default checkboxes and latency warnings."""

    def __init__(self, parent, config, app_ref, enable_mode_store=True):
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref
        self._mode_store_enabled = bool(enable_mode_store)

        self._hw_class, self._vram_gb, self._ram_gb = _detect_hardware_class()
        self._safe = SAFE_DEFAULTS.get(self._hw_class, SAFE_DEFAULTS['desktop_power'])
        self._mode_store = ModeTuningStore()
        self._syncing = False

        # Track default checkbox vars and lockable widgets for all settings
        self._default_vars = {}
        self._scales = {}
        self._check_widgets = {}

        self._last_popup_key = None
        self._mode_banner_var = tk.StringVar(value="")
        self._mode_status_var = tk.StringVar(value="")

        self._build_mode_banner(t)
        self._build_retrieval_section(t)
        self._build_llm_section(t)
        self._build_profile_section(t)
        self._build_reset_button(t)
        self._legacy_defaults = self._display_values_from_config()
        self._sync_sliders_to_config()

    def _capture_values(self):
        if self._mode_store_enabled:
            return self._mode_store.get_active_values(self.config, self._current_mode())
        return self._display_values_from_config()

    def get_profile_options(self):
        return list(self.profile_dropdown["values"])

    def _current_mode(self):
        return "online" if str(getattr(self.config, "mode", "offline")).lower() == "online" else "offline"

    def _build_mode_banner(self, t):
        row = tk.Frame(self, bg=t["panel_bg"])
        row.pack(fill=tk.X, padx=16, pady=(10, 2))
        self._mode_row = row
        self._mode_banner = tk.Label(
            row,
            textvariable=self._mode_banner_var,
            anchor=tk.W,
            bg=t["panel_bg"],
            fg=t["accent"],
            font=FONT_BOLD,
        )
        self._mode_banner.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._mode_status = tk.Label(
            row,
            textvariable=self._mode_status_var,
            anchor=tk.E,
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_SMALL,
        )
        self._mode_status.pack(side=tk.RIGHT)

    def _refresh_mode_banner(self):
        mode = self._current_mode()
        self._mode_banner_var.set(
            "Editing active mode defaults: {}  |  Offline and online keep separate values and locks.".format(
                mode.upper()
            )
        )
        if hasattr(self, "_llm_frame"):
            self._llm_frame.config(text="LLM Settings ({})".format(mode.capitalize()))
        if hasattr(self, "_llm_mode_note"):
            if mode == "online":
                self._llm_mode_note.config(
                    text=(
                        "Online mode uses api.context_window + max_tokens. "
                        "Offline-only controls are disabled."
                    )
                )
            else:
                self._llm_mode_note.config(
                    text=(
                        "Offline mode uses ollama.context_window + num_predict. "
                        "Online-only controls are disabled."
                    )
                )

    def _set_mode_status(self, text):
        self._mode_status_var.set(text)
        if text:
            self.after(2500, lambda: self._mode_status_var.set(""))

    def _active_locks(self):
        if not self._mode_store_enabled:
            return {}
        state = self._mode_store.get_mode_state(self.config, self._current_mode())
        return state.get("locks", {})

    def _default_value(self, key):
        if not self._mode_store_enabled:
            return self._display_values_from_config().get(key)
        state = self._mode_store.get_mode_state(self.config, self._current_mode())
        return state.get("defaults", {}).get(key)

    def _display_values_from_config(self):
        retrieval = getattr(self.config, "retrieval", None)
        api = getattr(self.config, "api", None)
        ollama = getattr(self.config, "ollama", None)
        return {
            "top_k": getattr(retrieval, "top_k", 5) if retrieval else 5,
            "min_score": getattr(retrieval, "min_score", 0.10) if retrieval else 0.10,
            "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
            "context_window": getattr(ollama, "context_window", 4096) if ollama else 4096,
            "num_predict": getattr(ollama, "num_predict", 512) if ollama else 512,
            "max_tokens": getattr(api, "max_tokens", 16384) if api else 16384,
            "temperature": getattr(api, "temperature", 0.1) if api else 0.1,
            "timeout_seconds": getattr(api, "timeout_seconds", 180) if api else 180,
        }

    def _mode_key_enabled(self, key):
        mode = self._current_mode()
        if key == "num_predict":
            return mode == "offline"
        if key == "max_tokens":
            return mode == "online"
        return True

    def _apply_mode_widget_states(self):
        locks = self._active_locks()
        for key, scale in self._scales.items():
            enabled = self._mode_key_enabled(key)
            locked = bool(locks.get(key, False))
            scale.config(state=(tk.NORMAL if enabled and not locked else tk.DISABLED))
        for key, widget in self._check_widgets.items():
            enabled = self._mode_key_enabled(key)
            locked = bool(locks.get(key, False))
            widget.config(state=(tk.NORMAL if enabled and not locked else tk.DISABLED))

    def _write_active_vars_to_config(self):
        retrieval = getattr(self.config, "retrieval", None)
        api = getattr(self.config, "api", None)
        ollama = getattr(self.config, "ollama", None)
        mode = self._current_mode()
        if retrieval:
            retrieval.top_k = self.topk_var.get()
            retrieval.min_score = self.minscore_var.get()
            retrieval.hybrid_search = self.hybrid_var.get()
        if not self._mode_store_enabled:
            if ollama:
                ollama.context_window = self.ctx_window_var.get()
                ollama.num_predict = self.num_predict_var.get()
            if api:
                api.max_tokens = self.maxtokens_var.get()
                api.temperature = self.temp_var.get()
                api.timeout_seconds = self.timeout_var.get()
            return
        if mode == "online":
            if api:
                api.context_window = self.ctx_window_var.get()
                api.max_tokens = self.maxtokens_var.get()
                api.temperature = self.temp_var.get()
                api.timeout_seconds = self.timeout_var.get()
        else:
            if ollama:
                ollama.context_window = self.ctx_window_var.get()
                ollama.num_predict = self.num_predict_var.get()
                if hasattr(ollama, "temperature"):
                    ollama.temperature = self.temp_var.get()
                ollama.timeout_seconds = self.timeout_var.get()
            elif api:
                api.temperature = self.temp_var.get()

    def _persist_active_mode_values(self):
        if not self._mode_store_enabled:
            return
        mode = self._current_mode()
        values = {
            "top_k": self.topk_var.get(),
            "min_score": self.minscore_var.get(),
            "hybrid_search": self.hybrid_var.get(),
            "context_window": self.ctx_window_var.get(),
            "temperature": self.temp_var.get(),
            "timeout_seconds": self.timeout_var.get(),
        }
        if mode == "online":
            values["max_tokens"] = self.maxtokens_var.get()
        else:
            values["num_predict"] = self.num_predict_var.get()
        for key, value in values.items():
            self._mode_store.update_value(self.config, mode, key, value)

    # ----------------------------------------------------------------
    # HELPER: slider row with Default checkbox
    # ----------------------------------------------------------------

    def _build_slider_row(self, parent, t, key, label, var, from_, to_,
                          resolution=1, on_change=None):
        """Build a labeled slider with a Default checkbox."""
        row = tk.Frame(parent, bg=t["panel_bg"])
        row.pack(fill=tk.X, pady=3)

        tk.Label(row, text=label, width=16, anchor=tk.W,
                 bg=t["panel_bg"], fg=t["fg"], font=FONT).pack(side=tk.LEFT)

        scale = tk.Scale(
            row, from_=from_, to=to_, resolution=resolution,
            orient=tk.HORIZONTAL, variable=var,
            command=lambda v: on_change() if on_change else None,
            bg=t["panel_bg"], fg=t["fg"], troughcolor=t["input_bg"],
            highlightthickness=0, font=FONT,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def_var = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(
            row, text="Default", variable=def_var,
            command=lambda: self._on_default_toggle(key, var, def_var, on_change),
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT_SMALL,
        )
        cb.pack(side=tk.RIGHT, padx=(4, 0))

        self._default_vars[key] = def_var
        self._scales[key] = scale
        return scale

    def _build_check_row(self, parent, t, key, label, var, on_change=None):
        """Build a labeled checkbox with a Default checkbox."""
        row = tk.Frame(parent, bg=t["panel_bg"])
        row.pack(fill=tk.X, pady=3)

        tk.Label(row, text=label, width=16, anchor=tk.W,
                 bg=t["panel_bg"], fg=t["fg"], font=FONT).pack(side=tk.LEFT)

        cb = tk.Checkbutton(
            row, variable=var, command=on_change,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT,
        )
        cb.pack(side=tk.LEFT)

        def_var = tk.BooleanVar(value=False)
        def_cb = tk.Checkbutton(
            row, text="Default", variable=def_var,
            command=lambda: self._on_default_toggle(key, var, def_var, on_change),
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT_SMALL,
        )
        def_cb.pack(side=tk.RIGHT, padx=(4, 0))

        self._default_vars[key] = def_var
        self._check_widgets[key] = cb
        return cb

    def _on_default_toggle(self, key, var, def_var, on_change):
        """Handle Default checkbox toggle for any lockable control."""
        if def_var.get():
            default_value = self._default_value(key)
            if default_value is not None:
                var.set(default_value)
                if self._mode_store_enabled:
                    self._mode_store.update_value(
                        self.config, self._current_mode(), key, default_value
                    )
            if self._mode_store_enabled:
                self._mode_store.set_lock(self.config, self._current_mode(), key, True)
        else:
            if self._mode_store_enabled:
                self._mode_store.set_lock(self.config, self._current_mode(), key, False)
        self._apply_mode_widget_states()
        if on_change:
            on_change()

    # ----------------------------------------------------------------
    # RETRIEVAL SETTINGS
    # ----------------------------------------------------------------

    def _build_retrieval_section(self, t):
        frame = tk.LabelFrame(self, text="Retrieval Settings", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=(8, 4))
        self._retrieval_frame = frame

        retrieval = getattr(self.config, "retrieval", None)

        self.topk_var = tk.IntVar(
            value=getattr(retrieval, "top_k", 5) if retrieval else 5)
        self._build_slider_row(frame, t, 'top_k', "top_k:", self.topk_var,
                               1, 50, on_change=self._on_retrieval_change)

        self.minscore_var = tk.DoubleVar(
            value=getattr(retrieval, "min_score", 0.10) if retrieval else 0.10)
        self._build_slider_row(frame, t, 'min_score', "min_score:", self.minscore_var,
                               0.0, 1.0, resolution=0.01,
                               on_change=self._on_retrieval_change)

        self.hybrid_var = tk.BooleanVar(
            value=getattr(retrieval, "hybrid_search", True) if retrieval else True)
        self._build_check_row(frame, t, 'hybrid_search', "Hybrid search:",
                              self.hybrid_var, on_change=self._on_retrieval_change)

        # Latency warning label
        self._latency_warn_label = tk.Label(
            frame, text="", anchor=tk.W, wraplength=600,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._latency_warn_label.pack(fill=tk.X, pady=(4, 0))
        self._update_latency_warning()

    def _on_retrieval_change(self):
        self._write_active_vars_to_config()
        if not self._syncing:
            self._persist_active_mode_values()
        self._update_latency_warning()
        self._check_dangerous_change()

    # ----------------------------------------------------------------
    # LLM SETTINGS
    # ----------------------------------------------------------------

    def _build_llm_section(self, t):
        frame = tk.LabelFrame(self, text="LLM Settings", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._llm_frame = frame

        ollama = getattr(self.config, "ollama", None)
        api = getattr(self.config, "api", None)

        self.ctx_window_var = tk.IntVar(
            value=getattr(ollama, "context_window", 4096) if ollama else 4096)
        self._build_slider_row(frame, t, 'context_window', "Context window:",
                               self.ctx_window_var, 1024, 131072,
                               on_change=self._on_llm_change)

        self.num_predict_var = tk.IntVar(
            value=getattr(ollama, "num_predict", 512) if ollama else 512)
        self._build_slider_row(frame, t, 'num_predict', "Num predict:",
                               self.num_predict_var, 64, 4096,
                               on_change=self._on_llm_change)

        self.maxtokens_var = tk.IntVar(
            value=getattr(api, "max_tokens", 16384) if api else 16384)
        self._build_slider_row(frame, t, 'max_tokens', "Max tokens (API):",
                               self.maxtokens_var, 256, 16384,
                               on_change=self._on_llm_change)

        self.temp_var = tk.DoubleVar(
            value=getattr(api, "temperature", 0.1) if api else 0.1)
        self._build_slider_row(frame, t, 'temperature', "Temperature:",
                               self.temp_var, 0.0, 1.0, resolution=0.01,
                               on_change=self._on_llm_change)

        self.timeout_var = tk.IntVar(
            value=getattr(api, "timeout_seconds", 180) if api else 180)
        self._build_slider_row(frame, t, 'timeout_seconds', "Timeout (s):",
                               self.timeout_var, 10, 300,
                               on_change=self._on_llm_change)

        self._llm_mode_note = tk.Label(
            frame, text="", anchor=tk.W, wraplength=600,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._llm_mode_note.pack(fill=tk.X, pady=(4, 0))

    def _on_llm_change(self):
        self._write_active_vars_to_config()
        if not self._syncing:
            self._persist_active_mode_values()
        self._update_latency_warning()
        self._check_dangerous_change()

    # ----------------------------------------------------------------
    # LATENCY WARNING (inline label + popup for dangerous thresholds)
    # ----------------------------------------------------------------

    def _get_current_model(self):
        """Return the active Ollama model name."""
        if self._current_mode() == "online":
            api = getattr(self.config, "api", None)
            return (
                getattr(api, "model", "")
                or getattr(api, "deployment", "")
                or "gpt-4o"
            )
        ollama = getattr(self.config, "ollama", None)
        return getattr(ollama, "model", "phi4:14b-q4_K_M") if ollama else "phi4:14b-q4_K_M"

    def _update_latency_warning(self):
        if not hasattr(self, "_latency_warn_label"):
            return
        mode = self._current_mode()
        top_k = self.topk_var.get()
        ctx = self.ctx_window_var.get() if hasattr(self, "ctx_window_var") else 4096
        num_pred = self.num_predict_var.get() if hasattr(self, "num_predict_var") else 512
        model = self._get_current_model()
        if mode == "online":
            max_tokens = self.maxtokens_var.get() if hasattr(self, "maxtokens_var") else 16384
            note = "Online mode: ctx={} | max_tokens={} | model={}".format(
                ctx, max_tokens, model
            )
            if top_k > 15:
                self._latency_warn_label.config(
                    text="[WARN] {} | top_k={} may dilute grounding.".format(note, top_k),
                    fg=current_theme()["orange"],
                )
            else:
                self._latency_warn_label.config(
                    text=note, fg=current_theme()["green"]
                )
            return
        est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
        overflow = _vram_overflows(model, ctx, self._vram_gb)

        warnings = []
        if overflow and self._vram_gb > 0:
            warnings.append("VRAM overflow: {} + ctx={} on {:.0f}GB".format(
                model, ctx, self._vram_gb))
        if top_k > 10:
            warnings.append("top_k={} adds ~{:.0f}s extra".format(
                top_k, (top_k - 5) * 300 / 60))

        t = current_theme()
        if est > 120:
            self._latency_warn_label.config(
                text="[WARN] Est. ~{:.0f}s/query -- {}".format(
                    est, " | ".join(warnings) if warnings else "reduce settings"),
                fg=t["red"])
        elif warnings:
            self._latency_warn_label.config(
                text="[WARN] Est. ~{:.0f}s/query -- {}".format(
                    est, " | ".join(warnings)),
                fg=t["orange"])
        else:
            self._latency_warn_label.config(
                text="Est. ~{:.0f}s/query ({:.0f}GB VRAM, {})".format(
                    est, self._vram_gb, model),
                fg=t["green"])

    def _check_dangerous_change(self):
        """Show a one-time popup when settings cross dangerous thresholds."""
        if not self._mode_store_enabled:
            return
        if self._current_mode() == "online":
            top_k = self.topk_var.get()
            popup_key = None
            title = ""
            msg = ""
            if top_k > 15:
                popup_key = "topk_high_online"
                title = "High top_k -- Retrieval Dilution Risk"
                msg = (
                    "top_k={} can flood the prompt with marginal chunks.\n\n"
                    "For grounded GPT-4o responses, start around 6-10 and tune upward only "
                    "when retrieval quality supports it."
                ).format(top_k)
            if popup_key and popup_key != self._last_popup_key:
                self._last_popup_key = popup_key
                messagebox.showwarning(title, msg)
            return
        ctx = self.ctx_window_var.get() if hasattr(self, "ctx_window_var") else 4096
        top_k = self.topk_var.get()
        num_pred = self.num_predict_var.get() if hasattr(self, "num_predict_var") else 512
        model = self._get_current_model()

        popup_key = None
        title = ""
        msg = ""

        overflow = _vram_overflows(model, ctx, self._vram_gb)
        if overflow and self._vram_gb > 0:
            spec = _MODEL_SPECS.get(model, _MODEL_SPECS.get("phi4:14b-q4_K_M"))
            kv_gb = (ctx / 1000) * spec["kv_per_1k_mb"] / 1024
            total = spec["weight_gb"] + kv_gb
            est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
            popup_key = "ctx_{}".format(ctx // 4096)
            title = "VRAM Overflow -- High Latency"
            msg = (
                "context_window={} with {} needs ~{:.1f}GB VRAM\n"
                "but this machine has {:.0f}GB.\n\n"
                "Model weights: {:.1f}GB\n"
                "KV cache at {}: ~{:.1f}GB\n\n"
                "Ollama will spill to CPU.\n"
                "Estimated query time: {:.0f}s (vs {:.0f}s at 4096).\n\n"
                "Recommended: 4096 for 12GB, 8192+ for 24GB+."
            ).format(
                ctx, model, total, self._vram_gb,
                spec["weight_gb"], ctx, kv_gb,
                est,
                _estimate_query_seconds(top_k, 4096, num_pred, self._vram_gb, model),
            )
        elif top_k > 15:
            est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
            popup_key = "topk_high"
            title = "High top_k -- Slow Queries"
            msg = (
                "top_k={} injects ~{} tokens of context.\n\n"
                "Estimated query time: {:.0f}s on {:.0f}GB VRAM.\n\n"
                "Recommended: top_k <= 8 for 12GB GPU."
            ).format(top_k, top_k * 300, est, self._vram_gb)

        if popup_key and popup_key != self._last_popup_key:
            self._last_popup_key = popup_key
            messagebox.showwarning(title, msg)

    # ----------------------------------------------------------------
    # PERFORMANCE PROFILE
    # ----------------------------------------------------------------

    def _build_profile_section(self, t):
        frame = tk.LabelFrame(self, text="Profile & Model Ranking", padx=16, pady=8,
                               bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._profile_frame = frame

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
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.profile_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Hardware info line
        hw_text = "Detected: {:.0f}GB RAM, {:.0f}GB VRAM -> {}".format(
            self._ram_gb, self._vram_gb, self._hw_class)
        tk.Label(frame, text=hw_text, anchor=tk.W,
                 bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
                 ).pack(fill=tk.X, pady=(2, 0))

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

        self.model_table = tk.Text(
            frame, height=12, wrap=tk.NONE, state=tk.DISABLED,
            font=("Consolas", 9), bg=t["input_bg"], fg=t["input_fg"],
            relief=tk.FLAT, bd=2,
        )
        self.model_table.pack(fill=tk.X, pady=(4, 2))

        self._detect_current_profile()
        self._refresh_profile_info()
        self._refresh_model_table()

    def _detect_current_profile(self):
        self.profile_var.set(_detect_profile_name(self.config))

    def _refresh_profile_info(self):
        embed = getattr(self.config, "embedding", None)
        ollama = getattr(self.config, "ollama", None)
        model_name = getattr(embed, "model_name", "?") if embed else "?"
        dim = getattr(embed, "dimension", "?") if embed else "?"
        device = getattr(embed, "device", "?") if embed else "?"
        llm = getattr(ollama, "model", "?") if ollama else "?"
        self.profile_info_label.config(
            text="Embedder: {} ({}d, {})  |  LLM: {}".format(
                model_name, dim, device, llm),
        )

    def _refresh_model_table(self):
        text = _build_ranking_text(self.profile_var.get())
        self.model_table.config(state=tk.NORMAL)
        self.model_table.delete("1.0", tk.END)
        self.model_table.insert("1.0", text)
        self.model_table.config(state=tk.DISABLED)

    def _on_profile_change(self, event=None):
        t = current_theme()
        profile = self.profile_var.get()
        self.profile_apply_btn.config(state=tk.DISABLED)
        self.profile_status_label.config(
            text="Switching to {}...".format(profile), fg=t["gray"],
        )
        threading.Thread(
            target=self._do_profile_switch, args=(profile,), daemon=True,
        ).start()

    def _do_profile_switch(self, profile):
        _run_profile_switch(self, profile)

    def _profile_switch_done(self, new_config, profile, embedding_changed,
                             old_embed_model, new_embed_model):
        t = current_theme()

        if embedding_changed:
            messagebox.showwarning(
                "Re-Index Required",
                "Embedding model changed:\n\n"
                "  Old: {}\n  New: {}\n\n"
                "Existing vectors are INCOMPATIBLE.\n"
                "You MUST re-index before querying.".format(
                    old_embed_model, new_embed_model),
            )

        self.config = new_config
        try:
            if hasattr(self._app, "reload_config"):
                self._app.reload_config(new_config)
            if hasattr(self._app, "reset_backends"):
                self._app.reset_backends()
        except Exception as e:
            logger.warning("Profile apply failed: %s", e)
            safe_after(self, 0, self._profile_switch_failed,
                       "Backend reset: {}".format(str(e)[:60]))
            return

        # Update safe defaults to match new profile
        self._hw_class = profile
        self._safe = SAFE_DEFAULTS.get(profile, SAFE_DEFAULTS['desktop_power'])

        self._refresh_profile_info()
        self._refresh_model_table()
        self._sync_sliders_to_config()

        status = "[OK] Switched to {}".format(profile)
        if embedding_changed:
            status += " -- RE-INDEX REQUIRED"
        self.profile_status_label.config(text=status, fg=t["green"])
        self.profile_apply_btn.config(state=tk.NORMAL)

    def _profile_switch_failed(self, error_msg):
        t = current_theme()
        self.profile_status_label.config(
            text="[FAIL] {}".format(error_msg), fg=t["red"])
        self.profile_apply_btn.config(state=tk.NORMAL)

    def _sync_sliders_to_config(self):
        if self._mode_store_enabled:
            values = self._mode_store.apply_to_config(self.config, self._current_mode())
        else:
            values = self._display_values_from_config()
        self._apply_values(values)
        self._refresh_mode_banner()
        self._update_latency_warning()

    def _all_vars(self):
        """Map setting keys to their tk variables."""
        return {
            'top_k': self.topk_var, 'min_score': self.minscore_var,
            'hybrid_search': self.hybrid_var,
            'context_window': self.ctx_window_var,
            'num_predict': self.num_predict_var,
            'max_tokens': self.maxtokens_var,
            'temperature': self.temp_var,
            'timeout_seconds': self.timeout_var,
        }

    def _var_matches_safe(self, key):
        var = self._all_vars().get(key)
        default_value = self._default_value(key)
        return var is None or default_value is None or var.get() == default_value

    # ----------------------------------------------------------------
    # RESET TO DEFAULTS
    # ----------------------------------------------------------------

    def _build_reset_button(self, t):
        btn_frame = tk.Frame(self, bg=t["panel_bg"])
        btn_frame.pack(fill=tk.X, padx=16, pady=16)
        self._reset_frame = btn_frame

        self._save_mode_defaults_btn = tk.Button(
            btn_frame, text="Save Active Mode Defaults",
            command=self._on_save_mode_defaults,
            width=24, bg=t["accent"], fg=t["accent_fg"],
            font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
        )
        self._save_mode_defaults_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self._save_mode_defaults_btn)

        self._reset_btn = tk.Button(
            btn_frame, text="Reset to Defaults", command=self._on_reset,
            width=16, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
        )
        self._reset_btn.pack(side=tk.LEFT)
        bind_hover(self._reset_btn)

        self._lock_all_btn = tk.Button(
            btn_frame, text="Lock All to Defaults", command=self._lock_all_defaults,
            width=16, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
        )
        self._lock_all_btn.pack(side=tk.LEFT, padx=(8, 0))
        bind_hover(self._lock_all_btn)

    def _apply_values(self, vals):
        """Set all slider/check vars from a dict and refresh default checkboxes."""
        self._syncing = True
        for key, var in self._all_vars().items():
            if key in vals:
                var.set(vals[key])
        locks = self._active_locks()
        for key, def_var in self._default_vars.items():
            def_var.set(bool(locks.get(key, False)))
        self._apply_mode_widget_states()
        self._syncing = False
        self._write_active_vars_to_config()
        self._update_latency_warning()

    def _on_reset(self):
        if not self._mode_store_enabled:
            self._apply_values(self._legacy_defaults)
            self._set_mode_status("[OK] Reset settings")
            return
        self._mode_store.reset_mode_to_defaults(self.config, self._current_mode())
        self._sync_sliders_to_config()
        self._set_mode_status("[OK] Reset active mode to defaults")

    def _on_save_mode_defaults(self):
        if not self._mode_store_enabled:
            return
        self._persist_active_mode_values()
        self._mode_store.save_mode_defaults_from_values(self.config, self._current_mode())
        self._sync_sliders_to_config()
        self._set_mode_status("[OK] Saved {} defaults".format(self._current_mode()))

    def _lock_all_defaults(self):
        """Lock every setting to the active mode's saved defaults."""
        if not self._mode_store_enabled:
            return
        mode = self._current_mode()
        for key, def_var in self._default_vars.items():
            if self._mode_key_enabled(key):
                def_var.set(True)
                self._mode_store.set_lock(self.config, mode, key, True)
        self._mode_store.reset_mode_to_defaults(self.config, mode)
        self._sync_sliders_to_config()
        self._set_mode_status("[OK] Locked active mode to defaults")

    # ----------------------------------------------------------------
    # THEME
    # ----------------------------------------------------------------

    def apply_theme(self, t):
        self.configure(bg=t["panel_bg"])
        for frame_attr in ("_retrieval_frame", "_llm_frame", "_profile_frame"):
            frame = getattr(self, frame_attr, None)
            if frame:
                frame.configure(bg=t["panel_bg"], fg=t["accent"])
                for child in frame.winfo_children():
                    _theme_widget(child, t)
        if hasattr(self, "_reset_frame"):
            self._reset_frame.configure(bg=t["panel_bg"])
            self._save_mode_defaults_btn.configure(
                bg=t["accent"], fg=t["accent_fg"])
            self._reset_btn.configure(
                bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
            self._lock_all_btn.configure(
                bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
        if hasattr(self, "_mode_row"):
            self._mode_row.configure(bg=t["panel_bg"])
            self._mode_banner.configure(bg=t["panel_bg"], fg=t["accent"])
            self._mode_status.configure(bg=t["panel_bg"], fg=t["gray"])
