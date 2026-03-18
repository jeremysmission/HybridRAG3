from __future__ import annotations

import copy
import os
from typing import Any

from .config_files import deep_merge_dict
from .mode_config import (
    MODE_PATH_DEFAULTS,
    MODE_ROOT_FALLBACK_PATH_KEYS,
    MODE_RUNTIME_DEFAULTS,
    normalize_mode,
)
from .user_modes import apply_active_profile_overlay


_ROOT_RUNTIME_MIRRORS = (
    "active_profile",
    "api",
    "ollama",
    "query",
    "retrieval_online",
)
_MODE_RETRIEVAL_KEYS = {
    "top_k",
    "min_score",
    "hybrid_search",
    "reranker_enabled",
    "reranker_top_n",
}
_ACTIVE_MODE_ENV_NAME = "HYBRIDRAG_ACTIVE_MODE"


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _merge_path_overrides(
    base_paths: dict[str, Any] | None,
    mode_paths: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge mode paths over root paths without letting blanks erase values."""
    merged = _dict_or_empty(base_paths)
    fallback_keys = set(MODE_ROOT_FALLBACK_PATH_KEYS)
    for key, value in _dict_or_empty(mode_paths).items():
        if value:
            merged[key] = copy.deepcopy(value)
        elif key not in fallback_keys:
            merged[key] = copy.deepcopy(value)
    return merged


def set_runtime_active_mode(mode: str) -> str:
    """Track the live runtime mode without forcing an on-disk mode write."""
    normalized = normalize_mode(mode)
    os.environ[_ACTIVE_MODE_ENV_NAME] = normalized
    return normalized


def resolve_runtime_active_mode(
    persisted_data: dict[str, Any] | None = None,
    *,
    default: str = "offline",
) -> str:
    raw_env = str(os.environ.get(_ACTIVE_MODE_ENV_NAME, "") or "").strip().lower()
    if raw_env in ("offline", "online"):
        return raw_env
    if isinstance(persisted_data, dict):
        return normalize_mode(persisted_data.get("mode", default))
    return normalize_mode(default)


def _merge_mode_section(
    mode_entry: dict[str, Any],
    section_name: str,
    defaults: dict[str, Any],
    legacy: dict[str, Any] | None = None,
) -> None:
    current = _dict_or_empty(mode_entry.get(section_name))
    merged = deep_merge_dict(defaults, _dict_or_empty(legacy))
    merged = deep_merge_dict(merged, current)
    mode_entry[section_name] = merged


def _split_retrieval_sections(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    shared: dict[str, Any] = {}
    per_mode: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _MODE_RETRIEVAL_KEYS:
            per_mode[key] = copy.deepcopy(value)
        else:
            shared[key] = copy.deepcopy(value)
    return shared, per_mode


def canonicalize_config_dict(yaml_data: dict | None) -> dict[str, Any]:
    """Return the single canonical on-disk config shape.

    The persisted file may contain legacy flat runtime mirrors from older
    builds. Those values are migrated into `modes.*` once, then the flat
    mirrors are removed so the file no longer has competing authorities.
    """
    data = copy.deepcopy(yaml_data or {})
    if not isinstance(data, dict):
        return {"mode": "offline", "modes": {}}

    active_mode = normalize_mode(data.get("mode", "offline"))
    data["mode"] = active_mode
    data.pop("active_profile", None)

    raw_modes = data.get("modes")
    modes = copy.deepcopy(raw_modes) if isinstance(raw_modes, dict) else {}
    data["modes"] = modes
    offline = _dict_or_empty(modes.get("offline"))
    online = _dict_or_empty(modes.get("online"))

    root_retrieval = _dict_or_empty(data.get("retrieval"))
    shared_retrieval, mode_retrieval = _split_retrieval_sections(root_retrieval)
    root_online_retrieval = _dict_or_empty(data.get("retrieval_online"))
    root_query = _dict_or_empty(data.get("query"))
    root_ollama = _dict_or_empty(data.get("ollama"))
    root_api = _dict_or_empty(data.get("api"))
    root_paths = _dict_or_empty(data.get("paths"))
    offline_paths_legacy = _dict_or_empty(offline.get("paths")) or copy.deepcopy(root_paths)
    online_paths_legacy = _dict_or_empty(online.get("paths")) or copy.deepcopy(root_paths)

    offline_retrieval_legacy = mode_retrieval if active_mode == "offline" else {}
    online_retrieval_legacy = root_online_retrieval
    if active_mode == "online" and not online_retrieval_legacy:
        online_retrieval_legacy = mode_retrieval
    offline_query_legacy = root_query if active_mode == "offline" else {}
    online_query_legacy = root_query if active_mode == "online" else {}

    needs_offline = (
        bool(offline)
        or bool(root_ollama)
        or bool(offline_retrieval_legacy)
        or bool(offline_query_legacy)
        or bool(offline_paths_legacy)
    )
    needs_online = (
        bool(online)
        or bool(root_api)
        or bool(online_retrieval_legacy)
        or bool(online_query_legacy)
        or bool(online_paths_legacy)
    )

    if needs_offline:
        _merge_mode_section(
            offline,
            "retrieval",
            MODE_RUNTIME_DEFAULTS["offline"]["retrieval"],
            offline_retrieval_legacy,
        )
        _merge_mode_section(
            offline,
            "ollama",
            MODE_RUNTIME_DEFAULTS["offline"]["ollama"],
            root_ollama,
        )
        _merge_mode_section(
            offline,
            "query",
            MODE_RUNTIME_DEFAULTS["offline"]["query"],
            offline_query_legacy,
        )
        _merge_mode_section(
            offline,
            "paths",
            MODE_PATH_DEFAULTS,
            offline_paths_legacy,
        )
        modes["offline"] = offline
    else:
        modes.pop("offline", None)

    if needs_online:
        _merge_mode_section(
            online,
            "retrieval",
            MODE_RUNTIME_DEFAULTS["online"]["retrieval"],
            online_retrieval_legacy,
        )
        _merge_mode_section(
            online,
            "api",
            MODE_RUNTIME_DEFAULTS["online"]["api"],
            root_api,
        )
        _merge_mode_section(
            online,
            "query",
            MODE_RUNTIME_DEFAULTS["online"]["query"],
            online_query_legacy,
        )
        _merge_mode_section(
            online,
            "paths",
            MODE_PATH_DEFAULTS,
            online_paths_legacy,
        )
        modes["online"] = online
    else:
        modes.pop("online", None)

    if shared_retrieval:
        data["retrieval"] = shared_retrieval
    else:
        data.pop("retrieval", None)

    active_entry = _dict_or_empty(modes.get(active_mode))
    active_paths = _merge_path_overrides(root_paths, active_entry.get("paths"))
    if active_paths:
        data["paths"] = active_paths
    else:
        data.pop("paths", None)

    for mirror in _ROOT_RUNTIME_MIRRORS:
        data.pop(mirror, None)

    return data


def build_runtime_config_dict(
    yaml_data: dict | None,
    user_modes_data: dict | None = None,
) -> dict[str, Any]:
    """Project canonical persisted config into the runtime config shape."""
    persisted = canonicalize_config_dict(yaml_data)
    runtime = apply_active_profile_overlay(persisted, user_modes_data)
    active_mode = normalize_mode(runtime.get("mode", "offline"))
    runtime["mode"] = active_mode
    runtime["active_profile"] = str(
        (user_modes_data or {}).get("active_profile", "") or ""
    )

    modes = runtime.get("modes", {})
    offline = _dict_or_empty(modes.get("offline"))
    online = _dict_or_empty(modes.get("online"))
    active_entry = offline if active_mode == "offline" else online

    runtime["ollama"] = deep_merge_dict(
        copy.deepcopy(MODE_RUNTIME_DEFAULTS["offline"]["ollama"]),
        _dict_or_empty(offline.get("ollama")),
    )
    runtime["api"] = deep_merge_dict(
        copy.deepcopy(MODE_RUNTIME_DEFAULTS["online"]["api"]),
        _dict_or_empty(online.get("api")),
    )
    runtime["retrieval"] = deep_merge_dict(
        _dict_or_empty(runtime.get("retrieval")),
        deep_merge_dict(
            copy.deepcopy(MODE_RUNTIME_DEFAULTS[active_mode]["retrieval"]),
            _dict_or_empty(active_entry.get("retrieval")),
        ),
    )
    runtime["query"] = deep_merge_dict(
        copy.deepcopy(MODE_RUNTIME_DEFAULTS[active_mode]["query"]),
        _dict_or_empty(active_entry.get("query")),
    )
    runtime["paths"] = _merge_path_overrides(
        runtime.get("paths"),
        active_entry.get("paths"),
    )
    runtime.pop("retrieval_online", None)
    return runtime


def _resolve_canonical_key(data: dict[str, Any], key: str) -> str:
    active_mode = resolve_runtime_active_mode(data)
    if key.startswith("api."):
        return "modes.online.api." + key.split(".", 1)[1]
    if key.startswith("ollama."):
        return "modes.offline.ollama." + key.split(".", 1)[1]
    if key.startswith("paths."):
        return f"modes.{active_mode}.paths." + key.split(".", 1)[1]
    if key.startswith("retrieval_online."):
        return "modes.online.retrieval." + key.split(".", 1)[1]
    if key.startswith("retrieval."):
        suffix = key.split(".", 1)[1]
        if suffix.split(".", 1)[0] not in _MODE_RETRIEVAL_KEYS:
            return key
        return f"modes.{active_mode}.retrieval.{suffix}"
    if key.startswith("query."):
        return f"modes.{active_mode}.query." + key.split(".", 1)[1]
    return key


def set_canonical_config_value(
    yaml_data: dict | None,
    key: str,
    value: Any,
) -> dict[str, Any]:
    """Update a config value against the canonical persisted schema."""
    data = canonicalize_config_dict(yaml_data)
    canonical_key = _resolve_canonical_key(data, key)
    target = data
    parts = canonical_key.split(".")
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = copy.deepcopy(value)
    if key.startswith("paths."):
        root_paths = _ensure_dict(data, "paths")
        root_paths[key.split(".", 1)[1]] = copy.deepcopy(value)
    return canonicalize_config_dict(data)
