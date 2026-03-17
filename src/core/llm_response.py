# ============================================================================
# llm_response.py -- LLMResponse dataclass + shared utility functions
# ============================================================================
#
# Extracted from llm_router.py to keep each module under 500 lines.
# Contains the shared response format and helper functions used by all
# router classes (OllamaRouter, VLLMRouter, APIRouter, LLMRouter).
# ============================================================================

import os
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default Azure API version -- used as the last-resort fallback when no
# version is configured via YAML, environment variable, or URL parameter.
# IMPORTANT: Must match api_client_factory.py DEFAULT_AZURE_API_VERSION
# so that both modules agree on the default. The exhaustive virtual test
# (SIM-04) cross-checks these values to prevent version drift.
_DEFAULT_API_VERSION = "2024-02-02"


# ============================================================================
# LLMResponse -- The standard answer format
# ============================================================================
# Every backend (Ollama, Azure, OpenAI) returns its answer wrapped in
# this same structure. That way the rest of HybridRAG doesn't care
# which backend answered -- it always gets the same fields.
# ============================================================================
@dataclass
class LLMResponse:
    """Standardized response from any LLM backend."""
    text: str              # The actual AI-generated answer
    tokens_in: int         # How many tokens were in the prompt
    tokens_out: int        # How many tokens the AI generated
    model: str             # Which model answered (e.g., "phi4-mini")
    latency_ms: float      # How long the call took in milliseconds


# ============================================================================
# _build_httpx_client -- Factory for all HTTP clients in this module
# ============================================================================
#
# WHY A FACTORY:
#   Different environments need different HTTP settings:
#     - Home PC:     direct internet, default CA bundle, no proxy
#     - Work laptop: enterprise proxy, custom CA bundle, HTTPS_PROXY env var
#     - Localhost:   Ollama/vLLM -- must NEVER use a proxy
#
#   Instead of sprinkling proxy/CA logic into each router class, this
#   factory centralizes it. Every httpx.Client() in this file goes
#   through here.
#
# AUTO-DETECTION:
#   - HTTPS_PROXY / https_proxy env var -> sets proxy for outbound calls
#   - REQUESTS_CA_BUNDLE / SSL_CERT_FILE / CURL_CA_BUNDLE -> sets verify path
#   - If neither is set, uses httpx defaults (system CA, no proxy)
#
# LOCALHOST SAFETY:
#   Ollama and vLLM talk to localhost. Enterprise proxies break localhost
#   connections. Pass localhost_only=True to force proxy=None.
# ============================================================================

def _build_httpx_client(
    timeout: float = 30.0,
    localhost_only: bool = False,
    verify: bool = True,
):
    """
    Build an httpx.Client with environment-aware proxy and CA settings.

    Args:
        timeout:        Request timeout in seconds.
        localhost_only:  If True, proxy is forced to None (for Ollama/vLLM).
        verify:         SSL verification. True = use CA bundle, False = skip.

    Returns:
        Configured httpx.Client ready for use.
    """
    import httpx

    kwargs = {
        "timeout": httpx.Timeout(timeout),
    }

    # -- CA bundle detection --
    # Enterprise environments often set one of these to point at a custom
    # CA bundle that includes the local root CA. Without it, SSL
    # handshakes to Azure Government endpoints fail with CERTIFICATE_VERIFY_FAILED.
    if verify:
        ca_bundle = (
            os.environ.get("REQUESTS_CA_BUNDLE")
            or os.environ.get("SSL_CERT_FILE")
            or os.environ.get("CURL_CA_BUNDLE")
        )
        if ca_bundle and os.path.isfile(ca_bundle):
            kwargs["verify"] = ca_bundle
        else:
            kwargs["verify"] = True
    else:
        kwargs["verify"] = False

    # -- Proxy detection --
    # Localhost traffic must NEVER go through a proxy. Enterprise proxies
    # intercept localhost connections and return garbage (301/502, HTML).
    # trust_env=False is REQUIRED in addition to proxy=None because
    # httpx still reads HTTP_PROXY env vars when trust_env=True (default).
    if localhost_only:
        kwargs["proxy"] = None
        kwargs["trust_env"] = False
    else:
        # Let httpx handle proxy via trust_env=True (default).
        # httpx natively reads HTTP_PROXY/HTTPS_PROXY AND respects
        # NO_PROXY.  Setting an explicit proxy= bypasses NO_PROXY
        # semantics, which breaks enterprise environments where
        # NO_PROXY is used to exempt internal/local targets.
        kwargs["trust_env"] = True

    return httpx.Client(**kwargs)


def _openai_sdk_available():
    """Check if the openai SDK is installed (lazy, no import at module load)."""
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def _call_stream_with_optional_cancel(method, prompt: str, cancel_event):
    """Call a stream method with cancel_event when supported."""
    try:
        return method(prompt, cancel_event=cancel_event)
    except TypeError as exc:
        if "cancel_event" not in str(exc):
            raise
        return method(prompt)


def _safe_timeout_seconds(raw_timeout: Any, default: float = 120.0) -> float:
    """Parse configured timeout values defensively."""
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        timeout = default
    return max(timeout, 0.01)


def _http_error_message(error: Exception) -> str:
    """Include backend-provided error details when an HTTP call fails."""
    message = f"{type(error).__name__}: {error}"
    response = getattr(error, "response", None)
    if response is None:
        return message

    detail = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            detail = str(data.get("error", "") or "").strip()
    except Exception:
        detail = ""

    if not detail:
        try:
            detail = str(getattr(response, "text", "") or "").strip()
        except Exception:
            detail = ""

    if detail:
        return f"{message} | {detail}"
    return message


def _ollama_retry_model_name(router, attempted_model: str, error: Exception) -> str:
    """Retry with a fresh tag probe when Ollama rejects a cold-cache alias."""
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", 0) if response is not None else 0
    if status_code and status_code < 500 and status_code != 404:
        return ""

    refreshed = router._resolve_model_name(
        router.config.ollama.model,
        allow_network=True,
    )
    if refreshed and refreshed != attempted_model:
        router.logger.info(
            "ollama_model_retry_refresh",
            configured=router.config.ollama.model,
            attempted=attempted_model,
            refreshed=refreshed,
            status_code=status_code or None,
        )
        return refreshed
    return ""
