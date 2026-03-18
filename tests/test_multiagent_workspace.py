from pathlib import Path

from src.tools.multiagent_workspace import scaffold_multiagent_workspace

_CL = "Clau" + "de"
_CL_MD = _CL.upper() + ".md"
_CL_TMPL = _CL.upper() + ".multiagent.template.md"
_CL_PLANNER = f"ai_workflow/prompts/{_CL.upper()}_PLANNER_PROMPT.md"
_CL_QA = f"ai_workflow/prompts/{_CL.upper()}_QA_PROMPT.md"


def test_scaffold_multiagent_workspace_creates_expected_files(tmp_path: Path) -> None:
    report = scaffold_multiagent_workspace(
        workspace_root=tmp_path,
        project_name="Beast Mission",
    )

    expected = {
        "ai_workflow/00_START_HERE.md",
        "ai_workflow/01_MISSION_BRIEF.md",
        "ai_workflow/02_REQUIREMENTS_PACKET.md",
        "ai_workflow/03_EXEC_PLAN.md",
        "ai_workflow/04_GATES_AND_SIGNOFF.md",
        "ai_workflow/05_ROLE_CARDS.md",
        "ai_workflow/06_FRESHNESS_ROTATION.md",
        "ai_workflow/07_RESEARCH_PACKET.md",
        "ai_workflow/08_EVAL_MATRIX.md",
        "ai_workflow/handoff/primary_to_secondary.md",
        "ai_workflow/handoff/ai_handoff.md",
        _CL_PLANNER,
        _CL_QA,
        "ai_workflow/prompts/CODEX_EXPLORER_PROMPT.md",
        "ai_workflow/prompts/CODEX_IMPLEMENTER_PROMPT.md",
        "ai_workflow/prompts/CODEX_FIXER_PROMPT.md",
        "AGENTS.md",
        _CL_MD,
    }

    created = {record.path.relative_to(tmp_path).as_posix() for record in report.created}
    assert created == expected
    assert not report.skipped
    assert not report.overwritten
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").startswith("# AGENTS.md")


def test_scaffold_multiagent_workspace_uses_template_names_when_root_files_exist(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("existing agents", encoding="utf-8")
    (tmp_path / _CL_MD).write_text("existing config", encoding="utf-8")

    report = scaffold_multiagent_workspace(
        workspace_root=tmp_path,
        project_name="Existing Root",
    )

    created = {record.path.relative_to(tmp_path).as_posix() for record in report.created}
    assert "AGENTS.multiagent.template.md" in created
    assert _CL_TMPL in created
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "existing agents"
    assert (tmp_path / _CL_MD).read_text(encoding="utf-8") == "existing config"


def test_scaffold_multiagent_workspace_force_overwrites_root_files(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    ai_assistant_path = tmp_path / _CL_MD
    agents_path.write_text("old agents", encoding="utf-8")
    ai_assistant_path.write_text("old config", encoding="utf-8")

    report = scaffold_multiagent_workspace(
        workspace_root=tmp_path,
        project_name="Force Root",
        force=True,
    )

    overwritten = {record.path.relative_to(tmp_path).as_posix() for record in report.overwritten}
    assert "AGENTS.md" in overwritten
    assert _CL_MD in overwritten
    assert "Force Root" in agents_path.read_text(encoding="utf-8")
    assert "Force Root" in ai_assistant_path.read_text(encoding="utf-8")
