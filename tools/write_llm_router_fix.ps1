# ===========================================================================
# write_llm_router_fix.ps1 -- File Writer (Bypasses Clipboard)
# ===========================================================================
#
# WHAT THIS SCRIPT DOES (PLAIN ENGLISH):
#   Writes the llm_router_fix.py Python file directly to your hard drive
#   using a .NET method that completely BYPASSES the Windows clipboard.
#
#   Why bypass the clipboard?
#   When you copy-paste code, Windows can silently corrupt characters:
#     - Straight quotes " become curly quotes (breaks Python)
#     - Files get saved with a BOM (invisible bytes Python chokes on)
#     - Special characters get mangled by encoding conversion
#   By writing directly to disk, none of that happens.
#
# HOW TO RUN:
#   Option 1: Right-click in File Explorer -> "Run with PowerShell"
#   Option 2: In PowerShell terminal:
#       cd D:\HybridRAG3
#       . .\tools\write_llm_router_fix.ps1
#
#   The dot-space ". .\" is called "dot-sourcing" -- it means "run this
#   script inside my current session." Without the dot, the script runs
#   in a separate session and everything disappears after.
#
# WHAT HAPPENS WHEN YOU RUN IT:
#   1. Searches for your HybridRAG project folder
#   2. Backs up any existing llm_router.py
#   3. Writes llm_router_fix.py to src\core\ with correct encoding
#   4. Runs a Python syntax check to verify the file is valid
#   5. Prints next steps
#
# WHERE THE FILE ENDS UP:
#   D:\HybridRAG3\src\core\llm_router_fix.py
# ===========================================================================


# ---------------------------------------------------------------------------
# STEP 1: FIND YOUR PROJECT DIRECTORY
# ---------------------------------------------------------------------------
# We check common locations. The script uses the first one it finds.
#
# POWERSHELL CONCEPT - @(...):
#   Creates an "array" (a list of items). Each quoted string is one item.
#
# POWERSHELL CONCEPT - $env:USERPROFILE:
#   A built-in variable containing your Windows user folder.
#   Example: C:\Users\Jeremy
#   We use it because different PCs have different usernames.

$projectDirs = @(
    "D:\HybridRAG3",
    "D:\HybridRAG2",
    "$env:USERPROFILE\OneDrive\Desktop\AI Project\HybridRAG",
    "$env:USERPROFILE\Desktop\HybridRAG3",
    "$env:USERPROFILE\Desktop\HybridRAG"
)

# $null means "empty / not set yet"
$projectRoot = $null

# POWERSHELL CONCEPT - foreach:
#   Goes through each item in the list, one at a time.
#   Each time through the loop, $dir holds the current item.
foreach ($dir in $projectDirs) {
    $expanded = [System.Environment]::ExpandEnvironmentVariables($dir)
    # Test-Path checks if a folder or file actually exists on disk
    if (Test-Path $expanded) {
        $projectRoot = $expanded
        Write-Host "[OK] Found project at: $projectRoot" -ForegroundColor Green
        break  # Stop looking -- we found it
    }
}

# If none of the locations existed, use the current directory
if (-not $projectRoot) {
    Write-Host "[!!] Could not auto-detect project directory." -ForegroundColor Red
    Write-Host "     Writing to current directory instead." -ForegroundColor Yellow
    $projectRoot = Get-Location
}


# ---------------------------------------------------------------------------
# STEP 2: CREATE TARGET DIRECTORY AND BACKUP
# ---------------------------------------------------------------------------
# Join-Path safely combines folder paths (handles slashes correctly).

$targetDir = Join-Path $projectRoot "src\core"

# Create the directory if it doesn't exist.
# -Force means "create parent folders too, don't complain if it exists."
# | Out-Null means "throw away the output text" (we don't need to see it).
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Write-Host "[OK] Created directory: $targetDir" -ForegroundColor Green
}

$targetFile = Join-Path $targetDir "llm_router_fix.py"

# Back up any existing llm_router.py (not the fix -- the original)
$existingRouter = Join-Path $targetDir "llm_router.py"
if (Test-Path $existingRouter) {
    $backupName = "llm_router.py.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    $backupPath = Join-Path $targetDir $backupName
    Copy-Item $existingRouter $backupPath
    Write-Host "[OK] Backed up existing llm_router.py -> $backupName" -ForegroundColor Cyan
}


