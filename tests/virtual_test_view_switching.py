#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the virtual view switching area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- VIRTUAL TEST: Single-Window View-Switching GUI     RevA
# ============================================================================
# FILE: tests/virtual_test_view_switching.py
#
# Validates the NavBar + view-switching refactor that converts Toplevel
# windows (Admin Settings, Cost Dashboard, Reference) into embeddable
# Frames switched in-place within the main window.
#
# TEST TIERS:
#   SIM-01: File Integrity (existence, compile, ASCII, LOC)
#   SIM-02: NavBar Structure
#   SIM-03: View Switching Mechanism (app.py)
#   SIM-04: Settings View
#   SIM-05: Cost Dashboard Conversion
#   SIM-06: Reference Panel Conversion
#   SIM-07: Integration + Regression
#   SIM-08: Banned Words + RevA Stamps
#
# INTERNET ACCESS: NONE
# DEPENDENCIES: Python stdlib only
# ============================================================================

import os
import sys
import ast
import re
from pathlib import Path

# Ensure project root on sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tests.virtual_test_framework import (
    section, test, get_report, reset_report, finish,
    check_python_syntax, check_no_non_ascii,
)

reset_report()
report = get_report()
report.change_description = "Single-window view-switching GUI refactor (RevA)"
report.files_modified = [
    "src/gui/panels/nav_bar.py",
    "src/gui/panels/settings_view.py",
    "src/gui/panels/cost_dashboard.py",
    "src/gui/panels/reference_panel.py",
    "src/gui/app.py",
    "src/gui/panels/engineering_menu.py (DELETED)",
]

# Paths
ROOT = _project_root
NAV_BAR = ROOT / "src" / "gui" / "panels" / "nav_bar.py"
SETTINGS_VIEW = ROOT / "src" / "gui" / "panels" / "settings_view.py"
COST_DASHBOARD = ROOT / "src" / "gui" / "panels" / "cost_dashboard.py"
REFERENCE_PANEL = ROOT / "src" / "gui" / "panels" / "reference_panel.py"
APP_PY = ROOT / "src" / "gui" / "app.py"
ENG_MENU = ROOT / "src" / "gui" / "panels" / "engineering_menu.py"
LAUNCH_GUI = ROOT / "src" / "gui" / "launch_gui.py"


def _read(p):
    """Read file content, return empty string if missing."""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _count_code_lines(filepath):
    """Count non-blank, non-comment lines in the class body."""
    content = _read(filepath)
    count = 0
    in_class = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("class ") and ":" in stripped:
            in_class = True
            continue
        if in_class:
            if stripped == "" or stripped.startswith("#"):
                continue
            # Detect if we left the class (new top-level def/class)
            if not line.startswith(" ") and not line.startswith("\t"):
                if stripped.startswith("def ") or stripped.startswith("class "):
                    break
                if stripped and not stripped.startswith("#"):
                    break
            count += 1
    return count


# ============================================================================
# SIM-01: FILE INTEGRITY
# ============================================================================
section("SIM-01: FILE INTEGRITY (existence, compile, ASCII, LOC)")

NEW_FILES = {
    "nav_bar.py": NAV_BAR,
    "settings_view.py": SETTINGS_VIEW,
}
MODIFIED_FILES = {
    "cost_dashboard.py": COST_DASHBOARD,
    "reference_panel.py": REFERENCE_PANEL,
    "app.py": APP_PY,
}
ALL_FILES = {**NEW_FILES, **MODIFIED_FILES}


@test("All new/modified files exist")
def _():
    for label, path in ALL_FILES.items():
        assert path.exists(), "Missing: {}".format(label)


@test("All Python files compile cleanly (AST)")
def _():
    errors = []
    for label, path in ALL_FILES.items():
        err = check_python_syntax(path)
        if err:
            errors.append(err)
    assert not errors, "Compile errors:\n  " + "\n  ".join(errors)


@test("No non-ASCII characters in new/modified files")
def _():
    issues = []
    for label, path in ALL_FILES.items():
        issues.extend(check_no_non_ascii(path, label))
    assert not issues, "Non-ASCII:\n  " + "\n  ".join(issues[:10])


