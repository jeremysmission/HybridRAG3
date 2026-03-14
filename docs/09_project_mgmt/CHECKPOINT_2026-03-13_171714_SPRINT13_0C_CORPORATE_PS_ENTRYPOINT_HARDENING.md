# Sprint 13 Corporate PowerShell Entrypoint Hardening

- Created: 2026-03-13_171714
- Updated: 2026-03-13_171714
- Timestamp: 2026-03-13_171714
- Session ID: codex-hybridrag3-corporate-ps-20260313
- Topic: sprint13-corporate-ps-entrypoint-hardening

## What Changed

- Added a process-scope execution-policy bypass block to the direct PowerShell entrypoints used in the managed-machine operator path:
  - `start_hybridrag.ps1`
  - `tools/launch_gui.ps1`
  - `tools/setup_home.ps1`
  - `tools/build_usb_deploy_bundle.ps1`
  - `tools/usb_install_offline.ps1`
- Hardened direct PowerShell GUI launch:
  - `tools/launch_gui.ps1` now resets the working directory to repo root
  - exports `HYBRIDRAG_PROJECT_ROOT`
  - exports `.venv` context before launching the GUI
- Hardened USB bundle building:
  - `tools/build_usb_deploy_bundle.ps1` now resolves repo `.venv\Scripts\python.exe` from `$projectRoot` instead of the caller working directory
- Closed the lingering launcher-doc reject detail:
  - fixed the stale printable path at the bottom of `docs/03_guides/GUI_GUIDE.md`
  - regenerated `docs/_printable/21_GUI_Guide.docx`
- Added regression coverage in:
  - `tests/test_powershell_entrypoints.py`
  - `tests/virtual_test_setup_scripts.py`

## Tests

- `python -m pytest tests/test_powershell_entrypoints.py tests/test_start_gui_bat.py tests/test_launch_gui_startup.py -q`
  - result: `14 passed`
- `python tests\virtual_test_setup_scripts.py`
  - result: `107 passed, 0 failed`
- `python tests\virtual_test_setup_group_policy.py`
  - result: `30 passed, 0 failed`
- `python tests\virtual_test_setup_wizard.py`
  - result: `54 PASS, 0 FAIL`
- `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
- `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --dry-run`
  - result: correct repo-root and terminal target
- `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --detach --dry-run`
  - result: correct detached `pythonw.exe` target
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `709 passed, 6 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `832 passed, 4 skipped, 7 warnings`

## Open Items

- `13.0b` and `13.0c` still need QA rerun/acceptance.
- Sprint `13.6` remains environment-blocked on missing shared token and online API credentials.
