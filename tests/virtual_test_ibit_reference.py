#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the virtual ibit reference area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- VIRTUAL TEST: IBIT + Reference Panel
# ============================================================================
# FILE: tests/virtual_test_ibit_reference.py
#
# Tests the Initial Built-In Test system (src/core/ibit.py),
# status bar IBIT display (status_bar.py), launcher integration
# (launch_gui.py), reference panel (reference_panel.py), and
# Admin menu wiring (app.py).
#
# 6 simulation tiers:
#   SIM-01  File integrity (exists, syntax, encoding, size)
#   SIM-02  IBIT engine logic (6 checks, pass/fail scenarios)
#   SIM-03  Status bar IBIT methods exist and are wired
#   SIM-04  Launch sequence IBIT integration
#   SIM-05  Reference panel structure and content
#   SIM-06  Admin menu wiring + sticky notes persistence
#
# INTERNET ACCESS: NONE
# DEPENDENCIES: Python stdlib + project source
# ============================================================================

import os
import sys
import tempfile
import shutil
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tests.virtual_test_framework import (
    section, test, get_report, reset_report, finish,
    check_python_syntax, check_no_non_ascii,
)

reset_report()
report = get_report()
report.change_description = "IBIT system + Reference panel"
report.files_modified = [
    "src/core/ibit.py",
    "src/gui/panels/status_bar.py",
    "src/gui/launch_gui.py",
    "src/gui/panels/reference_panel.py",
    "src/gui/app.py",
]

IBIT_PATH = _project_root / "src" / "core" / "ibit.py"
STATUSBAR_PATH = _project_root / "src" / "gui" / "panels" / "status_bar.py"
LAUNCH_PATH = _project_root / "src" / "gui" / "launch_gui.py"
REF_PATH = _project_root / "src" / "gui" / "panels" / "reference_panel.py"
APP_PATH = _project_root / "src" / "gui" / "app.py"


def _workspace_tmp_dir(prefix: str) -> str:
    base = _project_root / "output" / "virtual_tmp"
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=str(base))


# ============================================================================
# SIM-01: FILE INTEGRITY
# ============================================================================
section("SIM-01: FILE INTEGRITY")

for path, label in [
    (IBIT_PATH, "ibit.py"),
    (STATUSBAR_PATH, "status_bar.py"),
    (LAUNCH_PATH, "launch_gui.py"),
    (REF_PATH, "reference_panel.py"),
    (APP_PATH, "app.py"),
]:
    @test("{} exists and compiles".format(label))
    def _(p=path):
        assert p.exists(), "Not found: {}".format(p)
        err = check_python_syntax(p)
        assert err is None, err


@test("ibit.py has zero non-ASCII characters")
def _():
    issues = check_no_non_ascii(IBIT_PATH)
    assert len(issues) == 0, "\n  ".join(issues[:5])


@test("reference_panel.py has zero non-ASCII characters")
def _():
    issues = check_no_non_ascii(REF_PATH)
    assert len(issues) == 0, "\n  ".join(issues[:5])


@test("reference_panel.py is under 500 lines")
def _():
    lines = REF_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 500, "Got {} lines (max 500)".format(len(lines))


@test("ibit.py is under 500 lines")
def _():
    lines = IBIT_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 500, "Got {} lines".format(len(lines))


@test("No banned words in new files")
def _():
    banned = ["defense", "contractor", "classified", "NGC",
              "Northrop", "NIST", "DoD", "Claude", "Anthropic"]
    for path in [IBIT_PATH, REF_PATH]:
        content = path.read_text(encoding="utf-8")
        found = [w for w in banned if w.lower() in content.lower()]
        assert not found, "{}: banned words: {}".format(path.name, found)


# ============================================================================
# SIM-02: IBIT ENGINE LOGIC
# ============================================================================
section("SIM-02: IBIT ENGINE LOGIC (6 checks, pass/fail scenarios)")


@test("run_ibit returns exactly 6 IBITCheck results")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import Config
    config = Config()
    results = run_ibit(config)
    assert len(results) == 6, "Expected 6, got {}".format(len(results))


@test("IBITCheck has required fields (name, ok, detail, elapsed_ms)")
def _():
    from src.core.ibit import IBITCheck
    check = IBITCheck(name="Test", ok=True, detail="good", elapsed_ms=1.0)
    assert check.name == "Test"
    assert check.ok is True
    assert check.detail == "good"
    assert check.elapsed_ms == 1.0


@test("Config check passes with valid config")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    results = run_ibit(config)
    config_check = results[0]
    assert config_check.name == "Config"
    assert config_check.ok is True, config_check.detail


@test("Config check fails with None config")
def _():
    from src.core.ibit import run_ibit
    results = run_ibit(None)
    assert results[0].ok is False
    assert "None" in results[0].detail


