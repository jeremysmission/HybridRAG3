import json
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from src.core.mode_config import MODE_TUNED_DEFAULTS, normalize_mode
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.settings_view import (
    _build_ranking_text,
    _detect_profile_name,
    _load_profile_names,
    _theme_widget,
)
from src.gui.theme import FONT, FONT_BOLD, FONT_SMALL, bind_hover, current_theme

logger = logging.getLogger(__name__)


SAFE_DEFAULTS = {
    "laptop_safe": {
        "top_k": 4,
        "min_score": 0.10,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "num_predict": 384,
        "max_tokens": 1024,
        "temperature": 0.05,
        "top_p": 0.90,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": 0,
        "timeout_seconds": 180,
    },
    "desktop_power": {
        "top_k": 4,
        "min_score": 0.10,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "num_predict": 384,
        "max_tokens": 1024,
        "temperature": 0.05,
        "top_p": 0.90,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": 0,
        "timeout_seconds": 180,
    },
    "server_max": {
        "top_k": 10,
        "min_score": 0.10,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 30,
        "context_window": 4096,
        "num_predict": 384,
        "max_tokens": 1024,
        "temperature": 0.05,
        "top_p": 0.90,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": 0,
        "timeout_seconds": 180,
    },
}


def _mode_llm_values_from_config(config, mode: str) -> dict:
    """Return visible tuning values for the active mode without mixing paths."""
    mode = normalize_mode(mode)
    retrieval = getattr(config, "retrieval", None)
    api = getattr(config, "api", None)
    ollama = getattr(config, "ollama", None)
    offline_defaults = MODE_TUNED_DEFAULTS["offline"]
    online_defaults = MODE_TUNED_DEFAULTS["online"]
    active_defaults = MODE_TUNED_DEFAULTS[mode]

    values = {
        "top_k": getattr(retrieval, "top_k", active_defaults["top_k"]) if retrieval else active_defaults["top_k"],
        "min_score": getattr(retrieval, "min_score", active_defaults["min_score"]) if retrieval else active_defaults["min_score"],
        "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
        "context_window": offline_defaults["context_window"],
        "num_predict": getattr(ollama, "num_predict", offline_defaults["num_predict"]) if ollama else offline_defaults["num_predict"],
        "max_tokens": getattr(api, "max_tokens", online_defaults["max_tokens"]) if api else online_defaults["max_tokens"],
        "temperature": offline_defaults["temperature"] if mode == "offline" else online_defaults["temperature"],
        "top_p": offline_defaults["top_p"] if mode == "offline" else online_defaults["top_p"],
        "presence_penalty": online_defaults["presence_penalty"],
        "frequency_penalty": online_defaults["frequency_penalty"],
        "seed": offline_defaults["seed"] if mode == "offline" else online_defaults["seed"],
        "timeout_seconds": offline_defaults["timeout_seconds"] if mode == "offline" else online_defaults["timeout_seconds"],
    }

    if mode == "online":
        values["context_window"] = (
            getattr(api, "context_window", online_defaults["context_window"])
            if api
            else online_defaults["context_window"]
        )
        values["temperature"] = (
            getattr(api, "temperature", online_defaults["temperature"])
            if api
            else online_defaults["temperature"]
        )
        values["top_p"] = (
            getattr(api, "top_p", online_defaults["top_p"])
            if api
            else online_defaults["top_p"]
        )
        values["presence_penalty"] = (
            getattr(api, "presence_penalty", online_defaults["presence_penalty"])
            if api
            else online_defaults["presence_penalty"]
        )
        values["frequency_penalty"] = (
            getattr(api, "frequency_penalty", online_defaults["frequency_penalty"])
            if api
            else online_defaults["frequency_penalty"]
        )
        values["seed"] = (
            getattr(api, "seed", online_defaults["seed"])
            if api
            else online_defaults["seed"]
        )
        values["timeout_seconds"] = (
            getattr(api, "timeout_seconds", online_defaults["timeout_seconds"])
            if api
            else online_defaults["timeout_seconds"]
        )
    else:
        values["context_window"] = (
            getattr(ollama, "context_window", offline_defaults["context_window"])
            if ollama
            else offline_defaults["context_window"]
        )
        values["temperature"] = (
            getattr(ollama, "temperature", offline_defaults["temperature"])
            if ollama and hasattr(ollama, "temperature")
            else offline_defaults["temperature"]
        )
        values["top_p"] = (
            getattr(ollama, "top_p", offline_defaults["top_p"])
            if ollama
            else offline_defaults["top_p"]
        )
        values["seed"] = (
            getattr(ollama, "seed", offline_defaults["seed"])
            if ollama
            else offline_defaults["seed"]
        )
        values["timeout_seconds"] = (
            getattr(ollama, "timeout_seconds", offline_defaults["timeout_seconds"])
            if ollama
            else offline_defaults["timeout_seconds"]
        )
    return values


