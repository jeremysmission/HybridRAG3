# Work Laptop -- Fresh .venv Setup Guide

Last Updated: 2026-02-23

---

## Before You Start

**Turn off OneDrive sync** for your project folder. OneDrive locks .pyc
files mid-compile, corrupts SQLite databases, and tries to sync thousands
of files in site-packages. It will slow down your GUI (dropdown lag,
disk I/O spikes) and can corrupt the .venv entirely.

Right-click your HybridRAG3 folder in File Explorer > "Free up space"
or exclude it from OneDrive sync in OneDrive Settings > Account >
Choose folders.

---

## QUIRK: cmd vs PowerShell

Your work laptop may alias `cmd` to PowerShell without telling you.
Check your window title bar -- it will say "Command Prompt" or
"PowerShell" (or "Windows PowerShell").

**How to tell:** If you type `rmdir /s /q .venv` and get this error:

```
Remove-Item : A positional parameter cannot be found that accepts argument '/q'
```

...you are in **PowerShell**, not cmd. The two shells use different
syntax for common operations:

| Task | cmd syntax | PowerShell syntax |
|------|-----------|-------------------|
| Delete folder | `rmdir /s /q .venv` | `Remove-Item -Recurse -Force .venv` |
| Set env var | `set PYTHONPATH=C:\path` | `$env:PYTHONPATH = 'C:\path'` |
| Activate venv | `.venv\Scripts\activate.bat` | `.venv\Scripts\Activate.ps1` |

**This guide uses cmd syntax.** To open a real cmd window:

1. Press `Win+R`
2. Type `cmd` and press Enter
3. If the title bar says "PowerShell" anyway, type `cmd` and press Enter
   again to start a cmd shell inside it

---

## Step 1: Check for Python

```
python --version
```

If this returns a version number (e.g., `Python 3.12.1`), Python is
installed. Skip to Step 3.

If it says `'python' is not recognized`, also try:

```
py --list
```

This shows every Python version the Windows launcher knows about:

```
 -V:3.12 *        Python 3.12 (64-bit)
 -V:3.9           Python 3.9 (64-bit)
```

The `*` marks the default. If nothing comes back, Python is not
installed. Continue to Step 2.

If even `py` is not found, do a full drive scan (takes a minute):

```
where /r C:\ python.exe
```

If still nothing, Python is genuinely not on the machine.

---

## Step 2: Install Python (If Missing)

Python must be installed through your company's approved software
channel. This is typically one of:

- **Software Center** (SCCM/MECM -- most common)
- **Company Portal** (Intune-managed laptops)
- **ServiceNow** software catalog (request-based)

Search for "Python" and request **3.12** (approved version: 3.12rc3).
Python 3.11 also works. Python 3.9 and 3.10 are compatible but 3.11+
is preferred.

**IMPORTANT:** If the installer offers "Add Python to PATH", check
that box. If you installed without it, you will need to add the Python
folder to your PATH manually or use the full path to python.exe.

After install, close and reopen your cmd window, then verify:

```
python --version
```

---

## Step 3: Clean Up Old .venv (If Present)

If you have a leftover .venv folder (e.g., from OneDrive sync), delete
it first. In **cmd**:

```
rmdir /s /q .venv
```

If you are in **PowerShell** (check title bar):

```
Remove-Item -Recurse -Force .venv
```

If you get "access denied" errors, close all Python processes first:

```
taskkill /f /im python.exe
```

Then retry the delete.

---

## Step 4: Navigate to Project Folder

```
cd /d D:\HybridRAG3
```

The `/d` flag switches drives. Without it, `cd D:\HybridRAG3` does
nothing if you are currently on C:.

If your project is on C: (e.g., `C:\Users\you\HybridRAG3`):

```
cd C:\Users\you\HybridRAG3
```

Verify you are in the right place:

```
dir requirements.txt
```

You should see `requirements.txt` listed. If not, you are in the
wrong folder.

---

## Step 5: Create the Virtual Environment

Using `py` launcher (if available):

```
py -3.12 -m venv .venv
```

Or with whichever version you have:

```
py -3.11 -m venv .venv
```

If `py` is not available, use python directly:

```
python -m venv .venv
```

This creates the `.venv` folder with a clean Python install inside it.
Takes about 10 seconds.

---

## Step 6: Activate the Virtual Environment

In **cmd**:

```
.venv\Scripts\activate.bat
```

