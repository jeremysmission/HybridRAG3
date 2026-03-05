<#
=== NON-PROGRAMMER GUIDE ===
Purpose: Supports the build usb package workflow in this repository.
How to follow: Read variables first, then each command block in order.
Inputs: Environment variables, script parameters, and local files.
Outputs: Console messages, changed files, or system configuration updates.
Safety notes: Run in a test environment before using on production systems.
=============================
#>
# ============================================================================
# HybridRAG3 -- Build USB Offline Installer Package
# Date: 2026-02-25
# Status: RESEARCH / PROTOTYPE
# Scope: Personal repo only
#
# WHAT THIS DOES:
#   Downloads everything needed to install HybridRAG3 without internet.
#   Creates a self-contained folder that you copy to a USB drive.
#   The user on the target machine just double-clicks INSTALL.bat.
#
# PREREQUISITES:
#   - Internet connection (this script downloads files)
#   - Python 3.10+ installed
#   - About 4 GB of free disk space for the staging folder
#
# RUN:
#   powershell -ExecutionPolicy Bypass -File "USB Installer Research\build_usb_package.ps1"
# ============================================================================

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
function Write-Step {
    param([int]$num, [string]$msg)
    Write-Host "`n=== Step $num of 6 : $msg ===" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
# Where this script lives (USB Installer Research folder)
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
# The HybridRAG3 project root (one level up from USB Installer Research)
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

# Where to build the USB package
$STAGING = "$PROJECT_ROOT\USB Installer Research\_staging"

# Python versions to download wheels for (covers most work laptops)
$PY_VERSIONS = @("cp311", "cp312", "cp310")

# Ollama download URL (Windows AMD64)
$OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"

# Python embeddable download URL (3.11.9 AMD64)
$PYTHON_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
$PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Build USB Offline Installer Package" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This will download all dependencies and create a folder"
Write-Host "  you can copy to a USB drive for offline installation."
Write-Host ""
Write-Host "  Staging folder: $STAGING"
Write-Host "  Estimated download: 3-4 GB (depending on models)"
Write-Host ""

# ==================================================================
# Step 1: Create staging folder structure
# ==================================================================
Write-Step 1 "Creating staging folder"

if (Test-Path "$STAGING") {
    Write-Warn "Staging folder already exists"
    $confirm = Read-Host "  Delete and rebuild? [Y/n]"
    if ($confirm -eq "n" -or $confirm -eq "N") {
        Write-Host "  Cancelled."
        exit 0
    }
    Remove-Item -Path "$STAGING" -Recurse -Force
}

# Create the folder structure that will be on the USB
# USB root/
#   INSTALL.bat          -- double-click to start
#   HybridRAG3/          -- the source code
#   wheels/              -- pre-downloaded pip packages
#   python/              -- Python installer
#   ollama/              -- Ollama installer + models
New-Item -ItemType Directory -Path "$STAGING" -Force | Out-Null
New-Item -ItemType Directory -Path "$STAGING\wheels" -Force | Out-Null
New-Item -ItemType Directory -Path "$STAGING\python" -Force | Out-Null
New-Item -ItemType Directory -Path "$STAGING\ollama" -Force | Out-Null
New-Item -ItemType Directory -Path "$STAGING\ollama\models" -Force | Out-Null
Write-Ok "Staging folder created"

# ==================================================================
# Step 2: Copy HybridRAG3 source code
# ==================================================================
# We copy only the essential files (no .venv, .git, __pycache__, etc.)
# This keeps the USB package small and clean.
# ------------------------------------------------------------------
Write-Step 2 "Copying HybridRAG3 source code"

# Folders to copy
$COPY_DIRS = @("src", "tests", "config", "tools", "scripts", "docs", "diagnostics")
# Individual files to copy
$COPY_FILES = @(
    "requirements.txt",
    "requirements_approved.txt",
    "pytest.ini",
    "start_hybridrag.ps1",
    "start_gui.bat",
    "start_rag.bat",
    "INSTALL.bat",
    ".gitignore"
)

$destProject = "$STAGING\HybridRAG3"
New-Item -ItemType Directory -Path "$destProject" -Force | Out-Null

foreach ($dir in $COPY_DIRS) {
    $srcDir = "$PROJECT_ROOT\$dir"
    if (Test-Path "$srcDir") {
        # Robocopy: /E = recurse, /XD = exclude dirs, /XF = exclude files
        # /NJH /NJS /NDL /NFL = suppress noisy output
        robocopy "$srcDir" "$destProject\$dir" /E /XD __pycache__ .model_cache /XF *.pyc *.bak /NJH /NJS /NDL /NFL | Out-Null
        Write-Ok "Copied $dir/"
    }
}

foreach ($file in $COPY_FILES) {
    $srcFile = "$PROJECT_ROOT\$file"
    if (Test-Path "$srcFile") {
        Copy-Item -Path "$srcFile" -Destination "$destProject\$file" -Force
    }
}
Write-Ok "Source code copied to staging"

# ==================================================================
# Step 3: Download pip wheel files (offline package cache)
# ==================================================================
# pip download saves .whl files that can be installed without internet.
# We download wheels for the requirements file so the target machine
# does not need to connect to PyPI at all.
# ------------------------------------------------------------------
Write-Step 3 "Downloading pip wheels for offline install"
Write-Host "  This downloads all packages as .whl files."
Write-Host "  It may take 2-5 minutes depending on your internet speed."
Write-Host ""

$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"
if (-not (Test-Path "$PIP")) {
    # Fall back to system pip
    $PIP = "pip"
}

# Download wheels for the personal requirements (includes pytest/psutil)
& $PIP download -r "$PROJECT_ROOT\requirements.txt" -d "$STAGING\wheels" --only-binary=:all: --platform win_amd64 --python-version 3.11 2>&1 | ForEach-Object {
    $line = $_.ToString()
    if ($line -match "Downloading|Saved|ERROR") { Write-Host "  $line" }
}

# Also download for the approved requirements (work repo)
& $PIP download -r "$PROJECT_ROOT\requirements_approved.txt" -d "$STAGING\wheels" --only-binary=:all: --platform win_amd64 --python-version 3.11 2>&1 | ForEach-Object {
    $line = $_.ToString()
    if ($line -match "Downloading|Saved|ERROR") { Write-Host "  $line" }
}

# Some packages are pure Python (no binary) -- download those too
& $PIP download -r "$PROJECT_ROOT\requirements.txt" -d "$STAGING\wheels" --no-binary=:none: --platform any 2>&1 | Out-Null

$wheelCount = (Get-ChildItem "$STAGING\wheels" -Filter "*.whl").Count
Write-Ok "Downloaded $wheelCount wheel files"

# ==================================================================
# Step 4: Download Python installer
# ==================================================================
# The target machine may not have Python installed, so we include
# the official Python installer. The user can run it manually or
# the install script will prompt them.
# ------------------------------------------------------------------
Write-Step 4 "Downloading Python installer"

$pythonDest = "$STAGING\python\python-3.11.9-amd64.exe"
if (Test-Path "$pythonDest") {
    Write-Ok "Python installer already downloaded"
} else {
    Write-Host "  Downloading Python 3.11.9 installer (~25 MB)..."
    try {
        Invoke-WebRequest -Uri $PYTHON_INSTALLER_URL -OutFile "$pythonDest" -UseBasicParsing
        Write-Ok "Python installer downloaded"
    } catch {
        Write-Warn "Could not download Python installer"
        Write-Host "  You can manually download it from:"
        Write-Host "  $PYTHON_INSTALLER_URL"
        Write-Host "  and place it in: $STAGING\python\"
    }
}

# ==================================================================
# Step 5: Download Ollama installer and models
# ==================================================================
# Ollama is the local AI engine. We download the installer and
# optionally pre-download the AI models so the target machine
# does not need internet for those either.
# ------------------------------------------------------------------
Write-Step 5 "Downloading Ollama installer and models"

$ollamaDest = "$STAGING\ollama\OllamaSetup.exe"
if (Test-Path "$ollamaDest") {
    Write-Ok "Ollama installer already downloaded"
} else {
    Write-Host "  Downloading Ollama installer (~200 MB)..."
    try {
        Invoke-WebRequest -Uri $OLLAMA_URL -OutFile "$ollamaDest" -UseBasicParsing
        Write-Ok "Ollama installer downloaded"
    } catch {
        Write-Warn "Could not download Ollama installer"
        Write-Host "  Download manually from: https://ollama.com/download"
    }
}

# Copy Ollama model files if they exist locally
# Models are stored in ~/.ollama/models/ as blob files
$ollamaModels = "$env:USERPROFILE\.ollama\models"
if (Test-Path "$ollamaModels") {
    Write-Host "  Copying local Ollama models (this may take a few minutes)..."

    # Copy the manifests (tells Ollama which models are available)
    $manifestDir = "$ollamaModels\manifests"
    if (Test-Path "$manifestDir") {
        robocopy "$manifestDir" "$STAGING\ollama\models\manifests" /E /NJH /NJS /NDL /NFL | Out-Null
    }

    # Copy the blob files (the actual model weights)
    $blobDir = "$ollamaModels\blobs"
    if (Test-Path "$blobDir") {
        # Only copy nomic-embed-text and phi4-mini blobs
        # (skip large models like phi4:14b to save USB space)
        robocopy "$blobDir" "$STAGING\ollama\models\blobs" /E /NJH /NJS /NDL /NFL | Out-Null
    }

    Write-Ok "Ollama models copied"
    Write-Warn "NOTE: All local models were copied. Remove large ones"
    Write-Host "  to save space if you only need nomic-embed-text + phi4-mini."
} else {
    Write-Warn "No local Ollama models found -- models will need to be"
    Write-Host "  downloaded on the target machine (requires internet)."
}

# ==================================================================
# Step 6: Create the USB-side installer files
# ==================================================================
# Copy the USB install script and launcher to the staging root.
# These are what the user double-clicks on the target machine.
# ------------------------------------------------------------------
Write-Step 6 "Creating USB installer files"

$usbScriptSrc = "$SCRIPT_DIR\usb_install.ps1"
$usbBatSrc = "$SCRIPT_DIR\usb_install.bat"

if (Test-Path "$usbScriptSrc") {
    Copy-Item -Path "$usbScriptSrc" -Destination "$STAGING\usb_install.ps1" -Force
    Write-Ok "Copied usb_install.ps1"
} else {
    Write-Warn "usb_install.ps1 not found in USB Installer Research folder"
}

if (Test-Path "$usbBatSrc") {
    Copy-Item -Path "$usbBatSrc" -Destination "$STAGING\INSTALL.bat" -Force
    Write-Ok "Copied INSTALL.bat (USB version)"
} else {
    Write-Warn "usb_install.bat not found -- creating basic launcher"
    Set-Content -Path "$STAGING\INSTALL.bat" -Value @"
@echo off
title HybridRAG3 -- USB Offline Installer
echo.
echo  ============================================================
echo  HybridRAG3 USB Offline Installer
echo  No internet connection required.
echo  ============================================================
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0usb_install.ps1"
echo.
echo  Press any key to close...
pause >nul
"@
}

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  USB Package Built Successfully" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# Calculate total size
$totalBytes = (Get-ChildItem "$STAGING" -Recurse | Measure-Object -Property Length -Sum).Sum
$totalGB = [math]::Round($totalBytes / 1GB, 2)
$totalMB = [math]::Round($totalBytes / 1MB, 0)

Write-Host "  Location: $STAGING"
if ($totalGB -ge 1) {
    Write-Host "  Total size: $totalGB GB"
} else {
    Write-Host "  Total size: $totalMB MB"
}
Write-Host ""
Write-Host "  NEXT STEPS:"
Write-Host "    1. Review the contents of: $STAGING"
Write-Host "    2. Remove any large models you do not need"
Write-Host "    3. Copy the entire _staging folder to your USB drive"
Write-Host "    4. On the target machine: double-click INSTALL.bat"
Write-Host ""
Write-Host "  RECOMMENDED USB SIZE: 8 GB (gives headroom for models)"
Write-Host ""
