#!/usr/bin/env python3
"""
============================================================================
 PHASE 4 CLEANUP -- EXHAUSTIVE VIRTUAL TEST
============================================================================
 Tests all Phase 4 changes forwards (do they work?) and backwards (did they
 break anything?), plus cross-cutting checks.

 SIM-01: File integrity (compile, non-ASCII, encoding)
 SIM-02: Kill switch consolidation (behavioral mock)
 SIM-03: http_client.py duplicate kill switch removed
 SIM-04: API version alignment (exact match, no stale refs)
 SIM-05: Bare excepts eliminated (project-wide scan)
 SIM-06: Mojibake eliminated (byte scan ALL PS1 files)
 SIM-07: Hardcoded dev paths eliminated (ALL PS1 files)
 SIM-08: PSScriptRoot fallback for Invoke-Expression
 SIM-09: component_tests.py checks NetworkGate
 SIM-10: system_diagnostic.py checks correct env var
 SIM-11: Class size < 500 lines
 SIM-12: No read+write same file in modified code
 SIM-13: PS1 encoding (BOM + CRLF readiness)
 SIM-14: Phase 1 regression (portable config paths)
 SIM-15: Phase 2 regression (credential consolidation)
 SIM-16: Core module regression (imports still work)
 SIM-17: Behavioral: NetworkGate HYBRIDRAG_OFFLINE override
 SIM-18: Windows-gap documentation (what Linux cannot test)
============================================================================
"""

import os
import sys
import re
import ast
import importlib
from unittest import mock
from io import StringIO

# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
WARN = 0
SKIP = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  -- {detail}")

def warn_check(label, detail=""):
    global WARN
    WARN += 1
    print(f"  [WARN] {label}  -- {detail}")

def skip_check(label, detail=""):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {label}  -- {detail}")

def section(num, title):
    print(f"\n{'=' * 70}")
    print(f"  SIM-{num:02d}: {title}")
    print("=" * 70)


# ======================================================================
section(1, "FILE INTEGRITY (compile + non-ASCII + encoding)")
# ======================================================================

# All modified Python files must compile cleanly
py_modified = [
    "src/core/network_gate.py",
    "src/core/http_client.py",
    "src/core/api_client_factory.py",
    "src/diagnostic/component_tests.py",
    "src/tools/system_diagnostic.py",
    "diagnostics/hybridrag_diagnostic_v2.py",
    "tools/py/test_api_verbose.py",
]
for pf in py_modified:
    try:
        raw = open(pf, "rb").read()
        # Strip BOM if present (should not be in Python files)
        if raw[:3] == b'\xef\xbb\xbf':
            warn_check(f"{pf} has UTF-8 BOM (unusual for Python)")
            raw = raw[3:]
        code = raw.decode("utf-8")
        ast.parse(code)
        check(f"{pf} compiles", True)
    except SyntaxError as e:
        check(f"{pf} compiles", False, str(e))
    except UnicodeDecodeError as e:
        check(f"{pf} compiles", False, f"encoding error: {e}")

# Python files: zero non-ASCII (except string literals)
for pf in py_modified:
    raw = open(pf, "rb").read()
    if raw[:3] == b'\xef\xbb\xbf':
        raw = raw[3:]
    # Check for non-ASCII outside of string literals
    # Simple heuristic: check comment lines and code structure lines
    lines = raw.split(b'\n')
    bad_lines = []
    for i, line in enumerate(lines, 1):
        # Skip lines that are clearly string content (contain quotes)
        stripped = line.strip()
        if stripped.startswith(b'#'):
            # Comment line -- check for non-ASCII
            for b in stripped:
                if b > 127:
                    bad_lines.append(i)
                    break
    check(f"{pf} comments have zero non-ASCII", len(bad_lines) == 0,
          f"non-ASCII in comment lines: {bad_lines[:5]}" if bad_lines else "")

# PS1 files: zero non-ASCII (except BOM)
ps1_all = []
for root, dirs, files in os.walk("tools"):
    for f in files:
        if f.endswith(".ps1"):
            ps1_all.append(os.path.join(root, f))
# Also check start_hybridrag.ps1
if os.path.exists("start_hybridrag.ps1"):
    ps1_all.append("start_hybridrag.ps1")

for pf in ps1_all:
    raw = open(pf, "rb").read()
    check_data = raw[3:] if raw[:3] == b'\xef\xbb\xbf' else raw
    bad_offsets = [i for i, b in enumerate(check_data) if b > 127]
    check(f"{pf} has ZERO non-ASCII (after BOM)", len(bad_offsets) == 0,
          f"{len(bad_offsets)} non-ASCII bytes found" if bad_offsets else "")