In **PowerShell**:

```
.venv\Scripts\Activate.ps1
```

**Success indicator:** You will see `(.venv)` at the start of your
command prompt:

```
(.venv) D:\HybridRAG3>
```

If PowerShell blocks Activate.ps1 with an execution policy error, try:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.venv\Scripts\Activate.ps1
```

If that is also blocked by Group Policy, switch to cmd (see QUIRK
section at top).

---

## Step 7: Upgrade pip (With Proxy Bypass)

Corporate proxies intercept HTTPS traffic, which makes pip think it is
being attacked. The `--trusted-host` flags tell pip to accept the
proxy's certificate for PyPI:

```
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

---

## Step 8: Install pip-system-certs (One-Time SSL Fix)

This package tells Python to trust the same certificates that Windows
trusts. After this, you never need `--trusted-host` again:

```
pip install pip-system-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

This is the **last time** you use `--trusted-host`. All future pip
installs will work without flags because pip-system-certs makes Python
use your corporate CA from the Windows certificate store.

---

## Optional: Start the Install Timer

Open a **second** cmd window, navigate to the project folder, and run:

```
python tools\py\clock.py
```

This ticks every second and logs elapsed time to `clock_log.txt`.
Press Ctrl+C when the install finishes to stop it. The total elapsed
time is printed and saved. Copy this script to the work laptop with
the rest of the project files.

To read the log later: `python tools\py\clock.py --read`

---

## Step 9: Install All Dependencies

**IMPORTANT:** On the work laptop, always use `requirements_approved.txt`.
This is the software-cleared package list. `requirements.txt` may contain
packages that have not been through approval.

```
pip install -r requirements_approved.txt
```

No `--trusted-host` needed (pip-system-certs handles it).

This downloads ~800 MB of packages. PyTorch alone is ~280 MB. Expect
5-15 minutes depending on network speed.

**If it still throws SSL errors** (rare -- means your corporate CA is
not in the Windows store), fall back to:

```
pip install -r requirements_approved.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

---

## Step 10: Verify the Install

```
python -c "import torch; import sentence_transformers; print('OK')"
```

Should print `OK`.

If it errors, check which package failed:

```
python -c "import torch; print('torch OK')"
python -c "import sentence_transformers; print('ST OK')"
python -c "import fastapi; print('fastapi OK')"
python -c "import pdfplumber; print('pdfplumber OK')"
```

---

## Step 11: Launch the GUI

Double-click `start_gui.bat` in File Explorer, or from cmd:

```
start_gui.bat
```

The GUI should open. If it shows "[WARN] Virtual environment not found",
you are not in the right folder or the .venv was not created properly.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `rmdir /s /q` gives "positional parameter" error | You are in PowerShell, not cmd. Use `Remove-Item -Recurse -Force .venv` |
| `python` not recognized | Python not installed or not on PATH. Check Step 1-2. |
| `py -3.11` not found but `py -3.12` works | Use 3.12 -- it is compatible. Adjust the venv command. |
| pip SSL certificate error | Use `--trusted-host` flags (Step 7-8) |
| pip hangs during torch download | PyTorch is ~280 MB. Wait. Or add `--timeout 300` |
| "Access denied" deleting .venv | Close all Python processes: `taskkill /f /im python.exe` |
| Activate.ps1 blocked by Group Policy | Switch to cmd and use `activate.bat` instead |
| start_gui.bat says venv not found | Run from the project root folder, not a subfolder |
| OneDrive re-syncing .venv | Turn off OneDrive sync for the project folder |
| Dropdowns lag in GUI | OneDrive is syncing in background -- turn it off |

---

## What NOT to Sync Between Machines

These are machine-specific and should never be copied from another PC:

| Item | Why |
|------|-----|
| `.venv/` | Different Python version, different OS patches |
| `.model_cache/` | Downloaded locally, ~87 MB |
| `start_hybridrag.ps1` | Contains machine-specific folder paths |
| `config/system_profile.json` | Auto-detected hardware fingerprint |
| API credentials | In Windows Credential Manager, per-user |

---

## Quick Reference: Python Version Compatibility

| Version | Status |
|---------|--------|
| Python 3.9 | Works (minimum supported) |
| Python 3.10 | Works |
| Python 3.11 | Works |
| Python 3.12 | Works (approved on work laptop: 3.12rc3) |
| Python 3.13+ | Not tested -- check before using |
