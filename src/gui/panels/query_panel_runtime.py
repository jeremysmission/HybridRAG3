# Extracted runtime/query/model methods from QueryPanel.
from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox

from scripts._model_meta import (
    USE_CASES, select_best_model, RECOMMENDED_OFFLINE, WORK_ONLY_MODELS,
    use_case_score, get_offline_models_with_specs,
)
from src.core.llm_router import get_available_deployments
from src.core.model_identity import canonicalize_model_name
from src.core.cost_tracker import get_cost_tracker
from src.gui.theme import current_theme
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.query_constants import (
    ONLINE_USE_CASE_TUNING,
    PROFILE_DIAL_DEFAULTS,
    GROUNDING_BIAS_HINTS,
    REASONING_DIAL_HINTS,
    PROFILE_TASK_PLAYBOOK,
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
    except Exception:
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
        # Apply to live router if already initialized
        try:
            if self.query_engine and hasattr(self.query_engine, "llm_router"):
                api_router = getattr(self.query_engine.llm_router, "api", None)
                if api_router is not None:
                    api_router.deployment = chosen
        except Exception:
            pass
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
    self._grounding_bias_hint.set(
        GROUNDING_BIAS_HINTS.get(bias, "Grounding bias updated")
    )
    self._apply_grounding_bias_live(bias)

def _on_reasoning_dial_change(self, _value=None):
    """Plain-English: Applies user reasoning-level changes to prompt behavior and UI indicators."""
    lvl = int(self._reasoning_dial_var.get())
    self._reasoning_dial_hint.set(
        REASONING_DIAL_HINTS.get(lvl, "Reasoning dial updated")
    )
    self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

def _apply_grounding_bias_live(self, bias: int):
    """
    Map 1..10 slider into live guard settings.
    Lower bias => more synthesis freedom.
    Higher bias => stricter evidence requirements.
    """
    b = max(0, min(10, int(bias)))
    r = max(0, min(10, int(self._reasoning_dial_var.get())))
    guard_on = b > 0
    threshold = 0.35 + (max(1, b) / 10.0) * 0.55
    min_chunks = 1 if b <= 4 else 2 if b <= 7 else 3
    min_score = 0.00 if b <= 2 else 0.03 if b <= 4 else 0.06 if b <= 7 else 0.10
    action = "flag" if b <= 5 else "block"

    # Config object update (if fields exist)
    try:
        hg = getattr(self.config, "hallucination_guard", None)
        if hg is not None:
            hg.enabled = bool(guard_on)
            hg.threshold = float(round(threshold, 2))
            hg.failure_action = action
        if hasattr(self.config, "retrieval"):
            self.config.retrieval.min_score = max(
                float(getattr(self.config.retrieval, "min_score", 0.0)),
                float(min_score),
            )
    except Exception:
        pass

    # Live engine update (works without restart)
    qe = self.query_engine
    if qe is not None:
        try:
            # Independent reasoning dial: 0 disables, >0 enables.
            setattr(qe, "allow_open_knowledge", bool(r > 0))
            setattr(qe, "reasoning_level", int(r))
            if hasattr(qe, "guard_enabled"):
                qe.guard_enabled = bool(guard_on)
            if hasattr(qe, "guard_threshold"):
                qe.guard_threshold = float(round(threshold, 2))
            if hasattr(qe, "guard_min_chunks"):
                qe.guard_min_chunks = int(min_chunks)
            if hasattr(qe, "guard_min_score"):
                qe.guard_min_score = float(min_score)
            if hasattr(qe, "guard_action"):
                qe.guard_action = action
        except Exception:
            pass

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

# ----------------------------------------------------------------
# USE CASE CHANGE
# ----------------------------------------------------------------

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
                self.config.ollama.temperature = rec["temperature"]
        if hasattr(self.config, "retrieval"):
            if "top_k" in rec:
                self.config.retrieval.top_k = rec["top_k"]
        return

    # Online tuning bundle
    rec = ONLINE_USE_CASE_TUNING.get(uc_key, {})
    if not rec:
        return
    if hasattr(self.config, "api"):
        if "temperature" in rec:
            self.config.api.temperature = rec["temperature"]
        if "max_tokens" in rec:
            self.config.api.max_tokens = rec["max_tokens"]
        if "timeout_seconds" in rec:
            self.config.api.timeout_seconds = rec["timeout_seconds"]
    if hasattr(self.config, "retrieval"):
        if "top_k" in rec:
            self.config.retrieval.top_k = rec["top_k"]
        if "min_score" in rec:
            self.config.retrieval.min_score = rec["min_score"]

def _apply_profile_dial_defaults(self, uc_key: str, mode: str) -> None:
    """Apply safe per-profile defaults for grounding/reasoning dials."""
    mode_key = "online" if str(mode).lower() == "online" else "offline"
    rec = PROFILE_DIAL_DEFAULTS.get(mode_key, {}).get(
        uc_key, {"grounding": 7, "reasoning": 4}
    )
    try:
        self._grounding_bias_var.set(int(rec.get("grounding", 7)))
        self._reasoning_dial_var.set(int(rec.get("reasoning", 4)))
        self._grounding_bias_hint.set(
            GROUNDING_BIAS_HINTS.get(
                int(self._grounding_bias_var.get()), "Grounding updated"
            )
        )
        self._reasoning_dial_hint.set(
            REASONING_DIAL_HINTS.get(
                int(self._reasoning_dial_var.get()), "Reasoning updated"
            )
        )
        self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))
    except Exception:
        pass

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

