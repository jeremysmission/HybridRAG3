# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the virtual setup scripts area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Virtual test: Setup script validation
Validates setup_home.ps1 and setup_work.ps1 without executing them.
Tests: file presence, syntax, required steps, Group Policy handling,
       path handling, requirements file references, and error recovery.

INTERNET ACCESS: NONE
DEPENDENCIES: stdlib only
RUN: python tests/virtual_test_setup_scripts.py
"""

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name} -- {detail}")


def read_script(name):
    path = PROJECT_ROOT / "tools" / name
    if not path.exists():
        return None
    # utf-8-sig strips BOM (expected on .ps1 files per standing rule)
    return path.read_text(encoding="utf-8-sig", errors="replace")


# ===================================================================
# TEST GROUP 1: File Presence
# ===================================================================
print("\n=== File Presence ===")

check("setup_home.ps1 exists", (PROJECT_ROOT / "tools" / "setup_home.ps1").exists())
check("setup_home.bat exists", (PROJECT_ROOT / "tools" / "setup_home.bat").exists())
check("setup_work.ps1 exists", (PROJECT_ROOT / "tools" / "setup_work.ps1").exists())
check("setup_work.bat exists", (PROJECT_ROOT / "tools" / "setup_work.bat").exists())

# ===================================================================
# TEST GROUP 2: Batch Launchers
# ===================================================================
print("\n=== Batch Launchers ===")

for bat_name in ["setup_home.bat", "setup_work.bat"]:
    content = read_script(bat_name)
    if content is None:
        check(f"{bat_name} readable", False, "file not found")
        continue
    check(f"{bat_name} has ExecutionPolicy Bypass",
          "-ExecutionPolicy Bypass" in content,
          "must bypass Group Policy")
    check(f"{bat_name} has @echo off",
          "@echo off" in content.lower(),
          "should suppress command echo")
    check(f"{bat_name} has pause",
          "pause" in content.lower(),
          "should keep window open for user to read output")

# ===================================================================
# TEST GROUP 3: Home Script Validation
# ===================================================================
print("\n=== Home Script (setup_home.ps1) ===")

home = read_script("setup_home.ps1")
if home is None:
    check("setup_home.ps1 readable", False, "file not found")
else:
    # Basic structure
    check("Has ErrorActionPreference", "$ErrorActionPreference" in home)
    check("Has Write-Ok function", "function Write-Ok" in home)
    check("Has Write-Fail function", "function Write-Fail" in home)
    check("Has Write-Warn function", "function Write-Warn" in home)
    check("Has Group Policy bypass at top",
          "Set-ExecutionPolicy" in home.split("$ErrorActionPreference")[0] if "$ErrorActionPreference" in home else False,
          "must attempt process-scope bypass before the main setup flow")
    check("Uses -Scope Process bypass",
          "-Scope Process" in home,
          "process-scope bypass is the safest approach")
    check("Has SilentlyContinue for GP errors",
          "SilentlyContinue" in home,
          "must silently handle policy denial")

    # Python detection (scripts use foreach loop with @("3.12", "3.11", ...))
    check("Detects Python 3.12", '"3.12"' in home)
    check("Detects Python 3.11", '"3.11"' in home)
    check("Detects Python 3.10", '"3.10"' in home)

    # Venv creation
    check("Creates .venv", "-m venv .venv" in home or "venv .venv" in home)
    check("Checks .venv existence before creation", 'Test-Path ".venv"' in home or "Test-Path .venv" in home)

    # Pip
    check("Upgrades pip", "pip install --upgrade pip" in home)
    check("Uses requirements.txt (personal)", "requirements.txt" in home)
    check("Does NOT use requirements_approved.txt as primary",
          "requirements_approved.txt" not in home.split("pip install")[0] if "pip install" in home else True,
          "home script should use requirements.txt")

    # Path configuration
    check("Prompts for data directory", "Read-Host" in home and "Data" in home)
    check("Prompts for source directory", "Read-Host" in home and "Source" in home)
    check("Has default path suggestions", "RAG Indexed Data" in home or "default" in home.lower())
    check("Creates directories", "New-Item" in home and "Directory" in home)

    # Config file updates
    check("Updates config.yaml", "config.yaml" in home)
    check("Updates start_hybridrag.ps1", "start_hybridrag.ps1" in home)

    # Ollama check
    check("Checks Ollama status", "11434" in home)
    check("Checks nomic-embed-text", "nomic-embed-text" in home)
    check("Checks phi4-mini", "phi4-mini" in home)

    # Regression tests
    check("Runs pytest", "pytest" in home)
    check("Ignores test_fastapi_server.py", "test_fastapi_server" in home)

    # Log tags (no em-dashes)
    check("Uses [OK] tag", "[OK]" in home)
    check("Uses [FAIL] tag", "[FAIL]" in home)
    check("Uses [WARN] tag", "[WARN]" in home)
    check("No em-dash characters", "\u2014" not in home and "\u2013" not in home)

    # No banned content
    check("No hardcoded API keys", not re.search(r'sk-[a-zA-Z0-9]{20,}', home))
    check("No non-ASCII in script", all(ord(c) < 128 for c in home),
          "found non-ASCII characters")

# ===================================================================
# TEST GROUP 4: Work Script Validation
# ===================================================================
print("\n=== Work Script (setup_work.ps1) ===")

work = read_script("setup_work.ps1")
if work is None:
    check("setup_work.ps1 readable", False, "file not found")
else:
    # Basic structure
    check("Has ErrorActionPreference", "$ErrorActionPreference" in work)
    check("Has Write-Ok function", "function Write-Ok" in work)
    check("Has Write-Fail function", "function Write-Fail" in work)
    check("Has Write-Warn function", "function Write-Warn" in work)

    # Group Policy handling (CRITICAL for work)
    check("Has Group Policy bypass at top",
          "Set-ExecutionPolicy" in work.split("$ErrorActionPreference")[0] if "$ErrorActionPreference" in work else False,
          "must attempt GP bypass before any other code")
    check("Uses -Scope Process bypass",
          "-Scope Process" in work,
          "process-scope bypass is the safest approach")
    check("Has SilentlyContinue for GP errors",
          "SilentlyContinue" in work,
          "must silently handle GP denial")
    check("References .bat launcher as fallback",
          ".bat" in work or "setup_work.bat" in work,
          "should tell users about the batch launcher")
    check("Has cmd.exe fallback instructions",
          "cmd" in work.lower() and "activate.bat" in work,
          "must provide cmd fallback for fully locked PowerShell")
    check("Writes setup checkpoint artifact",
          "setup_checkpoint_latest.json" in work,
          "should persist a latest checkpoint file during setup")
    check("Starts transcript trace logging",
          "Start-Transcript" in work and "setup_trace_" in work,
          "should capture a per-run transcript for troubleshooting")
    check("Documents both venv activation paths",
          "Activate.ps1" in work and "activate.bat" in work,
          "must show both PowerShell and cmd activation commands")

    # Proxy handling (CRITICAL for work)
    check("Has --trusted-host pypi.org",
          "--trusted-host" in work and "pypi.org" in work,
          "must handle corporate SSL interception")
    check("Has --trusted-host files.pythonhosted.org",
          "files.pythonhosted.org" in work,
          "must handle corporate SSL interception")
    check("Installs pip-system-certs",
          "pip-system-certs" in work,
          "must bootstrap Windows CA trust")
    check("Sets NO_PROXY for localhost",
          "NO_PROXY" in work and "localhost" in work,
          "must prevent proxy from intercepting Ollama")

    # Python detection (wider range for work)
    check("Detects Python 3.12", '"3.12"' in work)
    check("Detects Python 3.11", '"3.11"' in work)
    check("Detects Python 3.10", '"3.10"' in work)
    check("Does NOT accept Python 3.9", '"3.9"' not in work,
          "faiss-cpu requires >= 3.10, 3.9 must not be offered")

    # Requirements
    check("Uses requirements_approved.txt",
          "requirements_approved.txt" in work,
          "work must use approved packages only")

    # Pytest is optional on work
    check("pytest install is optional",
          "Read-Host" in work and "pytest" in work.lower(),
          "should ask before installing unapproved testing packages")
    check("No sensitive approval info in public script",
          "YELLOW" not in work and "applying for" not in work.lower() and "store approval" not in work.lower(),
          "approval status belongs in requirements_approved.txt, not setup scripts")

    # Template handling
    check("Handles start_hybridrag.ps1.template",
          "template" in work.lower() or ".template" in work,
          "Educational uses template, not the real start script")

    # API credential prompts
    check("Prompts for API endpoint",
          "API" in work and ("endpoint" in work.lower() or "Endpoint" in work),
          "should offer API config")
    check("Prompts for API key",
          "API" in work and ("key" in work.lower() or "Key" in work),
          "should offer API config")
    check("Uses SecureString for API key",
          "SecureString" in work or "AsSecureString" in work,
          "API key input should be hidden")

    # Path configuration
    # Work script shows example paths in prompts but does NOT pre-fill defaults
    check("Does NOT pre-fill default paths in Read-Host",
          "$DEFAULT_DATA" not in work,
          "work paths must be entered by user, no pre-filled defaults")
    check("Requires non-empty paths",
          "IsNullOrWhiteSpace" in work,
          "should reject empty path inputs")

    # Trusted hosts on ALL pip commands
    pip_lines = [line for line in work.split("\n") if "$PIP install" in line and not line.strip().startswith("#")]
    trusted_on_all = all("TRUSTED" in line or "trusted-host" in line for line in pip_lines)
    check("All pip install commands use trusted hosts",
          trusted_on_all,
          f"found {len(pip_lines)} pip install lines, not all have trusted-host")

    # Ollama check with proxy bypass
    check("Ollama check bypasses proxy",
          "WebProxy" in work or "NO_PROXY" in work.split("11434")[0] if "11434" in work else False,
          "Ollama check must bypass corporate proxy")

    # No banned content
    check("No hardcoded API keys", not re.search(r'sk-[a-zA-Z0-9]{20,}', work))
    check("No non-ASCII in script", all(ord(c) < 128 for c in work),
          "found non-ASCII characters")
    check("No em-dash characters", "\u2014" not in work and "\u2013" not in work)

# ===================================================================
# TEST GROUP 5: Cross-Script Consistency
# ===================================================================
print("\n=== Cross-Script Consistency ===")

if home and work:
    # Both should have same core structure
    check("Both have Python detection loops",
          "foreach" in home.lower() and "foreach" in work.lower())
    check("Both have venv creation",
          ".venv" in home and ".venv" in work)
    check("Both run diagnostics or tests",
          "pytest" in home and ("pytest" in work or "rag-diag" in work))
    check("Both have Ollama check",
          "11434" in home and "11434" in work)
    check("Both update config paths",
          "config.yaml" in home and "config.yaml" in work)

    # Work should have MORE security than home
    check("Work has proxy handling, home does not",
          "trusted-host" in work and "trusted-host" not in home)
    check("Work has pip-system-certs, home does not",
          "pip-system-certs" in work and "pip-system-certs" not in home)
    check("Home has Group Policy bypass at top",
          "Set-ExecutionPolicy" in home.split("$ErrorActionPreference")[0] if "$ErrorActionPreference" in home else False)
    check("Work has Group Policy bypass at top",
          "Set-ExecutionPolicy" in work.split("$ErrorActionPreference")[0] if "$ErrorActionPreference" in work else False)

# ===================================================================
# TEST GROUP 6: Requirements File Integrity
# ===================================================================
print("\n=== Requirements File Integrity ===")

req_path = PROJECT_ROOT / "requirements.txt"
req_approved_path = PROJECT_ROOT / "requirements_approved.txt"

if req_path.exists():
    req = req_path.read_text(encoding="utf-8")
    check("requirements.txt has pytest", "pytest" in req)
    check("requirements.txt has psutil", "psutil" in req)
    check("requirements.txt has changelog", "Changelog" in req)
    check("requirements.txt has no HuggingFace", "sentence-transformers" not in req)
    check("requirements.txt has no torch", "torch==" not in req)
else:
    check("requirements.txt exists", False)

if req_approved_path.exists():
    req_a = req_approved_path.read_text(encoding="utf-8")
    check("requirements_approved.txt has keyring", "keyring" in req_a)
    check("requirements_approved.txt has no torch", "torch==" not in req_a)
    check("requirements_approved.txt has waiver annotations",
          "YELLOW" in req_a or "applying" in req_a.lower())
else:
    check("requirements_approved.txt exists", False)


# ===================================================================
# TEST GROUP 7: Cross-Runtime BOM Safety
# ===================================================================
# PowerShell 5.1's Set-Content/Out-File -Encoding UTF8 writes BOM.
# BOM is correct for .ps1 files but BREAKS Python consumers (.yaml,
# .ini, .cfg, .toml, .json).  Scripts must use WriteAllText() for
# files consumed by Python.
print("\n=== Cross-Runtime BOM Safety ===")

# Pattern: files Python reads must NOT be written with -Encoding UTF8
# (which adds BOM in PS 5.1).  Must use WriteAllText instead.
PYTHON_CONSUMED_EXTENSIONS = (".yaml", ".ini", ".cfg", ".toml", ".json", ".txt")

for script_name, content in [("setup_home.ps1", home), ("setup_work.ps1", work)]:
    if not content:
        continue

    # Find all Set-Content/Out-File lines that write -Encoding UTF8
    bom_write_lines = []
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ("-Encoding UTF8" in line or "-Encoding utf8" in line):
            if "Set-Content" in line or "Out-File" in line:
                bom_write_lines.append((i, stripped))

    # Each BOM write must target a .ps1 file or a log file (not Python-consumed)
    for lineno, line in bom_write_lines:
        targets_ps1 = "$startScript" in line or ".ps1" in line
        targets_log = "$LOG_FILE" in line or "log" in line.lower()
        is_python_target = False
        for ext in PYTHON_CONSUMED_EXTENSIONS:
            if ext in line:
                is_python_target = True
                break
        # Also check for generic config paths
        if "$configPath" in line or "pip.ini" in line or "pip.conf" in line:
            is_python_target = True

        if is_python_target:
            check(f"{script_name}:{lineno} no BOM on Python file",
                  False,
                  f"Set-Content/Out-File -Encoding UTF8 writes BOM -- use WriteAllText: {line[:80]}")
        elif not targets_ps1 and not targets_log:
            check(f"{script_name}:{lineno} BOM target identified",
                  True)  # unrecognized but not flagged

    # Positive check: Python-consumed files MUST use WriteAllText
    if "WriteAllText" in content:
        check(f"{script_name} uses WriteAllText for Python files", True)
    else:
        check(f"{script_name} uses WriteAllText for Python files", False,
              "no WriteAllText found -- Python-consumed files may get BOM")

    # YAML config must NOT use Set-Content
    yaml_set_content = re.search(
        r'Set-Content.*\$configPath.*-Encoding UTF8', content)
    check(f"{script_name} YAML config avoids Set-Content BOM",
          yaml_set_content is None,
          "config.yaml written with Set-Content -Encoding UTF8 (adds BOM)")

    # pip.ini must NOT use Out-File
    pipini_outfile = re.search(
        r'Out-File.*pip\.ini.*-Encoding UTF8|Out-File.*\$pipIni.*-Encoding UTF8',
        content)
    check(f"{script_name} pip.ini avoids Out-File BOM",
          pipini_outfile is None,
          "pip.ini written with Out-File -Encoding UTF8 (adds BOM)")


# ===================================================================
# TEST GROUP 8: PS 5.1 Gotcha Patterns
# ===================================================================
# These catch known PowerShell 5.1 runtime bugs that look correct
# in PS 7 but fail silently or crash on PS 5.1.
print("\n=== PS 5.1 Gotcha Patterns ===")

# Pattern 1: Unparenthesized string multiplication in array contexts
# PS comma operator binds tighter than *: "=" * 70, "next" => "=" * (70, "next")
# This throws: Cannot convert System.Object[] to System.Int32
# Fix: ("=" * 70), "next"
MULT_IN_ARRAY = re.compile(r'"[^"]*"\s*\*\s*\d+\s*,')
for script_name, content in [("setup_home.ps1", home), ("setup_work.ps1", work)]:
    if not content:
        continue
    matches = []
    for i, line in enumerate(content.split("\n"), 1):
        if line.strip().startswith("#"):
            continue
        # Skip Python code inside here-strings
        if "print(" in line:
            continue
        if MULT_IN_ARRAY.search(line):
            matches.append((i, line.strip()))
    check(f"{script_name} no unparenthesized string*N in arrays",
          len(matches) == 0,
          f"Lines {[m[0] for m in matches]}: comma binds before * in PS 5.1")

# Pattern 2: ErrorActionPreference must be 'Continue' for Phase 2
# Phase 2 has native commands (pip, python) whose stderr WARNINGs
# become terminating errors under 'Stop' in PS 5.1
for script_name, content in [("setup_home.ps1", home), ("setup_work.ps1", work)]:
    if not content:
        continue
    phase2_marker = "Automated setup begins now"
    phase2_idx = content.find(phase2_marker)
    if phase2_idx >= 0:
        # Check that ErrorActionPreference is set to Continue AFTER the marker
        phase2 = content[phase2_idx:]
        has_continue = "$ErrorActionPreference = 'Continue'" in phase2
        check(f"{script_name} ErrorActionPreference=Continue in Phase 2",
              has_continue,
              "'Stop' converts native command stderr to terminating errors in PS 5.1")

# Pattern 3: Cmdlets inside try/catch should have -ErrorAction Stop
# When global ErrorActionPreference is 'Continue', cmdlet errors are
# non-terminating and will NOT be caught by try/catch without explicit flag
CMDLETS_NEEDING_EA = ["Get-Content", "Set-Content", "Out-File"]
for script_name, content in [("setup_home.ps1", home), ("setup_work.ps1", work)]:
    if not content:
        continue
    lines = content.split("\n")
    in_try = False
    missing = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("try {") or stripped == "try {":
            in_try = True
        if stripped.startswith("} catch") or stripped == "} catch {":
            in_try = False
        if in_try:
            for cmdlet in CMDLETS_NEEDING_EA:
                if cmdlet in stripped and "-ErrorAction" not in stripped:
                    missing.append((i, cmdlet))
    check(f"{script_name} cmdlets in try/catch have -ErrorAction Stop",
          len(missing) == 0,
          f"Lines {[m[0] for m in missing]}: {[m[1] for m in missing]} need -ErrorAction Stop")


# Pattern 4: Invoke-RestMethod must NOT use -Proxy ([System.Net.WebProxy]::new())
# In PS 5.1, -Proxy takes [Uri], not [WebProxy]. This silently fails on
# some corporate proxy configs. Correct method: -WebSession with empty proxy.
BROKEN_PROXY = re.compile(r'-Proxy\s+\(\[System\.Net\.WebProxy\]::new\(\)\)')
for script_name, content in [("setup_home.ps1", home), ("setup_work.ps1", work)]:
    if not content:
        continue
    matches = []
    for i, line in enumerate(content.split("\n"), 1):
        if line.strip().startswith("#"):
            continue
        if BROKEN_PROXY.search(line):
            matches.append(i)
    check(f"{script_name} no broken -Proxy WebProxy pattern",
          len(matches) == 0,
          f"Lines {matches}: -Proxy takes [Uri] not [WebProxy] in PS 5.1, use -WebSession")

# Pattern 5: Ollama check in work script must use -WebSession (proxy bypass)
# Home script does not need proxy bypass (no corporate proxy)
if work:
    has_websession = "-WebSession" in work
    check("setup_work.ps1 Ollama check uses -WebSession for proxy bypass",
          has_websession,
          "Invoke-RestMethod needs -WebSession with empty WebProxy to bypass proxy in PS 5.1")

# Pattern 6: Work script Ollama check should have curl.exe fallback
if work:
    has_curl_fallback = "curl.exe" in work and "noproxy" in work
    check("setup_work.ps1 Ollama check has curl.exe fallback",
          has_curl_fallback,
          "curl.exe --noproxy bypasses all .NET proxy logic as fallback")


# ===================================================================
# SUMMARY
# ===================================================================
print(f"\n{'='*60}")
print(f"  RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
print(f"{'='*60}")

if FAIL_COUNT > 0:
    print("\n  [WARN] Some validations failed -- review output above")
    sys.exit(1)
else:
    print("\n  [OK] All setup script validations passed")
    sys.exit(0)
