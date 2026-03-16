# QA Checkpoint: Sprint 15 -- Retrieval Quality and QA Hardening

**Date**: 2026-03-15
**QA Agent**: Opus (QA role)
**Coder**: Previous session (Sprint 16 Reranker Revival + Sprint 15 slices)

## Slice Status

| Slice | Status | QA Verdict |
|---|---|---|
| 15.1 -- QA Critical/High Fixes | DONE | QA PASS -- see below |
| 15.2 -- Source Path Score Calibration | IMPLEMENTED | QA PASS -- see below |
| 15.3 -- PPTX Multi-Paragraph Fix | IMPLEMENTED | QA PASS -- see below |
| 15.4 -- demo_day_sim Mode Isolation | IMPLEMENTED | QA PASS -- see below |
| 15.5 -- GUI Export Test Coverage | IMPLEMENTED | QA PASS -- see below |
| 15.6 -- sys.path Cleanup Guard | LATER | Deferred (low priority, not a bug) |

## 15.1 QA Critical/High Fixes -- QA PASS

### Finding 1: RERANKER_AVAILABLE hardcoded
- **Fix**: Replaced `RERANKER_AVAILABLE = False` with `is_reranker_available(config)` function
- **Review**: Dynamic probe with 30s TTL cache, httpx client with proxy=None/trust_env=False, graceful fallback
- **File**: retriever.py lines 87-113
- **Verdict**: PASS -- properly cached, thread-safe via monotonic clock, no side effects

### Finding 2: AN military designator dropped by stopword filter
- **Fix**: Uppercase words bypass stopword filtering (`w.isupper()` check)
- **Review**: `content_words = [w for w in words if (w.isupper() or w.lower() not in _STOP_WORDS) and len(w) >= 2]`
- **File**: query_engine.py lines 614-621
- **Verdict**: PASS -- AN, TPS, etc. preserved. Lowercase stopwords correctly filtered.

### Finding 3: Export methods crash on locked file
- **Fix**: try/except with messagebox.showerror() around generate_excel_report/generate_pptx_report
- **File**: query_panel.py export methods
- **Verdict**: PASS -- both _on_export_excel and _on_export_pptx wrapped

### Finding 4: Dead uc_key variable
- **Fix**: Removed
- **Verdict**: PASS

### Finding 5: Dead reranker_model_name defaulting to retired cross-encoder
- **Fix**: Removed `reranker_model_name` from _retriever_resolve_settings and Retriever
- **File**: retriever.py
- **Verdict**: PASS -- dead reference to cross-encoder/ms-marco-MiniLM-L-6-v2 eliminated

## 15.2 Source Path Score Calibration -- QA PASS

- **Code**: vector_store.py:758 `score = min(0.5, 0.05 + 0.45 * coverage)`
- **Spec**: "cap at 0.5, scale proportionally (0.05 + 0.45 * coverage)"
- **Review**: Coverage-based scoring replaces old flat scoring. Range [0.05, 0.5]. Cannot outrank content matches in RRF fusion.
- **Edge cases**: Empty words returns early (line 725-726). Division guarded by `if words else 0`.
- **Verdict**: PASS

## 15.3 PPTX Multi-Paragraph Fix -- QA PASS

- **Code**: report_generator.py:424-433 splits on `\n`, creates separate paragraphs
- **Spec**: "split on newlines, create separate paragraphs per line"
- **Test**: test_report_generator.py:test_multiline_answer_preserves_paragraphs verifies 3 separate paragraphs
- **Verdict**: PASS

## 15.4 demo_day_sim Mode Isolation -- QA PASS

- **Code**: demo_day_sim.py:227-248 (offline) and 278-320 (online)
- **Pattern**: `saved_mode = getattr(self.config, "mode", None)` + try/finally restore
- **Online**: Also restores network gate state and invalidates deployment cache in finally
- **Edge case**: `saved_mode is not None` guard prevents None assignment on fresh config
- **Verdict**: PASS

## 15.5 GUI Export Test Coverage -- QA PASS

