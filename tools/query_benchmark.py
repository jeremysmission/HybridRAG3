#!/usr/bin/env python3
# ============================================================================
# HybridRAG v3 -- Query Mode Benchmark
# ============================================================================
# FILE: src/tools/query_benchmark.py
#
# WHAT THIS DOES (plain English):
#   Runs the same questions through both online (API) and offline (Phi4-Mini)
#   modes, times each phase (retrieval vs LLM response), and generates
#   a visual bar chart comparing the results.
#
# TEST SCENARIOS:
#   1. Online API  + RAG question (answer is in your indexed documents)
#   2. Online API  + General question (answer is NOT in your documents)
#   3. Offline LLM + RAG question (answer is in your indexed documents)
#   4. Offline LLM + General question (answer is NOT in your documents)
#
# HOW TO RUN:
#   rag-benchmark              (after sourcing start_hybridrag.ps1)
#   python src\tools\query_benchmark.py   (direct)
#
# OUTPUT:
#   - Console table with timing breakdown
#   - logs/query_benchmark_YYYY-MM-DD.html  (visual chart)
#   - logs/query_benchmark_YYYY-MM-DD.json  (raw data)
#
# INTERNET ACCESS:
#   - Online mode tests require API connectivity
#   - Offline mode tests require Ollama running locally
#   - Chart generation is 100% local (no external libraries)
#
# ============================================================================

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Test questions
# ============================================================================
# RAG_QUESTION: Something your indexed documents should answer well.
#   Your indexed data is EN.95.663.81.FA19 Technical Personnel Management,
#   covering leadership styles, succession planning, organizational behavior.
#
# GENERAL_QUESTION: Something NOT in your documents. The LLM must answer
#   from its training data (online API) or its local weights (Phi4-Mini).
#   This tests what happens when RAG retrieval returns low-relevance chunks.
# ============================================================================

RAG_QUESTION = "What leadership styles are discussed and how do they differ?"

GENERAL_QUESTION = (
    "What is the difference between frequency modulation "
    "and amplitude modulation in radio communications?"
)


def init_engine(mode):
    """
    Initialize the full query pipeline for a given mode.

    Returns (query_engine, config) or (None, error_string).

    WHY WE RE-INITIALIZE PER MODE:
      The LLMRouter caches the mode at creation time. Switching modes
      mid-run without re-creating the router can cause it to call the
      wrong backend. Re-init is the safe approach -- it adds ~2 seconds
      but guarantees correct routing.
    """
    try:
        from src.core.config import (
            load_config, validate_config, ensure_directories
        )
        from src.core.vector_store import VectorStore
        from src.core.embedder import Embedder
        from src.core.llm_router import LLMRouter
        from src.core.query_engine import QueryEngine

        config = load_config(str(PROJECT_ROOT))
        errors = validate_config(config)
        if errors:
            return None, f"Config errors: {errors}"
        ensure_directories(config)
        config.mode = mode

        vs = VectorStore(
            db_path=config.paths.database,
            embedding_dim=config.embedding.dimension
        )
        vs.connect()

        embedder = Embedder(config.embedding.model_name)

        api_key = os.getenv("OPENAI_API_KEY", "")
        llm = LLMRouter(config, api_key=api_key)

        qe = QueryEngine(config, vs, embedder, llm)
        return qe, config
    except Exception as e:
        return None, str(e)


def run_timed_query(engine, question, label):
    """
    Run a single query and capture timing breakdown.

    Returns a dict with all timing and result data.

    HOW TIMING WORKS:
      The QueryEngine.query() method records total latency_ms internally.
      We also wrap the call in our own timer to capture any overhead.
      The retrieval vs LLM split comes from the QueryResult fields.
    """
    print(f"    Running: {label}...", end="", flush=True)

    t0 = time.perf_counter()
    try:
        result = engine.query(question)
        total_ms = (time.perf_counter() - t0) * 1000

        data = {
            "label": label,
            "question": question,
            "mode": result.mode,
            "total_ms": round(total_ms, 1),
            "engine_ms": round(result.latency_ms, 1),
            "chunks_used": result.chunks_used,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "answer_preview": result.answer[:200] if result.answer else "",
            "error": result.error,
            "status": "OK",
        }
        print(f" {total_ms:.0f}ms")
        return data

    except Exception as e:
        total_ms = (time.perf_counter() - t0) * 1000
        print(f" ERROR: {e}")
        return {
            "label": label,
            "question": question,
            "mode": "?",
            "total_ms": round(total_ms, 1),
            "engine_ms": 0,
            "chunks_used": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0,
            "answer_preview": "",
            "error": str(e),
            "status": "FAIL",
        }