def _detect_hardware_class():
    """Read system_profile.json, falling back to a live nvidia-smi + psutil probe."""
    root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
    path = os.path.join(root, "config", "system_profile.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        hw = data.get("hardware", {})
        vram = hw.get("gpu_vram_gb", 0.0)
        ram = hw.get("ram_gb", 0.0)
        profile = data.get("profile", {}).get("recommended_profile", "desktop_power")
        if vram > 0 or ram > 0:
            return profile, vram, ram
    except Exception:
        pass

    vram = 0.0
    ram = 0.0
    try:
        import psutil

        ram = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
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


_MODEL_SPECS = {
    "phi4-mini": {"weight_gb": 2.3, "kv_per_1k_mb": 150, "gpu_tok_s": 45},
    "phi4:14b-q4_K_M": {"weight_gb": 9.1, "kv_per_1k_mb": 400, "gpu_tok_s": 20},
    "mistral:7b": {"weight_gb": 4.1, "kv_per_1k_mb": 200, "gpu_tok_s": 35},
    "mistral-nemo:12b": {"weight_gb": 7.1, "kv_per_1k_mb": 350, "gpu_tok_s": 22},
    "gemma3:4b": {"weight_gb": 3.3, "kv_per_1k_mb": 150, "gpu_tok_s": 40},
}


def _vram_overflows(model_name, ctx_window, vram_gb):
    """True if model + KV cache at ctx_window exceeds available VRAM."""
    if vram_gb <= 0:
        return True
    spec = _MODEL_SPECS.get(model_name, _MODEL_SPECS.get("phi4:14b-q4_K_M"))
    kv_gb = (ctx_window / 1000) * spec["kv_per_1k_mb"] / 1024
    return (spec["weight_gb"] + kv_gb) > vram_gb * 0.95


def _estimate_query_seconds(top_k, ctx_window, num_predict, vram_gb, model_name="phi4:14b-q4_K_M"):
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
        prompt_rate = spec["gpu_tok_s"] * 3
        gen_rate = spec["gpu_tok_s"]
    return prompt_tokens / prompt_rate + output_tokens / gen_rate


def _run_profile_switch(tab, profile):
    """Background thread: run subprocess, reload config, reset backends."""
    root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
    old_embed = getattr(getattr(tab.config, "embedding", None), "model_name", "")

    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "_profile_switch.py"), profile],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=root,
        )
        if proc.returncode != 0:
            safe_after(tab, 0, tab._profile_switch_failed, proc.stderr.strip()[:80])
            return
    except Exception as exc:
        safe_after(tab, 0, tab._profile_switch_failed, str(exc)[:80])
        return

    try:
        from src.core.config import load_config

        new_config = load_config(root)
    except Exception as exc:
        safe_after(tab, 0, tab._profile_switch_failed, "Config reload: {}".format(str(exc)[:60]))
        return

    new_config.mode = tab.config.mode
    try:
        from src.core.network_gate import configure_gate

        if new_config.mode == "online":
            configure_gate(
                mode="online",
                api_endpoint=getattr(getattr(new_config, "api", None), "endpoint", "") or "",
                allowed_prefixes=getattr(getattr(new_config, "api", None), "allowed_endpoint_prefixes", []),
            )
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
        except Exception as exc:
            logger.warning("Could not clear embedder cache: %s", exc)

    safe_after(tab, 0, tab._profile_switch_done, new_config, profile, embed_changed, old_embed, new_embed)


def _capture_values(self):
    if self._mode_store_enabled:
        return self._mode_store.get_active_values(self.config, self._current_mode())
    return self._display_values_from_config()


def get_profile_options(self):
    return list(self.profile_dropdown["values"])


def _current_mode(self):
    return normalize_mode(self._editor_mode_var.get())


def _runtime_mode(self):
    return "online" if str(getattr(self.config, "mode", "offline")).lower() == "online" else "offline"


def _build_mode_banner(self, theme):
    row = tk.Frame(self, bg=theme["panel_bg"])
    row.pack(fill=tk.X, padx=16, pady=(10, 2))
    self._mode_row = row
    tk.Label(
        row,
        text="Admin target:",
        anchor=tk.W,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        font=FONT,
    ).pack(side=tk.LEFT)
    self._mode_selector = ttk.Combobox(
        row,
        textvariable=self._editor_mode_var,
        values=["offline", "online"],
        state="readonly",
        width=10,
        font=FONT,
    )
    self._mode_selector.pack(side=tk.LEFT, padx=(8, 12))
    self._mode_selector.bind("<<ComboboxSelected>>", self._on_editor_mode_change)
    self._mode_banner = tk.Label(
        row,
        textvariable=self._mode_banner_var,
        anchor=tk.W,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    self._mode_banner.pack(side=tk.LEFT, fill=tk.X, expand=True)
    self._mode_status = tk.Label(
        row,
        textvariable=self._mode_status_var,
        anchor=tk.E,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._mode_status.pack(side=tk.RIGHT)


def _build_editor_columns(self, theme):
    split = tk.Frame(self, bg=theme["panel_bg"])
    split.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
    self._editor_split = split

    left = tk.Frame(split, bg=theme["panel_bg"])
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 6))
    self._retrieval_column = left

    right = tk.Frame(split, bg=theme["panel_bg"])
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 8))
    self._query_column = right

    self._build_retrieval_section(theme, parent=left)
    self._build_llm_section(theme, parent=right)


