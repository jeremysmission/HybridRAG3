# HybridRAG3 Software History and Scalability Plan

Date: 2026-03-02
Scope: HybridRAG3 and HybridRAG3_Educational (last 7 days + baseline)

## 1. Objective
This document records:
- the original software stack and operating model
- major architecture and implementation changes over time
- why each major change was made
- tradeoffs accepted for each change
- current state and known gaps
- scalability options and a phased plan
- a chronological ledger of commits from the last 7 days

## 2. Original Stack (Baseline)
The initial operating baseline (before the late-February hardening wave) was:
- Local-first RAG pipeline with parser registry, chunker, embedder, vector store, retriever, query engine.
- Offline mode as default, online mode as optional via OpenAI-compatible endpoints.
- SQLite + FTS5 for metadata and keyword search.
- Embeddings and LLM generation primarily via local model serving (later standardized on Ollama-served models).
- Windows-first deployment with PowerShell/BAT launchers and machine-local paths.

Original design intent:
- Keep data local by default.
- Provide enterprise-usable behavior on managed Windows machines.
- Preserve observability and reproducibility through scripts, diagnostics, and tests.

## 3. Major Changes, Why, and Tradeoffs

### 3.1 Embedding/Model Stack Standardization
What changed:
- Consolidated around Ollama-served local stack, including `nomic-embed-text` for embeddings.
- Canonicalized model names and routing behavior across GUI/router/status paths.

Why chosen:
- Removed dependency drift and model-name mismatch issues.
- Reduced runtime ambiguity and support burden.

Tradeoffs:
- Requires reliable local Ollama service availability and model preloading.
- Increased dependence on installer/model transfer discipline for air-gapped deployments.

### 3.2 Parser Coverage and Drift Hardening
What changed:
- Expanded parser allowlist and parser-related dependencies.
- Added guard tests to catch allowlist/registry divergence.
- Hardened indexer fallback behavior to reduce silent skips.

Why chosen:
- Reliability issue surfaced where parser support and indexer gating drifted independently.
- Silent skip behavior undermined trust and completeness.

Tradeoffs:
- Wider parser/dependency surface increases setup complexity.
- More validation and tests add maintenance overhead but prevent silent regressions.

### 3.3 Setup/Install Script Hardening (Work + Home)
What changed:
- Recovery loops, proxy handling, Group Policy bypass patterns, BOM safety fixes, and step-by-step diagnostics in setup scripts.
- Better drill-down output and explicit remediation paths.

Why chosen:
- Managed Windows environments showed non-deterministic failures (proxy/cert/policy quirks).
- Setup reliability was a top blocker for adoption.

Tradeoffs:
- Scripts are longer and more procedural.
- Additional complexity is intentional for robustness in constrained enterprise environments.

### 3.4 USB/Offline Bundle Path
What changed:
- Added offline bundle builder + offline installer scripts.
- Added wheelhouse-based install path and model/cache transfer path.

Why chosen:
- Required for no-internet or restricted-network environments.

Tradeoffs:
- Bundle composition and media logistics become operational responsibility.
- Full model stack size exceeds single-disc media constraints.

### 3.5 GUI/UX Stabilization and Controls
What changed:
- Added/expanded data transfer controls, status clarity, model visibility, mode signaling, and admin tuning surfaces.
- Added independent reasoning/grounding dials and profile playbooks.

Why chosen:
- Demo and operator workflows needed deterministic controls and clearer state presentation.

Tradeoffs:
- More UI controls increase cognitive load.
- Requires stronger defaults and reference guidance to keep non-expert operation safe.

### 3.6 Transfer and Indexing Resilience
What changed:
- Transfer stop/start hardening, telemetry, ETA controls, and freeze-safe handover updates.
- Incremental reliability improvements around indexing/transfer orchestration.

Why chosen:
- Large data movement and long-running operations exposed race/stop/recovery gaps.

Tradeoffs:
- Additional state tracking and code paths increase complexity.
- Complexity is justified by operational durability.

## 4. Current State (Where We Are)
As of 2026-03-02:
- Parser and allowlist reliability significantly improved vs prior silent-skip behavior.
- Setup/install path is much more robust for managed Windows environments.
- Offline deployment path exists and is functional, but media strategy must be explicit (single-disc assumptions are risky).
- GUI/operator control surface is broader and more capable, with improved telemetry and mode clarity.

Current risk focus:
- Ongoing drift between private and educational mirrors if sync boundaries are unclear.
- Offline media operational process (build/verify/stage/install) must be documented and consistently executed.
- Large model footprint requires deliberate packaging strategy (minimal vs full model set).

## 5. Scalability Options

### Option A: Keep SQLite+Memmap and Optimize (Near-term)
- Best for small-to-mid scale and low operational complexity.
- Actions:
  - tighten incremental indexing behavior
  - prioritize skip-reason observability
  - enforce config/registry sync guards
- Tradeoff: eventual limits at higher chunk counts/concurrency.

### Option B: Introduce ANN Vector Backend (Mid-term)
- Add FAISS/HNSW class backend for higher-scale retrieval latency control.
- Keep SQLite metadata/FTS where valuable.
- Tradeoff: added binary/runtime complexity and packaging burden.

### Option C: Service Decomposition (Mid/Long-term)
- Separate indexer/query/API/GUI concerns into independently deployable services.
- Tradeoff: much higher deployment/ops complexity.

