# ============================================================================
# HybridRAG3 -- USB Offline Installer
# Date: 2026-02-25
# Status: RESEARCH / PROTOTYPE
#
# WHAT THIS DOES:
#   Installs HybridRAG3 from a USB drive without needing internet.
#   All packages, Python, and AI models are pre-loaded on the USB.
#
# HOW TO USE:
#   1. Plug in the USB drive
#   2. Double-click INSTALL.bat on the USB
#   3. Follow the prompts
#
# THIS SCRIPT HANDLES:
#   - Group Policy restrictions (ExecutionPolicy bypass)
#   - Corporate proxy (not needed -- everything is local)
#   - Python installation check
#   - Offline pip install from pre-downloaded wheel files
#   - Ollama model deployment from USB
#   - All path configuration
# ============================================================================

# ------------------------------------------------------------------
# Group Policy Bypass
# ------------------------------------------------------------------
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue
} catch { }

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# UTF-8 Encoding Fix
# ------------------------------------------------------------------
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
$TOTAL_STEPS = 10
function Write-Step {
    param([int]$num, [string]$msg)
    Write-Host "`n=== Step $num of $TOTAL_STEPS : $msg ===" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------------
# Detect USB drive location
# ------------------------------------------------------------------
# This script should be at the root of the USB staging folder.
# The folder structure is:
#   USB_ROOT/
#     INSTALL.bat
#     usb_install.ps1    <-- this file
#     HybridRAG3/        <-- source code
#     wheels/            <-- pre-downloaded pip packages
#     python/            <-- Python installer
#     ollama/            <-- Ollama installer + models
# ------------------------------------------------------------------
$USB_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HybridRAG3 -- USB Offline Installer" -ForegroundColor Cyan
Write-Host "  No internet connection required" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  USB location: $USB_ROOT"
Write-Host ""
Write-Host "  This installer works completely offline."
Write-Host "  All packages and AI models are pre-loaded on the USB."
Write-Host ""
Write-Host "  SAFE TO RE-RUN: Skips completed steps."
Write-Host ""

# Verify USB contents
$hasSource = Test-Path "$USB_ROOT\HybridRAG3"
$hasWheels = Test-Path "$USB_ROOT\wheels"
$hasPython = Test-Path "$USB_ROOT\python"

if (-not $hasSource) {
    Write-Fail "HybridRAG3 source folder not found on USB"
    Write-Host "  Expected: $USB_ROOT\HybridRAG3\"
    Write-Host "  The USB package may be incomplete. Rebuild it."
    exit 1
}
if (-not $hasWheels) {
    Write-Fail "Wheels folder not found on USB"
    Write-Host "  Expected: $USB_ROOT\wheels\"
    Write-Host "  The USB package may be incomplete. Rebuild it."
    exit 1
}
Write-Ok "USB contents verified"

# ==================================================================
# Step 1: Choose install location
# ==================================================================
Write-Step 1 "Choose install location"

Write-Host ""
Write-Host "  Where should HybridRAG3 be installed?"
Write-Host "  The source code will be COPIED from the USB to this location."
Write-Host ""
Write-Host "  Suggested: D:\HybridRAG3" -ForegroundColor White
Write-Host ""
$INSTALL_DIR = Read-Host "  Install folder [D:\HybridRAG3]"
if ([string]::IsNullOrWhiteSpace($INSTALL_DIR)) { $INSTALL_DIR = "D:\HybridRAG3" }
$INSTALL_DIR = [System.IO.Path]::GetFullPath($INSTALL_DIR)

# Safety: do not overwrite a different project
if (Test-Path "$INSTALL_DIR") {
    if ((Test-Path "$INSTALL_DIR\.git") -and -not (Test-Path "$INSTALL_DIR\requirements.txt")) {
        Write-Fail "Directory '$INSTALL_DIR' contains a different project."
        Write-Host "  Choose an empty folder or the correct HybridRAG3 folder."
        exit 1
    }
    if (Test-Path "$INSTALL_DIR\requirements.txt") {
        Write-Warn "HybridRAG3 already exists at this location."
        Write-Host ""
        Write-Host "  Options:"
        Write-Host "    Enter = Update source code and re-run setup"
        Write-Host "    P     = Purge .venv and start completely fresh"
        Write-Host "    N     = Cancel"
        Write-Host ""
        $confirm = Read-Host "  Choose [Enter/P/N]"
        if ($confirm -eq "n" -or $confirm -eq "N") { exit 0 }
        if ($confirm -eq "p" -or $confirm -eq "P") {
            Write-Host "  Removing old .venv..."
            Remove-Item -Path "$INSTALL_DIR\.venv" -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "Old .venv removed"
        }
    }
}

# ==================================================================
# Step 2: Copy source code from USB
# ==================================================================
Write-Step 2 "Copying source code from USB"

Write-Host "  Copying HybridRAG3 files to $INSTALL_DIR..."
if (-not (Test-Path "$INSTALL_DIR")) {
    New-Item -ItemType Directory -Path "$INSTALL_DIR" -Force | Out-Null
}
robocopy "$USB_ROOT\HybridRAG3" "$INSTALL_DIR" /E /XD __pycache__ /XF *.pyc /NJH /NJS /NDL /NFL | Out-Null
# BUG 11 FIX: robocopy exit codes 0-3 = success, 4+ = error
if ($LASTEXITCODE -ge 4) {
    Write-Fail "File copy failed (robocopy exit code $LASTEXITCODE)"
    exit 1
}
# Reset LASTEXITCODE -- robocopy returns 1 for "new files copied" which is success
$global:LASTEXITCODE = 0
Write-Ok "Source code copied to $INSTALL_DIR"
Set-Location "$INSTALL_DIR"

# ==================================================================
# Step 3: Check Python
# ==================================================================
Write-Step 3 "Checking Python"

$PY_EXE = $null
$PY_VER_FLAG = $null
# BUG 10 FIX: faiss-cpu requires Python >= 3.10, drop 3.9
foreach ($ver in @("3.12", "3.11", "3.10")) {
    try {
        $result = & py "-$ver" --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PY_EXE = "py"
            $PY_VER_FLAG = "-$ver"
            Write-Ok "Found Python $ver"
            break
        }
    } catch { }
}

