# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the query cache area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Tests for the QueryCache semantic similarity cache (20 tests)
# WHY:  The cache is the fast path for repeated queries. A broken cache
#       either returns stale/wrong results (correctness bug) or fails
#       to return cached results (performance regression). These tests
#       verify every code path: hits, misses, TTL, LRU eviction, thread
#       safety, and the enable/disable toggle.
# HOW:  Uses random L2-normalized 768-dim numpy arrays to simulate real
#       embeddings without needing Ollama running. No I/O, no network.
# USAGE: pytest tests/test_query_cache.py -v
# ===================================================================

import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
np = pytest.importorskip("numpy")

# -- sys.path setup --
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.query_cache import QueryCache, CacheEntry


# ============================================================================
# HELPERS
# ============================================================================

def _random_embedding(dim: int = 768, seed: int = None) -> np.ndarray:
    """
    Generate a random L2-normalized embedding vector.

    Uses a fixed seed when provided so tests are deterministic.
    Returns shape (dim,), dtype float32 -- same format as Embedder.embed_query().
    """
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


def _similar_embedding(base: np.ndarray, noise_scale: float = 0.01, seed: int = 42) -> np.ndarray:
    """
    Create an embedding very similar to `base` by adding small noise.

    The resulting vector is re-normalized to unit length.
    With noise_scale=0.01, cosine similarity to base is typically > 0.999.
    """
    rng = np.random.RandomState(seed)
    noise = rng.randn(*base.shape).astype(np.float32) * noise_scale
    perturbed = base + noise
    perturbed /= np.linalg.norm(perturbed)
    return perturbed


def _different_embedding(base: np.ndarray, seed: int = 999) -> np.ndarray:
    """
    Create an embedding that is dissimilar to `base`.

    Uses a completely different random seed, producing a vector
    with low cosine similarity to base (typically < 0.1 in 768-dim).
    """
    return _random_embedding(dim=base.shape[0], seed=seed)


def _make_result(answer: str = "Test answer") -> dict:
    """Create a minimal QueryResult-compatible dict."""
    return {
        "answer": answer,
        "sources": [{"path": "test.pdf", "chunks": 3, "avg_relevance": 0.85}],
        "chunks_used": 3,
        "tokens_in": 150,
        "tokens_out": 80,
        "cost_usd": 0.001,
        "latency_ms": 1200.0,
        "mode": "offline",
    }


def _make_cache(**kwargs) -> QueryCache:
    """Create a QueryCache with test-friendly defaults."""
    defaults = {
        "max_entries": 500,
        "ttl_seconds": 3600,
        "similarity_threshold": 0.95,
    }
    defaults.update(kwargs)
    return QueryCache(**defaults)


# ============================================================================
# TEST 1: Exact same query returns cached result
# ============================================================================

def test_exact_cache_hit():
    """Passing the same embedding should return the cached result."""
    cache = _make_cache()
    emb = _random_embedding(seed=1)
    result = _make_result("exact match answer")

    cache.put("What is the max temp?", emb, result)
    cached = cache.get("What is the max temp?", emb)

    assert cached is not None
    assert cached["answer"] == "exact match answer"


# ============================================================================
# TEST 2: Similar query returns cached result (cosine > threshold)
# ============================================================================

def test_similar_query_cache_hit():
    """A slightly different embedding above threshold should hit."""
    cache = _make_cache(similarity_threshold=0.95)
    base_emb = _random_embedding(seed=10)
    similar_emb = _similar_embedding(base_emb, noise_scale=0.01)

    # Verify our test vectors are actually similar enough
    sim = float(np.dot(base_emb, similar_emb))
    assert sim > 0.95, f"Test setup error: similarity {sim} too low"

    result = _make_result("similar match answer")
    cache.put("maximum operating temperature", base_emb, result)

    cached = cache.get("max operating temp", similar_emb)
    assert cached is not None
    assert cached["answer"] == "similar match answer"


# ============================================================================
# TEST 3: Different query returns cache miss
# ============================================================================