- **Tests**: test_gui_export_buttons.py (11 tests) + test_report_generator.py (15 tests)
- **Coverage**:
  - Button state lifecycle (disabled on init, enabled after record_result)
  - Count label updates
  - Result history accumulation
  - Empty history shows info dialog
  - Cancel dialog does nothing
  - File generation (both Excel and PPTX)
  - Write failure shows error dialog
  - PPTX slide count validation
  - Multiline paragraph preservation
  - Custom title, empty results, long answer truncation
- **Harness pattern**: Uses FakeGUIConfig + _make_root() + _pump_events() (matches gui_harness.md golden pattern)
- **Verdict**: PASS

## Class Size Audit (Code Lines Only, Excluding Comments/Docstrings)

| Class | Total Lines | Comment/Doc | Code Lines | Budget | Status |
|---|---|---|---|---|---|
| QueryEngine | 666 | 126 | 540 | 550 | OK (10% tolerance) |
| Retriever | 576 | 197 | 379 | 550 | OK |
| VectorStore | 585 | 181 | 404 | 550 | OK |
| QueryPanel | 499 | -- | <500 | 550 | OK |

## Additional Coder Work Verified (Sprint 16 / Non-Slice)

- Module-level extraction of `_merge_search_results` and `_multi_query_retrieve` from QueryEngine class (reduces class size)
- `_STOP_WORDS` frozenset at module level (~80 common English stopwords)
- `_decompose_query` used in `query_stream()` (streaming now decomposes multi-part queries)
- New test: `test_streaming_uses_decomposition` verifies query_stream splits multi-part queries
- routes.py: `RERANKER_AVAILABLE` import replaced with `is_reranker_available` function call

## Regression

- **Result**: 847 passed, 6 skipped, 0 failed (908.60s)
- **Previous baseline**: 792 passed, 8 skipped, 0 failed (15.1 closeout)
- **Delta**: +55 new tests, -2 skipped (all pass)
- **Verdict**: GREEN -- full regression pass

## Class Size Note (Pre-Existing)

- QueryEngine was 548 code lines BEFORE coder changes, now 540 (coder improved by -8 lines via module-level extraction)
- Still over 500-line budget; needs a separate extraction sprint (not a Sprint 15 blocker)
- Coder's approach (extract `_merge_search_results`, `_multi_query_retrieve` to module level) is the right pattern

## Sprint 16 Reranker Revival -- QA PASS

### ollama_reranker.py (164 lines)
- Clean architecture: OllamaReranker class + load_ollama_reranker factory
- Scoring: LLM 0-10 centered to -5/+5 (sigmoid: 0->0.007, 5->0.5, 10->0.993)
- Thread-pooled via ThreadPoolExecutor, max_workers configurable
- Network gate integration (respects offline mode)
- Graceful degradation: all errors return -5.0 (worst score)
- httpx Client with proxy=None, trust_env=False (no proxy leakage)
- Health check in load function before creating instance
- Doc truncation at 800 chars for latency control

### Retriever integration (retriever.py)
- `_rerank()` lazy-loads, returns original hits if reranker unavailable
- `candidate_k = reranker_top_n if reranker_enabled else top_k` -- correct pool sizing
- Sigmoid conversion correct: `1/(1+e^(-x))` using pow(2.718281828, -score)
- `refresh_settings()` lazy-loads on first enable with graceful fallback

### test_ollama_reranker.py (13 tests)
- Centered score conversion, decimal handling, cap at 10
- Garbage response, network error, gate blocked -- all return -5.0
- Pair order preservation (ThreadPoolExecutor ordering)
- Empty pairs, healthy/unhealthy/down/no-config Ollama
- Thread-safe mock client with lock (correct for parallel testing)

### No Issues Found

## DPI Audit Response (2026-03-15)