# ---------------------------------------------------------------------------
# STEP 3: DEFINE THE PYTHON FILE CONTENT
# ---------------------------------------------------------------------------
# POWERSHELL CONCEPT - HERE-STRING (@' ... '@):
#   A here-string is a special way to define multi-line text.
#   Everything between @' and '@ is LITERAL TEXT:
#     - Quotes inside are preserved exactly (no escaping needed)
#     - $ signs are literal (not PowerShell variables)
#     - Newlines preserved exactly as written
#
#   CRITICAL RULES:
#     - The opening @' MUST be the LAST thing on its line
#     - The closing '@ MUST be at column 1 (no spaces before it)
#
#   We use single-quote (@' '@) not double-quote (@" "@) because
#   the Python code has $ signs that PowerShell would misinterpret.

$pyContent = @'
# This file was written by write_llm_router_fix.ps1 (clipboard bypass)
# See the full-commentary version in the kit's src\core\llm_router_fix.py

import requests
import logging
import time

logger = logging.getLogger(__name__)

def detect_provider(endpoint_url):
    """Detect Azure vs OpenAI from URL. Returns 'azure' or 'openai'."""
    url_lower = endpoint_url.lower()
    if ".openai.azure.com" in url_lower:
        return "azure"
    elif ".azure-api.net" in url_lower:
        return "azure"
    elif "azure" in url_lower:
        return "azure"
    else:
        return "openai"

def build_api_url(endpoint_url, deployment_name="gpt-35-turbo", api_version="2024-02-01"):
    """Build full API URL without doubling path segments."""
    url = endpoint_url.strip().rstrip("/")
    if "/chat/completions" in url:
        logger.info("URL already complete, using as-is")
        return url
    provider = detect_provider(url)
    if provider == "azure":
        if "/openai/deployments/" in url:
            full_url = url + "/chat/completions"
            if "api-version" not in full_url:
                full_url = full_url + "?api-version=" + api_version
            return full_url
        else:
            return (url + "/openai/deployments/" + deployment_name
                    + "/chat/completions" + "?api-version=" + api_version)
    else:
        if "/v1/" in url:
            return url + "/chat/completions"
        else:
            return url + "/v1/chat/completions"

def build_headers(endpoint_url, api_key):
    """Build correct auth headers. Azure=api-key, OpenAI=Bearer."""
    provider = detect_provider(endpoint_url)
    headers = {"Content-Type": "application/json"}
    if provider == "azure":
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = "Bearer " + api_key
    return headers

def call_llm_api(endpoint_url, api_key, messages, max_tokens=512, temperature=0.2):
    """Main API call with auto provider detection and error handling."""
    start_time = time.time()
    provider = detect_provider(endpoint_url)
    full_url = build_api_url(endpoint_url)
    headers = build_headers(endpoint_url, api_key)
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    key_preview = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    logger.info("API call: provider=%s url=%s key=%s", provider, full_url, key_preview)
    try:
        response = requests.post(full_url, headers=headers, json=body, timeout=60, verify=True)
        latency = time.time() - start_time
        if response.status_code == 200:
            data = response.json()
            return {"answer": data["choices"][0]["message"]["content"],
                    "provider": provider, "model": data.get("model", "unknown"),
                    "usage": data.get("usage", {}), "latency": latency, "error": None}
        elif response.status_code == 401:
            msg = "401 Unauthorized. Provider: " + provider + ". "
            if provider == "azure":
                msg += "FIX: (1) Verify api-key not Bearer. (2) Test direct LAN. (3) Check key expiry. (4) Check Azure RBAC role."
            else:
                msg += "FIX: (1) Check key. (2) Check billing. (3) Check org."
            logger.error(msg)
            return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": latency, "error": msg}
        elif response.status_code == 404:
            msg = "404 Not Found. URL: " + full_url + " -- Compare with Postman. Check for doubling."
            logger.error(msg)
            return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": latency, "error": msg}
        elif response.status_code == 429:
            msg = "429 Rate Limited. Wait 30-60s and retry."
            logger.warning(msg)
            return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": latency, "error": msg}
        else:
            msg = "HTTP " + str(response.status_code) + ": " + response.text[:500]
            logger.error(msg)
            return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": latency, "error": msg}
    except requests.exceptions.SSLError as e:
        msg = "SSL Error. Install pip-system-certs. Detail: " + str(e)[:200]
        logger.error(msg)
        return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": time.time() - start_time, "error": msg}
    except requests.exceptions.Timeout:
        msg = "Timeout after 60s."
        logger.error(msg)
        return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": time.time() - start_time, "error": msg}
    except requests.exceptions.ConnectionError as e:
        msg = "Connection failed. Detail: " + str(e)[:200]
        logger.error(msg)
        return {"answer": None, "provider": provider, "model": None, "usage": None, "latency": time.time() - start_time, "error": msg}