def test_different_query_cache_miss():
    """A completely different embedding should not match."""
    cache = _make_cache()
    base_emb = _random_embedding(seed=20)
    diff_emb = _different_embedding(base_emb, seed=21)

    result = _make_result("should not match")
    cache.put("What is the max temp?", base_emb, result)

    cached = cache.get("How do I install the software?", diff_emb)
    assert cached is None


# ============================================================================
# TEST 4: TTL expiration
# ============================================================================

def test_ttl_expiration():
    """Entries older than ttl_seconds should not be returned."""
    cache = _make_cache(ttl_seconds=1)
    emb = _random_embedding(seed=30)
    result = _make_result("will expire")

    cache.put("test query", emb, result)

    # Immediate lookup should hit
    assert cache.get("test query", emb) is not None

    # Wait for TTL to expire
    time.sleep(1.1)

    # Should now be a miss
    assert cache.get("test query", emb) is None


# ============================================================================
# TEST 5: LRU eviction at max_entries
# ============================================================================

def test_lru_eviction():
    """When full, the least recently accessed entry should be evicted."""
    cache = _make_cache(max_entries=3)

    emb1 = _random_embedding(seed=40)
    emb2 = _random_embedding(seed=41)
    emb3 = _random_embedding(seed=42)
    emb4 = _random_embedding(seed=43)

    cache.put("query 1", emb1, _make_result("answer 1"))
    cache.put("query 2", emb2, _make_result("answer 2"))
    cache.put("query 3", emb3, _make_result("answer 3"))

    # Access query 1 to make it recently used
    cache.get("query 1", emb1)

    # Add query 4 -- should evict query 2 (LRU, not query 1 which was just accessed)
    cache.put("query 4", emb4, _make_result("answer 4"))

    # query 1 should still be cached (was recently accessed)
    assert cache.get("query 1", emb1) is not None
    # query 2 should be evicted (oldest last_accessed)
    assert cache.get("query 2", emb2) is None
    # query 3 should still be cached
    assert cache.get("query 3", emb3) is not None
    # query 4 should be cached
    assert cache.get("query 4", emb4) is not None


# ============================================================================
# TEST 6: Invalidate clears everything
# ============================================================================

def test_invalidate_clears_all():
    """invalidate() should remove all entries and return the count."""
    cache = _make_cache()
    for i in range(10):
        cache.put(f"query {i}", _random_embedding(seed=50 + i), _make_result())

    count = cache.invalidate()
    assert count == 10
    assert cache.stats()["size"] == 0


# ============================================================================
# TEST 7: Stats tracking -- hits, misses, hit_rate
# ============================================================================

def test_stats_tracking():
    """Stats should accurately reflect cache hit/miss counts."""
    cache = _make_cache()
    emb = _random_embedding(seed=60)

    cache.put("test", emb, _make_result())

    # 3 hits
    for _ in range(3):
        cache.get("test", emb)

    # 2 misses
    for i in range(2):
        cache.get("different", _random_embedding(seed=600 + i))

    stats = cache.stats()
    assert stats["hits"] == 3
    assert stats["misses"] == 2
    assert abs(stats["hit_rate"] - 0.6) < 0.001
    assert stats["size"] == 1
    assert stats["max_entries"] == 500


# ============================================================================
# TEST 8: Thread safety -- concurrent get/put
# ============================================================================

