# HybridRAG3 Sprint Plan

**Created:** 2026-03-08  
**Last updated:** 2026-03-15 America/Denver  
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
- Offline/online mode separation was re-stabilized across `5A.1` through `5A.4` in the 2026-03-12 one-QA workflow.
- The query-mode stabilization sprint is now cleared in this checkout:
  - localhost Ollama normalization is fixed on boot plus embedder paths
  - low-grounding semantics are covered by runtime sync tests
  - GUI/API entry-point parity plus mode-churn reset coverage are green
  - harness and button-smash verification passed after hardening config persistence under rapid mode churn
- The verification-tooling pre-slice `5A.4a -- GUI E2E Combobox Callback Trap` remains closed, and `Sprint 5 -- Demo Hardening` is now the active sprint.
- Two optional advisory add-on lanes were completed on 2026-03-12 and are now part of PM synthesis:
  - `deep-packet-inspector-2-offline-mode-inspection-20260312-1052`
  - `deep-packet-inspector-online-mode-dials-20260312-1120`
- Query-side autotune is now landed and locally re-verified.
- The demo rehearsal pack is now aligned to the live indexed corpus in this checkout:
  - `python tools/demo_rehearsal_audit.py` is green `10/10`
  - `tools/gui_demo_smoke.py` and `tools/demo_transcript.py` were rerun against the revised pack
- Remaining Sprint 5 blocker:
  - live online answer execution is still skipped because API credentials are not configured in this session
- Sprint 6 shared deployment surfaces advanced again:
  - FastAPI `/status` now reports deployment mode, current user, auth posture, network-gate audit summary, a live indexing snapshot, the latest persisted indexing run summary, and a compact query-activity summary
  - FastAPI `/activity/queries` now exposes active and recent API query activity for shared deployment dashboards, protected by the same optional API token auth policy when enabled
  - FastAPI `/activity/network` now exposes detailed recent network-gate audit entries for shared deployment dashboards, again behind the optional API token when configured
  - FastAPI `/auth/context` now exposes the resolved request auth posture plus actor identity context, and `/activity/queries` now records actor attribution for shared dashboards
  - trusted proxy-user headers now require the feature flag, an explicit trusted-proxy host boundary, and a shared proxy proof header, so direct header spoofing is no longer accepted by default
  - FastAPI `/activity/query-queue` now exposes shared query queue capacity and saturation state, and `/status` now includes the same queue summary for dashboards
  - FastAPI now also provides a browser-facing shared console via `/auth/login`, `/auth/logout`, and `/dashboard`
- Sprint 7 Admin operations work is now active in this checkout:
  - FastAPI `/admin` plus `/admin/data` now provide an operator-facing browser shell that consolidates deployment status, auth context, query activity, queue pressure, network audit, runtime config, and retrieval-trace visibility
  - the Admin console now includes a recent retrieval-trace explorer backed by in-memory trace retention and per-trace detail fetches via `/admin/traces/{trace_id}`
- The active roadmap now extends through Sprint 14 with a normalized completion order:
  - `Sprint 5 -> Sprint 6 -> Sprint 7 -> Sprint 8 -> Sprint 9 -> Sprint 10 -> Sprint 11 -> Sprint 12 -> Sprint 13 -> Sprint 14`
  - remaining blockers on that chain are now explicit:
    - `Sprint 5`: missing live API credentials for the final online demo-hardening pass
    - `Sprint 13`: shared-launch auth boundary reverify is now closed; the current live blocker is environmental because this workstation has no shared API auth token and no online API credentials configured for the authenticated-online soak rerun
- Repo-wide QA evidence was pushed one step further after the GUI parity harness slice:
  - the authoritative repo-wide evidence for this checkout is the split `.venv` gate:
    - `.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_fastapi_server.py`
    - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - the ambient system `python -m pytest tests/` is not a valid full gate on this machine because that interpreter cannot import `fastapi`
  - the non-FastAPI `.venv` gate passed `704 passed, 4 skipped, 7 warnings`
  - the FastAPI slice passed `78 passed, 1 warning`
  - required virtual suites were rerun and remained green
  - a non-fatal Tk shutdown warning remains on the maintenance watchlist because the green full-suite path can still print `Variable.__del__` / `main thread is not in main loop` noise at interpreter shutdown
- Sprint 9 is now effectively closed in this checkout:
  - `9.1 -- Role Model and Policy Store` is landed and green
  - `9.2 -- Document Classification and Access Tags` is landed and green
  - `9.3 -- Retrieval Enforcement and Deny Audit` is landed and green
  - `9.4 -- Admin Policy Review Surface` is landed and green
  - `9.2 -- Document Classification and Access Tags` is now landed and green:
    - document tag rules/defaults are regression-tested directly in `src/core/access_tags.py`
    - index-time classification is now regression-tested through `Indexer`
    - retriever source summaries now surface `access_tags` plus `access_tag_source`
- Sprint 10 is now effectively closed in this checkout:
  - `10.1 -- Scheduled Index Runner` is landed and green
  - shared status and Admin surfaces now expose recurring schedule state through `index_schedule`
  - FastAPI startup can launch an env-backed scheduled indexing loop that reuses the same background indexing worker as manual `POST /index`
  - `10.2 -- Freshness and Drift Dashboard` is landed and green
  - the Admin console now exposes source-tree freshness, latest source update, files newer than the last run, and a drift summary for maintenance triage
  - `10.3 -- Alerting and Failure Surfacing` is reverified and green
  - `10.4 -- Maintenance Controls` is landed and green via the new Admin `Reindex if stale` action
- Sprint 11 is now effectively closed in this checkout:
  - `11.1 -- Conversation Thread Model` is landed and green
  - persistent conversation history now lives beside the configured data DB and is exposed through `/history/threads`, per-thread detail, and JSON export
  - `11.2 -- Follow-Up Query Handling` is landed and green
  - `/query` and `/query/stream` now accept `thread_id` and project bounded recent-turn context into follow-up prompts while preserving raw stored user questions for auditability
  - `11.3 -- Shared History Browser` is landed and green
  - the shared browser console now shows saved conversation threads, per-thread detail, active-thread resume controls, and streamed thread metadata
  - `11.4 -- Retention and Export Controls` is landed and green
  - env-backed retention limits now bound stored thread count and turns per thread, and per-thread JSON export is available for handoff/review
  - the shared browser and Admin console now surface those retention limits and selected-thread export directly in the web UI
- Sprint 12 is now active in this checkout:
  - `12.1 -- Secret Handling and Rotation` is landed and green
  - API token auth, browser-session signing, and trusted proxy identity proofs now support current-plus-previous secret rotation via env-backed previous-secret slots
  - rotated sessions and previous active tokens remain valid during cutover while newly minted browser sessions keep signing with the current primary secret
  - `12.2 -- Protected Data Storage` is landed and green
  - conversation-history rows now support env-backed encryption at rest with current-plus-previous key rotation, opportunistic rewrap to the current key, secure-delete-on-app-connection, and best-effort local file hardening
  - the Admin runtime-safety panel now makes the protection scope explicit by surfacing the protected history DB path, encryption source, rotation status, and secure-delete posture
  - shared API startup now supports protected-root enforcement for the main and history databases via `HYBRIDRAG_PROTECTED_STORAGE_ROOTS` and `HYBRIDRAG_REQUIRE_PROTECTED_STORAGE`
  - the Admin console now exposes a dedicated `Data protection` panel and raises an operator alert when tracked database paths fall outside the configured protected roots
  - `12.3 -- Audit Access Controls and Anomaly Detection` is landed and green
  - shared-auth Admin routes now require the `admin` role instead of allowing any authenticated actor to open the operator console or fire admin controls
  - denied Admin access attempts now land in the existing auth/security activity feed and raise a dedicated Admin alert, so role-boundary probes are visible to actual admins
  - invalid browser logins, unauthorized shared requests, rejected proxy-identity attempts, and login rate-limit hits now land in the same Admin `security_activity` snapshot and anomaly alerts
  - `12.4 -- Security Documentation and Recovery Procedure` is landed and green
  - the shared deployment path now has an operator-facing security and recovery guide covering auth boundaries, rotation order, history-key recovery, and backup expectations
  - the security audit and demo prep docs now reference the implemented shared-history encryption and recovery posture instead of leaving that path as roadmap-only guidance
  - `Sprint 12` is effectively closed in this checkout
  - `13.0 -- GUI/CLI Parity Surface And Harness` is now landed as a Sprint 13 launch-readiness support slice:
    - the desktop `Command Center` now ships as a first-class GUI tab, reusing the existing HybridRAG dark-mode layout and exposing the 19 primary `rag-*` commands through native workflows or streamed subprocess execution
    - parity support tooling remains in place via `tools/gui_cli_parity_harness.py`, `tools/gui_cli_parity_model.py`, `src/gui/testing/gui_cli_parity_harness.py`, and `tools/gui_cli_parity.py`
    - the same full-gate pass also closed the seed-entry stale-`IntVar` regression in `src/gui/panels/tuning_tab_runtime.py`
  - `13.0c -- Corporate PowerShell Entrypoint Hardening` is now landed as a Sprint 13 launch-support slice:
    - direct PowerShell entrypoints now attempt a process-scope execution-policy bypass before the main script body so managed corporate shells do not depend entirely on wrapper launchers
    - `tools/launch_gui.ps1` now reasserts repo-root and `.venv` context before launching the GUI from PowerShell
    - `tools/build_usb_deploy_bundle.ps1` now resolves repo `.venv\Scripts\python.exe` from `$projectRoot` instead of the caller working directory
    - the lingering GUI printable-path tail fix was reapplied and `docs/_printable/21_GUI_Guide.docx` was regenerated
  - `13.1 -- Multi-User Soak and Performance Baseline` is now started:
    - refreshed `docs/WORKSTATION_STRESS_TEST.md` from the current workstation simulation harness
    - added `src/tools/shared_deployment_soak.py` plus `tools/shared_deployment_soak.py` for repeatable shared-API soak baselines
    - timestamped JSON soak reports now land under `output/shared_soak/`
    - first semi-live in-process baseline artifact captured at `output/shared_soak/2026-03-13_091702_shared_deployment_soak.json`
    - refreshed semi-live in-process baseline artifact captured at `output/shared_soak/2026-03-13_094723_shared_deployment_soak.json`
    - workstation-backed live ceiling artifact captured at `output/shared_soak/2026-03-13_102643_shared_deployment_soak.json`
    - workstation-backed live low-concurrency baseline captured at `output/shared_soak/2026-03-13_103135_shared_deployment_soak.json`
  - `13.2 -- Backup, Restore, and Rollback Drill` is now landed:
  - live backup bundle created at `output/shared_backups/2026-03-13_103253_shared_deployment_backup`
  - live restore drill created at `output/shared_restore_drills/2026-03-13_103335_shared_restore_drill`
  - backup/restore evidence was reverified after a live history-snapshot race fix:
    - refreshed bundle: `output/shared_backups/2026-03-13_104241_shared_deployment_backup`
    - refreshed restore drill: `output/shared_restore_drills/2026-03-13_104315_shared_restore_drill`
  - `13.3 -- Launch Checklist and Operator Runbook` is now landed:
    - added `docs/05_security/SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_103437.md`
  - `13.4 -- Cutover Readiness Review` is now landed:
    - review note: `docs/09_project_mgmt/CHECKPOINT_2026-03-13_103437_SPRINT13_CUTOVER_REVIEW.md`
    - current verdict: not ready for shared launch
    - active blockers:
      - live soak auth posture remained `open`
      - live soak mode remained `offline`
      - current workstation ceiling only supports `concurrency=1`
  - `13.5 -- Shared Launch Auth And Preflight` is now landed:
    - shared API auth now resolves from env or Windows Credential Manager through one canonical resolver
    - server startup, request auth, browser-session fallback signing, runtime-safety surfaces, and GUI mode-boundary logic now use that shared auth source instead of env-only token checks
    - added `src/tools/shared_launch_preflight.py` plus `tools/shared_launch_preflight.py`
    - the desktop `Command Center` now exposes:
      - `rag-shared-launch`
      - `rag-store-shared-token`
    - the auth/mode drift found in `13.4` is now closable through shipped code and tooling instead of manual env-only setup
  - `13.5`, `13.5a`, and `13.5b` are now closed in this checkout:
    - shared auth now requires a current token before the deployment is treated as configured or rotation-enabled
    - previous-token-only preflight now fails closed
    - previous-token-only production API startup now fails closed
    - previous-token-only `/auth/context` requests now stay in the anonymous open posture instead of being treated as authenticated shared auth
    - the same full-gate pass also hardened GUI seed persistence in `src/gui/panels/tuning_tab_runtime.py` so a lagging entry widget cannot overwrite a newer bound `IntVar` seed during large suite runs
    - QA explicitly cleared `13.5a -- Current Token Requirement Fix` on `2026-03-13 12:36:36 -06:00`
    - coder-side `13.5b -- Auth Boundary Reverify` reconfirmed env-backed and keyring-backed auth-source reporting after the QA pass
  - remaining completion path is now normalized as:
    - `13.5a -- Current Token Requirement Fix`
    - `13.5b -- Auth Boundary Reverify`
    - `13.6 -- Live Authenticated-Online Soak Refresh`
    - `13.7 -- Load Ceiling Decision And Operating Limit`
    - `13.8 -- Launch Verdict Refresh`
    - `Sprint 14 -- Shared Launch Acceptance And Project Closeout`
  - next forward move is `13.6 -- Live Authenticated-Online Soak Refresh`
- Repo-level health blocker cleared again in this checkout:
  - class-size enforcement now follows the actual repo rule that comments, blank lines, and docstrings do not count
  - `QueryEngine` and `GroundedQueryEngine` helper surfaces were split so the effective class sizes are back under the standing 500-line rule
  - full repo gate is green again after fixing:
    - mode-autotune candidate writes so mode-scoped retrieval/query knobs no longer drift with `HYBRIDRAG_ACTIVE_MODE`
    - wildcard document-tag normalization in `src/core/access_tags.py`
- Sprint 14 preparation is now started under explicit forward-execution direction:
  - live shared cutover is still blocked behind `13.6`
  - but the controlled cutover worksheet, post-cutover smoke checklist, final QA/PM freeze checklist, and project completion handoff template are now staged for the acceptance sprint

## Active Sprint Board

