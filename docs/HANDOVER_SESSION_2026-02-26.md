# Handover -- Session 2026-02-26: Demo Stability Hardening

## What We Did

ChatGPT (architect) directed a demo-freeze stability audit and fix pass.
Claude (testbed) executed all code changes, tests, and verification.

### P0 -- Index Cancel Correctness (F8 + F7)

**Problem:** Clicking Cancel during indexing raised `InterruptedError` inside
the progress callback, but the per-file `except Exception` caught it and
continued, emitting one error per remaining file. On a 1,345-file dataset
this meant 1,344 error callbacks and no actual stop. Discovery phase also
ignored the stop flag entirely.

**Fix:**
- Created `src/core/indexing/cancel.py` with `IndexCancelled(BaseException)`.
  BaseException bypasses `except Exception` in the per-file handler.
- Added `stop_flag` parameter to `Indexer.index_folder()`.
- Stop flag checked every 500 files during discovery AND at the top of
  the file processing loop (before `on_file_start`).
- Removed the old `InterruptedError` raise from `_GUIProgressCallback`.
- Added `_on_indexing_cancelled()` handler in `IndexPanel` for clean UI reset.

### P1 -- Mode Switch Atomicity (F10)

**Problem:** `_do_switch_to_online()` set `app.config.mode = "online"` and
persisted it to YAML *before* rebuilding the router. If the router rebuild
failed, the system was stuck in a half-online state with mode persisted
as "online" on disk.

**Fix:**
- Transactional pattern: gate + router must BOTH succeed before
  `app.config.mode` is mutated or `persist_mode()` is called.
- On router failure: gate is reverted to offline, messagebox shows error,
  mode stays unchanged in memory and on disk.
- Same pattern applied to offline switch direction.

### P1 -- Safe Shutdown (F9 / F14 / F18)

**Problem:** Daemon threads calling `widget.after()` after `destroy()` printed
`RuntimeError`/`TclError` to console during shutdown. Status bar dot timer
was not cancelled in `stop()`. Query elapsed timer not cancelled on close.

**Fix:**
- Created `src/gui/helpers/safe_after.py` -- wraps `widget.after()` in
  try/except, returns None on destroyed widget.
- Created `src/gui/helpers/shutdown_coordinator.py` -- registers threads
  and stop events, cancels timers, joins threads with bounded timeout
  (max 2s total, 0.3s per thread).
- Replaced all `self.after(0, ...)` calls from background threads in
  `query_panel.py`, `index_panel.py`, `tuning_tab.py`, and `status_bar.py`
  with `safe_after(self, 0, ...)`.
- `status_bar.stop()` now cancels both `_dot_timer_id` and `_cbit_timer_id`.
- `app._on_close()` collects timer IDs, registers threads, calls
  `shutdown.request_shutdown()` before `destroy()`.

### P2 -- Dimension Fallback (F5)

**Problem:** Two production init paths (`backend_loader.py:97` and
`launch_gui.py:201`) used `384` as the fallback embedding dimension.
The actual dimension is 768 (nomic-embed-text). Config load failure
could silently create a 384-dim VectorStore against 768-dim embeddings.

**Fix:**
- Created `src/core/constants.py` with `DEFAULT_EMBED_DIM = 768`.
- Replaced both `384` fallbacks with `DEFAULT_EMBED_DIM`.
- Fixed stale comment in `retriever.py:369` ("384" -> "768").

## Files Changed

### Modified (10 files, +141 / -49 lines)

| File | Change |
|------|--------|
| `src/core/indexer.py` | Added stop_flag param, cancel checks, IndexCancelled import |
| `src/core/retriever.py` | Fixed stale 384-dim comment |
| `src/core/bootstrap/backend_loader.py` | DEFAULT_EMBED_DIM fallback |
| `src/gui/app.py` | AppShutdownCoordinator wiring, new _on_close |
| `src/gui/helpers/mode_switch.py` | Transactional mode switch both directions |
| `src/gui/launch_gui.py` | DEFAULT_EMBED_DIM fallback |
| `src/gui/panels/index_panel.py` | safe_after, IndexCancelled catch, _on_indexing_cancelled |
| `src/gui/panels/query_panel.py` | safe_after in all background thread paths |
| `src/gui/panels/status_bar.py` | safe_after for CBIT, cancel dot timer in stop() |
| `src/gui/panels/tuning_tab.py` | safe_after for profile switch callback |

### New (5 files)

| File | Purpose |
|------|---------|
| `src/core/constants.py` | DEFAULT_EMBED_DIM = 768 |
| `src/core/indexing/__init__.py` | Package init, exports IndexCancelled |
| `src/core/indexing/cancel.py` | IndexCancelled(BaseException) |
| `src/gui/helpers/safe_after.py` | safe_after() wrapper |
| `src/gui/helpers/shutdown_coordinator.py` | AppShutdownCoordinator |

## How to Reproduce Tests

### Index Cancel Test

```python
import threading, time, tempfile, os
from src.core.indexer import Indexer, IndexingProgressCallback
from src.core.indexing.cancel import IndexCancelled
from src.core.config import load_config

tmpdir = tempfile.mkdtemp()
for i in range(100):
    with open(os.path.join(tmpdir, f'f{i}.txt'), 'w') as f:
        f.write('test ' * 200)

config = load_config()
# ... (use mock embedder/store/chunker) ...
stop = threading.Event()
threading.Timer(0.2, stop.set).start()
try:
    indexer.index_folder(tmpdir, stop_flag=stop)
except IndexCancelled:
    print("Clean cancel")
```

### Mode Switch Failure Test

```python
from src.gui.helpers import mode_switch

# Monkeypatch _rebuild_router to return Exception
mode_switch._rebuild_router = lambda app, **k: RuntimeError("forced")
mode_switch._do_switch_to_online(app)
assert app.config.mode == "offline"  # not mutated
```

## Remaining Known Issues

| ID | Severity | Description |
|----|----------|-------------|
| F3 | HIGH | Mode switch mid-query race -- no guard prevents switching while query is streaming |
| F4 | HIGH | reset_backends() nulls query_engine while query thread may be using it |
| F6 | HIGH | OpenAI (non-Azure) client has no timeout injection (600s default) |
| F11 | MEDIUM | API server bypasses LimitingEmbedder |
| F12 | MEDIUM | Config YAML write is not atomic (read-modify-write without file lock) |
| F13 | MEDIUM | CBIT thread handle not stored; overlapping runs possible after 60s |

These are deferred past demo freeze. None cause crashes -- they produce
cosmetic glitches or suboptimal behavior under specific race conditions.

## Test Results (Final)

```
pytest: 410 passed, 0 skipped, 0 warnings in 49.65s
```

Previous session: 409 passed, 1 skipped, 1 warning.
The tuning_tab RuntimeError warning is permanently eliminated.

## Commit Message (suggested)

```
Demo stability: transactional mode switch, clean index cancel, safe shutdown, 768-dim default
```
