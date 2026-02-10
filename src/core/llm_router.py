# ============================================================================
# HybridRAG v3 — LLM Router (src/core/llm_router.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Routes AI queries to the correct backend based on the "mode" setting:
#     - "offline" → Ollama (runs locally on your machine, FREE, no internet)
#     - "online"  → GPT-3.5 Turbo API (cloud, costs ~$0.002/query)
#
#   This is the ONLY file in the entire system that makes network calls
#   to an LLM. Every other file works 100% locally.
#
# HOW IT WORKS:
#   1. The QueryEngine calls LLMRouter.query(prompt)
#   2. LLMRouter checks config.mode ("offline" or "online")
#   3. It routes the prompt to the right backend (Ollama or GPT API)
#   4. The backend sends back the AI-generated answer + token counts
#   5. LLMRouter wraps the answer in an LLMResponse object and returns it
#
# API KEY RESOLUTION (for online mode):
#   The API key is resolved from these sources, in order of priority:
#     1. Explicit api_key parameter (if the caller passes one)
#     2. Windows Credential Manager via keyring (most secure)
#     3. OPENAI_API_KEY environment variable (fallback)
#     4. None → online mode disabled, offline still works
#
# CUSTOM ENDPOINT RESOLUTION:
#   The API endpoint is resolved from these sources, in order:
#     1. Windows Credential Manager via keyring
#     2. OPENAI_API_ENDPOINT environment variable
#     3. config.api.endpoint from default_config.yaml (default)
#
# INTERNET ACCESS:
#   - OllamaRouter: Connects to localhost only (127.0.0.1) — NO internet
#   - APIRouter: Connects to configured API endpoint — REQUIRES internet
#   - The mode setting in config.yaml controls which one is used
#   - HuggingFace is ALWAYS blocked regardless of mode (Layer 1 lockdown)
#
# DEPENDENCIES:
#   - httpx: Modern HTTP client library (like "requests" but cleaner)
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
        model:      Which model generated the answer (e.g., "llama3", "gpt-3.5-turbo")
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
        # Example: "http://localhost:11434/" becomes "http://localhost:11434"
        self.base_url = config.ollama.base_url.rstrip("/")

    def is_available(self) -> bool:
        """
        Check if Ollama is currently running on this machine.

        How it works:
            Sends a quick request to Ollama's /api/tags endpoint.
            If Ollama is running, it responds with a list of available models.
            If it's not running, the connection fails and we return False.

        Returns:
            True if Ollama is running and responding, False otherwise
        """
        try:
            # timeout=5 means give up after 5 seconds if no response
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                # HTTP 200 means "OK, everything worked"
                return resp.status_code == 200
        except Exception as e:
            # Any error (connection refused, timeout, etc.) means Ollama isn't available
            self.logger.warn("ollama_unavailable", error=str(e))
            return False

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to Ollama and get the AI-generated answer back.

        How it works:
            1. Packages the prompt into a JSON payload with model settings
            2. Sends it to Ollama's /api/generate endpoint via HTTP POST
            3. Ollama runs the model and returns the generated text
            4. We extract the answer and token counts from the response
            5. Wrap everything in an LLMResponse object and return it

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        start_time = time.time()

        # Build the request payload for Ollama's /api/generate endpoint
        payload = {
            "model": self.config.ollama.model,    # e.g., "llama3"
            "prompt": prompt,                      # The full prompt text
            "stream": False,                       # Get complete response at once
            "num_predict": self.config.ollama.context_window,  # Max tokens to generate
        }

        try:
            # Create an HTTP client with the configured timeout
            with httpx.Client(timeout=self.config.ollama.timeout_seconds) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()  # Throw error if HTTP status != 200

            # Parse the JSON response from Ollama
            data = resp.json()
            response_text = data.get("response", "")
            prompt_eval_count = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            latency_ms = (time.time() - start_time) * 1000

            # Log success for audit trail
            self.logger.info(
                "ollama_query_success",
                model=self.config.ollama.model,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                latency_ms=round(latency_ms, 1),
            )

            # Return the standardized response object
            return LLMResponse(
                text=response_text,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                model=self.config.ollama.model,
                latency_ms=latency_ms,
            )

        except httpx.HTTPError as e:
            # HTTP-level errors (connection refused, timeout, bad status code)
            self.logger.error("ollama_http_error", error=str(e))
            return None
        except Exception as e:
            # Any other unexpected error
            self.logger.error("ollama_error", error=str(e))
            return None


