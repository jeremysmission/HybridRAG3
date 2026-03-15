from __future__ import annotations

import copy
from typing import Any


MODE_BACKEND_SECTION = {
    "offline": "ollama",
    "online": "api",
}

MODE_TUNING_KEYS = {
    "offline": (
        "top_k",
        "min_score",
        "hybrid_search",
        "reranker_enabled",
        "reranker_top_n",
        "context_window",
        "num_predict",
        "temperature",
        "top_p",
        "seed",
        "timeout_seconds",
        "grounding_bias",
        "allow_open_knowledge",
    ),
    "online": (
        "top_k",
        "min_score",
        "hybrid_search",
        "reranker_enabled",
        "reranker_top_n",
        "context_window",
        "max_tokens",
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "timeout_seconds",
        "grounding_bias",
        "allow_open_knowledge",
    ),
}

MODE_KEY_TYPES = {
    "top_k": int,
    "min_score": float,
    "hybrid_search": bool,
    "reranker_enabled": bool,
    "reranker_top_n": int,
    "context_window": int,
    "num_predict": int,
    "max_tokens": int,
    "temperature": float,
    "top_p": float,
    "presence_penalty": float,
    "frequency_penalty": float,
    "seed": int,
    "timeout_seconds": int,
    "grounding_bias": int,
    "allow_open_knowledge": bool,
}

MODE_LEGACY_KEY_ALIASES = {
    "reasoning_dial": "allow_open_knowledge",
}

MODE_TUNED_DEFAULTS = {
    "offline": {
        "top_k": 4,
        "min_score": 0.10,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "num_predict": 384,
        "temperature": 0.05,
        "top_p": 0.90,
        "seed": 0,
        "timeout_seconds": 180,
        "grounding_bias": 8,
        "allow_open_knowledge": True,
    },
    "online": {
        "top_k": 6,
        "min_score": 0.08,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 128000,
        "max_tokens": 1024,
        "temperature": 0.05,
        "top_p": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": 0,
        "timeout_seconds": 180,
        "grounding_bias": 7,
        "allow_open_knowledge": True,
    },
}

MODE_PATH_DEFAULTS = {
    "database": "",
    "embeddings_cache": "",
    "source_folder": "",
    "download_folder": "",
    "transfer_source_folder": "",
}

MODE_RUNTIME_DEFAULTS = {
    "offline": {
        "retrieval": {
            "top_k": 4,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
        },
        "ollama": {
            "model": "phi4-mini",
            "base_url": "http://127.0.0.1:11434",
            "context_window": 4096,
            "num_predict": 384,
            "temperature": 0.05,
            "top_p": 0.90,
            "seed": 0,
            "timeout_seconds": 180,
        },
        "query": {
            "grounding_bias": 8,
            "allow_open_knowledge": True,
        },
    },
    "online": {
        "retrieval": {
            "top_k": 6,
            "min_score": 0.08,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "corrective_retrieval": True,
            "corrective_threshold": 0.35,
        },
        "api": {
            "model": "",
            "deployment": "",
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.05,
            "top_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 0,
            "timeout_seconds": 180,
        },
        "query": {
            "grounding_bias": 7,
            "allow_open_knowledge": True,
        },
    },
}

MODE_RUNTIME_PATHS = {
    "offline": {
        "top_k": ("retrieval", "top_k"),
        "min_score": ("retrieval", "min_score"),
        "hybrid_search": ("retrieval", "hybrid_search"),
        "reranker_enabled": ("retrieval", "reranker_enabled"),
        "reranker_top_n": ("retrieval", "reranker_top_n"),
        "context_window": ("ollama", "context_window"),
        "num_predict": ("ollama", "num_predict"),
        "temperature": ("ollama", "temperature"),
        "top_p": ("ollama", "top_p"),
        "seed": ("ollama", "seed"),
        "timeout_seconds": ("ollama", "timeout_seconds"),
        "grounding_bias": ("query", "grounding_bias"),
        "allow_open_knowledge": ("query", "allow_open_knowledge"),
    },
    "online": {
        "top_k": ("retrieval", "top_k"),
        "min_score": ("retrieval", "min_score"),
        "hybrid_search": ("retrieval", "hybrid_search"),
        "reranker_enabled": ("retrieval", "reranker_enabled"),
        "reranker_top_n": ("retrieval", "reranker_top_n"),
        "context_window": ("api", "context_window"),
        "max_tokens": ("api", "max_tokens"),
        "temperature": ("api", "temperature"),
        "top_p": ("api", "top_p"),
        "presence_penalty": ("api", "presence_penalty"),
        "frequency_penalty": ("api", "frequency_penalty"),
        "seed": ("api", "seed"),
        "timeout_seconds": ("api", "timeout_seconds"),
        "grounding_bias": ("query", "grounding_bias"),
        "allow_open_knowledge": ("query", "allow_open_knowledge"),
    },
}


def normalize_mode(mode: str) -> str:
    return "online" if str(mode).strip().lower() == "online" else "offline"


