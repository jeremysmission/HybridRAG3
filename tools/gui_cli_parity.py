#!/usr/bin/env python3
"""
Headless GUI CLI-parity runtime runner for QA.

Examples:
  python tools/gui_cli_parity.py
  python tools/gui_cli_parity.py --only rag-index --only rag-query
  python tools/gui_cli_parity.py --allow-network-probes --strict-missing
  python tools/gui_cli_parity.py --list
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from src.gui.testing.gui_cli_parity_harness import DEFAULT_CLI_CHECKS, GuiCliParityHarness


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the GUI CLI-parity harness headlessly and emit a JSON report.",
    )
    parser.add_argument(
        "--report",
        default=str(PROJECT_ROOT / "output" / "gui_cli_parity_runtime_report.json"),
        help="JSON report output path.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run only the named CLI command parity check. Repeatable.",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Skip the named CLI command parity check. Repeatable.",
    )
    parser.add_argument(
        "--attach-backends",
        choices=("auto", "always", "never"),
        default="auto",
        help="Backend attach policy for index/query checks.",
    )
    parser.add_argument(
        "--allow-network-probes",
        action="store_true",
        help="Allow live API test probes when stored credentials are present.",
    )
    parser.add_argument(
        "--strict-missing",
        action="store_true",
        help="Return non-zero when a CLI parity target is missing or still manual-only.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available CLI parity targets and exit.",
    )
    return parser


def _print_check_list() -> int:
    for check in DEFAULT_CLI_CHECKS:
        status = check.probe_name or "missing_gui_surface"
        print(f"{check.cli_command:18s}  {check.title:28s}  {status}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list:
        return _print_check_list()

    harness = GuiCliParityHarness(
        attach_mode=args.attach_backends,
        allow_network_probes=args.allow_network_probes,
    )
    report = harness.run(only=args.only, skip=args.skip)
    report_path = harness.write_report(report, args.report)

    counts = report["counts"]
    print(
        f"GUI CLI parity: passed={counts.get('passed', 0)} failed={counts.get('failed', 0)} "
        f"skipped={counts.get('skipped', 0)} missing={counts.get('missing_gui_surface', 0)} "
        f"manual={counts.get('manual_check_required', 0)}"
    )
    print(f"Report: {report_path}")

    if counts.get("failed", 0):
        return 1
    if args.strict_missing and (
        counts.get("missing_gui_surface", 0) or counts.get("manual_check_required", 0)
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
