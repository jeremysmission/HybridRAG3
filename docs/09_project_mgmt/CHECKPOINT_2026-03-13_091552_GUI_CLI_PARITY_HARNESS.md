# Checkpoint -- GUI/CLI Parity Harness

**Created:** 2026-03-13 09:15 America/Denver  
**Session ID:** `codex-hybridrag3-gui-cli-parity-harness-20260313-091552`  
**Purpose:** capture the new QA harness that tracks whether a future GUI reaches parity with the existing CLI/operator surface.

## What Landed

- Added the parity model and persistence helpers:
  - `tools/gui_cli_parity_model.py`
- Added the Tk QA harness:
  - `tools/gui_cli_parity_harness.py`
- Added focused regression coverage:
  - `tests/test_gui_cli_parity_harness.py`
- Added operator guidance:
  - `docs/03_guides/GUI_CLI_PARITY_HARNESS.md`

## What The Harness Does

- catalogs high-value CLI/operator capabilities
- maps each capability to the intended future GUI surface
- tracks GUI parity status:
  - `missing`
  - `planned`
  - `partial`
  - `implemented`
  - `verified`
- records smoke-command results and QA notes
- saves the working parity artifact to:
  - `output/gui_cli_parity_report.json`

## Verification

- Syntax gate:
  - `.venv\Scripts\python.exe -m py_compile tools\gui_cli_parity_model.py tools\gui_cli_parity_harness.py tests\test_gui_cli_parity_harness.py`
  - result: `passed`
- Headless report dump:
  - `.venv\Scripts\python.exe tools\gui_cli_parity_harness.py --dump-json`
  - result: `passed`
- Focused GUI/tooling slice:
  - `.venv\Scripts\python.exe -m pytest tests/test_gui_cli_parity_harness.py tests/test_gui_demo_smoke_tool.py tests/test_gui_e2e_run.py tests/test_view_aliases.py -q`
  - result: `10 passed, 1 skipped`
- Repo-wide QA evidence after the harness landed:
  - `.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `704 passed, 4 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - result: `78 passed, 1 warning`
- Required virtual suites rerun and green:
  - `phase1`, `phase2`, `phase4`, `view_switching`, `setup_wizard`, `setup_scripts`, `guard_part1`, `guard_part2`, `setup_group_policy`, `ibit_reference`, `offline_isolation`

## Open Items

- expand the capability catalog as new CLI/operator surfaces land
- use the saved report as the acceptance artifact when the future GUI starts absorbing CLI functionality
- consider later whether parts of the catalog should be derived automatically from feature/command registries rather than being maintained entirely by hand
