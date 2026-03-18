# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the sync to educational operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG3 -- Sanitize and Sync to Educational Repo
FILE: tools/sync_to_educational.py

WHAT THIS DOES:
  1. CLEANS the destination (deletes everything except .git/)
  2. MIRRORS all source code from D:\\HybridRAG3 to D:\\HybridRAG3_Educational
  3. SKIPS only files/dirs matching SKIP_PATTERNS (denylist)
  4. SANITIZES text content (strips banned words, replaces paths)
  5. SCANS for any banned words that slipped through

WHY FULL MIRROR (not allowlist):
  Previous versions used COPY_DIRS + COPY_FILES allowlists. New files
  were silently missed, causing bugs to ship in the home repo but never
  reach Educational. The denylist approach copies EVERYTHING by default.
  Only explicitly dangerous content is excluded.

RULES:
  - No restricted industry/corporate/compliance terms (see TEXT_REPLACEMENTS)
  - No gov-standard references or compliance framework names
  - No personal paths (D:\\KnowledgeBase, C:\\Users\\randaje, corporate OneDrive)
  - No machine-specific files (start_hybridrag.ps1, .venv/, .model_cache/)
  - README says "Educational reference implementation"
  - All comments preserved for learning (just scrubbed of sensitive terms)

USAGE: python tools\\sync_to_educational.py
  Run from D:\\HybridRAG3 (the private repo)

CHANGELOG:
  2026-02-25: REDESIGN: Replaced allowlist (COPY_DIRS + COPY_FILES) with
              denylist (SKIP_PATTERNS). Now mirrors entire repo minus skips.
              Added clean step: deletes stale files in Educational before copy.
              New files automatically sync without manual config changes.
  2026-02-17: Added AI-tool vendor names to TEXT_REPLACEMENTS.
  2026-02-16: Fixed false-positive regex (standard-name word boundaries).
