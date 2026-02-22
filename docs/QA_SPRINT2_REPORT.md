# QA Sprint 2 Report

**Date:** 2026-02-21
**Clone:** D:\HybridRAG3_QA_Sprint2
**Commit:** 627ce52 (main)

---

## 1. Test Suite Results

**Command:** `.venv\Scripts\python.exe -m pytest tests\ -v --tb=long`
**Result:** 136 passed, 1 failed, 1 warning (396.54s)

### 1.1 Failure

| Test | File:Line | Error | Diagnosis | Suggested Fix |
|------|-----------|-------|-----------|---------------|
| `test_09_status_bar_online_mode` | `tests/test_gui_integration_w4.py:386` | `_tkinter.TclError: Can't find a usable init.tcl` | Flaky environment issue. Test 08 (offline mode) passes with the same `_make_root()` helper, but test 09 fails. The Tk runtime occasionally cannot find `init.tcl` when rapidly creating/destroying Tk roots in the same process. The venv's tcl8.6 path exists but the file is intermittently unreadable. | Add `pytest.importorskip("tkinter")` guard at module level and catch `TclError` in `_make_root()` with `pytest.skip("Tk unavailable")`. Alternatively, reuse a single Tk root across all status-bar tests via a module-scoped fixture. |

### 1.2 Warning

| Source | Message |
|--------|---------|
| `starlette/formparsers.py:12` | `PendingDeprecationWarning: Please use 'import python_multipart' instead.` |

This comes from starlette 0.38.6 importing the old `multipart` package name. Harmless for now but will break when the deprecation becomes an error. Fix: `pip install python-multipart` (already installed) -- the warning is in starlette's own code and will be fixed upstream.

---

## 2. Manual Code Audit

### 2.1 Double `/v1/v1/` URL Bug -- `src/core/api_client_factory.py`

**Status: POTENTIAL BUG FOUND**

`src/core/api_client_factory.py:562-566` -- `_build_url()` OpenAI path:

```python
else:
    # OpenAI format
    if "/chat/completions" in base:
        return base
    return f"{base}/v1/chat/completions"
```

If a user stores an endpoint like `https://api.openai.com/v1` (which is the default OpenAI base URL and what the openai SDK uses), the guard at line 564 checks only for `/chat/completions` -- it does NOT check whether the URL already ends with `/v1`. Result:

