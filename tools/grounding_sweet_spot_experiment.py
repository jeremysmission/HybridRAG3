#!/usr/bin/env python3
"""
Grounding Sweet-Spot Experiment
================================
Creates controlled source files with known facts, indexes them, then sweeps
grounding/creativity settings against gpt-4o to find the optimal balance
between source-locked accuracy and reasoning/synthesis capability.

The experiment answers: "What settings let gpt-4o cite RAG facts accurately
while still being creative enough to synthesize, infer, and interpret?"

Usage:
    export OPENAI_API_KEY="sk-..."
    export HYBRIDRAG_API_ENDPOINT="https://api.openai.com"
    export HYBRIDRAG_API_PROVIDER="openai"
    python tools/grounding_sweet_spot_experiment.py
"""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from src.core.chunker import Chunker
from src.core.config import apply_mode_to_config, load_config
from src.core.embedder import Embedder
from src.core.llm_router import LLMRouter, invalidate_deployment_cache
from src.core.network_gate import configure_gate
from src.core.query_engine import QueryEngine
from src.core.query_mode import apply_query_mode_to_config
from src.core.vector_store import ChunkMetadata, VectorStore
from src.security.credentials import resolve_credentials

# ---------------------------------------------------------------------------
# Test corpus -- synthetic engineering docs with verifiable ground truth
# ---------------------------------------------------------------------------

MARKER = "GSSE"  # Grounding Sweet Spot Experiment -- unique prefix

