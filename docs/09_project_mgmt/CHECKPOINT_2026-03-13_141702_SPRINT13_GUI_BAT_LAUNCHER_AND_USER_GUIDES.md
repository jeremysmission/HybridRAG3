# Checkpoint -- Sprint 13 GUI BAT Launcher And User Guides

- Created: 2026-03-13_141702
- Updated: 2026-03-13_141702
- Timestamp: 2026-03-13_141702
- Session ID: codex-hybridrag3-bat-launcher-user-guides-20260313-141611
- Topic: Sprint 13 GUI BAT Launcher And User Guides

## What Changed

- Hardened the shipped GUI batch launcher in `start_gui.bat`.
- The launcher now:
  - resolves the project root from the batch-file location
  - validates the local `.venv` and `src\gui\launch_gui.py`
  - sets `HYBRIDRAG_PROJECT_ROOT`, `PYTHONPATH`, localhost proxy bypass, and UTF-8 env vars
  - supports `--detach` for detached GUI startup
  - supports dry-run/no-pause automation so QA can execute the real BAT without opening the app
- Added Windows batch-execution regressions in `tests/test_start_gui_bat.py`.
- Refreshed the main end-user docs to match the current shipped GUI and CLI:
  - `docs/03_guides/USER_GUIDE.md`
  - `docs/03_guides/CLI_GUIDE.md`
  - `docs/03_guides/GUI_GUIDE.md`
- Aligned the markdown guides with the matching guide-local Word outputs:
  - `docs/03_guides/USER_GUIDE.docx`
  - `docs/03_guides/CLI_GUIDE.docx`
  - `docs/03_guides/GUI_GUIDE.docx`
- The numbered packet copies remain available for the landing guide and GUI guide:
  - `docs/_printable/20_User_Guide.docx`
  - `docs/_printable/21_GUI_Guide.docx`
- Refreshed the main doc-entry links so the root README and setup guide expose the current guide set.
- Synced the project records:
  - `docs/09_project_mgmt/SPRINT_PLAN.md`
  - `docs/09_project_mgmt/PM_TRACKER_2026-03-12_110046.md`

## Tests

- `python -m pytest tests/test_start_gui_bat.py -q`
  - result: `5 passed`
- `python -m pytest tests/test_launch_gui_startup.py -q`
  - result: `6 passed`
- `python tests\virtual_test_setup_wizard.py`
  - result: `54 PASS, 0 FAIL`
- `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `704 passed, 8 skipped, 7 warnings`
- `python tools\markdown_to_docx.py docs\03_guides\USER_GUIDE.md --output docs\_printable\20_User_Guide.docx`
  - result: succeeded
- `python tools\markdown_to_docx.py docs\03_guides\CLI_GUIDE.md --output docs\03_guides\CLI_GUIDE.docx`
  - result: succeeded
- `python tools\markdown_to_docx.py docs\03_guides\GUI_GUIDE.md --output docs\_printable\21_GUI_Guide.docx`
  - result: succeeded

## Open Items

- BAT launcher slice is ready for QA.
- Guide refresh is attached to the same handoff so QA can check the launcher against current docs.
- `13.6 -- Live Authenticated-Online Soak Refresh` remains environment-blocked by missing shared token and online API credentials on this workstation.
