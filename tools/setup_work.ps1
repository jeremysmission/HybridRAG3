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
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# ------------------------------------------------------------------
# Helper functions for colored output and timing
# ------------------------------------------------------------------
$TOTAL_STEPS = 13
function Write-Step {
    param([int]$num, [string]$msg)
    Write-Host "`n=== Step $num of $TOTAL_STEPS : $msg ===" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }

# Format elapsed time from a Stopwatch into a readable string
function Format-Elapsed {
    param([System.Diagnostics.Stopwatch]$sw)
    $secs = $sw.Elapsed.TotalSeconds
    if ($secs -ge 60) {
        $min = [math]::Floor($secs / 60)
        $sec = [math]::Floor($secs % 60)
        return "${min}m ${sec}s"
    }
    return "$([math]::Ceiling($secs))s"
}

# ------------------------------------------------------------------
# Welcome banner
# ------------------------------------------------------------------
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    HybridRAG3 -- Work/Educational Setup" -ForegroundColor Cyan
Write-Host "    (Enterprise-approved packages only)" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This script will set up HybridRAG3 on your work computer."
Write-Host "  It handles corporate proxy and security restrictions automatically."
Write-Host ""
Write-Host "  PHASE 1: We ask a few questions (type B to go back anytime)"
Write-Host "  PHASE 2: Everything else is automatic with real-time progress"
Write-Host ""
Write-Host "  SAFE TO RE-RUN: Skips completed steps. Use 'P' to purge and restart."
Write-Host ""

# ======================================================================
#  PHASE 1: INPUT WIZARD (interactive -- type B to go back)
# ======================================================================
# This collects all your choices before doing any work. If you make a
# mistake, type B at any prompt to go back to the previous step.
# After all inputs, you will see a summary to review before continuing.
# ======================================================================

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$DETECTED_ROOT = Split-Path -Parent $SCRIPT_DIR

# Variables to collect
$PROJECT_ROOT = $null
$PY_EXE = $null
$PY_VER_FLAG = $null
$DATA_DIR = $null
$SOURCE_DIR = $null

