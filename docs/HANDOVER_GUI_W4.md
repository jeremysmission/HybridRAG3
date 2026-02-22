# HANDOVER: GUI Prototype (Window 4)

## Date: 2026-02-21
## Status: Prototype complete, 14/14 tests pass, 115/115 regression pass

---

## How to Launch

```
python src/gui/launch_gui.py
```

Or from PowerShell:
```
.\tools\launch_gui.ps1
```

---

## Panel Descriptions

### Title Bar
- Shows "HybridRAG v3" with two toggle buttons: OFFLINE and ONLINE
- Active mode button is green with sunken relief
- OFFLINE is always safe (no confirmation needed)
- ONLINE checks credentials first -- shows error dialog if API key or endpoint missing
- Tells user to run `rag-store-key` and `rag-store-endpoint` from PowerShell if creds missing

### Query Panel
- **Use case dropdown**: Populated from `USE_CASES` in `scripts/_model_meta.py` (9 options: Software Engineering, Engineering/STEM, Systems Administration, Drafting/AutoCAD, Logistics Analyst, Program Management, Field Engineer, Cybersecurity Analyst, General AI)
- **Model field** (read-only): Shows auto-selected model via `select_best_model()` stub. Updates when use case changes.
- **Question entry**: Text field with placeholder text, supports Enter key
- **Ask button**: Disables during query, runs `QueryEngine.query()` in background thread, re-enables on completion
- **Network indicator**: Shows "Sending to API..." during online queries, "Querying local model..." during offline
- **Answer area**: Scrollable, selectable text. Shows errors in red with `[FAIL]` prefix
- **Sources line**: Lists source filenames with chunk counts
- **Metrics line**: Shows latency (ms), tokens in, tokens out

### Index Panel
- **Source folder**: Text entry with Browse button (opens folder picker dialog)
- **Start Indexing**: Validates folder exists, runs `indexer.index_folder()` in background thread with progress callback
- **Stop button**: Sets a flag checked between files -- stops after current file completes
- **Progress bar**: Advances as each file completes, shows "X / Y files" counter
- **Progress label**: Shows current filename being processed, errors in orange
- **Last run label**: Shows timestamp, chunk count, and elapsed time after completion

### Status Bar (bottom)
- Updates every 5 seconds automatically
- **LLM indicator**: Shows model name and provider (e.g., "gpt-4o (Azure)" or "phi4-mini (Ollama)")
- **Ollama indicator**: Green "Ready" or gray "Offline"
- **Gate indicator**: Clickable label that toggles mode. Green dot for ONLINE, gray for OFFLINE

### Engineering Menu (separate window)
- Opened from Engineering menu bar item
- **Retrieval Settings**: top_k slider (1-50), min_score slider (0.0-1.0), hybrid search toggle, reranker toggle
- **LLM Settings**: max tokens slider (256-4096), temperature slider (0.0-1.0), timeout slider (10-120s)
- **Performance Profile**: Dropdown (laptop_safe/desktop_power/server_max), calls `_profile_switch.py`
- **Test Query**: Input field with Run Test button, shows result and latency
- **Reset to Defaults**: Restores all sliders to values captured at window open
- **Close**: Dismisses the window
- All changes write to config immediately

### Menu Bar
- **File > Exit**: Clean shutdown
- **Engineering > Engineering Settings...**: Opens engineering menu
- **Help > About**: Shows system description

---

## Backend Functions Called

| Panel | Function | Module |
|-------|----------|--------|
| Query | `QueryEngine.query(question)` | `src/core/query_engine.py` |
| Query | `select_best_model(uc_key, deployments)` | `src/gui/stubs.py` (TODO: `scripts/_model_meta.py`) |
| Query | `get_available_deployments()` | `src/gui/stubs.py` (TODO: `src/core/llm_router.py`) |
| Index | `indexer.index_folder(path, callback)` | `src/core/indexer.py` |
| Status | `router.get_status()` | `src/core/llm_router.py` |
| Mode | `credential_status()` | `src/security/credentials.py` |
| Mode | `configure_gate(mode, endpoint)` | `src/core/network_gate.py` |
| Profile | `_profile_switch.py [name]` | `scripts/_profile_switch.py` (subprocess) |
| Profile | `_profile_status.py` | `scripts/_profile_status.py` (subprocess) |

