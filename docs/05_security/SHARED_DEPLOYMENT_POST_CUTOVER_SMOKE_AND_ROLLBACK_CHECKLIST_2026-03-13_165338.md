# Shared Deployment Post-Cutover Smoke And Rollback Checklist

**Created:** 2026-03-13 16:53 America/Denver  
**Purpose:** one checklist for `14.2 -- Post-Cutover Smoke And Rollback Proof`.

## Immediate Smoke Checks

| Check | Expected Result | Status | Notes |
|---|---|---|---|
| `GET /health` | `200 OK` | `TBD` |  |
| `GET /status` | `200 OK`, online shared posture visible | `TBD` |  |
| `GET /auth/context` | authenticated shared context | `TBD` |  |
| open `/dashboard` | browser page loads and query surface is usable | `TBD` |  |
| `GET /dashboard/data` | shared snapshot returns | `TBD` |  |
| open `/admin` | admin console loads for admin actor | `TBD` |  |
| `GET /admin/data` | operator snapshot returns | `TBD` |  |
| `GET /activity/query-queue` | queue summary returns | `TBD` |  |
| `GET /activity/queries` | recent activity returns | `TBD` |  |

## Safe Baseline Query

| Field | Value |
|---|---|
| Question used | `TBD` |
| Response accepted | `TBD` |
| Sources accepted | `TBD` |
| Latency accepted | `TBD` |

## Rollback Proof

| Field | Value |
|---|---|
| Backup bundle | `TBD` |
| Backup verify result | `TBD` |
| Restore drill | `TBD` |
| Restore drill result | `TBD` |

Recommended commands:

```powershell
python tools/shared_deployment_backup.py verify output\shared_backups\<bundle>
python tools/shared_deployment_backup.py restore-drill output\shared_backups\<bundle>
```

## Rollback Trigger Review

- [ ] repeated timeouts above the supported concurrency limit
- [ ] queue growth or request rejection beyond the declared ceiling
- [ ] auth or identity anomalies that are not explained by the cutover window
- [ ] database quick-check failure
- [ ] admin or dashboard pages not staying healthy after launch

## Final Outcome

- Outcome: `TBD`
- If rollback happened, record the reason:
  - `TBD`

## Sign-Off

| Role | Name | Date / Time |
|---|---|---|
| Operator | `TBD` | `TBD` |
| QA | `TBD` | `TBD` |
