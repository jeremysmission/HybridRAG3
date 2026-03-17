# ============================================================================
# ollama_router.py -- OllamaRouter class (offline, localhost)
# ============================================================================
#
# Extracted from llm_router.py to keep each module under 500 lines.
# Ollama runs on your machine at http://localhost:11434. It hosts
# open-source models like Phi-4 and Mistral that work without internet.
#
# This router uses raw httpx because Ollama has a simple REST API
# and doesn't need the openai SDK.
#
# INTERNET ACCESS: NONE (localhost only)
# ============================================================================

import json
import time
import threading
from typing import Optional, Dict, Any, Generator

from .llm_response import (
    LLMResponse,
    _build_httpx_client,
    _http_error_message,
    _ollama_retry_model_name,
    _safe_timeout_seconds,
)
from .config import Config
from .generation_params import build_ollama_generation_options
from .model_identity import canonicalize_model_name, resolve_ollama_model_name
from .network_gate import get_gate, NetworkBlockedError
from .ollama_endpoint_resolver import sanitize_ollama_base_url
from ..monitoring.logger import get_app_logger


def _build_ollama_request_timeout(config: Config, prompt: str) -> Any:
    """Give large grounded prompts more read headroom before first token."""
    import httpx

    base_timeout = _safe_timeout_seconds(
        getattr(getattr(config, "ollama", None), "timeout_seconds", 120.0),
        default=120.0,
    )
    prompt_text = str(prompt or "")
    read_timeout = base_timeout
    if prompt_text.startswith("GROUNDING RULES:") and len(prompt_text) >= 3000:
        read_timeout = max(base_timeout, 600.0)

    connect_timeout = min(max(base_timeout, 5.0), 30.0)
    pool_timeout = min(max(base_timeout, 5.0), 30.0)
    return httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=base_timeout,
        pool=pool_timeout,
    )


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
        return build_ollama_generation_options(self.config)

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
        """
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

        def _post_generate(selected_model: str):
            payload = {
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": getattr(self.config.ollama, "keep_alive", -1),
                "options": self._build_options(),
            }
            response = self._client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=_build_ollama_request_timeout(self.config, prompt),
            )
            response.raise_for_status()
            return response

        model_name = self._resolve_model_name(self.config.ollama.model)

        try:
            try:
                resp = _post_generate(model_name)
            except httpx.HTTPStatusError as e:
                retry_model = _ollama_retry_model_name(self, model_name, e)
                if not retry_model:
                    raise
                model_name = retry_model
                resp = _post_generate(model_name)

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
            self.last_error = _http_error_message(e)
            self.logger.error("ollama_http_error", error=str(e))
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_error", error=str(e))
            return None

    def query_stream(
        self,
        prompt: str,
        cancel_event=None,
    ) -> Generator[Dict[str, Any], None, None]:
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

        try:
            if cancel_event is not None and cancel_event.is_set():
                return
            refreshed = False
            while True:
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
                        timeout=_build_ollama_request_timeout(self.config, prompt),
                    ) as response:
                        response.raise_for_status()
                        tokens_in = 0
                        tokens_out = 0
                        watcher_stop = threading.Event()
                        watcher = None
                        if cancel_event is not None:
                            def _close_on_cancel():
                                while not watcher_stop.wait(0.05):
                                    if cancel_event.is_set():
                                        try:
                                            response.close()
                                        except Exception:
                                            pass
                                        return

                            watcher = threading.Thread(
                                target=_close_on_cancel,
                                daemon=True,
                                name="hybridrag-ollama-stream-cancel",
                            )
                            watcher.start()
                        try:
                            for line in response.iter_lines():
                                if cancel_event is not None and cancel_event.is_set():
                                    return
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
                        finally:
                            watcher_stop.set()
                            if watcher is not None:
                                watcher.join(timeout=0.2)
                    break
                except httpx.HTTPStatusError as e:
                    retry_model = ""
                    if not refreshed:
                        retry_model = _ollama_retry_model_name(self, model_name, e)
                    if not retry_model:
                        raise
                    model_name = retry_model
                    refreshed = True

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
            if cancel_event is not None and cancel_event.is_set():
                return
            self.last_error = _http_error_message(e)
            self.logger.error("ollama_stream_http_error", error=str(e))
            yield {"error": self.last_error, "backend": "ollama"}
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                return
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("ollama_stream_error", error=str(e))
            yield {"error": self.last_error, "backend": "ollama"}

    def close(self):
        """Release the persistent HTTP client."""
        if hasattr(self, "_client") and self._client:
            self._client.close()