TEST_DOCUMENTS = {
    f"{MARKER}_Site_Visit_Report_2025.txt": """
SITE VISIT SUMMARY REPORT -- FISCAL YEAR 2025

Prepared by: Regional Operations Division
Report ID: {m}-SVR-2025-001

SITE VISIT COUNTS BY LOCATION:
- SITE-ALPHA (Phoenix AZ): 47 visits in 2025, 38 visits in 2024
- SITE-BRAVO (Denver CO): 31 visits in 2025, 29 visits in 2024
- SITE-CHARLIE (Tampa FL): 22 visits in 2025, 41 visits in 2024
- SITE-DELTA (Portland OR): 18 visits in 2025, 15 visits in 2024
- SITE-ECHO (Boston MA): 12 visits in 2025, 19 visits in 2024

Total visits across all sites: 130 in 2025, 142 in 2024.
Year-over-year change: -8.5% reduction in total visits.

NOTABLE FINDINGS:
- SITE-ALPHA had the most visits due to ongoing RF amplifier replacement project.
- SITE-CHARLIE visits dropped 46% year-over-year due to completion of antenna upgrade.
- SITE-ECHO had lowest visit count; only scheduled preventive maintenance performed.
- SITE-DELTA showed 20% increase driven by new equipment installation.

COST PER VISIT (average):
- SITE-ALPHA: $2,847 per visit (high due to specialized RF equipment)
- SITE-BRAVO: $1,923 per visit
- SITE-CHARLIE: $3,105 per visit (highest -- remote location surcharge)
- SITE-DELTA: $1,654 per visit (lowest -- local technician availability)
- SITE-ECHO: $2,211 per visit
""".format(m=MARKER),

    f"{MARKER}_Parts_Failure_Log_2025.txt": """
PARTS FAILURE ANALYSIS LOG -- 2025

Document ID: {m}-PFL-2025-001
Classification: Internal Use Only

FAILURE COUNTS BY PART NUMBER (ranked highest to lowest):
1. HR-7741 (RF Power Amplifier): 23 failures across all sites
   - Mean time between failures (MTBF): 4,200 hours
   - Primary failure mode: thermal degradation of output transistor
   - Affected sites: SITE-ALPHA (14), SITE-BRAVO (5), SITE-CHARLIE (4)

2. HR-7742 (Antenna Feed Assembly): 17 failures
   - MTBF: 6,800 hours
   - Primary failure mode: moisture ingress causing corrosion at SMA connector
   - Affected sites: SITE-CHARLIE (8), SITE-DELTA (5), SITE-ECHO (4)

3. HR-7743 (Digital Signal Processor Board): 11 failures
   - MTBF: 12,500 hours
   - Primary failure mode: electrolytic capacitor aging (C47, C48 on rev D boards)
   - Affected sites: SITE-ALPHA (4), SITE-BRAVO (4), SITE-DELTA (3)

4. HR-7744 (Power Supply Module 48V): 8 failures
   - MTBF: 18,000 hours
   - Primary failure mode: input filter capacitor ESR increase
   - Affected sites: SITE-BRAVO (3), SITE-ALPHA (3), SITE-ECHO (2)

5. HR-7745 (Fiber Optic Transceiver): 3 failures
   - MTBF: 45,000 hours
   - Primary failure mode: laser diode end-of-life
   - Affected sites: SITE-ALPHA (2), SITE-CHARLIE (1)

TOTAL FAILURES IN 2025: 62 parts across 5 sites.
TOTAL REPAIR COST: $187,400.
Average cost per failure: $3,022.58.

TREND NOTE: HR-7741 failures increased 35% vs 2024 (was 17 failures).
HR-7742 failures steady (was 16 in 2024).
HR-7743 failures decreased 21% (was 14 in 2024).
""".format(m=MARKER),

    f"{MARKER}_Maintenance_Schedule_2025.txt": """
PREVENTIVE MAINTENANCE SCHEDULE -- 2025

Document ID: {m}-PMS-2025-001

MAINTENANCE INTERVALS BY SYSTEM:
- RF Subsystem: 90-day cycle (quarterly)
  - Tasks: amplifier bias check, antenna VSWR measurement, cable continuity
  - Estimated duration: 4 hours per site visit
  - Required tools: spectrum analyzer SA-9000, power meter PM-200, VSWR bridge

- Digital Subsystem: 180-day cycle (semi-annual)
  - Tasks: firmware version verification, memory diagnostics, log review
  - Estimated duration: 2 hours per site visit
  - Required tools: laptop with diagnostic software v3.2+

- Power Subsystem: 365-day cycle (annual)
  - Tasks: capacitor ESR measurement, thermal imaging scan, battery load test
  - Estimated duration: 6 hours per site visit
  - Required tools: ESR meter, thermal camera TC-500, battery analyzer BA-100

- Environmental Controls: 90-day cycle (quarterly)
  - Tasks: HVAC filter replacement, temperature sensor calibration, humidity check
  - Estimated duration: 1.5 hours per site visit
  - Required tools: calibrated thermometer, hygrometer

MAINTENANCE COMPLIANCE RATES (2025):
- SITE-ALPHA: 94% on-time compliance
- SITE-BRAVO: 87% on-time compliance (3 deferred due to weather)
- SITE-CHARLIE: 78% on-time compliance (remote access challenges)
- SITE-DELTA: 91% on-time compliance
- SITE-ECHO: 96% on-time compliance (best in region)

CRITICAL FINDING: Sites with compliance below 85% show 2.3x higher failure rates.
""".format(m=MARKER),

    f"{MARKER}_Performance_Metrics_Q4_2025.txt": """
SYSTEM PERFORMANCE METRICS -- Q4 2025

Document ID: {m}-SPM-2025-Q4

UPTIME BY SITE (October-December 2025):
- SITE-ALPHA: 97.2% uptime (68.1 hours downtime)
- SITE-BRAVO: 99.1% uptime (19.7 hours downtime)
- SITE-DELTA: 98.7% uptime (28.4 hours downtime)
- SITE-ECHO: 99.6% uptime (8.7 hours downtime) -- BEST
- SITE-CHARLIE: 94.3% uptime (124.5 hours downtime) -- WORST

SIGNAL QUALITY MEASUREMENTS:
- SITE-ALPHA: SNR 24.3 dB average, peak 31.2 dB
- SITE-BRAVO: SNR 28.1 dB average, peak 33.7 dB
- SITE-CHARLIE: SNR 19.8 dB average, peak 25.4 dB (below 22 dB threshold 37% of time)
- SITE-DELTA: SNR 26.7 dB average, peak 32.1 dB
- SITE-ECHO: SNR 30.2 dB average, peak 35.8 dB

DATA THROUGHPUT:
- Network aggregate: 847 GB processed in Q4
- Average query latency: 142ms (target: <200ms)
- Peak concurrent connections: 312 (capacity: 500)
- Failed transactions: 0.03% (target: <0.1%)

POWER CONSUMPTION:
- Average per site: 4.7 kW
- SITE-ALPHA: 5.8 kW (highest -- additional cooling for RF amps)
- SITE-ECHO: 3.2 kW (lowest -- minimal equipment footprint)

ENVIRONMENTAL:
- Operating temperature range: -10C to 45C (all sites within spec)
- Humidity range: 20% to 80% RH (SITE-CHARLIE exceeded 85% RH on 3 occasions)
""".format(m=MARKER),

    f"{MARKER}_Budget_Forecast_2026.txt": """
BUDGET FORECAST AND RESOURCE ALLOCATION -- FY 2026

Document ID: {m}-BFA-2026-001

PROJECTED MAINTENANCE BUDGET:
- Total FY2026 budget: $412,000
- Breakdown:
  - Parts and materials: $195,000 (47%)
  - Labor (technician travel + hours): $142,000 (34%)
  - Equipment and tools: $45,000 (11%)
  - Contingency reserve: $30,000 (7%)

PRIORITY CAPITAL INVESTMENTS:
1. Replace all rev D DSP boards (HR-7743) at SITE-ALPHA and SITE-BRAVO
   - Estimated cost: $67,000
   - Justification: rev D capacitor aging causing 11 failures/year
   - Expected savings: $33,000/year in reduced failures

2. Install environmental monitoring upgrade at SITE-CHARLIE
   - Estimated cost: $23,000
   - Justification: 85% RH exceedances causing HR-7742 corrosion
   - Expected savings: $24,000/year in reduced antenna feed failures

3. Procure 6 spare HR-7741 RF amplifiers for regional stock
   - Estimated cost: $41,000
   - Justification: 23 failures/year, 3-week lead time causing extended downtime
   - Expected savings: 340 hours/year reduced downtime

STAFFING:
- Current: 4 field technicians, 1 regional coordinator
- Proposed FY2026: Add 1 technician dedicated to SITE-ALPHA/SITE-BRAVO corridor
- Cost: $89,000 (salary + benefits + travel)
- ROI justification: Reduces average response time from 48 hours to 12 hours

RISK ITEMS:
- HR-7741 sole-source supplier may discontinue production in 2027
- SITE-CHARLIE lease renewal due July 2026; landlord requesting 18% increase
- Fiber optic backbone upgrade needed by Q3 2026 (current capacity at 67%)
""".format(m=MARKER),
}

