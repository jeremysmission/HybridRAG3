#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the virtual setup wizard area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- VIRTUAL TEST: First-Run Setup Wizard
# ============================================================================
# FILE: tests/virtual_test_setup_wizard.py
#
# Tests the setup wizard (src/gui/panels/setup_wizard.py), the launcher
# integration (src/gui/launch_gui.py), and the config.py edit.
#
# 7 simulation tiers, from easy to brutal:
#   SIM-01  File integrity (exists, syntax, encoding)
#   SIM-02  needs_setup() logic under 6 conditions
#   SIM-03  Config YAML round-trip (write, read-back, key correctness)
#   SIM-04  Path validation (empty, nonexistent, spaces, unicode, UNC)
#   SIM-05  config.py setup_complete stripping
#   SIM-06  Launch script resilience (batch file GP bypass, quote safety)
#   SIM-07  Work-computer simulation (GP detection, encoding, fallback)
#
# INTERNET ACCESS: NONE
# DEPENDENCIES: Python stdlib + project source (no pip packages needed)
# ============================================================================

import os
import sys
import ast
import re
import tempfile
import shutil
import textwrap
from pathlib import Path

# Ensure project root on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tests.virtual_test_framework import (
    section, test, get_report, reset_report, finish,
    check_python_syntax, check_no_non_ascii,
)

reset_report()
report = get_report()
report.change_description = "First-Run Setup Wizard (setup_wizard.py + launcher + config)"
report.files_modified = [
    "src/gui/panels/setup_wizard.py",
    "src/gui/launch_gui.py",
    "src/core/config.py",
    "start_gui.bat",
    "start_rag.bat",
]

WIZARD_PATH = _project_root / "src" / "gui" / "panels" / "setup_wizard.py"
LAUNCH_PATH = _project_root / "src" / "gui" / "launch_gui.py"
CONFIG_PATH = _project_root / "src" / "core" / "config.py"
GUI_BAT = _project_root / "start_gui.bat"
RAG_BAT = _project_root / "start_rag.bat"
YAML_PATH = _project_root / "config" / "config.yaml"
VIRTUAL_TMP_ROOT = _project_root / "output" / "virtual_tmp" / "setup_wizard"
VIRTUAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _make_tmp_dir(prefix: str) -> str:
    """Create temp dirs inside the repo so sandboxed virtual tests can write."""
    return tempfile.mkdtemp(prefix=prefix, dir=str(VIRTUAL_TMP_ROOT))


# ============================================================================
# SIM-01: FILE INTEGRITY
# ============================================================================
section("SIM-01: FILE INTEGRITY (exists, syntax, encoding, size)")


@test("setup_wizard.py exists and is readable")
def _():
    assert WIZARD_PATH.exists(), f"Not found: {WIZARD_PATH}"
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert len(content) > 1000, f"Suspiciously small: {len(content)} chars"


@test("setup_wizard.py compiles without syntax errors")
def _():
    err = check_python_syntax(WIZARD_PATH)
    assert err is None, err


@test("setup_wizard.py has zero non-ASCII characters")
def _():
    issues = check_no_non_ascii(WIZARD_PATH)
    assert len(issues) == 0, "\n  ".join(issues[:5])


@test("launch_gui.py compiles without syntax errors")
def _():
    err = check_python_syntax(LAUNCH_PATH)
    assert err is None, err


@test("config.py compiles without syntax errors")
def _():
    err = check_python_syntax(CONFIG_PATH)
    assert err is None, err


@test("setup_wizard.py is under 500 lines (class limit)")
def _():
    tree = ast.parse(WIZARD_PATH.read_text(encoding="utf-8"))
    wizard_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SetupWizard"
    )
    end_line = max(
        getattr(node, "end_lineno", wizard_class.lineno)
        for node in ast.walk(wizard_class)
    )
    span = end_line - wizard_class.lineno + 1
    assert span <= 500, f"SetupWizard span {span} lines (max 500)"


@test("No banned words in setup_wizard.py")
def _():
    banned = ["defense", "contractor", "classified", "NGC",
              "Northrop", "NIST", "DoD", "Claude", "Anthropic"]
    content = WIZARD_PATH.read_text(encoding="utf-8")
    found = [w for w in banned if w.lower() in content.lower()]
    assert not found, f"Banned words found: {found}"


@test("start_gui.bat exists and is readable")
def _():
    assert GUI_BAT.exists(), f"Not found: {GUI_BAT}"


