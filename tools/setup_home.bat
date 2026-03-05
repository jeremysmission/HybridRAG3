@REM === NON-PROGRAMMER GUIDE ===
@REM Purpose: Automates the setup home operational workflow for developers or operators.
@REM How to follow: Read each command line in order from top to bottom.
@REM Inputs: Command arguments, environment variables, and local files.
@REM Outputs: Terminal messages and any files changed by called tools.
@REM Safety notes: Confirm paths before running on important data.
@REM ============================
@echo off
REM HybridRAG3 Home Setup -- Bypasses Group Policy execution restrictions
REM Run this file by double-clicking or from cmd: tools\setup_home.bat
powershell -ExecutionPolicy Bypass -File "%~dp0setup_home.ps1"
pause
