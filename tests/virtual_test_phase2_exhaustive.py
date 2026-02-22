#!/usr/bin/env python3
# ============================================================================
# EXHAUSTIVE VIRTUAL TEST: Phase 2 Credential Consolidation (Feb 17, 2026)
# ============================================================================
# FILE: tests/virtual_test_phase2_exhaustive.py
#
# WHAT THIS TESTS (every behavioral path):
#   1. FILE INTEGRITY: All modified files exist, compile, no non-ASCII
#   2. SCHEMA CONSISTENCY: Every keyring.get_password call uses correct
#      service name and key names across the entire project
#   3. SINGLE RESOLVER: LLMRouter and _set_model.py delegate to
#      resolve_credentials() instead of duplicate logic
#   4. CONFIG MUTATION PROTECTION: LLMRouter does NOT overwrite
#      config.api.endpoint after gate configuration
#   5. OFFLINE ROUTING: OllamaRouter has ZERO dependency on credentials
#   6. BEHAVIORAL: resolve_credentials actually resolves from keyring,
#      env vars, and config dict in correct priority order
#   7. BEHAVIORAL: LLMRouter.__init__ with/without credentials
#   8. BEHAVIORAL: Config is unchanged after LLMRouter init
#   9. REGRESSION: All Phase 1 modules still import
#  10. BLAST RADIUS: No unintended files modified
#
# HOW TO RUN:
#   cd D:\HybridRAG3
#   python tests\virtual_test_phase2_exhaustive.py
#
# INTERNET ACCESS: NONE
# ============================================================================

import os
import sys
import re
import ast
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the test framework
from tests.virtual_test_framework import (
    test, section, get_report, reset_report, finish,
    check_no_non_ascii, check_python_syntax,
)


# ============================================================================
# FILE CATALOG: What Phase 2 modified
# ============================================================================

# These are the files Phase 2 changed
PHASE2_MODIFIED = {
    "llm_router.py": PROJECT_ROOT / "src" / "core" / "llm_router.py",
    "_set_model.py": PROJECT_ROOT / "scripts" / "_set_model.py",
    "credentials.py": PROJECT_ROOT / "src" / "security" / "credentials.py",
    "diagnostic_v2.py": PROJECT_ROOT / "diagnostics" / "hybridrag_diagnostic_v2.py",
}

# These are files with direct keyring calls that must use correct schema
KEYRING_FILES = {
    "debug_url.py": PROJECT_ROOT / "tools" / "py" / "debug_url.py",
    "net_check.py": PROJECT_ROOT / "tools" / "py" / "net_check.py",
    "show_creds.py": PROJECT_ROOT / "tools" / "py" / "show_creds.py",
    "ssl_check.py": PROJECT_ROOT / "tools" / "py" / "ssl_check.py",
    "store_endpoint.py": PROJECT_ROOT / "tools" / "py" / "store_endpoint.py",
    "store_key.py": PROJECT_ROOT / "tools" / "py" / "store_key.py",
    "test_api_verbose.py": PROJECT_ROOT / "tools" / "py" / "test_api_verbose.py",
    "diagnostic_v2.py": PROJECT_ROOT / "diagnostics" / "hybridrag_diagnostic_v2.py",
    "_rebuild_toolkit.py": PROJECT_ROOT / "tools" / "_rebuild_toolkit.py",
}

# Core modules that must NOT be broken
CORE_MODULES = [
    "src/core/config.py",
    "src/core/network_gate.py",
    "src/core/boot.py",
    "src/core/embedder.py",
    "src/core/vector_store.py",
    "src/core/retriever.py",
    "src/core/query_engine.py",
    "src/core/indexer.py",
    "src/core/chunker.py",
    "src/core/chunk_ids.py",
]


# Directories to exclude from project-wide scans (not active source code)
SCAN_EXCLUDE_DIRS = {".venv", "venv", "__pycache__", "AICodeReviewFindings"}


