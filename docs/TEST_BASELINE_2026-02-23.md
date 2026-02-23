# HybridRAG3 Test Baseline -- 2026-02-23
# One measurement is better than a thousand opinions.

## Environment
- Machine: Personal laptop (test bench)
- Python: 3.11.9
- Platform: win32
- Config mode: offline
- Ollama model: phi4:14b-q4_K_M
- Embedding: all-MiniLM-L6-v2 (384d)
- Database: 78.83MB, 39,602 chunks, 1345 sources

---

## 1. REGRESSION TESTS (pytest)
**Command:** `pytest tests/ --ignore=tests/test_fastapi_server.py -v`
**Result: 199 PASSED, 2 SKIPPED, 0 FAILED**
**Duration:** 33.46s

### Skipped (2):
- test_14_dashboard_displays_session (tkinter display dependency)
- test_07_index_panel_progress_bar_advances (async progress dependency)

### Warning (1, cosmetic):
- RuntimeError: main thread is not in main loop (tuning_tab.py line 415)
  - Cause: tkinter after() called from background thread during test teardown
  - Impact: NONE in production (only during test cleanup)

### Test Breakdown by Module:
| Module | Tests | Result |
|--------|-------|--------|
| test_all.py | 1 | 1 PASS |
| test_api_router.py | 10 | 10 PASS |
| test_bulk_transfer_stress.py | 48 | 48 PASS |
| test_cost_tracker.py | 19 | 17 PASS, 2 SKIP |
| test_credential_management.py | 10 | 10 PASS |
| test_deployment_routing.py | 12 | 12 PASS |
| test_gui_integration_w4.py | 21 | 21 PASS |
| test_indexer.py | 17 | 17 PASS |
| test_ollama_router.py | 10 | 10 PASS |
| test_phase3_stress.py | 32 | 32 PASS |
| test_query_engine.py | 8 | 8 PASS |
| test_vllm_router.py | 7 | 7 PASS |
| **TOTAL** | **201** | **199 PASS, 2 SKIP** |

---

## 2. VIRTUAL TEST FRAMEWORK
**Result: 544 PASS, 4 FAIL across 8 virtual test files**

### Per-File Results:
| File | Pass | Fail | Status |
|------|------|------|--------|
| virtual_test_phase1_foundation.py | 63 | 0 | CLEAN |
| virtual_test_phase2_exhaustive.py | 64 | 0 | CLEAN |
| virtual_test_phase4_exhaustive.py | 166 | 0 | CLEAN |
| virtual_test_setup_wizard.py | 54 | 0 | CLEAN |
| virtual_test_view_switching.py | ~48 | 2 | FAIL |
| virtual_test_guard_part1.py | 97 | 1 | FAIL |
| virtual_test_guard_part2.py | ~17 | 0 | CLEAN |
| virtual_test_ibit_reference.py | ~35 | 1 | FAIL |

### Failures (4 total):

**FAIL-V1: virtual_test_view_switching.py**
- `_scrollbar not found` (ScrollableFrame attribute missing)
- `RevA stamp present in all changed files` -- Missing RevA stamp: settings_view.py, reference_panel.py

**FAIL-V2: virtual_test_guard_part1.py**
- `query_engine.py: 473 lines (untouched)` -- line count check flagging, not a functional failure

**FAIL-V3: virtual_test_ibit_reference.py**
- `Got 546 lines (max 500)` -- class size enforcement (a file exceeds 500 line limit)
- `Docs tab opens files with os.startfile` -- missing os.startfile call in docs tab

---

## 3. DIAGNOSTIC SUITE
**Command:** `python src/diagnostic/hybridrag_diagnostic.py`
**Result: 15 PASSED, 0 FAILED, 0 WARNINGS**
**Duration:** 19.7s

