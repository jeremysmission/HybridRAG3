# ============================================================================
# HybridRAG -- Semantic Query Cache (src/core/query_cache.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Caches query results keyed by embedding similarity so that the same
#   (or a semantically near-identical) question answered once can be
#   returned instantly on subsequent asks without re-running the full
#   retrieval + LLM pipeline.
#
# WHY A SEMANTIC CACHE (not an exact-string cache):
#   Users rarely ask the exact same question twice, but they DO ask
#   very similar questions:
#     "What is the max operating temp?"
#     "What's the maximum operating temperature?"
#   A string-based cache misses these. A semantic cache embeds each
#   query into a 768-dim vector and compares cosine similarity. If
#   the new query's embedding is >= the threshold (default 0.95) to
#   a cached entry, we return the cached result -- zero retrieval,
#   zero LLM cost, sub-millisecond latency.
#
# DUAL-PURPOSE CACHING:
#   1. Demo-time fast loading -- pre-warm with common questions so
#      live demos never show the 5-180 second cold-query delay.
#   2. Update isolation -- cached responses block outbound probes,
#      supporting the zero-trust offline architecture.
#
# DESIGN DECISIONS:
#   - Pure in-memory (no SQLite): eliminates I/O latency. The cache
#     is ephemeral -- it dies with the process. This is intentional:
#     stale cached answers are worse than no cache at all.
#   - LRU eviction by last-access time (not insertion time): hot
#     queries stay cached, cold ones get evicted first.
#   - Thread-safe via threading.Lock: the GUI runs queries from
#     background threads, so concurrent get/put must be safe.
#   - Disabled during eval runs: the eval harness tests the full
#     pipeline, not the cache. A cache hit during eval would mask
#     regressions. Toggle via cache.enabled = False.
#
# PERFORMANCE:
#   Similarity search is O(N) where N = cache size (max 500 default).
#   With 768-dim normalized vectors, numpy dot product over 500 entries
#   takes < 0.1ms on any modern CPU. This is not a bottleneck.
#
# INTERNET ACCESS: NONE
#   This module does no network I/O. Embeddings are computed by the
#   caller (Embedder) before being passed here.
# ============================================================================

from __future__ import annotations

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import numpy as np

from ..monitoring.logger import get_app_logger


# -------------------------------------------------------------------
# CacheEntry: one cached query + result
# -------------------------------------------------------------------

@dataclass
class CacheEntry:
    """
    A single cached query-result pair.

    query_text:
        The original query string (for debugging / stats display).

    query_embedding:
        The L2-normalized 768-dim embedding vector. Used for cosine
        similarity comparison against incoming queries.

    result:
        The QueryResult-compatible dict returned to the caller.
        Stored as a plain dict (not a dataclass) so the cache has
        no import dependency on query_engine.py.

    timestamp:
        Unix epoch when this entry was created (for TTL expiry).

    last_accessed:
        Unix epoch when this entry was last returned as a cache hit.
        Used for LRU eviction (oldest last_accessed gets evicted first).

    hit_count:
        Number of times this entry has been returned as a cache hit.
        Useful for understanding query patterns and cache effectiveness.
    """
    query_text: str
    query_embedding: np.ndarray
    result: dict
    timestamp: float
    last_accessed: float
    hit_count: int = 0


# -------------------------------------------------------------------
# QueryCache: semantic similarity cache
# -------------------------------------------------------------------