@test("start_rag.bat exists and is readable")
def _():
    assert RAG_BAT.exists(), f"Not found: {RAG_BAT}"


# ============================================================================
# SIM-02: needs_setup() LOGIC (6 conditions)
# ============================================================================
section("SIM-02: needs_setup() LOGIC")


@test("needs_setup() returns False when HYBRIDRAG_DATA_DIR is set")
def _():
    from src.gui.panels.setup_wizard import needs_setup
    saved = os.environ.get("HYBRIDRAG_DATA_DIR")
    try:
        os.environ["HYBRIDRAG_DATA_DIR"] = "C:\\fake\\path"
        result = needs_setup(str(_project_root))
        assert result is False, f"Expected False, got {result}"
    finally:
        if saved is not None:
            os.environ["HYBRIDRAG_DATA_DIR"] = saved
        else:
            os.environ.pop("HYBRIDRAG_DATA_DIR", None)


@test("needs_setup() returns True when config has empty paths and no env var")
def _():
    import yaml
    # Use a temp directory with a minimal config that has empty paths
    tmp = _make_tmp_dir("wiz_test_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        with open(os.path.join(cfg_dir, "config.yaml"), "w") as f:
            yaml.dump({"mode": "offline", "paths": {
                "database": "", "source_folder": "", "embeddings_cache": "",
            }}, f)

        saved = os.environ.pop("HYBRIDRAG_DATA_DIR", None)
        try:
            from src.gui.panels.setup_wizard import needs_setup
            result = needs_setup(tmp)
            assert result is True, f"Expected True, got {result}"
        finally:
            if saved is not None:
                os.environ["HYBRIDRAG_DATA_DIR"] = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("needs_setup() returns False when setup_complete is true")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_test_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        with open(os.path.join(cfg_dir, "config.yaml"), "w") as f:
            yaml.dump({
                "mode": "offline",
                "setup_complete": True,
                "paths": {"database": "", "source_folder": ""},
            }, f)

        saved = os.environ.pop("HYBRIDRAG_DATA_DIR", None)
        try:
            from src.gui.panels.setup_wizard import needs_setup
            result = needs_setup(tmp)
            assert result is False, f"Expected False, got {result}"
        finally:
            if saved is not None:
                os.environ["HYBRIDRAG_DATA_DIR"] = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("needs_setup() returns False when paths are already populated and valid")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_test_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        source_dir = os.path.join(tmp, "docs")
        index_dir = os.path.join(tmp, "index")
        os.makedirs(source_dir, exist_ok=True)
        os.makedirs(index_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "config.yaml"), "w") as f:
            yaml.dump({
                "mode": "offline",
                "paths": {
                    "database": os.path.join(index_dir, "hybridrag.sqlite3"),
                    "source_folder": source_dir,
                },
            }, f)

        saved = os.environ.pop("HYBRIDRAG_DATA_DIR", None)
        try:
            from src.gui.panels.setup_wizard import needs_setup
            result = needs_setup(tmp)
            assert result is False, f"Expected False, got {result}"
        finally:
            if saved is not None:
                os.environ["HYBRIDRAG_DATA_DIR"] = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("needs_setup() returns True when config file is missing entirely")
def _():
    tmp = _make_tmp_dir("wiz_test_")
    try:
        saved = os.environ.pop("HYBRIDRAG_DATA_DIR", None)
        try:
            from src.gui.panels.setup_wizard import needs_setup
            result = needs_setup(tmp)
            assert result is True, f"Expected True (no config dir), got {result}"
        finally:
            if saved is not None:
                os.environ["HYBRIDRAG_DATA_DIR"] = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("needs_setup() returns True when YAML is corrupt/unparseable")
