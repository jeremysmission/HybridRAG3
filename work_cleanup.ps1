# ============================================================================
# HybridRAG v3 -- Work Laptop Cleanup
# Moves root clutter into tools/, diagnostics/, archive/
# Safe to run multiple times -- skips files that don't exist
# ============================================================================

$proj = $PSScriptRoot
if (-not $proj) { $proj = $pwd.Path }

Write-Host "=== HybridRAG Work Laptop Cleanup ===" -ForegroundColor Cyan
Write-Host "Project: $proj"

# Ensure target folders exist
foreach ($dir in @("tools", "diagnostics", "archive")) {
    $path = Join-Path $proj $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "  Created: $dir\"
    }
}

# Move scripts to tools/
$toTools = @(
    "open_api_update_notepads.ps1",
    "open_diagnostic_v2.ps1",
    "api_mode_commands.ps1"
)
foreach ($f in $toTools) {
    $src = Join-Path $proj $f
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $proj "tools\$f") -Force
        Remove-Item $src -Force
        Write-Host "  [OK] $f -> tools\" -ForegroundColor Green
    }
}

# Move diagnostic outputs to diagnostics/
$toDiag = @(
    "hybridrag_diagnostic_v2.py",
    "api_diag_report.txt",
    "api_diag_results.json"
)
foreach ($f in $toDiag) {
    $src = Join-Path $proj $f
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $proj "diagnostics\$f") -Force
        Remove-Item $src -Force
        Write-Host "  [OK] $f -> diagnostics\" -ForegroundColor Green
    }
}

# Move superseded files to archive/
$toArchive = @(
    "api_mode_simulation.py",
    "API_MODE_REVIEW.md",
    "HybridRAG_Combined_Forces_Review.docx",
    "Code Review.zip"
)
foreach ($f in $toArchive) {
    $src = Join-Path $proj $f
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $proj "archive\$f") -Force
        Remove-Item $src -Force
        Write-Host "  [OK] $f -> archive\" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Remaining root files:" -ForegroundColor Cyan
Get-ChildItem $proj -File | Select-Object Name
Write-Host ""
Write-Host "=== Cleanup complete ===" -ForegroundColor Green
