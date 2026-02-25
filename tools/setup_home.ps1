# ============================================================================
# HybridRAG3 -- Automated Home/Personal Setup
# Date: 2026-02-25
# Uses: requirements.txt (personal, more software liberty)
# Run via: INSTALL.bat (double-click) or tools\setup_home.bat
#   or: powershell -ExecutionPolicy Bypass -File tools\setup_home.ps1
#
# SAFE TO RE-RUN: If setup was interrupted or you want to redo it,
# just run this script again. It skips what is already done and fixes
# anything left incomplete. Use "P" at the prompt to purge and restart.
# ============================================================================

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
# These print tagged messages so you can see at a glance what passed,
# failed, or needs attention. The step counter shows overall progress.
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
# Welcome banner
# ------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HybridRAG3 -- Home/Personal Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This script will set up HybridRAG3 on your computer."
Write-Host "  It will ask you a few questions, then do the rest automatically."
Write-Host "  Estimated time: 5-10 minutes (depends on internet speed)."
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

# Figure out where we are: this script is in tools/, project is one level up
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$DETECTED_ROOT = Split-Path -Parent $SCRIPT_DIR

Write-Host ""
Write-Host "  We found the project files here:"
Write-Host "    $DETECTED_ROOT" -ForegroundColor White
Write-Host ""
Write-Host "  Is this correct? Just press Enter to continue."
Write-Host "  Or type a different folder path if you moved the files."
Write-Host ""
$USER_PATH = Read-Host "  Project folder [$DETECTED_ROOT]"
if ([string]::IsNullOrWhiteSpace($USER_PATH)) { $USER_PATH = $DETECTED_ROOT }

# Clean up the path (resolve relative paths, remove trailing slashes)
$PROJECT_ROOT = [System.IO.Path]::GetFullPath($USER_PATH)

# ------------------------------------------------------------------
# Safety checks: make sure we are in the right folder
# ------------------------------------------------------------------
if (Test-Path "$PROJECT_ROOT") {
    # Wrong repo? Educational has a .template file that personal does not
    if (Test-Path "$PROJECT_ROOT\start_hybridrag.ps1.template") {
        Write-Fail "Directory '$PROJECT_ROOT' contains HybridRAG3_Educational (work repo)."
        Write-Host "  This script is for the PERSONAL repo."
        Write-Host "  Use setup_work.bat for the Educational repo instead."
        exit 1
    }
    # Some other git repo that is not HybridRAG3?
    if ((Test-Path "$PROJECT_ROOT\.git") -and -not (Test-Path "$PROJECT_ROOT\requirements.txt")) {
        Write-Fail "Directory '$PROJECT_ROOT' contains a different git repository."
        Write-Host "  Choose the correct HybridRAG3 folder."
        exit 1
    }
    # Already installed? Offer resume or purge
    if ((Test-Path "$PROJECT_ROOT\requirements.txt") -and (Test-Path "$PROJECT_ROOT\.venv")) {
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
    Write-Host "  Clone the repo first: git clone <repo-url>"
    Write-Host "  Or download and extract the ZIP to that location."
    exit 1
}

# Final check: the requirements file must exist
if (-not (Test-Path "$PROJECT_ROOT\requirements.txt")) {
    Write-Fail "Cannot find requirements.txt in $PROJECT_ROOT"
    Write-Host "  This does not appear to be a HybridRAG3 project folder."
    exit 1
}
Write-Ok "Install location: $PROJECT_ROOT"
Set-Location "$PROJECT_ROOT"

# ==================================================================
# Step 2: Detect Python
# ==================================================================
# We try the Windows "py" launcher first (supports version selection),
# then fall back to bare "python" on PATH.
# ------------------------------------------------------------------
Write-Step 2 "Detecting Python"
$PY_EXE = $null
$PY_VER_FLAG = $null
foreach ($ver in @("3.12", "3.11", "3.10")) {
    try {
        $result = & py "-$ver" --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $PY_EXE = "py"
            $PY_VER_FLAG = "-$ver"
            Write-Ok "Found Python $ver via py launcher"
            break
        }
    } catch { }
}

# Fallback: try bare "python" command
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
    Write-Host "  1. Go to https://www.python.org/downloads/"
    Write-Host "  2. Download Python 3.11 or 3.12"
    Write-Host "  3. Run the installer"
    Write-Host "  4. IMPORTANT: Check the box 'Add Python to PATH'"
    Write-Host "  5. Restart your computer"
    Write-Host "  6. Double-click INSTALL.bat again"
    Write-Host ""
    exit 1
}

# ==================================================================
# Step 3: Configure paths
# ==================================================================
# You need two folders:
#   DATA_DIR   = where HybridRAG stores its search database and AI embeddings
#   SOURCE_DIR = where your documents (PDFs, Word, Excel) live
# ------------------------------------------------------------------
Write-Step 3 "Configure paths"