| Sprint | Status | Goal | Exit Criteria |
|---|---|---|---|
| Sprint 1 -- QA Closeout and Config Freeze | `DONE` | Finish the config-authority cleanup and freeze the new authority model. | QA signs off on config authority, GUI save/reload, YAML round-trip, mode isolation, and no stale guidance in active docs. |
| Sprint 2 -- Retrieval and Query Debug View | `DONE` | Add Admin-only diagnostics so failures can be traced to retrieval, query policy, or contamination. | Admin debug panel shows retrieved chunks, similarity scores, source files, kept/dropped reasons, effective settings, and active mode/data paths for each query. |
| Sprint 3 -- Tuning UI Redesign | `DONE` | Split tuning into a clean retrieval/query-generation layout and expose the missing mirrored controls. | Tuning screen is split cleanly, offline and online common controls are mirrored, backend-only advanced controls are capability-gated, and the GUI round-trips to YAML cleanly. |
| Sprint 4 -- Query-Side Autotune | `DONE` | Tune query-policy and generation bundles overnight instead of only retriever-side settings. | Autotune can run query/generation bundles, save effective settings with results, and produce a ranked winner set for online and offline. |
| Sprint 5A -- Query Mode Stabilization | `DONE` | Fix offline/online query regressions before further demo or ship work. | 5A.1 through 5A.4 cleared in the 2026-03-12 one-QA workflow for this checkout. |
| Sprint 5 -- Demo Hardening | `IN PROGRESS` | Make the demo path stable, explainable, and rehearsed. | Clean index, stable online-first demo config, rehearsal question bank, retrieval debug ready for troubleshooting, and offline demo path kept Admin-only. |
| Sprint 6 -- Shared Online Deployment | `IN PROGRESS` | Prepare the workstation-hosted intranet deployment for small-team use. | User-facing web GUI, login identity, visible queue/status, audit logging, and online-only shared path are working. |
| Sprint 7 -- Admin Operations Console | `IN PROGRESS` | Expand the Admin side into the operational control surface. | Admin can review logs, audits, queue state, retrieval traces, profiles, and indexing schedule from one place. |
| Sprint 8 -- Offline/Admin Specialization | `DONE` | Keep offline mode isolated for PII/admin/demo/nightly use without contaminating shared online behavior. | Offline mode is admin-scoped, path-isolated, and validated not to leak settings or data into online mode. |
| Sprint 9 -- Role-Based Access and Document Controls | `DONE` | Add document-level authorization and role-aware retrieval for shared deployment. | Users only retrieve authorized documents, denied retrieval attempts are logged, and role/profile policy is test-covered. |
| Sprint 10 -- Scheduled Operations and Freshness | `DONE` | Automate indexing cadence, freshness checks, and operator alerting. | Scheduled index runs, stale-content visibility, failure alerts, and maintenance actions are surfaced in the operator console. |
| Sprint 11 -- Conversational Workflow and Shared History | `DONE` | Add follow-up question handling and persistent team query history. | Browser and Admin users can resume query threads, ask follow-ups, and review saved history without losing auditability or source integrity. |
| Sprint 12 -- Security Hardening and Data Protection | `DONE` | Close the main production-grade security gaps for shared use. | Encryption-at-rest path, secret rotation story, audit-access controls, anomaly detection, and security docs are implemented and validated. |
| Sprint 13 -- Launch Cutover and Scale Readiness | `BLOCKED` | Finish launch prep, soak testing, and operator runbooks for sustained shared use. | Desktop command center covers the primary CLI/operator path, and launch checklist, backup/restore, performance baselines, multi-user soak results, and rollback/runbook docs are complete. |
| Sprint 14 -- Shared Launch Acceptance and Project Closeout | `IN PROGRESS` | Convert the launch-ready system into a formally accepted project completion state. | Controlled cutover or explicit rollback verdict is documented, final QA/PM signoff is recorded, project docs are frozen, and the completion handoff is ready for maintenance-only work. |
| Sprint 15 -- Retrieval Quality and QA Hardening | `DONE` | Fix QA audit findings, recalibrate retrieval scoring, close cosmetic and test gaps. | All CRITICAL/HIGH findings fixed, source path scores calibrated, PPTX multi-paragraph fix, demo mode isolation, export test coverage. QA cleared 2026-03-15: 847 passed, 6 skipped, 0 failed. |
| Sprint 16 -- Reranker Revival and Retrieval Improvements | `DONE` | Replace retired sentence-transformers reranker with Ollama-based scorer, improve corrective retrieval. | Ollama reranker opt-in, retriever lazy-load wiring, corrective reformulation with stopword removal, query decomposition in streaming. QA cleared 2026-03-15: 847 passed, 6 skipped, 0 failed. |
| Sprint 17 -- Live API Validation (GPT-4o) | `IN PROGRESS` | Leverage GPT-4o API access to run previously-blocked live online tests and close Sprint 5 demo blocker. | Demo preflight GO, real E2E query test, cost tracker validation, FastAPI /query live smoke. |
| Sprint 18 -- DPI Audit Hardening + Test Modernization | `DONE` | Close remaining DPI audit findings, add property-based and RRF tests, stabilize flaky tests with time-machine. | 18.1-18.10 done. 18.11-18.12 LATER (BEAST). 871+ tests pass. |
| Sprint 19 -- Deep QA Hardening | `DONE` | Fix critical/high findings from 2026-03-15 deep packet QA audit across core engine, API, GUI, and parsers. | 4 critical fixes verified, rate limiter hardened, GUI class splits done, silent exceptions replaced with logging. 871+ tests pass. |

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

## Sprint 5A Detail

### Why This Sprint Is Active

- Direct user reports describe two active regressions:
  - offline query failure hitting `https://127.0.0.1:11434/api/generate`
  - online low-grounding behavior blocking basic questions as if grounding were maxed out
- The 2026-03-12 deep-inspection passes produced concrete findings that are strong enough to guide implementation and QA targeting.
- Demo hardening should not proceed until the base offline/online query path is stable again.

### Advisory Findings Synthesized Into This Sprint

- Offline inspector:
  - current loaded offline state still points at `http://localhost:11434`, so the reported HTTPS localhost failure is likely coming from runtime normalization, stale boot handling, or a mode-specific persistence path rather than the static YAML alone
  - `boot_hybridrag()` appears to still treat loaded config like a dict in several places, so boot-time mode selection, custom Ollama base URL handling, and vLLM probing may be stale or broken
  - GUI/bootstrap paths use `GroundedQueryEngine`, but FastAPI still builds plain `QueryEngine`, so grounding-bias semantics are not uniform across entry points
- Online inspector:
  - per-mode storage and runtime projection are intentionally separated, so this is likely a query-policy mapping or runtime reapplication issue rather than a flat config-authority collision
  - online mode still uses synthetic streaming only; this is a valid follow-up item but not the current blocker
  - online open-knowledge fallback remains deliberate behavior when enabled; QA must distinguish between intended fallback and unintended hard-blocking
- Online packet-trace advisory:
  - online mode remains local retrieval/context/prompt plus remote generation only, so the remote boundary is narrower than the user symptom might suggest
  - GUI and REST mode switches look transactionally correct before `config.mode` commit
  - packet-boundary evidence does not currently implicate online request assembly, endpoint routing, or provider parameter wiring as the primary blocker
  - that shifts priority toward effective query-policy semantics, low-grounding behavior, use-case bundle side effects, and source-sufficiency handling at query time

### Must-Fix Scope

- Repair localhost Ollama endpoint normalization so localhost never routes to HTTPS in offline mode
- Reconcile grounding dial semantics with runtime behavior, especially `1/10`
- Validate the full grounding scale `1..10` with clear expected behavior bands
- Verify repeated `offline -> online -> offline` switching does not leak stale router, model, guard, or retrieval/query-policy state
- Verify basic questions with adequate source data answer reliably in both modes
- Use GUI harness and button-smash style validation where feasible
- For online mode, investigate effective runtime settings and query-policy behavior before spending implementation time on gate/router transactionality unless fresh evidence appears

### Slice Plan

#### Completed Pre-Slice 5A.4a -- GUI E2E Combobox Callback Trap

- Status:
  - approved and closed on 2026-03-12
- Outcome:
  - the GUI E2E harness no longer false-greens combobox-triggered async Tk callback failures
  - targeted regression coverage now exists for the combobox callback-trap path
- Boundary:
  - this pre-slice does not replace the broader `5A.4 -- Harness and Button-Smash Verification` slice

#### Slice 5A.1 -- Offline Localhost Routing

- Scope:
  - localhost Ollama normalization
  - boot/startup handling that may reintroduce wrong localhost assumptions
- Exit criteria:
  - offline localhost never routes to HTTPS
  - targeted normalization and startup tests pass
  - coder sign-off is ready for QA1

#### Slice 5A.2 -- Low-Grounding Semantics

- Scope:
  - `grounding_bias` mapping
  - `allow_open_knowledge` interplay
  - UI contract vs runtime behavior at low settings, especially `1/10`
- Exit criteria:
  - low-grounding online behavior matches the intended dial contract
  - regression tests cover at least the low, middle, and high ends of the dial
  - coder sign-off is ready for QA1

#### Slice 5A.3 -- Entry-Point Parity and Mode Churn

- Scope:
  - grounded vs plain query-engine behavior across GUI/bootstrap/API entry points
  - repeated `offline -> online -> offline` state isolation
- Exit criteria:
  - no reproduced contamination across repeated mode churn
  - entry-point behavior is either aligned or explicitly bounded and documented
  - coder sign-off is ready for QA1

#### Slice 5A.4 -- Harness and Button-Smash Verification

- Scope:
  - GUI harness coverage
  - button-smash stability
  - baseline generative-dial validation path
- Exit criteria:
  - feasible harness coverage is executed
  - basic GUI controls remain stable under repeated interaction
  - residual live-only gaps are explicitly documented

### Planned Team Sequence

1. `Codex_Coder`
2. `QA1`
3. `QA2`
4. `Claude_QA`
5. `Final Approver`
6. `Agent Planner`
7. `Project Manager`

### Operating Rule For Slice Progress

- Do not wait for the entire stabilization scope to be “done” before QA starts.
- Move slice by slice.
- Each slice should have its own coder sign-off, QA review, and PM advancement decision.
- PM can reopen a later slice without invalidating an already accepted earlier slice unless the later work regresses it.

### Required Sign-Off Rule

- Every lane must sign off with exact date, time, role/name, status, test evidence, known limits, and next handoff target.
- PM will not advance the sprint lane without a complete sign-off block.

### Exit Criteria

- Slices 5A.1 through 5A.4 each clear with sign-off
- Offline basic query path verified locally with no HTTPS localhost regression
- Online basic query path verified locally with adequate source data behavior at low grounding
- Grounding dial `1..10` has regression coverage and QA-reviewed semantics
- Mode-switch contamination checks pass across at least coder plus two QA lanes
- Remaining live-only gaps, such as real API-key validation, are explicitly documented rather than implied

## Sprint 5 Detail

### Demo Rules

- shared/demo path is online-first
- offline remains available from the workstation Admin side
- hallucination guard can stay lighter during development, then be tightened for rehearsal
- the demo question bank must be realistic, not just the tiny corpus smoke set
- every `expected_evidence.target` in `docs/04_demo/DEMO_REHEARSAL_PACK.json` must exist in the indexed corpus, or the pack must be revised before Sprint 5 can be treated as rehearsal-ready
- Sprint 5 became active after `Sprint 5A` cleared on 2026-03-12

### Current Verification State -- 2026-03-12 20:36 America/Denver

- Rehearsal-pack validation:
  - `python -m pytest --basetemp output/pytest_tmp_sprint5_audit_pref tests/test_demo_rehearsal_pack.py tests/test_demo_validation_report.py tests/test_demo_transcript_tool.py tests/test_demo_rehearsal_audit.py -q`
  - result: `17 passed in 5.10s`
- Pack-to-index audit:
  - `python tools/demo_rehearsal_audit.py`
  - result: `10/10 passed`
  - artifact: `output/rehearsal_validation/2026-03-12_202952_demo_rehearsal_audit.json`
- GUI smoke rehearsal:
  - `python tools/gui_demo_smoke.py`
  - result: `24/24 checks passed`, `1 skipped`
  - artifact: `output/rehearsal_validation/2026-03-12_203045_gui_demo_smoke_ops_calibration_review_cadence.json`
- Transcript rehearsal:
  - `python tools/demo_transcript.py`
  - result: `passed_with_skips`
  - artifact: `output/rehearsal_validation/2026-03-12_203314_demo_transcript_pm_leadership_styles_compare.json`

### Remaining Sprint 5 Gap

- The rehearsal tooling is now truthful and aligned to the live corpus.
- The remaining blocker is environmental:
  - the online query step still skips because API credentials are not configured in this session
  - Sprint 5 should not be marked `DONE` until at least one live online transcript-style answer executes cleanly with the current pack

## Sprint 6 Detail

### Early Shared-Deployment Foothold -- 2026-03-12

- FastAPI `/status` now exposes:
  - `deployment_mode`
  - `current_user`
  - `api_auth_required`
  - `indexing_active`
  - `network_audit`
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_status tests/test_fastapi_server.py -q`
  - result: `23 passed, 1 warning in 44.20s`

### Shared Status Expansion -- 2026-03-12 21:18 America/Denver

- FastAPI `/status` now also exposes:
  - `indexing`
    - live in-memory indexing snapshot with processed/total/skipped/errored counts, current file, elapsed seconds, and `progress_pct`
  - `latest_index_run`
    - most recent persisted `index_runs` record when the shared SQLite DB contains tracker history
- Compatibility rule:
  - the older top-level `indexing_active` field remains in place for existing clients while the richer nested snapshot is added for new shared-status consumers
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_status_plus tests/test_fastapi_server.py -q`
  - result: `27 passed, 1 warning in 11.03s`
- Interpretation:
  - this materially advances the Sprint 6 "visible queue/status" lane
  - shared web GUI, multi-user identity/auth flows, and broader audit-log consumption still remain open

### Shared Query Activity Visibility -- 2026-03-12 21:20 America/Denver

- FastAPI `/status` now also exposes:
  - `query_activity`
    - compact counters for active queries, recent stored queries, completed count, failed count, and last success/error timestamps
- FastAPI now also provides:
  - `GET /activity/queries`
    - active and recent query entries with question preview, transport (`sync` or `stream`), client host, status, latency, chunk count, and source count
- Security posture:
  - `/activity/queries` follows the same optional `HYBRIDRAG_API_AUTH_TOKEN` enforcement as the mutable/query endpoints when a token is configured
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_query_activity tests/test_fastapi_server.py -q`
  - result: `32 passed, 1 warning in 9.44s`
- Interpretation:
  - this further advances the Sprint 6 "visible queue/status" lane without waiting on the Sprint 5 live-credential blocker
  - shared web GUI, multi-user identity/auth flows, and broader audit-log consumption still remain open

### Shared Network Audit Visibility -- 2026-03-12 21:31 America/Denver

- FastAPI now also provides:
  - `GET /activity/network`
    - recent detailed network-gate audit entries with newest-first ordering, limit support, URL/host/purpose/caller metadata, allow/deny verdict, and ISO timestamps
- Relationship to existing status surfaces:
  - `/status` still exposes the compact `network_audit` summary for cheap polling
  - `/activity/network` is the detail surface for shared dashboards and operator troubleshooting
- Security posture:
  - `/activity/network` follows the same optional `HYBRIDRAG_API_AUTH_TOKEN` enforcement as the other shared activity endpoints when a token is configured
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_network_activity tests/test_fastapi_server.py -q`
  - result: `35 passed, 1 warning in 3.58s`
- Interpretation:
  - this advances the Sprint 6 "audit logging / audit visibility" lane without waiting on the Sprint 5 live-credential blocker
  - shared web GUI and multi-user identity/auth flows still remain open

### Shared Auth and Identity Context -- 2026-03-12 21:54 America/Denver

- FastAPI now also provides:
  - `GET /auth/context`
    - resolved request auth posture and effective actor identity for the current request
    - includes `auth_required`, `auth_mode`, `actor`, `actor_source`, `client_host`, and the trusted proxy-header list when proxy identity trust is enabled
- FastAPI query activity now also records:
  - `actor`
  - `actor_source`
  - this makes `/activity/queries` usable for shared deployment dashboards that need to know which shared user or proxy-authenticated operator triggered each query
- Security posture:
  - token enforcement remains unchanged when `HYBRIDRAG_API_AUTH_TOKEN` is configured
  - optional `HYBRIDRAG_API_AUTH_LABEL` now names the shared-token actor when no proxy identity is present
  - reverse-proxy identity headers are ignored by default and are only trusted when `HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS=1`
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/auth_identity.py src/api/query_activity.py src/api/models.py src/api/routes.py tests/test_fastapi_server.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_auth_context tests/test_fastapi_server.py -q`
  - result: `40 passed, 1 warning in 13.32s`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `611 passed, 5 skipped, 7 warnings in 149.04s`
- Interpretation:
  - this advances the Sprint 6 multi-user identity/auth lane without waiting on the Sprint 5 live-credential blocker
  - shared web GUI and fuller login/session management still remain open

### Shared Query Queue Visibility -- 2026-03-12 22:03 America/Denver

- FastAPI now also provides:
  - `GET /activity/query-queue`
    - shared query queue and concurrency status for small-team deployment dashboards
    - includes whether queue control is enabled, configured concurrency and queue depth, active/waiting counts, available slots, saturation state, totals, and latest start/complete/reject timestamps
- FastAPI `/status` now also exposes:
  - `query_queue`
    - the same queue summary for cheap polling alongside the rest of the deployment status payload
- Runtime behavior:
  - optional shared query admission control is now available through:
    - `HYBRIDRAG_QUERY_CONCURRENCY_MAX`
    - `HYBRIDRAG_QUERY_QUEUE_MAX`
  - when concurrency control is enabled, `/query` and `/query/stream` now reject excess load cleanly with a queue-full response instead of silently oversubscribing the workstation
- Security posture:
  - `/activity/query-queue` follows the same optional `HYBRIDRAG_API_AUTH_TOKEN` enforcement as the other shared activity endpoints when configured
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/query_queue.py src/api/server.py src/api/models.py src/api/routes.py tests/test_fastapi_server.py tests/test_query_queue.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_query_queue tests/test_fastapi_server.py tests/test_query_queue.py -q`
  - result: `47 passed, 1 warning in 9.93s`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `614 passed, 5 skipped, 7 warnings in 132.51s`
- Interpretation:
  - this advances the Sprint 6 "visible queue/status" lane from passive activity history into real shared-load visibility and admission control
  - shared web GUI and fuller login/session management still remain open

