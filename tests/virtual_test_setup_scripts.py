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
    return path.read_text(encoding="utf-8", errors="replace")


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
    check("Updates default_config.yaml", "default_config.yaml" in home)
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
    check("Detects Python 3.9", '"3.9"' in work,
          "work laptops may only have 3.9")

    # Requirements
    check("Uses requirements_approved.txt",
          "requirements_approved.txt" in work,
          "work must use approved packages only")

    # Pytest is optional on work
    check("pytest install is optional",
          "Read-Host" in work and "pytest" in work.lower(),
          "should ask before installing unapproved testing packages")
    check("Notes YELLOW approval status",
          "YELLOW" in work or "applying" in work.lower(),
          "should flag pytest/psutil approval status")

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
          "default_config.yaml" in home and "default_config.yaml" in work)

    # Work should have MORE security than home
    check("Work has proxy handling, home does not",
          "trusted-host" in work and "trusted-host" not in home)
    check("Work has pip-system-certs, home does not",
          "pip-system-certs" in work and "pip-system-certs" not in home)
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
