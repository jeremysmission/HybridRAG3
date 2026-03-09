#!/usr/bin/env python3
# Shared config I/O helpers for scripts/.
#
# Design goals:
# - Single portable config path resolver
# - Atomic YAML writes (temp + replace)
# - No duplicated path logic across helper scripts
# - Primary authority is config/config.yaml

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


def config_path() -> Path:
    """Absolute path to config/config.yaml."""
    return project_root() / "config" / "config.yaml"


def load_primary_config() -> Dict[str, Any]:
    """Load config/config.yaml as a dictionary."""
    path = config_path()
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_primary_config_atomic(data: Dict[str, Any]) -> Path:
    """Atomically write config/config.yaml."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp, path)
    return path


def default_config_path() -> Path:
    """Backward-compatible alias for the primary config path."""
    return config_path()


def load_default_config() -> Dict[str, Any]:
    """Backward-compatible alias for the primary config loader."""
    return load_primary_config()


def save_default_config_atomic(data: Dict[str, Any]) -> Path:
    """Backward-compatible alias for the primary config writer."""
    return save_primary_config_atomic(data)