### Shared Browser Dashboard and Trusted Proxy Boundary -- 2026-03-12 22:07 America/Denver

- FastAPI now also provides:
  - `GET /auth/login`
    - browser login page for the shared deployment token when API auth is enabled
  - `POST /auth/login`
    - validates the shared token and issues an HTTP-only same-origin browser session cookie
  - `POST /auth/logout`
    - clears the browser session cookie
  - `GET /dashboard`
    - read-only shared deployment dashboard that polls `/status`, `/auth/context`, `/activity/queries`, and `/activity/network`
- Auth hardening in the same slice:
  - proxy identity headers are now ignored unless:
    - `HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS=1`
    - the request client host matches `HYBRIDRAG_TRUSTED_PROXY_HOSTS`
    - the request also presents the shared proof header configured by `HYBRIDRAG_PROXY_IDENTITY_SECRET` and optionally renamed via `HYBRIDRAG_PROXY_IDENTITY_SECRET_HEADER`
  - the default trusted-proxy boundary is local-only (`127.0.0.1`, `::1`, `localhost`) until an operator explicitly widens it
- Browser-session behavior:
  - session cookies are HMAC-signed
  - the signing secret defaults to `HYBRIDRAG_API_AUTH_TOKEN` unless `HYBRIDRAG_BROWSER_SESSION_SECRET` is set
  - browser sessions expire automatically via `HYBRIDRAG_BROWSER_SESSION_TTL_SECONDS` or the default 8-hour lifetime
  - dashboard access can bootstrap a browser session from a valid `Authorization` header so API-token tooling can hand off cleanly into the browser view
- Verification:
  - `.venv\\Scripts\\python.exe -m py_compile src/api/browser_session.py src/api/deployment_dashboard.py src/api/web_dashboard.py src/api/auth_identity.py src/api/models.py src/api/server.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\\Scripts\\python.exe -m pytest --basetemp output/pytest_tmp_sprint6_web_dashboard_auth_fix tests/test_api_web_dashboard.py tests/test_fastapi_server.py -q`
  - result: `51 passed, 1 warning in 2.08s`
- Interpretation:
  - this is the first concrete Sprint 6 user-facing web GUI foothold
  - it also resolves the earlier direct proxy-header spoofing defect before building browser-side identity flows on top of the shared deployment surface
  - shared browser query submission and broader web-console workflows still remain open

### Shared Browser Dashboard Snapshot Endpoint -- 2026-03-12 22:27 America/Denver

- FastAPI now also provides:
  - `GET /dashboard/data`
    - one aggregated browser-console snapshot containing:
      - `status`
      - `auth`
      - `queries`
      - `network`
- Browser console behavior:
  - `/dashboard` now refreshes from `/dashboard/data` instead of stitching together four separate browser fetches
  - the shared-console surface still respects the same browser-session and API-token auth rules
- Verification:
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `614 passed, 6 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m py_compile src/api/models.py src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_postchange_sprint6_dashboard_data tests/test_fastapi_server.py tests/test_query_queue.py tests/test_api_web_dashboard.py -q`
  - result: `60 passed, 1 warning in 5.41s`
- Interpretation:
  - this closes one of the remaining shared web-console gaps by giving the browser dashboard a single authenticated data surface

### Shared Browser Streaming Query Workflow -- 2026-03-12 22:33 America/Denver

- Browser console query workflow now supports:
  - streaming mode toggle in the shared dashboard
  - live `/query/stream` token rendering
  - stream cancel control for browser operators
  - existing sync `/query` fallback remains intact
- Browser-session coverage now explicitly includes:
  - browser session auth for `/query/stream`
  - dashboard HTML references to `/query/stream` and the streaming control
- Verification:
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `613 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m py_compile src/api/models.py src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_postchange_sprint6_dashboard_stream tests/test_fastapi_server.py tests/test_query_queue.py tests/test_api_web_dashboard.py -q`
  - result: `66 passed, 1 warning in 5.08s`
- Interpretation:
  - Sprint 6 now has a real browser-side query workflow instead of a status-only shared console
  - broader web-console/Admin consolidation still remains for later Sprint 6 closeout and Sprint 7 work

### Shared Recent Query Detail Surface -- 2026-03-12 22:48 America/Denver

- Query activity records now also retain:
  - `answer_preview`
  - `source_paths`
- Browser console behavior:
  - `/dashboard` now shows a `Latest recent query` panel alongside the recent-query table
  - the panel surfaces the most recent shared query's question, actor, status, transport, answer preview, and top source paths without rerunning the query
- Regression hardening landed in the same pass:
  - seed-entry persistence now reads the live widget text more defensively in `src/gui/panels/tuning_tab_runtime.py`
  - the Tk-sensitive cost-dashboard menu test now skips cleanly when the interpreter enters the same unavailable state already handled elsewhere in the GUI suite
- Verification:
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/test_cost_tracker.py tests/test_gui_integration_w4.py -q`
  - result: `50 passed, 2 skipped in 59.05s`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `614 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m py_compile src/gui/panels/tuning_tab_runtime.py src/api/models.py src/api/query_activity.py src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_cost_tracker.py tests/test_gui_integration_w4.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_postchange_sprint6_recent_detail tests/test_fastapi_server.py tests/test_query_queue.py tests/test_api_web_dashboard.py -q`
  - result: `73 passed, 1 warning in 8.34s`
- Interpretation:
  - Sprint 6 browser workflows are now more useful for shared review without crossing into Sprint 7 Admin operations
  - the current non-FastAPI regression gate is green again after the mid-pass GUI fixes

## Sprint 7 Detail

### Focus

- consolidate the deployment-facing status, queue, auth, and audit surfaces into one real Admin operations workflow
- expose operator-visible indexing state, recent failures, and retrieval/debug context from one control surface instead of endpoint-only inspection
- keep mutating actions explicit, authenticated, and reviewable

### Exit Criteria

- Admin can review logs, audits, queue state, retrieval traces, profiles, and indexing schedule from one place
- operator actions that change shared state are deliberate and regression-tested
- the Admin operations surface is useful without requiring direct raw-endpoint polling

## Sprint 8 Detail

### Focus

- isolate offline/Admin-only workflows from the shared online path
- separate data paths, caches, and runtime state so offline work cannot leak into shared deployment behavior
- codify those boundaries in config and tests

### Exit Criteria

- offline mode is admin-scoped and path-isolated
- offline settings and data paths do not contaminate shared online runtime
- restart and mode-switch behavior preserve the offline/shared boundary

## Sprint 9 Detail

### Focus

- enforce actor-aware document visibility during retrieval and answer assembly
- attach policy decisions to audit trails so denied access is reviewable later
- connect the shared-auth identity work to actual content authorization

### Exit Criteria

- users only retrieve authorized documents
- denied retrieval attempts are logged with enough detail for operator review
- role/profile policy is regression-tested across API and browser flows

## Sprint 10 Detail

### Focus

- automate indexing cadence, freshness visibility, and failure alerting for sustained shared use
- make content staleness and missed runs visible to operators without manual database inspection
- close the gap between one-off indexing and ongoing operations

### Exit Criteria

- scheduled index runs and freshness checks are implemented
- stale-content visibility and maintenance actions surface in the operator console
- failure alerts and recovery next steps are documented and test-covered where practical

## Sprint 11 Detail

### Focus

- add shared conversational workflow instead of single-turn browser querying only
- preserve history, follow-up intent, and auditability together
- make shared query review useful for both browser users and Admin operators

### Exit Criteria

- browser and Admin users can resume query threads and ask follow-ups
- persistent shared history keeps source integrity and auditability
- conversation state does not break retrieval grounding or actor attribution

## Sprint 12 Detail

### Focus

- close the main production-grade security gaps before launch
- harden data protection, secret handling, and audit access for shared use
- reduce the delta between development-safe controls and launch-safe controls

### Exit Criteria

- encryption-at-rest path and secret rotation story are implemented or explicitly bounded
- audit-access controls and anomaly detection are in place
- security docs and validation evidence reflect the real deployment posture

## Sprint 13 Detail

### Focus

- assemble the launch-ready cutover package for sustained team use
- finish soak validation, operator runbooks, and rollback readiness
- make final release go/no-go evidence explicit

### Exit Criteria

- launch checklist and rollback/runbook docs are complete
- backup/restore path and performance baselines are validated
- multi-user soak results and final ship evidence are ready for sign-off

## Tonight Execution Order -- 2026-03-12 22:18 America/Denver

1. Close `Sprint 5` as soon as live API credentials are available so the current demo path is fully exercised online.
2. Finish `Sprint 6` shared browser query workflows and the remaining shared web-console gaps.
3. Move directly into `Sprint 7` Admin operations consolidation.
4. Move directly into `Sprint 8` offline/Admin isolation hardening.
5. Move directly into `Sprint 9` role-based access and document controls.
6. Move directly into `Sprint 10` scheduled operations and freshness.
7. Move directly into `Sprint 11` conversational workflow and shared history.
8. Move directly into `Sprint 12` security hardening and data protection.
9. Finish with `Sprint 13` launch cutover and scale readiness.

### Gating Assumption

- `Sprint 5` still has a real environmental blocker in this checkout until live API credentials exist.
- If that blocker remains, continue `Sprint 6` through `Sprint 13` in order and return to the live Sprint 5 closeout the moment credentials are available.
- Keep the one-QA advancement rule for coder progression unless the user changes it again.
- Each sprint should close through slice-sized implementation plus targeted verification, not one oversized batch.

### Repo Health Update -- 2026-03-12 21:27 America/Denver

- Cleared the near-whole-repo QA blocker on class-size enforcement:
  - `tests/test_phase3_stress.py` now counts class size per the actual repo rule by excluding comments, blank lines, and docstrings
  - `src/core/query_engine.py` now keeps prompt/runtime helper methods in a separate mixin
  - `src/core/grounded_query_engine.py` now keeps guard helper methods in a separate mixin
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_classsize_refactor tests/test_phase3_stress.py tests/test_query_engine.py tests/test_query_stream_resilience_new.py tests/test_query_engine_online_streaming_new.py tests/test_grounded_query_engine_stream.py tests/test_grounded_query_engine_stream_additional_new.py tests/test_grounded_query_stream_resilience_new.py tests/test_runtime_retrieval_sync.py -q`
  - result: `82 passed in 13.38s`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `612 passed, 4 skipped, 7 warnings in 109.17s`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - result: `32 passed, 1 warning in 1.58s`
- Interpretation:
  - the previously reported Phase 3 module-size blocker is cleared in the current worktree
  - Sprint 5 remains blocked only by missing live API credentials, not by repo-wide regression failure

## Sprint 7 Detail

### Focus

- consolidate queue, index, network, retrieval-trace, and query-history visibility into one Admin surface
- add operator actions that belong in the console, such as controlled index start/stop/retry and audit export
- make Admin review fast enough that troubleshooting no longer requires hopping between raw files, Swagger, and the desktop GUI

### Unified Admin Console Shell -- 2026-03-12 22:31 America/Denver

- FastAPI now provides:
  - `GET /admin`
  - `GET /admin/data`
- Operator-facing browser behavior:
  - shows deployment status, auth context, recent query activity, queue pressure, network audit, runtime config, and the latest retrieval trace from one Admin surface
  - reuses the browser-session auth flow when shared token auth is enabled
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/models.py src/api/routes.py src/api/deployment_dashboard.py src/api/web_dashboard.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint7_admin tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `69 passed in 4.20s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Retrieval Trace Explorer -- 2026-03-12 22:37 America/Denver

- Query-trace capture now retains a small recent in-memory history with stable `trace_id` values.
- FastAPI now also provides:
  - `GET /admin/traces/{trace_id}`
- Operator-facing browser behavior:
  - `/admin` renders recent traces as selectable entries instead of only showing the newest trace
  - selected traces can stay visible across auto-refresh while still present in retained history
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/core/query_trace.py src/api/models.py src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_query_trace.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint7_trace tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `73 passed in 7.98s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Index and Queue Operations -- 2026-03-12 22:45 America/Denver

- Admin console operator actions now include:
  - `Start indexing`
    - browser action that reuses the existing authenticated `POST /index` path
  - `Stop indexing`
    - protected `POST /admin/index/stop` path for cooperative stop requests against the active indexing worker
- Operator-action behavior:
  - start/stop buttons enable or disable from the live indexing snapshot already returned by `/admin/data`
  - stop requests return `409` instead of false success when no indexing job is active
  - both shared-token header auth and browser-session auth are covered for the new stop path
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/models.py src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py tests/test_api_web_dashboard.py -q`
  - result: `70 passed, 1 warning in 3.31s`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
  - result: `615 passed, 6 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
  - result: `50 passed, 1 warning in 8.01s`
  - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -q`
  - result: `20 passed in 6.63s`

### Profile and Runtime Safety Panel -- 2026-03-12 22:45 America/Denver

- `/admin/data` now includes an explicit runtime-safety snapshot for operators:
  - deployment mode
  - active profile
  - grounding/open-knowledge posture
  - auth label and browser-session lifetime
  - trusted-proxy boundary summary
  - source/index path targets
- `/admin` now renders that information as a dedicated `Runtime safety` panel instead of forcing operators to infer the boundary from scattered status fields.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/auth_identity.py src/api/browser_session.py src/api/models.py src/api/routes.py src/api/deployment_dashboard.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint7_safety tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `78 passed in 3.32s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Operator Log Visibility -- 2026-03-12 22:52 America/Denver

- `/admin/data` now includes a compact operator-log snapshot:
  - latest structured app-log file name and recent event summaries
  - recent index-report artifacts with timestamps and sizes
- `/admin` now renders that snapshot in a dedicated `Operator logs` panel so operators can see recent app and indexing evidence without leaving the browser console.
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/models.py src/api/routes.py src/api/deployment_dashboard.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint7_logs tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `79 passed in 4.05s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Planned Slice Order

1. `7.1 -- Unified Admin Console Shell` -- `DONE`
2. `7.2 -- Retrieval Trace Explorer` -- `DONE`
3. `7.3 -- Index and Queue Operations` -- `DONE`
4. `7.4 -- Profile and Runtime Safety Panel` -- `DONE`
5. `7.5 -- Operator Log Visibility` -- `DONE`

### Exit Criteria

- Admin can review recent queries, queue state, index runs, network audit, and retrieval/debug traces from one coherent surface
- operator actions that mutate shared state are explicitly guarded and auditable
- the Admin console is test-covered enough that shared-deployment troubleshooting does not depend on ad hoc manual steps
- Residual note:
  - Sprint 7 still remains `IN PROGRESS` at the board level because indexing-schedule consolidation is not complete yet even though slices `7.1` through `7.5` are now green in the current checkout

## Sprint 8 Detail

### Focus

- split offline/admin runtime paths, caches, and operational knobs away from the shared online path
- keep offline mode available for demo, PII, and nightly/admin use without exposing it as the shared default
- prove that switching between shared online use and admin offline work cannot contaminate data roots, model targets, or policy state

### Offline Access Guardrails -- 2026-03-12 22:58 America/Denver

- Shared browser and shared query surfaces now fail closed when the shared deployment boundary is active but runtime mode is offline:
  - `GET /dashboard`
  - `GET /dashboard/data`
  - `POST /query`
  - `POST /query/stream`
- Auth precedence is preserved for `GET /dashboard/data`:
  - unauthenticated shared requests still get `401`
  - authenticated shared requests in offline mode now get `503`
- Admin runtime safety now exposes:
  - `shared_online_enforced`
  - `shared_online_ready`
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/web_dashboard.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint8_guard_v2 tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `83 passed in 4.30s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Path and State Isolation -- 2026-03-12 23:12 America/Denver

- Shared API `PUT /mode` can no longer downgrade a shared deployment into offline mode:
  - authenticated shared callers now get `409` when they request `offline`
  - runtime mode stays unchanged
  - shared-safe mode persistence is not touched on the rejected path
- Local GUI mode switching now keeps shared restart state isolated:
  - when the shared deployment boundary is active, GUI offline switches remain runtime-local and do not persist `mode=offline` into `config/config.yaml`
  - online persistence still works normally
  - open/local development mode still persists offline switches
- Supporting GUI hardening landed in the same verification pass:
  - online use-case changes skip deployment discovery when no API endpoint exists
  - seed slider writes now honor the bound variable value, fixing offline and online seed persistence in the Admin tuning panel
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/routes.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint8_mode_lock tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `84 passed in 3.46s`
  - `.venv\Scripts\python.exe -m py_compile src/gui/panels/query_panel_use_case_runtime.py src/gui/panels/tuning_tab_runtime.py src/gui/helpers/mode_switch.py tests/test_mode_switch_runtime.py tests/test_gui_integration_w4.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_gui_stability_v2 tests/test_mode_switch_runtime.py tests/test_gui_integration_w4.py -q`
  - result: `41 passed, 1 skipped in 66.40s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`