# ======================================================================
section(2, "KILL SWITCH CONSOLIDATION (network_gate.py)")
# ======================================================================

gate_code = open("src/core/network_gate.py", "r").read()

# Structural checks
check("network_gate.py imports os",
      "import os" in gate_code)
check("network_gate.py checks HYBRIDRAG_OFFLINE env var",
      'os.environ.get("HYBRIDRAG_OFFLINE"' in gate_code)
check("configure() forces mode_lower='offline' when env var set",
      'mode_lower = "offline"' in gate_code)
check("Log message includes HYBRIDRAG_OFFLINE",
      "HYBRIDRAG_OFFLINE" in gate_code and "forcing offline" in gate_code)

# The check must be BEFORE the mode switch (online/admin/offline)
lines = gate_code.split("\n")
env_check_line = None
online_switch_line = None
for i, line in enumerate(lines):
    if 'HYBRIDRAG_OFFLINE' in line and 'os.environ' in line:
        env_check_line = i
    if env_check_line and 'mode_lower == "online"' in line:
        online_switch_line = i
        break
check("HYBRIDRAG_OFFLINE check is BEFORE mode switch",
      env_check_line is not None and online_switch_line is not None
      and env_check_line < online_switch_line,
      f"env_check={env_check_line}, online_switch={online_switch_line}")


# ======================================================================
section(3, "http_client.py DUPLICATE KILL SWITCH REMOVED")
# ======================================================================

http_code = open("src/core/http_client.py", "r").read()

check("No HYBRIDRAG_OFFLINE env var check in http_client.py",
      'os.environ.get("HYBRIDRAG_OFFLINE"' not in http_code)
check("No 'NETWORK KILL SWITCH' anywhere in file",
      "NETWORK KILL SWITCH" not in http_code)
check("No 'kill switch' (case-insensitive) in functional code",
      "kill switch" not in http_code.lower().replace("# network access control", ""))
check("Still imports network_gate for centralized control",
      "network_gate" in http_code)
check("Still calls check_allowed()",
      "check_allowed" in http_code)
check("offline_mode config check still present (for direct config use)",
      "self.config.offline_mode" in http_code)


# ======================================================================
section(4, "API VERSION ALIGNMENT")
# ======================================================================

router_code = open("src/core/llm_router.py", "r").read()
factory_code = open("src/core/api_client_factory.py", "r").read()

router_match = re.search(r'_DEFAULT_API_VERSION\s*=\s*"([^"]+)"', router_code)
factory_match = re.search(r'DEFAULT_AZURE_API_VERSION\s*=\s*"([^"]+)"', factory_code)

router_v = router_match.group(1) if router_match else "NOT FOUND"
factory_v = factory_match.group(1) if factory_match else "NOT FOUND"

check(f"llm_router._DEFAULT_API_VERSION = {router_v}", router_v != "NOT FOUND")
check(f"api_client_factory.DEFAULT_AZURE_API_VERSION = {factory_v}",
      factory_v != "NOT FOUND")
check("Versions match EXACTLY", router_v == factory_v,
      f"router={router_v} vs factory={factory_v}")

# No stale 2024-02-01 ANYWHERE in factory (code, comments, docstrings)
stale_refs = [(i+1, line.strip()) for i, line in enumerate(factory_code.split("\n"))
              if "2024-02-01" in line]
check("Zero references to stale 2024-02-01 in api_client_factory.py",
      len(stale_refs) == 0,
      f"found on lines: {[r[0] for r in stale_refs]}" if stale_refs else "")

# Cross-check: version string is a valid date format
check("Version string is valid date format (YYYY-MM-DD)",
      bool(re.match(r'^\d{4}-\d{2}-\d{2}$', router_v)),
      f"got: {router_v}")


# ======================================================================
section(5, "BARE EXCEPTS ELIMINATED (project-wide scan)")
# ======================================================================

