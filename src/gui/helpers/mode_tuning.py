from __future__ import annotations

import copy
import os
import threading
from typing import Any

import yaml

_STORE_LOCK = threading.Lock()
_STORE_VERSION = 1

_MODE_KEYS = {
    "offline": (
        "top_k",
        "min_score",
        "hybrid_search",
        "reranker_enabled",
        "reranker_top_n",
        "context_window",
        "num_predict",
        "temperature",
        "timeout_seconds",
        "grounding_bias",
        "reasoning_dial",
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
        "timeout_seconds",
        "grounding_bias",
        "reasoning_dial",
    ),
}

_MODE_DEFAULTS = {
    "offline": {
        "top_k": 5,
        "min_score": 0.10,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "num_predict": 512,
        "temperature": 0.05,
        "timeout_seconds": 180,
        "grounding_bias": 8,
        "reasoning_dial": 2,
    },
    "online": {
        "top_k": 8,
        "min_score": 0.08,
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 128000,
        "max_tokens": 2048,
        "temperature": 0.05,
        "timeout_seconds": 60,
        "grounding_bias": 7,
        "reasoning_dial": 5,
    },
}

_KEY_TYPES = {
    "top_k": int,
    "min_score": float,
    "hybrid_search": bool,
    "reranker_enabled": bool,
    "reranker_top_n": int,
    "context_window": int,
    "num_predict": int,
    "max_tokens": int,
    "temperature": float,
    "timeout_seconds": int,
    "grounding_bias": int,
    "reasoning_dial": int,
}


def _normalize_mode(mode: str) -> str:
    return "online" if str(mode).strip().lower() == "online" else "offline"


def _project_root() -> str:
    return os.path.abspath(os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))


def _store_path() -> str:
    return os.path.join(_project_root(), "config", "mode_tuning.yaml")


def _coerce_value(key: str, value: Any) -> Any:
    caster = _KEY_TYPES.get(key)
    if caster is None:
        return value
    try:
        if caster is bool:
            return bool(value)
        return caster(value)
    except Exception:
        for mode_name, defaults in _MODE_DEFAULTS.items():
            if key in defaults:
                return copy.deepcopy(defaults[key])
        return value


def _new_store() -> dict[str, Any]:
    return {"version": _STORE_VERSION, "modes": {}}


