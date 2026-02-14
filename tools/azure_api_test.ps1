# ===========================================================================
# AZURE API TEST TOOL â€” COMPLETE DIAGNOSTIC + LIVE TEST
# ===========================================================================
#
# WHAT THIS DOES:
#   Runs a 4-stage diagnostic of your Azure API connection:
#     Stage 1: Discover all Azure/API environment variables
#     Stage 2: Read stored credentials (keyring)
#     Stage 3: Build the correct Azure URL and show it
#     Stage 4: Make a real API call and show the response
#
#   Each stage writes a temp Python file and runs it. This avoids ALL
#   PowerShell quoting issues that broke rag-debug-url and rag-test-api.
#
# HOW TO RUN:
#   cd "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
#   .\.venv\Scripts\Activate
#   . .\tools\azure_api_test.ps1
#
# SAFETY:
#   - Stage 4 makes ONE real API call (a simple "Say hello" test)
#   - All temp files are cleaned up automatically
#   - Your API key is never displayed in full
# ===========================================================================

$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
$tempDir = Join-Path $projectRoot "temp_diag"

# --- Setup ---
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AZURE API CONNECTION DIAGNOSTIC" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# ===================================================================
# STAGE 1: DISCOVER ENVIRONMENT VARIABLES
# ===================================================================
Write-Host "--- STAGE 1: Environment Variables ---" -ForegroundColor Yellow

# Show all Azure/API related env vars
$envVars = Get-ChildItem env: | Where-Object { 
    $_.Name -match "azure|openai|api|endpoint|deploy|proxy|version|ollama|model" 
} | Sort-Object Name

if ($envVars.Count -eq 0) {
    Write-Host "  No Azure/API environment variables found." -ForegroundColor Gray
    Write-Host "  (This is OK if you stored creds via keyring instead)" -ForegroundColor Gray
} else {
    Write-Host "  Found $($envVars.Count) relevant environment variables:" -ForegroundColor White
    foreach ($v in $envVars) {
        $displayVal = $v.Value
        # Mask anything that looks like an API key (long alphanumeric strings)
        if ($v.Name -match "key|secret|token|password" -and $displayVal.Length -gt 8) {
            $displayVal = $displayVal.Substring(0,4) + "..." + $displayVal.Substring($displayVal.Length - 4)
        }
        Write-Host "  $($v.Name) = $displayVal" -ForegroundColor White
    }
}
Write-Host ""

# ===================================================================
# STAGE 2: READ STORED CREDENTIALS
# ===================================================================
Write-Host "--- STAGE 2: Stored Credentials (keyring) ---" -ForegroundColor Yellow

$stage2Script = @'
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import keyring
    endpoint = keyring.get_password("hybridrag", "azure_endpoint")
    api_key = keyring.get_password("hybridrag", "azure_api_key")
    
    print("CRED_CHECK_START")
    if endpoint:
        print(f"ENDPOINT={endpoint}")
    else:
        print("ENDPOINT=EMPTY")
    
    if api_key:
        masked = api_key[:4] + "..." + api_key[-4:]
        print(f"KEY_PREVIEW={masked}")
        print(f"KEY_LENGTH={len(api_key)}")
        print("KEY_PRESENT=YES")
    else:
        print("KEY_PRESENT=NO")
    print("CRED_CHECK_END")
    
except ImportError:
    print("CRED_CHECK_START")
    print("ERROR=keyring module not installed")
    print("CRED_CHECK_END")
except Exception as e:
    print("CRED_CHECK_START")
    print(f"ERROR={str(e)}")
    print("CRED_CHECK_END")
'@

$stage2File = Join-Path $tempDir "stage2_creds.py"
$stage2Script | Out-File -FilePath $stage2File -Encoding UTF8

Push-Location $projectRoot
$stage2Output = python $stage2File 2>&1
Pop-Location

# Parse the output
$endpoint = ""
$keyPresent = $false
$keyPreview = ""

foreach ($line in $stage2Output) {
    $lineStr = $line.ToString().Trim()
    if ($lineStr -match "^ENDPOINT=(.+)$") { $endpoint = $Matches[1] }
    if ($lineStr -match "^KEY_PRESENT=YES") { $keyPresent = $true }
    if ($lineStr -match "^KEY_PREVIEW=(.+)$") { $keyPreview = $Matches[1] }
    if ($lineStr -match "^ERROR=(.+)$") { 
        Write-Host "  ERROR: $($Matches[1])" -ForegroundColor Red 
    }
}

