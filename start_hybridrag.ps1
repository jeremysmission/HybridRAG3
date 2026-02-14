
# ============================================================================
# HybridRAG v3 - Start Script (Windows / PowerShell)
# ============================================================================
# Created:    2026-02-06
# Modified:   2026-02-08
# Distribution: Internal / Research Use
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
#
#   Why? PowerShell normally runs scripts in a "child scope" that
#   gets thrown away when the script finishes. The leading dot tells
#   PowerShell to run it in YOUR session so the functions persist.
# ============================================================================

# ---- 1) PROJECT ROOT -------------------------------------------------------
# $PSScriptRoot auto-detects the folder this script lives in, so if you
# move the project to a USB drive or another machine, it just works.
$PROJECT_ROOT = $PSScriptRoot

# ---- 2) CANONICAL PATHS (the important standard) ---------------------------
# DATA_DIR: Where indexed data is stored (SQLite DB + embedding memmap files).
#   This is the OUTPUT of indexing. It should be on a fast local drive.
#
# SOURCE_DIR: Where your raw documents live (PDFs, Word docs, etc.).
#   This is the INPUT to indexing. Can be a network drive or local folder.
#
# Why separate folders?
#   - Source files can be huge (100GB+), stored on network/OneDrive
#   - Indexed data must be fast local storage for good search performance
#   - Keeps "originals" completely separate from "derived data"
#   - You can delete indexed data and re-create it; you can't recreate originals
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

