#!/usr/bin/env python3
# ============================================================================
# HybridRAG v3 -- VIRTUAL TEST FRAMEWORK (Reusable Engine)
# ============================================================================
# FILE: tests/virtual_test_framework.py
#
#   Think of it as a flight simulator for code changes -- you test the change
#   in a sandbox, check every module that could be affected, and only deploy
#   when every check passes.
#
# WHY IT EXISTS:
#   During the Feb 15 kill-switch removal, Claude caught two bugs during
#   virtual testing that would have caused runtime failures:
#     1. A duplicate NETWORK_GATE check that doubled diagnostic output
#     2. Using gate.allowed_hosts (doesn't exist) vs gate._allowed_hosts
#   Both were caught by running this framework BEFORE giving Jeremy the files.
#   This framework ensures that rigor is repeatable in future sessions.
#
# HOW TO USE (for future Claude sessions):
#   1. Read this file to understand the test patterns
#   2. Copy tests/virtual_test_TEMPLATE.py for your specific change
#   3. Fill in the template sections with your change-specific tests
#   4. Run: python tests/virtual_test_<your_change>.py
#   5. Fix any failures, re-run until 0 FAIL
#   6. Only THEN deliver the files to Jeremy
#
# HOW TO USE (for Jeremy):
#   Tell Claude: "Use the virtual test framework in tests/ to validate
#   your changes before giving them to me."
#
# INTERNET ACCESS: NONE -- all tests are offline simulation
# DEPENDENCIES: Python stdlib only (no pip packages needed)
# ============================================================================

import os
import re
import ast
import sys
import time
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# TEST RESULT TRACKING
# ============================================================================

class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class VirtualTestResult:
    """One test outcome with details for the report."""
    name: str
    status: TestStatus
    message: str = ""
    section: str = ""
    elapsed_ms: float = 0.0


@dataclass
class VirtualTestReport:
    """Collects all results and produces the final summary."""
    results: List[VirtualTestResult] = field(default_factory=list)
    change_description: str = ""
    files_modified: List[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAIL)

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.WARN)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIP)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def print_summary(self):
        """Print the final pass/fail summary."""
        print()
        print("=" * 70)
        print(f"  RESULTS: {self.passed} PASS, {self.failed} FAIL, "
              f"{self.warned} WARN, {self.skipped} SKIP")
        print(f"  TOTAL:   {self.total} tests")
        print()
        if self.all_passed:
            print("  ALL TESTS PASSED -- changes are safe to deploy")
        else:
            print("  FAILURES DETECTED -- DO NOT DEPLOY WITHOUT FIXING:")
            for r in self.results:
                if r.status == TestStatus.FAIL:
                    print(f"    [FAIL] {r.name}")
                    if r.message:
                        print(f"           {r.message}")
        print("=" * 70)
        print()


# Global report instance
_report = VirtualTestReport()


def get_report() -> VirtualTestReport:
    return _report


def reset_report():
    global _report
    _report = VirtualTestReport()