Write-Host "  Stored endpoint: $endpoint" -ForegroundColor White
Write-Host "  API key present: $keyPresent" -ForegroundColor $(if ($keyPresent) { "Green" } else { "Red" })
if ($keyPreview) { Write-Host "  Key preview: $keyPreview" -ForegroundColor White }

if (-not $endpoint -or $endpoint -eq "EMPTY") {
    Write-Host ""
    Write-Host "  [STOP] No endpoint stored. Run rag-store-endpoint first." -ForegroundColor Red
    Remove-Item $tempDir -Recurse -Force
    return
}
if (-not $keyPresent) {
    Write-Host ""
    Write-Host "  [STOP] No API key stored. Run rag-store-key first." -ForegroundColor Red
    Remove-Item $tempDir -Recurse -Force
    return
}
Write-Host ""

# ===================================================================
# STAGE 3: BUILD AND VERIFY THE URL
# ===================================================================
Write-Host "--- STAGE 3: URL Construction Analysis ---" -ForegroundColor Yellow

$stage3Script = @'
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyring
endpoint = keyring.get_password("hybridrag", "azure_endpoint")
api_key = keyring.get_password("hybridrag", "azure_api_key")

print("URL_ANALYSIS_START")

# ---- Provider Detection (FIXED to recognize "aoai") ----
url_lower = endpoint.lower()
is_azure = (
    "azure" in url_lower
    or ".openai.azure.com" in url_lower
    or "aoai" in url_lower          # Company abbreviation for Azure OpenAI
    or "azure-api" in url_lower     # Another common pattern
)

provider = "AZURE" if is_azure else "OPENAI"
print(f"PROVIDER={provider}")
print(f"BASE_ENDPOINT={endpoint}")

# ---- Detection Evidence ----
markers_found = []
for marker in ["azure", ".openai.azure.com", "aoai", "azure-api"]:
    if marker in url_lower:
        markers_found.append(marker)
print(f"MARKERS_FOUND={','.join(markers_found) if markers_found else 'NONE'}")

# ---- Look for deployment name in env vars ----
deployment = None
api_version = None

# Check multiple possible env var names
deploy_vars = [
    "AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT", "OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_DEPLOYMENT_NAME", "DEPLOYMENT_NAME", "AZURE_DEPLOYMENT_NAME",
    "AZURE_CHAT_DEPLOYMENT", "CHAT_MODEL_DEPLOYMENT"
]
for var in deploy_vars:
    val = os.environ.get(var)
    if val:
        deployment = val
        print(f"DEPLOYMENT={deployment} (from env:{var})")
        break

version_vars = [
    "AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION", "OPENAI_API_VERSION",
    "API_VERSION"
]
for var in version_vars:
    val = os.environ.get(var)
    if val:
        api_version = val
        print(f"API_VERSION={api_version} (from env:{var})")
        break

# ---- Check if endpoint already has full path ----
has_chat_completions = "/chat/completions" in endpoint
has_deployments = "/deployments/" in endpoint
has_openai_path = "/openai/" in endpoint
print(f"URL_HAS_CHAT_COMPLETIONS={has_chat_completions}")
print(f"URL_HAS_DEPLOYMENTS={has_deployments}")
print(f"URL_HAS_OPENAI_PATH={has_openai_path}")

# ---- Extract deployment from URL if present ----
if has_deployments and not deployment:
    import re
    match = re.search(r"/deployments/([^/]+)", endpoint)
    if match:
        deployment = match.group(1)
        print(f"DEPLOYMENT={deployment} (extracted from URL)")