### Option D: Tiered Model Strategy by Hardware Profile (Near-term)
- Enforce profile-based model packs (minimal, standard, full) to manage footprint.
- Tradeoff: more profile documentation and support matrix overhead.

## 6. Recommended Phased Plan

### Phase 1 (Immediate, 1-2 weeks)
- Lock parser drift prevention in CI and enforce on PR/push pipeline.
- Finalize offline media SOP: official-source verification, hash/signature logs, staging script usage.
- Standardize “minimal offline pack” as default deployment target.

### Phase 2 (Short-term, 2-6 weeks)
- Add structured skip-reason analytics and daily summary reporting.
- Add parser/OCR health preflight checks with actionable remediation.
- Validate large corpus runbook (650 GB goal) with measured checkpoints.

### Phase 3 (Mid-term, 1-3 months)
- Evaluate ANN backend prototype for retrieval at larger corpus scale.
- Add concurrency/load profiles and production tuning matrix.
- Define upgrade gate criteria (latency, completeness, failure-rate thresholds).

## 7. Deployment Capacity Notes (Offline Media)
Practical media assumptions:
- DVD single-layer (DVD-5): 4.7 GB decimal (~4.38 GiB), plan payload ~4.3 GiB.
- DVD dual-layer (DVD-9): 8.5 GB decimal (~7.95 GiB), still insufficient for full local model stack.

Operational implication:
- Use pre-staged multi-disc workflow for larger bundles.
- Treat model packs as tiered artifacts (minimal vs full) to control operational complexity.

## 8. 7-Day Chronological Change Ledger
Format: `commit | date | subject`

