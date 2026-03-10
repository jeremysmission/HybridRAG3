# Mode Autotune Guide

## What this does

`tools/run_mode_autotune.py` automates the tuning workflow for offline and online mode.

Default safe behavior:

- Start with a **50-question screening pass**
- Use the small **starter** retrieval grid plus named query/generation bundles
- **Do not** change `config/config.yaml` unless you explicitly apply winners

The tool writes timestamped results under:

- `logs/autotune_runs/<timestamp>/`

Key output files:

- `leaderboard.csv` -- ranked candidates across the run
- `winner_set.json` / `winner_set.csv` -- preferred-stage ranked candidate set per mode
- `bundle_summary.json` / `bundle_summary.csv` -- grouped summary by mode, stage, and query/generation bundle
- `winners.json` -- preferred winner per mode, including whether that winner is eligible for `--apply-winner`
- `offline|online/<stage>/<candidate>/effective_settings.json` -- retrieval, query-policy, and generation snapshot for that candidate
- `README_NEXT_STEPS.txt` -- plain-English next actions
- `applied_defaults.json` -- only written when winners are applied

## What Sprint 4 changed

Autotune no longer screens only retrieval plus a token-budget dial.

Each candidate now combines:

- retrieval knobs:
  - `top_k`
  - `min_score`
  - output budget (`num_predict` offline, `max_tokens` online)
- query/generation bundle:
  - `grounding_bias`
  - `allow_open_knowledge`
  - `temperature`
  - `top_p`

That keeps the search space manageable while finally tuning the query-policy and generation side, not just retriever behavior.

## Workstation-friendly launchers

Use the batch files on the work machine first. They avoid PowerShell execution-policy problems.

The batch launchers try Python in this order:

1. `.venv\Scripts\python.exe`
2. `py -3`
3. `python`

Main launcher:

- `tools\run_mode_autotune.bat`

Preset launchers:

- `tools\autotune_preflight.bat`
- `tools\autotune_screen_50.bat`
- `tools\autotune_full.bat`
- `tools\autotune_apply_winners.bat`

The preset batch files default to **offline mode first**. You can override that by adding `--mode online` or `--mode both`.

## What data you actually need

The current default config expects these paths:

- `D:\RAG Source Data` -- your raw documents
- `D:\RAG Indexed Data\hybridrag.sqlite3` -- the built search database
- `D:\RAG Indexed Data\_embeddings` -- cached embedding data

The important distinction:

- `source_folder` is where you put documents you want HybridRAG to index
- `database` and `_embeddings` are the index artifacts HybridRAG reads at query and autotune time

For autotuning and normal querying, you do **not** need to re-copy raw documents if the workstation already has a valid index at:

```text
D:\RAG Indexed Data\hybridrag.sqlite3
```

If that file already exists and `rag-status` shows the index is populated, you can start with autotune immediately.

You only need raw source documents when:

- the workstation does not have an index yet
- you want to rebuild the index on that machine
- you need to add new documents before tuning

## Where to get the data

Get source documents from the same controlled document locations your team already uses, for example:

- engineering shared drives
- report folders on file servers
- SharePoint or Teams exports
- approved project archive folders

If you need to pull a large document set from a network share onto the workstation, use the built-in transfer tool instead of manual drag-and-drop:

```powershell
python -m src.tools.bulk_transfer_v2 `
    --sources "\\Server\Share\Engineering" "\\Server\Share\Reports" `
    --dest "D:\RAG_Staging"
```

After that:

