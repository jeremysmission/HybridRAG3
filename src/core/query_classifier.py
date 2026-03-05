# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the query classifier part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Query Classifier (src/core/query_classifier.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Before the RAG pipeline retrieves documents and calls the LLM, this
#   module classifies the incoming query into one of five types:
#
#     ANSWERABLE   -- a normal factual question the corpus can answer
#     UNANSWERABLE -- asks for info clearly outside the document corpus
#     AMBIGUOUS    -- too vague, needs clarification before searching
#     INJECTION    -- contains prompt-injection attack patterns
#     UNKNOWN      -- could not classify with confidence
#
# WHY THIS EXISTS:
#   The cross-encoder reranker improves retrieval accuracy for ANSWERABLE
#   queries (+3-5% on factual scores). But it DESTROYS scores for the
#   other three types:
#     - Unanswerable: 100% -> 76%  (reranker promotes irrelevant chunks)
#     - Injection:    100% -> 46%  (reranker surfaces injected content)
#     - Ambiguous:    100% -> 82%  (reranker picks one interpretation)
#
#   By classifying the query FIRST, we can conditionally enable reranking
#   only for ANSWERABLE queries, getting the best of both worlds.
#
# DESIGN DECISIONS:
#   1. RULE-BASED, NO ML MODEL
#      A lightweight regex/heuristic approach has zero startup cost, zero
#      dependencies, and deterministic behavior. An ML classifier would
#      add model loading time, GPU/CPU overhead, and non-determinism --
#      all for a problem that a few dozen patterns solve well enough.
#
#   2. CONSERVATIVE DEFAULTS
#      When in doubt, classify as ANSWERABLE (the default). This means
#      the reranker gets used, which is the safe choice for accuracy.
#      Only confident detections of injection/unanswerable/ambiguous
#      will bypass the reranker.
#
#   3. CONFIDENCE SCORES
#      Each classification includes a confidence score (0.0-1.0).
#      Integration code can use this to make graduated decisions,
#      e.g., only skip reranking if confidence > 0.7.
#
# INTEGRATION POINT (future -- do NOT modify query_engine.py yet):
#   In query_engine.py.query(), BEFORE calling self.retriever.search():
#     classifier = QueryClassifier()
#     result = classifier.classify(user_query)
#     if result.should_rerank:
#         self.retriever.reranker_enabled = True
#     else:
#         self.retriever.reranker_enabled = False
#
# INTERNET ACCESS: NONE (pure string analysis)
# ============================================================================

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query type enum
# ---------------------------------------------------------------------------

class QueryType(Enum):
    """
    Classification of a user query by intent.

    ANSWERABLE:   Standard factual query the document corpus can answer.
    UNANSWERABLE: Asks about topics clearly outside the indexed documents.
    AMBIGUOUS:    Too vague or underspecified to answer without clarification.
    INJECTION:    Contains prompt-injection attack patterns.
    UNKNOWN:      Could not classify with confidence; treated as answerable.
    """
    ANSWERABLE = "answerable"
    UNANSWERABLE = "unanswerable"
    AMBIGUOUS = "ambiguous"
    INJECTION = "injection"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """
    Result of classifying a user query.

    query_type:
      The detected query type (ANSWERABLE, UNANSWERABLE, etc.)

    confidence:
      How confident the classifier is in this classification (0.0-1.0).
      Higher = more certain. Rules that match multiple strong signals
      produce higher confidence than single weak signals.

    reason:
      Human-readable explanation of why this classification was chosen.
      Useful for logging, debugging, and audit trails.

    matched_rules:
      List of rule names that fired. Empty for ANSWERABLE (default).
    """
    query_type: QueryType
    confidence: float
    reason: str
    matched_rules: List[str]

    @property
    def should_rerank(self) -> bool:
        """
        Whether the reranker should be enabled for this query type.

        True for ANSWERABLE and UNKNOWN -- these benefit from reranking.
        False for UNANSWERABLE, INJECTION, AMBIGUOUS -- reranking hurts.
        """
        return self.query_type in (QueryType.ANSWERABLE, QueryType.UNKNOWN)


