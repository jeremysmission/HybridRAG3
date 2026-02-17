# ============================================================================
# Open Notepad windows for API update files
# Run this from your HybridRAG directory on the WORK LAPTOP
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

