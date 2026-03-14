from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.tools.final_qa_freeze_packet import default_final_qa_freeze_dir


def default_project_completion_handoff_dir(
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "docs" / "09_project_mgmt"


def build_project_completion_handoff(
    *,
    project_root: str | Path = ".",
    freeze_packet: str | Path | None = "latest",
    qa_evidence_path: str | Path | None = None,
    supported_operating_limit: str = "",
    watchlist_items: list[str] | None = None,
    open_items: list[str] | None = None,
    allow_blocked_preview: bool = False,
    coder_name: str = "Codex",
    coder_time: str = "",
    qa_name: str = "",
    qa_time: str = "",
    pm_name: str = "",
    pm_time: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    generated_at = datetime.now().astimezone()
    generated_iso = generated_at.isoformat(timespec="seconds")
    generated_display = generated_at.strftime("%Y-%m-%d %H:%M %Z")

    freeze_path = _resolve_file_artifact(
        freeze_packet,
        root_dir=default_final_qa_freeze_dir(root),
        suffix="_final_qa_freeze_packet.json",
    )
    freeze_payload = _load_json(freeze_path)
    freeze_record = _freeze_packet_record(freeze_path, freeze_payload)

    artifact_paths = dict(
        (freeze_payload.get("summary", {}) or {}).get("artifact_paths", {}) or {}
    )
    detailed_artifacts = dict(freeze_payload.get("artifacts", {}) or {})

    sprint_plan_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="sprint_plan",
        fallback=root / "docs" / "09_project_mgmt" / "SPRINT_PLAN.md",
    )
    pm_tracker_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="pm_tracker",
        fallback=root / "docs" / "09_project_mgmt" / "PM_TRACKER_2026-03-12_110046.md",
    )
    runbook_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="launch_runbook",
        fallback=_find_latest_named_file(
            root / "docs" / "05_security",
            prefix="SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_",
            suffix=".md",
        ),
    )
    freeze_checklist_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="freeze_checklist",
        fallback=_find_latest_named_file(
            root / "docs" / "09_project_mgmt",
            prefix="FINAL_QA_PM_FREEZE_CHECKLIST_",
            suffix=".md",
        ),
    )
    completion_template_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="completion_handoff_template",
        fallback=_find_latest_named_file(
            root / "docs" / "09_project_mgmt",
            prefix="PROJECT_COMPLETION_HANDOFF_TEMPLATE_",
            suffix=".md",
        ),
    )
    shared_handoff_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="shared_handoff",
        fallback=None,
    )
    cutover_smoke_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="cutover_smoke",
        fallback=None,
    )
    shared_soak_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="shared_soak",
        fallback=None,
    )
    backup_bundle_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="backup_bundle",
        fallback=None,
    )
    restore_drill_path = _artifact_path_from_packet(
        artifact_paths,
        detailed_artifacts,
        key="restore_drill",
        fallback=None,
    )
    final_qa_evidence_path = (
        Path(qa_evidence_path).resolve() if qa_evidence_path else pm_tracker_path
    )

    acceptance = dict(freeze_payload.get("acceptance", {}) or {})
    acceptance_state = str(acceptance.get("state", "pending") or "pending").strip().lower()
    acceptance_note = str(acceptance.get("note", "") or "").strip()
    freeze_summary = dict(freeze_payload.get("summary", {}) or {})
    freeze_blockers = list(freeze_summary.get("blockers", []) or [])
    freeze_ready = bool(freeze_summary.get("ready_for_freeze"))

    derived_watchlist = _load_watchlist_items(sprint_plan_path)
    for item in watchlist_items or []:
        normalized = str(item or "").strip()
        if normalized and normalized not in derived_watchlist:
            derived_watchlist.append(normalized)

    normalized_open_items = [
        str(item).strip() for item in (open_items or []) if str(item).strip()
    ]
    preview_only = not freeze_ready
    write_allowed = freeze_ready or bool(allow_blocked_preview)
    blockers: list[str] = []
    if not freeze_record["present"]:
        blockers.append("Final QA freeze packet is missing.")
    if freeze_record["present"] and not freeze_ready:
        blockers.append("Final QA freeze packet is not ready.")
        blockers.extend("Freeze packet: {}".format(item) for item in freeze_blockers)
    if preview_only and not allow_blocked_preview:
        blockers.append("Blocked preview is not enabled.")

    operating_limit = _derive_supported_operating_limit(
        supported_operating_limit=supported_operating_limit,
        detailed_artifacts=detailed_artifacts,
    )
    final_state = _derive_final_state(
        acceptance_state=acceptance_state,
        preview_only=preview_only,
    )
    accepted_launch_or_rollback = _derive_launch_outcome(
        acceptance_state=acceptance_state,
        preview_only=preview_only,
    )

    if not normalized_open_items:
        if preview_only:
            normalized_open_items = list(freeze_blockers) or [
                "Final launch acceptance is still pending."
            ]
        elif acceptance_state == "rolled_back":
            normalized_open_items = [
                "Shared launch remains intentionally rolled back; any reactivation is separate future work."
            ]
        else:
            normalized_open_items = [
                "No active delivery blockers remain; only maintenance watchlist items continue."
            ]

    signoff = {
        "coder_name": str(coder_name or "").strip() or "Codex",
        "coder_time": str(coder_time or "").strip() or generated_iso,
        "qa_name": str(qa_name or "").strip() or "TBD",
        "qa_time": str(qa_time or "").strip() or "TBD",
        "pm_name": str(pm_name or "").strip() or "TBD",
        "pm_time": str(pm_time or "").strip() or "TBD",
    }

    artifacts = {
        "sprint_plan": _artifact_record(sprint_plan_path),
        "pm_tracker": _artifact_record(pm_tracker_path),
        "launch_runbook": _artifact_record(runbook_path),
        "final_freeze_packet": _artifact_record(freeze_path),
        "final_qa_evidence": _artifact_record(final_qa_evidence_path),
        "freeze_checklist": _artifact_record(freeze_checklist_path),
        "completion_handoff_template": _artifact_record(completion_template_path),
        "latest_backup_bundle": _artifact_record(backup_bundle_path, kind="directory"),
        "latest_restore_drill": _artifact_record(restore_drill_path, kind="directory"),
        "latest_cutover_smoke": _artifact_record(cutover_smoke_path),
        "latest_shared_soak": _artifact_record(shared_soak_path),
        "shared_handoff": _artifact_record(shared_handoff_path),
    }

    summary = {
        "ready_for_handoff": freeze_ready,
        "preview_only": preview_only,
        "write_allowed": write_allowed,
        "final_state": final_state,
        "accepted_launch_or_rollback": accepted_launch_or_rollback,
        "supported_operating_limit": operating_limit,
        "acceptance_state": acceptance_state,
        "acceptance_note": acceptance_note,
        "blockers": blockers,
    }

    report = {
        "ok": freeze_ready,
        "timestamp": generated_iso,
        "generated_display": generated_display,
        "project_root": str(root),
        "freeze_packet": freeze_record,
        "artifacts": artifacts,
        "signoff": signoff,
        "maintenance_watchlist": derived_watchlist,
        "open_items": normalized_open_items,
        "summary": summary,
    }
    report["markdown"] = render_project_completion_handoff(report)
    return report


