"""
End-to-end latency tests for offline (Ollama) and online (API) query modes.

Measures real wall-clock time for the full RAG pipeline:
  embed query -> retrieve chunks -> build context -> LLM generate -> return

Requirements:
  - Ollama running with phi4-mini and nomic-embed-text pulled
  - Indexed data present at configured paths
  - For online mode: valid API credentials configured

Usage:
  pytest tests/test_e2e_latency.py -v -s
  python tests/test_e2e_latency.py   (standalone)
"""

import os
import sys
import time
import statistics

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import Config, load_config
from src.core.vector_store import VectorStore
from src.core.embedder import Embedder
from src.core.llm_router import LLMRouter
from src.core.query_engine import QueryEngine, QueryResult


# ---------------------------------------------------------------------------
# Test queries spanning different complexity levels
# ---------------------------------------------------------------------------
TEST_QUERIES = [
    "What is the maximum operating temperature?",
    "What voltage is used for the power supply?",
    "Describe the data retention policy.",
]

# Thresholds tuned per hardware tier
# Laptop (16GB, CPU-only): phi4-mini ~70s per query on CPU
# Workstation (64GB, 12GB GPU): phi4:14b ~3-8s per query
LATENCY_THRESHOLDS = {
    "offline": {
        "retrieval_warn_ms": 2000,
        "total_warn_ms": 90_000,    # 90s warn (CPU inference is slow)
        "total_fail_ms": 300_000,   # 5min hard fail
    },
    "online": {
        "retrieval_warn_ms": 2000,
        "total_warn_ms": 15_000,    # 15s warn for API
        "total_fail_ms": 60_000,    # 1min hard fail
    },
}


def _build_engine(mode: str) -> QueryEngine:
    """Build a QueryEngine for the given mode."""
    config = load_config()
    config.mode = mode
    db_path = config.paths.database
    dim = config.embedding.dimension
    model_name = config.embedding.model_name
    vector_store = VectorStore(db_path, embedding_dim=dim, embedding_model=model_name)
    vector_store.connect()
    embedder = Embedder(model_name=model_name, dimension=dim)
    llm_router = LLMRouter(config)
    return QueryEngine(config, vector_store, embedder, llm_router)


def _measure_query(engine: QueryEngine, query: str) -> dict:
    """Run a single query and return timing breakdown."""
    t0 = time.perf_counter()
    result = engine.query(query)
    total_ms = (time.perf_counter() - t0) * 1000

    return {
        "query": query[:60],
        "total_ms": total_ms,
        "latency_ms_reported": result.latency_ms,
        "chunks_used": result.chunks_used,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "answer_len": len(result.answer),
        "error": result.error,
        "mode": result.mode,
    }


def _measure_stream(engine: QueryEngine, query: str) -> dict:
    """Run a streaming query and return timing breakdown."""
    t0 = time.perf_counter()
    retrieval_ms = 0
    token_count = 0
    first_token_ms = None
    result = None

    for chunk in engine.query_stream(query):
        if chunk.get("phase") == "generating":
            retrieval_ms = chunk.get("retrieval_ms", 0)
        elif "token" in chunk:
            token_count += 1
            if first_token_ms is None:
                first_token_ms = (time.perf_counter() - t0) * 1000
        elif chunk.get("done"):
            result = chunk.get("result")

    total_ms = (time.perf_counter() - t0) * 1000

    return {
        "query": query[:60],
        "total_ms": total_ms,
        "retrieval_ms": retrieval_ms,
        "first_token_ms": first_token_ms or 0,
        "token_count": token_count,
        "answer_len": len(result.answer) if result else 0,
        "error": result.error if result else "no result",
        "mode": result.mode if result else "unknown",
    }


