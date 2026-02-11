# ===========================================================================
# new_commands_for_start_hybridrag.ps1 -- New rag- Commands
# ===========================================================================
#
# WHAT THIS DOES (PLAIN ENGLISH):
#   Defines 5 new PowerShell commands (functions) that you can type at
#   the prompt. Each command starts with "rag-" so they are easy to
#   find and remember. These add diagnostic and maintenance tools to
#   your HybridRAG workflow.
#
# HOW TO USE:
#   TEMPORARY (lasts until you close PowerShell):
#       . .\tools\new_commands_for_start_hybridrag.ps1
#
#   PERMANENT (loads every time you start HybridRAG):
#       Add this one line to the bottom of start_hybridrag.ps1:
#           . .\tools\new_commands_for_start_hybridrag.ps1
#       OR copy-paste all the function blocks below into start_hybridrag.ps1
#
# THE NEW COMMANDS:
#   rag-debug-url          Pre-flight check: shows URL + headers without calling API
#   rag-test-api-verbose   Tests the API with full debug output
#   rag-fix-quotes         Fixes smart quotes in all project files
#   rag-detect-bad-chars   Scans for non-ASCII characters in code files
#   rag-enable-wal         Enables SQLite WAL mode for concurrent reads
#
# WHERE THIS GOES IN YOUR PROJECT:
#   D:\HybridRAG3\tools\new_commands_for_start_hybridrag.ps1
#
# POWERSHELL CONCEPT - DOT-SOURCING:
#   The ". .\" at the start is called "dot-sourcing." It means "run this
#   script INSIDE my current session." Without the dot, PowerShell runs it
#   in a separate session and the functions vanish when the script ends.
#   With the dot, the functions stay available in your terminal.
# ===========================================================================


# ---------------------------------------------------------------------------
# PROXY ENVIRONMENT VARIABLES (UNCOMMENT IF NEEDED)
# ---------------------------------------------------------------------------
# WHAT THESE DO:
#   If your corporate network requires a proxy server to reach the internet,
#   Python's requests library needs to know about it. These environment
#   variables tell Python which proxy to use.
#
#   HTTP_PROXY  = proxy for unencrypted traffic (rarely used now)
#   HTTPS_PROXY = proxy for encrypted traffic (this is the important one)
#   NO_PROXY    = addresses that should NOT go through the proxy
#                 (like localhost and your internal company domains)
#
# HOW TO USE:
#   1. Ask IT for your proxy server address and port
#   2. Uncomment the three lines below (remove the # at the start)
#   3. Replace the placeholder with your actual proxy address
#   4. Save and reload

# $env:HTTP_PROXY  = "http://your-proxy-server:8080"
# $env:HTTPS_PROXY = "http://your-proxy-server:8080"
# $env:NO_PROXY    = "localhost,127.0.0.1,.yourcompany.com"


# ===========================================================================
# COMMAND 1: rag-debug-url
# ===========================================================================
# WHAT IT DOES:
#   Shows exactly what URL and authentication headers WOULD be sent to
#   the API, WITHOUT actually making an API call. Like a pre-flight
#   checklist -- verify the plane is ready before takeoff.
#
# WHEN TO USE:
#   ALWAYS run this BEFORE rag-test-api-verbose. It takes zero API
#   credits and catches configuration mistakes immediately.
#
# WHAT TO LOOK FOR IN THE OUTPUT:
#   - "Detected provider" should say "azure"
#   - "Constructed URL" should match your Postman URL exactly
#   - "Auth header name" should say "api-key" (NOT "Authorization")
#   - No "PROBLEMS FOUND" at the bottom

