# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the embedder part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
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
#   Uses 127.0.0.1 (not "localhost") to prevent managed-network proxy/DNS
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

import numpy as np

from ..monitoring.logger import get_app_logger
from .exceptions import OllamaNotRunningError, OllamaModelNotFoundError
from .ollama_endpoint_resolver import sanitize_ollama_base_url


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

    # nomic-embed-text is a task-aware model: queries and documents use
    # different prefixes so the model maps them to the correct embedding
    # subspace. Without these, retrieval accuracy drops 2-5%.
    # Ref: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
    _NOMIC_MODELS = frozenset({"nomic-embed-text", "nomic-embed-text:latest",
                                "nomic-embed-text:v1.5"})

    def __init__(self, model_name: str | None = None, dimension: int = 0):
        """
        Initialize the embedder.

        Parameters
        ----------
        model_name : str or None
            Name of the Ollama embedding model. When None, falls back to
            DEFAULT_MODEL. Must be pre-pulled via "ollama pull <model>".
        dimension : int
            If >0, skip the startup probe and use this dimension.
            Pass from config to avoid blocking GUI startup.
        """
        import httpx

        self.model_name = model_name or self.DEFAULT_MODEL
        self.logger = get_app_logger("embedder")
        self._use_task_prefix = self.model_name.split(":")[0] in {"nomic-embed-text"}

        self.base_url = sanitize_ollama_base_url(
            os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        )

        self._validate_host()

        # Managed-network proxy bypass for localhost Ollama connections.
        # proxy=None: do not configure an explicit proxy.
        # trust_env=False: ignore HTTP_PROXY / HTTPS_PROXY env vars
        #   entirely. proxy=None alone is NOT enough -- httpx still
        #   reads proxy env vars when trust_env=True (the default).
        #   On managed-network machines, HTTP_PROXY can cause
        #   httpx to route 127.0.0.1 traffic through the proxy, which
        #   returns HTTP 301 Moved Permanently instead of reaching Ollama.
        # follow_redirects=False: fail-fast if a proxy does intercept.
        self._client = httpx.Client(
            timeout=httpx.Timeout(120),
            follow_redirects=False,
            proxy=None,
            trust_env=False,
        )

        if dimension > 0:
            self.dimension = dimension
            self.logger.info(
                "embedder_ready",
                model=self.model_name,
                dimension=dimension,
                base_url=self.base_url,
                note="dimension from config (no probe)",
            )
        else:
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

        WHY: Managed-network proxies can intercept localhost requests and return
        a 301/302 pointing to a remote proxy IP (e.g. 10.x.x.x). If we
        followed the redirect, embedding text would be sent off-machine.
        This was observed on work networks where "localhost" DNS resolved
        through a managed-network interceptor.
        """
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("location", "(unknown)")
            raise OllamaNotRunningError(
                f"Ollama at {self.base_url} returned redirect "
                f"{resp.status_code} -> {location}. "
                f"A managed-network proxy may be intercepting localhost traffic. "
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

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """
        Embed documents with the correct task prefix for asymmetric models.

        For nomic-embed-text, prepends 'search_document: ' to each text.
        For other models, behaves identically to embed_batch().
        Call this from the indexer; call embed_query() for search.
        """
        if self._use_task_prefix:
            texts = ["search_document: " + t for t in texts]
        return self.embed_batch(texts)

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

        For nomic-embed-text, prepends 'search_query: ' for asymmetric
        retrieval. Must pair with embed_documents() at index time.

        Parameters
        ----------
        text : str
            The user's question.

        Returns
        -------
        np.ndarray
            Shape (dimension,), dtype float32.
        """
        query_text = str(text or "")
        if self._use_task_prefix:
            query_text = "search_query: " + query_text
        vec = self.embed_batch([query_text])
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
        """Plain-English: Starts a managed resource block and returns the ready-to-use object."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Plain-English: Closes or cleans up resources when a managed block ends."""
        self.close()
        return False
