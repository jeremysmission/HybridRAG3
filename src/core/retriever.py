# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the retriever part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Retriever (src/core/retriever.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   This is the "search engine" of HybridRAG. When a user types a question,
#   the Retriever finds the most relevant chunks from the indexed documents.
#
#   It supports three search strategies:
#     1. Vector search    -- finds chunks whose *meaning* is similar to the query
#     2. Keyword search   -- finds chunks that contain the query's *exact words*
#     3. Hybrid search    -- combines both using Reciprocal Rank Fusion (RRF)
#
#   Hybrid is the default and usually best: vector catches paraphrases and
#   synonyms, while keyword catches exact terms like part numbers or acronyms
#   that vector search might miss.
#
# KEY DESIGN DECISIONS:
#
#   1. Reciprocal Rank Fusion (RRF) for hybrid search
#      WHY: We have two ranked lists (vector hits and keyword hits) that use
#      completely different scoring scales. Vector scores are cosine similarity
#      (0.0-1.0), keyword scores are BM25 weights (unbounded). RRF sidesteps
#      this by only using *rank position*, not raw scores. A chunk ranked #1
#      in both lists gets a higher combined score than one ranked #1 in only
#      one list. This is the same algorithm used by Elasticsearch and other
#      production search engines.
#
#   2. Weighted combination scoring (0.4 vector + 0.6 RRF)
#      WHY: RRF scores are tiny fractions (e.g., 0.016 for a top result).
#      We normalize RRF by its theoretical maximum (2/(k+1) for k=60)
#      to map it into [0.0, 1.0], then blend with cosine similarity via
#      a weighted sum. This properly combines both retrieval signals
#      instead of discarding one via max(). RRF gets 0.6 weight because
#      it already incorporates the vector ranking; vector gets 0.4 to
#      let high cosine similarity boost borderline results.
#
#   3. Optional cross-encoder reranker
#      WHY: The initial retrieval (vector or hybrid) is fast but approximate.
#      A cross-encoder reads the full query + chunk text together and produces
#      a much more accurate relevance score, but it's ~100x slower. So we
#      use it as a second pass: retrieve 20 candidates fast, then rerank
#      to find the best 5. Disabled by default (needs extra model download).
#
#   4. Lexical boost for vector-only mode
#      WHY: When hybrid mode is off, pure vector search sometimes ranks a
#      chunk high even though none of the query's actual words appear in it.
#      The lexical boost adds a small score bonus (+0.02 per matching word,
#      capped at lex_boost) if query terms appear in the first 250 characters
#      of the chunk. This is a lightweight fallback -- hybrid mode with FTS5
#      is the better solution and makes this unnecessary.
#
#   ALTERNATIVES CONSIDERED:
#   - Linear score combination (0.7*vector + 0.3*keyword): requires careful
#     weight tuning per dataset. RRF is parameter-free and robust.
#   - BM25 from scratch: SQLite FTS5 already implements BM25 natively.
#   - Always-on reranker: too slow for interactive use on CPU laptops.
#     We keep it opt-in for batch/evaluation workflows.
# ============================================================================

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from .access_tags import normalize_access_tags
from .request_access import get_request_access_context
from .vector_store import VectorStore
from .embedder import Embedder
from .query_trace import build_retrieval_trace, hit_to_debug_dict
from .source_quality import ensure_source_quality_map

logger = logging.getLogger(__name__)

_reranker_available_cache: bool | None = None
_reranker_available_ts: float = 0.0
_RERANKER_CHECK_TTL = 30.0  # seconds between Ollama probes
_reranker_lock = threading.Lock()


def is_reranker_available(config) -> bool:
    """Check if the Ollama reranker backend is reachable (cached 30s)."""
    global _reranker_available_cache, _reranker_available_ts
    with _reranker_lock:
        now = time.monotonic()
        if _reranker_available_cache is not None and (now - _reranker_available_ts) < _RERANKER_CHECK_TTL:
            return _reranker_available_cache

        import httpx as _httpx
        ollama_cfg = getattr(config, "ollama", None)
        base_url = getattr(ollama_cfg, "base_url", "http://127.0.0.1:11434") if ollama_cfg else "http://127.0.0.1:11434"
        try:
            with _httpx.Client(timeout=3, proxy=None, trust_env=False) as client:
                resp = client.get(base_url, timeout=3)
                available = resp.status_code == 200
        except Exception:
            available = False

        _reranker_available_cache = available
        _reranker_available_ts = now
        return available


