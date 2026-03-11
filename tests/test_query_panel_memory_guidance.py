from src.gui.panels.query_panel_query_render_runtime import (
    _looks_like_offline_memory_pressure,
)


def test_generic_500_does_not_count_as_memory_pressure():
    assert not _looks_like_offline_memory_pressure(
        "HTTP 500 Internal Server Error for url http://127.0.0.1:11434/api/generate"
    )


def test_timeout_does_not_count_as_memory_pressure():
    assert not _looks_like_offline_memory_pressure(
        "ReadTimeout while calling local Ollama backend"
    )


def test_real_memory_pressure_message_is_detected():
    assert _looks_like_offline_memory_pressure(
        "llama runner failed to allocate KV cache: out of memory"
    )


def test_context_overflow_is_not_memory_pressure():
    assert not _looks_like_offline_memory_pressure(
        "requested context window exceeds context length supported by the model"
    )


def test_context_length_exceeded_is_not_memory_pressure():
    assert not _looks_like_offline_memory_pressure(
        "context length 4096 exceeded by prompt of 5200 tokens"
    )
