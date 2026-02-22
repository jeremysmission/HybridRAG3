@echo off
title HybridRAG v3

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo.
    echo  [WARN] Virtual environment not found.
    echo.
    echo  This is normal on first run. You need to create a .venv first.
    echo  Open PowerShell and run these commands:
    echo.
    echo    cd "%~dp0"
    echo    py -3.11 -m venv .venv
    echo    .\.venv\Scripts\Activate.ps1
    echo    pip install -r requirements.txt
    echo    . .\start_hybridrag.ps1
    echo    rag-diag
    echo.
    echo  For the full walkthrough, see:
    echo    START_HERE.txt
    echo    docs\INSTALL_AND_SETUP.md
    echo.
    pause
    exit /b 1
)

powershell -NoExit -Command "Set-ExecutionPolicy -Scope Process Bypass -Force; . '%~dp0start_hybridrag.ps1'"