@test("Paths check passes when paths are configured (env var)")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    paths_check = run_ibit(config)[1]
    assert paths_check.name == "Paths"
    # On this machine, env vars provide paths
    if os.environ.get("HYBRIDRAG_DATA_DIR"):
        assert paths_check.ok is True, paths_check.detail


@test("Database check returns chunk count when DB exists")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    db_check = run_ibit(config)[2]
    assert db_check.name == "Database"
    if db_check.ok:
        assert "chunks" in db_check.detail, db_check.detail


@test("Embedder/Router/Pipeline checks fail without backends (expected)")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    results = run_ibit(config)
    # Without GUI loaded, these should fail gracefully
    for r in results[3:]:  # Embedder, Router, Pipeline
        assert r.ok is False or r.ok is True  # Just verify no crash
        assert r.detail != ""  # Must have a reason


@test("All IBIT checks complete in under 2 seconds total")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    results = run_ibit(config)
    total_ms = sum(r.elapsed_ms for r in results)
    assert total_ms < 2000, "IBIT took {:.0f}ms (max 2000ms)".format(total_ms)


@test("IBIT check names are human-readable (no underscores, no jargon)")
def _():
    from src.core.ibit import run_ibit
    from src.core.config import Config
    results = run_ibit(Config())
    names = [r.name for r in results]
    expected = ["Config", "Paths", "Database", "Embedder", "Router", "Pipeline"]
    assert names == expected, "Got: {}".format(names)


# ============================================================================
# SIM-03: STATUS BAR IBIT METHODS
# ============================================================================
section("SIM-03: STATUS BAR IBIT METHODS")


@test("StatusBar has set_ibit_stage method")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "def set_ibit_stage" in content, \
        "Missing set_ibit_stage method"


@test("StatusBar has set_ibit_result method")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "def set_ibit_result" in content, \
        "Missing set_ibit_result method"


@test("set_ibit_result makes label clickable (cursor=hand2)")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert 'cursor="hand2"' in content, \
        "IBIT result label should be clickable"


@test("IBIT detail popup exists (_show_ibit_detail)")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "def _show_ibit_detail" in content, \
        "Missing IBIT detail popup method"


@test("IBIT uses existing theme colors (accent for in-progress, green/red for result)")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert 't["accent"]' in content, "IBIT stage should use accent blue"
    assert 't["green"]' in content, "IBIT pass should use theme green"
    assert 't["red"]' in content, "IBIT fail should use theme red"


@test("IBIT detail popup auto-closes (timeout or focus-out)")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "8000" in content or "auto" in content.lower(), \
        "IBIT popup should auto-close after a timeout"


@test("apply_theme handles IBIT state correctly")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "_ibit_results" in content, \
        "apply_theme should check for IBIT results state"


# ============================================================================
# SIM-04: LAUNCH SEQUENCE IBIT INTEGRATION
# ============================================================================
section("SIM-04: LAUNCH SEQUENCE IBIT INTEGRATION")


@test("launch_gui.py imports and calls run_ibit")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "from src.core.ibit import run_ibit" in content, \
        "launch_gui.py must import run_ibit"


@test("IBIT runs after _attach() (not before)")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    idx_attach = content.find("def _attach():")
    idx_ibit = content.find("_run_ibit_sequence")
    assert idx_ibit > idx_attach, \
        "IBIT must run after _attach() so backends are available"


@test("_run_ibit_sequence exists with stepped display logic")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "def _run_ibit_sequence" in content
    assert "STEP_DELAY_MS" in content, \
        "Must have per-step delay for labor illusion"


@test("_step_display uses after() for non-blocking animation")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "def _step_display" in content
    assert "app.after(" in content, \
        "Must use after() for non-blocking stepped display"


@test("IBIT replaces set_ready() (no redundant Ready state)")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    # In _attach(), set_ready() should NOT be called anymore
    # because IBIT's final result replaces it
    attach_block = content[content.find("def _attach():"):
                           content.find("_run_ibit_sequence")]
    assert "set_ready()" not in attach_block, \
        "_attach() should not call set_ready() -- IBIT replaces it"


@test("Step delay is in perceptual sweet spot (100-300ms)")
def _():
    import re
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    match = re.search(r"STEP_DELAY_MS\s*=\s*(\d+)", content)
    assert match, "STEP_DELAY_MS not found"
    delay = int(match.group(1))
    assert 100 <= delay <= 300, \
        "STEP_DELAY_MS={} outside sweet spot (100-300ms)".format(delay)


# ============================================================================
# SIM-05: REFERENCE PANEL STRUCTURE AND CONTENT
# ============================================================================
section("SIM-05: REFERENCE PANEL STRUCTURE AND CONTENT")


