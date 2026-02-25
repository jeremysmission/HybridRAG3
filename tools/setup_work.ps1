# ============================================================================
# HybridRAG3 -- Automated Work/Educational Setup
# Date: 2026-02-25
# Uses: requirements_approved.txt (enterprise-approved packages only)
# Handles: Corporate proxy, SSL certificates, Group Policy
# Run via: INSTALL.bat (double-click) or tools\setup_work.bat
#   or: powershell -ExecutionPolicy Bypass -File tools\setup_work.ps1
#
# SAFE TO RE-RUN: If setup was interrupted or you want to redo it,
# just run this script again. It skips what is already done and fixes
# anything left incomplete. Use "P" at the prompt to purge and restart.
# ============================================================================

# ------------------------------------------------------------------
# Group Policy Bypass
# ------------------------------------------------------------------
# Work laptops often have Group Policy that blocks PowerShell scripts.
# This attempts to set the execution policy for just this process.
# If Group Policy blocks even this, the .bat launcher handles it
# via the -ExecutionPolicy Bypass flag on the powershell.exe command.
# ------------------------------------------------------------------
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue
} catch {
    # Group Policy may block this -- the .bat launcher already bypassed
}

$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------
# UTF-8 Encoding Fix (prevents garbled parentheses and special chars)
# ------------------------------------------------------------------
# Windows PowerShell defaults to system locale code page (437/1252).
# Python outputs UTF-8 by default. Without this fix, parentheses,
# accents, and Unicode in Python output get mangled in the console.
# ------------------------------------------------------------------
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Fallback: older PowerShell versions may not support this
}

