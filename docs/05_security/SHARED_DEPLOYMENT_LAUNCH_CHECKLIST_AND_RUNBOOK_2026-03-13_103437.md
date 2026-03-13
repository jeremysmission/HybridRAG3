# Shared Deployment Launch Checklist And Operator Runbook

**Created:** 2026-03-13 10:34 America/Denver  
**Purpose:** one operator-facing launch and steady-state runbook for the workstation-hosted shared deployment path.

## Scope

- This runbook covers the workstation-hosted FastAPI + browser-dashboard deployment path.
- It assumes the desktop GUI, shared browser console, security guide, soak runner, and backup/restore drill tooling already exist.
- It does not replace the security-specific recovery details in:
  - `docs/05_security/SHARED_DEPLOYMENT_SECURITY_AND_RECOVERY_GUIDE_2026-03-13_051214.md`

## Launch Checklist

Before opening the workstation-hosted shared deployment to users:

1. Confirm the workstation is back in shared-safe mode.
   - run `python tools/shared_launch_preflight.py --fail-if-blocked`
   - Runtime mode is `online`
   - no local/admin-only offline task is still active
   - `/status` and `/admin/data` do not show an offline/shared-boundary conflict
2. Confirm auth and secret posture.
   - `python tools/shared_launch_preflight.py` reports shared auth as configured
   - if env is not being used, the shared token is stored in Windows Credential Manager
   - browser-session and proxy secrets are present in the approved secret inventory
   - previous-secret slots are only populated if a real rotation window is active
3. Confirm data-protection posture.
   - `storage_protection` in `/admin/data` shows no unexpected unprotected paths
   - SQLite quick-check status is healthy
4. Confirm backup evidence exists.
   - latest backup bundle:
     - `output/shared_backups/2026-03-13_103253_shared_deployment_backup`
   - latest restore drill:
     - `output/shared_restore_drills/2026-03-13_103335_shared_restore_drill`
5. Confirm soak evidence is current enough for the cutover window.
   - successful live baseline:
     - `output/shared_soak/2026-03-13_103135_shared_deployment_soak.json`
   - known ceiling/failure case:
     - `output/shared_soak/2026-03-13_102643_shared_deployment_soak.json`
6. Confirm operator surfaces are reachable.
   - `/health`
   - `/status`
   - `/auth/context`
   - `/activity/query-queue`
   - `/activity/queries`
   - `/admin/data`

## Start Procedure

1. Launch the shared server:

```powershell
.venv\Scripts\python.exe src\api\server.py --host 127.0.0.1 --port 8000
```

Recommended pre-start posture apply:

```powershell
.venv\Scripts\python.exe tools\shared_launch_preflight.py --apply-online --apply-production --fail-if-blocked
```

2. Validate the shared endpoints:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/status
Invoke-RestMethod http://127.0.0.1:8000/auth/context
```

3. Open the browser surfaces:
   - `http://127.0.0.1:8000/dashboard`
   - `http://127.0.0.1:8000/admin`

## Normal Operating Checks

Watch these fields during steady-state use:

- `/status`
  - deployment mode
  - current runtime mode
  - queue summary
  - indexing summary
- `/activity/query-queue`
  - active queries
  - waiting queries
  - rejected queries
- `/activity/queries`
  - active and recent requests
  - actor attribution
  - failure counts
- `/admin/data`
  - alerts
  - freshness
  - index schedule
  - storage protection
  - security activity

## Current Performance Baseline

- Successful live workstation-backed baseline:
  - artifact: `output/shared_soak/2026-03-13_103135_shared_deployment_soak.json`
  - `2/2` successful requests
  - `concurrency=1`
  - client latency:
    - `p50=127122.7ms`
    - `p95=173533.5ms`
    - `max=178690.3ms`
  - server latency:
    - `p50=126929.2ms`
    - `p95=173252.2ms`
    - `max=178399.2ms`
- Observed ceiling/failure case:
  - artifact: `output/shared_soak/2026-03-13_102643_shared_deployment_soak.json`
  - `1/5` successful requests
  - `concurrency=2`
  - four `TimeoutError: timed out` failures at `90s`

Operator meaning:

- `concurrency=1` is the current safe baseline on this workstation
- `concurrency=2` with the full demo rehearsal pack exceeded the current live ceiling
- do not advertise higher shared concurrency until a later tuning/hardening pass changes the measured baseline

## Backup And Restore Commands

Create a backup bundle:

```powershell
.venv\Scripts\python.exe tools\shared_deployment_backup.py create --project-root D:\HybridRAG3
```

Verify the bundle:

```powershell
.venv\Scripts\python.exe tools\shared_deployment_backup.py verify D:\HybridRAG3\output\shared_backups\2026-03-13_103253_shared_deployment_backup
```

Stage a non-destructive restore drill:

```powershell
.venv\Scripts\python.exe tools\shared_deployment_backup.py restore-drill D:\HybridRAG3\output\shared_backups\2026-03-13_103253_shared_deployment_backup
```

Important:

- the repo backup bundle does not copy shared auth tokens, browser-session secrets, proxy secrets, or history-encryption keys
- keep those values in the approved secure secret inventory

## Rollback Triggers

Rollback should be considered when any of these happen:

- repeated shared query timeouts above the current `concurrency=1` baseline
- queue growth or rejections beyond the documented ceiling
- SQLite quick-check failure on the main or history DB
- backup verification or restore drill mismatch
- auth anomalies or proxy-identity rejections that cannot be explained by a known cutover window
- unexpected offline/shared-boundary contamination

## Rollback Procedure

1. Block new shared use.
   - stop sending users to the browser surface
   - stop the FastAPI server
2. Take an emergency backup before overwriting anything.
3. Use the most recent verified bundle and restore drill as the source of truth.
4. Copy the required files from the restore-drill payload into the live runtime paths during the maintenance window:
   - `database/...`
   - `history/...`
   - `config/config.yaml`
   - `config/user_modes.yaml`
5. Re-enter secrets from the approved secure inventory if rotation or environment loss is part of the incident.
6. Restart the server and recheck:
   - `/health`
   - `/status`
   - `/admin/data`
7. Rerun the safe low-concurrency soak baseline before reopening the shared deployment to users.

## Shutdown Procedure

1. Stop the FastAPI server cleanly.
2. Confirm no indexing or long-running maintenance task is still active.
3. Capture a fresh backup bundle if the system state changed materially during the window.
4. Record notable alerts, auth events, or soak anomalies in the sprint tracker or the operator handoff.

## References

- `docs/05_security/SHARED_DEPLOYMENT_SECURITY_AND_RECOVERY_GUIDE_2026-03-13_051214.md`
- `docs/04_demo/DEMO_PREP.md`
- `docs/09_project_mgmt/SPRINT_PLAN.md`
- `tools/shared_deployment_soak.py`
- `tools/shared_deployment_backup.py`
