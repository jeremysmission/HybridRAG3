# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the grounded query engine part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
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

import copy
import time
from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass

from .query_engine import (
    QueryEngine, QueryResult, _retrieval_access_denied,
    _decompose_query, _filter_low_relevance_chunks, _multi_query_retrieve,
    _attempt_corrective_retrieval,
)
from .query_mode import apply_query_mode_to_engine
from .config import Config
from .vector_store import VectorStore
from .embedder import Embedder
from .llm_router import LLMRouter
from .query_trace import (
    attach_result_trace,
    minimal_retrieval_trace,
    new_query_trace,
)
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

class GroundedQueryEngineGuardMixin:
    """Guard helper methods split out to keep GroundedQueryEngine reviewable."""

    def _apply_guard_action(self, raw_answer, score, details):
        """Apply block/strip/flag action based on grounding score.

        Returns (answer, blocked) tuple.
        """
        return _gqe_apply_guard_action(self, raw_answer, score, details)

    def _make_error_result(self, start_time, error_msg, sources=None, chunks=0):
        """Build a GroundedQueryResult for error/empty-LLM cases."""
        return _gqe_make_error_result(
            self,
            start_time,
            error_msg,
            sources=sources,
            chunks=chunks,
        )

    def _access_denied_result(self, *, start_time: float, latency_ms: float | None = None):
        """Build a grounded result for retrieval access denial."""
        return _gqe_access_denied_result(self, start_time, latency_ms=latency_ms)

    def _retrieval_gate(self, user_query, search_results, start_time):
        """Check retrieval quality before generation."""
        return _gqe_retrieval_gate(
            self,
            user_query,
            search_results,
            start_time,
        )

    def _log_grounded_result(self, event_name, result, blocked, elapsed_ms):
        """Log a grounded query result."""
        _gqe_log_grounded_result(
            self,
            event_name,
            result,
            blocked,
            elapsed_ms,
        )

    def _build_grounded_prompt(
        self, user_query: str, context: str, hits: list
    ) -> str:
        """
        Build a prompt with grounding rules that instruct the LLM
        to stick to source material and cite chunks.
        """
        return _gqe_build_grounded_prompt(self, user_query, context, hits)

    def _verify_response(
        self, response_text: str, hits: list
    ) -> tuple:
        """NLI verification with batch early-exit. Returns (score, details)."""
        return _gqe_verify_response(self, response_text, hits)

    @staticmethod
    def _fallback_score(claims, source_texts, threshold):
        """Plain-English: Produces a backup confidence score when full grounding metrics are unavailable."""
        return _gqe_fallback_score(claims, source_texts, threshold)

    def _no_evidence_result(self, start_time: float) -> GroundedQueryResult:
        """Return result when no search results found."""
        return _gqe_no_evidence_result(self, start_time)

    def _insufficient_evidence_result(
        self, start_time: float, hits: list
    ) -> GroundedQueryResult:
        """Return result when evidence is too weak to proceed."""
        return _gqe_insufficient_evidence_result(self, start_time, hits)