def _refresh_mode_banner(self):
    mode = self._current_mode()
    runtime_mode = self._runtime_mode()
    self._mode_banner_var.set(
        "Editing {} defaults in Admin  |  Runtime mode: {}.".format(mode.upper(), runtime_mode.upper())
    )
    if hasattr(self, "_llm_frame"):
        self._llm_frame.config(text="Query & Generation ({})".format(mode.capitalize()))
    if hasattr(self, "_llm_mode_note"):
        if mode == "online":
            self._llm_mode_note.config(
                text=(
                    "Online mode uses api.context_window + max_tokens. "
                    "Changes save to config.yaml and apply live when runtime is online."
                )
            )
        else:
            self._llm_mode_note.config(
                text=(
                    "Offline mode uses ollama.context_window + num_predict. "
                    "Changes save to config.yaml and apply live when runtime is offline."
                )
            )


def _set_mode_status(self, text):
    self._mode_status_var.set(text)
    if text:
        self.after(2500, lambda: self._mode_status_var.set(""))


def _on_editor_mode_change(self, event=None):
    self._sync_sliders_to_config()


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
    return _mode_llm_values_from_config(self.config, self._current_mode())


def _current_seed_value(self):
    mode = self._current_mode()
    if mode == "online":
        api = getattr(self.config, "api", None)
        return int(getattr(api, "seed", 0) or 0) if api is not None else 0
    ollama = getattr(self.config, "ollama", None)
    return int(getattr(ollama, "seed", 0) or 0) if ollama is not None else 0


def _seed_value_or_current(self):
    try:
        return int(self.seed_var.get())
    except (tk.TclError, TypeError, ValueError):
        return self._current_seed_value()


def _var_value(self, key, var):
    if key == "seed":
        return self._seed_value_or_current()
    try:
        return var.get()
    except tk.TclError:
        return None


def _mode_key_enabled(self, key):
    mode = self._current_mode()
    if key == "num_predict":
        return mode == "offline"
    if key == "max_tokens":
        return mode == "online"
    if key in ("presence_penalty", "frequency_penalty"):
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
    if self._current_mode() != self._runtime_mode():
        return
    retrieval = getattr(self.config, "retrieval", None)
    api = getattr(self.config, "api", None)
    ollama = getattr(self.config, "ollama", None)
    mode = self._current_mode()
    if retrieval:
        retrieval.top_k = self.topk_var.get()
        retrieval.min_score = self.minscore_var.get()
        retrieval.hybrid_search = self.hybrid_var.get()
    if not self._mode_store_enabled:
        if mode == "online":
            if api:
                api.context_window = self.ctx_window_var.get()
                api.max_tokens = self.maxtokens_var.get()
                api.temperature = self.temp_var.get()
                api.top_p = self.top_p_var.get()
                api.presence_penalty = self.presence_penalty_var.get()
                api.frequency_penalty = self.frequency_penalty_var.get()
                api.seed = self._seed_value_or_current()
                api.timeout_seconds = self.timeout_var.get()
        else:
            if ollama:
                ollama.context_window = self.ctx_window_var.get()
                ollama.num_predict = self.num_predict_var.get()
                if hasattr(ollama, "temperature"):
                    ollama.temperature = self.temp_var.get()
                ollama.top_p = self.top_p_var.get()
                ollama.seed = self._seed_value_or_current()
                ollama.timeout_seconds = self.timeout_var.get()
        return
    if mode == "online":
        if api:
            api.context_window = self.ctx_window_var.get()
            api.max_tokens = self.maxtokens_var.get()
            api.temperature = self.temp_var.get()
            api.top_p = self.top_p_var.get()
            api.presence_penalty = self.presence_penalty_var.get()
            api.frequency_penalty = self.frequency_penalty_var.get()
            api.seed = self._seed_value_or_current()
            api.timeout_seconds = self.timeout_var.get()
    else:
        if ollama:
            ollama.context_window = self.ctx_window_var.get()
            ollama.num_predict = self.num_predict_var.get()
            if hasattr(ollama, "temperature"):
                ollama.temperature = self.temp_var.get()
            ollama.top_p = self.top_p_var.get()
            ollama.seed = self._seed_value_or_current()
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
        "top_p": self.top_p_var.get(),
        "seed": self._seed_value_or_current(),
        "timeout_seconds": self.timeout_var.get(),
    }
    if mode == "online":
        values["max_tokens"] = self.maxtokens_var.get()
        values["presence_penalty"] = self.presence_penalty_var.get()
        values["frequency_penalty"] = self.frequency_penalty_var.get()
    else:
        values["num_predict"] = self.num_predict_var.get()
    for key, value in values.items():
        self._mode_store.update_value(self.config, mode, key, value)


