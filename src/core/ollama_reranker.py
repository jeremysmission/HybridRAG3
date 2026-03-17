# ============================================================================
# HybridRAG -- Ollama Reranker (src/core/ollama_reranker.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Replaces the retired sentence-transformers cross-encoder with a
#   lightweight LLM-based relevance scorer using the local Ollama server.
#
#   A cross-encoder reads query + document TOGETHER (not separately like
#   the bi-encoder used for initial retrieval). An LLM does the same thing
#   -- it reads both and judges relevance. The tradeoff is speed: LLM calls
#   are slower than a small cross-encoder, so we only rerank a small
#   candidate pool (default 10-20 items).
#
# HOW IT WORKS:
#   1. Takes a list of (query, document_text) pairs
#   2. Sends each pair to Ollama with a short relevance-scoring prompt
#   3. Extracts a 0-10 score from the LLM response
#   4. Returns scores centered around 0 (for sigmoid normalization)
#
# PERFORMANCE:
#   - CPU (toaster): ~2s per pair, 20 pairs = ~10s with 4 threads
#   - GPU (BEAST):   ~0.2s per pair, 20 pairs = ~1s with 4 threads
#   - Prompt is kept short (max 800 chars of doc) to minimize latency
#
# SAFETY:
#   - Reranker is opt-in (reranker_enabled=False by default)
#   - Never auto-enables during eval runs
#   - Falls back gracefully on Ollama errors (returns original order)
# ============================================================================

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from .network_gate import get_gate, NetworkBlockedError

logger = logging.getLogger(__name__)

# Short, directive prompt -- minimizes token count and latency.
# "ONLY a single number" prevents the LLM from explaining its reasoning.
_RERANK_PROMPT = (
    "Rate how relevant this passage is to the question. "
    "Reply with ONLY a single number from 0 to 10, nothing else.\n\n"
    "Question: {query}\n\n"
    "Passage: {doc}\n\n"
    "Relevance score:"
)

# Truncate documents to keep prompts short and latency low.
_MAX_DOC_CHARS = 800


class OllamaReranker:
    """Score (query, document) pairs using a local Ollama model.

    Interface matches the retired sentence-transformers cross-encoder:
    calling ``predict(pairs)`` returns a list of float scores that
    the retriever maps through sigmoid to get 0-1 probabilities.
    """

    def __init__(self, base_url, model, timeout=15, max_workers=4):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_workers = max_workers

    def predict(self, pairs):
        """Score a list of (query, doc_text) pairs.

        Returns a list of float scores centered around 0.0, matching
        the cross-encoder logit convention so the retriever's existing
        sigmoid normalization produces sensible 0-1 probabilities:

          LLM score 0  -> returns -5.0 -> sigmoid = 0.007
          LLM score 5  -> returns  0.0 -> sigmoid = 0.500
          LLM score 10 -> returns  5.0 -> sigmoid = 0.993
        """

        def _score_one(idx, query, doc):
            doc_preview = doc[:_MAX_DOC_CHARS]
            prompt = _RERANK_PROMPT.format(query=query, doc=doc_preview)
            try:
                get_gate().check_allowed(
                    f"{self.base_url}/api/generate",
                    "ollama_rerank", "reranker",
                )
            except NetworkBlockedError:
                return idx, -5.0

            try:
                with httpx.Client(
                    timeout=self.timeout, proxy=None, trust_env=False,
                ) as client:
                    resp = client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.0,
                                "num_predict": 8,
                            },
                        },
                    )
                    resp.raise_for_status()
                    text = resp.json().get("response", "0")
                    match = re.search(r"\d+\.?\d*", text.strip())
                    if match:
                        raw = min(float(match.group()), 10.0)
                        return idx, raw - 5.0
                    return idx, -5.0
            except Exception as e:
                logger.warning("Reranker scoring failed for pair %d: %s", idx, e)
                return idx, -5.0

        scores = [0.0] * len(pairs)
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [
                pool.submit(_score_one, i, q, d)
                for i, (q, d) in enumerate(pairs)
            ]
            for future in as_completed(futures):
                try:
                    idx, score = future.result()
                    scores[idx] = score
                except Exception:
                    pass
        return scores


def load_ollama_reranker(config):
    """Create an OllamaReranker from the live config, or None if unavailable.

    Checks that Ollama is reachable before returning a reranker instance.
    Returns None if the server is down (retriever falls back to no reranking).
    """
    ollama_cfg = getattr(config, "ollama", None)
    if ollama_cfg is None:
        logger.warning("No ollama config -- reranker unavailable")
        return None

    base_url = getattr(ollama_cfg, "base_url", "http://127.0.0.1:11434")
    # Prefer dedicated reranker_model from retrieval config; fall back to
    # the main Ollama model so the reranker works even if reranker_model
    # is not explicitly set.
    retrieval_cfg = getattr(config, "retrieval", None)
    reranker_model = getattr(retrieval_cfg, "reranker_model", None) if retrieval_cfg else None
    # Only use reranker_model if it's a real string (not a MagicMock or empty),
    # and not the retired sentence-transformers model name.
    if isinstance(reranker_model, str) and reranker_model and "cross-encoder" not in reranker_model:
        model = reranker_model
    else:
        model = getattr(ollama_cfg, "model", "phi4:14b-q4_K_M")

    # Quick health check -- don't create reranker if Ollama is down
    try:
        get_gate().check_allowed(base_url, "ollama_rerank_probe", "reranker")
        with httpx.Client(timeout=3, proxy=None, trust_env=False) as client:
            resp = client.get(base_url, timeout=3)
            if resp.status_code != 200:
                logger.warning("Ollama not healthy (status %d) -- reranker unavailable", resp.status_code)
                return None
    except (NetworkBlockedError, Exception) as e:
        logger.warning("Ollama unreachable -- reranker unavailable: %s", e)
        return None

    logger.info("[OK] Ollama reranker loaded (model=%s)", model)
    return OllamaReranker(base_url=base_url, model=model)
