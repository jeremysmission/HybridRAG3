#!/usr/bin/env python3
"""
response_scoring.py -- Layers 3-4: Confidence Calibration & Response Construction
===================================================================================

PURPOSE:
    After NLI verification produces a verdict for each claim, this module:
    1. Detects overconfident language on unverified claims (Layer 4)
    2. Builds the safe response based on the failure_action setting (Layer 3)

    These are grouped together because they both operate on the claim_results
    list AFTER NLI verification is complete. They transform raw verdicts into
    the final user-facing response.

LAYER 4 -- CONFIDENCE CALIBRATION:
    The most dangerous hallucinations are CONFIDENT ones. Compare:
        "The system DEFINITELY operates at 15 MHz" (source says 10 MHz)
        "The system may operate around 15 MHz"     (source says 10 MHz)
    Both are wrong, but the first one will be acted on without question.
    Sonnet is especially prone to confident hallucination vs. Llama3.

LAYER 3 -- RESPONSE CONSTRUCTION:
    Based on the failure_action setting, builds the safe response:
        "block" = Return error message, hide response entirely
        "flag"  = Show response with [UNVERIFIED] / [CONTRADICTED] markers
        "strip" = Remove unverified claims, show only verified content
        "warn"  = Show full response with warning header

NETWORK ACCESS: None. This module is 100% offline, pure string processing.

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

from .guard_types import (
    ClaimVerdict, ClaimResult, GuardConfig,
    HEDGE_WORDS, OVERCONFIDENCE_MARKERS,
)
from .claim_extractor import ClaimExtractor


# =============================================================================
# LAYER 4: CONFIDENCE CALIBRATION
# =============================================================================

class ConfidenceCalibrator:
    """
    Detects when the LLM is overconfident about unverified claims.

    THE PROBLEM:
        Online LLMs (online LLM, GPT-4) are trained to sound confident.
        When they hallucinate, they hallucinate CONFIDENTLY. This module
        catches the pattern: strong language + no source backing = danger.

    DETECTION LOGIC:
        1. Check for OVERCONFIDENCE_MARKERS (definitely, certainly, always...)
        2. Check for HEDGE_WORDS (may, might, approximately, sources indicate...)
        3. If markers present AND no hedging on an unverified claim -> flag it
        4. Severity escalation:
           - CONTRADICTED + overconfident = HIGH (worst case: confident lie)
           - UNSUPPORTED + 2+ markers = HIGH
           - UNSUPPORTED + 1 marker = MEDIUM
           - UNSUPPORTED + no markers = LOW

    All methods are @staticmethod -- no state needed.
    """

    @staticmethod
    def check_overconfidence(claim_text, verdict):
        """
        Check if an unverified claim uses overconfident language.

        WHY WE ONLY CHECK UNVERIFIED/CONTRADICTED:
            If a claim is SUPPORTED by sources, confident language is fine.
            "The radar definitely operates at 10 MHz" is actually accurate
            if the source says 10 MHz. We only worry about confidence
            when the claim is NOT backed by sources.

        PARAMETERS:
            claim_text: str          -- The sentence to analyze
            verdict:    ClaimVerdict -- The NLI verdict for this claim

        RETURNS:
            dict with:
                is_overconfident: bool       -- True if flagged
                markers_found:   list[str]   -- Which bad words were found
                has_hedging:     bool         -- True if hedge words present
                severity:        str          -- "none" / "low" / "medium" / "high"
        """
        text_lower = claim_text.lower()

        # SUPPORTED or TRIVIAL claims: confident language is acceptable
        if verdict in (ClaimVerdict.SUPPORTED, ClaimVerdict.TRIVIAL):
            return {
                "is_overconfident": False,
                "markers_found": [],
                "has_hedging": False,
                "severity": "none",
            }

        # Find overconfidence markers in the claim
        markers = [m for m in OVERCONFIDENCE_MARKERS if m in text_lower]

        # Find hedge words (these OFFSET the overconfidence markers)
        hedges = [h for h in HEDGE_WORDS if h in text_lower]

        # Overconfident = has confidence markers but NO hedging
        is_oc = len(markers) > 0 and len(hedges) == 0

        # Determine severity based on verdict + marker count
        if verdict == ClaimVerdict.CONTRADICTED and len(markers) > 0:
            # Worst case: source says X, LLM "definitely" says Y
            sev = "high"
        elif verdict == ClaimVerdict.CONTRADICTED:
            # Still bad: contradiction even without strong language
            sev = "high"
        elif is_oc and len(markers) >= 2:
            # Double-down overconfidence on unsupported claim
            sev = "high"
        elif is_oc:
            # Single overconfidence marker on unsupported claim
            sev = "medium"
        elif verdict == ClaimVerdict.UNSUPPORTED:
            # Unsupported but at least not using strong language
            sev = "low"
        else:
            sev = "none"

        return {
            "is_overconfident": is_oc,
            "markers_found": markers,
            "has_hedging": len(hedges) > 0,
            "severity": sev,
        }


# =============================================================================
# LAYER 3: RESPONSE CONSTRUCTION
# =============================================================================

class ResponseConstructor:
    """
    Builds the safe response based on verification results.

    This is where the rubber meets the road -- we take all the claim-level
    verdicts and produce the actual text the user will see. The behavior
    depends on the failure_action setting in GuardConfig:

    MODES:
        "block"  -- Return error message, hide the response entirely.
                    Best for: production systems where false info is unacceptable.
        "flag"   -- Show response with [UNVERIFIED] / [!! CONTRADICTED] markers.
                    Best for: analyst review workflows (DEFAULT).
        "strip"  -- Remove unverified claims, show only verified content.
                    Best for: automated pipelines that need clean output.
        "warn"   -- Show full response with warning header.
                    Best for: exploration/research where context is needed.

    All methods are @staticmethod -- no state needed.
    """

    @staticmethod
    def build_safe_response(original, claim_results, score, config):
        """
        Build the safe response based on faithfulness score and config.

        LOGIC:
            1. If score >= threshold AND no contradictions -> return original
            2. If score >= threshold BUT has contradictions -> flag just those
            3. If score < threshold -> apply failure_action

        PARAMETERS:
            original:      str              -- The raw LLM response text
            claim_results: list[ClaimResult] -- Verification results per claim
            score:         float             -- Faithfulness score (0.0-1.0)
            config:        GuardConfig       -- Settings (threshold, action)

        RETURNS:
            str -- The modified (safe) response text
        """
        is_safe = score >= config.faithfulness_threshold

        if is_safe:
            # Even if overall score passes, flag any contradictions
            contras = [cr for cr in claim_results
                       if cr.verdict == ClaimVerdict.CONTRADICTED]
            if not contras:
                return original  # Clean pass -- return as-is
            # Has contradictions despite passing score: flag just those
            return ResponseConstructor._flag_claims(
                original, claim_results, only_contradictions=True)

        # Score below threshold -- apply the configured action
        action = config.failure_action
        if action == "block":
            return ResponseConstructor._block_msg(
                score, claim_results, config)
        elif action == "strip":
            return ResponseConstructor._strip_claims(
                original, claim_results)
        elif action == "warn":
            return ResponseConstructor._warn_header(
                original, score, claim_results)
        else:  # "flag" (default)
            return ResponseConstructor._flag_claims(
                original, claim_results)

    @staticmethod
    def _block_msg(score, results, config):
        """
        Generate a block message when the response is completely rejected.

        Shows the user:
            - The faithfulness score vs threshold
            - How many claims were contradicted and unsupported
            - The specific contradicted claims and why
            - Three options for what to do next
        """
        contras = [cr for cr in results
                   if cr.verdict == ClaimVerdict.CONTRADICTED]
        unsup = [cr for cr in results
                 if cr.verdict == ClaimVerdict.UNSUPPORTED]
        msg = (
            "== RESPONSE BLOCKED BY HALLUCINATION GUARD ==\n\n"
            f"Faithfulness Score: {score:.2f} "
            f"(threshold: {config.faithfulness_threshold:.2f})\n"
            f"Contradicted Claims: {len(contras)}\n"
            f"Unsupported Claims: {len(unsup)}\n\n"
            "The response contained claims not verified against source "
            "docs.\n"
            "OPTIONS:\n"
            "1. Rephrase your query more specifically\n"
            "2. Check if relevant documents are indexed\n"
            "3. Use offline mode (Llama3) for conservative response\n\n"
        )
        if contras:
            msg += "CONTRADICTED CLAIMS:\n"
            for cr in contras:
                msg += (
                    f"  [X] {cr.claim_text}\n"
                    f"      {cr.explanation}\n\n"
                )
        if unsup:
            msg += "UNSUPPORTED CLAIMS (first 5):\n"
            for cr in unsup[:5]:
                msg += f"  [?] {cr.claim_text}\n"
        return msg

    @staticmethod
    def _flag_claims(original, results, only_contradictions=False):
        """
        Add inline markers to the response text.

        Contradicted claims get: [!! CONTRADICTED - explanation] claim_text
        Unsupported claims get:  [UNVERIFIED] claim_text

        The original text is modified in-place using string replacement.
        """
        flagged = original
        for cr in results:
            if cr.verdict == ClaimVerdict.CONTRADICTED:
                marker = (
                    f"[!! CONTRADICTED - {cr.explanation}] "
                    f"{cr.claim_text}"
                )
                flagged = flagged.replace(cr.claim_text, marker, 1)
            elif (cr.verdict == ClaimVerdict.UNSUPPORTED
                  and not only_contradictions):
                flagged = flagged.replace(
                    cr.claim_text,
                    f"[UNVERIFIED] {cr.claim_text}",
                    1,
                )
        return flagged

    @staticmethod
    def _strip_claims(original, results):
        """
        Remove unverified and contradicted claims, keep only verified ones.

        If ALL claims are removed, returns a helpful message instead of
        an empty string. Also appends a note about how many claims were removed.
        """
        sentences = ClaimExtractor.split_into_sentences(original)

        # Build set of bad claim texts for fast lookup
        bad = set()
        for cr in results:
            if cr.verdict in (ClaimVerdict.CONTRADICTED,
                              ClaimVerdict.UNSUPPORTED):
                bad.add(cr.claim_text)

        # Keep only sentences whose cleaned text isn't in the bad set
        kept = []
        for s in sentences:
            clean = ClaimExtractor.CITATION_PATTERN.sub("", s).strip()
            clean = clean.replace("[UNSOURCED INFERENCE]", "").strip()
            if clean not in bad:
                kept.append(s)

        if not kept:
            return (
                "[All claims unverified. Source docs may not contain "
                "relevant information. Try rephrasing or check the index.]"
            )

        removed = len(sentences) - len(kept)
        result = " ".join(kept)
        if removed > 0:
            result += (
                f"\n\n[Note: {removed} claim(s) removed -- could not "
                f"be verified against source documents.]"
            )
        return result

    @staticmethod
    def _warn_header(original, score, results):
        """
        Prepend a warning header but show the full response.

        Used for research/exploration where the user wants to see everything
        but needs to know the verification status.
        """
        c = sum(1 for cr in results
                if cr.verdict == ClaimVerdict.CONTRADICTED)
        u = sum(1 for cr in results
                if cr.verdict == ClaimVerdict.UNSUPPORTED)
        return (
            "== HALLUCINATION GUARD WARNING ==\n"
            f"Faithfulness: {score:.2f} | "
            f"Contradicted: {c} | Unsupported: {u}\n"
            "Cross-check critical facts against source documents.\n"
            "=" * 40 + "\n\n" + original
        )
