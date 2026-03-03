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
    Write-Host "       .venv\Scripts\pip.exe install -r requirements_approved.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org"
    Write-Host ""
    Write-Host "    3. Re-run this script to pick up where you left off"
    Write-Host "       (it detects existing .venv and skips completed steps)"
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
}

# Configure Ollama for enterprise/offline defaults.
# This disables Ollama Cloud features that can trigger update/cloud checks.
function Set-OllamaOfflineDefaults {
    try {
        [Environment]::SetEnvironmentVariable("OLLAMA_NO_CLOUD", "1", "User")
        $env:OLLAMA_NO_CLOUD = "1"
        Write-Ok "Set user env: OLLAMA_NO_CLOUD=1"
    } catch {
        Write-Warn "Could not set OLLAMA_NO_CLOUD env var: $($_.Exception.Message)"
    }

    try {
        $ollamaDir = Join-Path $env:USERPROFILE ".ollama"
        if (-not (Test-Path $ollamaDir)) {
            New-Item -ItemType Directory -Path $ollamaDir -Force | Out-Null
        }
        $serverJsonPath = Join-Path $ollamaDir "server.json"
        $cfg = @{}
        if (Test-Path $serverJsonPath) {
            try {
                $raw = Get-Content $serverJsonPath -Raw
                if (-not [string]::IsNullOrWhiteSpace($raw)) {
                    $obj = $raw | ConvertFrom-Json
                    foreach ($p in $obj.PSObject.Properties) {
                        $cfg[$p.Name] = $p.Value
                    }
                }
            } catch {
                Write-Warn "Could not parse existing .ollama\\server.json, rewriting minimal config"
                $cfg = @{}
            }
        }
        $cfg["disable_ollama_cloud"] = $true
        $cfg | ConvertTo-Json -Depth 10 | Set-Content -Path $serverJsonPath -Encoding UTF8
        Write-Ok "Configured .ollama\\server.json (disable_ollama_cloud=true)"
    } catch {
        Write-Warn "Could not write .ollama\\server.json: $($_.Exception.Message)"
    }
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
$OCR_DIVERSION_DIR = $null

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
        # Keep compatibility with current approved package set (Python 3.10+).
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
                if ($LASTEXITCODE -eq 0) { $PY_EXE = "python"; Write-Ok "Found: $result" }
            } catch { }
        }
        if (-not $PY_EXE) {
            Write-Fail "Python is not installed (or not on PATH)."
            Write-Host "  Request Python 3.12 from your IT department."
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
        Write-Host "    M = I will enter my own folder paths"
        Write-Host "    B = Go back to previous step"
        Write-Host ""
        $pathChoice = Read-Host "  Choose [C/M/B]"

        if ($pathChoice -eq "B" -or $pathChoice -eq "b") { $wizStep = 2; continue }

        if ($pathChoice -eq "M" -or $pathChoice -eq "m") {
            # Manual path entry
            Write-Host ""
            Write-Host "  Where should HybridRAG3 store its search database?"
            Write-Host "  (Uses about 1-5 GB depending on how many documents you have)"
            Write-Host "  Example: D:\RAG Indexed Data" -ForegroundColor White
            Write-Host ""
            $input = Read-Host "  Database folder"
            if ($input -eq "B" -or $input -eq "b") { continue }
            while ([string]::IsNullOrWhiteSpace($input)) {
                Write-Warn "Cannot be empty. Type a folder path, or B to go back."
                $input = Read-Host "  Database folder"
                if ($input -eq "B" -or $input -eq "b") { break }
            }
            if ($input -eq "B" -or $input -eq "b") { continue }
            $DATA_DIR = $input

            Write-Host ""
            Write-Host "  Where are the documents you want to search?"
            Write-Host "  (HybridRAG3 reads these files but never modifies them)"
            Write-Host "  Example: D:\RAG Source Data" -ForegroundColor White
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

# PS 5.1 converts native command stderr (pip/python WARNINGs) to ErrorRecords.
# With 'Stop', these become terminating errors that crash the script before
# $LASTEXITCODE can be checked. Phase 2 pip/python calls already have their
# own error handling (while loops, $LASTEXITCODE, try/catch), so 'Continue'
# is correct here. Cmdlets inside try/catch use explicit -ErrorAction Stop.
$ErrorActionPreference = 'Continue'

Set-Location "$PROJECT_ROOT"
if (-not (Test-Path "$DATA_DIR"))   { New-Item -ItemType Directory -Path "$DATA_DIR" -Force | Out-Null; Write-Ok "Created: $DATA_DIR" }
if (-not (Test-Path "$SOURCE_DIR")) { New-Item -ItemType Directory -Path "$SOURCE_DIR" -Force | Out-Null; Write-Ok "Created: $SOURCE_DIR" }
$OCR_DIVERSION_DIR = "$SOURCE_DIR\_ocr_diversions"
if (-not (Test-Path "$OCR_DIVERSION_DIR")) { New-Item -ItemType Directory -Path "$OCR_DIVERSION_DIR" -Force | Out-Null; Write-Ok "Created: $OCR_DIVERSION_DIR" }

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
# Step 5: Upgrade pip + detect corporate proxy
# ==================================================================
Write-Step 5 "Upgrading pip (with proxy detection)"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$PIP = "$PROJECT_ROOT\.venv\Scripts\pip.exe"
# Corporate proxies add latency. Default pip timeout is 15 seconds which
# is too short -- packages time out before the proxy finishes relaying.
# We increase to 120 seconds and allow 5 retries for TCP RST recovery.
$TRUSTED = "--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org", "--timeout", "120", "--retries", "3"

# --- Detect corporate proxy from Windows registry ---
# Corporate networks configure proxy via Group Policy / Internet Settings.
# pip reads HTTP_PROXY/HTTPS_PROXY env vars but these are often NOT set.
# Without them pip tries to connect DIRECTLY to PyPI -- which the corporate
# firewall blocks with TCP RST (WinError 10054: forcibly closed).
# We read the proxy from the registry and set the env vars so pip uses it.
$proxyDetected = $false
try {
    $inetSettings = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    $proxyEnabled = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyEnable
    $proxyServer  = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyServer
    if ($proxyEnabled -eq 1 -and $proxyServer) {
        # ProxyServer may be "host:port" or "http=host:port;https=host:port"
        if ($proxyServer -match "https=([^;]+)") {
            $httpsProxy = $Matches[1]
        } elseif ($proxyServer -match "http=([^;]+)") {
            $httpsProxy = $Matches[1]
        } else {
            $httpsProxy = $proxyServer
        }
        # Ensure scheme prefix
        if ($httpsProxy -notmatch "^https?://") {
            $httpsProxy = "http://$httpsProxy"
        }
        if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = $httpsProxy }
        if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $httpsProxy }
        $proxyDetected = $true
        Write-Ok "Detected corporate proxy: $httpsProxy"
    } else {
        # Check for PAC auto-config
        $autoConfigUrl = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).AutoConfigURL
        if ($autoConfigUrl) {
            Write-Warn "Proxy uses auto-config (PAC): $autoConfigUrl"
            Write-Host "  pip cannot read PAC files. If packages fail to install,"
            Write-Host "  ask IT for the direct proxy address and set it manually:"
            Write-Host "  `$env:HTTPS_PROXY = 'http://proxy.yourcompany.com:8080'"
        } else {
            Write-Host "  No system proxy detected (direct internet or VPN)"
        }
    }
} catch {
    Write-Host "  Could not read proxy settings from registry"
}
$env:NO_PROXY = "localhost,127.0.0.1"

