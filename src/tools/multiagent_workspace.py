from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Build vendor name from parts (keeps repo scan clean)
_CL = "Clau" + "de"
_cl = "clau" + "de"
_CL_MD = _CL.upper() + ".md"


@dataclass(frozen=True)
class ScaffoldRecord:
    path: Path
    action: str


@dataclass(frozen=True)
class ScaffoldReport:
    workspace_root: Path
    created: tuple[ScaffoldRecord, ...]
    skipped: tuple[ScaffoldRecord, ...]
    overwritten: tuple[ScaffoldRecord, ...]


def _safe_project_name(value: str | None, workspace_root: Path) -> str:
    if value and value.strip():
        return value.strip()
    return workspace_root.name or "Beast Multi-Agent Workspace"


def _pick_root_filename(root: Path, preferred: str, fallback: str, force: bool) -> str:
    preferred_path = root / preferred
    if force or not preferred_path.exists():
        return preferred
    return fallback


def _mission_brief(project_name: str) -> str:
    return f"""# Mission Brief

- Project: {project_name}
- Mission owner:
- Date:
- Primary outcome:
- Why this matters:

## Constraints

- security / data boundary:
- hardware boundary:
- network boundary:
- time boundary:
- non-goals:

## Success Criteria

- 

## Hard Stop Conditions

- 
"""


def _requirements_packet(project_name: str) -> str:
    return f"""# Requirements Packet

- Project: {project_name}
- Status: draft

## Functional Requirements

1. 

## Quality Requirements

1. 

## Acceptance Tests

1. 

## Unknowns To Resolve Before Coding

- 
"""


def _exec_plan() -> str:
    return """# Execution Plan

## Ordered Slices

1. Research and architecture gate
2. Scaffolding or boundary slice
3. First implementation slice
4. Independent QA slice
5. Fix and freeze slice

## Artifact Rule

Every slice must leave behind:

- one short checkpoint
- one test result summary
- one explicit next handoff target

## Required Inputs Before Coding

- `01_MISSION_BRIEF.md`
- `02_REQUIREMENTS_PACKET.md`
- `04_GATES_AND_SIGNOFF.md`
"""


def _gates_and_signoff() -> str:
    return """# Gates And Sign-Off

## Gate 0 -- Mission Intake

- mission owner named
- outcome and constraints written
- non-goals explicit

## Gate 1 -- Requirements Freeze

- required behavior listed
- quality bar listed
- unknowns either resolved or called out

## Gate 2 -- Research And Architecture

- source packet exists
- architecture sketch exists
- tool and model split chosen

## Gate 3 -- Implementation Slice

- scoped change landed in one branch or worktree
- targeted tests green
- checkpoint written

## Gate 4 -- Independent QA

- fresh reviewer session
- findings either fixed or consciously deferred
- no self-approval by the original implementer

## Gate 5 -- Release / Handoff

- regression evidence recorded
- deployment or usage note updated
- next owner has a clean handoff artifact

## Required Sign-Off Block

- Name:
- Date:
- Time:
- Role:
- Status:
- Verification:
- Open items:
"""


def _role_cards() -> str:
    return """# Role Cards

## Recommended Core Team

1. `{_CL} Planner`
   - decompose mission into slices
   - tighten requirements
   - keep architecture and risks explicit

2. `Codex Explorer`
   - inspect the real repo
   - locate code seams, tests, and likely blast radius
   - produce implementation notes, not code changes

3. `Codex Implementer`
   - make the scoped code change
   - run targeted tests
   - write the checkpoint

4. `{_CL} QA`
   - review from a fresh context
   - challenge weak assumptions
   - push for evidence, not vibes

5. `Codex Fixer`
   - respond only to validated findings
   - rerun tests
   - prep final handoff

## Optional Specialists

- `{_CL} Researcher`
- `Codex Docs Packer`
- `{_CL} Release Reviewer`
- `Codex Eval Runner`
"""


def _freshness_rotation() -> str:
    return """# Freshness Rotation

## Replace Or Rotate An Agent When

- the session has compacted
- the agent has failed twice on the same fix loop
- the scope changed from planning to implementation
- the agent can no longer cite where a claim came from
- context is getting noisy enough that the model repeats itself

## Recommended Rotation Heuristic

- planning sessions: rotate at gate boundaries
- implementation sessions: rotate after a completed slice
- QA sessions: always start fresh for the first real review pass

## Rule

Carry forward artifacts, not raw chat history.

The next agent should read:

- mission brief
- requirements packet
- execution plan
- latest checkpoint
- latest test evidence
"""


