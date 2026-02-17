#!/usr/bin/env python3
"""
hallucination_guard.py -- Main Orchestrator & Convenience API
==============================================================

PURPOSE:
    This is the entry point for the hallucination guard system.
    It ties all 5 layers together into one clean verify() call:

        Layer 1: Prompt Hardening   (prompt_hardener.py)
        Layer 2: Claim Extraction   (claim_extractor.py)
        Layer 2: NLI Verification   (nli_verifier.py)
        Layer 3: Response Scoring   (response_scoring.py)
        Layer 4: Confidence Check   (response_scoring.py)
        Layer 5: Dual-Path Consensus (dual_path.py, optional)

    Plus convenience one-liners for quick integration:
        guard_response()          -- Verify in one line
        harden_prompt()           -- Harden a prompt in one line
        init_hallucination_guard() -- Pre-load NLI model at startup

USAGE (query_engine.py integration):
    from hallucination_guard import guard_response, harden_prompt

    # Step 1: Harden the prompt before calling the LLM
    pkg = harden_prompt(system_prompt, query, chunks, source_files)
    response = api_call(system=pkg["system"], user=pkg["user"])

    # Step 2: Verify the LLM response after it comes back
    result = guard_response(response, chunks, query)
    if result.is_safe:
        return result.original_response
    else:
        return result.safe_response

NETWORK ACCESS:
    - NLI model download on first run (~440MB from huggingface.co)
    - All subsequent runs are 100% offline
    - KILL SWITCH: HALLUCINATION_GUARD_OFFLINE=1

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime

# Import all components from this package
from .guard_types import (
    ClaimVerdict, ClaimResult, GuardResult, GuardConfig,
    LOG_FORMAT, LOG_DATE_FORMAT,
)
from .prompt_hardener import PromptHardener
from .claim_extractor import ClaimExtractor
from .nli_verifier import NLIVerifier
from .response_scoring import ConfidenceCalibrator, ResponseConstructor


# =============================================================================
# MAIN ENGINE: HALLUCINATION GUARD
# =============================================================================

class HallucinationGuard:
    """
    The main orchestrator tying all 5 layers together.

    LIFECYCLE:
        1. Create:   guard = HallucinationGuard(config)
        2. Verify:   result = guard.verify(llm_response, chunks, query)
        3. Decide:   if result.is_safe -> show original, else -> show safe_response

    The NLI model is loaded lazily on the first verify() call.
    After that, each verification takes ~500ms-1s on CPU.
    """

    def __init__(self, config=None):
        """
        Initialize the guard with configuration.

        PARAMETERS:
            config: GuardConfig -- All settings. If None, reads from
                    environment variables (GuardConfig.from_env()).
        """
        self.config = config or GuardConfig.from_env()
        self.nli = NLIVerifier(self.config)
        self.logger = logging.getLogger("hallucination_guard")
        self._setup_logging()

    def _setup_logging(self):
        """Set up console logging if no handlers exist yet."""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def verify(self, llm_response, source_chunks, user_query="",
               source_files=None, metadata=None):
        """
        Verify an LLM response against source context.

        This is the main method. It runs all layers in sequence:
            1. Extract claims from the response
            2. NLI-verify each claim against source chunks
            3. Compute faithfulness score
            4. Check confidence calibration
            5. Build safe response based on failure_action

        PARAMETERS:
            llm_response:  str       -- The LLM's text response
            source_chunks: list[str] -- Context chunks that were sent to LLM
            user_query:    str       -- Original user query (for audit log)
            source_files:  list[str] -- File names per chunk (traceability)
            metadata:      dict      -- Extra metadata for audit log

        RETURNS:
            GuardResult with:
                is_safe:           bool  -- Pass/fail
                safe_response:     str   -- Modified response text
                faithfulness_score: float -- 0.0-1.0
                claim_results:     list  -- Per-claim details
                contradictions:    list  -- Contradicted claim texts
                verification_time_ms: float -- Performance metric
        """
        start_time = time.time()

        # Generate a unique ID for this verification (audit log linking)
        vid = hashlib.md5(
            f"{llm_response[:100]}{time.time()}".encode()
        ).hexdigest()[:12]

        self.logger.info(
            f"[{vid}] Verifying ({len(llm_response)} chars, "
            f"{len(source_chunks)} chunks)")

        # -- LAYER 2a: Extract claims from the LLM response --
        claims = ClaimExtractor.extract_claims(llm_response)
        self.logger.info(f"[{vid}] {len(claims)} claims extracted")

        # Cap claims to prevent runaway on very long responses
        if len(claims) > self.config.max_claims_per_response:
            claims = claims[:self.config.max_claims_per_response]

        # -- LAYER 2b: NLI verification of each claim --
        claim_results = []
        for claim in claims:
            if claim["is_trivial"]:
                # Skip NLI for non-factual sentences (save ~12ms each)
                cr = ClaimResult(
                    claim_text=claim["text"],
                    verdict=ClaimVerdict.TRIVIAL,
                    confidence=1.0,
                    explanation="Non-factual sentence",
                )
            else:
                # Run NLI: does any chunk support/contradict this?
                cr = self.nli.verify_claim_against_chunks(
                    claim["text"], source_chunks)
                # Attach source file info if the LLM cited a chunk
                if claim["cited_chunks"] and source_files:
                    for cn in claim["cited_chunks"]:
                        idx = cn - 1  # 1-indexed in citations
                        if 0 <= idx < len(source_files):
                            cr.source_file = source_files[idx]
            claim_results.append(cr)

        # -- LAYER 3: Compute faithfulness score --
        verifiable = [cr for cr in claim_results
                      if cr.verdict != ClaimVerdict.TRIVIAL]
        if verifiable:
            sup = sum(1 for cr in verifiable
                      if cr.verdict == ClaimVerdict.SUPPORTED)
            faith_score = sup / len(verifiable)
        else:
            faith_score = 1.0  # No claims = vacuously true

        # -- LAYER 4: Confidence calibration --
        conf_warnings = []
        if self.config.enable_confidence_check:
            for cr in claim_results:
                cal = ConfidenceCalibrator.check_overconfidence(
                    cr.claim_text, cr.verdict)
                if cal["is_overconfident"]:
                    w = (
                        f"Overconfident {cr.verdict.value}: "
                        f"'{cr.claim_text[:80]}...' "
                        f"markers: {cal['markers_found']} "
                        f"severity: {cal['severity']}"
                    )
                    conf_warnings.append(w)
                    cr.explanation += (
                        f" [OVERCONFIDENCE: {cal['severity']}]")

        # -- Final safety decision --
        contra_count = sum(
            1 for cr in claim_results
            if cr.verdict == ClaimVerdict.CONTRADICTED
        )
        if contra_count > 0:
            is_safe = False  # Zero tolerance for contradictions
        else:
            is_safe = (faith_score
                       >= self.config.faithfulness_threshold)

        # -- Build the safe response --
        safe_resp = ResponseConstructor.build_safe_response(
            llm_response, claim_results, faith_score, self.config)

        elapsed = (time.time() - start_time) * 1000

        # -- Assemble the complete result object --
        result = GuardResult(
            is_safe=is_safe,
            original_response=llm_response,
            safe_response=safe_resp,
            faithfulness_score=faith_score,
            supported_count=sum(
                1 for cr in claim_results
                if cr.verdict == ClaimVerdict.SUPPORTED),
            contradicted_count=contra_count,
            unsupported_count=sum(
                1 for cr in claim_results
                if cr.verdict == ClaimVerdict.UNSUPPORTED),
            trivial_count=sum(
                1 for cr in claim_results
                if cr.verdict == ClaimVerdict.TRIVIAL),
            total_claims=len(claim_results),
            claim_results=claim_results,
            contradictions=[
                cr.claim_text for cr in claim_results
                if cr.verdict == ClaimVerdict.CONTRADICTED],
            unverified_claims=[
                cr.claim_text for cr in claim_results
                if cr.verdict == ClaimVerdict.UNSUPPORTED],
            confidence_warnings=conf_warnings,
            verification_time_ms=elapsed,
            active_layers=[
                "prompt_hardening", "claim_extraction",
                "nli_verification", "faithfulness_gating",
                "confidence_calibration",
            ],
            timestamp=datetime.now().isoformat(),
            verification_id=vid,
        )

        self.logger.info(
            f"[{vid}] score={faith_score:.2f} safe={is_safe} "
            f"sup={result.supported_count} "
            f"con={result.contradicted_count} "
            f"unsup={result.unsupported_count} "
            f"time={elapsed:.0f}ms")

        if self.config.enable_audit_log:
            self._write_audit_log(result, user_query, metadata)

        return result

    def _write_audit_log(self, result, query, metadata):
        """
        Write verification to JSONL audit log for compliance.

        JSONL format: append-only, one line per entry, grep-friendly,
        ASCII-only (PS 5.1 compatible), no source text (security).
        """
        try:
            os.makedirs(self.config.log_dir, exist_ok=True)
            path = os.path.join(
                self.config.log_dir, self.config.audit_log_file)
            entry = {
                "verification_id": result.verification_id,
                "timestamp": result.timestamp,
                "query": query[:200] if query else "",
                "is_safe": result.is_safe,
                "faithfulness_score": round(
                    result.faithfulness_score, 4),
                "total_claims": result.total_claims,
                "supported": result.supported_count,
                "contradicted": result.contradicted_count,
                "unsupported": result.unsupported_count,
                "trivial": result.trivial_count,
                "contradictions": result.contradictions[:5],
                "confidence_warnings": (
                    result.confidence_warnings[:3]),
                "verification_time_ms": round(
                    result.verification_time_ms, 1),
                "failure_action": self.config.failure_action,
                "threshold": self.config.faithfulness_threshold,
                "metadata": metadata or {},
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception as e:
            self.logger.error(f"Audit log write failed: {e}")

    def get_prompt_package(self, system_prompt, user_query, chunks,
                           source_files=None):
        """Convenience wrapper for PromptHardener.build_hardened_prompt()."""
        return PromptHardener.build_hardened_prompt(
            system_prompt, user_query, chunks, source_files)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_guard_instance = None


def get_guard(config=None):
    """Get or create singleton HallucinationGuard instance."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = HallucinationGuard(config)
    return _guard_instance


def guard_response(llm_response, source_chunks, user_query="",
                   **kwargs):
    """
    One-liner to verify an LLM response.

    USAGE:
        from hallucination_guard import guard_response
        result = guard_response(response_text, chunks, query)
        if result.is_safe:
            return result.original_response
        else:
            return result.safe_response
    """
    return get_guard().verify(
        llm_response, source_chunks, user_query, **kwargs)


def harden_prompt(system_prompt, user_query, chunks,
                  source_files=None):
    """One-liner to get a hardened prompt package."""
    return PromptHardener.build_hardened_prompt(
        system_prompt, user_query, chunks, source_files)


def init_hallucination_guard(config=None):
    """
    Pre-load NLI model at startup to avoid delay on first query.

    Call once at application startup:
        from hallucination_guard import init_hallucination_guard
        init_hallucination_guard()
    """
    guard = get_guard(config)
    return guard.nli.load_model()