def print_results_table(results):
    """Print a formatted console table of benchmark results."""
    print()
    print("=" * 76)
    print("  QUERY BENCHMARK RESULTS")
    print("=" * 76)
    print()
    print(f"  {'Scenario':<40} {'Total':>8} {'Chunks':>7} {'Status':>8}")
    print(f"  {'-' * 40} {'-' * 8} {'-' * 7} {'-' * 8}")

    for r in results:
        label = r["label"][:40]
        total = f"{r['total_ms']:.0f}ms"
        chunks = str(r["chunks_used"])
        status = r["status"]
        print(f"  {label:<40} {total:>8} {chunks:>7} {status:>8}")

    print()

    # Answer previews
    print("  ANSWER PREVIEWS")
    print("  " + "-" * 74)
    for r in results:
        if r["status"] == "OK":
            preview = r["answer_preview"].replace("\n", " ")[:70]
            print(f"  {r['label'][:35]:<35}")
            print(f"    {preview}...")
            print()

    print("=" * 76)


def generate_chart_html(results, output_path):
    """
    Generate a self-contained HTML bar chart comparing query times.

    WHY HTML INSTEAD OF MATPLOTLIB:
      - Zero dependencies (no pip install needed)
      - Opens in any browser on any machine
      - Works on the air-gapped work laptop
      - Easy to share with manager in a demo
    """
    # Find max time for scaling bars
    max_ms = max(r["total_ms"] for r in results) if results else 1
    if max_ms < 1:
        max_ms = 1

    # Color coding by mode
    colors = {
        "online": "#4a90d9",   # Blue for API
        "offline": "#e07a3a",  # Orange for Ollama
    }

    bars_html = ""
    for r in results:
        bar_width = (r["total_ms"] / max_ms) * 100
        color = colors.get(r["mode"], "#888888")
        status_icon = "[OK]" if r["status"] == "OK" else "[FAIL]"
        label = r["label"]
        time_str = f"{r['total_ms']:.0f}ms"
        chunks_str = f"{r['chunks_used']} chunks"

        bars_html += f"""
        <div style="margin-bottom: 18px;">
          <div style="font-size: 14px; font-weight: bold; margin-bottom: 4px;
                      color: #222; font-family: Consolas, monospace;">
            {status_icon} {label}
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <div style="
              background: {color};
              width: {bar_width}%;
              min-width: 2px;
              height: 28px;
              border-radius: 4px;
              transition: width 0.3s;
            "></div>
            <span style="font-size: 14px; font-weight: bold; color: #333;
                         white-space: nowrap; font-family: Consolas, monospace;">
              {time_str}
            </span>
          </div>
          <div style="font-size: 12px; color: #666; margin-top: 2px;
                      font-family: Consolas, monospace;">
            {chunks_str} | tokens: {r['tokens_in']}in/{r['tokens_out']}out
            | cost: ${r['cost_usd']:.4f}
          </div>
        </div>
        """

    # Build answer comparison section
    answers_html = ""
    for r in results:
        if r["status"] == "OK" and r["answer_preview"]:
            color = colors.get(r["mode"], "#888888")
            preview = r["answer_preview"].replace("<", "&lt;").replace(">", "&gt;")
            answers_html += f"""
            <div style="margin-bottom: 16px; padding: 10px;
                        border-left: 4px solid {color};
                        background: #f8f9fa;">
              <div style="font-weight: bold; font-size: 13px;
                          color: #333; margin-bottom: 4px;
                          font-family: Consolas, monospace;">
                {r['label']}
              </div>
              <div style="font-size: 12px; color: #555;
                          font-family: Consolas, monospace;">
                {preview}...
              </div>
            </div>
            """

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>HybridRAG Query Benchmark</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      max-width: 800px;
      margin: 40px auto;
      padding: 0 20px;
      background: #fff;
      color: #333;
    }}
    h1 {{
      font-size: 22px;
      border-bottom: 2px solid #333;
      padding-bottom: 8px;
    }}
    h2 {{
      font-size: 16px;
      margin-top: 30px;
      color: #555;
    }}
    .legend {{
      display: flex;
      gap: 20px;
      margin: 12px 0 20px 0;
      font-size: 13px;
      font-family: Consolas, monospace;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .legend-dot {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
    }}
    .meta {{
      font-size: 12px;
      color: #888;
      margin-top: 30px;
      font-family: Consolas, monospace;
    }}
    .questions {{
      font-size: 12px;
      color: #666;
      margin: 10px 0 20px 0;
      padding: 10px;
      background: #f5f5f5;
      border-radius: 4px;
      font-family: Consolas, monospace;
    }}
  </style>
</head>
<body>
  <h1>HybridRAG Query Benchmark</h1>
  <div class="meta">{timestamp}</div>

  <div class="legend">
    <div class="legend-item">
      <div class="legend-dot" style="background: #4a90d9;"></div>
      Online (API)
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background: #e07a3a;"></div>
      Offline (Phi4-Mini)
    </div>
  </div>

  <div class="questions">
    <strong>RAG Question:</strong> {RAG_QUESTION}<br>
    <strong>General Question:</strong> {GENERAL_QUESTION}
  </div>

  <h2>Response Time (lower is better)</h2>
  {bars_html}

  <h2>Answer Previews</h2>
  {answers_html}

  <div class="meta">
    Generated by src/tools/query_benchmark.py<br>
    System: HybridRAG v3 | Database: ~{len(results)}  scenarios tested
  </div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    print()
    print("=" * 60)
    print("  HYBRIDRAG QUERY MODE BENCHMARK")
    print("=" * 60)
    print()
    print(f"  RAG question (local data):")
    print(f"    \"{RAG_QUESTION}\"")
    print()
    print(f"  General question (API/LLM knowledge):")
    print(f"    \"{GENERAL_QUESTION}\"")
    print()

    results = []

    # Ensure logs directory exists
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    # ================================================================
    # SCENARIO 1 & 2: Online (API) mode
    # ================================================================
    print("  --- ONLINE MODE (API) ---")
    engine, config_or_err = init_engine("online")
    if engine is None:
        print(f"    [SKIP] Cannot init online mode: {config_or_err}")
        results.append({
            "label": "Online + RAG Question", "question": RAG_QUESTION,
            "mode": "online", "total_ms": 0, "engine_ms": 0,
            "chunks_used": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0, "answer_preview": "", "error": config_or_err,
            "status": "SKIP",
        })
        results.append({
            "label": "Online + General Question",
            "question": GENERAL_QUESTION,
            "mode": "online", "total_ms": 0, "engine_ms": 0,
            "chunks_used": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0, "answer_preview": "", "error": config_or_err,
            "status": "SKIP",
        })
    else:
        r1 = run_timed_query(engine, RAG_QUESTION, "Online + RAG Question")
        results.append(r1)

        r2 = run_timed_query(
            engine, GENERAL_QUESTION, "Online + General Question"
        )
        results.append(r2)

    print()

    # ================================================================
    # SCENARIO 3 & 4: Offline (Phi4-Mini) mode
    # ================================================================
    print("  --- OFFLINE MODE (Phi4-Mini) ---")
    engine, config_or_err = init_engine("offline")
    if engine is None:
        print(f"    [SKIP] Cannot init offline mode: {config_or_err}")
        results.append({
            "label": "Offline + RAG Question", "question": RAG_QUESTION,
            "mode": "offline", "total_ms": 0, "engine_ms": 0,
            "chunks_used": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0, "answer_preview": "", "error": config_or_err,
            "status": "SKIP",
        })
        results.append({
            "label": "Offline + General Question",
            "question": GENERAL_QUESTION,
            "mode": "offline", "total_ms": 0, "engine_ms": 0,
            "chunks_used": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0, "answer_preview": "", "error": config_or_err,
            "status": "SKIP",
        })
    else:
        r3 = run_timed_query(engine, RAG_QUESTION, "Offline + RAG Question")
        results.append(r3)

        r4 = run_timed_query(
            engine, GENERAL_QUESTION, "Offline + General Question"
        )
        results.append(r4)

    # ================================================================
    # Output
    # ================================================================
    print_results_table(results)

    # Save JSON for trend tracking
    timestamp = datetime.now().strftime("%Y-%m-%d")
    json_path = log_dir / f"query_benchmark_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }, f, indent=2)
    print(f"  JSON saved: {json_path}")

    # Generate HTML chart
    html_path = log_dir / f"query_benchmark_{timestamp}.html"
    generate_chart_html(results, html_path)
    print(f"  Chart saved: {html_path}")
    print()
    print(f"  Open the chart:  start {html_path}")
    print()


if __name__ == "__main__":
    main()