@test("All classes under 500 LOC (code only)")
def _():
    over_limit = []
    for label, path in ALL_FILES.items():
        count = _count_code_lines(path)
        if count > 500:
            over_limit.append("{}: {} lines".format(label, count))
    assert not over_limit, "Over 500 LOC:\n  " + "\n  ".join(over_limit)


@test("engineering_menu.py is DELETED")
def _():
    assert not ENG_MENU.exists(), "engineering_menu.py still exists -- should be deleted"


# ============================================================================
# SIM-02: NAVBAR STRUCTURE
# ============================================================================
section("SIM-02: NAVBAR STRUCTURE")

nav_src = _read(NAV_BAR)


@test("NavBar class exists in nav_bar.py")
def _():
    assert "class NavBar" in nav_src, "class NavBar not found"


@test("NavBar has 4 tabs: Query, Settings, Cost, Ref")
def _():
    for tab_name in ["Query", "Settings", "Cost", "Ref"]:
        assert '"{}"'.format(tab_name) in nav_src, "Tab '{}' not found in TABS".format(tab_name)


@test("NavBar has select() method")
def _():
    assert "def select(" in nav_src, "select() method not found"


@test("NavBar has apply_theme() method")
def _():
    assert "def apply_theme(" in nav_src, "apply_theme() method not found"


@test("NavBar uses accent color for selected tab")
def _():
    assert 'accent' in nav_src, "accent color not referenced"
    assert 'accent_fg' in nav_src, "accent_fg not referenced"


@test("NavBar has separator line")
def _():
    assert "separator" in nav_src, "separator not found -- needs thin line below tabs"


# ============================================================================
# SIM-03: VIEW SWITCHING MECHANISM
# ============================================================================
section("SIM-03: VIEW SWITCHING MECHANISM (app.py)")

app_src = _read(APP_PY)


@test("app.py has show_view() method")
def _():
    assert "def show_view(" in app_src, "show_view() not found"


@test("app.py has _build_content_frame() method")
def _():
    assert "def _build_content_frame(" in app_src, "_build_content_frame() not found"


@test("app.py has _build_view() for lazy construction")
def _():
    assert "def _build_view(" in app_src, "_build_view() not found"


@test("app.py has _build_query_view() for eager build")
def _():
    assert "def _build_query_view(" in app_src, "_build_query_view() not found"


@test("_views dict exists in app.py")
def _():
    assert "_views" in app_src, "_views dict not found"


@test("_current_view tracking exists in app.py")
def _():
    assert "_current_view" in app_src, "_current_view not found"


@test("pack_forget used for view hiding")
def _():
    assert "pack_forget" in app_src, "pack_forget not used for instant view switching"


@test("Admin menu commands call show_view() not _open_*")
def _():
    assert "_open_engineering_menu" not in app_src, "Old _open_engineering_menu still present"
    assert "_open_cost_dashboard" not in app_src, "Old _open_cost_dashboard still present"
    assert "_open_reference" not in app_src, "Old _open_reference still present"
    assert 'show_view("settings")' in app_src, "Menu does not call show_view(settings)"
    assert 'show_view("cost")' in app_src, "Menu does not call show_view(cost)"
    assert 'show_view("reference")' in app_src, "Menu does not call show_view(reference)"


# ============================================================================
# SIM-04: SETTINGS VIEW
# ============================================================================
section("SIM-04: SETTINGS VIEW")

settings_src = _read(SETTINGS_VIEW)


@test("settings_view.py exists and compiles")
def _():
    assert SETTINGS_VIEW.exists(), "File not found"
    err = check_python_syntax(SETTINGS_VIEW)
    assert err is None, err


@test("SettingsView inherits from tk.Frame (not Toplevel)")
def _():
    assert "class SettingsView(tk.Frame)" in settings_src, "Not inheriting from tk.Frame"
    assert "tk.Toplevel" not in settings_src, "Toplevel reference still present"


@test("Has retrieval sliders (top_k, min_score, hybrid, reranker)")
def _():
    for term in ["topk_var", "minscore_var", "hybrid_var", "reranker_var"]:
        assert term in settings_src, "Missing retrieval control: {}".format(term)


@test("Has LLM sliders (max_tokens, temperature, timeout)")
def _():
    for term in ["maxtokens_var", "temp_var", "timeout_var"]:
        assert term in settings_src, "Missing LLM control: {}".format(term)


