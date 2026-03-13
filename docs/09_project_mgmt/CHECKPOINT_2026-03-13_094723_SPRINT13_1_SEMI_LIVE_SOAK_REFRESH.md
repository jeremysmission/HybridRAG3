# Checkpoint -- Sprint 13.1 Semi-Live Soak Refresh

**Timestamp:** 2026-03-13 09:47 -06:00  
**Session ID:** `codex-hybridrag3-sprint13-semi-live-soak-refresh-20260313-094723`  
**Sprint:** `13.1 -- Multi-User Soak and Performance Baseline`  
**Status:** `EVIDENCE REFRESHED / SPRINT 13.1 STILL ACTIVE`

## What Ran

- Reused the new shared soak runner against the real FastAPI application surfaces in-process.
- Prompt source:
  - first four prompts from `docs/04_demo/DEMO_REHEARSAL_PACK.json`
- Run shape:
  - `rounds=2`
  - `concurrency=2`
  - `8` total requests

## Fresh Artifact

- `output/shared_soak/2026-03-13_094723_shared_deployment_soak.json`

## Summary

- Requests:
  - `8/8` successful
  - `0` failed
- Client latency:
  - `p50=144.69ms`
  - `p95=176.41ms`
  - `max=188.45ms`
- Server latency:
  - `p50=18.5ms`
  - `p95=18.5ms`
  - `max=18.5ms`
- Queue:
  - peak active `0`
  - peak waiting `0`
  - peak rejected `0`

## Method

- Used `.venv\Scripts\python.exe` with `fastapi.testclient.TestClient(app)` against `src.api.server.app`.
- Kept the real FastAPI lifespan, routing, query-queue tracking, and query-activity surfaces active.
- Patched the query engine response deterministically for repeatable semi-live measurement.

## Documentation Sync

- Updated `docs/09_project_mgmt/SPRINT_PLAN.md`
- Updated `docs/09_project_mgmt/PM_TRACKER_2026-03-12_110046.md`

## Open Item

- Sprint `13.1` is stronger than before, but still not closed.
- Remaining exit item:
  - workstation-backed live soak evidence
- Next planned move after that remains:
  - `13.2 -- Backup, Restore, and Rollback Drill`