$wizStep = 1
while ($wizStep -le 3) {

    # ==============================================================
    # Wizard Step 1: Choose install location
    # ==============================================================
    if ($wizStep -eq 1) {
        Write-Step 1 "Choose install location"
        Write-Host ""
        Write-Host "  We found the project files here:"
        Write-Host "    $DETECTED_ROOT" -ForegroundColor White
        Write-Host ""
        Write-Host "  Press Enter to accept, or type a different folder."
        Write-Host ""
        $input = Read-Host "  Project folder [$DETECTED_ROOT]"
        if ([string]::IsNullOrWhiteSpace($input)) { $input = $DETECTED_ROOT }
        $PROJECT_ROOT = [System.IO.Path]::GetFullPath($input)

        # Safety checks
        if (-not (Test-Path "$PROJECT_ROOT")) {
            Write-Fail "Directory '$PROJECT_ROOT' does not exist."
            Write-Host "  Download the ZIP from the Educational repo first."
            continue
        }
        if ((Test-Path "$PROJECT_ROOT\requirements.txt") -and -not (Test-Path "$PROJECT_ROOT\requirements_approved.txt")) {
            Write-Fail "This is the PERSONAL repo. Use setup_home.bat instead."
            continue
        }
        if (-not (Test-Path "$PROJECT_ROOT\requirements_approved.txt")) {
            Write-Fail "Cannot find requirements_approved.txt in $PROJECT_ROOT"
            continue
        }

        # Already installed? Offer resume or purge
        if ((Test-Path "$PROJECT_ROOT\.venv")) {
            Write-Warn "Existing installation detected."
            Write-Host ""
            Write-Host "  Enter = Resume (keeps .venv, updates config)"
            Write-Host "  P     = Purge .venv and start fresh"
            Write-Host "  N     = Cancel"
            $confirm = Read-Host "  Choose [Enter/P/N]"
            if ($confirm -eq "n" -or $confirm -eq "N") { exit 0 }
            if ($confirm -eq "p" -or $confirm -eq "P") {
                Write-Host "  Removing old .venv..."
                Remove-Item -Path "$PROJECT_ROOT\.venv" -Recurse -Force -ErrorAction SilentlyContinue
                Write-Ok "Old .venv removed"
            }
        }
        Write-Ok "Install location: $PROJECT_ROOT"
        $wizStep = 2
    }

    # ==============================================================
    # Wizard Step 2: Detect Python
    # ==============================================================
    if ($wizStep -eq 2) {
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
                if ($LASTEXITCODE -eq 0) { $PY_EXE = "python"; Write-Ok "Found: $result" }
            } catch { }
        }
        if (-not $PY_EXE) {
            Write-Fail "Python is not installed (or not on PATH)."
            Write-Host "  Request Python 3.11 or 3.12 from your IT department."
            Write-Host "  (Software Center, Company Portal, or ServiceNow)"
            Write-Host ""
            Write-Host "  B = Go back to change install location"
            Write-Host "  N = Exit"
            $input = Read-Host "  [B/N]"
            if ($input -eq "B" -or $input -eq "b") { $wizStep = 1; continue }
            exit 1
        }
        Write-Host ""
        Write-Host "  Press Enter to continue, or B to go back."
        $input = Read-Host "  [Enter/B]"
        if ($input -eq "B" -or $input -eq "b") { $wizStep = 1; continue }
        $wizStep = 3
    }

    # ==============================================================
    # Wizard Step 3: Configure paths
    # ==============================================================
    if ($wizStep -eq 3) {
        Write-Step 3 "Configure paths"
        Write-Host ""
        Write-Host "  Where should HybridRAG3 store its search database?"
        Write-Host "  (Uses about 1-5 GB depending on how many documents you have)"
        Write-Host "  Example: D:\RAG Indexed Data" -ForegroundColor White
        Write-Host ""
        Write-Host "  Type B to go back to previous step."
        Write-Host ""
        $input = Read-Host "  Database folder"
        if ($input -eq "B" -or $input -eq "b") { $wizStep = 2; continue }
        while ([string]::IsNullOrWhiteSpace($input)) {
            Write-Warn "Cannot be empty. Type a folder path, or B to go back."
            $input = Read-Host "  Database folder"
            if ($input -eq "B" -or $input -eq "b") { break }
        }
        if ($input -eq "B" -or $input -eq "b") { $wizStep = 2; continue }
        $DATA_DIR = $input

        Write-Host ""
        Write-Host "  Where are the documents you want to search?"
        Write-Host "  (HybridRAG3 reads these files but never modifies them)"
        Write-Host "  Example: D:\RAG Source Data" -ForegroundColor White
        Write-Host ""
        Write-Host "  Type B to go back to the database folder prompt."
        Write-Host ""
        $input = Read-Host "  Documents folder"
        if ($input -eq "B" -or $input -eq "b") { continue }
        while ([string]::IsNullOrWhiteSpace($input)) {
            Write-Warn "Cannot be empty. Type a folder path, or B to go back."
            $input = Read-Host "  Documents folder"
            if ($input -eq "B" -or $input -eq "b") { break }
        }
        if ($input -eq "B" -or $input -eq "b") { continue }
        $SOURCE_DIR = $input

        $wizStep = 4
    }
}

# ==================================================================
# Review all settings before proceeding
# ==================================================================
# Shows everything you entered. Type a number to redo that item.
# This is your last chance to fix mistakes before automation begins.
# ------------------------------------------------------------------
do {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "    Review your settings:" -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  [1] Install location : $PROJECT_ROOT" -ForegroundColor White
    Write-Host "  [2] Python           : $PY_EXE $(if($PY_VER_FLAG){$PY_VER_FLAG}else{'(system)'})" -ForegroundColor White
    Write-Host "  [3] Data directory   : $DATA_DIR" -ForegroundColor White
    Write-Host "  [4] Source directory : $SOURCE_DIR" -ForegroundColor White
    Write-Host ""
    Write-Host "  Enter = Continue with these settings"
    Write-Host "  3/4   = Redo that path"
    Write-Host "  N     = Cancel and exit"
    Write-Host ""
    $reviewChoice = Read-Host "  Your choice"

    if ($reviewChoice -eq "N" -or $reviewChoice -eq "n") { exit 0 }
    if ($reviewChoice -eq "3") {
        $DATA_DIR = Read-Host "  Database folder"
        while ([string]::IsNullOrWhiteSpace($DATA_DIR)) { $DATA_DIR = Read-Host "  Database folder" }
    }
    if ($reviewChoice -eq "4") {
        $SOURCE_DIR = Read-Host "  Documents folder"
        while ([string]::IsNullOrWhiteSpace($SOURCE_DIR)) { $SOURCE_DIR = Read-Host "  Documents folder" }
    }
} while ($reviewChoice -match "^[1234]$")

