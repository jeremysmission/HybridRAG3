@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Automates the usb install offline operational workflow for developers or operators.
@REM How to follow: Read each command line in order from top to bottom.
@REM Inputs: Command arguments, environment variables, and local files.
@REM Outputs: Terminal messages and any files changed by called tools.
@REM Safety notes: Confirm paths before running on important data.
@REM ============================
@echo off
setlocal
title HybridRAG3 Offline Installer
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo   HybridRAG3 Offline Installer
echo ============================================================
echo.
echo This will install HybridRAG3 from local bundle files only.
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\usb_install_offline.ps1"
set "EXIT_CODE=%errorlevel%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [FAIL] Installer exited with code %EXIT_CODE%.
) else (
  echo [OK] Installer completed.
)
echo.
pause
endlocal
