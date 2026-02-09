# ============================================================================
# HybridRAG — LLM Router (src/core/llm_router.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   This is the "switchboard" that decides which AI model answers your question.
#   HybridRAG supports two modes:
#     - OFFLINE: Uses Ollama (a program running on your laptop that hosts an
#                AI model locally — no internet needed)
#     - ONLINE:  Uses OpenAI's GPT-3.5 Turbo API (requires internet + API key)
#
# WHY TWO MODES?
#   In restricted environments, internet access may not be available.
#   Offline mode lets you run the full RAG pipeline without any network.
#   Online mode gives you access to a more powerful model when internet is OK.
#
# HOW IT WORKS:
#   1. The QueryEngine calls LLMRouter.query(prompt)
#   2. LLMRouter checks config.mode ("offline" or "online")
#   3. It routes the prompt to the right backend (Ollama or GPT API)
#   4. The backend sends back the AI-generated answer + token counts
#   5. LLMRouter wraps the answer in an LLMResponse object and returns it
#
# INTERNET ACCESS:
#   - OllamaRouter: Connects to localhost only (127.0.0.1) — NO internet
#   - APIRouter: Connects to OpenAI's API — REQUIRES internet
#   - The mode setting in config.yaml controls which one is used
#
# DEPENDENCIES:
#   - httpx: A modern HTTP client library (like "requests" but async-capable)
#   - config.py: Provides all settings (URLs, model names, timeouts)
#   - logger.py: Structured logging for audit trail
# ============================================================================

import httpx          # HTTP client for making web requests to APIs
import json           # For parsing JSON responses from APIs
import time           # For measuring how long each query takes
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
        model:      Which model generated the answer (e.g., "mistral", "gpt-3.5-turbo")
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
            5. Wrap everything in an LLMResponse object

        Args:
            prompt: The full prompt text (includes context from retrieved
                    documents plus the user's question)

        Returns:
            LLMResponse with the answer, or None if something went wrong
        """
        # Start a timer so we can measure how long the LLM takes
        start_time = time.time()

        # Build the request payload (what we send to Ollama)
        # This is a JSON object with the model name, prompt, and settings
        payload = {
            "model": self.config.ollama.model,       # e.g., "mistral" or "llama2"
            "prompt": prompt,                         # The full prompt text
            "stream": False,                          # Get the complete answer at once
                                                      # (not word-by-word streaming)
            "num_predict": self.config.ollama.context_window,  # Max tokens to generate
        }

        try:
            # Create an HTTP client with a timeout from config
            # (prevents hanging forever if Ollama freezes)
            with httpx.Client(timeout=self.config.ollama.timeout_seconds) as client:
                # Send the prompt to Ollama via HTTP POST
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,  # httpx automatically converts dict to JSON
                )
                # Raise an error if the HTTP status code indicates failure
                # (e.g., 404 Not Found, 500 Server Error)
                resp.raise_for_status()

            # Parse the JSON response from Ollama
            data = resp.json()

            # Extract the pieces we need
            response_text = data.get("response", "")       # The actual answer text
            prompt_eval_count = data.get("prompt_eval_count", 0)  # Input tokens used
            eval_count = data.get("eval_count", 0)          # Output tokens generated

            # Calculate how long the whole round-trip took
            latency_ms = (time.time() - start_time) * 1000  # Convert seconds to ms

            # Log the successful query for audit trail
            self.logger.info(
                "ollama_query_success",
                model=self.config.ollama.model,
                tokens_in=prompt_eval_count,
                tokens_out=eval_count,
                latency_ms=latency_ms,
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
# APIRouter — Talks to OpenAI's GPT-3.5 Turbo API
# ============================================================================
# This router sends prompts to the cloud-based GPT API.
# It REQUIRES internet access and a valid API key.
#
# COST: Every call costs money based on token usage.
#   - Input tokens (your prompt): ~$0.0005 per 1K tokens
#   - Output tokens (the answer): ~$0.0015 per 1K tokens
#   - The QueryEngine calculates and logs costs automatically
#
# INTERNET ACCESS: YES — connects to api.openai.com (or your custom endpoint)
# ============================================================================
class APIRouter:
    """Route queries to GPT-3.5 Turbo API (online mode)."""

    def __init__(self, config: Config, api_key: str):
        self.config = config
        self.api_key = api_key     # Your OpenAI API key (from environment variable)
        self.logger = get_app_logger("api_router")

    def query(self, prompt: str) -> Optional[LLMResponse]:
        """
        Send a prompt to GPT-3.5 Turbo and get the AI-generated answer back.

        How it works:
            1. Builds an HTTP request with your API key in the Authorization header
            2. Sends the prompt as a "chat message" to OpenAI's messages endpoint
            3. OpenAI processes the prompt and returns the generated answer
            4. We extract the answer text and token usage from the response
            5. Wrap everything in an LLMResponse object

        Args:
            prompt: The full prompt text (context + user question)

        Returns:
            LLMResponse with the answer, or None if something went wrong
        """
        start_time = time.time()

        # HTTP headers — the API key goes in the Authorization header
        # "Bearer" is an authentication scheme used by most APIs
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # OpenAI's API uses a "chat" format where messages have roles
        # "user" = the person asking (that's our prompt)
        # "assistant" = the AI's response (OpenAI fills this in)
        payload = {
            "model": self.config.api.model,          # e.g., "gpt-3.5-turbo"
            "messages": [
                {"role": "user", "content": prompt}  # Our prompt as a user message
            ],
            "max_tokens": self.config.api.max_tokens,     # Max length of answer
            "temperature": self.config.api.temperature,   # 0.0 = deterministic,
                                                          # 1.0 = creative/random
        }

        try:
            with httpx.Client(timeout=self.config.api.timeout_seconds) as client:
                # Send to OpenAI (or whatever endpoint is configured)
                resp = client.post(
                    self.config.api.endpoint,  # Usually "https://api.openai.com/v1/..."
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()

            # Parse the JSON response
            data = resp.json()

            # OpenAI returns answers in data["choices"][0]["message"]["content"]
            # The "choices" array can contain multiple responses, but we only
            # request one, so we take choices[0]
            response_text = data["choices"][0]["message"]["content"]

            # Token usage for cost tracking
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)       # How many tokens our prompt used
            tokens_out = usage.get("completion_tokens", 0)   # How many tokens the answer used

            latency_ms = (time.time() - start_time) * 1000

            # Log successful query with full details for audit
            self.logger.info(
                "api_query_success",
                model=self.config.api.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )

            return LLMResponse(
                text=response_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=self.config.api.model,
                latency_ms=latency_ms,
            )

        except httpx.HTTPError as e:
            # HTTP errors: connection failed, timeout, 401 unauthorized, etc.
            self.logger.error("api_http_error", error=str(e))
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
# The QueryEngine creates one LLMRouter and calls router.query(prompt)
# without needing to know which backend is active.
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
        self.config = config
        self.logger = get_app_logger("llm_router")

        # Always create the Ollama router (it's local, no cost to initialize)
        self.ollama = OllamaRouter(config)

        # Only create the API router if an API key was provided
        # If no key, online mode will fail gracefully with an error message
        self.api = APIRouter(config, api_key) if api_key else None

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
                # This happens if mode is "online" but no API key was provided
                self.logger.error("query_error", error="API key not configured")
                return None
            self.logger.info("query_mode", mode="online")
            return self.api.query(prompt)

        else:
            # Unknown mode — this should never happen with a valid config
            self.logger.error("query_error", error=f"Unknown mode: {self.config.mode}")
            return None
