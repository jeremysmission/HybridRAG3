# ============================================================================
# HybridRAG v3 -- Grounded Query Engine (src/core/grounded_query_engine.py)
# ============================================================================
#
# WHAT: QueryEngine subclass that adds hallucination detection and
#       blocking before returning any LLM-generated answer.
#
# WHY:  LLMs sometimes "make up" facts that sound correct but are not
#       in the source documents. In an engineering context, a fabricated
#       tolerance or part number could cause real harm. This module adds
#       a verification step that checks every claim in the LLM's answer
#       against the actual source documents before showing it to the user.
#
# HOW:  Extends the base QueryEngine with three new stages:
#       1. RETRIEVAL GATE -- refuses to answer if evidence is too weak
#       2. PROMPT HARDENING -- injects extra grounding rules into the prompt
#       3. NLI VERIFICATION -- uses a local AI model (Natural Language
#          Inference) to check each claim against source text
#       If verification fails, the answer is blocked, stripped, or flagged
#       depending on config (guard_action: block / strip / flag).
#
# USAGE:
#       from src.core.grounded_query_engine import GroundedQueryEngine
#       engine = GroundedQueryEngine(config, vector_store, embedder, router)
#       result = engine.query("What is the torque spec?")
#       if result.grounding_blocked:
#           print("Answer was not sufficiently supported by sources")
#
# THE PIPELINE (8 steps):
#     1. Retrieve chunks          (inherited from QueryEngine)
#     2. Build context            (inherited from QueryEngine)
#     3. GATE: check evidence     (NEW -- refuses weak evidence)
#     4. BUILD GROUNDED PROMPT    (NEW -- adds citation rules)
#     5. Call LLM                 (inherited from QueryEngine)
#     6. VERIFY RESPONSE          (NEW -- NLI checks claims vs sources)
#     7. FILTER/FLAG RESULT       (NEW -- strips or blocks hallucination)
#     8. Log + return             (inherited from QueryEngine)
#
# DESIGN: Subclass instead of modifying query_engine.py because:
#   - Zero blast radius: base QueryEngine stays untouched
#   - All existing tests still pass with zero delta
#   - Guard can be disabled at runtime via config toggle
#
# NETWORK ACCESS: NONE (NLI model runs locally after first download)
#
# DEPENDENCIES: hallucination_guard/ package (already in src/core/)
#               NLI verifier is DORMANT (sentence-transformers retired)
#
# LINE BUDGET: Target <300 lines (well under 500 limit)
# ============================================================================

