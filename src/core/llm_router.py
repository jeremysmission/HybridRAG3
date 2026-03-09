# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the llm router part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# llm_router.py -- LLM Backend Router (Offline + Online)
# ============================================================================
#
# WHAT: The "switchboard" that decides where AI queries go based on mode.
#
# WHY:  The rest of HybridRAG should not care whether answers come from
#       a local model or a cloud API. This module hides that complexity
#       behind a single query() method. It also handles credential
#       resolution, model discovery, and error classification so callers
#       get clean results or clear error messages.
#
# HOW:  Four backend router classes, one orchestrator:
#       - OllamaRouter:  localhost Ollama server (offline, free)
#       - VLLMRouter:    localhost vLLM server (workstation, free, faster)
#       - APIRouter:     Azure/OpenAI cloud API (online, costs money)
#       - LLMRouter:     The orchestrator that picks the right backend
#
# USAGE:
#       router = LLMRouter(config)
#       answer = router.query("What is the operating frequency?")
#       # or stream:
#       for chunk in router.query_stream("What is X?"):
#           print(chunk.get("token", ""), end="")
#
# FILE LAYOUT (section markers for navigation):
#   Line ~70:   LLMResponse dataclass
#   Line ~95:   OllamaRouter (localhost Ollama)
#   Line ~310:  VLLMRouter (localhost vLLM)
#   Line ~500:  APIRouter (Azure/OpenAI cloud)
#   Line ~1060: Deployment Discovery (model listing)
#   Line ~1250: LLMRouter (main orchestrator)
#
# INTERNET ACCESS:
#   OllamaRouter -- NONE (talks to localhost only)
#   VLLMRouter   -- NONE (talks to localhost only)
#   APIRouter    -- YES (connects to Azure or OpenAI endpoint)
#
# DEPENDENCIES:
#   - httpx      (for Ollama/vLLM -- already installed)
#   - openai     (for Azure/OpenAI API -- lazy loaded)
#   - keyring    (optional, for credential storage)
# ============================================================================

import json
import os
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Generator

logger = logging.getLogger(__name__)

# Default Azure API version -- used as the last-resort fallback when no
# version is configured via YAML, environment variable, or URL parameter.
# IMPORTANT: Must match api_client_factory.py DEFAULT_AZURE_API_VERSION
# so that both modules agree on the default. The exhaustive virtual test
# (SIM-04) cross-checks these values to prevent version drift.
_DEFAULT_API_VERSION = "2024-02-02"

# -- httpx and OpenAI SDK are imported lazily at first use -------------------
# httpx pulls in rich.console (~60ms). Deferring it saves startup time
# when the user hasn't queried yet. OpenAI SDK (~50ms) is also lazy.
# ---------------------------------------------------------------------------


# ============================================================================
# _build_httpx_client -- Factory for all HTTP clients in this module
# ============================================================================
#
# WHY A FACTORY:
#   Different environments need different HTTP settings:
#     - Home PC:     direct internet, default CA bundle, no proxy
#     - Work laptop: corporate proxy, custom CA bundle, HTTPS_PROXY env var
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
#   Ollama and vLLM talk to localhost. Corporate proxies break localhost
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
    # Corporate environments often set one of these to point at a custom
    # CA bundle that includes the corporate root CA. Without it, SSL
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
    # Localhost traffic must NEVER go through a proxy. Corporate proxies
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
        # semantics, which breaks corporate environments where
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

# -- Import HybridRAG internals ---------------------------------------------
from .config import Config
from .model_identity import canonicalize_model_name, resolve_ollama_model_name
from .network_gate import get_gate, NetworkBlockedError
from .ollama_endpoint_resolver import sanitize_ollama_base_url
from ..monitoring.logger import get_app_logger


# --- SECTION 1: RESPONSE FORMAT -------------------------------------------

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


# --- SECTION 2: OLLAMA ROUTER (OFFLINE, LOCALHOST) -------------------------

