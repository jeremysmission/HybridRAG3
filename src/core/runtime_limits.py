# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the runtime limits part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Runtime Limits (src/core/runtime_limits.py)
# ============================================================================
# PURPOSE:
#   Centralized concurrency choke-point for all expensive operations:
#     - Query generation (LLM + retrieval orchestration)
#     - Embedding calls (indexing)
#
# WHY:
#   QA finding: concurrency guard existed but could be bypassed.
#   This module provides a single, explicit guard that facades must use.
#
# NOTES:
#   - Portable (stdlib only).
#   - Designed to be used by GUI + API entrypoints.
#   - Keeps the policy in one file for review.
# ============================================================================

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimePolicy:
    """Plain-English: This class groups logic for runtimepolicy."""
    max_concurrent_queries: int = 2
    max_concurrent_embeddings: int = 2

    @staticmethod
    def from_config(config: Any) -> "RuntimePolicy":
        # Allow config overrides but remain safe if fields do not exist.
        """Plain-English: This function handles from config."""
        mq = getattr(getattr(config, "runtime", None), "max_concurrent_queries", None)
        me = getattr(getattr(config, "runtime", None), "max_concurrent_embeddings", None)

        env_mq = os.getenv("HYBRIDRAG_MAX_CONCURRENT_QUERIES")
        env_me = os.getenv("HYBRIDRAG_MAX_CONCURRENT_EMBEDDINGS")

        def _to_int(v, default):
            """Plain-English: This function handles to int."""
            try:
                return int(v)
            except Exception:
                return default

        max_q = _to_int(env_mq, mq if mq is not None else 2)
        max_e = _to_int(env_me, me if me is not None else 2)

        # Clamp to sane bounds to prevent foot-guns.
        max_q = max(1, min(max_q, 32))
        max_e = max(1, min(max_e, 64))

        return RuntimePolicy(max_concurrent_queries=max_q, max_concurrent_embeddings=max_e)


class RuntimeLimiter:
    """Owns semaphores that enforce the runtime policy."""

    def __init__(self, policy: RuntimePolicy):
        """Plain-English: This function handles init."""
        self.policy = policy
        self._query_sem = threading.BoundedSemaphore(policy.max_concurrent_queries)
        self._embed_sem = threading.BoundedSemaphore(policy.max_concurrent_embeddings)

    @staticmethod
    def from_config(config: Any) -> "RuntimeLimiter":
        """Plain-English: This function handles from config."""
        return RuntimeLimiter(RuntimePolicy.from_config(config))

    @contextmanager
    def query_slot(self):
        """Plain-English: This function handles query slot."""
        self._query_sem.acquire()
        try:
            yield
        finally:
            self._query_sem.release()

    @contextmanager
    def embedding_slot(self):
        """Plain-English: This function handles embedding slot."""
        self._embed_sem.acquire()
        try:
            yield
        finally:
            self._embed_sem.release()
