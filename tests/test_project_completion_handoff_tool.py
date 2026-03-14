from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from src.tools.project_completion_handoff import (
    build_project_completion_handoff,
    format_project_completion_handoff_console_summary,
    write_project_completion_handoff,
)


def test_write_project_completion_handoff_uses_timestamped_name(tmp_path: Path) -> None:
    report = {
        "markdown": "# Project Completion Handoff\n",
        "summary": {"ready_for_handoff": True},
    }

    path = write_project_completion_handoff(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 13, 19, 30, 0),
    )

    assert path.name == "PROJECT_COMPLETION_HANDOFF_2026-03-13_193000.md"
    assert "Project Completion Handoff" in path.read_text(encoding="utf-8")


def test_build_project_completion_handoff_uses_latest_ready_freeze_packet(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_sprint_plan(project_root)
    freeze_dir = project_root / "output" / "final_qa_freeze"
    freeze_dir.mkdir(parents=True, exist_ok=True)

    old_packet = _ready_freeze_packet(
        project_root,
        stamp="2026-03-13_190000",
        concurrency=1,
    )
    new_packet = _ready_freeze_packet(
        project_root,
        stamp="2026-03-13_191500",
        concurrency=2,
    )
    (freeze_dir / "2026-03-13_190000_final_qa_freeze_packet.json").write_text(
        json.dumps(old_packet, indent=2),
        encoding="utf-8",
    )
    (freeze_dir / "2026-03-13_191500_final_qa_freeze_packet.json").write_text(
        json.dumps(new_packet, indent=2),
        encoding="utf-8",
    )

    report = build_project_completion_handoff(project_root=project_root)

    assert report["ok"] is True
    assert report["freeze_packet"]["path"].endswith(
        "2026-03-13_191500_final_qa_freeze_packet.json"
    )
    assert report["summary"]["supported_operating_limit"] == "concurrency=2"
    assert report["summary"]["final_state"] == "accepted"
    assert "track the non-fatal cross-suite Tk teardown noise" in report["maintenance_watchlist"][0]
    assert "accepted launch" in report["markdown"]


def test_build_project_completion_handoff_blocks_by_default_when_freeze_packet_not_ready(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_sprint_plan(project_root)
    freeze_dir = project_root / "output" / "final_qa_freeze"
    freeze_dir.mkdir(parents=True, exist_ok=True)
    (freeze_dir / "2026-03-13_192000_final_qa_freeze_packet.json").write_text(
        json.dumps(
            _blocked_freeze_packet(
                project_root,
                blockers=["Latest shared cutover smoke artifact is missing."],
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_project_completion_handoff(project_root=project_root)

    assert report["ok"] is False
    assert report["summary"]["write_allowed"] is False
    assert "Final QA freeze packet is not ready." in report["summary"]["blockers"]
    assert "Blocked preview is not enabled." in report["summary"]["blockers"]


def test_build_project_completion_handoff_can_write_blocked_preview(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_sprint_plan(project_root)
    freeze_dir = project_root / "output" / "final_qa_freeze"
    freeze_dir.mkdir(parents=True, exist_ok=True)
    (freeze_dir / "2026-03-13_193000_final_qa_freeze_packet.json").write_text(
        json.dumps(
            _blocked_freeze_packet(
                project_root,
                blockers=["Acceptance state is still pending."],
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_project_completion_handoff(
        project_root=project_root,
        allow_blocked_preview=True,
    )

    assert report["ok"] is False
    assert report["summary"]["preview_only"] is True
    assert report["summary"]["write_allowed"] is True
    assert "## Blockers Preventing Final Handoff" in report["markdown"]
    assert "Acceptance state is still pending." in report["markdown"]


def test_format_project_completion_handoff_console_summary_mentions_preview() -> None:
    summary = format_project_completion_handoff_console_summary(
        {
            "project_root": "D:/HybridRAG3",
            "summary": {
                "final_state": "preview_only",
                "ready_for_handoff": False,
                "preview_only": True,
                "write_allowed": True,
                "supported_operating_limit": "concurrency=1",
                "blockers": ["Final QA freeze packet is not ready."],
            },
        }
    )

    assert "Final state: preview_only" in summary
    assert "Preview only: True" in summary
    assert "Final QA freeze packet is not ready." in summary


def _ready_freeze_packet(
    project_root: Path,
    *,
    stamp: str,
    concurrency: int,
) -> dict[str, object]:
    docs_root = project_root / "docs" / "09_project_mgmt"
    security_root = project_root / "docs" / "05_security"
    docs_root.mkdir(parents=True, exist_ok=True)
    security_root.mkdir(parents=True, exist_ok=True)
    sprint_plan = docs_root / "SPRINT_PLAN.md"
    pm_tracker = docs_root / "PM_TRACKER_2026-03-12_110046.md"
    freeze_checklist = docs_root / "FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_165338.md"
    template = docs_root / "PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_165338.md"
    runbook = security_root / "SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_103437.md"
    shared_handoff = project_root / "ai_handoff.md"
    cutover = (
        project_root
        / "output"
        / "shared_cutover_smoke"
        / "{}_shared_cutover_smoke.json".format(stamp)
    )
    soak = (
        project_root
        / "output"
        / "shared_soak"
        / "{}_shared_deployment_soak.json".format(stamp)
    )
    backup = (
        project_root
        / "output"
        / "shared_backups"
        / "{}_shared_deployment_backup".format(stamp)
    )
    restore = (
        project_root
        / "output"
        / "shared_restore_drills"
        / "{}_shared_restore_drill".format(stamp)
    )
    for path in (
        sprint_plan,
        pm_tracker,
        freeze_checklist,
        template,
        runbook,
        shared_handoff,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(path.name, encoding="utf-8")
    cutover.parent.mkdir(parents=True, exist_ok=True)
    soak.parent.mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)
    restore.mkdir(parents=True, exist_ok=True)
    cutover.write_text("{}", encoding="utf-8")
    soak.write_text("{}", encoding="utf-8")
    return {
        "timestamp": "{}T19:15:00-06:00".format(stamp[:10]),
        "acceptance": {"state": "accepted", "note": ""},
        "summary": {
            "ready_for_freeze": True,
            "blockers": [],
            "artifact_paths": {
                "sprint_plan": str(sprint_plan.resolve()),
                "pm_tracker": str(pm_tracker.resolve()),
                "launch_runbook": str(runbook.resolve()),
                "freeze_checklist": str(freeze_checklist.resolve()),
                "completion_handoff_template": str(template.resolve()),
                "shared_handoff": str(shared_handoff.resolve()),
                "cutover_smoke": str(cutover.resolve()),
                "shared_soak": str(soak.resolve()),
                "backup_bundle": str(backup.resolve()),
                "restore_drill": str(restore.resolve()),
            },
        },
        "artifacts": {
            "shared_soak": {
                "path": str(soak.resolve()),
                "present": True,
                "ok": True,
                "concurrency": concurrency,
                "total_requests": 4,
                "failed_requests": 0,
            },
            "backup_bundle": {"path": str(backup.resolve()), "present": True},
            "restore_drill": {
                "path": str(restore.resolve()),
                "present": True,
                "ok": True,
            },
            "cutover_smoke": {
                "path": str(cutover.resolve()),
                "present": True,
                "ok": True,
            },
            "sprint_plan": {"path": str(sprint_plan.resolve()), "present": True},
            "pm_tracker": {"path": str(pm_tracker.resolve()), "present": True},
            "launch_runbook": {"path": str(runbook.resolve()), "present": True},
            "freeze_checklist": {
                "path": str(freeze_checklist.resolve()),
                "present": True,
            },
            "completion_handoff_template": {
                "path": str(template.resolve()),
                "present": True,
            },
            "shared_handoff": {"path": str(shared_handoff.resolve()), "present": True},
        },
    }


def _blocked_freeze_packet(project_root: Path, *, blockers: list[str]) -> dict[str, object]:
    packet = _ready_freeze_packet(
        project_root,
        stamp="2026-03-13_193000",
        concurrency=1,
    )
    packet["acceptance"] = {"state": "pending", "note": ""}
    packet["summary"] = {
        **dict(packet["summary"]),
        "ready_for_freeze": False,
        "blockers": blockers,
    }
    return packet


def _write_sprint_plan(project_root: Path) -> None:
    sprint_plan = project_root / "docs" / "09_project_mgmt" / "SPRINT_PLAN.md"
    sprint_plan.parent.mkdir(parents=True, exist_ok=True)
    sprint_plan.write_text(
        "\n".join(
            [
                "# HybridRAG3 Sprint Plan",
                "",
                "## Watchlist",
                "",
                "- track the non-fatal cross-suite Tk teardown noise",
                "- keep class sizes under 500 LOC",
                "",
                "## Notes",
                "",
                "- done",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