# ============================================================================
# OllamaRouter -- Talks to local Ollama server (offline mode)
# ============================================================================
#
# Ollama runs on your machine at http://localhost:11434. It hosts
# open-source models like Phi-4 and Mistral that work without internet.
#
# This router uses raw httpx because Ollama has a simple REST API
# and doesn't need the openai SDK. No changes from the old version.
#
# INTERNET ACCESS: NONE (localhost only)
# ============================================================================
class OllamaRouter:
    """Route queries to local Ollama server (offline mode)."""

    def __init__(self, config: Config):
        """
        Set up the Ollama router.

        Args:
            config: The HybridRAG configuration object. We read:
                    - config.ollama.base_url (default: http://localhost:11434)
                    - config.ollama.model (default: phi4-mini)
                    - config.ollama.timeout_seconds (default: 120)
        """
        self.config = config
        self.logger = get_app_logger("ollama_router")
        self.last_error = ""

        # Base URL for the local Ollama server (sanitize typo-prone inputs)
        self.base_url = sanitize_ollama_base_url(config.ollama.base_url)
        self._tags_cache = None
        self._tags_ttl = 30
        try:
            self.config.ollama.base_url = self.base_url
        except Exception:
            pass

        # Persistent HTTP client -- localhost only, never proxied
        self._client = _build_httpx_client(
            timeout=config.ollama.timeout_seconds,
            localhost_only=True,
        )

        # Health check cache: (available: bool, timestamp: float) with TTL
        self._health_cache = None
        self._health_ttl = 30  # seconds between live checks

    def _build_options(self):
        """Build the Ollama options dict from config for generation speed.

        Centralised here so query() and query_stream() stay in sync.
        Keys with value 0 are omitted so Ollama uses its own defaults.
        """
        # Read temperature from ollama config first, fall back to api config
        temperature = getattr(self.config.ollama, "temperature", None)
        if temperature is None:
            temperature = getattr(self.config.api, "temperature", 0.05)
        opts = {
            "temperature": temperature,
            "num_ctx": self.config.ollama.context_window,
            "num_predict": getattr(self.config.ollama, "num_predict", 512),
        }
        num_thread = getattr(self.config.ollama, "num_thread", 0)
        if num_thread > 0:
            opts["num_thread"] = num_thread
        return opts

    def _available_models(self) -> list[str]:
        """Query /api/tags with short cache to avoid repeated roundtrips."""
        now = time.time()
        if self._tags_cache and (now - self._tags_cache[1]) < self._tags_ttl:
            return self._tags_cache[0]
        try:
            r = self._client.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                return []
            models = data.get("models", [])
            if not isinstance(models, list):
                return []
            names = [m.get("name", "") for m in models if isinstance(m, dict) and m.get("name")]
            self._tags_cache = (names, now)
            return names
        except Exception:
            return []

    def _cached_available_models(self) -> list[str]:
        """Return cached Ollama tags without forcing a new network roundtrip."""
        now = time.time()
        if self._tags_cache and (now - self._tags_cache[1]) < self._tags_ttl:
            return list(self._tags_cache[0])
        return []

    def _resolve_model_name(self, requested: str, allow_network: bool = False) -> str:
        """Resolve a model name with a cache-first fast path for query-time use."""
        req = canonicalize_model_name(requested)
        available = (
            self._available_models()
            if allow_network
            else self._cached_available_models()
        )
        if available:
            return resolve_ollama_model_name(req, available)
        return req

    def is_available(self) -> bool:
        """
        Check if Ollama is running and reachable.

        Returns:
            True if Ollama responds, False otherwise

        How it works:
            Sends a simple GET request to Ollama's root URL.
            If Ollama is running, it responds with "Ollama is running".
            If not, the connection fails and we return False.
        """
        # Return cached result if still fresh (avoids TCP roundtrip every 5s)
        now = time.time()
        if self._health_cache and (now - self._health_cache[1]) < self._health_ttl:
            return self._health_cache[0]

        try:
            get_gate().check_allowed(self.base_url, "ollama_health", "ollama_router")
            resp = self._client.get(self.base_url, timeout=5)
            result = resp.status_code == 200
        except (NetworkBlockedError, Exception):
            result = False

        self._health_cache = (result, now)
        return result

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to the local Ollama server.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        import httpx
        start_time = time.time()
        self.last_error = ""

        # -- Network gate check --
        try:
            get_gate().check_allowed(
                f"{self.base_url}/api/generate",
                "ollama_query", "ollama_router",
            )
        except NetworkBlockedError as e:
            self.last_error = f"NetworkBlockedError: {e}"
            self.logger.error("ollama_blocked_by_gate", error=str(e))
            return None

        # Build the request body for Ollama's /api/generate endpoint
        model_name = self._resolve_model_name(self.config.ollama.model)
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": getattr(self.config.ollama, "keep_alive", -1),
            "options": self._build_options(),
        }

        try:
            resp = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.ollama.timeout_seconds,
            )
            resp.raise_for_status()

            data = resp.json()
            response_text = data.get("response", "")
            prompt_eval_count = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            latency_ms = (time.time() - start_time) * 1000

            self.logger.info(
                "ollama_query_success",
                model=model_name,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                latency_ms=latency_ms,
            )

            return LLMResponse(
                text=response_text,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                model=model_name,
                latency_ms=latency_ms,
            )

        except httpx.HTTPError as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_http_error", error=str(e))
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_error", error=str(e))
            return None

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream tokens from the local Ollama server.

        Yields dicts with either:
          {"token": str}        -- a partial text token
          {"done": True, ...}   -- final metadata (tokens_in, tokens_out, model, latency_ms)

        Returns nothing (via generator) if the call fails.
        """
        import httpx
        start_time = time.time()
        self.last_error = ""

        try:
            get_gate().check_allowed(
                f"{self.base_url}/api/generate",
                "ollama_query_stream", "ollama_router",
            )
        except NetworkBlockedError as e:
            self.last_error = f"NetworkBlockedError: {e}"
            self.logger.error("ollama_stream_blocked_by_gate", error=str(e))
            yield {"error": self.last_error, "backend": "ollama"}
            return

        model_name = self._resolve_model_name(self.config.ollama.model)
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": True,
            "keep_alive": getattr(self.config.ollama, "keep_alive", -1),
            "options": self._build_options(),
        }

        try:
            with self._client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.config.ollama.timeout_seconds,
            ) as response:
                response.raise_for_status()
                tokens_in = 0
                tokens_out = 0
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token_text = chunk.get("response", "")
                    if token_text:
                        yield {"token": token_text}
                    if chunk.get("done", False):
                        tokens_in = chunk.get("prompt_eval_count", 0)
                        tokens_out = chunk.get("eval_count", 0)
                        break

            latency_ms = (time.time() - start_time) * 1000
            self.logger.info(
                "ollama_stream_complete",
                model=model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
            yield {
                "done": True,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "model": model_name,
                "latency_ms": latency_ms,
            }

        except httpx.HTTPError as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_stream_http_error", error=str(e))
            yield {"error": self.last_error, "backend": "ollama"}
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_stream_error", error=str(e))
            yield {"error": self.last_error, "backend": "ollama"}

    def close(self):
        """Release the persistent HTTP client."""
        if hasattr(self, "_client") and self._client:
            self._client.close()


# --- SECTION 3: VLLM ROUTER (WORKSTATION OFFLINE, LOCALHOST) ---------------

# ============================================================================
# VLLMRouter -- Talks to local vLLM server (workstation offline mode)
# ============================================================================
#
# vLLM serves an OpenAI-compatible API on localhost. It provides:
#   - Continuous batching (multiple concurrent queries)
#   - Prefix caching (repeated prompt prefixes are free)
#   - Tensor parallelism (split one model across both RTX 3090s)
#   - 2-3x faster generation than Ollama for the same model
#
# The router uses raw httpx (same as OllamaRouter) to POST to the
# OpenAI-compatible /v1/chat/completions endpoint. This avoids
# coupling to the openai SDK version.
#
# INTERNET ACCESS: NONE (localhost only)
# ============================================================================
class VLLMRouter:
    """Route queries to local vLLM server (workstation offline mode)."""

    def __init__(self, config: Config):
        """
        Set up the vLLM router.

        Args:
            config: The HybridRAG configuration object. We read:
                    - config.vllm.base_url (default: http://localhost:8000)
                    - config.vllm.model (default: phi4-mini)
                    - config.vllm.timeout_seconds (default: 120)
        """
        self.config = config
        self.logger = get_app_logger("vllm_router")
        self.last_error = ""

        self.base_url = config.vllm.base_url.rstrip("/")
        self.model = config.vllm.model
        self.timeout = config.vllm.timeout_seconds

        # Persistent HTTP client -- localhost only, never proxied
        self._client = _build_httpx_client(
            timeout=config.vllm.timeout_seconds,
            localhost_only=True,
        )

        # Health check cache: (available: bool, timestamp: float) with TTL
        self._health_cache = None
        self._health_ttl = 30  # seconds between live checks

    def is_available(self) -> bool:
        """
        Check if vLLM is running and reachable.

        Sends GET to /health. vLLM returns 200 when ready.
        Result is cached for 30 seconds to avoid TCP roundtrips.
        """
        now = time.time()
        if self._health_cache and (now - self._health_cache[1]) < self._health_ttl:
            return self._health_cache[0]

        try:
            get_gate().check_allowed(
                f"{self.base_url}/health", "vllm_health", "vllm_router",
            )
            resp = self._client.get(f"{self.base_url}/health", timeout=5)
            result = resp.status_code == 200
        except (NetworkBlockedError, Exception):
            result = False

        self._health_cache = (result, now)
        return result

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to the local vLLM server via OpenAI-compatible API.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        import httpx
        start_time = time.time()
        self.last_error = ""

        try:
            get_gate().check_allowed(
                f"{self.base_url}/v1/chat/completions",
                "vllm_query", "vllm_router",
            )
        except NetworkBlockedError as e:
            self.last_error = f"NetworkBlockedError: {e}"
            self.logger.error("vllm_blocked_by_gate", error=str(e))
            return None

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        try:
            resp = self._client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            data = resp.json()
            choice = data.get("choices", [{}])[0]
            response_text = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            latency_ms = (time.time() - start_time) * 1000

            self.logger.info(
                "vllm_query_success",
                model=self.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )

            return LLMResponse(
                text=response_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=self.model,
                latency_ms=latency_ms,
            )

        except httpx.HTTPError as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_http_error", error=str(e))
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_error", error=str(e))
            return None

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream tokens from the local vLLM server via SSE.

        Yields dicts with either:
          {"token": str}        -- a partial text token
          {"done": True, ...}   -- final metadata
        """
        import httpx
        start_time = time.time()
        self.last_error = ""

        try:
            get_gate().check_allowed(
                f"{self.base_url}/v1/chat/completions",
                "vllm_query_stream", "vllm_router",
            )
        except NetworkBlockedError as e:
            self.last_error = f"NetworkBlockedError: {e}"
            self.logger.error("vllm_stream_blocked_by_gate", error=str(e))
            yield {"error": self.last_error, "backend": "vllm"}
            return

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

        try:
            tokens_in = 0
            tokens_out = 0
            with self._client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        break
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token_text = delta.get("content", "")
                    if token_text:
                        yield {"token": token_text}
                    usage = chunk.get("usage")
                    if usage:
                        tokens_in = usage.get("prompt_tokens", 0)
                        tokens_out = usage.get("completion_tokens", 0)

            latency_ms = (time.time() - start_time) * 1000
            self.logger.info(
                "vllm_stream_complete",
                model=self.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
            yield {
                "done": True,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "model": self.model,
                "latency_ms": latency_ms,
            }

        except httpx.HTTPError as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_stream_http_error", error=str(e))
            yield {"error": self.last_error, "backend": "vllm"}
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_stream_error", error=str(e))
            yield {"error": self.last_error, "backend": "vllm"}

    def close(self):
        """Release the persistent HTTP client."""
        if hasattr(self, "_client") and self._client:
            self._client.close()


# --- SECTION 4: API ROUTER (CLOUD, ONLINE MODE) ---------------------------

# ============================================================================
# APIRouter -- Talks to Azure OpenAI or standard OpenAI API
# ============================================================================
#
# THIS IS THE PART THAT CHANGED (February 2026):
#
#   OLD WAY (broke constantly):
#     - Hand-built the URL: base + /openai/deployments/gpt-35-turbo/...
#     - Hand-built the auth header: "api-key: ..." or "Bearer ..."
#     - Result: URL doubling (404), wrong headers (401)
#
#   NEW WAY (using official openai SDK):
#     - AzureOpenAI() client builds URLs automatically
#     - Auth headers are handled internally by the SDK
#     - Same approach your company's own example code uses
#     - Result: it just works
#
# The SDK auto-detects Azure vs standard OpenAI based on which
# client class you use:
#
#   Azure:    AzureOpenAI(azure_endpoint=..., api_key=..., api_version=...)
#   Standard: OpenAI(api_key=...)
#   Home dev: OpenAI(api_key=...)  <-- same as standard, different key
#
# INTERNET ACCESS: YES -- connects to API endpoint
# ============================================================================
def _resolve_deployment(config, endpoint_url):
    """
    Resolve Azure deployment name from config, env vars, URL, or fallback.

    Resolution order: YAML > env vars > URL extraction > "gpt-35-turbo".
    """
    import re

    if config.api.deployment:
        return config.api.deployment

    for var in [
        "AZURE_OPENAI_DEPLOYMENT", "AZURE_DEPLOYMENT",
        "OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME",
        "DEPLOYMENT_NAME", "AZURE_CHAT_DEPLOYMENT",
    ]:
        val = os.environ.get(var, "").strip()
        if val:
            return val

    if endpoint_url and "/deployments/" in endpoint_url:
        match = re.search(r"/deployments/([^/?]+)", endpoint_url)
        if match:
            return match.group(1)

    return "gpt-35-turbo"


def _resolve_api_version(config, endpoint_url):
    """
    Resolve Azure API version from config, env vars, URL, or fallback.

    Resolution order: YAML > env vars > URL extraction > "2024-02-02".
    """
    import re

    if config.api.api_version:
        return config.api.api_version

    for var in [
        "AZURE_OPENAI_API_VERSION", "AZURE_API_VERSION",
        "OPENAI_API_VERSION", "API_VERSION",
    ]:
        val = os.environ.get(var, "").strip()
        if val:
            return val

    if endpoint_url and "api-version=" in endpoint_url:
        match = re.search(r"api-version=([^&]+)", endpoint_url)
        if match:
            return match.group(1)

    return _DEFAULT_API_VERSION


# ============================================================================
# Prompt splitting for chat-based API models
# ============================================================================
# Chat models (GPT-4o, GPT-4-turbo, etc.) treat system-role messages as
# authoritative instructions and user-role messages as the user's input.
# When the entire RAG prompt (grounding rules + context + question) is sent
# as a single user message, the model treats the grounding rules as casual
# suggestions rather than strict directives.  Splitting the prompt into
# system (rules) + user (context + question) dramatically improves grounding.
#
# The prompt from QueryEngine._build_prompt() has a clear structure:
#   "You are a precise technical assistant. ..."  (system rules)
#   "\nContext:\n{chunks}\n\nQuestion: {query}\n\nAnswer:"  (user content)
# ============================================================================

_CONTEXT_MARKERS = ("\nContext:\n", "\nContext (may be empty/partial):\n")


def _extract_system_user(prompt: str) -> tuple:
    """Split a combined prompt into (system_text, user_text).

    Returns (system, user) if a Context boundary is found,
    or ("", prompt) if the prompt has no recognizable structure.
    """
    for marker in _CONTEXT_MARKERS:
        idx = prompt.find(marker)
        if idx >= 0:
            return prompt[:idx].strip(), prompt[idx + 1:].strip()
    return "", prompt


def _split_prompt_to_messages(prompt: str) -> list:
    """Split a combined prompt into system + user messages for chat API."""
    system_text, user_text = _extract_system_user(prompt)
    if system_text:
        return [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
    return [{"role": "user", "content": prompt}]


class APIRouter:
    """Route queries to Azure OpenAI or standard OpenAI API (online mode)."""

    def __init__(self, config: Config, api_key: str, endpoint: str = "",
                 deployment_override: str = "", api_version_override: str = "",
                 provider_override: str = ""):
        """
        Set up the API router using the official openai SDK.

        Args:
            config:   The HybridRAG configuration object
            api_key:  Your API key (from Credential Manager or env var)
            endpoint: Your API base URL (Azure endpoint or OpenAI base)
            deployment_override: Pre-resolved deployment name (from credentials.py).
                If provided, skips the internal _resolve_deployment() chain.
            api_version_override: Pre-resolved API version (from credentials.py).
                If provided, skips the internal _resolve_api_version() chain.
            provider_override: Explicit provider type from credentials/config.
                "azure" or "azure_gov" = use AzureOpenAI client.
                "openai" = use OpenAI client.
                Empty = auto-detect from endpoint URL (original behavior).

        What happens here:
            1. We figure out if this is Azure or standard OpenAI
            2. We resolve deployment name and API version from config/env
            3. We create the appropriate SDK client
            4. The client handles all URL/header construction from here on

        RESOLUTION ORDER for deployment and api_version:
            0. Override from resolve_credentials() (if provided by LLMRouter)
            1. config/config.yaml (api.deployment, api.api_version)
            2. Environment variables (AZURE_OPENAI_DEPLOYMENT, etc.)
            3. Extracted from endpoint URL (if it contains /deployments/xxx)
            4. Hardcoded fallback defaults (last resort)
        """
        self.config = config
        self.api_key = api_key
        self.logger = get_app_logger("api_router")
        self.last_error = ""
        self.provider = provider_override or ""
        self.http_api_client = None
        self._init_error = ""

        # Store the raw endpoint for diagnostics/status reporting
        self.base_endpoint = endpoint.rstrip("/") if endpoint else config.api.endpoint.rstrip("/")

        # -- Detect Azure vs standard OpenAI --
        # If provider is explicitly set, trust it. Otherwise auto-detect
        # from the endpoint URL. This matters because government endpoints
        # (.azure.us) were not caught by the old "azure" substring check
        # when stored as a bare base URL without "azure" in the hostname.
        if self.provider in ("azure", "azure_gov"):
            self.is_azure = True
        elif self.provider == "openai":
            self.is_azure = False
        else:
            # Auto-detect: "azure" catches both .azure.com and .azure.us
            # "aoai" is a common enterprise abbreviation for Azure OpenAI.
            self.is_azure = (
                "azure" in self.base_endpoint.lower()
                or "aoai" in self.base_endpoint.lower()
            )

        # -- Resolve deployment name --
        # If the canonical resolver already extracted deployment from URL
        # or env vars, use that directly (no duplicate resolution).
        if deployment_override:
            self.deployment = deployment_override
        else:
            # Fallback: run the local resolution chain
            self.deployment = _resolve_deployment(config, self.base_endpoint)

        # -- Resolve API version --
        if api_version_override:
            self.api_version = api_version_override
        else:
            self.api_version = _resolve_api_version(config, self.base_endpoint)

        # -- Network gate check --
        # Verify the endpoint is allowed before we even create the SDK client.
        # This is an early fail-fast check. The gate also checks on each
        # query() call, but catching it here gives a clearer error message
        # during startup rather than on the first query.
        try:
            get_gate().check_allowed(
                self.base_endpoint, "api_client_init", "api_router",
            )
        except NetworkBlockedError as e:
            self.client = None
            self.logger.error(
                "api_endpoint_blocked_by_gate",
                endpoint=self.base_endpoint,
                error=str(e),
            )
            return

        # -- Lazy import openai SDK (not loaded at module level) --
        try:
            from openai import AzureOpenAI, OpenAI
        except ImportError:
            self.client = None
            self._init_error = "openai SDK missing"
            self.logger.error(
                "openai_sdk_missing",
                hint="Run: pip install openai",
            )
            return

        # -- Create the appropriate SDK client --
        #
        # WHY TWO DIFFERENT CLIENTS?
        #   Azure and standard OpenAI use different URL formats and auth
        #   methods. The SDK handles this automatically -- you just pick
        #   the right client class and it does the rest.
        #
        # AzureOpenAI client:
        #   - Builds URL: {endpoint}/openai/deployments/{model}/chat/completions
        #   - Sends header: "api-key: your-key"
        #   - Requires: azure_endpoint, api_version, api_key
        #
        # OpenAI client:
        #   - Builds URL: https://api.openai.com/v1/chat/completions
        #   - Sends header: "Authorization: Bearer your-key"
        #   - Requires: api_key (endpoint defaults to api.openai.com)
        #
        try:
            if self.is_azure:
                # -- AZURE CLIENT --
                # azure_endpoint must be the base URL only (no /openai/... path).
                # _extract_azure_base() strips any extra path the user stored.
                clean_endpoint = self._extract_azure_base(self.base_endpoint)

                self.client = AzureOpenAI(
                    azure_endpoint=clean_endpoint,
                    api_key=self.api_key,
                    api_version=self.api_version,
                    http_client=_build_httpx_client(
                        timeout=getattr(self.config.api, "timeout_seconds", 60),
                    ),
                )

                self.logger.info(
                    "api_router_init",
                    provider="azure_openai",
                    endpoint=clean_endpoint,
                    deployment=self.deployment,
                    api_version=self.api_version,
                    sdk="openai_official",
                )

            else:
                # -- STANDARD OPENAI CLIENT --
                # For home development with a personal OpenAI API key,
                # or for any OpenAI-compatible service (OpenRouter, etc).
                #
                # If endpoint is provided and it's not Azure, use it as
                # the base_url (for OpenRouter, local proxies, etc).
                # Otherwise, the SDK defaults to https://api.openai.com/v1
                client_kwargs = {"api_key": self.api_key}

                if self.base_endpoint and "openai.com" not in self.base_endpoint:
                    # Custom endpoint (OpenRouter, Together AI, etc.)
                    client_kwargs["base_url"] = self.base_endpoint

                self.client = OpenAI(**client_kwargs)

                self.logger.info(
                    "api_router_init",
                    provider="openai",
                    sdk="openai_official",
                )

        except Exception as e:
            self.client = None
            self._init_error = str(e)
            self.logger.error("api_router_init_failed", error=str(e))
            self._init_http_fallback_client()

        # If SDK import/init failed, try the internal HTTP client as fallback.
        if self.client is None and self.http_api_client is None:
            self._init_http_fallback_client()

    def _init_http_fallback_client(self):
        """Plain-English: Initializes a basic HTTP fallback client when the main SDK client is unavailable."""
        _api_init_http_fallback_client(self)

    def _reinit_sdk_client(self):
        """Plain-English: Rebuilds the SDK client after endpoint, credential, or mode changes."""
        _api_reinit_sdk_client(self)

    def _attempt_late_init(self):
        """Plain-English: Attempts lazy client initialization at first use if startup initialization was deferred."""
        _api_attempt_late_init(self)

    def _extract_azure_base(self, url: str) -> str:
        """Plain-English: Derives the Azure base URL from a deployment-style endpoint string."""
        return _api_extract_azure_base(url)

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to the API and get the AI-generated answer back.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed

        How it works:
            1. We call client.chat.completions.create() -- this is the
               standard OpenAI SDK method for chat-based completions.
            2. The SDK handles URL construction, headers, retries.
            3. We parse the response into our standard LLMResponse format.

        The call is IDENTICAL for both Azure and standard OpenAI.
        The only difference is which client we created in __init__.
        """
        self.last_error = ""
        if self.client is None and self.http_api_client is None:
            self._attempt_late_init()
        if self.client is None and self.http_api_client is None:
            detail = self._init_error.strip() if isinstance(self._init_error, str) else ""
            self.last_error = (
                f"API client not ready (SDK missing or init failed): {detail}"
                if detail else "API client not ready (SDK missing or init failed)"
            )
            self.logger.error(
                "api_client_not_ready",
                hint="openai SDK not installed and HTTP fallback unavailable",
            )
            return None

        # -- Network gate check (per-query) --
        # Even though we checked in __init__, the mode could have changed
        # (e.g., user ran rag-mode-offline mid-session). Check again.
        try:
            get_gate().check_allowed(
                self.base_endpoint, "api_query", "api_router",
            )
        except NetworkBlockedError as e:
            # User-facing guidance should reference GUI actions, not YAML edits.
            gate_mode = getattr(get_gate(), "mode_name", "offline")
            if gate_mode == "offline":
                self.last_error = (
                    "Network access is blocked because the app is in Offline Mode. "
                    "Switch to Online Mode, then verify Admin > API Credentials."
                )
            else:
                self.last_error = (
                    "Network access blocked by endpoint allowlist. "
                    "Verify Admin > API Credentials and approved endpoint settings."
                )
            self.logger.error("api_query_blocked_by_gate", error=str(e))
            return None

        # -- PII scrub (only when enabled in config) --
        if getattr(self.config, "security", None) and self.config.security.pii_sanitization:
            from src.security.pii_scrubber import scrub_pii
            prompt, pii_count = scrub_pii(prompt)
            if pii_count > 0:
                self.logger.info("pii_scrubbed", count=pii_count)

        start_time = time.time()

        # -- Pick the model name --
        # Azure uses deployment names in the URL. OpenAI-compatible providers
        # expect a model ID in the request body. The GUI historically wrote the
        # online selection to api.deployment, so we fall back to that when
        # api.model is blank to keep OpenRouter/OpenAI routing aligned.
        if self.is_azure:
            model_name = (self.deployment or "").strip()
        else:
            configured_model = (
                getattr(getattr(self.config, "api", None), "model", "") or ""
            ).strip()
            selected_model = (self.deployment or "").strip()
            model_name = configured_model or selected_model
            # Keep deployment fallback local to this request path.
            # Mutating shared config here can leak transient online state
            # back into GUI/YAML flows and cause mode snapback confusion.

        if not model_name:
            self.last_error = (
                "No online model selected. Verify Admin > Online Model Selection "
                "or configure api.model/api.deployment."
            )
            self.logger.error("api_model_not_configured", is_azure=self.is_azure)
            return None

        try:
            # -- THE API CALL --
            # This single line replaces all the old httpx URL-building,
            # header-building, and HTTP-sending code. The SDK does it all.
            #
            # For Azure, the SDK sends:
            #   POST https://company.openai.azure.com/openai/deployments/
            #        gpt-35-turbo/chat/completions?api-version=2024-02-02
            #   Header: api-key: your-key
            #
            # For standard OpenAI, the SDK sends:
            #   POST https://api.openai.com/v1/chat/completions
            #   Header: Authorization: Bearer your-key
            #
            # We don't build any of that -- the SDK handles it.

            self.logger.info(
                "api_query_sending",
                provider="azure" if self.is_azure else "openai",
                model=model_name,
            )

            # Split the combined prompt into system + user messages.
            # Chat models (GPT-4o etc.) follow system-role instructions
            # with much higher fidelity than user-role text. Without
            # this split, the 9-rule grounding prompt is treated as a
            # suggestion rather than a directive.
            messages = _split_prompt_to_messages(prompt)

            if self.client is not None:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=self.config.api.max_tokens,
                    temperature=self.config.api.temperature,
                )
                answer_text = response.choices[0].message.content
                tokens_in = response.usage.prompt_tokens if response.usage else 0
                tokens_out = response.usage.completion_tokens if response.usage else 0
                actual_model = response.model or model_name
            else:
                sys_msg, usr_msg = _extract_system_user(prompt)
                fallback = self.http_api_client.chat(
                    user_message=usr_msg,
                    system_prompt=sys_msg or None,
                    max_tokens=self.config.api.max_tokens,
                    temperature=self.config.api.temperature,
                )
                answer_text = fallback.get("answer", "")
                usage = fallback.get("usage", {}) or {}
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
                actual_model = fallback.get("model", model_name) or model_name
            latency_ms = (time.time() - start_time) * 1000

            self.logger.info(
                "api_query_success",
                model=actual_model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                is_azure=self.is_azure,
            )

            return LLMResponse(
                text=answer_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=actual_model,
                latency_ms=latency_ms,
            )

        # -- ERROR HANDLING --
        # The openai SDK raises specific exception types for different
        # failures. We catch each one and log a helpful message.

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_name = type(e).__name__
            error_msg = str(e)
            self.last_error = f"{error_name}: {error_msg}"

            # Classify the error for better troubleshooting
            if "401" in error_msg or "Unauthorized" in error_msg:
                self.logger.error(
                    "api_auth_error",
                    error=error_msg[:500],
                    hint=(
                        "TROUBLESHOOTING 401: "
                        "(1) Is the API key correct and not expired? "
                        "(2) Run rag-store-key to re-enter it. "
                        "(3) Check Azure portal for Cognitive Services User role."
                    ),
                )
            elif "404" in error_msg or "NotFound" in error_msg:
                self.logger.error(
                    "api_not_found",
                    error=error_msg[:500],
                    hint=(
                        "TROUBLESHOOTING 404: "
                        "(1) Is the deployment name correct? Expected: "
                        + self.deployment + ". "
                        "(2) Is the endpoint URL correct? "
                        "(3) Check Azure portal for the exact deployment name."
                    ),
                )
            elif "429" in error_msg or "RateLimit" in error_msg:
                self.logger.error(
                    "api_rate_limited",
                    error=error_msg[:200],
                    hint="Wait 30-60 seconds and retry.",
                )
            elif "SSL" in error_msg or "certificate" in error_msg.lower():
                self.logger.error(
                    "api_ssl_error",
                    error=error_msg[:500],
                    hint=(
                        "TROUBLESHOOTING SSL: "
                        "(1) Is pip-system-certs installed? "
                        "(2) Are you on enterprise LAN (not VPN)? "
                        "(3) Run: pip install pip-system-certs"
                    ),
                )
            elif "Connection" in error_name or "connect" in error_msg.lower():
                self.logger.error(
                    "api_connection_error",
                    error=error_msg[:500],
                    hint="Check VPN/network connection and firewall rules.",
                )
            elif "Timeout" in error_name or "timed out" in error_msg.lower():
                self.logger.error(
                    "api_timeout",
                    error=error_msg[:200],
                    timeout_seconds=self.config.api.timeout_seconds,
                )
            else:
                self.logger.error(
                    "api_error",
                    error_type=error_name,
                    error=error_msg[:500],
                )

            return None

    def get_status(self) -> Dict[str, Any]:
        """Plain-English: Returns a concise status snapshot for display and diagnostics."""
        return _api_get_status(self)


def _api_init_http_fallback_client(router: "APIRouter") -> None:
    """Initialize internal HTTP client fallback when SDK path is unavailable."""
    try:
        from src.core.api_client_factory import ApiClientFactory
        from src.security.credentials import ApiCredentials

        config_dict = (
            router.config.to_dict()
            if hasattr(router.config, "to_dict")
            else {
                "api": {
                    "provider": "azure" if router.is_azure else "openai",
                    "endpoint": router.base_endpoint,
                    "deployment": router.deployment,
                    "api_version": router.api_version,
                    "model": (
                        getattr(router.config.api, "model", "")
                        or (router.deployment if not router.is_azure else "")
                    ),
                }
            }
        )
        factory = ApiClientFactory(config_dict)
        creds = ApiCredentials(
            api_key=router.api_key,
            endpoint=router.base_endpoint,
            deployment=router.deployment,
            api_version=router.api_version,
            provider=("azure" if router.is_azure else "openai"),
        )
        router.http_api_client = factory.build(creds)
        router.logger.info(
            "api_router_http_fallback_ready",
            provider=("azure" if router.is_azure else "openai"),
        )
    except Exception as e:
        router.http_api_client = None
        router._init_error = str(e)
        router.logger.error("api_router_http_fallback_init_failed", error=str(e))


def _api_reinit_sdk_client(router: "APIRouter") -> None:
    """Best-effort SDK client re-init using current resolved fields."""
    try:
        from openai import AzureOpenAI, OpenAI
        if router.is_azure:
            clean_endpoint = _api_extract_azure_base(router.base_endpoint)
            router.client = AzureOpenAI(
                azure_endpoint=clean_endpoint,
                api_key=router.api_key,
                api_version=router.api_version,
                http_client=_build_httpx_client(
                    timeout=getattr(router.config.api, "timeout_seconds", 60),
                ),
            )
        else:
            client_kwargs = {"api_key": router.api_key}
            if router.base_endpoint and "openai.com" not in router.base_endpoint:
                client_kwargs["base_url"] = router.base_endpoint
            router.client = OpenAI(**client_kwargs)
        router._init_error = ""
    except Exception as e:
        router.client = None
        router._init_error = str(e)
        router.logger.warning("api_router_sdk_reinit_failed", error=str(e))


def _api_attempt_late_init(router: "APIRouter") -> None:
    """Last-chance API client initialization at query time."""
    if router.client is not None or router.http_api_client is not None:
        return
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(use_cache=False)
        if getattr(creds, "api_key", ""):
            router.api_key = creds.api_key
        if getattr(creds, "endpoint", ""):
            router.base_endpoint = creds.endpoint.rstrip("/")
        if getattr(creds, "deployment", ""):
            router.deployment = creds.deployment
        if getattr(creds, "api_version", ""):
            router.api_version = creds.api_version

        provider = (getattr(creds, "provider", "") or router.provider or "").lower()
        if provider in ("azure", "azure_gov"):
            router.is_azure = True
            router.provider = provider
        elif provider == "openai":
            router.is_azure = False
            router.provider = provider
        else:
            low = (router.base_endpoint or "").lower()
            router.is_azure = ("azure" in low or "aoai" in low)

        _api_reinit_sdk_client(router)
        _api_init_http_fallback_client(router)
    except Exception as e:
        router.logger.warning("api_router_late_init_failed", error=str(e))


def _api_extract_azure_base(url: str) -> str:
    """Extract just the base domain from an Azure endpoint URL."""
    idx = url.lower().find("/openai/")
    if idx > 0:
        return url[:idx]
    idx = url.lower().find("/chat/")
    if idx > 0:
        return url[:idx]
    idx = url.find("?")
    if idx > 0:
        return url[:idx]
    return url


def _api_get_status(router: "APIRouter") -> Dict[str, Any]:
    """Return current API router status for diagnostics."""
    detected_provider = router.provider if router.provider else (
        "azure_openai" if router.is_azure else "openai"
    )
    status = {
        "provider": detected_provider,
        "endpoint": router.base_endpoint,
        "api_configured": (
            router.client is not None or router.http_api_client is not None
        ),
        "sdk_available": _openai_sdk_available(),
        "sdk": "openai_official" if router.client is not None else "http_fallback",
    }
    if router.is_azure:
        status["deployment"] = router.deployment
        status["api_version"] = router.api_version
        status["clean_endpoint"] = _api_extract_azure_base(router.base_endpoint)
    return status


# --- SECTION 5: DEPLOYMENT DISCOVERY (MODEL LISTING) ----------------------

# ============================================================================
# DEPLOYMENT DISCOVERY -- Detects available models on Azure or OpenAI
# ============================================================================
#
# WHY THIS EXISTS:
#   Azure uses a different API endpoint for listing deployments than
#   OpenAI/OpenRouter. Without this, _list_models.py silently returns
#   nothing for Azure endpoints. This module detects the provider type
#   from the stored endpoint and uses the correct discovery path.
#
# AZURE PATH:
#   GET {base}/openai/deployments?api-version={version}
#   Header: api-key: {key}
#   Response: {"value": [{"id": "gpt-4o", "model": "gpt-4o", ...}, ...]}
#
# OPENAI/OPENROUTER PATH:
#   GET {endpoint}/models
#   Header: Authorization: Bearer {key}
#   Response: {"data": [{"id": "gpt-4o", ...}, ...]}
#
# COMPATIBILITY NOTE (openai 1.51.2):
#   We use httpx directly for discovery instead of the openai SDK because:
#   1. The openai 1.51.2 SDK does not have a deployments.list() method
#   2. httpx is already a dependency (used by Ollama path)
#   3. Direct HTTP gives us full control over the request format
#
# INTERNET ACCESS: YES (one GET request per call)
# ============================================================================

# Module-level cache for deployment discovery results.
# WHY CACHE: Deployment discovery makes an HTTP request to the API endpoint,
# which takes ~200ms. We cache the result so subsequent calls (e.g., refreshing
# the Admin GUI model dropdown) return instantly.
_deployment_cache = None
_deployment_lock = __import__("threading").Lock()


def _is_azure_endpoint(endpoint):
    """
    Check if an endpoint URL is Azure-style (commercial or government).
    Uses the same detection logic as APIRouter.is_azure.
    Covers:
      - *.openai.azure.com (commercial)
      - *.openai.azure.us  (government)
      - URLs containing "aoai" (enterprise abbreviation)
    """
    if not endpoint:
        return False
    lower = endpoint.lower()
    return "azure" in lower or "aoai" in lower


# Banned model families (NDAA / ITAR policy).
# These model families are disqualified for use in this environment.
# See docs/05_security/ for the full audit and reasoning.
_BANNED_PREFIXES = ["qwen", "deepseek", "llama", "baidu", "bge"]


def _filter_banned_deployments(models):
    """Remove banned model families from a deployment list."""
    filtered = []
    for m in models:
        lower = m.lower()
        if any(b in lower for b in _BANNED_PREFIXES):
            continue
        filtered.append(m)
    return filtered


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
            # (endpoint might contain /openai/deployments/... already)
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
                # Each deployment has an "id" (deployment name) and "model" field
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

            # Standard OpenAI format: {"data": [{...}, ...]}
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


# --- SECTION 6: LLM ROUTER (MAIN ORCHESTRATOR) ----------------------------

# ============================================================================
# LLMRouter -- The main switchboard
# ============================================================================
#
# This is the class that the rest of HybridRAG talks to.
# It decides whether to use Ollama (offline) or the API (online)
# based on the mode setting in your config.
#
# Usage:
#   router = LLMRouter(config)
#   answer = router.query("What is the operating frequency?")
#
# The caller never needs to know which backend answered.
# ============================================================================
class LLMRouter:
    """
    Route queries to the appropriate LLM backend.

    Mode selection:
        "offline" --> Ollama (local, free, no internet)
        "online"  --> Azure OpenAI API (company cloud, costs money)
    """

    def __init__(self, config: Config, api_key: Optional[str] = None,
                 credentials=None):
        """
        Initialize the router and set up both backends.

        Args:
            config:  The HybridRAG configuration object
            api_key: Optional explicit API key (overrides all other sources)
            credentials: Pre-resolved credentials from boot (skips keyring lookup)

        Credential resolution order (tries each in sequence):
            1. Explicit api_key parameter (for testing)
            2. Windows Credential Manager via keyring
            3. AZURE_OPENAI_API_KEY environment variable
            4. AZURE_OPEN_AI_KEY environment variable (company variant)
            5. OPENAI_API_KEY environment variable (home/standard)
        """
        self.config = config
        self.logger = get_app_logger("llm_router")
        self.last_error = ""

        # -- Always create the Ollama router (offline mode) --
        # This is lightweight (no network call) and doesn't need any
        # credentials, so we always create it even in online mode.
        # It serves as the fallback if the API is unreachable.
        self.ollama = OllamaRouter(config)

        # -- Create vLLM router if enabled (workstation offline mode) --
        # vLLM is 2-3x faster than Ollama for the same model because it
        # uses continuous batching and prefix caching. When enabled,
        # offline queries prefer vLLM over Ollama.
        # If vLLM is unreachable, queries fall back to Ollama silently.
        if config.vllm.enabled:
            self.vllm = VLLMRouter(config)
            self.logger.info("llm_router_vllm_enabled", model=config.vllm.model)
        else:
            self.vllm = None

        # Offline mode does not need API credentials or APIRouter bootstrap.
        # Skipping this avoids expensive keyring lookups that can block first query.
        mode = str(getattr(config, "mode", "offline")).lower()
        if mode != "online" and api_key is None and credentials is None:
            self.api = None
            self.logger.info("llm_router_init", api_mode="skipped_offline")
            return

        # -- Resolve credentials -------------------------------------------
        # Use pre-resolved credentials from boot if available (saves the
        # 10-50ms keyring lookup). Otherwise resolve from scratch.
        resolved_key = api_key
        resolved_endpoint = ""
        resolved_deployment = ""
        resolved_api_version = ""

        creds = credentials
        if creds is None:
            try:
                from ..security.credentials import resolve_credentials
                config_dict = None
                if hasattr(config, "to_dict"):
                    config_dict = config.to_dict()
                elif hasattr(config, "api"):
                    config_dict = {
                        "api": {
                            "endpoint": config.api.endpoint or "",
                            "deployment": config.api.deployment or "",
                            "api_version": config.api.api_version or "",
                        }
                    }
                creds = resolve_credentials(config_dict)
            except ImportError:
                self.logger.warning("llm_router_credentials_import_failed")

        resolved_provider = ""

        if creds is not None:
            if not resolved_key and creds.api_key:
                resolved_key = creds.api_key
            if creds.endpoint:
                resolved_endpoint = creds.endpoint
            if creds.deployment:
                resolved_deployment = creds.deployment
            if creds.api_version:
                resolved_api_version = creds.api_version
            if getattr(creds, "provider", None):
                resolved_provider = creds.provider

            self.logger.info(
                "llm_router_creds_resolved",
                key_source=getattr(creds, "source_key", "") or "caller",
                endpoint_source=getattr(creds, "source_endpoint", "") or "config",
                provider=resolved_provider or "auto",
            )

        # Fall back to config.api.provider if credentials didn't supply one
        if not resolved_provider:
            resolved_provider = getattr(config.api, "provider", "") or ""

        # NOTE: We do NOT mutate config.api.endpoint here.
        # The gate was already configured with the correct endpoint by
        # boot_hybridrag() or configure_gate(). Mutating config after
        # gate configuration creates invisible failures where the gate
        # blocks requests to the new endpoint.

        # -- Create the API router only when credentials are complete --
        if resolved_key and resolved_endpoint:
            self.api = APIRouter(
                config, resolved_key, resolved_endpoint,
                deployment_override=resolved_deployment,
                api_version_override=resolved_api_version,
                provider_override=resolved_provider,
            )
            self.logger.info("llm_router_init", api_mode="enabled")
        elif resolved_key:
            self.api = None
            self.logger.info("llm_router_init", api_mode="disabled_no_endpoint")
        else:
            self.api = None
            self.logger.info("llm_router_init", api_mode="disabled_no_key")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Route a query to the appropriate backend based on config.mode.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        mode = self.config.mode
        self.last_error = ""

        self.logger.info("query_mode", mode=mode)

        if mode == "online":
            if self.api is None:
                # Credentials may have been saved after router creation.
                # Re-resolve once and attach APIRouter dynamically.
                try:
                    from ..security.credentials import resolve_credentials
                    creds = resolve_credentials(use_cache=False)
                    if (
                        getattr(creds, "api_key", "")
                        and getattr(creds, "endpoint", "")
                    ):
                        self.api = APIRouter(
                            self.config,
                            creds.api_key,
                            getattr(creds, "endpoint", "") or "",
                            deployment_override=getattr(creds, "deployment", "") or "",
                            api_version_override=getattr(creds, "api_version", "") or "",
                            provider_override=getattr(creds, "provider", "") or "",
                        )
                    elif getattr(creds, "api_key", ""):
                        self.logger.warning(
                            "online_late_router_attach_skipped",
                            reason="missing_endpoint",
                        )
                except Exception as e:
                    self.logger.warning("online_late_router_attach_failed", error=str(e))
            if self.api is None:
                self.last_error = "API is not configured (missing key/endpoint)"
                self.logger.error(
                    "api_not_configured",
                    hint="Run rag-store-key and rag-store-endpoint first",
                )
                return None

            # Self-heal gate state for GUI mode/race inconsistencies:
            # if mode is online but gate still carries offline policy,
            # re-apply online config using the active API endpoint.
            try:
                from .network_gate import configure_gate
                endpoint = (
                    getattr(self.api, "base_endpoint", "")
                    or getattr(getattr(self.config, "api", None), "endpoint", "")
                    or ""
                )
                configure_gate(
                    mode="online",
                    api_endpoint=endpoint,
                    allowed_prefixes=getattr(
                        getattr(self.config, "api", None),
                        "allowed_endpoint_prefixes", [],
                    ) if self.config else [],
                )
            except Exception as e:
                self.logger.warning("online_gate_self_heal_failed", error=str(e))

            result = self.api.query(prompt)
            if result is None:
                self.last_error = (
                    getattr(self.api, "last_error", "")
                    or "Online API query failed"
                )
            return result

        else:
            # Offline mode priority: vLLM > Ollama
            if self.vllm and self.vllm.is_available():
                result = self.vllm.query(prompt)
                if result is not None:
                    return result
                self.last_error = (
                    getattr(self.vllm, "last_error", "")
                    or "vLLM query failed"
                )
                self.logger.warning("vllm_query_failed_falling_back_to_ollama")
            result = self.ollama.query(prompt)
            if result is None:
                self.last_error = (
                    getattr(self.ollama, "last_error", "")
                    or "Ollama query failed"
                )
            return result

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream tokens from the appropriate backend.

        Only supported in offline (Ollama) mode. Online mode falls back
        to non-streaming query() wrapped as a single-chunk yield.

        Yields dicts -- see OllamaRouter.query_stream() for format.
        """
        mode = self.config.mode
        self.last_error = ""

        if mode == "offline":
            # Priority: vLLM > Ollama
            if self.vllm and self.vllm.is_available():
                for chunk in self.vllm.query_stream(prompt):
                    if "error" in chunk:
                        self.last_error = str(chunk.get("error", ""))
                    yield chunk
            else:
                for chunk in self.ollama.query_stream(prompt):
                    if "error" in chunk:
                        self.last_error = str(chunk.get("error", ""))
                    yield chunk
        else:
            # Online mode: no streaming support, yield full response as one chunk
            result = self.query(prompt)
            if result:
                yield {"token": result.text}
                yield {
                    "done": True,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "model": result.model,
                    "latency_ms": result.latency_ms,
                }
            else:
                # Query failed -- must still yield "done" or UI hangs
                err = self.last_error or "Online API query failed"
                yield {"error": err, "backend": "api"}
                yield {
                    "done": True,
                    "tokens_in": 0, "tokens_out": 0,
                    "model": "unknown", "latency_ms": 0.0,
                }

    def close(self):
        """Release HTTP clients held by backend routers.

        Call before replacing an LLMRouter instance (e.g. on mode switch)
        to avoid leaking sockets and file descriptors.
        """
        if hasattr(self, "ollama") and hasattr(self.ollama, "_client"):
            try:
                self.ollama._client.close()
            except Exception:
                pass
        if hasattr(self, "vllm") and self.vllm and hasattr(self.vllm, "_client"):
            try:
                self.vllm._client.close()
            except Exception:
                pass
        if hasattr(self, "api") and self.api and hasattr(self.api, "client"):
            try:
                if self.api.client:
                    self.api.client.close()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of all LLM backends.
        Used by rag-cred-status, rag-test-api, and diagnostics.
        """
        api_present = (
            self.api is not None
            and (
                getattr(self.api, "client", None) is not None
                or getattr(self.api, "http_api_client", None) is not None
            )
        )
        status = {
            "mode": self.config.mode,
            "ollama_model": self.config.ollama.model,
            "ollama_available": self.ollama.is_available(),
            "vllm_enabled": self.vllm is not None,
            "vllm_available": self.vllm.is_available() if self.vllm else False,
            # Mode-aware: in offline mode API is not considered "configured"
            # for active routing, even if credentials are present.
            "api_configured": (self.config.mode == "online" and api_present),
            "api_present": api_present,
            "sdk_available": _openai_sdk_available(),
        }

        if self.api:
            api_status = self.api.get_status()
            status.update({
                "api_provider": api_status["provider"],
                "api_endpoint": api_status["endpoint"],
                "api_sdk": api_status.get("sdk", "unknown"),
            })
            if api_status.get("deployment"):
                status["api_deployment"] = api_status["deployment"]
                status["api_version"] = api_status["api_version"]
                status["api_clean_endpoint"] = api_status.get("clean_endpoint", "")

        return status
