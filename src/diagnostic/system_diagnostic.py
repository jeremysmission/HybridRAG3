# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the system diagnostic part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Legacy convenience stub that opens index_status in Notepad
# WHY:  Early development helper, kept for backwards compatibility.
#       The real diagnostic suite is hybridrag_diagnostic.py.
# HOW:  Launches Notepad with the index_status.py tool file
# USAGE: python -m src.diagnostic  (preferred -- runs full diagnostics)
#        This file is not the main entry point.
# ===================================================================
import subprocess
import sys
import os

def main():
    """Open the index status tool for quick review."""
    tool_path = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "index_status.py")
    tool_path = os.path.abspath(tool_path)
    if os.path.exists(tool_path):
        if sys.platform == "win32":
            subprocess.Popen(["notepad", tool_path])
        else:
            print(f"  Open this file: {tool_path}")
    else:
        print(f"  [WARN] File not found: {tool_path}")
        print("  Use 'python -m src.diagnostic' for full diagnostics instead.")

if __name__ == "__main__":
    main()
