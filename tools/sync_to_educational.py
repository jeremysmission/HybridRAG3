"""
HybridRAG3 -- Sanitize and Sync to Educational Repo
FILE: tools/sync_to_educational.py

WHAT THIS DOES:
  1. Copies source code from D:\\HybridRAG3 to D:\\HybridRAG3_Educational
  2. Strips defense/contractor/corporate/personal references
  3. Replaces machine-specific paths with placeholders
  4. Writes a clean educational README
  5. Skips files that should never be public (.venv, caches, API keys, .bak)

RULES:
  - No "defense", "contractor", "NGC", "Northrop", "Grumman", "classified"
  - No "NIST", "DoD", "CJCSM", "ITAR", "CUI", "CMMC", "clearance"
  - No personal paths (D:\\KnowledgeBase, C:\\Users\\randaje, OneDrive - NGC)
  - No machine-specific files (start_hybridrag.ps1, .venv/, .model_cache/)
  - README says "Educational reference implementation"
  - All comments preserved for learning (just scrubbed of sensitive terms)

USAGE: python tools\\sync_to_educational.py
  Run from D:\\HybridRAG3 (the private repo)

CHANGELOG:
  2026-02-16: Added "scripts" to COPY_DIRS (model wizard files).
              Moved api_mode_commands.ps1 from SKIP to COPY (NGC paths removed).
              Added hallucination_guard to SKIP (unverified, defer to future sync).
              Fixed false-positive regex: NIST/CUI now use \\b word boundaries
              to prevent corrupting "Administration" -> "Admisecurity standardration".
              Added standalone "clearance" and "randaje" to TEXT_REPLACEMENTS
              (previously only "security clearance" was caught).
  2026-02-17: Replaced 3 specific virtual_test skips with catch-all "virtual_test"
              prefix (catches all current and future virtual test files).
              Added sync_to_educational.py itself to SKIP (contains banned terms).
              Added "Claude" and "Anthropic" to TEXT_REPLACEMENTS and banned words
              (session artifacts that should not appear in educational repo).
"""
import os
import sys
import shutil
import re

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

SRC_ROOT = r"D:\HybridRAG3"
DST_ROOT = r"D:\HybridRAG3_Educational"

# Folders to copy (relative to SRC_ROOT)
COPY_DIRS = [
    "src",
    "tests",
    "config",
    "tools/py",
    "tools/work_validation",  # model validation scripts (defense-cleared stack)
    "diagnostics",
    "scripts",              # model wizard (_set_model.py, _model_meta.py)
]

# Individual files to copy
COPY_FILES = [
    "requirements.txt",
    ".gitignore",
    "tools/master_toolkit.ps1",
    "tools/_rebuild_toolkit.py",
    "tools/test_all_diagnostics.ps1",
    "tools/api_mode_commands.ps1",   # cleaned of NGC paths; has rag-set-model
    "start.cmd",                     # cross-env launcher (works on restricted machines)
    "run.cmd",                       # fallback launcher via python tools/run.py
    "start_rag.bat",                 # execution policy bypass launcher (double-click)
    "start_gui.bat",                 # direct GUI launcher (double-click)
]

