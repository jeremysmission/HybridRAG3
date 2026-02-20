#!/usr/bin/env python3
"""
hallucination_guard -- Multi-Layer Hallucination Prevention for HybridRAG3
==========================================================================

This package prevents online API mode (online LLM, GPT, etc.) from
feeding hallucinated information to defense customers where inaccuracy
can cost lives.

ARCHITECTURE (6 files, each < 500 lines, AI-reviewable):
    guard_types.py        -- Constants, enums, data classes
    prompt_hardener.py    -- Layer 1: Force LLM to stay grounded
    claim_extractor.py    -- Layer 2a: Split response into claims
    nli_verifier.py       -- Layer 2b: NLI model checks each claim
    response_scoring.py   -- Layers 3-4: Scoring + safe response
    hallucination_guard.py -- Main orchestrator + Layer 5 + convenience

QUICK START:
    from hallucination_guard import guard_response, harden_prompt

    # Before LLM call: harden the prompt
    pkg = harden_prompt(system_prompt, query, chunks, source_files)
    response = api_call(system=pkg["system"], user=pkg["user"])

    # After LLM call: verify the response
    result = guard_response(response, chunks, query)
    if result.is_safe:
        show(result.original_response)
    else:
        show(result.safe_response)

FULL CONTROL:
    from hallucination_guard import HallucinationGuard, GuardConfig

    config = GuardConfig(faithfulness_threshold=0.90, failure_action="block")
    guard = HallucinationGuard(config)
    result = guard.verify(llm_response, chunks, query)

SELF-TEST:
    python -m hallucination_guard

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

# -- Data classes and types (used everywhere) --
from .guard_types import (
    ClaimVerdict,
    ClaimResult,
    GuardResult,
    GuardConfig,
    # Constants (rarely imported directly, but available)
    NLI_MODEL_NAME,
    HEDGE_WORDS,
    OVERCONFIDENCE_MARKERS,
)

# -- Individual layer classes (for advanced/custom usage) --
from .prompt_hardener import PromptHardener
from .claim_extractor import ClaimExtractor
from .nli_verifier import NLIVerifier
from .response_scoring import ConfidenceCalibrator, ResponseConstructor

# -- Main orchestrator and convenience functions --
from .hallucination_guard import (
    HallucinationGuard,
    get_guard,
    guard_response,
    harden_prompt,
    init_hallucination_guard,
)

# -- Layer 5: Dual-path consensus (optional, for critical queries) --
from .dual_path import DualPathConsensus

# -- Self-test --
from .self_test import run_self_test

# -- BIT (Built-In Test) -- runs automatically on import --
from .startup_bit import run_bit

# Package metadata
__version__ = "1.1.0"
__author__ = "Jeremy"

# Run BIT on first import (< 50ms, no model loading, no network)
# Logs warnings if any test fails, but does NOT crash.
import logging as _logging
_bit_logger = _logging.getLogger("hallucination_guard.bit")
try:
    _bit_passed, _bit_total, _ = run_bit(verbose=False)
    if _bit_passed == _bit_total:
        _bit_logger.debug("BIT: %d/%d passed on import", _bit_passed, _bit_total)
    else:
        _bit_logger.warning(
            "BIT: %d/%d passed on import -- check hallucination_guard",
            _bit_passed, _bit_total)
except Exception as _bit_err:
    _bit_logger.error("BIT failed to run: %s", _bit_err)

# What gets exported with "from hallucination_guard import *"
__all__ = [
    # Data types
    "ClaimVerdict", "ClaimResult", "GuardResult", "GuardConfig",
    # Layer classes
    "PromptHardener", "ClaimExtractor", "NLIVerifier",
    "ConfidenceCalibrator", "ResponseConstructor",
    # Main classes
    "HallucinationGuard", "DualPathConsensus",
    # Convenience functions
    "get_guard", "guard_response", "harden_prompt",
    "init_hallucination_guard", "run_self_test", "run_bit",
]

GUARD_VERSION = "1.1.0"