class ModeTuningStore:
    """Persist per-mode tuning values, defaults, and lock state."""

    def __init__(self, root: str | None = None):
        self.root = os.path.abspath(root or _project_root())
        self.path = os.path.join(self.root, "config", "mode_tuning.yaml")

    def load(self) -> dict[str, Any]:
        with _STORE_LOCK:
            if not os.path.isfile(self.path):
                return _new_store()
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception:
                return _new_store()
        if not isinstance(data, dict):
            return _new_store()
        result = _new_store()
        modes = data.get("modes", {})
        if isinstance(modes, dict):
            result["modes"] = modes
        return result

    def save(self, data: dict[str, Any]) -> None:
        cfg_dir = os.path.join(self.root, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        tmp_path = self.path + ".tmp"
        with _STORE_LOCK:
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, self.path)

    def snapshot_config(self, config, mode: str) -> dict[str, Any]:
        mode = _normalize_mode(mode)
        retrieval = getattr(config, "retrieval", None)
        api = getattr(config, "api", None)
        ollama = getattr(config, "ollama", None)
        values = {
            "top_k": getattr(retrieval, "top_k", _MODE_DEFAULTS[mode]["top_k"]),
            "min_score": getattr(retrieval, "min_score", _MODE_DEFAULTS[mode]["min_score"]),
            "hybrid_search": getattr(
                retrieval, "hybrid_search", _MODE_DEFAULTS[mode]["hybrid_search"]
            ),
            "reranker_enabled": getattr(
                retrieval, "reranker_enabled", _MODE_DEFAULTS[mode]["reranker_enabled"]
            ),
            "reranker_top_n": getattr(
                retrieval, "reranker_top_n", _MODE_DEFAULTS[mode]["reranker_top_n"]
            ),
            "grounding_bias": _MODE_DEFAULTS[mode]["grounding_bias"],
            "reasoning_dial": _MODE_DEFAULTS[mode]["reasoning_dial"],
        }
        if mode == "online":
            values.update(
                {
                    "context_window": getattr(
                        api, "context_window", _MODE_DEFAULTS[mode]["context_window"]
                    ),
                    "max_tokens": getattr(api, "max_tokens", _MODE_DEFAULTS[mode]["max_tokens"]),
                    "temperature": getattr(
                        api, "temperature", _MODE_DEFAULTS[mode]["temperature"]
                    ),
                    "timeout_seconds": getattr(
                        api, "timeout_seconds", _MODE_DEFAULTS[mode]["timeout_seconds"]
                    ),
                }
            )
        else:
            values.update(
                {
                    "context_window": getattr(
                        ollama, "context_window", _MODE_DEFAULTS[mode]["context_window"]
                    ),
                    "num_predict": getattr(
                        ollama, "num_predict", _MODE_DEFAULTS[mode]["num_predict"]
                    ),
                    "temperature": getattr(
                        ollama,
                        "temperature",
                        getattr(api, "temperature", _MODE_DEFAULTS[mode]["temperature"]),
                    ),
                    "timeout_seconds": getattr(
                        ollama,
                        "timeout_seconds",
                        _MODE_DEFAULTS[mode]["timeout_seconds"],
                    ),
                }
            )
        return values

    def ensure_mode(self, data: dict[str, Any], config, mode: str) -> dict[str, Any]:
        mode = _normalize_mode(mode)
        modes = data.setdefault("modes", {})
        entry = modes.setdefault(mode, {})
        values = entry.setdefault("values", {})
        defaults = entry.setdefault("defaults", {})
        locks = entry.setdefault("locks", {})
        seed = self.snapshot_config(config, mode)
        for key in _MODE_KEYS[mode]:
            if key not in defaults:
                defaults[key] = copy.deepcopy(seed.get(key, _MODE_DEFAULTS[mode][key]))
            if key not in values:
                values[key] = copy.deepcopy(seed.get(key, defaults[key]))
            if key not in locks:
                locks[key] = False
            defaults[key] = _coerce_value(key, defaults[key])
            values[key] = _coerce_value(key, values[key])
            locks[key] = bool(locks[key])
        return entry

    def get_mode_state(self, config, mode: str) -> dict[str, Any]:
        data = self.load()
        self.ensure_mode(data, config, mode)
        self.save(data)
        return copy.deepcopy(data["modes"][_normalize_mode(mode)])

    def get_active_values(self, config, mode: str) -> dict[str, Any]:
        entry = self.get_mode_state(config, mode)
        active = {}
        for key in _MODE_KEYS[_normalize_mode(mode)]:
            if entry["locks"].get(key):
                active[key] = copy.deepcopy(entry["defaults"][key])
            else:
                active[key] = copy.deepcopy(entry["values"][key])
        return active

    def apply_to_config(self, config, mode: str) -> dict[str, Any]:
        mode = _normalize_mode(mode)
        active = self.get_active_values(config, mode)
        for key, value in active.items():
            self._write_config_value(config, mode, key, value)
        return active

    def update_value(self, config, mode: str, key: str, value: Any) -> None:
        mode = _normalize_mode(mode)
        if key not in _MODE_KEYS[mode]:
            return
        data = self.load()
        entry = self.ensure_mode(data, config, mode)
        entry["values"][key] = _coerce_value(key, value)
        self.save(data)

    def update_default(self, config, mode: str, key: str, value: Any) -> None:
        mode = _normalize_mode(mode)
        if key not in _MODE_KEYS[mode]:
            return
        data = self.load()
        entry = self.ensure_mode(data, config, mode)
        entry["defaults"][key] = _coerce_value(key, value)
        self.save(data)

    def set_lock(self, config, mode: str, key: str, locked: bool) -> None:
        mode = _normalize_mode(mode)
        if key not in _MODE_KEYS[mode]:
            return
        data = self.load()
        entry = self.ensure_mode(data, config, mode)
        entry["locks"][key] = bool(locked)
        self.save(data)

    def is_locked(self, config, mode: str, key: str) -> bool:
        entry = self.get_mode_state(config, mode)
        return bool(entry["locks"].get(key, False))

    def get_active_value(self, config, mode: str, key: str, fallback: Any = None) -> Any:
        active = self.get_active_values(config, mode)
        if key in active:
            return active[key]
        return fallback

    def save_mode_defaults_from_values(self, config, mode: str) -> None:
        mode = _normalize_mode(mode)
        data = self.load()
        entry = self.ensure_mode(data, config, mode)
        for key in _MODE_KEYS[mode]:
            entry["defaults"][key] = copy.deepcopy(entry["values"][key])
        self.save(data)

    def reset_mode_to_defaults(self, config, mode: str) -> dict[str, Any]:
        mode = _normalize_mode(mode)
        data = self.load()
        entry = self.ensure_mode(data, config, mode)
        for key in _MODE_KEYS[mode]:
            entry["values"][key] = copy.deepcopy(entry["defaults"][key])
        self.save(data)
        return self.apply_to_config(config, mode)

    def _write_config_value(self, config, mode: str, key: str, value: Any) -> None:
        retrieval = getattr(config, "retrieval", None)
        api = getattr(config, "api", None)
        ollama = getattr(config, "ollama", None)
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


def apply_mode_settings_to_config(config, mode: str) -> dict[str, Any]:
    return ModeTuningStore().apply_to_config(config, mode)


def mode_setting_locked(config, mode: str, key: str) -> bool:
    return ModeTuningStore().is_locked(config, mode, key)


def update_mode_setting(config, mode: str, key: str, value: Any) -> None:
    ModeTuningStore().update_value(config, mode, key, value)