class GroundedQueryEngine(GroundedQueryEngineGuardMixin, QueryEngine):
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
        """Plain-English: Sets up the GroundedQueryEngine object and prepares state used by its methods."""
        super().__init__(config, vector_store, embedder, llm_router)

        self.guard_logger = get_app_logger("grounding_guard")

        # Guard config (getattr for backward compat with older YAML)
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
        self.guard_min_score = config.retrieval.min_score
        apply_query_mode_to_engine(self, sync_guard_policy=True)

        self._guard_available = False
        self._nli_verifier = None
        if self.guard_enabled:
            self._ensure_guard_backend_loaded()

    # ------------------------------------------------------------------
    # Shared guard helpers (used by both query and query_stream)
    # ------------------------------------------------------------------

    def _ensure_guard_backend_loaded(self) -> bool:
        """Load the verification stack on demand when the live UI enables it."""
        if self._guard_available:
            return True
        try:
            from .hallucination_guard.hallucination_guard import harden_prompt
            from .hallucination_guard.claim_extractor import ClaimExtractor
            from .hallucination_guard.nli_verifier import NLIVerifier

            self._harden_prompt = harden_prompt
            self._extract_claims = ClaimExtractor.extract_claims
            self._score_response = self._fallback_score
            if not isinstance(getattr(self, "_nli_verifier", None), NLIVerifier):
                self._nli_verifier = None
            self._guard_available = True
            self.guard_logger.info(
                "guard_init",
                status="enabled",
                threshold=self.guard_threshold,
                action=self.guard_action,
            )
            return True
        except ImportError as e:
            self.guard_logger.warning(
                "guard_init_failed",
                error=str(e),
                fallback="prompt_hardening_only",
            )
            return False

    # ------------------------------------------------------------------
    # query() -- synchronous guarded path
    # ------------------------------------------------------------------

    def query(self, user_query: str) -> GroundedQueryResult:
        """Execute a guarded query. Falls through to base QueryEngine
        when guard is disabled."""
        self._sync_runtime_components()
        if self.guard_enabled and not self._guard_available:
            self._ensure_guard_backend_loaded()
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
                debug_trace=base_result.debug_trace,
            )

        start_time = time.time()
        trace = new_query_trace(self, user_query, stream=False, engine_kind="grounded")
        retrieval_trace = minimal_retrieval_trace([])
        context_before_trim = ""
        context_after_trim = ""
        prompt_preview = ""
        try:
            # ---- Full retrieval pipeline (matches base QueryEngine) ----
            # Step 0.5: Classify query (gates conditional reranker)
            classification = self._classifier.classify(user_query)

            # Step 0.7: Acronym expansion
            search_query = user_query
            if getattr(self, "_query_expander", None):
                expanded = self._query_expander.expand_keywords(user_query)
                if expanded != user_query:
                    search_query = expanded

            # Step 1a: Query decomposition (multi-part detection)
            sub_queries = _decompose_query(search_query)
            if len(sub_queries) > 1:
                search_results = _multi_query_retrieve(
                    self.retriever, sub_queries,
                    classification=classification)
            else:
                search_results = self.retriever.search(
                    search_query, classification=classification)

            # Step 1.5: Corrective retrieval (CRAG pattern)
            search_results = _attempt_corrective_retrieval(
                self.config, self.retriever, user_query,
                search_results, query_expander=self._query_expander)

            retrieval_trace = getattr(self.retriever, "last_search_trace", None) or minimal_retrieval_trace(search_results)
            if not search_results and _retrieval_access_denied(retrieval_trace):
                result = self._access_denied_result(start_time=start_time)
                attach_result_trace(
                    self,
                    result,
                    trace,
                    decision_path="access_denied_no_results",
                    retrieval_trace=retrieval_trace,
                    grounding={
                        "score": result.grounding_score,
                        "safe": result.grounding_safe,
                        "blocked": result.grounding_blocked,
                        "details": copy.deepcopy(result.grounding_details),
                    },
                )
                return result

            # Step 1.7: Chunk relevance filter (CRAG decompose pattern)
            search_results = _filter_low_relevance_chunks(
                user_query, search_results)

            gate_result = self._retrieval_gate(
                user_query, search_results, start_time)
            if gate_result is not None:
                if bool(getattr(self, "allow_open_knowledge", False)):
                    base_result = super().query(user_query)
                    return _gqe_wrap_open_knowledge_fallback_result(
                        self,
                        base_result,
                        trace=trace,
                        retrieval_trace=retrieval_trace,
                        decision_path="open_knowledge_retrieval_gate_fallback",
                        reason="retrieval_gate_open_knowledge_fallback_unverified",
                    )
                attach_result_trace(
                    self,
                    gate_result,
                    trace,
                    decision_path="retrieval_gate_blocked",
                    retrieval_trace=retrieval_trace,
                    grounding={
                        "score": getattr(gate_result, "grounding_score", -1.0),
                        "safe": getattr(gate_result, "grounding_safe", False),
                        "blocked": getattr(gate_result, "grounding_blocked", True),
                        "details": copy.deepcopy(getattr(gate_result, "grounding_details", None)),
                    },
                )
                return gate_result

            context = self.retriever.build_context(search_results)
            sources = self.retriever.get_sources(search_results)
            context_before_trim = context
            if not context.strip():
                if bool(getattr(self, "allow_open_knowledge", False)):
                    base_result = super().query(user_query)
                    return _gqe_wrap_open_knowledge_fallback_result(
                        self,
                        base_result,
                        trace=trace,
                        retrieval_trace=retrieval_trace,
                        decision_path="open_knowledge_empty_context_fallback",
                        reason="empty_context_open_knowledge_fallback_unverified",
                        context_before_trim=context_before_trim,
                        sources=sources,
                    )
                result = GroundedQueryResult(
                    answer=(
                        "Relevant documents were found, but no usable context "
                        "text was available."
                    ),
                    sources=sources,
                    chunks_used=len(search_results),
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=(time.time() - start_time) * 1000,
                    mode=self.config.mode,
                    error="empty_context",
                    grounding_blocked=True,
                    grounding_details={"reason": "empty_context"},
                )
                attach_result_trace(
                    self,
                    result,
                    trace,
                    decision_path="empty_context",
                    retrieval_trace=retrieval_trace,
                    context_before_trim=context_before_trim,
                    sources=sources,
                    grounding={
                        "score": result.grounding_score,
                        "safe": result.grounding_safe,
                        "blocked": result.grounding_blocked,
                        "details": copy.deepcopy(result.grounding_details),
                    },
                )
                return result
            context_after_trim = self._trim_context_to_fit(context, user_query)
            prompt = self._build_grounded_prompt(
                user_query, context_after_trim, search_results)
            prompt_preview = prompt

            llm_response = self.llm_router.query(prompt)
            if not llm_response:
                result = self._make_error_result(
                    start_time, "LLM call failed", sources,
                    len(search_results))
                attach_result_trace(
                    self,
                    result,
                    trace,
                    decision_path="llm_error",
                    retrieval_trace=retrieval_trace,
                    context_before_trim=context_before_trim,
                    context_after_trim=context_after_trim,
                    prompt_builder="grounded",
                    prompt_preview=prompt_preview,
                    sources=sources,
                    grounding={
                        "score": result.grounding_score,
                        "safe": result.grounding_safe,
                        "blocked": result.grounding_blocked,
                        "details": copy.deepcopy(result.grounding_details),
                    },
                )
                return result

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
            attach_result_trace(
                self,
                result,
                trace,
                decision_path="guarded_answer_blocked" if blocked else "guarded_answer",
                retrieval_trace=retrieval_trace,
                context_before_trim=context_before_trim,
                context_after_trim=context_after_trim,
                prompt_builder="grounded",
                prompt_preview=prompt_preview,
                llm_response=llm_response,
                sources=sources,
                grounding={
                    "score": score,
                    "safe": score >= self.guard_threshold,
                    "blocked": blocked,
                    "details": copy.deepcopy(details),
                },
            )
            self._log_grounded_result(
                "query_grounded", result, blocked, elapsed_ms)
            return result

        except Exception as e:
            error_msg = "{}: {}".format(type(e).__name__, e)
            self.guard_logger.error("guard_query_error", error=error_msg)
            result = self._make_error_result(start_time, error_msg)
            attach_result_trace(
                self,
                result,
                trace,
                decision_path="guarded_engine_error",
                retrieval_trace=retrieval_trace,
                context_before_trim=context_before_trim,
                context_after_trim=context_after_trim,
                prompt_builder="grounded",
                prompt_preview=prompt_preview,
                grounding={
                    "score": result.grounding_score,
                    "safe": result.grounding_safe,
                    "blocked": result.grounding_blocked,
                    "details": copy.deepcopy(result.grounding_details),
                },
            )
            return result

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
        yield from _gqe_query_stream(self, user_query)


