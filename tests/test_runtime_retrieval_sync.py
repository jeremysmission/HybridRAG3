# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies runtime retrieval/config sync behavior and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake config objects and mocked backends.
# Outputs: Assertions that retrieval settings follow live mode/config changes.
# Safety notes: No file I/O or network; all dependencies are mocked.
# ============================

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core.query_engine import QueryEngine
from src.core.retriever import Retriever


class _DummyStore:
    def search(self, *_args, **_kwargs):
        return []

    def fts_search(self, *_args, **_kwargs):
        return []


class _DummyEmbedder:
    def embed_query(self, _query):
        return []


def _make_config(mode: str = "offline"):
    return SimpleNamespace(
        mode=mode,
        retrieval=SimpleNamespace(
            top_k=5,
            min_score=0.10,
            hybrid_search=True,
            reranker_enabled=False,
            reranker_model="",
            reranker_top_n=20,
            rrf_k=60,
            block_rows=25000,
            lex_boost=0.06,
            offline_top_k=3,
        ),
        api=SimpleNamespace(
            model="gpt-4o",
            deployment="gpt-4o",
            context_window=128000,
            max_tokens=2048,
            temperature=0.05,
            timeout_seconds=60,
        ),
        ollama=SimpleNamespace(
            model="phi4:14b-q4_K_M",
            context_window=4096,
            num_predict=512,
            temperature=0.1,
            timeout_seconds=180,
        ),
        cost=SimpleNamespace(
            input_cost_per_1k=0.0015,
            output_cost_per_1k=0.002,
        ),
    )


def test_retriever_search_refreshes_live_config_before_search():
    cfg = _make_config(mode="offline")
    retriever = Retriever(_DummyStore(), _DummyEmbedder(), cfg)

    cfg.retrieval.top_k = 11
    cfg.retrieval.min_score = 0.05
    cfg.retrieval.hybrid_search = False
    cfg.retrieval.offline_top_k = None

    with patch.object(retriever, "_hybrid_search", return_value=[]) as mock_hybrid, \
            patch.object(retriever, "_vector_search", return_value=[]) as mock_vector:
        retriever.search("search with fresh config")

    assert retriever.top_k == 11
    assert abs(retriever.min_score - 0.05) < 1e-9
    assert retriever.hybrid_search is False
    assert retriever.offline_top_k is None
    mock_vector.assert_called_once()
    mock_hybrid.assert_not_called()


def test_query_engine_rebinds_retriever_and_router_to_latest_config():
    cfg_old = _make_config(mode="offline")
    router = SimpleNamespace(
        config=cfg_old,
        ollama=SimpleNamespace(config=cfg_old),
        api=SimpleNamespace(config=cfg_old),
        vllm=None,
    )

    with patch("src.core.query_engine.get_app_logger", return_value=MagicMock()), \
            patch("src.core.query_engine.Retriever") as mock_retriever_cls:
        retriever = MagicMock()
        retriever.config = cfg_old
        retriever.search.return_value = []
        mock_retriever_cls.return_value = retriever
        engine = QueryEngine(cfg_old, MagicMock(), MagicMock(), router)

    cfg_new = _make_config(mode="online")
    cfg_new.retrieval.top_k = 12
    engine.config = cfg_new

    def _assert_rebound(_query):
        assert engine.retriever.config is engine.config
        assert engine.llm_router.config is engine.config
        assert engine.llm_router.api.config is engine.config
        return []

    engine.retriever.search.side_effect = _assert_rebound
    result = engine.query("Does runtime sync before search?")

    assert result.mode == "online"
    assert result.answer == "No relevant information found in knowledge base."