# ---- Build the correct URL ----
if provider == "AZURE":
    # Strip trailing slash
    base = endpoint.rstrip("/")
    
    if has_chat_completions:
        # URL already complete - use as-is
        final_url = base
        if "api-version" not in base:
            v = api_version or "2024-02-01"
            final_url = f"{base}?api-version={v}"
        print(f"URL_STRATEGY=COMPLETE (using as-is)")
    elif has_deployments:
        # Has deployment but missing /chat/completions
        v = api_version or "2024-02-01"
        final_url = f"{base}/chat/completions?api-version={v}"
        print(f"URL_STRATEGY=APPEND_COMPLETIONS")
    else:
        # Just base URL - need deployment name
        if not deployment:
            deployment = "gpt-35-turbo"  # Most common default
            print(f"DEPLOYMENT={deployment} (GUESSED - may need to change)")
        if not api_version:
            api_version = "2024-02-01"
            print(f"API_VERSION={api_version} (default)")
        final_url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        print(f"URL_STRATEGY=BUILD_FULL")
    
    auth_header = "api-key"
    print(f"AUTH_HEADER=api-key")
else:
    base = endpoint.rstrip("/")
    if has_chat_completions:
        final_url = base
    else:
        final_url = f"{base}/v1/chat/completions"
    auth_header = "Authorization"
    print(f"AUTH_HEADER=Authorization: Bearer")

print(f"FINAL_URL={final_url}")

# ---- Check for common problems ----
problems = []
if "//" in final_url.replace("https://", "").replace("http://", ""):
    problems.append("DOUBLE_SLASH in URL path")
if provider == "AZURE" and not deployment:
    problems.append("NO_DEPLOYMENT_NAME (will fail)")
if provider == "AZURE" and "v1/chat" in final_url:
    problems.append("WRONG_PATH (OpenAI path on Azure endpoint)")
if not api_key:
    problems.append("NO_API_KEY")

if problems:
    print(f"PROBLEMS={'|'.join(problems)}")
else:
    print("PROBLEMS=NONE")

print("URL_ANALYSIS_END")
'@

$stage3File = Join-Path $tempDir "stage3_url.py"
$stage3Script | Out-File -FilePath $stage3File -Encoding UTF8

Push-Location $projectRoot
$stage3Output = python $stage3File 2>&1
Pop-Location

# Parse and display
$provider = ""
$finalUrl = ""
$deployment = ""
$apiVersion = ""
$authHeader = ""
$problems = ""

foreach ($line in $stage3Output) {
    $lineStr = $line.ToString().Trim()
    if ($lineStr -match "^PROVIDER=(.+)$") { $provider = $Matches[1] }
    if ($lineStr -match "^FINAL_URL=(.+)$") { $finalUrl = $Matches[1] }
    if ($lineStr -match "^DEPLOYMENT=(.+)$") { $deployment = $Matches[1] }
    if ($lineStr -match "^API_VERSION=(.+)$") { $apiVersion = $Matches[1] }
    if ($lineStr -match "^AUTH_HEADER=(.+)$") { $authHeader = $Matches[1] }
    if ($lineStr -match "^PROBLEMS=(.+)$") { $problems = $Matches[1] }
    if ($lineStr -match "^MARKERS_FOUND=(.+)$") { 
        Write-Host "  Azure markers found: $($Matches[1])" -ForegroundColor Green 
    }
    if ($lineStr -match "^URL_STRATEGY=(.+)$") { 
        Write-Host "  URL strategy: $($Matches[1])" -ForegroundColor White 
    }
    if ($lineStr -match "^URL_HAS") { 
        Write-Host "  $lineStr" -ForegroundColor Gray 
    }
}

Write-Host ""
Write-Host "  Detected provider:  $provider" -ForegroundColor $(if ($provider -eq "AZURE") { "Green" } else { "Red" })
if ($deployment) { Write-Host "  Deployment name:    $deployment" -ForegroundColor White }
if ($apiVersion) { Write-Host "  API version:        $apiVersion" -ForegroundColor White }
Write-Host "  Auth header:        $authHeader" -ForegroundColor White
Write-Host "  Final URL:          $finalUrl" -ForegroundColor Cyan
Write-Host ""

if ($problems -and $problems -ne "NONE") {
    Write-Host "  PROBLEMS DETECTED:" -ForegroundColor Red
    foreach ($p in $problems.Split("|")) {
        Write-Host "    - $p" -ForegroundColor Red
    }
    Write-Host ""
}