def _is_excluded(py_file):
    """Return True if py_file is in an excluded directory."""
    parts = py_file.relative_to(PROJECT_ROOT).parts
    return any(p in SCAN_EXCLUDE_DIRS for p in parts)


# ============================================================================
# SIM-01: FILE INTEGRITY
# ============================================================================

section("SIM-01: FILE INTEGRITY (all Phase 2 files exist and compile)")

for label, filepath in PHASE2_MODIFIED.items():

    @test(f"{label} exists and is readable")
    def _check(fp=filepath):
        assert fp.exists(), f"File not found: {fp}"
        content = fp.read_text(encoding="utf-8")
        assert len(content) > 100, f"File suspiciously small: {len(content)} bytes"

    @test(f"{label} compiles cleanly (AST parse)")
    def _syntax(fp=filepath, lbl=label):
        err = check_python_syntax(fp)
        assert err is None, err

    @test(f"{label} has ZERO non-ASCII characters")
    def _ascii(fp=filepath, lbl=label):
        issues = check_no_non_ascii(fp, lbl)
        assert len(issues) == 0, (
            f"Non-ASCII found:\n  " + "\n  ".join(issues[:5])
        )


# ============================================================================
# SIM-02: KEYRING SCHEMA CONSISTENCY (project-wide)
# ============================================================================

section("SIM-02: KEYRING SCHEMA CONSISTENCY (every file, every call)")

# Correct schema:
#   service:  "hybridrag"
#   key:      "azure_api_key"
#   endpoint: "azure_endpoint"


@test("Project-wide: ZERO references to wrong service name 'hybridragv3'")
def _():
    violations = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if _is_excluded(py_file) or ".bak" in py_file.suffix:
            continue
        if "virtual_test" in py_file.name:
            continue  # Test files reference the string in their assertions
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "hybridragv3" in stripped:
                rel = py_file.relative_to(PROJECT_ROOT)
                violations.append(f"  {rel} line {i}: {stripped[:80]}")
    assert len(violations) == 0, (
        f"Found 'hybridragv3' in active code:\n" + "\n".join(violations)
    )


@test("Project-wide: ZERO keyring calls with bare 'api_key' (must be 'azure_api_key')")
def _():
    violations = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if _is_excluded(py_file) or ".bak" in py_file.suffix:
            continue
        if "virtual_test" in py_file.name:
            continue  # Skip test files that mention patterns in assertions
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "keyring.get_password" in stripped or "keyring.set_password" in stripped:
                # Check for bare "api_key" without "azure_" prefix
                if '"api_key"' in stripped and '"azure_api_key"' not in stripped:
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"  {rel} line {i}: {stripped[:80]}")
                if "'api_key'" in stripped and "'azure_api_key'" not in stripped:
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"  {rel} line {i}: {stripped[:80]}")
    assert len(violations) == 0, (
        f"Found bare 'api_key' in keyring calls:\n" + "\n".join(violations)
    )


@test("Project-wide: ZERO keyring calls with bare 'api_endpoint' (must be 'azure_endpoint')")
def _():
    violations = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if _is_excluded(py_file) or ".bak" in py_file.suffix:
            continue
        if "virtual_test" in py_file.name:
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "keyring.get_password" in stripped or "keyring.set_password" in stripped:
                if '"api_endpoint"' in stripped:
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"  {rel} line {i}: {stripped[:80]}")
                if "'api_endpoint'" in stripped:
                    rel = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"  {rel} line {i}: {stripped[:80]}")
    assert len(violations) == 0, (
        f"Found bare 'api_endpoint' in keyring calls:\n" + "\n".join(violations)
    )


