# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the limiting embedder part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
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
    """Plain-English: This class groups logic for limitingembedder."""
    _inner: Any
    _limiter: RuntimeLimiter

    def embed_query(self, text: str):
        """Plain-English: This function handles embed query."""
        with self._limiter.embedding_slot():
            return self._inner.embed_query(text)

    def embed_batch(self, texts: List[str]):
        """Plain-English: This function handles embed batch."""
        with self._limiter.embedding_slot():
            return self._inner.embed_batch(texts)

    def __getattr__(self, name: str):
        """Plain-English: This function handles getattr."""
        return getattr(self._inner, name)