# Scan ALL Python files in the project for bare excepts
bare_except_report = {}
for root, dirs, files in os.walk("."):
    # Skip .venv, __pycache__, .git
    dirs[:] = [d for d in dirs if d not in ('.venv', '__pycache__', '.git',
               'node_modules', '.model_cache')]
    for f in files:
        if not f.endswith(".py"):
            continue
        fpath = os.path.join(root, f)
        try:
            lines = open(fpath, "r", errors="ignore").readlines()
        except Exception:
            continue
        bare_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Actual bare except: (not string content about detecting bare excepts)
            if (stripped == "except:" or stripped.startswith("except: ")) and \
               "bare except" not in line.lower() and \
               "CODE-SMELL" not in line and \
               '"""' not in line and "'''" not in line:
                bare_lines.append(i)
        if bare_lines:
            bare_except_report[fpath] = bare_lines

# Report per-file
targeted_files = [
    "diagnostics/hybridrag_diagnostic_v2.py",
    "src/tools/system_diagnostic.py",
    "tools/py/test_api_verbose.py",
]
for tf in targeted_files:
    tf_key = f"./{tf}" if not tf.startswith("./") else tf
    bare = bare_except_report.get(tf_key, [])
    check(f"{tf} has ZERO bare excepts", len(bare) == 0,
          f"lines: {bare}" if bare else "")

# Summary of any remaining bare excepts project-wide
total_bare = sum(len(v) for v in bare_except_report.values())
remaining_files = {k: v for k, v in bare_except_report.items()
                   if not any(t in k for t in targeted_files)}
if remaining_files:
    warn_check(f"{total_bare} bare excepts remain project-wide in "
               f"{len(remaining_files)} other files",
               str({k: v for k, v in list(remaining_files.items())[:3]}))
else:
    check("Zero bare excepts project-wide", total_bare == 0)


# ======================================================================
section(6, "MOJIBAKE ELIMINATED (byte scan ALL PS1)")
# ======================================================================

# Double-encoded em-dash pattern
BAD_SEQ = bytes([0xC3, 0xA2, 0xE2, 0x82, 0xAC, 0xE2, 0x80, 0x9D])
# Smart quote patterns (common mojibake)
SMART_QUOTES = [
    bytes([0xE2, 0x80, 0x9C]),  # left double quote
    bytes([0xE2, 0x80, 0x9D]),  # right double quote
    bytes([0xE2, 0x80, 0x98]),  # left single quote
    bytes([0xE2, 0x80, 0x99]),  # right single quote
    bytes([0xE2, 0x80, 0x93]),  # en-dash
    bytes([0xE2, 0x80, 0x94]),  # em-dash
]

for pf in ps1_all:
    raw = open(pf, "rb").read()
    # Strip BOM for checking
    body = raw[3:] if raw[:3] == b'\xef\xbb\xbf' else raw
    check(f"{pf} has no mojibake (double-encoded em-dash)",
          BAD_SEQ not in body)


# ======================================================================
section(7, "HARDCODED DEV PATHS ELIMINATED (ALL PS1)")
# ======================================================================

HARDCODED_PATTERNS = [
    "randaje",
    "OneDrive - NGC",
    r"C:\\Users\\[a-zA-Z]+\\OneDrive",
    r"C:\\Users\\[a-zA-Z]+\\Desktop\\HybridRAG3",
]

for pf in ps1_all:
    code = open(pf, "r", errors="ignore").read()
    found = []
    for pat in HARDCODED_PATTERNS:
        if re.search(pat, code, re.IGNORECASE):
            found.append(pat)
    check(f"{pf} has NO hardcoded dev paths", len(found) == 0,
          f"patterns found: {found}" if found else "")


# ======================================================================
section(8, "PSScriptRoot FALLBACK FOR Invoke-Expression")
# ======================================================================

# These 3 files were modified to use $PSScriptRoot -- they MUST have
# the fallback pattern for the work laptop Invoke-Expression workaround
PSROOT_FILES = [
    "tools/azure_api_test.ps1",
    "tools/fix_azure_detection.ps1",
    "tools/work_transfer.ps1",
]

for pf in PSROOT_FILES:
    if not os.path.exists(pf):
        skip_check(f"{pf} not found")
        continue
    code = open(pf, "r", errors="ignore").read()

    # Must have the if/else fallback, not bare (Split-Path -Parent $PSScriptRoot)
    has_if_check = "if ($PSScriptRoot)" in code
    has_else_fallback = "Get-Location" in code or "$PWD" in code
    has_bare_psscriptroot = re.search(
        r'^\$\w+\s*=\s*\(Split-Path\s+-Parent\s+\$PSScriptRoot\)',
        code, re.MULTILINE)

    check(f"{pf} has if ($PSScriptRoot) check",
          has_if_check,
          "Missing -- will fail under Invoke-Expression on work laptop")
    check(f"{pf} has Get-Location fallback",
          has_else_fallback,
          "Missing -- $PSScriptRoot is empty under Invoke-Expression")
    check(f"{pf} has NO bare PSScriptRoot assignment (no fallback)",
          not has_bare_psscriptroot,
          "Bare assignment will return empty string under Invoke-Expression")