### 8.1 HybridRAG3
- `cb40a04 | 2026-03-02 01:03:43 -0700 | Add test temp dirs to sync skip patterns`
- `5d177b0 | 2026-03-02 00:46:12 -0700 | Add dated parser guardrail postmortem notes to setup docs`
- `3f84ef7 | 2026-03-02 00:26:27 -0700 | Add CI guard tests and harden indexer registry fallback`
- `fb54cb5 | 2026-03-01 23:41:25 -0700 | Fix parser coverage gap: expand indexer allowlist, add 9 parser deps`
- `0b65342 | 2026-03-01 21:39:47 -0700 | Update docs/deps and fix DataPanel stop watchdog theme lookup`
- `a295f61 | 2026-03-01 21:13:53 -0700 | Fix query panel startup crash by importing FONT_SMALL`
- `fc76515 | 2026-03-01 20:51:34 -0700 | Add independent reasoning and grounding dials with profile playbooks`
- `4fa23e0 | 2026-03-01 20:28:12 -0700 | Add Apply ETA control and immediate estimate refresh`
- `99715dc | 2026-03-01 20:11:27 -0700 | Clarify downloader ETA field as estimated optional input`
- `dd76ee8 | 2026-03-01 20:11:12 -0700 | Improve downloader with streaming discovery and operator ETA estimate`
- `14eab30 | 2026-03-01 20:02:16 -0700 | Improve downloader resilience, grounding controls, and freeze-safe handover`
- `50345ec | 2026-03-01 19:59:46 -0700 | Add .tmp_* dirs to gitignore, clean test artifacts`
- `770024a | 2026-03-01 18:39:54 -0700 | Harden transfer stop/start flow and clarify indexing telemetry`
- `1a37529 | 2026-03-01 18:16:50 -0700 | Validate eval_runner --mode flag input`
- `2299cf1 | 2026-03-01 15:22:36 -0700 | Add live indexing telemetry (chunks/skips/errors/rate/ETA)`
- `7cdabc4 | 2026-03-01 15:11:37 -0700 | Make transfer copy loop stop-aware to prevent stop hang`
- `096e12b | 2026-03-01 15:06:00 -0700 | Always show transfer telemetry placeholders in GUI`
- `fac87b0 | 2026-03-01 15:04:01 -0700 | Add dev-only Clear Index button in Index panel`
- `701f9ec | 2026-03-01 14:41:49 -0700 | GUI dev controls, transfer auto-resume, and XLSX parsing improvements`
- `a13d7e4 | 2026-03-01 14:23:13 -0700 | Improve answer readability formatting in prompt rules`
- `6fb8d1d | 2026-03-01 14:21:10 -0700 | Add admin chunking controls with re-index warning`
- `485dad7 | 2026-03-01 14:06:21 -0700 | Hide admin connection test by default for demo safety`
- `73ef5e4 | 2026-03-01 13:55:16 -0700 | Fix online mode gate override and launcher defaults`
- `ac1cd4c | 2026-03-01 13:38:59 -0700 | Improve admin probe UX and status bar readability`
- `b2e0d1d | 2026-03-01 13:24:23 -0700 | Fix online gate/mode mismatch messaging and probe behavior`
- `1625544 | 2026-03-01 13:13:54 -0700 | Improve mode clarity and online gate behavior`
- `f7dd6bf | 2026-03-01 12:50:25 -0700 | Enforce sanitization on force-included educational files`
- `80d9475 | 2026-03-01 12:45:28 -0700 | Improve online mode resilience and GUI status clarity`
- `f1c1fc3 | 2026-03-01 11:55:18 -0700 | Fix online API GUI wiring, status model display, and resilient API fallback`
- `d4eebdc | 2026-03-01 01:44:48 -0700 | Add transfer-source default persistence and educational sync verifier`
- `d015171 | 2026-03-01 01:36:33 -0700 | Improve admin troubleshooting UX and path default toggles`
- `7202557 | 2026-03-01 01:15:51 -0700 | Two-stage API probe with HTTP status feedback`
- `c56b5c0 | 2026-03-01 01:04:45 -0700 | Structured query retrieval, persist toggles, deployment-aware API test`
- `20c2593 | 2026-03-01 00:05:34 -0700 | Fix setup guide link in docs README`
- `7316a05 | 2026-03-01 00:05:01 -0700 | Align theory/security/setup docs with current runtime and repo split`
- `a01d1b7 | 2026-02-28 23:54:25 -0700 | Normalize Ollama endpoint and model identity across router and GUI`
- `5c5b260 | 2026-02-28 23:24:34 -0700 | Fix mock-safe last_error lookup, trim grounded engine to 500 lines`
- `2f4add1 | 2026-02-28 23:19:50 -0700 | Surface concrete LLM stream/query errors in UI fallback`
- `76dded3 | 2026-02-28 21:14:42 -0700 | Remove SCIF references, clarify model info display`
- `be4652b | 2026-02-28 20:11:21 -0700 | Add 11 Codex-authored tests: online streaming + grounded guard paths`
- `c69cee6 | 2026-02-28 19:54:18 -0700 | Fix 2 critical query bugs + add collab audit docs`
- `1f40b73 | 2026-02-28 19:31:36 -0700 | Guard streaming path + refactor shared helpers under 500 LOC`
- `9f005c4 | 2026-02-28 19:04:53 -0700 | Decouple download and indexer source paths`
- `9deeff3 | 2026-02-28 18:55:47 -0700 | GUI: topmost launch, Apply button, never-blank answers, source wrapping`
- `a8e5fc6 | 2026-02-28 18:05:47 -0700 | Fix TimeoutError import, trim status_bar, revert config drift`
- `6269cec | 2026-02-28 17:25:53 -0700 | Fix 5 Codex round 2 findings + download button layout`
- `98ffdda | 2026-02-28 17:18:06 -0700 | Fix path sanitizer regex for YAML double-backslash, skip user_overrides.yaml`
- `e51b4ad | 2026-02-28 16:56:05 -0700 | Fix 13 bugs from Codex deep QA (security, stability, proxy, GUI)`
- `d6afbd9 | 2026-02-28 16:04:22 -0700 | Add passthrough marker system for sync sanitizer`
- `39563af | 2026-02-28 15:56:02 -0700 | Add FORCE_INCLUDE to sync script for waiver docs in 05_security/`
- `570754c | 2026-02-28 15:53:22 -0700 | Update waiver docs: openai 1.109.1, 410 tests, fix ITAR sanitizer bug`
- `b71c7b0 | 2026-02-28 15:43:23 -0700 | Skip wizard when setup_complete is True (trust prior config)`
- `017b2e3 | 2026-02-28 15:31:18 -0700 | Fix wizard blocking: auto-create dirs instead of wizard, fix withdrawn parent`
- `287e9f7 | 2026-02-28 15:27:00 -0700 | Remove wait_visibility() -- blocks forever on corporate Windows`
- `cc505d4 | 2026-02-28 15:18:32 -0700 | Add wait_visibility() guard before wait_window() on setup wizard`
- `494387e | 2026-02-28 15:16:33 -0700 | Force setup wizard to foreground on Windows (fixes invisible modal hang)`
- `60eb688 | 2026-02-28 15:09:09 -0700 | Fix embedder fallback: pass dimension from config, skip blocking Ollama probe`
- `99214bd | 2026-02-28 14:43:21 -0700 | Canonicalize model names: phi4:14b-q4_K_M everywhere, purge :latest`
- `13490fa | 2026-02-28 14:31:15 -0700 | Fix default model: phi4:14b-q4_K_M (not phi4-mini)`
- `b2fddd7 | 2026-02-28 14:29:42 -0700 | Fix YAML parse error: remove stray line, quote Windows paths`
- `f08d339 | 2026-02-28 14:04:47 -0700 | Add startup drill-down diagnostics: print() at every boot step`
- `fba6818 | 2026-02-27 19:08:09 -0700 | Fix corporate proxy 301: trust_env=False on all localhost httpx clients`
- `8506141 | 2026-02-27 18:11:46 -0700 | Add standalone data transfer tool (no GUI/Ollama dependency)`
- `5ae081f | 2026-02-27 18:09:17 -0700 | Skip embedder startup probe when dimension known from config`
- `aef278b | 2026-02-27 18:04:07 -0700 | Fix corporate proxy interception: proxy=None on all loopback httpx clients`
- `810d497 | 2026-02-27 17:57:37 -0700 | Consolidate start_gui.bat: self-contained one-click launcher`
- `d6f3fe7 | 2026-02-27 17:41:19 -0700 | Purge snowflake embedder, lock all profiles to nomic-embed-text`
- `fb1a30f | 2026-02-27 17:16:25 -0700 | Canonicalize Ollama model names: Admin and Query panels now match`
- `71b0f8d | 2026-02-27 17:07:03 -0700 | Add embedding_model to embeddings_meta.json manifest`
- `0e4a12c | 2026-02-27 16:55:13 -0700 | Fix launch import order, retire stale torch/HF refs, update GUI reference data`
- `c92d55f | 2026-02-27 16:24:33 -0700 | Fix banned word in TWO_REPO_STRATEGY.md: defense -> security-context, remove stray artifact`
- `24dcc2f | 2026-02-27 16:16:17 -0700 | Fix corporate proxy redirect interception on work machines`
- `54cccf7 | 2026-02-27 15:30:46 -0700 | QA round 4: audit alignment, pytest isolation, module headers, config comments`
- `de66b5c | 2026-02-27 14:57:54 -0700 | QA round 3: NetworkGate enforcement, thread safety, boot correctness`
- `34b316c | 2026-02-27 14:34:40 -0700 | Update docs to reflect current architecture: 768-dim, nomic-embed-text, phi4:14b default`
- `a638abf | 2026-02-27 14:25:03 -0700 | Sync: unblock hallucination_guard + guard deps for Educational repo`
- `db15ccc | 2026-02-27 14:18:55 -0700 | Docs: fix stale model refs, remove duplicate RevA doc`
- `6ef6db1 | 2026-02-27 14:16:12 -0700 | QA hardening: sanitize API errors, thread-safe VectorStore, scrollable cleanup`
- `e280510 | 2026-02-27 13:47:34 -0700 | QA audit fixes: config truth, thread safety, API hardening, GUI stability`
- `45eb873 | 2026-02-27 10:19:17 -0700 | Fix sync skip: data/ logs/ output/ dir-only matching`
- `c941c35 | 2026-02-27 10:11:54 -0700 | Make Index Panel stop button visible and prominent`
- `d6d04e5 | 2026-02-27 09:43:43 -0700 | Public testing interface for GUI panels + queue-backed safe_after`
- `71a0790 | 2026-02-27 08:42:27 -0700 | Refactor Indexer: extract _process_single_file, add pipeline smoke test`
- `f5c878f | 2026-02-27 07:54:46 -0700 | Add config overlay system: user_overrides.yaml protects shipped defaults`
- `dc81b43 | 2026-02-27 07:41:25 -0700 | Fix GUI demo-blockers: Chunker config, model download, index diagnostics`
- `8090929 | 2026-02-27 06:58:39 -0700 | Fix GUI: model selector, index panel enable, data panel nav`
- `69416b2 | 2026-02-27 05:12:22 -0700 | Complete autonomous GUI stabilization + regression framework`
- `429f923 | 2026-02-27 04:45:50 -0700 | Sync script: skip remaining artifacts, preserve .gitignore`
- `edd3422 | 2026-02-27 04:43:52 -0700 | Sync script: skip output, .pytest_cache, claude_diag, *.log`
- `470c008 | 2026-02-27 04:35:00 -0700 | Show active offline model in status; fix UI model label; add gitignore and untrack caches`
- `6ba074d | 2026-02-27 04:24:57 -0700 | Show active offline model in status bar; harden .gitignore`
- `7622ede | 2026-02-27 04:07:41 -0700 | Fix GUI nav/registry; dedupe Admin; make Index standalone; persist/apply offline model; add regression selftests`
- `5cdb9b1 | 2026-02-27 03:22:45 -0700 | Add enterprise GUI troubleshooter: headless behavioral engine + BAT launcher`
- `2a77a7b | 2026-02-27 00:50:36 -0700 | Make GUI launcher deterministic; add GUI/ollama/data selftests`
- `4801267 | 2026-02-26 23:56:20 -0700 | Add GUI core diagnostics + selftests (ollama + data pipeline)`
- `3176e02 | 2026-02-26 20:54:14 -0700 | Add new-Claude intro handover doc`
- `259c893 | 2026-02-26 20:53:43 -0700 | Demo stability: transactional mode switch, clean index cancel, safe shutdown, 768-dim default`
- `2eb68c2 | 2026-02-26 20:12:17 -0700 | Fix 6 runtime bugs found during demo-week validation`
- `359d2c1 | 2026-02-26 18:41:38 -0700 | Session credential cache + async mode switch for demo speed`
- `9fa1998 | 2026-02-26 18:09:45 -0700 | Add bootstrap architecture, GUI bug fixes, cleanup stale files`
- `83a00a9 | 2026-02-26 16:37:41 -0700 | Fix test_all.py failing on Educational repo (virtual_test files excluded from sync)`
- `651bee4 | 2026-02-26 08:01:49 -0700 | Default to desktop_power profile (64GB/12GB VRAM is new standard)`
- `afa3ebf | 2026-02-26 07:15:48 -0700 | Fix GUI loading loop, keyring error handling, model default consistency`
- `f022cc3 | 2026-02-26 06:20:39 -0700 | Add mcp_server.py to Educational skip list (private AI agent infra)`
- `7ce665a | 2026-02-26 06:08:45 -0700 | Fix desktop_power profile model, surface GUI init/mode-switch errors`
- `10865c5 | 2026-02-25 22:20:17 -0700 | Fix hardware specs: work=64GB/12GB GPU, home=128GB/48GB dual-3090`
- `db3914e | 2026-02-25 21:59:32 -0700 | Add upgrade roadmap, bump Technical TOO to RevC with bulk transfer section`
- `2145b86 | 2026-02-25 21:51:05 -0700 | Harden bulk transfer for production nightly sync, fix 22 QA bugs, set desktop_power defaults`
- `cf2ec09 | 2026-02-25 19:46:47 -0700 | Fix Python version reference: 3.12 not 3.11 in setup_home.ps1`
- `b729c0c | 2026-02-25 19:13:16 -0700 | Add Ollama help text to setup_home, PS analyzer tools doc, stress test doc`
- `0567997 | 2026-02-25 19:11:28 -0700 | Add production scale estimate doc with measured baseline and projections`
- `06b1b52 | 2026-02-25 18:58:10 -0700 | Show actual error on Ollama check failure, add drill-down to both scripts`
- `c80b521 | 2026-02-25 18:53:25 -0700 | Fix Ollama proxy bypass for PS 5.1, add connectivity drill-down`
- `8f7ca28 | 2026-02-25 18:34:19 -0700 | Split troubleshooting sections: work-only vs both environments`
- `6ebf056 | 2026-02-25 18:31:27 -0700 | Add manual install guide, remove sensitive verbiage from setup script`
- `febc0aa | 2026-02-25 18:15:03 -0700 | Fix 9 audit bugs in setup scripts, add BOM safety tests`
- `807023a | 2026-02-25 13:25:17 -0700 | Add 7 product documentation documents for management and technical audiences`
- `ef87c84 | 2026-02-25 13:23:58 -0700 | Fix 9 audit bugs in setup scripts, add BOM safety tests`
- `924f3b6 | 2026-02-25 13:14:56 -0700 | Fix BOM bug: PS 5.1 writes UTF-8 BOM that breaks Python consumers`
- `6460a0d | 2026-02-25 08:14:27 -0700 | Simplify: reduce retries to 3, remove wheel fallback`
- `7778359 | 2026-02-25 08:10:05 -0700 | Add proxy auto-detection from Windows registry, create .venv\pip.ini`
- `f393906 | 2026-02-25 08:00:30 -0700 | Remove sneakernet language from drill-down, point to software store`
- `38e5c57 | 2026-02-25 07:58:15 -0700 | Fix openai proxy failure: --no-deps, retries 5, wheel fallback`
- `ffc3c89 | 2026-02-25 07:50:03 -0700 | Add step recovery prompts, split Step 7 into 17 groups (7A-7R)`
- `9d3e7a3 | 2026-02-25 07:16:19 -0700 | Add setup scripts to Educational sync list`
- `db76d50 | 2026-02-25 07:11:53 -0700 | Remove sensitive approval language from setup_work.ps1, fix virtual tests`
- `5e20b19 | 2026-02-25 06:41:47 -0700 | Use flexible openai version range for work mirror compatibility`
- `ceb18c3 | 2026-02-25 06:40:39 -0700 | Fix work setup: separate openai install, add progress-bar flags`
- `b000c72 | 2026-02-25 02:51:04 -0700 | Bump openai 1.45.1->1.51.2, add waiver reference sheet, purge stale docs`
- `c9b54f4 | 2026-02-25 02:03:57 -0700 | Add auto-create data folders option to setup wizard Step 3`
- `043a741 | 2026-02-25 01:59:39 -0700 | Add real-time progress, go-back wizard, full diagnostics to setup scripts`
- `a1d712d | 2026-02-25 01:30:15 -0700 | Add setup automation, hardwire hallucination guard, USB installer prototype`
- `035644c | 2026-02-25 07:09:13 +0000 | Update all three Theory of Operation docs to RevB (2026-02-25)`
- `aacd40e | 2026-02-24 23:07:10 -0700 | Fix 10 pre-existing test failures (credential, snapshot, LRU cache)`
- `7e230b6 | 2026-02-24 23:06:15 -0700 | Add RAG trading AI research doc (Bond-marked private)`
- `b39e009 | 2026-02-24 22:43:19 -0700 | Add PII scrubber, migrate all-MiniLM refs to nomic-embed-text, archive stale docs`
- `fad037d | 2026-02-24 18:38:21 -0700 | Redesign BulkTransferV2 into three classes under 500-line limit`
- `2655bdc | 2026-02-24 18:25:36 -0700 | Add use case application doc, dual-env API layer, GUI refactors, and multi-session hardening`
- `36cad39 | 2026-02-24 08:19:31 -0700 | Add work laptop setup guide, waiver summary, SSL/cert docs, Python 3.12 updates`
- `37d1431 | 2026-02-23 20:43:08 -0700 | Add Data Transfer panel, mode persistence, offline field graying, dev inventory`
- `3b8cb9a | 2026-02-23 19:05:11 -0700 | Fix 3 crash paths and 1 hardcoded model name found by code audit`