if (-not $PY_EXE) {
    try {
        $result = & python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PY_EXE = "python"
            Write-Ok "Found: $result"
        }
    } catch { }
}

if (-not $PY_EXE) {
    Write-Fail "Python is not installed."
    Write-Host ""
    if ($hasPython) {
        $installer = Get-ChildItem "$USB_ROOT\python" -Filter "*.exe" | Select-Object -First 1
        if ($installer) {
            Write-Host "  A Python installer is included on this USB:"
            Write-Host "    $($installer.FullName)" -ForegroundColor White
            Write-Host ""
            Write-Host "  To install Python:"
            Write-Host "    1. Run the installer above"
            Write-Host "    2. IMPORTANT: Check 'Add Python to PATH'"
            Write-Host "    3. Restart your computer"
            Write-Host "    4. Run this installer again"
        }
    } else {
        Write-Host "  Ask your IT department to install Python 3.11 or 3.12."
    }
    Write-Host ""
    exit 1
}

# ==================================================================
# Step 4: Configure paths
# ==================================================================
Write-Step 4 "Configure paths"

Write-Host ""
Write-Host "  Where should the search database be stored?"
Write-Host "  Example: D:\RAG Indexed Data" -ForegroundColor White
Write-Host ""
$DATA_DIR = Read-Host "  Database folder"
while ([string]::IsNullOrWhiteSpace($DATA_DIR)) {
    Write-Warn "Please enter a folder path"
    $DATA_DIR = Read-Host "  Database folder"
}

Write-Host ""
Write-Host "  Where are your documents?"
Write-Host "  Example: D:\RAG Source Data" -ForegroundColor White
Write-Host ""
$SOURCE_DIR = Read-Host "  Documents folder"
while ([string]::IsNullOrWhiteSpace($SOURCE_DIR)) {
    Write-Warn "Please enter a folder path"
    $SOURCE_DIR = Read-Host "  Documents folder"
}

if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null }
Write-Ok "Paths configured"

# ==================================================================
# Step 5: Create virtual environment
# ==================================================================
Write-Step 5 "Creating virtual environment"

if (Test-Path ".venv") {
    Write-Ok ".venv already exists -- skipping"
} else {
    Write-Host "  Creating .venv..."
    if ($PY_VER_FLAG) {
        & $PY_EXE $PY_VER_FLAG -m venv .venv
    } else {
        & $PY_EXE -m venv .venv
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Fail "Virtual environment creation failed"
        exit 1
    }
    Write-Ok "Virtual environment created"
}