---

## Stub Functions (Window 2 Dependency)

Three functions are stubbed in `src/gui/stubs.py` pending Window 2 delivery:

1. `get_available_deployments()` -- returns fake deployment list
2. `select_best_model(use_case_key, available_deployments)` -- returns first deployment
3. `get_routing_table(available_deployments)` -- maps all use cases to first deployment

**To replace stubs:**
1. Window 2 delivers to `D:\HybridRAG3_API_MOD`
2. Merge `_model_meta.py` and `llm_router.py`
3. Search-and-replace imports from `src.gui.stubs` to real modules
4. Delete `src/gui/stubs.py`

All stub call sites are marked with `# TODO: stub -- replace with real _model_meta.py call after Window 2 merge`

---

## Files Created

```
src/gui/__init__.py               -- Package init
src/gui/app.py                    -- Main application window (HybridRAGApp class)
src/gui/stubs.py                  -- Temporary stubs for Window 2 functions
src/gui/launch_gui.py             -- Entry point with boot pipeline
src/gui/panels/__init__.py        -- Panels subpackage init
src/gui/panels/query_panel.py     -- Query input and answer display
src/gui/panels/index_panel.py     -- Folder picker and indexing progress
src/gui/panels/status_bar.py      -- Live system status strip
src/gui/panels/engineering_menu.py -- Tuning controls (child window)
tools/launch_gui.ps1              -- PowerShell launcher
tests/test_gui_integration_w4.py  -- 14 integration tests
docs/HANDOVER_GUI_W4.md           -- This file
```

---

## Known Limitations

1. **Stubs**: Three model routing functions are stubbed. Query panel always shows first deployment regardless of use case.
2. **Launch requires boot**: `launch_gui.py` attempts full boot pipeline. If boot fails (no vector store, no embedder), GUI opens but query/indexing are disabled.
3. **No config persistence**: Engineering menu changes live in the config object in memory. They are not saved to YAML. Profile changes ARE saved via `_profile_switch.py`.
4. **No indexing cancellation mid-file**: Stop button waits for current file to finish.
5. **No query history**: Previous queries are not saved or navigable.
6. **Single query thread**: Cannot run multiple queries simultaneously.
7. **No dark mode**: Uses system default tkinter theme.
8. **tkinter limitations**: No rich text formatting in answer area, basic widget styling.

---

## What Needs Jeremy's Review

1. **Layout and UX**: Does the panel arrangement work? Any controls missing?
2. **Use case list**: All 9 USE_CASES are shown. Should any be hidden for the prototype?
3. **Engineering menu defaults**: Slider ranges match spec. Are the defaults correct?
4. **Mode switching**: Online mode requires stored credentials. Is the error message clear enough?
5. **Network indicators**: Every panel shows network activity status. Is visibility sufficient?
6. **Stub replacement plan**: The search-and-replace approach for Window 2 merge. Any concerns?

---

## Suggested Next Steps

1. **Merge Window 2 stubs**: Replace `stubs.py` with real `select_best_model()` and `get_routing_table()`
2. **Config persistence**: Save engineering menu changes to `default_config.yaml`
3. **Query history**: Add a history dropdown or list of recent queries
4. **Result export**: Copy answer to clipboard, or save as text file
5. **Progress persistence**: Remember last indexed folder across sessions
6. **Production UI**: Consider replacing tkinter with a web-based UI (FastAPI + HTML) for richer formatting
7. **Accessibility**: Add keyboard shortcuts for common actions
