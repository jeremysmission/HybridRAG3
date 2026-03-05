# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the model selector part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Model Auto-Selector (src/gui/panels/model_selector.py)
# ============================================================================
# Pure logic class extracted from query_panel.py. Handles model scoring,
# auto-selection, primary/fallback detection, and online deployment
# discovery. Contains NO tkinter imports -- fully testable without GUI.
# ============================================================================

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from scripts._model_meta import (
    RECOMMENDED_OFFLINE, WORK_ONLY_MODELS, use_case_score,
    select_best_model, get_offline_models_with_specs,
)
from src.core.llm_router import get_available_deployments
from src.core.model_identity import canonicalize_model_name

logger = logging.getLogger(__name__)

# Embedding-only models that should be excluded from LLM model lists.
_EMBED_MODELS = {"nomic-embed-text", "all-minilm", "mxbai-embed"}


@dataclass
class ModelSelection:
    """Result of an auto-selection decision."""
    model: str = ""
    primary: str = ""
    is_fallback: bool = False
    detail: str = ""
    score: int = -1


@dataclass
class ModelSelectorState:
    """Observable state that the GUI reads after each selection cycle."""
    installed_models: List[str] = field(default_factory=list)
    online_models: List[str] = field(default_factory=list)
    auto_mode: bool = True
    auto_selected_model: str = ""
    auto_primary_model: str = ""
    auto_fallback_active: bool = False
    auto_fallback_note: str = ""


class ModelAutoSelector:
    """Score and select the best model for a use case.

    This class owns the model-selection logic but has NO widget references.
    QueryPanel creates one of these and calls its methods, then reads
    the .state attribute to update widgets.
    """

    def __init__(self, config):
        """Plain-English: This function handles init."""
        self.config = config
        self.state = ModelSelectorState()

    def fetch_installed_models(self) -> List[str]:
        """Get installed Ollama model names (excludes embedders).

        Safe to call from a background thread.
        """
        try:
            models = get_offline_models_with_specs()
            names = []
            for m in models:
                name = m["name"]
                if not any(pat in name.lower() for pat in _EMBED_MODELS):
                    names.append(name)
            self.state.installed_models = names
            return names
        except Exception as e:
            logger.debug("Model list fetch failed: %s", e)
            return []

    def select_offline_model(self, uc_key: str) -> ModelSelection:
        """Pick the best offline model for a use case.

        Scores ALL installed models and picks the highest. Falls back
        through the recommendation chain if no scored models are found.
        """
        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        primary = (rec.get("primary", "") or "").strip()
        installed = self.state.installed_models

        best_model = None
        best_score = -1
        for name in installed:
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
        elif not installed:
            ollama_model = getattr(
                getattr(self.config, "ollama", None), "model", ""
            ) or rec.get("primary", "phi4:14b-q4_K_M")
        else:
            ollama_model = (
                rec.get("primary", "")
                or rec.get("alt", "")
                or rec.get("fallback", "")
                or getattr(
                    getattr(self.config, "ollama", None), "model", ""
                )
                or "phi4:14b-q4_K_M"
            )

        primary_c = canonicalize_model_name(primary)
        selected_c = canonicalize_model_name(ollama_model)
        installed_c = {canonicalize_model_name(m) for m in installed}
        is_fallback = (
            bool(primary) and primary_c not in installed_c
            and selected_c != primary_c
        )

        sel = ModelSelection(
            model=ollama_model,
            primary=primary,
            is_fallback=is_fallback,
            detail="offline",
            score=best_score,
        )

        # Update shared state
        self.state.auto_selected_model = ollama_model
        self.state.auto_primary_model = primary
        self.state.auto_fallback_active = is_fallback
        return sel

    def resolve_online_model(self, uc_key: str) -> ModelSelection:
        """Discover and select the best online deployment.

        Safe to call from a background thread.
        """
        try:
            deployments = get_available_deployments()
            best = select_best_model(uc_key, deployments)
            if best:
                self.state.online_models = list(deployments) if deployments else [best]
                sel = ModelSelection(
                    model=best, primary=best, is_fallback=False, detail="online auto",
                )
                self.state.auto_selected_model = best
                self.state.auto_primary_model = best
                self.state.auto_fallback_active = False
                return sel
        except Exception:
            pass

        # Fallback to configured deployment
        configured = self._get_configured_deployment()
        if configured:
            self.state.online_models = [configured]
            sel = ModelSelection(
                model=configured, primary="", is_fallback=True,
                detail="configured fallback",
            )
            self.state.auto_selected_model = configured
            self.state.auto_primary_model = ""
            self.state.auto_fallback_active = False
            return sel

        return ModelSelection(detail="no model")

    def check_primary_available(self, uc_key: str, mode: str) -> Optional[str]:
        """Check if the primary model is now available. Returns model name or None."""
        if mode == "offline":
            try:
                names = [m["name"] for m in get_offline_models_with_specs()]
            except Exception:
                names = list(self.state.installed_models)
            rec = RECOMMENDED_OFFLINE.get(uc_key, {})
            primary = (rec.get("primary", "") or "").strip()
            if primary and primary in names:
                return primary
            return None

        try:
            deployments = get_available_deployments()
            best = select_best_model(uc_key, deployments)
            current = (self.state.auto_selected_model or "").strip()
            if best and best != current:
                return best
        except Exception:
            pass
        return None

    def get_model_info(self, model_name: str, uc_key: str, mode: str) -> str:
        """Get display info string for a model."""
        mode_label = "Offline Mode" if mode == "offline" else "Online Mode"
        meta = WORK_ONLY_MODELS.get(model_name, {})
        if meta:
            score = use_case_score(
                meta.get("tier_eng", 30), meta.get("tier_gen", 30), uc_key,
            )
            if self.state.auto_mode:
                return "{} | Score: {} | {}".format(model_name, score, mode_label)
            return "Score: {} | {}".format(score, mode_label)
        return mode_label

    def build_auto_note(self, selection: ModelSelection) -> str:
        """Build the user-visible auto-mode status text."""
        selected = (selection.model or "").strip() or "(none)"
        primary = (selection.primary or "").strip()
        if selection.is_fallback:
            msg = "Auto Mode - Primary unavailable, Secondary selected: {}".format(selected)
        elif primary:
            msg = "Auto Mode - Primary selected: {}".format(selected)
        else:
            msg = "Auto Mode - Selected: {}".format(selected)
        if selection.detail:
            msg = "{} ({})".format(msg, selection.detail)
        self.state.auto_fallback_note = msg
        return msg

    def build_fallback_alert(self, selection: ModelSelection) -> str:
        """Build the persistent alert text for degraded routing."""
        if selection.is_fallback:
            return "Note: Primary AI Model Unavailable - Secondary model in use ({})".format(
                (selection.model or "").strip() or "(none)"
            )
        return ""

    def _get_configured_deployment(self) -> str:
        """Best-effort deployment from config or credential manager."""
        deployment = (
            getattr(getattr(self.config, "api", None), "deployment", "") or ""
        ).strip()
        if deployment:
            return deployment
        try:
            from src.security.credentials import resolve_credentials
            creds = resolve_credentials(use_cache=False)
            return (getattr(creds, "deployment", "") or "").strip()
        except Exception:
            return ""
