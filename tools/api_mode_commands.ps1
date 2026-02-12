# ============================================================================
# HybridRAG v3 - API Mode and Profile Commands (api_mode_commands.ps1)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Provides PowerShell functions for managing API mode and performance:
#     rag-store-key       Store your API key in Windows Credential Manager
#     rag-store-endpoint  Store your company API endpoint URL
#     rag-cred-status     Check what credentials are stored
#     rag-cred-delete     Remove stored credentials
#     rag-mode-online     Switch to online (API) mode
#     rag-mode-offline    Switch back to offline (Ollama) mode
#     rag-test-api        Quick test that the API connection works
#     rag-profile         View/switch performance profile
#
# TECHNICAL NOTE:
#   All Python logic lives in the scripts/ folder as separate .py files.
#   PowerShell only calls "python scripts\_something.py" with no inline
#   Python code. This prevents PowerShell from trying to parse Python
#   syntax and throwing errors.
#
# SECURITY NOTES:
#   API keys stored via Windows Credential Manager (DPAPI encrypted).
#   Keys tied to YOUR Windows login. Other users cannot read them.
#   Keys never appear in config files, logs, or git.
#   HuggingFace remains blocked in ALL modes.
#
# INTERNET ACCESS:
#   rag-store-key/endpoint: NO internet (local Credential Manager only)
#   rag-test-api: YES (makes one HTTP request to your API endpoint)
#   rag-mode-online: NO requests (just changes config.mode in YAML)
# ============================================================================


# ============================================================================
# CREDENTIAL MANAGEMENT COMMANDS
# ============================================================================


function rag-store-key {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 - Store API Key" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Your key will be encrypted in Windows Credential Manager."
    Write-Host "It will NOT appear in any file, log, or config."
    Write-Host ""
    python -m src.security.credentials store
}


function rag-store-endpoint {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 - Store API Endpoint" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Enter your company internal GPT API endpoint URL."
    Write-Host "Example: https://your-company.com/v1/chat/completions"
    Write-Host ""
    python -m src.security.credentials endpoint
}


function rag-cred-status {
    python -m src.security.credentials status
}


function rag-cred-delete {
    Write-Host ""
    $confirm = Read-Host "Delete stored API key and endpoint? (yes/no)"
    if ($confirm -eq "yes") {
        python -m src.security.credentials delete
        Write-Host "Credentials removed." -ForegroundColor Green
    } else {
        Write-Host "Cancelled." -ForegroundColor Yellow
    }
}


# ============================================================================
# MODE SWITCHING COMMANDS
# ============================================================================


function rag-mode-online {
    Write-Host ""
    Write-Host "Checking credentials..." -ForegroundColor Cyan

    $status = python "$PROJECT_ROOT\scripts\_check_creds.py" 2>$null

    $hasKey = $status | Select-String "KEY:True"
    $hasEndpoint = $status | Select-String "ENDPOINT:True"

    if (-not $hasKey) {
        Write-Host "  ERROR: No API key found!" -ForegroundColor Red
        Write-Host "  Run: rag-store-key" -ForegroundColor Yellow
        Write-Host ""
        return
    }

    if (-not $hasEndpoint) {
        Write-Host "  WARNING: No custom endpoint set." -ForegroundColor Yellow
        Write-Host "  Using default: api.openai.com" -ForegroundColor Yellow
        Write-Host "  To set your company endpoint: rag-store-endpoint" -ForegroundColor Yellow
        Write-Host ""
    }

    python "$PROJECT_ROOT\scripts\_set_online.py"

    Write-Host ""
    Write-Host "  Mode:                 ONLINE (API)" -ForegroundColor Green
    Write-Host "  HF_HUB_OFFLINE:       $env:HF_HUB_OFFLINE (still locked)" -ForegroundColor Green
    Write-Host "  TRANSFORMERS_OFFLINE:  $env:TRANSFORMERS_OFFLINE (still locked)" -ForegroundColor Green
    Write-Host "  Kill switch:          $env:HYBRIDRAG_NETWORK_KILL_SWITCH" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Online mode active. Queries now route to GPT API." -ForegroundColor Cyan
    Write-Host "  To switch back: rag-mode-offline" -ForegroundColor DarkGray
    Write-Host ""
}


function rag-mode-offline {
    python "$PROJECT_ROOT\scripts\_set_offline.py"
    Write-Host ""
    Write-Host "  Mode: OFFLINE (Ollama)" -ForegroundColor Yellow
    Write-Host "  Queries now route to local Ollama instance."
    Write-Host "  Make sure Ollama is running: ollama serve"
    Write-Host ""
}


# ============================================================================
# API CONNECTIVITY TEST
# ============================================================================


function rag-test-api {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 - API Connectivity Test" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Sending test prompt to API endpoint..." -ForegroundColor Cyan
    Write-Host ""

    python "$PROJECT_ROOT\scripts\_test_api.py"

    Write-Host ""
}


# ============================================================================
# PERFORMANCE PROFILE SWITCHING
# ============================================================================


function rag-profile {
    param(
        [Parameter(Position=0)]
        [ValidateSet("laptop_safe", "desktop_power", "server_max", "status")]
        [string]$Profile = "status"
    )

    if ($Profile -eq "status") {
        Write-Host ""
        Write-Host "Current performance profile:" -ForegroundColor Cyan

        python "$PROJECT_ROOT\scripts\_profile_status.py"

        Write-Host ""
        Write-Host "  Switch with: rag-profile laptop_safe" -ForegroundColor DarkGray
        Write-Host "               rag-profile desktop_power" -ForegroundColor DarkGray
        Write-Host "               rag-profile server_max" -ForegroundColor DarkGray
        Write-Host ""
        return
    }

    Write-Host ""
    Write-Host "Switching to profile: $Profile" -ForegroundColor Cyan

    python "$PROJECT_ROOT\scripts\_profile_switch.py" $Profile

    Write-Host ""
    Write-Host "  Profile applied. Re-index to use new batch settings." -ForegroundColor Green
    Write-Host ""
}


# ============================================================================
# STARTUP MESSAGE
# ============================================================================

Write-Host ""
Write-Host "API + Profile Commands loaded:" -ForegroundColor Cyan
Write-Host "  rag-store-key       Store API key (encrypted)" -ForegroundColor DarkGray
Write-Host "  rag-store-endpoint  Store custom API endpoint" -ForegroundColor DarkGray
Write-Host "  rag-cred-status     Check credential status" -ForegroundColor DarkGray
Write-Host "  rag-cred-delete     Remove stored credentials" -ForegroundColor DarkGray
Write-Host "  rag-mode-online     Switch to API mode" -ForegroundColor DarkGray
Write-Host "  rag-mode-offline    Switch to Ollama mode" -ForegroundColor DarkGray
Write-Host "  rag-test-api        Test API connectivity" -ForegroundColor DarkGray
Write-Host "  rag-profile         View/switch performance profile" -ForegroundColor DarkGray
Write-Host ""
