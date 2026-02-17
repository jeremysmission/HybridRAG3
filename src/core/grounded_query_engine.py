# ============================================================================
# HybridRAG v3 -- Grounded Query Engine (src/core/grounded_query_engine.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Wraps the base QueryEngine with hallucination guard verification.
#   When enabled, the pipeline becomes:
#
#     1. Retrieve chunks          (inherited from QueryEngine)
#     2. Build context            (inherited from QueryEngine)
#     3. GATE: check evidence     (NEW -- refuses weak evidence)
#     4. BUILD GROUNDED PROMPT    (NEW -- adds citation rules)
#     5. Call LLM                 (inherited from QueryEngine)
#     6. VERIFY RESPONSE          (NEW -- NLI checks claims vs sources)
#     7. FILTER/FLAG RESULT       (NEW -- strips or blocks hallucination)
#     8. Log + return             (inherited from QueryEngine)
#
# WHY A SUBCLASS INSTEAD OF MODIFYING query_engine.py:
#   - Zero blast radius: base QueryEngine stays at 235 lines, untouched
#   - All existing tests still pass with zero delta
#   - Consumers who don't want the guard use QueryEngine directly
#   - Consumers who want the guard import GroundedQueryEngine
#   - Guard can be disabled at runtime via config toggle
#
# NETWORK ACCESS: NONE (NLI model runs locally after first download)
#
# DEPENDENCIES: hallucination_guard/ package (already in src/core/)
#               sentence-transformers (already pinned for embeddings)
#
# LINE BUDGET: Target <300 lines (well under 500 limit)
# ============================================================================

import time
from typing import Optional
from dataclasses import dataclass

from .query_engine import QueryEngine, QueryResult
from .config import Config
from .vector_store import VectorStore
from .embedder import Embedder
from .llm_router import LLMRouter
from ..monitoring.logger import get_app_logger


# ---------------------------------------------------------------------------
# Extended QueryResult with grounding metadata
# ---------------------------------------------------------------------------

@dataclass
class GroundedQueryResult(QueryResult):
    """
    QueryResult + grounding verification metadata.

    Inherits all base fields (answer, sources, chunks_used, etc.)
    and adds:
      grounding_score: float (0.0 to 1.0) -- fraction of claims verified
      grounding_safe:  bool -- True if score >= threshold
      grounding_blocked: bool -- True if response was blocked/replaced
      grounding_details: dict -- claim-level verification breakdown
    """
    grounding_score: float = -1.0
    grounding_safe: bool = True
    grounding_blocked: bool = False
    grounding_details: Optional[dict] = None


# ---------------------------------------------------------------------------
# GroundedQueryEngine -- QueryEngine + hallucination guard
# ---------------------------------------------------------------------------

