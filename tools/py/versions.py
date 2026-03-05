# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the versions operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Installed Package Versions (tools/py/versions.py)
# ============================================================================
#
# WHAT THIS DOES:
#   Prints the version of Python and every key library HybridRAG depends
#   on. This is the first thing to check when something that "used to
#   work" suddenly breaks -- a package may have been upgraded or is
#   missing entirely.
#
# HOW TO USE:
#   python tools/py/versions.py
#
# WHAT "NOT INSTALLED" MEANS:
#   That package is missing from your virtual environment. Fix with:
#   pip install -r requirements.txt
# ============================================================================
import sys
print(f"  Python:             {sys.version.split()[0]}")

packages = [
    "numpy", "keyring", "httpx", "openai", "pydantic",
    "structlog", "yaml", "requests", "urllib3", "certifi",
    "sqlite3"
]
# RETIRED (Session 15, 2026-02-24): sentence_transformers, torch
# Embeddings now served by Ollama nomic-embed-text. No HuggingFace deps.

for pkg in packages:
    try:
        if pkg == "yaml":
            import yaml
            print(f"  PyYAML:             {yaml.__version__}")
        elif pkg == "sqlite3":
            import sqlite3
            print(f"  SQLite:             {sqlite3.sqlite_version}")
        else:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "installed (no version)")
            display = pkg.replace("_", "-")
            print(f"  {display:20s} {ver}")
    except ImportError:
        display = pkg.replace("_", "-")
        print(f"  {display:20s} NOT INSTALLED")