@echo off
REM HybridRAG3 Work/Educational Setup -- Bypasses Group Policy execution restrictions
REM Run this file by double-clicking or from cmd: tools\setup_work.bat
REM Uses requirements_approved.txt (enterprise-approved packages only)
powershell -ExecutionPolicy Bypass -File "%~dp0setup_work.ps1"
pause
