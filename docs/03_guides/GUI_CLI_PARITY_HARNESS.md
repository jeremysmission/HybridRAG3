# GUI CLI Parity Harness

**Created:** 2026-03-13  
**Purpose:** provide a QA harness for tracking whether an upcoming GUI has reached parity with the major CLI/operator capabilities already present in the repo.

## What It Is

The parity tooling now has two parts:

- `tools/gui_cli_parity_harness.py`
- `tools/gui_cli_parity_model.py`
- `tools/gui_cli_parity.py`
- `src/gui/testing/gui_cli_parity_harness.py`
- `src/gui/testing/gui_cli_parity_probes.py`

They serve different purposes:

- `tools/gui_cli_parity_harness.py`
  - interactive Tk parity board
  - lets QA track capability status and notes by hand
  - persists the catalog-style parity ledger
- `tools/gui_cli_parity.py`
  - headless runtime runner
  - boots the real GUI test shell and executes CLI-equivalent checks
  - emits an automated QA report for pass/fail/skip/manual/missing states

Together they answer:

- what CLI capabilities exist today
- which future GUI surface each capability belongs to
- whether the GUI is currently `missing`, `planned`, `partial`, `implemented`, or `verified`
- whether the current GUI runtime can actually exercise core CLI-equivalent behaviors

## Why It Exists

The repo already has many CLI and script-level operator surfaces.

If a future GUI is expected to "have everything the CLI has", QA needs a structured way to track parity instead of relying on memory.

This harness set gives QA both:

- a live parity board for long-running GUI roadmap tracking
- a runtime-backed checker for concrete GUI acceptance evidence

## Usage

Open the parity board:

```powershell
python tools/gui_cli_parity_harness.py
```

Dump the merged catalog/report JSON without opening Tk:

```powershell
python tools/gui_cli_parity_harness.py --dump-json
```

Run the automated runtime checker:

```powershell
python tools/gui_cli_parity.py
```

List the automated runtime targets:

```powershell
python tools/gui_cli_parity.py --list
```

## Report Output

The parity board writes a catalog report to:

- `output/gui_cli_parity_report.json`

unless a custom `--report` path is supplied.

The runtime runner writes an automated QA report to:

- `output/gui_cli_parity_runtime_report.json`

## What To Update Over Time

When more CLI capabilities matter for parity:

1. add them to `build_default_catalog()` in `tools/gui_cli_parity_model.py`
2. map them to the intended GUI target
3. give them a safe smoke command when possible
4. add or extend the runtime probe in `src/gui/testing/gui_cli_parity_probes.py` when the GUI can exercise that capability automatically

## Related Tests

- `tests/test_gui_cli_parity_harness.py`
- `tools/gui_cli_parity.py --list`
- existing GUI harness tests such as:
  - `tests/test_gui_demo_smoke_tool.py`
  - `tests/test_gui_e2e_run.py`