### Contamination Regression Harness -- 2026-03-12 23:12 America/Denver

- Browser-session regression now proves a rejected shared `PUT /mode -> offline` attempt does not poison the live shared session:
  - the downgrade request returns `409`
  - runtime mode remains `online`
  - the next shared browser-session query still succeeds
- GUI regression now proves online use-case changes skip deployment discovery when no endpoint exists, preventing stray background discovery threads during local/admin-only flows

### Offline Operations Playbook -- 2026-03-12 23:12 America/Denver

- Added the current operator playbook to `docs/04_demo/DEMO_PREP.md` for the workstation-hosted shared deployment path.
- The playbook now defines the sanctioned local/admin offline flow:
  - save Admin defaults first
  - switch offline locally, not through the shared API/browser surface
  - restore defaults and return to online mode before resuming shared service
  - verify `/admin` runtime safety before reopening the workstation for shared use

### Planned Slice Order

1. `8.1 -- Offline Access Guardrails` -- `DONE`
2. `8.2 -- Path and State Isolation` -- `DONE`
3. `8.3 -- Contamination Regression Harness` -- `DONE`
4. `8.4 -- Offline Operations Playbook` -- `DONE`

### Exit Criteria

- offline mode is admin-scoped with separate path/config boundaries where required
- shared web and shared API paths cannot silently fall back into offline/admin-only behavior
- regression coverage demonstrates no cross-contamination between shared online and admin offline workflows

## Sprint 9 Detail

### Focus

- add role-aware document metadata and retrieval-time authorization filters
- map browser/API identities onto role or profile policy instead of treating every shared user as equivalent
- record denied retrieval decisions in audit output so access control is explainable instead of silent

### Planned Slice Order

1. `9.1 -- Role Model and Policy Store` -- `DONE`
2. `9.2 -- Document Classification and Access Tags` -- `DONE`
3. `9.3 -- Retrieval Enforcement and Deny Audit` -- `DONE`
4. `9.4 -- Admin Policy Review Surface` -- `DONE`

### 9.1 Landing Notes -- 2026-03-12 23:21 America/Denver

- Added an env-backed shared access-policy resolver so actor-to-role mapping is deterministic and portable.
- `/auth/context` now exposes:
  - `actor_role`
  - `actor_role_source`
  - `allowed_doc_tags`
  - `document_policy_source`
- Query activity entries now persist the same role/tag scope for sync, stream, token, browser-session, and trusted-proxy actor paths.
- Focused verification for the role-policy slice:
  - `.venv\Scripts\python.exe -m py_compile src/api/access_policy.py src/api/auth_identity.py src/api/models.py src/api/query_activity.py src/api/routes.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint9_roles tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py -q`
  - result: `86 passed in 4.36s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 PASS, 0 FAIL`

### 9.2 Through 9.4 Closeout -- 2026-03-12 23:48 America/Denver

- `9.2 -- Document Classification and Access Tags`
  - document tag defaults and path rules are covered directly in `tests/test_access_tags.py`
  - index-time tag classification is covered through `Indexer`
  - retriever source summaries now carry `access_tags` plus `access_tag_source`
- `9.3 -- Retrieval Enforcement and Deny Audit`
  - shared query routes now project `document_policy_source` into the request-scoped retrieval context
  - deny-all retrieval results stay closed instead of falling through to open-knowledge answers
  - shared query activity now records:
    - `document_policy_source`
    - `denied_hits`
  - query traces now preserve the policy source in both request access context and retrieval access-control summaries
- `9.4 -- Admin Policy Review Surface`
  - the Admin console snapshot already exposes the active access-policy review payload with:
    - default document tags
    - actor-to-role mappings
    - role tag policies
    - document tag rules
    - recent denied-trace visibility
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/core/request_access.py src/core/retriever.py src/core/query_trace.py src/api/routes.py src/api/query_activity.py src/api/models.py tests/test_query_engine.py tests/test_query_trace.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `python -m pytest tests/test_query_engine.py tests/test_query_trace.py -q`
  - result: `14 passed in 0.46s`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py tests/test_api_web_dashboard.py -q`
  - result: `82 passed, 1 warning in 4.42s`
  - required post-change gate:
    - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
    - result: `636 passed, 6 skipped, 7 warnings in 120.60s`
    - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
    - result: `56 passed, 1 warning in 8.00s`
    - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -q`
    - result: `27 passed in 2.48s`
    - required virtual suites:
      - `phase1` `55 PASS`
      - `phase2` `63 PASS, 1 SKIP`
      - `phase4` `152 PASS, 5 WARN, 1 SKIP`
      - `view_switching` `51 PASS`
      - `setup_wizard` `54 PASS`
      - `setup_scripts` `103 passed`
      - `guard_part1` `97 PASS`
      - `guard_part2` `61 PASS`
      - `setup_group_policy` `30 passed`
      - `ibit_reference` `66 PASS`
      - `offline_isolation` `8 PASS`

### 9.2 Landing Notes -- 2026-03-12 23:46 America/Denver

- Document-access tagging is now materially verified instead of implicit:
  - added dedicated rule/default normalization coverage in `tests/test_access_tags.py`
  - indexer regression now proves `resolve_document_access_tags()` is applied to chunk metadata before persistence
  - retriever source summaries now surface:
    - `access_tags`
    - `access_tag_source`
- Repo-health fixes required to keep the sprint ladder green in the same pass:
  - `tools/run_mode_autotune.py` now writes candidate knobs to explicit `modes.<mode>.*` paths so autotune config generation cannot drift with `HYBRIDRAG_ACTIVE_MODE`
  - `src/core/access_tags.py` now honors the `*` wildcard tag during normalization
  - guarded streaming moved into `_gqe_query_stream()` so `GroundedQueryEngine` is back under the repo's 500-line class limit
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/core/access_tags.py src/core/retriever.py src/core/grounded_query_engine.py tools/run_mode_autotune.py tests/test_access_tags.py tests/test_indexer.py tests/test_retriever_structured_queries.py tests/test_mode_autotune.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_access_tags.py tests/test_indexer.py tests/test_retriever_structured_queries.py tests/test_mode_autotune.py tests/test_runtime_retrieval_sync.py tests/test_grounded_query_engine_stream_additional_new.py tests/test_query_engine_online_streaming_new.py tests/test_phase3_stress.py::TestModuleSizeEnforcement::test_core_classes_under_500_lines -q`
  - result: `45 passed`
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `634 passed, 6 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `717 passed, 6 skipped, 7 warnings`

### Exit Criteria

- authorized users only see documents they are permitted to retrieve
- unauthorized retrieval attempts are blocked and auditable
- tagging, policy configuration, and role/profile mapping are documented and test-covered

## Sprint 10 Detail

### Focus

- add scheduled indexing windows, stale-content visibility, and maintenance reminders
- surface freshness age, failed runs, and retry state in the operator tooling
- make routine upkeep predictable instead of relying on memory and manual spot checks

### Planned Slice Order

1. `10.1 -- Scheduled Index Runner` -- `DONE`
2. `10.2 -- Freshness and Drift Dashboard` -- `DONE`
3. `10.3 -- Alerting and Failure Surfacing` -- `DONE`
4. `10.4 -- Maintenance Controls` -- `DONE`

### Scheduled Index Runner -- 2026-03-13 00:04 America/Denver

- `10.1 -- Scheduled Index Runner` is now landed and verified in the active checkout.
- Delivered in this pass:
  - added `src/api/index_schedule.py` as the env-backed schedule tracker and due-run helper
  - added `src/api/indexing_runtime.py` so manual and scheduled indexing reuse the same background worker path
  - FastAPI `/status` and Admin `/admin/data` now include `index_schedule` snapshots
  - server startup now initializes an env-backed schedule tracker and runs a lightweight polling thread when a schedule is configured
  - the Admin browser console now shows `Index schedule` status, cadence, next run, last result, and source path

### Freshness and Drift Dashboard -- 2026-03-13 00:12 America/Denver

- `10.2 -- Freshness and Drift Dashboard` is now landed and verified in the active checkout.
- Delivered in this pass:
  - added `src/api/content_freshness.py` as a cached source-tree freshness snapshot helper aligned to the configured indexing extensions and excluded folders
  - Admin `/admin/data` now includes `freshness` with:
    - source-folder existence
    - total indexable files
    - newest source-file timestamp/path
    - last index run timestamp/status
    - count of files newer than the last recorded run
    - stale/fresh summary text
  - the Admin browser console now shows `Freshness and drift` so operators can see source churn without opening the file share or SQLite DB manually
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/content_freshness.py src/api/models.py src/api/routes.py src/api/deployment_dashboard.py tests/test_content_freshness.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest --basetemp output/pytest_tmp_post_sprint10_freshness tests/test_content_freshness.py tests/test_index_schedule.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py tests/test_query_queue.py tests/test_query_trace.py tests/test_access_tags.py tests/test_query_engine.py tests/test_grounded_query_engine_stream_additional_new.py tests/test_runtime_retrieval_sync.py -q`
  - result: `136 passed in 6.99s`
  - `python tests/virtual_test_view_switching.py`
  - result: `51 pass, 0 fail`
- Verification evidence:
  - `.venv\Scripts\python.exe -m py_compile src/api/index_schedule.py src/api/indexing_runtime.py src/api/models.py src/api/routes.py src/api/server.py src/api/deployment_dashboard.py tests/test_index_schedule.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_index_schedule.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py -q`
  - result: `83 passed in 4.49s`
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `638 passed, 7 skipped, 7 warnings in 118.56s`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `718 passed, 6 skipped, 7 warnings in 110.80s`
- Interpretation:
  - this slice completed the freshness visibility lane
  - the next forward move at that checkpoint was `10.3 -- Alerting and Failure Surfacing`

### Alerting and Failure Surfacing -- 2026-03-13 00:18 America/Denver

- `10.3 -- Alerting and Failure Surfacing` is now treated as landed and reverified in the active checkout.
- Delivered in this pass:
  - operator alert summaries from `src/api/operator_alerts.py` are wired into Admin `/admin/data`
  - the Admin browser console renders `Active alerts` with severity, code, message, and action guidance
  - alert rules cover shared-offline blocking, queue saturation, source drift, stale freshness, failed index runs, and failed/due schedule states
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/operator_alerts.py src/api/models.py src/api/routes.py src/api/deployment_dashboard.py tests/test_operator_alerts.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_operator_alerts.py tests/test_api_web_dashboard.py tests/test_fastapi_server.py -q`
  - result: `90 passed in 4.93s`

### Maintenance Controls -- 2026-03-13 00:18 America/Denver

- `10.4 -- Maintenance Controls` is now landed and verified in the active checkout.
- Delivered in this pass:
  - added `POST /admin/index/reindex-if-stale` as a maintenance-safe recovery action
  - the new action only starts indexing when the source tree is stale, returns a clean no-op when content is already fresh, and preserves the existing missing-source conflict boundary
  - the Admin browser console now exposes `Reindex if stale` beside the existing start/stop controls
  - browser-session and API-token auth coverage now explicitly protect the new maintenance action
- Verification:
  - `.venv\Scripts\python.exe -m py_compile src/api/routes.py src/api/web_dashboard.py src/api/deployment_dashboard.py tests/test_fastapi_server.py tests/test_api_web_dashboard.py`
  - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py tests/test_api_web_dashboard.py -q`
  - result: `92 passed, 1 warning in 5.55s`
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `650 passed, 5 skipped, 7 warnings in 125.08s`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `740 passed, 6 skipped, 7 warnings in 126.47s`
- Interpretation:
  - Sprint 10 exit criteria are now satisfied in the active checkout
  - next forward move is `11.1 -- Conversation Thread Model`

### Exit Criteria

- scheduled or repeatable index operations can run with observable status and failure reporting
- operators can see stale corpus areas and maintenance debt at a glance
- maintenance actions and failures are visible from the shared/Admin operations surfaces

## Sprint 11 Detail

### Focus

- add multi-turn query continuity for browser and Admin operators
- persist thread-safe query history so follow-ups, bookmarks, and handoffs survive page refreshes and session restarts
- keep citations and audit semantics intact even when a question depends on prior context

### Planned Slice Order

1. `11.1 -- Conversation Thread Model`
2. `11.2 -- Follow-Up Query Handling`
3. `11.3 -- Shared History Browser`
4. `11.4 -- Retention and Export Controls`

### Exit Criteria

- users can ask follow-up questions against a persisted conversation thread
- saved/shared history remains attributable to actor identity and source evidence
- browser and Admin workflows can resume prior investigative threads without losing traceability

## Sprint 12 Detail

### Focus

- close the main shared-deployment security gaps called out in the audit notes
- harden secrets, audit visibility, session invalidation, and anomaly detection
- establish the at-rest protection story instead of leaving it as a roadmap-only statement

### Planned Slice Order

1. `12.1 -- Secret Handling and Rotation`
2. `12.2 -- Protected Data Storage`
3. `12.3 -- Audit Access Controls and Anomaly Detection`
4. `12.4 -- Security Documentation and Recovery Procedure`

### 12.2 Protected-Storage Enforcement Follow-Up -- 2026-03-13 05:16 America/Denver

- shared FastAPI startup now fails closed when `HYBRIDRAG_REQUIRE_PROTECTED_STORAGE=1` and either the main DB or the conversation-history DB sits outside `HYBRIDRAG_PROTECTED_STORAGE_ROOTS`
- Admin `/admin/data` now includes `storage_protection` with:
  - mode
  - required flag
  - configured protected roots
  - tracked, protected, and unprotected data paths
  - an operator-facing summary string
- the Admin browser console now renders that snapshot in a dedicated `Data protection` panel beside the existing runtime-safety posture
- operator alerts now raise `protected_storage_unprotected_paths` when tracked DB files fall outside the configured protected roots
- the server also applies best-effort local permission hardening to the configured main/history SQLite paths after startup

### Exit Criteria

- the chosen encryption-at-rest path is implemented or explicitly integrated
- secret rotation and session invalidation behavior are documented and test-covered
- suspicious query-rate or auth behavior is detectable from the operational surfaces

## Sprint 13 Detail

### Focus

- run the final production-style stabilization passes for shared use
- capture launch docs: deployment checklist, rollback, backup/restore, performance baseline, and soak evidence
- make the system supportable by someone other than the current live developer session

### Planned Slice Order

1. `13.0 -- GUI/CLI Parity Surface And Harness` -- `DONE`
2. `13.0a -- Explorer-Safe GUI BAT Launcher` -- `DONE` (QA verified 2026-03-16: 8/8 tests pass)
3. `13.0b -- User Guide Refresh And Printable Export` -- `DONE`
4. `13.0c -- Corporate PowerShell Entrypoint Hardening` -- `DONE`
5. `13.1 -- Multi-User Soak and Performance Baseline` -- `DONE`
6. `13.2 -- Backup, Restore, and Rollback Drill` -- `DONE`
7. `13.3 -- Launch Checklist and Operator Runbook` -- `DONE`
8. `13.4 -- Cutover Readiness Review` -- `DONE`
9. `13.5 -- Shared Launch Auth And Preflight` -- `DONE`
10. `13.5a -- Current Token Requirement Fix` -- `DONE`
11. `13.5b -- Auth Boundary Reverify` -- `DONE`
12. `13.5c -- Preflight Online-Credential Blocker Surfacing` -- `DONE` (QA verified 2026-03-16: preflight/cutover/launch tests pass)
13. `13.6 -- Live Authenticated-Online Soak Refresh` -- `BLOCKED (ENV)`
14. `13.7 -- Load Ceiling Decision And Operating Limit` -- `NEXT`
15. `13.8 -- Launch Verdict Refresh` -- `NEXT`

### 13.0 GUI/CLI Parity Surface And Harness -- 2026-03-13 09:28 America/Denver

- Sprint 13 parity work now includes both the QA tooling and the shipped desktop operator surface.
- QA/support infrastructure retained:
  - `tools/gui_cli_parity_model.py`
  - `tools/gui_cli_parity_harness.py`
  - `src/gui/testing/gui_cli_parity_harness.py`
  - `src/gui/testing/gui_cli_parity_probes.py`
  - `tools/gui_cli_parity.py`
  - `docs/03_guides/GUI_CLI_PARITY_HARNESS.md`
- Shipped operator surface:
  - `src/gui/command_center_registry.py`
  - `src/gui/command_center_runtime.py`
  - `src/gui/panels/command_center_panel.py`
  - wiring in `src/gui/app.py`, `src/gui/app_runtime.py`, `src/gui/panels/panel_registry.py`, and `src/gui/panels/panel_keys.py`
- The `Command Center` reuses the existing HybridRAG dark-mode theme, card layout, and navigation structure instead of introducing a separate launcher palette.
- The desktop GUI now covers the 19 primary `rag-*` actions from `start_hybridrag.ps1` by:
  - routing mature workflows natively for query, index, model selection, mode switching, credential storage, paths, and status
  - running CLI-backed utilities in-panel for diagnostics, API tests, model listing, profile switching, FastAPI server launch, and detached GUI launch
- Full-gate follow-up in the same pass fixed the seed-entry recovery bug in `src/gui/panels/tuning_tab_runtime.py`:
  - valid numeric seed text now wins over stale `IntVar` state after temporary invalid input
  - blank or invalid temporary text still leaves the persisted seed unchanged instead of throwing
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests/test_command_center_panel.py tests/test_view_aliases.py tests/test_launch_gui_startup.py -q`
  - result: `15 passed in 0.84s`
  - `python -m pytest tests/test_gui_integration_w4.py::test_12c_seed_entry_tolerates_temporary_invalid_text -q`
  - result: `1 passed in 0.83s`
  - `python tests\virtual_test_phase1_foundation.py`
  - result: `55 PASS, 0 FAIL`
  - `python tests\virtual_test_view_switching.py`
  - result: `51 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
  - result: `679 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
  - result: `796 passed, 5 skipped, 7 warnings`