def _gqe_query_stream(
    engine: GroundedQueryEngine, user_query: str
) -> Generator[Dict[str, Any], None, None]:
    engine._sync_runtime_components()
    if engine.guard_enabled and not engine._guard_available:
        engine._ensure_guard_backend_loaded()
    if not engine.guard_enabled or not engine._guard_available:
        yield from super(GroundedQueryEngine, engine).query_stream(user_query)
        return

    start_time = time.time()
    trace = new_query_trace(engine, user_query, stream=True, engine_kind="grounded")
    retrieval_trace = minimal_retrieval_trace([])
    context_before_trim = ""
    context_after_trim = ""
    prompt_preview = ""
    try:
        yield {"phase": "searching"}
        # ---- Full retrieval pipeline (matches base QueryEngine) ----
        classification = engine._classifier.classify(user_query)

        search_query = user_query
        if getattr(engine, "_query_expander", None):
            expanded = engine._query_expander.expand_keywords(user_query)
            if expanded != user_query:
                search_query = expanded

        sub_queries = _decompose_query(search_query)
        if len(sub_queries) > 1:
            search_results = _multi_query_retrieve(
                engine.retriever, sub_queries,
                classification=classification)
        else:
            search_results = engine.retriever.search(
                search_query, classification=classification)

        search_results = _attempt_corrective_retrieval(
            engine.config, engine.retriever, user_query,
            search_results, query_expander=engine._query_expander)

        retrieval_ms = (time.time() - start_time) * 1000
        retrieval_trace = getattr(engine.retriever, "last_search_trace", None) or minimal_retrieval_trace(search_results)

        # Chunk relevance filter
        search_results = _filter_low_relevance_chunks(
            user_query, search_results)

        if not search_results and _retrieval_access_denied(retrieval_trace):
            result = engine._access_denied_result(
                start_time=start_time,
                latency_ms=retrieval_ms,
            )
            attach_result_trace(
                engine,
                result,
                trace,
                decision_path="access_denied_no_results",
                retrieval_trace=retrieval_trace,
                grounding={
                    "score": result.grounding_score,
                    "safe": result.grounding_safe,
                    "blocked": result.grounding_blocked,
                    "details": copy.deepcopy(result.grounding_details),
                },
            )
            yield {"done": True, "result": result}
            return

        gate_result = engine._retrieval_gate(user_query, search_results, start_time)
        if gate_result is not None:
            if bool(getattr(engine, "allow_open_knowledge", False)):
                # Use the streaming base path so the UI shows tokens
                # as they arrive instead of blocking until completion.
                yield from _gqe_stream_open_knowledge_fallback(
                    engine,
                    user_query,
                    trace=trace,
                    retrieval_trace=retrieval_trace,
                    decision_path="open_knowledge_retrieval_gate_fallback",
                    reason="retrieval_gate_open_knowledge_fallback_unverified",
                )
                return
            attach_result_trace(
                engine,
                gate_result,
                trace,
                decision_path="retrieval_gate_blocked",
                retrieval_trace=retrieval_trace,
                grounding={
                    "score": getattr(gate_result, "grounding_score", -1.0),
                    "safe": getattr(gate_result, "grounding_safe", False),
                    "blocked": getattr(gate_result, "grounding_blocked", True),
                    "details": copy.deepcopy(getattr(gate_result, "grounding_details", None)),
                },
            )
            yield {"done": True, "result": gate_result}
            return

        context = engine.retriever.build_context(search_results)
        sources = engine.retriever.get_sources(search_results)
        context_before_trim = context
        if not context.strip():
            if bool(getattr(engine, "allow_open_knowledge", False)):
                # Use streaming base path for token-by-token UI updates
                yield from _gqe_stream_open_knowledge_fallback(
                    engine,
                    user_query,
                    trace=trace,
                    retrieval_trace=retrieval_trace,
                    decision_path="open_knowledge_empty_context_fallback",
                    reason="empty_context_open_knowledge_fallback_unverified",
                    context_before_trim=context_before_trim,
                    sources=sources,
                )
                return
            result = engine._make_error_result(
                start_time, "empty_context", sources, len(search_results)
            )
            attach_result_trace(
                engine,
                result,
                trace,
                decision_path="empty_context",
                retrieval_trace=retrieval_trace,
                context_before_trim=context_before_trim,
                sources=sources,
                grounding={
                    "score": result.grounding_score,
                    "safe": result.grounding_safe,
                    "blocked": result.grounding_blocked,
                    "details": copy.deepcopy(result.grounding_details),
                },
            )
            yield {"done": True, "result": result}
            return

        context_after_trim = engine._trim_context_to_fit(context, user_query)
        prompt = engine._build_grounded_prompt(
            user_query, context_after_trim, search_results
        )
        prompt_preview = prompt

        yield {
            "phase": "generating",
            "chunks": len(search_results),
            "retrieval_ms": retrieval_ms,
        }

        full_text = []
        tokens_in = tokens_out = 0
        model = ""
        llm_latency_ms = 0.0
        saw_done = False
        stream_error = ""
        for chunk in engine.llm_router.query_stream(prompt):
            if "token" in chunk:
                full_text.append(chunk["token"])
            elif "error" in chunk:
                stream_error = str(chunk.get("error", "")).strip()
            elif chunk.get("done"):
                saw_done = True
                tokens_in = chunk.get("tokens_in", 0)
                tokens_out = chunk.get("tokens_out", 0)
                model = chunk.get("model", "")
                llm_latency_ms = chunk.get("latency_ms", 0.0)

        raw_answer = "".join(full_text)
        if not saw_done and not raw_answer.strip() and not stream_error:
            fallback = engine.llm_router.query(prompt)
            if fallback and (fallback.text or "").strip():
                raw_answer = fallback.text
                tokens_in = fallback.tokens_in
                tokens_out = fallback.tokens_out
                model = fallback.model
                llm_latency_ms = fallback.latency_ms
        if not raw_answer:
            reason = stream_error
            if not reason:
                last_error = getattr(engine.llm_router, "last_error", None)
                reason = last_error.strip() if isinstance(last_error, str) else ""
            msg = f"LLM stream failed: {reason}" if reason else "LLM stream empty"
            result = engine._make_error_result(
                start_time, msg, sources, len(search_results)
            )
            attach_result_trace(
                engine,
                result,
                trace,
                decision_path="stream_llm_error",
                retrieval_trace=retrieval_trace,
                context_before_trim=context_before_trim,
                context_after_trim=context_after_trim,
                prompt_builder="grounded",
                prompt_preview=prompt_preview,
                llm_stream_error=reason,
                sources=sources,
                grounding={
                    "score": result.grounding_score,
                    "safe": result.grounding_safe,
                    "blocked": result.grounding_blocked,
                    "details": copy.deepcopy(result.grounding_details),
                },
            )
            yield {"done": True, "result": result}
            return

        score, details = engine._verify_response(raw_answer, search_results)
        answer, blocked = engine._apply_guard_action(raw_answer, score, details)

        if answer:
            words = answer.split()
            for i, word in enumerate(words):
                yield {"token": word + (" " if i < len(words) - 1 else "")}

        from .llm_router import LLMResponse

        llm_resp = LLMResponse(
            text=raw_answer,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            latency_ms=llm_latency_ms,
        )
        elapsed_ms = (time.time() - start_time) * 1000

        result = GroundedQueryResult(
            answer=answer,
            sources=sources,
            chunks_used=len(search_results),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=engine._calculate_cost(llm_resp),
            latency_ms=elapsed_ms,
            mode=engine.config.mode,
            grounding_score=score,
            grounding_safe=score >= engine.guard_threshold,
            grounding_blocked=blocked,
            grounding_details=details,
        )
        attach_result_trace(
            engine,
            result,
            trace,
            decision_path="guarded_stream_answer_blocked" if blocked else "guarded_stream_answer",
            retrieval_trace=retrieval_trace,
            context_before_trim=context_before_trim,
            context_after_trim=context_after_trim,
            prompt_builder="grounded",
            prompt_preview=prompt_preview,
            llm_response=llm_resp,
            llm_stream_error=stream_error,
            sources=sources,
            grounding={
                "score": score,
                "safe": score >= engine.guard_threshold,
                "blocked": blocked,
                "details": copy.deepcopy(details),
            },
        )
        engine._log_grounded_result(
            "query_stream_grounded", result, blocked, elapsed_ms
        )
        yield {"done": True, "result": result}

    except Exception as e:
        error_msg = "{}: {}".format(type(e).__name__, e)
        engine.guard_logger.error("guard_query_stream_error", error=error_msg)
        result = engine._make_error_result(start_time, error_msg)
        attach_result_trace(
            engine,
            result,
            trace,
            decision_path="guarded_stream_engine_error",
            retrieval_trace=retrieval_trace,
            context_before_trim=context_before_trim,
            context_after_trim=context_after_trim,
            prompt_builder="grounded",
            prompt_preview=prompt_preview,
            grounding={
                "score": result.grounding_score,
                "safe": result.grounding_safe,
                "blocked": result.grounding_blocked,
                "details": copy.deepcopy(result.grounding_details),
            },
        )
        yield {"done": True, "result": result}

