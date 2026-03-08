@echo off
setlocal
call "%~dp0claude_bridge.bat" send %*
exit /b %ERRORLEVEL%