def render_project_completion_handoff(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary", {}) or {})
    artifacts = dict(report.get("artifacts", {}) or {})
    signoff = dict(report.get("signoff", {}) or {})
    freeze_packet = dict(report.get("freeze_packet", {}) or {})
    watchlist = list(report.get("maintenance_watchlist", []) or [])
    open_items = list(report.get("open_items", []) or [])
    blockers = list(summary.get("blockers", []) or [])

    lines = [
        "# Project Completion Handoff",
        "",
        "**Created:** {}".format(str(report.get("generated_display", "") or "")),
        "**Purpose:** generated handoff for `14.4 -- Project Completion Handoff`.",
        "",
        "## Generation Status",
        "",
        "- mode: {}".format("preview" if summary.get("preview_only") else "final"),
        "- freeze packet ready: {}".format(bool(summary.get("ready_for_handoff"))),
        "- freeze packet source: `{}`".format(
            str(freeze_packet.get("path", "") or "TBD")
        ),
    ]
    if freeze_packet.get("acceptance_note"):
        lines.append(
            "- acceptance note: `{}`".format(
                str(freeze_packet.get("acceptance_note") or "")
            )
        )
    if blockers:
        lines.extend(["", "## Blockers Preventing Final Handoff", ""])
        lines.extend("- {}".format(item) for item in blockers)

    lines.extend(
        [
            "",
            "## Project State",
            "",
            "| Field | Value |",
            "|---|---|",
            "| Completion date | `{}` |".format(
                str(report.get("generated_display", "") or "TBD")
            ),
            "| Final state | `{}` |".format(
                str(summary.get("final_state", "") or "TBD")
            ),
            "| Accepted launch or rollback | `{}` |".format(
                str(summary.get("accepted_launch_or_rollback", "") or "TBD")
            ),
            "| Supported operating limit | `{}` |".format(
                str(summary.get("supported_operating_limit", "") or "TBD")
            ),
            "",
            "## Frozen Artifacts",
            "",
        ]
    )
    lines.extend(
        _artifact_line(label, artifacts.get(key))
        for label, key in (
            ("sprint tracker", "sprint_plan"),
            ("PM tracker", "pm_tracker"),
            ("launch runbook", "launch_runbook"),
            ("final freeze packet", "final_freeze_packet"),
            ("final QA evidence", "final_qa_evidence"),
            ("latest backup bundle", "latest_backup_bundle"),
            ("latest restore drill", "latest_restore_drill"),
            ("latest cutover smoke", "latest_cutover_smoke"),
            ("latest shared soak", "latest_shared_soak"),
            ("shared handoff", "shared_handoff"),
            ("completion handoff template", "completion_handoff_template"),
        )
    )

    lines.extend(["", "## Maintenance-Only Watchlist", ""])
    if watchlist:
        lines.extend("- {}".format(item) for item in watchlist)
    else:
        lines.append("- `TBD`")

    lines.extend(["", "## Open Items That Are No Longer Delivery Blockers", ""])
    if open_items:
        lines.extend("- {}".format(item) for item in open_items)
    else:
        lines.append("- `TBD`")

    lines.extend(
        [
            "",
            "## Recommended First Maintenance Checks",
            "",
            "1. confirm `/health`, `/status`, and `/admin/data`",
            "2. confirm the current backup bundle still verifies cleanly",
            "3. confirm the shared auth token and online credentials are still present",
            "4. confirm the documented concurrency ceiling has not drifted",
            "",
            "## Sign-Off",
            "",
            "| Role | Name | Date / Time |",
            "|---|---|---|",
            "| Coder | `{}` | `{}` |".format(
                str(signoff.get("coder_name", "TBD") or "TBD"),
                str(signoff.get("coder_time", "TBD") or "TBD"),
            ),
            "| QA | `{}` | `{}` |".format(
                str(signoff.get("qa_name", "TBD") or "TBD"),
                str(signoff.get("qa_time", "TBD") or "TBD"),
            ),
            "| PM | `{}` | `{}` |".format(
                str(signoff.get("pm_name", "TBD") or "TBD"),
                str(signoff.get("pm_time", "TBD") or "TBD"),
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def write_project_completion_handoff(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    output_dir = default_project_completion_handoff_dir(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    path = output_dir / "PROJECT_COMPLETION_HANDOFF_{}.md".format(stamp)
    path.write_text(str(report.get("markdown", "") or ""), encoding="utf-8")
    return path


def format_project_completion_handoff_console_summary(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary", {}) or {})
    lines = [
        "HYBRIDRAG PROJECT COMPLETION HANDOFF",
        "Project root: {}".format(str(report.get("project_root", "") or "")),
        "Final state: {}".format(str(summary.get("final_state", "") or "")),
        "Ready for handoff: {}".format(bool(summary.get("ready_for_handoff"))),
        "Preview only: {}".format(bool(summary.get("preview_only"))),
        "Write allowed: {}".format(bool(summary.get("write_allowed"))),
        "Supported operating limit: {}".format(
            str(summary.get("supported_operating_limit", "") or "")
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
            "Generate the final project completion handoff from the latest final "
            "QA freeze packet. By default this fails closed until the freeze "
            "packet is truly ready."
        )
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="HybridRAG project root used for artifact discovery and output.",
    )
    parser.add_argument(
        "--freeze-packet",
        default="latest",
        help="Final QA freeze packet JSON path, or 'latest'.",
    )
    parser.add_argument(
        "--qa-evidence-path",
        default="",
        help="Optional final QA evidence path to show in the generated handoff.",
    )
    parser.add_argument(
        "--supported-operating-limit",
        default="",
        help="Override the supported operating limit shown in the handoff.",
    )
    parser.add_argument(
        "--watchlist-item",
        action="append",
        default=[],
        help="Extra maintenance watchlist item. Repeat for multiple entries.",
    )
    parser.add_argument(
        "--open-item",
        action="append",
        default=[],
        help="Extra non-blocking open item. Repeat for multiple entries.",
    )
    parser.add_argument(
        "--coder-name",
        default="Codex",
        help="Coder sign-off name placed into the generated handoff.",
    )
    parser.add_argument(
        "--coder-time",
        default="",
        help="Optional coder sign-off timestamp. Defaults to the current time.",
    )
    parser.add_argument("--qa-name", default="", help="Optional QA sign-off name.")
    parser.add_argument("--qa-time", default="", help="Optional QA sign-off timestamp.")
    parser.add_argument("--pm-name", default="", help="Optional PM sign-off name.")
    parser.add_argument("--pm-time", default="", help="Optional PM sign-off timestamp.")
    parser.add_argument(
        "--allow-blocked-preview",
        action="store_true",
        help="Allow writing a preview handoff even when the freeze packet is blocked.",
    )
    parser.add_argument(
        "--fail-if-blocked",
        action="store_true",
        help="Exit 1 when the freeze packet is not ready for the final handoff.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write a timestamped markdown handoff note.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)
    report = build_project_completion_handoff(
        project_root=args.project_root,
        freeze_packet=args.freeze_packet,
        qa_evidence_path=args.qa_evidence_path or None,
        supported_operating_limit=args.supported_operating_limit,
        watchlist_items=list(args.watchlist_item or []),
        open_items=list(args.open_item or []),
        allow_blocked_preview=bool(args.allow_blocked_preview),
        coder_name=args.coder_name,
        coder_time=args.coder_time,
        qa_name=args.qa_name,
        qa_time=args.qa_time,
        pm_name=args.pm_name,
        pm_time=args.pm_time,
    )
    print(format_project_completion_handoff_console_summary(report))

    summary = dict(report.get("summary", {}) or {})
    if not args.no_write and summary.get("write_allowed"):
        path = write_project_completion_handoff(report, project_root=args.project_root)
        print("Wrote completion handoff: {}".format(path))
    elif not args.no_write:
        print("Did not write handoff because the freeze packet is blocked.")

    if args.fail_if_blocked and not report.get("ok"):
        return 1
    return 0


def _freeze_packet_record(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload.get("summary", {}) or {})
    acceptance = dict(payload.get("acceptance", {}) or {})
    return {
        "path": str(path) if path else "",
        "present": bool(path and path.exists()),
        "ready_for_freeze": bool(summary.get("ready_for_freeze")),
        "acceptance_state": str(acceptance.get("state", "pending") or "pending"),
        "acceptance_note": str(acceptance.get("note", "") or "").strip(),
        "blockers": list(summary.get("blockers", []) or []),
        "timestamp": str(payload.get("timestamp", "") or ""),
    }


def _derive_supported_operating_limit(
    *,
    supported_operating_limit: str,
    detailed_artifacts: dict[str, Any],
) -> str:
    explicit = str(supported_operating_limit or "").strip()
    if explicit:
        return explicit
    soak = dict(detailed_artifacts.get("shared_soak", {}) or {})
    concurrency = int(soak.get("concurrency", 0) or 0)
    if concurrency > 0:
        return "concurrency={}".format(concurrency)
    return "TBD"


def _derive_final_state(*, acceptance_state: str, preview_only: bool) -> str:
    if preview_only:
        return "preview_only"
    if acceptance_state == "rolled_back":
        return "rolled_back"
    if acceptance_state == "accepted":
        return "accepted"
    return "pending"


def _derive_launch_outcome(*, acceptance_state: str, preview_only: bool) -> str:
    if preview_only:
        return "pending preview"
    if acceptance_state == "rolled_back":
        return "rolled back"
    if acceptance_state == "accepted":
        return "accepted launch"
    return "pending"


def _artifact_path_from_packet(
    artifact_paths: dict[str, Any],
    detailed_artifacts: dict[str, Any],
    *,
    key: str,
    fallback: Path | None,
) -> Path | None:
    path_text = str(artifact_paths.get(key, "") or "").strip()
    if not path_text:
        path_text = str((detailed_artifacts.get(key, {}) or {}).get("path", "") or "").strip()
    if path_text:
        return Path(path_text).resolve()
    return fallback.resolve() if fallback else None


def _artifact_record(path: Path | None, *, kind: str = "file") -> dict[str, Any]:
    return {
        "path": str(path) if path else "",
        "present": bool(path and path.exists()),
        "kind": kind,
    }


def _artifact_line(label: str, artifact: dict[str, Any] | None) -> str:
    record = dict(artifact or {})
    value = str(record.get("path", "") or "TBD")
    return "- {}: `{}`".format(label, value)


def _load_watchlist_items(path: Path | None) -> list[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    items: list[str] = []
    inside_watchlist = False
    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("## "):
            if inside_watchlist:
                break
            inside_watchlist = line.strip() == "## Watchlist"
            continue
        if not inside_watchlist:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


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
    return Path(text).resolve()


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
        key=lambda item: item.name,
    )
    if not candidates:
        return None
    return candidates[-1]


def _find_latest_file(root_dir: Path, suffix: str) -> Path | None:
    if not root_dir.exists():
        return None
    candidates = sorted(
        [path for path in root_dir.iterdir() if path.is_file() and path.name.endswith(suffix)],
        key=lambda item: item.name,
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