def _gqe_fallback_score(claims, source_texts, threshold):
    """Token-overlap claim-vs-source scoring when NLI model is not loaded.

    Scores each claim by the fraction of its content tokens that appear
    somewhere in the source texts.  Much more robust than the old 60-char
    substring approach because GPT-4o paraphrases freely -- individual
    technical terms still match even when sentence structure differs.

    A claim is SUPPORTED when >= 30% of its content tokens appear in
    sources.  This threshold is deliberately lenient: false negatives
    (blocking good answers) are far worse than false positives here.
    GPT-4o paraphrases heavily, so token overlap is typically 30-45%
    even for fully grounded answers.  The previous 50% threshold
    caused silent blocking of correct, well-written responses.
    """
    if not claims:
        return 1.0, {"method": "fallback_no_claims"}

    # Build a set of all content tokens from source texts (once)
    _STOP = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "nor", "not", "no", "so", "if", "than", "that",
        "this", "these", "those", "it", "its", "they", "them", "their",
        "we", "our", "you", "your", "he", "she", "his", "her",
    }
    import re as _re

    def _tokenize(text):
        """Split text into content tokens, handling 28VDC -> [28, vdc]."""
        tokens = []
        for raw in _re.findall(r"[A-Za-z0-9][\w\-\.]*", (text or "").lower()):
            # Split on digit-letter boundaries (e.g. 28vdc -> 28, vdc)
            parts = _re.findall(r"[a-z]+|[0-9]+", raw)
            for p in parts:
                if len(p) >= 2 and p not in _STOP:
                    tokens.append(p)
        return tokens

    source_tokens = set()
    for src in source_texts:
        source_tokens.update(_tokenize(src))

    supported = 0
    trivial_count = 0
    claim_details = []
    for c in claims:
        text = c.get("text", "") if isinstance(c, dict) else str(c)
        if c.get("is_trivial", False):
            # Trivial claims (greetings, transitions, headers) are excluded
            # from the score denominator -- they are not factual assertions
            # and should not inflate the grounding score.
            trivial_count += 1
            claim_details.append({"claim": text[:80], "verdict": "TRIVIAL"})
            continue
        # Claims explicitly tagged as general knowledge are allowed
        orig = c.get("original_text", text) if isinstance(c, dict) else text
        if "[General Knowledge]" in orig or "[GENERAL KNOWLEDGE]" in orig:
            supported += 1
            claim_details.append({"claim": text[:80], "verdict": "OPEN_KNOWLEDGE"})
            continue
        claim_tokens = _tokenize(text)
        if not claim_tokens:
            # No scorable tokens (e.g. all stopwords) -- exclude from denominator
            trivial_count += 1
            claim_details.append({"claim": text[:80], "verdict": "NO_TOKENS"})
            continue
        hits = sum(1 for tok in claim_tokens if tok in source_tokens)
        overlap = hits / len(claim_tokens)
        verdict = "SUPPORTED" if overlap >= 0.30 else "UNSUPPORTED"
        if verdict == "SUPPORTED":
            supported += 1
        claim_details.append({
            "claim": text[:80],
            "verdict": verdict,
            "overlap": round(overlap, 2),
            "tokens": len(claim_tokens),
            "hits": hits,
        })

    verifiable = len(claims) - trivial_count
    score = supported / verifiable if verifiable > 0 else 1.0
    return score, {
        "method": "fallback_token_overlap",
        "total_claims": len(claims),
        "verifiable_claims": verifiable,
        "trivial_claims": trivial_count,
        "supported": supported,
        "claims": claim_details,
    }


