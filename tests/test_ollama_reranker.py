"""Tests for the Ollama-based reranker (src/core/ollama_reranker.py).

Tests run without a live Ollama server by mocking httpx responses.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.ollama_reranker import OllamaReranker, load_ollama_reranker
from src.core.network_gate import NetworkBlockedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nbe(msg="blocked"):
    """Build a NetworkBlockedError with required positional args."""
    return NetworkBlockedError(msg, "offline", "test block")


def _mock_ollama_response(score_text):
    """Build a fake httpx.Response-like object returning the given score."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"response": score_text}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_client_class(scores):
    """Return a class that acts as httpx.Client context manager.

    Each .post() call pops the next score from the list.
    Thread-safe via a lock since the reranker uses ThreadPoolExecutor.
    """
    import threading
    lock = threading.Lock()
    call_idx = {"n": 0}

    class FakeClient:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kw):
            with lock:
                idx = call_idx["n"]
                call_idx["n"] += 1
            score = scores[idx] if idx < len(scores) else "0"
            return _mock_ollama_response(str(score))

        def get(self, url, **kw):
            return _mock_ollama_response("")

    return FakeClient


# ---------------------------------------------------------------------------
# OllamaReranker.predict
# ---------------------------------------------------------------------------

class TestOllamaRerankerPredict:

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_returns_centered_scores(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        scores_from_llm = ["8", "3", "10", "0"]

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class(scores_from_llm)):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            pairs = [
                ("what is X?", "doc about X"),
                ("what is X?", "doc about Y"),
                ("what is X?", "perfect doc about X"),
                ("what is X?", "totally irrelevant"),
            ]
            result = reranker.predict(pairs)

        assert len(result) == 4
        assert result[0] == pytest.approx(3.0)   # 8 - 5
        assert result[1] == pytest.approx(-2.0)  # 3 - 5
        assert result[2] == pytest.approx(5.0)   # 10 - 5
        assert result[3] == pytest.approx(-5.0)  # 0 - 5

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_handles_decimal_scores(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class(["7.5"])):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            result = reranker.predict([("q", "d")])

        assert result[0] == pytest.approx(2.5)  # 7.5 - 5.0

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_caps_at_10(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class(["15"])):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            result = reranker.predict([("q", "d")])

        # Capped at 10 -> 10-5 = 5.0
        assert result[0] == pytest.approx(5.0)

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_handles_garbage_response(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class(["I cannot rate this passage"])):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            result = reranker.predict([("q", "d")])

        # No number found -> -5.0
        assert result[0] == pytest.approx(-5.0)

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_handles_network_error(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()

        class ErrorClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def post(self, *a, **kw):
                raise ConnectionError("server down")

        with patch("src.core.ollama_reranker.httpx.Client", ErrorClient):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            result = reranker.predict([("q", "d")])

        assert result[0] == pytest.approx(-5.0)

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_handles_gate_blocked(self, mock_gate):
        mock_gate.return_value.check_allowed.side_effect = _nbe()

        reranker = OllamaReranker(
            base_url="http://127.0.0.1:11434",
            model="phi4-mini",
            max_workers=1,
        )
        result = reranker.predict([("q", "d")])

        assert result[0] == pytest.approx(-5.0)

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_preserves_pair_order(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        scores = ["1", "9", "5", "7", "3"]

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class(scores)):
            reranker = OllamaReranker(
                base_url="http://127.0.0.1:11434",
                model="phi4-mini",
                max_workers=1,
            )
            pairs = [(f"q{i}", f"d{i}") for i in range(5)]
            result = reranker.predict(pairs)

        expected = [1 - 5, 9 - 5, 5 - 5, 7 - 5, 3 - 5]
        for got, want in zip(result, expected):
            assert got == pytest.approx(float(want))

    @patch("src.core.ollama_reranker.get_gate")
    def test_predict_empty_pairs(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        reranker = OllamaReranker(
            base_url="http://127.0.0.1:11434",
            model="phi4-mini",
        )
        result = reranker.predict([])
        assert result == []


# ---------------------------------------------------------------------------
# load_ollama_reranker
# ---------------------------------------------------------------------------

class TestLoadOllamaReranker:

    @patch("src.core.ollama_reranker.get_gate")
    def test_returns_reranker_when_ollama_healthy(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4-mini"

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class([])):
            result = load_ollama_reranker(config)

        assert isinstance(result, OllamaReranker)
        assert result.model == "phi4-mini"

    @patch("src.core.ollama_reranker.get_gate")
    def test_returns_none_when_ollama_down(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4-mini"

        class DownClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def get(self, *a, **kw):
                raise ConnectionError("down")

        with patch("src.core.ollama_reranker.httpx.Client", DownClient):
            result = load_ollama_reranker(config)

        assert result is None

    def test_returns_none_when_no_ollama_config(self):
        config = MagicMock(spec=[])  # no ollama attr
        result = load_ollama_reranker(config)
        assert result is None

    @patch("src.core.ollama_reranker.get_gate")
    def test_returns_none_when_gate_blocks(self, mock_gate):
        mock_gate.return_value.check_allowed.side_effect = _nbe()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4-mini"

        result = load_ollama_reranker(config)
        assert result is None

    @patch("src.core.ollama_reranker.get_gate")
    def test_returns_none_when_unhealthy_status(self, mock_gate):
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4-mini"

        class UnhealthyClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def get(self, *a, **kw):
                resp = MagicMock()
                resp.status_code = 503
                return resp

        with patch("src.core.ollama_reranker.httpx.Client", UnhealthyClient):
            result = load_ollama_reranker(config)

        assert result is None

    @patch("src.core.ollama_reranker.get_gate")
    def test_prefers_retrieval_reranker_model(self, mock_gate):
        """load_ollama_reranker prefers retrieval.reranker_model over ollama.model."""
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4:14b-q4_K_M"
        config.retrieval.reranker_model = "phi4:14b"

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class([])):
            result = load_ollama_reranker(config)

        assert isinstance(result, OllamaReranker)
        assert result.model == "phi4:14b"

    @patch("src.core.ollama_reranker.get_gate")
    def test_ignores_retired_crossencoder_model(self, mock_gate):
        """Retired cross-encoder model name is ignored, falls back to ollama.model."""
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4:14b-q4_K_M"
        config.retrieval.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class([])):
            result = load_ollama_reranker(config)

        assert isinstance(result, OllamaReranker)
        assert result.model == "phi4:14b-q4_K_M"

    @patch("src.core.ollama_reranker.get_gate")
    def test_falls_back_to_ollama_model_when_no_reranker_model(self, mock_gate):
        """When retrieval.reranker_model is not set, uses ollama.model."""
        mock_gate.return_value.check_allowed = MagicMock()
        config = MagicMock()
        config.ollama.base_url = "http://127.0.0.1:11434"
        config.ollama.model = "phi4-mini"
        # Simulate retrieval config without reranker_model attribute
        config.retrieval = MagicMock(spec=["top_k", "min_score"])

        with patch("src.core.ollama_reranker.httpx.Client",
                    _mock_client_class([])):
            result = load_ollama_reranker(config)

        assert isinstance(result, OllamaReranker)
        assert result.model == "phi4-mini"