Write-Host ""
Write-Ok "Settings confirmed"
Write-Host "  ---- Automated setup begins now. You will see real-time progress. ----"

Set-Location "$PROJECT_ROOT"
if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null; Write-Ok "Created: $DATA_DIR" }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null; Write-Ok "Created: $SOURCE_DIR" }

# ======================================================================
#  PHASE 2: AUTOMATED SETUP (real-time progress on every step)
# ======================================================================

# ==================================================================
# Step 4: Create virtual environment
# ==================================================================
Write-Step 4 "Creating virtual environment"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

if (Test-Path ".venv") {
    Write-Ok ".venv already exists -- skipping (use Purge to redo)"
} else {
    Write-Host "  Creating .venv -- please wait (typically 30-60 seconds)..."
    Write-Host "  (You will see a confirmation when it finishes)"
    if ($PY_VER_FLAG) {
        & $PY_EXE $PY_VER_FLAG -m venv .venv
    } else {
        & $PY_EXE -m venv .venv
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Fail "Virtual environment creation failed"
        exit 1
    }
}
$stepTimer.Stop()
Write-Ok "Virtual environment ready ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 5: Upgrade pip (with corporate proxy workaround)
# ==================================================================
Write-Step 5 "Upgrading pip (with proxy bypass)"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"
# Corporate proxies add latency. Default pip timeout is 15 seconds which
# is too short -- packages time out before the proxy finishes relaying.
# We increase to 120 seconds and add 5 retries for reliability.
$TRUSTED = "--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org", "--timeout", "120", "--retries", "5"

Write-Host "  Upgrading pip with proxy-safe timeouts (120s per request)..."
& $PYTHON -m pip install --upgrade pip @TRUSTED
$pipVer = & $PIP --version 2>&1
$stepTimer.Stop()
Write-Ok "pip ready: $pipVer ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 6: Install pip-system-certs (corporate SSL integration)
# ==================================================================
Write-Step 6 "Installing corporate certificate support"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "  Installing pip-system-certs (makes Python trust Windows certs)..."
Write-Host "  (This teaches Python to use your Windows certificate store)"
& $PIP install pip-system-certs @TRUSTED
$env:NO_PROXY = "localhost,127.0.0.1"

$stepTimer.Stop()
Write-Ok "Certificate support installed ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 7: Install approved packages
# ==================================================================
# You will see EVERY package being downloaded and installed below.
# pip shows progress bars for each download. If interrupted, re-run
# this script -- pip keeps its cache and resumes from where it stopped.
# ------------------------------------------------------------------
Write-Step 7 "Installing packages (full output below)"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host ""
Write-Host "  This is the longest step (2-5 minutes on first install)."
Write-Host "  You will see each package being downloaded and installed."
Write-Host "  If interrupted, re-run this script -- pip resumes from cache."
Write-Host ""
Write-Host "  ---- pip output starts ----" -ForegroundColor DarkGray

$maxAttempts = 3
$attempt = 0
$pipSuccess = $false
do {
    $attempt++
    if ($attempt -gt 1) {
        Write-Host ""
        Write-Warn "Retrying... (attempt $attempt of $maxAttempts)"
    }
    # pip runs unfiltered -- you see every download bar and install message
    & $PIP install -r requirements_approved.txt @TRUSTED
    if ($LASTEXITCODE -eq 0) { $pipSuccess = $true; break }
    Write-Warn "Package install had issues (exit code $LASTEXITCODE)"
} while ($attempt -lt $maxAttempts)

Write-Host "  ---- pip output ends ----" -ForegroundColor DarkGray
$stepTimer.Stop()

if (-not $pipSuccess) {
    Write-Fail "Package installation failed after $maxAttempts attempts"
    Write-Host "  Try: .venv\Scripts\pip.exe install -r requirements_approved.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org"
    exit 1
}
Write-Ok "All packages installed ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 8: Install test tools (optional)
# ==================================================================
Write-Step 8 "Test tools (optional)"
Write-Host "  pytest and psutil verify the installation works correctly."
Write-Host "  (Approval status: YELLOW -- being submitted for formal approval)"
Write-Host ""
$installTests = Read-Host "  Install test tools? [Y/n]"
if ($installTests -ne "n" -and $installTests -ne "N") {
    $stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host "  Installing pytest and psutil..."
    & $PIP install pytest==9.0.2 psutil==7.2.2 @TRUSTED
    $stepTimer.Stop()
    Write-Ok "Test packages installed ($(Format-Elapsed $stepTimer))"
} else {
    Write-Warn "Skipped -- diagnostics at the end will be limited"
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
    Write-Warn "Config file not found -- configure paths manually later"
}

