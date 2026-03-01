# HybridRAG3 -- Online API Setup From Scratch

Last updated: 2026-03-01

This guide is for a new machine where online mode is not working yet.

## Goal

Get online query working with:
- Correct endpoint
- Correct API key
- Correct Azure deployment
- Correct API version

And verify with a real completion call.

## One-Command Method (Recommended)

From repo root:

```powershell
python .\tools\py\setup_online_api.py
```

Enter:
1. API Key
2. Endpoint (base URL only)
3. Deployment (example: `gpt-4o`)
4. API Version (example: `2024-02-01`)

The script stores credentials and runs a live probe.

## Manual Method (Step-by-Step)

From repo root:

1. Store key:

```powershell
python .\tools\py\store_key.py "YOUR_API_KEY"
```

2. Store endpoint + deployment + version:

```powershell
python .\tools\py\store_endpoint.py https://your-endpoint.example.com/
```

3. Verify stored values:

```powershell
python .\tools\py\show_creds.py
```

4. Run verbose API test:

```powershell
python .\tools\py\test_api_verbose.py
```

Expected success pattern:
- `Status: 200 OK`
- model name returned
- `[SUCCESS] API is working!`

## GUI Usage After CLI Setup

1. Start GUI.
2. Switch to Online mode.
3. In Query panel ask:

`Reply with exactly: ONLINE_OK`

If answer appears, online path is working.

## Critical Rules

1. Endpoint must be base URL only.
- Good: `https://aiml-aoai-api.gc1.mycompany.com/`
- Bad: full path ending in `/openai/deployments/.../chat/completions?...`

2. Deployment and API version must be set.
- Missing deployment/version can silently fall back to old defaults and fail.

3. Do not rely only on GUI "Test Connection".
- Use `test_api_verbose.py` as authoritative proof.

## Common Failure Patterns

1. `HTTP 410 ModelDeprecated`
- Deployment points to retired model (often old `gpt-35-turbo` deployment).
- Fix deployment to active one (example: `gpt-4o`).

2. `HTTP 500` on deployment listing
- Enterprise proxy/APIM may block listing endpoint.
- Chat completions can still work with explicit deployment.

3. API client not ready
- Usually SDK/env mismatch or wrong Python environment.
- Verify:

```powershell
python -c "import openai, httpx; print(openai.__version__, httpx.__version__)"
```

Expected in this repo:
- `openai 1.109.1`
- `httpx 0.28.1`

4. Test script keeps showing old deployment
- Set deployment in keyring and clear stale env overrides:

```powershell
Remove-Item Env:AZURE_OPENAI_DEPLOYMENT -ErrorAction SilentlyContinue
Remove-Item Env:OPENAI_DEPLOYMENT -ErrorAction SilentlyContinue
Remove-Item Env:AZURE_OPENAI_API_VERSION -ErrorAction SilentlyContinue
```

Then rerun `store_endpoint.py` and `test_api_verbose.py`.

## Recommended Demo Defaults

- Deployment: `gpt-4o`
- API version: `2024-02-01` (or tenant-required version)
- Prompt sanity test: `Reply with exactly: ONLINE_OK`

