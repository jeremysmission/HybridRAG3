# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the query engine area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Tests for the QueryEngine -- the central pipeline that turns
#       a user question into a grounded, cited answer
# WHY:  The query pipeline has multiple stages (retrieve chunks, build
#       context, call LLM, format result). Each stage can fail
#       independently. These tests verify the full pipeline end-to-end
#       using mocked LLM and retriever backends.
# HOW:  Mocks all external dependencies (LLM router, vector store,
#       embedder) so tests run instantly with no network or GPU needed
# USAGE: python -m pytest tests/test_query_engine.py -v
# ===================================================================

import time
from unittest.mock import MagicMock, Mock, patch, PropertyMock
import pytest
# Import shared fixtures from conftest.py in the same directory.
# WHY this style: avoids requiring tests/__init__.py to exist.
# Works on both home PC and work laptop regardless of package structure.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeLLMResponse

class TestQueryEngine:
    """
    Tests for the QueryEngine orchestration pipeline.
    """

    def _make_engine(self, config=None, search_results=None,
                     llm_text="Test answer"):
        """
        Helper: create a QueryEngine with all dependencies mocked.

        Args:
            config:         Optional FakeConfig
            search_results: What the retriever should return (list of dicts)
            llm_text:       What the LLM should return as answer text

        Returns:
            (engine, mocks) -- the engine and a dict of all mock objects
        """
        if config is None:
            config = FakeConfig(mode="offline")

        # Mock all the dependencies that QueryEngine needs
        mock_vector_store = MagicMock()
        mock_embedder = MagicMock()
        mock_llm_router = MagicMock()

        # Set up the LLM router to return a fake response
        mock_llm_router.query.return_value = FakeLLMResponse(
            text=llm_text,
            tokens_in=150,
            tokens_out=25,
            model="phi4-mini",
            latency_ms=3000.0,
        )

        with patch("src.core.query_engine.get_app_logger") as mock_logger:
            mock_logger.return_value = MagicMock()

            with patch("src.core.query_engine.Retriever") as MockRetriever:
                mock_retriever_instance = MagicMock()

                # Default: return some search results
                if search_results is None:
                    search_results = [
                        {
                            "chunk_id": "abc123",
                            "text": "The system operates at 5.2 GHz.",
                            "score": 0.85,
                            "source_path": "/docs/spec.pdf",
                        },
                        {
                            "chunk_id": "def456",
                            "text": "Power output is 100 watts.",
                            "score": 0.72,
                            "source_path": "/docs/spec.pdf",
                        },
                    ]

                mock_retriever_instance.search.return_value = search_results

                # build_context joins the chunk texts into a single string
                mock_retriever_instance.build_context.return_value = (
                    "The system operates at 5.2 GHz.\n\n"
                    "Power output is 100 watts."
                )

                # get_sources returns source file summaries
                mock_retriever_instance.get_sources.return_value = [
                    {
                        "path": "/docs/spec.pdf",
                        "chunks": 2,
                        "avg_relevance": 0.785,
                    }
                ]

                MockRetriever.return_value = mock_retriever_instance

                from src.core.query_engine import QueryEngine
                engine = QueryEngine(
                    config, mock_vector_store, mock_embedder, mock_llm_router
                )

        mocks = {
            "vector_store": mock_vector_store,
            "embedder": mock_embedder,
            "llm_router": mock_llm_router,
            "retriever": mock_retriever_instance,
        }

        return engine, mocks

    # ------------------------------------------------------------------
    # Test 4.1: Successful end-to-end query
    # ------------------------------------------------------------------
    def test_successful_query(self):
        """
        WHAT: Run a full query and verify all fields in QueryResult.
        WHY:  This is the "happy path" -- everything works. If this test
              fails, the core functionality is broken.
        """
        engine, mocks = self._make_engine(
            llm_text="The system operates at 5.2 GHz with 100W output."
        )

        # WHY mock time.time here:
        #   The entire query pipeline (retriever + LLM) is mocked, so it
        #   completes in microseconds. time.time() delta rounds to 0.0 ms.
        #   We return t+0.1 on the second call to simulate 100ms latency.
        _time_calls = []
        def fake_time():
            _time_calls.append(1)
            return 1000.000 if len(_time_calls) == 1 else 1000.100

        with patch("src.core.query_engine.time.time", side_effect=fake_time):
            result = engine.query("What is the operating frequency?")

        assert result.answer == (
            "The system operates at 5.2 GHz with 100W output."
        )
        assert result.chunks_used == 2
        assert result.sources[0]["path"] == "/docs/spec.pdf"
        assert result.mode == "offline"
        assert result.error is None
        assert result.latency_ms > 0

    # ------------------------------------------------------------------
    # Test 4.2: No relevant documents found
    # ------------------------------------------------------------------
    def test_no_results_found(self):
        """
        WHAT: When the retriever finds nothing, return a clear message.
        WHY:  Empty results shouldn't crash or return "None." The user
              should see a friendly message explaining nothing was found.
        """
        engine, mocks = self._make_engine(search_results=[])
        engine.config.query.allow_open_knowledge = False

        result = engine.query("What is quantum entanglement?")

        assert "No relevant information" in result.answer
        assert result.chunks_used == 0
        assert result.sources == []
        assert result.error is None

    def test_access_filtered_no_results_skip_open_knowledge_fallback(self):
        config = FakeConfig(mode="online")
        engine, mocks = self._make_engine(config=config, search_results=[])
        engine.config.query.allow_open_knowledge = True
        mocks["retriever"].last_search_trace = {
            "counts": {
                "raw_hits": 2,
                "post_rerank_hits": 2,
                "post_filter_hits": 0,
                "post_augment_hits": 0,
                "final_hits": 0,
                "dropped_hits": 0,
                "denied_hits": 2,
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
                "document_policy_source": "role_tags:viewer",
                "authorized_hits": 0,
                "denied_hits": 2,
            },
        }

        result = engine.query("What is in the restricted plan?")

        assert result.answer == "No authorized information found in knowledge base."
        assert result.error == "access_denied"
        assert mocks["llm_router"].query.call_count == 0
        assert result.debug_trace["decision"]["path"] == "access_denied_no_results"

    # ------------------------------------------------------------------
    # Test 4.3: Empty context edge case
    # ------------------------------------------------------------------
    def test_empty_context_returns_error(self):
        """
        WHAT: If chunks exist but their text is empty (extremely rare),
              handle it gracefully.
        WHY:  A corrupted index could have entries with empty text fields.
              Rather than sending a blank prompt to the LLM, we catch this.
        """
        engine, mocks = self._make_engine()
        engine.config.query.allow_open_knowledge = False

        # Override build_context to return empty string
        mocks["retriever"].build_context.return_value = ""

        result = engine.query("Test query")

        assert "no usable context" in result.answer.lower()
        assert result.error == "empty_context"

    # ------------------------------------------------------------------
    # Test 4.4: LLM call failure
    # ------------------------------------------------------------------
    def test_llm_failure(self):
        """
        WHAT: If the LLM router returns None (call failed), show error.
        WHY:  Network glitches, Ollama crashes, API timeouts -- any of
              these would cause the LLM call to fail. User should see a
              clear error message, not a traceback.
        """
        engine, mocks = self._make_engine()

        # Override LLM router to return None (simulating failure)
        mocks["llm_router"].query.return_value = None

        result = engine.query("Test query")

        assert "Error calling LLM" in result.answer
        assert result.error == "LLM call failed"
        assert result.chunks_used == 2  # Chunks were found, LLM just failed

    # ------------------------------------------------------------------
    # Test 4.5: Cost calculation -- offline mode = $0
    # ------------------------------------------------------------------
    def test_cost_calculation_offline(self):
        """
        WHAT: In offline mode, cost should always be $0.
        WHY:  Ollama runs locally -- no API charges. If cost shows up
              in offline mode, something is wrong with the calculation.
        """
        config = FakeConfig(mode="offline")
        engine, mocks = self._make_engine(config=config)

        result = engine.query("Test query")

        assert result.cost_usd == 0.0, (
            "Offline mode should have zero cost"
        )

    # ------------------------------------------------------------------
    # Test 4.6: Cost calculation -- online mode
    # ------------------------------------------------------------------
    def test_cost_calculation_online(self):
        """
        WHAT: In online mode, verify cost is calculated from token counts.
        WHY:  Cost tracking lets you monitor API spend. Wrong formula
              = wrong budget tracking. The formula is:
              (tokens_in / 1000) * input_rate + (tokens_out / 1000) * output_rate
        """
        config = FakeConfig(mode="online")
        engine, mocks = self._make_engine(config=config)

        result = engine.query("Test query")

        # Expected: (150/1000)*0.0015 + (25/1000)*0.002 = 0.000225 + 0.00005 = 0.000275
        expected_cost = (150 / 1000) * 0.0015 + (25 / 1000) * 0.002
        assert abs(result.cost_usd - expected_cost) < 0.0001, (
            f"Expected cost ~{expected_cost}, got {result.cost_usd}"
        )

    # ------------------------------------------------------------------
    # Test 4.7: Prompt construction
    # ------------------------------------------------------------------
    def test_prompt_includes_context_and_question(self):
        """
        WHAT: Verify the prompt sent to the LLM contains both the
              retrieved context and the user's question.
        WHY:  If the context is missing, the LLM hallucinates.
              If the question is missing, the LLM writes a random summary.
              Both parts must be present.
        """
        engine, mocks = self._make_engine()

        engine.query("What is the frequency?")

        # Get the prompt that was actually sent to the LLM
        call_args = mocks["llm_router"].query.call_args
        prompt_sent = call_args[0][0]

        assert "5.2 GHz" in prompt_sent, "Prompt should contain the context"
        assert "What is the frequency?" in prompt_sent, (
            "Prompt should contain the user question"
        )

    # ------------------------------------------------------------------
    # Test 4.8: Exception handling -- unexpected errors
    # ------------------------------------------------------------------
    def test_exception_returns_error_result(self):
        """
        WHAT: If something unexpected crashes, return an error QueryResult
              instead of an unhandled exception.
        WHY:  The GUI should show "Error processing query: ..." not a
              Python traceback. Never crash the application.
        """
        engine, mocks = self._make_engine()

        # Force the retriever to raise an unexpected exception
        mocks["retriever"].search.side_effect = RuntimeError(
            "Corrupted index file"
        )

        result = engine.query("Test query")

        assert "RuntimeError" in result.error
        assert "Corrupted index" in result.answer
        assert result.chunks_used == 0


