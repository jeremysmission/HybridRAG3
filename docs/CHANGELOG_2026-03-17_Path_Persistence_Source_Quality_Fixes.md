# Path Persistence and Source Quality Fixes -- 2026-03-17

**Author:** Codex (GPT-5)
**Timestamp:** 2026-03-17 19:28:41 -06:00
**Scope:** mode/path persistence, stale source-quality refresh, retrieval hygiene, launcher reliability, grounded fallback transparency, grounded fallback UI visibility

---

## Why This Work Was Done

Two production-facing issues were still hurting the educational repo after the
earlier grounded GPT-4o fixes:

1. Saved data paths could reset or disappear on mode switch / restart.
2. The live index still contained stale `source_quality` metadata, so junk
   sources such as `golden_seeds_*`, `Testing_Addon_Pack`, ZIP bundles, and
   temp/demo artifacts were not being penalized at retrieval time.

There was also a separate syntax blocker in the multi-agent workspace scaffold
tool and a launcher dry-run regression in `start_gui.bat`.

---

## Files Changed

- `src/core/mode_config.py`
- `src/core/config_authority.py`
- `src/core/config.py`
- `src/gui/helpers/mode_tuning.py`
- `src/core/source_quality.py`
- `src/core/retriever.py`
- `src/core/index_qc.py`
- `src/core/grounded_query_engine.py`
- `src/gui/panels/query_panel_query_render_runtime.py`
- `src/gui/panels/reference_content.py`
- `src/tools/multiagent_workspace.py`
- `start_gui.bat`
- `start_rag.bat`
- `start_hybridrag.ps1`
- `tools/refresh_source_quality.py`
- `tests/test_config_authority.py`
- `tests/test_grounded_query_engine_stream_additional_new.py`
- `tests/test_index_qc.py`
- `tests/test_mode_tuning.py`
- `tests/test_powershell_entrypoints.py`
- `tests/test_query_panel_grounding_status.py`
- `tests/test_retriever_source_quality.py`
- `tests/test_runtime_retrieval_sync.py`
- `tests/test_source_quality.py`

---

## Fixes

### 1. Path persistence no longer wipes durable data paths

**What was wrong**

- `MODE_RUNTIME_DEFAULTS` did not include a `paths` section, which could trigger
  `KeyError: 'paths'` during mode snapshots.
- `save_config_field("paths.*")` only wrote into the active mode entry.
- Blank mode-entry paths could overwrite real root paths during runtime merges.
- GUI mode application could blank live config paths when a mode entry carried
  empty strings.
- `apply_mode_to_config()` updated retrieval/query/backend settings but did not
  reapply resolved runtime paths.

**What changed**

- Added `paths` to both mode runtime defaults.
- Root `paths.*` now mirror the last saved durable data paths.
- Runtime path merges now only inherit root fallback for durable data-path keys:
  `database`, `embeddings_cache`, `source_folder`, `download_folder`.
- Explicit blank `transfer_source_folder` values remain blank instead of being
  filled from the root fallback.
- `apply_mode_to_config()` now reapplies runtime paths and normalizes them.

**Result**

- Source/index paths persist correctly across restarts and mode switches.
- CLI/tooling mode switches now stay aligned with the selected mode’s DB/source
  paths.

### 2. Existing indexes can now recover from stale source-quality records

**What was wrong**

- `ensure_source_quality_map()` only backfilled missing rows.
- Any source indexed before the junk-detection rules existed kept stale rows like:
  `flags_json=[]`, `quality_score=0.92`, `retrieval_tier='serve'`.
- That meant penalties for junk categories never fired, even though the code now
  knew how to detect them.

**What changed**

- `ensure_source_quality_map()` now refreshes stale rows against current rules.
- Added `refresh_source_quality_records()` and
  `refresh_all_source_quality_records()` to re-score existing DB content.
- Added `tools/refresh_source_quality.py` for in-place refresh runs against an
  existing `hybridrag.sqlite3`.

**Result**

- Existing indexes no longer depend on a full rebuild just to pick up new
  source-quality rules.

### 3. Junk categories now resolve to `suspect`, not weakly penalized `archive`

**What was wrong**

- Test/demo artifacts, golden seeds, ZIP bundles, and temp/pipeline docs could
  end up as `archive` instead of `suspect`.
- `archive` only got a light penalty, so junk could still rank near the top.

