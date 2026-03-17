from __future__ import annotations

import os
import sys

# Ensure the project root is on sys.path so ``src`` is importable when
# this script is executed as a subprocess (e.g. from tests).
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.tools.shared_deployment_backup import main


if __name__ == "__main__":
    raise SystemExit(main())
