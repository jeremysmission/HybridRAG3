# GUI E2E "Human Clicker" (Tkinter)

This tool simulates a person clicking every GUI button and menu item and outputs a JSON report
that you can paste into AI CLI tool for diagnosis.

## Why this exists
AI CLI tool can run unit/integration tests, but it can't *interact* with a GUI. This runner
*drives* the GUI via Tkinter's widget API (invoke/event_generate), so we can validate wiring
end-to-end.

## Quick start (mock mode — safe, offline)
```bash
python tools/gui_e2e/run.py --mode mock --report gui_e2e_report.json
```

## Real mode (live backends)
```bash
python tools/gui_e2e/run.py --mode real --show --report gui_e2e_report.json
```

## Excluding risky actions
The runner skips common destructive items by default (Exit/Quit/Close). Add more excludes:
```bash
python tools/gui_e2e/run.py --exclude "Reset" --exclude "Delete" --report out.json
```

## What it tests
- Menu items (File/Admin/Help) by invoking their callbacks
- Buttons (tk.Button and ttk.Button) via `.invoke()`
- Comboboxes (ttk.Combobox): cycles through up to 3 values (configurable)
- Checkbuttons/radiobuttons: toggles once

## How to use with AI CLI tool
1. Run the tool to generate `gui_e2e_report.json`
2. Paste the JSON into the AI tool and ask it to:
   - Identify failing actions by label/path
   - Locate the handler code (widget path + text helps)
   - Propose a redesign fix (not patch) if wiring is wrong

## Environment variables
- `GUI_E2E_ALLOW_DIALOGS=1` : allow real modal dialogs (not recommended)
- `GUI_E2E_COMBO_MAX=3`      : max combobox values to cycle per widget