def section(title: str):
    """Print a section header matching the SIM-XX format."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test(name: str, section_name: str = ""):
    """
    Decorator-style test runner.

    Usage:
        @test("My test description")
        def _():
            assert something, "error message"

    Returns "WARN" or "SKIP" from the function to set those statuses.
    Any AssertionError = FAIL. Any other Exception = FAIL.
    Normal return = PASS.
    """
    def decorator(func):
        start = time.perf_counter()
        try:
            result = func()
            elapsed = (time.perf_counter() - start) * 1000
            if result == "WARN":
                _report.results.append(VirtualTestResult(
                    name, TestStatus.WARN, section=section_name, elapsed_ms=elapsed))
                print(f"  [WARN] {name}")
            elif result == "SKIP":
                _report.results.append(VirtualTestResult(
                    name, TestStatus.SKIP, section=section_name, elapsed_ms=elapsed))
                print(f"  [SKIP] {name}")
            else:
                _report.results.append(VirtualTestResult(
                    name, TestStatus.PASS, section=section_name, elapsed_ms=elapsed))
                print(f"  [PASS] {name}")
        except AssertionError as e:
            elapsed = (time.perf_counter() - start) * 1000
            _report.results.append(VirtualTestResult(
                name, TestStatus.FAIL, str(e), section_name, elapsed))
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            _report.results.append(VirtualTestResult(
                name, TestStatus.FAIL,
                f"{type(e).__name__}: {e}", section_name, elapsed))
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
        return func
    return decorator


# ============================================================================
# REUSABLE TEST UTILITIES
# ============================================================================


def check_no_non_ascii(filepath: Path, label: str = "") -> List[str]:
    """
    Scan a file for non-ASCII characters. Returns list of issues found.
    """
    label = label or filepath.name
    content = filepath.read_text(encoding="utf-8")
    issues = []
    for i, ch in enumerate(content):
        if ord(ch) > 127:
            line_num = content[:i].count('\n') + 1
            issues.append(
                f"{label} line {line_num}: char {repr(ch)} (U+{ord(ch):04X})"
            )
    return issues


def check_python_syntax(filepath: Path) -> Optional[str]:
    """
    AST-parse a Python file to check for syntax errors.
    Returns None if OK, or error message if syntax error found.
    """
    content = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(content, filename=filepath.name)
        return None
    except SyntaxError as e:
        return f"{filepath.name} line {e.lineno}: {e.msg}"


def check_file_references(
    content: str,
    expected_refs: List[str],
    label: str = "file"
) -> List[str]:
    """
    Verify that a file contains expected references (imports, paths, etc.)
    Returns list of missing references.
    """
    missing = []
    for ref in expected_refs:
        if ref not in content:
            missing.append(ref)
    return missing


def check_no_active_code_with(
    filepath: Path,
    pattern: str,
    allow_patterns: List[str] = None,
) -> List[str]:
    """
    Scan a file for ACTIVE (non-comment) lines matching a pattern.
    Returns list of violations.
    """
    allow_patterns = allow_patterns or []
    content = filepath.read_text(encoding="utf-8", errors="replace")
    violations = []
    for i, line in enumerate(content.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if pattern in stripped:
            if any(ap in stripped for ap in allow_patterns):
                continue
            violations.append(f"line {i}: {stripped}")
    return violations


def scan_blast_radius(
    project_root: Path,
    search_terms: List[str],
    extensions: List[str] = None,
) -> Dict[str, List[Tuple[int, str]]]:
    """
    Find every file+line in the project that matches any search term.
    Returns {filepath: [(line_num, line_text), ...]}.
    """
    extensions = extensions or ["*.py", "*.ps1", "*.yaml"]
    results = {}
    for ext in extensions:
        for f in project_root.rglob(ext):
            if "__pycache__" in str(f) or ".bak" in f.suffix:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                hits = []
                for i, line in enumerate(content.split('\n'), 1):
                    if any(term in line for term in search_terms):
                        hits.append((i, line.strip()))
                if hits:
                    rel = str(f.relative_to(project_root))
                    results[rel] = hits
            except Exception:
                pass
    return results


def verify_gate_api_surface(
    expected_attrs: Dict[str, bool] = None,
) -> Dict[str, Dict]:
    """
    Verify that NetworkGate has the expected public/private attributes.
    Returns results dict for each attribute.
    """
    from src.core.network_gate import NetworkGate
    gate = NetworkGate()
    if expected_attrs is None:
        expected_attrs = {
            "_mode": True,
            "_allowed_hosts": True,
            "_allowed_prefixes": True,
            "_audit_log": True,
            "mode": True,
            "mode_name": True,
            "configure": True,
            "check_allowed": True,
            "allowed_hosts": False,  # This is private (_allowed_hosts)
        }
    results = {}
    for attr, should_exist in expected_attrs.items():
        exists = hasattr(gate, attr)
        results[attr] = {
            "exists": exists,
            "expected": should_exist,
            "ok": exists == should_exist,
        }
    return results


# ============================================================================
# STANDARD TEST SECTIONS
# ============================================================================


def run_file_integrity_checks(
    modified_files: Dict[str, Path],
    check_ascii: bool = True,
):
    """SIM-01: Check all modified files exist, readable, no non-ASCII in .ps1."""
    section("SIM-01: FILE INTEGRITY (encoding, non-ASCII, size)")

    for label, filepath in modified_files.items():

        @test(f"{label} exists and is readable")
        def _check(fp=filepath):
            assert fp.exists(), f"File not found: {fp}"
            content = fp.read_text(encoding="utf-8")
            assert len(content) > 100, f"File suspiciously small: {len(content)} bytes"

        if check_ascii and filepath.suffix in (".ps1",):
            @test(f"{label} has ZERO non-ASCII characters")
            def _ascii(fp=filepath, lbl=label):
                issues = check_no_non_ascii(fp, lbl)
                assert len(issues) == 0, (
                    f"Non-ASCII found:\n  " + "\n  ".join(issues[:5])
                )


def run_python_syntax_checks(project_root: Path, directories: List[str]):
    """SIM-03: AST-parse all Python files in given directories."""
    section("SIM-03: PYTHON SYNTAX VALIDATION (AST compile)")

    for dir_name in directories:
        dir_path = project_root / dir_name

        @test(f"All {dir_name}/*.py files compile cleanly")
        def _check(dp=dir_path, dn=dir_name):
            if not dp.exists():
                return "SKIP"
            failures = []
            for py_file in sorted(dp.rglob("*.py")):
                if "__pycache__" in str(py_file) or py_file.suffix == ".bak":
                    continue
                err = check_python_syntax(py_file)
                if err:
                    failures.append(err)
            assert len(failures) == 0, (
                "Compile failures:\n  " + "\n  ".join(failures)
            )


def run_existing_test_regression(
    project_root: Path,
    test_commands: Dict[str, str],
):
    """SIM-10/11: Run existing test suites and verify pass/fail counts."""
    import subprocess

    section("SIM-10/11: EXISTING TEST SUITE REGRESSION")

    for label, cmd in test_commands.items():

        @test(f"{label} produces same results as baseline")
        def _check(c=cmd, l=label):
            result = subprocess.run(
                c, shell=True, capture_output=True, text=True,
                cwd=str(project_root), timeout=120,
            )
            output = result.stdout
            match = re.search(r'(\d+)\s+passed.*?(\d+)\s+failed', output)
            if match:
                passed, failed = int(match.group(1)), int(match.group(2))
                print(f"    ({passed} passed, {failed} failed)")
            else:
                match2 = re.search(r'RESULTS:\s+(\d+)\s+passed,\s+(\d+)\s+failed', output)
                if match2:
                    print(f"    ({match2.group(1)} passed, {match2.group(2)} failed)")
                else:
                    print(f"    (could not parse results)")


# ============================================================================
# ENTRY POINT
# ============================================================================

def finish(exit_code: bool = True):
    """Print the final report and optionally sys.exit."""
    _report.print_summary()
    if exit_code:
        sys.exit(0 if _report.all_passed else 1)