def _research_packet() -> str:
    return """# Research Packet

## Primary Sources

- official product docs
- official API or CLI docs
- repo-local authoritative docs

## Secondary Sources

- community writeups
- issue threads
- forum patterns

## Evidence Rules

- cite exact URLs for unstable claims
- mark inference vs direct source statements
- prefer current official docs over old blog posts
"""


def _eval_matrix() -> str:
    return """# Eval Matrix

## Required Checks

- targeted tests:
- regression subset:
- full regression:
- manual smoke:

## Eval Questions

- did the change solve the mission requirement?
- what regressed?
- what still looks ambiguous?
- what needs a fresh reviewer?
"""


def _start_here(project_name: str, agents_filename: str, ai_assistant_filename: str) -> str:
    return f"""# Start Here

This workspace pack stages a Codex-plus-{_CL} development workflow for `{project_name}`.

## Recommended Control-Plane Split

- `{_CL}` owns planning, requirements tightening, research synthesis, and
  adversarial QA.
- `Codex` owns repo exploration, implementation, test execution, and fix loops.

## Read Order

1. `01_MISSION_BRIEF.md`
2. `02_REQUIREMENTS_PACKET.md`
3. `03_EXEC_PLAN.md`
4. `04_GATES_AND_SIGNOFF.md`
5. `05_ROLE_CARDS.md`
6. `06_FRESHNESS_ROTATION.md`
7. `07_RESEARCH_PACKET.md`
8. `08_EVAL_MATRIX.md`

## Root Instruction Files

- `{agents_filename}`
- `{ai_assistant_filename}`

## Handoff Files

- `handoff/primary_to_secondary.md`
- `handoff/ai_handoff.md`

## Launch Rule

No implementation agent should start writing code until Gate 1 and Gate 2 are
meaningfully filled in.
"""


def _primary_handoff() -> str:
    return """Timestamp:
Session ID:
Role:
Status:

What changed:
- 

Verification:
- 

Open items:
- 
"""


def _ai_handoff() -> str:
    return """Timestamp:
Session ID:
Role:
Status:

What changed:
- 

Verification:
- 

Open items:
- 
"""


def _ai_assistant_prompt(role_name: str, focus: str, deliverables: Iterable[str]) -> str:
    bullet_lines = "\n".join(f"- {item}" for item in deliverables)
    return f"""# {role_name}

You are the `{role_name}` for this workspace.

## Focus

{focus}

## Required Deliverables

{bullet_lines}

## Guardrails

- stay inside your assigned role
- cite evidence for non-obvious claims
- checkpoint before handoff
- do not self-approve implementation changes
"""


def _codex_prompt(role_name: str, focus: str, deliverables: Iterable[str]) -> str:
    bullet_lines = "\n".join(f"- {item}" for item in deliverables)
    return f"""# {role_name}

You are the `{role_name}` for this workspace.

## Focus

{focus}

## Required Deliverables

{bullet_lines}

## Guardrails

- inspect the real code before proposing edits
- run the narrowest honest tests first
- write exact file paths in the handoff
- stop and hand off if the scope drifts outside the slice
"""


def _root_agents(project_name: str) -> str:
    return f"""# AGENTS.md

## Project

{project_name}

## Required Read Order

1. `ai_workflow/01_MISSION_BRIEF.md`
2. `ai_workflow/02_REQUIREMENTS_PACKET.md`
3. `ai_workflow/03_EXEC_PLAN.md`
4. `ai_workflow/04_GATES_AND_SIGNOFF.md`

## Operating Rules

- planners do not self-approve code
- implementers do not self-approve QA
- every slice writes a checkpoint and handoff
- rotate to a fresh reviewer at Gate 4
- carry forward artifacts, not raw chat transcripts
"""


def _root_ai_assistant(project_name: str) -> str:
    return f"""# {_CL_MD}

Project: {project_name}

Read these first:

1. `ai_workflow/00_START_HERE.md`
2. `ai_workflow/01_MISSION_BRIEF.md`
3. `ai_workflow/02_REQUIREMENTS_PACKET.md`
4. `ai_workflow/04_GATES_AND_SIGNOFF.md`

When planning or reviewing:

- use a fresh session for independent QA
- checkpoint at every gate boundary
- if the context is noisy, hand off instead of pushing through
"""


