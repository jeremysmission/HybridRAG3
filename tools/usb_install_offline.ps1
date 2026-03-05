<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Automates the usb install offline operational workflow for developers or operators.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
# ============================================================================
# HybridRAG3 -- Offline Bundle Installer (Target Desktop)
# FILE: tools/usb_install_offline.ps1
# ============================================================================
# Expected bundle layout (root):
#   INSTALL.bat
#   scripts\usb_install_offline.ps1
#   HybridRAG3\...
#   wheels\...
#   cache\...
#   installers\...
#
# Runs fully offline when wheelhouse and installers are present.
# ============================================================================

[CmdletBinding()]
param(
    [string]$BundleRoot = "",
    [switch]$SkipHashCheck
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Ok([string]$m)   { Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Fail([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red }

function Copy-Tree([string]$Source, [string]$Dest) {
    if (-not (Test-Path $Source)) { return }
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    & robocopy $Source $Dest /E /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed from '$Source' to '$Dest' (exit $LASTEXITCODE)"
    }
    $global:LASTEXITCODE = 0
}

function Resolve-Python() {
    try {
        foreach ($v in @("3.12", "3.11", "3.10")) {
            & py "-$v" --version *> $null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$v") }
        }
    } catch {}
    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) { return @("python") }
    } catch {}
    return @()
}

function Test-BundleIntegrity([string]$Root) {
    $manifestPath = Join-Path $Root "MANIFEST_SHA256.txt"
    if (-not (Test-Path $manifestPath)) {
        Write-Warn "MANIFEST_SHA256.txt not found. Skipping integrity verification."
        return
    }

    Write-Info "Verifying bundle integrity (SHA-256)..."
    $bad = 0
    $checked = 0
    foreach ($line in Get-Content -Path $manifestPath -Encoding UTF8) {
        $raw = $line.Trim()
        if (-not $raw) { continue }
        if ($raw.Length -lt 67) { continue }
        if ($raw[64] -ne ' ') { continue }

        $expected = $raw.Substring(0, 64).ToLowerInvariant()
        $rel = $raw.Substring(66).Trim()
        $target = Join-Path $Root $rel
        $checked += 1

        if (-not (Test-Path $target)) {
            Write-Fail "Missing file from manifest: $rel"
            $bad += 1
            continue
        }

        $actual = (Get-FileHash -Path $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            Write-Fail "Hash mismatch: $rel"
            $bad += 1
        }
    }

    if ($bad -gt 0) {
        throw "Integrity verification failed ($bad issue(s) across $checked file(s)). Re-copy/prestage bundle before installing."
    }
    Write-Ok "Integrity verified ($checked files)"
}

function Write-LocalConfig([string]$CfgPath, [string]$DataDir, [string]$SourceDir) {
    if (-not (Test-Path $CfgPath)) { return }
    $txt = Get-Content $CfgPath -Raw -Encoding UTF8
    $dbPath = (Join-Path $DataDir "hybridrag.sqlite3").Replace("\", "\\")
    $embPath = (Join-Path $DataDir "_embeddings").Replace("\", "\\")
    $src = $SourceDir.Replace("\", "\\")
    $txt = $txt -replace '(?m)^(\s*database:\s*).*$', ('$1"' + $dbPath + '"')
    $txt = $txt -replace '(?m)^(\s*embeddings_cache:\s*).*$', ('$1"' + $embPath + '"')
    $txt = $txt -replace '(?m)^(\s*source_folder:\s*).*$', ('$1"' + $src + '"')
    $txt = $txt -replace '(?m)^(\s*download_folder:\s*).*$', ('$1"' + $src + '"')
    [System.IO.File]::WriteAllText($CfgPath, $txt)
}

$scriptPath = $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptPath
$defaultBundleRoot = Split-Path -Parent $scriptsDir
if ([string]::IsNullOrWhiteSpace($BundleRoot)) {
    $bundleRoot = $defaultBundleRoot
} else {
    $bundleRoot = [System.IO.Path]::GetFullPath($BundleRoot)
}

Write-Info "Bundle root: $bundleRoot"

$appSrc = Join-Path $bundleRoot "HybridRAG3"
$wheels = Join-Path $bundleRoot "wheels"
$cacheRoot = Join-Path $bundleRoot "cache"
$installers = Join-Path $bundleRoot "installers"

if (-not (Test-Path $appSrc)) {
    Write-Fail "Bundle missing HybridRAG3 folder"
    exit 2
}

$requiredDirs = @("HybridRAG3", "scripts")
$missing = @()
foreach ($d in $requiredDirs) {
    $p = Join-Path $bundleRoot $d
    if (-not (Test-Path $p)) { $missing += $d }
}
if ($missing.Count -gt 0) {
    Write-Fail "Bundle root is incomplete. Missing: $($missing -join ', ')"
    Write-Host "Expected layout root contains: HybridRAG3, scripts, wheels (optional), cache (optional), installers (optional)"
    exit 2
}

if (-not $SkipHashCheck) {
    Test-BundleIntegrity -Root $bundleRoot
} else {
    Write-Warn "Integrity verification skipped (--SkipHashCheck)."
}

$defaultInstall = "D:\HybridRAG3"
$installDir = Read-Host "Install folder [$defaultInstall]"
if ([string]::IsNullOrWhiteSpace($installDir)) { $installDir = $defaultInstall }
$installDir = [System.IO.Path]::GetFullPath($installDir)

$defaultData = "D:\RAG Indexed Data"
$dataDir = Read-Host "Index/data folder [$defaultData]"
if ([string]::IsNullOrWhiteSpace($dataDir)) { $dataDir = $defaultData }

$defaultSource = "D:\RAG Source Data"
$sourceDir = Read-Host "Source documents folder [$defaultSource]"
if ([string]::IsNullOrWhiteSpace($sourceDir)) { $sourceDir = $defaultSource }

New-Item -ItemType Directory -Path $installDir,$dataDir,$sourceDir -Force | Out-Null

Write-Info "Copying app files..."
Copy-Tree -Source $appSrc -Dest $installDir
Write-Ok "Application copied"

Set-Location $installDir

$pyCmd = Resolve-Python
if ($pyCmd.Count -eq 0) {
    $pyInstaller = Get-ChildItem $installers -Filter "python*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Fail "Python 3.10+ not found"
    if ($pyInstaller) {
        Write-Warn "Python installer found in bundle:"
        Write-Host "  $($pyInstaller.FullName)"
        $runPy = Read-Host "Run Python installer now? [Y/n]"
        if ($runPy -ne "n" -and $runPy -ne "N") {
            Start-Process -FilePath $pyInstaller.FullName -Wait
            $pyCmd = Resolve-Python
        }
    }
    if ($pyCmd.Count -eq 0) {
        Write-Fail "Python still not available. Install Python, then rerun INSTALL.bat."
        exit 3
    }
}

Write-Info "Creating virtual environment..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $pyCmd @("-m", "venv", ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv" }
}
$pyExe = Join-Path $installDir ".venv\Scripts\python.exe"
$pipExe = Join-Path $installDir ".venv\Scripts\pip.exe"
Write-Ok "Virtual environment ready"

if (Test-Path $wheels) {
    Write-Info "Installing packages from local wheelhouse..."
    $req = "requirements.txt"
    if (Test-Path "requirements_approved.txt") { $req = "requirements_approved.txt" }
    & $pipExe install -r $req --no-index --find-links $wheels
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Offline pip install failed"
        exit 4
    }
    Write-Ok "Dependencies installed from wheelhouse"
} else {
    Write-Warn "No wheels folder found. Skipping dependency install."
}

