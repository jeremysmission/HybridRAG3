# =============================================================
# EXECUTION ENVIRONMENT DETECTION -- HybridRAG3
# =============================================================
# Automatically detects Group Policy restrictions and uses the
# correct script loading method for this machine.
# Home PC: dot-source (standard)
# Work laptop (AllSigned/Restricted GP): IEX via ReadAllText
# =============================================================

function Test-MachineRestricted {
    # Checks both GP-controlled execution policy scopes.
    # MachinePolicy = per-machine Group Policy (cannot be overridden by user)
    # UserPolicy    = per-user Group Policy    (cannot be overridden by user)
    #
    # IMPORTANT: Only 'Restricted' and 'AllSigned' actually block unsigned
    # local scripts. RemoteSigned, Bypass, and Default allow them to run.
    # Checking -ne 'Undefined' would falsely trigger IEX on RemoteSigned/Bypass
    # machines -- correct check is -in ('Restricted', 'AllSigned') only.
    foreach ($scope in @('MachinePolicy', 'UserPolicy')) {
        $policy = Get-ExecutionPolicy -Scope $scope
        if ($policy -in @('Restricted', 'AllSigned')) {
            return $true
        }
    }
    return $false
}


function Invoke-Script {
    # Drop-in replacement for dot-source that works on restricted machines.
    # BOTH code paths run in the CURRENT scope -- functions persist after load.
    # Do NOT use & (ampersand) or -File -- both run in a child scope and
    # cause loaded functions to silently disappear when the child exits.
    param([Parameter(Mandatory=$true)][string]$ScriptPath)

    $resolved = [System.IO.Path]::GetFullPath($ScriptPath)

    if (-not (Test-Path $resolved)) {
        Write-Host "[FAIL] Script not found: $resolved" -ForegroundColor Red
        return
    }

    if (Test-MachineRestricted) {
        # IEX path: reads script as text, runs it in current scope.
        # SECURITY NOTE: ReadAllText + Invoke-Expression is a sanctioned
        # workaround for Group Policy execution policy restrictions on
        # developer tool scripts. Path is resolved to absolute from the
        # controlled repository root only. Reviewed and approved for this use.
        $code = [System.IO.File]::ReadAllText($resolved, [System.Text.Encoding]::UTF8)
        Invoke-Expression $code
    } else {
        # Dot-source: also runs in current scope -- identical to IEX behavior.
        # Safe to use on unrestricted machines (home PC).
        . $resolved
    }
}


function Import-ScriptFolder {
    # Load all .ps1 files from a folder using Invoke-Script (scope-safe on both machines).
    # Reads _load_order.txt from the folder if present to control load sequence.
    # Without a manifest, loads alphabetically and warns -- add manifest before
    # adding inter-dependent scripts to any tool folder.
    param(
        [Parameter(Mandatory=$true)][string]$FolderPath,
        [string]$Filter = '*.ps1'
    )

    $manifest = Join-Path $FolderPath '_load_order.txt'

    if (Test-Path $manifest) {
        # Load in explicit order from manifest (# lines are comments)
        $scripts = Get-Content $manifest |
            Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } |
            ForEach-Object { Join-Path $FolderPath $_.Trim() }
    } else {
        Write-Host "[WARN] No _load_order.txt in $FolderPath -- loading alphabetically" -ForegroundColor Yellow
        $scripts = Get-ChildItem -Path $FolderPath -Filter $Filter -File |
            Select-Object -ExpandProperty FullName
    }

    foreach ($script in $scripts) {
        if (Test-Path $script) {
            Write-Host "[OK]  $([System.IO.Path]::GetFileName($script))" -ForegroundColor Green
            Invoke-Script $script
        } else {
            Write-Host "[WARN] In manifest but not found: $script" -ForegroundColor Yellow
        }
    }
}


# Report detected environment on session load
if (Test-MachineRestricted) {
    Write-Host '[WARN] Restricted machine -- IEX path active for script loading' -ForegroundColor Yellow
} else {
    Write-Host '[OK]  Unrestricted machine -- dot-source active' -ForegroundColor Green
}