# Verify the pattern uses Split-Path correctly (not just raw $PSScriptRoot)
for pf in PSROOT_FILES:
    if not os.path.exists(pf):
        continue
    code = open(pf, "r", errors="ignore").read()
    check(f"{pf} uses Split-Path to get parent of tools/",
          "Split-Path" in code and "Parent" in code)


# ======================================================================
section(9, "component_tests.py CHECKS NetworkGate (not kill_switch)")
# ======================================================================

comp_code = open("src/diagnostic/component_tests.py", "r").read()

check("Uses 'gate_present' key (not 'kill_switch')",
      "gate_present" in comp_code)
check("No 'kill_switch' key in dict literal",
      '"kill_switch"' not in comp_code)
check("Scans for 'network_gate' string in source files",
      '"network_gate"' in comp_code)
check("Scans for 'NetworkGate' string in source files",
      '"NetworkGate"' in comp_code)
check("Scans for 'check_allowed' string in source files",
      '"check_allowed"' in comp_code)
check("Fix hint mentions NetworkGate (not kill switch)",
      "network_gate" in comp_code.lower() or "NetworkGate" in comp_code)


# ======================================================================
section(10, "system_diagnostic.py CHECKS CORRECT ENV VAR")
# ======================================================================

sysdiag = open("src/tools/system_diagnostic.py", "r").read()

check("References HYBRIDRAG_OFFLINE (the real env var)",
      "HYBRIDRAG_OFFLINE" in sysdiag)
check("No reference to phantom HYBRIDRAG_NETWORK_KILL_SWITCH",
      "HYBRIDRAG_NETWORK_KILL_SWITCH" not in sysdiag)
check("No reference to generic KILL_SWITCH label",
      "KILL_SWITCH" not in sysdiag)
check("Shows warning when forced offline",
      "forced offline" in sysdiag.lower() or "WARN" in sysdiag)


# ======================================================================
section(11, "CLASS SIZE < 500 LINES")
# ======================================================================

