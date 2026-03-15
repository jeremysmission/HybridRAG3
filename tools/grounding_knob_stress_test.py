#!/usr/bin/env python3
"""
Grounding Knob Stress Test -- Live API

Proves that the grounding_bias and allow_open_knowledge knobs actually
control RAG source utilization vs open knowledge reasoning.

Runs the SAME questions under multiple grounding configurations and
compares answers to show:
  1. Strict grounding (bias=10, no open knowledge) -> answers come from sources only
  2. Moderate grounding (bias=8, open knowledge) -> answers use sources + reasoning
  3. Low grounding (bias=5, open knowledge) -> more creative, may add model knowledge
  4. Open knowledge off vs on -> clear behavioral difference

Evidence collected per answer:
  - Did it contain expected facts from RAG data?
  - Did it mark [General Knowledge] sections?
  - Did it refuse (no info found)?
  - Length, latency, token usage, cost

Usage:
    export OPENAI_API_KEY="sk-..."
    export HYBRIDRAG_API_ENDPOINT="https://api.openai.com"
    export HYBRIDRAG_API_PROVIDER="openai"
    python tools/grounding_knob_stress_test.py [--questions 10] [--model gpt-4o]
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
# Grounding configurations to test
# ---------------------------------------------------------------------------
GROUNDING_CONFIGS = [
    {
        "name": "strict-max (bias=10, no open knowledge)",
        "grounding_bias": 10,
        "allow_open_knowledge": False,
        "temperature": 0.01,
        "top_p": 0.85,
    },
    {
        "name": "strict-default (bias=9, no open knowledge)",
        "grounding_bias": 9,
        "allow_open_knowledge": False,
        "temperature": 0.05,
        "top_p": 0.90,
    },
    {
        "name": "current-baseline (bias=8, open knowledge ON)",
        "grounding_bias": 8,
        "allow_open_knowledge": True,
        "temperature": 0.08,
        "top_p": 1.0,
    },
    {
        "name": "moderate (bias=7, open knowledge ON)",
        "grounding_bias": 7,
        "allow_open_knowledge": True,
        "temperature": 0.12,
        "top_p": 0.93,
    },
    {
        "name": "creative (bias=5, open knowledge ON)",
        "grounding_bias": 5,
        "allow_open_knowledge": True,
        "temperature": 0.20,
        "top_p": 0.97,
    },
]


# ---------------------------------------------------------------------------
# Curated test questions -- mix of RAG-answerable and open-knowledge-only
# ---------------------------------------------------------------------------
CURATED_QUESTIONS = [
    # --- Questions answerable ONLY from RAG data ---
    {
        "query": "What is the operating temperature range for field deployment?",
        "expected_facts": ["-10C", "45C"],
        "category": "rag_only",
        "why": "Specific to indexed engineering docs. Model cannot know this.",
    },
    {
        "query": "What TCP port should be reachable for application connectivity?",
        "expected_facts": ["8443"],
        "category": "rag_only",
        "why": "Port number is project-specific, not general knowledge.",
    },
    {
        "query": "What is risk R-17 and how severe is it?",
        "expected_facts": ["R-17", "Supply chain delay", "High"],
        "category": "rag_only",
        "why": "Project risk register item. No model would know this.",
    },
    {
        "query": "What is the data retention policy duration?",
        "expected_facts": [],
        "category": "rag_only",
        "why": "Organization-specific policy, not public knowledge.",
    },
    {
        "query": "What voltage is used for the power supply?",
        "expected_facts": [],
        "category": "rag_only",
        "why": "Hardware-specific specification from indexed docs.",
    },
    # --- Questions that COULD use open knowledge ---
    {
        "query": "What is the difference between symmetric and asymmetric encryption?",
        "expected_facts": [],
        "category": "open_knowledge",
        "why": "General CS knowledge. Strict grounding should refuse if not in docs.",
    },
    {
        "query": "Explain the OSI model layers.",
        "expected_facts": [],
        "category": "open_knowledge",
        "why": "Standard networking knowledge. Tests if model uses training data.",
    },
    {
        "query": "What are best practices for API rate limiting?",
        "expected_facts": [],
        "category": "open_knowledge",
        "why": "General engineering knowledge, may or may not be in indexed data.",
    },
    # --- Questions that need BOTH RAG + reasoning ---
    {
        "query": "Based on the system architecture, what are the main failure modes?",
        "expected_facts": [],
        "category": "rag_plus_reasoning",
        "why": "Needs RAG data but also requires analytical reasoning.",
    },
    {
        "query": "Summarize the key risks and their mitigations from the project documents.",
        "expected_facts": [],
        "category": "rag_plus_reasoning",
        "why": "Synthesis across multiple docs. Tests reasoning with grounding.",
    },
]


@dataclass
class AnswerAnalysis:
    """Analysis of a single answer for grounding evidence."""
    config_name: str
    query: str
    category: str
    answer: str
    fact_hits: int = 0
    fact_total: int = 0
    has_general_knowledge_tag: bool = False
    is_refusal: bool = False
    answer_length: int = 0
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    chunks_used: int = 0
    error: str = ""

    @property
    def fact_rate(self) -> float:
        return self.fact_hits / self.fact_total if self.fact_total else 0.0

    @property
    def grounding_evidence(self) -> str:
        """Classify the answer's grounding behavior."""
        if self.error:
            return "ERROR"
        if self.is_refusal:
            return "REFUSED (source-bounded)"
        if self.has_general_knowledge_tag:
            return "MIXED (RAG + open knowledge)"
        if self.chunks_used > 0 and self.answer_length > 50:
            return "GROUNDED (source only)"
        if self.answer_length > 50:
            return "OPEN (no source evidence)"
        return "MINIMAL"


