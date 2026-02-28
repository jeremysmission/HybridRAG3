# ============================================================================
# HybridRAG -- Embedder (src/core/embedder.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Converts text into "embedding vectors" -- arrays of numbers that
#   represent the MEANING of the text. Two pieces of text with similar
#   meaning will have similar vectors, even if they use different words.
#
#   Example:
#     "The maximum operating temperature is 85C"
#     "Thermal limit: do not exceed eighty-five degrees"
#     -> These produce similar vectors (high cosine similarity)
#
# HOW IT WORKS:
#   We send text to the local Ollama server which runs the nomic-embed-text
#   model. Ollama handles the actual neural network inference. This file
#   just manages the HTTP calls, batching, and vector normalization.
#
#   Input: a string of text (up to ~8192 tokens for nomic-embed-text)
#   Output: a numpy array of 768 floating-point numbers
#
# WHY nomic-embed-text:
#   - Served by Ollama: same server that runs our LLM, no extra dependencies
#   - 768 dimensions: higher quality than 384-dim alternatives
#   - 8192 token context: handles long chunks without truncation
#   - Apache 2.0 license: no use-case restrictions, no AI approval required
#   - Removes ~2.5GB of HuggingFace dependencies (torch, transformers, etc.)
#
# SECURITY MODEL:
#   Ollama runs on 127.0.0.1:11434 only. No data leaves the machine.
#   Uses 127.0.0.1 (not "localhost") to prevent corporate proxy/DNS
#   interception that can redirect embedding traffic to remote hosts.
#   The OLLAMA_HOST env var can override the base URL if needed.
#
# INTERNET ACCESS: NONE
#   Ollama serves models from local disk. Models must be pre-pulled via
#   "ollama pull nomic-embed-text" before first use.
# ============================================================================

from __future__ import annotations

import os
from urllib.parse import urlparse

from ..monitoring.logger import get_app_logger
from .exceptions import OllamaNotRunningError, OllamaModelNotFoundError