- PM interpretation:
  - Sprint 13 no longer treats GUI/CLI parity as harness-only future work; the real desktop command surface is now present in the app
  - the parity board and runtime runner remain acceptance tooling for future GUI growth instead of being the only GUI story

### 13.0a Explorer-Safe GUI BAT Launcher -- 2026-03-13 14:16 America/Denver

- Hardened `start_gui.bat` as the real one-click GUI launcher for Explorer and terminal use.
- Launcher behavior now includes:
  - repo-root resolution from the batch file location instead of caller working directory
  - explicit `.venv` and `launch_gui.py` entrypoint checks with plain-English failures
  - environment setup for `HYBRIDRAG_PROJECT_ROOT`, `PYTHONPATH`, proxy bypass, and UTF-8
  - optional `--detach` mode for a console-free launch path
  - dry-run and no-pause support so QA can execute the real batch file without opening the GUI
- Added real Windows batch-execution coverage in:
  - `tests/test_start_gui_bat.py`
- Existing GUI-startup and setup-wizard launch guards stayed green.
- Verification:
  - `python -m pytest tests/test_start_gui_bat.py -q`
    - result: `5 passed`
  - `python -m pytest tests/test_launch_gui_startup.py -q`
    - result: `6 passed`
  - `python tests\virtual_test_setup_wizard.py`
    - result: `54 PASS, 0 FAIL`
  - `python tests\virtual_test_phase1_foundation.py`
    - result: `55 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
    - result: `704 passed, 8 skipped, 7 warnings`
- PM interpretation:
  - the GUI now has a documented and testable BAT-first startup path that QA can exercise directly
  - this is a Sprint 13 launch-support slice and does not change the environment blocker on `13.6`

### 13.0b User Guide Refresh And Printable Export -- 2026-03-13 14:16 America/Denver

- Refreshed the three main end-user guides to match the current shipped app:
  - `docs/03_guides/USER_GUIDE.md`
  - `docs/03_guides/CLI_GUIDE.md`
  - `docs/03_guides/GUI_GUIDE.md`
- The refreshed guides now document:
  - `start_gui.bat`, `start_gui.bat --detach`, `start_rag.bat`, and direct Python launch
  - the current single-window GUI anatomy (`File | View | Admin | Help`, nav tabs, status bar)
  - the dark-mode `Command Center` as the GUI surface for CLI-equivalent workflows
  - shared-launch preflight usage from both CLI and GUI
- Primary DOCX outputs now align with the guide-local files:
  - `docs/03_guides/USER_GUIDE.docx`
  - `docs/03_guides/CLI_GUIDE.docx`
  - `docs/03_guides/GUI_GUIDE.docx`
- Supplemental numbered packet copies remain available for the landing and GUI guides:
  - `docs/_printable/20_User_Guide.docx`
  - `docs/_printable/21_GUI_Guide.docx`
- QA follow-up fix:
  - corrected stale guide references so the landing guide points at `USER_GUIDE.docx`, `CLI_GUIDE.docx`, and `GUI_GUIDE.docx`
  - added the CLI guide entry to the root `README.md` documentation index
  - corrected `docs/01_setup/INSTALL_AND_SETUP.md` metadata and setup-link references
  - added explicit `start_gui.bat` and `start_gui.bat --detach` launch guidance to the refreshed markdown guides
  - kept the numbered `_printable` packet copies documented as supplemental outputs instead of the primary guide-local DOCX set
- PM interpretation:
  - the launcher and the user-facing documentation are now aligned
  - QA can review the BAT launcher slice against current docs instead of stale pre-Command-Center guidance
  - QA cleared this slice on `2026-03-13 17:44 America/Denver`

### 13.0c Corporate PowerShell Entrypoint Hardening -- 2026-03-13 17:18 America/Denver

- Hardened the direct PowerShell entrypoints that operators are most likely to use on managed machines:
  - `start_hybridrag.ps1`
  - `tools/launch_gui.ps1`
  - `tools/setup_home.ps1`
  - `tools/build_usb_deploy_bundle.ps1`
  - `tools/usb_install_offline.ps1`
- Each now attempts:
  - `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force -ErrorAction SilentlyContinue`
  - before the main script body, so direct PowerShell use does not rely entirely on a wrapper BAT file
- Additional launch-path hardening:
  - `tools/launch_gui.ps1` now sets the current directory to repo root, exports `HYBRIDRAG_PROJECT_ROOT`, and exports `.venv` context before launching the GUI
  - `tools/build_usb_deploy_bundle.ps1` now prefers repo `.venv\Scripts\python.exe` using `$projectRoot` instead of the caller working directory
- Regression coverage added in:
  - `tests/test_powershell_entrypoints.py`
  - `tests/virtual_test_setup_scripts.py`
- Verification:
  - `python -m pytest tests/test_powershell_entrypoints.py tests/test_start_gui_bat.py tests/test_launch_gui_startup.py -q`
    - result: `14 passed`
  - `python tests\virtual_test_setup_scripts.py`
    - result: `107 passed, 0 failed`
  - `python tests\virtual_test_setup_group_policy.py`
    - result: `30 passed, 0 failed`
  - `python tests\virtual_test_setup_wizard.py`
    - result: `54 PASS, 0 FAIL`
  - `python tests\virtual_test_phase1_foundation.py`
    - result: `55 PASS, 0 FAIL`
  - `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --dry-run`
    - result: correct repo-root and terminal target
  - `cmd.exe /d /c D:\HybridRAG3\start_gui.bat --detach --dry-run`
    - result: correct detached `pythonw.exe` target
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
    - result: `709 passed, 6 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
    - result: `832 passed, 4 skipped, 7 warnings`
- PM interpretation:
  - corporate PowerShell launches are now more self-contained and less dependent on wrapper-specific policy bypass
  - this slice does not change the Sprint `13.6` environment blocker; it hardens the operator entrypoints around it
  - QA cleared this slice on `2026-03-13 17:44 America/Denver`

### 13.1 Shared Deployment Soak Tooling -- 2026-03-13 09:25 America/Denver

- Added the repeatable shared soak runner:
  - `src/tools/shared_deployment_soak.py`
  - `tools/shared_deployment_soak.py`
  - `tests/test_shared_deployment_soak_tool.py`
- The new tooling now:
  - loads prompts from flat text files or the existing demo rehearsal-pack JSON shape
  - exercises the live shared API surfaces used by operators:
    - `/health`
    - `/status`
    - `/auth/context`
    - `/activity/query-queue`
    - `/activity/queries`
    - `/query`
  - records per-run totals plus p50/p95/max client and server latency, queue peaks, mode counts, and error buckets
  - writes timestamped JSON evidence into `output/shared_soak/`
- Semi-live baseline evidence for this slice now exists in the active checkout:
  - `output/shared_soak/2026-03-13_091702_shared_deployment_soak.json`
  - this artifact was generated in-process against the real FastAPI app surfaces with deterministic query responses so the report shape is grounded to the actual shared deployment API
- Refreshed semi-live baseline evidence:
  - `output/shared_soak/2026-03-13_094723_shared_deployment_soak.json`
  - generated in-process against the real FastAPI app surfaces with the live FastAPI lifespan, request routing, queue tracking, and query activity surfaces active
  - summary:
    - `8/8` successful requests
    - client latency `p50=144.69ms`, `p95=176.41ms`, `max=188.45ms`
    - server latency `p50=p95=max=18.5ms`
- Workstation-backed live evidence now exists as well:
  - ceiling/failure case:
    - `output/shared_soak/2026-03-13_102643_shared_deployment_soak.json`
    - `1/5` successful at `concurrency=2` with four `90s` timeouts
  - low-concurrency baseline:
    - `output/shared_soak/2026-03-13_103135_shared_deployment_soak.json`
    - `2/2` successful at `concurrency=1`
    - client latency `p50=127122.7ms`, `p95=173533.5ms`, `max=178690.3ms`
    - server latency `p50=126929.2ms`, `p95=173252.2ms`, `max=178399.2ms`
- Verification:
  - `python -m py_compile src\tools\shared_deployment_soak.py tools\shared_deployment_soak.py tests\test_shared_deployment_soak_tool.py`
  - result: `passed`
  - `python -m pytest tests/test_shared_deployment_soak_tool.py -q`
  - result: `7 passed, 1 skipped`
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_soak_tool.py -q`
  - result: `8 passed`
- PM interpretation:
  - Sprint `13.1` now has both a reproducible semi-live path and real workstation-backed live evidence
  - the current workstation ceiling is documented instead of guessed:
    - `concurrency=1` is the live safe baseline
    - `concurrency=2` with the full rehearsal pack exceeded the current live ceiling
  - this is enough to advance to `13.2`

### 13.2 Backup, Restore, and Rollback Drill -- 2026-03-13 10:34 America/Denver

- The backup/restore drill tooling was already present and green in the checkout:
  - `src/tools/shared_deployment_backup.py`
  - `tools/shared_deployment_backup.py`
  - `tests/test_shared_deployment_backup_tool.py`
- Live drill evidence for this slice now exists in the active checkout:
  - backup bundle:
    - `output/shared_backups/2026-03-13_103253_shared_deployment_backup`
  - restore drill:
    - `output/shared_restore_drills/2026-03-13_103335_shared_restore_drill`
- Live run summary:
  - `1847` files copied
  - main DB quick-check `ok`, `33738` chunks, `1285` sources
  - history DB quick-check `ok`, `200` threads, `200` turns
  - backup verify:
    - `0` missing files
    - `0` hash mismatches
    - main/history fingerprint match `True`
  - restore drill:
    - `1847` files restored
    - `0` SQLite failures
    - main/history fingerprint match `True`
- Live reverify after a real operator-path defect:
  - a fresh live rerun first exposed a history-summary race in the backup manifest:
    - bundle `output/shared_backups/2026-03-13_102947_shared_deployment_backup`
    - verify still showed `0` missing files and `0` hash mismatches, but the history fingerprint mismatched because the manifest summary was reading the mutable live history DB after the copy step
  - the tool was fixed to compute DB summaries and fingerprints from the copied payload snapshot instead of the mutable live source
  - a regression now simulates history drift immediately after the copy step and keeps verify green:
    - `tests/test_shared_deployment_backup_tool.py::test_backup_summary_uses_copied_history_snapshot_when_live_history_changes`
  - refreshed live artifacts after the fix:
    - `output/shared_backups/2026-03-13_104241_shared_deployment_backup`
    - `output/shared_restore_drills/2026-03-13_104315_shared_restore_drill`
  - refreshed live outcome:
    - `1876` files copied
    - `1876` files restored
    - `0` missing files
    - `0` hash mismatches
    - `0` SQLite failures
    - main/history fingerprint match `True`
- Verification:
  - `python -m py_compile src\tools\shared_deployment_backup.py tools\shared_deployment_backup.py tests\test_shared_deployment_backup_tool.py`
  - result: `passed`
  - `python -m pytest tests/test_shared_deployment_backup_tool.py -q`
  - result: `7 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_backup_tool.py -q`
  - result: `7 passed`
  - live commands:
    - `.venv\Scripts\python.exe tools\shared_deployment_backup.py create --project-root D:\HybridRAG3`
    - `.venv\Scripts\python.exe tools\shared_deployment_backup.py verify D:\HybridRAG3\output\shared_backups\2026-03-13_103253_shared_deployment_backup`
    - `.venv\Scripts\python.exe tools\shared_deployment_backup.py restore-drill D:\HybridRAG3\output\shared_backups\2026-03-13_103253_shared_deployment_backup`
    - `python tools\shared_deployment_backup.py create --timestamp 2026-03-13_104241`
    - `python tools\shared_deployment_backup.py verify output\shared_backups\2026-03-13_104241_shared_deployment_backup`
    - `python tools\shared_deployment_backup.py restore-drill output\shared_backups\2026-03-13_104241_shared_deployment_backup --timestamp 2026-03-13_104315`
  - repo-wide post-fix gates:
    - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
    - result: `687 passed, 6 skipped, 7 warnings`
    - `.venv\Scripts\python.exe -m pytest tests/`
    - result: `804 passed, 4 skipped, 7 warnings`
- PM interpretation:
  - Sprint `13.2` is now backed by a real create/verify/restore cycle against the active checkout instead of tool-only confidence
  - the live reverify closed a genuine operator-path race before handoff, so the backup evidence is now based on the fixed manifest boundary rather than the earlier mutable-history behavior
  - the repo now has a refreshed concrete known-good bundle plus a refreshed concrete non-destructive restore drill to anchor rollback docs

### 13.3 Launch Checklist And Operator Runbook -- 2026-03-13 10:34 America/Denver

- Added the consolidated operator packet:
  - `docs/05_security/SHARED_DEPLOYMENT_LAUNCH_CHECKLIST_AND_RUNBOOK_2026-03-13_103437.md`
- The new runbook pulls the active launch path into one place:
  - launch checklist
  - start procedure
  - steady-state operator checks
  - current live soak baseline and ceiling
  - backup/create/verify/restore commands
  - rollback triggers and rollback procedure
  - shutdown procedure
- PM interpretation:
  - Sprint `13.3` now has a single operator-facing document instead of asking a future maintainer to reconstruct launch procedure from scattered sprint notes, demo prep, and security guidance

### 13.4 Cutover Readiness Review -- 2026-03-13 10:34 America/Denver

- Added the cutover review note:
  - `docs/09_project_mgmt/CHECKPOINT_2026-03-13_103437_SPRINT13_CUTOVER_REVIEW.md`
- Review verdict:
  - `NOT READY FOR SHARED LAUNCH / READY FOR CONTROLLED FOLLOW-UP ONLY`
- Positive evidence considered:
  - command-center operator surface is shipped
  - semi-live and workstation-backed soak artifacts exist
  - backup create/verify/restore drill succeeded
  - launch checklist and rollback runbook exist
- Blocking findings from the live review:
  - live soak auth posture remained `open`
  - live soak requests ran in `offline` mode instead of the intended shared-online posture
  - current workstation ceiling is only validated at `concurrency=1`
- PM interpretation:
  - all planned Sprint 13 slices now have real artifacts
  - Sprint 13 itself remains blocked on the launch verdict until auth, mode, and live load posture are corrected for the intended shared cutover

### 13.5 Shared Launch Auth And Preflight -- 2026-03-13 11:09 America/Denver

- Added the canonical shared auth resolver:
  - `src/security/shared_deployment_auth.py`
- Added the shared launch operator tool:
  - `src/tools/shared_launch_preflight.py`
  - `tools/shared_launch_preflight.py`
- Threaded the shared auth source through:
  - `src/api/auth_identity.py`
  - `src/api/browser_session.py`
  - `src/api/server.py`
  - `src/api/routes.py`
  - `src/api/web_dashboard.py`
  - `src/gui/helpers/mode_switch.py`
- Extended the desktop operator surface:
  - `src/gui/command_center_runtime.py`
  - `src/gui/command_center_registry.py`
  - `src/gui/panels/command_center_panel.py`
  - new GUI entry points:
    - `rag-shared-launch`
    - `rag-store-shared-token`
- Functional result:
  - shared API auth no longer depends on env-only process setup
  - production startup can enforce a keyring-backed shared token
  - browser login and session fallback now accept keyring-backed shared tokens and rotated previous tokens
  - runtime-safety/admin surfaces now report the active auth source
  - operators can persist `online` plus `production` posture and check readiness from the CLI tool or the Command Center
- Verification:
  - `python tests\virtual_test_phase1_foundation.py`
    - result: `55 PASS, 0 FAIL`
  - `python tests\virtual_test_view_switching.py`
    - result: `51 PASS, 0 FAIL`
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_auth.py tests/test_mode_switch_runtime.py tests/test_command_center_panel.py -q`
    - result: `25 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
    - result: `80 passed, 1 warning`
  - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -q`
    - result: `40 passed`
  - `.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
    - result: `738 passed, 4 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
    - result: `818 passed, 4 skipped, 7 warnings`
