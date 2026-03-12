# HybridRAG3 Sprint Plan

**Created:** 2026-03-08  
**Last updated:** 2026-03-11  
**Purpose:** one active tracker for demo-critical work, deployment prep, and longer-term backlog.

## Status Key

- `DONE` -- completed and verified enough to move on
- `IN PROGRESS` -- active work or active QA loop
- `NEXT` -- next sprint once current blocker clears
- `BLOCKED` -- waiting on environment, QA, or external dependency
- `LATER` -- valid work, but not on the immediate path

## Current Position

- Config authority redesign is effectively closed:
  - `config/config.yaml` is the single base runtime authority
  - `config/user_modes.yaml` is the single profile authority
  - implicit runtime fallback to `default_config.yaml` / `user_overrides.yaml` is removed
- Offline/online mode separation is materially improved and recent QA passes did not find fresh contamination bugs.
- The main remaining environment gap is a real online end-to-end query against the Azure Government endpoint.
- Query-side autotune is now landed and locally re-verified.
- The next highest-value engineering work is demo hardening, starting with the rehearsal-pack validation and reporting path.

## Active Sprint Board

| Sprint | Status | Goal | Exit Criteria |
|---|---|---|---|
| Sprint 1 -- QA Closeout and Config Freeze | `DONE` | Finish the config-authority cleanup and freeze the new authority model. | QA signs off on config authority, GUI save/reload, YAML round-trip, mode isolation, and no stale guidance in active docs. |
| Sprint 2 -- Retrieval and Query Debug View | `DONE` | Add Admin-only diagnostics so failures can be traced to retrieval, query policy, or contamination. | Admin debug panel shows retrieved chunks, similarity scores, source files, kept/dropped reasons, effective settings, and active mode/data paths for each query. |
| Sprint 3 -- Tuning UI Redesign | `DONE` | Split tuning into a clean retrieval/query-generation layout and expose the missing mirrored controls. | Tuning screen is split cleanly, offline and online common controls are mirrored, backend-only advanced controls are capability-gated, and the GUI round-trips to YAML cleanly. |
| Sprint 4 -- Query-Side Autotune | `DONE` | Tune query-policy and generation bundles overnight instead of only retriever-side settings. | Autotune can run query/generation bundles, save effective settings with results, and produce a ranked winner set for online and offline. |
| Sprint 5 -- Demo Hardening | `IN PROGRESS` | Make the demo path stable, explainable, and rehearsed. | Clean index, stable online-first demo config, rehearsal question bank, retrieval debug ready for troubleshooting, and offline demo path kept Admin-only. |
| Sprint 6 -- Shared Online Deployment | `LATER` | Prepare the workstation-hosted intranet deployment for small-team use. | User-facing web GUI, login identity, visible queue/status, audit logging, and online-only shared path are working. |
| Sprint 7 -- Admin Operations Console | `LATER` | Expand the Admin side into the operational control surface. | Admin can review logs, audits, queue state, retrieval traces, profiles, and indexing schedule from one place. |
| Sprint 8 -- Offline/Admin Specialization | `LATER` | Keep offline mode isolated for PII/admin/demo/nightly use without contaminating shared online behavior. | Offline mode is admin-scoped, path-isolated, and validated not to leak settings or data into online mode. |

## Sprint 1 Detail

### Already Closed

- Canonical config authority and profile authority are in place.
- Legacy `mode_tuning.yaml` no longer contaminates runtime.
- Canonical writes converge on `config/config.yaml`.
- Checked vs agnostic profile semantics exist in `config/user_modes.yaml`.
- Setup scripts point to `config/config.yaml`.
- Active docs no longer point operators at `config/user_overrides.yaml`.

### Still Needed to Fully Close Sprint 1

- Run one real online Azure Government query successfully through the app.
- Get one final QA pass confirming no new authority or contamination defects.
- Treat the current config architecture as frozen unless a bug forces a change.

### Sprint 1 Blockers

- Environment gap: no usable live online endpoint configured in this machine/session.
- Slow-machine gap: `tests/virtual_test_phase2_exhaustive.py` has been timeout-prone in some runs, even without a concrete assertion failure.

## Sprint 2 Detail

### Why This Is Next

Right now a bad answer can still come from several different causes:

- retrieval failure
- over-strict query policy
- bad context packaging
- stale mode/runtime state
- model behavior

Without a trace view, tuning remains guesswork.

### Required Debug Payload

- active mode
- active profile
- effective retrieval settings
- effective query-policy settings
- effective generation/backend settings
- raw candidate hits
- final kept hits
- score per hit
- source file per hit
- chunk index per hit
- chunk text per hit
- kept/dropped reason
- context trim summary
- final answer path:
  - grounded
  - partial-evidence
  - open-knowledge fallback
  - blocked/no-answer

## Sprint 3 Detail

### Target UI Layout

- Left pane: `Retrieval`
- Right pane top: `Query Policy`
- Right pane bottom: `Generation`

### Design Rules

- common knobs mirrored across offline and online where honest
- backend-specific advanced knobs kept separate
- progressive disclosure for advanced settings
- Admin GUI remains the primary day-to-day editor
- GUI save and YAML edit must round-trip with last explicit save winning

## Sprint 4 Detail

### Priority Order

1. online query-side tuning
2. offline query-side tuning

### Minimum Output

- candidate bundles
- run summaries
- winner report
- effective setting snapshot per run
- applied winner path back into `config/config.yaml`

## Sprint 5 Detail

### Demo Rules

- shared/demo path is online-first
- offline remains available from the workstation Admin side
- hallucination guard can stay lighter during development, then be tightened for rehearsal
- the demo question bank must be realistic, not just the tiny corpus smoke set

## Watchlist

- verify online/offline data paths stay isolated when switching
- verify offline settings never contaminate online mode
- keep class sizes under 500 LOC
- keep new work modular and portable
- prefer redesigns over layering more compatibility shims

## Notes

- Historical handoff notes remain in `docs/HANDOVER_AND_SPRINT_PLAN_FREEZE_SAFE.md`.
- This file is the active sprint tracker going forward.
