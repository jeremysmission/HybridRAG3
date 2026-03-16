# TuningTab runtime: mode/slider/config state logic.
from __future__ import annotations

import tkinter as tk

from src.core.mode_config import MODE_TUNED_DEFAULTS, normalize_mode
from src.gui.panels.query_constants import (
    GROUNDING_BIAS_HINTS,
    OPEN_KNOWLEDGE_HINTS,
)
from src.gui.theme import FONT_SMALL


# ------------------------------------------------------------------
# Module-level helper (not bound to a class)
# ------------------------------------------------------------------


def _set_frame_visible(frame, visible: bool):
    mapped = bool(frame.winfo_manager())
    if visible and not mapped:
        frame.pack(fill=tk.X, pady=(4, 0))
    elif not visible and mapped:
        frame.pack_forget()


# ------------------------------------------------------------------
# Mode & value accessors
# ------------------------------------------------------------------


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


def _refresh_mode_banner(self):
    mode = self._current_mode()
    runtime_mode = self._runtime_mode()
    self._mode_banner_var.set(
        "Editing {} defaults in Admin  |  Runtime mode: {}.".format(mode.upper(), runtime_mode.upper())
    )
    if hasattr(self, "_query_policy_frame"):
        self._query_policy_frame.config(text="Query Policy ({})".format(mode.capitalize()))
    if hasattr(self, "_generation_frame"):
        self._generation_frame.config(text="Generation ({})".format(mode.capitalize()))
    if hasattr(self, "_query_policy_note"):
        self._query_policy_note.config(
            text=(
                "Grounding strictness and open-knowledge fallback are saved per mode "
                "under config.yaml and apply live when {} is the runtime mode."
            ).format(mode)
        )
    if hasattr(self, "_llm_mode_note"):
        if mode == "online":
            self._llm_mode_note.config(
                text=(
                    "Online generation uses api.context_window + max_tokens. "
                    "Provider-only controls stay disabled when they do not apply."
                )
            )
        else:
            self._llm_mode_note.config(
                text=(
                    "Offline generation uses ollama.context_window + num_predict. "
                    "Common controls stay mirrored; online-only penalties stay disabled."
                )
            )
    self._update_query_policy_hints()


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
    from src.gui.panels.tuning_tab_runtime import _mode_llm_values_from_config
    return _mode_llm_values_from_config(self.config, self._current_mode())


def _current_seed_value(self):
    mode = self._current_mode()
    if mode == "online":
        api = getattr(self.config, "api", None)
        return int(getattr(api, "seed", 0) or 0) if api is not None else 0
    ollama = getattr(self.config, "ollama", None)
    return int(getattr(ollama, "seed", 0) or 0) if ollama is not None else 0


def _seed_value_or_current(self):
    current_value = self._current_seed_value()
    var_value = None
    try:
        var_value = int(self.seed_var.get())
    except (AttributeError, tk.TclError, TypeError, ValueError):
        pass
    seed_entry = getattr(self, "_scales", {}).get("seed")
    if seed_entry is not None and hasattr(seed_entry, "get"):
        try:
            raw = str(seed_entry.get()).strip()
        except tk.TclError:
            raw = ""
        if raw:
            try:
                parsed = int(raw)
            except ValueError:
                return current_value
            # Tk entry text can lag behind a programmatic IntVar update during
            # larger suite runs. If the entry still shows the last committed
            # seed but the bound variable holds a newer valid value, trust the
            # newer value instead of snapping back to the stale seed.
            if var_value is not None and var_value != current_value and parsed == current_value:
                return var_value
            return parsed
        if var_value is not None and var_value != current_value:
            return var_value
        return current_value
    if var_value is not None:
        return var_value
    return current_value


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
    self._sync_retrieval_advanced_visibility()
    self._sync_generation_advanced_visibility()


def _set_row_visible(self, key, visible: bool):
    row = self._row_frames.get(key)
    if row is None:
        return
    mapped = bool(row.winfo_manager())
    if visible and not mapped:
        row.pack(fill=tk.X, pady=3)
    elif not visible and mapped:
        row.pack_forget()


def _advanced_retrieval_active(self) -> bool:
    return bool(self.reranker_var.get()) or int(self.reranker_topn_var.get()) != int(
        self._default_value("reranker_top_n") or MODE_TUNED_DEFAULTS[self._current_mode()]["reranker_top_n"]
    )


def _advanced_generation_active(self) -> bool:
    if int(self._seed_value_or_current()) > 0:
        return True
    if self._current_mode() == "online":
        return (
            abs(float(self.presence_penalty_var.get())) > 1e-9
            or abs(float(self.frequency_penalty_var.get())) > 1e-9
        )
    return False


