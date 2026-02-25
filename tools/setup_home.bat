@echo off
REM HybridRAG3 Home Setup -- Bypasses Group Policy execution restrictions
REM Run this file by double-clicking or from cmd: tools\setup_home.bat
powershell -ExecutionPolicy Bypass -File "%~dp0setup_home.ps1"
pause
