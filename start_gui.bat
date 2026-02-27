@echo off
title HybridRAG v3 GUI
setlocal
cd /d "%~dp0"
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo  [FAIL] Missing venv python: "%PY%"
  echo.
  echo  You need to create a .venv first:
  echo    cd "%~dp0"
  echo    py -3.11 -m venv .venv
  echo    .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 2
)
set "PYTHONPATH=%CD%"
set "HYBRIDRAG_PROJECT_ROOT=%CD%"
echo [INFO] Using "%PY%"
echo [INFO] Launching HybridRAG GUI...
"%PY%" src\gui\launch_gui.py
set "RC=%errorlevel%"
if %RC% NEQ 0 (
  echo.
  echo  [FAIL] GUI exited with code %RC%
  echo.
  echo  Common fixes:
  echo    1. Make sure Ollama is running (ollama serve)
  echo    2. Re-install packages: .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
)
exit /b %RC%