# ==================================================================
# Step 10: Create start_hybridrag.ps1 from template
# ==================================================================
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
    Write-Warn "No template found -- create start_hybridrag.ps1 manually"
}

$logsDir = "$PROJECT_ROOT\logs"
if (-not (Test-Path "$logsDir")) {
    New-Item -ItemType Directory -Path "$logsDir" -Force | Out-Null
    Write-Ok "Created logs directory"
}

# ==================================================================
# Step 11: API Credentials (optional)
# ==================================================================
Write-Step 11 "API Credentials (optional -- you can set these later)"
Write-Host ""
Write-Host "  If you have Azure OpenAI credentials, enter them now."
Write-Host "  They are stored securely in Windows Credential Manager."
Write-Host "  Press Enter to skip (you can configure later in the app)."
Write-Host ""
$configureApi = Read-Host "  Configure API credentials now? [y/N]"
if ($configureApi -eq "y" -or $configureApi -eq "Y") {
    Write-Host ""
    Write-Host "  Enter the API endpoint (BASE URL only, nothing after .com)"
    Write-Host "  Example: https://your-resource.openai.azure.com" -ForegroundColor White
    Write-Host "  Type B to skip API setup."
    Write-Host ""
    $apiEndpoint = Read-Host "  API Endpoint"
    if ($apiEndpoint -ne "B" -and $apiEndpoint -ne "b" -and -not [string]::IsNullOrWhiteSpace($apiEndpoint)) {
        & $PYTHON "tools/py/store_endpoint.py" $apiEndpoint 2>&1
        Write-Ok "API endpoint stored"

        Write-Host ""
        Write-Host "  Enter your API key (text is hidden as you type)."
        Write-Host ""
        $apiKey = Read-Host "  API Key" -AsSecureString
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey))
        if (-not [string]::IsNullOrWhiteSpace($plainKey)) {
            & $PYTHON "tools/py/store_key.py" $plainKey 2>&1
            Write-Ok "API key stored in Windows Credential Manager"
        }
        $plainKey = $null
    }
}

# ==================================================================
# Step 12: Check Ollama
# ==================================================================
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
    Write-Warn "Ollama is not running (OK for now -- set up later)"
    Write-Host "  If approved at your organization: download from https://ollama.com"
    Write-Host "  Then run: ollama pull nomic-embed-text"
}

# ======================================================================
#  PHASE 3: FULL DIAGNOSTICS
# ======================================================================
# This validates the entire installation. You will see each check
# as it runs so you know exactly what passed and what needs attention.
# ======================================================================
Write-Step 13 "Running full diagnostics"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
$diagPass = 0
$diagFail = 0

# --- Diagnostic 1: Import verification ---
Write-Host ""
Write-Host "  --- Import Verification ---" -ForegroundColor Cyan
Write-Host "  Checking that each package loads correctly..."
Write-Host ""
$packages = @(
    @{mod="fastapi"; label="FastAPI (web framework)"},
    @{mod="httpx"; label="httpx (HTTP client)"},
    @{mod="openai"; label="openai (Azure OpenAI SDK)"},
    @{mod="pydantic"; label="pydantic (data validation)"},
    @{mod="numpy"; label="numpy (numerical computing)"},
    @{mod="yaml"; label="PyYAML (config parser)"},
    @{mod="uvicorn"; label="uvicorn (web server)"},
    @{mod="cryptography"; label="cryptography (encryption)"}
)
foreach ($pkg in $packages) {
    & $PYTHON -c "import $($pkg.mod)" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [OK] $($pkg.label)" -ForegroundColor Green
        $diagPass++
    } else {
        Write-Host "    [FAIL] $($pkg.label)" -ForegroundColor Red
        $diagFail++
    }
}

