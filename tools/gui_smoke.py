from __future__ import annotations
import sys
import time

from src.gui.core.paths import AppPaths
from src.gui.core.controller import Controller
from src.gui.core.actions import SaveNoteAction, ExportCsvAction

def main() -> int:
    paths = AppPaths.default()
    ctrl = Controller(paths)

    # Minimal smoke: write a note to Downloads and ensure file exists
    ctrl.dispatch_save_note(SaveNoteAction(note_id="smoke", content="HybridRAG3 GUI smoke test"))
    # Wait briefly for background job
    time.sleep(1.0)
    last = ctrl.downloads.last()
    if not last or not last.get("exists"):
        print("FAIL: No download written", file=sys.stderr)
        print("Diagnostics:", ctrl.diag.run_dir, file=sys.stderr)
        return 2

    print("PASS: gui_smoke download exists:", last["path"])
    print("Diagnostics:", ctrl.diag.run_dir)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