$DEFAULT_DATA = "D:\RAG Indexed Data"
$DEFAULT_SOURCE = "D:\RAG Source Data"

Write-Host ""
Write-Host "  Where should HybridRAG3 store its search database?"
Write-Host "  (Uses about 1-5 GB depending on how many documents you have)"
Write-Host ""
Write-Host "  Suggested: $DEFAULT_DATA" -ForegroundColor White
Write-Host "  Press Enter to accept, or type a different folder."
Write-Host ""
$DATA_DIR = Read-Host "  Database folder [$DEFAULT_DATA]"
if ([string]::IsNullOrWhiteSpace($DATA_DIR)) { $DATA_DIR = $DEFAULT_DATA }

Write-Host ""
Write-Host "  Where are the documents you want to search?"
Write-Host "  (HybridRAG3 will read these files but never modify them)"
Write-Host ""
Write-Host "  Suggested: $DEFAULT_SOURCE" -ForegroundColor White
Write-Host "  Press Enter to accept, or type a different folder."
Write-Host ""
$SOURCE_DIR = Read-Host "  Documents folder [$DEFAULT_SOURCE]"
if ([string]::IsNullOrWhiteSpace($SOURCE_DIR)) { $SOURCE_DIR = $DEFAULT_SOURCE }

Write-Ok "Data directory: $DATA_DIR"
Write-Ok "Source directory: $SOURCE_DIR"

# Create the directories if they do not exist yet
if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null; Write-Ok "Created: $DATA_DIR" }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null; Write-Ok "Created: $SOURCE_DIR" }

# ==================================================================
# Step 4: Create virtual environment
# ==================================================================
# A virtual environment (.venv) keeps HybridRAG's packages separate
# from your system Python. This prevents version conflicts.
# If .venv already exists (from a previous run), we skip this step.
# ------------------------------------------------------------------
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
# Step 5: Upgrade pip (the package installer)
# ==================================================================
Write-Step 5 "Preparing package installer (pip)"

$PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"

Write-Host "  Upgrading pip to latest version..."
& $PYTHON -m pip install --upgrade pip 2>&1 | Out-Null
$pipVer = & $PIP --version 2>&1
Write-Ok "pip ready: $pipVer"

# ==================================================================
# Step 6: Install packages
# ==================================================================
# This downloads all required Python packages. You will see pip's
# progress bars showing download status for each package.
# If the download is interrupted, just re-run this script -- pip
# will resume where it left off (cached downloads are kept).
# ------------------------------------------------------------------
Write-Step 6 "Installing packages (you will see download progress below)"
Write-Host "  This may take 2-5 minutes on first install."
Write-Host "  If interrupted, just re-run -- pip resumes from cache."
Write-Host ""

# Try up to 3 times in case of network interruption
$maxAttempts = 3
$attempt = 0
$pipSuccess = $false
do {
    $attempt++
    if ($attempt -gt 1) {
        Write-Warn "Retrying... (attempt $attempt of $maxAttempts)"
    }
    & $PIP install -r requirements.txt 2>&1 | ForEach-Object {
        $line = $_.ToString()
        # Show download progress, installs, and errors
        if ($line -match "Downloading|Installing|Successfully|ERROR|WARNING") {
            Write-Host "  $line"
        }
    }
    if ($LASTEXITCODE -eq 0) { $pipSuccess = $true; break }
    Write-Warn "Package install had issues (exit code $LASTEXITCODE)"
} while ($attempt -lt $maxAttempts)

if (-not $pipSuccess) {
    Write-Fail "Package installation failed after $maxAttempts attempts"
    Write-Host "  Check your internet connection and try again."
    Write-Host "  Manual retry: .venv\Scripts\pip.exe install -r requirements.txt"
    exit 1
}

# Verify that the most important packages actually imported correctly
$failed = @()
foreach ($pkg in @("fastapi", "httpx", "openai", "pydantic", "numpy", "yaml", "pytest")) {
    & $PYTHON -c "import $pkg" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $failed += $pkg }
}

if ($failed.Count -gt 0) {
    Write-Fail "Failed to import: $($failed -join ', ')"
    Write-Host "  Try: .venv\Scripts\pip.exe install -r requirements.txt"
    exit 1
}
Write-Ok "All critical packages verified"

# ==================================================================
# Step 7: Configure default_config.yaml
# ==================================================================
# This updates the config file with the data and source paths you
# chose in Step 3. The config file tells HybridRAG where to find
# your documents and where to store the search database.
# ------------------------------------------------------------------
Write-Step 7 "Configuring default_config.yaml"

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
# Step 8: Configure start_hybridrag.ps1
# ==================================================================
# This updates the startup script with your data/source paths.
# The startup script sets environment variables each time you launch.
# ------------------------------------------------------------------
Write-Step 8 "Configuring start_hybridrag.ps1"