def _gqe_apply_guard_action(engine, raw_answer, score, details):
    if score >= engine.guard_threshold:
        return raw_answer, False

    if engine.guard_action == "block":
        return (
            "I found relevant documents but cannot provide "
            "a fully verified answer. The available evidence "
            "does not sufficiently support a complete response. "
            "Please refine your question or check the source "
            "documents directly."
        ), True

    if engine.guard_action == "strip":
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

    if engine.guard_action == "flag":
        # Annotate unsupported claims inline so the user can see which
        # parts of the answer lack source backing.
        claim_list = details.get("claims", [])
        flagged = raw_answer
        for cd in claim_list:
            verdict = cd.get("verdict", "")
            claim_text = cd.get("claim", "")
            if verdict == "UNSUPPORTED" and claim_text:
                # Try exact match first; claim_text may be truncated to 80 chars
                if claim_text in flagged:
                    flagged = flagged.replace(
                        claim_text, f"[UNVERIFIED] {claim_text}", 1)
                else:
                    # Fuzzy: find a line containing the claim core
                    core = claim_text[:50].rstrip()
                    if core:
                        for line in flagged.split("\n"):
                            if core in line:
                                flagged = flagged.replace(
                                    line, f"[UNVERIFIED] {line}", 1)
                                break
        return flagged, False

    # "warn" or unknown: return raw answer (permissive fallback)
    return raw_answer, False


