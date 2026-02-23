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

import httpx

# -- OpenAI SDK is imported lazily inside APIRouter.__init__() ----------------
# This avoids loading the SDK (~50ms) at module import time, which matters
# in offline mode where the SDK is never used.
# ---------------------------------------------------------------------------

def _openai_sdk_available():
    """Check if the openai SDK is installed (lazy, no import at module load)."""
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False

# -- Import HybridRAG internals ---------------------------------------------
from .config import Config
from .network_gate import get_gate, NetworkBlockedError
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

        # Base URL for the local Ollama server
        self.base_url = config.ollama.base_url.rstrip("/")

        # Persistent HTTP client -- reuses TCP connections across calls
        self._client = httpx.Client()

        # Health check cache: (available: bool, timestamp: float) with TTL
        self._health_cache = None
        self._health_ttl = 30  # seconds between live checks

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
        start_time = time.time()

        # -- Network gate check --
        try:
            get_gate().check_allowed(
                f"{self.base_url}/api/generate",
                "ollama_query", "ollama_router",
            )
        except NetworkBlockedError as e:
            self.logger.error("ollama_blocked_by_gate", error=str(e))
            return None

        # Build the request body for Ollama's /api/generate endpoint
        payload = {
            "model": self.config.ollama.model,
            "prompt": prompt,
            "stream": False,    # Get the full response at once, not word-by-word
            
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
                model=self.config.ollama.model,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                latency_ms=latency_ms,
            )

            return LLMResponse(
                text=response_text,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                model=self.config.ollama.model,
                latency_ms=latency_ms,
            )

        except httpx.HTTPError as e:
            self.logger.error("ollama_http_error", error=str(e))
            return None
        except Exception as e:
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
        start_time = time.time()

        try:
            get_gate().check_allowed(
                f"{self.base_url}/api/generate",
                "ollama_query_stream", "ollama_router",
            )
        except NetworkBlockedError as e:
            self.logger.error("ollama_stream_blocked_by_gate", error=str(e))
            return

        payload = {
            "model": self.config.ollama.model,
            "prompt": prompt,
            "stream": True,
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
                model=self.config.ollama.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
            yield {
                "done": True,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "model": self.config.ollama.model,
                "latency_ms": latency_ms,
            }

        except httpx.HTTPError as e:
            self.logger.error("ollama_stream_http_error", error=str(e))
        except Exception as e:
            self.logger.error("ollama_stream_error", error=str(e))

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

        self.base_url = config.vllm.base_url.rstrip("/")
        self.model = config.vllm.model
        self.timeout = config.vllm.timeout_seconds

        # Persistent HTTP client -- reuses TCP connections across calls
        self._client = httpx.Client()

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
        start_time = time.time()

        try:
            get_gate().check_allowed(
                f"{self.base_url}/v1/chat/completions",
                "vllm_query", "vllm_router",
            )
        except NetworkBlockedError as e:
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
            self.logger.error("vllm_http_error", error=str(e))
            return None
        except Exception as e:
            self.logger.error("vllm_error", error=str(e))
            return None

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream tokens from the local vLLM server via SSE.

        Yields dicts with either:
          {"token": str}        -- a partial text token
          {"done": True, ...}   -- final metadata
        """
        start_time = time.time()

        try:
            get_gate().check_allowed(
                f"{self.base_url}/v1/chat/completions",
                "vllm_query_stream", "vllm_router",
            )
        except NetworkBlockedError as e:
            self.logger.error("vllm_stream_blocked_by_gate", error=str(e))
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
            self.logger.error("vllm_stream_http_error", error=str(e))
        except Exception as e:
            self.logger.error("vllm_stream_error", error=str(e))

    def close(self):
        """Release the persistent HTTP client."""
        if hasattr(self, "_client") and self._client:
            self._client.close()


# --- SECTION 3B: TRANSFORMERS ROUTER (DIRECT GPU, NO SERVER) ---------------

# ============================================================================
# TransformersRouter -- Loads model directly via HuggingFace transformers
# ============================================================================
#
# No Ollama, no vLLM, no server. The model loads once into GPU memory
# at startup and stays there. Queries go straight to the GPU via Python.
#
# Uses 4-bit quantization (bitsandbytes) to fit 14B parameter models
# into 12GB VRAM. Requires: transformers, torch, accelerate, bitsandbytes.
#
# INTERNET ACCESS: NONE after initial model download
# ============================================================================
class TransformersRouter:
    """Route queries to a locally loaded HuggingFace transformers model."""

    def __init__(self, config: Config):
        """
        Load the model into GPU memory.

        Args:
            config: HybridRAG config. Reads config.transformers_llm.*
        """
        self.config = config
        self.logger = get_app_logger("transformers_router")
        self._model = None
        self._tokenizer = None
        self._pipe = None
        self._available = False

        tc = config.transformers_llm
        self.model_name = tc.model
        self.max_new_tokens = tc.max_new_tokens
        self.temperature = tc.temperature

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

            load_kwargs = {
                "device_map": tc.device_map,
                "torch_dtype": "auto",
                "trust_remote_code": tc.trust_remote_code,
            }

            if tc.load_in_4bit:
                try:
                    from transformers import BitsAndBytesConfig
                    load_kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.float16,
                    )
                    self.logger.info("transformers_4bit_enabled", model=self.model_name)
                except ImportError:
                    self.logger.warning(
                        "transformers_no_bitsandbytes",
                        hint="pip install bitsandbytes for 4-bit quantization",
                    )

            self.logger.info("transformers_loading_model", model=self.model_name)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name, **load_kwargs
            )
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=tc.trust_remote_code
            )
            self._pipe = pipeline(
                "text-generation",
                model=self._model,
                tokenizer=self._tokenizer,
            )
            self._available = True
            self.logger.info("transformers_model_loaded", model=self.model_name)

        except ImportError as e:
            self.logger.warning("transformers_import_error", error=str(e))
        except Exception as e:
            self.logger.error("transformers_load_error", error=str(e))

    def is_available(self) -> bool:
        """Check if the model is loaded and ready."""
        return self._available

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt directly to the loaded model.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        if not self._available:
            return None

        start_time = time.time()

        try:
            messages = [{"role": "user", "content": prompt}]

            output = self._pipe(
                messages,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature if self.temperature > 0 else None,
                do_sample=self.temperature > 0,
                return_full_text=False,
            )

            response_text = output[0]["generated_text"]
            if isinstance(response_text, list):
                response_text = response_text[0].get("content", "") if response_text else ""
            elif isinstance(response_text, dict):
                response_text = response_text.get("content", str(response_text))

            latency_ms = (time.time() - start_time) * 1000

            # Estimate token counts (transformers doesn't always report exact)
            tokens_in = len(self._tokenizer.encode(prompt))
            tokens_out = len(self._tokenizer.encode(str(response_text)))

            self.logger.info(
                "transformers_query_success",
                model=self.model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )

            return LLMResponse(
                text=str(response_text),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=self.model_name,
                latency_ms=latency_ms,
            )

        except Exception as e:
            self.logger.error("transformers_query_error", error=str(e))
            return None

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream is not natively supported by pipeline.
        Falls back to non-streaming query wrapped as a single chunk.
        """
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

    def close(self):
        """Release model from GPU memory."""
        self._model = None
        self._tokenizer = None
        self._pipe = None
        self._available = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


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
class APIRouter:
    """Route queries to Azure OpenAI or standard OpenAI API (online mode)."""

    # -- Fallback defaults (used only if YAML, env vars, and credentials
    #    all fail to provide a value) --
    _DEFAULT_API_VERSION = "2024-02-02"
    _DEFAULT_DEPLOYMENT = "gpt-35-turbo"

    def __init__(self, config: Config, api_key: str, endpoint: str = "",
                 deployment_override: str = "", api_version_override: str = ""):
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

        What happens here:
            1. We figure out if this is Azure or standard OpenAI
            2. We resolve deployment name and API version from config/env
            3. We create the appropriate SDK client
            4. The client handles all URL/header construction from here on

        RESOLUTION ORDER for deployment and api_version:
            0. Override from resolve_credentials() (if provided by LLMRouter)
            1. config/default_config.yaml (api.deployment, api.api_version)
            2. Environment variables (AZURE_OPENAI_DEPLOYMENT, etc.)
            3. Extracted from endpoint URL (if it contains /deployments/xxx)
            4. Hardcoded fallback defaults (last resort)
        """
        self.config = config
        self.api_key = api_key
        self.logger = get_app_logger("api_router")

        # Store the raw endpoint for diagnostics/status reporting
        self.base_endpoint = endpoint.rstrip("/") if endpoint else config.api.endpoint.rstrip("/")

        # -- Auto-detect Azure vs standard OpenAI --
        # Azure and standard OpenAI use different URL formats and auth headers.
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
            self.deployment = self._resolve_deployment(config, self.base_endpoint)

        # -- Resolve API version --
        if api_version_override:
            self.api_version = api_version_override
        else:
            self.api_version = self._resolve_api_version(config, self.base_endpoint)

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
                # This is what your company's example code uses.
                # The SDK extracts the base domain from azure_endpoint and
                # builds the full URL with deployment name and api-version.
                #
                # IMPORTANT: azure_endpoint should be JUST the base URL:
                #   https://your-company.openai.azure.com
                # The SDK appends /openai/deployments/... automatically.
                #
                # If the stored endpoint contains the full path (like
                # .../chat/completions?api-version=...), we strip it down
                # to just the base domain so the SDK doesn't double it.
                clean_endpoint = self._extract_azure_base(self.base_endpoint)

                self.client = AzureOpenAI(
                    azure_endpoint=clean_endpoint,
                    api_key=self.api_key,
                    api_version=self.api_version,
                    # http_client with verify=True ensures SSL works
                    # through enterprise proxy (with pip-system-certs installed)
                    http_client=httpx.Client(verify=True),
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
            self.logger.error("api_router_init_failed", error=str(e))

    @staticmethod
    def _resolve_deployment(config, endpoint_url):
        """
        Resolve Azure deployment name from multiple sources.

        WHY THIS EXISTS:
            Different machines may have different Azure deployment names.
            Instead of hardcoding "gpt-35-turbo", we check multiple sources
            so each machine can configure its own deployment name.

        Resolution order (first non-empty wins):
            1. YAML config: api.deployment in default_config.yaml
            2. Environment variables: AZURE_OPENAI_DEPLOYMENT, etc.
            3. URL extraction: if endpoint contains /deployments/xxx
            4. Fallback: "gpt-35-turbo" (safe default)

        Returns:
            str: The resolved deployment name.
        """
        import re

        # 1. YAML config
        if config.api.deployment:
            return config.api.deployment

        # 2. Environment variables (same aliases as credentials.py)
        for var in [
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_DEPLOYMENT",
            "OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "DEPLOYMENT_NAME",
            "AZURE_CHAT_DEPLOYMENT",
        ]:
            val = os.environ.get(var, "").strip()
            if val:
                return val

        # 3. Extract from URL (e.g., .../deployments/gpt-4o/...)
        if endpoint_url and "/deployments/" in endpoint_url:
            match = re.search(r"/deployments/([^/?]+)", endpoint_url)
            if match:
                return match.group(1)

        # 4. Fallback default
        return APIRouter._DEFAULT_DEPLOYMENT

    @staticmethod
    def _resolve_api_version(config, endpoint_url):
        """
        Resolve Azure API version from multiple sources.

        WHY THIS EXISTS:
            Azure API versions change over time and different tenants
            may require different versions. Instead of hardcoding one
            version, we check multiple sources.

        Resolution order (first non-empty wins):
            1. YAML config: api.api_version in default_config.yaml
            2. Environment variables: AZURE_OPENAI_API_VERSION, etc.
            3. URL extraction: if endpoint contains ?api-version=xxx
            4. Fallback: "2024-02-02" (safe default)

        Returns:
            str: The resolved API version string.
        """
        import re

        # 1. YAML config
        if config.api.api_version:
            return config.api.api_version

        # 2. Environment variables
        for var in [
            "AZURE_OPENAI_API_VERSION",
            "AZURE_API_VERSION",
            "OPENAI_API_VERSION",
            "API_VERSION",
        ]:
            val = os.environ.get(var, "").strip()
            if val:
                return val

        # 3. Extract from URL (e.g., ...?api-version=2024-02-02)
        if endpoint_url and "api-version=" in endpoint_url:
            match = re.search(r"api-version=([^&]+)", endpoint_url)
            if match:
                return match.group(1)

        # 4. Fallback default
        return APIRouter._DEFAULT_API_VERSION

    def _extract_azure_base(self, url: str) -> str:
        """
        Extract just the base domain from an Azure endpoint URL.

        WHY THIS EXISTS:
            Users might store different URL formats:
              - Just the base: https://company.openai.azure.com
              - With deployment path: https://company.openai.azure.com/openai/deployments/...
              - Full URL with query: ...chat/completions?api-version=2024-02-02

            The AzureOpenAI SDK needs ONLY the base domain. If we pass the
            full URL, the SDK will append /openai/deployments/... AGAIN,
            causing the URL doubling that gave us 404 errors before.

            This method strips everything after the domain, no matter what
            format the user stored.

        Examples:
            Input:  https://company.openai.azure.com/openai/deployments/gpt-35-turbo/chat/completions
            Output: https://company.openai.azure.com

            Input:  https://company.openai.azure.com
            Output: https://company.openai.azure.com  (unchanged)
        """
        # Find the position right after the domain
        # Look for /openai/ which is where the Azure path starts
        idx = url.lower().find("/openai/")
        if idx > 0:
            return url[:idx]

        # Look for /chat/ in case the URL starts mid-path
        idx = url.lower().find("/chat/")
        if idx > 0:
            return url[:idx]

        # If there's a query string, strip it
        idx = url.find("?")
        if idx > 0:
            return url[:idx]

        # Already a clean base URL
        return url

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
        if self.client is None:
            self.logger.error(
                "api_client_not_ready",
                hint="openai SDK not installed or client init failed",
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
            self.logger.error("api_query_blocked_by_gate", error=str(e))
            return None

        start_time = time.time()

        # -- Pick the model name --
        # Azure uses "deployment" names (company-chosen); OpenAI uses fixed model names.
        model_name = self.deployment if self.is_azure else self.config.api.model

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

            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.api.max_tokens,
                temperature=self.config.api.temperature,
            )

            # -- Parse the SDK response --
            # The SDK returns a typed object, not raw JSON.
            # response.choices[0].message.content = the AI's answer
            # response.usage.prompt_tokens = tokens in our prompt
            # response.usage.completion_tokens = tokens the AI generated
            # response.model = which model actually answered

            answer_text = response.choices[0].message.content
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            actual_model = response.model or model_name
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
        """
        Return current API router status for diagnostics.

        Used by: rag-cred-status, rag-test-api, rag-status
        """
        status = {
            "provider": "azure_openai" if self.is_azure else "openai",
            "endpoint": self.base_endpoint,
            "api_configured": self.client is not None,
            "sdk_available": _openai_sdk_available(),
            "sdk": "openai_official",
        }
        if self.is_azure:
            status["deployment"] = self.deployment
            status["api_version"] = self.api_version
            status["clean_endpoint"] = self._extract_azure_base(self.base_endpoint)
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
# COMPATIBILITY NOTE (openai 1.45.1):
#   We use httpx directly for discovery instead of the openai SDK because:
#   1. The openai 1.45.1 SDK does not have a deployments.list() method
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
    Check if an endpoint URL is Azure-style.
    Uses the same detection logic as APIRouter.is_azure.
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
            api_version = creds.api_version or "2024-02-02"

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

            with httpx.Client(timeout=3, verify=True) as client:
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

            with httpx.Client(timeout=3, verify=True) as client:
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

        # -- Create Transformers router if enabled (direct GPU mode) --
        # Loads model directly into GPU memory via HuggingFace transformers.
        # No server needed. Preferred over Ollama and vLLM when enabled.
        if config.transformers_llm.enabled:
            self.transformers_rt = TransformersRouter(config)
            self.logger.info(
                "llm_router_transformers_enabled",
                model=config.transformers_llm.model,
            )
        else:
            self.transformers_rt = None

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

        if creds is not None:
            if not resolved_key and creds.api_key:
                resolved_key = creds.api_key
            if creds.endpoint:
                resolved_endpoint = creds.endpoint
            if creds.deployment:
                resolved_deployment = creds.deployment
            if creds.api_version:
                resolved_api_version = creds.api_version

            self.logger.info(
                "llm_router_creds_resolved",
                key_source=getattr(creds, "source_key", "") or "caller",
                endpoint_source=getattr(creds, "source_endpoint", "") or "config",
            )

        # NOTE: We do NOT mutate config.api.endpoint here.
        # The gate was already configured with the correct endpoint by
        # boot_hybridrag() or configure_gate(). Mutating config after
        # gate configuration creates invisible failures where the gate
        # blocks requests to the new endpoint.

        # -- Create the API router (only if we have a key) --
        if resolved_key:
            self.api = APIRouter(
                config, resolved_key, resolved_endpoint,
                deployment_override=resolved_deployment,
                api_version_override=resolved_api_version,
            )
            self.logger.info("llm_router_init", api_mode="enabled")
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

        self.logger.info("query_mode", mode=mode)

        if mode == "online":
            if self.api is None:
                self.logger.error(
                    "api_not_configured",
                    hint="Run rag-store-key and rag-store-endpoint first",
                )
                return None
            return self.api.query(prompt)

        else:
            # Offline mode priority: Transformers > vLLM > Ollama
            if self.transformers_rt and self.transformers_rt.is_available():
                result = self.transformers_rt.query(prompt)
                if result is not None:
                    return result
                self.logger.warning("transformers_query_failed_falling_back")
            if self.vllm and self.vllm.is_available():
                result = self.vllm.query(prompt)
                if result is not None:
                    return result
                self.logger.warning("vllm_query_failed_falling_back_to_ollama")
            return self.ollama.query(prompt)

    def query_stream(self, prompt: str) -> Generator[Dict[str, Any], None, None]:
        """
        Stream tokens from the appropriate backend.

        Only supported in offline (Ollama) mode. Online mode falls back
        to non-streaming query() wrapped as a single-chunk yield.

        Yields dicts -- see OllamaRouter.query_stream() for format.
        """
        mode = self.config.mode

        if mode == "offline":
            # Priority: Transformers > vLLM > Ollama
            if self.transformers_rt and self.transformers_rt.is_available():
                yield from self.transformers_rt.query_stream(prompt)
            elif self.vllm and self.vllm.is_available():
                yield from self.vllm.query_stream(prompt)
            else:
                yield from self.ollama.query_stream(prompt)
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

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of all LLM backends.
        Used by rag-cred-status, rag-test-api, and diagnostics.
        """
        status = {
            "mode": self.config.mode,
            "ollama_available": self.ollama.is_available(),
            "vllm_enabled": self.vllm is not None,
            "vllm_available": self.vllm.is_available() if self.vllm else False,
            "transformers_enabled": self.transformers_rt is not None,
            "transformers_available": (
                self.transformers_rt.is_available() if self.transformers_rt else False
            ),
            "api_configured": self.api is not None,
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






