# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the vllm router area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# test_vllm_router.py -- Tests for VLLMRouter integration
# ============================================================================
#
# COVERS:
#   VLLMRouter -- workstation offline path: queries to local vLLM server
#   LLMRouter  -- vLLM-to-Ollama fallback when vLLM is unavailable
#
# RUN:
#   python -m pytest tests/test_vllm_router.py -v
#
# INTERNET ACCESS: NONE -- all external calls are mocked
# ============================================================================

import json
import time
from unittest.mock import MagicMock, patch
import pytest

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig, FakeVLLMConfig, FakeLLMResponse


class TestVLLMRouter:
    """Tests for the VLLMRouter class (workstation offline mode)."""

    def _make_router(self, config=None):
        """Create a VLLMRouter with a fake config and mocked logger."""
        if config is None:
            config = FakeConfig(mode="offline")
            config.vllm = FakeVLLMConfig(enabled=True)

        with patch("src.core.llm_router.get_app_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            from src.core.llm_router import VLLMRouter
            router = VLLMRouter(config)

        return router

    # ------------------------------------------------------------------
    # Test 1: vLLM disabled by default
    # ------------------------------------------------------------------
    def test_vllm_disabled_by_default(self):
        """
        WHAT: VLLMRouter is not created when config.vllm.enabled is False.
        WHY:  Laptop users with no vLLM installed should never see errors.
        """
        config = FakeConfig(mode="offline")
        assert config.vllm.enabled is False

        with patch("src.core.llm_router.get_app_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            from src.core.llm_router import LLMRouter
            router = LLMRouter(config, api_key=None)

        assert router.vllm is None, (
            "vLLM router should not be created when enabled=false"
        )

    # ------------------------------------------------------------------
    # Test 2: vLLM health check with 30s caching
    # ------------------------------------------------------------------
    def test_vllm_health_check(self):
        """
        WHAT: Health check hits /health and caches for 30 seconds.
        WHY:  Avoids TCP roundtrip on every query.
        """
        router = self._make_router()

        mock_response = MagicMock()
        mock_response.status_code = 200

        router._health_cache = None
        router._client = MagicMock()
        router._client.get.return_value = mock_response

        # First call: hits the server
        result = router.is_available()
        assert result is True
        assert router._client.get.call_count == 1

        # Second call within TTL: uses cache
        result2 = router.is_available()
        assert result2 is True
        assert router._client.get.call_count == 1, (
            "Should use cache on second call within TTL"
        )

    # ------------------------------------------------------------------
    # Test 3: Successful vLLM query
    # ------------------------------------------------------------------
    def test_vllm_query_success(self):
        """
        WHAT: Send prompt to vLLM, get back a proper LLMResponse.
        WHY:  This is the primary workstation offline path.
        """
        router = self._make_router()

        fake_vllm_response = {
            "choices": [{
                "message": {"content": "The operating frequency is 5.2 GHz."},
            }],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 25,
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_vllm_response
        mock_response.raise_for_status = MagicMock()

        router._client = MagicMock()
        router._client.post.return_value = mock_response

        result = router.query("What is the operating frequency?")

        assert result is not None
        assert result.text == "The operating frequency is 5.2 GHz."
        assert result.tokens_in == 150
        assert result.tokens_out == 25
        assert result.model == "phi4-mini"
        assert result.latency_ms >= 0

    # ------------------------------------------------------------------
    # Test 4: vLLM query failure returns None
    # ------------------------------------------------------------------
    def test_vllm_query_failure(self):
        """
        WHAT: HTTP errors from vLLM return None instead of crashing.
        WHY:  Allows fallback to Ollama in the LLMRouter layer.
        """
        router = self._make_router()

        import httpx as real_httpx
        router._client = MagicMock()
        router._client.post.side_effect = real_httpx.HTTPError(
            "Connection refused"
        )

        result = router.query("Test query")
        assert result is None

    # ------------------------------------------------------------------
    # Test 5: vLLM unavailable -> Ollama fallback
    # ------------------------------------------------------------------
    def test_vllm_fallback_to_ollama(self):
        """
        WHAT: When vLLM is enabled but unavailable, LLMRouter falls back
              to Ollama transparently.
        WHY:  Zero downtime -- if vLLM crashes, queries still work.
        """
        config = FakeConfig(mode="offline")
        config.vllm = FakeVLLMConfig(enabled=True)

        with patch("src.core.llm_router.get_app_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            from src.core.llm_router import LLMRouter
            router = LLMRouter(config, api_key=None)

        # vLLM is "enabled" but not available
        router.vllm = MagicMock()
        router.vllm.is_available.return_value = False

        # Ollama is available and returns a response
        mock_ollama = MagicMock()
        mock_ollama.query.return_value = FakeLLMResponse(
            text="Ollama fallback answer",
            tokens_in=100,
            tokens_out=20,
            model="phi4-mini",
            latency_ms=3000.0,
        )
        router.ollama = mock_ollama

        result = router.query("Test question")

        assert result is not None
        assert result.text == "Ollama fallback answer"
        mock_ollama.query.assert_called_once_with("Test question")

    # ------------------------------------------------------------------
    # Test 6: Network gate check on vLLM query
    # ------------------------------------------------------------------
    def test_vllm_network_gate(self):
        """
        WHAT: VLLMRouter calls gate.check_allowed before every request.
        WHY:  Defense-in-depth -- even localhost calls go through the gate.
        """
        router = self._make_router()

        from src.core.network_gate import NetworkBlockedError

        with patch("src.core.llm_router.get_gate") as mock_get_gate:
            mock_gate = MagicMock()
            mock_gate.check_allowed.side_effect = NetworkBlockedError(
                "http://localhost:8000/v1/chat/completions",
                "offline",
                "Blocked by gate",
            )
            mock_get_gate.return_value = mock_gate

            result = router.query("Test query")

        assert result is None, "Should return None when gate blocks request"

    # ------------------------------------------------------------------
    # Test 7: vLLM streaming returns tokens
    # ------------------------------------------------------------------
    def test_vllm_stream(self):
        """
        WHAT: query_stream() yields token dicts from SSE response.
        WHY:  Streaming enables real-time token display in the GUI.
        """
        router = self._make_router()

        # Simulate SSE lines from vLLM
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"Hello"}}],"usage":null}',
            'data: {"choices":[{"delta":{"content":" world"}}],"usage":null}',
            'data: {"choices":[{"delta":{"content":"!"}}],"usage":{"prompt_tokens":10,"completion_tokens":3}}',
            'data: [DONE]',
        ]

        mock_stream_response = MagicMock()
        mock_stream_response.__enter__ = MagicMock(return_value=mock_stream_response)
        mock_stream_response.__exit__ = MagicMock(return_value=False)
        mock_stream_response.raise_for_status = MagicMock()
        mock_stream_response.iter_lines.return_value = iter(sse_lines)

        router._client = MagicMock()
        router._client.stream.return_value = mock_stream_response

        tokens = list(router.query_stream("Test prompt"))

        # Should have 3 token chunks + 1 done marker
        token_texts = [t["token"] for t in tokens if "token" in t]
        assert token_texts == ["Hello", " world", "!"]

        done_markers = [t for t in tokens if t.get("done")]
        assert len(done_markers) == 1
        assert done_markers[0]["tokens_in"] == 10
        assert done_markers[0]["tokens_out"] == 3