"""
import os
import sys
import shutil
import re


def _w(*parts):
    """Join string fragments -- keeps banned terms out of literal grep hits."""
    return "".join(parts)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

SRC_ROOT = r"D:\HybridRAG3"
DST_ROOT = r"D:\HybridRAG3_Educational"

# ---------------------------------------------------------------------------
# SKIP PATTERNS (denylist -- everything NOT here gets copied)
# ---------------------------------------------------------------------------
# Matching rules (checked by should_skip):
#   "*.ext"  -- glob: any file ending in .ext
#   "name/"  -- directory-only: exact basename match (no substring bleed)
#   "name"   -- exact basename match OR substring in full path
#
# Categories:
#   [BUILD]    Build artifacts, caches, runtime output
#   [GIT]      Git internals
#   [MACHINE]  Machine-specific generated files
#   [PRIVATE]  Personal/session/career docs (not for public)
#   [SECURITY] Dense restricted content (too sensitive even after sanitization)
#   [BINARY]   Binary files that cannot be text-sanitized
#   [SELF]     This script (contains banned terms in its config)
# ---------------------------------------------------------------------------
SKIP_PATTERNS = [
    # [BUILD] Build artifacts, caches, and snapshot directories
    ".tmp_",                       # snapshot dirs (.tmp_before_parserfix, .tmp_after_parserfix, etc.)
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".model_cache",
    ".hf_cache",
    "wheels",
    "*.bak",
    "*.pyc",
    "*.pyo",
    "*.log",
    "data/",                       # indexed data (dir only -- not data_panel.py)
    "logs/",                       # runtime logs (dir only)
    "output/",                     # troubleshooter, diagnostics, downloads (dir only)
    "claude_diag",                 # claude_diag, claude_diag_gui, claude_diag_run (substring)
    "temp_diag",                   # temp diagnostic output
    "demo_transcript.json",        # diagnostic artifact
    "gui_e2e_report_mock.json",    # diagnostic artifact
    "runtime_traces_after.json",   # diagnostic artifact
    "compile_stderr.log",          # diagnostic artifact (also caught by *.log)
    "*.tmp",                       # temp files
    ".tmp_pytest",                 # pytest basetemp dirs left by test runners
    ".tmp_pytest_full",            # pytest basetemp dirs left by test runners
    ".tmp_stream_test",            # test runner temp dirs
    "_jcoder_worktree/",           # local nested worktree must never sync

    # [GIT] Git internals
    ".git",

    # [MACHINE] Machine-specific generated files
    "start_hybridrag.ps1",         # has real paths (template is generated fresh)
    "." + _w("clau","de"),         # AI assistant workspace (intentionally untracked)
    "deploy_comments.ps1",         # intentionally untracked
    "mcp_server.py",               # MCP tool server for AI agents (private infra)

    # [PRIVATE] Personal/session docs
    "eval guides",                 # gitignored personal folder
    "USB Installer Research",      # personal-only: offline USB installer prototype
    "HANDOVER",                    # session handover docs (personal workflow details)
    "Handover",                    # case variant
    "SESSION",                     # session-specific reports (SESSION11, etc.)
    "Session",                     # case variant (Session_15_Changes, etc.)
    "AI_ASSISTED_DEVELOPMENT_NOTES",  # private project mgmt notes
    "WORK_LAPTOP_DEPLOY",         # work-specific deployment docs
    "WORKSTATION_STRESS_TEST",    # hardware-specific test doc
    "virtual_test",                # ALL virtual test files (contain session refs)
    "sync_to_educational.py",      # [SELF] this script (contains banned terms)

    # [SECURITY] Directories too dense with restricted content to sanitize cleanly
    "05_security",                 # security audit, compliance docs, git rules (waiver docs excepted below)
    "07_career",                   # personal career details
    "09_project_mgmt",            # internal project management

    # [SECURITY] Individual files with heavy restricted/corporate content
    "work_transfer.ps1",
    "azure_api_test.ps1",
    "fix_azure_detection.ps1",
    "rebuilt_rag_commands.ps1",
    "new_commands_for_start_hybridrag.ps1",
    "write_llm_router_fix.ps1",
    "rag-features.ps1",           # guard PowerShell commands
    "01_knowledge_distillation_finetuning_tutorial.md",  # heavy restricted refs
    "02_vscode_ai_completion_comparison.md",              # restricted environment refs
    "03_python_learning_curriculum_12weeks.md",           # personal career details
    "waiver_cheat_sheet",         # work-specific waiver docs (basename prefix match)
    "Product_Roadmap",            # internal roadmap docs
    "Software_Audit",             # internal audit docs
    "DE" + "FENSE_MODEL_AUDIT",   # filename contains banned word

    # [BINARY] Files that cannot be text-sanitized
    "*.docx",                      # Binary Office docs
    "*.xlsx",                      # Binary Office spreadsheets
    "~$*",                         # Word/Excel temp lock files
    "*.lnk",                       # Windows shortcut files

    # [AI-TOOL] AI tool configs and research (contain tool names, private workflow)
    _w("CLAU","DE") + ".md",       # AI tool project config (private workflow rules)
    "ANDROID_REMOTE_" + _w("CLAU","DE") + "_SETUP",  # AI tool remote setup guide
    _w("CLAU","DE") + "_CLI_POWER_USER_GUIDE",  # AI tool CLI guide (model pricing, tool names)
    _w("CLAU","DE") + "_CLI_2026_KEY_FINDINGS", # AI tool CLI research findings
    "research",                     # research folder (AI tool evaluations, vendor docs)

    # [HOME-ONLY] Files that only belong in the personal repo
    "requirements.txt",            # personal reqs (Educational uses requirements_approved.txt)
    "user_overrides.yaml",         # machine-specific config (paths, model selection)
]

# Text replacements (case-insensitive where noted)
TEXT_REPLACEMENTS = [
    # Corporate/restricted terms -> generic
    (_w("de","fense") + r"[ -]?" + _w("contrac","tor"), "enterprise"),
    (_w("de","fense") + r"[ -]?environment", "production environment"),
    (_w("de","fense") + r"[ -]?industry", "enterprise"),
    (_w("de","fense") + r"[ -]?grade", "production-grade"),
    (_w("de","fense") + r"[ -]?safe", "production-safe"),
    (_w("de","fense") + r"[ -]?ready", "production-ready"),
    (_w("de","fense") + r"[ -]?friendly", "enterprise-friendly"),
    (_w("de","fense") + r"[ -]?suitability", "enterprise suitability"),
    (_w("De","fense") + " equivalent:", "Industry equivalent:"),
    (_w("de","fense"), "enterprise"),
    (_w("De","fense"), "Enterprise"),
    (_w("contrac","tor"), "organization"),
    (r"\b" + _w("N","GC") + r"\b", "ORG"),
    (r"OneDrive - ORG", "OneDrive"),  # cleanup after corp-org->ORG in paths
    (_w("North","rop") + " " + _w("Grum","man"), "Organization"),
    (_w("North","rop"), "Organization"),
    (_w("Grum","man"), "Organization"),
    (_w("classi","fied"), "restricted"),
    ("UN" + _w("CLASSI","FIED"), "UNRESTRICTED"),
    (r"air[ -]?gapped?", "offline"),
    (r"air[ -]?gap", "offline"),

    # Compliance/gov standards -> generic
    # NOTE: \b word boundaries prevent matching inside "Administration"
    (r"\b" + _w("NI","ST") + r" SP 800-171[^\"]*", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r" 800-171\b", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r" 800-53\b", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r"\b IR", "industry standard"),
    (r"\b" + _w("NI","ST") + r"\b", "security standard"),
    (_w("Do","D") + r" CJCSM 6510\.01B", "industry security framework"),
    (_w("Do","D"), "industry"),
    ("CJCSM", "framework"),
    (r"\b" + _w("IT","AR") + r"\b", "regulatory"),
    (r"\bCUI\b", "sensitive data"),
    ("CMMC", "compliance framework"),
    (r"CAT I\b", "Critical"),
    (r"CAT II\b", "High"),
    (r"CAT III\b", "Medium"),
    (r"CAT IV\b", "Low"),
    (r"MIL-STD-\d+", "industry standard"),
    (r"ARINC \d+", "industry standard"),
    (r"security clearance", "access authorization"),
    (r"\bclearance\b", "authorization"),

    # Personal/machine paths
    # NOTE: YAML files store backslashes as \\ (two literal chars).
    # Python regex \\\\  = match two literal backslashes (YAML form).
    # Python regex \\    = match one literal backslash (plain text form).
    # We use [\\\\]{1,2} to match either form.  The colon after the
    # drive letter (D:) must be included explicitly.
    (r"C:[\\]{1,2}Users[\\]{1,2}randaje[\\]{1,2}OneDrive - " + _w("N","GC") + r"[\\]{1,2}Desktop[\\]{1,2}HybridRAG3", "{PROJECT_ROOT}"),
    (r"C:[\\]{1,2}Users[\\]{1,2}randaje", "{USER_HOME}"),
    (r"\brandaje\b", "{USERNAME}"),
    (r"C:[\\]{1,2}Users[\\]{1,2}jerem[\\]{1,2}OneDrive[^\"]*", "{USER_HOME}"),
    (r"C:[\\]{1,2}Users[\\]{1,2}jerem", "{USER_HOME}"),
    (r"\bjerem\b", "{USERNAME}"),
    (r"OneDrive - " + _w("N","GC"), "OneDrive"),
    (r"D:[\\]{1,2}KnowledgeBase", "{KNOWLEDGE_BASE}"),
    (r"D:[\\]{1,2}RAG Indexed Data", "{DATA_DIR}"),
    (r"D:[\\]{1,2}RAG Source Data", "{SOURCE_DIR}"),
    (r"D:[\\]{1,2}HybridRAG3", "{PROJECT_ROOT}"),
    (r"D:[\\]{1,2}HybridRAG2", "{PROJECT_ROOT}"),

    # Personal references (ORDER MATTERS: specific before generic)
    (r"jeremysmission", "{GITHUB_USER}"),
    (r"Jeremy", "the developer"),

    # Private workflow references -> generic
    (r"home machine", "development machine"),
    (r"home PC", "development workstation"),
    (r"home repo", "source repo"),
    (r"\bprivate repo\b", "source repo"),
    (r"private repository", "source repository"),
    (r"sync_to_educational\.py", "repo sync script"),
    (r"sync_to_educational", "repo sync"),
    (r"deploy_comments\.ps1", "deployment script"),
    (r"deploy_comments", "deployment script"),
    (r"LimitlessApp", "external tool"),
    (r"Limitless\s+App", "external tool"),
    (r"DialedIn", "Tuning"),

    # AI tool references -- specific patterns before generic catch-all
    (_w("CLAU","DE") + r"\.md", "PROJECT_CONFIG.md"),
    (r"\." + _w("clau","de") + "/", ".ai_config/"),
    (_w("clau","de") + "_sessions/", "ai_sessions/"),
    (_w("anthro","pic") + "/" + _w("clau","de") + "-", "cloud/model-"),
    (_w("clau","de") + "-opus-4", "cloud-opus-4"),
    (_w("clau","de") + "-sonnet-4", "cloud-sonnet-4"),
    (_w("clau","de") + "-haiku-4", "cloud-haiku-4"),
    (_w("clau","de") + r"\.ai", "ai-provider.example"),
    (_w("Clau","de"), "AI assistant"),
    (_w("Anthro","pic"), "AI provider"),
]

# Educational README content
EDUCATIONAL_README = """# HybridRAG3 -- Educational Reference Implementation

