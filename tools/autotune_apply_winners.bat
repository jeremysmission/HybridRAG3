@echo off
setlocal
call "%~dp0run_mode_autotune.bat" --workflow full --grid starter --mode offline --screen-limit 50 --apply-winner %*
exit /b %ERRORLEVEL%
