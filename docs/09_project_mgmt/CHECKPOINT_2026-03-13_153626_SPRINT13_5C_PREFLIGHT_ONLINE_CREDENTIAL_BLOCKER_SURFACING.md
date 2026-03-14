# Checkpoint -- Sprint 13.5c Preflight Online-Credential Blocker Surfacing

- Created: 2026-03-13_153626
- Updated: 2026-03-13_153626
- Timestamp: 2026-03-13_153626
- Session ID: codex-hybridrag3-sprint13-5c-preflight-20260313-153556
- Topic: Sprint 13 5c Preflight Online Credential Blocker Surfacing

## What Changed

- Completed `13.5c -- Preflight Online-Credential Blocker Surfacing`.
- Extended `src/security/shared_deployment_auth.py` so the shared-launch snapshot now reports:
  - previous-token source/configured state
  - online API readiness
  - online API key, endpoint, and deployment sources
  - operator-facing next-step hints when readiness is blocked
- This removes the need for a separate manual credential probe just to explain why the shared-launch preflight is blocked.
- Updated regressions in:
  - `tests/test_shared_deployment_auth.py`
  - `tests/test_query_threads.py`
- Synced planning records:
  - `docs/09_project_mgmt/SPRINT_PLAN.md`
  - `docs/09_project_mgmt/PM_TRACKER_2026-03-12_110046.md`

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_auth.py -q`
  - result: `10 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -k "auth_context_does_not_treat_previous_token_without_current_primary_as_authenticated or production_startup_rejects_previous_token_without_current_primary" -q`
  - result: `2 passed, 80 deselected, 1 warning`
- `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -k "api_auth_source or keyring_token_required or login_accepts_keyring_backed_shared_token" -q`
  - result: `2 passed, 38 deselected`
- `.venv\Scripts\python.exe -m pytest tests/test_command_center_panel.py -q`
  - result: `8 passed`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `829 passed, 4 skipped, 7 warnings`

## Open Items

- Ready for QA.
- `13.6 -- Live Authenticated-Online Soak Refresh` remains blocked by missing shared token and online API credentials on this workstation.
