import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from src.core.retriever import Retriever, SearchHit
from src.core.source_quality import ensure_source_quality_schema

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig


class _DummyVectorStore:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_source_quality_schema(self.conn)


def test_retriever_search_downranks_suspect_saved_resource_hits():
    vector_store = _DummyVectorStore()
    config = FakeConfig(mode="offline")
    config.retrieval.min_score = -0.1
    retriever = Retriever(vector_store, SimpleNamespace(), config)

    suspect_path = r"D:\capture\_files\saved_resource.html"
    clean_path = r"D:\docs\manual.docx"
    raw_hits = [
        SearchHit(
            score=0.88,
            source_path=suspect_path,
            chunk_index=0,
            text="theme auto light dark previous topic next topic report a bug",
        ),
        SearchHit(
            score=0.82,
            source_path=clean_path,
            chunk_index=0,
            text="Recommended citation format uses author, year, and direct evidence from the source.",
        ),
    ]

    retriever._hybrid_search = lambda query, candidate_k, fts_query=None: list(raw_hits)

    with patch("src.core.retriever.build_retrieval_trace", return_value={}):
        results = retriever.search("What citation style is recommended?")

    assert [hit.source_path for hit in results[:2]] == [clean_path, suspect_path]

    quality_row = vector_store.conn.execute(
        "SELECT retrieval_tier, is_saved_resource FROM source_quality WHERE source_path = ?",
        (suspect_path,),
    ).fetchone()
    assert quality_row == ("suspect", 1)


def test_retriever_refreshes_stale_quality_rows_for_known_junk_sources():
    vector_store = _DummyVectorStore()
    config = FakeConfig(mode="offline")
    config.retrieval.min_score = -0.1
    retriever = Retriever(vector_store, SimpleNamespace(), config)

    junk_path = r"D:\RAG Source Data\golden_seeds_engineer.json"
    clean_path = r"D:\RAG Source Data\Docs\real_manual.pdf"
    vector_store.conn.execute(
        """
        INSERT INTO source_quality (
            source_path, source_type, retrieval_tier, quality_score,
            is_html_capture, is_saved_resource, is_boilerplate,
            has_missing_path, has_encoded_blob, flags_json, updated_at
        ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?)
        """,
        (junk_path, "json", "serve", 0.92, "[]", "2026-03-01T00:00:00+00:00"),
    )
    vector_store.conn.commit()

    raw_hits = [
        SearchHit(
            score=0.88,
            source_path=junk_path,
            chunk_index=0,
            text="Synthetic eval artifact content that should not be served.",
        ),
        SearchHit(
            score=0.82,
            source_path=clean_path,
            chunk_index=0,
            text="Recommended citation format uses author, year, and direct evidence from the source.",
        ),
    ]

    retriever._hybrid_search = lambda query, candidate_k, fts_query=None: list(raw_hits)

    with patch("src.core.retriever.build_retrieval_trace", return_value={}):
        results = retriever.search("What citation style is recommended?")

    assert [hit.source_path for hit in results[:2]] == [clean_path, junk_path]

    quality_row = vector_store.conn.execute(
        "SELECT retrieval_tier, flags_json FROM source_quality WHERE source_path = ?",
        (junk_path,),
    ).fetchone()
    assert quality_row[0] == "suspect"
    assert "golden_seed_file" in quality_row[1]
