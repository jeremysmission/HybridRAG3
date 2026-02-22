@echo off
title HybridRAG v3 GUI
REM ================================================================
REM  HybridRAG v3 -- GUI Launcher (start_gui.bat)
REM ================================================================
REM  GROUP POLICY SAFE: Uses ReadAllText + Invoke-Expression so the
REM  script loads even on work laptops with AllSigned/Restricted GP.
REM  If PowerShell fails entirely, falls back to launching Python
REM  directly with minimal environment variables.
REM
REM  WHAT THIS DOES:
REM    1. Checks that the .venv exists
REM    2. Tries PowerShell with IEX (bypasses execution policy)
REM    3. If PS fails, launches Python directly (basic mode)
REM ================================================================

REM ---- Check for virtual environment ----
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo.
    echo  [WARN] Virtual environment not found.
    echo.
    echo  This is normal on first run. You need to create a .venv first.
    echo  Open a command prompt and run these commands:
    echo.
    echo    cd "%~dp0"
    echo    py -3.11 -m venv .venv
    echo    .venv\Scripts\pip install -r requirements.txt
    echo.
    echo  Then double-click this file again.
    echo.
    echo  For the full walkthrough, see:
    echo    START_HERE.txt
    echo    docs\INSTALL_AND_SETUP.md
    echo.
    pause
    exit /b 1
)

REM ---- Launch via PowerShell (full environment setup) ----
REM   ReadAllText reads the .ps1 as plain text, then Invoke-Expression
REM   runs it. This is NOT subject to execution policy, so it works
REM   even when Group Policy is set to AllSigned or Restricted.
REM   Set-ExecutionPolicy is attempted first (for dot-sourced child
REM   scripts) but errors are suppressed -- it may fail under GP.
powershell -NoExit -Command "Set-ExecutionPolicy -Scope Process Bypass -Force 2>$null; $p=Join-Path '%~dp0' 'start_hybridrag.ps1'; $c=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8); iex $c; python src\gui\launch_gui.py"
if errorlevel 1 goto :fallback
goto :end

:fallback
REM ---- Fallback: launch Python directly (no PowerShell needed) ----
REM   This runs if PowerShell is completely broken or unavailable.
REM   The GUI will still work, but without the rag-* CLI commands.
echo.
echo  [WARN] PowerShell setup had an issue. Trying direct launch...
echo         The GUI will still work normally.
echo.

set "PYTHONPATH=%~dp0"
set "HYBRIDRAG_PROJECT_ROOT=%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0src\gui\launch_gui.py"
if errorlevel 1 (
    echo.
    echo  [FAIL] Could not start HybridRAG GUI.
    echo.
    echo  Common fixes:
    echo    1. Make sure Python 3.11 is installed
    echo    2. Re-create .venv:  py -3.11 -m venv .venv
    echo    3. Re-install packages:  .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
)

:end