def _resolve_online_model(self, uc_key):
    """Background thread: fetch deployments and update model label."""
    try:
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
            configured = self._get_configured_online_deployment()
            if configured:
                self._online_models = [configured]
                safe_after(self, 0, self.model_var.set, f"Online: {configured}")
                safe_after(
                    self, 0, self._apply_online_selection, configured, True, "configured fallback",
                )
                safe_after(self, 0, self._set_model_combo_for_mode)
                safe_after(self, 0, self._set_online_discovery_note, configured)
            else:
                safe_after(self, 0, self.model_info_var.set, "(no model)")
    except RuntimeError:
        pass  # Widget destroyed before thread finished -- safe to ignore
    except Exception:
        try:
            configured = self._get_configured_online_deployment()
            if configured:
                self._online_models = [configured]
                safe_after(self, 0, self.model_var.set, f"Online: {configured}")
                safe_after(
                    self, 0, self._apply_online_selection, configured, True, "configured fallback",
                )
                safe_after(self, 0, self._set_model_combo_for_mode)
                safe_after(self, 0, self._set_online_discovery_note, configured)
            else:
                safe_after(self, 0, self.model_info_var.set, "(discovery failed)")
        except RuntimeError:
            pass  # Widget destroyed

def _apply_online_selection(self, deployment, is_fallback=False, note=""):
    """Apply selected online deployment to live config/router for consistency."""
    dep = (deployment or "").strip()
    if not dep:
        return
    if hasattr(self.config, "api"):
        self.config.api.deployment = dep
    try:
        if self.query_engine and hasattr(self.query_engine, "llm_router"):
            api_router = getattr(self.query_engine.llm_router, "api", None)
            if api_router is not None:
                api_router.deployment = dep
    except Exception:
        pass

def _on_ask(self, event=None):
    """Handle Ask button click or Enter key.

    State transition: IDLE -> SEARCHING
    The query runs in a background thread to keep the GUI responsive.
    """
    question = self.question_entry.get().strip()
    if not question or question == "Type your question here...":
        return

    if self.query_engine is None:
        self._show_error("[FAIL] Query engine not initialized. Run boot first.")
        return
    if self.is_querying:
        return
    # Enforce current grounding bias before each query execution.
    self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

    # --- Transition to SEARCHING state ---
    self._set_query_controls(running=True)
    self._stream_start = time.time()
    self._query_seq += 1
    query_id = self._query_seq
    self._active_query_id = query_id
    self._cancelled_query_ids.discard(query_id)

    # Public testing state (main thread, before thread starts)
    self.is_querying = True
    self.query_done_event.clear()
    self.last_answer_preview = ""
    self.last_query_status = ""

    # Clear previous answer for fresh output
    self.answer_text.config(state=tk.NORMAL)
    self.answer_text.delete("1.0", tk.END)
    self.answer_text.config(state=tk.DISABLED)
    self.sources_label.config(text="Sources: (none)", fg=current_theme()["gray"])
    self.metrics_label.config(text="")

    # Show immediate visual feedback: status text + animated overlay
    t = current_theme()
    self.network_label.config(text="Searching documents...", fg=t["gray"])
    self._overlay.start("Searching documents...")

    # Choose streaming path (token-by-token) or fallback (wait for full result)
    has_stream = hasattr(self.query_engine, "query_stream")
    if has_stream:
        self._query_thread = threading.Thread(
            target=self._run_query_stream, args=(question, query_id), daemon=True,
        )
    else:
        self._query_thread = threading.Thread(
            target=self._run_query, args=(question, query_id), daemon=True,
        )
    self._query_thread.start()

