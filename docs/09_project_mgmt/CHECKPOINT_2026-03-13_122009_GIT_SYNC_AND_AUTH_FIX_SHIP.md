# CHECKPOINT -- 2026-03-13 12:20 America/Denver

## Status

- `SHIPPED`
- Private repo pushed: `8d59b98`
- Educational repo pushed: `dc2b999`

## What Landed

- Shared-launch auth now requires a current token before the deployment counts as configured or launch-ready.
- Previous-token-only posture no longer authenticates shared requests through the accepted token ring.
- Production startup now has explicit regression coverage for previous-token-only rejection.
- GUI seed persistence no longer drops programmatic updates when the entry text lags.
- Educational verification script now handles single-file private commits correctly.
- Educational sync no longer pulls `_jcoder_worktree/` into the mirror filesystem.

## Verification

- `python tests\virtual_test_phase1_foundation.py`
  - `55 PASS, 0 FAIL`
- `python tests\virtual_test_view_switching.py`
  - `51 PASS, 0 FAIL`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - `697 passed, 8 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/ -q`
  - `820 passed, 5 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_auth.py -q`
  - `8 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -k "auth_context_accepts_previous_api_token_during_rotation or auth_context_does_not_treat_previous_token_without_current_primary_as_authenticated or production_startup_rejects_previous_token_without_current_primary" -q`
  - `3 passed, 79 deselected, 1 warning`
- `powershell -ExecutionPolicy Bypass -File tools/verify_educational_sync.ps1`
  - passed

## Open Items

- QA should rerun the shared-launch auth slice against the shipped private tip.
- PM can keep `Sprint 13.5a` in the QA lane until that rerun clears.