class QueryCache:
    """
    In-memory semantic similarity cache for RAG query results.

    Stores query results keyed by embedding vectors. On lookup, computes
    cosine similarity between the incoming query embedding and all cached
    embeddings. If any cached entry exceeds the similarity threshold and
    has not expired (TTL), the cached result is returned instantly.

    Thread-safe: all public methods acquire self._lock before mutating
    or reading shared state.

    Usage:
        cache = QueryCache(max_entries=500, ttl_seconds=3600, similarity_threshold=0.95)
        embedding = embedder.embed_query("What is the max temp?")

        # Check cache first
        cached = cache.get("What is the max temp?", embedding)
        if cached is not None:
            return cached  # instant, no LLM call

        # Cache miss -- run full pipeline
        result = query_engine.query(...)
        cache.put("What is the max temp?", embedding, result_as_dict)
    """

    def __init__(
        self,
        max_entries: int = 500,
        ttl_seconds: int = 3600,
        similarity_threshold: float = 0.95,
    ):
        """
        Initialize the semantic query cache.

        Parameters
        ----------
        max_entries : int
            Maximum number of cached entries. When full, the least
            recently accessed entry is evicted to make room.

        ttl_seconds : int
            Time-to-live in seconds. Entries older than this are
            considered expired and will not be returned as cache hits.
            They are lazily evicted on the next get() or put() call.

        similarity_threshold : float
            Minimum cosine similarity (0.0 to 1.0) between a new query
            embedding and a cached embedding for a cache hit. Higher
            values require closer semantic matches. Default 0.95 is
            conservative -- only near-identical questions match.
        """
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._similarity_threshold = similarity_threshold

        # The cache store: maps a string key to a CacheEntry.
        # The key is an internal identifier (based on insertion order).
        self._entries: Dict[str, CacheEntry] = {}

        # Monotonic counter for generating unique cache keys.
        self._counter: int = 0

        # Stats counters
        self._hits: int = 0
        self._misses: int = 0

        # Toggle to disable cache (e.g., during eval runs)
        self._enabled: bool = True

        # Thread safety
        self._lock = threading.Lock()

        # Logger
        self._logger = get_app_logger("query_cache")

    # -------------------------------------------------------------------
    # Public properties
    # -------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Whether the cache is active. When False, get() always returns None."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def max_entries(self) -> int:
        """Maximum number of entries the cache can hold."""
        return self._max_entries

    @property
    def ttl_seconds(self) -> int:
        """Time-to-live for cache entries, in seconds."""
        return self._ttl_seconds

    @property
    def similarity_threshold(self) -> float:
        """Minimum cosine similarity for a cache hit."""
        return self._similarity_threshold

    # -------------------------------------------------------------------
    # Core methods
    # -------------------------------------------------------------------

    def get(self, query_text: str, query_embedding: np.ndarray) -> Optional[dict]:
        """
        Look up a cached result by semantic similarity.

        Computes cosine similarity between query_embedding and every
        cached embedding. If any non-expired entry has similarity >=
        the threshold, returns that entry's result dict and updates
        its last_accessed time and hit_count.

        Parameters
        ----------
        query_text : str
            The user's query string (used for logging only).

        query_embedding : np.ndarray
            The L2-normalized embedding vector for the query.
            Shape: (dimension,), dtype: float32.

        Returns
        -------
        dict or None
            The cached result dict if a hit is found, else None.
        """
        if not self._enabled:
            self._misses += 1
            return None

        with self._lock:
            now = time.time()

            # Fast path: nothing cached
            if not self._entries:
                self._misses += 1
                self._logger.debug(
                    "cache_miss", query=query_text[:80], reason="empty_cache"
                )
                return None

            # Collect all non-expired entries and their embeddings
            valid_keys = []
            valid_embeddings = []

            for key, entry in list(self._entries.items()):
                age = now - entry.timestamp
                if age > self._ttl_seconds:
                    # Lazily evict expired entries
                    del self._entries[key]
                    continue
                valid_keys.append(key)
                valid_embeddings.append(entry.query_embedding)

            if not valid_keys:
                self._misses += 1
                self._logger.debug(
                    "cache_miss", query=query_text[:80], reason="all_expired"
                )
                return None

            # Vectorized cosine similarity via dot product.
            # Embeddings are L2-normalized, so dot product = cosine similarity.
            cache_matrix = np.stack(valid_embeddings, axis=0)  # (N, dim)
            similarities = cache_matrix @ query_embedding       # (N,)

            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            if best_sim >= self._similarity_threshold:
                best_key = valid_keys[best_idx]
                entry = self._entries[best_key]
                entry.hit_count += 1
                entry.last_accessed = now
                self._hits += 1
                self._logger.info(
                    "cache_hit",
                    tag="[OK]",
                    query=query_text[:80],
                    cached_query=entry.query_text[:80],
                    similarity=round(best_sim, 4),
                    hit_count=entry.hit_count,
                )
                return entry.result

            self._misses += 1
            self._logger.debug(
                "cache_miss",
                query=query_text[:80],
                best_similarity=round(best_sim, 4),
                threshold=self._similarity_threshold,
            )
            return None

    def put(
        self,
        query_text: str,
        query_embedding: np.ndarray,
        result: dict,
    ) -> None:
        """
        Store a query result in the cache.

        If the cache is at max_entries, the least recently accessed
        entry is evicted first (LRU policy).

        Parameters
        ----------
        query_text : str
            The user's query string.

        query_embedding : np.ndarray
            The L2-normalized embedding vector for the query.

        result : dict
            The QueryResult-compatible dict to cache.
        """
        if not self._enabled:
            return

        with self._lock:
            now = time.time()

            # Evict expired entries first (housekeeping)
            self._evict_expired(now)

            # If still at capacity, evict LRU entry
            while len(self._entries) >= self._max_entries:
                self._evict_lru()

            # Create new entry
            self._counter += 1
            cache_key = f"q_{self._counter}"

            self._entries[cache_key] = CacheEntry(
                query_text=query_text,
                query_embedding=np.array(query_embedding, dtype=np.float32),
                result=result,
                timestamp=now,
                last_accessed=now,
                hit_count=0,
            )

            self._logger.info(
                "cache_put",
                tag="[OK]",
                query=query_text[:80],
                cache_size=len(self._entries),
            )

    def invalidate(self) -> int:
        """
        Clear all cached entries.

        Returns
        -------
        int
            Number of entries that were cleared.
        """
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._logger.info(
                "cache_invalidated",
                tag="[OK]",
                entries_cleared=count,
            )
            return count

    def stats(self) -> dict:
        """
        Return cache statistics.

        Returns
        -------
        dict
            Keys: size, max_entries, hits, misses, hit_rate,
                  oldest_entry_age, ttl_seconds, similarity_threshold,
                  enabled.
        """
        with self._lock:
            now = time.time()
            total_requests = self._hits + self._misses

            oldest_age = 0.0
            if self._entries:
                oldest_ts = min(e.timestamp for e in self._entries.values())
                oldest_age = now - oldest_ts

            return {
                "size": len(self._entries),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (
                    self._hits / total_requests if total_requests > 0 else 0.0
                ),
                "oldest_entry_age": round(oldest_age, 2),
                "ttl_seconds": self._ttl_seconds,
                "similarity_threshold": self._similarity_threshold,
                "enabled": self._enabled,
            }

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _evict_expired(self, now: float) -> int:
        """
        Remove all entries older than TTL.

        Called internally during put() to reclaim space before adding
        a new entry. Does NOT acquire the lock (caller must hold it).

        Returns the number of entries evicted.
        """
        expired_keys = [
            key
            for key, entry in self._entries.items()
            if (now - entry.timestamp) > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._entries[key]
        return len(expired_keys)

    def _evict_lru(self) -> None:
        """
        Remove the least recently accessed entry.

        Called internally during put() when the cache is at capacity.
        Does NOT acquire the lock (caller must hold it).
        """
        if not self._entries:
            return

        lru_key = min(
            self._entries,
            key=lambda k: self._entries[k].last_accessed,
        )
        evicted = self._entries.pop(lru_key)
        self._logger.debug(
            "cache_evict_lru",
            evicted_query=evicted.query_text[:80],
            age=round(time.time() - evicted.timestamp, 1),
        )