def _run_query(self, question, query_id):
    """Execute query in background thread (non-streaming fallback)."""
    try:
        result = self.query_engine.query(question)
        if self._is_query_aborted(query_id):
            return
        # Thread-safe completion signal + status
        self.is_querying = False
        self.last_answer_preview = (result.answer or "")[:200]
        self.last_query_status = "error" if result.error else "complete"
        self.query_done_event.set()
        safe_after(self, 0, self._display_result, result)
    except Exception as e:
        if self._is_query_aborted(query_id):
            return
        error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
        self.is_querying = False
        self.last_answer_preview = error_msg
        self.last_query_status = "error"
        self.query_done_event.set()
        safe_after(self, 0, self._show_error, error_msg)

def _run_query_stream(self, question, query_id):
    """Execute streaming query in background thread.

    State transitions driven by the query engine's yield chunks:
      "searching" phase -> stay in SEARCHING state
      "generating" phase -> transition to GENERATING state
      "token" chunks -> append tokens (GENERATING)
      "done" chunk -> transition to COMPLETE state
    """
    try:
        for chunk in self.query_engine.query_stream(question):
            if self._is_query_aborted(query_id):
                return
            if "phase" in chunk:
                if chunk["phase"] == "searching":
                    # Still in SEARCHING -- update status text
                    safe_after(self, 0, self._set_status_if_active, query_id, "Searching documents...")
                elif chunk["phase"] == "generating":
                    # --- Transition: SEARCHING -> GENERATING ---
                    n = chunk.get("chunks", 0)
                    ms = chunk.get("retrieval_ms", 0)
                    msg = "Found {} chunks ({:.0f}ms) -- Generating answer...".format(n, ms)
                    safe_after(self, 0, self._set_status_if_active, query_id, msg)
                    safe_after(self, 0, self._start_elapsed_timer_if_active, query_id)
                    safe_after(self, 0, self._prepare_streaming_if_active, query_id)
                    safe_after(self, 0, self._stop_overlay_if_active, query_id)
            elif "token" in chunk:
                safe_after(self, 0, self._append_token_if_active, query_id, chunk["token"])
            elif chunk.get("done"):
                result = chunk.get("result")
                if result:
                    if self._is_query_aborted(query_id):
                        return
                    # Thread-safe completion signal + status
                    self.is_querying = False
                    self.last_answer_preview = (result.answer or "")[:200]
                    self.last_query_status = "error" if result.error else "complete"
                    self.query_done_event.set()
                    safe_after(self, 0, self._finish_stream_if_active, query_id, result)
                return
        # If generator exhausted without "done"
        if self._is_query_aborted(query_id):
            return
        self.is_querying = False
        self.last_query_status = "incomplete"
        self.query_done_event.set()
        safe_after(self, 0, self._stop_elapsed_timer)
        safe_after(self, 0, self._stop_overlay_if_active, query_id)
        safe_after(self, 0, self._set_query_controls, False)
    except Exception as e:
        if self._is_query_aborted(query_id):
            return
        error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
        self.is_querying = False
        self.last_answer_preview = error_msg
        self.last_query_status = "error"
        self.query_done_event.set()
        safe_after(self, 0, self._stop_elapsed_timer)
        safe_after(self, 0, self._overlay.cancel)
        safe_after(self, 0, self._show_error, error_msg)

def _is_query_aborted(self, query_id):
    """True when a query is stale/cancelled and its UI updates must be ignored."""
    return (query_id != self._active_query_id) or (query_id in self._cancelled_query_ids)

def _set_query_controls(self, running):
    """Toggle Ask/Stop buttons for in-flight query UX."""
    t = current_theme()
    if running:
        self.ask_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
        self.stop_btn.config(state=tk.NORMAL, bg=t["red"], fg=t["accent_fg"])
    else:
        self.ask_btn.config(state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])

def _on_stop_query(self, event=None):
    """Soft-cancel current query: restore control immediately and ignore late results."""
    if not self.is_querying:
        return
    qid = self._active_query_id
    self._cancelled_query_ids.add(qid)
    self.is_querying = False
    self._streaming = False
    self.last_answer_preview = "[STOP] Query cancelled by user."
    self.last_query_status = "cancelled"
    self.query_done_event.set()
    self._stop_elapsed_timer()
    self._overlay.cancel()
    self._set_query_controls(running=False)
    t = current_theme()
    self.network_label.config(text="Query stopped.", fg=t["orange"])