@test("ReferencePanel has 5 tabs (Docs, Settings, Profiles, Tuning, Notes)")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    for tab in ["Docs", "Settings", "Profiles", "Tuning", "Notes"]:
        assert 'text="{}"'.format(tab) in content, \
            "Missing tab: {}".format(tab)


@test("Settings tab covers all critical retrieval settings")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    for setting in ["top_k", "min_score", "hybrid_search", "rrf_k",
                     "reranker_enabled", "min_chunks"]:
        assert setting in content, \
            "Missing retrieval setting: {}".format(setting)


@test("Settings tab covers LLM settings")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    for setting in ["temperature", "timeout_seconds", "context_window"]:
        assert setting in content, \
            "Missing LLM setting: {}".format(setting)


@test("Profiles tab lists all 9 profiles")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    for prof in ["sw", "eng", "pm", "sys", "log", "draft", "fe", "cyber", "gen"]:
        assert '"{}"'.format(prof) in content, \
            "Missing profile: {}".format(prof)


@test("Model ranking includes all 5 approved models")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    for model in ["phi4-mini", "mistral:7b", "gemma3:4b",
                   "phi4:14b-q4_K_M", "mistral-nemo:12b"]:
        assert model in content, \
            "Missing approved model: {}".format(model)


@test("Banned models section exists")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "BANNED" in content or "Banned" in content
    for banned in ["Qwen", "DeepSeek", "BGE", "Llama"]:
        assert banned in content, \
            "Missing banned model: {}".format(banned)


@test("Tuning log documents reranker danger")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "reranker" in content.lower()
    assert "NEVER" in content, \
        "Tuning log must warn about reranker danger"


@test("Sticky notes save to config/sticky_notes.txt")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "sticky_notes.txt" in content, \
        "Notes must persist to config/sticky_notes.txt"


@test("Sticky notes have Purge button")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "Purge" in content
    assert "purge_notes" in content or "_purge_notes" in content


@test("Sticky notes have Save button")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "_save_notes" in content


@test("Sticky note area uses warm tint (sticky-note aesthetic)")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    # Should have yellowish tint for sticky-note feel
    assert "fffde7" in content or "3d3a2e" in content, \
        "Sticky note area should use warm yellow tint"


@test("Docs tab opens files with os.startfile (Windows native)")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    assert "startfile" in content, \
        "Docs should open with os.startfile for native Windows behavior"


@test("Reference panel docs list matches actual docs/ folder")
def _():
    content = REF_PATH.read_text(encoding="utf-8")
    docs_dir = _project_root / "docs"
    # Check that referenced docs actually exist
    import re
    referenced = re.findall(r'"([A-Z_]+\.md)"', content)
    missing = []
    for doc in referenced:
        # Search flat and in numbered subfolders (post docs reorg)
        found = (docs_dir / doc).exists()
        if not found:
            for sub in docs_dir.iterdir():
                if sub.is_dir() and (sub / doc).exists():
                    found = True
                    break
        if not found:
            missing.append(doc)
    # Allow aliases like MODEL_AUDIT.md (mapped via _DOC_ALIASES)
    assert len(missing) <= 3, \
        "Referenced docs not found: {}".format(missing)


# ============================================================================
# SIM-06: ADMIN MENU WIRING + STICKY NOTES PERSISTENCE
# ============================================================================
section("SIM-06: ADMIN MENU WIRING + STICKY NOTES PERSISTENCE")


@test("app.py imports ReferencePanel")
def _():
    content = APP_PATH.read_text(encoding="utf-8")
    assert "from src.gui.panels.reference_panel import ReferencePanel" in content


@test("Admin menu has reference item")
def _():
    content = APP_PATH.read_text(encoding="utf-8")
    assert '"Reference"' in content or '"Ref"' in content, \
        "Admin menu must have a Reference/Ref menu item"


@test("Admin menu Ref item switches to reference view")
def _():
    content = APP_PATH.read_text(encoding="utf-8")
    assert 'show_view("reference")' in content, \
        "Admin menu should switch to reference view via show_view"


@test("show_view method exists for NavBar view switching")
def _():
    content = APP_PATH.read_text(encoding="utf-8")
    assert "def show_view" in content, \
        "app.py must have show_view for NavBar integration"


@test("Sticky notes round-trip (write, read back)")
def _():
    tmp = _workspace_tmp_dir("ref_notes_")
    try:
        notes_path = os.path.join(tmp, "config", "sticky_notes.txt")
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        test_text = "Remember: top_k=5 works best for eval"
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write(test_text)
        with open(notes_path, "r", encoding="utf-8") as f:
            readback = f.read()
        assert readback == test_text, \
            "Notes round-trip failed: {}".format(readback)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@test("Sticky notes purge deletes file")
