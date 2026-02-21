#!/usr/bin/env python3
"""
HybridRAG3 Automated Evaluation Runner

What it does
- Loads a golden dataset JSON (list of items)
- Boots HybridRAG3 using your STABLE boot interface
- Runs each query through QueryEngine.query()
- Writes results.jsonl (one JSON record per question) + run_summary.json

IMPORTANT
- This runner does NOT open raw source documents. It only calls your RAG pipeline.

Usage (from repo root)
  python tools/eval_runner.py --dataset datasets/golden_tuning_400.json --outdir eval_out/tuning --config config/default_config.yaml
  python tools/eval_runner.py --dataset datasets/golden_hidden_validation_100.json --outdir eval_out/hidden --config config/default_config.yaml

If your imports differ:
- Adjust the imports in the "BOOT + CONSTRUCT" section only.
"""

import argparse, json, os, time
from typing import Any, Dict, List

def safe_getattr(obj: Any, name: str, default=None):
    return getattr(obj, name, default)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="Path to golden dataset JSON")
    ap.add_argument("--outdir", default="eval_out", help="Output directory")
    ap.add_argument("--config", default=None, help="Config filename/path for boot")
    ap.add_argument("--mode", default=None, help="Optional override: online/offline")
    ap.add_argument("--limit", type=int, default=0, help="Optional limit number of questions")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # -----------------------------
    # BOOT + CONSTRUCT (STABLE API)
    # -----------------------------
    from src.core.boot import boot_hybridrag
    boot_res = boot_hybridrag(config_path=args.config)

    if not safe_getattr(boot_res, "success", False):
        raise SystemExit(f"Boot failed: {safe_getattr(boot_res,'errors',[])}")

    # If you prefer to use objects created by boot_res, you can adapt this section.
    from src.core.config import load_config
    from src.core.embedder import Embedder
    from src.core.vector_store import VectorStore
    from src.core.llm_router import LLMRouter
    from src.core.query_engine import QueryEngine

    cfg = load_config(project_dir=".", config_filename=(args.config or "default_config.yaml"))

    if args.mode:
        os.environ["HYBRIDRAG_MODE"] = args.mode

    store = VectorStore(db_path=cfg.paths.database, embedding_dim=cfg.embedding.dimension)
    store.connect()
    embedder = Embedder(model_name=cfg.embedding.model_name)
    router = LLMRouter(cfg, api_key=None)  # Your credentials resolver may configure this elsewhere.
    engine = QueryEngine(cfg, store, embedder, router)

    # -----------------------------
    # LOAD DATASET
    # -----------------------------
    with open(args.dataset, "r", encoding="utf-8") as f:
        data: List[Dict[str, Any]] = json.load(f)

    if args.limit and args.limit > 0:
        data = data[:args.limit]

    results_path = os.path.join(args.outdir, "results.jsonl")
    summary_path = os.path.join(args.outdir, "run_summary.json")

    t0 = time.time()
    n_ok = 0

    with open(results_path, "w", encoding="utf-8") as out:
        for item in data:
            qid = item["id"]
            query = item["query"]
            role = item.get("role","")
            qtype = item.get("type","")

            t_q0 = time.time()
            try:
                res = engine.query(query)
                latency_ms = safe_getattr(res, "latency_ms", int((time.time()-t_q0)*1000))
                record = {
                    "id": qid,
                    "role": role,
                    "type": qtype,
                    "query": query,
                    "answer": safe_getattr(res, "answer", ""),
                    "sources": safe_getattr(res, "sources", []),
                    "chunks_used": safe_getattr(res, "chunks_used", 0),
                    "tokens_in": safe_getattr(res, "tokens_in", 0),
                    "tokens_out": safe_getattr(res, "tokens_out", 0),
                    "cost_usd": safe_getattr(res, "cost_usd", 0.0),
                    "latency_ms": latency_ms,
                    "mode": safe_getattr(res, "mode", ""),
                    "error": safe_getattr(res, "error", ""),
                }
                if not record["error"]:
                    n_ok += 1
            except Exception as e:
                record = {
                    "id": qid,
                    "role": role,
                    "type": qtype,
                    "query": query,
                    "answer": "",
                    "sources": [],
                    "chunks_used": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": 0.0,
                    "latency_ms": int((time.time()-t_q0)*1000),
                    "mode": "",
                    "error": f"{type(e).__name__}: {e}",
                }

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    summary = {
        "dataset": args.dataset,
        "count": len(data),
        "completed_without_error": n_ok,
        "elapsed_seconds": elapsed,
        "results_jsonl": results_path,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
