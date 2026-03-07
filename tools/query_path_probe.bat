@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "HYBRIDRAG_PROJECT_ROOT=%REPO_ROOT%"

pushd "%REPO_ROOT%" >nul

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" tools\query_path_probe.py %*
    set "EXIT_CODE=!ERRORLEVEL!"
    popd >nul
    exit /b !EXIT_CODE!
)

where py >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    py -3 tools\query_path_probe.py %*
    set "EXIT_CODE=!ERRORLEVEL!"
    popd >nul
    exit /b !EXIT_CODE!
)

where python >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    python tools\query_path_probe.py %*
    set "EXIT_CODE=!ERRORLEVEL!"
    popd >nul
    exit /b !EXIT_CODE!
)

echo [FAIL] Python was not found.
echo         Checked:
echo           %REPO_ROOT%\.venv\Scripts\python.exe
echo           py -3
echo           python
popd >nul
exit /b 9009