Write-Info "Applying config paths..."
$cfg = Join-Path $installDir "config\default_config.yaml"
Write-LocalConfig -CfgPath $cfg -DataDir $dataDir -SourceDir $sourceDir
Write-Ok "Config updated"

Write-Info "Restoring local caches (if bundled)..."
$cachePairs = @(
    @{ Src = (Join-Path $cacheRoot "hf_cache"); Dst = (Join-Path $installDir ".hf_cache") },
    @{ Src = (Join-Path $cacheRoot "model_cache"); Dst = (Join-Path $installDir ".model_cache") },
    @{ Src = (Join-Path $cacheRoot "torch_cache"); Dst = (Join-Path $installDir ".torch_cache") }
)
foreach ($p in $cachePairs) {
    if (Test-Path $p.Src) {
        Copy-Tree -Source $p.Src -Dest $p.Dst
        Write-Ok "Restored cache: $($p.Dst)"
    }
}

$ollamaSrc = Join-Path $cacheRoot "ollama_models"
if (Test-Path $ollamaSrc) {
    $ollamaDst = Join-Path $env:USERPROFILE ".ollama\models"
    New-Item -ItemType Directory -Path $ollamaDst -Force | Out-Null
    Copy-Tree -Source $ollamaSrc -Dest $ollamaDst
    Write-Ok "Restored Ollama models"
}

# Install Ollama if missing and installer is bundled.
$ollamaOk = $false
try {
    & ollama --version *> $null
    if ($LASTEXITCODE -eq 0) { $ollamaOk = $true }
} catch {}
if (-not $ollamaOk) {
    $ollamaInstaller = Get-ChildItem $installers -Filter "OllamaSetup*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ollamaInstaller) {
        Write-Warn "Ollama is not installed."
        Write-Host "  Bundled installer: $($ollamaInstaller.FullName)"
        $runOllama = Read-Host "Run Ollama installer now? [Y/n]"
        if ($runOllama -ne "n" -and $runOllama -ne "N") {
            Start-Process -FilePath $ollamaInstaller.FullName -Wait
            try {
                & ollama --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    Write-Ok "Ollama installed"
                    $ollamaOk = $true
                }
            } catch {}
        }
    }
}
if (-not $ollamaOk) {
    Write-Warn "Ollama is not available. Offline query/index features will not work until Ollama is installed."
}

Write-Host ""
Write-Ok "Offline install complete"
Write-Host "  Install dir: $installDir"
Write-Host "  Data dir:    $dataDir"
Write-Host "  Source dir:  $sourceDir"
Write-Host ""
Write-Host "Next:"
Write-Host "  1) Open PowerShell in $installDir"
Write-Host "  2) Run: .\start_gui.bat"
Write-Host ""
exit 0