$PYTHON = "$INSTALL_DIR\.venv\Scripts\python.exe"
$PIP = "$INSTALL_DIR\.venv\Scripts\pip.exe"

# Upgrade pip (from USB cache, no internet needed)
# BUG 8 FIX: check exit code after pip upgrade
& $PYTHON -m pip install --upgrade pip --no-index --find-links="$USB_ROOT\wheels" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip upgrade failed (using existing version)"
} else {
    Write-Ok "pip upgraded (from USB cache)"
}

# ==================================================================
# Step 6: Install packages OFFLINE from USB wheels
# ==================================================================
# This is the key difference from the online installer.
# Instead of downloading from PyPI, we install from the pre-downloaded
# .whl files on the USB drive. The --no-index flag tells pip to NOT
# contact PyPI at all. The --find-links flag points to the USB's
# wheels folder.
# ------------------------------------------------------------------
Write-Step 6 "Installing packages from USB (offline)"
Write-Host "  Installing from pre-downloaded packages on USB..."
Write-Host "  No internet connection needed."
Write-Host ""

# Detect which requirements file to use
$reqFile = "requirements.txt"
if (Test-Path "$INSTALL_DIR\requirements_approved.txt") {
    if (Test-Path "$INSTALL_DIR\start_hybridrag.ps1.template") {
        $reqFile = "requirements_approved.txt"
        Write-Host "  Detected: Work/Educational repo"
        Write-Host "  Using: $reqFile"
    }
}

& $PIP install -r "$reqFile" --no-index --find-links="$USB_ROOT\wheels" 2>&1 | ForEach-Object {
    $line = $_.ToString()
    if ($line -match "Installing|Successfully|ERROR") { Write-Host "  $line" }
}

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Package installation failed"
    Write-Host "  Some wheels may be missing from the USB."
    Write-Host "  Rebuild the USB package with build_usb_package.ps1"
    exit 1
}

# Verify critical packages
$failed = @()
foreach ($pkg in @("fastapi", "httpx", "openai", "pydantic", "numpy", "yaml")) {
    & $PYTHON -c "import $pkg" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
}
if ($failed.Count -gt 0) {
    Write-Fail "Failed to import: $($failed -join ', ')"
    exit 1
}
Write-Ok "All packages installed from USB"

# ==================================================================
# Step 7: Configure application
# ==================================================================
Write-Step 7 "Configuring application"

$configPath = "$INSTALL_DIR\config\default_config.yaml"
if (Test-Path "$configPath") {
    $content = Get-Content "$configPath" -Raw -Encoding UTF8
    $dbPath = "$DATA_DIR\hybridrag.sqlite3"
    $embPath = "$DATA_DIR\_embeddings"
    # BUG 3 FIX: escape $ in paths so -replace does not treat them as backreferences
    $safeDbPath = $dbPath.Replace('$', '$$')
    $safeEmbPath = $embPath.Replace('$', '$$')
    $safeSrcDir = $SOURCE_DIR.Replace('$', '$$')
    $content = $content -replace '(?m)^(\s*database:\s*).*$', "`$1$safeDbPath"
    $content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', "`$1$safeEmbPath"
    $content = $content -replace '(?m)^(\s*source_folder:\s*).*$', "`$1$safeSrcDir"
    # YAML is consumed by Python -- must NOT have BOM (Set-Content adds BOM in PS 5.1)
    [System.IO.File]::WriteAllText($configPath, $content)
    Write-Ok "Config updated"
}

# Handle template-based start script (Educational repo)
$templatePath = "$INSTALL_DIR\start_hybridrag.ps1.template"
$startScript = "$INSTALL_DIR\start_hybridrag.ps1"
if ((-not (Test-Path "$startScript")) -and (Test-Path "$templatePath")) {
    $content = Get-Content "$templatePath" -Raw -Encoding UTF8
    $content = $content -replace 'C:\\path\\to\\HybridRAG3', $INSTALL_DIR
    $content = $content -replace 'C:\\path\\to\\data', $DATA_DIR
    $content = $content -replace 'C:\\path\\to\\source_docs', $SOURCE_DIR
    Set-Content -Path "$startScript" -Value $content -Encoding UTF8
    Write-Ok "start_hybridrag.ps1 created from template"
} elseif (Test-Path "$startScript") {
    $content = Get-Content "$startScript" -Raw -Encoding UTF8
    $content = $content -replace '(?m)^\$DATA_DIR\s*=\s*"[^"]*"', "`$DATA_DIR   = `"$DATA_DIR`""
    $content = $content -replace '(?m)^\$SOURCE_DIR\s*=\s*"[^"]*"', "`$SOURCE_DIR = `"$SOURCE_DIR`""
    Set-Content -Path "$startScript" -Value $content -Encoding UTF8
    Write-Ok "start_hybridrag.ps1 paths updated"
}

