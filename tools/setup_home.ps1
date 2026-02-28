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
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# ------------------------------------------------------------------
# Helper functions for colored output and timing
# ------------------------------------------------------------------
$TOTAL_STEPS = 10
function Write-Step {
    param([int]$num, [string]$msg)
    Write-Host "`n=== Step $num of $TOTAL_STEPS : $msg ===" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Warn { param([string]$msg) Write-Host "  [WARN] $msg" -ForegroundColor Yellow }

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

function Request-Recovery {
    param([string]$StepName, [int]$StepNum, [switch]$DrillDown)
    Write-Host ""
    Write-Host "  Step $StepNum ($StepName) did not complete successfully." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [R] Retry this step"
    if ($DrillDown) {
        Write-Host "  [D] Drill down -- install each package one at a time"
    }
    Write-Host "  [S] Skip this step and continue"
    Write-Host "  [X] Save progress and exit (manual troubleshooting)"
    Write-Host ""
    if ($DrillDown) {
        $choice = Read-Host "  Choose [R/D/S/X]"
    } else {
        $choice = Read-Host "  Choose [R/S/X]"
    }
    return $choice.ToUpper()
}

function Write-ManualResume {
    param([int]$FailedStep, [int]$TotalSteps)
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "  SETUP PAUSED -- Progress saved" -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Completed steps: 1 through $($FailedStep - 1) of $TotalSteps"
    Write-Host "  Failed on step:  $FailedStep"
    Write-Host ""
    Write-Host "  Your .venv and config changes are saved on disk."
    Write-Host "  To troubleshoot and finish manually:" -ForegroundColor White
    Write-Host ""
    Write-Host "    1. Activate the venv:"
    Write-Host "       .venv\Scripts\Activate.ps1"
    Write-Host ""
    Write-Host "    2. Retry the failed package install:"
    Write-Host "       .venv\Scripts\pip.exe install -r requirements.txt"
    Write-Host ""
    Write-Host "    3. Re-run this script to pick up where you left off"
    Write-Host "       (it detects existing .venv and skips completed steps)"
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
}

# ------------------------------------------------------------------
# Welcome banner
# ------------------------------------------------------------------
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    HybridRAG3 -- Home/Personal Setup" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  This script will set up HybridRAG3 on your computer."
Write-Host ""
Write-Host "  PHASE 1: We ask a few questions (type B to go back anytime)"
Write-Host "  PHASE 2: Everything else is automatic with real-time progress"
Write-Host ""
Write-Host "  SAFE TO RE-RUN: Skips completed steps. Use 'P' to purge and restart."
Write-Host ""

# ======================================================================
#  PHASE 1: INPUT WIZARD (interactive -- type B to go back)
# ======================================================================

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$DETECTED_ROOT = Split-Path -Parent $SCRIPT_DIR
$DEFAULT_DATA = Join-Path (Split-Path -Parent $DETECTED_ROOT) "RAG Indexed Data"
$DEFAULT_SOURCE = Join-Path (Split-Path -Parent $DETECTED_ROOT) "RAG Source Data"

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

        if (-not (Test-Path "$PROJECT_ROOT")) {
            Write-Fail "Directory '$PROJECT_ROOT' does not exist."
            Write-Host "  Clone the repo or extract the ZIP first."
            continue
        }
        if (Test-Path "$PROJECT_ROOT\start_hybridrag.ps1.template") {
            Write-Fail "This is the WORK/EDUCATIONAL repo. Use setup_work.bat instead."
            continue
        }
        if (-not (Test-Path "$PROJECT_ROOT\requirements.txt")) {
            Write-Fail "Cannot find requirements.txt in $PROJECT_ROOT"
            continue
        }

        if ((Test-Path "$PROJECT_ROOT\.venv")) {
            Write-Warn "Existing installation detected."
            Write-Host "  Enter = Resume   P = Purge .venv   N = Cancel"
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
        if (-not $PY_EXE) {
            try {
                $result = & python --version 2>&1
                if ($LASTEXITCODE -eq 0) { $PY_EXE = "python"; Write-Ok "Found: $result" }
            } catch { }
        }
        if (-not $PY_EXE) {
            Write-Fail "Python is not installed."
            Write-Host "  1. Go to https://www.python.org/downloads/"
            Write-Host "  2. Download Python 3.12"
            Write-Host "  3. IMPORTANT: Check 'Add Python to PATH'"
            Write-Host "  4. Restart computer, then re-run INSTALL.bat"
            Write-Host ""
            Write-Host "  B = Go back   N = Exit"
            $input = Read-Host "  [B/N]"
            if ($input -eq "B" -or $input -eq "b") { $wizStep = 1; continue }
            exit 1
        }
        Write-Host "  Press Enter to continue, or B to go back."
        $input = Read-Host "  [Enter/B]"
        if ($input -eq "B" -or $input -eq "b") { $wizStep = 1; continue }
        $wizStep = 3
    }

    # ==============================================================
    # Wizard Step 3: Configure paths
    # ==============================================================
    # HybridRAG3 needs two folders:
    #   Index folder = where the search database and AI embeddings are stored
    #   Source folder = where your documents (PDFs, Word, Excel) live
    #
    # Option C creates both inside a "data" folder next to the project,
    # so everything stays organized in one place.
    # ==============================================================
    if ($wizStep -eq 3) {
        Write-Step 3 "Configure paths"
        Write-Host ""
        Write-Host "  HybridRAG3 needs two folders: one for its search database"
        Write-Host "  and one where your documents live."
        Write-Host ""
        Write-Host "  OPTIONS:" -ForegroundColor White
        Write-Host "    C = Create them for me (recommended)" -ForegroundColor Green
        Write-Host "        Creates: $PROJECT_ROOT\data\index"
        Write-Host "        Creates: $PROJECT_ROOT\data\source"
        Write-Host "    D = Use default paths ($DEFAULT_DATA / $DEFAULT_SOURCE)"
        Write-Host "    M = I will enter my own folder paths"
        Write-Host "    B = Go back to previous step"
        Write-Host ""
        $pathChoice = Read-Host "  Choose [C/D/M/B]"

        if ($pathChoice -eq "B" -or $pathChoice -eq "b") { $wizStep = 2; continue }

        if ($pathChoice -eq "D" -or $pathChoice -eq "d") {
            # Use the default paths
            $DATA_DIR = $DEFAULT_DATA
            $SOURCE_DIR = $DEFAULT_SOURCE
            Write-Ok "Using defaults: $DEFAULT_DATA / $DEFAULT_SOURCE"
        } elseif ($pathChoice -eq "M" -or $pathChoice -eq "m") {
            # Manual path entry
            Write-Host ""
            Write-Host "  Where should HybridRAG3 store its search database?"
            Write-Host "  Suggested: $DEFAULT_DATA" -ForegroundColor White
            Write-Host ""
            $input = Read-Host "  Database folder [$DEFAULT_DATA]"
            if ($input -eq "B" -or $input -eq "b") { continue }
            if ([string]::IsNullOrWhiteSpace($input)) { $input = $DEFAULT_DATA }
            $DATA_DIR = $input

            Write-Host ""
            Write-Host "  Where are the documents you want to search?"
            Write-Host "  Suggested: $DEFAULT_SOURCE" -ForegroundColor White
            Write-Host ""
            $input = Read-Host "  Documents folder [$DEFAULT_SOURCE]"
            if ($input -eq "B" -or $input -eq "b") { continue }
            if ([string]::IsNullOrWhiteSpace($input)) { $input = $DEFAULT_SOURCE }
            $SOURCE_DIR = $input
        } else {
            # Auto-create data/index and data/source inside project root
            $DATA_DIR = "$PROJECT_ROOT\data\index"
            $SOURCE_DIR = "$PROJECT_ROOT\data\source"
            New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null
            New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null
            Write-Ok "Created: $DATA_DIR"
            Write-Ok "Created: $SOURCE_DIR"
            Write-Host ""
            Write-Host "  Put your documents (PDFs, Word, Excel, etc.) into:"
            Write-Host "    $SOURCE_DIR" -ForegroundColor White
        }

        $wizStep = 4
    }
}

