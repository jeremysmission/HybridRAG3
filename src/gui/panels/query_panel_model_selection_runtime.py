# QueryPanel runtime: model selection and primary/fallback control.
from __future__ import annotations

import logging
import threading
import tkinter as tk

from scripts._model_meta import (
    USE_CASES, select_best_model, RECOMMENDED_OFFLINE, WORK_ONLY_MODELS,
    use_case_score, get_offline_models_with_specs,
)
from src.core.llm_router import get_available_deployments
from src.core.model_identity import canonicalize_model_name
from src.core.query_mode import apply_query_mode_to_config, apply_query_mode_to_engine
from src.gui.helpers.mode_tuning import update_mode_setting
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.query_constants import (
    PROFILE_DIAL_DEFAULTS,
    GROUNDING_BIAS_HINTS,
    OPEN_KNOWLEDGE_HINTS,
)

logger = logging.getLogger(__name__)

def _init_model_list(self):
    """Fetch installed Ollama models in background, then apply defaults."""
    threading.Thread(
        target=self._fetch_installed_models, daemon=True,
    ).start()

def _fetch_installed_models(self):
    """Background: get installed Ollama model names (excludes embedders)."""
    try:
        from scripts._model_meta import get_offline_models_with_specs
        models = get_offline_models_with_specs()
        names = []
        for m in models:
            name = m["name"]
            # Skip embedding-only models
            skip = False
            for pat in self._EMBED_MODELS:
                if pat in name.lower():
                    skip = True
                    break
            if not skip:
                names.append(name)
        safe_after(self, 0, self._apply_model_list, names)
    except Exception as e:
        logger.debug("Model list fetch failed: %s", e)
        safe_after(self, 0, self._on_use_case_change)

def _apply_model_list(self, names):
    """Set combobox values and trigger initial model selection."""
    self._installed_models = names
    self._set_model_combo_for_mode()

    # If config already has a model that isn't the recommendation
    # default, pre-select it (user's persisted choice).
    # Names are already canonical (no ':latest' suffixes).
    cfg_model = getattr(
        getattr(self.config, "ollama", None), "model", ""
    ) or ""
    uc_key = self._uc_keys[0]
    rec_primary = RECOMMENDED_OFFLINE.get(uc_key, {}).get("primary", "")
    # Normalize before comparing so aliases (phi4:14b vs phi4:14b-q4_K_M)
    # do not force an unnecessary fallback warning.
    cfg_model_c = canonicalize_model_name(cfg_model)
    rec_primary_c = canonicalize_model_name(rec_primary)
    names_by_canon = {
        canonicalize_model_name(n): n for n in names
    }
    if cfg_model_c and cfg_model_c != rec_primary_c and cfg_model_c in names_by_canon:
        self.model_var.set(names_by_canon[cfg_model_c])
        self._model_auto = False

    self._on_use_case_change()

def _set_model_combo_for_mode(self):
    """Keep model combobox semantics aligned with offline/online mode."""
    mode = getattr(self.config, "mode", "offline")
    if mode == "online":
        # Online model comes from API deployment selection, not Ollama list.
        deployment = self._get_configured_online_deployment()
        if not deployment:
            deployment = "Auto (online)"
        label = f"Online: {deployment}"
        if self._online_models:
            vals = [f"Online: {m}" for m in self._online_models]
            if label not in vals:
                vals.insert(0, label)
            self.model_combo["values"] = vals
            self.model_var.set(label)
            self.model_combo.config(state="readonly")
        else:
            self.model_combo["values"] = [label]
            self.model_var.set(label)
            self.model_combo.config(state="readonly")
        return

    values = ["Auto"] + self._installed_models
    self.model_combo["values"] = values
    self.model_combo.config(state="readonly")
    if self._model_auto or self.model_var.get() not in values:
        self.model_var.set("Auto")

def _get_configured_online_deployment(self):
    """Best-effort deployment from live config, then credential manager."""
    deployment = (
        getattr(getattr(self.config, "api", None), "deployment", "") or ""
    ).strip()
    if deployment:
        return deployment
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(use_cache=False)
        deployment = (getattr(creds, "deployment", "") or "").strip()
        return deployment
    except Exception as e:
        logger.debug("Online deployment lookup failed: %s", e)
        return ""

def _on_model_select(self, event=None):
    """Handle user selecting a model from the dropdown."""
    mode = getattr(self.config, "mode", "offline")
    if mode == "online":
        chosen = self.model_var.get().replace("Online:", "").strip()
        if not chosen or chosen.lower().startswith("auto"):
            return
        if hasattr(self.config, "api"):
            self.config.api.deployment = chosen
            self.config.api.model = chosen
        # Apply to live router if already initialized
        try:
            if self.query_engine and hasattr(self.query_engine, "llm_router"):
                api_router = getattr(self.query_engine.llm_router, "api", None)
                if api_router is not None:
                    api_router.deployment = chosen
                    if hasattr(api_router.config, "api"):
                        api_router.config.api.model = chosen
        except Exception as e:
            logger.debug("Online deployment apply failed: %s", e)
        self.model_info_var.set("{} (manual)".format(chosen))
        return

    chosen = self.model_var.get()
    if chosen == "Auto":
        self._model_auto = True
        self._on_use_case_change()
    else:
        # Manual selection -- lock this model
        self._model_auto = False
        if hasattr(self.config, "ollama"):
            self.config.ollama.model = canonicalize_model_name(chosen)
        self._update_model_info(chosen)

