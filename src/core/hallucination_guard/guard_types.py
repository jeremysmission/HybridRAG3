#!/usr/bin/env python3
"""
guard_types.py -- Shared Constants, Enums, and Data Classes
============================================================

PURPOSE:
    Central type definitions for the hallucination guard system.
    Every other module in this package imports from here.
    Keeping types in one file prevents circular imports and
    gives reviewers a single place to understand the data model.

WHAT IS IN HERE:
    1. CONSTANTS   -- Model name, thresholds, word lists
    2. ClaimVerdict -- Enum: what happened when we checked a claim
    3. ClaimResult  -- One claim's verification result
    4. GuardResult  -- The final verdict for an entire LLM response
    5. GuardConfig  -- All tunable settings (with env var overrides)

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.1.0
DATE: 2026-02-14

PINNED STACK (from HybridRAG3 rag8.zip, verified Feb 2026):
    sentence-transformers==2.7.0   (DIRECT -- only non-stdlib import)
    torch==2.10.0                  (transitive, via sentence-transformers)
    transformers==4.57.6           (transitive, via sentence-transformers)
    tokenizers==0.22.2             (transitive, via transformers)
    huggingface_hub==0.36.1        (transitive, via sentence-transformers)
    numpy==1.26.4                  (transitive, via torch/scipy)

COMPATIBILITY NOTES:
    - CrossEncoder API (constructor + predict) stable across ST 2.x-5.x
    - numpy 1.26.4 works with torch 2.10 (deprecation warnings only)
    - RTX 5080 needs torch cu128 wheel (CUDA 12.8+)
    - Run verify_compatibility.py after install to confirm
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


# =============================================================================
# VERSION PINS -- Embedded here so the code itself documents what it needs.
# These match HybridRAG3's requirements.txt from rag8.zip (Feb 2026).
# If you change any version, run verify_compatibility.py to recheck.
# =============================================================================
REQUIRED_VERSIONS = {
    "sentence-transformers": "2.7.0",   # CrossEncoder for NLI verification
    "torch":                "2.10.0",   # ML backend (CPU or CUDA)
    "transformers":         "4.57.6",   # Hugging Face model loading
    "tokenizers":           "0.22.2",   # Fast tokenization
    "numpy":                "1.26.4",   # Numeric ops (DO NOT upgrade to 2.x)
}

# =============================================================================
# CONSTANTS
# =============================================================================
# These are used across multiple modules, so they live here centrally.

# The NLI model we use to check if source chunks support or contradict claims.
# Why this model: 90.04% accuracy on MNLI benchmark, runs offline after download.
# Alternatives considered:
#   cross-encoder/nli-roberta-base       -- Smaller, slightly less accurate
#   cross-encoder/nli-MiniLM2-L6-H768    -- Much smaller (80MB), faster, less accurate
#   vectara/hallucination_evaluation_model -- Purpose-built but dependency conflicts
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"

# The NLI model outputs 3 labels as array indices.
# Index 0 = Contradiction, Index 1 = Entailment, Index 2 = Neutral.
# These constants make the code readable instead of using magic numbers.
NLI_LABEL_CONTRADICTION = 0
NLI_LABEL_ENTAILMENT = 1
NLI_LABEL_NEUTRAL = 2

# Default threshold: 80% of claims must be backed by source docs.
# Research says 0.80-0.90 is optimal for high-stakes domains.
# In defense context: a false positive (flagging a good claim) is cheap,
# a false negative (passing a bad claim) can be catastrophic.
DEFAULT_FAITHFULNESS_THRESHOLD = 0.80

# Zero tolerance for contradictions. If ANY claim directly conflicts with
# a source document, the response is marked unsafe regardless of overall score.
DEFAULT_CONTRADICTION_THRESHOLD = 0.00

# --- Hedge words (GOOD) ---
# When the LLM uses these, it shows appropriate uncertainty.
# We WANT to see these on claims the LLM isn't sure about.
HEDGE_WORDS = [
    "may", "might", "could", "possibly", "potentially", "likely",
    "approximately", "around", "roughly", "estimated", "appears to",
    "suggests", "indicates", "based on the available", "according to",
    "it seems", "unclear", "uncertain", "not confirmed",
    "sources indicate", "the document states",
]

# --- Overconfidence markers (BAD) ---
# When the LLM uses these on UNVERIFIED claims, it is dangerously confident.
# "The system DEFINITELY operates at 15 MHz" (source says 10 MHz) = deadly.
OVERCONFIDENCE_MARKERS = [
    "definitely", "certainly", "absolutely", "without doubt",
    "it is clear that", "obviously", "undeniably", "proven",
    "always", "never", "guaranteed", "100%", "impossible",
    "everyone knows", "as is well known", "of course",
]

# Logging format -- plain text, timestamp first, no emojis, ASCII-safe.
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# =============================================================================
# ENUMS
# =============================================================================

class ClaimVerdict(Enum):
    """
    The result of verifying a single claim against source context.

    Think of it like a traffic light for each sentence in the LLM response:

    SUPPORTED:    GREEN  -- Source chunk backs this claim. Safe to show.
    CONTRADICTED: RED    -- Source chunk CONFLICTS with this claim. Remove it.
    UNSUPPORTED:  YELLOW -- No source confirms or denies. Flag for review.
    TRIVIAL:      WHITE  -- Not a factual claim (greeting, header, transition).
    """
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNSUPPORTED = "UNSUPPORTED"
    TRIVIAL = "TRIVIAL"


# =============================================================================
# DATA CLASSES
# =============================================================================
# These are plain data holders (like structs in C). Each one groups related
# fields together so we pass one object instead of a dozen loose variables.

@dataclass
class ClaimResult:
    """
    Verification result for a single factual claim.

    Fields:
        claim_text:  The sentence we checked (cleaned of citation markers)
        verdict:     SUPPORTED / CONTRADICTED / UNSUPPORTED / TRIVIAL
        confidence:  0.0-1.0 how confident the NLI model is in its verdict
        best_source: The chunk text that best supports/contradicts (truncated)
        source_file: Which file that chunk came from (for traceability)
        nli_scores:  Raw NLI model output [contradiction, entailment, neutral]
        explanation: Human-readable reason for the verdict
    """
    claim_text: str
    verdict: ClaimVerdict
    confidence: float = 0.0
    best_source: str = ""
    source_file: str = ""
    nli_scores: List[float] = field(default_factory=list)
    explanation: str = ""


@dataclass
class GuardResult:
    """
    Complete result of hallucination guard verification for one LLM response.

    This is what query_engine.py receives back and uses to decide what to
    show the user. The two most important fields are:
        is_safe:       True if OK to show as-is, False if needs intervention
        safe_response: The modified response (flagged/stripped/blocked/warned)

    Fields:
        is_safe:              Pass/fail overall
        original_response:    The LLM's raw text (before any modification)
        safe_response:        Modified text based on failure_action setting
        faithfulness_score:   0.0-1.0 (supported_claims / total_claims)
        supported_count:      How many claims the sources back up
        contradicted_count:   How many claims CONFLICT with sources (worst case)
        unsupported_count:    How many claims have no source backing
        trivial_count:        Non-factual sentences (greetings, headers)
        total_claims:         Total sentences analyzed
        claim_results:        List of ClaimResult for each sentence
        contradictions:       Text of contradicted claims (quick access)
        unverified_claims:    Text of unsupported claims (quick access)
        confidence_warnings:  Overconfidence alerts
        verification_time_ms: How long verification took (performance metric)
        active_layers:        Which defense layers ran
        timestamp:            ISO format when verification happened
        verification_id:      Unique ID linking to audit log
    """
    is_safe: bool
    original_response: str
    safe_response: str
    faithfulness_score: float
    supported_count: int = 0
    contradicted_count: int = 0
    unsupported_count: int = 0
    trivial_count: int = 0
    total_claims: int = 0
    claim_results: List[ClaimResult] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    unverified_claims: List[str] = field(default_factory=list)
    confidence_warnings: List[str] = field(default_factory=list)
    verification_time_ms: float = 0.0
    active_layers: List[str] = field(default_factory=list)
    timestamp: str = ""
    verification_id: str = ""


@dataclass
class GuardConfig:
    """
    Configuration for the Hallucination Guard.

    All settings can be overridden three ways (in priority order):
        1. Pass directly when creating HallucinationGuard(config=GuardConfig(...))
        2. Environment variables (see from_env())
        3. HybridRAG3 config.yaml (see from_hybridrag_config())

    Tuning guidance:
        Conservative (defense-critical): threshold=0.90, action="block"
        Balanced (DEFAULT):              threshold=0.80, action="flag"
        Permissive (research/exploration): threshold=0.60, action="warn"
    """
    # --- NLI Model Settings ---
    nli_model_name: str = NLI_MODEL_NAME      # Which cross-encoder to use
    model_cache_dir: str = ".model_cache"      # Where to store downloaded model

    # --- Faithfulness Gating ---
    faithfulness_threshold: float = DEFAULT_FAITHFULNESS_THRESHOLD  # 0.80
    contradiction_threshold: float = DEFAULT_CONTRADICTION_THRESHOLD  # 0.00
    # failure_action controls what happens when faithfulness is below threshold:
    #   "block" = Return error message, hide the response entirely
    #   "flag"  = Show response with [UNVERIFIED] / [CONTRADICTED] markers (DEFAULT)
    #   "strip" = Remove unverified claims, show only verified content
    #   "warn"  = Show full response with warning header
    failure_action: str = "flag"

    # --- Confidence Calibration ---
    enable_confidence_check: bool = True       # Check for overconfident language
    max_overconfidence_markers: int = 2        # How many before escalating

    # --- Dual-Path Consensus ---
    enable_dual_path: bool = False             # Run both offline + online
    consensus_threshold: float = 0.70          # Min agreement to trust online

    # --- Processing Limits ---
    max_claims_per_response: int = 50          # Cap claims to prevent runaway
    nli_batch_size: int = 16                   # NLI model batch size
    timeout_seconds: int = 30                  # Max verification time

    # --- Logging & Audit ---
    log_dir: str = "logs"                      # Where audit logs go
    enable_audit_log: bool = True              # Write JSONL audit trail
    audit_log_file: str = "hallucination_audit.jsonl"  # Audit log filename

    # --- Network Control ---
    offline_mode: bool = False                 # Block all downloads (air-gap)

    @classmethod
    def from_hybridrag_config(cls, hybridrag_config):
        """
        Create GuardConfig from an existing HybridRAG3 config dict.

        HOW IT WORKS:
            Reads the hallucination_guard section from your config.yaml
            and maps its keys to GuardConfig fields. Any keys not present
            in the YAML get the defaults shown above.

        PARAMETERS:
            hybridrag_config: dict loaded from config.yaml

        RETURNS:
            GuardConfig instance with merged settings
        """
        gc = cls()
        if isinstance(hybridrag_config, dict):
            hg = hybridrag_config.get("hallucination_guard", {})
            gc.faithfulness_threshold = hg.get(
                "faithfulness_threshold", gc.faithfulness_threshold)
            gc.failure_action = hg.get("failure_action", gc.failure_action)
            gc.enable_dual_path = hg.get(
                "enable_dual_path", gc.enable_dual_path)
            gc.model_cache_dir = hybridrag_config.get(
                "model_cache_dir", gc.model_cache_dir)
            gc.log_dir = hybridrag_config.get("log_dir", gc.log_dir)
            gc.offline_mode = hybridrag_config.get(
                "security", {}).get("offline_mode", gc.offline_mode)
        return gc

    @classmethod
    def from_env(cls):
        """
        Create GuardConfig from environment variables.

        This is useful for quick overrides without editing config.yaml.
        Set any of these in your terminal before running HybridRAG3:

            HALLUCINATION_GUARD_THRESHOLD  -- float 0.0-1.0
            HALLUCINATION_GUARD_ACTION     -- block/flag/strip/warn
            HALLUCINATION_GUARD_DUAL_PATH  -- 1/0
            HALLUCINATION_GUARD_OFFLINE    -- 1/0 (KILL SWITCH for downloads)
            HALLUCINATION_GUARD_MODEL      -- NLI model name override
            HALLUCINATION_GUARD_LOG_DIR    -- Log directory path
        """
        gc = cls()
        t = os.environ.get("HALLUCINATION_GUARD_THRESHOLD")
        if t:
            gc.faithfulness_threshold = float(t)
        a = os.environ.get("HALLUCINATION_GUARD_ACTION")
        if a and a in ("block", "flag", "strip", "warn"):
            gc.failure_action = a
        d = os.environ.get("HALLUCINATION_GUARD_DUAL_PATH")
        if d:
            gc.enable_dual_path = d.lower() in ("1", "true", "yes")
        o = os.environ.get("HALLUCINATION_GUARD_OFFLINE")
        if o:
            gc.offline_mode = o.lower() in ("1", "true", "yes")
        m = os.environ.get("HALLUCINATION_GUARD_MODEL")
        if m:
            gc.nli_model_name = m
        ld = os.environ.get("HALLUCINATION_GUARD_LOG_DIR")
        if ld:
            gc.log_dir = ld
        return gc