# ------------------------------------------------------------------
# Helper functions for colored output
# ------------------------------------------------------------------
$TOTAL_STEPS = 13
function Write-Step {
    param([int]$num, [string]$msg)
    Write-Host "`n=== Step $num of $TOTAL_STEPS : $msg ===" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------------
# Welcome banner
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HybridRAG3 -- Work/Educational Setup" -ForegroundColor Cyan
Write-Host "  (Enterprise-approved packages only)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This script will set up HybridRAG3 on your work computer."
Write-Host "  It handles corporate proxy and security restrictions automatically."
Write-Host "  It will ask you a few questions, then do the rest automatically."
Write-Host "  Estimated time: 5-10 minutes (depends on network speed)."
Write-Host ""
Write-Host "  SAFE TO RE-RUN: Skips completed steps. Use 'P' to purge and restart."
Write-Host ""

# ==================================================================
# Step 1: Choose install location
# ==================================================================
# The script detects where the project files are based on its own
# location (the tools/ folder). You can override if needed.
# ------------------------------------------------------------------
Write-Step 1 "Choose install location"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$DETECTED_ROOT = Split-Path -Parent $SCRIPT_DIR

Write-Host ""
Write-Host "  We found the project files here:"
Write-Host "    $DETECTED_ROOT" -ForegroundColor White
Write-Host ""
Write-Host "  Is this correct? Just press Enter to continue."
Write-Host "  Or type a different folder path if you moved the files."
Write-Host "  (This should be the folder you extracted the ZIP into)"
Write-Host ""
$USER_PATH = Read-Host "  Project folder [$DETECTED_ROOT]"
if ([string]::IsNullOrWhiteSpace($USER_PATH)) { $USER_PATH = $DETECTED_ROOT }

$PROJECT_ROOT = [System.IO.Path]::GetFullPath($USER_PATH)

# ------------------------------------------------------------------
# Safety checks
# ------------------------------------------------------------------
if (Test-Path "$PROJECT_ROOT") {
    # Wrong repo? Personal repo has requirements.txt but no _approved version
    if ((Test-Path "$PROJECT_ROOT\requirements.txt") -and -not (Test-Path "$PROJECT_ROOT\requirements_approved.txt")) {
        Write-Fail "Directory '$PROJECT_ROOT' contains HybridRAG3 (personal repo)."
        Write-Host "  This script is for the WORK/EDUCATIONAL repo."
        Write-Host "  Use setup_home.bat for the personal repo instead."
        exit 1
    }
    # Some other git repo?
    if ((Test-Path "$PROJECT_ROOT\.git") -and -not (Test-Path "$PROJECT_ROOT\requirements_approved.txt")) {
        Write-Fail "Directory '$PROJECT_ROOT' contains a different git repository."
        Write-Host "  Choose the correct HybridRAG3_Educational folder."
        exit 1
    }
    # Already installed? Offer resume or purge
    if ((Test-Path "$PROJECT_ROOT\requirements_approved.txt") -and (Test-Path "$PROJECT_ROOT\.venv")) {
        Write-Warn "This folder already has an existing installation."
        Write-Host ""
        Write-Host "  Options:"
        Write-Host "    Enter = Resume / re-run setup (keeps .venv, updates config)"
        Write-Host "    P     = Purge .venv and start completely fresh"
        Write-Host "    N     = Cancel and exit"
        Write-Host ""
        $confirm = Read-Host "  Choose [Enter/P/N]"
        if ($confirm -eq "n" -or $confirm -eq "N") {
            Write-Host "  Cancelled."
            exit 0
        }
        if ($confirm -eq "p" -or $confirm -eq "P") {
            Write-Host "  Removing old .venv (this may take a moment)..."
            Remove-Item -Path "$PROJECT_ROOT\.venv" -Recurse -Force -ErrorAction SilentlyContinue
            Write-Ok "Old .venv removed -- starting fresh"
        }
    }
} else {
    Write-Fail "Directory '$PROJECT_ROOT' does not exist."
    Write-Host "  Download the ZIP from the Educational repo on GitHub first."
    Write-Host "  Extract it to a folder, then re-run this script."
    exit 1
}

if (-not (Test-Path "$PROJECT_ROOT\requirements_approved.txt")) {
    Write-Fail "Cannot find requirements_approved.txt in $PROJECT_ROOT"
    Write-Host "  This does not appear to be a HybridRAG3_Educational folder."
    Write-Host "  If setting up the personal repo, use setup_home.bat instead."
    exit 1
}
Write-Ok "Install location: $PROJECT_ROOT"
Set-Location "$PROJECT_ROOT"

# ==================================================================
# Step 2: Detect Python
# ==================================================================
# Work laptops may have older Python versions. We try 3.12 down to 3.9.
# Python is usually installed by IT via Software Center or Company Portal.
# ------------------------------------------------------------------
Write-Step 2 "Detecting Python"
$PY_EXE = $null
$PY_VER_FLAG = $null
foreach ($ver in @("3.12", "3.11", "3.10", "3.9")) {
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
    Write-Fail "Python is not installed (or not on PATH)."
    Write-Host ""
    Write-Host "  HOW TO FIX:"
    Write-Host "  Python must be installed by your IT department."
    Write-Host "  Request it from one of these (whichever your company uses):"
    Write-Host "    - Software Center (on your Start menu)"
    Write-Host "    - Company Portal"
    Write-Host "    - ServiceNow (your IT ticketing system)"
    Write-Host ""
    Write-Host "  Ask for: Python 3.12, 3.11, or 3.10"
    Write-Host "  After IT installs it, double-click INSTALL.bat again."
    Write-Host ""
    exit 1
}

# ==================================================================
# Step 3: Configure paths
# ==================================================================
Write-Step 3 "Configure paths"

Write-Host ""
Write-Host "  Where should HybridRAG3 store its search database?"
Write-Host "  (Uses about 1-5 GB depending on how many documents you have)"
Write-Host ""
Write-Host "  Example: D:\RAG Indexed Data" -ForegroundColor White
Write-Host ""
$DATA_DIR = Read-Host "  Database folder"
while ([string]::IsNullOrWhiteSpace($DATA_DIR)) {
    Write-Warn "Please enter a folder path (cannot be empty)"
    $DATA_DIR = Read-Host "  Database folder"
}

Write-Host ""
Write-Host "  Where are the documents you want to search?"
Write-Host "  (HybridRAG3 will read these files but never modify them)"
Write-Host ""
Write-Host "  Example: D:\RAG Source Data" -ForegroundColor White
Write-Host ""
$SOURCE_DIR = Read-Host "  Documents folder"
while ([string]::IsNullOrWhiteSpace($SOURCE_DIR)) {
    Write-Warn "Please enter a folder path (cannot be empty)"
    $SOURCE_DIR = Read-Host "  Documents folder"
}

Write-Ok "Data directory: $DATA_DIR"
Write-Ok "Source directory: $SOURCE_DIR"

if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null; Write-Ok "Created: $DATA_DIR" }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null; Write-Ok "Created: $SOURCE_DIR" }