# ==================================================================
# Review settings
# ==================================================================
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
    Write-Host "  Enter = Continue   3/4 = Redo that path   N = Cancel"
    Write-Host ""
    $reviewChoice = Read-Host "  Your choice"
    if ($reviewChoice -eq "N" -or $reviewChoice -eq "n") { exit 0 }
    if ($reviewChoice -eq "3") {
        $DATA_DIR = Read-Host "  Database folder [$DEFAULT_DATA]"
        if ([string]::IsNullOrWhiteSpace($DATA_DIR)) { $DATA_DIR = $DEFAULT_DATA }
    }
    if ($reviewChoice -eq "4") {
        $SOURCE_DIR = Read-Host "  Documents folder [$DEFAULT_SOURCE]"
        if ([string]::IsNullOrWhiteSpace($SOURCE_DIR)) { $SOURCE_DIR = $DEFAULT_SOURCE }
    }
} while ($reviewChoice -match "^[1234]$")

Write-Host ""
Write-Ok "Settings confirmed"
Write-Host "  ---- Automated setup begins now. You will see real-time progress. ----"

# PS 5.1 converts native command stderr (pip WARNINGs) to ErrorRecords.
# With 'Stop', these become terminating errors that crash the script before
# $LASTEXITCODE can be checked. Phase 2 pip/python calls already have their
# own error handling (while loops, $LASTEXITCODE, try/catch), so 'Continue'
# is correct here. Cmdlets inside try/catch use explicit -ErrorAction Stop.
$ErrorActionPreference = 'Continue'