def _retriever_resolve_settings(config) -> dict:
    """Read the active retrieval settings from the current config object.

    The Config object is flat -- mode-specific retrieval values are merged
    into ``config.retrieval`` at load time by ``build_runtime_config_dict``,
    or at mode-switch time by ``apply_mode_to_config`` /
    ``apply_mode_settings_to_config``.  This function simply reads whatever
    is on the live Config.
    """
    retrieval = getattr(config, "retrieval", None)

    settings = {
        "top_k": int(getattr(retrieval, "top_k", 8) or 8) if retrieval else 8,
        "block_rows": int(getattr(retrieval, "block_rows", 25000) or 25000) if retrieval else 25000,
        "min_score": float(getattr(retrieval, "min_score", 0.20) or 0.20) if retrieval else 0.20,
        "lex_boost": float(getattr(retrieval, "lex_boost", 0.06) or 0.06) if retrieval else 0.06,
        "offline_top_k": None,
        "hybrid_search": bool(
            getattr(retrieval, "hybrid_search", getattr(retrieval, "hybrid", True))
        ) if retrieval else True,
        "rrf_k": int(getattr(retrieval, "rrf_k", 60) or 60) if retrieval else 60,
        "reranker_enabled": bool(
            getattr(retrieval, "reranker_enabled", getattr(retrieval, "reranker", False))
        ) if retrieval else False,
        "reranker_top_n": int(getattr(retrieval, "reranker_top_n", 20) or 20) if retrieval else 20,
    }

    if retrieval is not None:
        offline_top = getattr(retrieval, "offline_top_k", None)
        if offline_top is not None:
            try:
                settings["offline_top_k"] = max(1, int(offline_top))
            except (TypeError, ValueError):
                settings["offline_top_k"] = None

    env_block = os.getenv("HYBRIDRAG_RETRIEVAL_BLOCK_ROWS")
    if env_block:
        settings["block_rows"] = int(env_block)
    env_min = os.getenv("HYBRIDRAG_MIN_SCORE")
    if env_min:
        settings["min_score"] = float(env_min)

    return settings


class _EmbeddingCache:
    """Thread-safe LRU cache for query embeddings (maxsize entries)."""

    def __init__(self, maxsize: int = 64):
        """Plain-English: Sets up the _EmbeddingCache object and prepares state used by its methods."""
        self._maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        """Return cached embedding or None."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, value):
        """Store embedding, evicting oldest if full."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._maxsize:
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def clear(self) -> None:
        """Drop all cached query embeddings."""
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# Data class: one search result
# ---------------------------------------------------------------------------

