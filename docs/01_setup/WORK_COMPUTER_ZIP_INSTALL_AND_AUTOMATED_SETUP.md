# HybridRAG3 -- Work Computer ZIP Install and Automated Setup

Last Updated: 2026-03-13

---

## Recommended Path

If you are pulling HybridRAG3 down to a managed work computer as a ZIP file,
this is the recommended install path:

1. Download the ZIP from the repo
2. Extract it to a normal writable folder such as `D:\HybridRAG3`
3. Run `tools\setup_work.bat`
4. Let the script create the `.venv`, configure paths, and run diagnostics

This path is built for corporate PowerShell, proxy, and certificate issues.

---

## What the Automated Installer Does

`tools\setup_work.ps1` is the real installer. `tools\setup_work.bat` is the
recommended launcher for work machines.

The installer will:

1. Detect Python 3.12, 3.11, or 3.10
2. Create or reuse `.venv`
3. Upgrade `pip`
4. Install `pip-system-certs`
5. Install `requirements_approved.txt`
6. Configure `config.yaml`
7. Create `start_hybridrag.ps1` from the template
8. Optionally store online API credentials in Windows Credential Manager
9. Check Ollama
10. Run full local diagnostics

The script is safe to rerun. If it was interrupted, run it again and it will
reuse the existing `.venv` and continue through the remaining steps.

---

## Corporate PowerShell Exception Policy Statements

This matters on managed work machines.

- `tools\setup_work.bat` launches `powershell.exe` with `-ExecutionPolicy Bypass`
- `tools\setup_work.ps1` also attempts `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force`
- Both are session-only exceptions for the current run
- Neither command changes machine-wide or user-wide execution policy permanently

If your machine still blocks PowerShell, use `cmd.exe` to launch the batch file
or have IT confirm the approved execution path for script-based tooling.

---

## Exact ZIP Install Steps

### Step 1 -- Download and extract

1. Download the repo ZIP from GitHub
2. Extract it fully before running anything
3. Do not run from inside the ZIP viewer
4. Put it somewhere writable, for example:

```text
D:\HybridRAG3
```

### Step 2 -- Start the automated installer

From File Explorer:

```text
Double-click tools\setup_work.bat
```

From `cmd.exe`:

```cmd
cd /d D:\HybridRAG3
tools\setup_work.bat
```

From PowerShell:

```powershell
cd D:\HybridRAG3
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\tools\setup_work.ps1
```

### Step 3 -- Answer the wizard prompts

The script will ask for:

- the project folder
- the Python interpreter
- the data/index folder
- the source-document folder
- optional online API credentials

If you already have a `.venv`, the script lets you resume or purge it.

---

## Checkpoints and Tracing

The automated installer now writes setup state to `logs\` so you can recover or
hand the run to QA or IT without guessing what happened.

Artifacts created during setup:

- `logs\setup_checkpoint_latest.json`
  - latest step pointer for the most recent run
- `logs\setup_checkpoint_<timestamp>.json`
  - frozen checkpoint snapshot for that exact run
- `logs\setup_trace_<timestamp>.log`
  - full PowerShell transcript for the run
- `logs\setup_install_<timestamp>.log`
  - package-install output once dependency installation begins

If setup pauses or fails, keep these files. They are the first things to attach
to a troubleshooting handoff.

---

## Virtual Environment Activation

After setup completes, activate the virtual environment with the command that
matches your shell.

### PowerShell

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### cmd.exe

```cmd
.venv\Scripts\activate.bat
```

If `Activate.ps1` is blocked but the batch launcher worked, switch to `cmd.exe`
for activation and use the `.bat` path instead.

---

## Starting HybridRAG3 After Install

### Easiest path

```text
Double-click start_gui.bat
```

### PowerShell path

```powershell
cd D:\HybridRAG3
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
. .\start_hybridrag.ps1
```

### cmd.exe path

```cmd
cd /d D:\HybridRAG3
.venv\Scripts\activate.bat
python src\gui\launch_gui.py
```

---

## If Setup Stops Mid-Run

1. Read `logs\setup_checkpoint_latest.json`
2. Read `logs\setup_trace_<timestamp>.log`
3. If package install failed, also read `logs\setup_install_<timestamp>.log`
4. Fix the reported issue
5. Run `tools\setup_work.bat` again

The script is designed to resume cleanly after interruptions.

---

## Related Docs

- [INSTALL_AND_SETUP.md](INSTALL_AND_SETUP.md)
- [WORK_LAPTOP_VENV_SETUP.md](WORK_LAPTOP_VENV_SETUP.md)
- [ONLINE_API_SETUP_FROM_SCRATCH.md](ONLINE_API_SETUP_FROM_SCRATCH.md)
