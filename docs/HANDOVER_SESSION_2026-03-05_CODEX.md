# Codex Handoff

- Timestamp: 2026-03-05 America/Denver
- Session ID: codex-hybridrag3-online-rag-fix
- Repo: `D:\HybridRAG3`

## What changed

- Fixed online RAG prompt budgeting so API mode no longer inherits the small Ollama-style offline context budget.
- Fixed API chat prompt packaging so grounding instructions are sent as `system` content instead of one large `user` prompt.
- Fixed online model selection sync so GUI/runtime/admin paths set both `config.api.model` and `config.api.deployment`.
- Added per-mode tuning persistence in `config/mode_tuning.yaml` with separate `online` and `offline` values, defaults, and locks.
- Wired tuning UI to active-mode defaults/locks so you can tune each mode independently.
- Locked the clear-index action by default behind an explicit `Unlock Clear` control.

## Files changed

- `src/core/query_engine.py`
- `src/core/llm_router.py`
- `src/gui/helpers/mode_tuning.py`
- `src/gui/panels/tuning_tab.py`
- `src/gui/panels/query_panel.py`
- `src/gui/panels/query_panel_use_case_runtime.py`
- `src/gui/panels/query_panel_model_selection_runtime.py`
- `src/gui/helpers/mode_switch.py`
- `src/gui/app_runtime.py`
- `src/gui/panels/index_panel.py`
- `src/gui/panels/api_admin_tab.py`

## Verification

- `py_compile` passed for all edited Python files.
- Targeted `pytest` was started for API/query-engine coverage but timed out before a conclusive result.
- Private repo pushed: `264984a` on `main`
- Educational repo synced and pushed: `556155d` on `main`

## Remaining work

- Re-run targeted tests with a longer timeout:
  - `python -m pytest tests/test_api_router.py tests/test_query_engine_online_streaming_new.py -q`
  - `python -m pytest tests/test_gui_integration_w4.py -q`
- Add focused regression tests for:
  - online context budget staying online-sized
  - non-Azure `api.model` / `api.deployment` fallback
  - per-mode tuning defaults/locks independence
  - clear-index button locked by default
- Re-check `src/gui/panels/tuning_tab.py` in a live GUI pass; it compiles cleanly but changed materially.
- If tests use fake config objects, they may need `api.context_window` and related fields added.
- Private repo intentionally still has local-only dirt after restore:
  - `config/mode_tuning.yaml`
  - `docs/WORKSTATION_STRESS_TEST.md`
  - `bruce_lee.html`
  - `pacman.py`
  - `tools/query_latency_sim.py`
  - `void_hunter.html`
- Two temporary stashes remain in the private repo (`temp before educational sync*`) because they were not dropped after restore.

## Expected impact

- Online GPT-4o mode should be noticeably better grounded because it now gets the correct chat-role instructions and a much larger usable context budget.
- Offline mode should remain more grounded than before but still constrained by the local model's reasoning ceiling.
