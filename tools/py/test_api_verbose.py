# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the api verbose operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Verbose API Test (tools/py/test_api_verbose.py)
# ============================================================================
#
# WHAT THIS DOES:
#   Sends a real test message ("Say hello in exactly 3 words") to your
#   configured AI endpoint and shows every detail of the request and
#   response. This is the definitive test of whether your API setup works.
#
# WHAT IT SHOWS ON SUCCESS:
#   - Provider type (Azure or OpenAI)
#   - The exact URL it called
#   - HTTP status (200 = success)
#   - Response latency
#   - The AI's response text
#   - Token usage (how many words the AI processed)
#
# WHAT IT SHOWS ON FAILURE:
#   - 401: Wrong API key or wrong auth header format
#   - 403: Key doesn't have permission for this deployment
#   - 404: Wrong deployment name or API version
#   - 429: Rate limited (too many requests, wait a minute)
#   - Connection error: VPN/proxy/network issue
#
# HOW TO USE:
#   python tools/py/test_api_verbose.py
#
# PREREQUISITES:
#   Run these first if you haven't:
#     rag-store-endpoint    (saves your API URL)
#     rag-store-key         (saves your API key)
# ============================================================================
import sys, os, json, time
sys.path.insert(0, os.getcwd())

import keyring
endpoint = keyring.get_password("hybridrag", "azure_endpoint")
api_key = keyring.get_password("hybridrag", "azure_api_key")
deployment = keyring.get_password("hybridrag", "azure_deployment")
api_version = keyring.get_password("hybridrag", "azure_api_version")

if not endpoint or not api_key:
    print("  [ERROR] Missing credentials. Run rag-store-endpoint and rag-store-key.")
    sys.exit(1)

url_lower = endpoint.lower()
is_azure = ("azure" in url_lower or ".openai.azure.com" in url_lower 
            or "aoai" in url_lower or "azure-api" in url_lower
            or "cognitiveservices" in url_lower)

base = endpoint.rstrip("/")
d = "(not-applicable)"
v = (
    os.environ.get("AZURE_OPENAI_API_VERSION")
    or api_version
    or "2024-02-01"
)

if is_azure:
    if "/chat/completions" in endpoint:
        final_url = base
        if "api-version" not in base:
            final_url += "?api-version=" + v
        d = "(from endpoint URL)"
    elif "/deployments/" in endpoint:
        final_url = f"{base}/chat/completions?api-version={v}"
        d = "(from endpoint URL)"
    else:
        d = (
            os.environ.get("AZURE_OPENAI_DEPLOYMENT")
            or os.environ.get("AZURE_DEPLOYMENT")
            or os.environ.get("OPENAI_DEPLOYMENT")
            or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
            or os.environ.get("DEPLOYMENT_NAME")
            or deployment
        )
        if not d:
            d = "gpt-35-turbo"
        final_url = f"{base}/openai/deployments/{d}/chat/completions?api-version={v}"
    
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    print(f"  Provider:  AZURE")
    print(f"  Auth:      api-key header")
    print(f"  Deployment: {d}")
    print(f"  API Ver:    {v}")
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
import urllib.request, urllib.error, ssl

req = urllib.request.Request(final_url, data=json.dumps(payload).encode("utf-8"),
                             headers=headers, method="POST")
ctx = ssl.create_default_context()
start = time.time()

try:
    response = urllib.request.urlopen(req, context=ctx, timeout=30)
    latency = time.time() - start
    body = json.loads(response.read().decode("utf-8"))
    
    print(f"  Status:    200 OK")
    print(f"  Latency:   {latency:.2f}s")
    if "choices" in body and body["choices"]:
        print(f"  Response:  {body['choices'][0]['message']['content']}")
        print(f"  Model:     {body.get('model', 'unknown')}")
    if "usage" in body:
        u = body["usage"]
        print(f"  Tokens:    {u.get('prompt_tokens','?')} in, {u.get('completion_tokens','?')} out")
    print()
    print("  [SUCCESS] API is working!")

except urllib.error.HTTPError as e:
    latency = time.time() - start
    error_body = ""
    try: error_body = e.read().decode("utf-8")
    except Exception: pass
    print(f"  Status:    {e.code} {e.reason}")
    print(f"  Latency:   {latency:.2f}s")
    if error_body: print(f"  Response:  {error_body[:500]}")
    print()
    if e.code == 401:
        print("  [FAIL] Auth error. Key may be wrong/expired, or header format is wrong.")
    elif e.code == 404:
        print("  [FAIL] Not found. Deployment name or API version may be wrong.")
        print("  >> Run rag-store-deployment to set the correct name.")
    elif e.code == 403:
        print("  [FAIL] Forbidden. Key may lack permission for this deployment.")
    elif e.code == 429:
        print("  [FAIL] Rate limited. Wait a minute.")
    else:
        print(f"  [FAIL] HTTP {e.code}")

except urllib.error.URLError as e:
    latency = time.time() - start
    print(f"  [FAIL] Connection error: {e.reason}")
    print("  >> Check VPN/proxy/network settings.")

except Exception as e:
    print(f"  [FAIL] Unexpected: {e}")
