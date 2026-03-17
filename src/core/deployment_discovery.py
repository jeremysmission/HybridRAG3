# ============================================================================
# deployment_discovery.py -- Model deployment discovery for Azure/OpenAI
# ============================================================================
#
# Extracted from llm_router.py to keep each module under 500 lines.
# Detects available models on Azure or OpenAI endpoints.
#
# AZURE PATH:
#   GET {base}/openai/deployments?api-version={version}
#   Header: api-key: {key}
#
# OPENAI/OPENROUTER PATH:
#   GET {endpoint}/models
#   Header: Authorization: Bearer {key}
#
# INTERNET ACCESS: YES (one GET request per call)
# ============================================================================

import logging
import threading

from .llm_response import _build_httpx_client, _DEFAULT_API_VERSION
from .api_router import _is_azure_endpoint, _filter_banned_deployments

logger = logging.getLogger(__name__)

# Module-level cache for deployment discovery results.
_deployment_cache = None
_deployment_lock = threading.Lock()


def get_available_deployments():
    """
    Discover available model deployments from the configured endpoint.

    Detects Azure vs OpenAI from the stored endpoint URL and uses the
    correct API path and auth header format for each.

    Returns:
        list: Deployment name strings. Empty list if endpoint is
              unreachable or credentials are missing. Never raises.
    """
    global _deployment_cache
    if _deployment_cache is not None:
        return list(_deployment_cache)

    with _deployment_lock:
        # Double-check inside lock
        if _deployment_cache is not None:
            return list(_deployment_cache)
        return _get_deployments_locked()


def _get_deployments_locked():
    """Inner deployment discovery, called under _deployment_lock."""
    global _deployment_cache

    # Resolve credentials from the canonical source
    try:
        from ..security.credentials import resolve_credentials
        creds = resolve_credentials()
    except Exception:
        logger.error("[FAIL] Could not resolve credentials for deployment discovery")
        return []

    if not creds.has_key or not creds.has_endpoint:
        logger.error("[FAIL] Credentials incomplete -- need both API key and endpoint")
        return []

    endpoint = creds.endpoint.rstrip("/")
    api_key = creds.api_key

    try:
        if _is_azure_endpoint(endpoint):
            # Azure path: GET {base}/openai/deployments?api-version={version}
            api_version = creds.api_version or _DEFAULT_API_VERSION

            # Strip any existing path to get just the base domain
            base = endpoint
            idx = base.lower().find("/openai/")
            if idx > 0:
                base = base[:idx]
            idx = base.find("?")
            if idx > 0:
                base = base[:idx]

            url = f"{base}/openai/deployments?api-version={api_version}"

            with _build_httpx_client(timeout=3) as client:
                resp = client.get(
                    url,
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code != 200:
                logger.warning("[WARN] Azure deployment list returned HTTP %s", resp.status_code)
                _deployment_cache = []
                return []

            data = resp.json()
            # Azure returns {"value": [{...}, ...]}
            value_list = data.get("value", [])
            if not isinstance(value_list, list):
                _deployment_cache = []
                return []

            deployments = []
            for item in value_list:
                dep_id = item.get("id", "") or item.get("name", "")
                if dep_id:
                    deployments.append(dep_id)

            deployments = _filter_banned_deployments(deployments)
            _deployment_cache = deployments
            logger.info("[OK] Found %d Azure deployments", len(deployments))
            return list(deployments)

        else:
            # OpenAI/OpenRouter path: GET {endpoint}/models
            url = f"{endpoint}/models"

            with _build_httpx_client(timeout=3) as client:
                resp = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code != 200:
                logger.warning("[WARN] Model list returned HTTP %s", resp.status_code)
                _deployment_cache = []
                return []

            data = resp.json()

            if "data" in data and isinstance(data["data"], list):
                models = [m.get("id", "") for m in data["data"] if m.get("id")]
            elif isinstance(data, list):
                models = [m.get("id", "") for m in data if m.get("id")]
            else:
                _deployment_cache = []
                return []

            models = _filter_banned_deployments(sorted(models))
            _deployment_cache = models
            logger.info("[OK] Found %d models", len(models))
            return list(_deployment_cache)

    except Exception as e:
        logger.warning("[WARN] Deployment discovery failed: %s", e)
        _deployment_cache = []
        return []


def refresh_deployments():
    """
    Clear the deployment cache and re-probe the endpoint.

    Returns:
        list: Fresh deployment list from the endpoint.
    """
    global _deployment_cache
    _deployment_cache = None
    result = get_available_deployments()
    logger.info("[OK] Deployment cache refreshed: %d deployments", len(result))
    return result


def invalidate_deployment_cache():
    """Clear the deployment cache without re-probing.

    Called on mode switch to ensure stale model lists from a previous
    mode don't persist.
    """
    global _deployment_cache
    with _deployment_lock:
        _deployment_cache = None