Set-Location "$PROJECT_ROOT"
if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null; Write-Ok "Created: $DATA_DIR" }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null; Write-Ok "Created: $SOURCE_DIR" }

# ======================================================================
#  PHASE 2: AUTOMATED SETUP
# ======================================================================

# ==================================================================
# Step 4: Create virtual environment
# ==================================================================
Write-Step 4 "Creating virtual environment"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

if (Test-Path ".venv") {
    Write-Ok ".venv already exists -- skipping (use Purge to redo)"
} else {
    $stepDone = $false
    while (-not $stepDone) {
        Write-Host "  Creating .venv -- please wait (typically 30-60 seconds)..."
        Write-Host "  (You will see a confirmation when it finishes)"
        if ($PY_VER_FLAG) {
            & $PY_EXE $PY_VER_FLAG -m venv .venv
        } else {
            & $PY_EXE -m venv .venv
        }
        if (Test-Path ".venv\Scripts\python.exe") {
            $stepDone = $true
        } else {
            Write-Fail "Virtual environment creation failed"
            $choice = Request-Recovery "Creating venv" 4
            switch ($choice) {
                "R" { continue }
                "S" { Write-Warn "Skipped venv creation"; $stepDone = $true }
                "X" { Write-ManualResume 4 $TOTAL_STEPS; exit 0 }
                default { continue }
            }
        }
    }
}
$stepTimer.Stop()
Write-Ok "Virtual environment ready ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 5: Upgrade pip
# ==================================================================
Write-Step 5 "Upgrading pip"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"

