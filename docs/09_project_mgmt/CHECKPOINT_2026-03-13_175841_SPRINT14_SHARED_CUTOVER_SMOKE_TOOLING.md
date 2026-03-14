# Sprint 14 Shared Cutover Smoke Tooling

- Created: 2026-03-13_175841
- Updated: 2026-03-13_175841
- Timestamp: 2026-03-13_175841
- Session ID: codex-hybridrag3-cutover-smoke-20260313
- Topic: sprint14-shared-cutover-smoke-tooling

## What Changed

- Added the shared acceptance-smoke automation tool:
  - `src/tools/shared_cutover_smoke.py`
  - `tools/shared_cutover_smoke.py`
- The new tool:
  - checks `/health`, `/status`, `/auth/context`, `/dashboard`, post-dashboard session `/auth/context`, and `/admin/data`
  - records deployment mode, runtime mode, auth posture, actor/session actor, page title, and blocker text in a timestamped JSON report under `output/shared_cutover_smoke/`
  - can verify a backup bundle and optionally run a non-destructive restore drill in the same pass
  - supports `--backup-bundle latest` so operators can reuse the newest known-good backup without hand-copying paths
- Added regression coverage:
  - `tests/test_shared_cutover_smoke_tool.py`

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_shared_cutover_smoke_tool.py tests/test_shared_deployment_soak_tool.py tests/test_shared_deployment_backup_tool.py tests/test_shared_deployment_auth.py -q`
  - result: `30 passed`
- `python -m py_compile src/tools/shared_cutover_smoke.py tools/shared_cutover_smoke.py tests/test_shared_cutover_smoke_tool.py`
  - result: `passed`
- `python tools/shared_cutover_smoke.py --help`
  - result: `passed`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `713 passed, 7 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `835 passed, 6 skipped, 7 warnings`

## Open Items

- `14.2a` still needs QA.
- Actual cutover acceptance remains blocked behind Sprint `13.6` workstation credentials and authenticated-online soak evidence.
