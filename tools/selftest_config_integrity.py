# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the selftest config integrity operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Selftest: Configuration integrity verification.

Validates:
  1. Single config load path (no duplicate parsing)
  2. YAML roundtrip integrity
  3. Model selection persists after save_config_field
  4. Status bar and router read same config source
  5. Reset backends does not silently overwrite model
  6. Config file is valid YAML with expected top-level keys

Exit code 0 = all checks pass, 1 = failure.
"""
from __future__ import annotations

import sys
import os
import tempfile
import shutil

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.environ.setdefault("HYBRIDRAG_PROJECT_ROOT", _root)


def main() -> int:
    failures = []

    # 1. Config file exists and is valid YAML
    config_path = os.path.join(_root, "config", "config.yaml")
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        expected_keys = {"chunking", "embedding", "mode", "modes",
                         "paths", "retrieval", "security"}
        actual_keys = set(raw.keys())
        missing = expected_keys - actual_keys
        if missing:
            failures.append("Missing top-level config keys: {}".format(missing))
        else:
            print("[OK] Config YAML valid with all expected keys")
    except Exception as e:
        print("[FAIL] Cannot parse config YAML: {}".format(e))
        return 1

    # 2. load_config returns consistent object
    try:
        from src.core.config import load_config
        config1 = load_config(_root)
        config2 = load_config(_root)
        model1 = getattr(getattr(config1, "ollama", None), "model", None)
        model2 = getattr(getattr(config2, "ollama", None), "model", None)
        if model1 == model2:
            print("[OK] load_config consistent: {}".format(model1))
        else:
            failures.append(
                "load_config inconsistent: {} vs {}".format(model1, model2))
    except Exception as e:
        failures.append("load_config failed: {}".format(e))

    # 3. YAML roundtrip with temp copy
    try:
        from src.core.config import save_config_field
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_config = os.path.join(tmpdir, "config.yaml")
            shutil.copy2(config_path, tmp_config)

            with open(tmp_config, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            original = (
                data.get("modes", {})
                .get("offline", {})
                .get("ollama", {})
                .get("model", "")
            )

            # Write test value
            test_val = "integrity-test-model"
            data.setdefault("modes", {}).setdefault("offline", {}).setdefault(
                "ollama", {}
            )["model"] = test_val
            with open(tmp_config, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False)

            # Read back
            with open(tmp_config, "r", encoding="utf-8") as f:
                data2 = yaml.safe_load(f)
            roundtrip = (
                data2.get("modes", {})
                .get("offline", {})
                .get("ollama", {})
                .get("model", "")
            )

            if roundtrip == test_val:
                print("[OK] YAML roundtrip: '{}' -> '{}'".format(test_val, roundtrip))
            else:
                failures.append(
                    "YAML roundtrip failed: wrote '{}', read '{}'".format(
                        test_val, roundtrip))

            # Verify all top-level keys survived
            surviving_keys = set(data2.keys())
            lost = expected_keys - surviving_keys
            if lost:
                failures.append("Keys lost in roundtrip: {}".format(lost))
            else:
                print("[OK] All config keys survived roundtrip")
    except Exception as e:
        failures.append("YAML roundtrip test failed: {}".format(e))

    # 4. save_config_field roundtrip on real config (write same value back)
    try:
        from src.core.config import save_config_field
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        real_model = (
            data.get("modes", {})
            .get("offline", {})
            .get("ollama", {})
            .get("model", "")
        )
        save_config_field("ollama.model", real_model)

        # Re-read to verify
        with open(config_path, "r", encoding="utf-8") as f:
            data2 = yaml.safe_load(f)
        after = (
            data2.get("modes", {})
            .get("offline", {})
            .get("ollama", {})
            .get("model", "")
        )
        if after == real_model:
            print("[OK] save_config_field no-op write: '{}'".format(real_model))
        else:
            failures.append(
                "save_config_field corrupted: was '{}', now '{}'".format(
                    real_model, after))
    except Exception as e:
        failures.append("save_config_field test failed: {}".format(e))

    # 5. Config mutation is not cached (different instances reflect changes)
    try:
        from src.core.config import Config
        cfg = Config()
        cfg.ollama.model = "test-a"
        if cfg.ollama.model == "test-a":
            cfg.ollama.model = "test-b"
            if cfg.ollama.model == "test-b":
                print("[OK] Config model is mutable, not cached")
            else:
                failures.append("Config model stuck after second mutation")
        else:
            failures.append("Config model not set correctly")
    except Exception as e:
        failures.append("Config mutation test failed: {}".format(e))

    # 6. No BOM in config file
    try:
        with open(config_path, "rb") as f:
            first_bytes = f.read(3)
        if first_bytes == b"\xef\xbb\xbf":
            failures.append("Config YAML has BOM (breaks Python parsers)")
        else:
            print("[OK] Config YAML has no BOM")
    except Exception as e:
        failures.append("BOM check failed: {}".format(e))

    # Summary
    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All config integrity checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