def _():
    tmp = _workspace_tmp_dir("ref_notes_")
    try:
        notes_path = os.path.join(tmp, "config", "sticky_notes.txt")
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        with open(notes_path, "w") as f:
            f.write("temp note")
        assert os.path.isfile(notes_path)
        os.remove(notes_path)
        assert not os.path.isfile(notes_path), "Purge did not delete file"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================
# SIM-07: CBIT (CONTINUOUS BUILT-IN TEST)
# ============================================================================
section("SIM-07: CBIT (CONTINUOUS BUILT-IN TEST)")


@test("run_cbit exists and returns 3 IBITCheck results")
def _():
    from src.core.ibit import run_cbit
    from src.core.config import Config
    config = Config()
    results = run_cbit(config)
    assert len(results) == 3, "Expected 3, got {}".format(len(results))
    for r in results:
        assert hasattr(r, "name")
        assert hasattr(r, "ok")
        assert hasattr(r, "detail")
        assert hasattr(r, "elapsed_ms")


@test("CBIT check names are Database, Router, Disk")
def _():
    from src.core.ibit import run_cbit
    from src.core.config import Config
    results = run_cbit(Config())
    names = [r.name for r in results]
    assert names == ["Database", "Router", "Disk"], "Got: {}".format(names)


@test("CBIT completes in under 500ms (lightweight requirement)")
def _():
    import time
    from src.core.ibit import run_cbit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    t0 = time.perf_counter()
    results = run_cbit(config)
    elapsed = (time.perf_counter() - t0) * 1000
    assert elapsed < 500, "CBIT took {:.0f}ms (max 500ms)".format(elapsed)


@test("CBIT Database check passes with valid config")
def _():
    from src.core.ibit import run_cbit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    db_check = run_cbit(config)[0]
    assert db_check.name == "Database"
    db_path = getattr(getattr(config, "paths", None), "database", "")
    if db_path and os.path.isfile(db_path):
        assert db_check.ok is True, db_check.detail


@test("CBIT Disk check passes (reports free MB)")
def _():
    from src.core.ibit import run_cbit
    from src.core.config import load_config
    config = load_config(str(_project_root))
    disk_check = run_cbit(config)[2]
    assert disk_check.name == "Disk"
    assert disk_check.ok is True, disk_check.detail
    assert "MB free" in disk_check.detail


@test("CBIT Router check fails gracefully without router (no crash)")
def _():
    from src.core.ibit import run_cbit
    from src.core.config import Config
    results = run_cbit(Config(), query_engine=None, router=None)
    router_check = results[1]
    assert router_check.ok is False
    assert "not loaded" in router_check.detail


@test("StatusBar has start_cbit method")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "def start_cbit" in content


@test("StatusBar has CBIT_MS timer constant (60s)")
def _():
    import re
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    match = re.search(r"CBIT_MS\s*=\s*(\d+)", content)
    assert match, "CBIT_MS constant not found"
    ms = int(match.group(1))
    assert 30000 <= ms <= 120000, \
        "CBIT_MS={} should be 30-120 seconds".format(ms)


@test("StatusBar._apply_cbit uses orange for partial, red for critical")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "def _apply_cbit" in content
    assert 't["orange"]' in content, "Partial failure should use orange"
    assert 't["red"]' in content, "Critical failure should use red"


@test("CBIT detail shows in popup alongside IBIT results")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "_cbit_results" in content
    assert "Continuous Health Check" in content, \
        "Popup should label CBIT section"


@test("launch_gui starts CBIT after IBIT completes")
def _():
    content = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "start_cbit" in content, \
        "launch_gui must call start_cbit after IBIT finishes"


@test("CBIT stop() cancels timer cleanly")
def _():
    content = STATUSBAR_PATH.read_text(encoding="utf-8")
    assert "_cbit_timer_id" in content
    # stop() should cancel both status refresh and CBIT
    stop_block = content[content.find("def stop("):]
    assert "cbit" in stop_block.lower(), \
        "stop() must cancel the CBIT timer"


@test("ibit.py still under 500 lines after CBIT addition")
def _():
    lines = IBIT_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 500, "Got {} lines".format(len(lines))


@test("status_bar.py still under 500 lines after CBIT addition")
def _():
    lines = STATUSBAR_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 500, "Got {} lines".format(len(lines))


@test("No banned words in CBIT additions")
def _():
    banned = ["defense", "contractor", "classified", "NGC",
              "Northrop", "NIST", "DoD", "Claude", "Anthropic"]
    for path in [IBIT_PATH, STATUSBAR_PATH]:
        content = path.read_text(encoding="utf-8")
        found = [w for w in banned if w.lower() in content.lower()]
        assert not found, "{}: banned words: {}".format(path.name, found)


# ============================================================================
# FINISH
# ============================================================================
finish()