function rag-debug-url {
    Write-Host "Running API configuration diagnostic..." -ForegroundColor Cyan

    # POWERSHELL CONCEPT - @' ... '@ (HERE-STRING):
    #   Everything between @' and '@ is literal text. We use this to
    #   write a block of Python code that PowerShell passes to Python.
    #   The single-quote version (@' '@) prevents PowerShell from
    #   trying to interpret $variables inside the Python code.
    $pyCode = @'
import sys
sys.path.insert(0, ".")
try:
    from src.security.credentials import get_api_key, get_api_endpoint
    endpoint = get_api_endpoint()
    api_key = get_api_key()
    if not endpoint:
        print("ERROR: No endpoint stored. Run rag-store-endpoint first.")
        sys.exit(1)
    if not api_key:
        print("ERROR: No API key stored. Run rag-store-key first.")
        sys.exit(1)
    from src.core.llm_router_fix import debug_api_config
    debug_api_config(endpoint, api_key)
except ImportError as e:
    # Fallback if modules not yet available
    print("=" * 60)
    print("FALLBACK DIAGNOSTIC (some modules not found)")
    print("Import error:", str(e))
    print("=" * 60)
    try:
        from src.security.credentials import get_api_key, get_api_endpoint
        ep = get_api_endpoint()
        key = get_api_key()
        print("Stored endpoint:", ep if ep else "EMPTY")
        print("Key present:", "YES" if key else "NO")
        if key:
            print("Key preview:", key[:4] + "..." + key[-4:])
        if ep:
            ep_lower = ep.lower()
            if "azure" in ep_lower or ".openai.azure.com" in ep_lower:
                print("Detected: AZURE -> Should use api-key header")
            else:
                print("Detected: OpenAI -> Should use Bearer header")
            if "/chat/completions" in ep:
                print("URL has /chat/completions: YES (complete)")
            else:
                print("URL has /chat/completions: NO (code will append path)")
    except ImportError:
        print("Cannot import credentials module.")
        print("Are you in the right directory? Is your venv active?")
    print("=" * 60)
except Exception as e:
    print("Error:", str(e))
'@
    # Run the Python code. "python -c" means "execute this string as code."
    python -c $pyCode
}


# ===========================================================================
# COMMAND 2: rag-test-api-verbose
# ===========================================================================
# WHAT IT DOES:
#   Makes a REAL API call with a simple test message and shows full
#   debug output including the exact URL, headers (key masked), and
#   the server's response.
#
# WHEN TO USE:
#   After rag-debug-url shows no problems. This actually contacts the
#   API server so it uses real API credits (one small call).
#
# IMPORTANT:
#   Make sure you are on the DIRECT corporate LAN (not VPN) for
#   the first test. VPN and LAN may have different API permissions.

function rag-test-api-verbose {
    Write-Host "Running verbose API test..." -ForegroundColor Cyan
    $pyCode = @'
import sys, json
sys.path.insert(0, ".")
try:
    from src.security.credentials import get_api_key, get_api_endpoint
    endpoint = get_api_endpoint()
    api_key = get_api_key()
    if not endpoint or not api_key:
        print("ERROR: Missing endpoint or key.")
        print("Run rag-store-endpoint and rag-store-key first.")
        sys.exit(1)
    from src.core.llm_router_fix import (
        call_llm_api, detect_provider, build_api_url, build_headers
    )
    # Show what we are about to send
    provider = detect_provider(endpoint)
    full_url = build_api_url(endpoint)
    headers = build_headers(endpoint, api_key)
    # Mask sensitive values for display
    safe_headers = dict(headers)
    if "api-key" in safe_headers:
        v = safe_headers["api-key"]
        safe_headers["api-key"] = v[:4] + "..." + v[-4:] if len(v) > 8 else "***"
    if "Authorization" in safe_headers:
        v = safe_headers["Authorization"]
        safe_headers["Authorization"] = v[:11] + "..." + v[-4:] if len(v) > 15 else "***"
    print("=" * 60)
    print("VERBOSE API TEST")
    print("=" * 60)
    print("Provider:", provider)
    print("Full URL:", full_url)
    print("Headers:", json.dumps(safe_headers, indent=2))
    print("=" * 60)
    print("Sending test message...")
    messages = [
        {"role": "system", "content": "Reply in one sentence."},
        {"role": "user", "content": "Say hello and confirm you are working."}
    ]
    result = call_llm_api(endpoint, api_key, messages, max_tokens=50)
    if result["error"] is None:
        print("")
        print("SUCCESS!")
        print("Answer:", result["answer"])
        print("Model:", result["model"])
        print("Latency:", round(result["latency"], 2), "seconds")
        print("Tokens:", result.get("usage", {}))
    else:
        print("")
        print("FAILED:", result["error"])
    print("=" * 60)
except ImportError as e:
    print("Import error:", str(e))
    print("Is llm_router_fix.py in src/core/? Is your venv active?")
except Exception as e:
    print("Error:", str(e))
    import traceback
    traceback.print_exc()
'@
    python -c $pyCode
}


# ===========================================================================
# COMMAND 3: rag-fix-quotes
# ===========================================================================
# WHAT IT DOES:
#   Calls the fix_quotes.ps1 script to scan all project files and
#   replace smart/curly quotes with straight quotes. Creates backups.
#
# WHEN TO USE:
#   After rag-detect-bad-chars finds problems, or anytime you suspect
#   copy-paste corruption.

