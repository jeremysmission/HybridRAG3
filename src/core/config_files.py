from __future__ import annotations

import copy
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml


PRIMARY_CONFIG_NAME = "config.yaml"
USER_MODES_NAME = "user_modes.yaml"
LEGACY_DEFAULT_CONFIG_NAME = "default_config.yaml"
LEGACY_OVERRIDES_NAME = "user_overrides.yaml"
_PRIMARY_AUTHORITY_ALIASES = {
    PRIMARY_CONFIG_NAME,
    LEGACY_DEFAULT_CONFIG_NAME,
    LEGACY_OVERRIDES_NAME,
}
_SAVE_RETRIES = 5
_SAVE_RETRY_DELAY_SECONDS = 0.05


def project_root_path(project_dir: str = ".") -> Path:
    return Path(project_dir).resolve()


def config_dir_path(project_dir: str = ".") -> Path:
    return project_root_path(project_dir) / "config"


def primary_config_path(project_dir: str = ".") -> Path:
    return config_dir_path(project_dir) / PRIMARY_CONFIG_NAME


def user_modes_path(project_dir: str = ".") -> Path:
    return config_dir_path(project_dir) / USER_MODES_NAME


def legacy_default_config_path(project_dir: str = ".") -> Path:
    return config_dir_path(project_dir) / LEGACY_DEFAULT_CONFIG_NAME


def legacy_overrides_path(project_dir: str = ".") -> Path:
    return config_dir_path(project_dir) / LEGACY_OVERRIDES_NAME


def read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    return raw if isinstance(raw, dict) else {}


def write_yaml_dict(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)

    for attempt in range(_SAVE_RETRIES):
        tmp_fd = None
        tmp_path: Path | None = None
        try:
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=f"{path.name}.",
                suffix=".tmp",
                dir=str(path.parent),
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as stream:
                tmp_fd = None
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_path, path)
            return path
        except PermissionError:
            if tmp_fd is not None:
                os.close(tmp_fd)
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if attempt >= (_SAVE_RETRIES - 1):
                raise
            time.sleep(_SAVE_RETRY_DELAY_SECONDS * (attempt + 1))
        except Exception:
            if tmp_fd is not None:
                os.close(tmp_fd)
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    return path


def deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_requested_config_name(config_filename: str | None) -> str:
    raw = (config_filename or "").strip()
    if not raw:
        return PRIMARY_CONFIG_NAME
    return Path(raw).name


def load_primary_config_dict(
    project_dir: str = ".",
    config_filename: str | None = None,
) -> dict[str, Any]:
    """Load config data without implicit legacy fallback.

    `config/config.yaml` is the only implicit authority. Legacy filenames
    remain readable only when they are requested explicitly, which keeps
    older tools/tests usable without letting runtime silently drift back to
    `default_config.yaml` or `user_overrides.yaml`.
    """
    raw = (config_filename or "").strip()
    explicit_path = Path(raw) if raw else None
    requested = normalize_requested_config_name(config_filename)
    cfg_dir = config_dir_path(project_dir)
    primary_path = primary_config_path(project_dir)
    requested_path = cfg_dir / requested

    if primary_path.exists() and requested in _PRIMARY_AUTHORITY_ALIASES:
        return read_yaml_dict(primary_path)

    if explicit_path and explicit_path.is_file():
        return read_yaml_dict(explicit_path)

    if requested_path.exists():
        return read_yaml_dict(requested_path)

    if primary_path.exists():
        return read_yaml_dict(primary_path)

    return {}


def save_primary_config_dict(project_dir: str, data: dict[str, Any]) -> Path:
    return write_yaml_dict(primary_config_path(project_dir), data)
