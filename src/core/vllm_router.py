# ============================================================================
# vllm_router.py -- VLLMRouter class (workstation offline, localhost)
# ============================================================================
#
# Extracted from llm_router.py to keep each module under 500 lines.
# vLLM serves an OpenAI-compatible API on localhost. It provides:
#   - Continuous batching (multiple concurrent queries)
#   - Prefix caching (repeated prompt prefixes are free)
#   - Tensor parallelism (split one model across both RTX 3090s)
#   - 2-3x faster generation than Ollama for the same model
#
# The router uses raw httpx to POST to the OpenAI-compatible
# /v1/chat/completions endpoint.
#
# INTERNET ACCESS: NONE (localhost only)
# ============================================================================

import json
import time
import threading
from typing import Optional, Dict, Any, Generator

from .llm_response import LLMResponse, _build_httpx_client
from .config import Config
from .network_gate import get_gate, NetworkBlockedError
from ..monitoring.logger import get_app_logger


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

    def query_stream(
        self,
        prompt: str,
        cancel_event=None,
    ) -> Generator[Dict[str, Any], None, None]:
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
            if cancel_event is not None and cancel_event.is_set():
                return
            tokens_in = 0
            tokens_out = 0
            with self._client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
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
                        name="hybridrag-vllm-stream-cancel",
                    )
                    watcher.start()
                try:
                    for line in response.iter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            return
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
                finally:
                    watcher_stop.set()
                    if watcher is not None:
                        watcher.join(timeout=0.2)

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
            if cancel_event is not None and cancel_event.is_set():
                return
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_stream_http_error", error=str(e))
            yield {"error": self.last_error, "backend": "vllm"}
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                return
            self.last_error = f"{type(e).__name__}: {e}"
            self.logger.error("vllm_stream_error", error=str(e))
            yield {"error": self.last_error, "backend": "vllm"}

    def close(self):
        """Release the persistent HTTP client."""
        if hasattr(self, "_client") and self._client:
            self._client.close()