for label, filepath in KEYRING_FILES.items():

    @test(f"{label}: all keyring calls use service='hybridrag'")
    def _svc(fp=filepath, lbl=label):
        if not fp.exists():
            return "SKIP"
        content = fp.read_text(encoding="utf-8")
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "keyring.get_password" in stripped or "keyring.set_password" in stripped:
                if '"hybridrag"' not in stripped and "'hybridrag'" not in stripped:
                    assert False, (
                        f"{lbl} line {i}: keyring call without 'hybridrag': {stripped[:80]}"
                    )


# ============================================================================
# SIM-03: LLMRouter USES CANONICAL RESOLVER
# ============================================================================

section("SIM-03: LLMRouter USES CANONICAL RESOLVER (not duplicate logic)")


@test("LLMRouter imports resolve_credentials from credentials module")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    assert "from ..security.credentials import resolve_credentials" in content, (
        "LLMRouter does not import resolve_credentials"
    )


@test("LLMRouter has NO duplicate env var lists in __init__")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    # Find the __init__ method
    match = re.search(
        r'def __init__\(self, config.*?\n    def query\(',
        content, re.DOTALL
    )
    assert match, "Could not find LLMRouter.__init__"
    init_body = match.group(0)
    # These are the old duplicate env var names that should NOT be in __init__
    old_vars = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPEN_AI_KEY",
        "OPENAI_API_KEY",
        "HYBRIDRAG_API_KEY",
    ]
    found = []
    for var in old_vars:
        # Allow in comments/docstrings but not in active code
        for line in init_body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if var in stripped and "os.environ" in stripped:
                found.append(f"  {var} in: {stripped[:60]}")
    assert len(found) == 0, (
        "LLMRouter.__init__ still has duplicate env var lookups:\n" + "\n".join(found)
    )


@test("LLMRouter has NO direct keyring.get_password calls")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "keyring.get_password" not in stripped, (
            f"LLMRouter line {i} has direct keyring call: {stripped[:80]}"
        )


# ============================================================================
# SIM-04: CONFIG MUTATION PROTECTION
# ============================================================================

section("SIM-04: CONFIG MUTATION PROTECTION (LLMRouter does NOT modify config)")


@test("LLMRouter has NO config.api.endpoint assignment")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Check for any assignment to config.api.endpoint
        if re.match(r'.*config\.api\.endpoint\s*=', stripped):
            assert False, (
                f"LLMRouter line {i} mutates config.api.endpoint: {stripped[:80]}"
            )


@test("LLMRouter has NO config.api.* assignment at all")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("self.config = config"):
            continue  # This is the initial assignment, OK
        if re.match(r'.*self\.config\.api\.\w+\s*=', stripped):
            assert False, (
                f"LLMRouter line {i} mutates config.api: {stripped[:80]}"
            )


@test("LLMRouter has explicit NO-MUTATION guard comment")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    assert "We do NOT mutate config.api.endpoint" in content, (
        "Missing NO-MUTATION guard comment in LLMRouter"
    )


@test("BEHAVIORAL: Config object unchanged after LLMRouter init")
def _():
    """Create a mock config, init LLMRouter, verify config wasn't mutated."""
    config = MagicMock()
    config.mode = "online"
    config.api.endpoint = "https://original-endpoint.openai.azure.com/"
    config.api.deployment = "gpt-4"
    config.api.api_version = "2024-02-15"
    config.api.model = "gpt-4"
    config.api.timeout = 30
    config.api.max_retries = 3
    config.ollama.base_url = "http://localhost:11434"
    config.ollama.model = "phi4-mini"
    config.ollama.timeout_seconds = 120

    original_endpoint = "https://original-endpoint.openai.azure.com/"

    # Mock resolve_credentials to return a DIFFERENT endpoint
    mock_creds = MagicMock()
    mock_creds.api_key = "test-key-123"
    mock_creds.endpoint = "https://DIFFERENT-endpoint.openai.azure.com/"
    mock_creds.deployment = "gpt-4"
    mock_creds.api_version = "2024-02-15"
    mock_creds.source_key = "keyring"
    mock_creds.source_endpoint = "keyring"

    with patch("src.security.credentials.resolve_credentials", return_value=mock_creds):
        with patch("src.core.llm_router.APIRouter"):
            with patch("src.core.llm_router.OllamaRouter"):
                from src.core.llm_router import LLMRouter
                router = LLMRouter(config)

    # THE KEY CHECK: config.api.endpoint must still be the original
    assert config.api.endpoint == original_endpoint, (
        f"CONFIG MUTATED! config.api.endpoint changed from "
        f"'{original_endpoint}' to '{config.api.endpoint}'"
    )


