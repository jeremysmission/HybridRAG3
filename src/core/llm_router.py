# ============================================================================
# HybridRAG v3 — LLM Router (llm_router.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Routes AI queries to the right backend:
#     - OFFLINE mode → Ollama (local AI on your machine, free, no internet)
#     - ONLINE mode  → Azure OpenAI API (company's cloud AI, costs money)
#
#   Think of it like a phone switchboard operator:
#     "You want offline? I'll connect you to Ollama on localhost."
#     "You want online? I'll connect you to the company's Azure GPT API."
#
# HOW IT WORKS:
#   1. You call LLMRouter.query("your question here")
#   2. LLMRouter checks config.mode ("offline" or "online")
#   3. It forwards to the right backend (OllamaRouter or APIRouter)
#   4. The backend sends the prompt, gets an answer, returns it
#   5. LLMRouter wraps the answer in an LLMResponse object and returns it
#
# API KEY RESOLUTION (for online mode):
#   The API key is resolved from these sources, in order of priority:
#     1. Explicit api_key parameter (if the caller passes one)
#     2. Windows Credential Manager via keyring (most secure)
#     3. AZURE_OPENAI_API_KEY or OPENAI_API_KEY environment variable
#     4. None → online mode disabled, offline still works
#
# CUSTOM ENDPOINT RESOLUTION:
#   The API endpoint is resolved from these sources, in order:
#     1. Windows Credential Manager via keyring
#     2. AZURE_OPENAI_ENDPOINT or OPENAI_API_ENDPOINT environment variable
#     3. config.api.endpoint from default_config.yaml (default)
#
# AZURE vs STANDARD OPENAI — AUTO-DETECTED:
#   The router looks at your endpoint URL to decide which format to use:
#     - URL contains "azure" or "aoai" → Azure format (api-key header)
#     - Otherwise → Standard OpenAI format (Bearer token)
#   You do NOT need to configure this manually. Just store your URL.
#
# INTERNET ACCESS:
#   - OllamaRouter: Connects to localhost only (127.0.0.1) — NO internet
#   - APIRouter: Connects to configured API endpoint — REQUIRES internet
#   - The mode setting in config.yaml controls which one is used
#   - HuggingFace is ALWAYS blocked regardless of mode (Layer 1 lockdown)
#
# DEPENDENCIES:
#   - httpx: HTTP client library for making web requests
#   - config.py: Provides all settings (URLs, model names, timeouts)
#   - logger.py: Structured logging for audit trail
#   - credentials.py: Secure API key retrieval from Windows Credential Mgr
# ============================================================================

import os            # For reading environment variables
import httpx         # HTTP client for making web requests to APIs
import json          # For parsing JSON responses from APIs
import time          # For measuring how long each query takes
from typing import Optional, Dict, Any   # Type hints for code clarity
from dataclasses import dataclass        # Simplifies creating data classes

from .config import Config               # Our configuration object
from ..monitoring.logger import get_app_logger  # Our structured logger


# ============================================================================
# LLMResponse — The "answer envelope"
# ============================================================================
# Every time an AI model responds, we wrap the answer in this standard format.
# This way the rest of the code doesn't care whether Ollama or GPT answered —
# it always gets the same type of object back.
# ============================================================================
@dataclass
class LLMResponse:
    """
    Standardized response from any LLM backend.

    Fields:
        text:       The actual AI-generated answer text
        tokens_in:  How many tokens the prompt consumed (input cost)
        tokens_out: How many tokens the answer used (output cost)
        model:      Which model generated the answer (e.g., "llama3", "gpt-35-turbo")
        latency_ms: How long the round-trip took in milliseconds
    """
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: float


