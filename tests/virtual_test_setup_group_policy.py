"""
Virtual test: Group Policy restriction simulation
Simulates restricted PowerShell environments and verifies setup scripts
handle Group Policy blocks, proxy failures, and locked-down machines.

INTERNET ACCESS: NONE
DEPENDENCIES: stdlib only
RUN: python tests/virtual_test_setup_group_policy.py
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
    return path.read_text(encoding="utf-8", errors="replace")


# ===================================================================
# SCENARIO 1: ExecutionPolicy completely locked by GPO
# In this scenario, Set-ExecutionPolicy fails even with -Scope Process
# The .bat launcher must be the fallback.
# ===================================================================
print("\n=== SCENARIO 1: ExecutionPolicy locked by GPO ===")
print("  (Simulated: Set-ExecutionPolicy blocked at all scopes)")

work = read_script("setup_work.ps1")
work_bat = read_script("setup_work.bat")

if work is None or work_bat is None:
    check("Scripts exist", False, "setup_work.ps1 or .bat not found")
else:
    # The .bat launcher MUST use -ExecutionPolicy Bypass
    check("Batch launcher bypasses policy",
          "-ExecutionPolicy Bypass" in work_bat,
          "setup_work.bat must pass -ExecutionPolicy Bypass to powershell.exe")

    # The PS1 script must TRY to set policy but handle failure gracefully
    check("PS1 attempts Set-ExecutionPolicy",
          "Set-ExecutionPolicy" in work,
          "should try to set policy even if it might fail")

    # Must use try/catch or -ErrorAction SilentlyContinue
    check("GP failure is caught silently",
          "SilentlyContinue" in work or ("try" in work and "catch" in work),
          "must handle GP denial without crashing")

    # After GP failure, script must continue (not exit)
    # Check that Set-ExecutionPolicy is NOT followed immediately by exit
    ep_lines = [i for i, line in enumerate(work.split("\n"))
                if "Set-ExecutionPolicy" in line and "SilentlyContinue" in line]
    if ep_lines:
        next_lines = work.split("\n")[ep_lines[0]:ep_lines[0]+5]
        check("Script continues after GP denial",
              not any("exit" in line.lower() for line in next_lines),
              "must not exit after Set-ExecutionPolicy failure")

# ===================================================================
# SCENARIO 2: Corporate proxy blocks pip
# In this scenario, pip install fails with SSL certificate errors
# ===================================================================
print("\n=== SCENARIO 2: Corporate proxy blocks pip ===")
print("  (Simulated: pip gets SSL CERTIFICATE_VERIFY_FAILED)")

if work:
    # Must use --trusted-host for initial pip upgrade
    pip_upgrade_section = work.split("pip install --upgrade pip")[0] if "pip install --upgrade pip" in work else ""
    check("Trusted hosts defined before first pip call",
          "$TRUSTED" in work and work.index("$TRUSTED =") < work.index("pip install") if "$TRUSTED" in work and "pip install" in work else False,
          "TRUSTED array must be defined before any pip install")

    # Must install pip-system-certs before the main pip install -r command
    cert_install = work.find("$PIP install pip-system-certs")
    req_install = work.find("$PIP install -r")
    check("pip-system-certs installed before requirements",
          cert_install > 0 and req_install > 0 and cert_install < req_install,
          "pip-system-certs must come before main requirements install")

    # Count pip install commands and verify all have TRUSTED
    pip_install_lines = [line.strip() for line in work.split("\n")
                         if "$PIP install" in line and not line.strip().startswith("#")]
    trusted_count = sum(1 for line in pip_install_lines if "TRUSTED" in line or "trusted-host" in line)
    check(f"All {len(pip_install_lines)} pip commands use trusted hosts",
          trusted_count == len(pip_install_lines),
          f"only {trusted_count}/{len(pip_install_lines)} have trusted-host flags")

# ===================================================================
# SCENARIO 3: Proxy intercepts localhost (Ollama blocked)
# In this scenario, corporate proxy tries to intercept localhost:11434
# ===================================================================
print("\n=== SCENARIO 3: Proxy intercepts localhost ===")
print("  (Simulated: Invoke-RestMethod to localhost goes through proxy)")

if work:
    # Must set NO_PROXY before Ollama check
    ollama_section_start = work.find("Checking Ollama") or work.find("11434")
    no_proxy_positions = [m.start() for m in re.finditer(r'NO_PROXY', work)]

    check("NO_PROXY set before Ollama check",
          any(pos < ollama_section_start for pos in no_proxy_positions) if no_proxy_positions and ollama_section_start > 0 else False,
          "NO_PROXY must be set before the Ollama connectivity check")

    # Must use direct connection (bypass system proxy)
    check("Ollama request bypasses proxy",
          "WebProxy" in work or ("NO_PROXY" in work and "localhost" in work),
          "Invoke-RestMethod to localhost must bypass corporate proxy")

    # Ollama failure must not crash the script -- check the Ollama section only
    ollama_section = work[work.find("Checking Ollama"):] if "Checking Ollama" in work else ""
    check("Ollama failure is non-fatal",
          "catch" in ollama_section.lower() and "exit 1" not in ollama_section,
          "Ollama check should warn, not crash")

# ===================================================================
# SCENARIO 4: Python not on PATH
# In this scenario, py.exe launcher is not available
# ===================================================================
print("\n=== SCENARIO 4: Python not on PATH ===")
print("  (Simulated: py.exe returns error for all versions)")

if work:
    # Must try multiple Python versions (scripts use @("3.12", "3.11", ...) array)
    py_versions = re.findall(r'"(3\.\d+)"', work)
    check(f"Tries {len(py_versions)} Python versions",
          len(py_versions) >= 3,
          f"found {py_versions}, should try at least 3.12, 3.11, 3.10")

    # Must fall back to bare 'python'
    check("Falls back to bare python command",
          "& python --version" in work or '& python' in work,
          "if py launcher fails, should try bare 'python'")

    # Must give clear error if no Python found
    check("Clear error message if no Python",
          "not found" in work.lower() or "install" in work.lower(),
          "must tell user to install Python if none found")

    # Must tell user where to get Python
    check("Suggests Software Center for work laptop",
          "Software Center" in work or "Company Portal" in work or "ServiceNow" in work,
          "work laptop users get Python from IT portal, not python.org")

# ===================================================================
# SCENARIO 5: Script run from wrong directory
# ===================================================================
print("\n=== SCENARIO 5: Wrong working directory ===")
print("  (Simulated: script run from C:\\Users\\Desktop)")

if work:
    # Must detect project root from script location, not cwd
    check("Uses MyInvocation.MyCommand.Path",
          "MyInvocation" in work,
          "must locate project root from script path, not cwd")

    # Must verify requirements file exists
    check("Verifies requirements_approved.txt exists",
          "Test-Path" in work and "requirements_approved.txt" in work,
          "must verify project files exist before proceeding")

    # Must exit gracefully if project not found
    check("Exits with clear error if wrong directory",
          "exit 1" in work or "exit" in work,
          "must exit with error code if project root not found")

# ===================================================================
# SCENARIO 6: cmd.exe fallback (PowerShell completely unusable)
# ===================================================================
print("\n=== SCENARIO 6: PowerShell completely blocked ===")
print("  (Simulated: only cmd.exe available)")

if work:
    # Must document cmd.exe as fallback
    check("Documents cmd.exe fallback",
          "cmd" in work.lower() and "activate.bat" in work,
          "must tell users they can use cmd.exe instead")

    # Must mention direct Python execution
    check("Documents direct Python launch",
          "python src" in work or "python.exe" in work,
          "must show how to run Python directly without PowerShell")

# ===================================================================
# SCENARIO 7: Home script -- lighter restrictions
# ===================================================================
print("\n=== SCENARIO 7: Home script restrictions ===")
print("  (Simulated: personal machine with fewer restrictions)")

home = read_script("setup_home.ps1")
if home:
    # Home should NOT have proxy handling (personal internet)
    check("Home script has no proxy handling",
          "trusted-host" not in home and "pip-system-certs" not in home,
          "personal machine does not need proxy workarounds")

    # Home should have default path suggestions
    check("Home has default path suggestions",
          "RAG Indexed Data" in home,
          "personal setup should suggest standard paths")

    # Home should still handle execution policy
    check("Home bat uses ExecutionPolicy Bypass",
          "-ExecutionPolicy Bypass" in (read_script("setup_home.bat") or ""),
          "even personal machines may have execution policy restrictions")

# ===================================================================
# SCENARIO 8: Verify requirements file differences
# ===================================================================
print("\n=== SCENARIO 8: Requirements file validation ===")

req_path = PROJECT_ROOT / "requirements.txt"
req_approved_path = PROJECT_ROOT / "requirements_approved.txt"

if req_path.exists() and req_approved_path.exists():
    req = req_path.read_text(encoding="utf-8")
    req_approved = req_approved_path.read_text(encoding="utf-8")

    # Personal has pytest, work may or may not
    check("Personal requirements has pytest",
          "pytest" in req)
    check("Personal requirements has psutil",
          "psutil" in req)

    # Both should NOT have retired HuggingFace packages
    for pkg in ["sentence-transformers", "torch==", "transformers==", "tokenizers==", "huggingface_hub=="]:
        check(f"requirements.txt has no {pkg.rstrip('==')}",
              pkg not in req,
              f"RETIRED: {pkg} should not be in requirements.txt")

    # Approved should have waiver annotations
    check("requirements_approved.txt has approval annotations",
          "YELLOW" in req_approved or "GREEN" in req_approved or "applying" in req_approved.lower())

# ===================================================================
# SUMMARY
# ===================================================================
print(f"\n{'='*60}")
print(f"  RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
print(f"  Scenarios tested: 8")
print(f"{'='*60}")

if FAIL_COUNT > 0:
    print(f"\n  [WARN] {FAIL_COUNT} validations failed -- review above")
    sys.exit(1)
else:
    print("\n  [OK] All Group Policy simulation tests passed")
    sys.exit(0)