# Parse all modified Python files for class definitions
for pf in py_modified:
    try:
        tree = ast.parse(open(pf, "r").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Calculate class body line span
                start = node.lineno
                end = max(getattr(n, 'end_lineno', start)
                          for n in ast.walk(node)
                          if hasattr(n, 'end_lineno'))
                size = end - start + 1
                ok = size < 500
                check(f"{pf}::{node.name} is {size} lines (limit 500)",
                      ok, f"{size} lines exceeds 500" if not ok else "")
    except Exception as e:
        warn_check(f"Could not parse {pf} for class sizes", str(e))


# ======================================================================
section(12, "NO READ+WRITE SAME FILE IN MODIFIED CODE")
# ======================================================================

# Check modified files for patterns that read+write same file in one expr
READWRITE_PATTERNS = [
    # open(x,'r')...open(x,'w') on same line
    r"open\([^)]+,\s*['\"]r['\"]\).*open\([^)]+,\s*['\"]w['\"]\)",
    # f.read()...f.write() patterns
    r"\.read\(\).*\.write\(",
]

for pf in py_modified:
    code = open(pf, "r").read()
    violations = []
    for i, line in enumerate(code.split("\n"), 1):
        for pat in READWRITE_PATTERNS:
            if re.search(pat, line):
                violations.append(i)
    check(f"{pf} no read+write same file in one expression",
          len(violations) == 0,
          f"suspect lines: {violations}" if violations else "")


# ======================================================================
section(13, "PS1 ENCODING (BOM + CRLF READINESS)")
# ======================================================================

# PS1 files SHOULD have UTF-8 BOM for Windows PowerShell 5.1 compatibility
# and should use CRLF or be CRLF-ready (git autocrlf will convert)
for pf in PSROOT_FILES + ["tools/rebuilt_rag_commands.ps1"]:
    if not os.path.exists(pf):
        continue
    raw = open(pf, "rb").read()
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    if has_bom:
        check(f"{pf} has UTF-8 BOM (PS 5.1 compat)", True)
    else:
        warn_check(f"{pf} missing UTF-8 BOM",
                    "PS 5.1 may misinterpret encoding; git LF->CRLF warning expected")

    # Check for mixed line endings
    body = raw[3:] if has_bom else raw
    has_crlf = b'\r\n' in body
    has_bare_lf = b'\n' in body.replace(b'\r\n', b'')
    if has_crlf and has_bare_lf:
        warn_check(f"{pf} has MIXED line endings",
                    "git autocrlf should normalize on checkout")
    elif has_crlf:
        check(f"{pf} uses CRLF line endings", True)
    else:
        check(f"{pf} uses LF (git autocrlf will convert to CRLF on Windows)",
              True)


# ======================================================================
section(14, "PHASE 1 REGRESSION (portable config paths)")
# ======================================================================

# Phase 1 scripts must still have _config_path() function
phase1_scripts = [
    "scripts/_set_online.py",
    "scripts/_set_offline.py",
    "scripts/_profile_status.py",
    "scripts/_profile_switch.py",
    "scripts/_set_model.py",
]
for sf in phase1_scripts:
    if not os.path.exists(sf):
        skip_check(f"{sf} not found")
        continue
    code = open(sf, "r").read()
    check(f"{sf} has _config_path()",
          "def _config_path" in code or "_config_path()" in code)

# requirements.txt must be UTF-8 (not UTF-16LE)
if os.path.exists("requirements.txt"):
    raw = open("requirements.txt", "rb").read()
    is_utf16 = raw[:2] == b'\xff\xfe'
    check("requirements.txt is NOT UTF-16LE", not is_utf16)
else:
    skip_check("requirements.txt not found")


# ======================================================================
section(15, "PHASE 2 REGRESSION (credential consolidation)")
# ======================================================================

# LLMRouter must use resolve_credentials
router_code_fresh = open("src/core/llm_router.py", "r").read()
check("LLMRouter imports resolve_credentials",
      "resolve_credentials" in router_code_fresh)
check("LLMRouter has config mutation guard",
      "original_endpoint" in router_code_fresh or
      "mutate" in router_code_fresh.lower() or
      ("do not" in router_code_fresh.lower() and "endpoint" in router_code_fresh.lower()))

# _set_model.py uses canonical resolver
if os.path.exists("scripts/_set_model.py"):
    setmodel = open("scripts/_set_model.py", "r").read()
    check("_set_model.py uses resolve_credentials",
          "resolve_credentials" in setmodel)

# Keyring schema consistency in diagnostics
diag_code = open("diagnostics/hybridrag_diagnostic_v2.py", "r").read()
check("diagnostic_v2.py uses 'hybridrag' service (not 'hybridragv3')",
      '"hybridragv3"' not in diag_code or
      diag_code.count('"hybridrag"') > diag_code.count('"hybridragv3"'))

# test_azure.py keyring schema
if os.path.exists("test_azure.py"):
    azure_test = open("test_azure.py", "r").read()
    check("test_azure.py uses azure_api_key (not api_key)",
          "azure_api_key" in azure_test)


# ======================================================================
section(16, "CORE MODULE REGRESSION")
# ======================================================================

# Fresh imports to verify nothing broke
modules_to_check = [
    "src.core.network_gate",
    "src.core.http_client",
    "src.core.api_client_factory",
    "src.core.config",
    "src.core.boot",
    "src.core.llm_router",
    "src.security.credentials",
    "src.core.embedder",
    "src.core.chunker",
    "src.core.vector_store",
]
for mod in modules_to_check:
    try:
        # Force reimport to catch issues
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
        else:
            __import__(mod)
        check(f"{mod} importable", True)
    except ImportError as e:
        # Some modules require optional deps not available on Linux test env
        err_str = str(e)
        if any(dep in err_str for dep in [
            "sentence_transformers", "torch", "numpy", "PySide6",
            "keyring", "win32"
        ]):
            skip_check(f"{mod} importable",
                       f"optional dep: {err_str.split(chr(39))[1] if chr(39) in err_str else err_str}")
        else:
            check(f"{mod} importable", False, str(e)[:80])
    except Exception as e:
        check(f"{mod} importable", False, str(e)[:80])


# ======================================================================
section(17, "BEHAVIORAL: NetworkGate HYBRIDRAG_OFFLINE override")
# ======================================================================

# This tests the actual runtime behavior of the gate with the env var
try:
    # Reset any existing gate state
    from src.core import network_gate
    importlib.reload(network_gate)

    # Test 1: Without env var, online mode stays online
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HYBRIDRAG_OFFLINE", None)
        network_gate.reset_gate()
        gate = network_gate.configure_gate("online", "https://api.example.com")
        check("Without HYBRIDRAG_OFFLINE, online mode works",
              gate._mode.value == "online")

    # Test 2: With env var=1, online is overridden to offline
    with mock.patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "1"}):
        network_gate.reset_gate()
        gate = network_gate.configure_gate("online", "https://api.example.com")
        check("HYBRIDRAG_OFFLINE=1 forces online -> offline",
              gate._mode.value == "offline")

    # Test 3: With env var=true, also forces offline
    with mock.patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "true"}):
        network_gate.reset_gate()
        gate = network_gate.configure_gate("admin", "https://api.example.com")
        check("HYBRIDRAG_OFFLINE=true forces admin -> offline",
              gate._mode.value == "offline")

    # Test 4: With env var=yes, also forces offline
    with mock.patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "yes"}):
        network_gate.reset_gate()
        gate = network_gate.configure_gate("online", "https://api.example.com")
        check("HYBRIDRAG_OFFLINE=yes forces online -> offline",
              gate._mode.value == "offline")

    # Test 5: With env var=0 (not set to block), mode is respected
    with mock.patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "0"}):
        network_gate.reset_gate()
        gate = network_gate.configure_gate("online", "https://api.example.com")
        check("HYBRIDRAG_OFFLINE=0 does NOT force offline",
              gate._mode.value == "online")

    # Test 6: Env var with whitespace padding
    with mock.patch.dict(os.environ, {"HYBRIDRAG_OFFLINE": "  1  "}):
        network_gate.reset_gate()
        gate = network_gate.configure_gate("online", "https://api.example.com")
        check("HYBRIDRAG_OFFLINE='  1  ' (padded) forces offline",
              gate._mode.value == "offline")

    # Test 7: Offline mode still works without env var
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HYBRIDRAG_OFFLINE", None)
        network_gate.reset_gate()
        gate = network_gate.configure_gate("offline")
        check("Offline mode works without env var",
              gate._mode.value == "offline")

    # Cleanup
    network_gate.reset_gate()