# ---------------------------------------------------------------------------
# Queries with expected outcomes -- the scoring rubric
# ---------------------------------------------------------------------------

QUERIES = [
    # CATEGORY 1: Pure fact extraction (must come from sources)
    {
        "q": "Which site had the most visits in 2025?",
        "category": "fact_extraction",
        "expected_facts": ["SITE-ALPHA", "47"],
        "expected_refuse": False,
        "notes": "Direct lookup from site visit report",
    },
    {
        "q": "What is the MTBF for part HR-7741?",
        "category": "fact_extraction",
        "expected_facts": ["4,200", "hours"],
        "expected_refuse": False,
        "notes": "Direct lookup from parts failure log",
    },
    {
        "q": "What was SITE-ECHO's uptime in Q4 2025?",
        "category": "fact_extraction",
        "expected_facts": ["99.6"],
        "expected_refuse": False,
        "notes": "Direct lookup from performance metrics",
    },
    {
        "q": "What is the total FY2026 maintenance budget?",
        "category": "fact_extraction",
        "expected_facts": ["412,000"],
        "expected_refuse": False,
        "notes": "Direct lookup from budget forecast",
    },
    # CATEGORY 2: Cross-document synthesis
    {
        "q": "Is there a correlation between maintenance compliance rates and site uptime?",
        "category": "synthesis",
        "expected_facts": ["SITE-CHARLIE", "SITE-ECHO"],
        "expected_refuse": False,
        "notes": "Must combine maintenance schedule (compliance) + performance metrics (uptime)",
    },
    {
        "q": "Which site has the highest total cost considering both visit frequency and cost per visit?",
        "category": "synthesis",
        "expected_facts": ["SITE-ALPHA"],
        "expected_refuse": False,
        "notes": "Must multiply visits x cost_per_visit from site visit report",
    },
    # CATEGORY 3: Reasoning / inference
    {
        "q": "Based on the failure data and maintenance compliance, which site is most at risk of a major outage in 2026?",
        "category": "reasoning",
        "expected_facts": ["SITE-CHARLIE"],
        "expected_refuse": False,
        "notes": "Reasoning: CHARLIE has worst compliance (78%), worst uptime (94.3%), humidity issues, most HR-7742 failures",
    },
    {
        "q": "If the HR-7741 supplier discontinues production, what operational impact would you predict and what mitigation strategy would you recommend?",
        "category": "reasoning",
        "expected_facts": ["HR-7741"],
        "expected_refuse": False,
        "notes": "Must reason about 23 failures/year + sole source + lead time data",
    },
    # CATEGORY 4: Trend / pattern analysis
    {
        "q": "What trends in part failures are visible between 2024 and 2025, and what do they suggest?",
        "category": "trend_analysis",
        "expected_facts": ["HR-7741", "35%", "increased"],
        "expected_refuse": False,
        "notes": "Must reference year-over-year failure counts",
    },
    {
        "q": "Rank all 5 sites from best performing to worst performing, considering all available data.",
        "category": "trend_analysis",
        "expected_facts": ["SITE-ECHO"],
        "expected_refuse": False,
        "notes": "Must synthesize across all docs. ECHO = best (highest uptime, best compliance, fewest visits needed)",
    },
    # CATEGORY 5: Creative / open-ended
    {
        "q": "Write a one-paragraph executive recommendation for the FY2026 budget committee based on all the data.",
        "category": "creative",
        "expected_facts": [],
        "expected_refuse": False,
        "notes": "Should produce coherent narrative synthesizing all docs",
    },
    {
        "q": "If you had to cut $100,000 from the FY2026 budget, what would you recommend cutting and why?",
        "category": "creative",
        "expected_facts": [],
        "expected_refuse": False,
        "notes": "Should reason about ROI of each budget line item",
    },
    # CATEGORY 6: Unanswerable (must refuse)
    {
        "q": "What was the failure rate for part HR-9999?",
        "category": "unanswerable",
        "expected_facts": [],
        "expected_refuse": True,
        "notes": "HR-9999 does not exist in any document",
    },
    {
        "q": "How many visits did SITE-FOXTROT receive in 2025?",
        "category": "unanswerable",
        "expected_facts": [],
        "expected_refuse": True,
        "notes": "SITE-FOXTROT does not exist",
    },
]