def _set_status_if_active(self, query_id, text):
    """Plain-English: Updates status text only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._set_status(text)

def _start_elapsed_timer_if_active(self, query_id):
    """Plain-English: Starts the elapsed-time indicator only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._start_elapsed_timer()

def _prepare_streaming_if_active(self, query_id):
    """Plain-English: Prepares streaming output buffers only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._prepare_streaming()

def _append_token_if_active(self, query_id, token):
    """Plain-English: Appends streamed tokens only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._append_token(token)

def _finish_stream_if_active(self, query_id, result):
    """Plain-English: Finalizes stream rendering only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._finish_stream(result)

def _stop_overlay_if_active(self, query_id):
    """Plain-English: Hides the loading overlay only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._overlay.stop()

def _set_status(self, text):
    """Update the network/status label."""
    t = current_theme()
    self.network_label.config(text=text, fg=t["gray"])

def _prepare_streaming(self):
    """Set answer area to NORMAL for live token insertion."""
    self._streaming = True
    self.answer_text.config(state=tk.NORMAL)
    self.answer_text.delete("1.0", tk.END)

def _append_token(self, token):
    """Append a single token to the answer area (main thread)."""
    if not self._streaming:
        return
    self.answer_text.insert(tk.END, token)
    self.answer_text.see(tk.END)

def _start_elapsed_timer(self):
    """Start a 500ms timer that updates the status with elapsed time."""
    self._stop_elapsed_timer()
    self._update_elapsed()

def _update_elapsed(self):
    """Update status line with elapsed seconds."""
    if not self._streaming:
        return
    elapsed = time.time() - self._stream_start
    t = current_theme()
    self.network_label.config(
        text="Generating... ({:.1f}s)".format(elapsed), fg=t["gray"],
    )
    self._elapsed_timer_id = self.after(500, self._update_elapsed)

def _stop_elapsed_timer(self):
    """Cancel the elapsed timer if running."""
    if self._elapsed_timer_id is not None:
        self.after_cancel(self._elapsed_timer_id)
        self._elapsed_timer_id = None

def _finish_stream(self, result):
    """Finalize the UI after streaming completes.

    State transition: GENERATING -> COMPLETE
    """
    self._streaming = False
    self._stop_elapsed_timer()

    # Fallback: if streaming produced no visible tokens, populate
    # from result.answer so the answer box is never blank.
    current = self.answer_text.get("1.0", tk.END).strip()
    if not current and result.answer:
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert("1.0", result.answer)

    self.answer_text.config(state=tk.DISABLED)
    self._set_query_controls(running=False)
    self.network_label.config(text="")

    # Display sources and metrics from the final result
    t = current_theme()
    if result.error:
        detail = (result.answer or result.error or "").strip()
        self._show_error("[FAIL] {}".format(detail))
        return

    # Display grounding status if available
    g_score = getattr(result, "grounding_score", -1.0)
    g_blocked = getattr(result, "grounding_blocked", False)
    if g_blocked:
        self.network_label.config(
            text="Grounding: BLOCKED (score {:.0%})".format(g_score),
            fg=t["red"],
        )
    elif g_score >= 0:
        color = t["green"] if g_score >= 0.8 else t["orange"] if g_score >= 0.5 else t["red"]
        self.network_label.config(
            text="Grounding: {:.0%} verified".format(g_score),
            fg=color,
        )

    if result.sources:
        source_strs = []
        for s in result.sources:
            path = s.get("path", "unknown")
            chunks = s.get("chunks", 0)
            fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            source_strs.append("{} ({} chunks)".format(fname, chunks))
        self.sources_label.config(
            text="Sources: {}".format(", ".join(source_strs)),
            fg=t["fg"],
        )
    else:
        self.sources_label.config(text="Sources: (none)", fg=t["gray"])

    self.metrics_label.config(
        text="Latency: {:,.0f} ms | Tokens in: {} | Tokens out: {}".format(
            result.latency_ms, result.tokens_in, result.tokens_out
        ),
    )

    # Record cost event for PM dashboard
    self._emit_cost_event(result)

def _display_result(self, result):
    """Display query result in the UI (called on main thread)."""
    try:
        self._display_result_inner(result)
    except Exception as e:
        logger.error("Display result failed: %s", e)
        self._set_query_controls(running=False)
        self.network_label.config(text="")