def analyze_answer(answer: str, expected_facts: list) -> dict:
    """Analyze an answer for grounding indicators."""
    answer_lower = answer.lower()
    fact_hits = 0
    for fact in expected_facts:
        if fact.lower() in answer_lower:
            fact_hits += 1

    refusal_phrases = [
        "not found in the provided documents",
        "not found in the provided",
        "information was not found",
        "not present in provided documents",
        "no relevant information",
        "cannot answer",
        "no information available",
    ]
    is_refusal = any(phrase in answer_lower for phrase in refusal_phrases)
    has_gk_tag = "[general knowledge]" in answer_lower

    return {
        "fact_hits": fact_hits,
        "fact_total": len(expected_facts),
        "is_refusal": is_refusal,
        "has_general_knowledge_tag": has_gk_tag,
        "answer_length": len(answer),
    }


def apply_grounding_config(config, gc: dict, model: str) -> None:
    """Apply a grounding configuration to the config object."""
    config.query.grounding_bias = gc["grounding_bias"]
    config.query.allow_open_knowledge = gc["allow_open_knowledge"]
    config.api.temperature = gc["temperature"]
    config.api.top_p = gc["top_p"]
    config.api.model = model
    config.api.max_tokens = 1024
    config.api.presence_penalty = 0.0
    config.api.frequency_penalty = 0.0