function rag-fix-quotes {
    $toolPath = Join-Path (Get-Location) "tools\fix_quotes.ps1"
    if (Test-Path $toolPath) {
        & $toolPath -Path (Get-Location)
    } else {
        Write-Host "fix_quotes.ps1 not found in tools\" -ForegroundColor Red
        Write-Host "Expected at: $toolPath" -ForegroundColor Yellow
    }
}


# ===========================================================================
# COMMAND 4: rag-detect-bad-chars
# ===========================================================================
# WHAT IT DOES:
#   Calls detect_bad_chars.ps1 to scan for non-ASCII characters.
#   Does NOT modify any files -- just reports findings.
#
# WHEN TO USE:
#   After any copy-paste session. Before testing code. As a habit.

function rag-detect-bad-chars {
    $toolPath = Join-Path (Get-Location) "tools\detect_bad_chars.ps1"
    if (Test-Path $toolPath) {
        & $toolPath -Path (Get-Location)
    } else {
        Write-Host "detect_bad_chars.ps1 not found in tools\" -ForegroundColor Red
        Write-Host "Expected at: $toolPath" -ForegroundColor Yellow
    }
}


# ===========================================================================
# COMMAND 5: rag-enable-wal
# ===========================================================================
# WHAT IT DOES:
#   Enables WAL (Write-Ahead Logging) mode on your SQLite database.
#
# WHY WAL MODE MATTERS:
#   Without WAL: Only one process can read the database at a time.
#                If someone is reading, everyone else waits.
#   With WAL:    Unlimited readers can access the database simultaneously.
#                Only writers need to take turns.
#
#   For 10 users running queries at the same time, WAL is mandatory.
#   It is also safe and beneficial for single-user use.
#
# WHEN TO USE:
#   Run once after your database has been created (after indexing).
#   Safe to run multiple times -- it checks if WAL is already on.
#
# ALSO SETS:
#   synchronous=NORMAL  -> Faster writes, still crash-safe in WAL mode
#   busy_timeout=5000   -> Auto-retry for 5 seconds if database is busy
#   temp_store=MEMORY   -> Temp tables in RAM (faster)
#   optimize            -> Cleans up query planner stats

function rag-enable-wal {
    Write-Host "Enabling SQLite WAL mode..." -ForegroundColor Cyan
    $pyCode = @'
import sqlite3, os, sys
sys.path.insert(0, ".")

# Try to find the database path from config, fall back to default name
try:
    from src.core.config import load_config
    config = load_config()
    db_path = config.get("database", {}).get("path", "hybridrag.sqlite3")
except:
    db_path = "hybridrag.sqlite3"

if not os.path.exists(db_path):
    print("Database not found at:", db_path)
    print("Run indexing first to create the database.")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current mode
cursor.execute("PRAGMA journal_mode")
current = cursor.fetchone()[0]
print("Current journal mode:", current)

if current.lower() == "wal":
    print("WAL mode already enabled. No changes needed.")
else:
    cursor.execute("PRAGMA journal_mode=WAL")
    result = cursor.fetchone()[0]
    print("Changed journal mode to:", result)

# Set performance pragmas
cursor.execute("PRAGMA synchronous=NORMAL")
cursor.execute("PRAGMA busy_timeout=5000")
cursor.execute("PRAGMA temp_store=MEMORY")
cursor.execute("PRAGMA optimize")

print("Performance pragmas set:")
print("  synchronous = NORMAL (faster, crash-safe in WAL)")
print("  busy_timeout = 5000ms (auto-retry on lock)")
print("  temp_store = MEMORY (faster temp tables)")
print("  optimize = done (query planner updated)")
print("SQLite is now ready for concurrent reads.")

conn.close()
'@
    python -c $pyCode
}


# ---------------------------------------------------------------------------
# PRINT CONFIRMATION -- Shows the user what commands are now available
# ---------------------------------------------------------------------------

Write-Host "" -ForegroundColor White
Write-Host "===== New HybridRAG Commands Loaded =====" -ForegroundColor Green
Write-Host "  rag-debug-url          Pre-flight API config check" -ForegroundColor White
Write-Host "  rag-test-api-verbose   Test API with full debug output" -ForegroundColor White
Write-Host "  rag-fix-quotes         Fix smart quotes in all files" -ForegroundColor White
Write-Host "  rag-detect-bad-chars   Scan for bad characters" -ForegroundColor White
Write-Host "  rag-enable-wal         Enable SQLite WAL mode" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green