# ============================================================================
# SECTION 2B: CORRECTIVE RETRIEVAL (CRAG) TESTS
# ============================================================================
#
# Tests for the three corrective retrieval methods added in Sprint 15:
#   _attempt_corrective_retrieval, _reformulate_for_retry, _merge_search_results
# ============================================================================

from src.core.retriever import SearchHit


class TestCorrectiveRetrieval:

    def _make_engine_with_corrective(self, corrective=True, threshold=0.35,
                                      search_results=None, retry_results=None):
        """Helper: build engine with corrective retrieval enabled."""
        config = FakeConfig(mode="offline")
        config.retrieval.corrective_retrieval = corrective
        config.retrieval.corrective_threshold = threshold

        mock_vector_store = MagicMock()
        mock_embedder = MagicMock()
        mock_llm_router = MagicMock()
        mock_llm_router.query.return_value = FakeLLMResponse(
            text="Answer", tokens_in=100, tokens_out=20,
            model="phi4-mini", latency_ms=1000.0,
        )

        with patch("src.core.query_engine.get_app_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            with patch("src.core.query_engine.Retriever") as MockRetriever:
                mock_retriever = MagicMock()

                if search_results is None:
                    search_results = []
                if retry_results is None:
                    retry_results = []

                mock_retriever.search.side_effect = [search_results, retry_results]
                mock_retriever.build_context.return_value = "context"
                mock_retriever.get_sources.return_value = []
                MockRetriever.return_value = mock_retriever

                from src.core.query_engine import QueryEngine
                engine = QueryEngine(
                    config, mock_vector_store, mock_embedder, mock_llm_router
                )

        return engine, mock_retriever

    def _hit(self, score, path="doc.pdf", chunk=0, text="chunk text"):
        return SearchHit(score=score, source_path=path,
                         chunk_index=chunk, text=text)

    # ------------------------------------------------------------------
    # _attempt_corrective_retrieval
    # ------------------------------------------------------------------

    def test_disabled_returns_original(self):
        """When corrective_retrieval=False, results pass through unchanged."""
        engine, _ = self._make_engine_with_corrective(corrective=False)
        hits = [self._hit(0.9)]
        result = engine._attempt_corrective_retrieval("test query", hits)
        assert result is hits

    def test_high_confidence_skips_retry(self):
        """Above threshold, no retry happens."""
        engine, mock_ret = self._make_engine_with_corrective(threshold=0.35)
        hits = [self._hit(0.80), self._hit(0.50)]
        result = engine._attempt_corrective_retrieval("find the spec", hits)
        assert result is hits
        mock_ret.search.assert_not_called()

    def test_low_confidence_triggers_retry(self):
        """Below threshold, reformulate + retry is attempted."""
        engine, mock_ret = self._make_engine_with_corrective(threshold=0.50)
        initial = [self._hit(0.30, path="a.pdf", chunk=0)]
        retry = [self._hit(0.70, path="b.pdf", chunk=0)]
        mock_ret.search.side_effect = None
        mock_ret.search.return_value = retry

        result = engine._attempt_corrective_retrieval(
            "what is the operating frequency?", initial)

        mock_ret.search.assert_called_once()
        assert len(result) == 2
        assert result[0].score == 0.70

    def test_empty_initial_triggers_retry(self):
        """Empty initial results also trigger retry."""
        engine, mock_ret = self._make_engine_with_corrective()
        mock_ret.search.side_effect = None
        mock_ret.search.return_value = [self._hit(0.60)]

        result = engine._attempt_corrective_retrieval(
            "what is the power output?", [])

        mock_ret.search.assert_called_once()
        assert len(result) == 1

    def test_retry_returns_empty_keeps_initial(self):
        """If retry also returns nothing, keep initial results."""
        engine, mock_ret = self._make_engine_with_corrective(threshold=0.50)
        initial = [self._hit(0.20)]
        mock_ret.search.side_effect = None
        mock_ret.search.return_value = []

        result = engine._attempt_corrective_retrieval(
            "what is the spec?", initial)

        assert result is initial

    def test_unreformulable_query_skips_retry(self):
        """If reformulation produces same query, no retry."""
        engine, mock_ret = self._make_engine_with_corrective(threshold=0.50)
        initial = [self._hit(0.20)]
        result = engine._attempt_corrective_retrieval("xyz123", initial)
        assert result is initial
        mock_ret.search.assert_not_called()

    # ------------------------------------------------------------------
    # _reformulate_for_retry
    # ------------------------------------------------------------------

    def test_strips_question_prefix(self):
        """Question patterns are stripped to get keyword core."""
        engine, _ = self._make_engine_with_corrective()
        result = engine._reformulate_for_retry(
            "what is the operating frequency?")
        assert "what is" not in result.lower()
        assert "frequency" in result.lower()

    def test_strips_polite_prefix(self):
        engine, _ = self._make_engine_with_corrective()
        result = engine._reformulate_for_retry(
            "can you tell me about the calibration procedure?")
        assert "can you" not in result.lower()
        assert "calibration" in result.lower()

    def test_identity_query_unchanged(self):
        """Single keyword query can't be simplified further."""
        engine, _ = self._make_engine_with_corrective()
        result = engine._reformulate_for_retry("calibration")
        assert result == "calibration"

    def test_expander_integration(self):
        """If query expander is attached, acronyms are expanded."""
        engine, _ = self._make_engine_with_corrective()
        mock_expander = MagicMock()
        mock_expander.expand_keywords.return_value = "radio frequency expanded"
        engine._query_expander = mock_expander

        result = engine._reformulate_for_retry("what is the RF spec?")
        assert "expanded" in result

    # ------------------------------------------------------------------
    # _merge_search_results
    # ------------------------------------------------------------------

    def test_merge_deduplicates(self):
        """Same (path, chunk) keeps higher score."""
        from src.core.query_engine import QueryEngine
        a = [self._hit(0.60, "doc.pdf", 0)]
        b = [self._hit(0.80, "doc.pdf", 0)]
        merged = QueryEngine._merge_search_results(a, b)
        assert len(merged) == 1
        assert merged[0].score == 0.80

    def test_merge_combines_unique(self):
        """Different chunks from both sets appear in merged output."""
        from src.core.query_engine import QueryEngine
        a = [self._hit(0.90, "a.pdf", 0)]
        b = [self._hit(0.70, "b.pdf", 0)]
        merged = QueryEngine._merge_search_results(a, b)
        assert len(merged) == 2
        assert merged[0].score == 0.90

    def test_merge_sorted_descending(self):
        """Merged results are sorted by score descending."""
        from src.core.query_engine import QueryEngine
        a = [self._hit(0.30, "a.pdf", 0), self._hit(0.10, "a.pdf", 1)]
        b = [self._hit(0.50, "b.pdf", 0), self._hit(0.20, "b.pdf", 1)]
        merged = QueryEngine._merge_search_results(a, b)
        scores = [h.score for h in merged]
        assert scores == sorted(scores, reverse=True)

    def test_merge_handles_none_inputs(self):
        """None inputs are treated as empty lists."""
        from src.core.query_engine import QueryEngine
        b = [self._hit(0.70, "b.pdf", 0)]
        merged = QueryEngine._merge_search_results(None, b)
        assert len(merged) == 1

    def test_merge_both_empty(self):
        from src.core.query_engine import QueryEngine
        merged = QueryEngine._merge_search_results([], [])
        assert merged == []


# ============================================================================
# SECTION 2C: SOURCE PATH SEARCH TESTS
# ============================================================================
#
# Tests for VectorStore.source_path_search() -- filename-aware retrieval.
# Uses an in-memory SQLite database with real chunks table schema.
# ============================================================================

import sqlite3
import numpy as np


class TestSourcePathSearch:
    """Test VectorStore.source_path_search() with a real SQLite database."""

    def _make_store(self, tmp_path, chunks):
        """Create a minimal VectorStore with test chunks in SQLite."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE chunks (
                chunk_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT,
                chunk_index INTEGER,
                text TEXT,
                embedding_row INTEGER,
                file_hash TEXT DEFAULT '',
                access_tags TEXT DEFAULT 'shared',
                access_tag_source TEXT DEFAULT 'default_document_tags'
            )
        """)
        conn.execute(
            "CREATE INDEX idx_chunks_source ON chunks(source_path)")
        conn.execute("""
            CREATE VIRTUAL TABLE chunks_fts
            USING fts5(text, content='chunks', content_rowid='chunk_pk')
        """)
        for src, idx, text in chunks:
            cur = conn.execute(
                "INSERT INTO chunks (source_path, chunk_index, text, embedding_row)"
                " VALUES (?, ?, ?, 0)",
                (src, idx, text),
            )
            conn.execute(
                "INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)",
                (cur.lastrowid, text),
            )
        conn.commit()

        # Build a minimal VectorStore mock that has a real conn
        store = MagicMock()
        store.conn = conn
        store._db_lock = __import__("threading").Lock()
        store._ensure_connected = MagicMock()

        # Bind the real method
        from src.core.vector_store import VectorStore
        import types
        store.source_path_search = types.MethodType(
            VectorStore.source_path_search, store)
        return store

    def test_finds_by_filename(self, tmp_path):
        chunks = [
            ("D:/docs/Engineer_Calibration_Guide.pdf", 0, "Calibration steps"),
            ("D:/docs/Safety_Manual.pdf", 0, "Safety procedures"),
        ]
        store = self._make_store(tmp_path, chunks)
        hits = store.source_path_search("calibration guide", top_k=10)
        assert len(hits) >= 1
        assert any("Calibration" in h["source_path"] for h in hits)

    def test_no_match_returns_empty(self, tmp_path):
        chunks = [
            ("D:/docs/Safety_Manual.pdf", 0, "Safety procedures"),
        ]
        store = self._make_store(tmp_path, chunks)
        hits = store.source_path_search("quantum entanglement", top_k=10)
        assert hits == []

    def test_multi_word_scores_higher(self, tmp_path):
        chunks = [
            ("D:/docs/Engineer_Calibration_Guide.pdf", 0, "Step 1"),
            ("D:/docs/General_Guide.pdf", 0, "Overview"),
        ]
        store = self._make_store(tmp_path, chunks)
        hits = store.source_path_search("calibration guide", top_k=10)
        cal_hits = [h for h in hits if "Calibration" in h["source_path"]]
        gen_hits = [h for h in hits if "General" in h["source_path"]]
        # "Calibration" + "Guide" matches 2 words, "General" + "Guide" matches 1
        assert cal_hits[0]["score"] > gen_hits[0]["score"]

    def test_short_words_ignored(self, tmp_path):
        chunks = [
            ("D:/docs/an_overview.pdf", 0, "Content"),
        ]
        store = self._make_store(tmp_path, chunks)
        # "an" and "of" are < 3 chars, should be ignored
        hits = store.source_path_search("an of", top_k=10)
        assert hits == []

    def test_result_format(self, tmp_path):
        chunks = [
            ("D:/docs/Spec_Document.pdf", 0, "The specification"),
        ]
        store = self._make_store(tmp_path, chunks)
        hits = store.source_path_search("spec document", top_k=10)
        assert len(hits) == 1
        hit = hits[0]
        assert "score" in hit
        assert "source_path" in hit
        assert "chunk_index" in hit
        assert "text" in hit
        assert "access_tags" in hit

    def test_respects_top_k(self, tmp_path):
        chunks = [
            (f"D:/docs/Report_{i}.pdf", 0, f"Report {i} content")
            for i in range(20)
        ]
        store = self._make_store(tmp_path, chunks)
        hits = store.source_path_search("report", top_k=5)
        assert len(hits) == 5


