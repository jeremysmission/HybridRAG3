@echo off
setlocal
title HybridRAG3 Offline Installer
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo   HybridRAG3 Offline Installer
echo ============================================================
echo.
echo This will install HybridRAG3 from local bundle files only.
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\usb_install_offline.ps1"
set "EXIT_CODE=%errorlevel%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo [FAIL] Installer exited with code %EXIT_CODE%.
) else (
  echo [OK] Installer completed.
)
echo.
pause
endlocal
