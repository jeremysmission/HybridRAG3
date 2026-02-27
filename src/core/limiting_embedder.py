# ============================================================================
# HybridRAG v3 -- LimitingEmbedder (src/core/limiting_embedder.py)
# ============================================================================
# PURPOSE:
#   Enforce embedding concurrency limits without modifying the underlying
#   Embedder implementation. This prevents bypass of the guard in paths where
#   Indexer or other callers invoke embedder directly.
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from src.core.runtime_limits import RuntimeLimiter


@dataclass
class LimitingEmbedder:
    _inner: Any
    _limiter: RuntimeLimiter

    def embed_query(self, text: str):
        with self._limiter.embedding_slot():
            return self._inner.embed_query(text)

    def embed_batch(self, texts: List[str]):
        with self._limiter.embedding_slot():
            return self._inner.embed_batch(texts)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
