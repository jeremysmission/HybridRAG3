@echo off
setlocal enabledelayedexpansion
title HybridRAG3 -- First-Time Setup
color 0B
chcp 65001 >nul 2>&1
echo.
echo  ============================================================
echo.
echo    Welcome to HybridRAG3 Setup
echo.
echo    This will install everything you need to run HybridRAG3.
echo    It takes about 5-10 minutes. You will be asked a few
echo    questions along the way (like where to store your files).
echo.
echo    WHAT THIS DOES:
echo      - Checks that Python is installed
echo      - Creates a virtual environment (.venv)
echo      - Installs all required packages
echo      - Configures your file paths
echo      - Checks that Ollama AI is ready
echo      - Runs a quick verification test
echo.
echo  ============================================================
echo.

REM ---- Detect which repo we are in (goto-based to avoid parenthesis issues) ----
REM NOTE: Nested if() blocks break when paths contain parentheses
REM       e.g. "Program Files (x86)". Using goto labels instead.

if not exist "%~dp0requirements_approved.txt" goto :not_work
if not exist "%~dp0start_hybridrag.ps1.template" goto :not_work
echo  Detected: Work / Educational repository
echo  Using: requirements_approved.txt (enterprise-approved only)
echo.
set "SETUP_SCRIPT=%~dp0tools\setup_work.ps1"
goto :check_script

:not_work
if not exist "%~dp0requirements.txt" goto :no_req
echo  Detected: Personal / Home repository
echo  Using: requirements.txt
echo.
set "SETUP_SCRIPT=%~dp0tools\setup_home.ps1"
goto :check_script

:no_req
echo  [FAIL] Could not find requirements.txt in this folder.
echo.
echo  Make sure you extracted the ZIP file completely and are
echo  running INSTALL.bat from inside the HybridRAG3 folder.
echo.
pause
exit /b 1

:check_script
if not exist "!SETUP_SCRIPT!" goto :no_script
goto :ready

:no_script
echo  [FAIL] Setup script not found: !SETUP_SCRIPT!
echo.
echo  The tools folder may be missing. Re-download the project
echo  and make sure the tools folder is included.
echo.
pause
exit /b 1

:ready
echo  Press any key to begin setup...
echo  (You can close this window at any time to cancel)
echo.
pause >nul

REM ---- Launch PowerShell with Group Policy bypass ----
powershell -ExecutionPolicy Bypass -NoProfile -File "!SETUP_SCRIPT!"
set "EXIT_CODE=!errorlevel!"

if not "!EXIT_CODE!"=="0" goto :show_error
goto :done

:show_error
echo.
echo  ============================================================
echo  Setup encountered an issue. See the messages above.
echo.
echo  COMMON FIXES:
echo    1. Make sure Python 3.10 or newer is installed
echo    2. If on a work laptop, ask IT for Python access
echo    3. Make sure you have internet access for downloads
echo    4. Try running as Administrator (right-click, Run as admin)
echo  ============================================================
echo.

:done
echo.
echo  Press any key to close this window...
pause >nul
endlocal