def _coerce_value(key: str, value: Any) -> Any:
    caster = MODE_KEY_TYPES.get(key)
    if caster is None:
        return value
    try:
        if caster is bool:
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        return caster(value)
    except Exception:
        return copy.deepcopy(MODE_TUNED_DEFAULTS["offline"].get(key, value))


def _new_mode_entry(mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    return copy.deepcopy(MODE_RUNTIME_DEFAULTS[mode])


def snapshot_mode_entry(config, mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    entry = _new_mode_entry(mode)
    retrieval = getattr(config, "retrieval", None)
    api = getattr(config, "api", None)
    ollama = getattr(config, "ollama", None)
    paths = getattr(config, "paths", None)
    query = getattr(config, "query", None)

    if retrieval is not None:
        for key in ("top_k", "min_score", "hybrid_search", "reranker_enabled", "reranker_top_n",
                    "corrective_retrieval", "corrective_threshold"):
            if hasattr(retrieval, key):
                entry["retrieval"][key] = getattr(retrieval, key)

    if mode == "online":
        if api is not None:
            for key in (
                "model",
                "deployment",
                "context_window",
                "max_tokens",
                "temperature",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "seed",
                "timeout_seconds",
            ):
                if hasattr(api, key):
                    entry["api"][key] = getattr(api, key)
    else:
        if ollama is not None:
            for key in (
                "model",
                "base_url",
                "context_window",
                "num_predict",
                "temperature",
                "top_p",
                "seed",
                "timeout_seconds",
            ):
                if hasattr(ollama, key):
                    entry["ollama"][key] = getattr(ollama, key)

    if paths is not None:
        entry["paths"] = copy.deepcopy(MODE_PATH_DEFAULTS)
        for key in MODE_PATH_DEFAULTS:
            if hasattr(paths, key):
                entry["paths"][key] = getattr(paths, key)

    if query is not None:
        for key in ("grounding_bias", "allow_open_knowledge"):
            if hasattr(query, key):
                entry["query"][key] = getattr(query, key)

    return entry


def mode_entry_to_flat_values(mode: str, entry: dict[str, Any] | None) -> dict[str, Any]:
    mode = normalize_mode(mode)
    values = copy.deepcopy(MODE_TUNED_DEFAULTS[mode])
    entry = entry or {}
    for key, path in MODE_RUNTIME_PATHS[mode].items():
        section_name, field_name = path
        section = entry.get(section_name, {})
        if isinstance(section, dict) and field_name in section:
            values[key] = _coerce_value(key, section[field_name])
    legacy_values = entry.get("values", {})
    if isinstance(legacy_values, dict):
        for raw_key, raw_value in legacy_values.items():
            key = MODE_LEGACY_KEY_ALIASES.get(raw_key, raw_key)
            if key in MODE_TUNING_KEYS[mode]:
                values[key] = _coerce_value(key, raw_value)
    return values


def set_mode_value(entry: dict[str, Any], mode: str, key: str, value: Any) -> None:
    mode = normalize_mode(mode)
    if key not in MODE_RUNTIME_PATHS[mode]:
        return
    section_name, field_name = MODE_RUNTIME_PATHS[mode][key]
    section = entry.setdefault(section_name, {})
    if not isinstance(section, dict):
        section = {}
        entry[section_name] = section
    section[field_name] = _coerce_value(key, value)


def update_mode_section(entry: dict[str, Any], mode: str, section_name: str, key: str, value: Any) -> None:
    mode = normalize_mode(mode)
    valid_sections = {"retrieval", MODE_BACKEND_SECTION[mode], "query"}
    if section_name not in valid_sections:
        return
    section = entry.setdefault(section_name, {})
    if not isinstance(section, dict):
        section = {}
        entry[section_name] = section
    section[key] = value


def mode_runtime_overlay(mode: str, entry: dict[str, Any] | None) -> dict[str, Any]:
    mode = normalize_mode(mode)
    entry = entry or {}
    overlay = {}
    retrieval = entry.get("retrieval", {})
    if isinstance(retrieval, dict) and retrieval:
        overlay["retrieval"] = copy.deepcopy(retrieval)
    backend_name = MODE_BACKEND_SECTION[mode]
    backend = entry.get(backend_name, {})
    if isinstance(backend, dict) and backend:
        overlay[backend_name] = copy.deepcopy(backend)
    query = entry.get("query", {})
    if isinstance(query, dict) and query:
        overlay["query"] = copy.deepcopy(query)
    paths = entry.get("paths", {})
    if isinstance(paths, dict) and paths:
        overlay["paths"] = copy.deepcopy(paths)
    return overlay


def legacy_mode_store_to_runtime(mode: str, legacy_entry: dict[str, Any] | None) -> dict[str, Any]:
    mode = normalize_mode(mode)
    result = _new_mode_entry(mode)
    legacy_entry = legacy_entry or {}
    values = legacy_entry.get("values", {})
    if not isinstance(values, dict):
        return result
    for key in MODE_TUNING_KEYS[mode]:
        if key in values:
            set_mode_value(result, mode, key, values[key])
    return result
