# Final QA And PM Freeze Checklist

**Created:** 2026-03-13 16:53 America/Denver  
**Purpose:** checklist for `14.3 -- Final QA Sweep And PM Freeze`.

## Required Evidence

- [ ] accepted cutover or explicit rollback verdict exists
- [ ] latest shared soak artifact is linked
- [ ] latest backup verify result is linked
- [ ] latest restore drill result is linked
- [ ] launch runbook is current
- [ ] shared handoff file is current

## Final QA Command Pack

Record exact commands and results here:

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests/` | `TBD` |
| `python tools/shared_launch_preflight.py --json --fail-if-blocked` | `TBD` |
| `python tools/shared_deployment_soak.py ...` | `TBD` |
| `python tools/final_qa_freeze_packet.py --acceptance-state accepted --verify-backup --run-restore-drill` | `TBD` |
| `python tools/project_completion_handoff.py --freeze-packet latest --no-write --fail-if-blocked` | `TBD` |
| `python tools/shared_deployment_backup.py verify ...` | `TBD` |

Automation note:
- use `--acceptance-state accepted` for a launch-ready freeze packet
- use `--acceptance-state rolled_back --acceptance-note "reason"` for an explicit rollback closeout

## PM Freeze Actions

- [ ] freeze `docs/09_project_mgmt/SPRINT_PLAN.md`
- [ ] freeze `docs/09_project_mgmt/PM_TRACKER_2026-03-12_110046.md`
- [ ] freeze the active launch runbook
- [ ] write the final completion checkpoint
- [ ] update `C:\Users\jerem\.ai_handoff\ai_handoff.md`

## Residual Watchlist

Use this only for non-blocking items that are explicitly maintenance-only:

- `TBD`

## Sign-Off

| Role | Name | Date / Time |
|---|---|---|
| QA | `TBD` | `TBD` |
| PM | `TBD` | `TBD` |