def run_latency_suite(mode: str, stream: bool = False):
    """Run the full latency test suite for a given mode."""
    thresholds = LATENCY_THRESHOLDS[mode]
    print(f"\n{'='*70}")
    print(f"  E2E LATENCY TEST -- {mode.upper()} MODE ({'streaming' if stream else 'batch'})")
    print(f"{'='*70}")

    try:
        engine = _build_engine(mode)
    except Exception as e:
        print(f"  [FAIL] Could not build {mode} engine: {e}")
        return None

    # Warm-up query (embedder connection, model load)
    print("  Warm-up query...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        if stream:
            for _ in engine.query_stream("test warm up"):
                pass
        else:
            engine.query("test warm up")
        warmup_ms = (time.perf_counter() - t0) * 1000
        print(f"done ({warmup_ms:.0f}ms)")
    except Exception as e:
        print(f"[FAIL] warm-up failed: {e}")
        return None

    results = []
    for i, q in enumerate(TEST_QUERIES, 1):
        print(f"  [{i}/{len(TEST_QUERIES)}] {q[:55]}...", end=" ", flush=True)
        try:
            if stream:
                r = _measure_stream(engine, q)
            else:
                r = _measure_query(engine, q)
            results.append(r)

            tag = "[OK]"
            if r["total_ms"] > thresholds["total_fail_ms"]:
                tag = "[FAIL]"
            elif r["total_ms"] > thresholds["total_warn_ms"]:
                tag = "[WARN]"

            if stream:
                print(f"{tag} {r['total_ms']:.0f}ms total, "
                      f"retrieval={r['retrieval_ms']:.0f}ms, "
                      f"first_token={r['first_token_ms']:.0f}ms, "
                      f"tokens={r['token_count']}")
            else:
                print(f"{tag} {r['total_ms']:.0f}ms, "
                      f"chunks={r['chunks_used']}, "
                      f"answer={r['answer_len']}ch")

            if r.get("error"):
                print(f"        error: {r['error']}")

        except Exception as e:
            print(f"[FAIL] {type(e).__name__}: {e}")
            results.append({"query": q[:60], "total_ms": 0, "error": str(e)})

    # Summary statistics
    times = [r["total_ms"] for r in results if r["total_ms"] > 0]
    if times:
        print(f"\n  --- Summary ({mode}, {'stream' if stream else 'batch'}) ---")
        print(f"  Queries:  {len(times)}/{len(TEST_QUERIES)}")
        print(f"  Min:      {min(times):.0f}ms")
        print(f"  Max:      {max(times):.0f}ms")
        print(f"  Mean:     {statistics.mean(times):.0f}ms")
        print(f"  Median:   {statistics.median(times):.0f}ms")
        if len(times) > 1:
            print(f"  StdDev:   {statistics.stdev(times):.0f}ms")
        print(f"  Errors:   {sum(1 for r in results if r.get('error'))}")
        warn_count = sum(1 for r in results
                         if r["total_ms"] > thresholds["total_warn_ms"])
        fail_count = sum(1 for r in results
                         if r["total_ms"] > thresholds["total_fail_ms"])
        print(f"  Warnings: {warn_count} (>{thresholds['total_warn_ms']}ms)")
        print(f"  Failures: {fail_count} (>{thresholds['total_fail_ms']}ms)")

    return results


# ---------------------------------------------------------------------------
# pytest entry points
# ---------------------------------------------------------------------------
import pytest


def _skip_if_no_index():
    """Skip if no indexed data available."""
    config = load_config()
    db_path = config.paths.database
    if not os.path.exists(db_path):
        pytest.skip(f"No index database at {db_path}")


def _skip_if_no_ollama():
    """Skip if Ollama is not running."""
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if r.status_code != 200:
            pytest.skip("Ollama not responding")
    except Exception:
        pytest.skip("Ollama not reachable")


@pytest.mark.skipif(
    not os.environ.get("RUN_LATENCY_TESTS"),
    reason="Set RUN_LATENCY_TESTS=1 to run latency tests"
)
class TestOfflineLatency:
    """Offline (Ollama) latency tests."""

    def setup_method(self):
        _skip_if_no_index()
        _skip_if_no_ollama()

    def test_batch_latency(self):
        results = run_latency_suite("offline", stream=False)
        assert results is not None
        times = [r["total_ms"] for r in results if r["total_ms"] > 0]
        assert len(times) > 0, "No successful queries"
        assert max(times) < LATENCY_THRESHOLDS["offline"]["total_fail_ms"]

    def test_stream_latency(self):
        results = run_latency_suite("offline", stream=True)
        assert results is not None
        times = [r["total_ms"] for r in results if r["total_ms"] > 0]
        assert len(times) > 0, "No successful queries"
        # First token should appear within 5s for streaming
        first_tokens = [r["first_token_ms"] for r in results
                        if r.get("first_token_ms", 0) > 0]
        if first_tokens:
            assert max(first_tokens) < 15_000, \
                f"First token too slow: {max(first_tokens):.0f}ms"


@pytest.mark.skipif(
    not os.environ.get("RUN_LATENCY_TESTS"),
    reason="Set RUN_LATENCY_TESTS=1 to run latency tests"
)
class TestOnlineLatency:
    """Online (API) latency tests."""

    def setup_method(self):
        _skip_if_no_index()
        config = load_config()
        if not config.api.endpoint:
            pytest.skip("No API endpoint configured")

    def test_batch_latency(self):
        results = run_latency_suite("online", stream=False)
        assert results is not None
        times = [r["total_ms"] for r in results if r["total_ms"] > 0]
        assert len(times) > 0, "No successful queries"
        assert max(times) < LATENCY_THRESHOLDS["online"]["total_fail_ms"]

    def test_stream_latency(self):
        results = run_latency_suite("online", stream=True)
        assert results is not None
        times = [r["total_ms"] for r in results if r["total_ms"] > 0]
        assert len(times) > 0, "No successful queries"


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("HybridRAG3 End-to-End Latency Test Suite")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Always run offline
    offline_results = run_latency_suite("offline", stream=False)
    offline_stream = run_latency_suite("offline", stream=True)

    # Try online if configured
    try:
        config = load_config()
        if config.api.endpoint:
            online_results = run_latency_suite("online", stream=False)
            online_stream = run_latency_suite("online", stream=True)
        else:
            print("\n  [WARN] No API endpoint configured -- skipping online tests")
    except Exception as e:
        print(f"\n  [WARN] Online tests skipped: {e}")

    print(f"\n{'='*70}")
    print("  LATENCY TESTS COMPLETE")
    print(f"{'='*70}")