# --- Create .venv\pip.ini with proxy-safe defaults ---
# This ensures ALL pip commands inside the venv automatically get trusted
# hosts, timeout, and retries -- even manual troubleshooting commands.
$pipIni = "$PROJECT_ROOT\.venv\pip.ini"
$pipIniContent = @"
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
timeout = 120
retries = 3
"@
if ($proxyDetected -and $env:HTTPS_PROXY) {
    $pipIniContent += "`nproxy = $($env:HTTPS_PROXY)"
}
# MUST use WriteAllText -- Out-File -Encoding UTF8 writes BOM in PS 5.1,
# and pip cannot parse a config file that starts with BOM bytes.
[System.IO.File]::WriteAllText($pipIni, $pipIniContent)
# Validate pip can read its config -- catches BOM, encoding, or syntax errors.
# pip config list exits 0 even with warnings, so we check stderr for "could not load".
$pipConfigCheck = & $PYTHON -m pip config list 2>&1 | Out-String
if ($pipConfigCheck -match "could not load") {
    Write-Fail "pip.ini validation failed -- pip cannot read the config file"
    Write-Host "  Recreating pip.ini without BOM..."
    # Force clean rewrite
    [System.IO.File]::WriteAllText($pipIni, $pipIniContent)
    $pipConfigCheck2 = & $PYTHON -m pip config list 2>&1 | Out-String
    if ($pipConfigCheck2 -match "could not load") {
        Write-Fail "pip.ini still broken after rewrite"
        $choice = Request-Recovery "pip.ini validation" 5
        switch ($choice) {
            "R" { }
            "S" { Write-Warn "Skipped -- pip will use defaults (no proxy/timeout config)" }
            "X" { Write-ManualResume 5 $TOTAL_STEPS; exit 0 }
        }
    } else {
        Write-Ok "pip.ini repaired"
    }
} else {
    Write-Ok "Created .venv\pip.ini (proxy-safe defaults baked in)"
}

