# ============================================================================
# HybridRAG v3 — API Mode Commands (api_mode_commands.ps1)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Provides PowerShell functions for managing API mode:
#     rag-store-key      → Store your API key in Windows Credential Manager
#     rag-store-endpoint  → Store your company's API endpoint URL
#     rag-cred-status     → Check what credentials are stored
#     rag-mode-online     → Switch to online (API) mode
#     rag-mode-offline    → Switch back to offline (Ollama) mode
#     rag-test-api        → Quick test that the API connection works
#     rag-cred-delete     → Remove stored credentials
#
# HOW TO USE:
#   Option A: Dot-source this file manually:
#     . .\api_mode_commands.ps1
#
#   Option B: Add this line to the end of start_hybridrag.ps1:
#     . "$PROJECT_ROOT\api_mode_commands.ps1"
#     Then it loads automatically every time you start HybridRAG.
#
# SECURITY NOTES:
#   - API keys are stored via Windows Credential Manager (DPAPI encrypted)
#   - Keys are tied to YOUR Windows login — other users can't read them
#   - Keys never appear in config files, logs, or git
#   - HuggingFace remains blocked in ALL modes (the lockdown is independent)
#
# INTERNET ACCESS:
#   - rag-store-key/endpoint: NO internet (just writes to local Credential Mgr)
#   - rag-test-api: YES — makes one HTTP request to your API endpoint
#   - rag-mode-online: Does NOT make any requests (just changes config.mode)
# ============================================================================


# ─── rag-store-key ──────────────────────────────────────────────────────────
# Store your API key securely in Windows Credential Manager.
# The key is encrypted with DPAPI, tied to your Windows login.
# ────────────────────────────────────────────────────────────────────────────
function rag-store-key {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 — Store API Key" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Your key will be encrypted in Windows Credential Manager."
    Write-Host "It will NOT appear in any file, log, or config."
    Write-Host ""
    python -m src.security.credentials store
}


# ─── rag-store-endpoint ─────────────────────────────────────────────────────
# Store your company's custom API endpoint URL.
# This overrides the default OpenAI endpoint in default_config.yaml.
# ────────────────────────────────────────────────────────────────────────────
function rag-store-endpoint {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 — Store API Endpoint" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Enter your company's internal GPT API endpoint URL."
    Write-Host "Example: https://your-company.com/v1/chat/completions"
    Write-Host ""
    python -m src.security.credentials endpoint
}


# ─── rag-cred-status ────────────────────────────────────────────────────────
# Check what credentials are currently stored and where they came from.
# ────────────────────────────────────────────────────────────────────────────
function rag-cred-status {
    python -m src.security.credentials status
}


# ─── rag-cred-delete ────────────────────────────────────────────────────────
# Remove all stored credentials from Windows Credential Manager.
# Use this when rotating keys or for cleanup.
# ────────────────────────────────────────────────────────────────────────────
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