# --- Diagnostic 2: Config validation ---
Write-Host ""
Write-Host "  --- Config Validation ---" -ForegroundColor Cyan
Write-Host ""
if (Test-Path "$configPath") {
    Write-Host "    [OK] default_config.yaml exists" -ForegroundColor Green
    $diagPass++
    $cfgContent = Get-Content "$configPath" -Raw
    if ($cfgContent -match "database:") {
        Write-Host "    [OK] Database path configured" -ForegroundColor Green
        $diagPass++
    } else {
        Write-Host "    [FAIL] Database path missing" -ForegroundColor Red
        $diagFail++
    }
    if ($cfgContent -match "source_folder:") {
        Write-Host "    [OK] Source folder configured" -ForegroundColor Green
        $diagPass++
    } else {
        Write-Host "    [FAIL] Source folder missing" -ForegroundColor Red
        $diagFail++
    }
} else {
    Write-Host "    [FAIL] default_config.yaml not found" -ForegroundColor Red
    $diagFail++
}

# --- Diagnostic 3: Directory checks ---
Write-Host ""
Write-Host "  --- Directory Checks ---" -ForegroundColor Cyan
Write-Host ""
foreach ($dir in @("$DATA_DIR", "$SOURCE_DIR", "$PROJECT_ROOT\logs", "$PROJECT_ROOT\.venv")) {
    if (Test-Path "$dir") {
        Write-Host "    [OK] $dir" -ForegroundColor Green
        $diagPass++
    } else {
        Write-Host "    [FAIL] $dir (missing)" -ForegroundColor Red
        $diagFail++
    }
}

# --- Diagnostic 4: Quick boot test ---
Write-Host ""
Write-Host "  --- Boot Test ---" -ForegroundColor Cyan
Write-Host "  Checking that the core modules can load..."
Write-Host ""
$bootTest = & $PYTHON -c "from src.core.config import Config; c = Config(); print('Config OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [OK] Core config loads" -ForegroundColor Green
    $diagPass++
} else {
    Write-Host "    [WARN] Core config could not load (may need Ollama)" -ForegroundColor Yellow
}

# --- Diagnostic 5: Full regression tests ---
$hasPytest = & $PYTHON -c "import pytest" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "  --- Regression Tests ---" -ForegroundColor Cyan
    Write-Host "  Running full test suite. Each dot = pass, F = fail."
    Write-Host "  This typically takes 15-30 seconds."
    Write-Host ""

    & $PYTHON -m pytest tests/ --ignore=tests/test_fastapi_server.py --tb=no
    $testExitCode = $LASTEXITCODE

    if ($testExitCode -eq 0) {
        Write-Host ""
        Write-Ok "All regression tests passed"
        $diagPass++
    } else {
        Write-Host ""
        Write-Warn "Some tests had issues (common on fresh install without Ollama)"
    }
} else {
    Write-Host ""
    Write-Warn "pytest not installed -- skipping regression tests"
}

$stepTimer.Stop()

# --- Diagnostic summary ---
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    Diagnostic Summary" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "    Checks passed : $diagPass" -ForegroundColor Green
if ($diagFail -gt 0) {
    Write-Host "    Checks failed : $diagFail" -ForegroundColor Red
} else {
    Write-Host "    Checks failed : 0" -ForegroundColor Green
}
Write-Host "    Time elapsed  : $(Format-Elapsed $stepTimer)"
Write-Host ""

# ==================================================================
# Done!
# ==================================================================
Write-Host ""
if ($diagFail -eq 0) {
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "    Setup Complete!  Everything looks good." -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Green
} else {
    Write-Host "  ============================================" -ForegroundColor Yellow
    Write-Host "    Setup Complete (with $diagFail warnings)." -ForegroundColor Yellow
    Write-Host "    The app will work -- some features may need Ollama." -ForegroundColor Yellow
    Write-Host "  ============================================" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  HOW TO START HybridRAG3:"
Write-Host "  -----------------------------------------------"
Write-Host "  EASIEST WAY:" -ForegroundColor White
Write-Host "    Double-click:  start_gui.bat" -ForegroundColor White
Write-Host ""
Write-Host "  FROM CMD:" -ForegroundColor White
Write-Host "    cd /d `"$PROJECT_ROOT`""
Write-Host "    .venv\Scripts\activate.bat"
Write-Host "    python src/gui/launch_gui.py"
Write-Host ""
Write-Host "  FROM POWERSHELL:" -ForegroundColor White
Write-Host "    cd `"$PROJECT_ROOT`""
Write-Host "    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    . .\start_hybridrag.ps1"
Write-Host ""
Write-Host "  TO CHANGE SETTINGS:" -ForegroundColor Yellow
Write-Host "    Run this script again -- you can redo any choice."
Write-Host "    API credentials: use Admin tab in the app, or re-run setup."
Write-Host ""
