# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies document access-tag classification rules and protects against regressions.
# What to read first: Start at the top-level tests; they exercise the public helpers only.
# Inputs: Environment policy variables plus source file paths.
# Outputs: Assertions that default tags, rule matching, and normalization stay deterministic.
# Safety notes: No filesystem writes, network calls, or model dependencies.
# ============================

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.access_tags import (
    default_document_tags,
    normalize_access_tags,
    resolve_document_access_tags,
)
from tests.conftest import FakeConfig


np = pytest.importorskip("numpy")


def test_default_document_tags_fall_back_to_shared(monkeypatch):
    monkeypatch.delenv("HYBRIDRAG_DEFAULT_DOCUMENT_TAGS", raising=False)

    assert default_document_tags() == ("shared",)


def test_resolve_document_access_tags_merges_defaults_and_matching_rules(monkeypatch):
    monkeypatch.setenv("HYBRIDRAG_DEFAULT_DOCUMENT_TAGS", "shared")
    monkeypatch.setenv(
        "HYBRIDRAG_DOCUMENT_TAG_RULES",
        "*.md=review; *spec*.pdf = engineering, shared",
    )

    resolved = resolve_document_access_tags(r"D:\Docs\Spec Review\system_spec_v2.pdf")

    assert resolved.access_tags == ("shared", "engineering")
    assert resolved.access_tag_source == "document_tag_rules:*spec*.pdf"
    assert resolved.matched_rules == ("*spec*.pdf",)


def test_resolve_document_access_tags_matches_basename_rules(monkeypatch):
    monkeypatch.delenv("HYBRIDRAG_DEFAULT_DOCUMENT_TAGS", raising=False)
    monkeypatch.setenv(
        "HYBRIDRAG_DOCUMENT_TAG_RULES",
        "notes.md=review,shared",
    )

    resolved = resolve_document_access_tags(r"D:\Shared\Project\notes.md")

    assert resolved.access_tags == ("shared", "review")
    assert resolved.access_tag_source == "document_tag_rules:notes.md"


def test_normalize_access_tags_dedupes_and_honors_wildcard():
    assert normalize_access_tags([" Shared ", "shared", "Review"]) == (
        "shared",
        "review",
    )
    assert normalize_access_tags("engineering, *, review") == ("*",)


def test_vector_store_and_indexer_preserve_document_access_tags(tmp_path, monkeypatch):
    from src.core.indexer import Indexer
    from src.core.vector_store import ChunkMetadata, VectorStore

    monkeypatch.setenv("HYBRIDRAG_DOCUMENT_TAG_RULES", "*/restricted/*=restricted")

    source_root = tmp_path / "source"
    restricted_dir = source_root / "restricted"
    restricted_dir.mkdir(parents=True)
    source_file = restricted_dir / "spec.txt"
    source_file.write_text(
        "Restricted antenna specification with enough text for indexing.",
        encoding="utf-8",
    )

    mock_vector_store = MagicMock()
    mock_vector_store.get_file_hash.return_value = None
    mock_vector_store.delete_chunks_by_source.return_value = 0
    mock_vector_store.conn = None

    mock_embedder = MagicMock()
    mock_embedder.embed_batch.side_effect = lambda texts: [[0.0] * 384 for _ in texts]

    mock_chunker = MagicMock()
    mock_chunker.chunk_text.side_effect = lambda text: [text]

    with patch("src.core.indexer.make_chunk_id", return_value="chunk_000001"):
        indexer = Indexer(FakeConfig(), mock_vector_store, mock_embedder, mock_chunker)

    result = indexer.index_folder(str(source_root))
    assert result["total_files_indexed"] == 1

    stored_metadata = mock_vector_store.add_embeddings.call_args.args[1]
    assert stored_metadata[0].source_path == str(source_file)
    assert stored_metadata[0].access_tags == ("shared", "restricted")
    assert stored_metadata[0].access_tag_source == "document_tag_rules:*/restricted/*"

    db_path = tmp_path / "access_tags.sqlite3"
    store = VectorStore(db_path=str(db_path), embedding_dim=4)
    store.connect()
    try:
        embeddings = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
        metadata = [
            ChunkMetadata(
                source_path=str(source_file),
                chunk_index=0,
                text_length=42,
                created_at="2026-03-12T23:30:00",
                access_tags=("shared", "restricted"),
                access_tag_source="document_tag_rules:*/restricted/*",
            )
        ]
        store.add_embeddings(
            embeddings,
            metadata,
            texts=["restricted antenna specification"],
            file_hash="hash123",
        )

        search_hits = store.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), top_k=1)
        assert search_hits[0]["access_tags"] == ["shared", "restricted"]
        assert search_hits[0]["access_tag_source"] == "document_tag_rules:*/restricted/*"

        fts_hits = store.fts_search("antenna", top_k=1)
        assert fts_hits[0]["access_tags"] == ["shared", "restricted"]
        assert fts_hits[0]["access_tag_source"] == "document_tag_rules:*/restricted/*"
    finally:
        store.close()