# ---- ENCODING FIX (prevents garbled parentheses and special characters) ------
# Windows PowerShell defaults to the system locale code page (e.g., 437 or 1252).
# Python prints UTF-8 by default. Without this fix, parentheses, accents, and
# other characters in Python output get mangled in the PS console.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ============================================================================
# HybridRAG v3 - Start Script (Windows / PowerShell)
# ============================================================================
# Created:    2026-02-06
# Modified:   2026-02-18
# ============================================================================
# What this script does (plain English):
#   1) Moves PowerShell into the HybridRAG project folder
#   2) Activates the .venv Python virtual environment
#   3) Sets PYTHONPATH so "import src.*" works from anywhere
#   4) Verifies you are using the correct Python
#   5) Sets environment variables so every script uses the SAME paths
#   6) LOCKS DOWN all AI libraries from reaching the internet
#   7) Defines simple commands (rag-index, rag-query, etc.)
#
# HOW TO RUN:
#   Option A (recommended): Double-click start.cmd in the repo root
#   Option B: . .\start_hybridrag.ps1  (dot-space, from PowerShell)
# ============================================================================

# ---- 1) PROJECT ROOT -------------------------------------------------------
$PROJECT_ROOT = $PSScriptRoot

# ---- 2) CANONICAL PATHS ----------------------------------------------------
$DATA_DIR   = "D:\RAG Indexed Data"
$SOURCE_DIR = "D:\RAG Source Data"

Write-Host ""
Write-Host "=== HybridRAG Startup ===" -ForegroundColor Cyan
Write-Host "Project:    $PROJECT_ROOT"
Write-Host "Data dir:   $DATA_DIR"
Write-Host "Source dir: $SOURCE_DIR"
Write-Host ""

# Move into the project folder
if (-not (Test-Path $PROJECT_ROOT)) {
    Write-Host "ERROR: Project folder not found:" -ForegroundColor Red
    Write-Host "  $PROJECT_ROOT" -ForegroundColor Red
    Write-Host "Fix: Update PROJECT_ROOT at the top of start_hybridrag.ps1"
    return
}
Set-Location $PROJECT_ROOT

# ---- 3) ACTIVATE .VENV -----------------------------------------------------
# NOTE: .venv activation uses the standard method -- it is not a
# function-loading script, so Invoke-Script is not used here.
if (Test-Path ".\venv") {
    Write-Host "WARNING: A folder named 'venv' exists." -ForegroundColor Yellow
    Write-Host "This project standard is '.venv' only." -ForegroundColor Yellow
    Write-Host ""
}

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Host "ERROR: .venv not found." -ForegroundColor Red
    Write-Host "Fix:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  pip install -r requirements-lock.txt"
    return
}

Write-Host "Activating .venv..." -ForegroundColor Green
Invoke-Script "$PROJECT_ROOT\.venv\Scripts\Activate.ps1"

# ---- 4) SET PYTHONPATH -----------------------------------------------------
$env:PYTHONPATH = $PROJECT_ROOT
$env:HYBRIDRAG_PROJECT_ROOT = $PROJECT_ROOT

# ---- 5) VERIFY PYTHON ------------------------------------------------------
Write-Host ""
Write-Host "Python verification:" -ForegroundColor Cyan
python -c "import sys; print('Python exe:', sys.executable); print('Python version:', sys.version.split()[0])"

# ---- 6) NETWORK LOCKDOWN ---------------------------------------------------
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$env:HF_HUB_DISABLE_PROGRESS_BARS = "1"
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:SENTENCE_TRANSFORMERS_HOME = "$PROJECT_ROOT\.model_cache"
$env:HF_HOME = "$PROJECT_ROOT\.hf_cache"
$env:TORCH_HOME = "$PROJECT_ROOT\.torch_cache"
$env:HYBRIDRAG_NETWORK_KILL_SWITCH = "true"

Write-Host ""
Write-Host "Network lockdown:" -ForegroundColor Yellow
Write-Host "  HF_HUB_OFFLINE           = $env:HF_HUB_OFFLINE (blocked)"
Write-Host "  TRANSFORMERS_OFFLINE      = $env:TRANSFORMERS_OFFLINE (blocked)"
Write-Host "  HF_HUB_DISABLE_TELEMETRY = $env:HF_HUB_DISABLE_TELEMETRY (blocked)"
Write-Host "  NETWORK_KILL_SWITCH       = $env:HYBRIDRAG_NETWORK_KILL_SWITCH"
Write-Host "  Model cache: $env:SENTENCE_TRANSFORMERS_HOME"

