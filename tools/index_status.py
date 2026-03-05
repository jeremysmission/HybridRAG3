# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the index status operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Index Status (tools/index_status.py)
# ============================================================================
#
# WHAT THIS DOES:
#   Wrapper that runs the detailed index status checker. Shows how many
#   documents are indexed, how many chunks exist, and database size.
#
# NOTE:
#   The real implementation is in tools/py/index_status.py
#   This file exists so "python tools/index_status.py" also works.
#
# HOW TO USE:
#   python tools/index_status.py
# ============================================================================
import subprocess
import sys
import os

script = os.path.join(os.path.dirname(__file__), "py", "index_status.py")
if os.path.exists(script):
    subprocess.run([sys.executable, script])
else:
    print("  [WARN] tools/py/index_status.py not found")