### 8.2 HybridRAG3_Educational

- `09232c2 | 2026-03-02 00:10:18 -0700 | Update requirements, parser coverage, and waiver docs`
- `f1d06b4 | 2026-03-01 21:17:27 -0700 | Sync sanitized startup hotfix for query panel`
- `eaa78c4 | 2026-03-01 21:00:05 -0700 | Routine sync`
- `23068aa | 2026-03-01 20:31:13 -0700 | Sync sanitized updates including downloader UX`
- `85f61b0 | 2026-03-01 20:20:08 -0700 | Complete sanitized mirror sync`
- `2956cb8 | 2026-03-01 20:19:43 -0700 | Sync sanitized updates from private repo`
- `78fd915 | 2026-03-01 20:19:10 -0700 | Routine sync`
- `79925d2 | 2026-03-01 19:59:54 -0700 | Remove test artifacts, update gitignore`
- `34d7c87 | 2026-03-01 18:48:38 -0700 | Routine sync`
- `1d0832b | 2026-03-01 18:17:40 -0700 | Routine sync`
- `c5644d0 | 2026-03-01 15:16:10 -0700 | Routine sync`
- `af0ff29 | 2026-03-01 15:09:34 -0700 | Routine sync`
- `e1e45f6 | 2026-03-01 14:50:19 -0700 | Sync sanitized GUI dev controls, transfer resume, and parser updates`
- `5076ce7 | 2026-03-01 14:23:53 -0700 | Sync sanitized prompt readability improvements`
- `28ac21e | 2026-03-01 14:02:37 -0700 | Sync sanitized status and online mode updates`
- `5a1ccac | 2026-03-01 13:40:06 -0700 | Sync sanitized admin probe and status updates`
- `aafe2ad | 2026-03-01 13:25:01 -0700 | Sync sanitized gate mismatch fixes`
- `5650126 | 2026-03-01 13:15:32 -0700 | Sync sanitized status and online mode updates`
- `fcb4374 | 2026-03-01 12:51:19 -0700 | Sync sanitized app and GUI updates`
- `149fd6b | 2026-03-01 11:58:47 -0700 | Sync from private repo: online API GUI/status fixes`
- `45aab0d | 2026-03-01 01:48:40 -0700 | Sync from private repo: admin probes, path default persistence, troubleshooting`
- `f703054 | 2026-03-01 01:16:15 -0700 | Routine sync`
- `6c29eb6 | 2026-03-01 01:05:31 -0700 | Routine sync`
- `d46491f | 2026-03-01 00:37:07 -0700 | Routine sync`
- `b785b55 | 2026-02-28 23:25:25 -0700 | Routine sync`
- `ee1bed9 | 2026-02-28 21:15:29 -0700 | Sync: Update README use case examples, clarify model info display`
- `c2f815b | 2026-02-28 20:12:00 -0700 | Sync: Codex collab test files + streaming bug fixes`
- `a213323 | 2026-02-28 19:58:35 -0700 | Sync from private repo`
- `6797b32 | 2026-02-28 19:32:30 -0700 | Sync from private repo`
- `7922169 | 2026-02-28 19:05:25 -0700 | Sync from private repo`
- `910c9f3 | 2026-02-28 18:56:35 -0700 | Sync from private repo`
- `cbb6b73 | 2026-02-28 18:06:21 -0700 | Sync: fix TimeoutError import, trim status_bar, restore defaults`
- `a67a515 | 2026-02-28 17:26:43 -0700 | Sync from private repo: Codex round 2 security + stability fixes`
- `5d672f9 | 2026-02-28 16:57:10 -0700 | Sync: Fix 13 bugs from Codex deep QA pass`
- `8c7176d | 2026-02-28 16:05:11 -0700 | Sync from private repo: passthrough markers, model name cleanup, wizard fixes`
- `42e843a | 2026-02-28 15:56:11 -0700 | Sync: add waiver_reference_sheet.md and proxy notes to Educational`
- `16aefcf | 2026-02-28 15:53:52 -0700 | Sync: waiver docs v5c, fix milregulatoryy sanitizer bug`
- `681e71d | 2026-02-28 15:44:40 -0700 | Sync: skip wizard when setup_complete is True`
- `0390a76 | 2026-02-28 15:31:45 -0700 | Sync: auto-create dirs, fix withdrawn parent wizard hang`
- `af5b545 | 2026-02-28 15:27:26 -0700 | Sync: remove wait_visibility blocking call`
- `45417c6 | 2026-02-28 15:18:53 -0700 | Sync: add wait_visibility guard for wizard`
- `decb1df | 2026-02-28 15:16:58 -0700 | Sync: force setup wizard to foreground on Windows`
- `18d6099 | 2026-02-28 15:09:45 -0700 | Sync: fix embedder fallback dimension, skip blocking Ollama probe`
- `fb6daf2 | 2026-02-28 14:44:37 -0700 | Sync: canonicalize model names, purge :latest suffixes`
- `dd4fd95 | 2026-02-28 14:31:37 -0700 | Sync: default model phi4:14b-q4_K_M`
- `194cfde | 2026-02-28 14:30:16 -0700 | Sync: fix YAML parse error in default_config.yaml`
- `05c3046 | 2026-02-28 14:05:24 -0700 | Sync: startup drill-down diagnostics for hang troubleshooting`
- `0d0e640 | 2026-02-28 13:26:10 -0700 | Sync from private repo: trust_env=False corporate proxy fix`
- `e7dcb5f | 2026-02-27 18:12:08 -0700 | Sync from private repo`
- `f7e097e | 2026-02-27 18:09:45 -0700 | Sync from private repo`
- `1d3daa4 | 2026-02-27 18:04:44 -0700 | Sync from private repo`
- `9bc8727 | 2026-02-27 17:58:04 -0700 | Sync from private repo`
- `198e276 | 2026-02-27 17:41:51 -0700 | Sync from private repo`
- `0f8d036 | 2026-02-27 17:16:56 -0700 | Sync from private repo`
- `244b1c8 | 2026-02-27 17:07:31 -0700 | Sync: add embedding_model to manifest`
- `cce0e0c | 2026-02-27 16:56:07 -0700 | Sync: fix launch import order, retire stale refs, update GUI reference data`
- `8be9e06 | 2026-02-27 16:18:02 -0700 | Sync: fix corporate proxy redirect interception (127.0.0.1, no-redirect)`
- `d049c7f | 2026-02-27 15:33:36 -0700 | Sync: audit alignment, pytest isolation, module headers, config comments`
- `59d5d43 | 2026-02-27 15:07:39 -0700 | Sync: QA round 3 -- NetworkGate enforcement, thread safety, boot correctness`
- `18d55cb | 2026-02-27 14:28:35 -0700 | Sync: add hallucination_guard + guard deps (sanitized)`
- `d4f8c73 | 2026-02-27 14:22:06 -0700 | Sync: QA hardening round 2 + doc corrections`
- `87f47e4 | 2026-02-27 13:50:48 -0700 | Sync from private repo: QA audit fixes across 9 files`
- `29e8908 | 2026-02-27 10:26:06 -0700 | Sync: Add data panel + stop button fix + model default`
- `8dd21ca | 2026-02-27 09:44:34 -0700 | Public testing interface for GUI panels + queue-backed safe_after`
- `64f26f6 | 2026-02-27 08:43:08 -0700 | Sync: Indexer refactor + pipeline smoke test + VectorStore auto-connect`
- `97be9bf | 2026-02-27 07:55:33 -0700 | Sync from private repo: config overlay system + UI improvements`
- `9fc8299 | 2026-02-27 07:42:14 -0700 | Sync from private repo: GUI demo-blocker fixes`
- `ae755e2 | 2026-02-27 05:13:36 -0700 | Sync: GUI stabilization + regression framework`
- `4c15dea | 2026-02-27 04:37:10 -0700 | Sync: status active model + repo hygiene`
- `8243452 | 2026-02-27 04:26:41 -0700 | Sync from private repo: model indicator, .gitignore, purge tracked junk`
- `beb6903 | 2026-02-27 04:08:39 -0700 | Sync: GUI nav/registry redesign, model persistence, Index standalone tab, regression selftests`
- `f228c67 | 2026-02-27 03:31:27 -0700 | Sync from private repo: deterministic launcher, GUI core, enterprise troubleshooter, selftests`
- `723d976 | 2026-02-27 03:05:10 -0700 | Edu: fix YAML boot blocker -- quote paths containing braces`
- `478df64 | 2026-02-27 03:01:17 -0700 | Edu: make Data panel optional via panel registry`
- `4efd9e1 | 2026-02-26 20:13:40 -0700 | Sync from HybridRAG3: Fix 6 runtime bugs, add demo validation tools`
- `428f124 | 2026-02-26 18:42:06 -0700 | Session credential cache + async mode switch for demo speed`
- `0384aea | 2026-02-26 18:10:23 -0700 | Sync from private repo: bootstrap architecture, GUI bug fixes, cleanup`
- `fd8df2a | 2026-02-26 17:21:37 -0700 | Sanitize repo: purge AI tool names, private workflow refs, and infra leaks`
- `ce165f7 | 2026-02-26 16:38:13 -0700 | Sync: fix test_all.py manifest for Educational repo`
- `8e396e9 | 2026-02-26 08:02:22 -0700 | Sync from private repo: desktop_power defaults, stress test update`
- `3f42692 | 2026-02-26 07:16:23 -0700 | Sync from private repo: fix loading loop, keyring errors, model defaults`
- `0d182b6 | 2026-02-26 06:20:50 -0700 | Remove mcp_server.py (private AI agent infra, not for educational repo)`
- `be137a2 | 2026-02-26 06:09:55 -0700 | Sync from private repo: fix desktop_power model, surface GUI errors`
- `fbba286 | 2026-02-25 22:20:42 -0700 | Sync from private repo: fix hardware specs (work=12GB GPU, home=48GB dual-3090)`
- `008ad48 | 2026-02-25 21:59:57 -0700 | Sync from private repo: upgrade roadmap, Technical TOO RevC, executive updates`
- `1a8991d | 2026-02-25 21:51:38 -0700 | Sync from private repo: bulk transfer hardening, 22 QA fixes, desktop_power defaults`
- `1c29744 | 2026-02-25 19:47:10 -0700 | Sync: fix Python 3.12 reference in setup_home.ps1`
- `fec208e | 2026-02-25 19:13:51 -0700 | Sync: fix banned word in PS analyzer tools doc`
- `f07bbad | 2026-02-25 19:11:46 -0700 | Sync: production scale estimate doc`
- `42e7236 | 2026-02-25 18:58:34 -0700 | Sync: Ollama check error display and drill-down diagnostics`
- `060a0f6 | 2026-02-25 18:53:54 -0700 | Sync: fix Ollama proxy bypass, add connectivity drill-down`
- `456d6b0 | 2026-02-25 18:34:38 -0700 | Sync: split troubleshooting sections in manual install guide`
- `b289b60 | 2026-02-25 18:32:05 -0700 | Sync: add manual install guide, remove sensitive verbiage`
- `14036a5 | 2026-02-25 18:19:20 -0700 | Sync: recovery loops on all setup steps, PS 5.1 bug fixes, sync redesign`
- `8e58ec2 | 2026-02-25 13:24:48 -0700 | Sync: BOM bug fixes, audit hardening, BOM safety tests`
- `332e4ab | 2026-02-25 08:14:39 -0700 | Simplify: reduce retries to 3, remove wheel fallback`
- `3604d48 | 2026-02-25 08:10:20 -0700 | Add proxy auto-detection from Windows registry, create .venv\pip.ini`
- `e9057ab | 2026-02-25 08:00:43 -0700 | Remove sneakernet language from drill-down, point to software store`
- `2a306ed | 2026-02-25 07:58:39 -0700 | Fix openai proxy failure: --no-deps, retries 5, wheel fallback`
- `f348227 | 2026-02-25 07:50:52 -0700 | Add step recovery prompts, split Step 7 into 17 groups (7A-7R)`
- `5ccd90e | 2026-02-25 07:16:23 -0700 | Sync: updated setup scripts, removed sensitive approval language`
- `839d6d4 | 2026-02-25 06:56:02 -0700 | Sync: openai flexible range, progress bars, setup hardening`
- `b857444 | 2026-02-25 06:42:01 -0700 | Use flexible openai range for gov mirror`
- `d63fbde | 2026-02-25 06:40:56 -0700 | Fix work setup: separate openai, add progress bars`
- `4548962 | 2026-02-25 02:51:41 -0700 | Bump openai 1.45.1->1.51.2, add waiver reference sheet, update all docs`
- `59016d9 | 2026-02-25 02:04:13 -0700 | Add auto-create data folders option to setup wizard`
- `3b659a3 | 2026-02-25 02:01:47 -0700 | Update setup scripts: real-time progress, go-back wizard, full diagnostics`
- `3cdac81 | 2026-02-25 01:31:00 -0700 | Add setup automation, hardwire hallucination guard, GUI fixes`
- `23c12f8 | 2026-02-24 23:07:28 -0700 | Fix 10 test failures: credential reload, snapshot paths, LRU cache`
- `b6f73e8 | 2026-02-24 22:43:38 -0700 | Sync from HybridRAG3: PII scrubber, nomic-embed-text migration, doc cleanup`
- `5694656 | 2026-02-24 18:38:54 -0700 | Sync: BulkTransferV2 class split, data panel refactor`
- `1977fe8 | 2026-02-24 18:26:07 -0700 | Sync: use case application doc, dual-env API layer, GUI refactors, multi-session hardening`
- `5526bd5 | 2026-02-24 08:21:06 -0700 | Sync: work laptop setup guide, waiver summary, SSL docs, Python 3.12, vllm pin fix`
- `03a2dca | 2026-02-23 20:44:05 -0700 | Sync: Data Transfer panel, mode persistence, offline field graying, dev inventory`
- `1318cb4 | 2026-02-23 19:05:46 -0700 | Fix 3 crash paths and 1 hardcoded model name found by code audit`

