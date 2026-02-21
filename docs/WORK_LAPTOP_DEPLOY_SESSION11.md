# Work Laptop Deployment Guide -- Session 11 Build

## What Changed (Session 11 Optimization)

This build includes the optimization campaign results:

| Component | Change | Impact |
|-----------|--------|--------|
| config/default_config.yaml | temperature 0.1->0.05, min_score 0.3->0.10, top_k 5->12 | Better retrieval accuracy |
| src/core/query_engine.py | 9-rule source-bounded prompt with priority ordering | 98% eval pass rate |
| Eval/ | Golden dataset (400 questions) | Automated evaluation |
| scripts/run_eval.py | Minimal auto-eval scorer | Eval framework |
| tools/eval_runner.py | Full eval runner | Eval framework |
| tools/score_results.py | Detailed scorer with CSV output | Eval framework |
| tools/run_all.py | One-command eval wrapper | Eval framework |

---

## Deployment Steps

### Step 1: Sync to Educational Repo (home machine)

Per GIT_REPO_RULES.md -- never git clone on work machine. Use the sanitized
public repo:

```powershell
cd D:\HybridRAG3
python tools\sync_to_educational.py
```

Review the output for any [WARN] tags. Fix any leaked banned words before
proceeding.

```powershell
cd D:\HybridRAG3_Educational
git add -A
git status
git commit -m "Session 11: optimization campaign + eval framework"
git push origin main
```

### Step 2: Download ZIP on Work Laptop

1. Open browser on work laptop
2. Go to: https://github.com/jeremysmission/HybridRAG3_Educational
3. Click **Code** -> **Download ZIP**
4. Extract to your project folder (e.g., D:\HybridRAG3)

### Step 3: Preserve Machine-Specific Files

Before overwriting, back up these work-machine files:

```powershell
Copy-Item start_hybridrag.ps1 start_hybridrag_KEEP.ps1
```

After extracting the ZIP over the project folder:

```powershell
Copy-Item start_hybridrag_KEEP.ps1 start_hybridrag.ps1 -Force
Remove-Item start_hybridrag_KEEP.ps1
```

### Step 4: Verify Environment

```powershell
. .\start_hybridrag.ps1
rag-cred-status
rag-diag
```

### Step 5: Re-index (if source documents changed)

```powershell
rag-index
```

### Step 6: Test a Query

```powershell
rag-query "What is the operating frequency range?"
```

---

## Running the Evaluation Suite (home machine only)

The eval requires an active OpenRouter API key (online mode).

### Quick 100-question check:

```powershell
cd D:\HybridRAG3
. .\.venv\Scripts\Activate.ps1
python scripts\run_eval.py --golden Eval\golden_tuning_400.json --out eval_out\v4_100q.jsonl --limit 100
```

### Full 400-question evaluation:

```powershell
python scripts\run_eval.py --golden Eval\golden_tuning_400.json --out eval_out\v4_full_400.jsonl
```

### Expected Results (v4 prompt, Claude Opus):

| Gate | Target | Last Measured |
|------|--------|---------------|
| Overall pass rate | >= 90% | 98.0% |
| Answerable | >= 90% | 97.1% |
| Unanswerable | >= 95% | 100% |
| Injection resistance | >= 95% | 100% |
| Ambiguous | >= 90% | 100% |
| p95 latency | <= 5s | 6.6s (API dependent) |

Note: v4 prompt changes (priority ordering, tighter injection, ambiguity
override) have NOT yet been validated on full 400q run due to API key
exhaustion. Partial tests showed all fixes working correctly.

---

## Files NOT Transferred to Work (per GIT_REPO_RULES)

- .claude/ (local tooling state)
- deploy_comments.ps1 (sanitizer with banned word list)
- Any eval output files (eval_out/, scored_out/, *.jsonl)
- Virtual test framework files
- Session handover docs mentioning AI tools
- TIERED_MEMORY_DESIGN.md (removed -- contained AI references)

---

## Hardware Notes

- Current personal laptop: 8GB RAM, 512MB VRAM -- cannot run Ollama 3B+ models
- Work laptop: corporate standard (check RAM availability)
- Upcoming: dual RTX 3090 workstation (48GB GPU, 64GB RAM) -- will enable
  full offline Ollama evaluation with qwen2.5:7b-instruct-q5_K_M

---

## Key Config Settings to Verify on Work Machine

Open config/default_config.yaml and confirm:

```yaml
mode: online                          # or offline if Ollama available
api:
  endpoint: https://openrouter.ai/api/v1   # or your company endpoint
  model: anthropic/claude-opus-4.6         # or your company model
  temperature: 0.05
retrieval:
  min_score: 0.10
  top_k: 12
  reranker_enabled: false              # DO NOT enable -- see handover doc
```

API credentials are stored in Windows Credential Manager (per machine):
```powershell
rag-store-key         # stores API key
rag-store-endpoint    # stores endpoint URL
rag-cred-status       # verify credentials
```
