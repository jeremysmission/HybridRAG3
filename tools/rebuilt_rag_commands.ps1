# ===========================================================================
# REBUILT RAG COMMANDS â€” QUOTING-SAFE VERSION
# ===========================================================================
#
# WHAT THIS IS:
#   Replacement for new_commands_for_start_hybridrag.ps1
#   These commands write temp Python files instead of using inline Python
#   in PowerShell. This avoids the quoting corruption that broke
#   rag-debug-url and rag-test-api-verbose.
#
# HOW TO USE:
#   cd "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
#   .\.venv\Scripts\Activate
#   . .\tools\rebuilt_rag_commands.ps1
#
# COMMANDS PROVIDED:
#   rag-debug-url          Shows URL + headers without calling API
#   rag-test-api-verbose   Makes real API call with full debug output
#   rag-fix-quotes         Fixes smart quotes in project files
#   rag-detect-bad-chars   Scans for non-ASCII characters
#   rag-env-vars           Shows all API-related environment variables
# ===========================================================================


# ---------------------------------------------------------------------------
# HELPER: Write and run a temp Python script safely
# ---------------------------------------------------------------------------
# WHY THIS EXISTS:
#   PowerShell mangles quotes when you embed Python code inline with -c.
#   By writing to a temp .py file first, the Python code stays clean.
#   The temp file is deleted after running.
# ---------------------------------------------------------------------------
function Run-TempPython {
    param([string]$ScriptContent, [string]$ScriptName = "temp_rag_cmd")
    
    $projectRoot = Get-Location
    $tempFile = Join-Path $projectRoot "$ScriptName.py"
    
    try {
        $ScriptContent | Out-File -FilePath $tempFile -Encoding UTF8
        python $tempFile
    }
    finally {
        if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
    }
}


# ===========================================================================
# COMMAND: rag-debug-url
# ===========================================================================
# Shows exactly what URL and headers WOULD be sent, without calling the API.
# Like a pre-flight checklist.
# ---------------------------------------------------------------------------
function rag-debug-url {
    Write-Host "Running API configuration diagnostic..." -ForegroundColor Cyan
    
    $pythonCode = @'
import sys
import os

# Add project root to Python path so imports work
sys.path.insert(0, os.getcwd())

print("=" * 60)
print("  API CONFIGURATION DIAGNOSTIC")
print("=" * 60)
print()

# ---- Read credentials ----
try:
    import keyring
    endpoint = keyring.get_password("hybridrag", "azure_endpoint")
    api_key = keyring.get_password("hybridrag", "azure_api_key")
except ImportError:
    print("[ERROR] keyring not installed. Run: pip install keyring")
    sys.exit(1)

if not endpoint:
    print("[ERROR] No endpoint stored. Run rag-store-endpoint first.")
    sys.exit(1)
if not api_key:
    print("[ERROR] No API key stored. Run rag-store-key first.")
    sys.exit(1)

print(f"  Stored endpoint:   {endpoint}")
print(f"  Key present:       YES")
print(f"  Key preview:       {api_key[:4]}...{api_key[-4:]}")
print()

# ---- Detect provider (FIXED: recognizes "aoai") ----
url_lower = endpoint.lower()
is_azure = (
    "azure" in url_lower
    or ".openai.azure.com" in url_lower
    or "aoai" in url_lower
    or "azure-api" in url_lower
)

provider = "AZURE" if is_azure else "OpenAI"
print(f"  Detected provider: {provider}")

# Show what matched
markers = [m for m in ["azure", ".openai.azure.com", "aoai", "azure-api"] if m in url_lower]
print(f"  Matched patterns:  {', '.join(markers) if markers else 'NONE'}")
print()

# ---- Check for deployment name in env vars ----
deployment = None
for var in ["AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT", "OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_DEPLOYMENT_NAME", "DEPLOYMENT_NAME"]:
    val = os.environ.get(var)
    if val:
        deployment = val
        print(f"  Deployment name:   {deployment} (from env: {var})")
        break

api_version = None
for var in ["AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION", "API_VERSION"]:
    val = os.environ.get(var)
    if val:
        api_version = val
        print(f"  API version:       {api_version} (from env: {var})")
        break

# ---- Build URL ----
base = endpoint.rstrip("/")

if is_azure:
    if "/chat/completions" in endpoint:
        final_url = base
        if "api-version" not in base:
            v = api_version or "2024-02-01"
            final_url = f"{base}?api-version={v}"
        strategy = "URL already complete, using as-is"
    elif "/deployments/" in endpoint:
        v = api_version or "2024-02-01"
        final_url = f"{base}/chat/completions?api-version={v}"
        strategy = "Appending /chat/completions"
        import re
        match = re.search(r"/deployments/([^/]+)", endpoint)
        if match and not deployment:
            deployment = match.group(1)
    else:
        if not deployment:
            deployment = "gpt-35-turbo"
            print(f"  Deployment name:   {deployment} (GUESSED - may need to change!)")
        if not api_version:
            api_version = "2024-02-01"
            print(f"  API version:       {api_version} (default)")
        final_url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        strategy = "Built full Azure path from base URL"
    
    auth_header = "api-key"
    auth_format = f"api-key: {api_key[:4]}...{api_key[-4:]}"
else:
    if "/chat/completions" in endpoint:
        final_url = base
    else:
        final_url = f"{base}/v1/chat/completions"
    auth_header = "Authorization"
    auth_format = f"Authorization: Bearer {api_key[:4]}...{api_key[-4:]}"
    strategy = "Standard OpenAI path"

print()
print(f"  URL strategy:      {strategy}")
print(f"  Auth header:       {auth_header}")
print(f"  Final URL:         {final_url}")
print()

# ---- Check for problems ----
problems = []
clean_path = final_url.replace("https://", "").replace("http://", "")
if "//" in clean_path:
    problems.append("DOUBLE SLASH found in URL path")
if is_azure and not deployment:
    problems.append("No deployment name (Azure requires one)")
if is_azure and "v1/chat" in final_url:
    problems.append("OpenAI path format on Azure endpoint (should be /openai/deployments/...)")
if not is_azure and "openai/deployments" in final_url:
    problems.append("Azure path format on OpenAI endpoint")

if problems:
    print("  PROBLEMS FOUND:")
    for p in problems:
        print(f"    [!] {p}")
else:
    print("  No obvious problems found.")

print()
print("  If this looks correct, run: rag-test-api-verbose")
print("=" * 60)
'@
    
    Run-TempPython -ScriptContent $pythonCode -ScriptName "temp_debug_url"
}


