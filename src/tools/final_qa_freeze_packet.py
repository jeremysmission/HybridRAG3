from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from src.tools.shared_cutover_smoke import default_shared_cutover_report_dir
from src.tools.shared_deployment_backup import (
    default_shared_backup_dir,
    default_shared_restore_dir,
    run_shared_restore_drill,
    verify_shared_backup_bundle,
)
from src.tools.shared_deployment_soak import default_shared_soak_report_dir


_DEFAULT_SHARED_HANDOFF = Path(
    os.environ.get(
        "HYBRIDRAG_AI_HANDOFF_PATH",
        r"C:\Users\jerem\.ai_handoff\ai_handoff.md",
    )
)
_FINAL_ACCEPTANCE_STATES = ("pending", "accepted", "rolled_back")


def default_final_qa_freeze_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "output" / "final_qa_freeze"


def build_final_qa_freeze_packet(
    *,
    project_root: str | Path = ".",
    cutover_report: str | Path | None = "latest",
    soak_report: str | Path | None = "latest",
    backup_bundle: str | Path | None = "latest",
    restore_drill: str | Path | None = "latest",
    runbook: str | Path | None = "latest",
    freeze_checklist: str | Path | None = "latest",
    completion_handoff_template: str | Path | None = "latest",
    verify_backup: bool = False,
    run_restore_drill_flag: bool = False,
    handoff_file: str | Path | None = None,
    acceptance_state: str = "pending",
    acceptance_note: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    handoff_path = Path(handoff_file).resolve() if handoff_file else _DEFAULT_SHARED_HANDOFF
    final_acceptance_state = _normalize_acceptance_state(acceptance_state)

    cutover_path = _resolve_file_artifact(
        cutover_report,
        root_dir=default_shared_cutover_report_dir(root),
        suffix="_shared_cutover_smoke.json",
    )
    soak_path = _resolve_file_artifact(
        soak_report,
        root_dir=default_shared_soak_report_dir(root),
        suffix="_shared_deployment_soak.json",
    )
    backup_path = _resolve_dir_artifact(
        backup_bundle,
        root_dir=default_shared_backup_dir(root),
        suffix="_shared_deployment_backup",
    )
    restore_path = _resolve_dir_artifact(
        restore_drill,
        root_dir=default_shared_restore_dir(root),
        suffix="_shared_restore_drill",
    )
    runbook_path = _resolve_named_file_artifact(
        runbook,
        root_dir=root / "docs" / "05_security",
        prefix="SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_",
        suffix=".md",
    )
    freeze_checklist_path = _resolve_named_file_artifact(
        freeze_checklist,
        root_dir=root / "docs" / "09_project_mgmt",
        prefix="FINAL_QA_PM_FREEZE_CHECKLIST_",
        suffix=".md",
    )
    completion_template_path = _resolve_named_file_artifact(
        completion_handoff_template,
        root_dir=root / "docs" / "09_project_mgmt",
        prefix="PROJECT_COMPLETION_HANDOFF_TEMPLATE_",
        suffix=".md",
    )

    artifacts = {
        "cutover_smoke": _cutover_artifact_record(cutover_path),
        "shared_soak": _soak_artifact_record(soak_path),
        "backup_bundle": _backup_bundle_record(backup_path),
        "restore_drill": _restore_drill_record(restore_path),
        "launch_runbook": _simple_path_record(runbook_path),
        "sprint_plan": _simple_path_record(
            root / "docs" / "09_project_mgmt" / "SPRINT_PLAN.md"
        ),
        "pm_tracker": _simple_path_record(
            root / "docs" / "09_project_mgmt" / "PM_TRACKER_2026-03-12_110046.md"
        ),
        "freeze_checklist": _simple_path_record(freeze_checklist_path),
        "completion_handoff_template": _simple_path_record(completion_template_path),
        "shared_handoff": _simple_path_record(handoff_path),
    }

    backup_verify: dict[str, Any] = {
        "requested": bool(verify_backup),
        "executed": False,
        "ok": False,
        "status": "not_requested",
    }
    if verify_backup and backup_path is not None:
        backup_verify = dict(verify_shared_backup_bundle(backup_path))
        backup_verify["requested"] = True
        backup_verify["executed"] = True
        backup_verify["status"] = "passed" if backup_verify.get("ok") else "failed"
    elif verify_backup:
        backup_verify["status"] = "missing_backup_bundle"

    restore_result: dict[str, Any] = {
        "requested": bool(run_restore_drill_flag),
        "executed": False,
        "ok": bool(restore_path),
        "status": "linked_existing" if restore_path else "not_found",
        "restore_dir": str(restore_path) if restore_path else "",
    }
    if run_restore_drill_flag and backup_path is not None:
        can_run = True
        if verify_backup and not backup_verify.get("ok"):
            can_run = False
            restore_result = {
                "requested": True,
                "executed": False,
                "ok": False,
                "status": "skipped_backup_verify_failed",
                "restore_dir": "",
            }
        if can_run:
            restore_result = dict(
                run_shared_restore_drill(
                    backup_path,
                    restore_root=default_shared_restore_dir(root),
                )
            )
            restore_result["requested"] = True
            restore_result["executed"] = True
            restore_result["status"] = "passed" if restore_result.get("ok") else "failed"
    elif run_restore_drill_flag:
        restore_result = {
            "requested": True,
            "executed": False,
            "ok": False,
            "status": "missing_backup_bundle",
            "restore_dir": "",
        }

    summary = summarize_final_qa_freeze_packet(
        artifacts,
        backup_verify=backup_verify,
        restore_result=restore_result,
        acceptance_state=final_acceptance_state,
        acceptance_note=acceptance_note,
    )
    return {
        "ok": not summary["blockers"],
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_root": str(root),
        "acceptance": {
            "state": final_acceptance_state,
            "note": str(acceptance_note or "").strip(),
        },
        "artifacts": artifacts,
        "backup_verify": backup_verify,
        "restore_result": restore_result,
        "summary": summary,
    }


def summarize_final_qa_freeze_packet(
    artifacts: dict[str, dict[str, Any]],
    *,
    backup_verify: dict[str, Any],
    restore_result: dict[str, Any],
    acceptance_state: str,
    acceptance_note: str,
) -> dict[str, Any]:
    blockers: list[str] = []

    cutover = dict(artifacts.get("cutover_smoke", {}) or {})
    soak = dict(artifacts.get("shared_soak", {}) or {})
    backup_bundle = dict(artifacts.get("backup_bundle", {}) or {})
    restore = dict(artifacts.get("restore_drill", {}) or {})
    normalized_note = str(acceptance_note or "").strip()
    final_state = _normalize_acceptance_state(acceptance_state)

    if final_state == "pending":
        blockers.append("Acceptance state is still pending.")
    if final_state == "rolled_back" and not normalized_note:
        blockers.append("Rollback freeze packet requires an acceptance note.")

    if not cutover.get("present"):
        blockers.append("Latest shared cutover smoke artifact is missing.")
    elif final_state == "accepted" and not cutover.get("ok"):
        cutover_blockers = list(cutover.get("blockers", []) or [])
        if cutover_blockers:
            blockers.extend(
                "Cutover smoke: {}".format(item) for item in cutover_blockers
            )
        else:
            blockers.append("Latest shared cutover smoke artifact is not green.")

    if final_state != "rolled_back":
        if not soak.get("present"):
            blockers.append("Latest shared deployment soak artifact is missing.")
        elif final_state == "accepted" and not soak.get("ok"):
            blockers.append("Latest shared deployment soak artifact is not green.")

    if not backup_bundle.get("present"):
        blockers.append("Latest shared backup bundle is missing.")

    backup_proof_ok = False
    backup_proof_source = "missing"
    if backup_verify.get("requested"):
        if not backup_verify.get("executed"):
            blockers.append("Backup verify did not run.")
        elif not backup_verify.get("ok"):
            blockers.append("Backup verify did not pass.")
        else:
            backup_proof_ok = True
            backup_proof_source = "rerun"
    elif cutover.get("linked_backup_verify_ok"):
        backup_proof_ok = True
        backup_proof_source = "cutover_smoke"
    else:
        blockers.append("Backup verify result is missing.")

    restore_ok = False
    restore_source = "missing"
    if restore_result.get("requested"):
        if not restore_result.get("executed"):
            blockers.append("Restore drill did not run.")
        elif not restore_result.get("ok"):
            blockers.append("Restore drill did not pass.")
        else:
            restore_ok = True
            restore_source = "rerun"
    elif cutover.get("linked_restore_ok"):
        restore_ok = True
        restore_source = "cutover_smoke"
    elif restore.get("present") and restore.get("ok"):
        restore_ok = True
        restore_source = "linked_existing"
    else:
        blockers.append("Latest shared restore drill evidence is missing or invalid.")

    for key in (
        "launch_runbook",
        "sprint_plan",
        "pm_tracker",
        "freeze_checklist",
        "completion_handoff_template",
        "shared_handoff",
    ):
        record = dict(artifacts.get(key, {}) or {})
        if not record.get("present"):
            blockers.append("{} is missing.".format(key.replace("_", " ")))

    return {
        "ready_for_freeze": len(blockers) == 0,
        "acceptance_state": final_state,
        "acceptance_note": normalized_note,
        "blockers": blockers,
        "artifact_paths": {
            key: str((artifacts.get(key, {}) or {}).get("path", "") or "")
            for key in sorted(artifacts)
        },
        "cutover_ok": bool(cutover.get("ok")),
        "soak_ok": bool(soak.get("ok")),
        "backup_verify_ok": backup_proof_ok,
        "backup_proof_source": backup_proof_source,
        "restore_ok": restore_ok,
        "restore_source": restore_source,
    }


def write_final_qa_freeze_packet(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    report_dir = default_final_qa_freeze_dir(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    path = report_dir / "{}_final_qa_freeze_packet.json".format(stamp)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def format_final_qa_freeze_console_summary(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary", {}) or {})
    backup_verify = dict(report.get("backup_verify", {}) or {})
    restore_result = dict(report.get("restore_result", {}) or {})
    lines = [
        "HYBRIDRAG FINAL QA FREEZE PACKET",
        "Project root: {}".format(str(report.get("project_root", "") or "")),
        "Acceptance state: {}".format(str(summary.get("acceptance_state", "") or "")),
        "Ready for freeze: {}".format(bool(summary.get("ready_for_freeze"))),
        "Cutover smoke ok: {}".format(bool(summary.get("cutover_ok"))),
        "Shared soak ok: {}".format(bool(summary.get("soak_ok"))),
        "Backup verify: {} ({})".format(
            str(backup_verify.get("status", "not_requested")),
            str(summary.get("backup_proof_source", "missing")),
        ),
        "Restore drill: {} ({})".format(
            str(restore_result.get("status", "not_requested")),
            str(summary.get("restore_source", "missing")),
        ),
    ]
    blockers = list(summary.get("blockers", []) or [])
    if blockers:
        lines.append("Blockers:")
        lines.extend("- {}".format(item) for item in blockers)
    return "\n".join(lines)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the current shared deployment evidence into one final QA/PM "
            "freeze packet and optionally rerun backup verify plus restore drill."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="HybridRAG project root used for output and default artifact discovery.",
    )
    parser.add_argument(
        "--cutover-report",
        default="latest",
        help="Cutover smoke report JSON path, or 'latest'.",
    )
    parser.add_argument(
        "--soak-report",
        default="latest",
        help="Shared soak report JSON path, or 'latest'.",
    )
    parser.add_argument(
        "--backup-bundle",
        default="latest",
        help="Shared backup bundle directory, or 'latest'.",
    )
    parser.add_argument(
        "--restore-drill",
        default="latest",
        help="Shared restore drill directory, or 'latest'.",
    )
    parser.add_argument(
        "--runbook",
        default="latest",
        help="Launch runbook markdown path, or 'latest'.",
    )
    parser.add_argument(
        "--freeze-checklist",
        default="latest",
        help="Final QA/PM freeze checklist path, or 'latest'.",
    )
    parser.add_argument(
        "--completion-handoff-template",
        default="latest",
        help="Project completion handoff template path, or 'latest'.",
    )
    parser.add_argument(
        "--handoff-file",
        default=str(_DEFAULT_SHARED_HANDOFF),
        help="Shared AI handoff file path to link into the freeze packet.",
    )
    parser.add_argument(
        "--acceptance-state",
        choices=list(_FINAL_ACCEPTANCE_STATES),
        default="pending",
        help="Final launch verdict posture for the freeze packet.",
    )
    parser.add_argument(
        "--acceptance-note",
        default="",
        help="Required detail when acceptance state is rolled_back.",
    )
    parser.add_argument(
        "--verify-backup",
        action="store_true",
        help="Run backup verify against the selected backup bundle.",
    )
    parser.add_argument(
        "--run-restore-drill",
        action="store_true",
        help="Run a fresh non-destructive restore drill against the selected backup bundle.",
    )
    parser.add_argument(
        "--fail-if-blocked",
        action="store_true",
        help="Exit 1 when the resulting freeze packet is not ready.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write a timestamped JSON packet under output/final_qa_freeze.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    report = build_final_qa_freeze_packet(
        project_root=args.project_root,
        cutover_report=args.cutover_report,
        soak_report=args.soak_report,
        backup_bundle=args.backup_bundle,
        restore_drill=args.restore_drill,
        runbook=args.runbook,
        freeze_checklist=args.freeze_checklist,
        completion_handoff_template=args.completion_handoff_template,
        verify_backup=bool(args.verify_backup),
        run_restore_drill_flag=bool(args.run_restore_drill),
        handoff_file=args.handoff_file,
        acceptance_state=args.acceptance_state,
        acceptance_note=args.acceptance_note,
    )

    print(format_final_qa_freeze_console_summary(report))
    if not args.no_write:
        path = write_final_qa_freeze_packet(report, project_root=args.project_root)
        print("Wrote freeze packet: {}".format(path))

    if args.fail_if_blocked and not report.get("ok"):
        return 1
    return 0


def _resolve_file_artifact(
    value: str | Path | None,
    *,
    root_dir: Path,
    suffix: str,
) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "latest":
        return _find_latest_file(root_dir, suffix)
    path = Path(text)
    return path.resolve() if path.exists() else path.resolve()


def _resolve_dir_artifact(
    value: str | Path | None,
    *,
    root_dir: Path,
    suffix: str,
) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "latest":
        return _find_latest_dir(root_dir, suffix)
    path = Path(text)
    return path.resolve() if path.exists() else path.resolve()


def _resolve_named_file_artifact(
    value: str | Path | None,
    *,
    root_dir: Path,
    prefix: str,
    suffix: str,
) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "latest":
        return _find_latest_named_file(root_dir, prefix=prefix, suffix=suffix)
    path = Path(text)
    return path.resolve() if path.exists() else path.resolve()


def _find_latest_file(root_dir: Path, suffix: str) -> Path | None:
    if not root_dir.exists():
        return None
    candidates = sorted(
        [path for path in root_dir.iterdir() if path.is_file() and path.name.endswith(suffix)],
        key=lambda path: path.name,
    )
    if not candidates:
        return None
    return candidates[-1]


def _find_latest_dir(root_dir: Path, suffix: str) -> Path | None:
    if not root_dir.exists():
        return None
    candidates = sorted(
        [path for path in root_dir.iterdir() if path.is_dir() and path.name.endswith(suffix)],
        key=lambda path: path.name,
    )
    if not candidates:
        return None
    return candidates[-1]


def _find_latest_named_file(root_dir: Path, *, prefix: str, suffix: str) -> Path | None:
    if not root_dir.exists():
        return None
    candidates = sorted(
        [
            path
            for path in root_dir.iterdir()
            if path.is_file()
            and path.name.startswith(prefix)
            and path.name.endswith(suffix)
        ],
        key=lambda path: path.name,
    )
    if not candidates:
        return None
    return candidates[-1]


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")) or {})
    except Exception:
        return {}


def _simple_path_record(path: Path | None, *, kind: str = "file") -> dict[str, Any]:
    present = bool(path and path.exists())
    return {
        "path": str(path) if path else "",
        "present": present,
        "kind": kind,
    }


def _cutover_artifact_record(path: Path | None) -> dict[str, Any]:
    payload = _load_json(path)
    summary = dict(payload.get("summary", {}) or {})
    rollback = dict(payload.get("rollback_proof", {}) or {})
    rollback_verify = dict(rollback.get("verify", {}) or {})
    rollback_restore = dict(rollback.get("restore_drill", {}) or {})
    return {
        **_simple_path_record(path),
        "ok": bool(payload.get("ok")),
        "deployment_mode": str(summary.get("deployment_mode", "") or ""),
        "runtime_mode": str(summary.get("runtime_mode", "") or ""),
        "blockers": list(summary.get("blockers", []) or []),
        "linked_backup_verify_ok": bool(rollback_verify.get("ok")),
        "linked_restore_ok": bool(rollback_restore.get("ok")),
        "rollback_status": str(rollback.get("status", "") or ""),
    }


def _soak_artifact_record(path: Path | None) -> dict[str, Any]:
    payload = _load_json(path)
    summary = dict(payload.get("summary", {}) or {})
    config = dict(payload.get("config", {}) or {})
    return {
        **_simple_path_record(path),
        "ok": bool(payload.get("ok")),
        "total_requests": int(summary.get("total_requests", 0) or 0),
        "failed_requests": int(summary.get("failed_requests", 0) or 0),
        "concurrency": int(config.get("concurrency", 0) or 0),
    }


def _backup_bundle_record(path: Path | None) -> dict[str, Any]:
    manifest = _load_json((path / "backup_manifest.json") if path else None)
    summary = dict(manifest.get("summary", {}) or {})
    return {
        **_simple_path_record(path, kind="directory"),
        "manifest_path": str((path / "backup_manifest.json").resolve()) if path else "",
        "manifest_present": bool(manifest),
        "copied_files": int(summary.get("copied_files", 0) or 0),
        "missing_files": int(summary.get("missing_files", 0) or 0),
    }


def _restore_drill_record(path: Path | None) -> dict[str, Any]:
    payload_dir = (path / "payload") if path else None
    file_count = 0
    main_database_present = False
    history_database_present = False
    if payload_dir is not None and payload_dir.exists():
        file_count = sum(1 for item in payload_dir.rglob("*") if item.is_file())
        main_database_present = any(
            item.is_file() for item in (payload_dir / "database").glob("*.sqlite3")
        )
        history_database_present = any(
            item.is_file() for item in (payload_dir / "history").glob("*.sqlite3")
        )
    return {
        **_simple_path_record(path, kind="directory"),
        "payload_present": bool(payload_dir and payload_dir.exists()),
        "file_count": file_count,
        "main_database_present": main_database_present,
        "history_database_present": history_database_present,
        "ok": bool(
            path
            and path.exists()
            and payload_dir
            and payload_dir.exists()
            and file_count > 0
            and main_database_present
            and history_database_present
        ),
    }


def _normalize_acceptance_state(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _FINAL_ACCEPTANCE_STATES:
        return normalized
    return "pending"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
