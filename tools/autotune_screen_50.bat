@echo off
setlocal
call "%~dp0run_mode_autotune.bat" --workflow screen --grid starter --mode offline --screen-limit 50 %*
exit /b %ERRORLEVEL%
