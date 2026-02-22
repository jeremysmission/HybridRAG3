# ============================================================================
# HybridRAG -- Detect Bad Characters (tools/detect_bad_chars.ps1)
# ============================================================================
#
# WHAT THIS DOES:
#   Placeholder for a script that scans Python and PowerShell files for
#   non-ASCII characters that can cause encoding errors on Windows.
#
# WHY THIS MATTERS:
#   Windows PowerShell can choke on em-dashes, curly quotes, and other
#   Unicode characters that look normal but aren't standard ASCII.
#   Python scripts with non-ASCII can fail on machines with different
#   locale settings. This scanner would catch them before they cause
#   runtime errors.
#
# STANDING RULE (from CLAUDE.md):
#   "No non-ASCII characters in scripts"
#
# STATUS: Not yet implemented. For now, use:
#   Select-String -Path *.py -Pattern '[^\x00-\x7F]'
# ============================================================================
Write-Host "  [WARN] detect_bad_chars.ps1 is not yet implemented." -ForegroundColor Yellow
Write-Host "  Manual check: Select-String -Path *.py -Pattern '[^\x00-\x7F]'" -ForegroundColor White
