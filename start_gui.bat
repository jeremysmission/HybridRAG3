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
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HYBRIDRAG_NETWORK_KILL_SWITCH=true"

REM ---- LAUNCH GUI ----
echo [INFO] Launching HybridRAG GUI...
"%PY%" src\gui\launch_gui.py
if %errorlevel% NEQ 0 (
  echo.
  echo  [FAIL] GUI exited with code %errorlevel%
  echo  Make sure Ollama is running: ollama serve
  echo.
  pause
)
