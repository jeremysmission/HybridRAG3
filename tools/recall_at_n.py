#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Measures retrieval recall@N against the golden evaluation set.
# What to read first: main() at the bottom orchestrates everything.
# Inputs: Golden dataset JSON, existing vector index, config.
# Outputs: Console summary + JSON report in output/recall_baseline_YYYY-MM-DD.json.
# Safety notes: This is a READ-ONLY measurement tool. It does not modify the index.
# ============================
"""
Recall@N Measurement Tool for HybridRAG3

Measures how often the retriever surfaces the correct source documents
within the top N results, using the golden evaluation set as ground truth.

Usage (from repo root):
  python tools/recall_at_n.py
  python tools/recall_at_n.py --golden Eval/golden_tuning_400.json
  python tools/recall_at_n.py --top-n 100 --cutoffs 5,10,25,50,100

This is a READ-ONLY tool -- it does not modify the retriever or index.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _normalize_source(source: str) -> str:
    """Normalize a source path to just the filename, lowercased."""
    return os.path.basename(source.replace("\\", "/")).lower()


def _sources_from_hits(hits: list) -> List[str]:
    """Extract normalized source filenames from retrieval hits."""
    sources: List[str] = []
    for hit in hits:
        sp = hit.get("source_path", "") if isinstance(hit, dict) else getattr(hit, "source_path", "")
        if sp:
            sources.append(_normalize_source(sp))
    return sources


def _check_recall(retrieved: List[str], expected: List[str], n: int) -> Tuple[bool, List[str], List[str]]:
    """Check if ALL expected sources appear in top-n. Returns (hit, found, missing)."""
    top_n_set = set(retrieved[:n])
    exp = [_normalize_source(s) for s in expected]
    found = [s for s in exp if s in top_n_set]
    missing = [s for s in exp if s not in top_n_set]
    return len(missing) == 0, found, missing


def _check_recall_any(retrieved: List[str], expected: List[str], n: int) -> bool:
    """True if ANY expected source appears in top-n."""
    top_n_set = set(retrieved[:n])
    return any(_normalize_source(s) in top_n_set for s in expected)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    idx = int(round((pct / 100.0) * (len(v) - 1)))
    return float(v[max(0, min(idx, len(v) - 1))])


def _group_summary(per_question: list, group_key: str, cutoffs: list) -> Dict[str, Dict[str, Any]]:
    """Compute recall breakdown grouped by a field (role or type)."""
    groups: Dict[str, Dict[str, list]] = {}
    for q in per_question:
        g = q.get(group_key, "unknown")
        if g not in groups:
            groups[g] = {f"recall_all@{c}": [] for c in cutoffs}
            groups[g].update({f"recall_any@{c}": [] for c in cutoffs})
        for c in cutoffs:
            groups[g][f"recall_all@{c}"].append(1 if q["recall"].get(str(c)) else 0)
            groups[g][f"recall_any@{c}"].append(1 if q["recall_any"].get(str(c)) else 0)
    result: Dict[str, Dict[str, Any]] = {}
    for g, metrics in groups.items():
        result[g] = {k: round(sum(v) / len(v), 4) if v else 0.0 for k, v in metrics.items()}
        result[g]["count"] = len(next(iter(metrics.values()), []))
    return result


def run_recall_measurement(
    golden_path: str,
    top_n: int = 50,
    cutoffs: Optional[List[int]] = None,
    limit: int = 0,
    config_filename: str = "config.yaml",
) -> Dict[str, Any]:
    """Run recall@N measurement against the golden evaluation set."""
    if cutoffs is None:
        cutoffs = [5, 10, 20, 50]
    cutoffs = sorted(set(c for c in cutoffs if c <= top_n)) or [top_n]

    # Load golden dataset
    print(f"[1/4] Loading golden dataset from {golden_path} ...")
    with open(golden_path, "r", encoding="utf-8") as f:
        golden: List[Dict[str, Any]] = json.load(f)

    evaluable = [item for item in golden if item.get("expected_sources")]
    if limit > 0:
        evaluable = evaluable[:limit]
    total_evaluable = len(evaluable)
    total_golden = len(golden)
    print(f"    {total_golden} total questions, {total_evaluable} with expected sources")
    if total_evaluable == 0:
        return {"error": "no_evaluable_questions"}

    # Boot HybridRAG (retriever only -- no LLM needed)
    print("[2/4] Booting HybridRAG (retriever only) ...")
    from src.core.boot import boot_hybridrag
    boot_res = boot_hybridrag(config_path=None)
    if not getattr(boot_res, "success", False):
        raise SystemExit(f"Boot failed: {getattr(boot_res, 'errors', [])}")

    from src.core.config import load_config
    from src.core.embedder import Embedder
    from src.core.vector_store import VectorStore
    from src.core.retriever import Retriever

    cfg = load_config(project_dir=str(PROJECT_ROOT), config_filename=config_filename)
    store = VectorStore(db_path=cfg.paths.database, embedding_dim=cfg.embedding.dimension)
    store.connect()
    embedder = Embedder(model_name=cfg.embedding.model_name, dimension=cfg.embedding.dimension)
    retriever = Retriever(store, embedder, cfg)
    retriever.top_k = top_n
    retriever.min_score = 0.0  # No score filter -- we want all candidates

    stats = store.get_stats()
    print(f"    Index: {stats.get('chunk_count', '?')} chunks, "
          f"{stats.get('source_count', '?')} sources, dim={stats.get('embedding_dim', '?')}")

    # Run retrieval for each question
    print(f"[3/4] Running retrieval for {total_evaluable} questions (top_n={top_n}) ...")
    per_question: List[Dict[str, Any]] = []
    latencies: List[float] = []
    recall_counters = {c: {"all_hit": 0, "any_hit": 0, "total": 0} for c in cutoffs}

    t0 = time.time()
    for idx, item in enumerate(evaluable, 1):
        qid = item.get("id", f"Q{idx:04d}")
        query = item["query"]
        expected_sources = item["expected_sources"]
        qtype = item.get("type", "answerable")
        role = item.get("role", "")

        t_q = time.time()
        try:
            hits = retriever.search(query)
            latency_ms = (time.time() - t_q) * 1000
        except Exception as e:
            latency_ms = (time.time() - t_q) * 1000
            per_question.append({
                "id": qid, "role": role, "type": qtype, "query": query,
                "expected_sources": expected_sources, "retrieved_sources_top10": [],
                "n_retrieved": 0, "latency_ms": round(latency_ms, 1),
                "error": f"{type(e).__name__}: {e}",
                "recall": {str(c): False for c in cutoffs},
                "recall_any": {str(c): False for c in cutoffs},
            })
            latencies.append(latency_ms)
            for c in cutoffs:
                recall_counters[c]["total"] += 1
            if idx % 50 == 0:
                print(f"    Progress: {idx}/{total_evaluable}")
            continue

        latencies.append(latency_ms)
        retrieved_sources = _sources_from_hits(hits)

        recall_results: Dict[str, bool] = {}
        recall_any_results: Dict[str, bool] = {}
        recall_detail: Dict[str, Dict[str, Any]] = {}
        for c in cutoffs:
            all_hit, found, missing = _check_recall(retrieved_sources, expected_sources, c)
            any_hit = _check_recall_any(retrieved_sources, expected_sources, c)
            recall_results[str(c)] = all_hit
            recall_any_results[str(c)] = any_hit
            recall_detail[str(c)] = {"found": found, "missing": missing}
            recall_counters[c]["total"] += 1
            if all_hit:
                recall_counters[c]["all_hit"] += 1
            if any_hit:
                recall_counters[c]["any_hit"] += 1

        unique_retrieved = list(dict.fromkeys(retrieved_sources))
        per_question.append({
            "id": qid, "role": role, "type": qtype, "query": query,
            "expected_sources": expected_sources,
            "retrieved_sources_top10": unique_retrieved[:10],
            "n_retrieved": len(hits), "latency_ms": round(latency_ms, 1),
            "error": "", "recall": recall_results,
            "recall_any": recall_any_results, "recall_detail": recall_detail,
        })
        if idx % 50 == 0:
            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0
            print(f"    Progress: {idx}/{total_evaluable} ({rate:.1f} q/s, {elapsed:.0f}s elapsed)")

    elapsed_total = time.time() - t0

    # Compute aggregate metrics
    print("[4/4] Computing aggregate metrics ...")
    aggregate: Dict[str, Any] = {}
    for c in cutoffs:
        ct = recall_counters[c]
        total = ct["total"]
        aggregate[f"recall_all@{c}"] = round(ct["all_hit"] / total, 4) if total else 0.0
        aggregate[f"recall_any@{c}"] = round(ct["any_hit"] / total, 4) if total else 0.0

    max_cutoff = max(cutoffs)
    missed_questions = [
        {"id": q["id"], "query": q["query"],
         "expected_sources": q["expected_sources"],
         "retrieved_top10": q.get("retrieved_sources_top10", [])}
        for q in per_question if not q["recall"].get(str(max_cutoff), False)
    ]

    latency_stats = {
        "p50_ms": round(_percentile(latencies, 50), 1),
        "p95_ms": round(_percentile(latencies, 95), 1),
        "p99_ms": round(_percentile(latencies, 99), 1),
        "mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
    }
    n_errors = sum(1 for q in per_question if q.get("error"))

    report = {
        "metadata": {
            "tool": "recall_at_n.py",
            "timestamp": datetime.now().isoformat(),
            "golden_dataset": str(golden_path),
            "total_golden_questions": total_golden,
            "evaluable_questions": total_evaluable,
            "top_n": top_n, "cutoffs": cutoffs,
            "elapsed_seconds": round(elapsed_total, 2),
            "errors": n_errors, "index_stats": stats,
        },
        "aggregate": aggregate,
        "latency": latency_stats,
        "by_role": _group_summary(per_question, "role", cutoffs),
        "by_type": _group_summary(per_question, "type", cutoffs),
        "missed_at_max_cutoff": missed_questions[:50],
        "per_question": per_question,
    }
    store.close()
    return report


def print_summary(report: Dict[str, Any]) -> None:
    """Print a human-readable summary to the console."""
    meta = report["metadata"]
    agg = report["aggregate"]
    cutoffs = meta["cutoffs"]
    max_c = max(cutoffs)

    print("\n" + "=" * 68)
    print("  RECALL@N MEASUREMENT REPORT")
    print("=" * 68)
    print(f"  Golden dataset:    {meta['golden_dataset']}")
    print(f"  Evaluable items:   {meta['evaluable_questions']} / {meta['total_golden_questions']}")
    print(f"  Top-N retrieved:   {meta['top_n']}")
    print(f"  Elapsed:           {meta['elapsed_seconds']:.1f}s")
    print(f"  Errors:            {meta['errors']}")

    for label, prefix in [("all expected sources found", "recall_all"),
                           ("any expected source found", "recall_any")]:
        print(f"\n  --- Aggregate Recall ({label}) ---")
        for c in cutoffs:
            val = agg.get(f"{prefix}@{c}", 0.0)
            bar = "#" * int(val * 40)
            print(f"    recall@{c:<4d}  {val:6.1%}  {bar}")

    lat = report["latency"]
    print(f"\n  --- Latency ---")
    print(f"    p50={lat['p50_ms']:.0f}ms  p95={lat['p95_ms']:.0f}ms  "
          f"p99={lat['p99_ms']:.0f}ms  mean={lat['mean_ms']:.0f}ms")

    print("\n  --- By Role ---")
    for role, metrics in sorted(report.get("by_role", {}).items()):
        n = metrics.get("count", 0)
        r_all = metrics.get(f"recall_all@{max_c}", 0.0)
        r_any = metrics.get(f"recall_any@{max_c}", 0.0)
        print(f"    {role:<30s}  n={n:>3d}  all@{max_c}={r_all:5.1%}  any@{max_c}={r_any:5.1%}")

    missed = report.get("missed_at_max_cutoff", [])
    if missed:
        show_n = min(10, len(missed))
        print(f"\n  --- Missed at @{max_c} ({len(missed)} total, showing {show_n}) ---")
        for q in missed[:show_n]:
            print(f"    {q['id']}: {q['query'][:70]}")
            print(f"      expected: {q['expected_sources']}")
            print(f"      got:      {q.get('retrieved_top10', [])[:5]}")
    print("\n" + "=" * 68)


def main():
    ap = argparse.ArgumentParser(description="Measure retrieval recall@N against golden eval set")
    ap.add_argument("--golden", default=str(PROJECT_ROOT / "Eval" / "golden_tuning_400.json"),
                    help="Path to golden dataset JSON")
    ap.add_argument("--top-n", type=int, default=50, help="Max results per query (default: 50)")
    ap.add_argument("--cutoffs", default="5,10,20,50", help="Comma-separated recall cutoffs")
    ap.add_argument("--limit", type=int, default=0, help="Evaluate first N questions only (0=all)")
    ap.add_argument("--config", default="config.yaml", help="Config filename")
    ap.add_argument("--output", default="", help="Output JSON path")
    args = ap.parse_args()

    cutoffs = [int(c.strip()) for c in args.cutoffs.split(",") if c.strip()]
    os.chdir(str(PROJECT_ROOT))

    report = run_recall_measurement(
        golden_path=args.golden, top_n=args.top_n,
        cutoffs=cutoffs, limit=args.limit, config_filename=args.config,
    )
    if "error" in report:
        print(f"[ERROR] {report['error']}")
        sys.exit(1)

    print_summary(report)

    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = out_dir / f"recall_baseline_{datetime.now().strftime('%Y-%m-%d')}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Results saved to: {out_path}\n")


if __name__ == "__main__":
    main()