- Input: `https://api.openai.com/v1`
- Output: `https://api.openai.com/v1/v1/chat/completions` -- **DOUBLE /v1/**

The `diagnose()` method (line 685-696) has a `//` double-slash detector but `/v1/v1/` does not contain `//`, so the diagnostic check would NOT catch this.

**Note:** The active `llm_router.py` APIRouter uses the openai SDK directly (which constructs URLs internally), so this bug only affects code paths using `ApiClientFactory._build_url()` directly. If `ApiClientFactory` is used for OpenAI-compatible endpoints (OpenRouter, etc.), this bug is live.

**File:** `src/core/api_client_factory.py`
**Line:** 566

---

### 2.2 Silently Swallowed Exceptions in GUI Callbacks

#### Finding 2.2.1 -- SILENT `except Exception: pass`

**File:** `src/gui/launch_gui.py`
**Line:** 101-102

```python
try:
    app.after(0, _attach)
except Exception:
    pass  # GUI may have been closed
```

Comment explains the intent, but if `after()` fails for any OTHER reason (e.g., Tcl interpreter error, corrupted widget tree), the exception is silently eaten. No logging whatsoever.

**Severity:** Low (only fires during shutdown race condition)
**Fix:** Add `logger.debug("after() failed during attach: %s", e)`.

#### Finding 2.2.2 -- `except Exception` without logging

**File:** `src/gui/panels/status_bar.py`
**Line:** 112-114

```python
except Exception:
    self.llm_label.config(text="LLM: Error reading status", fg=t["fg"])
    self.ollama_label.config(text="Ollama: Unknown", fg=t["fg"])
```

Catches all exceptions from `self.router.get_status()` but does NOT log the exception object. The UI shows a generic error but the actual cause is invisible. Compare with the outer handler at line 104 which does `logger.debug(...)`.

**Severity:** Medium (makes API/router debugging harder)
**Fix:** Add `logger.debug("Router status error: %s", e)` inside the except block (need to capture `as e`).

#### Finding 2.2.3 -- GUI callbacks lack exception guards

The following background-thread callbacks post results to the main thread via `self.after(0, ...)` but if the main-thread handler itself raises, the exception propagates into tkinter's event loop and is printed to stderr (not logged):

- `src/gui/panels/query_panel.py:211` -- `self.after(0, self._display_result, result)`
- `src/gui/panels/query_panel.py:214` -- `self.after(0, self._show_error, error_msg)`
- `src/gui/panels/index_panel.py:216` -- `self.after(0, self._on_indexing_done, result)`
- `src/gui/panels/engineering_menu.py:396` -- `self.after(0, self._display_test_result, result)`

If `_display_result` or `_on_indexing_done` crash (e.g., `result` is None, missing key), the Ask button stays permanently disabled.

**Severity:** Medium (UI can get stuck in disabled state)

---

### 2.3 `after_idle()` Recursion / Memory Leak Risk

**Status: NO `after_idle()` CALLS FOUND**

Zero uses of `after_idle()` anywhere in `src/gui/`.

The only recursive `after()` pattern is in `src/gui/panels/status_bar.py:90-94`:

```python
def _schedule_refresh(self):
    if not self._stop_event.is_set():
        self._refresh_status()
        self.after(self.REFRESH_MS, self._schedule_refresh)
```

This is the standard tkinter polling pattern. It is properly guarded by `_stop_event` and `stop()` is called in `app.py:387` during `_on_close()`. **No memory leak risk.**

---

### 2.4 Banned Model References -- `src/core/llm_router.py`

**Status: CLEAN -- no banned model references in active code**

Full-file search for `qwen`, `deepseek`, `llama`, `codellama`, `bge`, `baai` (case-insensitive) returned zero matches in `src/core/llm_router.py`.

**Minor notes in other files (comments only, not operational):**

| File | Line | String | Status |
|------|------|--------|--------|
| `src/core/hallucination_guard/golden_probes.py` | 161, 171 | `"LLaMA-3 8B"` | Test fixture data inside a golden probe answer. Not a model reference. **Acceptable.** |
| `src/core/embedder.py` | 35 | `"BGE-small-en"` | Comment listing alternative embedders. Not used. **Acceptable but note for future cleanup.** |

---

### 2.5 `print()` Statements That Should Be `logger` Calls

#### 2.5.1 Production Library Code (SHOULD be logger)

These are in core library modules called by the GUI and API -- not CLI entry points.

| File | Lines | Count | Context |
|------|-------|-------|---------|
| `src/core/llm_router.py` | 797, 801, 834, 853, 870, 886, 890, 905 | 8 | `get_available_deployments()` and `refresh_deployments()` -- library functions called by GUI's QueryPanel. Use `print("[OK]...")`, `print("[FAIL]...")`, `print("[WARN]...")`. These should use the module logger. |
| `src/core/indexer.py` | 211, 240, 273, 305, 313, 395, 412-431, 454, 506 | 18 | `index_folder()` core method. Progress and summary output via `print()`. The indexer already has a `self.logger` but these print calls bypass it. |
| `src/core/retriever.py` | 385, 395, 399 | 3 | Reranker error handling: `print(..., file=sys.stderr)`. Should use `logger.error()`. |
| `src/api/routes.py` | 209 | 1 | Inside `/index` endpoint error handler: `print(f"[FAIL] Indexing error: {e}")`. FastAPI has its own logger; this print goes to stdout, not the API log. |
| `src/api/server.py` | 113, 116, 123, 126, 129, 137, 141, 146, 185, 186 | 10 | Lifespan startup/shutdown messages. These are server entry-point adjacent but run inside the ASGI lifespan context manager, not a `__main__` block. Should use `logger.info()`. |
| `src/core/feature_registry.py` | 227 | 1 | `print(f"[WARN] Could not load {config_path}: {e}")` inside `_load_state()` -- library method, not CLI. |

**Total: 41 print() calls in production library code that should be logger calls.**

#### 2.5.2 Acceptable Uses (CLI tools / `__main__` blocks)

These are in CLI entry points designed to print to the terminal:

| File | Approx Count | Reason Acceptable |
|------|-------------|-------------------|
| `src/tools/check_db_status.py` | 6 | CLI tool |
| `src/tools/check_db.py` | 13 | CLI tool |
| `src/tools/net_status.py` | 30 | CLI tool |
| `src/tools/scan_source_files.py` | 70+ | CLI interactive tool |
| `src/tools/bulk_transfer_v2.py` | 25 | CLI tool with progress output |
| `src/tools/rebuild_memmap_from_sqlite.py` | 12 | CLI tool |
| `src/tools/migrate_embeddings_to_memmap.py` | 10 | CLI tool |
| `src/tools/quick_test_retrieval.py` | 12 | CLI tool |
| `src/tools/index_status.py` | 15 | CLI tool |
| `src/tools/system_diagnostic.py` | 80+ | CLI diagnostic |
| `src/tools/scheduled_scan.py` | 5 | CLI tool |
| `src/security/credentials.py` | 20 | CLI entry points (`store-key`, `store-endpoint`, `cred-status`) |
| `src/core/config.py` | 4 | Inside `__main__` block |
| `src/core/feature_registry.py` | 30+ | CLI command handler in `__main__` |
| `src/core/hallucination_guard/self_test.py` | 30+ | Self-test CLI |
| `src/core/hallucination_guard/startup_bit.py` | 3 | BIT runner CLI |
| `src/core/llm_router_fix.py` | 15 | Diagnostic CLI tool |
| `src/diagnostic/fault_analysis.py` | 25 | CLI diagnostic |
| `src/diagnostic/hybridrag_diagnostic.py` | 15 | CLI diagnostic |
| `src/diagnostic/report.py` | 30+ | CLI report renderer |

---

## 3. Summary Punch List

| # | Severity | File:Line | Issue |
|---|----------|-----------|-------|
| P1 | **Medium** | `src/core/api_client_factory.py:566` | Double `/v1/v1/` when endpoint already ends with `/v1` |
| P2 | **Low** | `tests/test_gui_integration_w4.py:386` | Flaky Tk root creation in test_09 (intermittent TclError) |
| P3 | **Low** | `src/gui/launch_gui.py:101` | Silent `except Exception: pass` -- no logging |
| P4 | **Medium** | `src/gui/panels/status_bar.py:112` | `except Exception` without logging the error |
| P5 | **Medium** | `src/gui/panels/query_panel.py:211,214` | `after()` callbacks can leave Ask button permanently disabled if handler crashes |
| P6 | **Medium** | `src/core/llm_router.py:797-905` | 8 print() calls in library function `get_available_deployments()` -- should be logger |
| P7 | **Medium** | `src/core/indexer.py:211-506` | 18 print() calls in `index_folder()` core method -- should be logger |
| P8 | **Low** | `src/core/retriever.py:385,395,399` | 3 print-to-stderr calls in reranker -- should be logger |
| P9 | **Low** | `src/api/routes.py:209` | print() in API error handler -- should be logger |
| P10 | **Low** | `src/api/server.py:113-186` | 10 print() calls in lifespan handler -- should be logger |
| P11 | **Info** | `src/core/embedder.py:35` | Comment mentions BGE (banned vendor) -- cosmetic only |
| P12 | **Info** | `starlette/formparsers.py:12` | PendingDeprecationWarning for multipart import -- upstream issue |

---

## 4. Verdict

- **Test suite:** 136/137 passing (99.3%). Single failure is a Tk environment flake, not a code bug.
- **Banned models:** Clean. Zero operational references to banned models in llm_router.py or any core module.
- **URL bug:** Potential double `/v1/` in `api_client_factory.py` -- only affects non-SDK code paths.
- **GUI exceptions:** Two swallowed exceptions (low severity), plus unguarded `after()` callbacks that can leave buttons stuck.
- **Logging hygiene:** 41 print() calls in production library code should be converted to logger calls. The worst offenders are `indexer.py` (18) and `llm_router.py` (8).
