# Checkpoint: Grounding Fix + Online API Stress Test

**Date:** 2026-03-14 ~22:45 America/Denver
**Sprint context:** Sprint 5 (Demo Hardening) + Online API Proof

## What Was Done This Session

### 1. Generation Autotune (COMPLETE)
- 8 bundles swept against live gpt-4o, 20 questions each
- Winner: current-baseline (score=83.3%, temp=0.08, grounding=8, open knowledge ON)
- Results: `logs/generation_autotune/20260314_191730_generation_sweep.json`
- $0.69 total cost, 27 minutes, zero errors

### 2. Grounding Knob Stress Test (COMPLETE)
- Created `tools/grounding_knob_stress_test.py`
- 10 questions x 5 grounding configs = 50 API calls per run
- Two runs: before fix ($0.13) and after fix ($0.14)
- Results: `logs/grounding_stress_test/` (two JSON files)

### 3. Grounding Prompt Fix (COMPLETE)
- **Fix 1 - Strict prompt Rule 1 (GROUNDING)**: Changed from "Use only facts explicitly stated" to "Base your answer on information from the context. You may interpret, summarize, and connect facts"
- **Fix 2 - Strict prompt Rule 3 (REFUSAL)**: Changed from "If context does not contain info" to "If context contains NO relevant info at all... Prefer partial answer over full refusal"
- **Fix 3 - Relaxed prompt VERBATIM VALUES**: Added rule to preserve exact notation (-10C not -10 degrees C)
- File: `src/core/query_engine.py` lines ~149-167 (strict) and ~918-935 (relaxed)

### Before/After Results
| Config | Grounded BEFORE | Grounded AFTER |
|--------|----------------|----------------|
| bias=10 strict | 1/10 | 3/10 |
| bias=9 strict | 2/10 | 3/10 |
| bias=8 baseline | 6/10 | 8/10 |
| Fact hit rate | 33% | 50-67% |

### 4. QA Findings Fixed
- Banned word "defense" removed from hallucination_guard/__init__.py and claim_extractor.py
- Em-dashes replaced with -- in cli_test_phase1.py, gui_e2e/run.py, open_diagnostic.ps1
- Encoding corruption fixed in open_diagnostic.ps1

### 5. Remaining Strict-Mode Refusals (2/5 RAG questions)
- Root cause: retrieved chunks don't contain the specific answer
- Online config has top_k=10, but stress test only retrieves 5 chunks -- config not applying mode-specific retrieval
- guard_min_chunks=3 at bias=10 is tight for niche queries
- **FIX NEEDED**: Ensure mode-specific retrieval config is applied; consider adjusting guard formula

### 6. Still Outstanding
- Commit and push all changes
- Report generation feature (PPT/Excel) -- new sprint item
- PS1 BOM fixes (17 files) -- QA mechanical fix
- Set-Content BOM traps (7 instances) -- QA mechanical fix

## Credential env vars needed per session
```bash
export OPENAI_API_KEY="<your-key>"
export HYBRIDRAG_API_ENDPOINT="https://api.openai.com"
export HYBRIDRAG_API_PROVIDER="openai"
```

## Key File Locations
- Grounding stress test: `tools/grounding_knob_stress_test.py`
- Generation autotune: `tools/generation_autotune_live.py`
- Prompt (strict): `src/core/query_engine.py` ~line 142-209
- Prompt (relaxed): `src/core/query_engine.py` ~line 918
- Guard policy mapper: `src/core/query_mode.py` lines 23-44
- Config: `config/config.yaml`
- Previous checkpoint: `docs/09_project_mgmt/CHECKPOINT_2026-03-14_150000_ONLINE_API_PROOF.md`