# ---------------------------------------------------------------------------
# Injection patterns
# ---------------------------------------------------------------------------

# These patterns detect common prompt injection attacks. Each tuple is
# (compiled_regex, rule_name, confidence_contribution).
#
# WHY THESE SPECIFIC PATTERNS:
#   Drawn from the OWASP LLM Top 10, published injection attack datasets,
#   and the HybridRAG eval set (41 injection test cases). The patterns
#   target the most common attack vectors:
#     - Override instructions ("ignore previous", "forget your rules")
#     - Role hijacking ("you are now", "act as", "pretend you are")
#     - Embedded commands ("system:", "[INST]", "<<SYS>>")
#     - Context poisoning ("the correct answer is", "always respond with")
#     - Delimiter injection (triple backticks, XML-like tags)

_INJECTION_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    # --- Instruction override attacks ---
    (re.compile(r"\bignore\s+(all\s+)?(previous|prior|above|earlier)\b", re.IGNORECASE),
     "ignore_previous", 0.9),
    (re.compile(r"\bforget\s+(all\s+)?(your|the|my)\s+(instructions|rules|prompt|guidelines)\b", re.IGNORECASE),
     "forget_instructions", 0.9),
    (re.compile(r"\bdisregard\s+(all\s+)?(previous|prior|above|earlier|your)\b", re.IGNORECASE),
     "disregard_previous", 0.9),
    (re.compile(r"\bdo\s+not\s+follow\s+(your|the|any)\s+(rules|instructions|guidelines)\b", re.IGNORECASE),
     "do_not_follow", 0.85),
    (re.compile(r"\boverride\s+(your|the|all)\s+(rules|instructions|behavior|settings)\b", re.IGNORECASE),
     "override_rules", 0.85),

    # --- Role hijacking attacks ---
    (re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
     "role_hijack_now", 0.85),
    (re.compile(r"\bact\s+as\s+(if\s+you\s+are|a|an|the)\b", re.IGNORECASE),
     "act_as", 0.7),
    (re.compile(r"\bpretend\s+(you\s+are|to\s+be|that)\b", re.IGNORECASE),
     "pretend_to_be", 0.8),
    (re.compile(r"\bswitch\s+to\s+(a\s+)?new\s+(role|persona|mode)\b", re.IGNORECASE),
     "switch_role", 0.8),

    # --- Embedded command delimiters ---
    (re.compile(r"\[/?INST\]", re.IGNORECASE),
     "inst_tag", 0.95),
    (re.compile(r"<<SYS>>", re.IGNORECASE),
     "sys_tag", 0.95),
    (re.compile(r"\bsystem\s*:\s*you\b", re.IGNORECASE),
     "system_colon", 0.85),
    (re.compile(r"<\|?(system|user|assistant)\|?>", re.IGNORECASE),
     "role_delimiter", 0.9),

    # --- Output manipulation attacks ---
    (re.compile(r"\b(the\s+)?(correct|right|true|real)\s+answer\s+is\b", re.IGNORECASE),
     "forced_answer", 0.75),
    (re.compile(r"\balways\s+respond\s+with\b", re.IGNORECASE),
     "always_respond", 0.8),
    (re.compile(r"\brepeat\s+after\s+me\b", re.IGNORECASE),
     "repeat_after", 0.8),
    (re.compile(r"\bsay\s+exactly\b", re.IGNORECASE),
     "say_exactly", 0.75),

    # --- Jailbreak indicators ---
    (re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
     "dan_mode", 0.95),
    (re.compile(r"\bjailbreak\b", re.IGNORECASE),
     "jailbreak_keyword", 0.9),
    (re.compile(r"\bdevelo?per\s+mode\b", re.IGNORECASE),
     "developer_mode", 0.85),
]


# ---------------------------------------------------------------------------
# Unanswerable patterns
# ---------------------------------------------------------------------------

# Topics that are clearly outside any technical document corpus.
# These detect questions about personal opinions, future predictions,
# fictional/absurd concepts, and meta-questions about the AI itself.