# Create logs directory
$logsDir = "$INSTALL_DIR\logs"
if (-not (Test-Path "$logsDir")) {
    New-Item -ItemType Directory -Path "$logsDir" -Force | Out-Null
}

# ==================================================================
# Step 8: Install Ollama models from USB
# ==================================================================
# If the USB has pre-downloaded Ollama models, we copy them to the
# user's local Ollama directory so they do not need to download them.
# ------------------------------------------------------------------
Write-Step 8 "Installing Ollama models from USB"

$usbModels = "$USB_ROOT\ollama\models"
$localOllama = "$env:USERPROFILE\.ollama\models"

if (Test-Path "$usbModels\manifests") {
    Write-Host "  Copying AI models from USB to local Ollama directory..."
    Write-Host "  This may take a few minutes for large models."
    Write-Host ""

    if (-not (Test-Path "$localOllama")) {
        New-Item -ItemType Directory -Path "$localOllama" -Force | Out-Null
    }

    robocopy "$usbModels" "$localOllama" /E /NJH /NJS /NDL /NFL | Out-Null
    # BUG 11 FIX: robocopy exit codes 0-3 = success, 4+ = error
    if ($LASTEXITCODE -ge 4) {
        Write-Fail "File copy failed (robocopy exit code $LASTEXITCODE)"
        exit 1
    }
    # Reset LASTEXITCODE -- robocopy returns 1 for "new files copied" which is success
    $global:LASTEXITCODE = 0
    Write-Ok "Ollama models installed from USB"
} else {
    Write-Warn "No pre-downloaded models found on USB"
    Write-Host "  You will need internet to run: ollama pull nomic-embed-text"
}

# Check if Ollama itself is installed
$ollamaInstaller = "$USB_ROOT\ollama\OllamaSetup.exe"
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
    Write-Ok "Ollama is installed and running"
} catch {
    if (Test-Path "$ollamaInstaller") {
        Write-Warn "Ollama is not installed yet"
        Write-Host "  An Ollama installer is on this USB:"
        Write-Host "    $ollamaInstaller" -ForegroundColor White
        Write-Host "  Run it to install Ollama, then restart this script."
    } else {
        Write-Warn "Ollama is not installed and no installer found on USB"
    }
}

# ==================================================================
# Step 9: Run verification
# ==================================================================
Write-Step 9 "Running verification"

# BUG 19 FIX: use exit code instead of fragile output parsing
$hasPytest = & $PYTHON -c "import pytest" 2>&1
if ($LASTEXITCODE -eq 0) {
    & $PYTHON -m pytest tests/ --ignore=tests/test_fastapi_server.py -q --tb=no 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Verification: all tests passed"
    } else {
        Write-Warn "Some tests failed (exit code $LASTEXITCODE)"
        Write-Host "  Run manually: python -m pytest tests/ -q"
    }
} else {
    Write-Warn "pytest not available -- skipping verification"
}

# ==================================================================
# Step 10: Done
# ==================================================================
Write-Step 10 "Complete"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  USB Installation Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  HOW TO START HybridRAG3:"
Write-Host "  -----------------------------------------------"
Write-Host "  EASIEST WAY:" -ForegroundColor White
Write-Host "    Double-click:  start_gui.bat" -ForegroundColor White
Write-Host "    (in $INSTALL_DIR)"
Write-Host ""
Write-Host "  FROM CMD:" -ForegroundColor White
Write-Host "    1. Open cmd.exe"
Write-Host "    2. cd /d `"$INSTALL_DIR`""
Write-Host "    3. .venv\Scripts\activate.bat"
Write-Host "    4. python src/gui/launch_gui.py"
Write-Host ""
Write-Host "  You can now safely remove the USB drive."
Write-Host ""
