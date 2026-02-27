@echo off
title Hybrid3 Enterprise Troubleshooter
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY=%CD%\.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo  [FAIL] Virtual environment not found: %PY%
    echo  Run setup first.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Hybrid3 Enterprise Troubleshooter
echo ========================================
echo.
echo  Python:
"%PY%" --version
echo.

"%PY%" tools\run_hybrid3_troubleshoot.py
set "RC=%errorlevel%"

echo.
echo Creating ZIP bundle...
if exist output\_last_troubleshoot_dir.txt (
    set /p DIAG_DIR=<output\_last_troubleshoot_dir.txt
    powershell -NoProfile -Command "Compress-Archive -Path '!DIAG_DIR!\*' -DestinationPath '!DIAG_DIR!.zip' -Force" 2>nul
    if exist "!DIAG_DIR!.zip" (
        echo.
        echo  ========================================
        echo   Bundle ready:
        echo   !DIAG_DIR!.zip
        echo.
        echo   Send this ZIP to AI for troubleshooting.
        echo  ========================================
    ) else (
        echo  [WARN] ZIP creation failed. Send the folder instead:
        echo  !DIAG_DIR!
    )
) else (
    echo  [WARN] Could not find troubleshoot directory.
)

echo.
pause
exit /b %RC%