# ---- Ask user to confirm before making real API call ----
Write-Host "--- STAGE 4: Live API Test ---" -ForegroundColor Yellow
Write-Host ""
Write-Host "  The URL above will be tested with a simple 'Say hello' request." -ForegroundColor White
Write-Host ""
$confirm = Read-Host "  Press ENTER to test, or type 'skip' to stop here"
if ($confirm -eq "skip") {
    Write-Host "  Skipped live test." -ForegroundColor Gray
    Remove-Item $tempDir -Recurse -Force
    return
}

# ===================================================================
# STAGE 4: LIVE API TEST
# ===================================================================

$stage4Script = @'
import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keyring

endpoint = keyring.get_password("hybridrag", "azure_endpoint")
api_key = keyring.get_password("hybridrag", "azure_api_key")

# ---- Rebuild the URL (same logic as Stage 3) ----
url_lower = endpoint.lower()
is_azure = (
    "azure" in url_lower
    or ".openai.azure.com" in url_lower
    or "aoai" in url_lower
    or "azure-api" in url_lower
)

base = endpoint.rstrip("/")

if is_azure:
    if "/chat/completions" in endpoint:
        final_url = base
        if "api-version" not in base:
            final_url += "?api-version=2024-02-01"
    elif "/deployments/" in endpoint:
        final_url = base + "/chat/completions?api-version=2024-02-01"
    else:
        # Need deployment name - check env vars
        deployment = None
        for var in ["AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT", 
                     "OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME",
                     "DEPLOYMENT_NAME", "AZURE_CHAT_DEPLOYMENT"]:
            val = os.environ.get(var)
            if val:
                deployment = val
                break
        if not deployment:
            deployment = "gpt-35-turbo"
        
        api_version = None
        for var in ["AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION", "API_VERSION"]:
            val = os.environ.get(var)
            if val:
                api_version = val
                break
        if not api_version:
            api_version = "2024-02-01"
        
        final_url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
else:
    if "/chat/completions" in endpoint:
        final_url = base
    else:
        final_url = base + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

payload = {
    "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
    "max_tokens": 20,
    "temperature": 0.1
}

print("LIVE_TEST_START")
print(f"REQUESTING={final_url}")
print(f"AUTH_TYPE={'api-key' if is_azure else 'Bearer'}")

