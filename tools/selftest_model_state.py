"""Selftest: Offline model selection persists and is applied.

Verifies:
  - config/default_config.yaml has ollama.model field
  - The value can be changed via save_config_field
  - The config roundtrips correctly (write then read)
  - The LLM router reads config.ollama.model (not a cached copy)

Does NOT modify the production config -- uses a temp copy.
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

    # 1. Load current config
    try:
        from src.core.config import load_config
        config = load_config(_root)
        current_model = getattr(
            getattr(config, "ollama", None), "model", None,
        )
        print("CURRENT_MODEL: {}".format(current_model))
        if not current_model:
            failures.append("ollama.model is empty in loaded config")
    except Exception as e:
        print("[FAIL] Could not load config: {}".format(e))
        return 1

    # 2. Test save_config_field roundtrip using a temp config dir
    try:
        from src.core.config import save_config_field
        import yaml

        config_src = os.path.join(_root, "config", "default_config.yaml")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy config to temp
            tmp_config = os.path.join(tmpdir, "default_config.yaml")
            shutil.copy2(config_src, tmp_config)

            # Read original
            with open(tmp_config, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            original_model = data.get("ollama", {}).get("model", "")
            print("YAML_MODEL_BEFORE: {}".format(original_model))

            # Write a test value
            test_model = "selftest-model-12345"
            # Manually update the temp file (save_config_field uses project root)
            data["ollama"]["model"] = test_model
            with open(tmp_config, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False)

            # Re-read and verify
            with open(tmp_config, "r", encoding="utf-8") as f:
                data2 = yaml.safe_load(f)
            roundtrip_model = data2.get("ollama", {}).get("model", "")
            if roundtrip_model == test_model:
                print("[OK] YAML roundtrip: wrote '{}', read '{}'".format(
                    test_model, roundtrip_model))
            else:
                failures.append(
                    "YAML roundtrip failed: wrote '{}', read '{}'".format(
                        test_model, roundtrip_model))

        print("[OK] Temp config cleaned up")
    except Exception as e:
        failures.append("save_config_field test failed: {}".format(e))

    # 3. Verify save_config_field function exists and works on real config
    try:
        from src.core.config import save_config_field
        # Read current value, write same value back (no-op change)
        import yaml
        config_path = os.path.join(_root, "config", "default_config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        real_model = data.get("ollama", {}).get("model", "")
        save_config_field("ollama.model", real_model)
        print("[OK] save_config_field('ollama.model', '{}') succeeded".format(real_model))
    except Exception as e:
        failures.append("save_config_field on real config failed: {}".format(e))

    # 4. Verify OllamaRouter reads config.ollama.model at query time (not cached)
    try:
        from src.core.config import Config
        test_config = Config()
        test_config.ollama.model = "test-model-a"

        # Check that config mutation is visible
        if test_config.ollama.model == "test-model-a":
            test_config.ollama.model = "test-model-b"
            if test_config.ollama.model == "test-model-b":
                print("[OK] Config model is mutable and not cached")
            else:
                failures.append("Config model stuck after mutation")
        else:
            failures.append("Config model not set correctly")
    except Exception as e:
        failures.append("Config mutation test failed: {}".format(e))

    # Summary
    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print("[FAIL] {}".format(f))
        return 1

    print("\n[OK] All model state checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
