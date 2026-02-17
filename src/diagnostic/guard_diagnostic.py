#!/usr/bin/env python3
"""
guard_diagnostic.py -- Hallucination Guard Diagnostics (5 levels)
Config -> BIT -> NLI Model -> Golden Probes (69 claims, 13 STEM domains) -> Integration
Level 4 (probes) is critical: catches silent filter failures.

FILE: src/diagnostic/guard_diagnostic.py
NETWORK: NONE | VERSION: 1.0.0 | DATE: 2026-02-16
"""

from __future__ import annotations

import time
import logging
from typing import List, Tuple, Any

from . import TestResult, PROJ_ROOT

logger = logging.getLogger("diagnostic.guard")

def test_guard_config() -> TestResult:
    """Level 1: Is the guard configured? Catches YAML typos,
    missing sections, invalid threshold, bad failure_action."""
    try:
        from src.core.config import load_config
        config = load_config(str(PROJ_ROOT))

        guard_cfg = getattr(config, "hallucination_guard", None)
        if guard_cfg is None:
            return TestResult(
                "guard_config", "Hallucination Filter", "FAIL",
                "No hallucination_guard section in config",
                fix_hint="Add hallucination_guard to default_config.yaml",
            )

        enabled = getattr(guard_cfg, "enabled", False)
        threshold = getattr(guard_cfg, "threshold", 0.0)
        action = getattr(guard_cfg, "failure_action", "unknown")

        details = {
            "enabled": enabled, "threshold": threshold,
            "failure_action": action,
            "nli_model": getattr(guard_cfg, "nli_model", "not set"),
            "chunk_prune_k": getattr(guard_cfg, "chunk_prune_k", "?"),
        }

        if not (0.0 <= threshold <= 1.0):
            return TestResult(
                "guard_config", "Hallucination Filter", "FAIL",
                f"Invalid threshold: {threshold} (must be 0.0-1.0)",
                details,
                fix_hint="Set threshold between 0.0 and 1.0.",
            )

        valid_actions = {"block", "flag", "strip", "warn"}
        if action not in valid_actions:
            return TestResult(
                "guard_config", "Hallucination Filter", "WARN",
                f"Unknown failure_action: '{action}'", details,
                fix_hint=f"Use one of: {', '.join(sorted(valid_actions))}",
            )

        if enabled:
            return TestResult(
                "guard_config", "Hallucination Filter", "PASS",
                f"Filter ENABLED (threshold={threshold}, "
                f"action={action})", details,
            )
        else:
            return TestResult(
                "guard_config", "Hallucination Filter", "WARN",
                "Filter configured but DISABLED -- responses "
                "are NOT verified against sources.", details,
                fix_hint="rag-features enable hallucination-filter",
            )

    except Exception as e:
        return TestResult(
            "guard_config", "Hallucination Filter", "ERROR",
            f"Config check failed: {e}",
            fix_hint="Run from HybridRAG project root.")

def test_guard_bit() -> TestResult:
    """Level 2: Run 8 BIT checks on pure-Python guard components
    (claim extraction, prompt hardening, response construction, etc.)."""
    try:
        from src.core.hallucination_guard.startup_bit import run_bit
        passed, total, details = run_bit(verbose=False)

        detail_dict = {
            "passed": passed, "total": total, "results": details,
        }

        if passed == total:
            return TestResult(
                "guard_bit", "Hallucination Filter", "PASS",
                f"All {total} Built-In Tests passed", detail_dict,
            )
        elif passed >= total - 1:
            return TestResult(
                "guard_bit", "Hallucination Filter", "WARN",
                f"BIT: {passed}/{total} -- minor issues", detail_dict,
                fix_hint="python -m hallucination_guard --bit",
            )
        else:
            return TestResult(
                "guard_bit", "Hallucination Filter", "FAIL",
                f"BIT: {passed}/{total} -- guard components broken",
                detail_dict,
                fix_hint="python -m hallucination_guard --bit for details.",
            )

    except ImportError as e:
        return TestResult(
            "guard_bit", "Hallucination Filter", "SKIP",
            f"Guard package not installed: {e}",
            fix_hint="Copy hallucination_guard/ to src/core/",
        )
    except Exception as e:
        return TestResult(
            "guard_bit", "Hallucination Filter", "ERROR",
            f"BIT runner crashed: {e}",
        )