## 9. Notes
- Commit ledger is intentionally exhaustive for the 7-day window.
- For deep file-level diffs, use git show <commit> in the corresponding repository.


## 10. Supplemental Decision Matrix
| Condition | Preferred Option | Why |
|-----------|------------------|-----|
| <= 500K chunks, low ops headcount | A + D | Lowest operational complexity; fastest to stabilize |
| 500K-5M chunks, latency pressure | A -> B + D | Keep metadata stack, add ANN where it pays off |
| Multi-team/service integration needed | A/B -> C | Explicit interfaces and independent scaling |
| Air-gapped or media-constrained deployments | A + D | Smaller footprint, predictable packaging |

## 11. Delivery Gates (Exit Criteria)
- Phase 1 exit:
  - CI guard active for parser/config drift and enforced in push path
  - Offline media SOP published and dry-run validated
  - Minimal offline model pack reproducibly installable
- Phase 2 exit:
  - Skip-reason metrics available by extension and reason code
  - OCR/parser preflight check blocks misconfigured runs with clear fix steps
  - Large-corpus rehearsal completes with documented bottlenecks
- Phase 3 exit:
  - ANN prototype benchmarked against baseline on identical corpus
  - Decision memo created (adopt/defer) with explicit cost and complexity impact
  - Production runbook updated for chosen backend

## 12. Model-Pack Profiles (Recommended)
| Profile | Models | Typical Use | Media Fit |
|---------|--------|-------------|-----------|
| Minimal | `nomic-embed-text` + `phi4-mini` | Baseline offline indexing + Q/A | Single DVD-5 or DVD-9 feasible |
| Standard | Minimal + one medium alternate | Team workflows with one fallback model | Usually multi-disc |
| Full | Approved full local stack | Advanced tuning and broad role coverage | USB/SSD preferred, multi-disc required |

## 13. Risk Register (Current)
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Private/Educational drift | High | Medium | Strengthen sync checks and forced parity tests |
| Silent parser skips regression | High | Medium | CI guard + skip telemetry + daily summary |
| Offline media incompleteness | High | Medium | Pre-stage validator + required-layout checks |
| Model footprint exceeds media plan | Medium | High | Tiered model packs + explicit capacity planning |
| Installer source trust gap | High | Low/Medium | Authenticode + SHA256 logging before packaging |

## 14. Near-Term Priority Stack
1. Lock parser-drift CI enforcement and make failures blocking.
2. Finalize offline media process with pre-stage validation as default.
3. Instrument skip/OCR outcomes for operational observability.
4. Rehearse 650 GB flow with checkpointed bottleneck notes.