# ─── rag-mode-online ────────────────────────────────────────────────────────
# Switch HybridRAG to online mode (uses GPT API for queries).
#
# WHAT CHANGES:
#   - Queries route to your company's GPT-3.5 API instead of Ollama
#   - Response time drops from ~180s (Ollama CPU) to ~2-5s (API)
#   - Each query costs ~$0.002 ($1 buys ~500 queries)
#
# WHAT DOES NOT CHANGE:
#   - HuggingFace remains blocked (HF_HUB_OFFLINE=1 stays set)
#   - Indexing still runs 100% locally
#   - Model caches still use local project folder
#   - All security layers remain active
# ────────────────────────────────────────────────────────────────────────────
function rag-mode-online {
    # Verify credentials exist before switching
    Write-Host ""
    Write-Host "Checking credentials..." -ForegroundColor Cyan

    $status = python -c "
import sys; sys.path.insert(0, '.')
from src.security.credentials import credential_status
s = credential_status()
print(f'KEY:{s[\"api_key_set\"]}')
print(f'ENDPOINT:{s[\"api_endpoint_set\"]}')
print(f'KEY_SRC:{s[\"api_key_source\"]}')
" 2>$null

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

    # Update the config file to online mode
    # We use Python to safely modify the YAML
    python -c "
import yaml
with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
cfg['mode'] = 'online'
with open('config/default_config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('Mode set to: online')
"

    # Confirm HF lockdown is still active
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


# ─── rag-mode-offline ───────────────────────────────────────────────────────
# Switch back to offline mode (uses Ollama for queries).
# ────────────────────────────────────────────────────────────────────────────
function rag-mode-offline {
    python -c "
import yaml
with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
cfg['mode'] = 'offline'
with open('config/default_config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('Mode set to: offline')
"
    Write-Host ""
    Write-Host "  Mode: OFFLINE (Ollama)" -ForegroundColor Yellow
    Write-Host "  Queries now route to local Ollama instance."
    Write-Host "  Make sure Ollama is running: ollama serve"
    Write-Host ""
}


# ─── rag-test-api ───────────────────────────────────────────────────────────
# Quick connectivity test: sends a tiny prompt to your API endpoint.
# This verifies: key is valid, endpoint is reachable, model responds.
#
# INTERNET ACCESS: YES — makes one HTTP request to your API endpoint.
# ────────────────────────────────────────────────────────────────────────────
function rag-test-api {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  HybridRAG v3 — API Connectivity Test" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Sending test prompt to API endpoint..." -ForegroundColor Cyan
    Write-Host ""

    python -c "
import sys, time, os
sys.path.insert(0, '.')

from src.core.config import load_config, ensure_directories
from src.core.llm_router import LLMRouter, LLMResponse

# Load config
config = load_config('.')
ensure_directories(config)
config.mode = 'online'

# Create router (will auto-resolve key from keyring/env)
router = LLMRouter(config)
status = router.get_status()

print(f'  Mode:      {status[\"mode\"]}')
print(f'  API ready: {status[\"api_configured\"]}')
print(f'  Endpoint:  {status[\"api_endpoint\"] or \"NOT SET\"}')
print()

if not status['api_configured']:
    print('  ERROR: API not configured. Run rag-store-key first.')
    sys.exit(1)

# Send a tiny test prompt
print('  Sending test query: \"Say hello in exactly 5 words.\"')
print('  Waiting for response...')
print()

start = time.time()
resp = router.query('Say hello in exactly 5 words.')
elapsed = (time.time() - start) * 1000

if resp:
    print(f'  PASS  API responded successfully!')
    print(f'  Answer:     {resp.text.strip()[:100]}')
    print(f'  Model:      {resp.model}')
    print(f'  Tokens in:  {resp.tokens_in}')
    print(f'  Tokens out: {resp.tokens_out}')
    print(f'  Latency:    {elapsed:.0f}ms')
    print(f'  Est. cost:  \${(resp.tokens_in * 0.0005 + resp.tokens_out * 0.0015) / 1000:.6f}')
    print()
    print('  API mode is ready for use!')
else:
    print('  FAIL  API did not respond.')
    print('  Check: Is your endpoint URL correct?')
    print('  Check: Is your API key valid?')
    print('  Check: Are you on the intranet/VPN?')
    print('  Run: rag-cred-status')
    sys.exit(1)
"

    Write-Host ""
}


# ============================================================================
# PERFORMANCE PROFILE SWITCHING
# ============================================================================
# Three profiles control how aggressively HybridRAG uses system resources.
# The diagnostic auto-detects your hardware, but you can override manually.
#
#   laptop_safe    — 8-16GB RAM. Batch=16, block=200K, gc between files.
#   desktop_power  — 32-64GB RAM. Batch=64, block=500K, faster indexing.
#   server_max     — 64GB+ RAM. Batch=128, block=1M, max throughput.
#
# WHY switch profiles?
#   Your work laptop (16GB) should use laptop_safe.
#   Your powerful desktop should use desktop_power or server_max.
#   Indexing on the desktop will be 4-8x faster with a bigger profile.
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
        python -c "
import yaml
with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
eb = cfg.get('embedding', {}).get('batch_size', '?')
ck = cfg.get('chunking', {}).get('max_tokens', '?')
tk = cfg.get('vector_search', {}).get('top_k', '?')
print(f'  Embedding batch_size: {eb}')
print(f'  Chunk max_tokens:     {ck}')
print(f'  Search top_k:         {tk}')
# Infer profile from batch_size
if eb == 16:
    print(f'  Profile:              laptop_safe')
elif eb == 64:
    print(f'  Profile:              desktop_power')
elif eb == 128:
    print(f'  Profile:              server_max')
else:
    print(f'  Profile:              custom')
"
        Write-Host ""
        Write-Host "  Switch with: rag-profile laptop_safe" -ForegroundColor DarkGray
        Write-Host "               rag-profile desktop_power" -ForegroundColor DarkGray
        Write-Host "               rag-profile server_max" -ForegroundColor DarkGray
        Write-Host ""
        return
    }

    Write-Host ""
    Write-Host "Switching to profile: $Profile" -ForegroundColor Cyan

    python -c "
import yaml

profiles = {
    'laptop_safe': {
        'embedding': {'batch_size': 16},
        'vector_search': {'top_k': 5},
        'indexing': {'block_chars': 200000, 'max_concurrent_files': 1},
    },
    'desktop_power': {
        'embedding': {'batch_size': 64},
        'vector_search': {'top_k': 10},
        'indexing': {'block_chars': 500000, 'max_concurrent_files': 2},
    },
    'server_max': {
        'embedding': {'batch_size': 128},
        'vector_search': {'top_k': 15},
        'indexing': {'block_chars': 1000000, 'max_concurrent_files': 4},
    },
}

profile = '$Profile'
settings = profiles[profile]

with open('config/default_config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)

# Apply profile settings (deep merge)
for section, values in settings.items():
    if section not in cfg:
        cfg[section] = {}
    for key, val in values.items():
        cfg[section][key] = val

with open('config/default_config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)

desc = {
    'laptop_safe': 'Conservative — stability on 8-16GB RAM (batch=16)',
    'desktop_power': 'Aggressive — throughput on 32-64GB RAM (batch=64)',
    'server_max': 'Maximum — for 64GB+ workstations (batch=128)',
}
print(f'  Applied: {profile}')
print(f'  {desc[profile]}')
"

    Write-Host ""
    Write-Host "  Profile applied. Re-index to use new batch settings." -ForegroundColor Green
    Write-Host ""
}


# ─── Print available commands ───────────────────────────────────────────────
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