def test_guard_nli_model() -> TestResult:
    """Level 3: NLI model loads and produces valid 3-class output?
    Catches: missing cache, corrupt model, missing dependencies."""
    try:
        from src.core.hallucination_guard.nli_verifier import NLIVerifier

        verifier = NLIVerifier()
        t0 = time.time()
        loaded = verifier.load_model()
        load_s = time.time() - t0

        if not loaded:
            return TestResult(
                "guard_nli_model", "Hallucination Filter", "FAIL",
                "NLI model failed to load -- filter CANNOT verify claims",
                {"load_time_s": round(load_s, 2)},
                fix_hint="Download (~440MB) or copy .model_cache/ for air-gap.",
            )

        # Smoke test: must produce 3-class output
        pairs = [("The frequency is 1.3 GHz.",
                   "The system operates at 1.3 GHz.")]
        scores = verifier.model.predict(
            pairs, batch_size=1, show_progress_bar=False)

        if len(scores[0]) != 3:
            return TestResult(
                "guard_nli_model", "Hallucination Filter", "FAIL",
                f"Model output has {len(scores[0])} classes (expected 3)",
                fix_hint="Delete .model_cache/ and re-download.",
            )

        probs = verifier._softmax(scores[0])
        details = {
            "load_time_s": round(load_s, 2),
            "entailment": round(probs[1], 4),
            "contradiction": round(probs[0], 4),
            "neutral": round(probs[2], 4),
        }

        if probs[1] < 0.3:
            return TestResult(
                "guard_nli_model", "Hallucination Filter", "WARN",
                f"Model loaded but entailment score low ({probs[1]:.2f})",
                details,
                fix_hint="Model may be corrupted. Re-download.",
            )

        return TestResult(
            "guard_nli_model", "Hallucination Filter", "PASS",
            f"NLI model loaded in {load_s:.1f}s, smoke test "
            f"passed (entailment={probs[1]:.2f})", details,
        )

    except ImportError as e:
        return TestResult(
            "guard_nli_model", "Hallucination Filter", "FAIL",
            f"Missing dependency: {e}",
            fix_hint="pip install sentence-transformers --break-system-packages",
        )
    except Exception as e:
        return TestResult(
            "guard_nli_model", "Hallucination Filter", "ERROR",
            f"NLI model test crashed: {e}",
        )

def _probe_cache(cache_path, model_name, save_data=None):
    """Load or save probe cache. Returns cached data or None."""
    import json
    try:
        if save_data is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            save_data["model"] = model_name
            cache_path.write_text(json.dumps(save_data, indent=2),
                                  encoding="utf-8")
            return save_data
        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("model") == model_name:
                return data
    except Exception:
        pass
    return None

