@echo off
setlocal enabledelayedexpansion
title HybridRAG3 -- USB Offline Installer
chcp 65001 >nul 2>&1
echo.
echo  ============================================================
echo.
echo    HybridRAG3 -- USB Offline Installer
echo.
echo    No internet connection required.
echo    Everything you need is on this USB drive.
echo.
echo    WHAT THIS DOES:
echo      - Copies HybridRAG3 to your computer
echo      - Installs all packages from USB (no downloads)
echo      - Configures your file paths
echo      - Installs AI models from USB
echo.
echo  ============================================================
echo.
echo  Press any key to begin installation...
echo  (You can close this window at any time to cancel)
echo.
pause >nul

powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0usb_install.ps1"
set "EXIT_CODE=!errorlevel!"

if not "!EXIT_CODE!"=="0" goto :show_error
goto :done

:show_error
echo.
echo  ============================================================
echo  Installation encountered an issue. See messages above.
echo.
echo  COMMON FIXES:
echo    1. Make sure Python is installed on this computer
echo       (check the python folder on this USB for an installer)
echo    2. Try running as Administrator (right-click, Run as admin)
echo    3. If on a work laptop, ask IT for help
echo  ============================================================
echo.

:done
echo.
echo  Press any key to close...
pause >nul
endlocal
