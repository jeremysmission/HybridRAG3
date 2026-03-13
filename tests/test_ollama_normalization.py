# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the ollama normalization area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from types import SimpleNamespace

import pytest

from src.core.embedder import Embedder
from src.core.model_identity import (
    build_ollama_aliases,
    canonicalize_model_name,
    resolve_ollama_model_name,
)
from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url


def test_sanitize_ollama_base_url_fixes_common_typo():
    assert sanitize_ollama_base_url("http://127.0.0:11434") == "http://127.0.0.1:11434"
    assert sanitize_ollama_base_url("127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_sanitize_ollama_base_url_forces_http_for_loopback_and_strips_api_suffix():
    assert sanitize_ollama_base_url("https://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert sanitize_ollama_base_url("https://localhost:11434/") == "http://localhost:11434"
    assert sanitize_ollama_base_url("https://127.0.0:11434/api/generate") == "http://127.0.0.1:11434"
    assert sanitize_ollama_base_url("https://localhost:11434/custom/path") == "http://localhost:11434"
    assert sanitize_ollama_base_url("localhost") == "http://localhost:11434"


def test_sanitize_ollama_base_url_preserves_non_loopback_https():
    assert sanitize_ollama_base_url("https://ollama.internal:11434/api/generate") == "https://ollama.internal:11434"


def test_embedder_sanitizes_https_loopback_env_var_before_embed_requests(monkeypatch):
    import sys

    calls = []

    class DummyResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[1.0, 0.0]]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            return None

        def post(self, url, json=None):
            calls.append({"url": url, "json": json})
            return DummyResponse()

        def close(self):
            return None

    fake_httpx = SimpleNamespace(
        Client=DummyClient,
        Timeout=lambda *_args, **_kwargs: None,
    )

    monkeypatch.setenv("OLLAMA_HOST", "https://127.0.0.1:11434/api/embed")
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    embedder = Embedder(model_name="nomic-embed-text", dimension=2)
    try:
        assert embedder.base_url == "http://127.0.0.1:11434"
        result = embedder.embed_batch(["hello"])
    finally:
        embedder.close()

    assert result.shape == (1, 2)
    assert calls == [
        {
            "url": "http://127.0.0.1:11434/api/embed",
            "json": {
                "model": "nomic-embed-text",
                "input": ["hello"],
            },
        }
    ]


def test_canonicalize_model_name_phi_aliases():
    assert canonicalize_model_name("phi4-mini:latest") == "phi4-mini"
    assert canonicalize_model_name("phi4-mini:3.8b") == "phi4-mini"
    assert canonicalize_model_name("PHI4-MINI:LATEST") == "phi4-mini"
    assert canonicalize_model_name("phi4:14b-q4_K_M") == "phi4:14b-q4_K_M"
    assert canonicalize_model_name("phi4:14b-q4_k_m") == "phi4:14b-q4_K_M"
    assert canonicalize_model_name("PHI4:14B") == "phi4:14b-q4_K_M"


def test_alias_builder_includes_family_candidates():
    aliases = build_ollama_aliases("phi4-mini:latest")
    assert "phi4-mini" in aliases
    assert "phi4-mini:3.8b" in aliases


def test_resolve_ollama_model_name_prefers_installed_tag():
    installed = ["phi4-mini:latest", "phi4:14b-q4_K_M"]
    assert resolve_ollama_model_name("phi4-mini", installed) == "phi4-mini:latest"
    assert resolve_ollama_model_name("phi4:14b", installed) == "phi4:14b-q4_K_M"
    assert resolve_ollama_model_name("PHI4:14B", installed) == "phi4:14b-q4_K_M"


def test_boot_hybridrag_sanitizes_loopback_probe_url(monkeypatch):
    from src.core import boot as boot_module

    captured = {}

    class DummyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyOpener:
        def open(self, req, timeout=None):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return DummyResponse()

    monkeypatch.setattr(
        boot_module,
        "load_config",
        lambda _config_path=None: {
            "mode": "offline",
            "ollama": {"base_url": "https://127.0.0.1:11434/api/generate"},
            "api": {},
        },
    )
    monkeypatch.setattr(
        "src.security.credentials.resolve_credentials",
        lambda _config: SimpleNamespace(
            has_endpoint=False,
            has_key=False,
            source_endpoint="config",
            source_key="config",
            endpoint="",
            is_online_ready=False,
        ),
    )
    monkeypatch.setattr(
        "src.core.network_gate.configure_gate",
        lambda *args, **kwargs: SimpleNamespace(mode="offline"),
    )
    monkeypatch.setattr(
        "src.core.network_gate.get_gate",
        lambda: SimpleNamespace(check_allowed=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_args, **_kwargs: DummyOpener(),
    )

    result = boot_module.boot_hybridrag()

    assert captured["url"] == "http://127.0.0.1:11434"
    assert result.config["ollama"]["base_url"] == "http://127.0.0.1:11434"
    assert result.offline_available is True
