#!/usr/bin/env python3
"""
startup_bit.py -- Built-In Tests (BIT) for Hallucination Guard
================================================================

PURPOSE:
    Runs 8 quick sanity checks every time the guard starts up.
    These verify all pure-Python components work correctly WITHOUT
    loading the 440MB NLI model (which is tested separately).

    If any BIT fails, the guard logs a warning but does NOT crash --
    it degrades gracefully so the rest of HybridRAG still works.

WHEN THESE RUN:
    - Automatically on first import of hallucination_guard
    - On demand via: python -m hallucination_guard --bit
    - On demand via: from hallucination_guard.startup_bit import run_bit

WHAT THEY TEST:
    BIT-1: Claim extraction (sentence splitting)
    BIT-2: Trivial sentence detection
    BIT-3: Citation marker extraction
    BIT-4: Prompt hardening
    BIT-5: Overconfidence detection
    BIT-6: Safe response construction (all 4 modes)
    BIT-7: Configuration defaults
    BIT-8: Guard types and enums

RUNTIME: < 50ms total (no model loading, no I/O, no network)

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.1.0
DATE: 2026-02-14
"""

import logging
from .claim_extractor import ClaimExtractor
from .prompt_hardener import PromptHardener
from .response_scoring import ConfidenceCalibrator, ResponseConstructor
from .guard_types import (
    ClaimVerdict, ClaimResult, GuardResult, GuardConfig,
)

logger = logging.getLogger("hallucination_guard.bit")


def run_bit(verbose=False):
    """
    Run all 8 Built-In Tests. Returns (passed_count, total_count, details).

    PARAMETERS:
        verbose: bool -- If True, print results to console

    RETURNS:
        tuple: (passed: int, total: int, details: list[str])
        Each detail is "[OK] ..." or "[FAIL] ..." for one check.
    """
    results = []  # list of (name, passed, detail_string)

    # ---------------------------------------------------------------
    # BIT-1: Claim extraction splits sentences correctly
    # Validates the Feb 2026 redesign that fixed "MHz." abbreviation bug
    # ---------------------------------------------------------------
    try:
        text = "The system operates at 300 MHz. It uses AES-256 encryption."
        claims = ClaimExtractor.extract_claims(text)
        ok = len(claims) == 2
        results.append(("BIT-1 Claim Extraction",
                         ok, f"Got {len(claims)} claims (expected 2)"))
    except Exception as e:
        results.append(("BIT-1 Claim Extraction", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-2: Trivial sentence detection
    # NOTE: "Based on the provided context..." has enough structure
    #       that the claim extractor considers it potentially factual.
    #       Only clearly non-factual patterns (questions, headings,
    #       very short filler) are categorized as trivial.
    # ---------------------------------------------------------------
    try:
        trivials = [
            "What frequency does it use?",
            "# Heading",
            "I hope this helps with your question.",
        ]
        factuals = [
            "The antenna gain is 6 dBi at 300 MHz.",
        ]
        all_ok = True
        for t in trivials:
            if ClaimExtractor.is_factual_claim(t):
                all_ok = False
        for f in factuals:
            if not ClaimExtractor.is_factual_claim(f):
                all_ok = False
        results.append(("BIT-2 Trivial Detection",
                         all_ok, "Trivial/factual classification correct"))
    except Exception as e:
        results.append(("BIT-2 Trivial Detection", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-3: Citation marker extraction
    # ---------------------------------------------------------------
    try:
        text = "Freq is 300 MHz. [Source: chunk_1] Gain is 6 dBi. [Source: chunk_2]"
        claims = ClaimExtractor.extract_claims(text)
        has_cites = any(c["cited_chunks"] for c in claims)
        results.append(("BIT-3 Citation Extraction",
                         has_cites, "Citation markers extracted"))
    except Exception as e:
        results.append(("BIT-3 Citation Extraction", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-4: Prompt hardening
    # ---------------------------------------------------------------
    try:
        pkg = PromptHardener.build_hardened_prompt(
            "You are helpful.", "What freq?", ["chunk text"], ["test.pdf"])
        ok = ("system" in pkg and "user" in pkg
              and "ONLY USE INFORMATION" in pkg["system"]
              and "CHUNK 1" in pkg["user"])
        results.append(("BIT-4 Prompt Hardening", ok, "Hardened prompt correct"))
    except Exception as e:
        results.append(("BIT-4 Prompt Hardening", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-5: Overconfidence detection
    # ---------------------------------------------------------------
    try:
        cal = ConfidenceCalibrator.check_overconfidence(
            "It is absolutely certain this is true.",
            ClaimVerdict.UNSUPPORTED)
        ok = cal["is_overconfident"]
        results.append(("BIT-5 Overconfidence",
                         ok, "Overconfident claim detected"))
    except Exception as e:
        results.append(("BIT-5 Overconfidence", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-6: Safe response construction (all 4 modes)
    # ---------------------------------------------------------------
    try:
        bad_claims = [
            ClaimResult("Bad", ClaimVerdict.CONTRADICTED, 0.9),
            ClaimResult("Good", ClaimVerdict.SUPPORTED, 0.8),
        ]
        all_ok = True
        for mode in ["block", "flag", "strip", "warn"]:
            cfg = GuardConfig(failure_action=mode)
            resp = ResponseConstructor.build_safe_response(
                "Bad. Good.", bad_claims, 0.5, cfg)
            if not resp:
                all_ok = False
        results.append(("BIT-6 Response Construction",
                         all_ok, "All 4 failure modes produce output"))
    except Exception as e:
        results.append(("BIT-6 Response Construction", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-7: Configuration defaults
    # ---------------------------------------------------------------
    try:
        cfg = GuardConfig()
        ok = (cfg.faithfulness_threshold == 0.80
              and cfg.failure_action == "flag"
              and cfg.max_claims_per_response == 50)
        results.append(("BIT-7 Config Defaults", ok, "Defaults correct"))
    except Exception as e:
        results.append(("BIT-7 Config Defaults", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # BIT-8: Guard types and enums
    # ---------------------------------------------------------------
    try:
        ok = (ClaimVerdict.SUPPORTED.value == "SUPPORTED"
              and ClaimVerdict.CONTRADICTED.value == "CONTRADICTED"
              and ClaimVerdict.UNSUPPORTED.value == "UNSUPPORTED"
              and ClaimVerdict.TRIVIAL.value == "TRIVIAL")
        results.append(("BIT-8 Guard Types", ok, "Enum values correct"))
    except Exception as e:
        results.append(("BIT-8 Guard Types", False, f"Exception: {e}"))

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    details = []
    for name, ok, detail in results:
        status = "[OK]" if ok else "[FAIL]"
        line = f"  {status} {name}: {detail}"
        details.append(line)
        if verbose:
            print(line)

    if verbose:
        print(f"\n  BIT: {passed}/{total} passed")

    if passed < total:
        failures = [name for name, ok, _ in results if not ok]
        logger.warning(
            "BIT failures: %s (%d/%d passed). "
            "Guard may produce incorrect results.",
            ", ".join(failures), passed, total)
    else:
        logger.debug("BIT: all %d tests passed", total)

    return passed, total, details
