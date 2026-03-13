# Sprint 13.5a Current Token Requirement Fix

- Created: 2026-03-13_121754
- Updated: 2026-03-13_121754
- Timestamp: 2026-03-13_121754
- Session ID: codex-hybridrag3-sprint13-5a-current-token-fix-20260313-121641
- Topic: sprint13 5a current token fix

## What Changed

- Tightened shared-launch auth gating in `src/security/shared_deployment_auth.py`.
  - `configured` now requires a current token.
  - `rotation_enabled` now requires both current and previous tokens.
  - accepted request-auth tokens now collapse to `()` when the current token is missing, so previous-token-only posture cannot masquerade as valid shared auth.
- Added focused regressions in `tests/test_shared_deployment_auth.py`.
  - direct previous-token-only readiness regression
  - previous-token-only preflight regression for `mode=online` plus `deployment_mode=production`
- Added FastAPI regressions in `tests/test_fastapi_server.py`.
  - `/auth/context` stays anonymous/open when only the previous token exists
  - production startup fails closed when only the previous token exists
- Hardened GUI seed persistence in `src/gui/panels/tuning_tab_runtime.py` and `tests/test_gui_integration_w4.py`.
  - lagging entry text can no longer overwrite a newer valid bound `IntVar` seed during large suite runs

## Tests

- `python -m pytest tests/test_shared_deployment_auth.py tests/test_gui_integration_w4.py -q`
  - `44 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - `82 passed, 1 warning`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - `699 passed, 7 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/`
  - `823 passed, 4 skipped, 7 warnings`
- Required virtual suites rerun green:
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

## Open Items

- QA needs to confirm the original previous-token-only repro is closed.
- If QA clears `13.5a`, move immediately to `13.5b -- Auth Boundary Reverify`.
