# HybridRAG3 Study Guide

**Created:** 2026-03-14  
**Last updated:** 2026-03-14 13:55 America/Denver  
**Purpose:** provide the canonical learning path for HybridRAG3 so new users, operators, demo leads, and maintainers can ramp in a deliberate sequence without reading the entire repo.

## What This Guide Replaces

HybridRAG3 already has strong material, but it was spread across setup guides, interface guides, architecture references, demo notes, and a large external reading list.

This guide is now the canonical curriculum:

- repo-first before web-first
- outcomes before encyclopedic reading
- hands-on checkpoints before optional deep dives
- role-based routing instead of one giant path for everyone

If you only follow one learning document, follow this one.

## Pick The Right Route

| Role | Time | Start here | Finish with |
|---|---|---|---|
| everyday user | 60-90 min | [USER_GUIDE.md](../03_guides/USER_GUIDE.md) | ask one cited question and re-index once |
| CLI operator | 2-3 hr | [CLI_GUIDE.md](../03_guides/CLI_GUIDE.md) | switch modes, run diagnostics, start the server |
| GUI operator | 2-3 hr | [GUI_GUIDE.md](../03_guides/GUI_GUIDE.md) | run a query, index a folder, inspect Admin and Cost views |
| demo lead | 4-6 hr | [DEMO_PREP.md](../04_demo/DEMO_PREP.md) | deliver the 5-minute script and handle skeptical questions cleanly |
| builder / maintainer | 1-2 days | [TECHNICAL_THEORY_OF_OPERATION_RevC.md](../02_architecture/TECHNICAL_THEORY_OF_OPERATION_RevC.md) | explain the indexing and query pipelines end to end |

## Recommended Default Curriculum

This is the default route for anyone who wants to become genuinely effective with the system instead of just memorizing commands.

### Phase 1: Get The System Running

**Outcome:** you can boot the environment, verify health, index documents, and get one cited answer.

**Read:**

- [INSTALL_AND_SETUP.md](../01_setup/INSTALL_AND_SETUP.md)
- [USER_GUIDE.md](../03_guides/USER_GUIDE.md)

**Do:**

```powershell
. .\start_hybridrag.ps1
rag-status
rag-index
rag-query "What changed in the launch checklist?"
```

**Completion check:** you can explain the difference between setup, startup, indexing, and querying without looking it up.

### Phase 2: Understand The Core Architecture

**Outcome:** you can explain what HybridRAG3 is doing during indexing and query execution, and why the system uses hybrid retrieval instead of a single search method.

**Read:**

- [THEORY_OF_OPERATION_EXECUTIVE.md](../02_architecture/THEORY_OF_OPERATION_EXECUTIVE.md)
- [TECHNICAL_THEORY_OF_OPERATION_RevC.md](../02_architecture/TECHNICAL_THEORY_OF_OPERATION_RevC.md)
- [GLOSSARY.md](../03_guides/GLOSSARY.md)

**Do:**

- trace one query from question to retrieval to answer
- trace one indexing run from file parsing to chunking to storage
- identify where offline versus online behavior diverges

**Completion check:** you can answer these three questions in plain English:

1. Why is HybridRAG3 better than keyword search alone?
2. Why is it safer than sending documents straight to a generic chatbot?
3. Why do citations matter for trust?

### Phase 3: Learn Both Working Surfaces

**Outcome:** you can operate the system from either PowerShell or the GUI and know when each interface is the better tool.

**Read:**

- [CLI_GUIDE.md](../03_guides/CLI_GUIDE.md)
- [GUI_GUIDE.md](../03_guides/GUI_GUIDE.md)
- [SHORTCUT_SHEET.md](../03_guides/SHORTCUT_SHEET.md)

**Do:**

- launch the desktop app with `start_gui.bat`
- launch the browser surfaces with `rag-server`
- switch offline and online modes
- run one health command and one diagnostic command

**Completion check:** you can tell a teammate which interface to use for:

- a fast scripted operator workflow
- a visual live demo
- a shared browser session

### Phase 4: Become Demo-Ready

**Outcome:** you can present the system in a short meeting, show trust-building behavior, and survive the first wave of objections.

**Read:**

- [DEMO_PREP.md](../04_demo/DEMO_PREP.md)
- [DEMO_GUIDE.md](../04_demo/DEMO_GUIDE.md)
- [DEMO_QA_PREP.md](../04_demo/DEMO_QA_PREP.md)

**Do:**

- prepare one strong “wow” query
- prepare one unanswerable question that proves refusal behavior
- prepare one security or prompt-injection answer
- rehearse the 5-minute arc: problem, solution, proof, value, next step

**Completion check:** you can deliver the live demo without narrating config details or falling back to jargon.

### Phase 5: Learn The Guardrails

**Outcome:** you understand the repo's security, release, and operator boundaries well enough to avoid dangerous shortcuts.

**Read:**

- [DEFENSE_MODEL_AUDIT.md](../05_security/DEFENSE_MODEL_AUDIT.md)
- [GIT_REPO_RULES.md](../05_security/GIT_REPO_RULES.md)
- [INTERFACES.md](../02_architecture/INTERFACES.md)
- [SPRINT_PLAN.md](../09_project_mgmt/SPRINT_PLAN.md) if you are joining active development work

**Do:**

- review how offline versus online posture is controlled
- identify which commands are everyday user commands versus operator-only tools
- confirm where shared deployment workflows diverge from single-machine workflows

**Completion check:** you know which docs are authoritative before changing code, docs, or deployment posture.

## High-Impact Reading Order

If time is tight, use this compressed order:

1. [USER_GUIDE.md](../03_guides/USER_GUIDE.md)
2. [CLI_GUIDE.md](../03_guides/CLI_GUIDE.md) or [GUI_GUIDE.md](../03_guides/GUI_GUIDE.md)
3. [THEORY_OF_OPERATION_EXECUTIVE.md](../02_architecture/THEORY_OF_OPERATION_EXECUTIVE.md)
4. [DEMO_PREP.md](../04_demo/DEMO_PREP.md)
5. [DEMO_QA_PREP.md](../04_demo/DEMO_QA_PREP.md)

That sequence is usually enough to make someone productive and credible in the first working day.

## Optional Deep Dive Library

Use these only after the core curriculum:

- [DEMO_LEARNING_PATH.md](../04_demo/DEMO_LEARNING_PATH.md) for curated external reading by topic
- [MODE_AUTOTUNE_GUIDE.md](../03_guides/MODE_AUTOTUNE_GUIDE.md) for tuning workflow depth
- [FORMAT_SUPPORT.md](../02_architecture/FORMAT_SUPPORT.md) for parser/file-type specifics
- `docs/research/` for exploratory notes
- `docs/archive/` for superseded historical context

## What Not To Read First

Do not start with:

- `docs/09_project_mgmt/` checkpoint packets
- `docs/archive/`
- old handoff files
- long external reading lists

Those are useful after you have a working mental model, not before.