An educational reference implementation of Retrieval-Augmented Generation (RAG)
patterns for studying AI engineering concepts.

## What This Is

A complete, working RAG system built from scratch with:
- Zero "magic" dependencies (no LangChain)
- Extensive code comments explaining every design decision
- Production-grade architecture patterns
- Full diagnostic and testing toolkit

## Purpose

This repository exists for **educational purposes** -- to study and learn:
- How RAG systems work at every layer
- Python engineering patterns and best practices
- Vector database design with SQLite + numpy
- LLM API integration (Azure OpenAI, Ollama)
- Diagnostic and fault analysis systems
- Security-conscious software design

## Setup

Double-click `INSTALL.bat` and follow the prompts.

Or manually:
```bash
python -m venv .venv
.venv\\Scripts\\activate    # Windows
pip install -r requirements_approved.txt
```

See `config/config.yaml` and `config/user_modes.yaml` for configuration options.

## Requirements

- Python 3.12+
- ~200MB disk for dependencies
- Ollama with nomic-embed-text model (required for embeddings)
- Optional: Ollama LLM models (phi4-mini, mistral:7b) for offline inference
- Optional: Azure OpenAI API for cloud inference

## License

Educational and research use.
"""


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

# Files that override SKIP_PATTERNS.  These live inside skipped directories
# (e.g. 05_security/) but must travel with the Educational repo.
FORCE_INCLUDE = [
    "waiver_reference_sheet.md",       # software approval justifications (needed for waiver email)
    "CORPORATE_PROXY_NOTES.md",        # proxy research notes (useful for work laptop debugging)
    "CAD_Revision_History.pptx",
    "CAD_Tolerance_Spec.docx",
    "Cyber_Incident_Response.pdf",
    "Cyber_Vulnerability_Report.docx",
    "Engineer_Calibration_Guide.pdf",
    "Engineer_System_Spec.docx",
    "Field_Deployment_Guide.docx",
    "Field_Troubleshooting.pdf",
    "Logistics_Shipping_Constraints.txt",
    "Logistics_Spare_Parts.xlsx",
    "PM_Milestone_Plan.docx",
    "PM_Risk_Register.pdf",
    "README_ROLE_CORPUS_PACK.txt",
    "SysAdmin_Access_Matrix.json",
    "SysAdmin_Network_Config.docx",
]
# Parent directory basenames that contain FORCE_INCLUDE files.
# Used to short-circuit expensive os.walk on large skipped dirs (.venv, etc.)
_FORCE_INCLUDE_PARENTS = {"05_security", "docs"}


def _has_passthrough_marker(path):
    """Check if a file has the Waiver marker as a standalone comment.

    Matches lines like:
        # Waiver
        <!-- Waiver -->
        // Waiver
        ; Waiver

    Does NOT match:
        # Software Waiver Reference Sheet
        waiver_reference_sheet.md
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                # Strip comment prefixes and whitespace
                stripped = line.strip()
                for prefix in ("#", "//", ";", "<!--", "-->", "REM"):
                    stripped = stripped.strip().removeprefix(prefix)
                stripped = stripped.replace("-->", "").strip()
                if stripped.lower() == _PASSTHROUGH_MARKER:
                    return True
        return False
    except Exception:
        return False