# ===========================================================================
# COMMAND: rag-test-api-verbose
# ===========================================================================
# Makes a real API call with full debug output.
# Run rag-debug-url first to verify the URL looks correct.
# ---------------------------------------------------------------------------
function rag-test-api-verbose {
    Write-Host "Running live API test..." -ForegroundColor Cyan
    Write-Host ""
    
    $pythonCode = @'
import sys
import os
import json
import time

sys.path.insert(0, os.getcwd())

print("=" * 60)
print("  LIVE API TEST")
print("=" * 60)
print()

# ---- Read credentials ----
import keyring
endpoint = keyring.get_password("hybridrag", "azure_endpoint")
api_key = keyring.get_password("hybridrag", "azure_api_key")

if not endpoint or not api_key:
    print("[ERROR] Missing credentials. Run rag-store-endpoint and rag-store-key.")
    sys.exit(1)

# ---- Detect provider and build URL ----
url_lower = endpoint.lower()
is_azure = ("azure" in url_lower or ".openai.azure.com" in url_lower 
            or "aoai" in url_lower or "azure-api" in url_lower)

base = endpoint.rstrip("/")

if is_azure:
    if "/chat/completions" in endpoint:
        final_url = base
        if "api-version" not in base:
            final_url += "?api-version=2024-02-01"
    elif "/deployments/" in endpoint:
        v = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
        final_url = f"{base}/chat/completions?api-version={v}"
    else:
        deployment = None
        for var in ["AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT",
                     "OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME",
                     "DEPLOYMENT_NAME"]:
            val = os.environ.get(var)
            if val:
                deployment = val
                break
        if not deployment:
            deployment = "gpt-35-turbo"
        v = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
        final_url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={v}"
    
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    print(f"  Provider:  AZURE")
    print(f"  Auth:      api-key header")
else:
    if "/chat/completions" in endpoint:
        final_url = base
    else:
        final_url = f"{base}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    print(f"  Provider:  OpenAI")
    print(f"  Auth:      Bearer token")

print(f"  URL:       {final_url}")
print()

payload = {
    "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
    "max_tokens": 20,
    "temperature": 0.1
}

print("  Sending request...")

import urllib.request
import urllib.error
import ssl

req = urllib.request.Request(
    final_url,
    data=json.dumps(payload).encode("utf-8"),
    headers=headers,
    method="POST"
)

ctx = ssl.create_default_context()
start = time.time()

try:
    response = urllib.request.urlopen(req, context=ctx, timeout=30)
    latency = time.time() - start
    body = json.loads(response.read().decode("utf-8"))
    
    print(f"  Status:    200 OK")
    print(f"  Latency:   {latency:.2f}s")
    
    if "choices" in body and body["choices"]:
        answer = body["choices"][0]["message"]["content"]
        print(f"  Response:  {answer}")
        print(f"  Model:     {body.get('model', 'unknown')}")
    
    if "usage" in body:
        u = body["usage"]
        print(f"  Tokens:    {u.get('prompt_tokens', '?')} in, {u.get('completion_tokens', '?')} out")
    
    print()
    print("  [SUCCESS] API connection is working!")
    
except urllib.error.HTTPError as e:
    latency = time.time() - start
    error_body = ""
    try:
        error_body = e.read().decode("utf-8")
    except:
        pass
    
    print(f"  Status:    {e.code} {e.reason}")
    print(f"  Latency:   {latency:.2f}s")
    if error_body:
        print(f"  Response:  {error_body[:500]}")
    print()
    
    if e.code == 401:
        print("  [FAIL] Authentication error.")
        print("  >> Check that your API key is correct and not expired.")
        print("  >> Azure uses 'api-key' header, not 'Authorization: Bearer'.")
    elif e.code == 404:
        print("  [FAIL] URL not found.")
        print("  >> The deployment name may be wrong.")
        print("  >> Check Azure Portal > Azure OpenAI > Deployments for the exact name.")
        print("  >> Also check the api-version parameter.")
    elif e.code == 403:
        print("  [FAIL] Forbidden.")
        print("  >> Your key may not have permission for this deployment.")
    elif e.code == 429:
        print("  [FAIL] Rate limited.")
        print("  >> Wait a minute and try again.")
    else:
        print(f"  [FAIL] HTTP error {e.code}.")
    
except urllib.error.URLError as e:
    latency = time.time() - start
    print(f"  Status:    CONNECTION FAILED")
    print(f"  Latency:   {latency:.2f}s")
    print(f"  Error:     {str(e.reason)}")
    print()
    print("  [FAIL] Could not reach the server.")
    print("  >> Check: Are you on VPN or direct LAN?")
    print("  >> Check: Is a proxy required? (See proxy settings in start_hybridrag.ps1)")
    print("  >> Try:   Test-NetConnection -ComputerName <hostname> -Port 443")

except Exception as e:
    print(f"  [FAIL] Unexpected error: {str(e)}")

print()
print("=" * 60)
'@
    
    Run-TempPython -ScriptContent $pythonCode -ScriptName "temp_test_api"
}