def _build_slider_row(self, parent, theme, key, label, var, from_, to_, resolution=1, on_change=None):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    scale = tk.Scale(
        row,
        from_=from_,
        to=to_,
        resolution=resolution,
        orient=tk.HORIZONTAL,
        variable=var,
        command=lambda _value: on_change() if on_change else None,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        troughcolor=theme["input_bg"],
        highlightthickness=0,
        font=FONT,
    )
    scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def_var = tk.BooleanVar(value=False)
    checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._scales[key] = scale
    return scale


def _build_entry_row(self, parent, theme, key, label, var, on_change=None, width=12):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    entry = tk.Entry(
        row,
        textvariable=var,
        width=width,
        bg=theme["input_bg"],
        fg=theme["fg"],
        insertbackground=theme["fg"],
        relief=tk.FLAT,
        font=FONT,
    )
    entry.pack(side=tk.LEFT, padx=(0, 8))
    if on_change is not None:
        entry.bind("<FocusOut>", lambda _event: on_change())
        entry.bind("<Return>", lambda _event: on_change())

    def_var = tk.BooleanVar(value=False)
    checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._scales[key] = entry
    return entry


def _build_check_row(self, parent, theme, key, label, var, on_change=None):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    checkbox = tk.Checkbutton(
        row,
        variable=var,
        command=on_change,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT,
    )
    checkbox.pack(side=tk.LEFT)

    def_var = tk.BooleanVar(value=False)
    default_checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    default_checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._check_widgets[key] = checkbox
    return checkbox


def _on_default_toggle(self, key, var, def_var, on_change):
    if def_var.get():
        default_value = self._default_value(key)
        if default_value is not None:
            var.set(default_value)
            if self._mode_store_enabled:
                self._mode_store.update_value(self.config, self._current_mode(), key, default_value)
        if self._mode_store_enabled:
            self._mode_store.set_lock(self.config, self._current_mode(), key, True)
    else:
        if self._mode_store_enabled:
            self._mode_store.set_lock(self.config, self._current_mode(), key, False)
    self._apply_mode_widget_states()
    if on_change:
        on_change()


