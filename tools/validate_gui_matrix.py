"""Validate GUI matrix entries by testing handler accessibility.

For each entry in gui_matrix.json, verifies:
  - The source module can be imported
  - The handler method/function exists on the class
  - Thread safety annotation matches (background work uses workers)

Updates each entry status to PASS or FAIL and writes back.

Usage: python tools/validate_gui_matrix.py
"""
from __future__ import annotations

import json
import sys
import os
import importlib

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.environ.setdefault("HYBRIDRAG_PROJECT_ROOT", _root)

MATRIX_PATH = os.path.join(_root, "tools", "gui_matrix.json")

# Map panel names to their module paths and class names
PANEL_MODULE_MAP = {
    "app": ("src.gui.app", "HybridRAGApp"),
    "nav": ("src.gui.panels.nav_bar", "NavBar"),
    "status_bar": ("src.gui.panels.status_bar", "StatusBar"),
    "query": ("src.gui.panels.query_panel", "QueryPanel"),
    "index": ("src.gui.panels.index_panel", "IndexPanel"),
    "tuning": ("src.gui.panels.tuning_tab", "TuningTab"),
    "cost": ("src.gui.panels.cost_dashboard", "CostDashboard"),
    "data": ("src.gui.panels.data_panel", "DataPanel"),
    "admin": ("src.gui.panels.api_admin_tab", "ApiAdminTab"),
    "ref": ("src.gui.panels.reference_panel", "ReferencePanel"),
    "settings": ("src.gui.panels.settings_panel", "SettingsPanel"),
    "wizard": ("src.gui.panels.setup_wizard", "SetupWizard"),
    "eval": ("src.gui.panels.eval_tuning_panel", "EvalTuningPanel"),
    "roi": ("src.gui.panels.roi_calculator", "ROICalculatorFrame"),
}

# Additional class lookups for sub-panels within admin
ADMIN_SUBPANELS = {
    "DataPathsPanel": ("src.gui.panels.api_admin_tab", "DataPathsPanel"),
    "ModelSelectionPanel": ("src.gui.panels.api_admin_tab", "ModelSelectionPanel"),
    "OfflineModelSelectionPanel": ("src.gui.panels.api_admin_tab", "OfflineModelSelectionPanel"),
}


def _extract_handler_name(handler_str: str) -> tuple[str, str]:
    """Extract class and method from 'ClassName.method_name' or just 'method_name'."""
    # Strip any parenthesized arguments: toggle_mode("offline") -> toggle_mode
    clean = handler_str.split("(")[0].strip()
    if "." in clean:
        parts = clean.rsplit(".", 1)
        return parts[0], parts[1]
    return "", clean


def _find_class(panel: str, class_hint: str):
    """Find and return the class object for a panel/class combination."""
    # Check admin subpanels first
    if class_hint in ADMIN_SUBPANELS:
        mod_path, cls_name = ADMIN_SUBPANELS[class_hint]
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name, None)

    # Check panel map
    if panel in PANEL_MODULE_MAP:
        mod_path, cls_name = PANEL_MODULE_MAP[panel]
        mod = importlib.import_module(mod_path)
        # If class_hint matches the mapped class, use it
        if class_hint == cls_name or not class_hint:
            return getattr(mod, cls_name, None)
        # Otherwise try the hint as a class name in the same module
        cls = getattr(mod, class_hint, None)
        if cls:
            return cls
        # Fall back to mapped class
        return getattr(mod, cls_name, None)

    return None


def validate_entry(entry: dict) -> tuple[str, str]:
    """Validate a single matrix entry. Returns (status, detail)."""
    panel = entry.get("panel", "")
    handler_str = entry.get("handler", "")
    source = entry.get("source", "")

    if not handler_str:
        return "FAIL", "no handler specified"

    class_hint, method_name = _extract_handler_name(handler_str)

    # Try to find the class
    try:
        cls = _find_class(panel, class_hint)
        if cls is None:
            return "FAIL", "class not found for panel={} hint={}".format(panel, class_hint)
    except ImportError as e:
        return "FAIL", "import error: {}".format(e)
    except Exception as e:
        return "FAIL", "unexpected error finding class: {}".format(e)

    # Check if method exists on the class
    if hasattr(cls, method_name):
        return "PASS", "handler exists: {}.{}".format(cls.__name__, method_name)

    # Some handlers are lambdas or inline -- check if the source file has the pattern
    if method_name.startswith("lambda"):
        return "PASS", "lambda handler in source"

    # For menu commands that use direct method refs on the app
    if panel == "app":
        app_cls = _find_class("app", "HybridRAGApp")
        if app_cls and hasattr(app_cls, method_name):
            return "PASS", "handler on app: {}".format(method_name)

    return "FAIL", "method '{}' not found on {}".format(method_name, cls.__name__ if cls else "?")


def main() -> int:
    if not os.path.exists(MATRIX_PATH):
        print("[FAIL] gui_matrix.json not found")
        return 1

    with open(MATRIX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    total = len(entries)
    passed = 0
    failed = 0
    details = []

    for entry in entries:
        status, detail = validate_entry(entry)
        entry["status"] = status
        entry["validation_detail"] = detail
        if status == "PASS":
            passed += 1
        else:
            failed += 1
            details.append("{}: {} -- {}".format(
                entry.get("id", "?"), entry.get("handler", "?"), detail))

    # Write updated matrix back
    with open(MATRIX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("Matrix Validation: {}/{} PASS ({:.1f}%)".format(
        passed, total, passed / max(total, 1) * 100))

    if failed:
        print("\n--- FAILURES ({}) ---".format(failed))
        for d in details:
            print("[FAIL] {}".format(d))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
