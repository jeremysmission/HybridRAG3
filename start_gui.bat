@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Supports the start gui workflow in this repository.
@REM How to follow: Read each command line in order from top to bottom.
@REM Inputs: Command arguments, environment variables, and local files.
@REM Outputs: Terminal messages and any files changed by called tools.
@REM Safety notes: Confirm paths before running on important data.
@REM ============================
@echo off
title HybridRAG v3 GUI
setlocal
cd /d "%~dp0"

REM ================================================================
REM  HybridRAG v3 -- One-Click GUI Launcher (start_gui.bat)
REM ================================================================

REM ---- CHECK VENV ----
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo  [FAIL] Missing venv python: "%PY%"
  echo.
  echo  Run INSTALL.bat first, or manually:
  echo    py -3.12 -m venv .venv
  echo    .venv\Scripts\pip install -r requirements_approved.txt
  echo.
  pause
  exit /b 2
)

REM ---- PYTHON ENVIRONMENT ----
set "PYTHONPATH=%CD%"
set "HYBRIDRAG_PROJECT_ROOT=%CD%"

REM ---- NETWORK LOCKDOWN ----
REM NO_PROXY prevents corporate proxy from intercepting 127.0.0.1
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"
REM Start unlocked for app-managed mode switching (offline/online).
REM The GUI mode switch will set/clear this at runtime.
set "HYBRIDRAG_NETWORK_KILL_SWITCH=0"
set "HYBRIDRAG_OFFLINE=0"
REM Development UI controls (chunking/tuning). Set to 0 for production view.
set "HYBRIDRAG_DEV_UI=1"
REM Startup detach mode:
REM   0 = run in current process (stable focus, easier debugging)
REM   1 = relaunch detached background GUI process
if "%HYBRIDRAG_GUI_DETACH%"=="" set "HYBRIDRAG_GUI_DETACH=0"

REM ---- LAUNCH GUI ----
echo [INFO] Launching HybridRAG GUI...
if /I "%HYBRIDRAG_GUI_DETACH%"=="1" (
  "%PY%" src\gui\launch_gui.py --detach
) else (
  "%PY%" src\gui\launch_gui.py
)
if %errorlevel% NEQ 0 (
  echo.
  echo  [FAIL] GUI exited with code %errorlevel%
  echo  Make sure Ollama is running: ollama serve
  echo.
  pause
)
