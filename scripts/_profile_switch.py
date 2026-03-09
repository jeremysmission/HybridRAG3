#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Switches the active Admin profile stored in config/user_modes.yaml.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Profile name argument plus the current config/user_modes YAML files.
# Outputs: Updates user_modes.yaml and prints a summary for the caller.
# Safety notes: Does not directly rewrite base mode defaults in config.yaml.
# ============================
# ===========================================================================
# WHAT: Select or clear the active Admin profile.
# WHY:  Profiles now live in config/user_modes.yaml and overlay the base
#       config at load time. This script changes the selected profile
#       without mutating config/config.yaml directly.
# HOW:  Set active_profile -> reload effective config -> report whether the
#       embedding model changed (re-index warning) and show the resulting mode.
# USAGE: python scripts/_profile_switch.py desktop_power
#        python scripts/_profile_switch.py base
# ===========================================================================

from __future__ import annotations

import os
import sys

from _config_io import project_root

PROJECT_ROOT = project_root()
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_config
from src.core.user_modes import list_profile_names, set_active_profile


def _normalize_target(raw: str) -> str:
    value = (raw or "").strip()
    if value.lower() in {"base", "none", "off", "(base)"}:
        return ""
    return value


def main() -> int:
    root = str(PROJECT_ROOT)
    if len(sys.argv) < 2:
        names = ", ".join(list_profile_names(root))
        print("Usage: python scripts/_profile_switch.py <profile-name|base>")
        print(f"Available profiles: {names or '(none)'}")
        return 1

    target = _normalize_target(sys.argv[1])
    if target:
        names = list_profile_names(root)
        if target not in names:
            print(f"[FAIL] Unknown profile: {target}")
            print("Available profiles: " + (", ".join(names) or "(none)"))
            return 1

    before = load_config(root)
    before_embed = getattr(getattr(before, "embedding", None), "model_name", "")

    try:
        set_active_profile(root, target)
    except Exception as exc:
        print(f"[FAIL] Could not update user_modes.yaml: {exc}")
        return 1

    after = load_config(root)
    after_embed = getattr(getattr(after, "embedding", None), "model_name", "")
    active = getattr(after, "active_profile", "") or "(base)"

    print(f"[OK] Active profile: {active}")
    print(f"  Runtime mode: {getattr(after, 'mode', 'offline')}")
    print(f"  Offline model: {getattr(getattr(after, 'ollama', None), 'model', '')}")
    print(f"  Online model: {getattr(getattr(after, 'api', None), 'model', '') or getattr(getattr(after, 'api', None), 'deployment', '')}")

    if before_embed and after_embed and before_embed != after_embed:
        source_folder = getattr(getattr(after, "paths", None), "source_folder", "") or "D:\\RAG Source Data"
        print("")
        print(f"[WARN] Embedding model changed: {before_embed} -> {after_embed}")
        print("       Existing vectors are incompatible with the new embedding model.")
        print(f"       Re-index before querying. Source hint: {source_folder}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
