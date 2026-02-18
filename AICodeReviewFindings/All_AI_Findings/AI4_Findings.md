# AI4 Findings Report — HybridRAG3 (Hybrid3) Handover Review
**Reviewer:** AI4  
**Date:** 2026-02-17  

This report reviews the provided handover and the code snapshot in the attached repo zip, identifies defects (including additional ones beyond the handover), and provides a **redesign-style** solution set (whole-file replacements, not micro-patches).

---

## 0) Handover alignment (what I verified vs the handover)

The handover states Phase 4 included: kill switch consolidation (HYBRIDRAG_OFFLINE checked only in NetworkGate.configure), API version alignment to **2024-02-02**, mojibake fixes, and notes a **known issue**: `test_azure.py` uses `azure_api_key` instead of consolidated `api_key`. fileciteturn1file0L10-L19 fileciteturn1file0L49-L56

I confirmed the snapshot I tested contained **the same class of issue**: the Azure smoke test script was still using the old keyring names. I fixed this in the redesign set (see §2.6).

---

## 1) Exhaustive virtual test (front-to-back) — what I ran and what happened

### 1.1 Initial state (as-provided)
Running `pytest` immediately failed during **test collection** due to script-style files that:
- call `sys.exit()` at import time, and/or
- access keyring at import time on systems without a keyring backend.

This prevented **any meaningful “front-to-back” testing** until the harness issues were redesigned.

### 1.2 After redesign fixes
After redesigning the test harness + packaging surface + config normalization + a few correctness fixes, I ran:

- `python -m pytest -q`

Result: **44 passed** (2 warnings remain from docstring escape sequences).

---

## 2) Bugs found (including additional ones) and redesigned solutions

### 2.1 Pytest collection was broken by script-style “tests”
**Symptoms**
- `tests/test_audit.py` and `tests/test_redesign.py` execute large scripts at import time and call `sys.exit()` (collection abort).
- Root `test_azure.py` and `tools/py/test_api_verbose.py` were named like tests and were collected, but are actually manual scripts that require OS keyring backends.

**Redesign**
- Manual scripts were **moved/renamed** to not match pytest’s `test_*.py` module pattern.
- Script behavior was guarded behind `if __name__ == "__main__": ...`.
- Utilities were renamed so unit tests can run everywhere.

---

### 2.2 `src.core` package surface was empty, breaking expected imports
**Symptoms**
Many tests expected `import src.core as core; core.indexer ...`, but `src/core/__init__.py` was empty, so attribute access failed.

**Redesign**
- Implemented `src/core/__init__.py` using **lazy exports** (`__getattr__`) to provide a stable, ergonomic public surface without heavy eager imports.

---

### 2.3 Config schema mismatch vs tests/expectations
**Symptoms**
The config template lacked keys that the tests (and some tools) assume exist (e.g., `api.provider`, `api.auth_scheme`, plus a top-level `http:` section).

**Redesign**
- Added a `normalize_config()` step in `boot.load_config()` so older YAML shapes still work.
- Updated `config/default_config.yaml` template to reflect the normalized in-memory schema (without storing secrets).

---

### 2.4 `HttpResponse.json()` returned diagnostics instead of a dict
**Symptoms**
Tests and typical calling code expect `response.json()` to return a **dict** (or empty dict), but implementation returned a diagnostic structure.

**Redesign**
- `HttpResponse.json()` now returns `dict` or `{}`.
- Full forensic details are available via a `json_diagnostic` property.

---

### 2.5 Online APIRouter was blocked by default NetworkGate offline singleton
**Symptoms**
`NetworkGate` defaults to OFFLINE (fail-closed). In unit tests (and programmatic uses that don’t run boot), creating an `APIRouter` immediately failed the gate check and left `client=None`, causing online-path tests to return `None`.

**Redesign**
- In `APIRouter.__init__`, if config mode is explicitly `"online"` and the gate singleton is still OFFLINE, it auto-configures the gate for the configured endpoint (idempotent).
- Per-call checks remain in place, so policy is still enforced.

---

### 2.6 Known issue from the handover: Azure smoke test credential names
The handover’s known issue #1: `test_azure.py` uses `azure_api_key` instead of consolidated `api_key`. fileciteturn1file0L49-L52

**Redesign**
- Converted the file into a proper **manual smoke script** (`tools/py/azure_smoke.py`) that uses:
  - keyring service: `hybridrag`
  - keys: `endpoint`, `api_key`
- Removed the pytest-collectable naming.

---

### 2.7 Text extraction “binary garbage” heuristic was too permissive
**Symptoms**
`Indexer._validate_text()` accepted binary-like strings containing repeated PNG headers because the “normal char” ratio exceeded the threshold.

**Redesign**
- Reject immediately on NUL bytes.
- Use a non-printable ratio heuristic (allowing whitespace) and a minimum alnum ratio.

---

### 2.8 Hygiene issues (still worth fixing)
- Two `DeprecationWarning: invalid escape sequence` warnings from docstrings in tools modules. (Low severity, but easy to clean.)
- A remaining script (`tools/py/index_status.py`) still contains bare `except:` blocks, matching the handover’s “remaining bare excepts” theme. fileciteturn1file0L52-L56

---

## 3) Redesign deliverable contents

This zip includes:
1) `AI4_Findings.md` (this report)
2) `redesign_files/` — whole-file replacements for the redesigned solution.

Apply by replacing files in your repo with the versions under `redesign_files/` (preserving paths).

### Files included
- `src/core/__init__.py`
- `src/core/boot.py`
- `src/core/http_client.py`
- `src/core/indexer.py`
- `src/core/llm_router.py`
- `src/progress_wrapper.py`
- `config/default_config.yaml`
- `tools/py/azure_smoke.py`
- `tools/py/api_verbose_check.py`

---

## 4) Final note on “virtual testing”
I **did** run the full Python test suite end-to-end after redesign changes (44 passing).  
I cannot execute the Windows PowerShell launchers or validate Windows Credential Manager behavior inside this Linux sandbox, but the redesign explicitly removes OS-dependent keyring calls from import-time code paths so tests remain portable.

---
**AI4**
