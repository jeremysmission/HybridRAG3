@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Supports the start rag workflow in this repository.
@REM How to follow: Read each command line in order from top to bottom.
@REM Inputs: Command arguments, environment variables, and local files.
@REM Outputs: Terminal messages and any files changed by called tools.
@REM Safety notes: Confirm paths before running on important data.
@REM ============================
@echo off
title HybridRAG v3
REM ================================================================
REM  HybridRAG v3 -- CLI Launcher (start_rag.bat)
REM ================================================================
REM  GROUP POLICY SAFE: Uses ReadAllText + Invoke-Expression so the
REM  script loads even on work laptops with AllSigned/Restricted GP.
REM  If PowerShell fails entirely, drops to a basic Python prompt.
REM
REM  WHAT THIS DOES:
REM    1. Checks that the .venv exists
REM    2. Tries PowerShell with IEX (bypasses execution policy)
REM    3. If PS fails, activates .venv and opens a basic prompt
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
    echo    py -3.12 -m venv .venv
    echo    .venv\Scripts\pip install -r requirements_approved.txt
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

"%~dp0.venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [FAIL] Virtual environment exists, but its Python executable cannot start.
    echo.
    echo  This usually means .venv was created from a Python install that no longer exists.
    echo  Rebuild it from this repo:
    echo.
    echo    cd "%~dp0"
    echo    Remove-Item -Recurse -Force .venv
    echo    py -3.12 -m venv .venv
    echo    .venv\Scripts\pip install -r requirements_approved.txt
    echo.
    echo  Then double-click this file again.
    echo.
    pause
    exit /b 2
)

REM ---- Launch via PowerShell (full environment setup) ----
REM   ReadAllText reads the .ps1 as plain text, then Invoke-Expression
REM   runs it. This is NOT subject to execution policy, so it works
REM   even when Group Policy is set to AllSigned or Restricted.
REM   Set-ExecutionPolicy is attempted first (for dot-sourced child
REM   scripts) but errors are suppressed -- it may fail under GP.
powershell -NoExit -Command "Set-ExecutionPolicy -Scope Process Bypass -Force 2>$null; $p=Join-Path '%~dp0' 'start_hybridrag.ps1'; $c=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8); iex $c"
if errorlevel 1 goto :fallback
goto :end

:fallback
REM ---- Fallback: basic Python environment (no PowerShell needed) ----
REM   This runs if PowerShell is completely broken or unavailable.
REM   You get a command prompt with Python available, but without
REM   the rag-* shortcut commands.
echo.
echo  [WARN] PowerShell setup had an issue. Opening basic mode...
echo         You can still run Python commands directly.
echo         Example: python src\gui\launch_gui.py
echo.

set "PYTHONPATH=%~dp0"
set "HYBRIDRAG_PROJECT_ROOT=%~dp0"
call "%~dp0.venv\Scripts\activate.bat"
cd /d "%~dp0"
cmd /k echo [OK] Basic mode ready. Type: python src\gui\launch_gui.py

:end
