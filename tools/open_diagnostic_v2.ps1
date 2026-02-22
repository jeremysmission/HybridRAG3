# ============================================================================
# HybridRAG -- Diagnostic Quick Launcher (tools/open_diagnostic_v2.ps1)
# ============================================================================
#
# WHAT THIS DOES:
#   Prints a cheat sheet of diagnostic commands to your terminal and
#   opens the diagnostic Python file in Notepad for review. This is a
#   quick-reference card for running the 28-test health check suite.
#
# THE DIAGNOSTIC LEVELS:
#   Level 1 (Power-On):    Python, venv, packages, disk, structure
#   Level 2 (Initiated):   Config, database, schema, credentials
#   Level 3 (Continuous):  Embedder, chunker, Ollama, API, security
#   Level 4 (Maintenance): Code bugs, URL check, git, PowerShell
#
# HOW TO USE:
#   . .\tools\open_diagnostic_v2.ps1
#
# NOTE: References hybridrag_diagnostic_v2.py in project root.
#   If that file has moved, update the path on line 30 below.
# ============================================================================

Write-Host ""
Write-Host "  HybridRAG Diagnostic v2.0 -- Quick Reference" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  COMMANDS:" -ForegroundColor Yellow
Write-Host "    python hybridrag_diagnostic_v2.py                  # Full (28 tests)" -ForegroundColor White
Write-Host "    python hybridrag_diagnostic_v2.py --quick           # Fast (Level 1+2, ~5 sec)" -ForegroundColor White
Write-Host "    python hybridrag_diagnostic_v2.py --verbose         # Show fix hints" -ForegroundColor White
Write-Host "    python hybridrag_diagnostic_v2.py --skip-embed      # Skip model load (faster)" -ForegroundColor White
Write-Host "    python hybridrag_diagnostic_v2.py --json report.json  # Save JSON" -ForegroundColor White
Write-Host "    python hybridrag_diagnostic_v2.py --level 3         # Up to Level 3" -ForegroundColor White
Write-Host ""
Write-Host "  LEVELS:" -ForegroundColor Yellow
Write-Host "    1  Power-On   -- Python, venv, packages, disk, structure (6 tests)" -ForegroundColor DarkGray
Write-Host "    2  Initiated  -- Config, database, schema, credentials (7 tests)" -ForegroundColor DarkGray
Write-Host "    3  Continuous -- Embedder, chunker, Ollama, API, security (11 tests)" -ForegroundColor DarkGray
Write-Host "    4  Maintenance -- Code bugs, URL check, git, PowerShell (4 tests)" -ForegroundColor DarkGray
Write-Host ""

# Open the diagnostic file in notepad for review
if (Test-Path "hybridrag_diagnostic_v2.py") {
    Write-Host "  Opening diagnostic in Notepad..." -ForegroundColor DarkGray
    notepad hybridrag_diagnostic_v2.py
} else {
    Write-Host "  WARNING: hybridrag_diagnostic_v2.py not found in current directory" -ForegroundColor Red
    Write-Host "  Make sure you're in the HybridRAG project root" -ForegroundColor Yellow
}