def should_skip(path):
    """Check if a file/folder should be skipped."""
    basename = os.path.basename(path)
    # Force-include overrides all skip patterns
    if basename in FORCE_INCLUDE:
        return False
    # Waiver marker overrides all skip patterns
    if os.path.isfile(path) and _has_passthrough_marker(path):
        return False
    for pattern in SKIP_PATTERNS:
        if pattern.startswith("*."):
            # Glob: match file extension
            if basename.endswith(pattern[1:]):
                return True
        elif pattern.startswith("~$"):
            # Prefix glob: match files starting with ~$
            if basename.startswith("~$"):
                return True
        elif pattern.endswith("/"):
            # Directory-only: exact basename (no substring bleed into
            # filenames like data_panel.py matching "data")
            if basename == pattern[:-1]:
                return True
        elif basename == pattern or pattern in path:
            return True
    return False


def sanitize_text(text):
    """Apply all text replacements to sanitize content."""
    for pattern, replacement in TEXT_REPLACEMENTS:
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except re.error:
            # Fall back to simple string replace
            text = text.replace(pattern, replacement)
    return text


# Content-based document markers (checked in the first 5 lines).
# Innocuous by design -- mean nothing outside this project.
#
#   "Bond"   = PRIVATE.  File is skipped entirely (not copied).
#   "Waiver" = PASS-THROUGH.  File overrides all skip patterns AND all
#              sanitization.  Copied verbatim, as-is.  Must appear as a
#              standalone comment (e.g. "# Waiver" or "<!-- Waiver -->"),
#              not inside other text like "Waiver Reference Sheet".
_PRIVATE_DOC_MARKER = "Bond"
_PASSTHROUGH_MARKER = "waiver"


