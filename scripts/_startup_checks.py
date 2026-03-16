"""Startup diagnostics called by start_hybridrag.ps1.

Usage:
    python scripts/_startup_checks.py paths   -- print configured DB/cache paths
    python scripts/_startup_checks.py mode    -- print current mode and model
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _check_paths():
    try:
        from src.core.config import load_config
        c = load_config(str(PROJECT_ROOT))
        print("Config DB:", c.paths.database)
        print("Config embeddings cache:", c.paths.embeddings_cache)
    except Exception as e:
        print("Note: config check skipped:", type(e).__name__ + ":", e)


def _check_mode():
    try:
        from src.core.config import load_config
        c = load_config(str(PROJECT_ROOT))
        mode = getattr(c, "mode", "unknown")
        if mode == "online":
            model = getattr(c.api, "model", "unknown")
        else:
            model = getattr(c.ollama, "model", "unknown")
        print("  Mode:  {}".format(mode))
        print("  Model: {}".format(model))
    except Exception as e:
        print("  Could not read config: {}".format(e))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "paths"
    if cmd == "paths":
        _check_paths()
    elif cmd == "mode":
        _check_mode()
    else:
        print("Usage: python scripts/_startup_checks.py [paths|mode]")
        sys.exit(1)
