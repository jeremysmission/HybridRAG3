# Session 16: Dual-Environment API Layer (Home + Work)

**Date:** 2026-02-25
**Scope:** Provider config, proxy/CA auto-detection, government endpoint support
**Test result:** 220 passed, 1 skipped, 0 failed

---

## Problem

The same codebase runs on two machines with different API environments:

- **Home PC** -- Commercial Azure OpenAI (`*.openai.azure.com`), direct internet, default CA bundle, no proxy.
- **Work laptop** -- Azure Government OpenAI (`*.openai.azure.us`), corporate HTTPS proxy, custom CA bundle issued by the corporate root CA.

Before this change, the code failed on the work laptop for three reasons:

1. **Wrong SDK client.** Azure detection relied on the substring `"azure"` in the endpoint URL. Government endpoints (`.azure.us`) happened to match, but enterprise proxy URLs or unusual hostnames might not. There was no way to force Azure mode when auto-detection guessed wrong.

2. **No proxy support.** All `httpx.Client()` calls used bare defaults. On the corporate network, outbound HTTPS goes through a mandatory proxy (`HTTPS_PROXY` env var). Without passing that proxy to httpx, connections to Azure Government timed out or got rejected by the firewall.

3. **No CA bundle support.** The corporate proxy performs TLS inspection using a private root CA. Python's default CA store doesn't include it. The standard workaround is `REQUESTS_CA_BUNDLE` or `SSL_CERT_FILE` env vars pointing at the corporate bundle. httpx wasn't reading those.

---

## What Changed

### 1. Provider field in config and credentials

**Files:** `src/core/config.py`, `src/security/credentials.py`, `config/default_config.yaml`

Added `provider` and `auth_scheme` fields to `APIConfig`:

- `provider` accepts `"azure"`, `"azure_gov"`, `"openai"`, or empty string (auto-detect from URL).
- `auth_scheme` accepts `"api_key"`, `"bearer"`, or empty string (auto-detect from provider).

The `provider` field resolves through the same priority chain as other credentials: keyring > env var (`HYBRIDRAG_API_PROVIDER`) > config YAML. This means the work laptop can set `HYBRIDRAG_API_PROVIDER=azure_gov` in its environment and the home PC can leave it empty for auto-detection.

### 2. httpx client factory

**File:** `src/core/llm_router.py`

Added `_build_httpx_client()` -- a single factory function that creates every `httpx.Client` in the module. It:

- Reads `HTTPS_PROXY` / `HTTP_PROXY` from the environment and passes it to httpx.
- Reads `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE` and passes the path as `verify=`.
- Accepts `localhost_only=True` which forces `proxy=None`. Ollama and vLLM always use this flag because corporate proxies break localhost connections.

All four bare `httpx.Client()` calls in the file were replaced:
- OllamaRouter: `localhost_only=True`
- VLLMRouter: `localhost_only=True`
- APIRouter (Azure SDK http_client): uses factory with proxy + CA
- Deployment discovery (2 context-manager clients): uses factory with proxy + CA

### 3. Provider-aware APIRouter

**File:** `src/core/llm_router.py`

`APIRouter.__init__` now accepts `provider_override`. When set to `"azure"` or `"azure_gov"`, it forces `is_azure=True` and creates an `AzureOpenAI` client regardless of URL pattern. When set to `"openai"`, it forces `is_azure=False`. When empty, the original URL-sniffing logic runs unchanged.

The provider flows through the full chain: `resolve_credentials()` -> `LLMRouter.__init__` -> `APIRouter.__init__`.

### 4. Class size enforcement

Promoting `_resolve_deployment()` and `_resolve_api_version()` from `@staticmethod` methods to module-level functions kept `APIRouter` under the 500-line class limit enforced by `test_core_classes_under_500_lines`.

---

## Files Modified

| File | What changed |
|------|-------------|
| `src/core/config.py` | Added `provider`, `auth_scheme` to `APIConfig` |
| `config/default_config.yaml` | Added `provider: ''`, `auth_scheme: ''` under `api:` |
| `src/security/credentials.py` | Added `provider` + `source_provider` to `ApiCredentials`, `PROVIDER_ENV_ALIASES`, `KEYRING_PROVIDER_NAME`, provider resolution in `resolve_credentials()`, updated `credential_status()` and `to_diagnostic_dict()` |
| `src/core/llm_router.py` | Added `_build_httpx_client()` factory, replaced 4 bare `httpx.Client()` calls, added `provider_override` to `APIRouter`, wired provider through `LLMRouter`, promoted 2 static methods to module-level |

## Files Created

| File | What it contains |
|------|-----------------|
| `tests/test_provider_proxy.py` | 20 tests: proxy env flow, CA bundle detection, localhost safety, provider detection (azure/azure_gov/openai/auto), credential resolution, config loading |

---

## How to Configure Each Machine

### Home PC (no changes needed)

Leave `provider` empty. Auto-detection sees `"azure"` in the commercial endpoint URL and creates an `AzureOpenAI` client. No proxy, default CA bundle.

### Work Laptop

Set three environment variables (or store via keyring):

```
HYBRIDRAG_API_PROVIDER=azure_gov
HTTPS_PROXY=http://proxy.corp.internal:8080
REQUESTS_CA_BUNDLE=C:\corp\ca-bundle.crt
```

The provider forces Azure client creation. The proxy routes traffic through the corporate gateway. The CA bundle lets TLS inspection succeed.

---

## Test Coverage

20 new tests across 4 classes:

- **TestBuildHttpxClient** (5 tests) -- proxy env var flows to httpx, CA bundle from `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`, `localhost_only` forces `proxy=None`, default has no proxy.
- **TestProviderDetection** (7 tests) -- commercial Azure auto-detect, government `.azure.us` auto-detect, explicit `azure_gov` forces Azure, explicit `openai` forces non-Azure, OpenRouter non-Azure, provider in status output, government base URL extraction.
- **TestProviderCredentialResolution** (5 tests) -- provider from env var, from config dict, from keyring (with priority over env), in `credential_status()` output, in `to_diagnostic_dict()`.
- **TestConfigProviderFields** (3 tests) -- `APIConfig` defaults to empty, `auth_scheme` defaults to empty, `load_config()` reads provider from YAML.

Full regression: **220 passed, 1 skipped, 0 failed.**
