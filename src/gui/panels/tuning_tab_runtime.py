# ============================================================================
# TuningTab runtime coordinator -- shared data, hardware detection, and bind
# ============================================================================
# Sub-modules:
#   tuning_tab_ui_runtime.py     -- widget factory and section builders
#   tuning_tab_logic_runtime.py  -- mode/slider/config state logic
#   tuning_tab_action_runtime.py -- change handlers, profile, latency, resets
# ============================================================================
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

from src.core.mode_config import MODE_TUNED_DEFAULTS, normalize_mode
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.tuning_tab_ui_runtime import bind_tuning_tab_ui_runtime_methods
from src.gui.panels.tuning_tab_logic_runtime import bind_tuning_tab_logic_runtime_methods
from src.gui.panels.tuning_tab_action_runtime import bind_tuning_tab_action_runtime_methods

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Shared constants
# ------------------------------------------------------------------

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
        "grounding_bias": 8,
        "allow_open_knowledge": True,
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
        "grounding_bias": 8,
        "allow_open_knowledge": True,
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
        "grounding_bias": 7,
        "allow_open_knowledge": True,
    },
}


# ------------------------------------------------------------------
# Config value extraction (used by logic sub-module)
# ------------------------------------------------------------------


def _mode_llm_values_from_config(config, mode: str) -> dict:
    """Return visible tuning values for the active mode without mixing paths."""
    mode = normalize_mode(mode)
    retrieval = getattr(config, "retrieval", None)
    api = getattr(config, "api", None)
    ollama = getattr(config, "ollama", None)
    query = getattr(config, "query", None)
    offline_defaults = MODE_TUNED_DEFAULTS["offline"]
    online_defaults = MODE_TUNED_DEFAULTS["online"]
    active_defaults = MODE_TUNED_DEFAULTS[mode]

    values = {
        "top_k": getattr(retrieval, "top_k", active_defaults["top_k"]) if retrieval else active_defaults["top_k"],
        "min_score": getattr(retrieval, "min_score", active_defaults["min_score"]) if retrieval else active_defaults["min_score"],
        "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
        "reranker_enabled": getattr(retrieval, "reranker_enabled", active_defaults["reranker_enabled"]) if retrieval else active_defaults["reranker_enabled"],
        "reranker_top_n": getattr(retrieval, "reranker_top_n", active_defaults["reranker_top_n"]) if retrieval else active_defaults["reranker_top_n"],
        "context_window": offline_defaults["context_window"],
        "num_predict": getattr(ollama, "num_predict", offline_defaults["num_predict"]) if ollama else offline_defaults["num_predict"],
        "max_tokens": getattr(api, "max_tokens", online_defaults["max_tokens"]) if api else online_defaults["max_tokens"],
        "temperature": offline_defaults["temperature"] if mode == "offline" else online_defaults["temperature"],
        "top_p": offline_defaults["top_p"] if mode == "offline" else online_defaults["top_p"],
        "presence_penalty": online_defaults["presence_penalty"],
        "frequency_penalty": online_defaults["frequency_penalty"],
        "seed": offline_defaults["seed"] if mode == "offline" else online_defaults["seed"],
        "timeout_seconds": offline_defaults["timeout_seconds"] if mode == "offline" else online_defaults["timeout_seconds"],
        "grounding_bias": getattr(query, "grounding_bias", active_defaults["grounding_bias"]) if query else active_defaults["grounding_bias"],
        "allow_open_knowledge": getattr(query, "allow_open_knowledge", active_defaults["allow_open_knowledge"]) if query else active_defaults["allow_open_knowledge"],
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


# ------------------------------------------------------------------
# Hardware detection
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Model VRAM specs & estimation (used by action sub-module)
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Profile switch subprocess helper (used by action sub-module)
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Master bind -- delegates to sub-module binders
# ------------------------------------------------------------------


def bind_tuning_tab_runtime_methods(tab_cls) -> None:
    """Bind all runtime methods to TuningTab by delegating to sub-modules."""
    # Order matters: logic first (accessors), then UI (builders call accessors),
    # then actions (handlers call both).
    bind_tuning_tab_logic_runtime_methods(tab_cls)
    bind_tuning_tab_ui_runtime_methods(tab_cls)
    bind_tuning_tab_action_runtime_methods(tab_cls)


__all__ = [
    "SAFE_DEFAULTS",
    "_detect_hardware_class",
    "_mode_llm_values_from_config",
    "_MODEL_SPECS",
    "_vram_overflows",
    "_estimate_query_seconds",
    "_run_profile_switch",
    "bind_tuning_tab_runtime_methods",
]
