# Sprint 13.5 Checkpoint -- Shared Launch Auth And Preflight

**Timestamp:** 2026-03-13 11:09 America/Denver  
**Session ID:** `codex-hybridrag3-sprint13-5-shared-launch-auth-preflight-20260313-110943`  
**Status:** `IMPLEMENTED / READY FOR QA`

## What Changed

- Added a canonical shared launch auth resolver:
  - `src/security/shared_deployment_auth.py`
- Added a shared launch readiness tool:
  - `src/tools/shared_launch_preflight.py`
  - `tools/shared_launch_preflight.py`
- Threaded the new auth source through:
  - `src/api/auth_identity.py`
  - `src/api/browser_session.py`
  - `src/api/server.py`
  - `src/api/routes.py`
  - `src/api/web_dashboard.py`
  - `src/gui/helpers/mode_switch.py`
- Extended the desktop Command Center:
  - `src/gui/command_center_runtime.py`
  - `src/gui/command_center_registry.py`
  - `src/gui/panels/command_center_panel.py`
  - new GUI entry points:
    - `rag-shared-launch`
    - `rag-store-shared-token`

## Functional Outcome

- Shared API auth no longer depends on env-only process setup.
- Production startup can enforce a keyring-backed shared token.
- Browser login and session fallback now accept keyring-backed shared tokens and previous rotated tokens.
- Runtime safety/admin surfaces now report the active shared auth source.
- Operators can persist `online` plus `production` posture and run a shared launch readiness check from either:
  - `python tools/shared_launch_preflight.py`
  - the desktop `Command Center`

## Verification

- `python tests\virtual_test_phase1_foundation.py`
  - `55 PASS, 0 FAIL`
- `python tests\virtual_test_view_switching.py`
  - `51 PASS, 0 FAIL`
- `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_auth.py tests/test_mode_switch_runtime.py tests/test_command_center_panel.py -q`
  - `25 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - `80 passed, 1 warning`
- `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -q`
  - `40 passed`
- `.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - `738 passed, 4 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - `818 passed, 4 skipped, 7 warnings`

## Remaining Open Items

- Sprint 13 is still blocked at the PM level until the live workstation reruns the shared launch path with the new tooling and captures fresh soak evidence showing authenticated online posture.
- The live workstation ceiling is still only validated at `concurrency=1`.
- Next operational move:
  - store the shared token if needed
  - run `python tools/shared_launch_preflight.py --apply-online --apply-production --fail-if-blocked`
  - rerun the live soak baseline and compare against the prior `13.4` artifacts
