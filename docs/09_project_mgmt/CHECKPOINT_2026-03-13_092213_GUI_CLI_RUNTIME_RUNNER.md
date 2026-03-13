# Checkpoint -- GUI CLI Runtime Runner

**Created:** 2026-03-13 09:22 America/Denver  
**Session ID:** `codex-hybridrag3-gui-cli-runtime-runner-20260313-092213`  
**Purpose:** capture the automated runtime companion added on top of the existing GUI/CLI parity tracker.

## What Landed

- Added the headless runtime harness core:
  - `src/gui/testing/gui_cli_parity_harness.py`
  - `src/gui/testing/gui_cli_parity_probes.py`
- Added the operator-facing entrypoint:
  - `tools/gui_cli_parity.py`
- Updated supporting docs and sprint records so QA can distinguish:
  - the parity-board ledger
  - the runtime-backed acceptance runner

## Design Intent

- Keep the existing parity board as the long-lived manual catalog and note-taking surface.
- Add a second layer that boots the real GUI test shell headlessly and checks CLI-equivalent capabilities with machine-readable results.
- Keep report artifacts separate:
  - parity board: `output/gui_cli_parity_report.json`
  - runtime runner: `output/gui_cli_parity_runtime_report.json`

## Current Automated Coverage

- `rag-gui`
- `rag-paths`
- `rag-status`
- `rag-diag`
- `rag-index`
- `rag-query`
- `rag-mode-online`
- `rag-mode-offline`
- `rag-profile`
- `rag-models`
- `rag-set-model`
- `rag-cred-status`
- manual-only or missing surfaces are flagged explicitly instead of being silently treated as pass

## Verification

- syntax gate:
  - `.venv\Scripts\python.exe -m py_compile src\gui\testing\gui_cli_parity_harness.py src\gui\testing\gui_cli_parity_probes.py tools\gui_cli_parity.py tests\test_gui_cli_parity_harness.py`
  - result: `passed`
- focused unit slice:
  - `.venv\Scripts\python.exe -m pytest tests/test_gui_cli_parity_harness.py -q`
  - result: `4 passed`
- command discovery smoke:
  - `.venv\Scripts\python.exe tools\gui_cli_parity.py --list`
  - result: `passed`
- runtime smoke against non-backend parity targets:
  - `.venv\Scripts\python.exe tools\gui_cli_parity.py --only rag-gui --only rag-paths --only rag-status --attach-backends never --report output\gui_cli_parity_runtime_smoke.json`
  - result: `passed=3 failed=0 skipped=0 missing=0 manual=0`

## Open Items

- wire additional probes as future GUI surfaces become executable, especially the remaining credential and server-control paths
- decide later whether the parity-board UI should ingest the runtime-runner JSON directly or keep the two artifacts separate by design
- run the backend-enabled index/query probes in the full QA environment whenever GUI parity becomes an explicit acceptance gate
