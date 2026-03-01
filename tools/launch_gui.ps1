# ============================================================================
# HybridRAG v3 -- GUI Launcher (tools/launch_gui.ps1)
# ============================================================================
# Usage: .\tools\launch_gui.ps1
# Launches the tkinter GUI prototype.
# ============================================================================

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:HYBRIDRAG_PROJECT_ROOT = $ProjectRoot
$env:HYBRIDRAG_DEV_UI = "1"  # Set to "0" for production-style UI

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
    Write-Host "[OK] Launching HybridRAG GUI via venv: $VenvPython" -ForegroundColor Green
    & $VenvPython "$ProjectRoot\src\gui\launch_gui.py" --detach
} else {
    Write-Host "[WARN] .venv python not found; falling back to system python" -ForegroundColor Yellow
    python "$ProjectRoot\src\gui\launch_gui.py" --detach
}