@test("Has profile section with dropdown and apply button")
def _():
    assert "profile_var" in settings_src, "profile_var not found"
    assert "profile_dropdown" in settings_src, "profile_dropdown not found"
    assert "profile_apply_btn" in settings_src, "profile_apply_btn not found"


@test("Has reset to defaults")
def _():
    assert "_on_reset" in settings_src, "_on_reset method not found"
    assert "Reset to Defaults" in settings_src, "Reset button text not found"


@test("Has apply_theme() method")
def _():
    assert "def apply_theme(" in settings_src, "apply_theme() not found"


@test("Does NOT have test query section")
def _():
    assert "_build_test_section" not in settings_src, "Test section still present"
    assert "test_entry" not in settings_src, "test_entry still present"
    assert "Run Test" not in settings_src, "Run Test button still present"
    assert "ScrolledText" not in settings_src, "ScrolledText (from test section) still present"


# ============================================================================
# SIM-05: COST DASHBOARD CONVERSION
# ============================================================================
section("SIM-05: COST DASHBOARD CONVERSION")

cost_src = _read(COST_DASHBOARD)


@test("CostDashboard inherits from tk.Frame (not Toplevel)")
def _():
    assert "class CostDashboard(tk.Frame)" in cost_src, "Not inheriting from tk.Frame"
    assert "class CostDashboard(tk.Toplevel)" not in cost_src, "Still Toplevel"


@test("No self.title() call")
def _():
    # Should not have self.title("PM Cost Dashboard") or similar
    lines = cost_src.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "self.title(" in stripped:
            assert False, "self.title() found at line {}".format(i)


@test("No self.geometry() call")
def _():
    lines = cost_src.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "self.geometry(" in stripped:
            assert False, "self.geometry() found at line {}".format(i)


@test("Has scrollable canvas wrapper")
def _():
    assert "_canvas" in cost_src, "_canvas not found"
    assert "_scrollbar" in cost_src, "_scrollbar not found"
    assert "_inner" in cost_src, "_inner frame not found"
    assert "scrollregion" in cost_src, "scrollregion config not found"


@test("Has cleanup() method (replaces _on_close)")
def _():
    assert "def cleanup(" in cost_src, "cleanup() method not found"
    assert "remove_listener" in cost_src, "remove_listener not in cleanup"


@test("Has apply_theme() method")
def _():
    assert "def apply_theme(" in cost_src, "apply_theme() not found"


# ============================================================================
# SIM-06: REFERENCE PANEL CONVERSION
# ============================================================================
section("SIM-06: REFERENCE PANEL CONVERSION")

ref_src = _read(REFERENCE_PANEL)


@test("ReferencePanel inherits from tk.Frame (not Toplevel)")
def _():
    assert "class ReferencePanel(tk.Frame)" in ref_src, "Not inheriting from tk.Frame"
    assert "class ReferencePanel(tk.Toplevel)" not in ref_src, "Still Toplevel"


@test("No self.title() call")
def _():
    lines = ref_src.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "self.title(" in stripped:
            assert False, "self.title() found at line {}".format(i)


@test("No self.geometry() call")
def _():
    lines = ref_src.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "self.geometry(" in stripped:
            assert False, "self.geometry() found at line {}".format(i)


@test("Still has 5 tabs (Docs, Settings, Profiles, Tuning, Notes)")
def _():
    for tab_name in ["Docs", "Settings", "Profiles", "Tuning", "Notes"]:
        assert '"{}"'.format(tab_name) in ref_src, "Tab '{}' not found".format(tab_name)


@test("Still has sticky notes persistence")
def _():
    assert "_save_notes" in ref_src, "_save_notes not found"
    assert "_load_notes" in ref_src, "_load_notes not found"
    assert "_purge_notes" in ref_src, "_purge_notes not found"
    assert "sticky_notes.txt" in ref_src, "sticky_notes.txt path not found"


@test("Has apply_theme() method")
def _():
    assert "def apply_theme(" in ref_src, "apply_theme() not found"


# ============================================================================
# SIM-07: INTEGRATION + REGRESSION
# ============================================================================
section("SIM-07: INTEGRATION + REGRESSION")


@test("app.py does NOT import EngineeringMenu")
def _():
    assert "EngineeringMenu" not in app_src, "EngineeringMenu still imported in app.py"
    assert "engineering_menu" not in app_src, "engineering_menu module still referenced"