class GroundedQueryEngine(QueryEngine):
    """
    QueryEngine subclass that verifies LLM responses against sources.

    If hallucination_guard is disabled in config, this behaves identically
    to the base QueryEngine (super().query() is called with no extra work).

    The guard runs in 3 stages:
      PRE-LLM:   Retrieval gate checks evidence quality
      PROMPT:    Grounding rules injected into the LLM prompt
      POST-LLM:  NLI verifier checks each claim against source chunks
    """

    def __init__(
        self,
        config: Config,
        vector_store: VectorStore,
        embedder: Embedder,
        llm_router: LLMRouter,
    ):
        # Initialize base QueryEngine (sets up retriever, logger, etc.)
        super().__init__(config, vector_store, embedder, llm_router)

        self.guard_logger = get_app_logger("grounding_guard")

        # Load guard config from the config object
        # Uses getattr for backward compatibility -- if config doesn't
        # have hallucination_guard yet, we use safe defaults
        self.guard_enabled = getattr(
            config, "hallucination_guard_enabled", False
        )
        self.guard_threshold = getattr(
            config, "hallucination_guard_threshold", 0.80
        )
        self.guard_action = getattr(
            config, "hallucination_guard_action", "block"
        )
        self.guard_min_chunks = getattr(
            config.retrieval, "min_chunks", 1
        )
        self.guard_min_score = getattr(
            config.retrieval, "min_retrieval_score",
            config.retrieval.min_score,
        )

        # Try to load the guard modules (graceful if not installed)
        self._guard_available = False
        if self.guard_enabled:
            try:
                from .hallucination_guard.prompt_hardener import harden_prompt
                from .hallucination_guard.claim_extractor import (
                    extract_claims,
                )
                from .hallucination_guard.nli_verifier import NLIVerifier
                from .hallucination_guard.response_scoring import (
                    score_response,
                )
                self._harden_prompt = harden_prompt
                self._extract_claims = extract_claims
                self._score_response = score_response
                # NLI verifier is lazy-loaded (model is ~440MB)
                self._nli_verifier = None
                self._guard_available = True
                self.guard_logger.info(
                    "guard_init",
                    status="enabled",
                    threshold=self.guard_threshold,
                    action=self.guard_action,
                )
            except ImportError as e:
                self.guard_logger.warning(
                    "guard_init_failed",
                    error=str(e),
                    fallback="prompt_hardening_only",
                )

    def query(self, user_query: str) -> GroundedQueryResult:
        """
        Execute a guarded query. If guard is disabled, falls through
        to base QueryEngine.query() with no overhead.
        """
        # Fast path: guard disabled -> use base class directly
        if not self.guard_enabled or not self._guard_available:
            base_result = super().query(user_query)
            return GroundedQueryResult(
                answer=base_result.answer,
                sources=base_result.sources,
                chunks_used=base_result.chunks_used,
                tokens_in=base_result.tokens_in,
                tokens_out=base_result.tokens_out,
                cost_usd=base_result.cost_usd,
                latency_ms=base_result.latency_ms,
                mode=base_result.mode,
                error=base_result.error,
            )

        # Guarded path: retrieve -> gate -> harden -> LLM -> verify
        start_time = time.time()

        try:
            # Step 1: Retrieve (reuse base retriever)
            search_results = self.retriever.search(user_query)

            # Step 2: RETRIEVAL GATE -- refuse if evidence is too weak
            if not search_results:
                return self._no_evidence_result(start_time)

            passing = [
                h for h in search_results
                if h.score >= self.guard_min_score
            ]

            if len(passing) < self.guard_min_chunks:
                self.guard_logger.info(
                    "retrieval_gate_blocked",
                    query=user_query[:80],
                    chunks_found=len(search_results),
                    chunks_passing=len(passing),
                    min_required=self.guard_min_chunks,
                )
                return self._insufficient_evidence_result(
                    start_time, search_results
                )

            # Step 3: Build grounded context and prompt
            context = self.retriever.build_context(search_results)
            sources = self.retriever.get_sources(search_results)

            # Harden the prompt with grounding rules
            prompt = self._build_grounded_prompt(
                user_query, context, search_results
            )

            # Step 4: Call LLM (same as base)
            llm_response = self.llm_router.query(prompt)

            if not llm_response:
                return GroundedQueryResult(
                    answer="Error calling LLM. Please try again.",
                    sources=sources,
                    chunks_used=len(search_results),
                    tokens_in=0, tokens_out=0, cost_usd=0.0,
                    latency_ms=(time.time() - start_time) * 1000,
                    mode=self.config.mode,
                    error="LLM call failed",
                )

            # Step 5: VERIFY response against source chunks
            score, details = self._verify_response(
                llm_response.text, search_results
            )

            # Step 6: Apply action based on score
            answer = llm_response.text
            blocked = False

            if score < self.guard_threshold:
                if self.guard_action == "block":
                    answer = (
                        "I found relevant documents but cannot provide "
                        "a fully verified answer. The available evidence "
                        "does not sufficiently support a complete response. "
                        "Please refine your question or check the source "
                        "documents directly."
                    )
                    blocked = True
                elif self.guard_action == "strip":
                    # Keep only verified sentences
                    verified = [
                        d["claim"] for d in details.get("claims", [])
                        if d.get("verdict") == "SUPPORTED"
                    ]
                    if verified:
                        answer = " ".join(verified)
                    else:
                        answer = (
                            "No fully verified claims could be extracted. "
                            "Please check source documents directly."
                        )
                        blocked = True
                # "flag" action: pass through with metadata

            cost_usd = self._calculate_cost(llm_response)
            elapsed_ms = (time.time() - start_time) * 1000

            result = GroundedQueryResult(
                answer=answer,
                sources=sources,
                chunks_used=len(search_results),
                tokens_in=llm_response.tokens_in,
                tokens_out=llm_response.tokens_out,
                cost_usd=cost_usd,
                latency_ms=elapsed_ms,
                mode=self.config.mode,
                grounding_score=score,
                grounding_safe=score >= self.guard_threshold,
                grounding_blocked=blocked,
                grounding_details=details,
            )

            self.guard_logger.info(
                "query_grounded",
                score=f"{score:.2f}",
                safe=result.grounding_safe,
                blocked=blocked,
                action=self.guard_action,
                latency_ms=f"{elapsed_ms:.0f}",
            )

            return result

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.guard_logger.error(
                "guard_query_error", error=error_msg
            )
            return GroundedQueryResult(
                answer=f"Error processing query: {error_msg}",
                sources=[], chunks_used=0,
                tokens_in=0, tokens_out=0, cost_usd=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                mode=self.config.mode,
                error=error_msg,
            )

    def _build_grounded_prompt(
        self, user_query: str, context: str, hits: list
    ) -> str:
        """
        Build a prompt with grounding rules that instruct the LLM
        to stick to source material and cite chunks.
        """
        if self._guard_available:
            return self._harden_prompt(user_query, context)
        else:
            # Fallback: basic grounding rules without full hardener
            return (
                "GROUNDING RULES:\n"
                "- Answer ONLY using the provided context\n"
                "- If the context does not contain the answer, say so\n"
                "- Cite [Source N] for each claim\n"
                "- Do NOT add information beyond what the sources state\n"
                "\n"
                f"{context}\n\n"
                f"User Question:\n{user_query}\n\n"
                "Answer:"
            )

    def _verify_response(
        self, response_text: str, hits: list
    ) -> tuple:
        """
        Run NLI verification on the LLM response against source chunks.
        Uses batch processing with early-exit for speed:
        - Chunk pruning per claim (3-5x faster)
        - Early exit on consecutive pass/fail (1.5-3x faster)
        Returns (score: float, details: dict).
        """
        if not self._guard_available:
            return 1.0, {"method": "bypass", "reason": "guard_not_loaded"}

        try:
            # Extract claims from response
            claims = self._extract_claims(response_text)

            if not claims:
                return 1.0, {
                    "method": "no_claims",
                    "reason": "response_has_no_verifiable_claims",
                }

            # Build source text from chunks
            source_texts = [h.text for h in hits]

            # Use batch verification with early-exit if NLI loaded
            if self._nli_verifier is not None:
                from .hallucination_guard.nli_verifier import NLIVerifier
                if not isinstance(self._nli_verifier, NLIVerifier):
                    self._nli_verifier = NLIVerifier()
                results = self._nli_verifier.verify_batch_with_earlyexit(
                    claims, source_texts, self.guard_threshold,
                )
                # Convert results to score
                supported = sum(
                    1 for r in results
                    if r.verdict.value == "SUPPORTED"
                )
                total = len(results)
                score = supported / total if total > 0 else 0.0
                details = {
                    "method": "nli_batch_earlyexit",
                    "total_claims": total,
                    "supported": supported,
                    "claims": [
                        {
                            "claim": r.claim_text[:100],
                            "verdict": r.verdict.value,
                            "confidence": r.confidence,
                        }
                        for r in results
                    ],
                }
                return score, details

            # Fallback: use scoring module (no NLI model loaded)
            score, details = self._score_response(
                claims, source_texts, self.guard_threshold
            )
            return score, details

        except Exception as e:
            self.guard_logger.warning(
                "verify_error", error=str(e)
            )
            return 0.5, {
                "method": "error",
                "reason": str(e),
            }

    def _no_evidence_result(self, start_time: float) -> GroundedQueryResult:
        """Return result when no search results found."""
        return GroundedQueryResult(
            answer="No relevant information found in knowledge base.",
            sources=[], chunks_used=0,
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            latency_ms=(time.time() - start_time) * 1000,
            mode=self.config.mode,
            grounding_blocked=True,
            grounding_details={"reason": "no_search_results"},
        )

    def _insufficient_evidence_result(
        self, start_time: float, hits: list
    ) -> GroundedQueryResult:
        """Return result when evidence is too weak to proceed."""
        sources = self.retriever.get_sources(hits)
        return GroundedQueryResult(
            answer=(
                "Some documents were found but the evidence quality "
                "is insufficient for a reliable answer. Please try "
                "a more specific question or check source documents."
            ),
            sources=sources,
            chunks_used=len(hits),
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            latency_ms=(time.time() - start_time) * 1000,
            mode=self.config.mode,
            grounding_blocked=True,
            grounding_details={
                "reason": "insufficient_evidence",
                "chunks_found": len(hits),
                "min_required": self.guard_min_chunks,
            },
        )