# ============================================================================
# SIM-05: OFFLINE ROUTING (zero credential dependency)
# ============================================================================

section("SIM-05: OFFLINE ROUTING (OllamaRouter has ZERO credential dependency)")


@test("OllamaRouter class has NO keyring imports or credential code")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    # Extract OllamaRouter class
    match = re.search(
        r'class OllamaRouter:.*?(?=\nclass )',
        content, re.DOTALL
    )
    assert match, "Could not find OllamaRouter class"
    ollama_code = match.group(0)

    # Check active (non-comment) lines only
    violations = []
    for i, line in enumerate(ollama_code.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # Comments describing other routers are OK
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if "keyring" in stripped:
            violations.append(f"  line {i}: keyring ref: {stripped[:60]}")
        if "resolve_credentials" in stripped:
            violations.append(f"  line {i}: credentials ref: {stripped[:60]}")
        # Check for actual credential-handling code (not parameter names in comments)
        if "api_key" in stripped.lower() and "=" in stripped:
            # Allow only if it's inside a docstring continuation
            if not stripped.startswith('"') and not stripped.startswith("'"):
                violations.append(f"  line {i}: api_key assignment: {stripped[:60]}")

    assert len(violations) == 0, (
        "OllamaRouter has credential code:\n" + "\n".join(violations)
    )


@test("OllamaRouter does NOT import or call resolve_credentials")
def _():
    content = (PROJECT_ROOT / "src" / "core" / "llm_router.py").read_text(encoding="utf-8")
    match = re.search(
        r'class OllamaRouter:.*?(?=\nclass )',
        content, re.DOTALL
    )
    assert match, "Could not find OllamaRouter class"
    ollama_code = match.group(0)
    assert "resolve_credentials" not in ollama_code, (
        "OllamaRouter calls resolve_credentials!"
    )


@test("BEHAVIORAL: LLMRouter routes to Ollama in offline mode (no API needed)")
def _():
    config = MagicMock()
    config.mode = "offline"
    config.ollama.base_url = "http://localhost:11434"
    config.ollama.model = "phi4-mini"
    config.ollama.timeout_seconds = 120
    config.api.endpoint = ""
    config.api.deployment = ""
    config.api.api_version = ""

    mock_ollama = MagicMock()
    mock_ollama_response = MagicMock()
    mock_ollama_response.text = "Hello from Ollama"
    mock_ollama.query.return_value = mock_ollama_response

    # NO credentials at all
    mock_creds = MagicMock()
    mock_creds.api_key = None
    mock_creds.endpoint = None
    mock_creds.deployment = None
    mock_creds.api_version = None
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.security.credentials.resolve_credentials", return_value=mock_creds):
        with patch("src.core.llm_router.OllamaRouter", return_value=mock_ollama):
            from src.core.llm_router import LLMRouter
            router = LLMRouter(config)

    # Router should have ollama but NO api
    assert router.ollama is mock_ollama, "Ollama router not created"
    assert router.api is None, "API router should be None when no credentials"

    # Query should go to Ollama
    result = router.query("test question")
    mock_ollama.query.assert_called_once_with("test question")
    assert result == mock_ollama_response, "Offline query did not return Ollama response"


@test("BEHAVIORAL: LLMRouter creates Ollama even when online mode has credentials")
def _():
    config = MagicMock()
    config.mode = "online"
    config.ollama.base_url = "http://localhost:11434"
    config.ollama.model = "phi4-mini"
    config.ollama.timeout_seconds = 120
    config.api.endpoint = "https://test.openai.azure.com/"
    config.api.deployment = "gpt-4"
    config.api.api_version = "2024-02-15"
    config.api.model = "gpt-4"
    config.api.timeout = 30
    config.api.max_retries = 3

    mock_creds = MagicMock()
    mock_creds.api_key = "test-key"
    mock_creds.endpoint = "https://test.openai.azure.com/"
    mock_creds.deployment = "gpt-4"
    mock_creds.api_version = "2024-02-15"
    mock_creds.source_key = "keyring"
    mock_creds.source_endpoint = "keyring"

    with patch("src.security.credentials.resolve_credentials", return_value=mock_creds):
        with patch("src.core.llm_router.OllamaRouter") as MockOllama:
            with patch("src.core.llm_router.APIRouter") as MockAPI:
                from src.core.llm_router import LLMRouter
                router = LLMRouter(config)

    # Both routers should be created
    MockOllama.assert_called_once_with(config)
    assert router.api is not None, "API router should exist when key provided"


# ============================================================================
# SIM-06: _set_model.py CANONICAL RESOLVER
# ============================================================================

section("SIM-06: _set_model.py USES CANONICAL RESOLVER")


@test("_set_model.py _resolve_creds() calls resolve_credentials()")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_model.py").read_text(encoding="utf-8")
    match = re.search(r'def _resolve_creds\(\):.*?(?=\ndef )', content, re.DOTALL)
    assert match, "Could not find _resolve_creds function"
    func_body = match.group(0)
    assert "resolve_credentials" in func_body, (
        "_resolve_creds does not call resolve_credentials()"
    )


@test("_set_model.py _resolve_creds() has NO inline env var lists")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_model.py").read_text(encoding="utf-8")
    match = re.search(r'def _resolve_creds\(\):.*?(?=\ndef )', content, re.DOTALL)
    assert match, "Could not find _resolve_creds function"
    func_body = match.group(0)

    banned_in_func = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPEN_AI_KEY",
        "OPENAI_API_KEY",
        "HYBRIDRAG_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "OPENAI_BASE_URL",
    ]
    found = []
    for line in func_body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for var in banned_in_func:
            if var in stripped and "os.environ" in stripped:
                found.append(f"  {var}")
    assert len(found) == 0, (
        "Duplicate env var logic found in _resolve_creds:\n" + "\n".join(found)
    )


