# QueryPanel runtime: use-case tuning and online model resolution.
from __future__ import annotations

import logging
import threading

from scripts._model_meta import (
    USE_CASES,
    RECOMMENDED_OFFLINE,
    WORK_ONLY_MODELS,
    select_best_model,
    use_case_score,
)
from src.core.llm_router import get_available_deployments
from src.core.model_identity import canonicalize_model_name
from src.gui.helpers.mode_tuning import mode_setting_locked, update_mode_setting
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.query_constants import (
    ONLINE_USE_CASE_TUNING,
    PROFILE_DIAL_DEFAULTS,
    GROUNDING_BIAS_HINTS,
    OPEN_KNOWLEDGE_HINTS,
    PROFILE_TASK_PLAYBOOK,
)
logger = logging.getLogger(__name__)

def _apply_use_case_tuning(self, uc_key: str, mode: str) -> None:
    """
    Apply profession-specific tuning bundle, not just model selection.

    Offline: apply RECOMMENDED_OFFLINE tuning knobs.
    Online:  apply ONLINE_USE_CASE_TUNING knobs.
    """
    if not self.config:
        return

    self._apply_profile_dial_defaults(uc_key, mode)

    if mode == "offline":
        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        if not rec:
            return
        if hasattr(self.config, "ollama"):
            if "context" in rec:
                # Keep operator/admin-selected context window unchanged.
                # Use-case switches should not mutate this runtime limit.
                # Guard only against missing/invalid values.
                cur_ctx = int(
                    getattr(self.config.ollama, "context_window", 4096) or 4096
                )
                if cur_ctx < 1024:
                    self.config.ollama.context_window = int(
                        rec.get("context", 4096) or 4096
                    )
            if "temperature" in rec:
                if not mode_setting_locked(self.config, "offline", "temperature"):
                    self.config.ollama.temperature = rec["temperature"]
                    update_mode_setting(self.config, "offline", "temperature", rec["temperature"])
        if hasattr(self.config, "retrieval"):
            if "top_k" in rec:
                if not mode_setting_locked(self.config, "offline", "top_k"):
                    self.config.retrieval.top_k = rec["top_k"]
                    update_mode_setting(self.config, "offline", "top_k", rec["top_k"])
        return

    # Online tuning bundle
    rec = ONLINE_USE_CASE_TUNING.get(uc_key, {})
    if not rec:
        return
    if hasattr(self.config, "api"):
        if "temperature" in rec:
            if not mode_setting_locked(self.config, "online", "temperature"):
                self.config.api.temperature = rec["temperature"]
                update_mode_setting(self.config, "online", "temperature", rec["temperature"])
        if "max_tokens" in rec:
            if not mode_setting_locked(self.config, "online", "max_tokens"):
                self.config.api.max_tokens = rec["max_tokens"]
                update_mode_setting(self.config, "online", "max_tokens", rec["max_tokens"])
        if "timeout_seconds" in rec:
            if not mode_setting_locked(self.config, "online", "timeout_seconds"):
                self.config.api.timeout_seconds = rec["timeout_seconds"]
                update_mode_setting(self.config, "online", "timeout_seconds", rec["timeout_seconds"])
    if hasattr(self.config, "retrieval"):
        if "top_k" in rec:
            if not mode_setting_locked(self.config, "online", "top_k"):
                self.config.retrieval.top_k = rec["top_k"]
                update_mode_setting(self.config, "online", "top_k", rec["top_k"])
        if "min_score" in rec:
            if not mode_setting_locked(self.config, "online", "min_score"):
                self.config.retrieval.min_score = rec["min_score"]
                update_mode_setting(self.config, "online", "min_score", rec["min_score"])