@test("app.py imports NavBar and SettingsView (or lazy imports)")
def _():
    assert "NavBar" in app_src, "NavBar not referenced in app.py"
    # SettingsView can be lazy-imported inside _build_view
    assert "SettingsView" in app_src, "SettingsView not referenced in app.py"


@test("No Toplevel references for settings/cost/reference in app.py")
def _():
    # Should not have Toplevel in the context of building settings/cost/ref views
    # (CostDashboard and ReferencePanel are imported but are now Frames)
    lines = app_src.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "Toplevel" in stripped:
            assert False, "Toplevel found at line {}: {}".format(i, stripped)


@test("Status bar still packed side=BOTTOM")
def _():
    assert "side=tk.BOTTOM" in app_src, "Status bar not packed BOTTOM"


@test("IBIT/CBIT still wired (launch_gui.py references intact)")
def _():
    launch_src = _read(LAUNCH_GUI)
    assert "_run_ibit_sequence" in launch_src, "IBIT wiring missing from launch_gui.py"
    assert "start_cbit" in launch_src, "CBIT wiring missing from launch_gui.py"


@test("Title bar still has mode toggles and theme button")
def _():
    assert "toggle_mode" in app_src, "toggle_mode not found"
    assert "theme_btn" in app_src, "theme_btn not found"
    assert "_toggle_theme" in app_src, "_toggle_theme not found"


@test("Nav bar theme propagation in _apply_theme_to_all")
def _():
    assert "nav_bar.apply_theme" in app_src, "nav_bar.apply_theme not in _apply_theme_to_all"


@test("Cleanup calls cost dashboard cleanup on close")
def _():
    assert "cleanup" in app_src, "cleanup not called in _on_close"
    # Check that _on_close references cost view cleanup
    on_close_section = app_src[app_src.index("def _on_close"):]
    assert "cost" in on_close_section[:300], "cost view cleanup not in _on_close"


# ============================================================================
# SIM-08: BANNED WORDS + REVA STAMPS
# ============================================================================
section("SIM-08: BANNED WORDS + REVA STAMPS")

# Build banned words carefully to avoid this test file triggering itself
_BANNED = [
    chr(100) + chr(101) + chr(102) + chr(101) + chr(110) + chr(115) + chr(101),  # d-e-f-e-n-s-e
    chr(99) + chr(111) + chr(110) + chr(116) + chr(114) + chr(97) + chr(99) + chr(116) + chr(111) + chr(114),  # c-o-n-t-r-a-c-t-o-r
    chr(99) + chr(108) + chr(97) + chr(115) + chr(115) + chr(105) + chr(102) + chr(105) + chr(101) + chr(100),  # c-l-a-s-s-i-f-i-e-d
    "NGC",
    chr(78) + chr(111) + chr(114) + chr(116) + chr(104) + chr(114) + chr(111) + chr(112),  # N-o-r-t-h-r-o-p
]


@test("No banned words in any new/modified files")
def _():
    violations = []
    for label, path in ALL_FILES.items():
        content = _read(path).lower()
        for word in _BANNED:
            if word.lower() in content:
                violations.append("{}: contains banned word".format(label))
    assert not violations, "\n  ".join(violations)


@test("RevA stamp present in all changed files")
def _():
    missing = []
    for label, path in ALL_FILES.items():
        content = _read(path)
        if "RevA" not in content:
            missing.append(label)
    assert not missing, "Missing RevA stamp: {}".format(", ".join(missing))


@test("nav_bar.py has correct view names matching app.py")
def _():
    # Verify the TABS names in NavBar match what app.py expects
    for name in ["query", "settings", "cost", "reference"]:
        assert '"{}"'.format(name) in nav_src, "View name '{}' missing from NavBar TABS".format(name)
        assert '"{}"'.format(name) in app_src, "View name '{}' missing from app.py".format(name)


@test("No orphan imports (no unused engineering_menu imports anywhere)")
def _():
    # Check all Python files in src/gui/ for engineering_menu references
    gui_dir = ROOT / "src" / "gui"
    violations = []
    for py_file in gui_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="replace")
        if "engineering_menu" in content:
            violations.append(str(py_file.relative_to(ROOT)))
    assert not violations, "engineering_menu still referenced in: {}".format(", ".join(violations))


# ============================================================================
# FINISH
# ============================================================================
finish()
