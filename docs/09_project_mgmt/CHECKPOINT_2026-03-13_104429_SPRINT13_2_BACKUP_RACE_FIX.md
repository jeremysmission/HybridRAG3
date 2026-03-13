# Checkpoint -- Sprint 13.2 Backup Race Fix and Live Reverify

**Timestamp:** 2026-03-13 10:44 -06:00  
**Sprint:** `13.2 -- Backup, Restore, and Rollback Drill`  
**Status:** `CODE COMPLETE / LIVE REVERIFY COMPLETE / READY FOR QA`

## What Changed

- Fixed a real operator-path race in `src/tools/shared_deployment_backup.py`.
  - The backup manifest summary and DB fingerprints now come from the copied payload snapshot rather than the mutable live source DB after the copy step.
- Kept the operator entrypoint in `tools/shared_deployment_backup.py`.
- Added a regression in `tests/test_shared_deployment_backup_tool.py` that mutates the live history DB immediately after the history copy step and proves verify still passes.

## Why This Was Needed

- A fresh live reverify against:
  - `output/shared_backups/2026-03-13_102947_shared_deployment_backup`
- exposed a false history-fingerprint mismatch even though:
  - `Files missing = 0`
  - `Hash mismatches = 0`
  - `SQLite failures = 0`
- Root cause:
  - the copied history DB was stable, but the manifest summary was being built from the live history DB after the copy step, so a post-copy write could invalidate the saved fingerprint.

## Refreshed Live Evidence

- Backup bundle:
  - `output/shared_backups/2026-03-13_104241_shared_deployment_backup`
- Restore drill:
  - `output/shared_restore_drills/2026-03-13_104315_shared_restore_drill`
- Result:
  - `1876` files copied
  - `1876` files restored
  - `0` missing files
  - `0` hash mismatches
  - `0` SQLite failures
  - main/history fingerprint match `True`

## Verification

- `python -m py_compile src\tools\shared_deployment_backup.py tools\shared_deployment_backup.py tests\test_shared_deployment_backup_tool.py`
  - `passed`
- `python -m pytest tests/test_shared_deployment_backup_tool.py -q`
  - `7 passed`
- `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_backup_tool.py -q`
  - `7 passed`
- `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - `687 passed, 6 skipped, 7 warnings`
- `.venv\Scripts\python.exe -m pytest tests/`
  - `804 passed, 4 skipped, 7 warnings`
- Required virtual suite rerun:
  - `phase1 55 PASS`
  - `phase2 63 PASS, 1 SKIP`
  - `phase4 152 PASS, 5 WARN, 1 SKIP`
  - `view_switching 51 PASS`
  - `setup_wizard 54 PASS`
  - `setup_scripts 103 PASS`
  - `guard_part1 97 PASS`
  - `guard_part2 61 PASS`
  - `setup_group_policy 30 PASS`
  - `ibit_reference 66 PASS`
  - `offline_isolation 8 PASS`

## Open Items

- Sprint 13 cutover blockers remain the same as the existing `13.4` review:
  - live shared auth posture is still open
  - live soak evidence is still offline-mode
  - workstation concurrency ceiling is only validated at `1`
- Next engineering move should stay on the cutover blockers, not on more backup tooling.