- PM interpretation:
  - the auth and mode blockers identified by the `13.4` cutover review are now addressed in code and operator tooling
  - Sprint 13 remains blocked at the PM level until the live workstation reruns the new preflight path and a fresh soak artifact confirms authenticated online posture
  - the live concurrency ceiling is still only validated at `concurrency=1`

### 13.5a Current Token Requirement Fix -- DONE

- Tightened shared auth readiness semantics so a previous token can extend a rotation window but cannot become the only configured shared launch secret.
- Landed implementation:
  - `src/security/shared_deployment_auth.py`
    - `configured` now requires the current token instead of any non-empty token ring
    - `rotation_enabled` now requires both current and previous tokens
    - accepted request-auth tokens now collapse to `()` when the current token is missing, so previous-token-only posture is no longer treated as valid shared auth
  - `tests/test_shared_deployment_auth.py`
    - added direct regression for previous-token-only shared launch readiness
    - added direct regression for previous-token-only shared launch preflight in `mode=online` plus `deployment_mode=production`
  - `tests/test_fastapi_server.py`
    - added `/auth/context` regression proving previous-token-only requests stay anonymous/open
    - added production startup guard regression proving the API server fails closed when only the previous token exists
  - `src/gui/panels/tuning_tab_runtime.py`
    - hardened seed resolution against stale entry text during large suite runs
  - `tests/test_gui_integration_w4.py`
    - added regression proving programmatic seed updates survive lagging entry text
- Verification:
  - `python -m pytest tests/test_shared_deployment_auth.py tests/test_gui_integration_w4.py -q`
    - result: `44 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
    - result: `82 passed, 1 warning`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py`
    - result: `699 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/`
    - result: `823 passed, 4 skipped, 7 warnings`
  - required virtual suites rerun:
    - `phase1`, `phase2`, `phase4`, `view_switching`, `setup_wizard`, `setup_scripts`, `guard_part1`, `guard_part2`, `setup_group_policy`, `ibit_reference`, `offline_isolation`
    - result: green
- QA:
  - `2026-03-13 12:36:36 -06:00`
  - status: passed QA
  - note: Tk-dependent skip counts varied by machine availability, but the authoritative `.venv` full-suite gate stayed green

### 13.5b Auth Boundary Reverify -- DONE

- Pushed the corrected `13.5` slice through QA after the current-token requirement fix landed.
- Acceptance target achieved:
  - QA explicitly confirmed the previous-token-only repro is closed
  - shared auth source reporting still resolves correctly for env-backed and keyring-backed current tokens
- Coder-side reverify:
  - `python -m pytest tests/test_shared_deployment_auth.py -k "prefers_env_over_keyring or falls_back_to_keyring or build_shared_launch_snapshot_ready_with_keyring_token or previous_token_only_does_not_count_as_shared_launch_ready or shared_launch_preflight_previous_token_only_fails_in_production_online_mode" -q`
    - result: `5 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -k "api_auth_source or keyring_token_required or login_accepts_keyring_backed_shared_token" -q`
    - result: `2 passed`
- PM interpretation:
  - the auth-boundary portion of Sprint `13` is now closed
  - the remaining live blocker is no longer auth semantics, it is the workstation-backed authenticated-online rerun in `13.6`

### 13.5c Preflight Online-Credential Blocker Surfacing -- 2026-03-13 15:35 America/Denver

- Extended the shared-launch snapshot so the readiness report now surfaces online API credential posture directly instead of requiring a separate manual `resolve_credentials()` inspection.
- Updated `src/security/shared_deployment_auth.py`:
  - shared-launch snapshots now include:
    - previous-token source/configured state
    - online API readiness
    - online API key, endpoint, and deployment sources
    - operator-facing next-step hints
  - readiness now blocks cleanly when online API credentials are missing
  - formatted preflight output now includes a `Next Steps` section when the posture is blocked
- Updated regressions in:
  - `tests/test_shared_deployment_auth.py`
  - `tests/test_query_threads.py`
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_deployment_auth.py -q`
    - result: `10 passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -k "auth_context_does_not_treat_previous_token_without_current_primary_as_authenticated or production_startup_rejects_previous_token_without_current_primary" -q`
    - result: `2 passed, 80 deselected, 1 warning`
  - `.venv\Scripts\python.exe -m pytest tests/test_api_web_dashboard.py -k "api_auth_source or keyring_token_required or login_accepts_keyring_backed_shared_token" -q`
    - result: `2 passed, 38 deselected`
  - `.venv\Scripts\python.exe -m pytest tests/test_command_center_panel.py -q`
    - result: `8 passed`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
    - result: `829 passed, 4 skipped, 7 warnings`
- PM interpretation:
  - coder-side preflight semantics are now clearer for operators and QA
  - this still does not remove the workstation environment blocker on `13.6`

### 13.6 Live Authenticated-Online Soak Refresh -- BLOCKED (ENV)

- Run the workstation through the shipped shared launch preflight path:
  - store the shared token if needed
  - persist `mode=online`
  - persist `security.deployment_mode=production`
  - fail closed if readiness is still blocked
- Capture fresh live soak evidence showing:
  - authenticated shared posture
  - online runtime mode
  - updated baseline latency
- Current workstation result:
  - `python tools/shared_launch_preflight.py --json --fail-if-blocked`
    - result: blocked with
      - `Shared API auth token is not configured.`
      - `Deployment mode is not production.`
      - `Runtime mode is not online.`
  - `resolve_credentials(use_cache=False)`
    - `has_key=False`
    - `has_endpoint=False`
    - `is_online_ready=False`
- PM interpretation:
  - this slice cannot produce a valid authenticated-online soak artifact until the workstation has both:
    - a shared API auth token
    - online API credentials (key plus endpoint)
  - once those inputs exist, rerun the shipped preflight first and only then refresh the soak artifact

### 13.7 Load Ceiling Decision And Operating Limit -- NEXT

- Re-run the workstation load ceiling after the authenticated-online posture is corrected.
- Completion options:
  - harden the workstation enough to validate a higher ceiling
  - or explicitly freeze the supported operating limit at `concurrency=1`
- Required output:
  - a clear operator-facing supported concurrency statement tied to fresh soak evidence

### 13.8 Launch Verdict Refresh -- NEXT

- Rewrite the cutover review after the corrected auth/mode posture and refreshed soak evidence exist.
- Completion target:
  - either clear Sprint 13 for launch acceptance
  - or document the exact remaining blocker if one still exists

## Sprint 14 Detail

### Focus

- execute the final shared-launch acceptance path after Sprint 13 clears
- convert the launch-ready system into a formally completed project state
- freeze the operator packet, QA evidence, and handoff record for maintenance-only follow-on work

### Planned Slice Order

1. `14.0 -- Closeout Packet Prep` -- `DONE`
2. `14.2a -- Shared Cutover Smoke Automation` -- `IMPLEMENTED / READY FOR QA`
3. `14.3a -- Final QA Freeze Packet Automation` -- `IMPLEMENTED / READY FOR QA`
4. `14.4a -- Completion Handoff Automation` -- `IMPLEMENTED / READY FOR QA`
5. `14.1 -- Controlled Shared Cutover` -- `NEXT`
6. `14.2 -- Post-Cutover Smoke And Rollback Proof` -- `NEXT`
7. `14.3 -- Final QA Sweep And PM Freeze` -- `NEXT`
8. `14.4 -- Project Completion Handoff` -- `NEXT`

### 14.0 Closeout Packet Prep -- DONE

- Added the acceptance-sprint operator packet so Sprint 14 no longer starts from a blank page:
  - `docs/05_security/SHARED_DEPLOYMENT_CONTROLLED_CUTOVER_WORKSHEET_2026-03-13_165338.md`
  - `docs/05_security/SHARED_DEPLOYMENT_POST_CUTOVER_SMOKE_AND_ROLLBACK_CHECKLIST_2026-03-13_165338.md`
  - `docs/09_project_mgmt/FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_165338.md`
  - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_165338.md`
- PM interpretation:
  - this does not clear the live blocker on `13.6`
  - it does mean the next sprint packet is now prepared and reviewable while the environment blocker is being held outside the codebase

### 14.2a Shared Cutover Smoke Automation -- 2026-03-13 17:58 America/Denver

- Added the shared acceptance-smoke tool:
  - `src/tools/shared_cutover_smoke.py`
  - `tools/shared_cutover_smoke.py`
- Functional result:
  - runs the Sprint 14 acceptance-side endpoint checks against:
    - `/health`
    - `/status`
    - `/auth/context`
    - `/dashboard`
    - post-dashboard session `/auth/context`
    - `/admin/data`
  - captures whether the dashboard request bootstrapped a browser session
  - records deployment mode, runtime mode, auth posture, actor/session actor, and blocker text in one timestamped JSON artifact
  - can optionally verify a backup bundle and run a non-destructive restore drill so rollback proof is attached to the same smoke report
  - can auto-select the newest backup bundle via `--backup-bundle latest`
- Added regression coverage in:
  - `tests/test_shared_cutover_smoke_tool.py`
- Verification:
  - `.venv\Scripts\python.exe -m pytest tests/test_shared_cutover_smoke_tool.py tests/test_shared_deployment_soak_tool.py tests/test_shared_deployment_backup_tool.py tests/test_shared_deployment_auth.py -q`
    - result: `30 passed`
  - `python -m py_compile src/tools/shared_cutover_smoke.py tools/shared_cutover_smoke.py tests/test_shared_cutover_smoke_tool.py`
    - result: `passed`
  - `python tools/shared_cutover_smoke.py --help`
    - result: `passed`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
    - result: `713 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/ -q`
    - result: `835 passed, 6 skipped, 7 warnings`
- PM interpretation:
  - Sprint 14 no longer depends on a purely manual smoke/rollback proof pass once the live cutover window opens
  - this is support tooling only; the environment-bound Sprint `13.6` blocker still gates actual launch acceptance

### 14.3a Final QA Freeze Packet Automation -- 2026-03-13 18:47 America/Denver

- Added the final QA/PM freeze evidence collector:
  - `src/tools/final_qa_freeze_packet.py`
  - `tools/final_qa_freeze_packet.py`
- Added regression coverage in:
  - `tests/test_final_qa_freeze_packet_tool.py`
- Updated the final QA checklist command pack:
  - `docs/09_project_mgmt/FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_165338.md`
- Updated the completion handoff template so the freeze packet is part of the frozen artifact set:
  - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_165338.md`
- Functional result:
  - one tool now collects the current Sprint 14 freeze evidence into a timestamped JSON packet under `output/final_qa_freeze/`
  - it auto-discovers the latest:
    - shared cutover smoke artifact
    - shared soak artifact
    - shared backup bundle
    - shared restore drill directory
  - it auto-discovers the latest launch runbook, freeze checklist, and completion handoff template instead of pinning one hardcoded timestamp
  - it now requires an explicit final acceptance state:
    - `accepted`
    - `rolled_back`
    - otherwise the packet stays blocked
  - rollback can now close cleanly when the packet has:
    - an explicit rollback note
    - backup-verify proof
    - restore-drill proof
    - without falsely demanding a green cutover/soak result
  - it links the active sprint plan, PM tracker, launch runbook, freeze checklist, completion handoff template, and shared AI handoff file
  - it can optionally rerun backup verify and a fresh non-destructive restore drill so the freeze packet contains live rollback evidence instead of only stale links
  - it fails closed on the exact remaining blockers instead of forcing QA/PM to infer them from multiple files
- Verification:
  - `python -m py_compile src\tools\final_qa_freeze_packet.py tools\final_qa_freeze_packet.py tests\test_final_qa_freeze_packet_tool.py`
    - result: `passed`
  - `python -m pytest tests/test_final_qa_freeze_packet_tool.py -q`
    - result: `8 passed`
  - `python tools/final_qa_freeze_packet.py --help`
    - result: `passed`
  - `python tools/final_qa_freeze_packet.py --acceptance-state pending --no-write --fail-if-blocked`
    - result: blocked as designed because final acceptance state is still pending
- PM interpretation:
  - Sprint 14 now has a single machine-readable freeze packet instead of a hand-collected evidence list
  - this slice reduces manual PM/QA synthesis work but does not override the live cutover gate
  - the packet can now distinguish:
    - accepted launch freeze
    - explicit rollback freeze
    - still-pending launch posture
  - the next live blocker is still the missing cutover-smoke evidence, which itself depends on the environment-bound shared launch posture

### 14.3a Reject Fix And Reverify -- 2026-03-14 14:05 America/Denver

- Closed the rollback/no-soak QA reject in:
  - `src/tools/final_qa_freeze_packet.py`
  - `tests/test_final_qa_freeze_packet_tool.py`
- Functional correction:
  - `rolled_back` freeze packets no longer require a shared-soak artifact solely for presence when rollback note, backup proof, and restore proof already exist
- Repo-gate stabilization:
  - refreshed `tests/test_content_freshness.py` so the fresh-index case uses relative timestamps instead of a hardcoded date that aged out of the current day
- Refreshed live blocked artifacts:
  - `output/final_qa_freeze/2026-03-14_140545_final_qa_freeze_packet.json`
  - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_2026-03-14_140544.md`
- Verification:
  - `python -m pytest tests/test_final_qa_freeze_packet_tool.py tests/test_content_freshness.py -q`
    - result: `15 passed`
  - direct rollback repro:
    - `rolled_back` + rollback note + linked backup/restore proof + backup bundle + no soak artifact
    - result: `ready_for_freeze=true` and `blockers=[]`
  - `python -m pytest tests/test_project_completion_handoff_tool.py tests/test_final_qa_freeze_packet_tool.py -q`
    - result: `14 passed`
  - `python tools/final_qa_freeze_packet.py --acceptance-state pending`
    - result: wrote current blocked packet
  - `python tools/project_completion_handoff.py --allow-blocked-preview`
    - result: wrote current blocked preview handoff
  - `python tests\virtual_test_phase1_foundation.py`
    - result: `55 PASS, 0 FAIL`
  - `python tests\virtual_test_phase2_exhaustive.py`
    - result: `63 PASS, 0 FAIL, 1 SKIP`
  - `python tests\virtual_test_phase4_exhaustive.py`
    - result: `153 PASS, 0 FAIL, 4 WARN, 1 SKIP`
  - `python tests\virtual_test_view_switching.py`
    - result: `51 PASS, 0 FAIL`
  - `python tests\virtual_test_setup_wizard.py`
    - result: `54 PASS, 0 FAIL`
  - `python tests\virtual_test_setup_scripts.py`
    - result: `110 passed, 0 failed`
  - `python tests\virtual_test_guard_part1.py`
    - result: `97 PASS, 0 FAIL`
  - `python tests\virtual_test_guard_part2.py`
    - result: `61 PASS, 0 FAIL`
  - `python tests\virtual_test_setup_group_policy.py`
    - result: `30 passed, 0 failed`
  - `python tests\virtual_test_ibit_reference.py`
    - result: `66 PASS, 0 FAIL`
  - `python tests\virtual_test_offline_isolation.py`
    - result: `8 PASS, 0 FAIL`
  - `python -m pytest tests/ --ignore=tests/test_fastapi_server.py -q`
    - result: `733 passed, 7 skipped, 7 warnings`
  - `.venv\Scripts\python.exe -m pytest tests/test_fastapi_server.py -q`
    - result: `82 passed, 1 warning`
- PM interpretation:
  - the `14.3a` reject is closed and ready for QA rerun
  - `14.4a` preview generation has been refreshed against the fixed freeze-packet logic
  - the live operational blocker remains `13.6`