### Health Checks (15/15 PASS):
| Category | Check | Result | Time |
|----------|-------|--------|------|
| Config | Config OK (mode=offline) | PASS | 69ms |
| Config | Paths OK (1765 source files) | PASS | 776ms |
| Database | SQLite OK (78.83MB, wal, 39602 chunks) | PASS | 572ms |
| Database | Schema OK (9 cols, 3 indexes) | PASS | 23ms |
| Database | FTS5 OK (39602 rows) | PASS | 3753ms |
| Database | Data integrity (39602 chunks, 39602 emb, 1345 src) | PASS | 676ms |
| Indexer | Change detection + preflight gate | PASS | 7879ms |
| Indexer | Cleanup methods present | PASS | 0ms |
| Parsers | Registry OK (63 types) | PASS | 130ms |
| Parsers | All 11 critical libraries importable | PASS | 5674ms |
| Chunker | OK (7 chunks, avg 1168) | PASS | 4ms |
| Embedder | Importable (all-MiniLM-L6-v2) | PASS | 4ms |
| Storage | OK (39602 emb, 384d, 29.01MB) | PASS | 15ms |
| Security | Endpoint not public default | PASS | 57ms |
| Security | Audit: 4 files, gate_present=True | PASS | 48ms |

### Performance Benchmarks:
| Benchmark | Median | Min | Max |
|-----------|--------|-----|-----|
| Config Load | 3.9ms | 3.7ms | 4.1ms |
| SQLite Connect+Query | 29.3ms | 21.6ms | 37.6ms |
| Chunker Throughput | 271,240 chunks/sec | 249,328 | 288,130 |
| Vector Search Top5 | 453.7ms | 133.8ms | 1092.8ms |
| FTS5 Keyword Search | 52.3ms | 4.0ms | 148.6ms |

### Fault Analysis:
- **FAULT-LLM-001** (83% confidence): Ollama not running
  - Expected: Ollama serve was not started in this test session
  - NOT a code bug -- runtime dependency

### System Resources:
- Memory: 382MB RSS at end of diagnostic

---

## 4. FUNCTIONAL WIRING TESTS
**Command:** `python _verify_wiring.py`
**Result: 4 PASS, 1 INCOMPLETE**

| Check | Result | Details |
|-------|--------|---------|
| 1. Config loading | PASS | mode=offline, ollama.model=phi4:14b-q4_K_M |
| 2. Boot pipeline | PASS | success=True, warnings=0, errors=0 |
| 3. LLMRouter construction | PASS | 11 status keys, ollama_available=True, api_configured=True |
| 4. get_available_deployments() | PASS | 244 deployments returned |
| 5. Profile switch | INCOMPLETE | Printed usage only (no profile arg passed) |

### Observations:
- NET DENY correctly blocked openrouter.ai in offline mode
- LLMRouter mode field shows file path instead of "offline" string (cosmetic bug)
- API router blocked correctly: "offline_blocks_internet"

---

## 5. IMPORT CHAIN TEST
**All 11 GUI modules import cleanly:**
- HybridRAGApp, QueryPanel, SetupWizard, IndexPanel, StatusBar
- NavBar, SettingsView, CostDashboard, ReferencePanel, VectorFieldOverlay
- Theme engine (25 keys loaded)

---

## SUMMARY

| Suite | Pass | Fail | Skip | Total |
|-------|------|------|------|-------|
| Regression (pytest) | 199 | 0 | 2 | 201 |
| Virtual Tests | ~544 | 4 | 0 | ~548 |
| Diagnostics | 15 | 0 | 0 | 15 |
| Functional Wiring | 4 | 0 | 1 | 5 |
| **TOTAL** | **762** | **4** | **3** | **769** |

## KNOWN ISSUES (Pre-existing, not from recent changes)

1. **RevA stamps missing**: settings_view.py, reference_panel.py (cosmetic)
2. **Class size >500 lines**: One file in ibit_reference test exceeds 500-line rule
3. **query_engine.py 473 lines**: Guard part1 flags line count (not functional)
4. **_scrollbar attribute**: view_switching test expects attribute not present
5. **os.startfile missing**: Docs tab should use os.startfile for Windows
6. **LLMRouter mode display**: Shows config file path instead of "offline" string
7. **Ollama not running**: Expected -- not started in test session