def test_thread_safety():
    """Concurrent get/put from multiple threads should not crash."""
    cache = _make_cache(max_entries=50)
    errors = []
    barrier = threading.Barrier(10)

    def worker(thread_id):
        try:
            barrier.wait(timeout=5)
            emb = _random_embedding(seed=70 + thread_id)
            result = _make_result(f"thread {thread_id}")

            # Mix of puts and gets
            cache.put(f"query {thread_id}", emb, result)
            cache.get(f"query {thread_id}", emb)
            cache.put(f"query {thread_id} v2", emb, result)
            cache.get(f"query {thread_id}", emb)
            cache.stats()
        except Exception as e:
            errors.append((thread_id, str(e)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Thread errors: {errors}"
    # Cache should have entries (exact count depends on timing)
    assert cache.stats()["size"] > 0


# ============================================================================
# TEST 9: Enabled toggle -- disabled cache always misses
# ============================================================================

def test_enabled_toggle():
    """When disabled, get() returns None and put() does nothing."""
    cache = _make_cache()
    emb = _random_embedding(seed=80)

    # Put while enabled
    cache.put("query", emb, _make_result("cached"))
    assert cache.get("query", emb) is not None

    # Disable
    cache.enabled = False
    assert cache.enabled is False
    assert cache.get("query", emb) is None

    # Put while disabled should not store
    emb2 = _random_embedding(seed=81)
    cache.put("query 2", emb2, _make_result("should not cache"))

    # Re-enable
    cache.enabled = True
    # query 2 should NOT be in cache (was put while disabled)
    assert cache.get("query 2", emb2) is None
    # query 1 should still be there
    assert cache.get("query", emb) is not None


# ============================================================================
# TEST 10: Real 768-dim vectors
# ============================================================================

def test_768_dim_vectors():
    """Verify correct operation with production-size 768-dim embeddings."""
    cache = _make_cache()
    dim = 768
    emb = _random_embedding(dim=dim, seed=90)

    assert emb.shape == (768,)
    assert emb.dtype == np.float32
    assert abs(np.linalg.norm(emb) - 1.0) < 1e-5

    result = _make_result("768-dim result")
    cache.put("768-dim query", emb, result)
    cached = cache.get("768-dim query", emb)

    assert cached is not None
    assert cached["answer"] == "768-dim result"


# ============================================================================
# TEST 11: Empty cache returns None
# ============================================================================

def test_empty_cache_miss():
    """A get() on an empty cache should return None."""
    cache = _make_cache()
    emb = _random_embedding(seed=100)
    assert cache.get("anything", emb) is None


# ============================================================================
# TEST 12: Hit count increments correctly
# ============================================================================

def test_hit_count_increments():
    """Each cache hit should increment the entry's hit_count."""
    cache = _make_cache()
    emb = _random_embedding(seed=110)
    cache.put("repeated query", emb, _make_result())

    for i in range(5):
        cache.get("repeated query", emb)

    # Access the internal entry to check hit_count
    entry = list(cache._entries.values())[0]
    assert entry.hit_count == 5


# ============================================================================
# TEST 13: Stats oldest_entry_age
# ============================================================================

def test_stats_oldest_entry_age():
    """oldest_entry_age should reflect actual age of oldest entry."""
    cache = _make_cache()
    emb = _random_embedding(seed=120)
    cache.put("old query", emb, _make_result())

    time.sleep(0.5)

    stats = cache.stats()
    assert stats["oldest_entry_age"] >= 0.4


# ============================================================================
# TEST 14: Similarity threshold boundary
# ============================================================================

def test_similarity_threshold_boundary():
    """Entries just below threshold should miss; just above should hit."""
    cache = _make_cache(similarity_threshold=0.99)
    base_emb = _random_embedding(seed=130)

    # Very similar (noise_scale=0.01) -- might be above or below 0.99
    # Use extremely small noise to guarantee > 0.99
    very_similar = _similar_embedding(base_emb, noise_scale=0.001, seed=131)
    sim_high = float(np.dot(base_emb, very_similar))
    assert sim_high > 0.99, f"Test setup: {sim_high} not > 0.99"

    # Moderately similar -- should be below 0.99
    moderate = _similar_embedding(base_emb, noise_scale=0.15, seed=132)
    sim_low = float(np.dot(base_emb, moderate))
    assert sim_low < 0.99, f"Test setup: {sim_low} not < 0.99"

    cache.put("base query", base_emb, _make_result("threshold test"))

    # Very similar should hit
    assert cache.get("very similar", very_similar) is not None
    # Moderately similar should miss
    assert cache.get("moderate", moderate) is None


# ============================================================================
# TEST 15: Multiple entries -- best match wins
# ============================================================================

def test_best_match_wins():
    """When multiple entries are cached, the most similar one wins."""
    cache = _make_cache(similarity_threshold=0.90)

    base = _random_embedding(seed=140)
    close = _similar_embedding(base, noise_scale=0.01, seed=141)
    farther = _similar_embedding(base, noise_scale=0.05, seed=142)
    unrelated = _random_embedding(seed=143)

    cache.put("close match", close, _make_result("close answer"))
    cache.put("farther match", farther, _make_result("farther answer"))
    cache.put("unrelated", unrelated, _make_result("unrelated answer"))

    cached = cache.get("query", base)
    assert cached is not None
    assert cached["answer"] == "close answer"


# ============================================================================
# TEST 16: Invalidate returns zero on empty cache
# ============================================================================

def test_invalidate_empty_cache():
    """invalidate() on empty cache should return 0."""
    cache = _make_cache()
    assert cache.invalidate() == 0


# ============================================================================
# TEST 17: LRU evicts oldest-accessed, not oldest-inserted
# ============================================================================

def test_lru_evicts_by_access_not_insertion():
    """Eviction should be based on last_accessed, not timestamp."""
    cache = _make_cache(max_entries=2)

    emb_old = _random_embedding(seed=170)
    emb_new = _random_embedding(seed=171)
    emb_newest = _random_embedding(seed=172)

    cache.put("old query", emb_old, _make_result("old"))
    time.sleep(0.05)
    cache.put("new query", emb_new, _make_result("new"))

    # Access old query to refresh its last_accessed
    cache.get("old query", emb_old)

    # Insert newest -- should evict "new query" (least recently accessed)
    cache.put("newest query", emb_newest, _make_result("newest"))

    # old query should survive (was accessed most recently)
    assert cache.get("old query", emb_old) is not None
    # new query should be evicted
    assert cache.get("new query", emb_new) is None


# ============================================================================
# TEST 18: Result dict is preserved exactly
# ============================================================================

def test_result_dict_preserved():
    """The cached result dict should be returned exactly as stored."""
    cache = _make_cache()
    emb = _random_embedding(seed=180)

    original_result = {
        "answer": "The maximum operating temperature is 85C.",
        "sources": [
            {"path": "thermal_spec.pdf", "chunks": 5, "avg_relevance": 0.92},
            {"path": "design_guide.pdf", "chunks": 2, "avg_relevance": 0.78},
        ],
        "chunks_used": 7,
        "tokens_in": 523,
        "tokens_out": 187,
        "cost_usd": 0.0023,
        "latency_ms": 3420.5,
        "mode": "online",
    }

    cache.put("thermal query", emb, original_result)
    cached = cache.get("thermal query", emb)

    assert cached == original_result
    assert cached["sources"][0]["path"] == "thermal_spec.pdf"
    assert cached["cost_usd"] == 0.0023


# ============================================================================
# TEST 19: Stats with zero requests
# ============================================================================

def test_stats_zero_requests():
    """Stats on a fresh cache should show zeroes and 0.0 hit_rate."""
    cache = _make_cache()
    stats = cache.stats()

    assert stats["size"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_rate"] == 0.0
    assert stats["oldest_entry_age"] == 0.0
    assert stats["enabled"] is True


# ============================================================================
# TEST 20: Concurrent invalidation during get/put
# ============================================================================

def test_concurrent_invalidation():
    """Calling invalidate() while other threads do get/put should not crash."""
    cache = _make_cache(max_entries=100)
    errors = []

    # Pre-populate
    for i in range(50):
        cache.put(f"q{i}", _random_embedding(seed=200 + i), _make_result())

    def getter(tid):
        try:
            for _ in range(20):
                emb = _random_embedding(seed=200 + (tid % 50))
                cache.get(f"q{tid % 50}", emb)
        except Exception as e:
            errors.append((tid, str(e)))

    def putter(tid):
        try:
            for j in range(20):
                emb = _random_embedding(seed=300 + tid * 100 + j)
                cache.put(f"new_{tid}_{j}", emb, _make_result())
        except Exception as e:
            errors.append((tid, str(e)))

    def invalidator():
        try:
            for _ in range(5):
                cache.invalidate()
                time.sleep(0.01)
        except Exception as e:
            errors.append((-1, str(e)))

    threads = (
        [threading.Thread(target=getter, args=(i,)) for i in range(5)]
        + [threading.Thread(target=putter, args=(i,)) for i in range(5)]
        + [threading.Thread(target=invalidator)]
    )

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"Concurrency errors: {errors}"
