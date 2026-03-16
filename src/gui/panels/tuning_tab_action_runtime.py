# TuningTab runtime: change handlers, profile switching, latency warnings, resets.
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox

from src.core.query_mode import apply_query_mode_to_runtime
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.settings_view import (
    _build_ranking_text,
    _detect_profile_name,
)
from src.gui.panels.query_constants import (
    GROUNDING_BIAS_HINTS,
    OPEN_KNOWLEDGE_HINTS,
)
from src.gui.theme import current_theme

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Retrieval change handler
# ------------------------------------------------------------------


def _on_retrieval_change(self):
    self._write_active_vars_to_config()
    self._sync_retrieval_advanced_visibility()
    if not self._syncing:
        self._persist_active_mode_values()
    self._update_latency_warning()
    self._check_dangerous_change()


# ------------------------------------------------------------------
# Query policy helpers and handler
# ------------------------------------------------------------------


def _update_query_policy_hints(self):
    if hasattr(self, "_grounding_bias_hint_var") and hasattr(self, "grounding_bias_var"):
        try:
            bias = int(self.grounding_bias_var.get())
        except (tk.TclError, TypeError, ValueError):
            bias = int(self._default_value("grounding_bias") or 0)
        bias = max(0, min(10, bias))
        self._grounding_bias_hint_var.set(
            GROUNDING_BIAS_HINTS.get(bias, "Grounding bias updated")
        )
    if hasattr(self, "_open_knowledge_hint_var") and hasattr(self, "allow_open_knowledge_var"):
        enabled = bool(self.allow_open_knowledge_var.get())
        self._open_knowledge_hint_var.set(
            OPEN_KNOWLEDGE_HINTS.get(enabled, "Open knowledge updated")
        )


def _iter_live_query_engines(self):
    app = getattr(self, "_app", None)
    if app is None:
        return []

    seen = set()
    engines = []
    candidates = [
        getattr(app, "query_engine", None),
        getattr(getattr(app, "query_panel", None), "query_engine", None),
    ]
    for engine in candidates:
        if engine is None:
            continue
        engine_id = id(engine)
        if engine_id in seen:
            continue
        seen.add(engine_id)
        engines.append(engine)
    return engines


def _apply_query_policy_live(self):
    if self._current_mode() != self._runtime_mode():
        return

    engines = _iter_live_query_engines(self)
    if not engines:
        try:
            apply_query_mode_to_runtime(self.config)
        except Exception:
            logger.debug("Query policy config normalization failed", exc_info=True)
        return

    for engine in engines:
        try:
            apply_query_mode_to_runtime(
                self.config,
                engine,
                sync_guard_policy=True,
            )
        except Exception:
            logger.debug("Query policy live-update failed", exc_info=True)


def _on_query_policy_change(self):
    self._write_active_vars_to_config()
    self._apply_query_policy_live()
    if not self._syncing:
        self._persist_active_mode_values()
    self._update_query_policy_hints()
    self._check_dangerous_change()


# ------------------------------------------------------------------
# LLM change handler
# ------------------------------------------------------------------


def _on_llm_change(self):
    self._write_active_vars_to_config()
    self._sync_generation_advanced_visibility()
    if not self._syncing:
        self._persist_active_mode_values()
    self._update_latency_warning()
    self._check_dangerous_change()


# ------------------------------------------------------------------
# Latency estimation & warnings
# ------------------------------------------------------------------


def _get_current_model(self):
    if self._current_mode() == "online":
        api = getattr(self.config, "api", None)
        return getattr(api, "model", "") or getattr(api, "deployment", "") or "gpt-4o"
    ollama = getattr(self.config, "ollama", None)
    return getattr(ollama, "model", "phi4-mini") if ollama else "phi4-mini"


def _update_latency_warning(self):
    if not hasattr(self, "_latency_warn_label"):
        return

    from src.gui.panels.tuning_tab_runtime import (
        _estimate_query_seconds,
        _vram_overflows,
    )

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


# ------------------------------------------------------------------
# Dangerous-change guard
# ------------------------------------------------------------------


def _check_dangerous_change(self):
    if not self._mode_store_enabled:
        return

    from src.gui.panels.tuning_tab_runtime import (
        _MODEL_SPECS,
        _estimate_query_seconds,
        _vram_overflows,
    )

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


# ------------------------------------------------------------------
# Profile switching
# ------------------------------------------------------------------


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
    from src.gui.panels.tuning_tab_runtime import _run_profile_switch
    _run_profile_switch(self, profile)


def _profile_switch_done(self, new_config, profile, embedding_changed, old_embed_model, new_embed_model):
    from src.gui.panels.tuning_tab_runtime import SAFE_DEFAULTS

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


# ------------------------------------------------------------------
# Reset & save-defaults
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Bind
# ------------------------------------------------------------------


def bind_tuning_tab_action_runtime_methods(tab_cls):
    """Bind change-handler, profile, latency, and reset methods to TuningTab."""
    tab_cls._on_retrieval_change = _on_retrieval_change
    tab_cls._update_query_policy_hints = _update_query_policy_hints
    tab_cls._iter_live_query_engines = _iter_live_query_engines
    tab_cls._apply_query_policy_live = _apply_query_policy_live
    tab_cls._on_query_policy_change = _on_query_policy_change
    tab_cls._on_llm_change = _on_llm_change
    tab_cls._get_current_model = _get_current_model
    tab_cls._update_latency_warning = _update_latency_warning
    tab_cls._check_dangerous_change = _check_dangerous_change
    tab_cls._detect_current_profile = _detect_current_profile
    tab_cls._refresh_profile_info = _refresh_profile_info
    tab_cls._refresh_model_table = _refresh_model_table
    tab_cls._on_profile_change = _on_profile_change
    tab_cls._do_profile_switch = _do_profile_switch
    tab_cls._profile_switch_done = _profile_switch_done
    tab_cls._profile_switch_failed = _profile_switch_failed
    tab_cls._on_reset = _on_reset
    tab_cls._on_save_mode_defaults = _on_save_mode_defaults
    tab_cls._lock_all_defaults = _lock_all_defaults