# Files/folders to NEVER copy
SKIP_PATTERNS = [
    ".venv",
    ".git",
    "__pycache__",
    ".model_cache",
    ".hf_cache",
    "wheels",
    "*.bak",
    "*.pyc",
    "*.pyo",
    "start_hybridrag.ps1",        # machine-specific
    "eval guides",                 # gitignored personal folder
    "releases",                    # zip transfers
    "data",                        # indexed data
    "logs",                        # runtime logs
    "temp_diag",                   # temp diagnostic output
    "work_transfer.ps1",          # has NGC paths
    "azure_api_test.ps1",         # has NGC paths
    "fix_azure_detection.ps1",    # has NGC paths
    "rebuilt_rag_commands.ps1",   # has NGC paths
    # -- Hallucination guard: skip until verified and installed properly --
    "hallucination_guard",         # entire src/core/hallucination_guard/ subfolder
    # guard_config.py: now synced (clean dataclass, no banned words)
    "feature_registry.py",         # feature toggle (guard dependency)
    "grounded_query_engine.py",    # guard wrapper for query engine
    "guard_diagnostic.py",         # guard health check
    "virtual_test",                # ALL virtual test files (contain Claude/session refs)
    "sync_to_educational.py",      # this script itself (contains banned terms in config)
    "HANDOVER",                    # session handover docs (personal workflow details)
    "rag-features.ps1",           # guard PowerShell commands
    "HYBRIDRAG3_SECURITY_AUDIT_NIST_800_171.md",  # full NIST audit doc
    "01_knowledge_distillation_finetuning_tutorial.md",  # heavy defense refs
    "02_vscode_ai_completion_comparison.md",  # defense environment refs
    "03_python_learning_curriculum_12weeks.md",  # personal career details
    "*.lnk",                       # Windows shortcut files (personal/machine-specific)
    "*.docx",                      # Binary Office docs (cannot sanitize text inside)
    "*.xlsx",                      # Binary Office spreadsheets (cannot sanitize)
    "~$*",                         # Word/Excel temp lock files
    "Handover",                    # case variant of HANDOVER (session-specific docs)
    "SESSION11",                   # session-specific detailed reports
    "WORK_LAPTOP_DEPLOY",         # work-specific deployment session docs
    "waiver_cheat_sheet",         # work-specific waiver docs
    "Product_Roadmap",            # internal roadmap docs
    "Software_Audit",             # internal audit docs
    "DEFENSE_MODEL_AUDIT",        # filename contains banned word "defense"
]