try:
    import urllib.request
    import urllib.error
    
    req = urllib.request.Request(
        final_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    start = time.time()
    
    # Handle SSL (corporate proxies may need this)
    import ssl
    ctx = ssl.create_default_context()
    
    try:
        response = urllib.request.urlopen(req, context=ctx, timeout=30)
        latency = time.time() - start
        body = json.loads(response.read().decode("utf-8"))
        
        print(f"STATUS=200")
        print(f"LATENCY={latency:.2f}s")
        
        if "choices" in body and body["choices"]:
            answer = body["choices"][0]["message"]["content"]
            print(f"RESPONSE={answer}")
            model = body.get("model", "unknown")
            print(f"MODEL={model}")
        
        if "usage" in body:
            u = body["usage"]
            print(f"TOKENS_IN={u.get('prompt_tokens', '?')}")
            print(f"TOKENS_OUT={u.get('completion_tokens', '?')}")
        
        print("RESULT=SUCCESS")
        
    except urllib.error.HTTPError as e:
        latency = time.time() - start
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except:
            pass
        
        print(f"STATUS={e.code}")
        print(f"LATENCY={latency:.2f}s")
        print(f"HTTP_ERROR={e.reason}")
        
        if error_body:
            print(f"ERROR_BODY={error_body[:500]}")
        
        # Specific guidance per error code
        if e.code == 401:
            print("DIAGNOSIS=Authentication failed. Either the API key is wrong, expired, or the auth header format is incorrect.")
            print("TRY=Verify your API key is still valid in Azure Portal.")
        elif e.code == 404:
            print("DIAGNOSIS=URL not found. The deployment name or path is wrong.")
            print("TRY=Check your deployment name in Azure Portal > Azure OpenAI > Deployments.")
        elif e.code == 403:
            print("DIAGNOSIS=Forbidden. Your key may not have access to this deployment.")
            print("TRY=Check RBAC permissions in Azure Portal.")
        elif e.code == 429:
            print("DIAGNOSIS=Rate limited. Too many requests or quota exceeded.")
            print("TRY=Wait a minute and try again.")
        
        print("RESULT=FAILED")
        
    except urllib.error.URLError as e:
        latency = time.time() - start
        print(f"STATUS=CONNECTION_ERROR")
        print(f"LATENCY={latency:.2f}s")
        print(f"URL_ERROR={str(e.reason)}")
        print("DIAGNOSIS=Could not connect to the server. Check network, VPN, or proxy settings.")
        print("RESULT=FAILED")

except Exception as e:
    print(f"UNEXPECTED_ERROR={str(e)}")
    print("RESULT=FAILED")

print("LIVE_TEST_END")
'@

$stage4File = Join-Path $tempDir "stage4_test.py"
$stage4Script | Out-File -FilePath $stage4File -Encoding UTF8

Push-Location $projectRoot
$stage4Output = python $stage4File 2>&1
Pop-Location

# Parse and display Stage 4 results
$testResult = ""
foreach ($line in $stage4Output) {
    $lineStr = $line.ToString().Trim()
    if ($lineStr -match "^REQUESTING=(.+)$") { 
        Write-Host "  URL: $($Matches[1])" -ForegroundColor White 
    }
    if ($lineStr -match "^AUTH_TYPE=(.+)$") { 
        Write-Host "  Auth: $($Matches[1])" -ForegroundColor White 
    }
    if ($lineStr -match "^STATUS=(.+)$") { 
        $status = $Matches[1]
        $color = if ($status -eq "200") { "Green" } else { "Red" }
        Write-Host "  HTTP Status: $status" -ForegroundColor $color
    }
    if ($lineStr -match "^LATENCY=(.+)$") { 
        Write-Host "  Latency: $($Matches[1])" -ForegroundColor White 
    }
    if ($lineStr -match "^RESPONSE=(.+)$") { 
        Write-Host "  Response: $($Matches[1])" -ForegroundColor Green 
    }
    if ($lineStr -match "^MODEL=(.+)$") { 
        Write-Host "  Model: $($Matches[1])" -ForegroundColor White 
    }
    if ($lineStr -match "^TOKENS") { 
        Write-Host "  $lineStr" -ForegroundColor Gray 
    }
    if ($lineStr -match "^HTTP_ERROR=(.+)$") { 
        Write-Host "  Error: $($Matches[1])" -ForegroundColor Red 
    }
    if ($lineStr -match "^ERROR_BODY=(.+)$") { 
        Write-Host "  Details: $($Matches[1])" -ForegroundColor Yellow 
    }
    if ($lineStr -match "^DIAGNOSIS=(.+)$") { 
        Write-Host "  >>> $($Matches[1])" -ForegroundColor Yellow 
    }
    if ($lineStr -match "^TRY=(.+)$") { 
        Write-Host "  >>> $($Matches[1])" -ForegroundColor Cyan 
    }
    if ($lineStr -match "^URL_ERROR=(.+)$") { 
        Write-Host "  Connection Error: $($Matches[1])" -ForegroundColor Red 
    }
    if ($lineStr -match "^UNEXPECTED_ERROR=(.+)$") { 
        Write-Host "  Unexpected Error: $($Matches[1])" -ForegroundColor Red 
    }
    if ($lineStr -match "^RESULT=(.+)$") { $testResult = $Matches[1] }
}

Write-Host ""
if ($testResult -eq "SUCCESS") {
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "  API CONNECTION SUCCESSFUL" -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Your Azure API is working. Next steps:" -ForegroundColor White
    Write-Host "  1. Run: . .\tools\fix_azure_detection.ps1  (if not done)" -ForegroundColor White
    Write-Host "  2. Try: rag-query-api 'What is a digisonde?'" -ForegroundColor White
} else {
    Write-Host "  ============================================" -ForegroundColor Red
    Write-Host "  API CONNECTION FAILED" -ForegroundColor Red
    Write-Host "  ============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Copy the output above and share with Claude." -ForegroundColor White
    Write-Host "  The error details will tell us exactly what to fix." -ForegroundColor White
}

# --- Cleanup ---
Write-Host ""
Remove-Item $tempDir -Recurse -Force
Write-Host "  (Temp files cleaned up)" -ForegroundColor Gray

