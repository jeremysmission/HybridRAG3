@echo off
where python >nul 2>&1 && python "%~dp0tools\run.py" %* && exit /b 0
echo [FAIL] Python not found in PATH. Activate your venv first: .venv\Scripts\activate