# Text replacements (case-insensitive where noted)
TEXT_REPLACEMENTS = [
    # Corporate/defense terms -> generic
    (r"defense[ -]?contractor", "enterprise"),
    (r"defense[ -]?environment", "production environment"),
    (r"defense[ -]?industry", "enterprise"),
    (r"defense[ -]?grade", "production-grade"),
    (r"defense[ -]?safe", "production-safe"),
    (r"defense[ -]?ready", "production-ready"),
    (r"defense[ -]?friendly", "enterprise-friendly"),
    (r"defense[ -]?suitability", "enterprise suitability"),
    (r"Defense equivalent:", "Industry equivalent:"),
    (r"defense", "enterprise"),
    (r"Defense", "Enterprise"),
    (r"contractor", "organization"),
    (r"\bNGC\b", "ORG"),
    (r"OneDrive - ORG", "OneDrive"),  # cleanup after NGC->ORG in paths
    (r"Northrop Grumman", "Organization"),
    (r"Northrop", "Organization"),
    (r"Grumman", "Organization"),
    (r"classified", "restricted"),
    (r"UNCLASSIFIED", "UNRESTRICTED"),
    (r"air[ -]?gapped?", "offline"),
    (r"air[ -]?gap", "offline"),

    # NIST/DoD/military standards -> generic
    # NOTE: \b word boundaries prevent matching inside "Administration"
    (r"\bNIST SP 800-171[^\"]*", "security compliance standard"),
    (r"\bNIST 800-171\b", "security compliance standard"),
    (r"\bNIST 800-53\b", "security compliance standard"),
    (r"\bNIST\b IR", "industry standard"),
    (r"\bNIST\b", "security standard"),
    (r"DoD CJCSM 6510\.01B", "industry security framework"),
    (r"DoD", "industry"),
    (r"CJCSM", "framework"),
    (r"ITAR", "regulatory"),
    (r"\bCUI\b", "sensitive data"),
    (r"CMMC", "compliance framework"),
    (r"CAT I\b", "Critical"),
    (r"CAT II\b", "High"),
    (r"CAT III\b", "Medium"),
    (r"CAT IV\b", "Low"),
    (r"MIL-STD-\d+", "industry standard"),
    (r"ARINC \d+", "industry standard"),
    (r"security clearance", "access authorization"),
    (r"\bclearance\b", "authorization"),   # standalone "clearance" (not just "security clearance")

    # Personal/machine paths
    # randaje is the work username -- paths replaced with {USER_HOME}, not banned
    # jerem is the personal laptop username -- must never appear in Educational repo
    (r"C:\\Users\\randaje\\OneDrive - NGC\\Desktop\\HybridRAG3", "{PROJECT_ROOT}"),
    (r"C:\\Users\\randaje", "{USER_HOME}"),
    (r"\brandaje\b", "{USERNAME}"),         # catch any remaining work username references
    (r"C:\\Users\\jerem\\OneDrive[^\"]*", "{USER_HOME}"),   # personal laptop paths
    (r"C:\\Users\\jerem", "{USER_HOME}"),
    (r"\bjerem\b", "{USERNAME}"),           # catch any remaining personal username references
    (r"OneDrive - NGC", "OneDrive"),
    (r"D:\\KnowledgeBase", "{KNOWLEDGE_BASE}"),
    (r"D:\\RAG Indexed Data", "{DATA_DIR}"),
    (r"D:\\RAG Source Data", "{SOURCE_DIR}"),
    (r"D:\\HybridRAG3", "{PROJECT_ROOT}"),
    (r"D:\\HybridRAG2", "{PROJECT_ROOT}"),

    # Personal references
    (r"Jeremy", "the developer"),
    (r"jeremysmission", "{GITHUB_USER}"),

    # AI tool references (session artifacts)
    (r"Claude", "AI assistant"),
    (r"Anthropic", "AI provider"),
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

## Architecture

```
src/
  core/           # Core RAG engine
    indexer.py        # Document ingestion pipeline
    chunker.py        # Text splitting with overlap
    chunk_ids.py      # Deterministic ID generation
    embedder.py       # Sentence-transformer embeddings
    vector_store.py   # SQLite + numpy vector search
    retriever.py      # Hybrid retrieval (vector + keyword)
    llm_router.py     # Multi-provider LLM routing
    config.py         # Dataclass-based configuration
  diagnostic/     # Health monitoring
  tools/          # System utilities
tools/
  py/             # Extracted Python toolkit scripts
  master_toolkit.ps1  # PowerShell command interface
tests/            # Test suites
config/           # YAML configuration templates
```

## Key Design Principles

1. **Zero Magic** -- Every operation is explicit and traceable
2. **Offline-First** -- Works without internet by default
3. **Auditable** -- Full logging, deterministic behavior
4. **Minimal Dependencies** -- Only what's needed, pinned versions
5. **Readable** -- Extensive comments for learning

## Setup

```bash
python -m venv .venv
.venv\\Scripts\\activate    # Windows
pip install -r requirements.txt
```

See `config/default_config.yaml` for configuration options.

## Requirements

- Python 3.11+
- ~200MB disk for dependencies
- ~87MB for embedding model (downloads on first run)
- Optional: Ollama for local LLM inference
- Optional: Azure OpenAI API for cloud inference

## License

Educational and research use.
"""


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def should_skip(path):
    """Check if a file/folder should be skipped."""
    basename = os.path.basename(path)
    for pattern in SKIP_PATTERNS:
        if pattern.startswith("*."):
            if basename.endswith(pattern[1:]):
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


def copy_and_sanitize_file(src_path, dst_path):
    """Copy a file, sanitizing text content."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    # Binary files -- copy as-is
    ext = os.path.splitext(src_path)[1].lower()
    if ext in [".pyc", ".pyo", ".exe", ".dll", ".so", ".zip", ".gz"]:
        shutil.copy2(src_path, dst_path)
        return "copied"

    # Text files -- sanitize
    try:
        with open(src_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except (UnicodeDecodeError, PermissionError):
        shutil.copy2(src_path, dst_path)
        return "copied (binary)"

    sanitized = sanitize_text(text)

    with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sanitized)

    changed = sanitized != text
    return "sanitized" if changed else "clean"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print()
    print("  HybridRAG3 -> Educational Sync")
    print("  ================================")
    print()

    if not os.path.exists(SRC_ROOT):
        print("  [ERROR] Source not found: %s" % SRC_ROOT)
        sys.exit(1)

    if not os.path.exists(DST_ROOT):
        print("  [ERROR] Destination not found: %s" % DST_ROOT)
        print("  Create it first: mkdir %s" % DST_ROOT)
        sys.exit(1)

    stats = {"copied": 0, "sanitized": 0, "skipped": 0}

    # Copy directories
    for rel_dir in COPY_DIRS:
        src_dir = os.path.join(SRC_ROOT, rel_dir)
        dst_dir = os.path.join(DST_ROOT, rel_dir)

        if not os.path.exists(src_dir):
            print("  [SKIP] %s (not found)" % rel_dir)
            continue

        for root, dirs, files in os.walk(src_dir):
            # Filter out skip dirs
            dirs[:] = [d for d in dirs if not should_skip(os.path.join(root, d))]

            for fname in files:
                src_path = os.path.join(root, fname)
                if should_skip(src_path):
                    stats["skipped"] += 1
                    continue

                rel_path = os.path.relpath(src_path, SRC_ROOT)
                dst_path = os.path.join(DST_ROOT, rel_path)

                result = copy_and_sanitize_file(src_path, dst_path)
                if "sanitized" in result:
                    stats["sanitized"] += 1
                    print("  [SANITIZED] %s" % rel_path)
                else:
                    stats["copied"] += 1

    # Copy individual files
    for rel_file in COPY_FILES:
        src_path = os.path.join(SRC_ROOT, rel_file)
        dst_path = os.path.join(DST_ROOT, rel_file)

        if not os.path.exists(src_path):
            print("  [SKIP] %s (not found)" % rel_file)
            continue

        if should_skip(src_path):
            stats["skipped"] += 1
            continue

        result = copy_and_sanitize_file(src_path, dst_path)
        if "sanitized" in result:
            stats["sanitized"] += 1
            print("  [SANITIZED] %s" % rel_file)
        else:
            stats["copied"] += 1

    # Copy safe docs (skip the ones with heavy defense content)
    docs_src = os.path.join(SRC_ROOT, "docs")
    if os.path.exists(docs_src):
        for fname in os.listdir(docs_src):
            if should_skip(fname):
                stats["skipped"] += 1
                continue
            src_path = os.path.join(docs_src, fname)
            if os.path.isfile(src_path):
                dst_path = os.path.join(DST_ROOT, "docs", fname)
                result = copy_and_sanitize_file(src_path, dst_path)
                if "sanitized" in result:
                    stats["sanitized"] += 1
                    print("  [SANITIZED] docs/%s" % fname)
                else:
                    stats["copied"] += 1

    # Write educational README
    readme_path = os.path.join(DST_ROOT, "README.md")
    with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(EDUCATIONAL_README)
    print("  [OK] README.md (educational version)")

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

    # Final banned-word check
    print()
    print("  --- Banned Word Scan ---")
    # Banned words with whether they need word-boundary matching
    # Short terms like NGC match inside class names (ChunkingConfig)
    # so they need word-boundary regex matching
    banned = [
        ("defense contractor", False),
        ("defense", False),
        ("NGC", True),       # word boundary -- avoid ChunkingConfig false positive
        ("Northrop", False),
        ("Grumman", False),
        ("classified", True),  # word boundary -- avoid "misclassified" false positive
        ("NIST 800-171", False),
        ("NIST 800-53", False),
        ("NIST", True),
        ("DoD", True),
        ("CJCSM", False),
        ("ITAR", True),
        ("CMMC", True),
        ("clearance", False),
        # randaje is the work username -- not banned, use $env:USERPROFILE instead of hardcoding
        # jerem is the personal laptop username -- must never appear in Educational repo
        ("jerem", True),       # word boundary -- personal laptop username
        ("OneDrive - NGC", False),
        ("D:\\\\KnowledgeBase", False),
        ("jeremysmission", False),
        ("Claude", True),          # word boundary -- avoid "excluded" false positive
        ("Anthropic", False),
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
                    # Use regex word boundaries to avoid substring matches
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
    print("  Summary: %d copied, %d sanitized, %d skipped" % (
        stats["copied"], stats["sanitized"], stats["skipped"]))
    print()
    print("  Next steps:")
    print("    cd D:\\HybridRAG3_Educational")
    print("    git add -A")
    print("    git commit -m \"Initial educational release\"")
    print("    git branch -M main")
    print("    git push -u origin main")
    print()


if __name__ == "__main__":
    main()