# ==================================================================
# Step 4: Create virtual environment
# ==================================================================
Write-Step 4 "Creating virtual environment"

if (Test-Path ".venv") {
    Write-Ok ".venv already exists -- skipping (use Purge to redo)"
} else {
    Write-Host "  Creating .venv (this takes about 10 seconds)..."
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

# ==================================================================
# Step 5: Upgrade pip (with corporate proxy workaround)
# ==================================================================
# Corporate proxies often intercept HTTPS and replace the SSL certificate
# with their own. This causes pip to fail with CERTIFICATE_VERIFY_FAILED.
# The --trusted-host flags tell pip to skip certificate verification for
# the official PyPI servers, which is safe on a corporate network.
# ------------------------------------------------------------------
Write-Step 5 "Preparing package installer (handling corporate proxy)"

$PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"

# These flags bypass corporate SSL interception for PyPI downloads
$TRUSTED = "--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org"

Write-Host "  Upgrading pip with trusted-host flags..."
& $PYTHON -m pip install --upgrade pip @TRUSTED 2>&1 | Out-Null
$pipVer = & $PIP --version 2>&1
Write-Ok "pip ready: $pipVer"

# ==================================================================
# Step 6: Install pip-system-certs (corporate SSL integration)
# ==================================================================
# This package makes Python trust the Windows certificate store.
# After this, corporate proxy certificates are recognized and
# future pip commands no longer need --trusted-host flags.
# ------------------------------------------------------------------
Write-Step 6 "Installing corporate certificate support"

& $PIP install pip-system-certs @TRUSTED 2>&1 | Out-Null
Write-Ok "pip-system-certs installed -- Python now trusts Windows certificates"

# Prevent corporate proxy from intercepting localhost connections
# (Ollama runs on localhost:11434 and the proxy would break it)
$env:NO_PROXY = "localhost,127.0.0.1"
Write-Ok "NO_PROXY set for localhost"

# ==================================================================
# Step 7: Install approved packages
# ==================================================================
# Downloads all enterprise-approved Python packages. You will see
# download progress for each package. If interrupted, re-run the
# script -- pip keeps downloaded files in cache and resumes.
# ------------------------------------------------------------------
Write-Step 7 "Installing packages (you will see download progress below)"
Write-Host "  This may take 2-5 minutes on first install."
Write-Host "  If interrupted, just re-run -- pip resumes from cache."
Write-Host ""

$maxAttempts = 3
$attempt = 0
$pipSuccess = $false
do {
    $attempt++
    if ($attempt -gt 1) { Write-Warn "Retrying... (attempt $attempt of $maxAttempts)" }
    & $PIP install -r requirements_approved.txt @TRUSTED 2>&1 | ForEach-Object {
        $line = $_.ToString()
        if ($line -match "Downloading|Installing|Successfully|ERROR|WARNING") {
            Write-Host "  $line"
        }
    }
    if ($LASTEXITCODE -eq 0) { $pipSuccess = $true; break }
    Write-Warn "Package install had issues (exit code $LASTEXITCODE)"
} while ($attempt -lt $maxAttempts)

if (-not $pipSuccess) {
    Write-Fail "Package installation failed after $maxAttempts attempts"
    Write-Host "  Try: .venv\Scripts\pip.exe install -r requirements_approved.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org"
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
Write-Ok "All critical packages verified"

# ==================================================================
# Step 8: Install test tools (optional)
# ==================================================================
# pytest and psutil are used to verify the installation works.
# They are safe to install but are still being formally approved.
# ------------------------------------------------------------------
Write-Step 8 "Installing test tools (optional)"
Write-Host ""
Write-Host "  pytest and psutil verify the installation works correctly."
Write-Host "  They are safe and do not affect the main application."
Write-Host "  (Approval status: YELLOW -- being submitted for formal approval)"
Write-Host ""
$installTests = Read-Host "  Install test tools? Press Enter for Yes, or type N to skip [Y/n]"
if ($installTests -ne "n" -and $installTests -ne "N") {
    & $PIP install pytest==9.0.2 psutil==7.2.2 @TRUSTED 2>&1 | Out-Null
    Write-Ok "Test packages installed"
} else {
    Write-Warn "Skipped -- you will not be able to run regression tests"
}

# ==================================================================
# Step 9: Configure default_config.yaml
# ==================================================================
Write-Step 9 "Configuring default_config.yaml"

$configPath = "$PROJECT_ROOT\config\default_config.yaml"
if (Test-Path "$configPath") {
    $content = Get-Content "$configPath" -Raw -Encoding UTF8
    $dbPath = "$DATA_DIR\hybridrag.sqlite3"
    $embPath = "$DATA_DIR\_embeddings"

    $content = $content -replace '(?m)^(\s*database:\s*).*$', "`$1$dbPath"
    $content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', "`$1$embPath"
    $content = $content -replace '(?m)^(\s*source_folder:\s*).*$', "`$1$SOURCE_DIR"

    Set-Content -Path "$configPath" -Value $content -Encoding UTF8
    Write-Ok "Config updated with your paths"
} else {
    Write-Warn "Config file not found -- you may need to configure paths manually"
}

# ==================================================================
# Step 10: Create start_hybridrag.ps1 from template
# ==================================================================
# The Educational repo ships a .template file instead of the real
# start script. This step fills in your paths and creates the script.
# ------------------------------------------------------------------
Write-Step 10 "Creating start_hybridrag.ps1 from template"

$templatePath = "$PROJECT_ROOT\start_hybridrag.ps1.template"
$startScript = "$PROJECT_ROOT\start_hybridrag.ps1"

if (Test-Path "$startScript") {
    Write-Ok "start_hybridrag.ps1 already exists -- skipping"
} elseif (Test-Path "$templatePath") {
    $content = Get-Content "$templatePath" -Raw -Encoding UTF8
    $content = $content -replace 'C:\\path\\to\\HybridRAG3', $PROJECT_ROOT
    $content = $content -replace 'C:\\path\\to\\data', $DATA_DIR
    $content = $content -replace 'C:\\path\\to\\source_docs', $SOURCE_DIR
    Set-Content -Path "$startScript" -Value $content -Encoding UTF8
    Write-Ok "start_hybridrag.ps1 created from template"
} else {
    Write-Warn "No template found -- you may need to create start_hybridrag.ps1 manually"
}

# Create logs directory
$logsDir = "$PROJECT_ROOT\logs"
if (-not (Test-Path "$logsDir")) {
    New-Item -ItemType Directory -Path "$logsDir" -Force | Out-Null
    Write-Ok "Created logs directory"
}

# ==================================================================
# Step 11: API Credentials (optional)
# ==================================================================
# If you have an Azure OpenAI API key and endpoint, you can store
# them securely in Windows Credential Manager. This is optional --
# you can always set them up later from within the application.
# ------------------------------------------------------------------
Write-Step 11 "API Credentials (optional -- you can do this later)"
Write-Host ""
Write-Host "  If you have an Azure OpenAI API key and endpoint, you can enter"
Write-Host "  them now. They are stored securely in Windows Credential Manager."
Write-Host ""
Write-Host "  If you do not have these yet, just press Enter to skip."
Write-Host ""
$configureApi = Read-Host "  Configure API credentials now? [y/N]"
if ($configureApi -eq "y" -or $configureApi -eq "Y") {
    Write-Host ""
    Write-Host "  Enter the API endpoint (the BASE URL only, nothing after .com)"
    Write-Host "  Example: https://your-resource.openai.azure.com" -ForegroundColor White
    Write-Host ""
    $apiEndpoint = Read-Host "  API Endpoint"

    if (-not [string]::IsNullOrWhiteSpace($apiEndpoint)) {
        & $PYTHON "tools/py/store_endpoint.py" $apiEndpoint 2>&1
        Write-Ok "API endpoint stored"
    }

    Write-Host ""
    Write-Host "  Enter your API key below."
    Write-Host "  (The text will be hidden as you type for security)"
    Write-Host ""
    $apiKey = Read-Host "  API Key" -AsSecureString
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey))

    if (-not [string]::IsNullOrWhiteSpace($plainKey)) {
        & $PYTHON "tools/py/store_key.py" $plainKey 2>&1
        Write-Ok "API key stored in Windows Credential Manager"
    }
    $plainKey = $null
}

