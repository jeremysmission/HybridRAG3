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
