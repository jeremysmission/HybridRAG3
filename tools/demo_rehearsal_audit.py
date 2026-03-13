from __future__ import annotations

import argparse
from pathlib import Path
import sys

from src.tools.demo_rehearsal_audit import (
    audit_demo_rehearsal_pack,
    resolve_demo_rehearsal_db_path,
    write_demo_rehearsal_audit_report,
)
from src.tools.demo_rehearsal_pack import load_demo_rehearsal_pack


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit demo rehearsal-pack evidence targets against the indexed corpus.",
    )
    parser.add_argument(
        "--pack",
        default="",
        help="Optional path to a demo rehearsal pack JSON file.",
    )
    parser.add_argument(
        "--db",
        default="",
        help="Optional explicit path to hybridrag.sqlite3.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root used for config lookup and report output.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write a timestamped audit JSON report.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    project_root = Path(args.project_root).resolve()
    pack = load_demo_rehearsal_pack(args.pack or None)
    db_path = resolve_demo_rehearsal_db_path(
        project_root=project_root,
        database_path=args.db or None,
    )
    report = audit_demo_rehearsal_pack(pack, db_path=db_path)

    print("=" * 60)
    print("  HYBRIDRAG DEMO REHEARSAL AUDIT")
    print("=" * 60)
    print("Pack: {}".format(pack.get("_path", "")))
    print("DB:   {}".format(db_path))
    print(
        "Checks: {passed}/{checks} passed".format(
            passed=report["summary"]["passed"],
            checks=report["summary"]["checks"],
        )
    )
    if report["summary"]["failed"]:
        print("Failed: {}".format(report["summary"]["failed"]))
    print("")

    for question in report.get("questions", []):
        status = "PASS" if question.get("ok") else "FAIL"
        print("[{}] {} ({})".format(
            status,
            question.get("id", ""),
            question.get("preferred_mode", ""),
        ))
        for check in question.get("checks", []):
            marker = "OK" if check.get("ok") else "MISS"
            print(
                "  [{}] {} -- {} -- {}".format(
                    marker,
                    check.get("kind", ""),
                    check.get("target", ""),
                    check.get("detail", ""),
                )
            )
        print("")

    if not args.no_report:
        report_path = write_demo_rehearsal_audit_report(
            report,
            project_root=project_root,
        )
        print("Saved audit: {}".format(report_path))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