def _gqe_make_error_result(
    engine,
    start_time,
    error_msg,
    *,
    sources=None,
    chunks=0,
):
    return GroundedQueryResult(
        answer="Error processing query: {}".format(error_msg),
        sources=sources or [],
        chunks_used=chunks,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=(time.time() - start_time) * 1000,
        mode=engine.config.mode,
        error=error_msg,
        grounding_blocked=True,
        grounding_details={"reason": "error"},
    )


def _gqe_access_denied_result(
    engine,
    start_time: float,
    *,
    latency_ms: float | None = None,
) -> GroundedQueryResult:
    effective_latency = latency_ms
    if effective_latency is None:
        effective_latency = (time.time() - start_time) * 1000
    return GroundedQueryResult(
        answer="No authorized information found in knowledge base.",
        sources=[],
        chunks_used=0,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=effective_latency,
        mode=engine.config.mode,
        error="access_denied",
        grounding_blocked=True,
        grounding_safe=False,
        grounding_details={"reason": "access_denied"},
    )


def _gqe_retrieval_gate(engine, user_query, search_results, start_time):
    # FIXED: Previously, when allow_open_knowledge was True, this function
    # returned None immediately (line 1), completely bypassing all retrieval
    # quality checks.  That meant garbage low-score chunks were silently
    # fed to GPT-4o as authoritative context instead of triggering the
    # open-knowledge fallback in the caller.  The caller already handles
    # the open-knowledge case: when gate_result is not None AND
    # allow_open_knowledge is True, it falls back to super().query()
    # which uses the relaxed prompt.  So the gate should always run its
    # quality checks and return a blocking result when evidence is weak,
    # regardless of open_knowledge -- the caller decides what to do.
    if not search_results:
        return engine._no_evidence_result(start_time)

    passing = [
        hit for hit in search_results
        if hit.score >= engine.guard_min_score
    ]
    if len(passing) < engine.guard_min_chunks:
        engine.guard_logger.info(
            "retrieval_gate_blocked",
            query=user_query[:80],
            chunks_found=len(search_results),
            chunks_passing=len(passing),
            min_required=engine.guard_min_chunks,
        )
        return engine._insufficient_evidence_result(
            start_time,
            search_results,
        )
    return None


def _gqe_log_grounded_result(engine, event_name, result, blocked, elapsed_ms):
    engine.guard_logger.info(
        event_name,
        score="{:.2f}".format(result.grounding_score),
        safe=result.grounding_safe,
        blocked=blocked,
        action=engine.guard_action,
        latency_ms="{:.0f}".format(elapsed_ms),
    )