class Embedder:
    """
    Wrapper around Ollama embedding API for text -> vector conversion.

    Used in two places:
      1. Indexing: embed_batch() processes chunks in bulk
      2. Querying: embed_query() processes a single user question
    """

    # Default used only when no config is available (tests, scripts).
    # Production code should always pass model_name from config.
    DEFAULT_MODEL = "nomic-embed-text"

    # Hostnames considered safe for embedding traffic (no gate check needed)
    _LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

    def __init__(self, model_name: str | None = None):
        """
        Initialize the embedder and verify the Ollama model is available.

        Parameters
        ----------
        model_name : str or None
            Name of the Ollama embedding model. When None, falls back to
            DEFAULT_MODEL. Must be pre-pulled via "ollama pull <model>".

            Set via config/default_config.yaml -> embedding.model_name.
        """
        import httpx

        self.model_name = model_name or self.DEFAULT_MODEL
        self.logger = get_app_logger("embedder")

        # Ollama base URL -- default to 127.0.0.1 (NOT "localhost") to
        # prevent corporate proxy/DNS interception. On work networks,
        # "localhost" can resolve through corporate DNS and get redirected
        # to a proxy IP (e.g. 301 -> 10.x.x.x), silently sending
        # embedding text off-machine.
        self.base_url = os.getenv(
            "OLLAMA_HOST", "http://127.0.0.1:11434"
        ).rstrip("/")

        # Enforce localhost-only unless NetworkGate explicitly allows
        self._validate_host()

        # Persistent HTTP client -- never follow redirects (a redirect
        # from localhost means a proxy is intercepting our traffic).
        # proxy=None forces direct connection, bypassing corporate proxy
        # that intercepts even 127.0.0.1 via transparent interception.
        self._client = httpx.Client(
            timeout=httpx.Timeout(120),
            follow_redirects=False,
            proxy=None,
        )

        # Detect dimension by embedding a probe string.
        # This also verifies Ollama is running and the model is pulled.
        self.dimension = self._detect_dimension()

    def _validate_host(self) -> None:
        """
        Enforce that OLLAMA_HOST points to loopback unless NetworkGate
        explicitly allows the destination. Prevents accidental data
        exfiltration when OLLAMA_HOST is misconfigured to a remote host.
        """
        parsed = urlparse(self.base_url)
        hostname = (parsed.hostname or "").lower()
        if hostname not in self._LOOPBACK_HOSTS:
            # Non-local host -- must pass NetworkGate
            try:
                from .network_gate import get_gate
                get_gate().check_allowed(
                    f"{self.base_url}/api/embed",
                    "embedder_init", "embedder",
                )
                self.logger.info(
                    "embedder_remote_host_allowed",
                    base_url=self.base_url,
                )
            except Exception as exc:
                raise OllamaNotRunningError(
                    f"OLLAMA_HOST '{self.base_url}' is not localhost and "
                    f"NetworkGate blocked it: {exc}"
                ) from exc

    def _assert_no_redirect(self, resp) -> None:
        """
        Reject HTTP redirect responses (3xx).

        WHY: Corporate proxies can intercept localhost requests and return
        a 301/302 pointing to a remote proxy IP (e.g. 10.x.x.x). If we
        followed the redirect, embedding text would be sent off-machine.
        This was observed on work networks where "localhost" DNS resolved
        through a corporate interceptor.
        """
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("location", "(unknown)")
            raise OllamaNotRunningError(
                f"Ollama at {self.base_url} returned redirect "
                f"{resp.status_code} -> {location}. "
                f"A corporate proxy may be intercepting localhost traffic. "
                f"Verify Ollama is running: ollama serve"
            )

    def _detect_dimension(self) -> int:
        """
        Embed a test string to discover the model's output dimension.

        Also serves as a health check: if Ollama is not running or the
        model is not pulled, this will raise a clear error at startup
        rather than failing silently on the first real query.
        """
        import httpx

        try:
            resp = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model_name, "input": ["dimension probe"]},
            )
            self._assert_no_redirect(resp)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [[]])
            dim = len(embeddings[0])
            self.logger.info(
                "embedder_ready",
                model=self.model_name,
                dimension=dim,
                base_url=self.base_url,
            )
            return dim
        except httpx.ConnectError:
            raise OllamaNotRunningError(
                f"Ollama is not running at {self.base_url}. "
                f"Start it with: ollama serve"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise OllamaModelNotFoundError(
                    f"Embedding model '{self.model_name}' not found. "
                    f"Pull it with: ollama pull {self.model_name}",
                    model=self.model_name,
                )
            raise

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """
        Embed multiple texts at once (used during indexing).

        Sends texts to Ollama's /api/embed endpoint in batches. Each
        batch is a single HTTP call with multiple input strings.

        Parameters
        ----------
        texts : list[str]
            List of text strings to embed.

        Returns
        -------
        np.ndarray
            Shape (N, dimension), dtype float32.
            Vectors are L2-normalized so dot product = cosine similarity.
        """
        import numpy as np

        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)

        all_embeddings = []
        batch_size = int(os.getenv("HYBRIDRAG_EMBED_BATCH", "64"))

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            resp = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model_name, "input": batch},
            )
            self._assert_no_redirect(resp)
            resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend(data["embeddings"])

        result = np.array(all_embeddings, dtype=np.float32)

        # L2-normalize to unit length so dot product = cosine similarity.
        # The vector_store and retriever rely on this for scoring.
        norms = np.linalg.norm(result, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        result /= norms

        return result

    def encode(self, texts: list[str]) -> np.ndarray:
        """
        Alias for embed_batch().

        EXISTS FOR CONVENIENCE:
          Some callers (diagnostic tools, notebooks, quick tests) use
          the more intuitive name "encode" instead of "embed_batch".
          This alias keeps both working without duplicating code.
        """
        return self.embed_batch(texts)

    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed a single query string (used at search time).

        Parameters
        ----------
        text : str
            The user's question.

        Returns
        -------
        np.ndarray
            Shape (dimension,), dtype float32.
        """
        vec = self.embed_batch([str(text or "")])
        return vec[0]

    def close(self) -> None:
        """
        Release the HTTP client.

        Safe to call multiple times. After calling close(), the embedder
        cannot be used again -- create a new instance if needed.
        """
        if hasattr(self, "_client") and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