def _build_retrieval_section(self, theme, parent=None):
    host = parent or self
    frame = tk.LabelFrame(
        host,
        text="Retrieval Settings",
        padx=16,
        pady=8,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    frame.pack(
        fill=tk.BOTH if parent is not None else tk.X,
        expand=bool(parent is not None),
        padx=8 if parent is not None else 16,
        pady=(8, 4) if parent is None else (4, 4),
    )
    self._retrieval_frame = frame

    values = self._display_values_from_config()

    self.topk_var = tk.IntVar(value=values["top_k"])
    self._build_slider_row(frame, theme, "top_k", "top_k:", self.topk_var, 1, 50, on_change=self._on_retrieval_change)

    self.minscore_var = tk.DoubleVar(value=values["min_score"])
    self._build_slider_row(
        frame,
        theme,
        "min_score",
        "min_score:",
        self.minscore_var,
        0.0,
        1.0,
        resolution=0.01,
        on_change=self._on_retrieval_change,
    )

    self.hybrid_var = tk.BooleanVar(value=values["hybrid_search"])
    self._build_check_row(frame, theme, "hybrid_search", "Hybrid search:", self.hybrid_var, on_change=self._on_retrieval_change)

    self._latency_warn_label = tk.Label(
        frame,
        text="",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._latency_warn_label.pack(fill=tk.X, pady=(4, 0))
    self._update_latency_warning()


def _on_retrieval_change(self):
    self._write_active_vars_to_config()
    if not self._syncing:
        self._persist_active_mode_values()
    self._update_latency_warning()
    self._check_dangerous_change()


def _build_llm_section(self, theme, parent=None):
    host = parent or self
    frame = tk.LabelFrame(
        host,
        text="Query & Generation",
        padx=16,
        pady=8,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    frame.pack(
        fill=tk.BOTH if parent is not None else tk.X,
        expand=bool(parent is not None),
        padx=8 if parent is not None else 16,
        pady=8 if parent is None else (4, 4),
    )
    self._llm_frame = frame

    values = self._display_values_from_config()

    self.ctx_window_var = tk.IntVar(value=values["context_window"])
    self._build_slider_row(
        frame,
        theme,
        "context_window",
        "Context window:",
        self.ctx_window_var,
        1024,
        131072,
        on_change=self._on_llm_change,
    )

    self.num_predict_var = tk.IntVar(value=values["num_predict"])
    self._build_slider_row(frame, theme, "num_predict", "Num predict:", self.num_predict_var, 64, 4096, on_change=self._on_llm_change)

    self.maxtokens_var = tk.IntVar(value=values["max_tokens"])
    self._build_slider_row(
        frame,
        theme,
        "max_tokens",
        "Max tokens (API):",
        self.maxtokens_var,
        256,
        16384,
        on_change=self._on_llm_change,
    )

    self.temp_var = tk.DoubleVar(value=values["temperature"])
    self._build_slider_row(
        frame,
        theme,
        "temperature",
        "Temperature:",
        self.temp_var,
        0.0,
        2.0,
        resolution=0.01,
        on_change=self._on_llm_change,
    )

    self.top_p_var = tk.DoubleVar(value=values["top_p"])
    self._build_slider_row(
        frame,
        theme,
        "top_p",
        "Top p:",
        self.top_p_var,
        0.05,
        1.0,
        resolution=0.01,
        on_change=self._on_llm_change,
    )

    self.presence_penalty_var = tk.DoubleVar(value=values["presence_penalty"])
    self._build_slider_row(
        frame,
        theme,
        "presence_penalty",
        "Presence penalty:",
        self.presence_penalty_var,
        -2.0,
        2.0,
        resolution=0.05,
        on_change=self._on_llm_change,
    )

    self.frequency_penalty_var = tk.DoubleVar(value=values["frequency_penalty"])
    self._build_slider_row(
        frame,
        theme,
        "frequency_penalty",
        "Frequency penalty:",
        self.frequency_penalty_var,
        -2.0,
        2.0,
        resolution=0.05,
        on_change=self._on_llm_change,
    )

    self.seed_var = tk.IntVar(value=values["seed"])
    self._build_entry_row(
        frame,
        theme,
        "seed",
        "Seed:",
        self.seed_var,
        on_change=self._on_llm_change,
    )

    self.timeout_var = tk.IntVar(value=values["timeout_seconds"])
    self._build_slider_row(
        frame,
        theme,
        "timeout_seconds",
        "Timeout (s):",
        self.timeout_var,
        30,
        1200,
        on_change=self._on_llm_change,
    )

    self._llm_mode_note = tk.Label(
        frame,
        text="",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._llm_mode_note.pack(fill=tk.X, pady=(4, 0))


def _on_llm_change(self):
    self._write_active_vars_to_config()
    if not self._syncing:
        self._persist_active_mode_values()
    self._update_latency_warning()
    self._check_dangerous_change()


def _get_current_model(self):
    if self._current_mode() == "online":
        api = getattr(self.config, "api", None)
        return getattr(api, "model", "") or getattr(api, "deployment", "") or "gpt-4o"
    ollama = getattr(self.config, "ollama", None)
    return getattr(ollama, "model", "phi4-mini") if ollama else "phi4-mini"


def _update_latency_warning(self):
    if not hasattr(self, "_latency_warn_label"):
        return
    mode = self._current_mode()
    top_k = self.topk_var.get()
    ctx = self.ctx_window_var.get() if hasattr(self, "ctx_window_var") else 4096
    num_pred = self.num_predict_var.get() if hasattr(self, "num_predict_var") else 384
    model = self._get_current_model()
    if mode == "online":
        max_tokens = self.maxtokens_var.get() if hasattr(self, "maxtokens_var") else 1024
        note = "Online mode: ctx={} | max_tokens={} | model={}".format(ctx, max_tokens, model)
        if top_k > 15:
            self._latency_warn_label.config(
                text="[WARN] {} | top_k={} may dilute grounding.".format(note, top_k),
                fg=current_theme()["orange"],
            )
        else:
            self._latency_warn_label.config(text=note, fg=current_theme()["green"])
        return

    est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
    overflow = _vram_overflows(model, ctx, self._vram_gb)
    warnings = []
    if overflow and self._vram_gb > 0:
        warnings.append("VRAM overflow: {} + ctx={} on {:.0f}GB".format(model, ctx, self._vram_gb))
    if top_k > 10:
        warnings.append("top_k={} adds ~{:.0f}s extra".format(top_k, (top_k - 5) * 300 / 60))

    theme = current_theme()
    if est > 120:
        self._latency_warn_label.config(
            text="[WARN] Est. ~{:.0f}s/query -- {}".format(est, " | ".join(warnings) if warnings else "reduce settings"),
            fg=theme["red"],
        )
    elif warnings:
        self._latency_warn_label.config(
            text="[WARN] Est. ~{:.0f}s/query -- {}".format(est, " | ".join(warnings)),
            fg=theme["orange"],
        )
    else:
        self._latency_warn_label.config(
            text="Est. ~{:.0f}s/query ({:.0f}GB VRAM, {})".format(est, self._vram_gb, model),
            fg=theme["green"],
        )


def _check_dangerous_change(self):
    if not self._mode_store_enabled:
        return
    if self._current_mode() == "online":
        top_k = self.topk_var.get()
        if top_k > 15:
            popup_key = "topk_high_online"
            title = "High top_k -- Retrieval Dilution Risk"
            message = (
                "top_k={} can flood the prompt with marginal chunks.\n\n"
                "For grounded GPT-4o responses, start around 6-10 and tune upward only when retrieval quality supports it."
            ).format(top_k)
            if popup_key != self._last_popup_key:
                self._last_popup_key = popup_key
                self._set_mode_status("[WARN] {}".format(title))
                logger.warning("tuning_warning_online: %s | %s", title, message)
        else:
            self._last_popup_key = None
        return

    ctx = self.ctx_window_var.get() if hasattr(self, "ctx_window_var") else 4096
    top_k = self.topk_var.get()
    num_pred = self.num_predict_var.get() if hasattr(self, "num_predict_var") else 384
    model = self._get_current_model()

    popup_key = None
    title = ""
    message = ""
    overflow = _vram_overflows(model, ctx, self._vram_gb)
    if overflow and self._vram_gb > 0:
        spec = _MODEL_SPECS.get(model, _MODEL_SPECS.get("phi4:14b-q4_K_M"))
        kv_gb = (ctx / 1000) * spec["kv_per_1k_mb"] / 1024
        total = spec["weight_gb"] + kv_gb
        est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
        popup_key = "ctx_{}".format(ctx // 4096)
        title = "VRAM Overflow -- High Latency"
        message = (
            "context_window={} with {} needs ~{:.1f}GB VRAM\n"
            "but this machine has {:.0f}GB.\n\n"
            "Model weights: {:.1f}GB\n"
            "KV cache at {}: ~{:.1f}GB\n\n"
            "Ollama will spill to CPU.\n"
            "Estimated query time: {:.0f}s (vs {:.0f}s at 4096).\n\n"
            "Recommended: 4096 for 12GB, 8192+ for 24GB+."
        ).format(
            ctx,
            model,
            total,
            self._vram_gb,
            spec["weight_gb"],
            ctx,
            kv_gb,
            est,
            _estimate_query_seconds(top_k, 4096, num_pred, self._vram_gb, model),
        )
    elif top_k > 15:
        est = _estimate_query_seconds(top_k, ctx, num_pred, self._vram_gb, model)
        popup_key = "topk_high"
        title = "High top_k -- Slow Queries"
        message = (
            "top_k={} injects ~{} tokens of context.\n\n"
            "Estimated query time: {:.0f}s on {:.0f}GB VRAM.\n\n"
            "Recommended: top_k <= 8 for 12GB GPU."
        ).format(top_k, top_k * 300, est, self._vram_gb)

    if popup_key:
        if popup_key != self._last_popup_key:
            self._last_popup_key = popup_key
            self._set_mode_status("[WARN] {}".format(title))
            logger.warning("tuning_warning_offline: %s | %s", title, message)
    else:
        self._last_popup_key = None


def _build_profile_section(self, theme):
    frame = tk.LabelFrame(self, text="Profile & Model Ranking", padx=16, pady=8, bg=theme["panel_bg"], fg=theme["accent"], font=FONT_BOLD)
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._profile_frame = frame

    row = tk.Frame(frame, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=4)

    self._profile_label = tk.Label(row, text="Profile:", width=14, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT)
    self._profile_label.pack(side=tk.LEFT)

    self.profile_var = tk.StringVar(value="desktop_power")
    self.profile_dropdown = ttk.Combobox(
        row,
        textvariable=self.profile_var,
        values=_load_profile_names(),
        state="readonly",
        width=20,
        font=FONT,
    )
    self.profile_dropdown.pack(side=tk.LEFT, padx=(8, 0))

    self.profile_apply_btn = tk.Button(
        row,
        text="Apply",
        command=self._on_profile_change,
        width=8,
        bg=theme["accent"],
        fg=theme["accent_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=6,
        pady=2,
        activebackground=theme["accent_hover"],
        activeforeground=theme["accent_fg"],
    )
    self.profile_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

    hw_text = "Detected: {:.0f}GB RAM, {:.0f}GB VRAM -> {}".format(self._ram_gb, self._vram_gb, self._hw_class)
    tk.Label(frame, text=hw_text, anchor=tk.W, bg=theme["panel_bg"], fg=theme["gray"], font=FONT_SMALL).pack(fill=tk.X, pady=(2, 0))

    self.profile_info_label = tk.Label(frame, text="", anchor=tk.W, fg=theme["fg"], bg=theme["panel_bg"], font=FONT_SMALL)
    self.profile_info_label.pack(fill=tk.X, pady=(2, 0))

    self.profile_status_label = tk.Label(frame, text="", anchor=tk.W, fg=theme["gray"], bg=theme["panel_bg"], font=FONT)
    self.profile_status_label.pack(fill=tk.X, pady=2)

    self.model_table = tk.Text(
        frame,
        height=12,
        wrap=tk.NONE,
        state=tk.DISABLED,
        font=("Consolas", 9),
        bg=theme["input_bg"],
        fg=theme["input_fg"],
        relief=tk.FLAT,
        bd=2,
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
    self.profile_info_label.config(text="Embedder: {} ({}d, {})  |  LLM: {}".format(model_name, dim, device, llm))


def _refresh_model_table(self):
    text = _build_ranking_text(self.profile_var.get())
    self.model_table.config(state=tk.NORMAL)
    self.model_table.delete("1.0", tk.END)
    self.model_table.insert("1.0", text)
    self.model_table.config(state=tk.DISABLED)


def _on_profile_change(self, event=None):
    theme = current_theme()
    profile = self.profile_var.get()
    self.profile_apply_btn.config(state=tk.DISABLED)
    self.profile_status_label.config(text="Switching to {}...".format(profile), fg=theme["gray"])
    threading.Thread(target=self._do_profile_switch, args=(profile,), daemon=True).start()


def _do_profile_switch(self, profile):
    _run_profile_switch(self, profile)


def _profile_switch_done(self, new_config, profile, embedding_changed, old_embed_model, new_embed_model):
    theme = current_theme()
    if embedding_changed:
        messagebox.showwarning(
            "Re-Index Required",
            "Embedding model changed:\n\n"
            "  Old: {}\n  New: {}\n\n"
            "Existing vectors are INCOMPATIBLE.\n"
            "You MUST re-index before querying.".format(old_embed_model, new_embed_model),
        )

    self.config = new_config
    try:
        if hasattr(self._app, "reload_config"):
            self._app.reload_config(new_config)
        if hasattr(self._app, "reset_backends"):
            self._app.reset_backends()
    except Exception as exc:
        logger.warning("Profile apply failed: %s", exc)
        safe_after(self, 0, self._profile_switch_failed, "Backend reset: {}".format(str(exc)[:60]))
        return

    self._hw_class = profile
    self._safe = SAFE_DEFAULTS.get(profile, SAFE_DEFAULTS["desktop_power"])

    self._refresh_profile_info()
    self._refresh_model_table()
    self._sync_sliders_to_config()

    status = "[OK] Switched to {}".format(profile)
    if embedding_changed:
        status += " -- RE-INDEX REQUIRED"
    self.profile_status_label.config(text=status, fg=theme["green"])
    self.profile_apply_btn.config(state=tk.NORMAL)


def _profile_switch_failed(self, error_msg):
    theme = current_theme()
    self.profile_status_label.config(text="[FAIL] {}".format(error_msg), fg=theme["red"])
    self.profile_apply_btn.config(state=tk.NORMAL)


def _sync_sliders_to_config(self):
    if self._mode_store_enabled:
        mode = self._current_mode()
        if mode == self._runtime_mode():
            values = self._mode_store.apply_to_config(self.config, mode)
        else:
            values = self._mode_store.get_active_values(self.config, mode)
    else:
        values = self._display_values_from_config()
    self._apply_values(values)
    self._refresh_mode_banner()
    self._update_latency_warning()


def _all_vars(self):
    return {
        "top_k": self.topk_var,
        "min_score": self.minscore_var,
        "hybrid_search": self.hybrid_var,
        "context_window": self.ctx_window_var,
        "num_predict": self.num_predict_var,
        "max_tokens": self.maxtokens_var,
        "temperature": self.temp_var,
        "top_p": self.top_p_var,
        "presence_penalty": self.presence_penalty_var,
        "frequency_penalty": self.frequency_penalty_var,
        "seed": self.seed_var,
        "timeout_seconds": self.timeout_var,
    }


def _var_matches_safe(self, key):
    var = self._all_vars().get(key)
    default_value = self._default_value(key)
    current_value = self._var_value(key, var) if var is not None else None
    return var is None or default_value is None or current_value == default_value


def _build_reset_button(self, theme):
    frame = tk.Frame(self, bg=theme["panel_bg"])
    frame.pack(fill=tk.X, padx=16, pady=16)
    self._reset_frame = frame

    self._save_mode_defaults_btn = tk.Button(
        frame,
        text="Save Active Mode Defaults",
        command=self._on_save_mode_defaults,
        width=24,
        bg=theme["accent"],
        fg=theme["accent_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._save_mode_defaults_btn.pack(side=tk.LEFT, padx=(0, 8))
    bind_hover(self._save_mode_defaults_btn)

    self._reset_btn = tk.Button(
        frame,
        text="Reset to Defaults",
        command=self._on_reset,
        width=16,
        bg=theme["inactive_btn_bg"],
        fg=theme["inactive_btn_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._reset_btn.pack(side=tk.LEFT)
    bind_hover(self._reset_btn)

    self._lock_all_btn = tk.Button(
        frame,
        text="Lock All to Defaults",
        command=self._lock_all_defaults,
        width=16,
        bg=theme["inactive_btn_bg"],
        fg=theme["inactive_btn_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._lock_all_btn.pack(side=tk.LEFT, padx=(8, 0))
    bind_hover(self._lock_all_btn)


def _apply_values(self, values):
    self._syncing = True
    for key, var in self._all_vars().items():
        if key in values:
            var.set(values[key])
    locks = self._active_locks()
    for key, default_var in self._default_vars.items():
        default_var.set(bool(locks.get(key, False)))
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
    if not self._mode_store_enabled:
        return
    mode = self._current_mode()
    for key, default_var in self._default_vars.items():
        if self._mode_key_enabled(key):
            default_var.set(True)
            self._mode_store.set_lock(self.config, mode, key, True)
    self._mode_store.reset_mode_to_defaults(self.config, mode)
    self._sync_sliders_to_config()
    self._set_mode_status("[OK] Locked active mode to defaults")


def apply_theme(self, theme):
    self.configure(bg=theme["panel_bg"])
    if hasattr(self, "_editor_split"):
        self._editor_split.configure(bg=theme["panel_bg"])
    if hasattr(self, "_retrieval_column"):
        self._retrieval_column.configure(bg=theme["panel_bg"])
    if hasattr(self, "_query_column"):
        self._query_column.configure(bg=theme["panel_bg"])
    for frame_attr in ("_retrieval_frame", "_llm_frame", "_profile_frame"):
        frame = getattr(self, frame_attr, None)
        if frame:
            frame.configure(bg=theme["panel_bg"], fg=theme["accent"])
            for child in frame.winfo_children():
                _theme_widget(child, theme)
    if hasattr(self, "_reset_frame"):
        self._reset_frame.configure(bg=theme["panel_bg"])
        self._save_mode_defaults_btn.configure(bg=theme["accent"], fg=theme["accent_fg"])
        self._reset_btn.configure(bg=theme["inactive_btn_bg"], fg=theme["inactive_btn_fg"])
        self._lock_all_btn.configure(bg=theme["inactive_btn_bg"], fg=theme["inactive_btn_fg"])
    if hasattr(self, "_mode_row"):
        self._mode_row.configure(bg=theme["panel_bg"])
        self._mode_banner.configure(bg=theme["panel_bg"], fg=theme["accent"])
        self._mode_status.configure(bg=theme["panel_bg"], fg=theme["gray"])


def bind_tuning_tab_runtime_methods(tab_cls) -> None:
    tab_cls._capture_values = _capture_values
    tab_cls.get_profile_options = get_profile_options
    tab_cls._current_mode = _current_mode
    tab_cls._runtime_mode = _runtime_mode
    tab_cls._build_mode_banner = _build_mode_banner
    tab_cls._build_editor_columns = _build_editor_columns
    tab_cls._refresh_mode_banner = _refresh_mode_banner
    tab_cls._set_mode_status = _set_mode_status
    tab_cls._on_editor_mode_change = _on_editor_mode_change
    tab_cls._active_locks = _active_locks
    tab_cls._default_value = _default_value
    tab_cls._display_values_from_config = _display_values_from_config
    tab_cls._current_seed_value = _current_seed_value
    tab_cls._seed_value_or_current = _seed_value_or_current
    tab_cls._var_value = _var_value
    tab_cls._mode_key_enabled = _mode_key_enabled
    tab_cls._apply_mode_widget_states = _apply_mode_widget_states
    tab_cls._write_active_vars_to_config = _write_active_vars_to_config
    tab_cls._persist_active_mode_values = _persist_active_mode_values
    tab_cls._build_slider_row = _build_slider_row
    tab_cls._build_entry_row = _build_entry_row
    tab_cls._build_check_row = _build_check_row
    tab_cls._on_default_toggle = _on_default_toggle
    tab_cls._build_retrieval_section = _build_retrieval_section
    tab_cls._on_retrieval_change = _on_retrieval_change
    tab_cls._build_llm_section = _build_llm_section
    tab_cls._on_llm_change = _on_llm_change
    tab_cls._get_current_model = _get_current_model
    tab_cls._update_latency_warning = _update_latency_warning
    tab_cls._check_dangerous_change = _check_dangerous_change
    tab_cls._build_profile_section = _build_profile_section
    tab_cls._detect_current_profile = _detect_current_profile
    tab_cls._refresh_profile_info = _refresh_profile_info
    tab_cls._refresh_model_table = _refresh_model_table
    tab_cls._on_profile_change = _on_profile_change
    tab_cls._do_profile_switch = _do_profile_switch
    tab_cls._profile_switch_done = _profile_switch_done
    tab_cls._profile_switch_failed = _profile_switch_failed
    tab_cls._sync_sliders_to_config = _sync_sliders_to_config
    tab_cls._all_vars = _all_vars
    tab_cls._var_matches_safe = _var_matches_safe
    tab_cls._build_reset_button = _build_reset_button
    tab_cls._apply_values = _apply_values
    tab_cls._on_reset = _on_reset
    tab_cls._on_save_mode_defaults = _on_save_mode_defaults
    tab_cls._lock_all_defaults = _lock_all_defaults
    tab_cls.apply_theme = apply_theme


__all__ = [
    "SAFE_DEFAULTS",
    "_detect_hardware_class",
    "bind_tuning_tab_runtime_methods",
]
