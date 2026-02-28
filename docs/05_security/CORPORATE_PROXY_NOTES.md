# Corporate Proxy Bypass -- Research Notes

## Problem (2026-02-27)
Work machine gets `HTTP/1.1 301 Moved Permanently` when the embedder
calls Ollama at `http://127.0.0.1:11434/api/embed`. Home machine works fine.

## Root Cause
Corporate machines have `HTTP_PROXY` / `HTTPS_PROXY` set as system
environment variables. Python httpx reads these by default (`trust_env=True`)
and routes even 127.0.0.1 traffic through the corporate proxy. The proxy
sees a request for its own localhost and returns 301.

`proxy=None` alone is NOT enough. It just means "no explicit proxy" but
httpx still checks env vars when `trust_env=True` (the default).

## The Fix
```python
httpx.Client(proxy=None, trust_env=False)
```
`trust_env=False` disables ALL environment-based proxy detection:
- Ignores HTTP_PROXY, HTTPS_PROXY, ALL_PROXY env vars
- Ignores Windows registry proxy settings (via urllib.request.getproxies())
- All requests go direct through TCP

Applied to every httpx.Client that connects to localhost/127.0.0.1:
- `src/core/embedder.py` (embedding calls)
- `src/core/llm_router.py` (Ollama LLM factory, localhost_only branch)
- `src/core/golden_probe_checks.py` (Ollama connectivity probe)
- `src/gui/panels/api_admin_tab.py` (Ollama tags queries, 2 places)
- `tools/selftest_ollama.py` (diagnostic tool)

NOT applied to external API clients (they need the corporate proxy):
- `scripts/_model_meta.py` (Azure OpenAI model list)
- `src/core/golden_probe_checks.py` line 293 (API endpoint probe)

## Why Ollama Is Innocent
Ollama source code (`server/routes.go`) has zero redirect logic.
It does not support HTTPS natively (SSL PR #1310 was rejected).
The 301 comes from the corporate proxy, not Ollama.

## Additional Protections Already In Place
- `start_gui.bat` sets `NO_PROXY=localhost,127.0.0.1`
- `src/core/boot.py` uses `urllib.request.ProxyHandler({})` for Ollama check
- `src/core/embedder.py` has `_assert_no_redirect()` guard (fails fast on 3xx)
- `src/core/embedder.py` has `follow_redirects=False` (never silently follows)
- `src/core/embedder.py` uses `http://127.0.0.1` not `localhost` (avoids DNS)

## httpx Proxy Detection Chain (reference)
1. `httpx.Client()` calls `get_environment_proxies()`
2. Which calls `urllib.request.getproxies()`
3. Which checks: env vars first, then Windows registry (`ProxyServer` when `ProxyEnable=1`)
4. Does NOT handle WPAD/PAC auto-configuration
5. `trust_env=False` skips step 1 entirely

## Diagnostic Commands for Work Machine
```powershell
# Check Windows proxy settings
netsh winhttp show proxy

# Check environment variables
echo %HTTP_PROXY%
echo %HTTPS_PROXY%
echo %NO_PROXY%

# Raw TCP test (bypasses all proxy)
python -c "import socket; s=socket.create_connection(('127.0.0.1',11434),3); print('OK'); s.close()"

# httpx test with trust_env=False
python -c "import httpx; r=httpx.get('http://127.0.0.1:11434/', trust_env=False, timeout=5); print(r.status_code)"
```

## Key Sources
- httpx Discussion #1513: "httpx uses proxy unexpectedly on windows"
- httpx Issue #1536: "Respect system proxy exclusions" (unresolved)
- Ollama FAQ: "Avoid setting HTTP_PROXY. Setting HTTP_PROXY may interrupt client connections to the server."
- Ollama Issue #1546: HTTPS_PROXY must be on `ollama serve` process, not `ollama run`
- psf/requests #879: "Issues with HTTP proxy and accessing localhost"
- security.stackexchange Post 199282: "set a no_proxy environment variable"