$stepDone = $false
while (-not $stepDone) {
    Write-Host "  Upgrading pip to latest version..."
    & $PYTHON -m pip install --upgrade pip
    if ($LASTEXITCODE -eq 0) {
        $stepDone = $true
    } else {
        $choice = Request-Recovery "Upgrading pip" 5
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped pip upgrade"; $stepDone = $true }
            "X" { Write-ManualResume 5 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}
$pipVer = & $PIP --version 2>&1
$stepTimer.Stop()
Write-Ok "pip ready: $pipVer ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 6: Install packages
# ==================================================================
# You will see EVERY package being downloaded and installed in real
# time. pip shows download progress bars for each package.
# If interrupted, re-run -- pip resumes from its download cache.
# ------------------------------------------------------------------
Write-Step 6 "Installing packages (full output below)"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host ""
Write-Host "  This is the longest step (2-5 minutes on first install)."
Write-Host "  You will see each package being downloaded and installed."
Write-Host "  If interrupted, re-run -- pip resumes from cache."
Write-Host ""
Write-Host "  ---- pip output starts ----" -ForegroundColor DarkGray

$stepDone = $false
while (-not $stepDone) {
    $maxAttempts = 3
    $attempt = 0
    $pipSuccess = $false
    do {
        $attempt++
        if ($attempt -gt 1) {
            Write-Host ""
            Write-Warn "Retrying... (attempt $attempt of $maxAttempts)"
        }
        & $PIP install -r requirements.txt
        if ($LASTEXITCODE -eq 0) { $pipSuccess = $true; break }
        Write-Warn "Package install had issues (exit code $LASTEXITCODE)"
    } while ($attempt -lt $maxAttempts)

    if ($pipSuccess) {
        $stepDone = $true
    } else {
        Write-Fail "Package installation failed after $maxAttempts attempts"
        $choice = Request-Recovery "Installing packages" 6 -DrillDown
        switch ($choice) {
            "R" { continue }
            "D" {
                Write-Host ""
                Write-Host "  --- Drill-Down: Installing packages individually ---" -ForegroundColor Cyan
                Write-Host ""
                $reqLines = Get-Content "$PROJECT_ROOT\requirements.txt" | Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' }
                foreach ($reqLine in $reqLines) {
                    $pkgDone = $false
                    while (-not $pkgDone) {
                        Write-Host "    Installing: $reqLine" -ForegroundColor White
                        & $PIP install $reqLine 2>&1
                        if ($LASTEXITCODE -eq 0) {
                            Write-Ok "$reqLine"
                            $pkgDone = $true
                        } else {
                            Write-Fail "$reqLine"
                            Write-Host ""
                            Write-Host "  [R] Retry   [S] Skip   [X] Exit"
                            $pkgChoice = Read-Host "  Choose [R/S/X]"
                            switch ($pkgChoice.ToUpper()) {
                                "R" { continue }
                                "S" { Write-Warn "Skipped $reqLine"; $pkgDone = $true }
                                "X" { Write-ManualResume 6 $TOTAL_STEPS; exit 0 }
                                default { continue }
                            }
                        }
                    }
                }
                $stepDone = $true
            }
            "S" { Write-Warn "Skipped package install"; $stepDone = $true }
            "X" { Write-ManualResume 6 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

Write-Host "  ---- pip output ends ----" -ForegroundColor DarkGray
$stepTimer.Stop()
Write-Ok "All packages installed ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 7: Configure default_config.yaml
# ==================================================================
Write-Step 7 "Configuring default_config.yaml"

$configPath = "$PROJECT_ROOT\config\default_config.yaml"
$stepDone = $false
while (-not $stepDone) {
    try {
        if (Test-Path "$configPath") {
            $content = Get-Content "$configPath" -Raw -Encoding UTF8 -ErrorAction Stop
            $dbPath = "$DATA_DIR\hybridrag.sqlite3"
            $embPath = "$DATA_DIR\_embeddings"
            # BUG 3 fix: escape $ in paths so -replace does not treat them as backreferences
            $safeDbPath = $dbPath.Replace('$', '$$')
            $safeEmbPath = $embPath.Replace('$', '$$')
            $safeSrcDir = $SOURCE_DIR.Replace('$', '$$')
            $content = $content -replace '(?m)^(\s*database:\s*).*$', "`$1$safeDbPath"
            $content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', "`$1$safeEmbPath"
            $content = $content -replace '(?m)^(\s*source_folder:\s*).*$', "`$1$safeSrcDir"
            # YAML is consumed by Python -- must NOT have BOM (Set-Content adds BOM in PS 5.1)
            [System.IO.File]::WriteAllText($configPath, $content)
            Write-Ok "Config updated with your paths"
        } else {
            Write-Warn "Config file not found -- configure paths manually"
        }
        $stepDone = $true
    } catch {
        Write-Fail "Config update failed: $_"
        $choice = Request-Recovery "Config YAML" 7
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped config update"; $stepDone = $true }
            "X" { Write-ManualResume 7 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

# ==================================================================
# Step 8: Configure start_hybridrag.ps1
# ==================================================================
Write-Step 8 "Configuring start_hybridrag.ps1"

$startScript = "$PROJECT_ROOT\start_hybridrag.ps1"
$stepDone = $false
while (-not $stepDone) {
    try {
        if (Test-Path "$startScript") {
            $content = Get-Content "$startScript" -Raw -Encoding UTF8 -ErrorAction Stop
            $content = $content -replace '(?m)^\$DATA_DIR\s*=\s*"[^"]*"', "`$DATA_DIR   = `"$DATA_DIR`""
            $content = $content -replace '(?m)^\$SOURCE_DIR\s*=\s*"[^"]*"', "`$SOURCE_DIR = `"$SOURCE_DIR`""
            Set-Content -Path "$startScript" -Value $content -Encoding UTF8 -ErrorAction Stop
            Write-Ok "start_hybridrag.ps1 paths updated"
        } else {
            Write-Warn "start_hybridrag.ps1 not found -- configure paths manually"
        }
        $stepDone = $true
    } catch {
        Write-Fail "Start script update failed: $_"
        $choice = Request-Recovery "Start script" 8
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped start script update"; $stepDone = $true }
            "X" { Write-ManualResume 8 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

$logsDir = "$PROJECT_ROOT\logs"
if (-not (Test-Path "$logsDir")) {
    New-Item -ItemType Directory -Path "$logsDir" -Force | Out-Null
    Write-Ok "Created logs directory"
}

# ==================================================================
# Step 9: Check Ollama
# ==================================================================
Write-Step 9 "Checking Ollama"

$stepDone = $false
while (-not $stepDone) {
    $ollamaOk = $false
    $ollamaError = ""
    $models = @()

    # --- Method 1: Invoke-RestMethod ---
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10 -ErrorAction Stop
        $ollamaOk = $true
        $models = $response.models | ForEach-Object { $_.name }
    } catch {
        $ollamaError = $_.Exception.Message
    }

    # --- Method 2: curl.exe fallback ---
    if (-not $ollamaOk) {
        try {
            $curlResult = & curl.exe --silent --max-time 10 "http://localhost:11434/api/tags" 2>&1
            $curlExit = $LASTEXITCODE
            if ($curlExit -eq 0 -and $curlResult) {
                $parsed = $curlResult | ConvertFrom-Json
                $ollamaOk = $true
                $models = $parsed.models | ForEach-Object { $_.name }
                Write-Host "  (connected via curl.exe -- Invoke-RestMethod failed)" -ForegroundColor DarkGray
            }
        } catch { }
    }

    if ($ollamaOk) {
        Write-Ok "Ollama is running"
        if ($models -contains "nomic-embed-text:latest" -or $models -contains "nomic-embed-text") {
            Write-Ok "nomic-embed-text model found"
        } else {
            Write-Warn "nomic-embed-text NOT found -- run: ollama pull nomic-embed-text"
        }
        if ($models -contains "phi4:14b-q4_K_M" -or $models -contains "phi4-mini") {
            Write-Ok "Ollama LLM model found"
        } else {
            Write-Warn "No LLM model found -- run: ollama pull phi4:14b-q4_K_M"
        }
        $stepDone = $true
    } else {
        Write-Fail "Cannot reach Ollama at localhost:11434"
        if ($ollamaError) {
            Write-Host "  Error: $ollamaError" -ForegroundColor DarkGray
        }
        Write-Host ""
        Write-Host "  WHAT IS OLLAMA?" -ForegroundColor White
        Write-Host "    Ollama runs AI models locally on your computer (no internet needed)."
        Write-Host "    Without it, HybridRAG3 still works -- it just uses online AI instead."
        Write-Host ""
        Write-Host "  TO INSTALL (optional):" -ForegroundColor White
        Write-Host "    1. Download from https://ollama.com/download"
        Write-Host "    2. Run the installer"
        Write-Host "    3. Open a terminal and run: ollama pull nomic-embed-text"
        Write-Host "    4. Then re-run this setup, or press [R] below"
        Write-Host ""
        Write-Host "  Press [S] to skip if you only need online/cloud AI." -ForegroundColor Yellow
        Write-Host ""
        $choice = Request-Recovery "Checking Ollama" 9 -DrillDown
        switch ($choice) {
            "R" { continue }
            "D" {
                Write-Host ""
                Write-Host "  --- Drill-Down: Ollama Connectivity Diagnostics ---" -ForegroundColor Cyan
                Write-Host ""

                # Check 1: Is Ollama process running?
                Write-Host "  [1] Ollama process:" -ForegroundColor White
                $ollamaProcs = Get-Process -Name "ollama*" -ErrorAction SilentlyContinue
                if ($ollamaProcs) {
                    foreach ($p in $ollamaProcs) {
                        Write-Host "      [OK] $($p.ProcessName) (PID $($p.Id))" -ForegroundColor Green
                    }
                } else {
                    Write-Host "      [FAIL] No ollama process found" -ForegroundColor Red
                    Write-Host "      Fix: Start Ollama (ollama serve) or launch the Ollama app" -ForegroundColor Gray
                }

                # Check 2: Is port 11434 listening?
                Write-Host "  [2] Port 11434:" -ForegroundColor White
                try {
                    $tcpTest = Test-NetConnection -ComputerName localhost -Port 11434 -WarningAction SilentlyContinue -ErrorAction Stop
                    if ($tcpTest.TcpTestSucceeded) {
                        Write-Host "      [OK] Port 11434 is open" -ForegroundColor Green
                    } else {
                        Write-Host "      [FAIL] Port 11434 is closed" -ForegroundColor Red
                        Write-Host "      Ollama may not be running, or a firewall is blocking it" -ForegroundColor Gray
                    }
                } catch {
                    Write-Host "      [WARN] Test-NetConnection not available" -ForegroundColor Yellow
                }

                # Check 3: curl.exe direct test
                Write-Host "  [3] curl.exe direct test:" -ForegroundColor White
                try {
                    $curlOut = & curl.exe --silent --max-time 10 "http://localhost:11434" 2>&1
                    $curlCode = $LASTEXITCODE
                    if ($curlCode -eq 0 -and $curlOut -match "Ollama") {
                        Write-Host "      [OK] curl.exe reached Ollama" -ForegroundColor Green
                    } else {
                        Write-Host "      [FAIL] curl.exe exit code $curlCode" -ForegroundColor Red
                        if ($curlOut) { Write-Host "      Output: $curlOut" -ForegroundColor Gray }
                    }
                } catch {
                    Write-Host "      [WARN] curl.exe not available" -ForegroundColor Yellow
                }

                # Check 4: curl.exe /api/tags (verbose)
                Write-Host "  [4] curl.exe /api/tags (verbose):" -ForegroundColor White
                try {
                    $curlVerbose = & curl.exe --silent --show-error --max-time 10 "http://localhost:11434/api/tags" 2>&1
                    $curlCode2 = $LASTEXITCODE
                    if ($curlCode2 -eq 0) {
                        Write-Host "      [OK] Got response (length $($curlVerbose.Length))" -ForegroundColor Green
                        $preview = if ($curlVerbose.Length -gt 200) { $curlVerbose.Substring(0, 200) + "..." } else { $curlVerbose }
                        Write-Host "      Preview: $preview" -ForegroundColor DarkGray
                    } else {
                        Write-Host "      [FAIL] exit code $curlCode2" -ForegroundColor Red
                    }
                } catch {
                    Write-Host "      [WARN] curl.exe failed: $($_.Exception.Message)" -ForegroundColor Yellow
                }

                # Check 5: Invoke-RestMethod verbose error
                Write-Host "  [5] Invoke-RestMethod detail:" -ForegroundColor White
                try {
                    $testResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10 -ErrorAction Stop
                    Write-Host "      [OK] Invoke-RestMethod succeeded on retry" -ForegroundColor Green
                } catch {
                    Write-Host "      [FAIL] $($_.Exception.GetType().Name): $($_.Exception.Message)" -ForegroundColor Red
                    if ($_.Exception.InnerException) {
                        Write-Host "      Inner: $($_.Exception.InnerException.GetType().Name): $($_.Exception.InnerException.Message)" -ForegroundColor Red
                    }
                }

                # Check 6: PowerShell version
                Write-Host "  [6] PowerShell version:" -ForegroundColor White
                Write-Host "      $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))" -ForegroundColor White

                Write-Host ""
                Write-Host "  --- End Drill-Down ---" -ForegroundColor Cyan
                Write-Host ""
            }
            "S" { Write-Warn "Skipped Ollama check"; $stepDone = $true }
            "X" { Write-ManualResume 9 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

# ======================================================================
#  PHASE 3: FULL DIAGNOSTICS
# ======================================================================
Write-Step 10 "Running full diagnostics"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
$stepDone = $false
while (-not $stepDone) {
$diagPass = 0
$diagFail = 0

# --- Diagnostic 1: Import verification ---
Write-Host ""
Write-Host "  --- Import Verification ---" -ForegroundColor Cyan
Write-Host "  Checking each package loads correctly..."
Write-Host ""
$packages = @(
    @{mod="fastapi"; label="FastAPI (web framework)"},
    @{mod="httpx"; label="httpx (HTTP client)"},
    @{mod="openai"; label="openai (Azure OpenAI SDK)"},
    @{mod="pydantic"; label="pydantic (data validation)"},
    @{mod="numpy"; label="numpy (numerical computing)"},
    @{mod="yaml"; label="PyYAML (config parser)"},
    @{mod="uvicorn"; label="uvicorn (web server)"},
    @{mod="cryptography"; label="cryptography (encryption)"},
    @{mod="pytest"; label="pytest (test runner)"}
)
foreach ($pkg in $packages) {
    $null = & $PYTHON -c "import $($pkg.mod)" 2>&1
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

# --- Diagnostic 4: Boot test ---
Write-Host ""
Write-Host "  --- Boot Test ---" -ForegroundColor Cyan
Write-Host ""
$bootTest = & $PYTHON -c "from src.core.config import Config; c = Config(); print('Config OK')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [OK] Core config loads" -ForegroundColor Green
    $diagPass++
} else {
    Write-Host "    [WARN] Core config could not load (may need Ollama)" -ForegroundColor Yellow
}

# --- Diagnostic 5: Regression tests ---
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
    Write-Warn "Some tests had issues (common without Ollama running)"
}

# --- Summary ---
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

    if ($diagFail -eq 0) {
        $stepDone = $true
    } else {
        $choice = Request-Recovery "Diagnostics" 10 -DrillDown
        switch ($choice) {
            "R" { continue }
            "D" {
                Write-Host ""
                Write-Host "  --- Drill-Down: Re-checking imports individually ---" -ForegroundColor Cyan
                Write-Host ""
                foreach ($pkg in $packages) {
                    $pkgDone = $false
                    while (-not $pkgDone) {
                        $null = & $PYTHON -c "import $($pkg.mod)" 2>&1
                        if ($LASTEXITCODE -eq 0) {
                            Write-Host "    [OK] $($pkg.label)" -ForegroundColor Green
                            $pkgDone = $true
                        } else {
                            Write-Host "    [FAIL] $($pkg.label)" -ForegroundColor Red
                            $pipName = if ($pkg.mod -eq "yaml") { "pyyaml" } else { $pkg.mod }
                            Write-Host "    Fix: $PIP install $pipName" -ForegroundColor Gray
                            Write-Host ""
                            Write-Host "  [R] Retry (re-installs $pipName)   [S] Skip   [X] Exit"
                            $pkgChoice = Read-Host "  Choose [R/S/X]"
                            switch ($pkgChoice.ToUpper()) {
                                "R" {
                                    & $PIP install $pipName 2>&1
                                    continue
                                }
                                "S" { Write-Warn "Skipped $($pkg.label)"; $pkgDone = $true }
                                "X" { Write-ManualResume 10 $TOTAL_STEPS; exit 0 }
                                default { continue }
                            }
                        }
                    }
                }
                $stepDone = $true
            }
            "S" { Write-Warn "Skipped diagnostics recovery"; $stepDone = $true }
            "X" { Write-ManualResume 10 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
} # end diagnostics while loop
$stepTimer.Stop()

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
    Write-Host "  ============================================" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  HOW TO START:"
Write-Host "    Double-click:  start_gui.bat" -ForegroundColor White
Write-Host ""
Write-Host "  OLLAMA MODELS (if not installed):"
Write-Host "    ollama pull nomic-embed-text  (274 MB -- required)"
Write-Host "    ollama pull phi4-mini         (2.3 GB -- recommended)"
Write-Host ""
Write-Host "  TO CHANGE SETTINGS:" -ForegroundColor Yellow
Write-Host "    Run this script again -- you can redo any choice."
Write-Host ""
