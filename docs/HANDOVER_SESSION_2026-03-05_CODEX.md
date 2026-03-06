# Codex Handoff

- Timestamp: 2026-03-06 12:14:57 -07:00
- Session ID: codex-hybridrag3-online-rag-fix-round2
- Repo: `D:\HybridRAG3`

## What changed

- Fixed live retrieval settings so mode switches and tuning changes actually affect searches at query time.
- Fixed `QueryEngine` runtime sync so reloaded config objects propagate into the retriever and router instead of leaving stale references behind.
- Fixed per-mode tuning bootstrap so:
  - the first active mode starts from the live config
  - the inactive mode starts from its own mode defaults
  - offline values no longer leak into online mode
- Raised online defaults and fallbacks to GPT-4o-class values:
  - `api.max_tokens = 16384`
  - `api.timeout_seconds = 180`
  - `online min_score = 0.10`
- Removed the runtime `APIConfig.model = "gpt-3.5-turbo"` footgun; runtime default is now blank and online routing falls back cleanly to the selected deployment/model.
- Hardened online PII scrubbing so long engineering part numbers are not redacted as fake credit cards unless they pass Luhn validation.
- Fixed hidden `SettingsView` behavior so it no longer:
  - silently applies persisted dev tuning when the dev tuning tab is hidden
  - shows dev-only dangerous-setting popups
  - loses legacy reset-to-construction behavior
- Updated stale GUI/API fallback values that still said `2048` so the online path no longer defaults down to an old small output budget.

## Files changed

- `src/core/config.py`
- `config/default_config.yaml`
- `src/core/query_engine.py`
- `src/core/retriever.py`
- `src/core/llm_router.py`
- `src/security/pii_scrubber.py`
- `src/gui/helpers/mode_tuning.py`
- `src/gui/helpers/mode_switch.py`
- `src/gui/app_runtime.py`
- `src/gui/panels/query_constants.py`
- `src/gui/panels/tuning_tab.py`
- `src/gui/panels/settings_view.py`
- `src/gui/panels/api_admin_tab.py`
- `tests/conftest.py`
- `tests/test_api_router.py`
- `tests/test_mode_tuning.py`
- `tests/test_mode_switch_runtime.py`
- `tests/test_runtime_retrieval_sync.py`
- `tests/test_gui_mode_runtime_regressions.py`
- `tests/test_pii_scrubber.py`
- `tests/test_gui_integration_w4.py`

## Verification

- `python -m pytest --basetemp output/pytest_tmp_broad_c tests/test_runtime_retrieval_sync.py tests/test_mode_tuning.py tests/test_mode_switch_runtime.py tests/test_gui_mode_runtime_regressions.py tests/test_api_router.py tests/test_query_engine_online_streaming_new.py tests/test_pii_scrubber.py -q`
  - result: `41 passed, 1 skipped`
- `python -m pytest --basetemp output/pytest_tmp_broad_b tests/test_query_engine.py tests/test_retriever_structured_queries.py -q`
  - result: `11 passed`
- `python -m pytest --basetemp output/pytest_tmp_fix4 tests/test_mode_tuning.py tests/test_gui_integration_w4.py -k "test_11_settings_view_reads_config or test_12_settings_view_writes_config or test_17_admin_defaults_round_trip or test_18_data_paths_panel_reads_and_saves or test_first_active_mode_bootstraps_from_live_config_values or test_online_mode_bootstraps_from_online_defaults_not_shared_runtime_values or test_mode_values_and_locks_stay_independent_between_online_and_offline" -x -vv`
  - result: `6 passed, 1 skipped`
- Additional direct GUI checks passed:
  - `test_12_settings_view_writes_config`
  - `test_13_profile_dropdown_calls_switch`
  - `test_14_settings_view_reset_defaults`
  - `test_15_api_admin_tab_credential_fields`
  - `test_16_save_credentials_calls_store`
  - GUI halves `test_01` through `test_10` and `test_17` through `test_21`
- Official OpenAI docs check:
  - GPT-4o lists `128,000` context and `16,384` max output tokens, so `16384` is the correct non-artificial cap for standard GPT-4o

## Key conclusions

- The old `gpt-3.5-turbo` runtime default was a real bug, but secondary.
  - It could affect non-Azure/openai-compatible routing when `api.model` was blank.
  - It was not the main reason online mode felt weak.
- The bigger online underperformance causes were:
  - stale retrieval settings not updating live
  - stale config objects after reload/mode switch
  - overly low online defaults/fallbacks
  - hidden settings/dev tuning state mutating runtime config unexpectedly
- Online GPT-4o should now search and answer much more like the tuned online configuration instead of behaving like a partially disconnected offline profile.

## Remaining items

- Current local-only change left intentionally in the private repo:
  - `docs/WORKSTATION_STRESS_TEST.md`
- `tests/test_gui_integration_w4.py` is covered by passing sub-runs, but I still do not have one clean single-command whole-file pass under the current timeout budget.
- I did not change the prompt split to put retrieved context into the `system` role.
  - Current state remains: `system = rules`, `user = context + question`.
  - Reason for not changing it blindly: retrieved documents in `system` can amplify prompt-injection risk.
  - If revisited, do it as an explicit design choice with tests.
- There are still test-only references to `gpt-3.5-turbo` in simulation and routing fixtures; they are not runtime defaults now.

## Suggestions

- Add query-debug telemetry for both modes:
  - active mode
  - effective `top_k`
  - effective `min_score`
  - retrieved chunk count before and after pruning
  - final prompt/context chars or token estimate
  - selected online `model` and `deployment`
- Add a one-click GUI "compare modes" debug action that runs the same query through offline and online and saves:
  - retrieval scores
  - chunk IDs
  - context size
  - final answer
  This will make future grounding investigations much faster.
- If online still feels weaker after tuning, test prompt packaging variants explicitly:
  - current split: `system = rules`, `user = context + question`
  - safer two-user-message variant: `system = rules`, `user1 = context`, `user2 = question`
  Avoid moving raw retrieved context into `system` unless you accept the prompt-injection tradeoff.
- Run a manual A/B test with the same production-like question set in both modes after setting intentionally different knobs for each mode. The main thing to verify is that the GUI values now really stick per mode across:
  - app restart
  - mode switch
  - config reload
  - profile change
- If you want even stronger online answers later, the next highest-yield work is probably not more token budget. It is:
  - better retrieval telemetry
  - stricter eval-driven `top_k` / `min_score` tuning per use case
  - optional chunk-quality pruning before prompt assembly

## Repo state

- Private repo pushed: `059596a` on `main`
- Educational repo pushed: `fd2a0e2` on `main`
- Unrelated stray local files were removed from both repos.
- Educational repo is clean.

## Expected impact

- Online API GPT-4o mode should be materially better grounded and should obey online-specific retrieval settings instead of using stale offline-ish values.
- `16384` output tokens is now available consistently across config, GUI defaults, and prompt budgeting.
- Hidden settings/admin pages should stop mutating live tuning state when the dev tuning UI is not enabled.