def _sync_retrieval_advanced_visibility(self):
    frame = getattr(self, "_retrieval_advanced_frame", None)
    if frame is None:
        return
    show = bool(self._show_retrieval_advanced_var.get()) or self._advanced_retrieval_active()
    _set_frame_visible(frame, show)

    reranker_enabled = bool(self.reranker_var.get())
    topn_widget = self._scales.get("reranker_top_n")
    topn_enabled = self._mode_key_enabled("reranker_top_n") and reranker_enabled and not bool(
        self._active_locks().get("reranker_top_n", False)
    )
    if topn_widget is not None:
        topn_widget.config(state=(tk.NORMAL if topn_enabled else tk.DISABLED))


def _sync_generation_advanced_visibility(self):
    frame = getattr(self, "_generation_advanced_frame", None)
    if frame is None:
        return
    show = bool(self._show_generation_advanced_var.get()) or self._advanced_generation_active()
    _set_frame_visible(frame, show)
    online = self._current_mode() == "online"
    self._set_row_visible("seed", show)
    self._set_row_visible("presence_penalty", show and online)
    self._set_row_visible("frequency_penalty", show and online)


# ------------------------------------------------------------------
# Config write-back & persistence
# ------------------------------------------------------------------


def _write_active_vars_to_config(self):
    if self._current_mode() != self._runtime_mode():
        return
    retrieval = getattr(self.config, "retrieval", None)
    api = getattr(self.config, "api", None)
    ollama = getattr(self.config, "ollama", None)
    query = getattr(self.config, "query", None)
    mode = self._current_mode()
    if retrieval:
        retrieval.top_k = self.topk_var.get()
        retrieval.min_score = self.minscore_var.get()
        retrieval.hybrid_search = self.hybrid_var.get()
        retrieval.reranker_enabled = bool(self.reranker_var.get())
        retrieval.reranker_top_n = int(self.reranker_topn_var.get())
    if query:
        query.grounding_bias = int(self.grounding_bias_var.get())
        query.allow_open_knowledge = bool(self.allow_open_knowledge_var.get())
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
        "reranker_enabled": bool(self.reranker_var.get()),
        "reranker_top_n": int(self.reranker_topn_var.get()),
        "context_window": self.ctx_window_var.get(),
        "temperature": self.temp_var.get(),
        "top_p": self.top_p_var.get(),
        "seed": self._seed_value_or_current(),
        "timeout_seconds": self.timeout_var.get(),
        "grounding_bias": int(self.grounding_bias_var.get()),
        "allow_open_knowledge": bool(self.allow_open_knowledge_var.get()),
    }
    if mode == "online":
        values["max_tokens"] = self.maxtokens_var.get()
        values["presence_penalty"] = self.presence_penalty_var.get()
        values["frequency_penalty"] = self.frequency_penalty_var.get()
    else:
        values["num_predict"] = self.num_predict_var.get()
    for key, value in values.items():
        self._mode_store.update_value(self.config, mode, key, value)


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


# ------------------------------------------------------------------
# Slider sync, all-vars, value application, and reset helpers
# ------------------------------------------------------------------


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
        "reranker_enabled": self.reranker_var,
        "reranker_top_n": self.reranker_topn_var,
        "grounding_bias": self.grounding_bias_var,
        "allow_open_knowledge": self.allow_open_knowledge_var,
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
    self._update_query_policy_hints()
    self._update_latency_warning()


# ------------------------------------------------------------------
# Bind
# ------------------------------------------------------------------


def bind_tuning_tab_logic_runtime_methods(tab_cls):
    """Bind mode/slider/config logic methods to TuningTab."""
    tab_cls._capture_values = _capture_values
    tab_cls.get_profile_options = get_profile_options
    tab_cls._current_mode = _current_mode
    tab_cls._runtime_mode = _runtime_mode
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
    tab_cls._set_row_visible = _set_row_visible
    tab_cls._advanced_retrieval_active = _advanced_retrieval_active
    tab_cls._advanced_generation_active = _advanced_generation_active
    tab_cls._sync_retrieval_advanced_visibility = _sync_retrieval_advanced_visibility
    tab_cls._sync_generation_advanced_visibility = _sync_generation_advanced_visibility
    tab_cls._write_active_vars_to_config = _write_active_vars_to_config
    tab_cls._persist_active_mode_values = _persist_active_mode_values
    tab_cls._on_default_toggle = _on_default_toggle
    tab_cls._sync_sliders_to_config = _sync_sliders_to_config
    tab_cls._all_vars = _all_vars
    tab_cls._var_matches_safe = _var_matches_safe
    tab_cls._apply_values = _apply_values