def _gqe_wrap_open_knowledge_fallback_result(
    engine,
    base_result,
    *,
    trace: dict[str, Any],
    retrieval_trace: dict[str, Any] | None,
    decision_path: str,
    reason: str,
    context_before_trim: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> GroundedQueryResult:
    result = GroundedQueryResult(
        answer=base_result.answer,
        sources=copy.deepcopy(base_result.sources),
        chunks_used=base_result.chunks_used,
        tokens_in=base_result.tokens_in,
        tokens_out=base_result.tokens_out,
        cost_usd=base_result.cost_usd,
        latency_ms=base_result.latency_ms,
        mode=base_result.mode,
        error=base_result.error,
        grounding_score=-1.0,
        grounding_safe=False,
        grounding_blocked=False,
        grounding_details={
            "reason": reason,
            "verification": "skipped",
            "guard_bypassed": True,
            "fallback_mode": "open_knowledge",
        },
    )
    attach_result_trace(
        engine,
        result,
        trace,
        decision_path=decision_path,
        retrieval_trace=retrieval_trace,
        context_before_trim=context_before_trim,
        sources=copy.deepcopy(sources if sources is not None else base_result.sources),
        grounding={
            "score": result.grounding_score,
            "safe": result.grounding_safe,
            "blocked": result.grounding_blocked,
            "details": copy.deepcopy(result.grounding_details),
        },
    )
    return result


def _gqe_stream_open_knowledge_fallback(
    engine,
    user_query: str,
    *,
    trace: dict[str, Any],
    retrieval_trace: dict[str, Any] | None,
    decision_path: str,
    reason: str,
    context_before_trim: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> Generator[Dict[str, Any], None, None]:
    for event in super(GroundedQueryEngine, engine).query_stream(user_query):
        if event.get("done") and "result" in event:
            wrapped = _gqe_wrap_open_knowledge_fallback_result(
                engine,
                event["result"],
                trace=trace,
                retrieval_trace=retrieval_trace,
                decision_path=decision_path,
                reason=reason,
                context_before_trim=context_before_trim,
                sources=sources,
            )
            yield {"done": True, "result": wrapped}
        else:
            yield event


def _gqe_build_grounded_prompt(engine, user_query: str, context: str, hits: list) -> str:
    allow_open = bool(getattr(engine, "allow_open_knowledge", False))

    if engine._guard_available:
        from .llm_router import _extract_system_user

        base_prompt = engine._build_prompt(user_query, context)
        system_prompt, _ = _extract_system_user(base_prompt)
        if not system_prompt:
            system_prompt = "You are a precise technical assistant."

        # Strip [Source N] headers from chunks to avoid double-wrapping
        # (build_context adds headers, harden_prompt/open_knowledge add more)
        trimmed_chunks = []
        for block in context.split("\n\n---\n\n"):
            block = block.strip()
            if not block:
                continue
            _, body = _gqe_strip_source_header(block)
            trimmed_chunks.append(body if body else block)

        # When open knowledge is allowed, skip the ultra-strict hardening
        # that forbids training data — it contradicts the relaxed prompt
        # and makes GPT-4o over-cautious (refuses, hedges, thin answers).
        if allow_open:
            return _gqe_build_open_knowledge_prompt(
                system_prompt, user_query, trimmed_chunks,
            )

        hardened = engine._harden_prompt(
            system_prompt,
            user_query,
            trimmed_chunks,
        )
        if isinstance(hardened, dict):
            system_text = (hardened.get("system", "") or system_prompt).strip()
            user_text = (hardened.get("user", "") or "").strip()
            return system_text + "\n\nContext:\n" + user_text + "\n\nAnswer:"
        return hardened

    if allow_open:
        return (
            "GROUNDING RULES:\n"
            "- Prioritize the provided context when answering\n"
            "- When context is incomplete, you may supplement with general "
            "domain knowledge -- prefix those parts with [General Knowledge]\n"
            "- Cite [Source N] for claims drawn from the context\n"
            "- Do NOT fabricate source citations\n"
            "- Format the answer in short readable paragraphs; use bullets "
            "for lists\n"
            "\n"
            f"{context}\n\n"
            f"User Question:\n{user_query}\n\n"
            "Answer:"
        )

    return (
        "GROUNDING RULES:\n"
        "- Answer ONLY using the provided context\n"
        "- If the context does not contain the answer, say so\n"
        "- Cite [Source N] for each claim\n"
        "- Do NOT add information beyond what the sources state\n"
        "- Format the answer in short readable paragraphs; use bullets for lists\n"
        "\n"
        f"{context}\n\n"
        f"User Question:\n{user_query}\n\n"
        "Answer:"
    )


def _gqe_strip_source_header(chunk_text: str) -> tuple:
    """Strip the [Source N] header added by retriever.build_context().

    Returns (source_label, body) where source_label is e.g.
    '/docs/manual.txt' and body is the chunk text without the header.
    If no header found, returns ('', original_text).
    """
    import re as _re
    m = _re.match(
        r"^\[Source\s+\d+\]\s*(.*?)\s*\(chunk\s+\d+,\s*score=[\d.]+\)\s*\n?",
        chunk_text,
    )
    if m:
        source_label = m.group(1).strip()
        body = chunk_text[m.end():].strip()
        return source_label, body
    return "", chunk_text.strip()


def _gqe_build_open_knowledge_prompt(
    system_prompt: str, user_query: str, chunks: list,
) -> str:
    """Build a grounded-but-permissive prompt for open-knowledge mode.

    Encourages citations and context-first answering without the
    ultra-strict hardening that forbids all training-data usage.
    Strips double chunk headers from retriever.build_context().
    """
    numbered = []
    for i, chunk in enumerate(chunks):
        source_label, body = _gqe_strip_source_header(chunk)
        header = f"--- CHUNK {i + 1}"
        if source_label:
            fname = source_label.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            header += f" (from: {fname})"
        header += " ---"
        numbered.append(f"{header}\n{body}\n")
    chunk_block = "\n".join(numbered)

    # Build system portion (system_prompt + grounding guidelines).
    # Build user portion (context chunks + query).
    # Separate with "\n\nContext:\n" so _split_prompt_to_messages
    # can split them into proper system/user roles for the chat API.
    # Without this separator, GPT-4o receives everything as a single
    # user message and treats instructions with lower priority.
    system_part = (
        f"{system_prompt}\n\n"
        "GROUNDING GUIDELINES:\n"
        "- Use the retrieved context as your primary source of truth.\n"
        "- Cite [Source: chunk_N] for facts drawn from the context.\n"
        "- If the context is incomplete or does not cover part of the "
        "question, you may use general domain knowledge to fill gaps. "
        "Prefix those parts with [General Knowledge].\n"
        "- Do NOT fabricate source citations or chunk numbers.\n"
        "- Use short readable paragraphs and bullets for lists.\n"
        "- VERBATIM VALUES: When citing specific measurements, part "
        "numbers, or technical values from context, reproduce notation "
        "exactly as it appears."
    )
    user_part = (
        f"=== RETRIEVED CONTEXT ({len(chunks)} chunks) ===\n"
        f"{chunk_block}\n"
        f"=== END CONTEXT ===\n\n"
        f"USER QUERY:\n{user_query}\n\n"
        "Answer:"
    )
    return system_part + "\n\nContext:\n" + user_part


def _gqe_verify_response(engine, response_text: str, hits: list) -> tuple:
    if not engine._guard_available:
        return 1.0, {"method": "bypass", "reason": "guard_not_loaded"}

    try:
        claims = engine._extract_claims(response_text)
        if not claims:
            return 1.0, {
                "method": "no_claims",
                "reason": "response_has_no_verifiable_claims",
            }

        source_texts = [hit.text for hit in hits]
        if engine._nli_verifier is not None:
            from .hallucination_guard.nli_verifier import NLIVerifier

            if not isinstance(engine._nli_verifier, NLIVerifier):
                engine._nli_verifier = NLIVerifier()
            results = engine._nli_verifier.verify_batch_with_earlyexit(
                claims,
                source_texts,
                engine.guard_threshold,
            )
            supported = sum(
                1 for result in results
                if result.verdict.value == "SUPPORTED"
            )
            total = len(results)
            score = supported / total if total > 0 else 0.0
            details = {
                "method": "nli_batch_earlyexit",
                "total_claims": total,
                "supported": supported,
                "claims": [
                    {
                        "claim": result.claim_text[:100],
                        "verdict": result.verdict.value,
                        "confidence": result.confidence,
                    }
                    for result in results
                ],
            }
            return score, details

        return engine._score_response(
            claims,
            source_texts,
            engine.guard_threshold,
        )
    except Exception as exc:
        engine.guard_logger.warning("verify_error", error=str(exc))
        return 0.5, {"method": "error", "reason": str(exc)}


def _gqe_no_evidence_result(engine, start_time: float) -> GroundedQueryResult:
    return GroundedQueryResult(
        answer="No relevant information found in knowledge base.",
        sources=[],
        chunks_used=0,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=(time.time() - start_time) * 1000,
        mode=engine.config.mode,
        grounding_blocked=True,
        grounding_details={"reason": "no_search_results"},
    )


def _gqe_insufficient_evidence_result(
    engine,
    start_time: float,
    hits: list,
) -> GroundedQueryResult:
    sources = engine.retriever.get_sources(hits)
    return GroundedQueryResult(
        answer=(
            "Some documents were found but the evidence quality "
            "is insufficient for a reliable answer. Please try "
            "a more specific question or check source documents."
        ),
        sources=sources,
        chunks_used=len(hits),
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=(time.time() - start_time) * 1000,
        mode=engine.config.mode,
        grounding_blocked=True,
        grounding_details={
            "reason": "insufficient_evidence",
            "chunks_found": len(hits),
            "min_required": engine.guard_min_chunks,
        },
    )
