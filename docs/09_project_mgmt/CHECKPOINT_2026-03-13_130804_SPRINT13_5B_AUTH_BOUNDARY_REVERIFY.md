# Sprint 13.5b Auth Boundary Reverify

- Created: 2026-03-13_130804
- Updated: 2026-03-13_130804
- Timestamp: 2026-03-13_130804
- Session ID: codex-hybridrag3-sprint13-5b-auth-boundary-reverify-20260313-123636
- Topic: sprint13 5b auth boundary reverify

## What Changed

- Consumed the QA pass for `13.5a -- Current Token Requirement Fix`.
  - QA timestamp: `2026-03-13 12:36:36 -06:00`
  - QA status: passed
- Reverified the remaining acceptance target for `13.5b`.
  - previous-token-only auth repro is closed
  - env-backed auth-source reporting still resolves correctly
  - keyring-backed auth-source reporting still resolves correctly
- Rolled PM status forward so the next dispatch is now `13.6 -- Live Authenticated-Online Soak Refresh`.

## Tests

- QA-cleared gates already on record:
  - `python -m pytest tests/test_shared_deployment_auth.py tests/test_gui_integration_w4.py -q`
    - `42 passed, 2 skipped` on QA machine
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
    - `82 passed, 1 warning`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
    - `700 passed, 6 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/`
    - `822 passed, 5 skipped, 7 warnings`
- Coder-side 13.5b proof:
  - `python -m pytest tests/test_shared_deployment_auth.py -k "prefers_env_over_keyring or falls_back_to_keyring or build_shared_launch_snapshot_ready_with_keyring_token or previous_token_only_does_not_count_as_shared_launch_ready or shared_launch_preflight_previous_token_only_fails_in_production_online_mode" -q`
    - `5 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -k "api_auth_source or keyring_token_required or login_accepts_keyring_backed_shared_token" -q`
    - `2 passed`

## Open Items

- Auth-boundary work is closed; the next live blocker is `13.6 -- Live Authenticated-Online Soak Refresh`.
- That slice still depends on a workstation-backed authenticated-online preflight/soak rerun and fresh artifact capture.
