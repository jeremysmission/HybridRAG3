<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Automates the launch gui operational workflow for developers or operators.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
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
if (-not $env:HYBRIDRAG_GUI_DETACH) { $env:HYBRIDRAG_GUI_DETACH = "0" }
$LaunchArgs = @("$ProjectRoot\src\gui\launch_gui.py")
if ($env:HYBRIDRAG_GUI_DETACH -eq "1") {
    $LaunchArgs += "--detach"
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
    Write-Host "[OK] Launching HybridRAG GUI via venv: $VenvPython" -ForegroundColor Green
    & $VenvPython @LaunchArgs
} else {
    Write-Host "[WARN] .venv python not found; falling back to system python" -ForegroundColor Yellow
    python @LaunchArgs
}