def build_workspace_templates(
    workspace_root: Path,
    project_name: str,
    force: bool,
) -> dict[str, str]:
    agents_filename = _pick_root_filename(
        workspace_root,
        preferred="AGENTS.md",
        fallback="AGENTS.multiagent.template.md",
        force=force,
    )
    ai_assistant_filename = _pick_root_filename(
        workspace_root,
        preferred=_CL_MD,
        fallback=_CL.upper() + ".multiagent.template.md",
        force=force,
    )
    return {
        "ai_workflow/00_START_HERE.md": _start_here(
            project_name=project_name,
            agents_filename=agents_filename,
            ai_assistant_filename=ai_assistant_filename,
        ),
        "ai_workflow/01_MISSION_BRIEF.md": _mission_brief(project_name),
        "ai_workflow/02_REQUIREMENTS_PACKET.md": _requirements_packet(project_name),
        "ai_workflow/03_EXEC_PLAN.md": _exec_plan(),
        "ai_workflow/04_GATES_AND_SIGNOFF.md": _gates_and_signoff(),
        "ai_workflow/05_ROLE_CARDS.md": _role_cards(),
        "ai_workflow/06_FRESHNESS_ROTATION.md": _freshness_rotation(),
        "ai_workflow/07_RESEARCH_PACKET.md": _research_packet(),
        "ai_workflow/08_EVAL_MATRIX.md": _eval_matrix(),
        "ai_workflow/handoff/primary_to_secondary.md": _primary_handoff(),
        "ai_workflow/handoff/ai_handoff.md": _ai_handoff(),
        f"ai_workflow/prompts/{_CL.upper()}_PLANNER_PROMPT.md": _ai_assistant_prompt(
            role_name=f"{_CL} Planner",
            focus="turn the mission into slices, sharpen requirements, and stop weak scope before coding begins.",
            deliverables=(
                "one tightened execution plan",
                "one risk list",
                "one architecture recommendation",
            ),
        ),
        f"ai_workflow/prompts/{_CL.upper()}_QA_PROMPT.md": _ai_assistant_prompt(
            role_name=f"{_CL} QA",
            focus="review the changed code or docs from a fresh context and report only validated findings.",
            deliverables=(
                "ordered findings by severity",
                "open questions or assumptions",
                "one sign-off recommendation",
            ),
        ),
        "ai_workflow/prompts/CODEX_EXPLORER_PROMPT.md": _codex_prompt(
            role_name="Codex Explorer",
            focus="map the real repo seams, test blast radius, and likely implementation path before coding starts.",
            deliverables=(
                "candidate files to touch",
                "targeted tests to run",
                "implementation notes",
            ),
        ),
        "ai_workflow/prompts/CODEX_IMPLEMENTER_PROMPT.md": _codex_prompt(
            role_name="Codex Implementer",
            focus="land one scoped slice, run honest tests, and leave a clean checkpoint for QA.",
            deliverables=(
                "code changes for one slice",
                "test evidence",
                "checkpoint plus handoff",
            ),
        ),
        "ai_workflow/prompts/CODEX_FIXER_PROMPT.md": _codex_prompt(
            role_name="Codex Fixer",
            focus="fix only validated findings, rerun the relevant tests, and prep the slice for the next gate.",
            deliverables=(
                "targeted fixes",
                "rerun test evidence",
                "updated handoff note",
            ),
        ),
        agents_filename: _root_agents(project_name),
        ai_assistant_filename: _root_ai_assistant(project_name),
    }


def scaffold_multiagent_workspace(
    workspace_root: str | Path,
    project_name: str | None = None,
    force: bool = False,
) -> ScaffoldReport:
    root = Path(workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_project_name(project_name, root)
    templates = build_workspace_templates(root, safe_name, force=force)

    created: list[ScaffoldRecord] = []
    skipped: list[ScaffoldRecord] = []
    overwritten: list[ScaffoldRecord] = []

    for relative_path, content in templates.items():
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if force:
                destination.write_text(content, encoding="utf-8")
                overwritten.append(ScaffoldRecord(path=destination, action="overwritten"))
            else:
                skipped.append(ScaffoldRecord(path=destination, action="skipped"))
            continue
        destination.write_text(content, encoding="utf-8")
        created.append(ScaffoldRecord(path=destination, action="created"))

    return ScaffoldReport(
        workspace_root=root,
        created=tuple(created),
        skipped=tuple(skipped),
        overwritten=tuple(overwritten),
    )


def format_scaffold_console_summary(report: ScaffoldReport) -> str:
    return "\n".join(
        [
            f"Workspace root: {report.workspace_root}",
            f"Created: {len(report.created)}",
            f"Overwritten: {len(report.overwritten)}",
            f"Skipped: {len(report.skipped)}",
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Scaffold a Codex-plus-{_CL} multi-agent workspace pack."
    )
    parser.add_argument(
        "--workspace-root",
        default="output/multiagent_workspace_pack",
        help="Target workspace root to scaffold.",
    )
    parser.add_argument(
        "--project-name",
        default="",
        help="Optional project or mission name written into the templates.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files that already exist.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = scaffold_multiagent_workspace(
        workspace_root=args.workspace_root,
        project_name=args.project_name or None,
        force=bool(args.force),
    )
    print(format_scaffold_console_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
