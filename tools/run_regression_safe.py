#!/usr/bin/env python3
"""
Run full regression with an isolated per-run pytest temp base.

WHY:
    Some environments accumulate locked pytest temp folders under %TEMP%,
    causing PermissionError during fixture setup/cleanup. This runner forces
    a unique workspace-local temp base and mirrors TEMP/TMP to that location.

USAGE:
    python tools/run_regression_safe.py
    python tools/run_regression_safe.py --keep-temp
    python tools/run_regression_safe.py --extra "-k query_engine"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run HybridRAG regression safely.")
    p.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep per-run temp folder for debugging.",
    )
    p.add_argument(
        "--extra",
        default="",
        help='Extra args passed to pytest (example: "--maxfail=1 -k query_engine").',
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    project_root = Path(__file__).resolve().parent.parent
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = project_root / "output" / f"pytest_tmp_run_{stamp}_{os.getpid()}"
    base.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["TEMP"] = str(base)
    env["TMP"] = str(base)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--ignore=tests/test_fastapi_server.py",
        "-q",
        "--tb=short",
        "--basetemp",
        str(base),
    ]
    if args.extra.strip():
        cmd.extend(args.extra.strip().split())

    print(f"[INFO] Using basetemp: {base}")
    print("[INFO] Running:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(project_root), env=env)
    print(f"[INFO] pytest exit code: {rc}")

    if args.keep_temp:
        print(f"[INFO] Keeping temp folder: {base}")
        return rc

    try:
        shutil.rmtree(base, ignore_errors=True)
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

