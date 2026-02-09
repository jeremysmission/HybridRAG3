# ============================================================================
# HybridRAG v3 - Start Script (Windows / PowerShell)
# ============================================================================
# Created:    2026-02-06
# Modified:   2026-02-08
# Purpose:    Educational / Personal Learning Project
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
# IMPORTANT - How to run this script:
#   You MUST "dot-source" it so the commands stay available:
#
#     . .\start_hybridrag.ps1        <-- CORRECT (note the dot-space)
#     .\start_hybridrag.ps1          <-- WRONG (commands disappear)
# ============================================================================

# ---- 1) PROJECT ROOT -------------------------------------------------------
$PROJECT_ROOT = $PSScriptRoot

# ---- 2) CONFIGURABLE PATHS -------------------------------------------------
# ============================================================================
# CONFIGURE THESE FOR YOUR MACHINE:
# ============================================================================
#
# DATA_DIR:   Where indexed data is stored (SQLite DB + embeddings).
#             OUTPUT of indexing. Should be on fast local storage.
#
# SOURCE_DIR: Where your raw documents live (PDFs, Word docs, etc.).
#             INPUT to indexing. Can be a local folder OR network drive.
#
# Examples:
#   Local folder:    $DATA_DIR   = "C:\Users\you\RAG_Data"
#   Network drive:   $SOURCE_DIR = "\\server\share\documents"
#   Mapped drive:    $SOURCE_DIR = "Z:\Program Documents"
#   Relative:        $DATA_DIR   = "$PROJECT_ROOT\data\indexed"
# ============================================================================

$DATA_DIR   = "$PROJECT_ROOT\data\indexed"
$SOURCE_DIR = "$PROJECT_ROOT\data\source"

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
    return
}
Set-Location $PROJECT_ROOT

# ---- 3) ACTIVATE .VENV ------------------------------------------------------
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
    Write-Host "  pip install -r requirements.txt"
    return
}

Write-Host "Activating .venv..." -ForegroundColor Green
.\.venv\Scripts\Activate.ps1

# ---- 4) SET PYTHONPATH -------------------------------------------------------
$env:PYTHONPATH = $PROJECT_ROOT

# ---- 5) VERIFY PYTHON -------------------------------------------------------
Write-Host ""
Write-Host "Python verification:" -ForegroundColor Cyan
python -c "import sys; print('Python exe:', sys.executable); print('Python version:', sys.version.split()[0])"

# ---- 6) NETWORK LOCKDOWN ----------------------------------------------------
# CRITICAL FOR RESTRICTED ENVIRONMENTS
#
# These environment variables prevent ALL AI/ML libraries from making
# outbound network requests. Forces fully offline operation.

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
$env:HF_HUB_DISABLE_PROGRESS_BARS = "1"
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

# Model cache locations (inside project folder — portable)
$env:SENTENCE_TRANSFORMERS_HOME = "$PROJECT_ROOT\.model_cache"
$env:HF_HOME = "$PROJECT_ROOT\.hf_cache"
$env:TORCH_HOME = "$PROJECT_ROOT\.torch_cache"

# Network kill switch (read by HybridRAG application code)
$env:HYBRIDRAG_NETWORK_KILL_SWITCH = "true"

Write-Host ""
Write-Host "Network lockdown:" -ForegroundColor Yellow
Write-Host "  HF_HUB_OFFLINE           = $env:HF_HUB_OFFLINE (blocked)"
Write-Host "  TRANSFORMERS_OFFLINE      = $env:TRANSFORMERS_OFFLINE (blocked)"
Write-Host "  HF_HUB_DISABLE_TELEMETRY = $env:HF_HUB_DISABLE_TELEMETRY (blocked)"
Write-Host "  NETWORK_KILL_SWITCH       = $env:HYBRIDRAG_NETWORK_KILL_SWITCH"
Write-Host "  Model cache: $env:SENTENCE_TRANSFORMERS_HOME"

# ---- 7) SET HYBRIDRAG ENVIRONMENT VARIABLES ---------------------------------
$env:HYBRIDRAG_DATA_DIR     = $DATA_DIR
$env:HYBRIDRAG_INDEX_FOLDER = $SOURCE_DIR
$env:HYBRIDRAG_INDEXED_DATA = $DATA_DIR

# Laptop-safe performance defaults
$env:HYBRIDRAG_EMBED_BATCH = "16"
$env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = "25000"
$env:HYBRIDRAG_SQLITE_COMMIT_EVERY = "10"

# ---- 8) ENSURE DATA DIRECTORIES EXIST --------------------------------------
foreach ($dir in @($DATA_DIR, $SOURCE_DIR)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Yellow
    }
}
foreach ($cache in @("$PROJECT_ROOT\.model_cache", "$PROJECT_ROOT\.hf_cache", "$PROJECT_ROOT\.torch_cache")) {
    if (-not (Test-Path $cache)) {
        New-Item -ItemType Directory -Path $cache -Force | Out-Null
    }
}

# ---- 9) PRINT CONFIGURED PATHS ----------------------------------------------
Write-Host ""
Write-Host "Configured storage paths:" -ForegroundColor Cyan
Write-Host "  HYBRIDRAG_DATA_DIR     = $env:HYBRIDRAG_DATA_DIR"
Write-Host "  HYBRIDRAG_INDEX_FOLDER = $env:HYBRIDRAG_INDEX_FOLDER"
Write-Host "  HYBRIDRAG_EMBED_BATCH  = $env:HYBRIDRAG_EMBED_BATCH"
Write-Host "  HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = $env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS"
Write-Host "  PYTHONPATH             = $env:PYTHONPATH"
Write-Host ""

python -c "
try:
    from src.core.config import load_config
    c = load_config('.')
    print('Config DB:', c.paths.database)
    print('Config embeddings cache:', c.paths.embeddings_cache)
except Exception as e:
    print('Note: config check skipped:', type(e).__name__ + ':', e)
"

# ---- 10) FRIENDLY COMMANDS ---------------------------------------------------
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
    python .\tests\cli_test_phase1.py --query $q
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

# ---- 11) DONE ---------------------------------------------------------------
Write-Host ""
Write-Host "Ready. Commands available:" -ForegroundColor Green
Write-Host "  rag-paths              Show configured paths + network status"
Write-Host "  rag-index              Start indexing"
Write-Host '  rag-query "question"   Query the index'
Write-Host "  rag-diag               Run diagnostics (add --verbose, --test-embed)"
Write-Host "  rag-status             Quick health check"
Write-Host ""
Write-Host "TIP: If commands don't work, make sure you ran:" -ForegroundColor Yellow
Write-Host '  . .\start_hybridrag.ps1    (with the dot-space at the start)' -ForegroundColor Yellow
Write-Host ""
