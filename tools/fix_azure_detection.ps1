# ===========================================================================
# FIX AZURE DETECTION IN llm_router_fix.py
# ===========================================================================
#
# WHAT THIS DOES:
#   Your company's Azure URL uses "aoai" (Azure OpenAI abbreviated) instead
#   of the literal word "azure" in the domain. The llm_router_fix.py file
#   only checks for "azure" and ".openai.azure.com", so it thinks your
#   endpoint is regular OpenAI. This causes THREE cascading failures:
#
#   1. WRONG PROVIDER:  Detected as "OpenAI" instead of "Azure"
#   2. WRONG URL PATH:  Appends /v1/chat/completions (OpenAI format)
#                        instead of /openai/deployments/{name}/chat/completions
#   3. WRONG AUTH:      Uses "Authorization: Bearer" header
#                        instead of "api-key" header
#
#   This script patches the detection logic to recognize "aoai" as Azure.
#
# HOW TO RUN:
#   cd "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
#   .\.venv\Scripts\Activate
#   . .\tools\fix_azure_detection.ps1
#
# WHAT IT CHANGES:
#   In src\core\llm_router_fix.py, finds the provider detection function
#   and adds "aoai" to the list of Azure URL patterns.
#
# SAFETY:
#   - Creates a backup before making any changes
#   - Shows you exactly what changed
#   - Does NOT make any network calls
# ===========================================================================

$ErrorActionPreference = "Stop"

# --- Locate the file ---
$projectRoot = "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
$routerFile = Join-Path $projectRoot "src\core\llm_router_fix.py"

if (-not (Test-Path $routerFile)) {
    Write-Host "[ERROR] Cannot find: $routerFile" -ForegroundColor Red
    Write-Host "Make sure you ran write_llm_router_fix.ps1 first." -ForegroundColor Yellow
    return
}

# --- Create timestamped backup ---
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = Join-Path $projectRoot "src\core\llm_router_fix_backup_$timestamp.py"
Copy-Item $routerFile $backupFile
Write-Host "[OK] Backup saved: $backupFile" -ForegroundColor Green

# --- Read the file ---
$content = Get-Content $routerFile -Raw -Encoding UTF8

# --- PATCH 1: Fix provider detection ---
# The current code likely has something like:
#   if "azure" in url_lower or ".openai.azure.com" in url_lower
# We need to add "aoai" as another Azure indicator

# Strategy: Find the detect_provider function and add "aoai" check
# We'll do multiple possible patterns to be safe

$patched = $false

# Pattern A: Check for the exact string pattern in the detection logic
if ($content -match '"azure" in ') {
    # Add "aoai" to the Azure detection
    $content = $content -replace '("azure" in [^)]+)', '$1 or "aoai" in url_lower'
    
    # But avoid doubling if "aoai" is already there
    $content = $content -replace 'or "aoai" in url_lower or "aoai" in url_lower', 'or "aoai" in url_lower'
    
    $patched = $true
    Write-Host "[OK] Patched provider detection to recognize 'aoai' URLs" -ForegroundColor Green
}

# Pattern B: If the function uses a list of patterns
if ($content -match 'azure_patterns|azure_indicators|AZURE_MARKERS') {
    # Add aoai to the pattern list
    $content = $content -replace '(azure_patterns|azure_indicators|AZURE_MARKERS)\s*=\s*\[', '$0"aoai", '
    $patched = $true
    Write-Host "[OK] Added 'aoai' to Azure pattern list" -ForegroundColor Green
}

# Pattern C: If neither pattern found, do a broader replacement
if (-not $patched) {
    Write-Host "[INFO] Standard patterns not found. Applying broader fix..." -ForegroundColor Yellow
    
    # Find any line that checks for "azure" in the URL and add aoai
    $lines = $content -split "`n"
    $newLines = @()
    foreach ($line in $lines) {
        $newLines += $line
        # After any line that checks for "azure" in a URL, add aoai check
        if ($line -match 'if.*"azure".*in.*url' -and $line -notmatch 'aoai') {
            # The line already has the azure check, we need to modify it
            # Remove the line we just added and replace with modified version
            $newLines = $newLines[0..($newLines.Count - 2)]
            $modifiedLine = $line -replace '(if\s+)', '$1"aoai" in url_lower or '
            $newLines += $modifiedLine
            $patched = $true
            Write-Host "[OK] Injected 'aoai' check into detection line" -ForegroundColor Green
        }
    }
    $content = $newLines -join "`n"
}

if (-not $patched) {
    Write-Host "[WARNING] Could not find provider detection pattern to patch." -ForegroundColor Yellow
    Write-Host "The file structure may be different than expected." -ForegroundColor Yellow
    Write-Host "We will write a complete replacement instead." -ForegroundColor Yellow
}

# --- Write patched file ---
$content | Out-File -FilePath $routerFile -Encoding UTF8 -NoNewline
Write-Host "[OK] Patched file saved: $routerFile" -ForegroundColor Green

# --- Verify syntax ---
$syntaxCheck = python -c "import py_compile; py_compile.compile(r'$routerFile', doraise=True)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Python syntax check PASSED" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Syntax check FAILED. Restoring backup..." -ForegroundColor Red
    Copy-Item $backupFile $routerFile
    Write-Host "[OK] Backup restored. Original file unchanged." -ForegroundColor Green
    Write-Host "Error was: $syntaxCheck" -ForegroundColor Yellow
    return
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PATCH COMPLETE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Now run:  . .\tools\azure_api_test.ps1" -ForegroundColor White
Write-Host ""
