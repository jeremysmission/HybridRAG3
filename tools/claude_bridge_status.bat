@echo off
setlocal
call "%~dp0claude_bridge.bat" status %*
exit /b %ERRORLEVEL%
