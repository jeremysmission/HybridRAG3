from __future__ import annotations

import copy
from typing import Any

from .config_files import (
    config_dir_path,
    deep_merge_dict,
    read_yaml_dict,
    user_modes_path,
    write_yaml_dict,
)


def _checked_tree_from_values(values: Any) -> Any:
    if not isinstance(values, dict):
        return True
    return {key: _checked_tree_from_values(value) for key, value in values.items()}


def _profile_entry(label: str, notes: str, values: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "notes": notes,
        "values": copy.deepcopy(values),
        "checked": _checked_tree_from_values(values),
    }


_DEFAULT_USER_MODES = {
    "active_profile": "",
    "profiles": {
        "laptop_safe": _profile_entry(
            "Laptop Safe",
            "Conservative laptop profile",
            {
                "embedding": {
                    "model_name": "nomic-embed-text",
                    "dimension": 768,
                    "batch_size": 16,
                    "device": "cpu",
                },
                "chunking": {
                    "chunk_size": 1200,
                    "overlap": 200,
                },
                "indexing": {
                    "block_chars": 200000,
                    "max_chars_per_file": 2000000,
                },
                "performance": {
                    "max_concurrent_files": 1,
                    "gc_between_files": True,
                    "gc_between_blocks": True,
                },
                "modes": {
                    "offline": {
                        "ollama": {
                            "model": "phi4-mini",
                            "context_window": 4096,
                        },
                        "retrieval": {
                            "reranker_top_n": 20,
                        },
                    },
                    "online": {
                        "api": {
                            "model": "gpt-4o",
                            "deployment": "gpt-4o",
                            "context_window": 128000,
                            "max_tokens": 1024,
                        },
                        "retrieval": {
                            "reranker_top_n": 20,
                        },
                    },
                },
            },
        ),
        "desktop_power": _profile_entry(
            "Desktop Power",
            "Balanced desktop/workstation profile",
            {
                "embedding": {
                    "model_name": "nomic-embed-text",
                    "dimension": 768,
                    "batch_size": 64,
                    "device": "cuda",
                },
                "chunking": {
                    "chunk_size": 1200,
                    "overlap": 200,
                },
                "indexing": {
                    "block_chars": 500000,
                    "max_chars_per_file": 5000000,
                },
                "performance": {
                    "max_concurrent_files": 2,
                    "gc_between_files": False,
                    "gc_between_blocks": False,
                },
                "modes": {
                    "offline": {
                        "ollama": {
                            "model": "phi4:14b-q4_K_M",
                            "context_window": 4096,
                        },
                        "retrieval": {
                            "reranker_top_n": 20,
                        },
                    },
                    "online": {
                        "api": {
                            "model": "gpt-4o",
                            "deployment": "gpt-4o",
                            "context_window": 128000,
                            "max_tokens": 1024,
                        },
                        "retrieval": {
                            "reranker_top_n": 20,
                        },
                    },
                },
            },
        ),
        "server_max": _profile_entry(
            "Server Max",
            "High-end workstation/server profile",
            {
                "embedding": {
                    "model_name": "nomic-embed-text",
                    "dimension": 768,
                    "batch_size": 128,
                    "device": "cuda",
                },
                "chunking": {
                    "chunk_size": 1200,
                    "overlap": 200,
                },
                "indexing": {
                    "block_chars": 1000000,
                    "max_chars_per_file": 10000000,
                },
                "performance": {
                    "max_concurrent_files": 4,
                    "gc_between_files": False,
                    "gc_between_blocks": False,
                },
                "modes": {
                    "offline": {
                        "ollama": {
                            "model": "phi4:14b-q4_K_M",
                            "context_window": 4096,
                        },
                        "retrieval": {
                            "reranker_top_n": 30,
                        },
                    },
                    "online": {
                        "api": {
                            "model": "gpt-4o",
                            "deployment": "gpt-4o",
                            "context_window": 128000,
                            "max_tokens": 2048,
                        },
                        "retrieval": {
                            "reranker_top_n": 30,
                        },
                    },
                },
            },
        ),
    },
}


def _normalize_checked_tree(values: Any, checked: Any) -> Any:
    if not isinstance(values, dict):
        return bool(checked)
    if checked is True:
        return _checked_tree_from_values(values)
    checked_dict = checked if isinstance(checked, dict) else {}
    return {
        key: _normalize_checked_tree(value, checked_dict.get(key, False))
        for key, value in values.items()
    }


def _apply_checked_values(values: Any, checked: Any) -> Any:
    if not isinstance(values, dict):
        return copy.deepcopy(values) if bool(checked) else None
    if checked is True:
        return copy.deepcopy(values)
    checked_dict = checked if isinstance(checked, dict) else {}
    result: dict[str, Any] = {}
    for key, value in values.items():
        filtered = _apply_checked_values(value, checked_dict.get(key, False))
        if filtered is None:
            continue
        if isinstance(filtered, dict) and not filtered:
            continue
        result[key] = filtered
    return result


