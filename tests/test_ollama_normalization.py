from src.core.model_identity import (
    build_ollama_aliases,
    canonicalize_model_name,
    resolve_ollama_model_name,
)
from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url


def test_sanitize_ollama_base_url_fixes_common_typo():
    assert sanitize_ollama_base_url("http://127.0.0:11434") == "http://127.0.0.1:11434"
    assert sanitize_ollama_base_url("127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_canonicalize_model_name_phi_aliases():
    assert canonicalize_model_name("phi4-mini:latest") == "phi4-mini"
    assert canonicalize_model_name("phi4-mini:3.8b") == "phi4-mini"
    assert canonicalize_model_name("phi4:14b-q4_K_M") == "phi4:14b"


def test_alias_builder_includes_family_candidates():
    aliases = build_ollama_aliases("phi4-mini:latest")
    assert "phi4-mini" in aliases
    assert "phi4-mini:3.8b" in aliases


def test_resolve_ollama_model_name_prefers_installed_tag():
    installed = ["phi4-mini:latest", "phi4:14b-q4_K_M"]
    assert resolve_ollama_model_name("phi4-mini", installed) == "phi4-mini:latest"
    assert resolve_ollama_model_name("phi4:14b", installed) == "phi4:14b-q4_K_M"