# ---------------------------------------------------------------------------
# Settings to sweep
# ---------------------------------------------------------------------------

SETTINGS_SWEEP = [
    {"name": "STRICT-10", "grounding_bias": 10, "allow_open_knowledge": False, "temperature": 0.01},
    {"name": "STRICT-9",  "grounding_bias": 9,  "allow_open_knowledge": False, "temperature": 0.03},
    {"name": "STRICT-8",  "grounding_bias": 8,  "allow_open_knowledge": False, "temperature": 0.05},
    {"name": "GROUND-8",  "grounding_bias": 8,  "allow_open_knowledge": True,  "temperature": 0.05},
    {"name": "GROUND-7",  "grounding_bias": 7,  "allow_open_knowledge": True,  "temperature": 0.08},
    {"name": "BALANCED-7","grounding_bias": 7,  "allow_open_knowledge": True,  "temperature": 0.12},
    {"name": "BALANCED-6","grounding_bias": 6,  "allow_open_knowledge": True,  "temperature": 0.15},
    {"name": "CREATIVE-5","grounding_bias": 5,  "allow_open_knowledge": True,  "temperature": 0.20},
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

REFUSAL_PHRASES = [
    "not found", "no relevant", "no information", "does not contain",
    "no mention", "no data", "cannot answer", "no specific",
    "is not present", "not available in",
]


def score_answer(answer: str, query_spec: dict) -> dict:
    """Score a single answer against ground truth."""
    lower = answer.lower()
    facts = query_spec["expected_facts"]
    expect_refuse = query_spec["expected_refuse"]

    is_refused = any(p in lower for p in REFUSAL_PHRASES)
    fact_hits = sum(1 for f in facts if f.lower() in lower) if facts else 0
    fact_total = len(facts) if facts else 0
    has_gk = "[general knowledge]" in lower

    # Scoring:
    # - fact_extraction: full marks for all facts present, 0 for refusal
    # - synthesis/reasoning/trend: facts + answer length + no refusal
    # - creative: answer length > 200 + no refusal
    # - unanswerable: must refuse

    cat = query_spec["category"]
    if cat == "unanswerable":
        correct = is_refused
        score = 1.0 if correct else 0.0
    elif cat == "fact_extraction":
        if is_refused:
            score = 0.0
        elif fact_total > 0:
            score = fact_hits / fact_total
        else:
            score = 1.0
    elif cat in ("synthesis", "reasoning", "trend_analysis"):
        if is_refused:
            score = 0.0
        else:
            fact_score = (fact_hits / fact_total) if fact_total > 0 else 0.5
            length_score = min(len(answer) / 500, 1.0)
            score = 0.6 * fact_score + 0.4 * length_score
    elif cat == "creative":
        if is_refused:
            score = 0.0
        else:
            length_score = min(len(answer) / 500, 1.0)
            score = length_score
    else:
        score = 0.0

    return {
        "score": score,
        "fact_hits": fact_hits,
        "fact_total": fact_total,
        "is_refused": is_refused,
        "has_gk": has_gk,
        "answer_length": len(answer),
        "category": cat,
    }


# ---------------------------------------------------------------------------
# Index test documents
# ---------------------------------------------------------------------------

def index_test_corpus(config, embedder, store):
    """Index the test documents into the vector store."""
    chunker = Chunker(config.chunking)
    now = datetime.now(timezone.utc).isoformat()
    total_chunks = 0

    for filename, content in TEST_DOCUMENTS.items():
        # Check if already indexed
        fake_path = "EXPERIMENT/" + filename
        existing_hash = store.get_file_hash(fake_path)
        content_hash = "{}:0".format(len(content))
        if existing_hash == content_hash:
            print("  [SKIP] {} (already indexed)".format(filename))
            continue

        # Remove old chunks if re-indexing
        if existing_hash:
            store.delete_chunks_by_source(fake_path)

        # Chunk
        chunks = chunker.chunk_text(content.strip())
        if not chunks:
            print("  [WARN] {} produced 0 chunks".format(filename))
            continue

        # Embed
        embeddings = embedder.embed_batch(chunks)

        # Build metadata
        metadata_list = [
            ChunkMetadata(
                source_path=fake_path,
                chunk_index=i,
                text_length=len(c),
                created_at=now,
                access_tags=("shared",),
                access_tag_source="default_document_tags",
            )
            for i, c in enumerate(chunks)
        ]

        # Store
        store.add_embeddings(
            embeddings=embeddings,
            metadata_list=metadata_list,
            texts=chunks,
            file_hash=content_hash,
        )
        total_chunks += len(chunks)
        print("  [OK] {} -> {} chunks".format(filename, len(chunks)))

    return total_chunks


def cleanup_test_corpus(store):
    """Remove test documents from the vector store."""
    for filename in TEST_DOCUMENTS:
        fake_path = "EXPERIMENT/" + filename
        store.delete_chunks_by_source(fake_path)
    print("[OK] Cleaned up test corpus")


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment():
    config = load_config()
    apply_mode_to_config(config, "online")
    config.api.max_tokens = 2048

    creds = resolve_credentials(config, use_cache=False)
    if not creds.is_online_ready:
        print("[FAIL] No API credentials")
        sys.exit(1)

    configure_gate(mode="online", api_endpoint=creds.endpoint)

    store = VectorStore(config.paths.database)
    embedder = Embedder(dimension=768)

    # Step 1: Index test corpus
    print("=" * 70)
    print("STEP 1: Index Test Corpus")
    print("=" * 70)
    n = index_test_corpus(config, embedder, store)
    print("[OK] {} new chunks indexed".format(n))
    print()

    # Step 2: Sweep settings
    print("=" * 70)
    print("STEP 2: Settings Sweep ({} configs x {} queries = {} calls)".format(
        len(SETTINGS_SWEEP), len(QUERIES), len(SETTINGS_SWEEP) * len(QUERIES)))
    print("=" * 70)
    print()

    all_results = []
    total_cost = 0.0

    for si, setting in enumerate(SETTINGS_SWEEP):
        config.query.grounding_bias = setting["grounding_bias"]
        config.query.allow_open_knowledge = setting["allow_open_knowledge"]
        config.api.temperature = setting["temperature"]
        apply_query_mode_to_config(config)

        invalidate_deployment_cache()
        router = LLMRouter(config, credentials=creds)
        engine = QueryEngine(config, store, embedder, router)

        print("--- [{}/{}] {} (bias={}, open={}, temp={}) ---".format(
            si + 1, len(SETTINGS_SWEEP), setting["name"],
            setting["grounding_bias"], setting["allow_open_knowledge"],
            setting["temperature"]))

        config_scores = []

        for qi, qspec in enumerate(QUERIES):
            try:
                result = engine.query(qspec["q"])
                answer = getattr(result, "answer", "")
                sources = getattr(result, "sources", [])
                cost = getattr(result, "cost_usd", 0) or 0
                total_cost += cost

                s = score_answer(answer, qspec)
                s["config"] = setting["name"]
                s["question"] = qspec["q"][:60]
                s["answer_preview"] = answer[:120].replace("\n", " ")
                s["sources_count"] = len(sources)
                s["cost"] = cost
                config_scores.append(s)
                all_results.append(s)

                symbol = "+" if s["score"] >= 0.8 else ("~" if s["score"] >= 0.4 else "-")
                print("  {} Q{:02d} [{:.0f}%] {} | {} | {}ch | {}".format(
                    symbol, qi + 1, s["score"] * 100, s["category"][:8].ljust(8),
                    "REFUSED" if s["is_refused"] else "ANSWERED",
                    s["answer_length"], qspec["q"][:40]))

            except Exception as e:
                print("  X Q{:02d} [ERR] {} | {}".format(qi + 1, qspec["q"][:40], e))
                all_results.append({
                    "config": setting["name"], "question": qspec["q"][:60],
                    "score": 0, "category": qspec["category"], "error": str(e),
                })

        avg = sum(s["score"] for s in config_scores) / len(config_scores) if config_scores else 0
        print("  AVG SCORE: {:.1f}%".format(avg * 100))
        print()

    # Step 3: Results
    print("=" * 70)
    print("STEP 3: RESULTS MATRIX")
    print("=" * 70)
    print()

    # Per-config summary
    print("{:<14} {:>6} {:>6} {:>6} {:>6} {:>6} {:>6} {:>8}".format(
        "Config", "Fact%", "Synth%", "Reas%", "Trend%", "Creat%", "Unans%", "OVERALL"))
    print("-" * 70)

    config_summaries = {}
    for setting in SETTINGS_SWEEP:
        name = setting["name"]
        cr = [r for r in all_results if r.get("config") == name]
        cats = {}
        for cat in ["fact_extraction", "synthesis", "reasoning", "trend_analysis", "creative", "unanswerable"]:
            cat_results = [r for r in cr if r.get("category") == cat]
            cats[cat] = (sum(r["score"] for r in cat_results) / len(cat_results) * 100) if cat_results else 0

        overall = sum(r["score"] for r in cr) / len(cr) * 100 if cr else 0
        config_summaries[name] = {"cats": cats, "overall": overall}

        print("{:<14} {:>5.0f}% {:>5.0f}% {:>5.0f}% {:>5.0f}% {:>5.0f}% {:>5.0f}% {:>7.1f}%".format(
            name,
            cats["fact_extraction"], cats["synthesis"], cats["reasoning"],
            cats["trend_analysis"], cats["creative"], cats["unanswerable"],
            overall))

    # Find sweet spot
    print()
    best_name = max(config_summaries, key=lambda n: config_summaries[n]["overall"])
    best = config_summaries[best_name]
    print("SWEET SPOT: {} at {:.1f}% overall".format(best_name, best["overall"]))
    print()

    # Find best per category
    print("BEST PER CATEGORY:")
    for cat in ["fact_extraction", "synthesis", "reasoning", "trend_analysis", "creative", "unanswerable"]:
        best_cat = max(config_summaries, key=lambda n: config_summaries[n]["cats"][cat])
        print("  {}: {} ({:.0f}%)".format(cat, best_cat, config_summaries[best_cat]["cats"][cat]))

    dollar = chr(36)
    print()
    print("Total API cost: {}{:.4f}".format(dollar, total_cost))
    print("Total queries: {}".format(len(all_results)))

    # Save results
    outdir = PROJECT_ROOT / "logs" / "grounding_experiment"
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = outdir / "{}_sweet_spot_results.json".format(ts)
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "settings_sweep": SETTINGS_SWEEP,
            "config_summaries": config_summaries,
            "sweet_spot": best_name,
            "all_results": all_results,
            "total_cost": total_cost,
        }, f, indent=2, default=str)
    print("Results saved: {}".format(outfile))


if __name__ == "__main__":
    run_experiment()
