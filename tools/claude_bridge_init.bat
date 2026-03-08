@echo off
setlocal
call "%~dp0claude_bridge.bat" init %*
exit /b %ERRORLEVEL%