def _display_result_inner(self, result):
    """Inner display logic (separated so outer can catch and re-enable)."""
    t = current_theme()
    self._set_query_controls(running=False)
    self.network_label.config(text="")
    self._overlay.stop()

    # Check for error
    if result.error:
        detail = (result.answer or result.error or "").strip()
        self._show_error("[FAIL] {}".format(detail))
        return

    # Display answer -- never leave the box blank
    answer = result.answer or ""
    if not answer.strip():
        if result.sources:
            answer = (
                "Search found relevant documents but the LLM returned "
                "an empty response. This may indicate the model is still "
                "loading or the context was too large. Try again."
            )
        else:
            answer = "No relevant information found in knowledge base."
    self.answer_text.config(state=tk.NORMAL)
    self.answer_text.delete("1.0", tk.END)
    self.answer_text.insert("1.0", answer)
    self.answer_text.config(state=tk.DISABLED)

    # Display grounding status if available
    g_score = getattr(result, "grounding_score", -1.0)
    g_blocked = getattr(result, "grounding_blocked", False)
    if g_blocked:
        self.network_label.config(
            text="Grounding: BLOCKED (score {:.0%})".format(g_score),
            fg=t["red"],
        )
    elif g_score >= 0:
        color = t["green"] if g_score >= 0.8 else t["orange"] if g_score >= 0.5 else t["red"]
        self.network_label.config(
            text="Grounding: {:.0%} verified".format(g_score),
            fg=color,
        )

    # Display sources
    if result.sources:
        source_strs = []
        for s in result.sources:
            path = s.get("path", "unknown")
            chunks = s.get("chunks", 0)
            # Show just the filename, not full path
            fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            source_strs.append("{} ({} chunks)".format(fname, chunks))
        self.sources_label.config(
            text="Sources: {}".format(", ".join(source_strs)),
            fg=t["fg"],
        )
    else:
        self.sources_label.config(text="Sources: (none)", fg=t["gray"])

    # Display metrics
    latency = result.latency_ms
    tokens_in = result.tokens_in
    tokens_out = result.tokens_out
    self.metrics_label.config(
        text="Latency: {:,.0f} ms | Tokens in: {} | Tokens out: {}".format(
            latency, tokens_in, tokens_out
        ),
    )

    # Record cost event for PM dashboard
    self._emit_cost_event(result)

def _show_error(self, error_msg):
    """Display an error message in the answer area.

    State transition: any state -> ERROR (then effectively IDLE)
    """
    t = current_theme()
    self._set_query_controls(running=False)
    self.network_label.config(text="")
    self._overlay.cancel()

    self.answer_text.config(state=tk.NORMAL)
    self.answer_text.delete("1.0", tk.END)
    self.answer_text.insert("1.0", error_msg)
    self.answer_text.tag_add("error", "1.0", tk.END)
    self.answer_text.tag_config("error", foreground=t["red"])
    self.answer_text.config(state=tk.DISABLED)

    self.sources_label.config(text="Sources: (none)", fg=t["gray"])
    self.metrics_label.config(text="")
    self._maybe_show_memory_tuning_popup(error_msg)

def _maybe_show_memory_tuning_popup(self, error_msg):
    """Show targeted guidance for common offline 500/timeout memory failures."""
    try:
        msg = (error_msg or "").strip()
        low = msg.lower()
        if not low:
            return

        hit_500 = ("500" in low) or ("internal server error" in low)
        hit_timeout = ("timed out" in low) or ("timeout" in low) or ("readtimeout" in low)
        hit_runner = (
            ("llama runner" in low)
            or ("error calling llm" in low)
            or ("llm call failed" in low)
        )
        if not (hit_500 or hit_timeout or hit_runner):
            return

        mode = str(getattr(self.config, "mode", "") or "").lower().strip()
        if mode and mode != "offline":
            return

        now = time.time()
        if (now - float(self._last_mem_popup_ts or 0.0)) < 120:
            return
        self._last_mem_popup_ts = now

        ollama_cfg = getattr(self.config, "ollama", None)
        model = getattr(ollama_cfg, "model", "unknown") if ollama_cfg else "unknown"
        ctx = getattr(ollama_cfg, "context_window", "unknown") if ollama_cfg else "unknown"
        timeout = getattr(ollama_cfg, "timeout_seconds", "unknown") if ollama_cfg else "unknown"

        details = (
            "HybridRAG detected an offline LLM failure commonly caused by model/context memory pressure.\n\n"
            "Current settings:\n"
            "model={}\ncontext_window={}\ntimeout_seconds={}\n\n"
            "Recommended stability tweaks (in order):\n"
            "1) Set model to phi4-mini\n"
            "2) Set context_window to 4096\n"
            "3) Set timeout_seconds to 180\n\n"
            "Where to change:\n"
            "- GUI: Engineering > Admin Settings (Offline/Ollama tuning)\n"
            "- File: config/user_overrides.yaml (takes precedence over defaults)\n\n"
            "Quick validation:\n"
            "- ollama run phi4-mini \"OK\"\n"
            "- ollama ps\n\n"
            "Docs: docs/01_setup/MANUAL_INSTALL.md -> \"Ollama returns HTTP 500 on query/generate\""
        ).format(model, ctx, timeout)
        messagebox.showwarning("Offline LLM Memory Guidance", details, parent=self.winfo_toplevel())
    except Exception as e:
        logger.debug("Memory guidance popup skipped: %s", e)

