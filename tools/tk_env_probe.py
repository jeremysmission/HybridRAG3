# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the tk env probe operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from __future__ import annotations
import os, sys, json
def main() -> None:
    data = {
        "executable": sys.executable,
        "TCL_LIBRARY": os.environ.get("TCL_LIBRARY"),
        "TK_LIBRARY": os.environ.get("TK_LIBRARY"),
        "PYTHONHOME": os.environ.get("PYTHONHOME"),
        "PYTHONPATH": os.environ.get("PYTHONPATH"),
    }
    print(json.dumps(data, indent=2))
if __name__ == "__main__":
    main()