### 14.4a Completion Handoff Automation -- 2026-03-13 19:00 America/Denver

- Added the project-completion handoff generator:
  - `src/tools/project_completion_handoff.py`
  - `tools/project_completion_handoff.py`
- Added regression coverage in:
  - `tests/test_project_completion_handoff_tool.py`
- Updated the completion handoff template and freeze checklist so the final operator packet points at the real automation path:
  - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_TEMPLATE_2026-03-13_165338.md`
  - `docs/09_project_mgmt/FINAL_QA_PM_FREEZE_CHECKLIST_2026-03-13_165338.md`
- Functional result:
  - one tool now generates the final project-completion handoff markdown from the latest freeze packet
  - it auto-links the freeze packet, sprint tracker, PM tracker, launch runbook, backup/restore evidence, cutover smoke, soak evidence, and shared handoff path
  - it auto-loads the maintenance watchlist from `SPRINT_PLAN.md`
  - it derives the supported operating limit from the latest shared-soak evidence unless an explicit override is supplied
  - it fails closed by default when the freeze packet is still blocked
  - it can still write a clearly marked preview handoff when `--allow-blocked-preview` is used
- Generated preview artifact on the live blocked worktree:
  - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_2026-03-13_190511.md`
- Verification:
  - `python -m py_compile src\tools\project_completion_handoff.py tools\project_completion_handoff.py tests\test_project_completion_handoff_tool.py`
    - result: `passed`
  - `.venv\Scripts\python.exe -m pytest tests/test_project_completion_handoff_tool.py tests/test_final_qa_freeze_packet_tool.py -q`
    - result: `13 passed`
  - `python tools/project_completion_handoff.py --help`
    - result: `passed`
  - `python tools/project_completion_handoff.py --allow-blocked-preview`
    - result: wrote preview handoff and correctly surfaced the current blocked-freeze posture
- PM interpretation:
  - Sprint 14 now has automated freeze evidence plus automated completion-handoff generation
  - this still does not clear the environment-bound `13.6` blocker or the live cutover requirement
  - the generated handoff can now be previewed safely without pretending launch acceptance is complete
  - refreshed preview artifact after the `14.3a` reject fix:
    - `docs/09_project_mgmt/PROJECT_COMPLETION_HANDOFF_2026-03-14_140544.md`

### 14.1 Controlled Shared Cutover -- NEXT

- Execute the approved launch checklist against the workstation-hosted shared deployment.
- Record:
  - cutover timestamp
  - auth/mode posture
  - operator on-duty identity
  - active supported concurrency statement

### 14.2 Post-Cutover Smoke And Rollback Proof -- NEXT

- Run immediate post-cutover smoke checks across:
  - `/health`
  - `/status`
  - `/auth/context`
  - `/dashboard`
  - `/admin/data`
- Reconfirm the backup/restore path is still valid for rollback.
- If launch is not accepted, close this slice with an explicit rollback verdict instead of ambiguous partial-launch state.

### 14.3 Final QA Sweep And PM Freeze -- NEXT

- Run the final QA pass against the accepted launch or rollback state.
- Freeze:
  - sprint board
  - PM tracker
  - launch runbook
  - completion checkpoint

### 14.4 Project Completion Handoff -- NEXT

- Publish the final completion handoff for maintenance-only work.
- Completion target:
  - no active implementation sprint remains
  - outstanding items, if any, are maintenance watchlist items instead of delivery blockers

### Exit Criteria

- multi-user soak and performance baselines are recorded with known ceilings
- backup/restore and rollback procedures are documented and validated
- the launch packet is complete enough that shared deployment can be handed off as an operational system, not just a dev checkout
- the desktop GUI exposes the primary CLI/operator path directly enough that routine shared-use operations do not depend on PowerShell
- future GUI parity can be reviewed against an explicit capability catalog and saved report instead of ad hoc recollection

## Sprint 15 Detail -- Retrieval Quality and QA Hardening

### Focus

- Fix the remaining QA findings from the 2026-03-15 cross-repo audit
- Harden retrieval accuracy (source path scoring, stopword handling)
- Close cosmetic and test coverage gaps before BEAST day-one re-index

### Planned Slice Order

1. `15.1 -- QA Critical/High Fixes` -- `DONE`
2. `15.2 -- Source Path Score Calibration` -- `DONE`
3. `15.3 -- PPTX Multi-Paragraph Fix` -- `DONE`
4. `15.4 -- demo_day_sim Mode Isolation` -- `DONE`
5. `15.5 -- GUI Export Test Coverage` -- `DONE`
6. `15.6 -- sys.path Cleanup Guard` -- `LATER`

### 15.1 QA Critical/High Fixes -- DONE (2026-03-15)

- Fixed 5 findings from the cross-repo QA audit:
  - `RERANKER_AVAILABLE` hardcoded True -> dynamic `is_reranker_available(config)` with 30s TTL
  - AN military designator dropped by stopword filter -> uppercase words bypass stopwords
  - Export methods crash on locked file -> try/except with messagebox.showerror()
  - Dead `uc_key` variable in `record_result()` -> removed
  - Dead `reranker_model_name` defaulting to retired cross-encoder -> removed
- Files: retriever.py, routes.py, query_engine.py, query_panel.py
- Regression: 792 passed, 8 skipped, 0 failed

### 15.2 Source Path Score Calibration -- DONE (Sprint 16)

- Finding #10: source_path_search scores up to 0.7, inflating path-only matches
- Fixed in Sprint 16: `min(0.5, 0.05 + 0.45 * coverage)` in vector_store.py:758
- Path matches capped at 0.5, scaled proportionally by coverage ratio

### 15.3 PPTX Multi-Paragraph Fix -- DONE (Sprint 16)

- Finding #7: `_add_text_box` puts all text in one paragraph
- Fixed in Sprint 16: `_add_text_box` splits on `\n`, creates separate paragraphs per line
- Test: `test_multiline_answer_preserves_paragraphs` in test_report_generator.py

### 15.4 demo_day_sim Mode Isolation -- DONE (Sprint 16)

- Finding #12: `config.mode = "offline"` / `"online"` without save/restore
- Fixed in Sprint 16: `saved_mode` + `finally` block in both `check_offline_query` and `check_online_query`

### 15.5 GUI Export Test Coverage -- DONE (2026-03-15)

- Finding #11: No automated tests for Excel/PPTX export buttons
- Added `tests/test_gui_export_buttons.py` (13 tests, all pass)
- Covers: button state lifecycle, record_result, Excel/PPTX generation via buttons,
  empty-history info dialog, cancel-dialog no-op, write-failure error dialog, slide count

### 15.6 sys.path Cleanup Guard -- LATER

- Finding #8: 13 files do `sys.path.insert(0, ...)` without cleanup
- All are entry-point scripts (launch_gui, server, tools) -- mutation is expected for top-level scripts
- Low priority: not a bug, just a hygiene note

### Exit Criteria

- All QA HIGH/CRITICAL findings closed with regression proof
- Source path search scores recalibrated
- PPTX export renders multi-paragraph answers correctly
- demo_day_sim cannot leave config in a dirty state
- At least basic export test coverage exists

## Sprint 16 Detail -- Reranker Revival and Retrieval Improvements

### Focus

- Replace the retired sentence-transformers cross-encoder with an Ollama-based reranker
- Improve corrective retrieval reformulation quality
- Add query decomposition to streaming queries

### Deliverables (All QA-Verified 2026-03-15)

1. `src/core/ollama_reranker.py` (164 lines) -- OllamaReranker class + load_ollama_reranker factory
   - LLM-based relevance scoring via /api/generate
   - Thread-pooled parallel scoring (4 workers default)
   - Centered -5 to +5 output (sigmoid-compatible with existing retriever)
   - Network gate integration, 800-char doc truncation, graceful degradation
2. Retriever wiring (retriever.py)
   - `_load_reranker()` now creates OllamaReranker from config
   - `refresh_settings()` lazy-loads on first enable, falls back if unavailable
   - `is_reranker_available(config)` dynamic probe with 30s TTL (replaces hardcoded flag)
3. Corrective retrieval reformulation (query_engine.py)
   - `_STOP_WORDS` frozenset (80+ common English stopwords)
   - Uppercase words bypass stopwords (preserves AN, TPS military designators)
   - Terms sorted by length (most specific first) for FTS5 weighting
4. Query decomposition in streaming (query_engine.py)
   - `query_stream()` now calls `_decompose_query()` for multi-part queries
   - `_merge_search_results` and `_multi_query_retrieve` extracted to module level (class size reduction)
5. Source path scoring (vector_store.py)
   - Coverage-based formula: `min(0.5, 0.05 + 0.45 * coverage)` -- capped below content matches
6. Report export (new files)
   - `src/tools/report_generator.py` -- Excel and PPTX report generation
   - GUI export buttons in QueryPanel (record_result, _on_export_excel, _on_export_pptx)
   - Multi-paragraph PPTX via _add_text_box newline splitting

### Tests Added

- `tests/test_ollama_reranker.py` (13 tests)
- `tests/test_report_generator.py` (15 tests)
- `tests/test_gui_export_buttons.py` (11 tests)
- `tests/test_query_engine.py` (+1 streaming decomposition test)

### Regression

- 847 passed, 6 skipped, 0 failed (2026-03-15)

### QA Evidence

- `docs/09_project_mgmt/QA_CHECKPOINT_2026-03-15_S15_HARDENING.md`
- `docs/09_project_mgmt/CHECKPOINT_2026-03-15_S16_RERANKER_REVIVAL.md`

## Sprint 17 Detail -- Live API Validation (GPT-4o via OpenRouter)

### Focus

- Leverage newly available GPT-4o API access to run live online tests
  that were previously blocked by missing credentials
- Close Sprint 5 online demo hardening blocker
- Validate cost tracking, token accounting, and latency against real API
- Generate live answer quality evidence for demo prep

### Planned Slice Order

1. `17.1 -- Live Demo Preflight` -- `NEXT`
2. `17.2 -- Online Query Engine E2E Test` -- `NEXT`
3. `17.3 -- Cost Tracker Live Validation` -- `NEXT`
4. `17.4 -- FastAPI /query Live Smoke` -- `NEXT`
5. `17.5 -- Generation Autotune Sweep` -- `LATER` (costs real tokens)

### 17.1 Live Demo Preflight -- DONE (2026-03-15, partial)

- Ran `tools/demo_day_sim.py --full --online`
- **15/16 checks passed** -- full pipeline validated end-to-end
- Passed: config, database (33,738 chunks), Ollama (7 models), rehearsal pack (10/10),
  query decomposition, CRAG config, backend load, 3 retrieval tests, live offline query
- **FAIL: online query** -- OpenRouter API key limit exceeded (403)
  - Not a code bug -- mode switching, network gate, credential resolution all work
  - Fix: top up OpenRouter key or switch to direct OpenAI API key
- Offline query: 172s on toaster (slow but functional on CPU-only Ollama)

### 17.2 Online Query Engine E2E Test -- DONE (2026-03-15, gated)

- `tests/test_live_api_e2e.py` (5 tests, all skip without RUN_LIVE_API_TESTS=1)
- TestOnlineQueryE2E: real GPT-4o call, validates answer/tokens/cost/chunks/latency
- TestCostTrackerLive: validates cost event recorded with real token counts
- TestFastAPILiveSmoke: POST /query, GET /status in online mode
- Ready to light up the moment API key is funded

### 17.3 Cost Tracker Live Validation -- DONE (test written, gated)

- Included in test_live_api_e2e.py::TestCostTrackerLive
- Validates cost_usd > 0, tokens_in/out > 0, cost < $0.10 sanity cap

### 17.4 FastAPI /query Live Smoke -- DONE (test written, gated)

- Included in test_live_api_e2e.py::TestFastAPILiveSmoke
- POST /query with real question, verify real answer + token counts
- GET /status verifies online mode reported correctly

### 17.5 Generation Autotune Sweep -- LATER (BEAST + API key)

- `tools/generation_autotune_live.py` -- 8 param bundles x 20 questions
- ~160 API calls, nontrivial cost
- Only run after 17.1-17.4 confirm the pipeline works

### 17.8 CRAG Chunk Relevance Filter -- DONE (2026-03-15)

- Research: full CRAG decomposes retrieved docs, not just queries (arxiv 2401.15884)
- Implemented `_filter_low_relevance_chunks()` in query_engine.py (module-level)
- Filters chunks with zero query term overlap before context building (Step 1.7)
- Safety: skips filter when < 3 chunks, never drops all results
- 5 new tests in TestChunkRelevanceFilter (test_query_engine.py)
- Regression: pending (toaster resource-constrained)

### 17.9 Recall@50 Measurement Tool -- LATER (BEAST + eval set)

- Research: "recall must come before precision" -- verify recall@50 > 90%
  before investing more in reranker path
- Build a recall@N measurement script using the 400q golden eval set
- BEAST-dependent (needs full re-index + eval run)

### 17.6 Inline Python Extraction -- DONE (2026-03-15)

- Extracted 2 inline Python blocks from start_hybridrag.ps1 (lines 287-295, 430-440)
- New script: `scripts/_startup_checks.py` with `paths` and `mode` subcommands
- PS1 now calls `python scripts/_startup_checks.py paths` and `mode`
- Closes DPI audit P1 #4

### 17.7 Class Size Budget Enforcement -- DONE (2026-03-15)

- QueryEngine: extracted _attempt_corrective_retrieval + _reformulate_for_retry
  to module level. Class dropped from 531 -> 481 code lines (under 500).
- ConversationThreadStore: extracted _record_turn_impl, _rewrap_thread_rows,
  _rewrap_turn_rows to module level. Class dropped from 805 -> 512 code lines
  (under 550 tolerance).
- Updated 4 tests in test_query_engine.py to call module-level functions directly.
- IndexPanel: extracted _build_widgets (162 lines) to index_panel_build.py.
  Class dropped from 506 -> 375 code lines (under 500).

### 17.10 Config Model Default Regression Fix -- DONE (2026-03-15, hotfix)

- **Root cause**: commit 0863e61 changed the committed workstation defaults in
  three places: `config/config.yaml` offline model flipped from
  `phi4:14b-q4_K_M` to `phi4-mini`, `config/user_modes.yaml` started forcing
  `active_profile: laptop_safe`, and `src/core/mode_config.py` kept
  `phi4-mini` as the fallback runtime default
- **Symptom**: workstation startup shows "Backend Health: Warning -- Ollama generate
  probe failed (model 'phi4-mini'); server error 500" because phi4-mini is not
  installed on workstation (laptop-only fallback model)
- **Fix**: restored `config/config.yaml` line 11 to `model: phi4:14b-q4_K_M`
- **Secondary fix**: `src/core/config.py` OllamaConfig dataclass default also
  restored from `phi4-mini` to `phi4:14b-q4_K_M`, `config/user_modes.yaml`
  no longer commits a machine-specific active profile, and
  `src/core/mode_config.py` now matches the workstation default
- **Verification**: `user_modes.yaml` laptop_safe profile still keeps phi4-mini
  when selected intentionally, but the committed repo no longer forces it by
  default on workstation startup.

### Exit Criteria

- demo_day_sim --full --online returns GO verdict (BLOCKED: API key limit)
- At least one real E2E test proves query -> retrieval -> API -> answer -> cost pipeline (tests written, gated)
- Cost tracking verified against real API response (test written, gated)
- FastAPI /query endpoint works with real API backend (test written, gated)
- All classes under 500 code lines or within 10% tolerance (DONE)

## Sprint 18 Detail -- DPI Audit Hardening + Test Modernization

### Focus

- Close remaining DPI audit findings not addressed in Sprint 15-17
- Research-backed test modernization from 2026-03-15 deep-packet QA assessment
- Three new test tools (hypothesis, time-machine, mutmut) address the gap between
  high line coverage and actual defect detection
- All three are pure-Python / lightweight-C and run on the toaster with zero network

### Planned Slice Order

