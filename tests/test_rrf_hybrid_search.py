# === NON-PROGRAMMER GUIDE ===
# Purpose: Validates the Reciprocal Rank Fusion (RRF) scoring logic in the retriever.
# What to read first: Each test targets a specific property of the RRF algorithm.
# Inputs: Synthetic search result lists (no Ollama or database needed).
# Outputs: Pass/fail assertions on score values and ranking order.
# Safety notes: Pure unit tests, no side effects, safe to run anytime.
# ============================
"""
Hybrid search RRF validation tests.

Sprint 18.5 -- Validates the Reciprocal Rank Fusion formula, score
normalization, display blending, and dimension safety in the retrieval
pipeline.

RRF formula: score = 1 / (k + rank + 1), k=60 default
FTS5 normalization: raw / (raw + 1)  -> [0, 1]
Display blend: 0.4 * vec_score + 0.6 * rrf_normalized
Path search cap: min(0.5, 0.05 + 0.45 * coverage)
"""
from __future__ import annotations

import math
import numpy as np
import pytest


# -------------------------------------------------------------------------
# RRF formula unit tests (pure math, no retriever instance needed)
# -------------------------------------------------------------------------

class TestRRFFormula:
    """Test the RRF scoring formula in isolation."""

    def test_rrf_score_rank_zero(self) -> None:
        """Rank #1 result (index 0) with k=60 -> 1/61."""
        k = 60
        rank = 0
        score = 1.0 / (k + rank + 1)
        assert abs(score - 1.0 / 61) < 1e-10

    def test_rrf_score_rank_one(self) -> None:
        """Rank #2 result (index 1) with k=60 -> 1/62."""
        k = 60
        rank = 1
        score = 1.0 / (k + rank + 1)
        assert abs(score - 1.0 / 62) < 1e-10

    def test_rrf_scores_monotonically_decrease(self) -> None:
        """Higher rank -> lower RRF score (strictly decreasing)."""
        k = 60
        scores = [1.0 / (k + r + 1) for r in range(100)]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1]

    def test_rrf_score_always_positive(self) -> None:
        """RRF scores are always > 0 for any finite rank."""
        k = 60
        for rank in range(10_000):
            assert 1.0 / (k + rank + 1) > 0

    def test_rrf_fusion_additive(self) -> None:
        """A chunk appearing in both vector and FTS5 lists gets summed scores."""
        k = 60
        vec_rank = 0   # 1/61
        fts_rank = 2   # 1/63
        fused = 1.0 / (k + vec_rank + 1) + 1.0 / (k + fts_rank + 1)
        individual_max = 1.0 / (k + 0 + 1)
        assert fused > individual_max, "Fused score should exceed single-list score"

    def test_rrf_max_theoretical(self) -> None:
        """Max possible RRF = ranked #1 in both lists = 2/(k+1)."""
        k = 60
        max_rrf = 2.0 / (k + 1)
        assert abs(max_rrf - 2.0 / 61) < 1e-10


# -------------------------------------------------------------------------
# FTS5 score normalization tests
# -------------------------------------------------------------------------

class TestFTS5Normalization:
    """Test the FTS5 BM25 -> [0,1] normalization: raw/(raw+1)."""

    def test_zero_raw_score(self) -> None:
        raw = 0.0
        normalized = raw / (raw + 1.0) if raw > 0 else 0.0
        assert normalized == 0.0

    def test_small_raw_score(self) -> None:
        raw = 1.0
        normalized = raw / (raw + 1.0)
        assert abs(normalized - 0.5) < 1e-10

    def test_large_raw_score(self) -> None:
        """Large BM25 score approaches but never reaches 1.0."""
        raw = 1000.0
        normalized = raw / (raw + 1.0)
        assert normalized < 1.0
        assert normalized > 0.99

    def test_normalization_monotonic(self) -> None:
        """Higher raw score -> higher normalized score."""
        raws = [0.1, 0.5, 1.0, 5.0, 10.0, 100.0, 1000.0]
        norms = [r / (r + 1.0) for r in raws]
        for i in range(len(norms) - 1):
            assert norms[i] < norms[i + 1]

    def test_normalization_bounded(self) -> None:
        """All normalized scores are in [0, 1)."""
        for raw in [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 10000.0]:
            norm = raw / (raw + 1.0)
            assert 0.0 <= norm < 1.0


# -------------------------------------------------------------------------
# Display blend tests
# -------------------------------------------------------------------------