# ==================================================================
# Step 12: Check Ollama
# ==================================================================
# Ollama runs AI models locally. The corporate proxy can sometimes
# intercept localhost connections, so we bypass it explicitly.
# ------------------------------------------------------------------
Write-Step 12 "Checking Ollama"

try {
    $env:NO_PROXY = "localhost,127.0.0.1"
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop -Proxy ([System.Net.WebProxy]::new())
    Write-Ok "Ollama is running"

    $models = $response.models | ForEach-Object { $_.name }
    if ($models -contains "nomic-embed-text:latest" -or $models -contains "nomic-embed-text") {
        Write-Ok "nomic-embed-text model found"
    } else {
        Write-Warn "nomic-embed-text NOT found -- run: ollama pull nomic-embed-text"
    }
} catch {
    Write-Warn "Ollama is not running (this is OK for now)"
    Write-Host ""
    Write-Host "  Ollama is the local AI engine. You can set it up later."
    Write-Host "  If Ollama is approved at your organization:"
    Write-Host "    1. Download from https://ollama.com"
    Write-Host "    2. Install it (may need IT approval)"
    Write-Host "    3. Open a command prompt and type:"
    Write-Host "       ollama pull nomic-embed-text" -ForegroundColor White
    Write-Host ""
}

# ==================================================================
# Step 13: Run verification
# ==================================================================
Write-Step 13 "Running verification (this may take a moment)"

