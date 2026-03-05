# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the selftest gui registry operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Selftest: GUI panel registry integrity.

Verifies:
  - PANEL_KEYS are in deterministic order
  - All keys are unique (no duplicates)
  - 'index' is present (standalone, not embedded in query)
  - 'admin' appears exactly once
  - 'data' appears iff data_panel module exists
  - GUI entrypoint imports without crashing
  - All registered modules can be imported

Exit code 0 = all checks pass, 1 = failure.
"""
from __future__ import annotations

import sys
import os

# Ensure project root is on path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.environ.setdefault("HYBRIDRAG_PROJECT_ROOT", _root)


def main() -> int:
    failures = []

    # 1. Import registry
    try:
        from src.gui.panels.panel_registry import (
            get_panels, validate_unique_keys, _has_module,
        )
    except Exception as e:
        print("[FAIL] Cannot import panel_registry: {}".format(e))
        return 1

    panels = get_panels()
    keys = [p.key for p in panels]
    print("PANEL_KEYS:", keys)
    print("PANEL_COUNT:", len(panels))

    # 2. Deterministic ordering
    expected_prefix = ["query"]
    if _has_module("src.gui.panels.data_panel"):
        expected_prefix.append("data")
    expected_prefix.append("index")
    actual_prefix = keys[:len(expected_prefix)]
    if actual_prefix != expected_prefix:
        failures.append(
            "ORDER: expected prefix {} got {}".format(expected_prefix, actual_prefix))

    # 3. Unique keys
    dupes = validate_unique_keys()
    if dupes:
        failures.append("DUPLICATES: {}".format(dupes))
    else:
        print("[OK] All keys unique")

    # 4. Index present
    if "index" in keys:
        print("[OK] 'index' present as standalone tab")
    else:
        failures.append("'index' NOT in registry keys")

    # 5. Admin appears exactly once
    admin_count = keys.count("admin")
    if admin_count == 1:
        print("[OK] 'admin' appears exactly once")
    else:
        failures.append("'admin' appears {} times (expected 1)".format(admin_count))

    # 6. Data conditional
    data_exists = _has_module("src.gui.panels.data_panel")
    data_in_registry = "data" in keys
    if data_exists == data_in_registry:
        print("[OK] 'data' in registry: {} (module exists: {})".format(
            data_in_registry, data_exists))
    else:
        failures.append(
            "'data' mismatch: in_registry={} module_exists={}".format(
                data_in_registry, data_exists))

    # 7. All registered modules importable
    for p in panels:
        try:
            __import__(p.module_path, fromlist=[p.class_name])
            print("[OK] import {} ({})".format(p.module_path, p.class_name))
        except Exception as e:
            failures.append("import {} failed: {}".format(p.module_path, e))

    # 8. GUI entrypoint import
    try:
        import src.gui.launch_gui as _  # noqa: F401
        print("[OK] IMPORT_LAUNCH_GUI: OK")
    except Exception as e:
        failures.append("launch_gui import failed: {}".format(e))

    # Summary
    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All registry checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
