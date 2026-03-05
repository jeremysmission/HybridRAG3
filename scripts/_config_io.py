#!/usr/bin/env python3
# Shared config I/O helpers for scripts/.
#
# Design goals:
# - Single portable config path resolver
# - Atomic YAML writes (temp + replace)
# - No duplicated path logic across helper scripts

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def project_root() -> Path:
    """Resolve project root from env var with script-relative fallback."""
    env_root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", "").strip()
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    """Absolute path to config/default_config.yaml."""
    return project_root() / "config" / "default_config.yaml"


def load_default_config() -> Dict[str, Any]:
    """Load config/default_config.yaml as a dictionary."""
    path = default_config_path()
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_default_config_atomic(data: Dict[str, Any]) -> Path:
    """Atomically write config/default_config.yaml."""
    path = default_config_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp, path)
    return path