**What changed**

- `_resolve_retrieval_tier()` now treats these junk flags as `suspect`.
- Retriever penalties still apply per-flag, and the archive penalty was nudged
  upward slightly.

**Result**

- Known junk sources are pushed down much more aggressively.

### 4. Index QC now catches in-root junk categories

**What was wrong**

- `detect_index_contamination()` mainly caught temp paths and outside-root paths.
- Broad in-root junk like `Testing_Addon_Pack` and `golden_seeds_*` slipped by.

**What changed**

- Added contamination markers for:
  - `test_or_demo_artifact`
  - `golden_seed_file`
  - `zip_bundle`
  - `temp_or_pipeline_doc`

**Result**

- QC now reports these as suspicious even when they live inside the configured
  source root.

### 5. Miscellaneous blockers fixed

- Capped lexical boost in vector-only retrieval to `1.0`.
- Fixed invalid Python identifiers in `src/tools/multiagent_workspace.py`.
- Fixed `start_gui.bat` dry-run so it works without a local `.venv`, and added a
  zero-byte `python.exe` guard so broken-venv checks fail cleanly instead of hanging.
- Restored a safe `start_hybridrag.ps1` entrypoint for PowerShell launch tests.

### 6. Open-knowledge fallbacks are now explicitly marked unverified

**What was wrong**

- When the grounded engine allowed open-knowledge fallback, the sync and stream
  paths could fall through to the base query engine and return a normal-looking
  answer with no explicit indication that grounding verification had been skipped.

**What changed**

- Sync and stream open-knowledge fallbacks are now wrapped in
  `GroundedQueryResult` metadata that marks the result as unverified.
- The debug trace now records the fallback decision path instead of making the
  answer look like a normal grounded success.

**Result**

- UI, logs, and QA tooling can distinguish a grounded answer from an
  open-knowledge fallback that skipped verification.

### 7. Query UI now surfaces unverified open-knowledge fallbacks

**What was wrong**

- The backend now tagged open-knowledge fallbacks as unverified, but the query
  panel renderer only showed a grounding banner when the result was blocked or
  had a non-negative grounding score.
- Because fallback results intentionally use `grounding_score = -1.0` and
  `grounding_blocked = False`, the UI still showed no grounding banner at all.

**What changed**

- Added a shared grounding-banner helper in the query renderer.
- The renderer now shows
  `Grounding: UNVERIFIED (open-knowledge fallback)` when verification was
  intentionally skipped for an open-knowledge fallback.

**Result**

- The user-visible query UI now matches the backend metadata instead of making
  those answers look like ordinary grounded completions.

### 8. PowerShell launcher path is now validated and the CLI wrapper avoids user-profile noise

**What was wrong**

- The earlier PowerShell entrypoint test only checked for execution-policy
  bypass text, not real script execution.
- `start_rag.bat` launched PowerShell without `-NoProfile`, so broken user
  PowerShell profiles could still inject noisy errors into the shell experience.

**What changed**

- Added an end-to-end test that executes `start_hybridrag.ps1` in a clean
  `-NoProfile` PowerShell session against a seeded fake repo/venv.
- Updated `start_rag.bat` to launch PowerShell with `-NoLogo -NoProfile -NoExit`.
- Updated the in-app reference content to recommend the no-profile launcher path
  when a workstation has a broken PowerShell profile.

**Result**

- The repo now proves `start_hybridrag.ps1` can execute successfully in a clean
  shell, and the main CLI wrapper no longer loads the user profile by default.

---

## Before / After Evidence

### Test baselines before this fix set

- `tests/test_mode_tuning.py -q` previously failed with the path snapshot bug
  (`KeyError: 'paths'`).
- `tests/test_multiagent_workspace.py` previously failed during import because
  `src/tools/multiagent_workspace.py` contained identifiers with spaces.
- `tests/test_start_gui_bat.py` previously had 2 failing dry-run tests.

### Verification after this fix set

Focused verification run:

```text
python -m pytest --basetemp .tmp_pytest_focus2 tests/test_mode_tuning.py tests/test_mode_autotune.py tests/test_config_authority.py tests/test_source_quality.py tests/test_retriever_source_quality.py tests/test_index_qc.py tests/test_multiagent_workspace.py tests/test_start_gui_bat.py tests/test_powershell_entrypoints.py tests/test_runtime_retrieval_sync.py tests/test_grounded_query_engine_stream_additional_new.py -q
python -m pytest --basetemp .tmp_pytest_gui2 tests/test_gui_integration_w4.py -k "test_18_data_paths_panel_reads_and_saves or test_19_data_paths_rejects_bad_folders" -q
```