def test_guard_golden_probes(quick: bool = False) -> TestResult:
    """Feed known-true/false claims across 13 STEM domains.
    Batched (1 model call vs 69), cached to disk, quick mode available.
    CPU: ~1-3s first run, ~5ms cached. quick=True: 13 probes vs 69.
    CRITICAL FAILURE = wrong numbers pass through undetected."""
    try:
        from src.core.hallucination_guard.nli_verifier import NLIVerifier
        from src.core.hallucination_guard.golden_probes import (
            get_all_probes, get_domain_summary, PROBE_DOMAINS,
        )

        # --- Check cache first (instant if model unchanged) ---
        cache_path = PROJ_ROOT / ".probe_cache.json"
        summary = get_domain_summary()
        cache_key = "quick" if quick else "full"

        verifier = NLIVerifier()
        model_name = getattr(verifier, "model_name",
                             "nli-deberta-v3-base")

        cached = _probe_cache(cache_path, model_name)
        if cached and cache_key in cached:
            cd = cached[cache_key]
            return TestResult(
                "guard_golden_probes", "Hallucination Filter",
                cd["status"],
                cd["message"] + " [cached]",
                cd.get("details", {}),
                fix_hint=cd.get("fix_hint", ""),
            )

        # --- Load model ---
        if not verifier.load_model():
            return TestResult(
                "guard_golden_probes", "Hallucination Filter", "SKIP",
                "NLI model not available -- cannot run golden probes",
                fix_hint="Fix NLI model loading first.",
            )

        # --- Build probe set ---
        if quick:
            # Quick mode: 1 true + 1 false per domain = 26 probes
            pass_probes = []
            fail_probes = []
            for d in PROBE_DOMAINS:
                if d.should_pass:
                    c, r = d.should_pass[0]
                    pass_probes.append((d.source_text, c, r, d.display_name))
                if d.should_fail:
                    c, e, r = d.should_fail[0]
                    fail_probes.append((d.source_text, c, e, r, d.display_name))
        else:
            pass_probes, fail_probes = get_all_probes()

        # BATCH: One model.predict() call for all probes instead of
        # 69 separate calls. ~5-7x faster (saves per-call overhead).
        all_pairs = []
        pair_meta = []  # Track which probe each pair belongs to

        for source, claim, reason, domain in pass_probes:
            all_pairs.append((source, claim))
            pair_meta.append({
                "domain": domain, "claim": claim[:80],
                "expected": "SUPPORTED", "reason": reason,
                "is_pass_probe": True,
            })

        for source, claim, expected, reason, domain in fail_probes:
            all_pairs.append((source, claim))
            pair_meta.append({
                "domain": domain, "claim": claim[:80],
                "expected": expected, "reason": reason,
                "is_pass_probe": False,
            })

        # ONE model call for all probes
        batch_scores = verifier.model.predict(
            all_pairs,
            batch_size=min(32, len(all_pairs)),
            show_progress_bar=False,
        )

        # --- Process results ---
        true_pos = 0
        true_neg = 0
        false_neg = []
        false_pos = []
        domain_scores = {}
        all_results = []

        # NLI label indices (DeBERTa convention)
        IDX_CON, IDX_ENT, IDX_NEU = 0, 1, 2

        for i, (scores, meta) in enumerate(zip(batch_scores, pair_meta)):
            probs = verifier._softmax(scores)
            ent = probs[IDX_ENT]
            con = probs[IDX_CON]

            # Apply same decision logic as verify_claim_against_chunks
            if con > 0.70:
                got = "CONTRADICTED"
            elif ent > 0.50:
                got = "SUPPORTED"
            else:
                got = "UNSUPPORTED"

            if meta["is_pass_probe"]:
                ok = (got == "SUPPORTED")
                if ok:
                    true_pos += 1
                else:
                    false_pos.append({
                        "claim": meta["claim"], "got": got,
                        "domain": meta["domain"],
                        "reason": meta["reason"],
                    })
            else:
                ok = (got != "SUPPORTED")
                if ok:
                    true_neg += 1
                else:
                    sev = ("CRITICAL" if meta["expected"] == "CONTRADICTED"
                           else "HIGH")
                    false_neg.append({
                        "claim": meta["claim"],
                        "expected": meta["expected"], "got": got,
                        "domain": meta["domain"],
                        "reason": meta["reason"], "severity": sev,
                    })

            ds = domain_scores.setdefault(meta["domain"], {"p": 0, "t": 0})
            ds["t"] += 1
            if ok:
                ds["p"] += 1

            all_results.append({
                "domain": meta["domain"], "claim": meta["claim"],
                "expected": meta["expected"], "got": got,
                "ent": round(ent, 3), "con": round(con, 3), "ok": ok,
            })

        total = len(all_pairs)
        passed = true_pos + true_neg
        mode_label = "quick" if quick else "full"

        dom_report = {
            d: f"{s['p']}/{s['t']} ({s['p']/s['t']*100:.0f}%)"
            for d, s in domain_scores.items() if s["t"] > 0
        }

        details = {
            "mode": mode_label,
            "total_probes": total, "passed": passed,
            "true_positives": true_pos, "true_negatives": true_neg,
            "false_neg_count": len(false_neg),
            "false_pos_count": len(false_pos),
            "domains_tested": summary["domain_count"],
            "domain_scores": dom_report,
            "false_negatives": false_neg,
            "false_positives": false_pos,
            "all_probes": all_results,
        }

        # --- Build result ---
        critical = [fn for fn in false_neg if fn["severity"] == "CRITICAL"]

        if critical:
            doms = set(c["domain"] for c in critical)
            result = TestResult(
                "guard_golden_probes", "Hallucination Filter", "FAIL",
                f"CRITICAL: {len(critical)} wrong numbers passed "
                f"undetected in: {', '.join(doms)}. DO NOT TRUST "
                f"this filter for engineering work.",
                details,
                fix_hint="Check threshold, model files, softmax.",
            )
        elif false_neg:
            result = TestResult(
                "guard_golden_probes", "Hallucination Filter", "WARN",
                f"Missed {len(false_neg)} fabrications "
                f"({passed}/{total} probes, "
                f"{summary['domain_count']} domains).",
                details,
                fix_hint="Lower entailment threshold or enable dual-path.",
            )
        elif false_pos:
            result = TestResult(
                "guard_golden_probes", "Hallucination Filter", "WARN",
                f"Wrongly rejected {len(false_pos)} true claims "
                f"({passed}/{total}). Filter may be too aggressive.",
                details,
                fix_hint="Raise entailment threshold or check claim extraction.",
            )
        else:
            result = TestResult(
                "guard_golden_probes", "Hallucination Filter", "PASS",
                f"ALL {total} golden probes passed across "
                f"{summary['domain_count']} STEM domains -- "
                f"{true_pos} true accepted, "
                f"{true_neg} fabrications caught.",
                details,
            )

        # --- Cache for instant repeat runs ---
        cache_data = cached if cached else {}
        cache_data[cache_key] = {
            "status": result.status,
            "message": result.message,
            "details": details,
            "fix_hint": result.fix_hint,
        }
        _probe_cache(cache_path, model_name, save_data=cache_data)

        return result

    except ImportError as e:
        return TestResult(
            "guard_golden_probes", "Hallucination Filter", "SKIP",
            f"Guard or probes not available: {e}",
            fix_hint="Copy golden_probes.py to hallucination_guard/",
        )
    except Exception as e:
        return TestResult(
            "guard_golden_probes", "Hallucination Filter", "ERROR",
            f"Golden probe test crashed: {e}",
        )