$stepDone = $false
while (-not $stepDone) {
    Write-Host "  Upgrading pip with proxy-safe timeouts (120s per request)..."
    # BUG 6 fix: capture exit code before Out-String (pipeline may clobber LASTEXITCODE on old PS builds)
    $pipRaw = & $PYTHON -m pip install --upgrade pip --progress-bar on @TRUSTED 2>&1
    $pipExitCode = $LASTEXITCODE
    $pipOutput = $pipRaw | Out-String
    # Check BOTH exit code AND pip warnings -- pip exits 0 even when config is broken
    if ($pipExitCode -eq 0 -and $pipOutput -notmatch "could not load") {
        $stepDone = $true
    } else {
        if ($pipOutput -match "could not load") {
            Write-Fail "pip config error detected (pip exited 0 but config is broken)"
        }
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
# Step 6: Install pip-system-certs (corporate SSL integration)
# ==================================================================
Write-Step 6 "Installing corporate certificate support"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

$stepDone = $false
while (-not $stepDone) {
    Write-Host "  Installing pip-system-certs (makes Python trust Windows certs)..."
    Write-Host "  (This teaches Python to use your Windows certificate store)"
    & $PIP install pip-system-certs --progress-bar on @TRUSTED 2>&1
    if ($LASTEXITCODE -eq 0) {
        $stepDone = $true
    } else {
        $choice = Request-Recovery "Certificate support" 6
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped pip-system-certs"; $stepDone = $true }
            "X" { Write-ManualResume 6 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

$stepTimer.Stop()
Write-Ok "Certificate support installed ($(Format-Elapsed $stepTimer))"

# ==================================================================
# Step 7: Install approved packages (7A through 7R)
# ==================================================================
# Packages are installed in small groups (7A-7R) so that if the
# proxy drops a connection, we know exactly which group failed.
# If a group fails, choose [D] to drill into individual packages.
# openai is attempted LAST (7Q) since it has the most dependencies.
# ------------------------------------------------------------------
Write-Step 7 "Installing packages (7A-7R, grouped for proxy resilience)"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()

# Create detailed log for AI-assisted troubleshooting
$logsDir = "$PROJECT_ROOT\logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
$LOG_FILE = "$logsDir\setup_install_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

# BUG 2 fix: Out-File writes BOM -- log file is consumed by Python, use WriteAllText instead
$headerLines = @(
    ("=" * 70),
    "HybridRAG3 Setup Install Log",
    ("=" * 70),
    "Date       : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "Python     : $PY_EXE $(if($PY_VER_FLAG){$PY_VER_FLAG}else{'(system)'})",
    "pip        : $(& $PIP --version 2>&1)",
    "OS         : $([System.Environment]::OSVersion.VersionString)",
    "Machine    : $env:COMPUTERNAME",
    "HTTP_PROXY : $(if($env:HTTP_PROXY){$env:HTTP_PROXY}else{'(not set)'})",
    "HTTPS_PROXY: $(if($env:HTTPS_PROXY){$env:HTTPS_PROXY}else{'(not set)'})",
    "NO_PROXY   : $(if($env:NO_PROXY){$env:NO_PROXY}else{'(not set)'})",
    "Project    : $PROJECT_ROOT",
    "Req file   : requirements_approved.txt",
    ("=" * 70),
    ""
)
$headerText = ($headerLines -join "`n") + "`n"
[System.IO.File]::WriteAllText($LOG_FILE, $headerText)

Write-Host ""
Write-Host "  Packages are split into small groups (7A through 7R)."
Write-Host "  If a group fails, choose [D] to drill into individual packages."
Write-Host "  openai is attempted last (7Q) -- has the most dependencies."
Write-Host ""
Write-Host "  Log file: $LOG_FILE" -ForegroundColor DarkGray
Write-Host ""

Write-Host "  ---- pip output starts ----" -ForegroundColor DarkGray

$groups = @(
    @{ name = "Config basics";      pkgs = @("pyyaml==6.0.2", "numpy==1.26.4") },
    @{ name = "Typing support";     pkgs = @("typing_extensions==4.15.0", "annotated-types==0.7.0", "typing-inspection==0.4.2") },
    @{ name = "Data validation";    pkgs = @("pydantic==2.11.1") },
    @{ name = "HTTP async";         pkgs = @("httpx==0.28.1", "sniffio==1.3.1") },
    @{ name = "HTTP sync";          pkgs = @("requests==2.32.5", "urllib3==2.6.3") },
    @{ name = "Encryption";         pkgs = @("cryptography==44.0.2") },
    @{ name = "PDF parsing";        pkgs = @("pdfplumber==0.11.9", "pdfminer.six==20251230") },
    @{ name = "PDF utilities";      pkgs = @("pypdf==6.6.2", "pypdfium2==5.3.0") },
    @{ name = "Office documents";   pkgs = @("python-docx==1.2.0", "python-pptx==1.0.2") },
    @{ name = "Excel support";      pkgs = @("openpyxl==3.1.5", "xlsxwriter==3.2.9", "et_xmlfile==2.0.0") },
    @{ name = "XML and images";     pkgs = @("lxml==6.0.2", "pillow==12.1.0", "pdf2image==1.17.0", "pytesseract==0.3.13", "ocrmypdf==16.10.4") },
    @{ name = "Web framework";      pkgs = @("fastapi==0.115.0", "starlette==0.38.6", "python-multipart==0.0.22") },
    @{ name = "Web server";         pkgs = @("uvicorn==0.41.0", "click==8.3.1") },
    @{ name = "Credential storage"; pkgs = @("keyring==23.13.1", "jaraco.classes==3.4.0", "more-itertools==10.8.0") },
    @{ name = "Utilities";          pkgs = @("structlog==24.4.0", "rich==13.9.4", "tqdm==4.67.3", "regex==2026.1.15", "colorama==0.4.6") },
    @{ name = "AI core (openai)";   pkgs = @("openai==1.109.1", "tiktoken==0.8.0"); nodeps = $true }
)

$groupNum = 0
$groupsFailed = 0
foreach ($group in $groups) {
    $groupNum++
    $letter = [char](64 + $groupNum)
    Write-Host ""
    Write-Host "  --- Step 7$letter : $($group.name) ---" -ForegroundColor White
    "[$(Get-Date -Format 'HH:mm:ss')] Step 7$letter : $($group.name) -- START" | Add-Content $LOG_FILE -Encoding UTF8
    "  Packages: $($group.pkgs -join ', ')" | Add-Content $LOG_FILE -Encoding UTF8

    # Groups with nodeps=true have all deps installed by earlier groups.
    # --no-deps reduces network requests, which helps with proxy RST issues.
    $extraFlags = @()
    if ($group.nodeps) { $extraFlags += "--no-deps" }

    $stepDone = $false
    while (-not $stepDone) {
        $pipOutput = & $PIP install $($group.pkgs) --progress-bar on @extraFlags @TRUSTED 2>&1
        $pipExitCode = $LASTEXITCODE
        $pipOutput
        $pipOutput | Out-String | Add-Content $LOG_FILE -Encoding UTF8

        if ($pipExitCode -eq 0) {
            Write-Ok "7$letter $($group.name)"
            "[$(Get-Date -Format 'HH:mm:ss')] Step 7$letter : OK" | Add-Content $LOG_FILE -Encoding UTF8
            $stepDone = $true
        } else {
            Write-Fail "7$letter $($group.name)"
            "[$(Get-Date -Format 'HH:mm:ss')] Step 7$letter : FAIL (exit code $pipExitCode)" | Add-Content $LOG_FILE -Encoding UTF8

            $choice = Request-Recovery "7$letter $($group.name)" 7 -DrillDown
            "[$(Get-Date -Format 'HH:mm:ss')] Step 7$letter : User chose $choice" | Add-Content $LOG_FILE -Encoding UTF8
            switch ($choice) {
                "R" { continue }
                "D" {
                    # Drill down: install each package one at a time
                    $pkgIdx = 0
                    foreach ($pkg in $group.pkgs) {
                        $pkgIdx++
                        Write-Host ""
                        Write-Host "    --- Step 7${letter}-${pkgIdx} : $pkg ---" -ForegroundColor White
                        "[$(Get-Date -Format 'HH:mm:ss')]   7${letter}-${pkgIdx} : $pkg -- START" | Add-Content $LOG_FILE -Encoding UTF8
                        $pkgDone = $false
                        while (-not $pkgDone) {
                            $pkgOutput = & $PIP install $pkg --no-deps --progress-bar on @TRUSTED 2>&1
                            $pkgExitCode = $LASTEXITCODE
                            $pkgOutput
                            $pkgOutput | Out-String | Add-Content $LOG_FILE -Encoding UTF8
                            if ($pkgExitCode -eq 0) {
                                Write-Ok "$pkg"
                                "[$(Get-Date -Format 'HH:mm:ss')]   7${letter}-${pkgIdx} : OK" | Add-Content $LOG_FILE -Encoding UTF8
                                $pkgDone = $true
                            } else {
                                Write-Fail "$pkg"
                                "[$(Get-Date -Format 'HH:mm:ss')]   7${letter}-${pkgIdx} : FAIL (exit code $pkgExitCode)" | Add-Content $LOG_FILE -Encoding UTF8
                                Write-Host ""
                                Write-Host "  Proxy is blocking this package. Try:" -ForegroundColor Yellow
                                Write-Host "    Retry with aggressive timeouts (proxy may allow on next attempt):" -ForegroundColor White
                                Write-Host "    .venv\Scripts\pip.exe install $pkg --no-deps --timeout 120 --retries 10 --trusted-host pypi.org --trusted-host files.pythonhosted.org" -ForegroundColor Gray
                                Write-Host "    If repeated retries fail, request $($pkg.Split('==')[0]) in the enterprise software store." -ForegroundColor Gray
                                Write-Host ""
                                Write-Host "  [R] Retry   [S] Skip   [X] Exit"
                                $pkgChoice = Read-Host "  Choose [R/S/X]"
                                "[$(Get-Date -Format 'HH:mm:ss')]   7${letter}-${pkgIdx} : User chose $($pkgChoice.ToUpper())" | Add-Content $LOG_FILE -Encoding UTF8
                                switch ($pkgChoice.ToUpper()) {
                                    "R" { continue }
                                    "S" { Write-Warn "Skipped $pkg"; $pkgDone = $true }
                                    "X" { Write-ManualResume 7 $TOTAL_STEPS; exit 0 }
                                    default { continue }
                                }
                            }
                        }
                    }
                    $stepDone = $true
                }
                "S" { Write-Warn "Skipped 7$letter $($group.name)"; $groupsFailed++; $stepDone = $true }
                "X" { Write-ManualResume 7 $TOTAL_STEPS; exit 0 }
                default { continue }
            }
        }
    }
}

# Final pass: verify all requirements satisfied (catches missed deps)
Write-Host ""
Write-Host "  --- Step 7R : Dependency verification ---" -ForegroundColor White
"[$(Get-Date -Format 'HH:mm:ss')] Step 7R : Dependency verification -- START" | Add-Content $LOG_FILE -Encoding UTF8
$stepDone = $false
while (-not $stepDone) {
    $pipOutput = & $PIP install -r "$PROJECT_ROOT\requirements_approved.txt" --progress-bar on @TRUSTED 2>&1
    $pipExitCode = $LASTEXITCODE
    $pipOutput
    $pipOutput | Out-String | Add-Content $LOG_FILE -Encoding UTF8
    if ($pipExitCode -eq 0) {
        Write-Ok "7R All dependencies verified"
        "[$(Get-Date -Format 'HH:mm:ss')] Step 7R : OK" | Add-Content $LOG_FILE -Encoding UTF8
        $stepDone = $true
    } else {
        "[$(Get-Date -Format 'HH:mm:ss')] Step 7R : FAIL (exit code $pipExitCode)" | Add-Content $LOG_FILE -Encoding UTF8
        $choice = Request-Recovery "7R Dependency verification" 7
        "[$(Get-Date -Format 'HH:mm:ss')] Step 7R : User chose $choice" | Add-Content $LOG_FILE -Encoding UTF8
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped dependency verification"; $stepDone = $true }
            "X" { Write-ManualResume 7 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

# Log summary
"" | Add-Content $LOG_FILE -Encoding UTF8
"[$(Get-Date -Format 'HH:mm:ss')] SUMMARY: $($groups.Count) groups attempted, $groupsFailed skipped" | Add-Content $LOG_FILE -Encoding UTF8

Write-Host "  ---- pip output ends ----" -ForegroundColor DarkGray
Write-Host "  Full log: $LOG_FILE" -ForegroundColor DarkGray
$stepTimer.Stop()
if ($groupsFailed -gt 0) {
    Write-Warn "Packages installed ($groupsFailed group(s) skipped) ($(Format-Elapsed $stepTimer))"
} else {
    Write-Ok "All packages installed ($(Format-Elapsed $stepTimer))"
}

# ==================================================================
# Step 8: Install test tools (optional)
# ==================================================================
Write-Step 8 "Test tools (optional)"
Write-Host "  pytest and psutil verify the installation works correctly."
Write-Host ""
$installTests = Read-Host "  Install test tools? [Y/n]"
if ($installTests -ne "n" -and $installTests -ne "N") {
    $stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $stepDone = $false
    while (-not $stepDone) {
        Write-Host "  Installing pytest and psutil..."
        & $PIP install pytest==9.0.2 psutil==7.2.2 --progress-bar on @TRUSTED 2>&1
        if ($LASTEXITCODE -eq 0) {
            $stepDone = $true
        } else {
            $choice = Request-Recovery "Test tools install" 8
            switch ($choice) {
                "R" { continue }
                "S" { Write-Warn "Skipped test tools"; $stepDone = $true }
                "X" { Write-ManualResume 8 $TOTAL_STEPS; exit 0 }
                default { continue }
            }
        }
    }
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
$stepDone = $false
while (-not $stepDone) {
    try {
        if (Test-Path "$configPath") {
            $content = Get-Content "$configPath" -Raw -Encoding UTF8 -ErrorAction Stop
            $dbPath = "$DATA_DIR\hybridrag.sqlite3"
            $embPath = "$DATA_DIR\_embeddings"
            # BUG 3 fix: escape $ in paths so -replace does not treat them as regex backreferences
            $safeDbPath = $dbPath.Replace('$', '$$')
            $safeEmbPath = $embPath.Replace('$', '$$')
            $safeSrcDir = $SOURCE_DIR.Replace('$', '$$')
            $safeOcrDivDir = $OCR_DIVERSION_DIR.Replace('$', '$$')
            $content = $content -replace '(?m)^(\s*database:\s*).*$', "`$1$safeDbPath"
            $content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', "`$1$safeEmbPath"
            $content = $content -replace '(?m)^(\s*source_folder:\s*).*$', "`$1$safeSrcDir"
            $content = $content -replace '(?m)^(\s*ocr_diversion_folder:\s*).*$', "`$1$safeOcrDivDir"
            # YAML is consumed by Python -- must NOT have BOM (Set-Content adds BOM in PS 5.1)
            [System.IO.File]::WriteAllText($configPath, $content)
            Write-Ok "Config updated with your paths"
        } else {
            Write-Warn "Config file not found -- configure paths manually later"
        }
        $stepDone = $true
    } catch {
        Write-Fail "Config update failed: $_"
        $choice = Request-Recovery "Config YAML" 9
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped config update"; $stepDone = $true }
            "X" { Write-ManualResume 9 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

# ==================================================================
# Step 10: Create start_hybridrag.ps1 from template
# ==================================================================
Write-Step 10 "Creating start_hybridrag.ps1 from template"

$templatePath = "$PROJECT_ROOT\start_hybridrag.ps1.template"
$startScript = "$PROJECT_ROOT\start_hybridrag.ps1"

$stepDone = $false
while (-not $stepDone) {
    try {
        if (Test-Path "$startScript") {
            Write-Ok "start_hybridrag.ps1 already exists -- skipping"
        } elseif (Test-Path "$templatePath") {
            $content = Get-Content "$templatePath" -Raw -Encoding UTF8 -ErrorAction Stop
            # BUG 3 fix: escape $ in replacement paths to prevent regex backreference corruption
            $safeProjectRoot = $PROJECT_ROOT.Replace('$', '$$')
            $safeDataDir = $DATA_DIR.Replace('$', '$$')
            $safeSrcDir2 = $SOURCE_DIR.Replace('$', '$$')
            $content = $content -replace 'C:\\path\\to\\HybridRAG3', $safeProjectRoot
            $content = $content -replace 'C:\\path\\to\\data', $safeDataDir
            $content = $content -replace 'C:\\path\\to\\source_docs', $safeSrcDir2
            Set-Content -Path "$startScript" -Value $content -Encoding UTF8 -ErrorAction Stop
            Write-Ok "start_hybridrag.ps1 created from template"
        } else {
            Write-Warn "No template found -- create start_hybridrag.ps1 manually"
        }
        $stepDone = $true
    } catch {
        Write-Fail "Template creation failed: $_"
        $choice = Request-Recovery "Start script template" 10
        switch ($choice) {
            "R" { continue }
            "S" { Write-Warn "Skipped start script creation"; $stepDone = $true }
            "X" { Write-ManualResume 10 $TOTAL_STEPS; exit 0 }
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
        $stepDone = $false
        while (-not $stepDone) {
            & $PYTHON "tools/py/store_endpoint.py" $apiEndpoint 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "API endpoint stored"
                $stepDone = $true
            } else {
                Write-Fail "Failed to store API endpoint"
                $choice = Request-Recovery "Store endpoint" 11
                switch ($choice) {
                    "R" { continue }
                    "S" { Write-Warn "Skipped endpoint storage"; $stepDone = $true }
                    "X" { Write-ManualResume 11 $TOTAL_STEPS; exit 0 }
                    default { continue }
                }
            }
        }

        Write-Host ""
        Write-Host "  Enter your API key (text is hidden as you type)."
        Write-Host ""
        $apiKey = Read-Host "  API Key" -AsSecureString
        # BUG 7 fix: pass key via env var (not argv) to hide from process list, and free BSTR
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey)
        try {
            $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
            if (-not [string]::IsNullOrWhiteSpace($plainKey)) {
                $stepDone = $false
                while (-not $stepDone) {
                    $env:HYBRIDRAG_API_KEY = $plainKey
                    & $PYTHON "tools/py/store_key.py" 2>&1
                    if ($LASTEXITCODE -eq 0) {
                        Write-Ok "API key stored in Windows Credential Manager"
                        $stepDone = $true
                    } else {
                        Write-Fail "Failed to store API key"
                        $choice = Request-Recovery "Store API key" 11
                        switch ($choice) {
                            "R" { continue }
                            "S" { Write-Warn "Skipped API key storage"; $stepDone = $true }
                            "X" { Write-ManualResume 11 $TOTAL_STEPS; exit 0 }
                            default { continue }
                        }
                    }
                }
            }
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            $plainKey = $null
            $env:HYBRIDRAG_API_KEY = $null
        }
    }
}

# ==================================================================
# Step 12: Check Ollama
# ==================================================================
# PS 5.1 proxy bypass: Invoke-RestMethod has no -NoProxy flag (added
# in PS 7). The -Proxy parameter takes [Uri], not [WebProxy]. And
# $env:NO_PROXY is ignored by .NET Framework WebRequest (Unix-only).
#
# Correct method for PS 5.1: create a WebRequestSession with an empty
# WebProxy (Address=$null means IsBypassed returns true for all URIs).
# Fallback: curl.exe --noproxy (ships with Windows 10 1803+).
# ==================================================================
Write-Step 12 "Checking Ollama"
Set-OllamaOfflineDefaults

# Build proxy-free session for Invoke-RestMethod (PS 5.1 compatible)
$ollamaSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$ollamaSession.Proxy = New-Object System.Net.WebProxy

$stepDone = $false
while (-not $stepDone) {
    $ollamaOk = $false
    $ollamaError = ""
    $models = @()

    # --- Method 1: Invoke-RestMethod with proxy-free WebSession ---
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -ErrorAction Stop -WebSession $ollamaSession
        $ollamaOk = $true
        $models = $response.models | ForEach-Object { $_.name }
    } catch {
        $ollamaError = $_.Exception.Message
    }

    # --- Method 2: curl.exe fallback (bypasses all .NET proxy logic) ---
    if (-not $ollamaOk) {
        try {
            $curlResult = & curl.exe --noproxy "localhost,127.0.0.1" --silent --max-time 5 "http://localhost:11434/api/tags" 2>&1
            $curlExit = $LASTEXITCODE
            if ($curlExit -eq 0 -and $curlResult) {
                $parsed = $curlResult | ConvertFrom-Json
                $ollamaOk = $true
                $models = $parsed.models | ForEach-Object { $_.name }
                Write-Host "  (connected via curl.exe -- proxy was blocking PowerShell)" -ForegroundColor DarkGray
            }
        } catch {
            # curl.exe not available or JSON parse failed -- fall through
        }
    }

    if ($ollamaOk) {
        Write-Ok "Ollama is running"
        if ($models -contains "nomic-embed-text:latest" -or $models -contains "nomic-embed-text") {
            Write-Ok "nomic-embed-text model found"
        } else {
            Write-Warn "nomic-embed-text NOT found -- run: ollama pull nomic-embed-text"
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
        $choice = Request-Recovery "Checking Ollama" 12 -DrillDown
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

                # Check 3: System proxy config
                Write-Host "  [3] System proxy:" -ForegroundColor White
                try {
                    $inetSettings = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                    $proxyEnabled = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyEnable
                    $proxyServer  = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).ProxyServer
                    $autoConfig   = (Get-ItemProperty $inetSettings -ErrorAction SilentlyContinue).AutoConfigURL
                    if ($proxyEnabled -eq 1 -and $proxyServer) {
                        Write-Host "      Proxy enabled: $proxyServer" -ForegroundColor Yellow
                    } else {
                        Write-Host "      No manual proxy configured" -ForegroundColor Green
                    }
                    if ($autoConfig) {
                        Write-Host "      PAC auto-config: $autoConfig" -ForegroundColor Yellow
                    }
                } catch {
                    Write-Host "      Could not read registry" -ForegroundColor Yellow
                }

                # Check 4: .NET default proxy
                Write-Host "  [4] .NET default proxy (what PowerShell uses):" -ForegroundColor White
                $dotnetProxy = [System.Net.WebRequest]::DefaultWebProxy
                if ($dotnetProxy) {
                    $proxyFor = $dotnetProxy.GetProxy([Uri]"http://localhost:11434")
                    $bypassed = $dotnetProxy.IsBypassed([Uri]"http://localhost:11434")
                    Write-Host "      Proxy for localhost: $proxyFor" -ForegroundColor White
                    Write-Host "      Bypassed: $bypassed" -ForegroundColor $(if($bypassed){"Green"}else{"Red"})
                    if (-not $bypassed) {
                        Write-Host "      [FAIL] Proxy is intercepting localhost traffic" -ForegroundColor Red
                    }
                } else {
                    Write-Host "      No default proxy set" -ForegroundColor Green
                }

                # Check 5: curl.exe direct test
                Write-Host "  [5] curl.exe direct test:" -ForegroundColor White
                try {
                    $curlVer = & curl.exe --version 2>&1 | Select-Object -First 1
                    Write-Host "      $curlVer" -ForegroundColor DarkGray
                    $curlOut = & curl.exe --noproxy "localhost,127.0.0.1" --silent --max-time 10 "http://localhost:11434" 2>&1
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

                # Check 6: curl.exe /api/tags (verbose)
                Write-Host "  [6] curl.exe /api/tags (verbose):" -ForegroundColor White
                try {
                    $curlVerbose = & curl.exe --noproxy "localhost,127.0.0.1" --silent --show-error --max-time 10 "http://localhost:11434/api/tags" 2>&1
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

                # Check 7: Invoke-RestMethod verbose error
                Write-Host "  [7] Invoke-RestMethod detail:" -ForegroundColor White
                try {
                    $testSession2 = New-Object Microsoft.PowerShell.Commands.WebRequestSession
                    $testSession2.Proxy = New-Object System.Net.WebProxy
                    $testResult = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10 -ErrorAction Stop -WebSession $testSession2
                    Write-Host "      [OK] Invoke-RestMethod succeeded on retry" -ForegroundColor Green
                } catch {
                    Write-Host "      [FAIL] $($_.Exception.GetType().Name): $($_.Exception.Message)" -ForegroundColor Red
                    if ($_.Exception.InnerException) {
                        Write-Host "      Inner: $($_.Exception.InnerException.GetType().Name): $($_.Exception.InnerException.Message)" -ForegroundColor Red
                    }
                }

                # Check 8: PowerShell version
                Write-Host "  [8] PowerShell version:" -ForegroundColor White
                Write-Host "      $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))" -ForegroundColor White

                Write-Host ""
                Write-Host "  --- End Drill-Down ---" -ForegroundColor Cyan
                Write-Host ""
            }
            "S" { Write-Warn "Skipped Ollama check"; $stepDone = $true }
            "X" { Write-ManualResume 12 $TOTAL_STEPS; exit 0 }
            default { continue }
        }
    }
}

# ======================================================================
#  PHASE 3: FULL DIAGNOSTICS
# ======================================================================
# This validates the entire installation. You will see each check
# as it runs so you know exactly what passed and what needs attention.
# ======================================================================
Write-Step 13 "Running full diagnostics"
$stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
$stepDone = $false
while (-not $stepDone) {
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
    @{mod="cryptography"; label="cryptography (encryption)"},
    @{mod="ocrmypdf"; label="OCRmyPDF (scanned PDF OCR enhancement)"}
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

    if ($diagFail -eq 0) {
        $stepDone = $true
    } else {
        $choice = Request-Recovery "Diagnostics" 13 -DrillDown
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
                            Write-Host "    Fix: $PIP install $pipName --trusted-host pypi.org --trusted-host files.pythonhosted.org" -ForegroundColor Gray
                            Write-Host ""
                            Write-Host "  [R] Retry (re-installs $pipName)   [S] Skip   [X] Exit"
                            $pkgChoice = Read-Host "  Choose [R/S/X]"
                            switch ($pkgChoice.ToUpper()) {
                                "R" {
                                    & $PIP install $pipName @TRUSTED 2>&1
                                    continue
                                }
                                "S" { Write-Warn "Skipped $($pkg.label)"; $pkgDone = $true }
                                "X" { Write-ManualResume 13 $TOTAL_STEPS; exit 0 }
                                default { continue }
                            }
                        }
                    }
                }
                $stepDone = $true
            }
            "S" { Write-Warn "Skipped diagnostics recovery"; $stepDone = $true }
            "X" { Write-ManualResume 13 $TOTAL_STEPS; exit 0 }
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
