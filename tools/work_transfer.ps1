# ============================================================================
# HybridRAG -- Work Transfer Unpacker (tools/work_transfer.ps1)
# ============================================================================
#
# WHAT THIS DOES:
#   Extracts a session transfer ZIP file from your Downloads folder and
#   copies the updated code files into the correct project directories.
#   This is how code gets from the home PC to the work laptop.
#
# HOW THE TRANSFER WORKS:
#   1. At home: Claude session produces updated files, packaged as ZIP
#   2. ZIP is pushed to GitHub Educational repo under releases/
#   3. At work: you download the ZIP through your browser
#   4. Run this script: it unpacks and puts everything in the right place
#
# WHAT IT COPIES:
#   - src/       -> your project's src/ folder (all Python source code)
#   - tools/     -> your project's tools/ folder
#   - tests/     -> your project's tests/ folder
#   - config/    -> your project's config/ folder
#   - diagnostics/ -> your project's diagnostics/ folder
#
# HOW TO USE:
#   1. Download the ZIP to your Downloads folder
#   2. Open PowerShell in your project directory
#   3. Run: . .\tools\work_transfer.ps1
#
# SAFETY: This OVERWRITES existing files with the new versions.
#   Your old files are replaced, not backed up. If you have local changes
#   you want to keep, copy them somewhere else first.
# ============================================================================
$zip = "$env:USERPROFILE\Downloads\session2_transfer.zip"
$tmp = "$env:TEMP\transfer_tmp"
# Resolve project root -- works whether run directly, dot-sourced,
# or via Invoke-Expression (Group Policy workaround on work laptop).
if ($PSScriptRoot) {
    $proj = Split-Path -Parent $PSScriptRoot
} else {
    $proj = (Get-Location).Path
}
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Copy-Item "$tmp\src\*" -Destination "$proj\src\" -Recurse -Force
Copy-Item "$tmp\tools\*" -Destination "$proj\tools\" -Force
Copy-Item "$tmp\tests\*" -Destination "$proj\tests\" -Force
Copy-Item "$tmp\config\*" -Destination "$proj\config\" -Force
Copy-Item "$tmp\diagnostics\*" -Destination "$proj\diagnostics\" -Force
Copy-Item "$tmp\REDESIGN_README.txt" -Destination "$proj\REDESIGN_README.txt" -Force
Remove-Item $tmp -Recurse -Force
Write-Host "Transfer complete"