# ===========================================================================
# COMMAND: rag-env-vars
# ===========================================================================
# Quick view of all API-related environment variables.
# ---------------------------------------------------------------------------
function rag-env-vars {
    Write-Host ""
    Write-Host "API-Related Environment Variables:" -ForegroundColor Cyan
    Write-Host "-" * 50 -ForegroundColor Gray
    
    $vars = Get-ChildItem env: | Where-Object { 
        $_.Name -match "azure|openai|api|endpoint|deploy|proxy|version|ollama|model|hugging" 
    } | Sort-Object Name
    
    if ($vars.Count -eq 0) {
        Write-Host "  (none found)" -ForegroundColor Gray
    } else {
        foreach ($v in $vars) {
            $displayVal = $v.Value
            if ($v.Name -match "key|secret|token|password" -and $displayVal.Length -gt 8) {
                $displayVal = $displayVal.Substring(0,4) + "..." + $displayVal.Substring($displayVal.Length - 4)
            }
            Write-Host "  $($v.Name) = $displayVal" -ForegroundColor White
        }
    }
    Write-Host ""
}


# ===========================================================================
# COMMAND: rag-fix-quotes (UNCHANGED â€” this one worked fine)
# ===========================================================================
function rag-fix-quotes {
    Write-Host "Scanning and fixing smart quotes in project files..." -ForegroundColor Cyan
    
    $extensions = @("*.py", "*.ps1", "*.yaml", "*.yml", "*.bat", "*.txt", "*.md", "*.json", "*.cfg", "*.ini", "*.toml")
    $fixed = 0
    $scanned = 0
    
    foreach ($ext in $extensions) {
        $files = Get-ChildItem -Path . -Filter $ext -Recurse -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -notmatch "\.venv|__pycache__|\.git|node_modules|backup" }
        
        foreach ($file in $files) {
            $scanned++
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            
            $original = $content
            
            # Fix smart double quotes
            $content = $content -replace "\u201C", '"'  # Left double
            $content = $content -replace "\u201D", '"'  # Right double
            
            # Fix smart single quotes
            $content = $content -replace "\u2018", "'"  # Left single
            $content = $content -replace "\u2019", "'"  # Right single
            
            # Fix dashes
            $content = $content -replace "\u2013", "-"  # En-dash
            $content = $content -replace "\u2014", "--" # Em-dash
            
            # Fix ellipsis
            $content = $content -replace "\u2026", "..."
            
            if ($content -ne $original) {
                # Backup first
                $backupPath = $file.FullName + ".bak"
                if (-not (Test-Path $backupPath)) {
                    $original | Out-File -FilePath $backupPath -Encoding UTF8 -NoNewline
                }
                $content | Out-File -FilePath $file.FullName -Encoding UTF8 -NoNewline
                $fixed++
                Write-Host "  Fixed: $($file.FullName)" -ForegroundColor Yellow
            }
        }
    }
    
    Write-Host ""
    Write-Host "  Scanned $scanned files, fixed $fixed files." -ForegroundColor Green
}


