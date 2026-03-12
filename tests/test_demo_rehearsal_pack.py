from pathlib import Path

from src.tools.demo_rehearsal_pack import (
    default_demo_rehearsal_pack_path,
    format_expected_evidence,
    load_demo_rehearsal_pack,
    select_demo_question,
)


def test_default_demo_rehearsal_pack_loads_from_repo():
    pack_path = default_demo_rehearsal_pack_path()
    pack = load_demo_rehearsal_pack()

    assert pack_path.is_file()
    assert Path(pack["_path"]) == pack_path
    assert pack["pack_id"] == "sprint5_rehearsal_pack_foundation"
    assert pack["defaults"]["transcript_question_id"] == "pm_leadership_styles_compare"
    assert pack["defaults"]["gui_smoke_question_id"] == "ops_calibration_review_cadence"


def test_transcript_default_question_is_online_first_with_expected_evidence():
    pack = load_demo_rehearsal_pack()
    question = select_demo_question(pack, default_key="transcript_question_id")

    assert question["id"] == "pm_leadership_styles_compare"
    assert question["preferred_mode"] == "online"
    assert question["profile"] == "program_management"
    assert question["prompt"] == "What leadership styles are discussed and how do they differ?"
    assert any(item["kind"] == "path" for item in question["expected_evidence"])
    assert any(item["kind"] == "citation_target" for item in question["expected_evidence"])


def test_gui_smoke_default_question_stays_support_path_with_expected_evidence():
    pack = load_demo_rehearsal_pack()
    question = select_demo_question(pack, default_key="gui_smoke_question_id")

    assert question["id"] == "ops_calibration_review_cadence"
    assert question["preferred_mode"] == "offline"
    assert question["prompt"] == "calibration intervals quarterly review"
    assert "gui_demo_smoke" in question["operator_note"]
    assert any(
        item["target"] == "Maintenance_Procedure_Guide.docx"
        for item in question["expected_evidence"]
    )


def test_select_demo_question_allows_explicit_question_override():
    pack = load_demo_rehearsal_pack()

    question = select_demo_question(
        pack,
        default_key="transcript_question_id",
        question_id="security_offline_data_egress",
    )

    assert question["id"] == "security_offline_data_egress"
    assert question["profile"] == "security"
    assert question["preferred_mode"] == "online"


def test_format_expected_evidence_returns_readable_lines():
    pack = load_demo_rehearsal_pack()
    question = select_demo_question(pack, default_key="transcript_question_id")

    lines = format_expected_evidence(question)

    assert lines
    assert any("Path: Leadership_Playbook.pdf" in line for line in lines)
    assert any("Citation Target:" in line for line in lines)