def set_ready(self, enabled):
    """Enable or disable the Ask button based on backend readiness."""
    t = current_theme()
    if enabled:
        self.ask_btn.config(state=tk.NORMAL, bg=t["accent"],
                            fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])
    else:
        self.ask_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                            fg=t["inactive_btn_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])

def _emit_cost_event(self, result):
    """Record completed query in the cost tracker for PM dashboard."""
    try:
        tracker = get_cost_tracker()
        mode = getattr(result, "mode", "offline")
        chosen = self.model_var.get()
        if chosen == "Auto":
            model = getattr(
                getattr(self.config, "ollama", None), "model", ""
            ) or ""
        else:
            model = chosen
        profile = self.get_current_use_case_key()
        tracker.record(
            tokens_in=getattr(result, "tokens_in", 0),
            tokens_out=getattr(result, "tokens_out", 0),
            model=model,
            mode=mode,
            profile=profile,
            latency_ms=getattr(result, "latency_ms", 0.0),
        )
    except Exception as e:
        logger.debug("Cost event emit failed: %s", e)

def get_current_use_case_key(self):
    """Return the currently selected use case key."""
    idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
    return self._uc_keys[idx]

def bind_query_panel_runtime_methods(cls):
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
    cls._on_reasoning_dial_change = _on_reasoning_dial_change
    cls._apply_grounding_bias_live = _apply_grounding_bias_live
    cls._check_primary_worker = _check_primary_worker
    cls._switch_to_primary_offline = _switch_to_primary_offline
    cls._switch_to_primary_online = _switch_to_primary_online
    cls._check_primary_done = _check_primary_done
    cls._apply_use_case_tuning = _apply_use_case_tuning
    cls._apply_profile_dial_defaults = _apply_profile_dial_defaults
    cls._on_use_case_change = _on_use_case_change
    cls._update_profile_playbook = _update_profile_playbook
    cls._resolve_online_model = _resolve_online_model
    cls._apply_online_selection = _apply_online_selection
    cls._on_ask = _on_ask
    cls._run_query = _run_query
    cls._run_query_stream = _run_query_stream
    cls._is_query_aborted = _is_query_aborted
    cls._set_query_controls = _set_query_controls
    cls._on_stop_query = _on_stop_query
    cls._set_status_if_active = _set_status_if_active
    cls._start_elapsed_timer_if_active = _start_elapsed_timer_if_active
    cls._prepare_streaming_if_active = _prepare_streaming_if_active
    cls._append_token_if_active = _append_token_if_active
    cls._finish_stream_if_active = _finish_stream_if_active
    cls._stop_overlay_if_active = _stop_overlay_if_active
    cls._set_status = _set_status
    cls._prepare_streaming = _prepare_streaming
    cls._append_token = _append_token
    cls._start_elapsed_timer = _start_elapsed_timer
    cls._update_elapsed = _update_elapsed
    cls._stop_elapsed_timer = _stop_elapsed_timer
    cls._finish_stream = _finish_stream
    cls._display_result = _display_result
    cls._display_result_inner = _display_result_inner
    cls._show_error = _show_error
    cls._maybe_show_memory_tuning_popup = _maybe_show_memory_tuning_popup
    cls.set_ready = set_ready
    cls._emit_cost_event = _emit_cost_event
    cls.get_current_use_case_key = get_current_use_case_key