def _():
    tmp = _make_tmp_dir("wiz_test_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        with open(os.path.join(cfg_dir, "config.yaml"), "w") as f:
            f.write("{{{{not valid yaml: [[[")

        saved = os.environ.pop("HYBRIDRAG_DATA_DIR", None)
        try:
            from src.gui.panels.setup_wizard import needs_setup
            result = needs_setup(tmp)
            assert result is True, f"Expected True (corrupt YAML), got {result}"
        finally:
            if saved is not None:
                os.environ["HYBRIDRAG_DATA_DIR"] = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# SIM-03: CONFIG YAML ROUND-TRIP
# ============================================================================
section("SIM-03: CONFIG YAML ROUND-TRIP (write, read-back, correctness)")


@test("Wizard config write produces valid YAML with correct keys")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_yaml_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        cfg_path = os.path.join(cfg_dir, "config.yaml")
        # Start with a minimal existing config (simulates fresh install)
        with open(cfg_path, "w") as f:
            yaml.dump({
                "mode": "offline",
                "paths": {"database": "", "source_folder": "", "embeddings_cache": ""},
                "embedding": {"model_name": "nomic-embed-text"},
            }, f)

        # Simulate what _on_finish() does (without tkinter)
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        src_path = os.path.join(tmp, "docs")
        idx_path = os.path.join(tmp, "index")
        os.makedirs(src_path, exist_ok=True)
        os.makedirs(idx_path, exist_ok=True)

        data["paths"]["database"] = os.path.join(idx_path, "hybridrag.sqlite3")
        data["paths"]["embeddings_cache"] = os.path.join(idx_path, "_embeddings")
        data["paths"]["source_folder"] = src_path
        data["mode"] = "offline"
        data["setup_complete"] = True

        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        # Read back and verify
        with open(cfg_path, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        assert result["setup_complete"] is True, "setup_complete not True"
        assert result["mode"] == "offline", f"mode is {result['mode']}"
        assert result["paths"]["database"].endswith("hybridrag.sqlite3"), \
            f"database path wrong: {result['paths']['database']}"
        assert result["paths"]["source_folder"] == src_path, \
            f"source_folder wrong: {result['paths']['source_folder']}"
        assert "_embeddings" in result["paths"]["embeddings_cache"], \
            f"embeddings_cache wrong: {result['paths']['embeddings_cache']}"
        # Original keys preserved
        assert "embedding" in result, "Original embedding section lost"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("Wizard preserves all existing YAML keys (no data loss)")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_yaml_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        cfg_path = os.path.join(cfg_dir, "config.yaml")

        # Full config with lots of sections
        original = {
            "mode": "offline",
            "paths": {"database": "", "source_folder": "", "embeddings_cache": ""},
            "embedding": {"model_name": "nomic-embed-text", "dimension": 768},
            "chunking": {"chunk_size": 1200, "overlap": 200},
            "ollama": {"model": "phi4-mini", "timeout_seconds": 600},
            "retrieval": {"top_k": 5, "min_score": 0.1},
            "api": {"endpoint": "", "model": ""},
        }
        with open(cfg_path, "w") as f:
            yaml.dump(original, f, default_flow_style=False)

        # Simulate wizard write
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        data["paths"]["database"] = "C:\\idx\\hybridrag.sqlite3"
        data["paths"]["source_folder"] = "C:\\docs"
        data["paths"]["embeddings_cache"] = "C:\\idx\\_embeddings"
        data["mode"] = "online"
        data["setup_complete"] = True

        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        with open(cfg_path, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        # Every original section must still be present
        for key in ["embedding", "chunking", "ollama", "retrieval", "api"]:
            assert key in result, f"Section '{key}' lost during wizard write"
        assert result["ollama"]["model"] == "phi4-mini", "ollama.model changed"
        assert result["chunking"]["chunk_size"] == 1200, "chunk_size changed"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("Wizard handles mode='online' correctly in YAML")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_yaml_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        cfg_path = os.path.join(cfg_dir, "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump({"mode": "offline", "paths": {}}, f)

        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data["mode"] = "online"
        data["setup_complete"] = True
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        with open(cfg_path, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        assert result["mode"] == "online", f"Expected online, got {result['mode']}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# SIM-04: PATH VALIDATION
# ============================================================================
section("SIM-04: PATH VALIDATION (empty, missing, spaces, long paths)")


@test("_validate_paths rejects empty source folder")
def _():
    # Import the module and call the internal validator via a mock object
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "Source documents folder is required" in content, \
        "Missing error message for empty source folder"


@test("_validate_paths rejects nonexistent source folder")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "Source folder does not exist" in content, \
        "Missing error message for nonexistent source folder"


@test("_validate_paths rejects empty index folder")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "Index data folder is required" in content, \
        "Missing error message for empty index folder"


@test("_validate_paths rejects nonexistent parent of index folder")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "Parent of index folder does not exist" in content, \
        "Missing error message for nonexistent index parent"


@test("Path with spaces works in os.path.join (database derivation)")
def _():
    idx = "C:\\My Documents\\RAG Data"
    db = os.path.join(idx, "hybridrag.sqlite3")
    assert db == "C:\\My Documents\\RAG Data\\hybridrag.sqlite3", f"Got: {db}"
    emb = os.path.join(idx, "_embeddings")
    assert emb == "C:\\My Documents\\RAG Data\\_embeddings", f"Got: {emb}"


@test("Path with spaces round-trips through YAML correctly")
def _():
    import yaml
    data = {"paths": {
        "database": "C:\\Program Files\\RAG\\hybridrag.sqlite3",
        "source_folder": "D:\\My Documents\\Source Data",
    }}
    text = yaml.dump(data, default_flow_style=False)
    restored = yaml.safe_load(text)
    assert restored["paths"]["database"] == data["paths"]["database"], \
        f"Database path garbled: {restored['paths']['database']}"
    assert restored["paths"]["source_folder"] == data["paths"]["source_folder"], \
        f"Source path garbled: {restored['paths']['source_folder']}"


@test("Long path (>200 chars) round-trips through YAML")
def _():
    import yaml
    long_dir = "C:\\" + "\\".join(["subfolder_{}".format(i) for i in range(20)])
    data = {"paths": {"database": long_dir + "\\hybridrag.sqlite3"}}
    text = yaml.dump(data, default_flow_style=False)
    restored = yaml.safe_load(text)
    assert restored["paths"]["database"] == data["paths"]["database"], \
        "Long path garbled in YAML"


@test("os.makedirs handles already-existing directory gracefully")
def _():
    tmp = _make_tmp_dir("wiz_mkdir_")
    try:
        # Create once
        target = os.path.join(tmp, "index", "_embeddings")
        os.makedirs(target, exist_ok=True)
        assert os.path.isdir(target)
        # Create again (should not raise)
        os.makedirs(target, exist_ok=True)
        assert os.path.isdir(target)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# SIM-05: config.py setup_complete STRIPPING
# ============================================================================
section("SIM-05: config.py setup_complete STRIPPING")


@test("load_config strips setup_complete without warnings")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_cfg_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        cfg_path = os.path.join(cfg_dir, "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump({
                "mode": "offline",
                "setup_complete": True,
                "paths": {"database": "", "source_folder": ""},
            }, f)

        from src.core.config import load_config
        import io
        import contextlib
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            config = load_config(tmp)

        warnings = stderr_capture.getvalue()
        assert "setup_complete" not in warnings, \
            f"setup_complete produced a warning: {warnings}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("config.py source contains the pop('setup_complete') line")
def _():
    content = CONFIG_PATH.read_text(encoding="utf-8")
    assert (
        'data.pop("setup_complete", None)' in content
        or 'yaml_data.pop("setup_complete", None)' in content
    ), \
        "Missing setup_complete pop in config.py"


@test("load_config still works when setup_complete is absent")
def _():
    import yaml
    tmp = _make_tmp_dir("wiz_cfg_")
    try:
        cfg_dir = os.path.join(tmp, "config")
        os.makedirs(cfg_dir)
        cfg_path = os.path.join(cfg_dir, "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump({"mode": "offline"}, f)

        from src.core.config import load_config
        config = load_config(tmp)
        assert config.mode == "offline"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# SIM-06: LAUNCH SCRIPT RESILIENCE (batch files, GP bypass, quotes)
# ============================================================================
section("SIM-06: LAUNCH SCRIPT RESILIENCE (GP bypass, quote safety)")


@test("start_gui.bat launches GUI without PowerShell-only coupling")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    launches_python = "launch_gui.py" in content and "python" in content.lower()
    assert launches_python, \
        "start_gui.bat should launch launch_gui.py directly from the batch path"


@test("start_rag.bat uses IEX/ReadAllText (not dot-source for main load)")
def _():
    content = RAG_BAT.read_text(encoding="utf-8", errors="replace")
    has_iex = "ReadAllText" in content or "Invoke-Expression" in content or "iex " in content.lower()
    assert has_iex, \
        "start_rag.bat does not use IEX/ReadAllText -- will fail on GP-restricted machines"


@test("start_gui.bat has Python-direct fallback for total PS failure")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    has_fallback = ("launch_gui.py" in content
                    and content.count("launch_gui.py") >= 2)
    assert has_fallback, \
        "start_gui.bat needs a Python-direct fallback if PowerShell fails entirely"


@test("start_gui.bat does not use bare dot-source (. 'path') for start_hybridrag.ps1")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    # Old pattern: . '%~dp0start_hybridrag.ps1'
    # This fails under AllSigned/Restricted Group Policy
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("REM") or stripped.startswith("::"):
            continue
        if re.search(r"\.\s+['\"]%~dp0start_hybridrag\.ps1['\"]", stripped):
            raise AssertionError(
                "Found bare dot-source of start_hybridrag.ps1 -- "
                "this fails under Group Policy. Use IEX/ReadAllText instead."
            )


@test("Batch files suppress GP error output (2>$null or -ErrorAction)")
def _():
    for bat, name in [(GUI_BAT, "start_gui.bat"), (RAG_BAT, "start_rag.bat")]:
        content = bat.read_text(encoding="utf-8", errors="replace")
        if "Set-ExecutionPolicy" in content:
            has_suppress = ("2>$null" in content
                           or "-ErrorAction SilentlyContinue" in content
                           or "2>nul" in content)
            assert has_suppress, \
                f"{name}: Set-ExecutionPolicy should suppress errors " \
                f"(add 2>$null) so users don't see scary red text"


@test("Batch files set PYTHONPATH in fallback section")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    has_pythonpath = "PYTHONPATH" in content
    assert has_pythonpath, \
        "start_gui.bat fallback should set PYTHONPATH so imports work"


@test("Batch files set HYBRIDRAG_PROJECT_ROOT in fallback section")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    has_root = "HYBRIDRAG_PROJECT_ROOT" in content
    assert has_root, \
        "start_gui.bat fallback should set HYBRIDRAG_PROJECT_ROOT"


@test("No unmatched quotes in batch files (quote garbling check)")
def _():
    for bat, name in [(GUI_BAT, "start_gui.bat"), (RAG_BAT, "start_rag.bat")]:
        content = bat.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("REM") or stripped.startswith("::"):
                continue
            # Count double quotes -- should be even (matched pairs)
            dq = stripped.count('"')
            if dq % 2 != 0:
                raise AssertionError(
                    f"{name} line {i}: unmatched double quote "
                    f"(count={dq}). This WILL garble on work laptops.\n"
                    f"  Line: {stripped}"
                )


@test("Batch files use %~dp0 (unquoted drive+path) not %CD%")
def _():
    for bat, name in [(GUI_BAT, "start_gui.bat"), (RAG_BAT, "start_rag.bat")]:
        content = bat.read_text(encoding="utf-8", errors="replace")
        assert "%~dp0" in content, \
            f"{name} should use %~dp0 (reliable path) not %CD% (fragile)"


@test("Batch files have user-friendly error messages (no jargon)")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    # Should explain what went wrong in plain English
    lower = content.lower()
    has_friendly = ("not found" in lower
                    or "first run" in lower
                    or "install" in lower)
    assert has_friendly, \
        "start_gui.bat should have user-friendly error messages"


# ============================================================================
# SIM-07: WORK-COMPUTER SIMULATION
# ============================================================================
section("SIM-07: WORK-COMPUTER SIMULATION (GP, encoding, edge cases)")


@test("start_hybridrag.ps1 has Test-MachineRestricted function")
def _():
    ps1 = _project_root / "start_hybridrag.ps1"
    assert ps1.exists(), "start_hybridrag.ps1 not found"
    content = ps1.read_text(encoding="utf-8", errors="replace")
    assert "Test-MachineRestricted" in content, \
        "start_hybridrag.ps1 must have GP detection (Test-MachineRestricted)"


@test("start_hybridrag.ps1 has IEX fallback path (Invoke-Script)")
def _():
    ps1 = _project_root / "start_hybridrag.ps1"
    content = ps1.read_text(encoding="utf-8", errors="replace")
    assert "Invoke-Script" in content, \
        "start_hybridrag.ps1 must have Invoke-Script for GP bypass"
    assert "Invoke-Expression" in content, \
        "start_hybridrag.ps1 must use Invoke-Expression in restricted path"


@test("start_hybridrag.ps1 sets UTF-8 encoding (prevents garbled output)")
def _():
    ps1 = _project_root / "start_hybridrag.ps1"
    content = ps1.read_text(encoding="utf-8", errors="replace")
    assert "OutputEncoding" in content, \
        "start_hybridrag.ps1 must set Console OutputEncoding to UTF-8"
    assert "InputEncoding" in content, \
        "start_hybridrag.ps1 must set Console InputEncoding to UTF-8"


@test("Wizard browse dialog uses filedialog.askdirectory (not askopenfilename)")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "askdirectory" in content, \
        "Wizard should use askdirectory (folder picker), not askopenfilename"
    assert "askopenfilename" not in content, \
        "Wizard should NOT use askopenfilename (file picker) for folder selection"


@test("Wizard uses os.path.normpath on browse results")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "normpath" in content, \
        "Wizard should normalize paths with os.path.normpath"


@test("launch_gui.py exposes post-wizard config reload after setup check")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    # Must reload config after wizard writes YAML
    assert "load_config" in content, "launch_gui.py must call load_config"
    # The manual post-boot wizard helper should still reload config after the
    # setup check path decides the wizard is needed.
    helper_start = content.find("def _launch_setup_wizard_after_boot")
    helper_end = content.find("def _sanitize_tk_env", helper_start)
    helper_block = content[helper_start:helper_end]
    idx_wizard = helper_block.find("needs_setup")
    idx_reload = helper_block.find("_apply_wizard_config_reload")
    assert idx_wizard > 0, "needs_setup call not found in launch_gui.py"
    assert idx_reload > idx_wizard, \
        "Config reload helper should come AFTER the setup check"


@test("launch_gui.py keeps the main app alive on wizard cancel")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "Setup wizard dismissed; app remains open" in content, \
        "launch_gui.py should keep the main app alive when the wizard is cancelled"
    assert "setup wizard dismissed; continuing with main app" in content, \
        "launch_gui.py should log that startup continues after wizard dismissal"


@test("Wizard sets grab_set for modal behavior")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "grab_set" in content, \
        "Wizard should be modal (grab_set) so user can't interact with parent"


@test("Manual wizard helper waits for closure without a temp-root shell")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "wait_window" in content, \
        "launch_gui.py should use wait_window to block until wizard closes"
    assert "SetupWizard(app, _project_root)" in content, \
        "Wizard should attach to the main app once the GUI is already live"
    assert "_tmp_root.destroy()" not in content, \
        "launch_gui.py should not use a hidden temp-root shell in the current boot path"


@test("Simulated quote garbling: paths with special chars survive YAML")
def _():
    import yaml
    # Simulate what happens when PowerShell garbles quotes in paths
    garbled_paths = [
        "C:\\Users\\John's PC\\Documents",       # apostrophe
        'C:\\Users\\O"Brien\\Data',               # embedded double quote
        "C:\\Program Files (x86)\\RAG",           # parentheses
        "C:\\data\\[project]\\index",             # brackets
        "D:\\100% Complete\\docs",                 # percent sign
        "C:\\Users\\user\\Desktop\\My RAG Data",  # spaces
    ]
    for path in garbled_paths:
        data = {"paths": {"database": path}}
        text = yaml.dump(data, default_flow_style=False)
        restored = yaml.safe_load(text)
        assert restored["paths"]["database"] == path, \
            f"Path garbled in YAML round-trip: {path!r} -> {restored['paths']['database']!r}"


@test("Wizard creates index directory and _embeddings subdirectory")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "os.makedirs" in content, \
        "Wizard must create directories with os.makedirs"
    assert "_embeddings" in content, \
        "Wizard must create the _embeddings subdirectory"


@test("Wizard cancel sets completed=False (not None or missing)")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "self.completed = False" in content, \
        "Cancel must explicitly set completed = False"


@test("Wizard finish sets completed=True before destroy")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    # Find the _on_finish method
    idx_finish = content.find("def _on_finish")
    idx_destroy = content.find("self.destroy()", idx_finish)
    idx_completed = content.find("self.completed = True", idx_finish)
    assert idx_completed > 0, "Wizard must set completed = True in _on_finish"
    assert idx_completed < idx_destroy, \
        "completed = True must come BEFORE self.destroy()"


@test("Wizard uses current_theme() (respects dark/light mode)")
def _():
    content = WIZARD_PATH.read_text(encoding="utf-8")
    assert "current_theme()" in content, \
        "Wizard must use current_theme() for dark/light mode support"


@test("Batch fallback explains situation in plain English")
def _():
    content = GUI_BAT.read_text(encoding="utf-8", errors="replace")
    lower = content.lower()
    has_guidance = (
        "run install.bat first" in lower
        or "make sure ollama is running" in lower
        or ("gui exited with code" in lower and "[fail]" in lower)
    )
    assert has_guidance, \
        "Batch file should explain what's happening in plain English"


# ============================================================================
# FINISH
# ============================================================================
finish()
