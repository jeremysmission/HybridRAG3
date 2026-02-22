#!/usr/bin/env python3
"""
dual_path.py -- Layer 5: Dual-Path Consensus
==============================================

PURPOSE:
    The "nuclear option" for life-critical queries. Runs the same query
    through BOTH offline (Phi4-Mini) AND online (Sonnet), then compares
    their responses for agreement using NLI.

WHEN TO USE:
    - Safety-critical specifications (operating parameters, frequencies)
    - Queries where wrong info could cause physical harm
    - Borderline faithfulness scores that need a tiebreaker

HOW IT WORKS:
    1. Get response from offline LLM (Phi4-Mini via Ollama)
    2. Get response from online LLM (Sonnet via Azure API)
    3. Extract factual claims from both responses
    4. Use NLI to check if online claims are SUPPORTED by offline claims
    5. If agreement < threshold (default 0.70), fall back to offline

TRADE-OFF:
    Doubles response time (two LLM calls + NLI comparison).
    Only use when the cost of a wrong answer justifies the delay.

NETWORK ACCESS:
    This module itself does no network calls -- it just compares two
    responses that were already obtained by the caller.

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

import logging

from .guard_types import ClaimVerdict
from .claim_extractor import ClaimExtractor


class DualPathConsensus:
    """
    Compares offline and online LLM responses for agreement.

    USAGE:
        from hallucination_guard import HallucinationGuard, DualPathConsensus

        guard = HallucinationGuard()
        consensus = DualPathConsensus(guard)

        # You must obtain both responses yourself first:
        offline_resp = ollama_call(query, chunks)
        online_resp = api_call(query, chunks)

        comparison = consensus.compare_responses(
            offline_resp, online_resp, chunks)

        if comparison["agreement_score"] >= 0.70:
            final = consensus.build_consensus_response(
                comparison, online_resp, offline_resp)
        else:
            final = offline_resp  # Fall back to conservative
    """

    def __init__(self, guard):
        """
        PARAMETERS:
            guard: HallucinationGuard -- Uses its NLI verifier
                   for comparing claims across responses.
        """
        self.guard = guard
        self.logger = logging.getLogger(
            "hallucination_guard.consensus")

    def compare_responses(self, offline_response, online_response,
                          chunks):
        """
        Compare offline and online responses for agreement.

        ALGORITHM:
            1. Extract factual claims from both responses
            2. For each online claim, check if any offline claim
               supports it (using NLI)
            3. Compute agreement_score = agreed / total_online_claims

        WHY CHECK ONLINE AGAINST OFFLINE:
            The offline model (Phi4-Mini) is slower and less detailed but
            more conservative -- it tends to stick to what it knows.
            The online model (Sonnet) is fast and detailed but prone to
            filling gaps with training data. So we use offline as the
            "ground truth" to validate online's extra claims.

        PARAMETERS:
            offline_response: str       -- Phi4-Mini response text
            online_response:  str       -- Sonnet response text
            chunks:           list[str] -- Source chunks (context)

        RETURNS:
            dict with:
                agreement_score:  float     -- 0.0-1.0
                agreed_claims:    list[str]  -- Both models agree
                disagreed_claims: list[str]  -- Models conflict
                online_only:      list[str]  -- Only online claimed
                offline_only:     list[str]  -- Only offline claimed
        """
        online_claims = ClaimExtractor.extract_claims(
            online_response)
        offline_claims = ClaimExtractor.extract_claims(
            offline_response)

        online_factual = [
            c for c in online_claims if not c["is_trivial"]]
        offline_factual = [
            c for c in offline_claims if not c["is_trivial"]]

        # Edge case: if online produced no factual claims,
        # there's nothing to disagree about
        if not online_factual:
            return {
                "agreement_score": 1.0,
                "agreed_claims": [],
                "disagreed_claims": [],
                "online_only": [],
                "offline_only": [
                    c["text"] for c in offline_factual],
            }

        offline_texts = [c["text"] for c in offline_factual]
        agreed, disagreed, online_only = [], [], []

        for claim in online_factual:
            if not offline_texts:
                # Offline had no claims to compare against
                online_only.append(claim["text"])
                continue

            # Use NLI to check: does offline support this claim?
            result = self.guard.nli.verify_claim_against_chunks(
                claim["text"], offline_texts)

            if result.verdict == ClaimVerdict.SUPPORTED:
                agreed.append(claim["text"])
            elif result.verdict == ClaimVerdict.CONTRADICTED:
                disagreed.append(claim["text"])
            else:
                online_only.append(claim["text"])

        total = len(online_factual)
        score = len(agreed) / total if total > 0 else 1.0

        return {
            "agreement_score": score,
            "agreed_claims": agreed,
            "disagreed_claims": disagreed,
            "online_only": online_only,
            "offline_only": [c["text"] for c in offline_factual],
        }

    def build_consensus_response(self, comparison, online_resp,
                                  offline_resp):
        """
        Build a merged response highlighting agreement/disagreement.

        LOGIC:
            If agreement >= threshold: Use online response (better detail),
                but append a list of any disagreements for cross-checking.
            If agreement < threshold: Fall back to offline response,
                and list the unverified online-only claims.

        PARAMETERS:
            comparison:   dict -- Output from compare_responses()
            online_resp:  str  -- The online LLM's full response
            offline_resp: str  -- The offline LLM's full response

        RETURNS:
            str -- The consensus response with header and annotations
        """
        s = comparison["agreement_score"]
        header = (
            f"== DUAL-PATH CONSENSUS ==\n"
            f"Agreement: {s:.0%} | "
            f"Agreed: {len(comparison['agreed_claims'])} | "
            f"Disagreed: {len(comparison['disagreed_claims'])}\n"
            f"{'=' * 40}\n\n"
        )

        if s >= self.guard.config.consensus_threshold:
            # Good agreement: use online (better detail)
            body = online_resp
            if comparison["disagreed_claims"]:
                body += "\n\n[DISAGREEMENTS - cross-check]:\n"
                for d in comparison["disagreed_claims"]:
                    body += f"  [?] {d}\n"
        else:
            # Low agreement: fall back to offline (conservative)
            body = (
                "[LOW CONSENSUS: Using offline response for safety]"
                "\n\n" + offline_resp
            )
            if comparison["online_only"]:
                body += "\n\n[Online-only claims (UNVERIFIED)]:\n"
                for c in comparison["online_only"][:5]:
                    body += f"  [?] {c}\n"

        return header + body
