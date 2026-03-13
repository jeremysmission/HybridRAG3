# Checkpoint -- Sprint 13.1 Soak Tooling

**Timestamp:** 2026-03-13 09:25:13 -06:00  
**Sprint:** `13.1 -- Multi-User Soak and Performance Baseline`  
**Status:** `CODE COMPLETE / READY FOR QA`

## What Landed

- Added the shared deployment soak runner:
  - `src/tools/shared_deployment_soak.py`
  - `tools/shared_deployment_soak.py`
  - `tests/test_shared_deployment_soak_tool.py`
- The runner now:
  - loads questions from flat text files or the existing demo rehearsal-pack JSON format
  - calls `/health`, `/status`, `/auth/context`, `/activity/query-queue`, `/activity/queries`, and `/query`
  - records per-request totals, p50/p95/max client and server latency, queue peaks, mode counts, and error buckets
  - writes timestamped JSON evidence into `output/shared_soak/`
- Captured a first semi-live baseline artifact:
  - `output/shared_soak/2026-03-13_091702_shared_deployment_soak.json`
  - generated in-process against the real FastAPI app surfaces with deterministic query responses

## Verification

- Focused tooling verification:
  - `python -m py_compile src\tools\shared_deployment_soak.py tools\shared_deployment_soak.py tests\test_shared_deployment_soak_tool.py`
  - result: `passed`
  - `python -m pytest tests/test_shared_deployment_soak_tool.py -q`
  - result: `7 passed, 1 skipped`
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_soak_tool.py -q`
  - result: `8 passed`
- Post-change repo gate:
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `679 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/`
  - result: `796 passed, 5 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - result: `78 passed, 1 warning`
- Required virtual suites rerun and green:
  - `phase1`
  - `phase2`
  - `phase4`
  - `view_switching`
  - `setup_wizard`
  - `setup_scripts`
  - `guard_part1`
  - `guard_part2`
  - `setup_group_policy`
  - `ibit_reference`
  - `offline_isolation`

## Open Item

- Sprint `13.1` remains in progress until a workstation-backed live soak pass is recorded with the new runner. The next forward move is the real shared deployment soak, then `13.2 -- Backup, Restore, and Rollback Drill`.