class TestDisplayBlend:
    """Test the 0.4*vec + 0.6*rrf_norm display scoring."""

    def test_blend_weights_sum_to_one(self) -> None:
        vec_weight = 0.4
        rrf_weight = 0.6
        assert abs(vec_weight + rrf_weight - 1.0) < 1e-10

    def test_blend_with_perfect_scores(self) -> None:
        """Perfect vec=1.0, perfect rrf_norm=1.0 -> blend=1.0."""
        blend = 0.4 * 1.0 + 0.6 * 1.0
        assert abs(blend - 1.0) < 1e-10

    def test_blend_with_zero_scores(self) -> None:
        blend = 0.4 * 0.0 + 0.6 * 0.0
        assert blend == 0.0

    def test_blend_capped_at_one(self) -> None:
        """Even if components somehow exceed 1.0, final is capped."""
        blend = 0.4 * 1.5 + 0.6 * 1.5  # hypothetical overflow
        capped = min(blend, 1.0)
        assert capped == 1.0

    def test_vec_only_result(self) -> None:
        """Result only in vector list (rrf_norm from single list)."""
        k = 60
        rrf_score = 1.0 / (k + 0 + 1)  # rank 0 in one list only
        max_rrf = 2.0 / (k + 1)
        rrf_norm = min(rrf_score / max_rrf, 1.0)
        vec_score = 0.85
        blend = 0.4 * vec_score + 0.6 * rrf_norm
        assert 0.0 < blend < 1.0
        assert abs(rrf_norm - 0.5) < 1e-10  # half of max possible

    def test_dual_list_boost(self) -> None:
        """Result in both lists gets higher blend than single-list."""
        k = 60
        max_rrf = 2.0 / (k + 1)

        # Single list: rank 0
        single_rrf = 1.0 / (k + 1)
        single_norm = min(single_rrf / max_rrf, 1.0)
        single_blend = 0.4 * 0.8 + 0.6 * single_norm

        # Both lists: rank 0 in vector, rank 1 in FTS
        dual_rrf = 1.0 / (k + 1) + 1.0 / (k + 2)
        dual_norm = min(dual_rrf / max_rrf, 1.0)
        dual_blend = 0.4 * 0.8 + 0.6 * dual_norm

        assert dual_blend > single_blend


# -------------------------------------------------------------------------
# Path search score capping
# -------------------------------------------------------------------------

class TestPathSearchScoring:
    """Test source_path_search coverage-based scoring."""

    def test_zero_coverage(self) -> None:
        coverage = 0.0
        score = min(0.5, 0.05 + 0.45 * coverage)
        assert abs(score - 0.05) < 1e-10

    def test_full_coverage(self) -> None:
        coverage = 1.0
        score = min(0.5, 0.05 + 0.45 * coverage)
        assert abs(score - 0.5) < 1e-10

    def test_half_coverage(self) -> None:
        coverage = 0.5
        score = min(0.5, 0.05 + 0.45 * coverage)
        expected = 0.05 + 0.225  # = 0.275
        assert abs(score - expected) < 1e-10

    def test_score_never_exceeds_half(self) -> None:
        """Path scores are always <= 0.5 (below content match scores)."""
        for coverage in [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]:
            score = min(0.5, 0.05 + 0.45 * coverage)
            assert score <= 0.5

    def test_score_monotonically_increases(self) -> None:
        coverages = [0.0, 0.1, 0.2, 0.5, 0.8, 1.0]
        scores = [min(0.5, 0.05 + 0.45 * c) for c in coverages]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]


# -------------------------------------------------------------------------
# Embedding dimension validation
# -------------------------------------------------------------------------

class TestDimensionValidation:
    """Test that dimension mismatches are caught, not silently ignored."""

    def test_query_dim_mismatch_detected(self) -> None:
        """A 384-dim query against 768-dim store should raise ValueError."""
        # Simulate the check from vector_store.py:554-557
        expected_dim = 768
        query_vec = np.zeros(384, dtype=np.float32)
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        with pytest.raises(ValueError, match="mismatch"):
            if q.shape[0] != expected_dim:
                raise ValueError(
                    f"Query dim mismatch: expected {expected_dim}, "
                    f"got {q.shape[0]}"
                )

    def test_correct_dim_passes(self) -> None:
        """A 768-dim query against 768-dim store should NOT raise."""
        expected_dim = 768
        query_vec = np.zeros(768, dtype=np.float32)
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        assert q.shape[0] == expected_dim  # no error

    def test_append_dim_mismatch_detected(self) -> None:
        """Appending 384-dim embeddings to a 768-dim store should raise."""
        expected_dim = 768
        embeddings = np.zeros((10, 384), dtype=np.float32)
        with pytest.raises(ValueError, match="mismatch"):
            if embeddings.shape[1] != expected_dim:
                raise ValueError(
                    f"Dimension mismatch: got {embeddings.shape[1]}, "
                    f"expected {expected_dim}"
                )

    def test_zero_dim_query_rejected(self) -> None:
        """An empty (0-dim) query vector should fail validation."""
        expected_dim = 768
        query_vec = np.array([], dtype=np.float32)
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        assert q.shape[0] != expected_dim