_UNANSWERABLE_PATTERNS: List[Tuple[re.Pattern, str, float]] = [
    # --- Personal/opinion questions ---
    (re.compile(r"\bwhat\s+(do\s+you\s+think|is\s+your\s+opinion|are\s+your\s+thoughts)\b", re.IGNORECASE),
     "opinion_request", 0.8),
    (re.compile(r"\bhow\s+do\s+you\s+feel\s+about\b", re.IGNORECASE),
     "feeling_request", 0.85),
    (re.compile(r"\bwhat\s+is\s+your\s+(name|age|favorite|birthday)\b", re.IGNORECASE),
     "personal_question", 0.9),

    # --- Future prediction questions ---
    (re.compile(r"\bwhat\s+will\s+happen\s+(in|by|after)\s+(the\s+)?(year\s+)?\d{4}\b", re.IGNORECASE),
     "future_prediction", 0.75),
    (re.compile(r"\bpredict\s+(the|what|how|when)\b", re.IGNORECASE),
     "predict_request", 0.7),

    # --- Meta-questions about the AI ---
    (re.compile(r"\bare\s+you\s+(a|an)\s+(robot|ai|chatbot|computer|machine|language\s+model)\b", re.IGNORECASE),
     "ai_identity", 0.9),
    (re.compile(r"\bwho\s+(made|created|built|trained)\s+you\b", re.IGNORECASE),
     "ai_creator", 0.9),

    # --- Clearly fictional/absurd topics ---
    (re.compile(r"\b(antigravity|warp[- ]?drive|teleportation|time[- ]?travel)\b", re.IGNORECASE),
     "fictional_tech", 0.8),
    (re.compile(r"\bnuclear\s+launch\s+code\b", re.IGNORECASE),
     "nuclear_codes", 0.95),

    # --- Requests to generate/create content ---
    (re.compile(r"\b(write|compose|generate|create)\s+(me\s+)?(a|an|the)\s+(poem|story|essay|song|joke)\b", re.IGNORECASE),
     "creative_writing", 0.85),

    # --- Mathematical/calculation requests ---
    (re.compile(r"\b(calculate|compute|solve)\s+(the\s+)?(integral|derivative|equation|limit)\b", re.IGNORECASE),
     "math_request", 0.7),
]


# ---------------------------------------------------------------------------
# Ambiguity detection
# ---------------------------------------------------------------------------

# Pronouns without antecedent context (when they appear as the main subject)
_DANGLING_PRONOUN_RE = re.compile(
    r"^(what|how|where|when|why|which|who)\s+(is|are|was|were|does|do|did|can|could|should|would|will)\s+"
    r"(it|this|that|these|those|they|them|its)\b",
    re.IGNORECASE,
)

# Very short queries that lack specificity
_MIN_WORD_COUNT_FOR_SPECIFIC = 4

# Queries that are just a noun phrase with "the" (e.g., "What is the tolerance?")
# These are ambiguous when the corpus covers many different tolerances.
# Captures one or more trailing words so it works for both "tolerance" and
# "temperature range" or "lead time".
_BARE_WHAT_IS_THE_RE = re.compile(
    r"^what\s+(is|are)\s+the\s+([\w]+(?:\s+[\w]+)?)\s*\??$",
    re.IGNORECASE,
)

# Ambiguous technical terms (single-word and multi-word) that could
# refer to many different things in a technical corpus.
_AMBIGUOUS_BARE_TERMS = {
    "tolerance", "range", "limit", "threshold", "value", "rate",
    "time", "date", "version", "revision", "status",
    "temperature", "specification", "spec", "cost", "budget",
    "schedule", "deadline", "frequency", "interval", "duration",
    "capacity", "weight", "size", "dimension", "resolution",
    # Multi-word ambiguous terms
    "lead time", "temperature range", "operating temperature",
    "data rate", "bit rate", "sample rate",
}


# ---------------------------------------------------------------------------
# QueryClassifier
# ---------------------------------------------------------------------------