# ===========================================================================
# COMMAND: rag-detect-bad-chars (UNCHANGED â€” this one worked fine)
# ===========================================================================
function rag-detect-bad-chars {
    Write-Host "Scanning for non-ASCII characters in code files..." -ForegroundColor Cyan
    
    $extensions = @("*.py", "*.ps1", "*.yaml", "*.yml", "*.bat", "*.txt", "*.json", "*.cfg")
    $totalProblems = 0
    $problemFiles = 0
    
    foreach ($ext in $extensions) {
        $files = Get-ChildItem -Path . -Filter $ext -Recurse -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -notmatch "\.venv|__pycache__|\.git|node_modules|backup|\.bak" }
        
        foreach ($file in $files) {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $content) { continue }
            
            $matches = [regex]::Matches($content, "[\u2018\u2019\u201C\u201D\u2013\u2014\u2026]")
            if ($matches.Count -gt 0) {
                $totalProblems += $matches.Count
                $problemFiles++
                Write-Host "  [$($matches.Count)] $($file.FullName)" -ForegroundColor Yellow
            }
        }
    }
    
    Write-Host ""
    if ($totalProblems -eq 0) {
        Write-Host "  All clean! No smart quotes or bad characters found." -ForegroundColor Green
    } else {
        Write-Host "  Found $totalProblems problems in $problemFiles files." -ForegroundColor Red
        Write-Host "  Run rag-fix-quotes to fix them." -ForegroundColor Yellow
    }
}


# ===========================================================================
# CONFIRMATION
# ===========================================================================
Write-Host ""
Write-Host "Rebuilt RAG commands loaded:" -ForegroundColor Green
Write-Host "  rag-debug-url        - Show URL + headers (no API call)" -ForegroundColor White
Write-Host "  rag-test-api-verbose - Live API test with debug output" -ForegroundColor White
Write-Host "  rag-env-vars         - Show API-related env variables" -ForegroundColor White
Write-Host "  rag-fix-quotes       - Fix smart quotes in project files" -ForegroundColor White
Write-Host "  rag-detect-bad-chars - Scan for bad characters" -ForegroundColor White
Write-Host ""

