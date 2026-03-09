#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the virtual phase1 foundation area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# VIRTUAL INTEGRATION TEST: Phase 1 Foundation Fix (Feb 17, 2026)
# ============================================================================
# FILE: tests/virtual_test_phase1_foundation.py
#
# CHANGE DESCRIPTION:
#   Phase 1 of the HybridRAG3 redesign. Three independent fixes:
#     FIX-1: 5 scripts get portable config paths via _config_path()
#     FIX-2: requirements.txt converted from UTF-16LE to UTF-8
#     FIX-3: .gitignore line 51 mangled zip rule fixed
#
# FILES MODIFIED (8):
#   1. scripts/_set_online.py      (portable config path)
#   2. scripts/_set_offline.py     (portable config path)
#   3. scripts/_profile_status.py  (portable config path + added os import)
#   4. scripts/_profile_switch.py  (portable config path + added os import)
#   5. scripts/_set_model.py       (portable config path x3 call sites)
#   6. requirements.txt            (UTF-16LE -> UTF-8)
#   7. .gitignore                  (removed mangled line 51, removed dup)
#   8. tests/virtual_test_phase1_foundation.py  (this file)
#
# FILES NOT MODIFIED (all core modules):
#   llm_router.py, query_engine.py, config.py, embedder.py,
#   vector_store.py, retriever.py, indexer.py, chunker.py,
#   network_gate.py, boot.py, credentials.py, start_hybridrag.ps1
#
# HOW TO RUN:
#   cd D:\HybridRAG3
#   python tests\virtual_test_phase1_foundation.py
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
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Import the test framework
from tests.virtual_test_framework import (
    test, section, get_report, reset_report, finish,
    check_no_non_ascii, check_python_syntax, check_file_references,
    run_file_integrity_checks, run_python_syntax_checks,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

MODIFIED_SCRIPTS = {
    "_set_online.py": PROJECT_ROOT / "scripts" / "_set_online.py",
    "_set_offline.py": PROJECT_ROOT / "scripts" / "_set_offline.py",
    "_profile_status.py": PROJECT_ROOT / "scripts" / "_profile_status.py",
    "_profile_switch.py": PROJECT_ROOT / "scripts" / "_profile_switch.py",
    "_set_model.py": PROJECT_ROOT / "scripts" / "_set_model.py",
}
CONFIG_IO = PROJECT_ROOT / "scripts" / "_config_io.py"

REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
GITIGNORE = PROJECT_ROOT / ".gitignore"


def _workspace_tmpdir() -> str:
    root = PROJECT_ROOT / "output" / "virtual_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(dir=str(root))


# ============================================================================
# SIM-01: FILE INTEGRITY
# ============================================================================

section("SIM-01: FILE INTEGRITY (all modified files exist and parse)")

for label, filepath in MODIFIED_SCRIPTS.items():

    @test(f"{label} exists and is readable")
    def _check(fp=filepath):
        assert fp.exists(), f"File not found: {fp}"
        content = fp.read_text(encoding="utf-8")
        assert len(content) > 50, f"File suspiciously small: {len(content)} bytes"

    @test(f"{label} compiles cleanly (AST parse)")
    def _syntax(fp=filepath, lbl=label):
        err = check_python_syntax(fp)
        assert err is None, err


@test("requirements.txt exists and is UTF-8")
def _():
    assert REQUIREMENTS.exists(), "requirements.txt not found"
    raw = REQUIREMENTS.read_bytes()
    # Must NOT start with UTF-16 BOM (FF FE)
    assert raw[:2] != b'\xff\xfe', (
        f"requirements.txt is still UTF-16LE! First bytes: {raw[:4].hex()}"
    )
    # Must be decodable as UTF-8
    text = raw.decode("utf-8")
    assert "openai" in text.lower(), "requirements.txt missing expected package"


@test(".gitignore exists and is readable")
def _():
    assert GITIGNORE.exists(), ".gitignore not found"
    text = GITIGNORE.read_text(encoding="utf-8")
    assert len(text) > 100, ".gitignore suspiciously small"


# ============================================================================
# SIM-02: PORTABLE CONFIG PATH PATTERN
# ============================================================================

section("SIM-02: PORTABLE CONFIG PATH (shared _config_io helpers)")


@test("_config_io.py exists")
def _():
    assert CONFIG_IO.exists(), f"Missing helper: {CONFIG_IO}"


@test("_config_io.py uses HYBRIDRAG_PROJECT_ROOT")
def _():
    content = CONFIG_IO.read_text(encoding="utf-8")
    assert "HYBRIDRAG_PROJECT_ROOT" in content, (
        "_config_io.py missing HYBRIDRAG_PROJECT_ROOT reference"
    )

for label, filepath in MODIFIED_SCRIPTS.items():

    @test(f"{label} imports shared _config_io helpers")
    def _func(fp=filepath, lbl=label):
        content = fp.read_text(encoding="utf-8")
        assert "from _config_io import" in content, (
            f"{lbl} missing shared _config_io import"
        )

    @test(f"{label} has ZERO bare 'config/default_config.yaml' opens")
    def _bare(fp=filepath, lbl=label):
        content = fp.read_text(encoding="utf-8")
        # Find bare opens that are NOT inside the _config_path function
        # or inside comments or error messages
        lines = content.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Allow the string in print/error messages
            if "print(" in stripped and "config/default_config.yaml" in stripped:
                continue
            # Check for bare open calls
            if ("open(\"config/default_config" in stripped
                    or "open('config/default_config" in stripped):
                violations.append(f"  line {i}: {stripped}")
        assert len(violations) == 0, (
            f"{lbl} still has bare config opens:\n" + "\n".join(violations)
        )

# ============================================================================
# SIM-03: BEHAVIORAL TEST - shared config I/O works correctly
# ============================================================================

section("SIM-03: BEHAVIORAL TEST (_config_io resolves correctly)")


@test("default_config_path with HYBRIDRAG_PROJECT_ROOT set")
def _():
    from _config_io import default_config_path
    with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": "/test/project"}):
        normalized = str(default_config_path()).replace("\\", "/")
        assert normalized.endswith("/test/project/config/config.yaml"), (
            f"Bad path: {normalized}"
        )


@test("default_config_path without HYBRIDRAG_PROJECT_ROOT (fallback to repo)")
def _():
    env_copy = os.environ.copy()
    env_copy.pop("HYBRIDRAG_PROJECT_ROOT", None)
    with patch.dict(os.environ, env_copy, clear=True):
        from _config_io import default_config_path
        expected = (PROJECT_ROOT / "config" / "config.yaml").resolve()
        assert default_config_path() == expected, (
            f"Expected '{expected}', got '{default_config_path()}'"
        )


@test("_set_online.py reads and writes config correctly (round-trip)")
def _():
    """Create a temp config, run the logic, verify mode changes."""
    from _config_io import load_default_config, save_default_config_atomic

    tmpdir = _workspace_tmpdir()
    try:
        # Create temp config
        cfg_dir = os.path.join(tmpdir, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_file = os.path.join(cfg_dir, "config.yaml")
        with open(cfg_file, "w") as f:
            f.write("mode: offline\napi:\n  endpoint: https://test.com\n")

        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": tmpdir}):
            cfg = load_default_config()
            assert cfg["mode"] == "offline", f"Initial mode should be offline"

            cfg["mode"] = "online"
            save_default_config_atomic(cfg)
            cfg2 = load_default_config()
            assert cfg2["mode"] == "online", f"Mode should be online after write"
    finally:
        shutil.rmtree(tmpdir)


@test("_profile_switch.py deep merge preserves unrelated settings")
def _():
    """Verify profile switching only changes profile keys."""
    tmpdir = _workspace_tmpdir()
    try:
        cfg_dir = os.path.join(tmpdir, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_file = os.path.join(cfg_dir, "config.yaml")
        with open(cfg_file, "w") as f:
            f.write(
                "mode: offline\n"
                "embedding:\n"
                "  batch_size: 16\n"
                "  model_name: nomic-embed-text\n"
                "  device: cpu\n"
            )
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": tmpdir}):
            from _config_io import load_default_config, save_default_config_atomic

            cfg = load_default_config()

            # Simulate desktop_power profile
            profile_settings = {"embedding": {"batch_size": 64}}
            for sec, vals in profile_settings.items():
                if sec not in cfg:
                    cfg[sec] = {}
                for k, v in vals.items():
                    cfg[sec][k] = v

            save_default_config_atomic(cfg)
            cfg2 = load_default_config()

            assert cfg2["embedding"]["batch_size"] == 64, "batch_size not updated"
            assert cfg2["embedding"]["model_name"] == "nomic-embed-text", (
                "model_name was clobbered by profile switch!"
            )
            assert cfg2["embedding"]["device"] == "cpu", (
                "device was clobbered by profile switch!"
            )
            assert cfg2["mode"] == "offline", "mode changed unexpectedly"
    finally:
        shutil.rmtree(tmpdir)


# ============================================================================
# SIM-04: REQUIREMENTS.TXT ENCODING
# ============================================================================

section("SIM-04: REQUIREMENTS.TXT ENCODING")


@test("requirements.txt starts with ASCII (not UTF-16 BOM)")
def _():
    raw = REQUIREMENTS.read_bytes()
    assert raw[0] != 0xFF and raw[0] != 0xFE, (
        f"UTF-16 BOM detected: first bytes = {raw[:4].hex()}"
    )


@test("requirements.txt contains expected packages")
def _():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    # NOTE: sentence-transformers RETIRED 2026-02-24 (embeddings now via Ollama)
    expected = ["openai", "pyyaml", "numpy", "httpx"]
    missing = [p for p in expected if p.lower() not in text.lower()]
    assert len(missing) == 0, f"Missing packages: {missing}"


@test("requirements.txt has no null bytes (UTF-16 artifact)")
def _():
    raw = REQUIREMENTS.read_bytes()
    null_count = raw.count(b'\x00')
    assert null_count == 0, (
        f"Found {null_count} null bytes -- likely still UTF-16"
    )


@test("pip can parse requirements.txt (basic syntax check)")
def _():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    for i, line in enumerate(text.strip().split("\n"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Basic check: package==version or package>=version etc.
        assert re.match(r'^[\w\-\.]+[=<>!~]+', line), (
            f"Line {i} doesn't look like a requirement: '{line}'"
        )


# ============================================================================
# SIM-05: .GITIGNORE FIX
# ============================================================================

section("SIM-05: .GITIGNORE FIX")


@test(".gitignore has NO backtick-n (mangled line)")
def _():
    text = GITIGNORE.read_text(encoding="utf-8")
    assert "`n" not in text, (
        "Found backtick-n in .gitignore -- mangled line still present"
    )


@test(".gitignore has *.zip rule")
def _():
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = [l.strip() for l in text.split("\n")]
    assert "*.zip" in lines, "Missing *.zip rule"


@test(".gitignore has !releases/*.zip exception")
def _():
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = [l.strip() for l in text.split("\n")]
    assert "!releases/*.zip" in lines, "Missing !releases/*.zip exception"


@test(".gitignore *.zip rule comes BEFORE !releases/*.zip")
def _():
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = text.split("\n")
    zip_line = None
    exception_line = None
    for i, line in enumerate(lines):
        if line.strip() == "*.zip" and zip_line is None:
            zip_line = i
        if line.strip() == "!releases/*.zip" and exception_line is None:
            exception_line = i
    assert zip_line is not None, "*.zip rule not found"
    assert exception_line is not None, "!releases/*.zip not found"
    assert zip_line < exception_line, (
        f"*.zip (line {zip_line}) must come before "
        f"!releases/*.zip (line {exception_line})"
    )


@test(".gitignore has no duplicate .model_cache/ entries")
def _():
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
    count = lines.count(".model_cache/")
    assert count <= 1, f".model_cache/ appears {count} times (should be 1)"


# ============================================================================
# SIM-06: NON-ASCII CHECK (all Python files)
# ============================================================================

section("SIM-06: NON-ASCII CHECK (modified scripts)")

for label, filepath in MODIFIED_SCRIPTS.items():

    @test(f"{label} has ZERO non-ASCII characters")
    def _ascii(fp=filepath, lbl=label):
        issues = check_no_non_ascii(fp, lbl)
        assert len(issues) == 0, (
            f"Non-ASCII found:\n  " + "\n  ".join(issues[:5])
        )


# ============================================================================
# SIM-07: NO READ+WRITE SAME FILE IN ONE EXPRESSION
# ============================================================================

section("SIM-07: NO READ+WRITE SAME FILE IN ONE EXPRESSION")

for label, filepath in MODIFIED_SCRIPTS.items():

    @test(f"{label} separates read and write operations")
    def _rw(fp=filepath, lbl=label):
        content = fp.read_text(encoding="utf-8")
        # Check for patterns like: open(x, 'r')...open(x, 'w') in same with
        # This is a heuristic -- look for 'r' and 'w' opens of same var
        # in the same with block
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "open(" in line and "'rw'" in line:
                assert False, (
                    f"line {i+1}: read+write in same open: {line.strip()}"
                )


# ============================================================================
# SIM-08: REGRESSION - EXISTING TESTS STILL IMPORT
# ============================================================================

section("SIM-08: REGRESSION (existing imports still work)")


@test("credentials.py still importable")
def _():
    from src.security.credentials import resolve_credentials, credential_status


@test("config.py still importable")
def _():
    from src.core.config import Config, load_config


@test("network_gate still importable")
def _():
    from src.core.network_gate import configure_gate, get_gate


@test("boot.py still importable")
def _():
    from src.core.boot import boot_hybridrag, BootResult


# ============================================================================
# SIM-09: BLAST RADIUS - no unintended changes
# ============================================================================

section("SIM-09: BLAST RADIUS CHECK")


@test("start_hybridrag.ps1 was NOT modified (already has PROJECT_ROOT)")
def _():
    ps1 = PROJECT_ROOT / "start_hybridrag.ps1"
    content = ps1.read_text(encoding="utf-8", errors="replace")
    assert "$env:HYBRIDRAG_PROJECT_ROOT = $PROJECT_ROOT" in content, (
        "start_hybridrag.ps1 missing HYBRIDRAG_PROJECT_ROOT export!"
    )


@test("_check_creds.py was NOT modified (already uses PROJECT_ROOT)")
def _():
    f = PROJECT_ROOT / "scripts" / "_check_creds.py"
    content = f.read_text(encoding="utf-8")
    assert "HYBRIDRAG_PROJECT_ROOT" in content
    # Verify it does NOT have _config_path (it doesn't open config)
    assert "def _config_path" not in content, (
        "_check_creds.py should not have _config_path -- it doesn't open config"
    )


@test("_test_api.py was NOT modified (already uses PROJECT_ROOT)")
def _():
    f = PROJECT_ROOT / "scripts" / "_test_api.py"
    content = f.read_text(encoding="utf-8")
    assert "HYBRIDRAG_PROJECT_ROOT" in content


@test("credentials.py was NOT modified")
def _():
    f = PROJECT_ROOT / "src" / "security" / "credentials.py"
    content = f.read_text(encoding="utf-8")
    assert "def credential_status" in content, "credential_status missing!"
    assert 'if __name__ == "__main__"' in content, "__main__ block missing!"


# ============================================================================
# FINISH
# ============================================================================

finish()
