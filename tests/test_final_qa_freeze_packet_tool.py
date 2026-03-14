from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from src.tools.final_qa_freeze_packet import (
    build_final_qa_freeze_packet,
    format_final_qa_freeze_console_summary,
    write_final_qa_freeze_packet,
)
from src.tools.shared_deployment_backup import (
    create_shared_backup_bundle,
    run_shared_restore_drill,
)


def test_write_final_qa_freeze_packet_uses_timestamped_name(tmp_path: Path) -> None:
    report = {"ok": True, "summary": {"ready_for_freeze": True}}

    path = write_final_qa_freeze_packet(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 13, 19, 0, 0),
    )

    assert path.name == "2026-03-13_190000_final_qa_freeze_packet.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["ready_for_freeze"] is True


def test_build_final_qa_freeze_packet_uses_latest_artifacts_and_can_run_backup_proof(
    tmp_path: Path,
) -> None:
    project_root, main_db = _make_shared_project(tmp_path / "project")
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    cutover_dir = project_root / "output" / "shared_cutover_smoke"
    soak_dir = project_root / "output" / "shared_soak"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    soak_dir.mkdir(parents=True, exist_ok=True)

    (cutover_dir / "2026-03-13_180000_shared_cutover_smoke.json").write_text(
        json.dumps({"ok": False, "summary": {"blockers": ["old blocker"]}}, indent=2),
        encoding="utf-8",
    )
    (cutover_dir / "2026-03-13_181500_shared_cutover_smoke.json").write_text(
        json.dumps(
            {
                "ok": True,
                "summary": {
                    "deployment_mode": "production",
                    "runtime_mode": "online",
                    "blockers": [],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (soak_dir / "2026-03-13_180000_shared_deployment_soak.json").write_text(
        json.dumps({"ok": False, "summary": {"failed_requests": 1}}, indent=2),
        encoding="utf-8",
    )
    (soak_dir / "2026-03-13_182000_shared_deployment_soak.json").write_text(
        json.dumps(
            {
                "ok": True,
                "summary": {
                    "total_requests": 4,
                    "failed_requests": 0,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    backup = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=project_root / "output" / "shared_backups",
        timestamp=datetime(2026, 3, 13, 18, 30, 0),
        include_logs=False,
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        verify_backup=True,
        run_restore_drill_flag=True,
        handoff_file=handoff,
        acceptance_state="accepted",
    )

    assert report["ok"] is True
    assert report["artifacts"]["cutover_smoke"]["path"].endswith(
        "2026-03-13_181500_shared_cutover_smoke.json"
    )
    assert report["artifacts"]["shared_soak"]["path"].endswith(
        "2026-03-13_182000_shared_deployment_soak.json"
    )
    assert report["artifacts"]["backup_bundle"]["path"] == str(
        Path(backup["bundle_dir"]).resolve()
    )
    assert report["artifacts"]["launch_runbook"]["path"].endswith(
        "SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_103437.md"
    )
    assert report["backup_verify"]["ok"] is True
    assert report["restore_result"]["ok"] is True
    assert report["summary"]["backup_proof_source"] == "rerun"
    assert report["summary"]["restore_source"] == "rerun"
    assert report["summary"]["ready_for_freeze"] is True


def test_build_final_qa_freeze_packet_reports_missing_or_failed_evidence(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    soak_dir = project_root / "output" / "shared_soak"
    soak_dir.mkdir(parents=True, exist_ok=True)
    (soak_dir / "2026-03-13_182000_shared_deployment_soak.json").write_text(
        json.dumps({"ok": False, "summary": {"failed_requests": 2}}, indent=2),
        encoding="utf-8",
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        handoff_file=handoff,
    )

    blockers = list(report["summary"]["blockers"])
    assert report["ok"] is False
    assert "Acceptance state is still pending." in blockers
    assert "Latest shared cutover smoke artifact is missing." in blockers
    assert "Latest shared backup bundle is missing." in blockers
    assert "Backup verify result is missing." in blockers
    assert "Latest shared restore drill evidence is missing or invalid." in blockers


def test_build_final_qa_freeze_packet_allows_explicit_rollback_with_linked_proof(
    tmp_path: Path,
) -> None:
    project_root, main_db = _make_shared_project(tmp_path / "project_rollback")
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    cutover_dir = project_root / "output" / "shared_cutover_smoke"
    soak_dir = project_root / "output" / "shared_soak"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    soak_dir.mkdir(parents=True, exist_ok=True)

    (cutover_dir / "2026-03-13_183500_shared_cutover_smoke.json").write_text(
        json.dumps(
            {
                "ok": False,
                "summary": {
                    "deployment_mode": "production",
                    "runtime_mode": "online",
                    "blockers": ["Concurrency ceiling exceeded during launch window."],
                },
                "rollback_proof": {
                    "status": "failed",
                    "verify": {"ok": True},
                    "restore_drill": {"ok": True},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (soak_dir / "2026-03-13_183600_shared_deployment_soak.json").write_text(
        json.dumps(
            {
                "ok": False,
                "config": {"concurrency": 2},
                "summary": {"total_requests": 5, "failed_requests": 4},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=project_root / "output" / "shared_backups",
        timestamp=datetime(2026, 3, 13, 18, 30, 0),
        include_logs=False,
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        handoff_file=handoff,
        acceptance_state="rolled_back",
        acceptance_note="Rolled back after timeouts at concurrency 2.",
    )

    assert report["ok"] is True
    assert report["summary"]["ready_for_freeze"] is True
    assert report["summary"]["cutover_ok"] is False
    assert report["summary"]["soak_ok"] is False
    assert report["summary"]["backup_proof_source"] == "cutover_smoke"
    assert report["summary"]["restore_source"] == "cutover_smoke"
    assert report["summary"]["acceptance_state"] == "rolled_back"


def test_build_final_qa_freeze_packet_allows_rollback_without_soak_when_proof_exists(
    tmp_path: Path,
) -> None:
    project_root, main_db = _make_shared_project(tmp_path / "project_rollback_no_soak")
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    cutover_dir = project_root / "output" / "shared_cutover_smoke"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    (cutover_dir / "2026-03-13_184500_shared_cutover_smoke.json").write_text(
        json.dumps(
            {
                "ok": False,
                "summary": {
                    "deployment_mode": "production",
                    "runtime_mode": "online",
                    "blockers": ["Operator chose rollback after smoke failures."],
                },
                "rollback_proof": {
                    "status": "failed",
                    "verify": {"ok": True},
                    "restore_drill": {"ok": True},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=project_root / "output" / "shared_backups",
        timestamp=datetime(2026, 3, 13, 18, 46, 0),
        include_logs=False,
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        handoff_file=handoff,
        acceptance_state="rolled_back",
        acceptance_note="Rolled back because the live cutover was not accepted.",
    )

    assert report["ok"] is True
    assert report["summary"]["ready_for_freeze"] is True
    assert report["summary"]["acceptance_state"] == "rolled_back"
    assert report["summary"]["backup_proof_source"] == "cutover_smoke"
    assert report["summary"]["restore_source"] == "cutover_smoke"
    assert "Latest shared deployment soak artifact is missing." not in report["summary"]["blockers"]


def test_build_final_qa_freeze_packet_uses_existing_restore_drill_when_linked_result_missing(
    tmp_path: Path,
) -> None:
    project_root, main_db = _make_shared_project(tmp_path / "project_existing_restore")
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    cutover_dir = project_root / "output" / "shared_cutover_smoke"
    soak_dir = project_root / "output" / "shared_soak"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    soak_dir.mkdir(parents=True, exist_ok=True)
    (cutover_dir / "2026-03-13_184000_shared_cutover_smoke.json").write_text(
        json.dumps(
            {
                "ok": True,
                "summary": {
                    "deployment_mode": "production",
                    "runtime_mode": "online",
                    "blockers": [],
                },
                "rollback_proof": {"status": "passed", "verify": {"ok": True}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (soak_dir / "2026-03-13_184100_shared_deployment_soak.json").write_text(
        json.dumps(
            {
                "ok": True,
                "config": {"concurrency": 1},
                "summary": {"total_requests": 2, "failed_requests": 0},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    backup = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=project_root / "output" / "shared_backups",
        timestamp=datetime(2026, 3, 13, 18, 40, 0),
        include_logs=False,
    )
    restore = run_shared_restore_drill(
        backup["bundle_dir"],
        restore_root=project_root / "output" / "shared_restore_drills",
        timestamp=datetime(2026, 3, 13, 18, 41, 0),
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        handoff_file=handoff,
        acceptance_state="accepted",
    )

    assert restore["ok"] is True
    assert report["ok"] is True
    assert report["summary"]["restore_source"] == "linked_existing"
    assert report["artifacts"]["restore_drill"]["ok"] is True


def test_format_final_qa_freeze_console_summary_mentions_acceptance_and_blockers() -> None:
    summary = format_final_qa_freeze_console_summary(
        {
            "project_root": "D:/HybridRAG3",
            "summary": {
                "acceptance_state": "pending",
                "ready_for_freeze": False,
                "cutover_ok": False,
                "soak_ok": True,
                "backup_proof_source": "missing",
                "restore_source": "linked_existing",
                "blockers": ["Acceptance state is still pending."],
            },
            "backup_verify": {"status": "not_requested"},
            "restore_result": {"status": "linked_existing"},
        }
    )

    assert "Acceptance state: pending" in summary
    assert "Ready for freeze: False" in summary
    assert "Shared soak ok: True" in summary
    assert "Acceptance state is still pending." in summary


def test_build_final_qa_freeze_packet_requires_acceptance_note_for_rollback(
    tmp_path: Path,
) -> None:
    project_root, main_db = _make_shared_project(tmp_path / "project_rollback_note")
    _write_doc_scaffold(project_root)
    handoff = tmp_path / "ai_handoff.md"
    handoff.write_text("latest handoff\n", encoding="utf-8")

    cutover_dir = project_root / "output" / "shared_cutover_smoke"
    soak_dir = project_root / "output" / "shared_soak"
    cutover_dir.mkdir(parents=True, exist_ok=True)
    soak_dir.mkdir(parents=True, exist_ok=True)
    (cutover_dir / "2026-03-13_190000_shared_cutover_smoke.json").write_text(
        json.dumps(
            {
                "ok": False,
                "summary": {"blockers": ["rollback"]},
                "rollback_proof": {"status": "failed", "verify": {"ok": True}, "restore_drill": {"ok": True}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (soak_dir / "2026-03-13_190100_shared_deployment_soak.json").write_text(
        json.dumps({"ok": False, "summary": {"failed_requests": 3}}, indent=2),
        encoding="utf-8",
    )
    create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=project_root / "output" / "shared_backups",
        timestamp=datetime(2026, 3, 13, 19, 2, 0),
        include_logs=False,
    )

    report = build_final_qa_freeze_packet(
        project_root=project_root,
        handoff_file=handoff,
        acceptance_state="rolled_back",
    )

    assert report["ok"] is False
    assert "Rollback freeze packet requires an acceptance note." in report["summary"]["blockers"]


def test_format_final_qa_freeze_console_summary_mentions_blockers() -> None:
    summary = format_final_qa_freeze_console_summary(
        {
            "project_root": "D:/HybridRAG3",
            "summary": {
                "acceptance_state": "accepted",
                "ready_for_freeze": False,
                "cutover_ok": False,
                "soak_ok": True,
                "backup_proof_source": "rerun",
                "restore_source": "linked_existing",
                "blockers": ["Latest shared cutover smoke artifact is missing."],
            },
            "backup_verify": {"status": "passed"},
            "restore_result": {"status": "linked_existing"},
        }
    )

    assert "Ready for freeze: False" in summary
    assert "Shared soak ok: True" in summary
    assert "Latest shared cutover smoke artifact is missing." in summary


def _write_doc_scaffold(project_root: Path) -> None:
    security_dir = project_root / "docs" / "05_security"
    pm_dir = project_root / "docs" / "09_project_mgmt"
    security_dir.mkdir(parents=True, exist_ok=True)
    pm_dir.mkdir(parents=True, exist_ok=True)
    (
        security_dir / "SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_101500.md"
    ).write_text("older runbook\n", encoding="utf-8")
    (
        security_dir / "SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_103437.md"
    ).write_text("launch runbook\n", encoding="utf-8")
    (pm_dir / "SPRINT_PLAN.md").write_text("sprint plan\n", encoding="utf-8")
    (pm_dir / "PM_TRACKER_2026-03-12_110046.md").write_text(
        "pm tracker\n", encoding="utf-8"
    )
    (pm_dir / "FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_160000.md").write_text(
        "older freeze checklist\n", encoding="utf-8"
    )
    (pm_dir / "FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_165338.md").write_text(
        "freeze checklist\n", encoding="utf-8"
    )
    (pm_dir / "PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_160000.md").write_text(
        "older handoff template\n", encoding="utf-8"
    )
    (pm_dir / "PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_165338.md").write_text(
        "handoff template\n", encoding="utf-8"
    )


def _make_shared_project(project_root: Path) -> tuple[Path, Path]:
    from tests.test_shared_cutover_smoke_tool import _make_shared_project as helper

    return helper(project_root)
