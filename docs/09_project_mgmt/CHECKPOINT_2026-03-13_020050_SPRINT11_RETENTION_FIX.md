# Sprint 11 Retention Fix Checkpoint

- Timestamp: 2026-03-13 02:00 America/Denver
- Session: codex-hybridrag3-sprint11-retention-fix-20260313-020050
- Repo: `D:\HybridRAG3`
- Status: Sprint 11 conversation-history retention fix landed and green

## What Changed

- Fixed `src/api/query_threads.py` so `_now_iso()` is monotonic per process.
- This removes timestamp-order collisions that could prune the wrong conversation thread when `HYBRIDRAG_HISTORY_MAX_THREADS` is low and multiple turns are written within the same clock tick.

## Verification

- `.venv\Scripts\python.exe -m py_compile src/api/query_threads.py tests/test_query_threads.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - `passed`
- `.venv\Scripts\python.exe -m pytest tests/test_query_threads.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py -q`
  - `107 passed, 1 warning in 6.32s`
- `python tests\virtual_test_phase1_foundation.py`
  - `55 PASS, 0 FAIL`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - `653 passed, 6 skipped, 7 warnings in 101.04s`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - `758 passed, 5 skipped, 7 warnings in 122.80s`

## Open Items

- The previously written Sprint 11 handoff can now be treated as trustworthy again after this fix.
- Next forward move remains whatever the primary agent/QA wants after Sprint 11 validation; the existing handoff points at `Sprint 12.1 -- Secret Handling and Rotation`.
