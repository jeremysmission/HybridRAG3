from __future__ import annotations

import copy
import os
import threading
from datetime import datetime
from typing import Any

import yaml

from src.core.mode_config import (
    MODE_BACKEND_SECTION,
    MODE_LEGACY_KEY_ALIASES,
    MODE_RUNTIME_DEFAULTS,
    MODE_TUNED_DEFAULTS,
    MODE_TUNING_KEYS,
    mode_entry_to_flat_values,
    normalize_mode,
    set_mode_value,
    snapshot_mode_entry,
    update_mode_section as update_mode_section_entry,
)

_STORE_LOCK = threading.Lock()
_STORE_VERSION = 2


def _project_root() -> str:
    return os.path.abspath(os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))


def _store_path(root: str) -> str:
    return os.path.join(root, "config", "user_overrides.yaml")


def _legacy_store_path(root: str) -> str:
    return os.path.join(root, "config", "mode_tuning.yaml")


def _load_yaml(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_yaml(path: str, data: dict[str, Any]) -> None:
    cfg_dir = os.path.dirname(path)
    os.makedirs(cfg_dir, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp_path, path)


def _legacy_reasoning_to_open_knowledge(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return bool(value)


def _coerce_default(key: str, value: Any, mode: str) -> Any:
    default = MODE_TUNED_DEFAULTS[normalize_mode(mode)].get(key)
    if default is None:
        return value
    try:
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        return type(default)(value)
    except Exception:
        return copy.deepcopy(default)


def _new_mode_entry(mode: str) -> dict[str, Any]:
    mode = normalize_mode(mode)
    return {
        **copy.deepcopy(MODE_RUNTIME_DEFAULTS[mode]),
        "defaults": copy.deepcopy(MODE_TUNED_DEFAULTS[mode]),
        "locks": {key: False for key in MODE_TUNING_KEYS[mode]},
    }


class ModeTuningStore:
    """Persist per-mode values/defaults/locks inside config/user_overrides.yaml."""

    def __init__(self, root: str | None = None):
        self.root = os.path.abspath(root or _project_root())
        self.path = _store_path(self.root)
        self.legacy_path = _legacy_store_path(self.root)

    def _load_root(self) -> dict[str, Any]:
        with _STORE_LOCK:
            data = _load_yaml(self.path)
        return data

    def _save_root(self, root_data: dict[str, Any]) -> None:
        with _STORE_LOCK:
            _save_yaml(self.path, root_data)

    def _load_legacy_modes(self) -> dict[str, Any]:
        legacy = _load_yaml(self.legacy_path)
        modes = legacy.get("modes", {}) if isinstance(legacy, dict) else {}
        return modes if isinstance(modes, dict) else {}

    def _migrate_legacy_entry(self, entry: dict[str, Any], mode: str) -> None:
        mode = normalize_mode(mode)
        flat_values = mode_entry_to_flat_values(mode, entry)
        for key in MODE_TUNING_KEYS[mode]:
            set_mode_value(entry, mode, key, flat_values[key])

        defaults = entry.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
            entry["defaults"] = defaults
        locks = entry.get("locks", {})
        if not isinstance(locks, dict):
            locks = {}
            entry["locks"] = locks

        for legacy_key, target_key in MODE_LEGACY_KEY_ALIASES.items():
            if target_key not in defaults and legacy_key in defaults:
                defaults[target_key] = _legacy_reasoning_to_open_knowledge(defaults[legacy_key])
            if target_key not in locks and legacy_key in locks:
                locks[target_key] = bool(locks[legacy_key])

        for key in MODE_TUNING_KEYS[mode]:
            if key not in defaults:
                defaults[key] = copy.deepcopy(MODE_TUNED_DEFAULTS[mode][key])
            defaults[key] = _coerce_default(key, defaults[key], mode)
            locks[key] = bool(locks.get(key, False))

        entry.pop("values", None)
        for legacy_key in MODE_LEGACY_KEY_ALIASES:
            defaults.pop(legacy_key, None)
            locks.pop(legacy_key, None)

    def _ensure_mode_entry(self, root_data: dict[str, Any], config, mode: str) -> dict[str, Any]:
        mode = normalize_mode(mode)
        root_data.setdefault("mode_store_version", _STORE_VERSION)
        modes = root_data.setdefault("modes", {})
        if not isinstance(modes, dict):
            modes = {}
            root_data["modes"] = modes

        entry = modes.get(mode)
        if not isinstance(entry, dict):
            legacy_modes = self._load_legacy_modes()
            legacy_entry = legacy_modes.get(mode)
            if isinstance(legacy_entry, dict):
                entry = copy.deepcopy(legacy_entry)
            else:
                current_mode = normalize_mode(getattr(config, "mode", mode))
                if not modes and mode == current_mode:
                    entry = snapshot_mode_entry(config, mode)
                    entry["defaults"] = copy.deepcopy(mode_entry_to_flat_values(mode, entry))
                    entry["locks"] = {key: False for key in MODE_TUNING_KEYS[mode]}
                else:
                    entry = _new_mode_entry(mode)
            modes[mode] = entry

        self._migrate_legacy_entry(entry, mode)

        backend_name = MODE_BACKEND_SECTION[mode]
        if "retrieval" not in entry or not isinstance(entry["retrieval"], dict):
            entry["retrieval"] = copy.deepcopy(MODE_RUNTIME_DEFAULTS[mode]["retrieval"])
        if backend_name not in entry or not isinstance(entry[backend_name], dict):
            entry[backend_name] = copy.deepcopy(MODE_RUNTIME_DEFAULTS[mode][backend_name])
        if "query" not in entry or not isinstance(entry["query"], dict):
            entry["query"] = copy.deepcopy(MODE_RUNTIME_DEFAULTS[mode]["query"])

        return entry

    def load(self) -> dict[str, Any]:
        root_data = self._load_root()
        modes = root_data.get("modes", {})
        if not isinstance(modes, dict):
            modes = {}
        return {
            "version": int(root_data.get("mode_store_version", _STORE_VERSION) or _STORE_VERSION),
            "modes": copy.deepcopy(modes),
        }

    def save(self, data: dict[str, Any]) -> None:
        root_data = self._load_root()
        root_data["mode_store_version"] = int(data.get("version", _STORE_VERSION) or _STORE_VERSION)
        root_data["modes"] = copy.deepcopy(data.get("modes", {}))
        self._save_root(root_data)

    def snapshot_config(self, config, mode: str) -> dict[str, Any]:
        entry = snapshot_mode_entry(config, mode)
        return mode_entry_to_flat_values(mode, entry)

    def get_mode_state(self, config, mode: str) -> dict[str, Any]:
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        self._save_root(root_data)
        mode = normalize_mode(mode)
        return {
            "values": mode_entry_to_flat_values(mode, entry),
            "defaults": copy.deepcopy(entry.get("defaults", {})),
            "locks": copy.deepcopy(entry.get("locks", {})),
        }

    def get_active_values(self, config, mode: str) -> dict[str, Any]:
        state = self.get_mode_state(config, mode)
        mode = normalize_mode(mode)
        active = {}
        for key in MODE_TUNING_KEYS[mode]:
            if state["locks"].get(key):
                active[key] = copy.deepcopy(state["defaults"][key])
            else:
                active[key] = copy.deepcopy(state["values"][key])
        return active

    def apply_to_config(self, config, mode: str) -> dict[str, Any]:
        mode = normalize_mode(mode)
        active = self.get_active_values(config, mode)
        for key, value in active.items():
            self._write_config_value(config, mode, key, value)
        return active

    def update_value(self, config, mode: str, key: str, value: Any) -> None:
        mode = normalize_mode(mode)
        if key not in MODE_TUNING_KEYS[mode]:
            return
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        set_mode_value(entry, mode, key, value)
        self._save_root(root_data)

    def update_default(self, config, mode: str, key: str, value: Any) -> None:
        mode = normalize_mode(mode)
        if key not in MODE_TUNING_KEYS[mode]:
            return
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        entry["defaults"][key] = _coerce_default(key, value, mode)
        self._save_root(root_data)

    def set_lock(self, config, mode: str, key: str, locked: bool) -> None:
        mode = normalize_mode(mode)
        if key not in MODE_TUNING_KEYS[mode]:
            return
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        entry["locks"][key] = bool(locked)
        self._save_root(root_data)

    def is_locked(self, config, mode: str, key: str) -> bool:
        return bool(self.get_mode_state(config, mode)["locks"].get(key, False))

    def get_active_value(self, config, mode: str, key: str, fallback: Any = None) -> Any:
        active = self.get_active_values(config, mode)
        return copy.deepcopy(active[key]) if key in active else fallback

    def save_mode_defaults_from_values(self, config, mode: str) -> None:
        mode = normalize_mode(mode)
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        values = mode_entry_to_flat_values(mode, entry)
        for key in MODE_TUNING_KEYS[mode]:
            entry["defaults"][key] = copy.deepcopy(values[key])
        self._save_root(root_data)

    def save_admin_defaults(self, config) -> dict[str, Any]:
        """Persist admin defaults into user_overrides.yaml.

        This keeps the admin save/restore flow on the same YAML path used
        by mode tuning instead of maintaining a separate JSON snapshot file.
        """
        root_data = self._load_root()
        current_mode = normalize_mode(getattr(config, "mode", "offline"))
        current_entry = self._ensure_mode_entry(root_data, config, current_mode)
        live_entry = snapshot_mode_entry(config, current_mode)
        for section_name in ("retrieval", MODE_BACKEND_SECTION[current_mode], "query"):
            section_value = live_entry.get(section_name, {})
            if isinstance(section_value, dict):
                current_entry[section_name] = copy.deepcopy(section_value)

        offline_entry = self._ensure_mode_entry(root_data, config, "offline")
        online_entry = self._ensure_mode_entry(root_data, config, "online")
        api = getattr(config, "api", None)
        if api is not None:
            for key in ("model", "deployment", "context_window", "max_tokens", "temperature", "timeout_seconds"):
                if hasattr(api, key):
                    online_entry.setdefault("api", {})[key] = copy.deepcopy(getattr(api, key))
        ollama = getattr(config, "ollama", None)
        if ollama is not None:
            for key in ("model", "base_url", "context_window", "num_predict", "temperature", "timeout_seconds"):
                if hasattr(ollama, key):
                    offline_entry.setdefault("ollama", {})[key] = copy.deepcopy(getattr(ollama, key))

        paths = getattr(config, "paths", None)
        chunking = getattr(config, "chunking", None)
        snapshot = {
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": current_mode,
            "paths": {
                "source_folder": getattr(paths, "source_folder", "") if paths else "",
                "database": getattr(paths, "database", "") if paths else "",
                "embeddings_cache": getattr(paths, "embeddings_cache", "") if paths else "",
            },
            "chunking": {
                "chunk_size": getattr(chunking, "chunk_size", 1200),
                "overlap": getattr(chunking, "overlap", 200),
            },
        }
        root_data["admin_defaults"] = copy.deepcopy(snapshot)
        root_data["mode"] = current_mode
        root_data.setdefault("paths", {}).update(copy.deepcopy(snapshot["paths"]))
        root_data.setdefault("chunking", {}).update(copy.deepcopy(snapshot["chunking"]))
        for mode_key in ("offline", "online"):
            entry = self._ensure_mode_entry(root_data, config, mode_key)
            values = mode_entry_to_flat_values(mode_key, entry)
            for key in MODE_TUNING_KEYS[mode_key]:
                entry["defaults"][key] = copy.deepcopy(values[key])
        self._save_root(root_data)
        return snapshot

    def get_admin_defaults(self) -> dict[str, Any] | None:
        root_data = self._load_root()
        snapshot = root_data.get("admin_defaults")
        return copy.deepcopy(snapshot) if isinstance(snapshot, dict) else None

    def restore_admin_defaults(self, config) -> dict[str, Any] | None:
        """Restore admin defaults from user_overrides.yaml into live config."""
        root_data = self._load_root()
        snapshot = root_data.get("admin_defaults")
        if not isinstance(snapshot, dict):
            return None

        restored_mode = normalize_mode(snapshot.get("mode", getattr(config, "mode", "offline")))
        setattr(config, "mode", restored_mode)
        root_data["mode"] = restored_mode

        paths = getattr(config, "paths", None)
        if paths is not None:
            root_paths = root_data.setdefault("paths", {})
            for key, value in snapshot.get("paths", {}).items():
                setattr(paths, key, value)
                root_paths[key] = copy.deepcopy(value)

        chunking = getattr(config, "chunking", None)
        if chunking is not None:
            root_chunking = root_data.setdefault("chunking", {})
            for key, value in snapshot.get("chunking", {}).items():
                setattr(chunking, key, value)
                root_chunking[key] = copy.deepcopy(value)

        for mode_key in ("offline", "online"):
            entry = self._ensure_mode_entry(root_data, config, mode_key)
            for key in MODE_TUNING_KEYS[mode_key]:
                if key in entry.get("defaults", {}):
                    set_mode_value(entry, mode_key, key, entry["defaults"][key])

        offline_entry = self._ensure_mode_entry(root_data, config, "offline")
        online_entry = self._ensure_mode_entry(root_data, config, "online")

        ollama = getattr(config, "ollama", None)
        if ollama is not None:
            for key, value in offline_entry.get("ollama", {}).items():
                if hasattr(ollama, key):
                    setattr(ollama, key, copy.deepcopy(value))

        api = getattr(config, "api", None)
        if api is not None:
            for key, value in online_entry.get("api", {}).items():
                if hasattr(api, key):
                    setattr(api, key, copy.deepcopy(value))

        self._save_root(root_data)
        self.apply_to_config(config, restored_mode)
        return copy.deepcopy(snapshot)

    def reset_mode_to_defaults(self, config, mode: str) -> dict[str, Any]:
        mode = normalize_mode(mode)
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        for key in MODE_TUNING_KEYS[mode]:
            set_mode_value(entry, mode, key, entry["defaults"][key])
        self._save_root(root_data)
        return self.apply_to_config(config, mode)

    def update_mode_section(self, config, mode: str, section: str, key: str, value: Any) -> None:
        mode = normalize_mode(mode)
        root_data = self._load_root()
        entry = self._ensure_mode_entry(root_data, config, mode)
        update_mode_section_entry(entry, mode, section, key, value)
        self._save_root(root_data)

    def _write_config_value(self, config, mode: str, key: str, value: Any) -> None:
        retrieval = getattr(config, "retrieval", None)
        api = getattr(config, "api", None)
        ollama = getattr(config, "ollama", None)
        query = getattr(config, "query", None)
        if key == "top_k" and retrieval is not None:
            retrieval.top_k = int(value)
        elif key == "min_score" and retrieval is not None:
            retrieval.min_score = float(value)
        elif key == "hybrid_search" and retrieval is not None:
            retrieval.hybrid_search = bool(value)
        elif key == "reranker_enabled" and retrieval is not None:
            retrieval.reranker_enabled = bool(value)
        elif key == "reranker_top_n" and retrieval is not None:
            retrieval.reranker_top_n = int(value)
        elif key == "context_window":
            if mode == "online" and api is not None:
                api.context_window = int(value)
            elif mode == "offline" and ollama is not None:
                ollama.context_window = int(value)
        elif key == "num_predict" and ollama is not None:
            ollama.num_predict = int(value)
        elif key == "max_tokens" and api is not None:
            api.max_tokens = int(value)
        elif key == "temperature":
            if mode == "online" and api is not None:
                api.temperature = float(value)
            elif mode == "offline":
                if ollama is not None and hasattr(ollama, "temperature"):
                    ollama.temperature = float(value)
                elif api is not None:
                    api.temperature = float(value)
        elif key == "timeout_seconds":
            if mode == "online" and api is not None:
                api.timeout_seconds = int(value)
            elif mode == "offline" and ollama is not None:
                ollama.timeout_seconds = int(value)
        elif key == "grounding_bias":
            if query is None:
                from types import SimpleNamespace

                query = SimpleNamespace()
                setattr(config, "query", query)
            query.grounding_bias = int(value)
        elif key == "allow_open_knowledge":
            if query is None:
                from types import SimpleNamespace

                query = SimpleNamespace()
                setattr(config, "query", query)
            query.allow_open_knowledge = bool(value)

        if key in ("grounding_bias", "allow_open_knowledge"):
            try:
                from src.core.query_mode import apply_query_mode_to_config

                apply_query_mode_to_config(config)
            except Exception:
                pass


def apply_mode_settings_to_config(config, mode: str) -> dict[str, Any]:
    return ModeTuningStore().apply_to_config(config, mode)


def mode_setting_locked(config, mode: str, key: str) -> bool:
    return ModeTuningStore().is_locked(config, mode, key)


def update_mode_setting(config, mode: str, key: str, value: Any) -> None:
    ModeTuningStore().update_value(config, mode, key, value)


def update_mode_section(config, mode: str, section: str, key: str, value: Any) -> None:
    ModeTuningStore().update_mode_section(config, mode, section, key, value)
