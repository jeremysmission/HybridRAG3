# ============================================================================
# HybridRAG3 -- Build Offline Desktop Deploy Bundle
# FILE: tools/build_usb_deploy_bundle.ps1
# ============================================================================
# WHAT:
#   Creates a self-contained offline deploy folder for USB/DVD transfer.
#   Bundle includes:
#     - HybridRAG3 source (portable subset)
#     - Wheelhouse for offline pip install
#     - Optional local caches (.hf_cache, .model_cache, .ollama models)
#     - Optional Python and Ollama installers
#     - One-click offline installer scripts
#
# USAGE:
#   powershell -ExecutionPolicy Bypass -File tools/build_usb_deploy_bundle.ps1
#   powershell -ExecutionPolicy Bypass -File tools/build_usb_deploy_bundle.ps1 `
#     -OutputDir "D:\USB_DEPLOY_BUNDLE" -DownloadWheels -IncludeOllamaModels
#
# NOTES:
#   - This script is idempotent: rerun to refresh bundle.
#   - Download steps require internet; copy-only steps do not.
# ============================================================================

[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [switch]$DownloadWheels,
    [switch]$IncludeOllamaModels,
    [switch]$IncludeVenvSnapshot
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Ok([string]$m)   { Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Fail([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red }

function New-CleanDir([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -Recurse -Force $Path
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Copy-Tree([string]$Source, [string]$Dest, [string[]]$ExcludeDirs, [string[]]$ExcludeFiles) {
    if (-not (Test-Path $Source)) { return }
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    $args = @($Source, $Dest, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS")
    if ($ExcludeDirs -and $ExcludeDirs.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles -and $ExcludeFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFiles
    }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed from '$Source' to '$Dest' (exit $LASTEXITCODE)"
    }
    $global:LASTEXITCODE = 0
}

function Find-Python {
    if (Test-Path ".\.venv\Scripts\python.exe") { return (Resolve-Path ".\.venv\Scripts\python.exe").Path }
    try {
        $cmd = Get-Command py -ErrorAction Stop
        if ($cmd) { return "py -3.12" }
    } catch {}
    try {
        $cmd2 = Get-Command python -ErrorAction Stop
        if ($cmd2) { return "python" }
    } catch {}
    return ""
}

function Save-Manifest([string]$Root) {
    $manifest = Join-Path $Root "MANIFEST.txt"
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("HybridRAG3 Offline Deploy Bundle")
    $lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $lines.Add("")
    Get-ChildItem -Path $Root -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\')
        $size = $_.Length
        $lines.Add("{0}`t{1}" -f $size, $rel)
    }
    Set-Content -Path $manifest -Value $lines -Encoding UTF8
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $projectRoot "output\USB_DEPLOY_BUNDLE"
}
$bundleRoot = (Resolve-Path (Split-Path -Parent $OutputDir) -ErrorAction SilentlyContinue)
if (-not $bundleRoot) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $OutputDir) -Force | Out-Null
}
$output = [System.IO.Path]::GetFullPath($OutputDir)

Write-Info "Project root: $projectRoot"
Write-Info "Bundle output: $output"

New-CleanDir $output

# Folder layout
$appDir = Join-Path $output "HybridRAG3"
$wheelsDir = Join-Path $output "wheels"
$cacheDir = Join-Path $output "cache"
$installersDir = Join-Path $output "installers"
$scriptsDir = Join-Path $output "scripts"
New-Item -ItemType Directory -Path $appDir,$wheelsDir,$cacheDir,$installersDir,$scriptsDir -Force | Out-Null

Write-Info "Copying application source..."
$excludeDirs = @(
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".hf_cache", ".model_cache", ".torch_cache", "output", "eval_out",
    "scored_out", "logs", "USB Installer Research"
)
$excludeFiles = @("*.pyc", "*.pyo")
Copy-Tree -Source $projectRoot -Dest $appDir -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles
Write-Ok "Application source copied"

Write-Info "Copying installer scripts into bundle..."
Copy-Item (Join-Path $projectRoot "tools\usb_install_offline.ps1") (Join-Path $scriptsDir "usb_install_offline.ps1") -Force
Copy-Item (Join-Path $projectRoot "tools\usb_install_offline.bat") (Join-Path $output "INSTALL.bat") -Force
Write-Ok "Offline installer scripts copied"

Write-Info "Preparing wheelhouse..."
$copiedExisting = $false
$localWheelCandidates = @(
    (Join-Path $projectRoot "tools\work_validation\wheels"),
    (Join-Path $projectRoot "wheels")
)
foreach ($cand in $localWheelCandidates) {
    if (Test-Path $cand) {
        Copy-Tree -Source $cand -Dest $wheelsDir -ExcludeDirs @() -ExcludeFiles @()
        $copiedExisting = $true
        Write-Ok "Copied existing wheels from: $cand"
        break
    }
}

if ($DownloadWheels) {
    $py = Find-Python
    if (-not $py) {
        Write-Warn "Python launcher not found. Skipping wheel download."
    } else {
        Write-Info "Downloading wheels for offline install..."
        $reqFiles = @("requirements.txt", "requirements_approved.txt")
        foreach ($rf in $reqFiles) {
            $reqPath = Join-Path $projectRoot $rf
            if (-not (Test-Path $reqPath)) { continue }
            $cmd = "$py -m pip download -r `"$reqPath`" -d `"$wheelsDir`" --only-binary=:all:"
            Write-Info $cmd
            Invoke-Expression $cmd
        }
        Write-Ok "Wheel download completed"
    }
} elseif (-not $copiedExisting) {
    Write-Warn "No local wheels found and -DownloadWheels not set."
    Write-Warn "Bundle will still build, but offline install may fail without wheel files."
}

Write-Info "Copying local caches..."
$cacheMap = @(
    @{ Src = (Join-Path $projectRoot ".hf_cache");    Dst = (Join-Path $cacheDir "hf_cache") },
    @{ Src = (Join-Path $projectRoot ".model_cache"); Dst = (Join-Path $cacheDir "model_cache") },
    @{ Src = (Join-Path $projectRoot ".torch_cache"); Dst = (Join-Path $cacheDir "torch_cache") }
)
foreach ($m in $cacheMap) {
    if (Test-Path $m.Src) {
        Copy-Tree -Source $m.Src -Dest $m.Dst -ExcludeDirs @() -ExcludeFiles @()
        Write-Ok "Copied cache: $($m.Src)"
    }
}

if ($IncludeOllamaModels) {
    $ollamaModels = Join-Path $env:USERPROFILE ".ollama\models"
    if (Test-Path $ollamaModels) {
        Copy-Tree -Source $ollamaModels -Dest (Join-Path $cacheDir "ollama_models") -ExcludeDirs @() -ExcludeFiles @()
        Write-Ok "Copied Ollama model store"
    } else {
        Write-Warn "Ollama model store not found at $ollamaModels"
    }
}

if ($IncludeVenvSnapshot -and (Test-Path (Join-Path $projectRoot ".venv"))) {
    Write-Info "Copying .venv snapshot (large)..."
    Copy-Tree -Source (Join-Path $projectRoot ".venv") -Dest (Join-Path $output "venv_snapshot") -ExcludeDirs @("__pycache__") -ExcludeFiles @("*.pyc")
    Write-Ok "Venv snapshot copied"
}

Write-Info "Copying optional installers if present..."
$installerCandidates = @(
    @{ Name = "python-installer"; Src = (Join-Path $projectRoot "USB Installer Research\python-3.11.9-amd64.exe") },
    @{ Name = "ollama-installer"; Src = (Join-Path $projectRoot "USB Installer Research\OllamaSetup.exe") }
)
foreach ($ic in $installerCandidates) {
    if (Test-Path $ic.Src) {
        Copy-Item $ic.Src (Join-Path $installersDir ([System.IO.Path]::GetFileName($ic.Src))) -Force
        Write-Ok "Copied installer: $($ic.Name)"
    }
}

Save-Manifest -Root $output

$bytes = (Get-ChildItem $output -Recurse -File | Measure-Object -Property Length -Sum).Sum
$gb = [math]::Round($bytes / 1GB, 2)
Write-Host ""
Write-Ok "Offline deploy bundle is ready"
Write-Host "  Path: $output"
Write-Host "  Size: $gb GB"
Write-Host ""
Write-Host "Next:"
Write-Host "  1) Copy this folder to USB stick or DVD media"
Write-Host "  2) On target desktop, run INSTALL.bat from bundle root"
Write-Host ""