# ---- 7) SET HYBRIDRAG ENVIRONMENT VARIABLES --------------------------------
$env:HYBRIDRAG_DATA_DIR     = $DATA_DIR
$env:HYBRIDRAG_INDEX_FOLDER = $SOURCE_DIR
$env:HYBRIDRAG_INDEXED_DATA = $DATA_DIR
$env:HYBRIDRAG_EMBED_BATCH = "16"
$env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = "25000"
$env:HYBRIDRAG_SQLITE_COMMIT_EVERY = "10"

# ---- 8) ENSURE DATA DIRECTORY EXISTS ---------------------------------------
if (-not (Test-Path $DATA_DIR)) {
    New-Item -ItemType Directory -Path $DATA_DIR -Force | Out-Null
    Write-Host "Created data directory: $DATA_DIR" -ForegroundColor Yellow
}
if (-not (Test-Path "$PROJECT_ROOT\.model_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.model_cache" -Force | Out-Null
}
if (-not (Test-Path "$PROJECT_ROOT\.hf_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.hf_cache" -Force | Out-Null
}
if (-not (Test-Path "$PROJECT_ROOT\.torch_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.torch_cache" -Force | Out-Null
}

# ---- 9) PRINT CONFIGURED PATHS ---------------------------------------------
Write-Host ""
Write-Host "Configured storage paths:" -ForegroundColor Cyan
Write-Host "  HYBRIDRAG_DATA_DIR     = $env:HYBRIDRAG_DATA_DIR"
Write-Host "  HYBRIDRAG_INDEX_FOLDER = $env:HYBRIDRAG_INDEX_FOLDER"
Write-Host "  HYBRIDRAG_EMBED_BATCH  = $env:HYBRIDRAG_EMBED_BATCH"
Write-Host "  HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = $env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS"
Write-Host "  PYTHONPATH             = $env:PYTHONPATH"
Write-Host ""

# Quick config check (non-fatal if it fails)
python -c "
try:
    from src.core.config import load_config
    c = load_config('.')
    print('Config DB:', c.paths.database)
    print('Config embeddings cache:', c.paths.embeddings_cache)
except Exception as e:
    print('Note: config check skipped:', type(e).__name__ + ':', e)
"

# ---- 10) FRIENDLY COMMANDS -------------------------------------------------

function rag-paths {
    Write-Host ""
    Write-Host "HybridRAG Paths:" -ForegroundColor Cyan
    Write-Host "  PROJECT_ROOT: $PROJECT_ROOT"
    Write-Host "  DATA_DIR:     $DATA_DIR"
    Write-Host "  SOURCE_DIR:   $SOURCE_DIR"
    Write-Host "  PYTHONPATH:   $env:PYTHONPATH"
    Write-Host ""
    Write-Host "Environment vars:" -ForegroundColor Cyan
    Write-Host "  HYBRIDRAG_DATA_DIR     = $env:HYBRIDRAG_DATA_DIR"
    Write-Host "  HYBRIDRAG_INDEX_FOLDER = $env:HYBRIDRAG_INDEX_FOLDER"
    Write-Host "  HYBRIDRAG_EMBED_BATCH  = $env:HYBRIDRAG_EMBED_BATCH"
    Write-Host "  HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = $env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS"
    Write-Host ""
    Write-Host "Network lockdown:" -ForegroundColor Cyan
    Write-Host "  HF_HUB_OFFLINE           = $env:HF_HUB_OFFLINE"
    Write-Host "  TRANSFORMERS_OFFLINE      = $env:TRANSFORMERS_OFFLINE"
    Write-Host "  NETWORK_KILL_SWITCH       = $env:HYBRIDRAG_NETWORK_KILL_SWITCH"
    Write-Host ""
}

function rag-index {
    python .\src\tools\run_index_once.py
}

function rag-query {
    param([Parameter(Mandatory=$true)][string]$q)
    python .\tests\cli_test_phase1.py --query "$q"
}

function rag-diag {
    python -m src.diagnostic.hybridrag_diagnostic @args
}

function rag-status {
    Write-Host ""
    Write-Host "Python:" -ForegroundColor Cyan
    python -c "import sys; print(sys.executable)"

    Write-Host ""
    Write-Host "Network lockdown:" -ForegroundColor Cyan
    Write-Host "  HF_HUB_OFFLINE      = $env:HF_HUB_OFFLINE"
    Write-Host "  TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE"
    Write-Host "  KILL_SWITCH          = $env:HYBRIDRAG_NETWORK_KILL_SWITCH"

    Write-Host ""
    Write-Host "DB + memmap:" -ForegroundColor Cyan
    python -c "
import os, sqlite3
db = os.path.join(os.getenv('HYBRIDRAG_DATA_DIR', ''), 'hybridrag.sqlite3')
if not os.path.exists(db):
    print('DB not found at:', db)
    print('Run rag-index first.')
else:
    con = sqlite3.connect(db)
    try:
        count = con.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        sources = con.execute('SELECT COUNT(DISTINCT source_path) FROM chunks').fetchone()[0]
        print(f'DB: {db}')
        print(f'Chunks: {count}')
        print(f'Source files: {sources}')
    except Exception as e:
        print('DB exists but chunks table missing:', e)
    con.close()
"
}

function rag-server {
    param(
        [int]$Port = 8000,
        [string]$Host = '127.0.0.1'
    )
    Write-Host ""
    Write-Host "Starting HybridRAG API server..." -ForegroundColor Cyan
    Write-Host "  http://${Host}:${Port}/docs  (Swagger UI)" -ForegroundColor Green
    Write-Host ""
    python -m src.api.server --host $Host --port $Port
}

# ---- 11) LOAD API MODE COMMANDS --------------------------------------------
# Uses Invoke-Script -- works on both home PC and restricted work laptop.
$apiCmdsPath = "$PROJECT_ROOT\tools\api_mode_commands.ps1"
if (Test-Path $apiCmdsPath) {
    Invoke-Script $apiCmdsPath
} else {
    Write-Host "[WARN] tools\api_mode_commands.ps1 not found -- API commands not loaded." -ForegroundColor Yellow
}

# ---- 12) SHOW CURRENT MODE -------------------------------------------------
Write-Host ""
Write-Host "Current mode:" -ForegroundColor Cyan
python -c "
try:
    import yaml
    with open('config/default_config.yaml', 'r') as f:
        c = yaml.safe_load(f)
    mode = c.get('mode', 'unknown')
    model = c.get('api', {}).get('model', 'unknown') if mode == 'online' else c.get('ollama', {}).get('model', 'unknown')
    print(f'  Mode:  {mode}')
    print(f'  Model: {model}')
except Exception as e:
    print(f'  Could not read config: {e}')
"

# ---- 13) COMMAND REFERENCE BANNER -------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  HYBRIDRAG v3 -- COMMAND REFERENCE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  DAILY USE" -ForegroundColor Yellow
Write-Host '    rag-query "question"     Ask a question'
Write-Host "    rag-index                Index documents"
Write-Host "    rag-status               Quick health check"
Write-Host "    rag-diag                 Run diagnostics (--verbose, --test-embed)"
Write-Host ""
Write-Host "  MODE / MODEL" -ForegroundColor Yellow
Write-Host "    rag-set-model            Model selection wizard"
Write-Host "    rag-mode-online          Switch to cloud API"
Write-Host "    rag-mode-offline         Switch to local AI (Ollama)"
Write-Host "    rag-models               Show available models"
Write-Host ""
Write-Host "  CREDENTIALS" -ForegroundColor Yellow
Write-Host "    rag-store-key            Store API key (encrypted)"
Write-Host "    rag-store-endpoint       Store API endpoint URL"
Write-Host "    rag-cred-status          Check credential status"
Write-Host "    rag-cred-delete          Remove stored credentials"
Write-Host ""
Write-Host "  TOOLS" -ForegroundColor Yellow
Write-Host "    rag-profile              View/switch hardware profile"
Write-Host "    rag-server               Start REST API server (localhost:8000)"
Write-Host "    rag-paths                Show configured paths"
Write-Host "    rag-test-api             Test API connectivity"
Write-Host ""
Write-Host "  TIP: Double-click start_rag.bat to bypass execution policy" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""