def test_retriever_filters_hits_by_request_access_context():
    from src.core.request_access import reset_request_access_context, set_request_access_context
    from src.core.retriever import Retriever

    cfg = FakeConfig()
    cfg.retrieval.hybrid_search = False

    class DummyStore:
        conn = None

        @staticmethod
        def search(_query_vec, top_k=8, block_rows=None):
            _ = top_k, block_rows
            return [
                {
                    "score": 0.95,
                    "source_path": "/docs/shared.txt",
                    "chunk_index": 0,
                    "text": "shared content",
                    "access_tags": ["shared"],
                    "access_tag_source": "default_document_tags",
                },
                {
                    "score": 0.93,
                    "source_path": "/docs/restricted.txt",
                    "chunk_index": 0,
                    "text": "restricted content",
                    "access_tags": ["shared", "restricted"],
                    "access_tag_source": "document_tag_rules:*/restricted/*",
                },
            ]

    class DummyEmbedder:
        @staticmethod
        def embed_query(_query):
            return np.array([1.0, 0.0], dtype=np.float32)

    retriever = Retriever(DummyStore(), DummyEmbedder(), cfg)
    token = set_request_access_context(
        {
            "actor": "alice",
            "actor_source": "api_token",
            "actor_role": "viewer",
            "allowed_doc_tags": ("shared",),
        }
    )
    try:
        hits = retriever.search("show docs")
    finally:
        reset_request_access_context(token)

    assert [hit.source_path for hit in hits] == ["/docs/shared.txt"]
    assert retriever.last_search_trace["access_control"]["enabled"] is True
    assert retriever.last_search_trace["access_control"]["denied_hits"] == 1
    assert retriever.last_search_trace["hits"]["denied"][0]["source_path"] == "/docs/restricted.txt"
    assert "restricted" in retriever.last_search_trace["hits"]["denied"][0]["reason"]


def test_query_engine_blocks_open_knowledge_fallback_when_all_hits_are_denied():
    from src.core.query_engine import QueryEngine

    cfg = FakeConfig(mode="online")
    cfg.query.allow_open_knowledge = True
    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()

    denied_trace = {
        "counts": {
            "raw_hits": 1,
            "post_rerank_hits": 1,
            "post_filter_hits": 1,
            "post_augment_hits": 0,
            "final_hits": 0,
            "dropped_hits": 0,
            "denied_hits": 1,
        },
        "hits": {
            "raw": [],
            "post_rerank": [],
            "post_filter": [],
            "post_augment": [],
            "final": [],
            "dropped": [],
            "denied": [],
        },
        "source_path_flags": {
            "expected_source_root": "",
            "suspicious_count": 0,
            "suspicious_sources": [],
        },
        "access_control": {
            "enabled": True,
            "actor": "alice",
            "actor_source": "api_token",
            "actor_role": "viewer",
            "allowed_doc_tags": ["shared"],
            "authorized_hits": 0,
            "denied_hits": 1,
        },
    }

    with patch("src.core.query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as retriever_cls:
            retriever = MagicMock()
            retriever.search.return_value = []
            retriever.last_search_trace = denied_trace
            retriever_cls.return_value = retriever
            engine = QueryEngine(cfg, mock_vector_store, mock_embedder, mock_router)

    result = engine.query("show the restricted spec")

    assert result.error == "access_denied"
    assert result.answer == "No authorized information found in knowledge base."
    assert result.debug_trace["decision"]["path"] == "access_denied_no_results"
    assert result.debug_trace["retrieval"]["access_control"]["denied_hits"] == 1
    assert mock_router.query.call_count == 0


def test_query_engine_stream_blocks_open_knowledge_fallback_when_all_hits_are_denied():
    from src.core.query_engine import QueryEngine

    cfg = FakeConfig(mode="online")
    cfg.query.allow_open_knowledge = True
    mock_vector_store = MagicMock()
    mock_embedder = MagicMock()
    mock_router = MagicMock()

    denied_trace = {
        "counts": {
            "raw_hits": 1,
            "post_rerank_hits": 1,
            "post_filter_hits": 1,
            "post_augment_hits": 0,
            "final_hits": 0,
            "dropped_hits": 0,
            "denied_hits": 1,
        },
        "hits": {
            "raw": [],
            "post_rerank": [],
            "post_filter": [],
            "post_augment": [],
            "final": [],
            "dropped": [],
            "denied": [],
        },
        "source_path_flags": {
            "expected_source_root": "",
            "suspicious_count": 0,
            "suspicious_sources": [],
        },
        "access_control": {
            "enabled": True,
            "actor": "alice",
            "actor_source": "api_token",
            "actor_role": "viewer",
            "allowed_doc_tags": ["shared"],
            "authorized_hits": 0,
            "denied_hits": 1,
        },
    }

    with patch("src.core.query_engine.get_app_logger") as mock_logger:
        mock_logger.return_value = MagicMock()
        with patch("src.core.query_engine.Retriever") as retriever_cls:
            retriever = MagicMock()
            retriever.search.return_value = []
            retriever.last_search_trace = denied_trace
            retriever_cls.return_value = retriever
            engine = QueryEngine(cfg, mock_vector_store, mock_embedder, mock_router)

    events = list(engine.query_stream("show the restricted spec"))
    result = [event["result"] for event in events if event.get("done")][0]

    assert result.error == "access_denied"
    assert result.answer == "No authorized information found in knowledge base."
    assert result.debug_trace["decision"]["path"] == "access_denied_no_results"
    assert result.debug_trace["retrieval"]["access_control"]["denied_hits"] == 1
    assert mock_router.query.call_count == 0
