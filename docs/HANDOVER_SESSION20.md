# Handover -- Session 20 (2026-02-26/27)

## Commits This Session
- **359d2c1** -- Session credential cache + async mode switch for demo speed
- **9fa1998** -- Add bootstrap architecture, GUI bug fixes, cleanup stale files

Both pushed to HybridRAG3 (private) and HybridRAG3_Educational (428f124).

## What Was Done

### 1. Bootstrap Architecture (commit 9fa1998)
New `src/core/bootstrap/` package with clean startup state machine:
- `boot_coordinator.py` -- BootCoordinator state machine (COLD -> VALIDATING -> LOADING -> READY_FOR_GUI)
- `startup_validator.py` -- Pre-flight checks (Ollama, disk, model availability)
- `environment.py` -- Platform/hardware detection
- `startup_health_probe.py` -- Post-boot health verification
- `backend_loader.py` -- Embedder/VectorStore/Router initialization
- `runtime_limits.py` + `limiting_embedder.py` -- Hardware-aware resource limits

### 2. Session Credential Cache (commit 359d2c1)
Root cause of 11-second OFFLINE toggle: 10-20 keyring lookups at ~100-200ms each.

**Fix**: Module-level `_credential_cache` in `src/security/credentials.py`:
- Session cache with thread-safe lock
- Env vars checked first (fast, 0ms), then keyring (slow, ~100ms each)
- `invalidate_credential_cache()` for mode switches and tests
- `resolve_credentials(use_cache=True)` is the default -- keyring queried once per session

### 3. Non-Blocking Mode Switch (commit 359d2c1)
`src/gui/helpers/mode_switch.py` redesigned:
- Background thread with `_switch_lock` double-click protection
- Mode buttons disabled during switch with status bar feedback
- `_rebuild_router()` accepts pre-resolved credentials (no redundant lookups)
- `_finish_switch()` re-enables UI on main thread via `app.after()`

### 4. Bug Fixes
- `boot_coordinator.py` line 127: `startup_status.errors` -> `.warnings` (attribute didn't exist)
- `launch_gui.py` `_init_store()`: `os.path.exists()` -> `os.makedirs(exist_ok=True)` (first-run fix)
- `response_sanitizer.py`: "Defense-in-depth" -> "Layered guard" (banned word)
- `gui_e2e/run.py` + `README_GUI_E2E.md`: removed banned word references
- Suppressed keyring config warning in `_read_keyring()` via `warnings.catch_warnings()`

### 5. Test Updates
- `test_credential_management.py`: Cache invalidation in `_clear_env()`, `use_cache=False` for mock tests
- `test_gui_integration_w4.py::test_10`: Rewritten for async mode switch (mock `app.after`)
- `test_provider_proxy.py::test_c05`: Updated for env-first priority

## Test Results
- **410 passed, 0 failed, 1 skipped** (full regression)
- **23/23 GUI E2E actions passed** (pre-cache changes)

## Pre-Cache Timing Baseline (from E2E report)
| Action | Duration |
|--------|----------|
| OFFLINE toggle | 11,183 ms |
| ONLINE toggle | 2,250 ms |
| Boot total | 2,396 ms |
| Embedder load | 2,420 ms |
| Embedder warmup | 180 ms |
| Embedder query | 69 ms |

**Expected improvement**: OFFLINE/ONLINE toggle should drop to <2s with credential cache.
Post-change timing not yet measured (needs fresh app launch for accurate numbers).

## Architecture Decisions
- Embedder and VectorStore are **sticky** -- NOT rebuilt on mode switch. Only LLMRouter rebuilds.
- Resolution order is now: ENV VARS (0ms) -> KEYRING (slow, cached after first call) -> CONFIG
- Two-repo strategy unchanged: shared infrastructure goes to both, API routing stays repo-specific

## Pending / Next Session
1. Run updated E2E + timing traces to measure actual improvement (for ChatGPT QA review)
2. Task #16: Update trace script so IBIT runs after backend load (shows 6/6 not 3/6)
3. Demo run transcript: app start -> query -> switch mode -> query
4. ChatGPT collaboration continues -- user relays between testbed (here) and QA (ChatGPT)

## File Map (modified this session)
```
src/security/credentials.py        -- Session cache + env-first resolution
src/gui/helpers/mode_switch.py      -- Async mode switch with thread safety
src/core/bootstrap/                 -- New package (6 files)
src/core/runtime_limits.py          -- Hardware-aware limits
src/core/limiting_embedder.py       -- Resource-bounded embedder wrapper
src/gui/launch_gui.py               -- _init_store bug fix
src/security/response_sanitizer.py  -- Banned word fix
tests/test_credential_management.py -- Updated for env-first + cache
tests/test_gui_integration_w4.py    -- Updated test_10 for async
tests/test_provider_proxy.py        -- Updated test_c05 for env-first
```