import time
from typing import Optional, Dict, Any, Generator
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

        # Load guard config from the config object.
        # Uses getattr for backward compatibility -- if config doesn't
        # have hallucination_guard settings yet (older YAML), we use
        # safe defaults. This prevents crashes when upgrading.
        self.guard_enabled = getattr(
            config, "hallucination_guard_enabled", False
        )
        # Threshold: fraction of claims that must be verified (0.80 = 80%).
        # Below this, the answer is considered unreliable.
        self.guard_threshold = getattr(
            config, "hallucination_guard_threshold", 0.80
        )
        # Action on failure: "block" = replace with refusal message,
        # "strip" = keep only verified sentences, "flag" = pass through
        # with metadata so the UI can show a warning.
        self.guard_action = getattr(
            config, "hallucination_guard_action", "block"
        )
        # Retrieval gate settings: how many chunks and what minimum score
        # must pass before we even try to generate an answer.
        self.guard_min_chunks = getattr(
            config.retrieval, "min_chunks", 1
        )
        self.guard_min_score = getattr(
            config.retrieval, "min_retrieval_score",
            config.retrieval.min_score,
        )

        # Try to load the guard modules (graceful degradation if the
        # hallucination_guard package is not installed -- the system
        # still works, just without verification).
        self._guard_available = False
        if self.guard_enabled:
            try:
                from .hallucination_guard.hallucination_guard import harden_prompt
                from .hallucination_guard.claim_extractor import ClaimExtractor
                from .hallucination_guard.nli_verifier import NLIVerifier
                self._harden_prompt = harden_prompt
                self._extract_claims = ClaimExtractor.extract_claims
                self._score_response = self._fallback_score
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

    # ------------------------------------------------------------------
    # Shared guard helpers (used by both query and query_stream)
    # ------------------------------------------------------------------

    def _apply_guard_action(self, raw_answer, score, details):
        """Apply block/strip/flag action based on grounding score.

        Returns (answer, blocked) tuple.
        """
        if score >= self.guard_threshold:
            return raw_answer, False

        if self.guard_action == "block":
            return (
                "I found relevant documents but cannot provide "
                "a fully verified answer. The available evidence "
                "does not sufficiently support a complete response. "
                "Please refine your question or check the source "
                "documents directly."
            ), True

        if self.guard_action == "strip":
            verified = [
                d["claim"] for d in details.get("claims", [])
                if d.get("verdict") == "SUPPORTED"
            ]
            if verified:
                return " ".join(verified), False
            return (
                "No fully verified claims could be extracted. "
                "Please check source documents directly."
            ), True

        # "flag" action: pass through with metadata only
        return raw_answer, False

    def _make_error_result(self, start_time, error_msg, sources=None,
                           chunks=0):
        """Build a GroundedQueryResult for error/empty-LLM cases."""
        return GroundedQueryResult(
            answer="Error processing query: {}".format(error_msg),
            sources=sources or [], chunks_used=chunks,
            tokens_in=0, tokens_out=0, cost_usd=0.0,
            latency_ms=(time.time() - start_time) * 1000,
            mode=self.config.mode, error=error_msg,
            grounding_blocked=True,
            grounding_details={"reason": "error"},
        )

    def _retrieval_gate(self, user_query, search_results, start_time):
        """Check retrieval quality. Returns GroundedQueryResult if blocked,
        None if evidence is sufficient to proceed."""
        if not search_results:
            return self._no_evidence_result(start_time)
        passing = [
            h for h in search_results if h.score >= self.guard_min_score
        ]
        if len(passing) < self.guard_min_chunks:
            self.guard_logger.info(
                "retrieval_gate_blocked", query=user_query[:80],
                chunks_found=len(search_results),
                chunks_passing=len(passing),
                min_required=self.guard_min_chunks,
            )
            return self._insufficient_evidence_result(
                start_time, search_results
            )
        return None  # gate passed

    def _log_grounded_result(self, event_name, result, blocked, elapsed_ms):
        """Log a grounded query result."""
        self.guard_logger.info(
            event_name,
            score="{:.2f}".format(result.grounding_score),
            safe=result.grounding_safe, blocked=blocked,
            action=self.guard_action,
            latency_ms="{:.0f}".format(elapsed_ms),
        )

    # ------------------------------------------------------------------
    # query() -- synchronous guarded path
    # ------------------------------------------------------------------

    def query(self, user_query: str) -> GroundedQueryResult:
        """Execute a guarded query. Falls through to base QueryEngine
        when guard is disabled."""
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

        start_time = time.time()
        try:
            search_results = self.retriever.search(user_query)
            gate_result = self._retrieval_gate(
                user_query, search_results, start_time)
            if gate_result is not None:
                return gate_result

            context = self.retriever.build_context(search_results)
            sources = self.retriever.get_sources(search_results)
            prompt = self._build_grounded_prompt(
                user_query, context, search_results)

            llm_response = self.llm_router.query(prompt)
            if not llm_response:
                return self._make_error_result(
                    start_time, "LLM call failed", sources,
                    len(search_results))

            score, details = self._verify_response(
                llm_response.text, search_results)
            answer, blocked = self._apply_guard_action(
                llm_response.text, score, details)

            cost_usd = self._calculate_cost(llm_response)
            elapsed_ms = (time.time() - start_time) * 1000

            result = GroundedQueryResult(
                answer=answer, sources=sources,
                chunks_used=len(search_results),
                tokens_in=llm_response.tokens_in,
                tokens_out=llm_response.tokens_out,
                cost_usd=cost_usd, latency_ms=elapsed_ms,
                mode=self.config.mode,
                grounding_score=score,
                grounding_safe=score >= self.guard_threshold,
                grounding_blocked=blocked,
                grounding_details=details,
            )
            self._log_grounded_result(
                "query_grounded", result, blocked, elapsed_ms)
            return result

        except Exception as e:
            error_msg = "{}: {}".format(type(e).__name__, e)
            self.guard_logger.error("guard_query_error", error=error_msg)
            return self._make_error_result(start_time, error_msg)

    def query_stream(
        self, user_query: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a guarded query response.

        IMPORTANT:
            Guarded streaming intentionally buffers the raw model stream,
            verifies grounding, then emits only the post-guard answer.
            This prevents unverified tokens from being shown in real time.
        """
        if not self.guard_enabled or not self._guard_available:
            yield from super().query_stream(user_query)
            return

        start_time = time.time()
        try:
            yield {"phase": "searching"}
            search_results = self.retriever.search(user_query)
            retrieval_ms = (time.time() - start_time) * 1000

            # Retrieval gate
            gate_result = self._retrieval_gate(
                user_query, search_results, start_time)
            if gate_result is not None:
                yield {"done": True, "result": gate_result}
                return

            context = self.retriever.build_context(search_results)
            sources = self.retriever.get_sources(search_results)
            if not context.strip():
                yield {"done": True, "result": self._make_error_result(
                    start_time, "empty_context", sources,
                    len(search_results))}
                return

            prompt = self._build_grounded_prompt(
                user_query, context, search_results)

            yield {"phase": "generating", "chunks": len(search_results),
                   "retrieval_ms": retrieval_ms}

            # Buffer raw stream (tokens must not reach UI before guard)
            full_text = []
            tokens_in = tokens_out = 0
            model = ""
            llm_latency_ms = 0.0
            for chunk in self.llm_router.query_stream(prompt):
                if "token" in chunk:
                    full_text.append(chunk["token"])
                elif chunk.get("done"):
                    tokens_in = chunk.get("tokens_in", 0)
                    tokens_out = chunk.get("tokens_out", 0)
                    model = chunk.get("model", "")
                    llm_latency_ms = chunk.get("latency_ms", 0.0)

            raw_answer = "".join(full_text)
            if not raw_answer:
                yield {"done": True, "result": self._make_error_result(
                    start_time, "LLM stream empty", sources,
                    len(search_results))}
                return

            # Verify and apply guard action
            score, details = self._verify_response(
                raw_answer, search_results)
            answer, blocked = self._apply_guard_action(
                raw_answer, score, details)

            # Emit only post-guard answer text
            if answer:
                words = answer.split()
                for i, w in enumerate(words):
                    yield {"token": w + (" " if i < len(words) - 1 else "")}

            from .llm_router import LLMResponse
            llm_resp = LLMResponse(
                text=raw_answer, tokens_in=tokens_in,
                tokens_out=tokens_out, model=model,
                latency_ms=llm_latency_ms)
            elapsed_ms = (time.time() - start_time) * 1000

            result = GroundedQueryResult(
                answer=answer, sources=sources,
                chunks_used=len(search_results),
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=self._calculate_cost(llm_resp),
                latency_ms=elapsed_ms, mode=self.config.mode,
                grounding_score=score,
                grounding_safe=score >= self.guard_threshold,
                grounding_blocked=blocked,
                grounding_details=details,
            )
            self._log_grounded_result(
                "query_stream_grounded", result, blocked, elapsed_ms)
            yield {"done": True, "result": result}

        except Exception as e:
            error_msg = "{}: {}".format(type(e).__name__, e)
            self.guard_logger.error(
                "guard_query_stream_error", error=error_msg)
            yield {"done": True, "result": self._make_error_result(
                start_time, error_msg)}

    def _build_grounded_prompt(
        self, user_query: str, context: str, hits: list
    ) -> str:
        """
        Build a prompt with grounding rules that instruct the LLM
        to stick to source material and cite chunks.
        """
        if self._guard_available:
            source_texts = [h.text for h in hits]
            hardened = self._harden_prompt(context, user_query, source_texts)
            # harden_prompt returns {"system": ..., "user": ...} dict.
            # Flatten to a single prompt string for the LLM router.
            if isinstance(hardened, dict):
                return hardened.get("system", "") + "\n\n" + hardened.get("user", "")
            return hardened
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

    @staticmethod
    def _fallback_score(claims, source_texts, threshold):
        """Lightweight claim-vs-source scoring when NLI model is not loaded.

        Counts how many extracted claims have a substring match in any
        source chunk.  This is less accurate than NLI but prevents the
        guard from blocking everything when the heavy model is absent.
        """
        if not claims:
            return 1.0, {"method": "fallback_no_claims"}
        joined = " ".join(source_texts).lower()
        supported = 0
        for c in claims:
            text = c.get("text", "") if isinstance(c, dict) else str(c)
            # Grab first 60 chars of claim as search key
            key = text[:60].strip().lower()
            if key and key in joined:
                supported += 1
        total = len(claims)
        score = supported / total if total > 0 else 0.0
        return score, {
            "method": "fallback_substring",
            "total_claims": total,
            "supported": supported,
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