# ============================================================================
# OllamaRouter — Talks to the LOCAL AI model
# ============================================================================
# Ollama is a free program that runs AI models on your own computer.
# It exposes a simple HTTP API on localhost (usually port 11434).
# This router sends prompts to Ollama and gets answers back.
#
# IMPORTANT: This NEVER touches the internet. It talks to your own machine.
# ============================================================================
class OllamaRouter:
    """Route queries to a local Ollama instance (offline mode)."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = get_app_logger("ollama_router")
        # Remove trailing slash from URL to prevent double-slash issues
        self.base_url = config.ollama.base_url.rstrip("/")

    def is_available(self) -> bool:
        """
        Check if Ollama is currently running on this machine.

        Returns:
            True if Ollama is running and responding, False otherwise
        """
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception as e:
            self.logger.warn("ollama_unavailable", error=str(e))
            return False

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to Ollama and get the AI-generated answer back.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        start_time = time.time()

        payload = {
            "model": self.config.ollama.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self.config.ollama.timeout_seconds) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
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


# ============================================================================
# APIRouter — Talks to Azure OpenAI (or standard OpenAI) API
# ============================================================================
#
# YOUR COMPANY SETUP (Azure OpenAI):
#   Your company hosts GPT-3.5 Turbo through Microsoft Azure. This is NOT
#   the public api.openai.com — it's your company's private instance.
#
#   Two key differences from standard OpenAI:
#
#   1. AUTHENTICATION HEADER:
#      - Standard OpenAI:  "Authorization: Bearer sk-abc123..."
#      - Azure OpenAI:     "api-key: your-company-key-here"
#
#   2. URL STRUCTURE:
#      - Standard OpenAI:  https://api.openai.com/v1/chat/completions
#      - Azure OpenAI:     https://your-company.openai.azure.com/openai/
#                           deployments/gpt-35-turbo/chat/completions
#                           ?api-version=2024-02-01
#
#   The router auto-detects which format to use based on the URL.
#
# INTERNET ACCESS: YES — connects to your company's intranet API endpoint
# ============================================================================
class APIRouter:
    """Route queries to Azure OpenAI or standard OpenAI API (online mode)."""

    # ── Azure OpenAI settings ──
    # AZURE_API_VERSION: Which Azure API version to use.
    #   Your company supports "2024-02-01" per the IT email.
    # AZURE_DEPLOYMENT: The deployment name for GPT-3.5 in Azure.
    #   Azure names it "gpt-35-turbo" (dash, not dot).
    AZURE_API_VERSION = "2024-02-01"
    AZURE_DEPLOYMENT = "gpt-35-turbo"

    def __init__(self, config: Config, api_key: str, endpoint: str = ""):
        """
        Set up the API router.

        Args:
            config:   The HybridRAG configuration object
            api_key:  Your API key (from Credential Manager or env var)
            endpoint: Your company's API base URL
        """
        self.config = config
        self.api_key = api_key
        self.logger = get_app_logger("api_router")

        # ── Determine the endpoint URL ──
        self.base_endpoint = endpoint.rstrip("/") if endpoint else config.api.endpoint.rstrip("/")

        # ── Auto-detect Azure vs standard OpenAI ──
        # If the URL contains "azure" or "aoai" anywhere, it's Azure.
        self.is_azure = (
            "azure" in self.base_endpoint.lower()
            or "aoai" in self.base_endpoint.lower()
        )

        # ── Build the full request URL ──
        if self.is_azure:
            # AZURE URL FORMAT:
            # {base}/openai/deployments/{deployment}/chat/completions?api-version={ver}
            self.request_url = (
                f"{self.base_endpoint}/openai/deployments/"
                f"{self.AZURE_DEPLOYMENT}/chat/completions"
                f"?api-version={self.AZURE_API_VERSION}"
            )
            self.logger.info(
                "api_router_init",
                provider="azure_openai",
                deployment=self.AZURE_DEPLOYMENT,
                api_version=self.AZURE_API_VERSION,
            )
        else:
            # STANDARD OPENAI URL FORMAT:
            # {base}/v1/chat/completions
            if "/v1/chat/completions" in self.base_endpoint:
                self.request_url = self.base_endpoint
            else:
                self.request_url = f"{self.base_endpoint}/v1/chat/completions"
            self.logger.info("api_router_init", provider="openai")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to the API and get the AI-generated answer back.

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        start_time = time.time()

        # ── Build HTTP headers ──
        # Azure:    "api-key: your-key-here"
        # Standard: "Authorization: Bearer your-key-here"
        if self.is_azure:
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        else:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

        # ── Build the request payload ──
        # Both Azure and standard OpenAI use the same chat message format.
        # NOTE: For Azure, we do NOT include "model" in the payload because
        # the model is already specified in the URL via the deployment name.
        payload = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": self.config.api.max_tokens,
            "temperature": self.config.api.temperature,
        }

        # Only include model name for standard OpenAI (not Azure)
        if not self.is_azure:
            payload["model"] = self.config.api.model

        try:
            with httpx.Client(timeout=self.config.api.timeout_seconds) as client:
                self.logger.info(
                    "api_query_sending",
                    url=self.request_url,
                    is_azure=self.is_azure,
                )
                resp = client.post(
                    self.request_url,
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()

            # ── Parse the response ──
            # Both Azure and standard OpenAI return the same JSON structure
            data = resp.json()
            response_text = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

            latency_ms = (time.time() - start_time) * 1000

            model_name = data.get(
                "model",
                self.AZURE_DEPLOYMENT if self.is_azure else self.config.api.model
            )

            self.logger.info(
                "api_query_success",
                model=model_name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                is_azure=self.is_azure,
            )

            return LLMResponse(
                text=response_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=model_name,
                latency_ms=latency_ms,
            )

        except httpx.HTTPStatusError as e:
            # ── HTTP error with a status code (401, 404, 429, 500, etc.) ──
            error_body = ""
            try:
                error_body = e.response.text[:500]
            except Exception:
                pass
            self.logger.error(
                "api_http_error",
                status_code=e.response.status_code,
                error=str(e),
                response_body=error_body,
                url=self.request_url,
                is_azure=self.is_azure,
            )
            return None

        except httpx.ConnectError as e:
            # ── Can't reach the server ──
            self.logger.error(
                "api_connection_error",
                error=str(e),
                url=self.request_url,
                hint="Check VPN connection and firewall rules",
            )
            return None

        except httpx.TimeoutException as e:
            # ── Request timed out ──
            self.logger.error(
                "api_timeout",
                error=str(e),
                timeout_seconds=self.config.api.timeout_seconds,
            )
            return None

        except (KeyError, json.JSONDecodeError) as e:
            # ── Response format unexpected ──
            self.logger.error("api_response_parse_error", error=str(e))
            return None

        except Exception as e:
            # ── Catch-all ──
            self.logger.error("api_error", error=str(e))
            return None

    def get_status(self) -> Dict[str, Any]:
        """
        Return current API router status for diagnostics.
        """
        status = {
            "provider": "azure_openai" if self.is_azure else "openai",
            "endpoint": self.base_endpoint,
            "request_url": self.request_url,
            "api_configured": True,
        }
        if self.is_azure:
            status["deployment"] = self.AZURE_DEPLOYMENT
            status["api_version"] = self.AZURE_API_VERSION
        return status


# ============================================================================
# LLMRouter — The main switchboard
# ============================================================================
# This is the class that the rest of HybridRAG talks to.
# It decides whether to use Ollama (offline) or the API (online)
# based on the mode setting in your config.
# ============================================================================
class LLMRouter:
    """
    Route queries to the appropriate LLM backend.

    Mode selection:
        "offline" → Ollama (local, free, no internet)
        "online"  → Azure OpenAI API (company cloud, costs money)
    """

    def __init__(self, config: Config, api_key: Optional[str] = None):
        """
        Initialize the router and set up both backends.

        Args:
            config:  The HybridRAG configuration object
            api_key: Optional explicit API key (overrides all other sources)
        """
        self.config = config
        self.logger = get_app_logger("llm_router")

        # ── Always create the Ollama router (offline mode) ──
        self.ollama = OllamaRouter(config)

        # ── Resolve API key from the priority chain ──
        resolved_key = api_key

        if not resolved_key:
            try:
                from ..security.credentials import get_api_key
                resolved_key = get_api_key()
            except ImportError:
                pass

        if not resolved_key:
            resolved_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        if not resolved_key:
            resolved_key = os.environ.get("OPENAI_API_KEY", "")

        # ── Resolve API endpoint from the priority chain ──
        resolved_endpoint = ""

        try:
            from ..security.credentials import get_api_endpoint
            resolved_endpoint = get_api_endpoint()
        except ImportError:
            pass

        if not resolved_endpoint:
            resolved_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not resolved_endpoint:
            resolved_endpoint = os.environ.get("OPENAI_API_ENDPOINT", "")

        # ── Override config endpoint if we found a custom one ──
        if resolved_endpoint:
            self.config.api.endpoint = resolved_endpoint

        # ── Create the API router (only if we have a key) ──
        if resolved_key:
            self.api = APIRouter(config, resolved_key, resolved_endpoint)
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
            return self.ollama.query(prompt)

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of all LLM backends.
        Used by rag-cred-status, rag-test-api, and diagnostics.
        """
        status = {
            "mode": self.config.mode,
            "ollama_available": self.ollama.is_available(),
            "api_configured": self.api is not None,
        }

        if self.api:
            api_status = self.api.get_status()
            status.update({
                "api_provider": api_status["provider"],
                "api_endpoint": api_status["endpoint"],
                "api_request_url": api_status["request_url"],
            })
            if api_status.get("deployment"):
                status["api_deployment"] = api_status["deployment"]
                status["api_version"] = api_status["api_version"]

        return status
