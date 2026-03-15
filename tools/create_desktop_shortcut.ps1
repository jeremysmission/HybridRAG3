<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Automates the create desktop shortcut operational workflow for developers or operators.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
# ============================================================================
# create_desktop_shortcut.ps1 -- Create Desktop shortcuts for HybridRAG v3
# ============================================================================
# Creates two .lnk shortcuts on the current user's Desktop:
#   - "HybridRAG CLI.lnk"  -> start_rag.bat
#   - "HybridRAG GUI.lnk"  -> start_gui.bat
#
# Safe to re-run (overwrites existing shortcuts).
# Uses WScript.Shell COM object (built into every Windows install).
# Icon: powershell.exe,0 (blue PS icon, ships with Windows).
#
# Usage:
#   powershell -File tools\create_desktop_shortcut.ps1
# ============================================================================

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$IconPath    = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$WshShell = New-Object -ComObject WScript.Shell

# --- CLI shortcut ---
$CliLink = $WshShell.CreateShortcut("$DesktopPath\HybridRAG CLI.lnk")
$CliLink.TargetPath       = "$ProjectRoot\start_rag.bat"
$CliLink.WorkingDirectory  = $ProjectRoot
$CliLink.Description       = "HybridRAG v3 -- Command Line Interface"
$CliLink.IconLocation      = "$IconPath,0"
$CliLink.Save()
Write-Host "[OK] Created: $DesktopPath\HybridRAG CLI.lnk"

# --- GUI shortcut ---
$GuiLink = $WshShell.CreateShortcut("$DesktopPath\HybridRAG GUI.lnk")
$GuiLink.TargetPath       = "$ProjectRoot\start_gui.bat"
$GuiLink.WorkingDirectory  = $ProjectRoot
$GuiLink.Description       = "HybridRAG v3 -- Graphical Interface"
$GuiLink.IconLocation      = "$IconPath,0"
$GuiLink.Save()
Write-Host "[OK] Created: $DesktopPath\HybridRAG GUI.lnk"

Write-Host "[OK] Done -- two shortcuts on Desktop"