def _apply_profile_dial_defaults(self, uc_key: str, mode: str) -> None:
    """Apply safe per-profile defaults for grounding and fallback controls."""
    mode_key = "online" if str(mode).lower() == "online" else "offline"
    rec = PROFILE_DIAL_DEFAULTS.get(mode_key, {}).get(
        uc_key, {"grounding": 7, "open_knowledge": True}
    )
    try:
        store = getattr(self, "_mode_tuning_store", None)
        grounding = int(rec.get("grounding", 7))
        open_knowledge = bool(rec.get("open_knowledge", True))
        if store is not None:
            grounding = int(
                store.get_active_value(self.config, mode_key, "grounding_bias", grounding)
            )
            open_knowledge = bool(
                store.get_active_value(
                    self.config, mode_key, "allow_open_knowledge", open_knowledge
                )
            )
        self._grounding_bias_var.set(grounding)
        self._open_knowledge_var.set(open_knowledge)
        self._grounding_bias_hint.set(
            GROUNDING_BIAS_HINTS.get(
                int(self._grounding_bias_var.get()), "Grounding updated"
            )
        )
        self._open_knowledge_hint.set(
            OPEN_KNOWLEDGE_HINTS.get(
                bool(self._open_knowledge_var.get()), "Open knowledge updated"
            )
        )
        self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))
    except Exception:
        logger.debug("Use-case tuning apply failed", exc_info=True)

def _on_use_case_change(self, event=None):
    """Update model display when use case changes.

    Offline + Auto: selects per-use-case model from RECOMMENDED_OFFLINE
                    and applies temperature/top_k settings to live config.
    Offline + Manual: keeps user's model, still applies tuning params.
    Online: runs get_available_deployments() in a background thread
            so the GUI never freezes on a network call.
    """
    idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
    uc_key = self._uc_keys[idx]

    mode = getattr(self.config, "mode", "offline")
    self._update_profile_playbook(uc_key)
    self._set_model_combo_for_mode()
    if mode == "offline":
        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        primary = (rec.get("primary", "") or "").strip()

        if self._model_auto:
            # Auto mode: score ALL installed models for this use case
            # and pick the highest-scoring one.  This ensures the best
            # available hardware is used (e.g., phi4:14b-q4_K_M on 48GB GPU).
            best_model = None
            best_score = -1
            for name in self._installed_models:
                meta = WORK_ONLY_MODELS.get(name, {})
                if meta:
                    s = use_case_score(
                        meta.get("tier_eng", 30),
                        meta.get("tier_gen", 30),
                        uc_key,
                    )
                    if s > best_score:
                        best_score = s
                        best_model = name

            if best_model:
                ollama_model = best_model
            elif not self._installed_models:
                # Model list not fetched yet -- use config default
                # (will be re-evaluated when _apply_model_list fires)
                ollama_model = getattr(
                    getattr(self.config, "ollama", None), "model", ""
                ) or rec.get("primary", "phi4:14b-q4_K_M")
            else:
                # Models loaded but none in WORK_ONLY_MODELS -- use
                # recommendation chain: primary > alt > fallback > config
                ollama_model = (
                    rec.get("primary", "")
                    or rec.get("alt", "")
                    or rec.get("fallback", "")
                    or getattr(
                        getattr(self.config, "ollama", None), "model", ""
                    )
                    or "phi4:14b-q4_K_M"
                )

            self.model_var.set("Auto")
            if hasattr(self.config, "ollama"):
                self.config.ollama.model = canonicalize_model_name(ollama_model)
            primary_c = canonicalize_model_name(primary)
            selected_c = canonicalize_model_name(ollama_model)
            installed_c = {
                canonicalize_model_name(m) for m in self._installed_models
            }
            fallback = bool(primary) and primary_c not in installed_c and selected_c != primary_c
            self._set_auto_note(
                ollama_model,
                primary=primary,
                fallback=fallback,
                detail="offline",
            )
        else:
            # Manual mode: keep user's chosen model
            ollama_model = self.model_var.get()
            if hasattr(self.config, "ollama"):
                self.config.ollama.model = canonicalize_model_name(ollama_model)
            self._auto_fallback_note = ""
            self.primary_alert_var.set("")
            self._auto_fallback_active = False
            self._auto_selected_model = ollama_model
            self._auto_primary_model = ""
            self._update_primary_controls()

        self._update_model_info(ollama_model)

        # Apply profession tuning bundle (offline model + retrieval knobs).
        # NOTE: Reranker is intentionally not changed here.
        self._apply_use_case_tuning(uc_key, "offline")

        # Flash confirmation so user knows the change took effect
        self.uc_status_var.set("[OK] Applied")
        self.after(3000, lambda: self.uc_status_var.set(""))
    else:
        # Apply profession tuning bundle for online mode before model resolve.
        self._apply_use_case_tuning(uc_key, "online")

        # Online: resolve deployments off the main thread to avoid
        # freezing the GUI on a 1-3s network call.
        self._auto_fallback_note = ""
        self.primary_alert_var.set("")
        self._auto_fallback_active = False
        self._update_primary_controls()
        self.model_info_var.set("loading...")
        self.uc_status_var.set("[OK] Applied")
        self.after(3000, lambda: self.uc_status_var.set(""))
        threading.Thread(
            target=self._resolve_online_model,
            args=(uc_key,),
            daemon=True,
        ).start()

