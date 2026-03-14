# HybridRAG3 Guides Index

**Created:** 2026-03-14  
**Last updated:** 2026-03-14 13:55 America/Denver  
**Purpose:** route users to the right guide, define the role of each canonical doc, and reduce overlap between onboarding, operations, demo prep, and deep reference material.

## Start Here

Use the documents in this order:

1. `README.md` for the repo overview and quick start
2. [USER_GUIDE.md](USER_GUIDE.md) for day-to-day interface selection
3. [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) for the canonical learning path
4. the role-specific guides below only when you know what job you are trying to do

This folder is intentionally narrower than the repo root README:

- the repo README owns the broad project story
- this file owns guide routing
- `USER_GUIDE.md` owns interface triage
- `CLI_GUIDE.md` owns command workflows
- `GUI_GUIDE.md` owns desktop and browser workflows
- `STUDY_GUIDE.md` owns the learning sequence

## Pick Your Route

| If you need to... | Start with | Then read |
|---|---|---|
| get productive quickly on one machine | [USER_GUIDE.md](USER_GUIDE.md) | [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) |
| work mainly from PowerShell | [CLI_GUIDE.md](CLI_GUIDE.md) | [USER_GUIDE.md](USER_GUIDE.md), [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) |
| work mainly from the desktop GUI or browser surfaces | [GUI_GUIDE.md](GUI_GUIDE.md) | [USER_GUIDE.md](USER_GUIDE.md), [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) |
| explain or demo the system to leadership | [DEMO_PREP.md](../04_demo/DEMO_PREP.md) | [DEMO_GUIDE.md](../04_demo/DEMO_GUIDE.md), [DEMO_QA_PREP.md](../04_demo/DEMO_QA_PREP.md) |
| learn the system in a deliberate sequence | [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) | [DEMO_LEARNING_PATH.md](../04_demo/DEMO_LEARNING_PATH.md) only for optional external deep dives |
| maintain or extend the system | [TECHNICAL_THEORY_OF_OPERATION_RevC.md](../02_architecture/TECHNICAL_THEORY_OF_OPERATION_RevC.md) | [INTERFACES.md](../02_architecture/INTERFACES.md), [SPRINT_PLAN.md](../09_project_mgmt/SPRINT_PLAN.md) |

## Canonical Guide Set

### Daily Use

| Document | Role |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | front door for normal users; fastest way to choose CLI, desktop GUI, or browser flow |
| [CLI_GUIDE.md](CLI_GUIDE.md) | command-first workflow, diagnostics, profiles, credentials, and operator tasks |
| [GUI_GUIDE.md](GUI_GUIDE.md) | desktop window map, browser dashboard/admin surfaces, and visual workflow guidance |
| [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) | phone-friendly quick reference after the basics are already understood |

### Learning and Onboarding

| Document | Role |
|---|---|
| [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) | canonical repo-first curriculum with outcomes and completion checks |
| [GLOSSARY.md](GLOSSARY.md) | plain-English support doc for technical terms and acronyms |
| [THEORY_OF_OPERATION_EXECUTIVE.md](../02_architecture/THEORY_OF_OPERATION_EXECUTIVE.md) | management-friendly explanation of the system and business value |
| [TECHNICAL_THEORY_OF_OPERATION_RevC.md](../02_architecture/TECHNICAL_THEORY_OF_OPERATION_RevC.md) | technical architecture and pipeline reference for builders and maintainers |

### Demo and Communication

| Document | Role |
|---|---|
| [DEMO_PREP.md](../04_demo/DEMO_PREP.md) | primary talk track and rehearsal checklist |
| [DEMO_GUIDE.md](../04_demo/DEMO_GUIDE.md) | narrative structure, positioning, and audience-specific demo guidance |
| [DEMO_QA_PREP.md](../04_demo/DEMO_QA_PREP.md) | objection handling and likely audience questions |
| [DEMO_LEARNING_PATH.md](../04_demo/DEMO_LEARNING_PATH.md) | external research library for optional background reading after the core curriculum |

### Setup, Security, and Operations

| Document | Role |
|---|---|
| [INSTALL_AND_SETUP.md](../01_setup/INSTALL_AND_SETUP.md) | complete setup path for new machines |
| [WORK_COMPUTER_ZIP_INSTALL_AND_AUTOMATED_SETUP.md](../01_setup/WORK_COMPUTER_ZIP_INSTALL_AND_AUTOMATED_SETUP.md) | recommended managed-workstation ZIP install workflow |
| [DEFENSE_MODEL_AUDIT.md](../05_security/DEFENSE_MODEL_AUDIT.md) | approved model stack and sourcing posture |
| [GIT_REPO_RULES.md](../05_security/GIT_REPO_RULES.md) | git and sanitization guardrails for maintainers |

## Read Later, Not First

These are useful, but they are not the starting point for learning or daily use:

- `docs/09_project_mgmt/` checkpoint and sprint documents
- `docs/archive/` superseded historical material
- `docs/cross_ai_collabs/` investigation notes and QA follow-ups
- `docs/research/` exploratory research notes

## Redundancy Rules

When you update docs in this area, keep the ownership boundaries intact:

- do not duplicate the repo overview from `README.md` into this guide index
- do not copy command walkthroughs into `USER_GUIDE.md`; link to `CLI_GUIDE.md`
- do not copy GUI panel details into `USER_GUIDE.md`; link to `GUI_GUIDE.md`
- do not create another “master curriculum” outside `docs/08_learning/STUDY_GUIDE.md`
- do not use demo-prep docs as general onboarding docs; they are for rehearsed communication