1. Check `D:\RAG_Staging\quarantine\` for failures.
2. Use `D:\RAG_Staging\verified\` as the safe folder to index.
3. Point HybridRAG `source_folder` at that `verified\` folder or copy those files into `D:\RAG Source Data`.
4. Run `rag-index`.

If you are using the packaged educational tuning corpus from this repo, copy:

```text
docs\03_guides\Role_Corpus_Pack
```

into:

```text
D:\RAG Source Data\
```

That should leave you with:

```text
D:\RAG Source Data\Role_Corpus_Pack
```

## Quick preflight before autotune

1. Check whether the built index already exists:

```text
D:\RAG Indexed Data\hybridrag.sqlite3
```

2. Run:

```powershell
rag-status
```

3. If the database is missing or empty, populate `D:\RAG Source Data` and run:

```powershell
rag-index
```

4. For offline autotune, also make sure Ollama is up and at least these models are available:

```powershell
ollama pull nomic-embed-text
ollama pull phi4-mini
```

5. For online autotune, you still need the same local index, plus working API credentials.

## Recommended operator flow

### 1. Run the preflight check

From the repo root:

```bat
tools\autotune_preflight.bat
```

This checks:

- dataset exists
- index exists and is populated
- current index appears to match the eval corpus
- offline or online runtime readiness

If you want to check both runtimes:

```bat
tools\autotune_preflight.bat --mode both
```

### 2. First pass: offline 50-question screen

From the repo root:

```bat
tools\autotune_screen_50.bat
```

This runs:

- mode: `offline`
- workflow: `screen`
- grid: `starter`
- limit: `50`

Approximate time:

- Offline starter screen: about **30 to 90 minutes**

### 3. Review results

Open the newest run folder under:

```text
logs\autotune_runs\
```

Review:

- `leaderboard.csv`
- `winner_set.json`
- `bundle_summary.csv`
- `winners.json`

### 4. Promote offline finalists to the full dataset

```bat
tools\autotune_full.bat
```

This keeps the same starter grid, reruns the best screen finalists, and scores them on the full set.

Approximate time:

- Offline full finalist pass: about **1.5 to 4 hours**

### 5. Apply the offline winner

```bat
tools\autotune_apply_winners.bat
```

This writes the winning tuned keys into:

- `config/config.yaml`

It updates the mirrored per-mode sections under:

- `modes.offline`
- `modes.online`

It updates both:

- active values
- stored defaults

Important baseline rule:

- `tools/run_mode_autotune.py` defaults to `--config config/config.yaml`
- that means each autotune run starts from the current active runtime sections under:
  - `modes.offline.retrieval`
  - `modes.offline.ollama`
  - `modes.offline.query`
  - `modes.online.retrieval`
  - `modes.online.api`
  - `modes.online.query`
- the separate `modes.offline.defaults` and `modes.online.defaults` entries are stored defaults, not necessarily the active starting point for a run

Before comparing a new autotune run to an older handoff or cheat sheet, check `config/config.yaml` first so you are comparing against the actual baseline used by the tool.

Sprint 4 winner artifacts now also show the paired query/generation bundle and a preferred-stage ranked winner set, so review is no longer limited to retriever-side settings.

If a full-run finalist stage fails but the screen-stage result is still the best available evidence, `winner_set.json` and `winners.json` can point back to that screen fallback. In that case `winners.json` marks the mode as not apply-eligible so `--apply-winner` does not silently promote a screen-only fallback.

## Online mode

After offline looks good, run the same flow for online.

### Online 50-question screen

```bat
tools\autotune_screen_50.bat --mode online
```

Approximate time:

- Online starter screen: about **15 to 60 minutes**

### Online full finalists

```bat
tools\autotune_full.bat --mode online
```

### Apply the online winner

```bat
tools\autotune_apply_winners.bat --mode online
```

If online credentials are missing, the autotune tool will skip online mode and tell you why.

## Tune both modes in one run

If you want a combined run after the offline pass is proven stable:

```bat
tools\run_mode_autotune.bat --workflow screen --mode both
tools\run_mode_autotune.bat --workflow full --mode both
tools\run_mode_autotune.bat --workflow full --mode both --apply-winner
```

## Useful overrides

Run the wider overnight grid:

```bat
tools\run_mode_autotune.bat --workflow screen --mode offline --grid wide
```

Lock tuned keys after applying winners:

```bat
tools\run_mode_autotune.bat --workflow full --mode offline --apply-winner --lock-winner
```

Cap the full finalist run for a shorter spot check:

```bat
tools\run_mode_autotune.bat --workflow full --mode offline --full-limit 100
```

## Notes

- The autotuner reuses `tools/eval_runner.py` and `tools/score_results.py`.
- Candidate configs are written under `config/.tmp_autotune/` for the run.
- Results go under `logs/autotune_runs/`.
- The v1 autotuner intentionally excludes:
  - advanced backend-specific generation knobs such as online `presence_penalty` / `frequency_penalty`
  - backend-specific search-space expansion beyond the current shared bundle set

That keeps the overnight search space manageable while Sprint 4 focuses on retrieval plus shared query-policy and generation bundle tuning.