@dataclass
class SearchHit:
    """
    One search result returned by the Retriever.

    Fields:
      score       -- relevance score (0.0 to 1.0, higher = more relevant)
      source_path -- full file path of the original document
      chunk_index -- which chunk within that document (0-based)
      text        -- the actual text content of the chunk
    """
    score: float
    source_path: str
    chunk_index: int
    text: str
    access_tags: tuple[str, ...] = ()
    access_tag_source: str = ""


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class Retriever:
    """
    Searches the vector store for chunks relevant to a user's query.

    Designed for:
    - Sub-200ms search on a laptop with 10,000+ chunks
    - Hybrid search combining semantic + keyword matching
    - Tunable via config (top_k, min_score, hybrid on/off, etc.)
    - Optional cross-encoder reranking for higher precision
    """

    def __init__(self, vector_store, embedder, config):
        """
        Parameters
        ----------
        vector_store : VectorStore
            The storage backend containing chunks and embeddings.

        embedder : Embedder
            Converts query text into an embedding vector.

        config : Config
            Master configuration. Retrieval settings come from config.retrieval.
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.config = config

        # Lazy-loaded reranker model (only loaded when first needed)
        self._reranker = None

        # Query embedding cache -- repeat queries skip the embedding step
        self._embed_cache = _EmbeddingCache(maxsize=64)
        self.last_search_trace = None
        self.refresh_settings(warn=True)

    def refresh_settings(self, warn: bool = False):
        """Refresh live retrieval settings from the current config object.

        QueryPanel, mode switching, and profile changes all mutate config at
        runtime. Without this refresh, Retriever keeps stale offline values
        and online mode can continue searching with the weaker old budget.
        """
        settings = _retriever_resolve_settings(self.config)
        self.top_k = settings["top_k"]
        self.block_rows = settings["block_rows"]
        self.min_score = settings["min_score"]
        self.lex_boost = settings["lex_boost"]
        self.offline_top_k = settings["offline_top_k"]
        self.hybrid_search = settings["hybrid_search"]
        self.rrf_k = settings["rrf_k"]
        self.reranker_enabled = settings["reranker_enabled"]
        self.reranker_top_n = settings["reranker_top_n"]

        if self.reranker_enabled:
            # Lazy-load on first enable -- _load_reranker checks Ollama health
            if self._reranker is None:
                self._reranker = self._load_reranker()
            if self._reranker is None:
                logger.warning(
                    "[WARN] reranker_enabled but Ollama reranker unavailable. "
                    "Running without reranker."
                )
                self.reranker_enabled = False

    def clear_runtime_state(self, warn: bool = False):
        """Purge query-time caches so a mode/profile switch starts clean."""
        self._embed_cache.clear()
        self.last_search_trace = None
        self.refresh_settings(warn=warn)

        if warn:
            _warn_aggressive_settings(self.top_k, self.reranker_top_n)

    # ------------------------------------------------------------------
    # Public API -- this is what query_engine.py calls
    # ------------------------------------------------------------------

    def search(self, query, classification=None):
        """
        Search for chunks relevant to the query.

        Pipeline:
          1. Choose search strategy (hybrid or vector-only)
          2. Retrieve candidates (more than top_k if reranker is on)
          3. Conditionally rerank with cross-encoder
          4. Filter by min_score
          5. Trim to top_k results

        classification: optional ClassificationResult from QueryClassifier.
            When provided, enables conditional reranking -- the reranker
            only fires for ANSWERABLE/UNKNOWN queries where initial
            retrieval scores are in the uncertain middle range.

        Returns a list of SearchHit objects, sorted by score descending.
        """
        self.refresh_settings()
        self.last_search_trace = None

        # Conditional reranker: config is the master switch, classification
        # gates by query type, retrieval scores gate by confidence.
        use_reranker = self.reranker_enabled
        reranker_skip_reason = None
        if use_reranker and classification is not None:
            if not classification.should_rerank:
                use_reranker = False
                reranker_skip_reason = "query_type=%s" % classification.query_type.name

        # If reranker is on, we fetch more candidates so it has a bigger
        # pool to rerank from. Otherwise, just fetch top_k directly.
        candidate_k = self.reranker_top_n if use_reranker else self.top_k
        structured_query = _is_structured_lookup_query(query)
        fts_query = query
        min_score = self.min_score
        if structured_query:
            # Parts/BOM/serial queries are usually table-heavy and spread
            # across neighboring chunks, so pull a wider candidate set.
            candidate_k = max(candidate_k, min(self.top_k * 4, 48))
            fts_query = self._expand_structured_fts_query(query)
            min_score = max(0.05, self.min_score * 0.5)

        # --- Step 1: Retrieve candidates ---
        search_started = time.perf_counter()
        if self.hybrid_search:
            hits = self._hybrid_search(query, candidate_k, fts_query=fts_query)
        else:
            hits = self._vector_search(query, candidate_k)
        search_ms = (time.perf_counter() - search_started) * 1000
        raw_hits = list(hits)

        # --- Step 2: Conditional reranking ---
        # Gate 2: Retrieval confidence -- skip reranking if results are
        # already high-confidence (median > 0.65) or too low to salvage
        # (max < 0.15). The "uncertain middle" is where reranking helps.
        rerank_ms = 0.0
        if use_reranker and len(hits) > 1:
            scores = sorted([h.score for h in hits], reverse=True)
            median_score = scores[len(scores) // 2]
            if scores[0] < 0.15:
                use_reranker = False
                reranker_skip_reason = "max_score=%.3f (too low)" % scores[0]
            elif median_score > 0.65:
                use_reranker = False
                reranker_skip_reason = "median=%.3f (confident)" % median_score
        if reranker_skip_reason:
            logger.info("[OK] reranker skipped: %s", reranker_skip_reason)
        if use_reranker and len(hits) > 0:
            rerank_started = time.perf_counter()
            hits = self._rerank(query, hits)
            rerank_ms = (time.perf_counter() - rerank_started) * 1000
        hits = _apply_source_quality_bias(self, hits)
        post_rerank_hits = list(hits)

        # --- Step 3: Filter by minimum score ---
        filtered_hits = [h for h in hits if h.score >= min_score]
        dropped_hits = [
            hit_to_debug_dict(hit, idx + 1, stage="post_filter", reason="below_min_score")
            for idx, hit in enumerate(hits)
            if hit.score < min_score
        ]
        authorized_hits, denied_hits, access_control = _apply_document_access_control(filtered_hits)

        if structured_query:
            hits = self._augment_with_adjacent_chunks(authorized_hits)
        else:
            hits = list(authorized_hits)
        post_augment_hits = list(hits)

        # --- Step 4: Trim to final top_k ---
        final_k = self.top_k
        mode = getattr(self.config, "mode", "offline")
        if mode == "offline" and self.offline_top_k is not None:
            final_k = min(final_k, self.offline_top_k)
        hits = hits[:final_k]
        final_hits = list(hits)

        if len(post_augment_hits) > final_k:
            for idx, hit in enumerate(post_augment_hits[final_k:], start=final_k + 1):
                dropped_hits.append(
                    hit_to_debug_dict(
                        hit,
                        idx,
                        stage="final",
                        reason="final_top_k_trim",
                    )
                )

        expected_source_root = str(
            getattr(getattr(self.config, "paths", None), "source_folder", "") or ""
        )
        self.last_search_trace = build_retrieval_trace(
            self,
            query=query,
            raw_hits=raw_hits,
            post_rerank_hits=post_rerank_hits,
            post_filter_hits=filtered_hits,
            post_augment_hits=post_augment_hits,
            final_hits=final_hits,
            dropped_hits=dropped_hits,
            denied_hits=denied_hits,
            structured_query=structured_query,
            fts_query=fts_query,
            candidate_k=candidate_k,
            min_score_applied=min_score,
            timings_ms={
                "search": search_ms,
                "rerank": rerank_ms,
            },
            expected_source_root=expected_source_root,
            access_control=access_control,
        )

        return hits

    # ------------------------------------------------------------------
    # Hybrid search (vector + keyword via RRF)
    # ------------------------------------------------------------------

    def _embed_query_cached(self, query):
        """Embed a query string, using the LRU cache when possible."""
        cached = self._embed_cache.get(query)
        if cached is not None:
            return cached
        q_vec = self.embedder.embed_query(query)
        self._embed_cache.put(query, q_vec)
        return q_vec

    def _hybrid_search(self, query, candidate_k, fts_query=None):
        """
        Run both vector search and keyword search, then merge results
        using Reciprocal Rank Fusion (RRF).

        This is the default and recommended search mode.
        """
        # Vector search: embed the query, find similar embeddings
        q_vec = self._embed_query_cached(query)
        vector_hits = self.vector_store.search(q_vec, top_k=candidate_k, block_rows=self.block_rows)

        # Source-path pre-filter: if the query references a specific document
        # by name, scope FTS5 to only that document's chunks at the SQL level.
        # This replaces post-retrieval prompt-level filtering with faster,
        # more precise SQL-level filtering.
        source_path_filter = None
        path_hits = []
        if hasattr(self.vector_store, "source_path_search"):
            path_hits = self.vector_store.source_path_search(query, top_k=candidate_k)
            source_path_filter = _extract_strong_path_matches(path_hits)

        # Keyword search: use SQLite FTS5 full-text index.
        # When source_path_filter is set, FTS5 only searches within the
        # referenced documents (scoped retrieval at SQL level).
        fts_hits = self.vector_store.fts_search(
            fts_query if fts_query is not None else query,
            top_k=candidate_k,
            source_path_filter=source_path_filter,
        )

        # Append remaining path hits not already in FTS results.
        # These enter RRF as weak keyword signals (purely additive).
        if path_hits:
            fts_keys = {(h["source_path"], h["chunk_index"]) for h in fts_hits}
            for hit in path_hits:
                key = (hit["source_path"], hit["chunk_index"])
                if key not in fts_keys:
                    fts_hits.append(hit)

        # Merge the two ranked lists using RRF
        return self._reciprocal_rank_fusion(vector_hits, fts_hits)

    def _reciprocal_rank_fusion(self, vector_hits, fts_hits):
        """
        Merge two ranked lists into one using Reciprocal Rank Fusion.

        HOW RRF WORKS (plain English):
          Each result gets a score based on its rank position:
            rrf_score = 1 / (k + rank + 1)

          where k=60 (smoothing constant) and rank starts at 0.

          So the #1 result gets 1/61 = 0.0164, #2 gets 1/62 = 0.0161, etc.

          If a chunk appears in BOTH lists, its RRF scores are added together.
          This means a chunk ranked well in both vector AND keyword search
          will float to the top, even if it wasn't #1 in either list alone.

        WHY THIS WORKS:
          Vector search finds "digisonde ionospheric measurements" when you
          ask about "ionogram data collection". Keyword search finds chunks
          containing the exact word "ionogram". RRF combines both signals
          so you get the best of both worlds.
        """
        # Dictionary to accumulate RRF scores. Key = (source_path, chunk_index)
        combined = {}

        # Score each vector hit by its rank position
        for rank, hit in enumerate(vector_hits):
            key = (hit["source_path"], hit["chunk_index"])
            rrf_score = 1.0 / (self.rrf_k + rank + 1)
            if key not in combined:
                combined[key] = {
                    "rrf_score": 0.0,
                    "vector_score": hit.get("score", 0.0),
                    "source_path": hit["source_path"],
                    "chunk_index": hit["chunk_index"],
                    "text": hit["text"],
                    "access_tags": normalize_access_tags(hit.get("access_tags", ())),
                    "access_tag_source": str(hit.get("access_tag_source", "") or ""),
                }
            combined[key]["rrf_score"] += rrf_score

        # Score each keyword hit by its rank position.
        # If the same chunk was already added from vector hits, its
        # RRF score increases (that's the whole point of fusion).
        for rank, hit in enumerate(fts_hits):
            key = (hit["source_path"], hit["chunk_index"])
            rrf_score = 1.0 / (self.rrf_k + rank + 1)
            if key not in combined:
                combined[key] = {
                    "rrf_score": 0.0,
                    "vector_score": hit.get("score", 0.0),
                    "source_path": hit["source_path"],
                    "chunk_index": hit["chunk_index"],
                    "text": hit["text"],
                    "access_tags": normalize_access_tags(hit.get("access_tags", ())),
                    "access_tag_source": str(hit.get("access_tag_source", "") or ""),
                }
            elif not combined[key].get("access_tags"):
                combined[key]["access_tags"] = normalize_access_tags(hit.get("access_tags", ()))
                combined[key]["access_tag_source"] = str(hit.get("access_tag_source", "") or "")
            combined[key]["rrf_score"] += rrf_score

        # Sort by combined RRF score (highest first)
        sorted_results = sorted(combined.values(), key=lambda x: x["rrf_score"], reverse=True)

        # Convert to SearchHit objects with a display-friendly score
        #
        # Scoring strategy: weighted combination of vector cosine similarity
        # and normalized RRF rank score. This properly blends both signals
        # instead of discarding one via max().
        #
        # RRF normalization: the theoretical maximum RRF score is
        # 2 / (rrf_k + 1) -- a chunk ranked #1 in BOTH lists.
        # Dividing by this ceiling maps RRF into [0.0, 1.0].
        #
        # Weights: 0.4 vector + 0.6 RRF. RRF gets higher weight because
        # it already incorporates the vector signal (vector rank feeds
        # into RRF). Giving vector 0.4 still lets high cosine similarity
        # boost borderline results.
        max_rrf = 2.0 / (self.rrf_k + 1)  # theoretical ceiling
        hits = []
        for item in sorted_results:
            rrf_normalized = min(item["rrf_score"] / max_rrf, 1.0)
            display_score = (
                0.4 * item["vector_score"]
                + 0.6 * rrf_normalized
            )
            hits.append(SearchHit(
                score=min(display_score, 1.0),
                source_path=item["source_path"],
                chunk_index=item["chunk_index"],
                text=item["text"],
                access_tags=tuple(item.get("access_tags", ()) or ()),
                access_tag_source=str(item.get("access_tag_source", "") or ""),
            ))
        return hits

    # ------------------------------------------------------------------
    # Vector-only search (fallback when hybrid is disabled)
    # ------------------------------------------------------------------

    def _vector_search(self, query, candidate_k):
        """
        Pure vector (semantic) search with optional lexical boost.

        Used when hybrid_search is set to False in config. Less accurate
        than hybrid for queries containing specific terms or part numbers,
        but simpler and faster.
        """
        # Embed the query into a 768-dimensional vector
        q_vec = self._embed_query_cached(query)

        # Find the closest chunk embeddings by cosine similarity
        raw_hits = self.vector_store.search(q_vec, top_k=candidate_k, block_rows=self.block_rows)

        # Extract query terms for the optional lexical boost
        q_terms = _query_terms(query)

        # Convert raw dict results to SearchHit objects, applying boost
        hits = []
        for h in raw_hits:
            base = float(h.get("score", 0.0))
            text = str(h.get("text", "") or "")
            # Add a small bonus if query words appear in the chunk's opening text
            boosted = min(base + self._lexical_boost(text, q_terms), 1.0)
            hits.append(SearchHit(
                score=boosted,
                source_path=str(h.get("source_path", "")),
                chunk_index=int(h.get("chunk_index", 0)),
                text=text,
                access_tags=normalize_access_tags(h.get("access_tags", ())),
                access_tag_source=str(h.get("access_tag_source", "") or ""),
            ))
        hits.sort(key=lambda x: x.score, reverse=True)
        return hits

    # ------------------------------------------------------------------
    # Cross-encoder reranking (optional second pass)
    # ------------------------------------------------------------------

    def _rerank(self, query, hits):
        """
        Re-score hits using a cross-encoder model for higher accuracy.

        A cross-encoder reads the query and chunk text TOGETHER (not
        separately like the bi-encoder used for initial retrieval).
        This produces much more accurate relevance scores but is ~100x
        slower, so we only run it on the top N candidates.

        The raw cross-encoder output is a logit (can be any number).
        We convert it to a 0-1 probability using the sigmoid function:
          sigmoid(x) = 1 / (1 + e^(-x))
        """
        # Lazy-load the reranker model on first use
        if self._reranker is None:
            self._reranker = self._load_reranker()
        if self._reranker is None:
            return hits  # Reranker unavailable, return original order

        # Build (query, chunk_text) pairs for the cross-encoder
        pairs = [(query, hit.text) for hit in hits]
        try:
            # Get raw logit scores from the cross-encoder
            scores = self._reranker.predict(pairs)
            # Convert logits to 0-1 probabilities using sigmoid
            # (2.718281828 is Euler's number "e")
            for hit, score in zip(hits, scores):
                hit.score = 1.0 / (1.0 + pow(2.718281828, -float(score)))
            # Re-sort by the new scores
            hits.sort(key=lambda x: x.score, reverse=True)
        except Exception as e:
            logger.error("Reranker error: %s", e)
        return hits

    def _load_reranker(self):
        """Load the Ollama-based reranker (replaces retired sentence-transformers)."""
        from .ollama_reranker import load_ollama_reranker
        reranker = load_ollama_reranker(self.config)
        if reranker is None:
            logger.warning(
                "Reranker requested but Ollama unavailable; "
                "running without reranker."
            )
        return reranker

    # ------------------------------------------------------------------
    # Context building -- format hits for the LLM prompt
    # ------------------------------------------------------------------

    def build_context(self, hits):
        """
        Format search hits into a text block that gets inserted into
        the LLM prompt as the "retrieved context".

        Each hit is labeled with its source, chunk number, and score
        so the LLM (and the user) can trace answers back to sources.
        """
        blocks = []
        for i, h in enumerate(hits, start=1):
            blocks.append(
                f"[Source {i}] {h.source_path} "
                f"(chunk {h.chunk_index}, score={h.score:.3f})\n{h.text}"
            )
        return "\n\n---\n\n".join(blocks)

    def get_sources(self, hits):
        """
        Summarize which files contributed to the search results.

        Returns a list of dicts with:
          path          -- file path
          chunks        -- how many chunks came from this file
          avg_relevance -- average score of those chunks
          access_tags   -- normalized access tags carried by that source
          access_tag_source -- rule/default source that produced the tags

        Useful for showing "Sources used" in the UI.
        """
        if not hits:
            return []
        # Group hits by file path
        by_path = {}
        for h in hits:
            entry = by_path.setdefault(
                h.source_path,
                {
                    "scores": [],
                    "access_tags": [],
                    "access_tag_sources": [],
                },
            )
            entry["scores"].append(h.score)
            for tag in normalize_access_tags(
                getattr(h, "access_tags", ()) or ()
            ) or ("shared",):
                if tag not in entry["access_tags"]:
                    entry["access_tags"].append(tag)
            source = str(getattr(h, "access_tag_source", "") or "").strip()
            if source and source not in entry["access_tag_sources"]:
                entry["access_tag_sources"].append(source)
        # Build summary for each file
        out = []
        for path, info in by_path.items():
            scores = info["scores"]
            source_value = "|".join(info["access_tag_sources"]) or "default_document_tags"
            out.append({
                "path": path,
                "chunks": len(scores),
                "avg_relevance": sum(scores) / max(1, len(scores)),
                "access_tags": list(info["access_tags"] or ["shared"]),
                "access_tag_source": source_value,
            })
        return out

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _expand_structured_fts_query(self, query):
        """
        Expand FTS terms for parts/serial queries.

        Keeps behavior deterministic: no model inference, just explicit terms.
        """
        base_terms = _query_terms(query)
        extra_terms = [
            "part", "parts", "number", "numbers", "serial", "list",
            "table", "item", "items", "bom", "materials", "assembly",
            "component", "components", "spare", "replacement",
        ]
        seen = set()
        ordered = []
        for term in base_terms + extra_terms:
            t = term.lower().strip()
            if len(t) >= 3 and t not in seen:
                ordered.append(t)
                seen.add(t)
        return " ".join(ordered)

    def _augment_with_adjacent_chunks(self, hits):
        """
        Add neighboring chunks for top hits to recover split tables.
        """
        if not hits:
            return hits
        conn = getattr(self.vector_store, "conn", None)
        lock = getattr(self.vector_store, "_db_lock", None)
        if conn is None or lock is None:
            return hits

        by_key = {(h.source_path, h.chunk_index): h for h in hits}
        seeds = hits[: min(len(hits), 6)]
        try:
            with lock:
                for seed in seeds:
                    lo = max(0, int(seed.chunk_index) - 1)
                    hi = int(seed.chunk_index) + 1
                    rows = conn.execute(
                        "SELECT source_path, chunk_index, text, access_tags, access_tag_source "
                        "FROM chunks WHERE source_path = ? "
                        "AND chunk_index BETWEEN ? AND ? "
                        "ORDER BY chunk_index",
                        (seed.source_path, lo, hi),
                    ).fetchall()
                    for source_path, chunk_index, text, access_tags, access_tag_source in rows:
                        key = (str(source_path), int(chunk_index))
                        if key in by_key:
                            continue
                        score = max(0.0, float(seed.score) - 0.03)
                        by_key[key] = SearchHit(
                            score=score,
                            source_path=str(source_path),
                            chunk_index=int(chunk_index),
                            text=str(text or ""),
                            access_tags=normalize_access_tags(access_tags),
                            access_tag_source=str(access_tag_source or ""),
                        )
        except Exception as e:
            logger.warning("[WARN] Adjacent chunk augmentation failed: %s", e)
            return hits

        out = list(by_key.values())
        out.sort(key=lambda h: h.score, reverse=True)
        return out

    def _lexical_boost(self, chunk_text, q_terms):
        """
        Small score bonus when query terms appear in the chunk's opening text.

        Only used in vector-only mode (hybrid mode uses FTS5 instead).

        Checks the first 250 characters of the chunk (typically the heading
        or first sentence). Each matching term adds +0.02 to the score,
        capped at self.lex_boost (default 0.06).

        WHY ONLY 250 CHARS:
          A term appearing in the heading/first sentence is much more likely
          to indicate the chunk is *about* that topic, vs. a passing mention
          buried in paragraph 5.
        """
        if not chunk_text or not q_terms:
            return 0.0
        head = chunk_text[:250].lower()
        matches = sum(1 for t in q_terms if t in head)
        if matches == 0:
            return 0.0
        return min(self.lex_boost, 0.02 * matches)


# -------------------------------------------------------------------
# Extracted helpers (keep Retriever class under 500 lines)
# -------------------------------------------------------------------

def _warn_aggressive_settings(top_k, reranker_top_n):
    """Log warnings when retrieval settings may cause high latency."""
    if top_k > 10:
        logger.warning(
            "[WARN] top_k=%d exceeds 10. Each extra chunk adds ~1-3s "
            "of LLM inference on 12GB GPUs. Reduce top_k or upgrade GPU.",
            top_k,
        )
    if reranker_top_n > 30:
        logger.warning(
            "[WARN] reranker_top_n=%d exceeds 30. Only server-class "
            "hardware (24GB+ VRAM, 64GB+ RAM) should use values above 30.",
            reranker_top_n,
        )


def _apply_source_quality_bias(retriever: Retriever, hits: List[SearchHit]) -> List[SearchHit]:
    """Down-rank suspect sources without deleting archive content."""
    if not hits:
        return hits

    conn = getattr(getattr(retriever, "vector_store", None), "conn", None)
    if conn is None:
        return hits

    source_samples: Dict[str, str] = {}
    for hit in hits:
        key = str(getattr(hit, "source_path", "") or "").strip()
        if key not in source_samples:
            source_samples[key] = str(getattr(hit, "text", "") or "")[:8000]

    try:
        quality_map = ensure_source_quality_map(conn, source_samples)
    except Exception:
        return hits

    adjusted_hits: List[SearchHit] = []
    for hit in hits:
        key = str(getattr(hit, "source_path", "") or "").strip()
        adjusted_hits.append(
            SearchHit(
                score=_apply_source_quality_score(hit.score, quality_map.get(key)),
                source_path=hit.source_path,
                chunk_index=hit.chunk_index,
                text=hit.text,
                access_tags=tuple(getattr(hit, "access_tags", ()) or ()),
                access_tag_source=str(getattr(hit, "access_tag_source", "") or ""),
            )
        )

    adjusted_hits.sort(key=lambda item: item.score, reverse=True)
    return adjusted_hits


def _apply_document_access_control(
    hits: List[SearchHit],
) -> tuple[List[SearchHit], list[dict[str, Any]], dict[str, Any]]:
    """Filter hits against the active per-request access context."""
    access_context = get_request_access_context()
    if not access_context:
        return list(hits), [], {
            "enabled": False,
            "actor": "",
            "actor_source": "",
            "actor_role": "",
            "allowed_doc_tags": [],
            "document_policy_source": "",
            "authorized_hits": len(hits),
            "denied_hits": 0,
        }

    actor = str(access_context.get("actor", "") or "")
    actor_source = str(access_context.get("actor_source", "") or "")
    actor_role = str(access_context.get("actor_role", "") or "")
    allowed_doc_tags = normalize_access_tags(access_context.get("allowed_doc_tags", ()))
    document_policy_source = str(
        access_context.get("document_policy_source", "") or ""
    )
    if not allowed_doc_tags or "*" in allowed_doc_tags:
        return list(hits), [], {
            "enabled": True,
            "actor": actor,
            "actor_source": actor_source,
            "actor_role": actor_role,
            "allowed_doc_tags": list(allowed_doc_tags or ("*",)),
            "document_policy_source": document_policy_source,
            "authorized_hits": len(hits),
            "denied_hits": 0,
        }

    allowed_set = set(allowed_doc_tags)
    authorized_hits: List[SearchHit] = []
    denied_hits: list[dict[str, Any]] = []

    for rank, hit in enumerate(hits, start=1):
        required_tags = normalize_access_tags(getattr(hit, "access_tags", ())) or ("shared",)
        if "*" in required_tags or set(required_tags).issubset(allowed_set):
            authorized_hits.append(hit)
            continue
        missing_tags = [tag for tag in required_tags if tag not in allowed_set]
        denied_hits.append(
            hit_to_debug_dict(
                hit,
                rank,
                stage="access_control",
                reason="access_denied_missing_tags:" + ",".join(missing_tags),
            )
        )

    return authorized_hits, denied_hits, {
        "enabled": True,
        "actor": actor,
        "actor_source": actor_source,
        "actor_role": actor_role,
        "allowed_doc_tags": list(allowed_doc_tags),
        "document_policy_source": document_policy_source,
        "authorized_hits": len(authorized_hits),
        "denied_hits": len(denied_hits),
    }


def _apply_source_quality_score(base_score: float, record: Optional[Dict[str, Any]]) -> float:
    """Apply a light serving bias toward cleaner, citation-ready sources."""
    if not record:
        return float(base_score)

    penalty = 0.0
    tier = str(record.get("retrieval_tier", "serve") or "serve")
    if tier == "suspect":
        penalty += 0.35
    elif tier == "archive":
        penalty += 0.12

    if int(record.get("is_saved_resource", 0) or 0):
        penalty += 0.25
    if int(record.get("has_missing_path", 0) or 0):
        penalty += 0.20
    if int(record.get("has_encoded_blob", 0) or 0):
        penalty += 0.20
    if int(record.get("is_boilerplate", 0) or 0):
        penalty += 0.10

    # Downrank known junk sources hard so real documents outrank them
    flags_str = str(record.get("flags_json", "[]") or "[]")
    if "test_or_demo_artifact" in flags_str:
        penalty += 0.30
    if "golden_seed_file" in flags_str:
        penalty += 0.30
    if "temp_or_pipeline_doc" in flags_str:
        penalty += 0.25
    if "zip_bundle" in flags_str:
        penalty += 0.20

    bonus = 0.0
    if tier == "serve" and float(record.get("quality_score", 0.0) or 0.0) >= 0.90:
        bonus = 0.03

    return max(0.0, float(base_score) - penalty + bonus)


def _query_terms(query):
    """Extract searchable terms from the query.

    Splits on non-alphanumeric characters, lowercases everything,
    and drops very short words (under 3 chars).
    """
    terms = re.findall(r"[A-Za-z0-9]+", (query or "").lower())
    return [t for t in terms if len(t) >= 3]


def _extract_strong_path_matches(path_hits):
    """Extract unique source paths with strong document-name coverage.

    source_path_search scores are: min(0.5, 0.05 + 0.45 * coverage).
    A score >= 0.35 means ~67% of query terms match the filename, which
    is a strong signal the query references that specific document.

    Returns a list of path strings for SQL-level FTS scoping, or None
    if no strong matches were found. Limited to 3 paths to prevent
    over-scoping when many documents weakly match.
    """
    if not path_hits:
        return None
    strong = sorted(
        {h["source_path"] for h in path_hits if h.get("score", 0) >= 0.35},
    )
    if not strong or len(strong) > 3:
        return None
    return strong


def _is_structured_lookup_query(query):
    """Detect list/spec queries that are commonly answered from tables."""
    q = (query or "").lower()
    patterns = [
        r"\bpart(?:s)?\b",
        r"\bpart\s*(?:#|number|no\.?|numbers)\b",
        r"\bserial(?:\s*(?:#|number|no\.?))?\b",
        r"\bbom\b",
        r"\bbill of materials\b",
        r"\bbreakdown\b",
        r"\blist\b.*\bparts?\b",
    ]
    return any(re.search(p, q) for p in patterns)
