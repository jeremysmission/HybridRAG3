#!/usr/bin/env python
# ============================================================================
# setup_online_api.py -- One-shot online API setup + validation
# ============================================================================
# WHAT:
#   Interactive helper for new machines:
#     1) Store API key
#     2) Store endpoint
#     3) Store deployment + api version (Azure)
#     4) Run a live API probe
#
# USAGE:
#   python tools/py/setup_online_api.py
#   python tools/py/setup_online_api.py --endpoint https://... --deployment gpt-4o --api-version 2024-02-01
# ============================================================================

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))

from src.security.credentials import (  # noqa: E402
    clear_credentials,
    resolve_credentials,
    store_api_key,
    store_api_version,
    store_deployment,
    store_endpoint,
    validate_endpoint,
    invalidate_credential_cache,
)


def _prompt(label: str, default: str = "") -> str:
    if default:
        text = input(f"{label} [{default}]: ").strip()
        return text or default
    return input(f"{label}: ").strip()


def _is_azure(endpoint: str) -> bool:
    lower = (endpoint or "").lower()
    return ("azure" in lower) or ("aoai" in lower) or ("cognitiveservices" in lower)


def _build_probe(endpoint: str, deployment: str, api_version: str) -> tuple[str, dict]:
    base = endpoint.rstrip("/")
    if _is_azure(base):
        if not deployment:
            raise ValueError("Azure requires a deployment name.")
        url = f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        return url, {"auth": "api-key"}
    url = f"{base}/v1/chat/completions"
    return url, {"auth": "bearer"}


def _probe(endpoint: str, api_key: str, deployment: str, api_version: str) -> tuple[bool, str]:
    url, meta = _build_probe(endpoint, deployment, api_version)
    payload = {
        "messages": [{"role": "user", "content": "Reply with exactly: ONLINE_OK"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if meta["auth"] == "api-key":
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    ctx = ssl.create_default_context()
    start = time.time()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        latency = time.time() - start
        model = body.get("model", "unknown")
        text = ""
        if isinstance(body.get("choices"), list) and body["choices"]:
            text = body["choices"][0].get("message", {}).get("content", "")
        return True, f"200 OK ({latency:.2f}s) model={model} response={text!r}"
    except urllib.error.HTTPError as e:
        latency = time.time() - start
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            detail = ""
        return False, f"HTTP {e.code} ({latency:.2f}s) {e.reason} {detail}"
    except Exception as e:
        latency = time.time() - start
        return False, f"{type(e).__name__} ({latency:.2f}s): {e}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--deployment", default="")
    parser.add_argument("--api-version", default="")
    parser.add_argument("--clear-first", action="store_true")
    args = parser.parse_args()

    if args.clear_first:
        clear_credentials()
        invalidate_credential_cache()
        print("[OK] Cleared existing credentials.")

    existing = resolve_credentials(use_cache=False)

    key_default = args.key or (existing.api_key or "")
    endpoint_default = args.endpoint or (existing.endpoint or "")
    deployment_default = args.deployment or (existing.deployment or "")
    api_ver_default = args.api_version or (existing.api_version or "2024-02-01")

    print("Online API setup")
    print("----------------")
    key = _prompt("API Key", key_default)
    endpoint = _prompt("Endpoint (base URL only)", endpoint_default)
    endpoint = validate_endpoint(endpoint)

    deployment = _prompt("Deployment", deployment_default)
    api_version = _prompt("API Version", api_ver_default)

    store_api_key(key)
    store_endpoint(endpoint)
    if deployment:
        store_deployment(deployment)
    if api_version:
        store_api_version(api_version)
    invalidate_credential_cache()

    print("[OK] Stored credentials.")
    print(f"[OK] Endpoint:   {endpoint}")
    print(f"[OK] Deployment: {deployment or '(not set)'}")
    print(f"[OK] API Ver:    {api_version or '(not set)'}")

    ok, msg = _probe(endpoint, key, deployment, api_version)
    if ok:
        print(f"[OK] Probe: {msg}")
        return 0
    print(f"[FAIL] Probe: {msg}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