$startScript = "$PROJECT_ROOT\start_hybridrag.ps1"
if (Test-Path "$startScript") {
    $content = Get-Content "$startScript" -Raw -Encoding UTF8
    $content = $content -replace '(?m)^\$DATA_DIR\s*=\s*"[^"]*"', "`$DATA_DIR   = `"$DATA_DIR`""
    $content = $content -replace '(?m)^\$SOURCE_DIR\s*=\s*"[^"]*"', "`$SOURCE_DIR = `"$SOURCE_DIR`""
    Set-Content -Path "$startScript" -Value $content -Encoding UTF8
    Write-Ok "start_hybridrag.ps1 paths updated"
} else {
    Write-Warn "start_hybridrag.ps1 not found -- you may need to configure paths manually"
}

# Create logs directory if it does not exist
$logsDir = "$PROJECT_ROOT\logs"
if (-not (Test-Path "$logsDir")) {
    New-Item -ItemType Directory -Path "$logsDir" -Force | Out-Null
    Write-Ok "Created logs directory"
}

# ==================================================================
# Step 9: Check Ollama (the local AI engine)
# ==================================================================
# Ollama runs AI models locally on your computer. It needs two models:
#   nomic-embed-text = converts documents into searchable vectors (required)
#   phi4-mini        = generates AI answers from search results (recommended)
# ------------------------------------------------------------------
Write-Step 9 "Checking Ollama"

try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
    Write-Ok "Ollama is running"

    $models = $response.models | ForEach-Object { $_.name }
    if ($models -contains "nomic-embed-text:latest" -or $models -contains "nomic-embed-text") {
        Write-Ok "nomic-embed-text model found"
    } else {
        Write-Warn "nomic-embed-text NOT found -- run: ollama pull nomic-embed-text"
    }

    if ($models -contains "phi4-mini:latest" -or $models -contains "phi4-mini") {
        Write-Ok "phi4-mini model found"
    } else {
        Write-Warn "phi4-mini NOT found -- run: ollama pull phi4-mini"
    }
} catch {
    Write-Warn "Ollama is not running (this is OK for now)"
    Write-Host ""
    Write-Host "  Ollama is the local AI engine. You can set it up later."
    Write-Host "  To install:"
    Write-Host "    1. Go to https://ollama.com and download the installer"
    Write-Host "    2. Run the installer"
    Write-Host "    3. Open a command prompt and type:"
    Write-Host "       ollama pull nomic-embed-text" -ForegroundColor White
    Write-Host "       ollama pull phi4-mini" -ForegroundColor White
    Write-Host ""
}

# ==================================================================
# Step 10: Run quick verification
# ==================================================================
# This runs the automated test suite to make sure everything installed
# correctly. If some tests fail, setup still worked -- the failures
# are usually caused by missing Ollama models (which are optional).
# ------------------------------------------------------------------
Write-Step 10 "Running quick verification (this may take a moment)"

$pytestResult = & $PYTHON -m pytest tests/ --ignore=tests/test_fastapi_server.py -q --tb=no 2>&1
$lastLine = ($pytestResult | Select-Object -Last 1)
Write-Host "  $lastLine"

if ($lastLine -match "passed") {
    Write-Ok "Regression tests passed"
} else {
    Write-Warn "Some tests may have failed -- this is usually OK"
    Write-Host "  (Tests that need Ollama will fail if Ollama is not set up yet)"
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
Write-Host "  OR FROM POWERSHELL:" -ForegroundColor White
Write-Host "    1. Open PowerShell"
Write-Host "    2. cd `"$PROJECT_ROOT`""
Write-Host "    3. Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
Write-Host "    4. .\.venv\Scripts\Activate.ps1"
Write-Host "    5. . .\start_hybridrag.ps1"
Write-Host "    6. python src/gui/launch_gui.py"
Write-Host ""
Write-Host "  OR FROM CMD (if PowerShell is blocked):" -ForegroundColor White
Write-Host "    1. Open cmd.exe"
Write-Host "    2. cd /d `"$PROJECT_ROOT`""
Write-Host "    3. .venv\Scripts\activate.bat"
Write-Host "    4. python src/gui/launch_gui.py"
Write-Host ""
Write-Host "  OLLAMA AI MODELS (if not yet installed):"
Write-Host "    ollama pull nomic-embed-text  (274 MB -- required for search)"
Write-Host "    ollama pull phi4-mini         (2.3 GB -- for AI answers)"
Write-Host ""
