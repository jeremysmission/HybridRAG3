# Checkpoint: Mode-Switch Retrieval Config Fix

**Date:** 2026-03-14 ~23:20 America/Denver
**Sprint context:** Sprint 5 (Demo Hardening) -- Priority 3

## What Was Done This Session

### 1. Root Cause Analysis (COMPLETE)
- Traced full config loading pipeline: `load_config()` -> `load_config_data()` -> `normalize_config_dict()` -> `build_runtime_config_dict()`
- `build_runtime_config_dict` in `config_authority.py:213` correctly merges mode-specific retrieval from YAML `modes.{mode}.retrieval` into flat `runtime["retrieval"]` dict
- But this only runs at load time with the persisted mode (offline)
- When tools/scripts set `config.mode = "online"` without calling `apply_mode_settings_to_config`, retrieval stays at offline values (top_k=5 instead of 10)

### 2. Fix: `apply_mode_to_config()` (COMPLETE)
- Added `apply_mode_to_config(config, mode, project_dir)` to `src/core/config.py`
- Re-reads YAML, overrides mode, re-runs `build_runtime_config_dict`, applies mode-specific retrieval/query/backend settings to live Config
- No GUI dependency -- safe to call from tools, scripts, API routes

### 3. Tool Fixes (COMPLETE)
- `tools/grounding_knob_stress_test.py`: replaced `config.mode = "online"` with `apply_mode_to_config(config, "online")`
- `tools/generation_autotune_live.py`: same fix

### 4. Retriever Cleanup (COMPLETE)
- Removed dead `config.modes` check from `_retriever_resolve_settings()` in `retriever.py`
- Config object is flat (no `modes` attribute), so the check never fired
- Docstring updated to explain the correct mode-switch flow

### 5. Verification (COMPLETE)
```
After load (offline): top_k=5, mode=offline
After apply online:   top_k=10, mode=online
After apply offline:  top_k=5, mode=offline
```
- 733 passed, 7 skipped, 0 failed (full regression)

## Config Mode-Switch Architecture (Reference)
1. **Load time**: `build_runtime_config_dict()` merges `MODE_RUNTIME_DEFAULTS[mode]` + YAML `modes.{mode}.retrieval` into flat dict
2. **GUI switch**: `mode_switch.py:_commit_router_and_mode()` -> `apply_mode_settings_to_config()` (reads from ModeTuningStore)
3. **API switch**: `routes.py:set_mode()` -> same `apply_mode_settings_to_config()`
4. **Tool/script switch**: NEW `apply_mode_to_config()` -> re-reads YAML, re-merges
5. Config YAML: `modes.online.retrieval.top_k: 10`, `modes.offline.retrieval.top_k: 5`
6. Hardcoded defaults (mode_config.py): online=6, offline=4 (overridden by YAML)

## Still Outstanding (from previous checkpoint)
- [ ] Commit and push all changes (Priority 4)
- [ ] PPT/Excel report generation feature (Priority 1 -- new sprint)
- [ ] PS1 BOM fixes (17 files) + Set-Content traps (7) + here-strings (3)
- [ ] Sprint plan update incorporating all

## Key File Locations
- New function: `src/core/config.py` `apply_mode_to_config()` (~line 836)
- Config authority merge: `src/core/config_authority.py:213` `build_runtime_config_dict()`
- Mode defaults: `src/core/mode_config.py:113` `MODE_RUNTIME_DEFAULTS`
- GUI mode switch: `src/gui/helpers/mode_switch.py:58` `_commit_router_and_mode()`
- Stress test: `tools/grounding_knob_stress_test.py:250`
- Previous checkpoint: `CHECKPOINT_2026-03-14_224500_GROUNDING_FIX_AND_STRESS_TEST.md`
