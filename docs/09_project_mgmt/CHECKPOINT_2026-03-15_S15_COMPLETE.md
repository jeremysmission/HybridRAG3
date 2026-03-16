# Checkpoint: Sprint 15 Complete -- Retrieval Quality and QA Hardening

**Date**: 2026-03-15
**Regression**: 849 passed, 4 skipped, 0 failed (non-FastAPI suite)

## Slices Completed

### 15.1 QA Critical/High Fixes (this session, earlier)
- `RERANKER_AVAILABLE` hardcoded True -> dynamic `is_reranker_available(config)` with 30s TTL
- AN military designator dropped by stopword filter -> uppercase words bypass stopwords
- Export methods crash on locked file -> try/except with messagebox.showerror()
- Dead `uc_key` variable in `record_result()` -> removed
- Dead `reranker_model_name` defaulting to retired cross-encoder -> removed

### 15.2 Source Path Score Calibration (done in Sprint 16)
- `vector_store.py:758`: `min(0.5, 0.05 + 0.45 * coverage)` -- capped at 0.5

### 15.3 PPTX Multi-Paragraph Fix (done in Sprint 16)
- `report_generator.py:424-433`: splits on `\n`, creates separate paragraphs per line

### 15.4 demo_day_sim Mode Isolation (done in Sprint 16)
- `demo_day_sim.py:227-248`: `saved_mode` + `finally` block for both offline and online

### 15.5 GUI Export Test Coverage (this session)
- New file: `tests/test_gui_export_buttons.py` (13 tests)
- Covers: button state lifecycle (disabled->enabled), record_result history,
  Excel/PPTX generation via GUI buttons, empty-history info dialog,
  cancel-dialog no-op, write-failure error dialog, PPTX slide count

### 15.6 sys.path Cleanup Guard -- LATER (deferred, low priority)

## Sprint 15 Exit Criteria Status
- [x] All QA HIGH/CRITICAL findings closed with regression proof
- [x] Source path search scores recalibrated (capped at 0.5)
- [x] PPTX export renders multi-paragraph answers correctly
- [x] demo_day_sim cannot leave config in a dirty state
- [x] Basic export test coverage exists (13 tests)

## What's Next

Sprint 15 is DONE. Next options:
1. Sprint 16 already done (Reranker Revival) -- checkpoint exists
2. Sprint 13.7/13.8 (Load Ceiling Decision / Launch Verdict Refresh) -- blocked on env
3. Sprint 14 (Shared Launch Acceptance) -- blocked on Sprint 13
4. **New: Leverage GPT-4o API access** for live online testing:
   - `tools/demo_day_sim.py --full --online` (full preflight with real API)
   - `tools/demo_transcript.py` (live demo flow)
   - `tools/generation_autotune_live.py` (parameter sweep, 160 API calls)
   - Sprint 5 final online demo hardening pass
   - Sprint 13.6 authenticated-online soak rerun

## Machine State
- Toaster: 16 GB RAM, Intel Iris Xe, CPU-only Ollama
- BEAST ETA: 2026-03-15 or 2026-03-17
- GPT-4o API access now available (new since last checkpoint)
