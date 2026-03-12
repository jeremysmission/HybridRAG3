import json
from datetime import datetime

from src.tools.demo_rehearsal_pack import (
    build_demo_validation_report,
    load_demo_rehearsal_pack,
    select_demo_question,
    summarize_mode_sequence,
    write_demo_validation_report,
)


def test_summarize_mode_sequence_reports_single_and_mixed_modes():
    assert summarize_mode_sequence([]) == "unknown"
    assert summarize_mode_sequence(["offline", "offline"]) == "offline"
    assert summarize_mode_sequence(["offline", "online", "offline"]) == "mixed"


def test_build_demo_validation_report_tracks_question_and_actual_run():
    pack = load_demo_rehearsal_pack()
    question = select_demo_question(pack, default_key="transcript_question_id")

    report = build_demo_validation_report(
        pack,
        question,
        tool_name="demo_transcript",
        actual_mode="mixed",
        actual_path=["boot", "offline_query_warmup", "switch_to_online", "online_query"],
        operator_notes=["PASS: Query/Online -- chunks=3"],
        passed=True,
        status="passed",
        primary_artifact="D:/HybridRAG3/demo_transcript.json",
        mode_sequence=["offline", "online", "offline"],
        details={"step_results": [{"step": "Query/Online", "ok": True}]},
        timestamp=datetime(2026, 3, 10, 23, 15, 0),
    )

    assert report["tool"]["name"] == "demo_transcript"
    assert report["selected_question"]["id"] == "pm_leadership_styles_compare"
    assert report["selected_question"]["profile"] == "program_management"
    assert report["selected_question"]["preferred_mode"] == "online"
    assert report["selected_question"]["expected_evidence"]
    assert report["actual_run"]["mode"] == "mixed"
    assert report["actual_run"]["mode_sequence"] == ["offline", "online", "offline"]
    assert report["actual_run"]["path_taken"][0] == "boot"
    assert report["validation"]["passed"] is True
    assert report["validation"]["operator_notes"] == ["PASS: Query/Online -- chunks=3"]


def test_write_demo_validation_report_uses_timestamped_tool_and_question_id(tmp_path):
    pack = load_demo_rehearsal_pack()
    question = select_demo_question(pack, default_key="gui_smoke_question_id")
    report = build_demo_validation_report(
        pack,
        question,
        tool_name="gui_demo_smoke",
        actual_mode="offline",
        actual_path=["boot_gui", "mode_switch_offline", "query_demo_document"],
        operator_notes=["PASS: Query completed -- "],
        passed=False,
        status="failed",
        primary_artifact="D:/HybridRAG3/output/gui_demo_smoke_report.json",
        mode_sequence=["offline"],
        details={"counts": {"passed": 4, "failed": 1}},
        timestamp=datetime(2026, 3, 10, 23, 16, 0),
    )

    report_path = write_demo_validation_report(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 10, 23, 16, 0),
    )

    assert report_path.parent == tmp_path / "output" / "rehearsal_validation"
    assert report_path.name == (
        "2026-03-10_231600_gui_demo_smoke_ops_calibration_review_cadence.json"
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["selected_question"]["id"] == "ops_calibration_review_cadence"
    assert payload["actual_run"]["mode"] == "offline"
    assert payload["validation"]["passed"] is False
