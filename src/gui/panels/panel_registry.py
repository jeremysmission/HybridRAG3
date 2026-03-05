# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the panel registry part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Registry for discovering, registering, and lazy-loading GUI panels
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Any, List, Dict
from src.gui.panels.panel_keys import (
    VIEW_QUERY, VIEW_DATA, VIEW_INDEX, VIEW_TUNING, VIEW_COST,
    VIEW_ADMIN, VIEW_REFERENCE, VIEW_SETTINGS,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PanelSpec:
    """Immutable descriptor for a GUI panel.

    key:   Internal routing key (must be unique across registry).
    label: Human-readable tab label shown in NavBar.
    module_path: Dotted import path (e.g., "src.gui.panels.query_panel").
    class_name:  Class or factory to import from *module_path*.
    enabled: False means the panel is registered but grayed out.
    """
    key: str
    label: str
    module_path: str
    class_name: str
    enabled: bool = True


def _has_module(module_path: str) -> bool:
    """Return True if *module_path* can be imported without error."""
    try:
        __import__(module_path, fromlist=["__name__"])
        return True
    except Exception:
        return False


def _import_attr(module_path: str, attr: str) -> Any:
    """Import *attr* from *module_path* lazily."""
    mod = __import__(module_path, fromlist=[attr])
    return getattr(mod, attr)


def _safe_panel(
    key: str, label: str, module_path: str, class_name: str,
) -> Optional[PanelSpec]:
    """Create a PanelSpec only if the module exists."""
    if _has_module(module_path):
        return PanelSpec(key, label, module_path, class_name)
    logger.info("[INFO] Panel '%s' skipped -- module %s not found", key, module_path)
    return None


# ---------------------------------------------------------------
# REGISTRY -- single source of truth for panel order and identity
# ---------------------------------------------------------------

_PANEL_DEFS: List[Dict[str, Any]] = [
    {"key": VIEW_QUERY,   "label": "Query",     "module": "src.gui.panels.query_panel",      "cls": "QueryPanel"},
    {"key": VIEW_DATA,    "label": "Downloader (Data)", "module": "src.gui.panels.data_panel", "cls": "DataPanel", "optional": True},
    {"key": VIEW_INDEX,   "label": "Index",     "module": "src.gui.panels.index_panel",       "cls": "IndexPanel"},
    {"key": VIEW_TUNING,  "label": "Tuning",    "module": "src.gui.panels.tuning_tab",        "cls": "TuningTab"},
    {"key": VIEW_COST,    "label": "Cost",      "module": "src.gui.panels.cost_dashboard",    "cls": "CostDashboard"},
    {"key": VIEW_ADMIN,   "label": "Admin",     "module": "src.gui.panels.api_admin_tab",     "cls": "ApiAdminTab"},
    {"key": VIEW_REFERENCE, "label": "Reference", "module": "src.gui.panels.reference_panel",   "cls": "ReferencePanel"},
    {"key": VIEW_SETTINGS,"label": "Settings",  "module": "src.gui.panels.settings_panel",    "cls": "SettingsPanel"},
]


def get_panels() -> List[PanelSpec]:
    """Return the ordered list of available panels.

    Optional panels (e.g., Data) are omitted if their module is missing.
    Enforces unique keys -- duplicates are logged and dropped.
    """
    panels: List[PanelSpec] = []
    seen_keys: set = set()

    for defn in _PANEL_DEFS:
        key = defn["key"]

        # Uniqueness guard
        if key in seen_keys:
            logger.warning("[WARN] Duplicate panel key '%s' -- skipped", key)
            continue

        if defn.get("optional"):
            spec = _safe_panel(key, defn["label"], defn["module"], defn["cls"])
            if spec is None:
                continue
        else:
            spec = PanelSpec(key, defn["label"], defn["module"], defn["cls"])

        panels.append(spec)
        seen_keys.add(key)

    return panels


def get_panel(key: str) -> Optional[PanelSpec]:
    """Return the PanelSpec for *key*, or None if not registered."""
    for p in get_panels():
        if p.key == key:
            return p
    return None


def validate_unique_keys() -> List[str]:
    """Return list of duplicate keys (empty = valid)."""
    keys = [p.key for p in get_panels()]
    seen = set()
    dupes = []
    for k in keys:
        if k in seen:
            dupes.append(k)
        seen.add(k)
    return dupes