def test_guard_integration() -> TestResult:
    """Level 5: Is GroundedQueryEngine wired into QueryEngine?"""
    try:
        from src.core.grounded_query_engine import GroundedQueryEngine
        from src.core.query_engine import QueryEngine

        if not issubclass(GroundedQueryEngine, QueryEngine):
            return TestResult(
                "guard_integration", "Hallucination Filter", "FAIL",
                "GroundedQueryEngine does not extend QueryEngine",
            )

        attrs = dir(GroundedQueryEngine)
        missing = []
        if not hasattr(GroundedQueryEngine, "guard_enabled"):
            missing.append("guard_enabled toggle")
        if not any("verify" in n.lower() for n in attrs):
            missing.append("verify method")
        if not any("grounded" in n.lower() or "harden" in n.lower() for n in attrs):
            missing.append("prompt hardening")
        if missing:
            return TestResult("guard_integration", "Hallucination Filter",
                              "FAIL", f"Missing: {', '.join(missing)}")

        return TestResult(
            "guard_integration", "Hallucination Filter", "PASS",
            "GroundedQueryEngine extends QueryEngine with toggle, "
            "verification, and prompt hardening.",
        )

    except ImportError as e:
        return TestResult(
            "guard_integration", "Hallucination Filter", "SKIP",
            f"Cannot import: {e}",
            fix_hint="Copy grounded_query_engine.py to src/core/",
        )
    except Exception as e:
        return TestResult(
            "guard_integration", "Hallucination Filter", "ERROR",
            f"Integration check crashed: {e}",
        )

def get_guard_tests(include_golden_probes: bool = True,
                    quick: bool = False):
    """Guard test tuples for hybridrag_diagnostic.py.
    quick=True: 13 probes (demo). Full: 69 probes. Cached: ~5ms."""
    tests = [
        ("Filter: Config",      test_guard_config),
        ("Filter: BIT",         test_guard_bit),
        ("Filter: Integration", test_guard_integration),
    ]
    if include_golden_probes:
        tests.extend([
            ("Filter: NLI Model",     test_guard_nli_model),
            ("Filter: Golden Probes",
             lambda: test_guard_golden_probes(quick=quick)),
        ])
    return tests
