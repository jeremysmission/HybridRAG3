# Checkpoint -- GUI BAT Launcher Doc Reject Fix

- Created: 2026-03-13_155214
- Updated: 2026-03-13_155214
- Timestamp: 2026-03-13_155214
- Session ID: codex-hybridrag3-gui-bat-doc-reject-fix-20260313-155207
- Topic: GUI BAT Launcher Doc Reject Fix

## What Changed

- Fixed the QA-rejected doc slice for the BAT launcher/user-guide packet.
- Updated `docs/03_guides/USER_GUIDE.md` so it now:
  - points to the real printable outputs under `docs/_printable/20_User_Guide.docx` and `docs/_printable/21_GUI_Guide.docx`
  - explicitly documents `start_gui.bat` and `start_gui.bat --detach` as the desktop GUI launch path
- Updated `docs/03_guides/GUI_GUIDE.md` so it now:
  - explicitly documents `start_gui.bat` and `start_gui.bat --detach`
  - points to the real printable GUI guide output under `docs/_printable/21_GUI_Guide.docx`
- Regenerated the printable DOCX outputs after the markdown fixes.

## Tests

- `python tools\markdown_to_docx.py docs\03_guides\USER_GUIDE.md --output docs\_printable\20_User_Guide.docx`
  - result: succeeded
- `python tools\markdown_to_docx.py docs\03_guides\GUI_GUIDE.md --output docs\_printable\21_GUI_Guide.docx`
  - result: succeeded
- `python -m pytest tests/test_start_gui_bat.py -q`
  - result: `5 passed`
- `python -m pytest tests/test_launch_gui_startup.py -q`
  - result: `6 passed`
- `python tests\virtual_test_setup_wizard.py`
  - result: `54 PASS, 0 FAIL`
- `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
- `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --dry-run`
  - result: correct repo-root and terminal target
- `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --detach --dry-run`
  - result: correct detached `pythonw.exe` target
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `705 passed, 7 skipped, 7 warnings`

## Open Items

- Ready for QA rerun on the BAT launcher + user-guide slice.
- Sprint-critical blocker after this remains `13.6 -- Live Authenticated-Online Soak Refresh`, which is still environment-blocked on this workstation.