def _normalize_profile_entry(entry: dict[str, Any], name: str) -> dict[str, Any]:
    raw_values = entry.get("values")
    if not isinstance(raw_values, dict):
        raw_values = entry.get("overrides", {})
    values = copy.deepcopy(raw_values) if isinstance(raw_values, dict) else {}
    checked_seed = entry["checked"] if "checked" in entry else True
    checked = _normalize_checked_tree(values, checked_seed)
    normalized = {
        "label": str(entry.get("label", name.replace("_", " ").title()) or name.replace("_", " ").title()),
        "notes": str(entry.get("notes", "") or ""),
        "values": values,
        "checked": checked,
    }
    normalized["overrides"] = _apply_checked_values(values, checked) or {}
    return normalized


def _migrate_legacy_profiles(project_dir: str) -> dict[str, Any]:
    legacy_path = config_dir_path(project_dir) / "profiles.yaml"
    legacy_data = read_yaml_dict(legacy_path)
    if not legacy_data:
        return copy.deepcopy(_DEFAULT_USER_MODES)

    profiles = {}
    for name, profile_data in legacy_data.items():
        if not isinstance(profile_data, dict):
            continue
        overrides = copy.deepcopy(profile_data)
        label = name.replace("_", " ").title()
        notes = str(overrides.pop("notes", "") or "")
        profiles[name] = _normalize_profile_entry(
            {"label": label, "notes": notes, "values": overrides, "checked": True},
            name,
        )

    if not profiles:
        return copy.deepcopy(_DEFAULT_USER_MODES)

    result = copy.deepcopy(_DEFAULT_USER_MODES)
    result["profiles"] = profiles
    return result


def load_user_modes_data(project_dir: str = ".") -> dict[str, Any]:
    path = user_modes_path(project_dir)
    if path.exists():
        data = read_yaml_dict(path)
    else:
        data = _migrate_legacy_profiles(project_dir)

    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
    normalized_profiles = {
        name: _normalize_profile_entry(entry if isinstance(entry, dict) else {}, name)
        for name, entry in profiles.items()
    }
    return {
        "active_profile": str(data.get("active_profile", "") or ""),
        "profiles": normalized_profiles,
    }


def save_user_modes_data(project_dir: str, data: dict[str, Any]) -> None:
    normalized = load_user_modes_data(project_dir)
    normalized["active_profile"] = str(data.get("active_profile", "") or "")
    raw_profiles = data.get("profiles", {})
    if isinstance(raw_profiles, dict):
        normalized["profiles"] = {
            name: _normalize_profile_entry(entry if isinstance(entry, dict) else {}, name)
            for name, entry in raw_profiles.items()
        }
    persisted = {
        "active_profile": normalized["active_profile"],
        "profiles": {},
    }
    for name, entry in normalized["profiles"].items():
        persisted["profiles"][name] = {
            "label": entry["label"],
            "notes": entry["notes"],
            "values": copy.deepcopy(entry.get("values", {})),
            "checked": copy.deepcopy(entry.get("checked", {})),
        }
    write_yaml_dict(user_modes_path(project_dir), persisted)


def list_profile_names(project_dir: str = ".") -> list[str]:
    data = load_user_modes_data(project_dir)
    return list(data.get("profiles", {}).keys())


def active_profile_name(project_dir: str = ".") -> str:
    data = load_user_modes_data(project_dir)
    return str(data.get("active_profile", "") or "")


def profile_overrides(data: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        return {}
    entry = profiles.get(profile_name, {})
    if not isinstance(entry, dict):
        return {}
    overrides = entry.get("overrides", {})
    return copy.deepcopy(overrides) if isinstance(overrides, dict) else {}


def apply_active_profile_overlay(
    base_data: dict[str, Any],
    user_modes_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if not user_modes_data:
        return copy.deepcopy(base_data)
    active = str(user_modes_data.get("active_profile", "") or "").strip()
    if not active:
        return copy.deepcopy(base_data)
    overlay = profile_overrides(user_modes_data, active)
    if not overlay:
        return copy.deepcopy(base_data)
    result = deep_merge_dict(base_data, overlay)
    result["active_profile"] = active
    return result


def set_active_profile(project_dir: str, profile_name: str) -> None:
    data = load_user_modes_data(project_dir)
    active = (profile_name or "").strip()
    if active and active not in data.get("profiles", {}):
        raise KeyError(f"Unknown profile: {active}")
    data["active_profile"] = active
    save_user_modes_data(project_dir, data)
