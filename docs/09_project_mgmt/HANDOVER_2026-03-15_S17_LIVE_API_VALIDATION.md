# Handover: 2026-03-15 -- Sprint 17 Live API + Code Quality

**Time**: 2026-03-15 13:30 America/Denver
**Topic**: Sprint 15 closure, Sprint 17 (API tests + class size + DPI fixes)
**Regression**: pending final (GUI suite: 34 passed, 1 skip; prior full: 848+10 skip, 0 fail)

## Status Summary

### Sprint 15 -- DONE
- 5/5 slices closed (15.1-15.5)
- 13 new GUI export button tests

### Sprint 16 -- DONE (prior session)
- Ollama reranker, corrective reformulation, report export

### Sprint 17 -- IN PROGRESS (6/7 slices done)

| Slice | Status | Notes |
|-------|--------|-------|
| 17.1 Live Demo Preflight | DONE (partial) | 15/16 passed. OpenRouter key limit 403 (not code bug) |
| 17.2 Online Query E2E Test | DONE (gated) | 5 tests in test_live_api_e2e.py, skip without RUN_LIVE_API_TESTS=1 |
| 17.3 Cost Tracker Validation | DONE (gated) | Included in test_live_api_e2e.py |
| 17.4 FastAPI /query Smoke | DONE (gated) | Included in test_live_api_e2e.py |
| 17.5 Generation Autotune | LATER | Costs real tokens, BEAST-dependent |
| 17.6 Inline Python Extraction | DONE | start_hybridrag.ps1 -> scripts/_startup_checks.py |
| 17.7 Class Size Enforcement | DONE | All classes under 550 tolerance |

### Class Size Results (all under budget)

| Class | Before | After | File |
|-------|--------|-------|------|
| QueryEngine | 531 | 481 | query_engine.py (extracted corrective retrieval) |
| ConversationThreadStore | 805 | 512 | query_threads.py (extracted _record_turn_impl + rewrap) |
| IndexPanel | 506 | 375 | index_panel.py (extracted _build_widgets) |
| CommandCenterPanel | 616 | 319 | command_center_panel.py (QA did this one) |

### QA Session (parallel, merged on disk)
- Modified: DEMO_QA_PREP.md, cost_dashboard.py, index_panel.py, command_center_panel.py, test_fastapi_server.py
- Created: command_center_panel_build.py, .gitattributes, QA_CHECKPOINT
- QA regression: 930 tests, 0 failures

## Lessons Learned

1. **Class size drift is silent** -- ConversationThreadStore grew to 805 lines with nobody noticing.
   Add a CI check or periodic sweep.

2. **Widget build methods are always extractable** -- pure construction code with no logic.
   Pattern: `_build_*` -> companion `_build.py` module. QA used same pattern.

3. **Inline Python in PS1 is a maintenance trap** -- two separate `python -c` blocks
   doing the same `load_config()` call. Consolidated into one reusable script.

4. **Env-gated tests are the right API test pattern** -- skip cleanly in CI,
   light up on demand. No mock/real confusion.

## Files Changed This Session

| File | Change |
|------|--------|
| tests/test_gui_export_buttons.py | NEW -- 13 GUI export button tests |
| tests/test_live_api_e2e.py | NEW -- 5 env-gated live API tests |
| tests/test_query_engine.py | Updated 4 tests to use module-level functions |
| src/core/query_engine.py | Extracted corrective retrieval (481 code lines) |
| src/api/query_threads.py | Extracted _record_turn_impl + rewrap (512 code lines) |
| src/gui/panels/index_panel.py | Extracted _build_widgets (375 code lines) |
| src/gui/panels/index_panel_build.py | NEW -- widget construction companion |
| scripts/_startup_checks.py | NEW -- startup diagnostic script |
| start_hybridrag.ps1 | Replaced 2 inline Python blocks with script calls |
| docs/09_project_mgmt/SPRINT_PLAN.md | S15 DONE, S17 detail |
| docs/09_project_mgmt/CHECKPOINT_2026-03-15_S15_COMPLETE.md | NEW |
| docs/09_project_mgmt/HANDOVER_2026-03-15_S17_LIVE_API_VALIDATION.md | This file |

## Recovery Instructions

If session dies:
1. Read this file + SPRINT_PLAN.md Sprint 17 section
2. Run regression: `.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
3. If API key funded: `RUN_LIVE_API_TESTS=1 pytest tests/test_live_api_e2e.py -v`
4. Remaining work: Sprint 17.5 (autotune, BEAST), parser unit tests (future sprint)