# ============================================================================
# SECTION 2b: QUERY DECOMPOSITION TESTS
# ============================================================================

class TestQueryDecomposition:
    """Tests for multi-part query splitting."""

    def test_simple_and_splits(self):
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "What is the calibration procedure and what are the tolerance ranges?"
        )
        assert len(parts) == 2
        assert "calibration" in parts[0].lower()
        assert "tolerance" in parts[1].lower()

    def test_as_well_as_splits(self):
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "Describe the backup schedule as well as the disaster recovery steps"
        )
        assert len(parts) == 2

    def test_semicolon_splits(self):
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "What is the retention policy; how long are weekly backups kept"
        )
        assert len(parts) == 2

    def test_short_fragments_no_split(self):
        """Don't split if one half is too short to be meaningful."""
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "What is A and B?"
        )
        assert len(parts) == 1  # "A" and "B" are < 15 chars

    def test_single_query_unchanged(self):
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "What is the calibration procedure?"
        )
        assert len(parts) == 1
        assert parts[0] == "What is the calibration procedure?"

    def test_along_with_splits(self):
        from src.core.query_engine import _decompose_query
        parts = _decompose_query(
            "List all safety violations along with corrective actions taken"
        )
        assert len(parts) == 2

    def test_multi_query_retrieve_merges_results(self):
        """_multi_query_retrieve should merge hits from multiple sub-queries."""
        from src.core.query_engine import QueryEngine
        from src.core.retriever import SearchHit

        engine = MagicMock(spec=QueryEngine)
        engine._multi_query_retrieve = QueryEngine._multi_query_retrieve.__get__(engine)

        hit_a = SearchHit(score=0.9, source_path="a.pdf", chunk_index=0, text="chunk a")
        hit_b = SearchHit(score=0.8, source_path="b.pdf", chunk_index=0, text="chunk b")
        hit_a_dup = SearchHit(score=0.7, source_path="a.pdf", chunk_index=0, text="chunk a")

        engine.retriever = MagicMock()
        engine.retriever.search.side_effect = [
            [hit_a, hit_b],
            [hit_a_dup],
        ]

        results = engine._multi_query_retrieve(["query 1", "query 2"])
        assert len(results) == 2  # deduped
        assert results[0].score == 0.9  # kept best score for a.pdf


# ============================================================================
# SECTION 3: INDEXER TESTS
# ============================================================================
#
# WHAT WE'RE TESTING:
#   The indexer.py pipeline:
#     scan folder -> parse file -> validate text -> chunk -> embed -> store
#
# WHAT WE MOCK:
#   - VectorStore (fake database)
#   - Embedder (returns dummy vectors)
#   - Chunker (returns predictable chunks)
#   - File system (using temp directories)
#
# TEST CATEGORIES:
#   1. File discovery (supported extensions, excluded dirs)
#   2. File hash change detection (incremental re-indexing)
#   3. Text validation (garbage detection)
#   4. Block processing (large file handling)
#   5. Error resilience (corrupted files don't crash the run)
#   6. Resource cleanup (memory leak prevention)
# ============================================================================