# ============================================================================
# APIRouter — Talks to GPT-3.5 Turbo API (or any OpenAI-compatible endpoint)
# ============================================================================
# This router sends prompts to the cloud-based GPT API.
# It REQUIRES internet access and a valid API key.
#
# COST: Every call costs money based on token usage.
#   - Input tokens (your prompt): ~$0.0005 per 1K tokens
#   - Output tokens (the answer): ~$0.0015 per 1K tokens
#   - The QueryEngine calculates and logs costs automatically
#
# INTERNET ACCESS: YES — connects to the configured API endpoint
# ============================================================================
class APIRouter:
    """Route queries to GPT-3.5 Turbo API (online mode)."""

    def __init__(self, config: Config, api_key: str):
        self.config = config
        self.api_key = api_key     # Your API key (from Credential Manager or env var)
        self.logger = get_app_logger("api_router")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to GPT-3.5 Turbo and get the AI-generated answer back.

        How it works:
            1. Builds an HTTP request with your API key in the Authorization header
            2. Sends the prompt as a "chat message" to the API's messages endpoint
            3. The API processes the prompt and returns the generated answer
            4. We extract the answer text and token usage from the response
            5. Wrap everything in an LLMResponse and return it

        Args:
            prompt: The complete prompt (context + user question)

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        start_time = time.time()

        # ── Build HTTP headers ──
        # The Authorization header uses "Bearer" token authentication.
        # This is the industry standard for API authentication.
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # ── Build the request payload ──
        # This follows the OpenAI Chat Completions API format.
        # Most LLM APIs (including company-hosted ones) use this same format.
        payload = {
            "model": self.config.api.model,          # e.g., "gpt-3.5-turbo"
            "messages": [
                {"role": "user", "content": prompt}  # The prompt as a user message
            ],
            "max_tokens": self.config.api.max_tokens,       # Max response length
            "temperature": self.config.api.temperature,     # Creativity (0.1 = focused)
        }

        try:
            # ── Send the request ──
            with httpx.Client(timeout=self.config.api.timeout_seconds) as client:
                resp = client.post(
                    self.config.api.endpoint,  # The API URL (from config or env var)
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()  # Throw error if HTTP status != 200

            # ── Parse the response ──
            data = resp.json()
            response_text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            latency_ms = (time.time() - start_time) * 1000

            # Log success (but NEVER log the API key!)
            self.logger.info(
                "api_query_success",
                model=self.config.api.model,
                endpoint=self.config.api.endpoint,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(latency_ms, 1),
            )

            return LLMResponse(
                text=response_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=self.config.api.model,
                latency_ms=latency_ms,
            )

        except httpx.HTTPStatusError as e:
            # HTTP error with a response (400, 401, 403, 429, 500, etc.)
            # Log the status code but NOT the response body (may contain key)
            self.logger.error("api_http_error",
                              status_code=e.response.status_code,
                              error=str(e))
            return None
        except httpx.HTTPError as e:
            # Connection-level errors (timeout, DNS failure, etc.)
            self.logger.error("api_connection_error", error=str(e))
            return None
        except (KeyError, json.JSONDecodeError) as e:
            # Response parsing errors: API returned unexpected format
            self.logger.error("api_response_error", error=str(e))
            return None
        except Exception as e:
            # Catch-all for anything else
            self.logger.error("api_error", error=str(e))
            return None


# ============================================================================
# LLMRouter — The main switchboard
# ============================================================================
# This is what the rest of the code calls. It decides which backend to use
# based on the "mode" setting in config.yaml:
#   mode: "offline"  →  uses OllamaRouter (local, no internet)
#   mode: "online"   →  uses APIRouter (cloud, requires internet + API key)
#
# API KEY RESOLUTION (this is the critical fix for BUG 1 and BUG 2):
#   The constructor resolves the API key from multiple sources:
#     1. Explicit parameter (if the diagnostic script passes one)
#     2. Windows Credential Manager via keyring (most secure)
#     3. OPENAI_API_KEY environment variable (fallback)
#
# ENDPOINT RESOLUTION (fix for BUG 2):
#   If OPENAI_API_ENDPOINT is set in env vars or keyring, it overrides
#   the endpoint in default_config.yaml. This lets you use your company's
#   internal API without editing the YAML.
# ============================================================================
class LLMRouter:
    """
    Main LLM routing switchboard.

    Decides which AI backend handles each query based on the mode
    setting in config.yaml. The rest of the code just calls
    router.query(prompt) and gets an answer back — it doesn't need
    to know whether Ollama or GPT is doing the work.

    Mode selection:
        "offline" → Ollama (local, no internet)
        "online"  → GPT-3.5 API (cloud, costs money)
    """

    def __init__(self, config: Config, api_key: Optional[str] = None):
        """
        Initialize the LLM router.

        Args:
            config: The loaded configuration object
            api_key: Optional explicit API key. If not provided, the router
                     will try to find one from keyring or environment variables.
        """
        self.config = config
        self.logger = get_app_logger("llm_router")

        # ── Always create the Ollama router (it's local, free to init) ──
        self.ollama = OllamaRouter(config)

        # ── Resolve API key from multiple sources ──────────────────────
        # Priority: explicit param → keyring → env var → None
        #
        # This is the fix for BUG 1: Previously, if no api_key parameter
        # was passed, the APIRouter was never created and online mode
        # silently failed with "API key not configured."
        # ───────────────────────────────────────────────────────────────
        resolved_key = api_key  # Start with explicit parameter (may be None)

        if not resolved_key:
            # Try Windows Credential Manager (most secure)
            try:
                from ..security.credentials import get_api_key
                resolved_key = get_api_key()
            except ImportError:
                # credentials.py not yet deployed — fall through to env var
                pass

        if not resolved_key:
            # Try environment variable (less secure but functional)
            resolved_key = os.environ.get("OPENAI_API_KEY", "")

        # ── Resolve custom API endpoint ────────────────────────────────
        # Priority: keyring → env var → config.yaml
        #
        # This is the fix for BUG 2: Your company's internal API endpoint
        # can now be set via keyring or env var without editing the YAML.
        # ───────────────────────────────────────────────────────────────
        custom_endpoint = ""
        try:
            from ..security.credentials import get_api_endpoint
            custom_endpoint = get_api_endpoint()
        except ImportError:
            pass

        if not custom_endpoint:
            custom_endpoint = os.environ.get("OPENAI_API_ENDPOINT", "")

        if custom_endpoint:
            self.config.api.endpoint = custom_endpoint
            self.logger.info("api_endpoint_override",
                             endpoint=custom_endpoint)

        # ── Create APIRouter only if we found a key ────────────────────
        if resolved_key:
            self.api = APIRouter(config, resolved_key)
            # Log that we found a key (but NEVER log the key itself!)
            source = "parameter"
            if not api_key:
                source = "keyring_or_env"
            self.logger.info("api_key_resolved", source=source)
        else:
            self.api = None
            self.logger.info("api_key_not_found",
                             message="Online mode disabled. Offline mode available.")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Route a prompt to the appropriate AI backend and return the answer.

        This is the main entry point. The QueryEngine calls this method
        with a fully-built prompt (context + user question) and gets
        back an LLMResponse with the generated answer.

        Args:
            prompt: The complete prompt to send to the AI model

        Returns:
            LLMResponse with the answer, or None if the call failed
        """
        # Check which mode is configured and route accordingly
        if self.config.mode == "offline":
            # OFFLINE: Send to Ollama (local, no internet needed)
            self.logger.info("query_mode", mode="offline")
            return self.ollama.query(prompt)

        elif self.config.mode == "online":
            # ONLINE: Send to GPT API (requires internet + API key)
            if not self.api:
                # This happens if mode is "online" but no API key was found
                # anywhere (not in keyring, not in env var, not passed in)
                self.logger.error("query_error", error="API key not configured. "
                                  "Run: python -m src.security.credentials store")
                print("\n❌ API key not configured for online mode.")
                print("   Run: python -m src.security.credentials store")
                print("   Or set OPENAI_API_KEY environment variable.\n")
                return None
            self.logger.info("query_mode", mode="online",
                             endpoint=self.config.api.endpoint)
            return self.api.query(prompt)

        else:
            # Unknown mode — this should never happen with a valid config
            self.logger.error("query_error", error=f"Unknown mode: {self.config.mode}")
            return None

    def get_status(self) -> dict:
        """
        Get the current status of both LLM backends.

        Useful for diagnostics, health checks, and the future GUI.

        Returns:
            Dictionary with status of each backend:
            {
                "mode": "offline" | "online",
                "ollama_available": True | False,
                "api_configured": True | False,
                "api_endpoint": "https://..." | None,
            }
        """
        return {
            "mode": self.config.mode,
            "ollama_available": self.ollama.is_available(),
            "api_configured": self.api is not None,
            "api_endpoint": self.config.api.endpoint if self.api else None,
        }
