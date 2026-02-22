# ============================================================================
# HybridRAG v3 -- GUI Launcher (tools/launch_gui.ps1)
# ============================================================================
# Usage: .\tools\launch_gui.ps1
# Launches the tkinter GUI prototype.
# ============================================================================

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:HYBRIDRAG_PROJECT_ROOT = $ProjectRoot

Write-Host '[OK] Launching HybridRAG GUI...' -ForegroundColor Green
python "$ProjectRoot\src\gui\launch_gui.py"