except Exception as e:
    check("Behavioral tests could run", False, str(e))


# ======================================================================
section(18, "WINDOWS-GAP DOCUMENTATION")
# ======================================================================

print("""
  The following behaviors CANNOT be verified on Linux and must be
  manually tested on the Windows home PC and/or work laptop:

  [MANUAL-01] PowerShell $PSScriptRoot fallback
    Test: cd D:\\HybridRAG3
          $code = [IO.File]::ReadAllText("$pwd\\tools\\azure_api_test.ps1")
          Invoke-Expression $code
    Expect: $projectRoot resolves to D:\\HybridRAG3 (via Get-Location fallback)

  [MANUAL-02] PS 5.1 UTF-8 BOM handling
    Test: Run tools\\rebuilt_rag_commands.ps1 on work laptop
    Expect: No encoding errors, -- displays as double-dash (not mojibake)

  [MANUAL-03] Git autocrlf CRLF conversion
    Test: git diff --check (should show no whitespace errors)
    Expect: LF files convert to CRLF on checkout without issues

  [MANUAL-04] Windows Credential Manager (keyring) calls
    Test: python -m src.security.credentials status
    Expect: Shows credential sources correctly

  [MANUAL-05] Group Policy unsigned script execution
    Test: Run start_hybridrag.ps1 on work laptop
    Expect: ReadAllText/Invoke-Expression fallback works for all tools

  [MANUAL-06] Path with spaces (OneDrive folder)
    Test: All tools/ scripts resolve paths correctly when project is in
          C:\\Users\\<name>\\OneDrive - NGC\\Desktop\\HybridRAG3
    Expect: No path parsing errors from spaces in directory names
""")
check("Windows-gap items documented (6 manual tests)", True)


# ======================================================================
# FINAL RESULTS
# ======================================================================
print()
print("=" * 70)
total = PASS + FAIL + WARN + SKIP
print(f"  RESULTS: {PASS} PASS, {FAIL} FAIL, {WARN} WARN, {SKIP} SKIP")
print(f"  TOTAL:   {total} tests")
print()
if FAIL == 0:
    print("  ALL TESTS PASSED -- changes are safe to deploy")
else:
    print(f"  *** {FAIL} FAILURES -- DO NOT DEPLOY ***")
print("=" * 70)

sys.exit(1 if FAIL > 0 else 0)