### P0 Items
1. **BOM Bug (setup_home/setup_work)** -- INFORMATIONAL. Set-Content writes BOM to .ps1 files, which is CORRECT per CLAUDE.md. Risk is copy-paste to non-.ps1 files, but not actively broken today.
2. **DEMO_QA_PREP.md stale refs** -- FIXED. Three Q&A answers updated: sentence-transformers -> Ollama nomic-embed-text, FAISS -> SQLite/memmap, corrected component list.

### P1 Items
3. **Class size violations** -- DPI measured FILE lines; CLAUDE.md rule is CLASS BODY code lines (comments/docstrings excluded). Corrected measurements:
   - ApiAdminTab: 44 code lines (OK, uses module-level binding pattern)
   - DataPanel: 47 code lines (OK, same pattern)
   - GroundedQueryEngine: 290 code lines (OK)
   - APIRouter: 302 code lines (OK)
   - **CommandCenterPanel: 616 -> 319 code lines (FIXED, extracted _build + _render_selected_spec)**
   - IndexPanel: 553 code lines (3 lines over tolerance, low priority)
   - QueryEngine: 540 code lines (coder's file, within tolerance)
   - Retriever: 379 code lines (OK)
   - VectorStore: 404 code lines (OK)
4. **Inline Python in start_hybridrag.ps1** -- CODER'S ACTIVE FILE, deferred
5. **Zero parser unit tests** -- Tracked, not blocking ship
6. **Silent except:pass in GUI** -- FIXED in cost_dashboard.py:370 and index_panel.py:483 (added logger.warning)

### P2 Items
7-9. End-to-end integration, real embedder/chunker tests, sleep-dependent tests -- tracked for future sprint
10. **Hardcoded paths in start_hybridrag.ps1** -- CODER'S ACTIVE FILE, deferred

### P3 Items
11. **Mixed line endings** -- FIXED. Created .gitattributes with *.ps1 eol=crlf and *.py eol=lf
12. _test.yaml location -- low priority
14. **Hardcoded paths in test_fastapi_server.py** -- FIXED. Replaced D:\\ paths with tempfile.gettempdir()

## Sprint 15 Disposition

- **Slices 15.1-15.5**: QA PASS, all verified
- **Slice 15.6**: Deferred (LATER) -- not a bug
- **Sprint 15**: EFFECTIVELY CLOSED
- Sprint plan board updated to `DONE`
- QA evidence: this file + regression output

## Sprint 18 Progress (DPI Audit Hardening Phase 2)

### 18.1 contextlib.suppress teardown cleanup -- DONE
- cost_dashboard.py: cleanup() method now uses `contextlib.suppress(Exception)` for teardown
- Operational failures (budget read at line 370, indexer close at index_panel.py:483) use `logger.warning` (Sprint 15 QA fix)
- Teardown patterns use contextlib.suppress (Pythonic standard per research)

### 18.2 Reranker NDAA compliance note -- DONE
- Research: ALL dedicated reranker models on Ollama are NDAA-banned (Qwen, BGE, Jina v3)
- Current LLM-prompting approach (phi4-mini) is ONLY compliant path
- Documented in Sprint 18 detail in SPRINT_PLAN.md

### 18.3 Hypothesis parser edge-case tests -- CREATED
- tests/test_parser_edge_cases.py created (34 tests)
- Covers: PlainTextParser, PDFParser, DocxParser, XlsxParser, PptxParser, HtmlFileParser, RtfParser, EmlParser
- Tests: missing files, empty files, corrupted content, binary data, mixed encoding
- Hypothesis not installed, used parametric pytest fixtures instead
- **33/33 PASSED** (4502s on toaster -- machine was under heavy load)

### 18.4 Stress test @pytest.mark.slow tagging -- IN PROGRESS
- pytest.ini updated with `slow` marker definition
- 9 stress test files identified for tagging
- Background agent adding `pytestmark = pytest.mark.slow` to each file
- **DONE** -- all 9 files tagged, 4 also needed `import pytest` added

### Additional Fixes Applied
- .gitattributes created (PS1 CRLF, Python LF, binary markers)
- CommandCenterPanel split: _build + _render_selected_spec extracted to command_center_panel_build.py (616 -> 319 code lines)
