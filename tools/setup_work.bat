@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Automates the setup work operational workflow for developers or operators.
@REM How to follow: Read each command line in order from top to bottom.
@REM Inputs: Command arguments, environment variables, and local files.
@REM Outputs: Terminal messages and any files changed by called tools.
@REM Safety notes: Confirm paths before running on important data.
@REM ============================
@echo off
REM HybridRAG3 Work/Educational Setup -- Bypasses Group Policy execution restrictions
REM Run this file by double-clicking or from cmd: tools\setup_work.bat
REM Uses requirements_approved.txt (enterprise-approved packages only)
powershell -ExecutionPolicy Bypass -File "%~dp0setup_work.ps1"
pause