def _update_model_info(self, model_name):
    """Update the score/info label for the given model."""
    if self._auto_fallback_note:
        self.model_info_var.set(self._auto_fallback_note)
        return

    idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
    uc_key = self._uc_keys[idx]
    mode = getattr(self.config, "mode", "offline")
    mode_label = "Offline Mode" if mode == "offline" else "Online Mode"
    meta = WORK_ONLY_MODELS.get(model_name, {})
    if meta:
        score = use_case_score(
            meta.get("tier_eng", 30), meta.get("tier_gen", 30), uc_key,
        )
        if self._model_auto:
            self.model_info_var.set(
                "{} | Score: {} | {}".format(model_name, score, mode_label)
            )
        else:
            self.model_info_var.set(
                "Score: {} | {}".format(score, mode_label)
            )
    else:
        self.model_info_var.set(mode_label)

def _set_auto_note(self, selected, primary="", fallback=False, detail=""):
    """Set explicit auto-mode primary/secondary status text."""
    selected = (selected or "").strip() or "(none)"
    primary = (primary or "").strip()
    self._auto_selected_model = selected
    self._auto_primary_model = primary
    self._auto_fallback_active = bool(fallback)
    if fallback:
        msg = "Auto Mode - Primary unavailable, Secondary selected: {}".format(
            selected
        )
    else:
        if primary:
            msg = "Auto Mode - Primary selected: {}".format(selected)
        else:
            msg = "Auto Mode - Selected: {}".format(selected)
    if detail:
        msg = "{} ({})".format(msg, detail)
    self._auto_fallback_note = msg
    self.model_info_var.set(msg)
    if fallback:
        self.primary_alert_var.set(
            "Note: Primary AI Model Unavailable - Secondary model in use ({})".format(
                selected
            )
        )
    else:
        self.primary_alert_var.set("")
    self._update_primary_controls()

def _set_online_discovery_note(self, selected):
    """Set a neutral online note when deployment discovery is unavailable."""
    selected = (selected or "").strip() or "(none)"
    self._auto_selected_model = selected
    self._auto_primary_model = ""
    self._auto_fallback_active = False
    msg = "Auto Mode - Discovery unavailable, using configured model: {} (online)".format(
        selected
    )
    self._auto_fallback_note = msg
    self.model_info_var.set(msg)
    self.primary_alert_var.set("")
    self._update_primary_controls()

def _update_primary_controls(self):
    """Enable recovery controls only when fallback mode is active."""
    if self._auto_fallback_active:
        self.primary_check_btn.config(state=tk.NORMAL)
    else:
        self.primary_check_btn.config(state=tk.DISABLED)
        self.primary_check_var.set("")

def _current_use_case_key(self):
    """Plain-English: Returns the active use-case key that drives query routing and presets."""
    idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
    return self._uc_keys[idx]

def _on_check_primary(self):
    """Probe for primary availability and switch if recovered."""
    if not self._auto_fallback_active:
        return
    self.primary_check_btn.config(state=tk.DISABLED)
    self.primary_check_var.set("Checking...")
    threading.Thread(target=self._check_primary_worker, daemon=True).start()

def _on_grounding_bias_change(self, _value=None):
    """Update hint + live guard tuning when operator adjusts bias."""
    bias = int(self._grounding_bias_var.get())
    update_mode_setting(self.config, getattr(self.config, "mode", "offline"), "grounding_bias", bias)
    self._grounding_bias_hint.set(
        GROUNDING_BIAS_HINTS.get(bias, "Grounding bias updated")
    )
    self._apply_grounding_bias_live(bias)

def _on_open_knowledge_toggle(self):
    """Update hint + live fallback mode when operator toggles open knowledge."""
    enabled = bool(self._open_knowledge_var.get())
    update_mode_setting(
        self.config,
        getattr(self.config, "mode", "offline"),
        "allow_open_knowledge",
        enabled,
    )
    self._open_knowledge_hint.set(
        OPEN_KNOWLEDGE_HINTS.get(enabled, "Open knowledge updated")
    )
    self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