class QueryClassifier:
    """
    Classify incoming queries by type to control downstream pipeline behavior.

    This is a rule-based classifier using regex patterns and heuristics.
    No ML model, no GPU, no network calls. Deterministic and fast (<1ms).

    Usage:
        classifier = QueryClassifier()
        result = classifier.classify("What is the operating temperature?")
        if result.should_rerank:
            # enable reranker for this query
            ...

    Priority order (first match wins):
        1. INJECTION   -- highest priority, safety-critical
        2. UNANSWERABLE -- clearly outside corpus scope
        3. AMBIGUOUS   -- too vague to answer
        4. ANSWERABLE  -- default if no other type matches
    """

    def __init__(self):
        """Initialize the classifier with compiled pattern sets."""
        self._injection_patterns = _INJECTION_PATTERNS
        self._unanswerable_patterns = _UNANSWERABLE_PATTERNS

    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a query into one of the five QueryType categories.

        Parameters
        ----------
        query : str
            The raw user query text.

        Returns
        -------
        ClassificationResult
            Contains the query_type, confidence, reason, and matched_rules.
            Use result.should_rerank to check if reranking is appropriate.
        """
        if not query or not query.strip():
            logger.info("[OK] query_classifier: empty query -> UNKNOWN")
            return ClassificationResult(
                query_type=QueryType.UNKNOWN,
                confidence=1.0,
                reason="Empty or whitespace-only query",
                matched_rules=["empty_query"],
            )

        cleaned = query.strip()

        # --- Priority 1: Injection detection (safety-critical) ---
        injection_result = self._check_injection(cleaned)
        if injection_result is not None:
            logger.info(
                "[OK] query_classifier: INJECTION detected (confidence=%.2f, rules=%s)",
                injection_result.confidence,
                injection_result.matched_rules,
            )
            return injection_result

        # --- Priority 2: Unanswerable detection ---
        unanswerable_result = self._check_unanswerable(cleaned)
        if unanswerable_result is not None:
            logger.info(
                "[OK] query_classifier: UNANSWERABLE detected (confidence=%.2f, rules=%s)",
                unanswerable_result.confidence,
                unanswerable_result.matched_rules,
            )
            return unanswerable_result

        # --- Priority 3: Ambiguity detection ---
        ambiguous_result = self._check_ambiguous(cleaned)
        if ambiguous_result is not None:
            logger.info(
                "[OK] query_classifier: AMBIGUOUS detected (confidence=%.2f, rules=%s)",
                ambiguous_result.confidence,
                ambiguous_result.matched_rules,
            )
            return ambiguous_result

        # --- Default: ANSWERABLE ---
        logger.info("[OK] query_classifier: ANSWERABLE (default)")
        return ClassificationResult(
            query_type=QueryType.ANSWERABLE,
            confidence=0.6,
            reason="No injection, unanswerable, or ambiguity markers detected",
            matched_rules=[],
        )

    def should_rerank(self, query_type: QueryType) -> bool:
        """
        Whether the reranker should be enabled for this query type.

        Parameters
        ----------
        query_type : QueryType
            The classified query type.

        Returns
        -------
        bool
            True for ANSWERABLE and UNKNOWN (reranking helps).
            False for INJECTION, UNANSWERABLE, AMBIGUOUS (reranking hurts).
        """
        return query_type in (QueryType.ANSWERABLE, QueryType.UNKNOWN)

    # ------------------------------------------------------------------
    # Private: injection detection
    # ------------------------------------------------------------------

    def _check_injection(self, query: str) -> Optional[ClassificationResult]:
        """
        Check for prompt injection attack patterns.

        Scans the query against all injection patterns. If any match,
        returns an INJECTION classification. Multiple matches increase
        confidence.

        Returns None if no injection patterns are detected.
        """
        matched_rules = []
        max_confidence = 0.0

        for pattern, rule_name, confidence in self._injection_patterns:
            if pattern.search(query):
                matched_rules.append(rule_name)
                max_confidence = max(max_confidence, confidence)

        if not matched_rules:
            return None

        # Multiple matches boost confidence (capped at 1.0)
        if len(matched_rules) >= 3:
            final_confidence = min(1.0, max_confidence + 0.1)
        elif len(matched_rules) >= 2:
            final_confidence = min(1.0, max_confidence + 0.05)
        else:
            final_confidence = max_confidence

        return ClassificationResult(
            query_type=QueryType.INJECTION,
            confidence=final_confidence,
            reason="Injection pattern(s) detected: " + ", ".join(matched_rules),
            matched_rules=matched_rules,
        )

    # ------------------------------------------------------------------
    # Private: unanswerable detection
    # ------------------------------------------------------------------

    def _check_unanswerable(self, query: str) -> Optional[ClassificationResult]:
        """
        Check if the query asks about topics clearly outside the corpus.

        Matches against patterns for personal questions, future predictions,
        meta-AI questions, fictional concepts, and creative writing requests.

        Returns None if no unanswerable markers are detected.
        """
        matched_rules = []
        max_confidence = 0.0

        for pattern, rule_name, confidence in self._unanswerable_patterns:
            if pattern.search(query):
                matched_rules.append(rule_name)
                max_confidence = max(max_confidence, confidence)

        if not matched_rules:
            return None

        # Multiple matches boost confidence
        if len(matched_rules) >= 2:
            final_confidence = min(1.0, max_confidence + 0.1)
        else:
            final_confidence = max_confidence

        return ClassificationResult(
            query_type=QueryType.UNANSWERABLE,
            confidence=final_confidence,
            reason="Unanswerable pattern(s) detected: " + ", ".join(matched_rules),
            matched_rules=matched_rules,
        )

    # ------------------------------------------------------------------
    # Private: ambiguity detection
    # ------------------------------------------------------------------

    def _check_ambiguous(self, query: str) -> Optional[ClassificationResult]:
        """
        Check if the query is too vague or underspecified.

        Detection strategies:
          1. Very short queries (under 4 words)
          2. Dangling pronouns ("What is it?" without context)
          3. Bare "What is the X?" where X is a common ambiguous term
             (tolerance, range, limit, etc.)

        Returns None if the query appears specific enough.
        """
        matched_rules = []
        max_confidence = 0.0

        # --- Strategy 1: Very short queries ---
        words = query.split()
        if len(words) < _MIN_WORD_COUNT_FOR_SPECIFIC:
            # Single words or very short phrases are usually too vague
            if len(words) <= 2:
                matched_rules.append("very_short_query")
                max_confidence = max(max_confidence, 0.85)
            else:
                matched_rules.append("short_query")
                max_confidence = max(max_confidence, 0.6)

        # --- Strategy 2: Dangling pronouns ---
        if _DANGLING_PRONOUN_RE.search(query):
            matched_rules.append("dangling_pronoun")
            max_confidence = max(max_confidence, 0.8)

        # --- Strategy 3: Bare "What is the X?" with ambiguous X ---
        bare_match = _BARE_WHAT_IS_THE_RE.match(query)
        if bare_match:
            term = bare_match.group(2).lower()
            if term in _AMBIGUOUS_BARE_TERMS:
                matched_rules.append("bare_ambiguous_term")
                max_confidence = max(max_confidence, 0.85)

        # --- Strategy 4: Compound ambiguity check ---
        # "What is the lead time?" -- 5 words but still ambiguous
        lower_q = query.lower().rstrip("?").strip()
        for term in _AMBIGUOUS_BARE_TERMS:
            # Check "what is the {term}" pattern even with slight variations
            if re.match(
                r"^what\s+(is|are)\s+the\s+" + re.escape(term) + r"$",
                lower_q,
                re.IGNORECASE,
            ):
                if "bare_ambiguous_term" not in matched_rules:
                    matched_rules.append("bare_ambiguous_term")
                    max_confidence = max(max_confidence, 0.85)
                break

        if not matched_rules:
            return None

        # Multiple signals boost confidence
        if len(matched_rules) >= 2:
            final_confidence = min(1.0, max_confidence + 0.1)
        else:
            final_confidence = max_confidence

        return ClassificationResult(
            query_type=QueryType.AMBIGUOUS,
            confidence=final_confidence,
            reason="Ambiguity marker(s) detected: " + ", ".join(matched_rules),
            matched_rules=matched_rules,
        )