def run_grounding_stress_test(args):
    """Run the grounding knob stress test."""
    config = load_config()
    apply_mode_to_config(config, "online")

    creds = resolve_credentials(config, use_cache=False)
    if not creds.is_online_ready:
        print("[FAIL] No API credentials. Set OPENAI_API_KEY + HYBRIDRAG_API_ENDPOINT")
        sys.exit(1)

    configure_gate(mode="online", api_endpoint=creds.endpoint)

    # Build shared retrieval components
    store = VectorStore(config.paths.database)
    embedder = Embedder(dimension=768)

    questions = CURATED_QUESTIONS[:args.questions]
    configs = GROUNDING_CONFIGS

    print(f"[OK] Grounding Knob Stress Test")
    print(f"[OK] Model: {args.model}")
    print(f"[OK] Questions: {len(questions)}")
    print(f"[OK] Configs: {len(configs)}")
    print(f"[OK] Total API calls: ~{len(questions) * len(configs)}")
    print(f"[OK] Categories: {', '.join(sorted(set(q['category'] for q in questions)))}")
    print()

    all_analyses: List[AnswerAnalysis] = []
    total_start = time.time()

    for ci, gc in enumerate(configs):
        cname = gc["name"]
        print(f"{'='*70}")
        print(f"  CONFIG {ci+1}/{len(configs)}: {cname}")
        print(f"  grounding_bias={gc['grounding_bias']} | "
              f"allow_open_knowledge={gc['allow_open_knowledge']} | "
              f"temp={gc['temperature']}")
        print(f"{'='*70}")

        apply_grounding_config(config, gc, args.model)

        # Fresh router + engine per config
        router = LLMRouter(config, credentials=creds)
        engine = QueryEngine(config, store, embedder, router)

        for qi, q in enumerate(questions):
            question = q["query"]
            expected = q.get("expected_facts", [])
            category = q["category"]

            sys.stdout.write(f"  [{category:>20}] Q{qi+1}: {question[:55]}... ")
            sys.stdout.flush()

            try:
                t0 = time.time()
                result = engine.query(question)
                elapsed_ms = (time.time() - t0) * 1000

                answer = getattr(result, "answer", "") or ""
                t_in = getattr(result, "tokens_in", 0) or 0
                t_out = getattr(result, "tokens_out", 0) or 0
                chunks = getattr(result, "chunks_used", 0) or 0
                cost = getattr(result, "cost_usd", 0.0) or 0.0

                analysis = analyze_answer(answer, expected)

                aa = AnswerAnalysis(
                    config_name=cname,
                    query=question,
                    category=category,
                    answer=answer,
                    fact_hits=analysis["fact_hits"],
                    fact_total=analysis["fact_total"],
                    has_general_knowledge_tag=analysis["has_general_knowledge_tag"],
                    is_refusal=analysis["is_refusal"],
                    answer_length=analysis["answer_length"],
                    latency_ms=elapsed_ms,
                    tokens_in=t_in,
                    tokens_out=t_out,
                    cost_usd=cost,
                    chunks_used=chunks,
                )
                all_analyses.append(aa)

                evidence = aa.grounding_evidence
                sys.stdout.write(f"{evidence} | {elapsed_ms:.0f}ms | "
                                 f"{chunks} chunks | {aa.answer_length}ch\n")
                sys.stdout.flush()

            except Exception as e:
                aa = AnswerAnalysis(
                    config_name=cname,
                    query=question,
                    category=category,
                    answer="",
                    error=str(e),
                )
                all_analyses.append(aa)
                sys.stdout.write(f"ERROR: {e}\n")
                sys.stdout.flush()

        print()

    # ---------------------------------------------------------------------------
    # Results analysis
    # ---------------------------------------------------------------------------
    total_elapsed = time.time() - total_start
    total_cost = sum(a.cost_usd for a in all_analyses)

    print()
    print("=" * 70)
    print("  GROUNDING KNOB STRESS TEST RESULTS")
    print("=" * 70)

    # Per-config summary
    print(f"\n{'Config':<45} {'Grounded':<10} {'Mixed':<8} {'Refused':<9} "
          f"{'Open':<7} {'Errors':<7} {'AvgLen':<8}")
    print("-" * 94)

    for gc in configs:
        cname = gc["name"]
        config_results = [a for a in all_analyses if a.config_name == cname]
        grounded = sum(1 for a in config_results if "GROUNDED" in a.grounding_evidence)
        mixed = sum(1 for a in config_results if "MIXED" in a.grounding_evidence)
        refused = sum(1 for a in config_results if "REFUSED" in a.grounding_evidence)
        open_k = sum(1 for a in config_results if "OPEN" in a.grounding_evidence)
        errors = sum(1 for a in config_results if a.error)
        avg_len = (sum(a.answer_length for a in config_results) /
                   len(config_results)) if config_results else 0

        print(f"{cname:<45} {grounded:<10} {mixed:<8} {refused:<9} "
              f"{open_k:<7} {errors:<7} {avg_len:<8.0f}")

    # Per-category breakdown
    print(f"\n--- Category Breakdown ---")
    for cat in ["rag_only", "open_knowledge", "rag_plus_reasoning"]:
        cat_results = [a for a in all_analyses if a.category == cat]
        if not cat_results:
            continue
        print(f"\n  {cat.upper()} questions:")
        for gc in configs:
            cname = gc["name"]
            cr = [a for a in cat_results if a.config_name == cname]
            if not cr:
                continue
            behaviors = {}
            for a in cr:
                ev = a.grounding_evidence
                behaviors[ev] = behaviors.get(ev, 0) + 1
            behavior_str = ", ".join(f"{k}:{v}" for k, v in sorted(behaviors.items()))
            print(f"    {cname:<45} {behavior_str}")

    # Key insight: strict vs relaxed on open_knowledge questions
    print(f"\n--- KEY INSIGHT: Open Knowledge Questions ---")
    ok_questions = [a for a in all_analyses if a.category == "open_knowledge"]
    if ok_questions:
        for gc in configs:
            cname = gc["name"]
            cr = [a for a in ok_questions if a.config_name == cname]
            refused_count = sum(1 for a in cr if a.is_refusal)
            answered_count = sum(1 for a in cr if not a.is_refusal and not a.error)
            gk_tagged = sum(1 for a in cr if a.has_general_knowledge_tag)
            print(f"  {cname}")
            print(f"    Refused: {refused_count}/{len(cr)}  "
                  f"Answered: {answered_count}/{len(cr)}  "
                  f"[General Knowledge] tagged: {gk_tagged}/{len(cr)}")

    # Fact verification for RAG-only questions
    print(f"\n--- FACT VERIFICATION: RAG-Only Questions ---")
    rag_questions = [a for a in all_analyses if a.category == "rag_only" and a.fact_total > 0]
    if rag_questions:
        for gc in configs:
            cname = gc["name"]
            cr = [a for a in rag_questions if a.config_name == cname]
            total_hits = sum(a.fact_hits for a in cr)
            total_facts = sum(a.fact_total for a in cr)
            rate = total_hits / total_facts if total_facts else 0
            print(f"  {cname}")
            print(f"    Fact hit rate: {total_hits}/{total_facts} ({rate:.0%})")

    print(f"\n--- TOTALS ---")
    print(f"  Elapsed: {total_elapsed:.0f}s")
    print(f"  API cost: ${total_cost:.4f}")
    print(f"  Questions x configs: {len(all_analyses)}")

    # ---------------------------------------------------------------------------
    # Sample answers for side-by-side comparison
    # ---------------------------------------------------------------------------
    print(f"\n{'='*70}")
    print("  SIDE-BY-SIDE ANSWER COMPARISON (first RAG + first open knowledge Q)")
    print(f"{'='*70}")

    for sample_cat in ["rag_only", "open_knowledge"]:
        sample_q = next((q for q in questions if q["category"] == sample_cat), None)
        if not sample_q:
            continue
        print(f"\n  Q [{sample_cat}]: {sample_q['query']}")
        print(f"  Expected facts: {sample_q.get('expected_facts', [])}")
        for gc in configs:
            cname = gc["name"]
            aa = next((a for a in all_analyses
                       if a.config_name == cname and a.query == sample_q["query"]), None)
            if not aa:
                continue
            print(f"\n  --- {cname} ---")
            print(f"  Evidence: {aa.grounding_evidence}")
            print(f"  Chunks: {aa.chunks_used} | Facts: {aa.fact_hits}/{aa.fact_total}")
            # Truncate answer for readability
            ans_preview = aa.answer[:300].replace("\n", " ")
            if len(aa.answer) > 300:
                ans_preview += "..."
            print(f"  Answer: {ans_preview}")

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------
    out_dir = PROJECT_ROOT / "logs" / "grounding_stress_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"{ts}_grounding_stress.json"

    report = {
        "timestamp": ts,
        "model": args.model,
        "questions": len(questions),
        "configs": len(configs),
        "total_elapsed_s": total_elapsed,
        "total_cost_usd": total_cost,
        "analyses": [
            {
                "config": a.config_name,
                "query": a.query,
                "category": a.category,
                "grounding_evidence": a.grounding_evidence,
                "answer": a.answer,
                "fact_hits": a.fact_hits,
                "fact_total": a.fact_total,
                "has_general_knowledge_tag": a.has_general_knowledge_tag,
                "is_refusal": a.is_refusal,
                "answer_length": a.answer_length,
                "latency_ms": round(a.latency_ms, 1),
                "tokens_in": a.tokens_in,
                "tokens_out": a.tokens_out,
                "cost_usd": round(a.cost_usd, 6),
                "chunks_used": a.chunks_used,
                "error": a.error,
            }
            for a in all_analyses
        ],
    }
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[OK] Results saved: {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Grounding knob stress test")
    parser.add_argument("--questions", type=int, default=10,
                        help="Number of questions to test (default: 10, max: 10)")
    parser.add_argument("--model", default="gpt-4o",
                        help="Model to use (default: gpt-4o)")
    args = parser.parse_args()
    args.questions = min(args.questions, len(CURATED_QUESTIONS))
    run_grounding_stress_test(args)


if __name__ == "__main__":
    main()