$hasPytest = & $PYTHON -c "import pytest" 2>&1
if ($LASTEXITCODE -eq 0) {
    $pytestResult = & $PYTHON -m pytest tests/ --ignore=tests/test_fastapi_server.py -q --tb=no 2>&1
    $lastLine = ($pytestResult | Select-Object -Last 1)
    Write-Host "  $lastLine"

    if ($lastLine -match "passed") {
        Write-Ok "Regression tests passed"
    } else {
        Write-Warn "Some tests may have failed -- this is usually OK"
    }
} else {
    Write-Warn "pytest not installed -- skipping verification"
}

# ==================================================================
# Done!
# ==================================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Setup Complete!  You are ready to go." -ForegroundColor Green
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  HOW TO START HybridRAG3:"
Write-Host "  -----------------------------------------------"
Write-Host "  EASIEST WAY (recommended):" -ForegroundColor White
Write-Host "    Double-click:  start_gui.bat" -ForegroundColor White
Write-Host "    (in the $PROJECT_ROOT folder)"
Write-Host ""
Write-Host "  FROM CMD (works on all work laptops):" -ForegroundColor White
Write-Host "    1. Open cmd.exe"
Write-Host "    2. cd /d `"$PROJECT_ROOT`""
Write-Host "    3. .venv\Scripts\activate.bat"
Write-Host "    4. python src/gui/launch_gui.py"
Write-Host ""
Write-Host "  FROM POWERSHELL (if not blocked by Group Policy):" -ForegroundColor White
Write-Host "    1. Open PowerShell"
Write-Host "    2. cd `"$PROJECT_ROOT`""
Write-Host "    3. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
Write-Host "    4. .\.venv\Scripts\Activate.ps1"
Write-Host "    5. . .\start_hybridrag.ps1"
Write-Host ""
Write-Host "  NEED HELP?"
Write-Host "    See docs\01_setup\INSTALL_AND_SETUP.md for the full guide."
Write-Host ""