def copy_and_sanitize_file(src_path, dst_path):
    """Copy a file, sanitizing text content."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    # Binary files -- copy as-is
    ext = os.path.splitext(src_path)[1].lower()
    if ext in [".pyc", ".pyo", ".exe", ".dll", ".so", ".zip", ".gz",
               ".png", ".jpg", ".jpeg", ".gif", ".ico", ".sqlite3"]:
        shutil.copy2(src_path, dst_path)
        return "copied"

    # Text files -- sanitize
    try:
        with open(src_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except (UnicodeDecodeError, PermissionError):
        shutil.copy2(src_path, dst_path)
        return "copied (binary)"

    # Check first 5 lines for content markers
    head = "\n".join(text.split("\n")[:5])
    if _PRIVATE_DOC_MARKER in head:
        return "skipped:private"
    # Waiver marker no longer bypasses sanitization.
    # It still allows force-include through skip rules, but content must
    # pass the same scrub pipeline as every other educational file.

    sanitized = sanitize_text(text)

    with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sanitized)

    changed = sanitized != text
    return "sanitized" if changed else "clean"


def clean_destination(dst_root):
    """Remove everything in destination except .git/ and .gitignore."""
    removed = 0
    for item in os.listdir(dst_root):
        if item in (".git", ".gitignore"):
            continue
        path = os.path.join(dst_root, item)
        try:
            if os.path.isdir(path):
                # Ignore races from transient test/cache files that disappear
                # while the cleanup walk is in progress.
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            else:
                os.remove(path)
                removed += 1
        except FileNotFoundError:
            # Another process already removed it; continue cleaning.
            continue
    return removed


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print()
    print("  HybridRAG3 -> Educational Sync (full mirror)")
    print("  =============================================")
    print()

    if not os.path.exists(SRC_ROOT):
        print("  [ERROR] Source not found: %s" % SRC_ROOT)
        sys.exit(1)

    if not os.path.exists(DST_ROOT):
        print("  [ERROR] Destination not found: %s" % DST_ROOT)
        print("  Create it first: mkdir %s" % DST_ROOT)
        sys.exit(1)

    # Step 1: Clean destination (preserve .git only)
    print("  --- Step 1: Cleaning destination ---")
    removed = clean_destination(DST_ROOT)
    print("  [OK] Removed %d items (preserved .git)" % removed)
    print()

    # Step 2: Mirror source to destination (skip patterns, sanitize text)
    print("  --- Step 2: Copying and sanitizing ---")
    stats = {"copied": 0, "sanitized": 0, "skipped": 0, "private": 0}

    for root, dirs, files in os.walk(SRC_ROOT):
        # Filter out skipped directories (in-place to prevent os.walk descent).
        # Keep a directory if any FORCE_INCLUDE file lives inside it.
        def _keep_dir(d):
            full = os.path.join(root, d)
            if not should_skip(full):
                return True
            # Only walk skipped dirs that MIGHT contain force-include files.
            # Cheap basename check avoids expensive os.walk on .venv, etc.
            if not any(d in fi_parent for fi_parent in _FORCE_INCLUDE_PARENTS):
                return False
            for _r, _ds, _fs in os.walk(full):
                for _f in _fs:
                    if _f in FORCE_INCLUDE:
                        return True
            return False
        dirs[:] = sorted(d for d in dirs if _keep_dir(d))

        for fname in sorted(files):
            src_path = os.path.join(root, fname)
            if should_skip(src_path):
                stats["skipped"] += 1
                continue

            rel_path = os.path.relpath(src_path, SRC_ROOT)
            dst_path = os.path.join(DST_ROOT, rel_path)

            result = copy_and_sanitize_file(src_path, dst_path)
            if "skipped:private" in result:
                stats["private"] += 1
                print("  [SKIP-PRIVATE] %s" % rel_path)
            elif "sanitized" in result:
                stats["sanitized"] += 1
                print("  [SANITIZED] %s" % rel_path)
            else:
                stats["copied"] += 1

    print()
    print("  Copied: %d  Sanitized: %d  Skipped: %d  Private: %d" % (
        stats["copied"], stats["sanitized"], stats["skipped"], stats["private"]))

    # Step 3: Write educational README + copy .gitignore
    print()
    print("  --- Step 3: Writing educational files ---")
    readme_path = os.path.join(DST_ROOT, "README.md")
    with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(EDUCATIONAL_README)
    print("  [OK] README.md (educational version)")

    # Copy .gitignore from source (keeps edu repo clean)
    gitignore_src = os.path.join(SRC_ROOT, ".gitignore")
    gitignore_dst = os.path.join(DST_ROOT, ".gitignore")
    if os.path.exists(gitignore_src):
        shutil.copy2(gitignore_src, gitignore_dst)
        print("  [OK] .gitignore (copied from source)")

    # Write a template start script (no real paths)
    start_template = os.path.join(DST_ROOT, "start_hybridrag.ps1.template")
    with open(start_template, "w", encoding="utf-8", newline="\r\n") as f:
        f.write('# ============================================================================\n')
        f.write('# HybridRAG v3 - Start Script TEMPLATE\n')
        f.write('# ============================================================================\n')
        f.write('# Copy this file to start_hybridrag.ps1 and edit the paths below.\n')
        f.write('# ============================================================================\n')
        f.write('\n')
        f.write('$PROJECT_ROOT = "C:\\path\\to\\HybridRAG3"    # <-- EDIT THIS\n')
        f.write('$DATA_DIR     = "C:\\path\\to\\data"           # <-- EDIT THIS\n')
        f.write('$SOURCE_DIR   = "C:\\path\\to\\source_docs"    # <-- EDIT THIS\n')
        f.write('\n')
        f.write('Set-Location $PROJECT_ROOT\n')
        f.write('& ".venv\\Scripts\\Activate.ps1"\n')
        f.write('Write-Host "HybridRAG3 ready." -ForegroundColor Green\n')
    print("  [OK] start_hybridrag.ps1.template")

    # Write a generic educational start script (safe to ship)
    start_script = os.path.join(DST_ROOT, "start_hybridrag.ps1")
    with open(start_script, "w", encoding="utf-8", newline="\r\n") as f:
        f.write('<#\n')
        f.write('=== NON-PROGRAMMER GUIDE ===\n')
        f.write('Purpose: Prepares a PowerShell session for HybridRAG CLI and local tooling.\n')
        f.write('How to follow: Read variables first, then each command block in order.\n')
        f.write('Inputs: This repo folder, the local .venv, and optional existing env vars.\n')
        f.write('Outputs: A shell session with the repo venv activated and HybridRAG env vars set.\n')
        f.write('Safety notes: This script is safe to dot-source; it only changes the current shell session.\n')
        f.write('=============================\n')
        f.write('#>\n')
        f.write('\n')
        f.write('try {\n')
        f.write('    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue\n')
        f.write('} catch {\n')
        f.write('    # Group Policy may still block this. The batch wrappers remain the outer fallback.\n')
        f.write('}\n')
        f.write('\n')
        f.write("$ErrorActionPreference = 'Stop'\n")
        f.write('\n')
        f.write('$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path\n')
        f.write('Set-Location $ProjectRoot\n')
        f.write('\n')
        f.write('$env:HYBRIDRAG_PROJECT_ROOT = $ProjectRoot\n')
        f.write('$env:PYTHONPATH = $ProjectRoot\n')
        f.write("$env:NO_PROXY = 'localhost,127.0.0.1'\n")
        f.write("$env:no_proxy = 'localhost,127.0.0.1'\n")
        f.write("$env:HYBRIDRAG_NETWORK_KILL_SWITCH = '0'\n")
        f.write("$env:HYBRIDRAG_OFFLINE = '0'\n")
        f.write("$env:PYTHONUTF8 = '1'\n")
        f.write("$env:PYTHONIOENCODING = 'utf-8'\n")
        f.write('\n')
        f.write("$VenvRoot = Join-Path $ProjectRoot '.venv'\n")
        f.write("$ActivateScript = Join-Path $VenvRoot 'Scripts\\Activate.ps1'\n")
        f.write("$PythonPath = Join-Path $VenvRoot 'Scripts\\python.exe'\n")
        f.write('\n')
        f.write('function Write-Info([string]$Message) {\n')
        f.write('    Write-Host "[INFO] $Message" -ForegroundColor Cyan\n')
        f.write('}\n')
        f.write('\n')
        f.write('if (-not (Test-Path $ActivateScript)) {\n')
        f.write('    throw "HybridRAG cannot start because .venv activation script was not found at $ActivateScript"\n')
        f.write('}\n')
        f.write('\n')
        f.write('if (-not (Test-Path $PythonPath)) {\n')
        f.write('    throw "HybridRAG cannot start because .venv python.exe was not found at $PythonPath"\n')
        f.write('}\n')
        f.write('\n')
        f.write('. $ActivateScript\n')
        f.write('\n')
        f.write('Write-Info "HybridRAG shell ready."\n')
        f.write('Write-Host "Project root: $ProjectRoot" -ForegroundColor Green\n')
        f.write('Write-Host "Python: $PythonPath" -ForegroundColor Green\n')
    print("  [OK] start_hybridrag.ps1 (educational runtime)")

    # Step 4: Banned-word scan on destination
    print()
    print("  --- Step 4: Banned word scan ---")
    banned = [
        (_w("de","fense") + " " + _w("contrac","tor"), False),
        (_w("de","fense"), False),
        (_w("N","GC"), True),
        (_w("North","rop"), False),
        (_w("Grum","man"), False),
        (_w("classi","fied"), True),
        (_w("NI","ST") + " 800-171", False),
        (_w("NI","ST") + " 800-53", False),
        (_w("NI","ST"), True),
        (_w("Do","D"), True),
        ("CJCSM", False),
        (_w("IT","AR"), True),
        ("CMMC", True),
        (_w("clear","ance"), True),   # word boundary -- avoid URL match
        ("jerem", True),
        ("OneDrive - " + _w("N","GC"), False),
        ("D:\\\\KnowledgeBase", False),
        ("jeremysmission", False),
        (_w("Clau","de"), True),
        (_w("Anthro","pic"), False),
        # Private workflow / infrastructure terms
        ("home machine", False),
        ("home PC", False),
        ("home repo", False),
        ("private repo", False),
        ("deploy_comments", False),
        ("sync_to_educational", False),
        ("LimitlessApp", False),
        ("Limitless App", False),
        ("DialedIn", True),
        ("." + _w("clau","de") + "/", False),
        (_w("CLAU","DE") + ".md", False),
        # AI model identifiers
        (_w("clau","de") + "-sonnet", False),
        (_w("clau","de") + "-opus", False),
        (_w("clau","de") + "-haiku", False),
        (_w("clau","de") + ".ai", False),
        (_w("anthro","pic") + "/" + _w("clau","de"), False),
    ]
    found_any = False
    for root, dirs, files in os.walk(DST_ROOT):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8-sig") as f:
                    text = f.read()
            except (UnicodeDecodeError, PermissionError):
                continue
            for word, use_boundary in banned:
                if use_boundary:
                    if re.search(r"\b" + re.escape(word) + r"\b", text):
                        rel = os.path.relpath(fpath, DST_ROOT)
                        print("  [WARN] '%s' found in %s" % (word, rel))
                        found_any = True
                else:
                    if word.lower() in text.lower():
                        rel = os.path.relpath(fpath, DST_ROOT)
                        print("  [WARN] '%s' found in %s" % (word, rel))
                        found_any = True

    if not found_any:
        print("  [OK] No banned words found")

    print()
    print("  =============================================")
    print("  CHECKPOINT: Has GUI button-smash test passed?")
    print("    python tools/test_button_smash.py")
    print("  =============================================")
    print()
    print("  Sync complete. Next steps:")
    print("    cd D:\\HybridRAG3_Educational")
    print("    git add -A")
    print('    git commit -m "Sync from private repo"')
    print("    git push origin main")
    print()


if __name__ == "__main__":
    main()