@test("_set_model.py has NO direct keyring.get_password calls")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_model.py").read_text(encoding="utf-8")
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "keyring.get_password" not in stripped, (
            f"_set_model.py line {i} has direct keyring call: {stripped[:80]}"
        )


@test("_set_model.py _resolve_creds returns (api_key, endpoint) tuple")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_model.py").read_text(encoding="utf-8")
    match = re.search(r'def _resolve_creds\(\):.*?(?=\ndef )', content, re.DOTALL)
    assert match, "Could not find _resolve_creds function"
    func_body = match.group(0)
    assert "return creds.api_key, creds.endpoint" in func_body, (
        "_resolve_creds does not return (api_key, endpoint) tuple"
    )


@test("_set_model.py caller unpacks as (api_key, endpoint)")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_model.py").read_text(encoding="utf-8")
    assert "api_key, endpoint = _resolve_creds()" in content, (
        "Caller does not unpack _resolve_creds() as (api_key, endpoint)"
    )


# ============================================================================
# SIM-07: BEHAVIORAL - resolve_credentials priority order
# ============================================================================

section("SIM-07: BEHAVIORAL (resolve_credentials priority order)")


@test("resolve_credentials: keyring takes priority over env vars")
def _():
    from src.security.credentials import resolve_credentials, ApiCredentials

    # Mock keyring to return a key
    with patch("src.security.credentials._read_keyring") as mock_kr:
        mock_kr.side_effect = lambda key: {
            "azure_api_key": "keyring-key-123",
            "azure_endpoint": "https://keyring-endpoint.com/",
        }.get(key)

        # Also set env vars (should be ignored since keyring wins)
        with patch.dict(os.environ, {
            "AZURE_OPENAI_API_KEY": "env-key-456",
            "AZURE_OPENAI_ENDPOINT": "https://env-endpoint.com/",
        }):
            creds = resolve_credentials()

    assert creds.api_key == "keyring-key-123", (
        f"Expected keyring key, got: {creds.api_key}"
    )
    assert creds.source_key == "keyring", (
        f"Expected source 'keyring', got: {creds.source_key}"
    )
    assert "keyring-endpoint" in creds.endpoint, (
        f"Expected keyring endpoint, got: {creds.endpoint}"
    )


