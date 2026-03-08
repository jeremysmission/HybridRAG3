@echo off
setlocal
call "%~dp0claude_bridge.bat" watch %*
exit /b %ERRORLEVEL%
