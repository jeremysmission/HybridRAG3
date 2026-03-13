"""Canonical panel/view keys and normalization helpers."""

from __future__ import annotations

VIEW_QUERY = "query"
VIEW_DATA = "data"
VIEW_INDEX = "index"
VIEW_TUNING = "tuning"
VIEW_COST = "cost"
VIEW_ADMIN = "admin"
VIEW_REFERENCE = "reference"
VIEW_SETTINGS = "settings"
VIEW_COMMANDS = "commands"

_ALIASES = {
    "tuning": VIEW_ADMIN,
    "ref": VIEW_REFERENCE,
    "command-center": VIEW_COMMANDS,
    "cli": VIEW_COMMANDS,
    "toolbox": VIEW_COMMANDS,
}


def normalize_view_key(name: str) -> str:
    """Return canonical view key, preserving unknown keys as-is."""
    key = str(name or "").strip().lower()
    if not key:
        return key
    return _ALIASES.get(key, key)
