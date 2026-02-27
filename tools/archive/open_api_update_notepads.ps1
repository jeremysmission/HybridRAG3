# ============================================================================
# HybridRAG -- API Code Update Helper (tools/open_api_update_notepads.ps1)
# ============================================================================
#
# WHAT THIS DOES:
#   Opens two blank Notepad windows so you can paste in updated code from
#   a Claude session. This is a one-time helper for transferring code
#   changes to the work laptop when you can't use git.
#
# HOW TO USE (on work laptop):
#   1. Run this script: . .\tools\open_api_update_notepads.ps1
#   2. Notepad 1: paste the updated llm_router.py code, save to
#      D:\HybridRAG3\src\core\llm_router.py
#   3. Notepad 2: paste API setup notes, save to your personal
#      notes folder (NOT in the git repo)
#   4. Reload: . .\start_hybridrag.ps1
#   5. Test: rag-test-api
# ============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Opening files for API update" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# File 1: Updated llm_router.py (FULL REPLACEMENT)
# Copy ALL contents into: D:\HybridRAG3\src\core\llm_router.py
Write-Host "Opening Notepad 1: llm_router.py (FULL REPLACEMENT)" -ForegroundColor Yellow
Write-Host "  -> Select ALL, delete, paste new content" -ForegroundColor DarkGray
Write-Host "  -> Save to: D:\HybridRAG3\src\core\llm_router.py" -ForegroundColor DarkGray
Start-Process notepad

Start-Sleep -Seconds 1

# File 2: Secure API Setup Notes (KEEP LOCAL ONLY)
# Save to your secure notes location -- DO NOT commit to GitHub
Write-Host "Opening Notepad 2: API_SETUP_NOTES_SECURE.md" -ForegroundColor Yellow
Write-Host "  -> Save to your secure notes folder" -ForegroundColor DarkGray
Write-Host "  -> DO NOT commit this file to GitHub" -ForegroundColor Red
Start-Process notepad

Write-Host ""
Write-Host "INSTRUCTIONS:" -ForegroundColor Green
Write-Host "  1. Notepad 1: Paste the updated llm_router.py code" -ForegroundColor White
Write-Host "  2. Save as: D:\HybridRAG3\src\core\llm_router.py" -ForegroundColor White
Write-Host "  3. Notepad 2: Paste the API setup notes" -ForegroundColor White
Write-Host "  4. Save to your secure notes (NOT in the git repo)" -ForegroundColor White
Write-Host "  5. Reload: . .\start_hybridrag.ps1" -ForegroundColor White
Write-Host "  6. Test:   rag-test-api" -ForegroundColor White
Write-Host ""

