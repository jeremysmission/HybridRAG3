# Shared Deployment Controlled Cutover Worksheet

**Created:** 2026-03-13 16:53 America/Denver  
**Purpose:** one operator worksheet for Sprint 14 controlled shared cutover execution.

## Scope

- Use this during `14.1 -- Controlled Shared Cutover`.
- Fill it in during the real launch window.
- Do not mark cutover accepted until the Sprint 13 blockers are actually cleared:
  - authenticated-online preflight
  - refreshed live soak
  - supported concurrency decision
  - refreshed launch verdict

## Window

| Field | Value |
|---|---|
| Planned date | `TBD` |
| Planned start | `TBD` |
| Planned end | `TBD` |
| Operator on duty | `TBD` |
| Backup bundle in force | `TBD` |
| Restore drill in force | `TBD` |

## Go / No-Go Gate

- [ ] `python tools/shared_launch_preflight.py --json --fail-if-blocked` passed
- [ ] runtime mode is `online`
- [ ] deployment mode is `production`
- [ ] shared API auth token is configured
- [ ] online API credentials are configured
- [ ] live soak artifact exists for the intended posture
- [ ] supported concurrency statement is documented
- [ ] latest backup bundle and restore drill are verified
- [ ] operator has reviewed `/status` and `/admin/data`

## Planned Launch Commands

```powershell
python tools/shared_launch_preflight.py --json --fail-if-blocked
.venv\Scripts\python.exe src\api\server.py --host 127.0.0.1 --port 8000
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/status
Invoke-RestMethod http://127.0.0.1:8000/auth/context
```

## Recorded Posture

| Field | Value |
|---|---|
| Preflight timestamp | `TBD` |
| Auth posture | `TBD` |
| Runtime mode | `TBD` |
| Deployment mode | `TBD` |
| Supported concurrency | `TBD` |
| Shared dashboard URL | `http://127.0.0.1:8000/dashboard` |
| Admin console URL | `http://127.0.0.1:8000/admin` |

## Event Log

| Time | Event | Notes |
|---|---|---|
| `TBD` | cutover start |  |
| `TBD` | server started |  |
| `TBD` | browser dashboard validated |  |
| `TBD` | admin console validated |  |
| `TBD` | user access opened |  |

## Verdict

- Cutover result: `TBD`
- If rejected or rolled back, state why:
  - `TBD`

## Sign-Off

| Role | Name | Date / Time |
|---|---|---|
| Operator | `TBD` | `TBD` |
| PM | `TBD` | `TBD` |