def _update_profile_playbook(self, uc_key: str) -> None:
    """Show top high-value tasks and recommended dial settings by profile."""
    lines = PROFILE_TASK_PLAYBOOK.get(uc_key, PROFILE_TASK_PLAYBOOK["gen"])
    title = USE_CASES.get(uc_key, {}).get("label", "Profile")
    text = "Top 5 high-value tasks for {}:\n{}".format(
        title, "\n".join(lines)
    )
    self.playbook_label.config(text=text)


def _apply_configured_online_model_fallback(self, missing_message: str) -> None:
    """Use configured online deployment metadata when live discovery is unavailable."""
    configured = self._get_configured_online_deployment()
    if configured:
        self._online_models = [configured]
        safe_after(self, 0, self.model_var.set, f"Online: {configured}")
        safe_after(
            self, 0, self._apply_online_selection, configured, True, "configured fallback",
        )
        safe_after(self, 0, self._set_model_combo_for_mode)
        safe_after(self, 0, self._set_online_discovery_note, configured)
        return
    safe_after(self, 0, self.model_info_var.set, missing_message)


def _resolve_online_model(self, uc_key):
    """Background thread: fetch deployments and update model label."""
    try:
        endpoint = str(getattr(getattr(self.config, "api", None), "endpoint", "") or "").strip()
        if not endpoint:
            _apply_configured_online_model_fallback(self, "(no model)")
            return
        deployments = get_available_deployments()
        best = select_best_model(uc_key, deployments)
        if best:
            self._online_models = list(deployments) if deployments else [best]
            safe_after(self, 0, self.model_var.set, f"Online: {best}")
            safe_after(
                self, 0, self._apply_online_selection, best, False, "online auto",
            )
            safe_after(self, 0, self._set_model_combo_for_mode)
            safe_after(self, 0, self._set_auto_note, best, best, False, "online")
        else:
            _apply_configured_online_model_fallback(self, "(no model)")
    except RuntimeError:
        pass  # Widget destroyed before thread finished -- safe to ignore
    except Exception:
        try:
            _apply_configured_online_model_fallback(self, "(discovery failed)")
        except RuntimeError:
            pass  # Widget destroyed

def _apply_online_selection(self, deployment, is_fallback=False, note=""):
    """Apply selected online deployment to live config/router for consistency."""
    dep = (deployment or "").strip()
    if not dep:
        return
    if hasattr(self.config, "api"):
        self.config.api.deployment = dep
        self.config.api.model = dep
    try:
        if self.query_engine and hasattr(self.query_engine, "llm_router"):
            api_router = getattr(self.query_engine.llm_router, "api", None)
            if api_router is not None:
                api_router.deployment = dep
                if hasattr(api_router.config, "api"):
                    api_router.config.api.model = dep
    except Exception:
        logger.debug("Online deployment push to live router failed", exc_info=True)
def bind_query_panel_use_case_runtime_methods(cls):
    """Bind use-case runtime methods to QueryPanel."""
    cls._apply_use_case_tuning = _apply_use_case_tuning
    cls._apply_profile_dial_defaults = _apply_profile_dial_defaults
    cls._on_use_case_change = _on_use_case_change
    cls._update_profile_playbook = _update_profile_playbook
    cls._resolve_online_model = _resolve_online_model
    cls._apply_online_selection = _apply_online_selection
