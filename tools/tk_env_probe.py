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
