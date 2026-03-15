#!/usr/bin/env python3
"""
Generation-Side Autotune -- Live API Sweep

Locks retrieval settings (already tuned) and sweeps generation/query-policy
knobs against a live OpenAI API to find the best generation config.

Usage:
    export OPENAI_API_KEY="sk-..."
    export HYBRIDRAG_API_ENDPOINT="https://api.openai.com"
    export HYBRIDRAG_API_PROVIDER="openai"
    python tools/generation_autotune_live.py [--questions 20] [--model gpt-4o]
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import apply_mode_to_config, load_config
from src.core.embedder import Embedder
from src.core.llm_router import LLMRouter
from src.core.network_gate import configure_gate
from src.core.query_engine import QueryEngine
from src.core.vector_store import VectorStore
from src.security.credentials import resolve_credentials


# ---------------------------------------------------------------------------
# Generation bundles to sweep (retrieval stays fixed)
# ---------------------------------------------------------------------------

GENERATION_BUNDLES = [
    {
        "name": "strict-cold",
        "temperature": 0.01,
        "top_p": 0.85,
        "grounding_bias": 10,
        "allow_open_knowledge": False,
        "max_tokens": 1024,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "strict-warm",
        "temperature": 0.05,
        "top_p": 0.90,
        "grounding_bias": 9,
        "allow_open_knowledge": False,
        "max_tokens": 1024,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "current-baseline",
        "temperature": 0.08,
        "top_p": 1.0,
        "grounding_bias": 8,
        "allow_open_knowledge": True,
        "max_tokens": 1024,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "balanced",
        "temperature": 0.12,
        "top_p": 0.93,
        "grounding_bias": 7,
        "allow_open_knowledge": True,
        "max_tokens": 1024,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "creative",
        "temperature": 0.20,
        "top_p": 0.97,
        "grounding_bias": 5,
        "allow_open_knowledge": True,
        "max_tokens": 1024,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.1,
    },
    {
        "name": "strict-short",
        "temperature": 0.05,
        "top_p": 0.90,
        "grounding_bias": 9,
        "allow_open_knowledge": False,
        "max_tokens": 512,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "strict-long",
        "temperature": 0.05,
        "top_p": 0.90,
        "grounding_bias": 9,
        "allow_open_knowledge": False,
        "max_tokens": 2048,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    },
    {
        "name": "anti-repeat",
        "temperature": 0.08,
        "top_p": 1.0,
        "grounding_bias": 8,
        "allow_open_knowledge": True,
        "max_tokens": 1024,
        "presence_penalty": 0.2,
        "frequency_penalty": 0.2,
    },
]


@dataclass
class BundleResult:
    name: str
    settings: Dict[str, Any]
    scores: List[float] = field(default_factory=list)
    fact_hits: int = 0
    fact_total: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    errors: int = 0

    @property
    def avg_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def fact_rate(self) -> float:
        return self.fact_hits / self.fact_total if self.fact_total else 0.0

    @property
    def avg_latency(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def est_cost(self) -> float:
        # gpt-4o: $2.50/1M in, $10/1M out
        return (self.tokens_in * 2.50 + self.tokens_out * 10.0) / 1_000_000


def score_answer(answer: str, expected_facts: List[str]) -> tuple:
    """Score answer against expected key facts (case-insensitive substring)."""
    if not expected_facts:
        return 1.0, 0, 0
    hits = 0
    answer_lower = answer.lower()
    for fact in expected_facts:
        if fact.lower() in answer_lower:
            hits += 1
    return hits / len(expected_facts), hits, len(expected_facts)


def select_eval_subset(evals: list, n: int) -> list:
    """Pick n answerable questions spread across roles."""
    answerable = [q for q in evals if q.get("type") == "answerable"]
    # Spread across roles for diversity
    by_role = {}
    for q in answerable:
        role = q.get("role", "unknown")
        by_role.setdefault(role, []).append(q)
    selected = []
    role_cycle = list(by_role.keys())
    idx = 0
    while len(selected) < n and any(by_role.values()):
        role = role_cycle[idx % len(role_cycle)]
        if by_role[role]:
            selected.append(by_role[role].pop(0))
        idx += 1
    return selected[:n]


def apply_bundle(config, bundle: dict, model: str) -> None:
    """Apply generation bundle settings to config object."""
    config.api.temperature = bundle["temperature"]
    config.api.top_p = bundle["top_p"]
    config.api.max_tokens = bundle["max_tokens"]
    config.api.presence_penalty = bundle["presence_penalty"]
    config.api.frequency_penalty = bundle["frequency_penalty"]
    config.api.model = model
    config.query.grounding_bias = bundle["grounding_bias"]
    config.query.allow_open_knowledge = bundle["allow_open_knowledge"]


def run_sweep(args):
    """Run the generation autotune sweep."""
    config = load_config()
    apply_mode_to_config(config, "online")

    creds = resolve_credentials(config, use_cache=False)
    if not creds.is_online_ready:
        print("[FAIL] No API credentials. Set OPENAI_API_KEY + HYBRIDRAG_API_ENDPOINT")
        sys.exit(1)

    configure_gate(mode="online", api_endpoint=creds.endpoint)

    # Build shared components (retrieval is fixed)
    store = VectorStore(config.paths.database)
    embedder = Embedder(dimension=768)

    # Load eval subset
    eval_path = PROJECT_ROOT / "Eval" / "golden_tuning_400.json"
    with open(eval_path) as f:
        evals = json.load(f)
    questions = select_eval_subset(evals, args.questions)
    print(f"[OK] {len(questions)} eval questions selected across "
          f"{len(set(q['role'] for q in questions))} roles")
    print(f"[OK] Model: {args.model}")
    print(f"[OK] Bundles: {len(GENERATION_BUNDLES)}")
    print(f"[OK] Total API calls: ~{len(questions) * len(GENERATION_BUNDLES)}")
    print()

    results: List[BundleResult] = []
    total_start = time.time()

    for bi, bundle in enumerate(GENERATION_BUNDLES):
        bname = bundle["name"]
        print(f"--- Bundle {bi+1}/{len(GENERATION_BUNDLES)}: {bname} ---")
        apply_bundle(config, bundle, args.model)

        # Fresh router per bundle (picks up new settings)
        router = LLMRouter(config, credentials=creds)
        engine = QueryEngine(config, store, embedder, router)

        br = BundleResult(name=bname, settings=bundle)

        for qi, q in enumerate(questions):
            question = q["query"]
            expected = q.get("expected_key_facts", "[]")
            if isinstance(expected, str):
                try:
                    expected = json.loads(expected.replace("'", '"'))
                except Exception:
                    expected = []

            try:
                t0 = time.time()
                result = engine.query(question)
                elapsed_ms = (time.time() - t0) * 1000

                answer = getattr(result, "answer", "") or ""
                t_in = getattr(result, "tokens_in", 0) or 0
                t_out = getattr(result, "tokens_out", 0) or 0

                score, hits, total = score_answer(answer, expected)
                br.scores.append(score)
                br.fact_hits += hits
                br.fact_total += total
                br.latencies_ms.append(elapsed_ms)
                br.tokens_in += t_in
                br.tokens_out += t_out

                status = "OK" if score >= 0.5 else "MISS"
                sys.stdout.write(f"  [{status}] Q{qi+1} score={score:.0%} "
                                 f"facts={hits}/{total} {elapsed_ms:.0f}ms\n")
                sys.stdout.flush()

            except Exception as e:
                br.errors += 1
                br.scores.append(0.0)
                sys.stdout.write(f"  [ERR] Q{qi+1}: {e}\n")
                sys.stdout.flush()

        print(f"  >> {bname}: avg={br.avg_score:.1%} facts={br.fact_rate:.1%} "
              f"latency={br.avg_latency:.0f}ms cost=${br.est_cost:.3f} "
              f"errors={br.errors}")
        print()
        results.append(br)

    # Leaderboard
    total_elapsed = time.time() - total_start
    results.sort(key=lambda r: r.avg_score, reverse=True)

    print("=" * 70)
    print("GENERATION AUTOTUNE LEADERBOARD")
    print("=" * 70)
    print(f"{'Rank':<5} {'Bundle':<20} {'Score':<8} {'Facts':<8} "
          f"{'Latency':<10} {'Cost':<8} {'Errors':<7}")
    print("-" * 70)
    for i, r in enumerate(results):
        print(f"{i+1:<5} {r.name:<20} {r.avg_score:<8.1%} {r.fact_rate:<8.1%} "
              f"{r.avg_latency:<10.0f}ms ${r.est_cost:<7.3f} {r.errors}")

    total_cost = sum(r.est_cost for r in results)
    print(f"\nTotal: {total_elapsed:.0f}s elapsed, ${total_cost:.3f} API cost")

    winner = results[0]
    print(f"\nWINNER: {winner.name} (score={winner.avg_score:.1%})")
    print(f"  Settings: {json.dumps({k:v for k,v in winner.settings.items() if k != 'name'}, indent=2)}")

    # Save results
    out_dir = PROJECT_ROOT / "logs" / "generation_autotune"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"{ts}_generation_sweep.json"
    report = {
        "timestamp": ts,
        "model": args.model,
        "questions": args.questions,
        "total_elapsed_s": total_elapsed,
        "total_cost_usd": total_cost,
        "leaderboard": [
            {
                "rank": i + 1,
                "name": r.name,
                "avg_score": round(r.avg_score, 4),
                "fact_rate": round(r.fact_rate, 4),
                "avg_latency_ms": round(r.avg_latency, 1),
                "cost_usd": round(r.est_cost, 4),
                "errors": r.errors,
                "settings": r.settings,
            }
            for i, r in enumerate(results)
        ],
    }
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Generation-side autotune sweep")
    parser.add_argument("--questions", type=int, default=20,
                        help="Number of eval questions per bundle (default: 20)")
    parser.add_argument("--model", default="gpt-4o",
                        help="Model to use (default: gpt-4o)")
    args = parser.parse_args()
    run_sweep(args)


if __name__ == "__main__":
    main()
