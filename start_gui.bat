@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Starts the HybridRAG desktop GUI from Explorer or a terminal.
@REM How to follow: Read each command block in order from top to bottom.
@REM Inputs: This repo folder, the local .venv, optional launcher flags, and env vars.
@REM Outputs: A running GUI window or a plain-English startup error message.
@REM Safety notes: If startup fails, rerun from a terminal so the error text stays visible.
@REM ============================
@echo off
title HybridRAG v3 GUI
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM ================================================================
REM  HybridRAG v3 -- One-Click GUI Launcher (start_gui.bat)
REM ================================================================
REM  WHAT THIS DOES:
REM    1. Resolves the repo root from this batch file location.
REM    2. Verifies the .venv and launch_gui.py entrypoint exist.
REM    3. Activates the .venv environment and sets project-root vars.
REM    4. Launches src\gui\launch_gui.py in terminal or detached mode.
REM
REM  FLAGS:
REM    --detach   Launch the GUI without keeping this console attached.
REM    --dry-run  Print resolved paths and exit without starting launch_gui.py.
REM ================================================================

set "PROJECT_ROOT=%CD%"
set "VENV_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "VENV_PYTHONW=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
set "VENV_ACTIVATE=%PROJECT_ROOT%\.venv\Scripts\activate.bat"
set "GUI_SCRIPT=%PROJECT_ROOT%\src\gui\launch_gui.py"
set "GUI_MODULE=src.gui.launch_gui"
set "GUI_MODE=terminal"
set "DRY_RUN=0"
set "PASSTHROUGH_ARGS="

:parse_args
if "%~1"=="" goto after_parse_args
if /I "%~1"=="--detach" (
  set "GUI_MODE=detached"
  shift
  goto parse_args
)
if /I "%~1"=="--terminal" (
  set "GUI_MODE=terminal"
  shift
  goto parse_args
)
if /I "%~1"=="--dry-run" (
  set "DRY_RUN=1"
  shift
  goto parse_args
)
set "PASSTHROUGH_ARGS=!PASSTHROUGH_ARGS! "%~1""
shift
goto parse_args

:after_parse_args
if /I "%HYBRIDRAG_GUI_DRY_RUN%"=="1" set "DRY_RUN=1"
if /I "%HYBRIDRAG_GUI_DETACH%"=="1" if /I "%GUI_MODE%"=="terminal" set "GUI_MODE=detached"

if not exist "%VENV_PYTHON%" goto missing_venv
if not exist "%GUI_SCRIPT%" goto missing_gui_script

set "PYTHONPATH=%PROJECT_ROOT%"
set "HYBRIDRAG_PROJECT_ROOT=%PROJECT_ROOT%"
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"
set "HYBRIDRAG_NETWORK_KILL_SWITCH=0"
set "HYBRIDRAG_OFFLINE=0"
set "HYBRIDRAG_DEV_UI=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist "%VENV_ACTIVATE%" call "%VENV_ACTIVATE%" >nul 2>nul

set "LAUNCH_EXE=%VENV_PYTHON%"
if /I "%GUI_MODE%"=="detached" if exist "%VENV_PYTHONW%" set "LAUNCH_EXE=%VENV_PYTHONW%"

if "%DRY_RUN%"=="1" goto dry_run

if /I "%GUI_MODE%"=="detached" goto launch_detached

echo [INFO] Launching HybridRAG GUI from "%PROJECT_ROOT%"
"%LAUNCH_EXE%" -m %GUI_MODULE% !PASSTHROUGH_ARGS!
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto launch_failed
goto end

:launch_detached
echo [INFO] Launching HybridRAG GUI in detached mode from "%PROJECT_ROOT%"
start "" "%LAUNCH_EXE%" -m %GUI_MODULE% !PASSTHROUGH_ARGS!
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto launch_failed
goto end

:dry_run
echo GUI launcher dry run
echo Project root: %PROJECT_ROOT%
echo Working directory: %CD%
echo Python exe: %VENV_PYTHON%
echo Pythonw exe: %VENV_PYTHONW%
echo Activate script: %VENV_ACTIVATE%
echo GUI script: %GUI_SCRIPT%
echo GUI module: %GUI_MODULE%
echo Launch exe: %LAUNCH_EXE%
echo Launch mode: %GUI_MODE%
echo Args: !PASSTHROUGH_ARGS!
exit /b 0

:missing_venv
echo.
echo [FAIL] HybridRAG cannot start because the local virtual environment is missing.
echo Expected Python here:
echo   "%VENV_PYTHON%"
echo.
echo Run INSTALL.bat first, or run these commands from this repo:
echo   cd "%PROJECT_ROOT%"
echo   py -3.12 -m venv .venv
echo   .venv\Scripts\pip install -r requirements_approved.txt
echo.
echo Then run start_gui.bat again.
call :maybe_pause
exit /b 2

:missing_gui_script
echo.
echo [FAIL] HybridRAG cannot find launch_gui.py.
echo Expected file:
echo   "%GUI_SCRIPT%"
echo.
echo The repo may be incomplete or unpacked into the wrong folder.
echo Re-extract the repo or restore src\gui\launch_gui.py, then try again.
call :maybe_pause
exit /b 3

:launch_failed
echo.
echo [FAIL] The GUI exited before startup completed. Exit code: %EXIT_CODE%
echo Project root: "%PROJECT_ROOT%"
echo Python: "%LAUNCH_EXE%"
echo GUI entry: "%GUI_SCRIPT%"
echo.
echo If you double-clicked this file, rerun start_gui.bat from a terminal so the full error stays visible.
echo Common checks:
echo   - Confirm Ollama is running if you expect offline mode.
echo   - Confirm shared or API credentials if you expect online mode.
echo   - Run python -m pytest tests/test_launch_gui_startup.py -q for a focused startup regression check.
call :maybe_pause
exit /b %EXIT_CODE%

:maybe_pause
if /I "%HYBRIDRAG_GUI_NO_PAUSE%"=="1" exit /b 0
pause
exit /b 0

:end
endlocal