Result:

```text
81 passed in 57.29s
2 passed, 33 deselected in 37.88s
```

Additional targeted verification:

```text
python -m pytest --basetemp .tmp_pytest_grounding_fix tests/test_runtime_retrieval_sync.py tests/test_grounded_query_engine_stream_additional_new.py -q
python -m pytest --basetemp .tmp_pytest_qafix tests/test_index_qc.py tests/test_powershell_entrypoints.py tests/test_start_gui_bat.py -q
python -m pytest --basetemp .tmp_pytest_qa1_ui tests/test_query_panel_grounding_status.py tests/test_query_panel_memory_guidance.py -q
python -m pytest --basetemp .tmp_pytest_qa1_ps tests/test_powershell_entrypoints.py -q
python -m pytest --basetemp .tmp_pytest_qa1_grounded tests/test_runtime_retrieval_sync.py tests/test_grounded_query_engine_stream_additional_new.py -q
python -m pytest --basetemp .tmp_pytest_qa1_mix tests/test_index_qc.py tests/test_start_gui_bat.py tests/test_config_authority.py tests/test_mode_tuning.py -q
```

Result:

```text
17 passed in 1.83s
13 passed in 14.91s
9 passed in 0.53s
5 passed in 2.85s
17 passed in 1.59s
33 passed in 10.99s
```

### Live source-quality refresh evidence

Command run:

```text
python tools/refresh_source_quality.py --db "D:\RAG Indexed Data\hybridrag.sqlite3"
```

Before refresh:

```text
total_rows:   460
serve_rows:   279
suspect_rows: 3
archive_rows: 178
golden_seed:  0
test_demo:    0
zip_bundle:   0
temp_doc:     0
```

Refresh run:

```text
total_sources: 1285
refreshed:     975
skipped_manual_override: 0
```

After refresh:

```text
total_rows:   1297
serve_rows:   709
suspect_rows: 19
archive_rows: 569
golden_seed:  7
test_demo:    16
zip_bundle:   2
temp_doc:     4
```

Spot-checks after refresh:

- `golden_seeds_*.json` are now `suspect` with `["test_or_demo_artifact", "golden_seed_file"]`
- `Testing_Addon_Pack\Unanswerable_Question_Bank.pdf` is now `suspect`
- `HybridRAG3_Testing_Addon_Pack.zip` is now `suspect`
- temp/demo docs are now `suspect`

### Retrieval probe after refresh

Read-only retriever probe against the live DB:

- Query: `What frequency does the RF system operate at, and what is the tolerance?`
  - Top hits now include `Role_Corpus_Pack\CAD_Tolerance_Spec.docx` and
    `Role_Corpus_Pack\Engineer_System_Spec.docx`
- Query: `What TCP port should be reachable for application connectivity?`
  - Top hit is now `Role_Corpus_Pack\Field_Deployment_Guide.docx`

---

## Residual Risk / What Is Still Not Solved

The stale-metadata problem is fixed, but the live corpus is still broad and
mixed. Some generic queries still surface ordinary in-root but out-of-domain
documents such as textbooks or Python docs because they are not junk artifacts;
they are just semantically nearby in a mixed corpus.

Example from the post-refresh probe:

- Query: `What are the calibration intervals?`
  - Rank 1 was still a logic-design textbook PDF.

That is no longer a stale-source-quality bug. It is a corpus-shape / collection
scoping problem. The real fix there is:

1. keep role/workload corpora in cleaner source roots or collections
2. use stronger collection/domain scoping during retrieval
3. avoid mixing broad general-reference material into the same serving index

---

## Recommended Next Steps

1. Keep using `tools/refresh_source_quality.py` after any future rule changes.
2. Build the new 500 GB corpus in role-structured subfolders, not a flat junk drawer.
3. Consider separate indexes or collection tags for:
   - engineering
   - logistics analyst
   - program management
   - autocad
   - cyber security
   - system administrator
   - field engineer
4. Re-run recall / query probes after the large corpus is indexed.