# ---- 3) ACTIVATE .VENV ------------------------------------------------------
# We standardize on ".venv" for this project (not "venv").
if (Test-Path ".\venv") {
    Write-Host "WARNING: A folder named 'venv' exists." -ForegroundColor Yellow
    Write-Host "This project standard is '.venv' only." -ForegroundColor Yellow
    Write-Host "If 'venv' was created by mistake, delete it after confirming .venv works:"
    Write-Host "  Remove-Item -Recurse -Force venv"
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
.\.venv\Scripts\Activate.ps1

# ---- 4) SET PYTHONPATH -------------------------------------------------------
# This ensures "from src.core.config import ..." works no matter how you
# run a script (python file.py, python -m module, from any subfolder).
# Without this, scripts fail with "ModuleNotFoundError: No module named 'src'"
# $PSScriptRoot resolves to the folder this script lives in, so it works
# on any drive letter (C:, D:, E:, USB, etc.)
$env:PYTHONPATH = $PROJECT_ROOT

# ---- 5) VERIFY PYTHON -------------------------------------------------------
Write-Host ""
Write-Host "Python verification:" -ForegroundColor Cyan
python -c "import sys; print('Python exe:', sys.executable); print('Python version:', sys.version.split()[0])"

# ---- 6) NETWORK LOCKDOWN ----------------------------------------------------
# CRITICAL FOR RESTRICTED ENVIRONMENTS
#
# These environment variables prevent ALL AI/ML libraries from making
# outbound network requests. Without these, HuggingFace libraries will
# attempt to:
#   - Check for model updates (huggingface_hub)
#   - Download tokenizer files (transformers)
#   - Send usage telemetry (huggingface_hub)
#
# This caused IT security alerts and is unacceptable in a restricted
# environment. These variables force fully offline operation.
#
# To temporarily re-enable network access (e.g., for model downloads
# on a non-restricted machine), set these to "0" or remove them.
# Future GUI admin panel will provide a toggle for this.

# -- HuggingFace / Transformers lockdown --
$env:HF_HUB_OFFLINE = "1"                    # Block all huggingface_hub network calls
$env:TRANSFORMERS_OFFLINE = "1"               # Block all transformers network calls
$env:HF_HUB_DISABLE_TELEMETRY = "1"          # Kill usage tracking / analytics
$env:HF_HUB_DISABLE_PROGRESS_BARS = "1"      # Prevent download attempt UI
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = "1"     # Don't look for HF login tokens
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"   # Suppress symlink warnings
$env:NO_PROXY = "localhost,127.0.0.1"        # Stops proxy from being pinged

# -- Model cache location --
# Forces sentence-transformers to look for models HERE instead of
# the default user cache folder. Copy your model files here for
# offline operation.
$env:SENTENCE_TRANSFORMERS_HOME = "$PROJECT_ROOT\.model_cache"
$env:HF_HOME = "$PROJECT_ROOT\.hf_cache"
$env:TORCH_HOME = "$PROJECT_ROOT\.torch_cache"

# -- Network kill switch (read by HybridRAG code) --
# When "true", the application code itself refuses to make HTTP calls
# even if the environment variables above are somehow bypassed.
$env:HYBRIDRAG_NETWORK_KILL_SWITCH = "true"

Write-Host ""
Write-Host "Network lockdown:" -ForegroundColor Yellow
Write-Host "  HF_HUB_OFFLINE           = $env:HF_HUB_OFFLINE (blocked)"
Write-Host "  TRANSFORMERS_OFFLINE      = $env:TRANSFORMERS_OFFLINE (blocked)"
Write-Host "  HF_HUB_DISABLE_TELEMETRY = $env:HF_HUB_DISABLE_TELEMETRY (blocked)"
Write-Host "  NETWORK_KILL_SWITCH       = $env:HYBRIDRAG_NETWORK_KILL_SWITCH"
Write-Host "  Model cache: $env:SENTENCE_TRANSFORMERS_HOME"

# ---- 7) SET HYBRIDRAG ENVIRONMENT VARIABLES ---------------------------------
# These env vars are read by HybridRAG's Config system (src/core/config.py).
# They override whatever is in config/default_config.yaml.
#
# Why env vars instead of just YAML?
#   - Different machines have different paths
#   - You never commit machine-specific paths to git
#   - YAML has the defaults; env vars have the overrides
$env:HYBRIDRAG_DATA_DIR     = $DATA_DIR
$env:HYBRIDRAG_INDEX_FOLDER = $SOURCE_DIR

# Also set HYBRIDRAG_INDEXED_DATA for any scripts that use the older variable name
$env:HYBRIDRAG_INDEXED_DATA = $DATA_DIR

# Laptop-safe performance defaults
# EMBED_BATCH: How many text chunks to embed at once.
#   Higher = faster but uses more RAM. 16 is safe for 8GB laptops.
$env:HYBRIDRAG_EMBED_BATCH = "16"

# RETRIEVAL_BLOCK_ROWS: How many embedding rows to load per search block.
#   Controls RAM during search. 25000 rows * 384 dims * 4 bytes = ~37MB per block.
$env:HYBRIDRAG_RETRIEVAL_BLOCK_ROWS = "25000"

# SQLITE_COMMIT_EVERY: Commit to disk after this many files.
#   Lower = safer (less data lost on crash), Higher = faster indexing.
$env:HYBRIDRAG_SQLITE_COMMIT_EVERY = "10"

# ---- 8) ENSURE DATA DIRECTORY EXISTS ----------------------------------------
# Create the indexed data folder if it doesn't exist yet.
# Without this, the first indexing run would fail.
if (-not (Test-Path $DATA_DIR)) {
    New-Item -ItemType Directory -Path $DATA_DIR -Force | Out-Null
    Write-Host "Created data directory: $DATA_DIR" -ForegroundColor Yellow
}

# Create model cache directories if they don't exist
if (-not (Test-Path "$PROJECT_ROOT\.model_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.model_cache" -Force | Out-Null
}
if (-not (Test-Path "$PROJECT_ROOT\.hf_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.hf_cache" -Force | Out-Null
}
if (-not (Test-Path "$PROJECT_ROOT\.torch_cache")) {
    New-Item -ItemType Directory -Path "$PROJECT_ROOT\.torch_cache" -Force | Out-Null
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

# ---- 10) FRIENDLY COMMANDS ---------------------------------------------------
# These are PowerShell functions that save you from typing long commands.
# They only exist in this session (that's why dot-sourcing matters).

function rag-paths {
    <#
    .SYNOPSIS
    Print all configured paths and environment variables.
    Use this to verify everything is pointing where you expect.
    #>
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
    <#
    .SYNOPSIS
    Run indexing against your configured source folder.
    This is the command you'll use for the week-long indexing job.
    #>
    python .\src\tools\run_index_once.py
}

function rag-query {
    <#
    .SYNOPSIS
    Run a query against the indexed database.
    Example: rag-query "Summarize the manual"
    #>
    param([Parameter(Mandatory=$true)][string]$q)
    python .\tests\cli_test_phase1.py --query $q
}

function rag-diag {
    <#
    .SYNOPSIS
    Run the diagnostic tool to check system health.
    Example: rag-diag
    Example: rag-diag --verbose
    Example: rag-diag --test-embed
    #>
    python -m src.diagnostic.hybridrag_diagnostic @args
}

function rag-status {
    <#
    .SYNOPSIS
    Quick health check: Python path, DB stats, memmap status, network status.
    #>
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
. "$PROJECT_ROOT\tools\api_mode_commands.ps1"


