# Query Pipeline Deep Follow-Up
## Date: 2026-03-06
## Scope: Mode boundaries, runtime state bleed, index contamination, boot semantics, and offline latency

## Why This Doc Exists

This is the follow-up to `001_query_pipeline_audit.md`.
It captures what was learned from several hours of live tracing, code review,
targeted regression tests, and workstation-style probes so future agents do
not have to rediscover the same architecture traps.

## Highest-Value Lessons

1. Treat `offline` and `online` as separate operating profiles, not one
   symmetric path with different backends.
   - They have separate mode defaults.
   - They still share some code, but they do not behave identically in all
     runtime details.

2. Most bad behavior came from stale live state, not from a single bad prompt.
   - Config changed, but child runtime objects kept old state.
   - Credentials changed, but live online client kept old endpoint/key.
   - Query sync and query stream were not always following the same path.

3. Clean corpus and clean index matter more than almost any knob tweak.
   - A dirty index can make tuning results meaningless.
   - A temp/test document inside the index can look like a retrieval bug when
     it is really a data hygiene problem.

4. Boot/readiness must distinguish `not ready` from `not proven yet`.
   - A fast boot probe can time out even when real offline queries succeed.
   - Reporting that as total failure creates false-negative diagnostics.

## Concrete Bugs Fixed In This Sweep

### A. LLMRouter could attach an API router with only a key

- Problem:
  - `LLMRouter` created `APIRouter` when a key existed, even with no endpoint.
  - This made online readiness and diagnostics look healthier than reality.
- Fix:
  - `LLMRouter` now requires both key and endpoint before attaching
    `APIRouter`.
  - Late online attach also skips key-only credentials.
- Files:
  - `src/core/llm_router.py`
  - `tests/test_ollama_router.py`

### B. Guarded sync query path did not trim context

- Problem:
  - `GroundedQueryEngine.query()` built the guarded prompt from untrimmed
    context.
  - `GroundedQueryEngine.query_stream()` did trim.
  - Same query could behave differently depending on sync vs stream path.
- Fix:
  - Guarded sync path now calls `_trim_context_to_fit()` before prompt build.
- Files:
  - `src/core/grounded_query_engine.py`
  - `tests/test_runtime_retrieval_sync.py`
  - `tests/test_grounded_query_stream_resilience_new.py`

### C. Runtime sync skipped `transformers_rt`

- Problem:
  - `_sync_runtime_components()` updated `ollama`, `api`, and `vllm`, but not
    `transformers_rt`.
- Fix:
  - Runtime sync now propagates config into `transformers_rt` too.
- Files:
  - `src/core/query_engine.py`
  - `tests/test_runtime_retrieval_sync.py`

### D. Saving new API credentials did not invalidate the live online client

- Problem:
  - Admin panel saved credentials to storage but left an already-online
    in-memory API client attached.
  - Queries could continue using stale endpoint/key state until restart or
    mode switch.
- Fix:
  - Saving credentials now invalidates credential/deployment caches and clears
    the live API attachment so the next online query reattaches from fresh
    stored credentials.
- Files:
  - `src/gui/panels/api_admin_tab.py`
  - `tests/test_gui_integration_w4.py`

### E. Boot treated slow Ollama readiness as a hard total failure

- Problem:
  - `boot_hybridrag()` used a short background probe and could end with
    `success=False` even when offline queries worked moments later.
- Fix:
  - Boot now reports `offline_probe_pending=True` and shows `PENDING` in the
    summary instead of `FAILED` when the fast probe window expires.
- Files:
  - `src/core/boot.py`
  - `tests/test_boot_pending.py`

## New Tools Added

### `tools/query_path_probe.py`

Purpose:
- Trace the same queries through offline and online.
- Compare base engine vs grounded engine.
- Capture retrieval counts, prompt budget, suspicious source paths, and
  optional end-to-end latency.

Useful runs:
- `python tools/query_path_probe.py --engine base --mode both --skip-llm`
- `python tools/query_path_probe.py --engine base --mode offline --offline-model phi4-mini --offline-num-predict 32 --query "..."'

Key run folders from this sweep:
- `logs/query_path_probes/20260306_215140`
- `logs/query_path_probes/20260306_215622`
- `logs/query_path_probes/20260306_222643`
- `logs/query_path_probes/20260306_222818`

### `tools/index_qc.py`

Purpose:
- Detect index contamination from suspicious source paths.
- Build an index fingerprint baseline.
- Compare later fingerprints for drift.

Useful runs:
- `python tools/index_qc.py`
- `python tools/index_qc.py --write-baseline`

### `tools/index_qc.bat`

Purpose:
- Batch wrapper for workstation/operator use.

## Live Findings That Matter Operationally

### 1. Local index contamination was real

The MBTI probe query retrieved temp/test files under `AppData\\Local\\Temp`.
This was not hypothetical.

Implication:
- If retrieval looks irrational, check the indexed source paths before
  assuming a model or prompt bug.

### 2. The local index also did not match the autotune eval corpus

The local machine used for review had `0%` expected-source coverage for
`Eval/golden_tuning_400.json`.

Implication:
- Autotune on that local index would not have been meaningful.
- Corpus alignment must be checked before tuning.

### 3. Offline latency was workload-sensitive, not simply "Ollama is broken"

Observed:
- trivial raw Ollama prompt succeeded quickly
- full RAG prompt also succeeded when using `phi4-mini` and lower
  `num_predict`
- earlier long timeouts happened under heavier offline settings and/or
  colder model state

Implication:
- Offline latency is highly sensitive to:
  - chosen model
  - `num_predict`
  - warm vs cold model state
  - current workstation load

### 4. The boot probe was more pessimistic than the real query path

Boot still missed the 2-second join window on this machine even when later
offline queries succeeded.

Implication:
- Fast boot checks must be interpreted as readiness hints, not absolute truth.

## Mode Boundary Rules

Use this as the mental model:

### On mode switch
- Rebuild `LLMRouter`
- Reapply network gate policy
- Invalidate deployment cache
- Rebind runtime helpers to the live config

### On credential change
- Invalidate credential cache
- Invalidate deployment cache
- Clear live online API attachment

### On corpus/index change
- Rebuild the index from a clean source folder
- Reopen the vector store/retriever if needed

### Do not rebuild on every query
- whole app
- whole index
- whole engine stack

## Quality-Control Guidance

Use both:

1. Contamination detection
   - Read `chunks.source_path`
   - Fail if temp paths or outside-root paths exist

2. Fingerprint baseline
   - Hash the database plus embedding-cache artifacts after a known-clean
     rebuild
   - Compare later fingerprints to detect drift

This is better than hashing the index folder alone because hashing only tells
you the index changed, not whether it became contaminated.

## Remaining Open Risks

1. Guard-enabled end-to-end behavior was not deeply re-probed with the full
   real guard stack active in local config.

2. Runtime sync still mainly updates config references. Any child transport
   that caches derived state beyond the config object itself should still be
   reviewed carefully.

3. The local review machine still has a dirty index. Use `tools/index_qc.py`
   and a clean rebuild before trusting local retrieval conclusions.

## Recommended Next Steps

1. Keep `tools/index_qc.py` in the standard preflight workflow.
2. After a known-clean rebuild, write a fingerprint baseline.
3. Use `query_path_probe.py` whenever someone claims "online and offline
   behave differently" so the difference is measured, not guessed.
4. Build a separate behavior-eval set later for:
   - grounding bias
   - open-knowledge fallback
   - hallucination guard threshold/action
