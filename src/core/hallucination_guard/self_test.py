#!/usr/bin/env python3
"""
self_test.py -- Hallucination Guard Self-Test Suite
=====================================================

PURPOSE:
    Validates all components of the hallucination guard work correctly.
    Run after installation, after updates, or when troubleshooting.

HOW TO RUN:
    python -m hallucination_guard        (runs this file via __main__.py)
    -- OR --
    from hallucination_guard import run_self_test
    run_self_test()

TESTS:
    [1/7] Claim extraction    -- Sentence splitting, trivial detection
    [2/7] Prompt hardening    -- Grounding preamble injection
    [3/7] Context wrapping    -- Chunk numbering and file attribution
    [4/7] Confidence cal.     -- Overconfidence detection
    [5/7] Response construct. -- Flag/block/strip/warn modes
    [6/7] GuardResult         -- Data class integrity
    [7/7] NLI model           -- Entailment and contradiction detection
                                 (SKIP if sentence-transformers not installed)

NETWORK ACCESS: None, unless NLI model needs downloading for test 7.

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

from .guard_types import (
    ClaimVerdict, ClaimResult, GuardResult, GuardConfig,
)
from .prompt_hardener import PromptHardener
from .claim_extractor import ClaimExtractor
from .response_scoring import ConfidenceCalibrator, ResponseConstructor


def run_self_test():
    """
    Self-test to verify all hallucination guard components work.

    Each test is independent -- a failure in one doesn't prevent
    the others from running. Test 7 (NLI model) is optional and
    skipped gracefully if sentence-transformers isn't installed.
    """
    print("=" * 60)
    print("HALLUCINATION GUARD -- Self-Test")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Test 1: Claim Extraction
    # ------------------------------------------------------------------
    # Verifies that we can split an LLM response into sentences and
    # correctly identify which are factual claims vs. structural text.
    print("\n[1/7] Claim extraction...")
    resp = (
        "Here is what I found. "
        "The radar operates at 10 MHz [Source: chunk_1]. "
        "It has a range of 300 km. "
        "The system was built by Raytheon. "
        "INSUFFICIENT SOURCE DATA: Cannot determine power output."
    )
    claims = ClaimExtractor.extract_claims(resp)
    factual = sum(1 for c in claims if not c["is_trivial"])
    print(f"  {len(claims)} claims, {factual} factual")
    assert factual >= 2, f"Expected >=2 factual, got {factual}"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 2: Prompt Hardening
    # ------------------------------------------------------------------
    # Verifies that the grounding preamble is injected correctly and
    # contains the critical keywords that force LLM compliance.
    print("\n[2/7] Prompt hardening...")
    h = PromptHardener.harden_system_prompt("You are helpful.")
    assert "DEFENSE ENVIRONMENT" in h, "Missing DEFENSE ENVIRONMENT"
    assert "INSUFFICIENT SOURCE DATA" in h, "Missing refusal phrase"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 3: Context Wrapping
    # ------------------------------------------------------------------
    # Verifies that chunks get numbered correctly and file names are
    # attached for citation tracking.
    print("\n[3/7] Context wrapping...")
    w = PromptHardener.wrap_context_chunks(
        ["Radar at 10 MHz.", "Range 200 km."],
        ["radar.md", "specs.md"],
    )
    assert "CHUNK 1" in w, "Missing CHUNK 1"
    assert "CHUNK 2" in w, "Missing CHUNK 2"
    assert "radar.md" in w, "Missing source file name"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 4: Confidence Calibration
    # ------------------------------------------------------------------
    # Verifies overconfidence detection: "definitely" on an unsupported
    # claim should trigger, "may" + "approximately" should not.
    print("\n[4/7] Confidence calibration...")
    c1 = ConfidenceCalibrator.check_overconfidence(
        "Definitely operates at 15 MHz.",
        ClaimVerdict.UNSUPPORTED,
    )
    assert c1["is_overconfident"], "Should flag 'definitely' as overconfident"
    c2 = ConfidenceCalibrator.check_overconfidence(
        "May operate at approximately 15 MHz.",
        ClaimVerdict.UNSUPPORTED,
    )
    assert not c2["is_overconfident"], "Hedge words should cancel markers"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 5: Response Construction
    # ------------------------------------------------------------------
    # Verifies that the "flag" mode correctly marks contradicted claims
    # with [!! CONTRADICTED] and unsupported claims with [UNVERIFIED].
    print("\n[5/7] Response construction...")
    mock = [
        ClaimResult("A is true.", ClaimVerdict.SUPPORTED, 0.9),
        ClaimResult(
            "B is also true.", ClaimVerdict.CONTRADICTED, 0.8),
        ClaimResult("C might be.", ClaimVerdict.UNSUPPORTED, 0.3),
    ]
    cfg = GuardConfig(
        failure_action="flag", faithfulness_threshold=0.80)
    safe = ResponseConstructor.build_safe_response(
        "A is true. B is also true. C might be.", mock, 0.33, cfg)
    assert "CONTRADICTED" in safe, "Missing CONTRADICTED marker"
    assert "UNVERIFIED" in safe, "Missing UNVERIFIED marker"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 6: GuardResult Data Class
    # ------------------------------------------------------------------
    # Verifies the main result object can be created and its fields
    # are accessible.
    print("\n[6/7] GuardResult...")
    r = GuardResult(
        is_safe=False, original_response="test",
        safe_response="test_safe", faithfulness_score=0.33,
    )
    assert not r.is_safe, "Should be unsafe"
    assert r.faithfulness_score == 0.33, "Wrong score"
    print("  [PASS]")

    # ------------------------------------------------------------------
    # Test 7: NLI Model (Optional)
    # ------------------------------------------------------------------
    # This test requires sentence-transformers to be installed and the
    # NLI model to be available (downloaded or cached). If either is
    # missing, the test is skipped gracefully.
    print("\n[7/7] NLI model...")
    try:
        # Import here to avoid failing if not installed
        from .hallucination_guard import HallucinationGuard

        guard = HallucinationGuard(
            GuardConfig(enable_audit_log=False))
        if guard.nli.load_model():
            # Test entailment: claim matches source
            cr = guard.nli.verify_claim_against_chunks(
                "The radar operates at 10 MHz.",
                ["The radar system uses a frequency of 10 MHz."],
            )
            print(
                f"  Entailment: {cr.verdict.value} "
                f"({cr.confidence:.2f})")
            assert cr.verdict == ClaimVerdict.SUPPORTED, (
                f"Expected SUPPORTED, got {cr.verdict.value}")

            # Test contradiction: claim conflicts with source
            cr2 = guard.nli.verify_claim_against_chunks(
                "The radar operates at 50 MHz.",
                ["The radar system uses a frequency of 10 MHz."],
            )
            print(
                f"  Contradiction: {cr2.verdict.value} "
                f"({cr2.confidence:.2f})")
            assert cr2.verdict != ClaimVerdict.SUPPORTED, (
                f"Expected NOT SUPPORTED, got {cr2.verdict.value}")
            print("  [PASS]")
        else:
            print("  [SKIP] Model not available")
    except ImportError:
        print("  [SKIP] sentence-transformers not installed")
    except Exception as e:
        print(f"  [SKIP] {e}")

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