1. `18.1 -- contextlib.suppress teardown cleanup` -- `DONE`
2. `18.2 -- Reranker NDAA compliance note` -- `DONE`
3. `18.3 -- Test Tooling Bootstrap` -- `DONE` (hypothesis 6.151.9, time-machine 3.2.0 installed; mutmut deferred to BEAST)
4. `18.4 -- Property-Based Chunker Tests (Hypothesis)` -- `DONE` (7 tests pass in 6s)
5. `18.5 -- Hybrid Search RRF Validation` -- `DONE` (26 tests pass)
6. `18.6 -- Parser Fuzz Tests (Hypothesis)` -- `DONE` (33 edge-case tests pass in 71s)
7. `18.7 -- Flaky Test Stabilization (time-machine)` -- `DONE` (test_query_cache 2s->0.6s, test_runtime_limiter deterministic)
8. `18.8 -- Stress Test Slow Tagging` -- `DONE`
9. `18.9 -- Mutation Testing Baseline (mutmut)` -- `BLOCKED` (mutmut requires WSL/Linux, not native Windows; deferred to BEAST)
10. `18.10 -- PS1 Line Ending Normalization` -- `DONE` (.gitattributes created with *.ps1 eol=crlf)
11. `18.11 -- DeepEval RAG Metrics` -- `LATER` (needs BEAST or API-backed judge LLM)
12. `18.12 -- RAGAS Synthetic Test Generation` -- `LATER` (BEAST batch job)

### 18.1 contextlib.suppress teardown cleanup

- DPI P1 #6 follow-up: cost_dashboard.py lines 529, 534 use bare except:pass during teardown
- Research finding: `contextlib.suppress(Exception)` is the Pythonic standard for intentional ignores
- Operational failures (budget read, indexer close) already fixed with logger.warning in Sprint 15 QA
- Teardown patterns (widget destroy, listener removal) get contextlib.suppress

### 18.2 Reranker NDAA compliance note -- DONE (2026-03-15)

- Research finding: ALL dedicated reranker models on Ollama are NDAA-banned:
  - Qwen3-Reranker (0.6B/4B/8B) -- Alibaba/China
  - BGE-Reranker-v2-m3 -- BAAI/China
  - Jina Reranker v3 -- built on Qwen3 foundation
- Current LLM-prompting approach (phi4-mini with relevance prompt) is the ONLY compliant path
- Performance: ~2s/pair CPU, ~0.2s/pair GPU (acceptable for 10-20 candidate pools)
- Future: monitor for Mistral/Google/Microsoft dedicated reranker releases on Ollama

### 18.3 Test Tooling Bootstrap

- Create `requirements_dev.txt` with hypothesis, time-machine, mutmut
- These are dev/test-only deps, not production runtime
- Research sources:
  - hypothesis: property-based testing, auto-generates edge cases (https://hypothesis.readthedocs.io)
  - time-machine: 300x faster than freezegun, C-level time patching (https://github.com/adamchainz/time-machine)
  - mutmut: mutation testing, finds tests that pass but don't verify behavior (https://github.com/boxed/mutmut)

### 18.4 Property-Based Chunker Tests (Hypothesis)

- Invariant tests for Chunker.chunk_text():
  - Non-empty stripped input always produces at least one chunk
  - No chunk body exceeds chunk_size (excluding [SECTION] heading prepend)
  - Chunks are always stripped (no leading/trailing whitespace)
  - Chunker terminates for all inputs (no infinite loops)
  - With overlap=0, reconstructed text covers all original content
- Research: Hypothesis generates thousands of inputs including empty strings,
  unicode boundaries, extremely long text, null bytes, mixed encodings

### 18.5 Hybrid Search RRF Validation

- Test RRF formula: score = 1/(k+rank+1), k=60 default
- Verify FTS5 + vector fusion: chunks in both lists get added RRF scores
- Verify display blend: 0.4*vec_score + 0.6*rrf_normalized
- Verify final score capped at 1.0
- Verify FTS5 normalization: raw/(raw+1) maps BM25 to [0,1]
- Verify path search capped at 0.5: min(0.5, 0.05 + 0.45*coverage)
- Verify embedding dimension mismatch raises ValueError (768 expected vs 384 input)

### 18.6 Parser Fuzz Tests (Hypothesis)

- DPI P1 #5: 37 parsers, zero dedicated unit tests
- Hypothesis binary strategies: feed random bytes, empty files, truncated content
- Verify: no crashes, no hangs, graceful error or empty string return
- Priority parsers: PDF, DOCX, plain text, Excel, fallback/placeholder

### 18.7 Flaky Test Stabilization (time-machine)

- Replace time.sleep() in test_query_cache.py with time-machine travel()
- Replace time.sleep() in test_runtime_limiter.py
- Research: time-machine patches at C level, controls time.time(), datetime.now(),
  time.monotonic(), and time.sleep() with single API
- Verify deterministic pass on 10 consecutive runs

### 18.8 Stress Test Slow Tagging

- DPI P2 #9: sleep-dependent tests flake on slow CI
- Tag with @pytest.mark.slow so CI can skip them
- Files: test_bulk_transfer_stress.py, test_query_cache.py, test_runtime_limiter.py
- Add pytest.ini marker registration

### 18.9 Mutation Testing Baseline (mutmut)

- Run mutmut on src/core/chunker.py, src/core/embedder.py, src/core/retriever.py
- Research: 2024 IEEE study found 40% of high-coverage codebases still have undetected logical errors
- Triage surviving mutants as test gaps
- Write targeted kill tests for high-value survivors
- Document baseline mutation score for core modules

### 18.10 PS1 Line Ending Normalization

- Add `*.ps1 eol=crlf` to .gitattributes
- 6 files with mixed CRLF/LF: api_mode_commands.ps1, create_desktop_shortcut.ps1,
  launch_gui.ps1, setup_home.ps1, usb_install_offline.ps1, verify_educational_sync.ps1

### 18.11 DeepEval RAG Metrics -- LATER

- Install deepeval, configure with local Ollama judge (phi4:14b)
- pytest-native faithfulness + answer relevancy + contextual precision tests
- Research: DeepEval is pytest-compatible, 14+ RAG-specific metrics, CI/CD ready
- Validate phi4:14b can handle judge prompts before committing to this approach
- Requires BEAST (48GB VRAM) or funded API key for reliable judge LLM

### 18.12 RAGAS Synthetic Test Generation -- LATER

- Batch generate Q&A triplets from 39,602 chunks using RAGAS TestsetGenerator
- Research: manual test curation consumes up to 90% of RAG eval time (Red Hat 2026)
- Evolution-based paradigms: simple -> multi-hop -> reasoning query types
- Expand golden set from 400q to 2000+ with auto-generated ground truth contexts
- One-time BEAST job, check in generated dataset as static test fixture

### Exit Criteria

- hypothesis, time-machine, mutmut installable from requirements_dev.txt
- At least 5 Hypothesis property tests pass for Chunker
- Hybrid search RRF scoring validated with boundary tests
- Flaky sleep-based tests migrated to time-machine or tagged slow
- Mutation testing baseline documented for core modules
- No regressions in existing 847-test suite

## Sprint 19 Detail -- Deep QA Hardening

### Focus

- Fix all critical and high findings from the 2026-03-15 deep packet-level QA audit
- Audit covered 226 source files across core engine, API, security, GUI, parsers, scripts
- 4 critical bugs, 5 high issues, 14 medium issues identified
- Prioritized by blast radius: crash/security fixes first, then resource leaks,
  then maintainability

### Planned Slice Order

1. `19.1 -- Embedder numpy import crash` -- `NEXT`
2. `19.2 -- Reranker cache thread safety` -- `NEXT`
3. `19.3 -- Vector store memmap handle leak` -- `NEXT`
4. `19.4 -- Source path search SQL hardening` -- `NEXT`
5. `19.5 -- Rate limiter memory leak and proxy awareness` -- `NEXT`
6. `19.6 -- GUI class size splits (api_admin_tab, tuning_tab_runtime, data_panel)` -- `NEXT`
7. `19.7 -- Silent exception logging sweep` -- `NEXT`
8. `19.8 -- SQLite context manager cleanup` -- `NEXT`
9. `19.9 -- Embedding model mismatch guard` -- `NEXT`
10. `19.10 -- Parser robustness (TAR leak, XLSX cap, mbox warning)` -- `NEXT`
11. `19.11 -- Response sanitizer fallback` -- `NEXT`
12. `19.12 -- Auth audit event persistence` -- `NEXT`

### 19.1 Embedder numpy import crash

- **Severity**: CRITICAL -- runtime NameError
- **File**: `src/core/embedder.py:220`
- **Issue**: `embed_batch()` references `np.ndarray` and `np.zeros()` but numpy is
  only imported inside `__init__` and `_detect_dimension()`, not at module scope
- **Impact**: any call to `embed_batch()` crashes with NameError
- **Fix**: add `import numpy as np` at module top (around line 48)

### 19.2 Reranker cache thread safety

- **Severity**: CRITICAL -- race condition
- **File**: `src/core/retriever.py:88-112`
- **Issue**: `_reranker_available_cache` and `_reranker_available_ts` are global
  variables written by multiple threads without a lock (TOCTOU race)
- **Impact**: concurrent GUI queries can cause stale cache reads, duplicate Ollama
  health checks, and cache incoherence
- **Fix**: add module-level `threading.Lock()`, wrap cache read/write in `with` block

### 19.3 Vector store memmap handle leak

- **Severity**: CRITICAL -- resource leak (Windows-specific)
- **File**: `src/core/vector_store.py:221-230`
- **Issue**: `read_block()` creates numpy memmap, does `del mm` but never closes the
  underlying mmap handle. On Windows, memmap holds exclusive file locks.
- **Impact**: after ~1000 searches, OS file handle exhaustion causes crash
- **Fix**: explicit `mm._mmap.close()` in finally block, or use raw mmap context manager

### 19.4 Source path search SQL hardening

- **Severity**: CRITICAL -- SQL injection vector
- **File**: `src/core/vector_store.py:707-767`
- **Issue**: `source_path_search` builds WHERE clause via f-string from tokenized user
  input. Although LIKE values are parameterized, the clause structure itself is
  dynamically constructed.
- **Impact**: crafted queries with SQL metacharacters could bypass LIKE parameterization
- **Fix**: verify end-to-end parameterization, add explicit input sanitization for
  FTS5 special characters, add test with SQL injection payloads

### 19.5 Rate limiter memory leak and proxy awareness

- **Severity**: HIGH -- memory leak + DoS in shared deployment
- **File**: `src/api/routes.py:160-195`
- **Issue**: `_RATE_STATE` dict keyed on `(host, scope)` never evicts old entries.
  Behind reverse proxy, all users share one rate bucket (proxy IP), allowing one user
  to exhaust limits for everyone.
- **Impact**: unbounded memory growth over long server lifetime; unfair rate limiting
  in proxy environments
- **Fix**: add LRU eviction or periodic cleanup of stale buckets; optionally support
  X-Forwarded-For when trusted proxy is configured; document as best-effort local limit

### 19.6 GUI class size splits

- **Severity**: HIGH -- maintainability, violates 500-line class constraint
- **Files**:
  - `src/gui/panels/api_admin_tab.py` -- 2,041 code lines (4x limit)
  - `src/gui/panels/tuning_tab_runtime.py` -- 1,556 code lines (3x limit)
  - `src/gui/panels/data_panel.py` -- 1,067 code lines (2x limit)
- **Fix**: split api_admin_tab into `data_paths_panel.py`, `model_selection_panel.py`,
  `api_admin_tab.py` (coordinator). Extract tuning_tab_runtime into
  `_tuning_hardware.py`, `_tuning_ui_builder.py`, `_tuning_logic.py`. Extract
  data_panel into `_drive_browser.py`, `_transfer_progress.py`, `_transfer_controls.py`.
- **Pattern**: follow existing query_panel + query_panel_*_runtime.py extraction pattern

### 19.7 Silent exception logging sweep

- **Severity**: MEDIUM -- observability gap
- **Files**:
  - `src/core/vector_store.py:678-689` -- fts_search bare `except Exception: return []`
  - `src/core/retriever.py:768` -- _augment_with_adjacent_chunks bare except
  - `src/api/auth_audit.py:114-130` -- auth events silently dropped
  - `scripts/_model_meta.py:481` -- `except Exception: return 7`
  - `src/parsers/archive_parser.py:207-208` -- bare except increments counter
- **Fix**: replace bare `except Exception` with specific exception types + `logger.warning()`
  in all cases. Never silently drop auth/security events.

### 19.8 SQLite context manager cleanup

- **Severity**: MEDIUM -- resource leak under exceptions
- **Files**:
  - `src/core/cost_tracker.py:273-317` -- `get_cumulative_summary()` opens connection
    without context manager, leak if execute() throws
  - `src/api/routes.py:406-418` -- index run retrieval missing `con.close()` in
    success path
- **Fix**: wrap all SQLite connections in `with sqlite3.connect(...) as conn:` or
  use try/finally with explicit close

### 19.9 Embedding model mismatch guard

- **Severity**: MEDIUM -- silent wrong results
- **File**: `src/core/vector_store.py:301-304`
- **Issue**: when stored embedding model differs from configured model, code logs
  WARNING but continues. Dot-product on mismatched vector spaces returns garbage.
- **Fix**: raise `ValueError` with message to re-index, or at minimum surface the
  warning in GUI status bar. User must explicitly acknowledge mismatch before proceeding.

### 19.10 Parser robustness

- **Severity**: MEDIUM -- resource leak + silent data loss
- **Files**:
  - `src/parsers/archive_parser.py:201-205` -- TAR `extractfile()` stream opened but
    not closed when `src is None`
  - `src/parsers/office_xlsx_parser.py:82-114` -- no row cap, 1GB spreadsheet loads
    all values into memory (OOM on toaster)
  - `src/parsers/mbox_parser.py:45-70` -- silent truncation at 200 messages with no
    log WARNING. Users lose 99.6% of a 50K-message archive with no indication.
- **Fix**: add `if src:` guard for TAR streams; add 100K row cap for XLSX with
  logger.warning on truncation; log WARNING before mbox truncation and raise cap
  to 1000 or make configurable

### 19.11 Response sanitizer fallback

- **Severity**: LOW -- injection pass-through edge case
- **File**: `src/security/response_sanitizer.py:77-78`
- **Issue**: if sanitization removes ALL lines from a response, fallback returns
  the original (potentially injected) text
- **Fix**: return `"[Response could not be verified]"` instead of original text when
  sanitization produces empty output

### 19.12 Auth audit event persistence

- **Severity**: MEDIUM -- security audit gap
- **File**: `src/api/auth_audit.py:114-130`
- **Issue**: `record_auth_event()` silently returns on any import/state error,
  dropping security events from the audit trail
- **Fix**: log failures at WARNING level; optionally write to fallback file-based
  audit log when in-memory tracker is unavailable

### Exit Criteria

- All 4 critical findings (19.1-19.4) fixed and verified with targeted tests
- Rate limiter includes eviction and proxy documentation (19.5)
- All 3 oversized GUI files split to under 500 code lines (19.6)
- Zero bare `except Exception: pass/return` patterns in core + API + parsers (19.7)
- All SQLite connections use context managers or try/finally (19.8)
- Embedding model mismatch raises or surfaces warning (19.9)
- Parser truncation/caps are logged (19.10)
- Response sanitizer never returns unsanitized content (19.11)
- Auth events never silently dropped (19.12)
- Regression: 871+ tests pass, 0 fail

## Watchlist

- verify online/offline data paths stay isolated when switching
- verify offline settings never contaminate online mode
- verify localhost Ollama normalization is resilient to malformed localhost variants
- verify boot paths and GUI/API entry points apply the same mode/query-policy semantics
- centralize source-quality scoring and serving-bias constants if retrieval tuning continues; they currently live in both `src/core/source_quality.py` and `src/core/retriever.py`
- keep the bulk-transfer inline-hash compatibility fallback as low-priority maintenance only; it can still trigger a second source read when old monkeypatched tests return an empty digest
- keep `tools/gui_cli_parity_model.py` aligned with the real operator-facing CLI surface as new scripts or controls land
- keep `src/gui/testing/gui_cli_parity_probes.py` aligned with the real GUI runtime surface as parity items become executable
- track the non-fatal cross-suite Tk teardown noise seen only after the green combined `.venv` full-suite gate
- keep class sizes under 500 LOC
- keep new work modular and portable
- prefer redesigns over layering more compatibility shims

## Notes

- Historical handoff notes remain in `docs/HANDOVER_AND_SPRINT_PLAN_FREEZE_SAFE.md`.
- This file is the active sprint tracker going forward.
- Human-facing documentation backlog is tracked separately in `docs/09_project_mgmt/DOCUMENTATION_SPRINT_ROADMAP_2026-03-12.md` so the software sprint board stays focused on implementation and QA.
- Combined repo-wide QA should be read from `.venv\Scripts\python.exe -m pytest tests/`; the ambient system interpreter is currently missing `fastapi` and cannot serve as the authoritative full-suite gate.