def debug_api_config(endpoint_url, api_key):
    """Print diagnostic info. Called by rag-debug-url."""
    provider = detect_provider(endpoint_url)
    full_url = build_api_url(endpoint_url)
    key_preview = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    print("=" * 60)
    print("API CONFIGURATION DIAGNOSTIC")
    print("=" * 60)
    print("Stored endpoint:   ", endpoint_url)
    print("Detected provider: ", provider)
    print("Constructed URL:   ", full_url)
    print("Auth header name:  ", "api-key" if provider == "azure" else "Authorization")
    print("Auth key preview:  ", key_preview)
    print("=" * 60)
    problems = []
    url_path = full_url.replace("https://", "").replace("http://", "")
    if "//" in url_path:
        problems.append("ERROR: Double slash in URL path")
    if "chat/completions" not in full_url:
        problems.append("ERROR: /chat/completions missing")
    if provider == "azure" and "api-version" not in full_url:
        problems.append("ERROR: api-version missing")
    if len(api_key.strip()) < 10:
        problems.append("WARNING: Key too short")
    if not api_key.strip():
        problems.append("ERROR: Key is empty")
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  >>", p)
    else:
        print("\nNo problems found. If 401 persists, test direct LAN.")
    print("=" * 60)
'@


# ---------------------------------------------------------------------------
# STEP 4: WRITE TO DISK USING .NET (THE KEY TECHNIQUE)
# ---------------------------------------------------------------------------
# POWERSHELL CONCEPT - .NET Interop:
#   PowerShell can use .NET classes directly. We use them because
#   PowerShell's built-in file commands have encoding bugs:
#     Out-File defaults to UTF-16 (wrong for Python)
#     Set-Content in PS 5.1 defaults to ANSI (wrong for everything)
#     The > operator creates UTF-16 files
#
#   System.Text.UTF8Encoding($false):
#     Creates a UTF-8 encoder with BOM DISABLED.
#     $false means "no BOM." BOM = invisible bytes at file start.
#     Python chokes on BOM bytes, so we exclude them.
#
#   [System.IO.File]::WriteAllText($path, $content, $encoding):
#     Writes text to file using our exact encoding choice.
#     Most reliable way to create a correctly-encoded file.

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($targetFile, $pyContent, $utf8NoBom)

Write-Host "[OK] Wrote: $targetFile" -ForegroundColor Green
Write-Host "     Size: $((Get-Item $targetFile).Length) bytes" -ForegroundColor Gray


# ---------------------------------------------------------------------------
# STEP 5: VERIFY PYTHON SYNTAX
# ---------------------------------------------------------------------------
# Python's "ast" module can parse a file and check for syntax errors
# WITHOUT running the code. If it passes, every quote and indent is correct.

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = "python"
}

try {
    # & means "run this program". -c means "execute this one-line command."
    # 2>&1 captures both normal output and error output.
    $result = & $pythonExe -c "import ast; ast.parse(open(r'$targetFile').read()); print('SYNTAX OK')" 2>&1
    if ($result -match "SYNTAX OK") {
        Write-Host "[OK] Python syntax check: PASSED" -ForegroundColor Green
    } else {
        Write-Host "[!!] Syntax check: $result" -ForegroundColor Red
    }
} catch {
    # $_ holds the current error message
    Write-Host "[!!] Could not run syntax check: $_" -ForegroundColor Yellow
}


# ---------------------------------------------------------------------------
# STEP 6: PRINT NEXT STEPS
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "===== FILE WRITTEN SUCCESSFULLY =====" -ForegroundColor Cyan
Write-Host "NEXT:" -ForegroundColor Cyan
Write-Host "  1. Load commands: . .\tools\new_commands_for_start_hybridrag.ps1" -ForegroundColor White
Write-Host "  2. Pre-flight:    rag-debug-url" -ForegroundColor White
Write-Host "  3. Test API:      rag-test-api-verbose" -ForegroundColor White
Write-Host "======================================" -ForegroundColor Cyan