def _apply_grounding_bias_live(self, bias: int):
    """
    Map 1..10 slider into live guard settings.
    Lower bias => more synthesis freedom.
    Higher bias => stricter evidence requirements.
    """
    b = max(0, min(10, int(bias)))
    allow_open_knowledge = bool(self._open_knowledge_var.get())
    settings = None
    try:
        query_cfg = getattr(self.config, "query", None)
        if query_cfg is None:
            from types import SimpleNamespace

            query_cfg = SimpleNamespace()
            setattr(self.config, "query", query_cfg)
        query_cfg.grounding_bias = int(b)
        query_cfg.allow_open_knowledge = allow_open_knowledge
        settings = apply_query_mode_to_config(self.config)
    except Exception:
        logger.debug("Grounding bias config update failed", exc_info=True)

    # Live engine update (works without restart)
    qe = self.query_engine
    if qe is not None:
        try:
            if hasattr(qe, "config"):
                apply_query_mode_to_engine(qe, sync_guard_policy=True)
            elif settings is not None:
                setattr(qe, "allow_open_knowledge", settings["allow_open_knowledge"])
                if hasattr(qe, "guard_enabled"):
                    qe.guard_enabled = settings["guard_enabled"]
                if hasattr(qe, "guard_threshold"):
                    qe.guard_threshold = settings["guard_threshold"]
                if hasattr(qe, "guard_min_chunks"):
                    qe.guard_min_chunks = settings["guard_min_chunks"]
                if hasattr(qe, "guard_min_score"):
                    qe.guard_min_score = settings["guard_min_score"]
                if hasattr(qe, "guard_action"):
                    qe.guard_action = settings["guard_action"]
        except Exception:
            logger.debug("Grounding bias live-update failed", exc_info=True)

def _check_primary_worker(self):
    """Background primary availability check."""
    mode = getattr(self.config, "mode", "offline")
    uc_key = self._current_use_case_key()
    if mode == "offline":
        try:
            from scripts._model_meta import get_offline_models_with_specs
            names = [m["name"] for m in get_offline_models_with_specs()]
        except Exception:
            names = list(self._installed_models)
        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        primary = (rec.get("primary", "") or "").strip()
        if primary and primary in names and self._model_auto:
            safe_after(self, 0, self._switch_to_primary_offline, primary)
            return
        safe_after(self, 0, self._check_primary_done, False, "Primary still unavailable")
        return

    # Online mode: recompute best from live deployments and switch if better.
    try:
        deployments = get_available_deployments()
        best = select_best_model(uc_key, deployments)
        current = (self._auto_selected_model or "").strip()
        if best and self._model_auto and best != current:
            safe_after(self, 0, self._switch_to_primary_online, best, deployments)
            return
        if best and best == current:
            safe_after(self, 0, self._check_primary_done, True, "Primary already active")
        else:
            safe_after(self, 0, self._check_primary_done, False, "Primary still unavailable")
    except Exception:
        safe_after(self, 0, self._check_primary_done, False, "Primary check failed")

def _switch_to_primary_offline(self, primary):
    """Plain-English: Switches query routing back to the primary offline model path."""
    self._installed_models = list(self._installed_models or [])
    if primary not in self._installed_models:
        self._installed_models.append(primary)
    if hasattr(self.config, "ollama"):
        self.config.ollama.model = canonicalize_model_name(primary)
    self._set_auto_note(primary, primary, False, "offline recovered")
    self._set_model_combo_for_mode()
    self._check_primary_done(True, "Primary restored and selected")

def _switch_to_primary_online(self, primary, deployments):
    """Plain-English: Switches query routing back to the primary online model path."""
    self._online_models = list(deployments or [primary])
    self.model_var.set(f"Online: {primary}")
    self._apply_online_selection(primary, False, "online recovered")
    self._set_model_combo_for_mode()
    self._set_auto_note(primary, primary, False, "online recovered")
    self._check_primary_done(True, "Primary restored and selected")

def _check_primary_done(self, ok, message):
    """Plain-English: Checks whether the primary response path completed before triggering fallback behavior."""
    t = current_theme()
    self.primary_check_var.set(message)
    self.primary_check_label.config(fg=t["green"] if ok else t["orange"])
    self._update_primary_controls()
def bind_query_panel_model_selection_runtime_methods(cls):
    """Bind model-selection runtime methods to QueryPanel."""
    cls._init_model_list = _init_model_list
    cls._fetch_installed_models = _fetch_installed_models
    cls._apply_model_list = _apply_model_list
    cls._set_model_combo_for_mode = _set_model_combo_for_mode
    cls._get_configured_online_deployment = _get_configured_online_deployment
    cls._on_model_select = _on_model_select
    cls._update_model_info = _update_model_info
    cls._set_auto_note = _set_auto_note
    cls._set_online_discovery_note = _set_online_discovery_note
    cls._update_primary_controls = _update_primary_controls
    cls._current_use_case_key = _current_use_case_key
    cls._on_check_primary = _on_check_primary
    cls._on_grounding_bias_change = _on_grounding_bias_change
    cls._on_open_knowledge_toggle = _on_open_knowledge_toggle
    cls._apply_grounding_bias_live = _apply_grounding_bias_live
    cls._check_primary_worker = _check_primary_worker
    cls._switch_to_primary_offline = _switch_to_primary_offline
    cls._switch_to_primary_online = _switch_to_primary_online
    cls._check_primary_done = _check_primary_done
