@echo off
title HybridRAG v3 GUI
setlocal
cd /d "%~dp0"

REM ================================================================
REM  HybridRAG v3 -- One-Click GUI Launcher (start_gui.bat)
REM ================================================================
REM  Self-contained: sets all env vars, checks Ollama, launches GUI.
REM  No need to run start_rag.bat first.
REM
REM  WHAT THIS DOES:
REM    1. Checks .venv exists
REM    2. Sets PYTHONPATH + project root
REM    3. Sets network lockdown (NO_PROXY, HF offline, kill switch)
REM    4. Checks Ollama is running (auto-starts if found)
REM    5. Launches the GUI
REM ================================================================

REM ---- 1) CHECK VENV ----
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo  [FAIL] Missing venv python: "%PY%"
  echo.
  echo  You need to create a .venv first:
  echo    cd "%~dp0"
  echo    py -3.12 -m venv .venv
  echo    .venv\Scripts\pip install -r requirements_approved.txt
  echo.
  pause
  exit /b 2
)

REM ---- 2) PYTHON ENVIRONMENT ----
set "PYTHONPATH=%CD%"
set "HYBRIDRAG_PROJECT_ROOT=%CD%"

REM ---- 3) NETWORK LOCKDOWN ----
REM NO_PROXY prevents corporate proxy from intercepting Ollama on loopback.
REM This is CRITICAL on work machines -- without it, 127.0.0.1:11434 gets
REM redirected (HTTP 301) by the proxy, and the embedder/LLM fail.
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "HF_HUB_DISABLE_IMPLICIT_TOKEN=1"
set "HYBRIDRAG_NETWORK_KILL_SWITCH=true"

REM ---- 4) CHECK OLLAMA ----
REM Quick check: is Ollama responding on 127.0.0.1:11434?
REM If not running, try to start it in the background.
"%PY%" -c "import httpx; r = httpx.get('http://127.0.0.1:11434', timeout=3); exit(0 if r.status_code == 200 else 1)" >nul 2>&1
if %errorlevel% NEQ 0 (
  echo [INFO] Ollama not responding. Attempting to start...
  where ollama >nul 2>&1
  if %errorlevel% EQU 0 (
    start "" /B ollama serve >nul 2>&1
    echo [INFO] Waiting 5s for Ollama to start...
    timeout /t 5 /nobreak >nul
    "%PY%" -c "import httpx; r = httpx.get('http://127.0.0.1:11434', timeout=3); exit(0 if r.status_code == 200 else 1)" >nul 2>&1
    if %errorlevel% EQU 0 (
      echo [OK]   Ollama is running.
    ) else (
      echo [WARN] Ollama still not responding. GUI will start but offline features may fail.
    )
  ) else (
    echo [WARN] Ollama not found on PATH. Install from https://ollama.com
    echo        GUI will start but offline features may fail.
  )
) else (
  echo [OK]   Ollama is running.
)

REM ---- 5) LAUNCH GUI ----
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
  echo    2. Re-install packages: .venv\Scripts\pip install -r requirements_approved.txt
  echo.
  pause
)
exit /b %RC%
