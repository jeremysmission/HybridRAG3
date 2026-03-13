# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the retriever structured queries area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from types import SimpleNamespace

import pytest

from src.core.retriever import Retriever, SearchHit


class _DummyEmbedder:
    def embed_query(self, _q):
        return [0.0]


class _DummyStore:
    def search(self, *_args, **_kwargs):
        return []

    def fts_search(self, *_args, **_kwargs):
        return []


def _make_config(top_k=8, min_score=0.2):
    retrieval = SimpleNamespace(
        top_k=top_k,
        block_rows=25000,
        min_score=min_score,
        lex_boost=0.06,
        hybrid_search=True,
        rrf_k=60,
        reranker_enabled=False,
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        reranker_top_n=20,
    )
    return SimpleNamespace(retrieval=retrieval)


def test_structured_query_relaxes_min_score_and_expands_fts_terms(monkeypatch):
    retriever = Retriever(_DummyStore(), _DummyEmbedder(), _make_config(top_k=4, min_score=0.2))

    calls = {}

    def fake_hybrid_search(query, candidate_k, fts_query=None):
        calls["query"] = query
        calls["candidate_k"] = candidate_k
        calls["fts_query"] = fts_query
        return [
            SearchHit(0.12, "manual.pdf", 10, "part number A-100"),
            SearchHit(0.04, "manual.pdf", 11, "noise"),
        ]

    monkeypatch.setattr(retriever, "_hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(retriever, "_augment_with_adjacent_chunks", lambda hits: hits)

    out = retriever.search("List all parts and part #s for DPS4D")

    assert len(out) == 1
    assert out[0].chunk_index == 10
    assert calls["candidate_k"] >= 16
    assert "materials" in calls["fts_query"]


def test_non_structured_query_keeps_default_threshold(monkeypatch):
    retriever = Retriever(_DummyStore(), _DummyEmbedder(), _make_config(top_k=4, min_score=0.2))

    monkeypatch.setattr(
        retriever,
        "_hybrid_search",
        lambda _q, _k, fts_query=None: [
            SearchHit(0.12, "manual.pdf", 10, "weak hit"),
            SearchHit(0.25, "manual.pdf", 12, "strong hit"),
        ],
    )

    out = retriever.search("What is operating temperature?")

    assert len(out) == 1
    assert out[0].chunk_index == 12


def test_structured_lookup_detection_variants():
    from src.core.retriever import _is_structured_lookup_query

    assert _is_structured_lookup_query("list all parts for DPS4D")
    assert _is_structured_lookup_query("show serial number")
    assert _is_structured_lookup_query("give BOM breakdown")
    assert not _is_structured_lookup_query("what is boot time")


def test_get_sources_includes_access_tags_per_source():
    retriever = Retriever(_DummyStore(), _DummyEmbedder(), _make_config(top_k=4, min_score=0.2))

    sources = retriever.get_sources(
        [
            SearchHit(
                0.93,
                "/docs/spec.md",
                0,
                "spec text",
                access_tags=("shared", "review"),
                access_tag_source="document_tag_rules:spec.md",
            ),
            SearchHit(
                0.81,
                "/docs/spec.md",
                1,
                "more spec text",
                access_tags=("review", "shared"),
                access_tag_source="document_tag_rules:spec.md",
            ),
            SearchHit(
                0.77,
                "/docs/public.md",
                0,
                "public text",
                access_tags=(),
                access_tag_source="",
            ),
        ]
    )

    assert sources[0]["path"] == "/docs/spec.md"
    assert sources[0]["chunks"] == 2
    assert sources[0]["avg_relevance"] == pytest.approx(0.87)
    assert sources[0]["access_tags"] == ["shared", "review"]
    assert sources[0]["access_tag_source"] == "document_tag_rules:spec.md"

    assert sources[1]["path"] == "/docs/public.md"
    assert sources[1]["chunks"] == 1
    assert sources[1]["avg_relevance"] == pytest.approx(0.77)
    assert sources[1]["access_tags"] == ["shared"]
    assert sources[1]["access_tag_source"] == "default_document_tags"