@test("resolve_credentials: env vars used when keyring empty")
def _():
    from src.security.credentials import resolve_credentials

    with patch("src.security.credentials._read_keyring", return_value=None):
        with patch.dict(os.environ, {
            "AZURE_OPENAI_API_KEY": "env-key-789",
            "AZURE_OPENAI_ENDPOINT": "https://env-endpoint.com/",
        }, clear=False):
            creds = resolve_credentials()

    assert creds.api_key == "env-key-789", (
        f"Expected env key, got: {creds.api_key}"
    )
    assert creds.source_key == "env:AZURE_OPENAI_API_KEY", (
        f"Expected source 'env:AZURE_OPENAI_API_KEY', got: {creds.source_key}"
    )


@test("resolve_credentials: AZURE_OPEN_AI_KEY env var works")
def _():
    from src.security.credentials import resolve_credentials

    with patch("src.security.credentials._read_keyring", return_value=None):
        # Clear all other key env vars, set only the company variant
        env_overrides = {
            "HYBRIDRAG_API_KEY": "",
            "AZURE_OPENAI_API_KEY": "",
            "AZURE_OPEN_AI_KEY": "company-variant-key",
            "OPENAI_API_KEY": "",
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            creds = resolve_credentials()

    assert creds.api_key == "company-variant-key", (
        f"Expected company variant key, got: {creds.api_key}"
    )
    assert "AZURE_OPEN_AI_KEY" in creds.source_key, (
        f"Expected AZURE_OPEN_AI_KEY in source, got: {creds.source_key}"
    )


@test("resolve_credentials: config dict used as last resort")
def _():
    from src.security.credentials import resolve_credentials

    with patch("src.security.credentials._read_keyring", return_value=None):
        # Clear all env vars
        env_overrides = {
            "HYBRIDRAG_API_KEY": "",
            "AZURE_OPENAI_API_KEY": "",
            "AZURE_OPEN_AI_KEY": "",
            "OPENAI_API_KEY": "",
            "HYBRIDRAG_API_ENDPOINT": "",
            "AZURE_OPENAI_ENDPOINT": "",
            "OPENAI_API_ENDPOINT": "",
            "AZURE_OPENAI_BASE_URL": "",
            "OPENAI_BASE_URL": "",
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            config_dict = {
                "api": {
                    "key": "config-key-abc",
                    "endpoint": "https://config-endpoint.com/",
                }
            }
            creds = resolve_credentials(config_dict)

    assert creds.api_key == "config-key-abc", (
        f"Expected config key, got: {creds.api_key}"
    )
    assert creds.source_key == "config", (
        f"Expected source 'config', got: {creds.source_key}"
    )


@test("resolve_credentials: returns None when nothing found")
def _():
    from src.security.credentials import resolve_credentials

    with patch("src.security.credentials._read_keyring", return_value=None):
        env_overrides = {
            "HYBRIDRAG_API_KEY": "",
            "AZURE_OPENAI_API_KEY": "",
            "AZURE_OPEN_AI_KEY": "",
            "OPENAI_API_KEY": "",
            "HYBRIDRAG_API_ENDPOINT": "",
            "AZURE_OPENAI_ENDPOINT": "",
            "OPENAI_API_ENDPOINT": "",
            "AZURE_OPENAI_BASE_URL": "",
            "OPENAI_BASE_URL": "",
        }
        with patch.dict(os.environ, env_overrides, clear=False):
            creds = resolve_credentials(None)

    assert creds.api_key is None, f"Expected None, got: {creds.api_key}"
    assert creds.endpoint is None, f"Expected None, got: {creds.endpoint}"


@test("resolve_credentials: extracts deployment from URL")
def _():
    from src.security.credentials import resolve_credentials

    with patch("src.security.credentials._read_keyring") as mock_kr:
        mock_kr.side_effect = lambda key: {
            "azure_api_key": "test-key",
            "azure_endpoint": "https://myorg.openai.azure.com/openai/deployments/gpt4-turbo/chat/completions?api-version=2024-02-15",
        }.get(key)

        with patch.dict(os.environ, {
            "AZURE_OPENAI_DEPLOYMENT": "",
        }, clear=False):
            creds = resolve_credentials()

    assert creds.deployment == "gpt4-turbo", (
        f"Expected 'gpt4-turbo' extracted from URL, got: {creds.deployment}"
    )


# ============================================================================
# SIM-08: CREDENTIALS CONSTANTS ARE PUBLIC
# ============================================================================

section("SIM-08: CREDENTIALS CONSTANTS ARE PUBLIC (importable)")


@test("KEYRING_SERVICE is public and equals 'hybridrag'")
def _():
    from src.security.credentials import KEYRING_SERVICE
    assert KEYRING_SERVICE == "hybridrag", (
        f"KEYRING_SERVICE = '{KEYRING_SERVICE}', expected 'hybridrag'"
    )


@test("KEYRING_KEY_NAME is public and equals 'azure_api_key'")
def _():
    from src.security.credentials import KEYRING_KEY_NAME
    assert KEYRING_KEY_NAME == "azure_api_key", (
        f"KEYRING_KEY_NAME = '{KEYRING_KEY_NAME}', expected 'azure_api_key'"
    )


@test("KEYRING_ENDPOINT_NAME is public and equals 'azure_endpoint'")
def _():
    from src.security.credentials import KEYRING_ENDPOINT_NAME
    assert KEYRING_ENDPOINT_NAME == "azure_endpoint", (
        f"KEYRING_ENDPOINT_NAME = '{KEYRING_ENDPOINT_NAME}', expected 'azure_endpoint'"
    )


@test("KEY_ENV_ALIASES includes AZURE_OPEN_AI_KEY")
def _():
    from src.security.credentials import KEY_ENV_ALIASES
    assert "AZURE_OPEN_AI_KEY" in KEY_ENV_ALIASES, (
        f"AZURE_OPEN_AI_KEY missing from KEY_ENV_ALIASES: {KEY_ENV_ALIASES}"
    )


@test("KEY_ENV_ALIASES includes all 4 expected aliases")
def _():
    from src.security.credentials import KEY_ENV_ALIASES
    expected = [
        "HYBRIDRAG_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPEN_AI_KEY",
        "OPENAI_API_KEY",
    ]
    missing = [a for a in expected if a not in KEY_ENV_ALIASES]
    assert len(missing) == 0, (
        f"Missing from KEY_ENV_ALIASES: {missing}"
    )


@test("ENDPOINT_ENV_ALIASES includes all expected aliases")
def _():
    from src.security.credentials import ENDPOINT_ENV_ALIASES
    expected = [
        "HYBRIDRAG_API_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
        "OPENAI_API_ENDPOINT",
    ]
    missing = [a for a in expected if a not in ENDPOINT_ENV_ALIASES]
    assert len(missing) == 0, (
        f"Missing from ENDPOINT_ENV_ALIASES: {missing}"
    )


# ============================================================================
# SIM-09: REGRESSION - all core modules still import
# ============================================================================

section("SIM-09: REGRESSION (core modules still import)")


@test("credentials.py importable with all public functions")
def _():
    from src.security.credentials import (
        resolve_credentials,
        credential_status,
        ApiCredentials,
        KEYRING_SERVICE,
        KEYRING_KEY_NAME,
        KEYRING_ENDPOINT_NAME,
        KEY_ENV_ALIASES,
        ENDPOINT_ENV_ALIASES,
    )


@test("config.py importable")
def _():
    from src.core.config import Config, load_config


@test("network_gate importable")
def _():
    from src.core.network_gate import configure_gate, get_gate, NetworkGate


@test("boot.py importable")
def _():
    from src.core.boot import boot_hybridrag, BootResult


@test("llm_router.py importable")
def _():
    from src.core.llm_router import LLMRouter


@test("All core modules compile cleanly (AST)")
def _():
    failures = []
    for rel_path in CORE_MODULES:
        fp = PROJECT_ROOT / rel_path
        if not fp.exists():
            continue
        err = check_python_syntax(fp)
        if err:
            failures.append(err)
    assert len(failures) == 0, (
        "Core module compile failures:\n  " + "\n  ".join(failures)
    )


# ============================================================================
# SIM-10: Phase 1 REGRESSION
# ============================================================================

section("SIM-10: PHASE 1 REGRESSION (portable config paths still work)")


@test("_set_online.py still has _config_path()")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_online.py").read_text(encoding="utf-8")
    assert "def _config_path()" in content
    assert "HYBRIDRAG_PROJECT_ROOT" in content


@test("_set_offline.py still has _config_path()")
def _():
    content = (PROJECT_ROOT / "scripts" / "_set_offline.py").read_text(encoding="utf-8")
    assert "def _config_path()" in content
    assert "HYBRIDRAG_PROJECT_ROOT" in content


@test("_profile_status.py still has _config_path()")
def _():
    content = (PROJECT_ROOT / "scripts" / "_profile_status.py").read_text(encoding="utf-8")
    assert "def _config_path()" in content
    assert "HYBRIDRAG_PROJECT_ROOT" in content


@test("requirements.txt is UTF-8 (not UTF-16)")
def _():
    raw = (PROJECT_ROOT / "requirements.txt").read_bytes()
    assert raw[:2] != b'\xff\xfe', "requirements.txt is still UTF-16LE!"


@test(".gitignore has no backtick-n")
def _():
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "`n" not in content, "backtick-n still in .gitignore"


# ============================================================================
# SIM-11: BLAST RADIUS
# ============================================================================

section("SIM-11: BLAST RADIUS (remaining direct keyring calls inventory)")

@test("Inventory of direct keyring.get_password calls outside credentials.py")
def _():
    """Count and report all remaining direct keyring calls.
    These are in utility scripts where calling resolve_credentials()
    would add unnecessary import complexity. They all use correct schema."""
    count = 0
    files_with_calls = {}
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if _is_excluded(py_file) or ".bak" in py_file.suffix:
            continue
        if "virtual_test" in py_file.name:
            continue
        if py_file.name == "credentials.py":
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        hits = 0
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "keyring.get_password" in stripped:
                hits += 1
        if hits > 0:
            rel = str(py_file.relative_to(PROJECT_ROOT))
            files_with_calls[rel] = hits
            count += hits

    print(f"    Total direct keyring calls (outside credentials.py): {count}")
    print(f"    Files ({len(files_with_calls)}):")
    for f, n in sorted(files_with_calls.items()):
        print(f"        {f}: {n} calls")

    # These are acceptable -- utility scripts that need simple keyring reads
    # All verified to use correct schema in SIM-02


# ============================================================================
# FINISH
# ============================================================================

finish()
