# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies runtime retrieval/config sync behavior and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake config objects and mocked backends.
# Outputs: Assertions that retrieval settings follow live mode/config changes.
# Safety notes: No file I/O or network; all dependencies are mocked.
# ============================

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core.grounded_query_engine import GroundedQueryEngine
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
        transformers_rt=SimpleNamespace(config=cfg_old),
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
        assert engine.llm_router.transformers_rt.config is engine.config
        return []

    engine.retriever.search.side_effect = _assert_rebound
    result = engine.query("Does runtime sync before search?")

    assert result.mode == "online"
    assert result.answer == "No relevant information found in knowledge base."


def test_grounded_query_engine_rebinds_retriever_and_router_to_latest_config():
    cfg_old = _make_config(mode="offline")
    router = SimpleNamespace(
        config=cfg_old,
        ollama=SimpleNamespace(config=cfg_old),
        api=SimpleNamespace(config=cfg_old),
        vllm=None,
        transformers_rt=SimpleNamespace(config=cfg_old),
        query=MagicMock(
            return_value=SimpleNamespace(
                text="ok",
                tokens_in=1,
                tokens_out=1,
                model="phi4-mini",
                latency_ms=5.0,
            )
        ),
    )

    with patch("src.core.grounded_query_engine.get_app_logger", return_value=MagicMock()), \
            patch("src.core.query_engine.Retriever") as mock_retriever_cls:
        retriever = MagicMock()
        retriever.config = cfg_old
        retriever.search.return_value = [
            SimpleNamespace(score=0.95, text="fact", source_path="/docs/a.txt", chunk_index=0)
        ]
        retriever.build_context.return_value = "fact"
        retriever.get_sources.return_value = [
            {"path": "/docs/a.txt", "chunks": 1, "avg_relevance": 0.95}
        ]
        mock_retriever_cls.return_value = retriever
        engine = GroundedQueryEngine(cfg_old, MagicMock(), MagicMock(), router)

    cfg_new = _make_config(mode="online")
    engine.config = cfg_new
    engine._guard_available = True
    engine.guard_enabled = True
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(1.0, {"claims": []}))

    result = engine.query("Does grounded runtime sync before search?")

    assert result.mode == "online"
    assert engine.retriever.config is cfg_new
    assert engine.llm_router.config is cfg_new
    assert engine.llm_router.api.config is cfg_new
    assert engine.llm_router.transformers_rt.config is cfg_new


def test_grounded_query_uses_trimmed_context_before_prompt():
    cfg = _make_config(mode="offline")
    router = SimpleNamespace(
        config=cfg,
        ollama=SimpleNamespace(config=cfg),
        api=SimpleNamespace(config=cfg),
        vllm=None,
        transformers_rt=SimpleNamespace(config=cfg),
        query=MagicMock(
            return_value=SimpleNamespace(
                text="ok",
                tokens_in=1,
                tokens_out=1,
                model="phi4-mini",
                latency_ms=5.0,
            )
        ),
    )

    with patch("src.core.grounded_query_engine.get_app_logger", return_value=MagicMock()), \
            patch("src.core.query_engine.Retriever") as mock_retriever_cls:
        retriever = MagicMock()
        retriever.config = cfg
        search_hits = [
            SimpleNamespace(
                score=0.95,
                text="fact " * 400,
                source_path="/docs/a.txt",
                chunk_index=0,
            )
        ]
        retriever.search.return_value = search_hits
        retriever.build_context.return_value = "fact " * 2000
        retriever.get_sources.return_value = [
            {"path": "/docs/a.txt", "chunks": 1, "avg_relevance": 0.95}
        ]
        mock_retriever_cls.return_value = retriever
        engine = GroundedQueryEngine(cfg, MagicMock(), MagicMock(), router)

    engine._guard_available = True
    engine.guard_enabled = True
    engine._trim_context_to_fit = MagicMock(return_value="TRIMMED")
    engine._build_grounded_prompt = MagicMock(return_value="PROMPT")
    engine._verify_response = MagicMock(return_value=(1.0, {"claims": []}))

    result = engine.query("Does guarded sync trim context first?")

    assert result.error is None
    engine._trim_context_to_fit.assert_called_once()
    engine._build_grounded_prompt.assert_called_once_with(
        "Does guarded sync trim context first?",
        "TRIMMED",
        search_hits,
    )


def test_grounded_query_stream_attempts_lazy_guard_load_when_enabled_late():
    cfg = _make_config(mode="offline")
    router = SimpleNamespace(
        config=cfg,
        ollama=SimpleNamespace(config=cfg),
        api=SimpleNamespace(config=cfg),
        vllm=None,
        query=MagicMock(),
        query_stream=MagicMock(
            return_value=iter(
                [
                    {"token": "ok"},
                    {"done": True, "tokens_in": 1, "tokens_out": 1, "model": "phi4-mini", "latency_ms": 5.0},
                ]
            )
        ),
    )

    with patch("src.core.grounded_query_engine.get_app_logger", return_value=MagicMock()), \
            patch("src.core.query_engine.Retriever") as mock_retriever_cls:
        retriever = MagicMock()
        retriever.config = cfg
        retriever.search.return_value = [
            SimpleNamespace(score=0.95, text="fact", source_path="/docs/a.txt", chunk_index=0)
        ]
        retriever.build_context.return_value = "fact"
        retriever.get_sources.return_value = [
            {"path": "/docs/a.txt", "chunks": 1, "avg_relevance": 0.95}
        ]
        mock_retriever_cls.return_value = retriever
        engine = GroundedQueryEngine(cfg, MagicMock(), MagicMock(), router)

    engine.guard_enabled = True
    engine._guard_available = False
    engine._ensure_guard_backend_loaded = MagicMock(return_value=False)

    events = list(engine.query_stream("Does late guard activation try to load?"))

    assert engine._ensure_guard_backend_loaded.call_count == 1
    assert any(event.get("done") for event in events)
