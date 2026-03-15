# Autotune Cheat Sheet (March 2026)

This reference captures the final tuning results for March 6–7, 2026. Use it to hard-code the offline/online defaults, compare profiles, and check latency/cost expectations without replumbing the autotune logs every time.

## Offline Winner (`tk4_ms10_np384`)

| Metric | Value |
| --- | --- |
| Mode | offline (local Ollama `phi4-mini`) |
| Configuration | `hybrid_search=true`, `top_k=4`, `min_score=0.10`, `context_window=4096`, `num_predict=384`, `timeout_seconds=180`, `temperature=0.05`, `reranker=false` |
| Overall pass rate | 92.0% |
| Average score | 0.9631 |
| Latency | p50=46.8 s, p95=69.5 s |
| Gate notes | `injection_resistance` still ~46%; unanswerable accuracy 100% |
| Strongest profiles | Systems Admin (94.8%), Engineer (96.4%), Program Manager (94.7%) |
| Weakest profiles | Cybersecurity (86.5%), Field Engineer (89.5%) |
| Summary reference | `logs/tunelogs/offline_summary.json` (from `autotune_runs.zip` → `20260306_235420/offline/full/tk4_ms10_np384/scored/summary.json`) |

## Online Winner (`tk6_ms08_mt1024`)

| Metric | Value |
| --- | --- |
| Mode | online (API-backed, 128k context) |
| Configuration | `hybrid_search=true`, `top_k=6`, `min_score=0.08`, `max_tokens=1024`, `context_window=128000`, `timeout_seconds=180`, `temperature=0.05`, `reranker=false` |
| Overall pass rate | 94.5% |
| Average score | 0.9726 |
| Latency | p50≈0.52 s, p95≈0.98 s |
| Cost | ≈$0.0019 per 400-question run |
| Gate notes | injection/unanswerable both 100%, ambiguous still low at ~18% |
| Strongest profiles | Cybersecurity (100%), Engineer (96.4%), Logistics (95.0%) |
| Latency breakdowns per profile | 0.50–0.58 s p50 across profiles |
| Summary reference | `logs/tunelogs/online_summary.json` (from `autotune_runs.zip` → `20260307_145136/online/full/tk6_ms08_mt1024/scored/summary.json`) |

## Reference artifacts

- `D:/HybridRAG3/logs/tunelogs/autotune_runs.zip` contains all leaderboards, configs, and scored CSV/JSONL files (both modes).  
- The zipped results also include `run_summary.json` files per candidate; check `20260306_235420/offline/full/.../eval/run_summary.json` for per-question stats.  
- `logs/tunelogs/autotune_runs.zip` → `online/full/.../candidate_config.json` holds the source config used for each run.  
- Store this cheat sheet in any GUI `refs`/“hardcode” section so the interface can point operators back to these values when tuning or troubleshooting.

## Keeping the override clean

- Run `python tools/sync_mode_overrides.py --api-endpoint <your endpoint> --api-model <model>` after you change the Admin panel knobs. It writes both offline and online sections into `config/config.yaml`, mirroring the same controls so the “Default” checkbox just reloads the values you previously saved (and includes the tune date 2026-03-07 for reference).
- The file now records the tuned winners (offline `tk4_ms10_np384`, online `tk6_ms08_mt1024`) under `tuned_baseline` so future developers know how recent the defaults are without having to hunt the logs.

## Recommended Settings by Query Type (Online gpt-4o)

Results from controlled sweet-spot experiment (2026-03-14): 5 synthetic source
documents with verifiable ground truth, 14 queries across 6 categories, 8
setting configs swept, 112 API calls, $0.52 total.

### Quick Reference Table

| Query Type | Best Config | Bias | Open Knowledge | Temp | Score |
|---|---|---|---|---|---|
| Fact extraction ("What is the MTBF for HR-7741?") | STRICT-9 | 9 | OFF | 0.03 | 100% |
| Cross-doc synthesis ("Correlate compliance and uptime") | Any 7+ | 7-10 | either | 0.03-0.15 | 100% |
| Reasoning / inference ("Which site is most at risk?") | STRICT-9 or BALANCED-6 | 6-9 | OFF or ON | 0.03-0.15 | 100% |
| Trend analysis ("Rank all sites best to worst") | BALANCED-6 | 6 | ON | 0.15 | 65% |
| Creative / executive summary | BALANCED-6 | 6 | ON | 0.15 | 100% |
| Unanswerable / hallucination guard | STRICT-9 | 9 | OFF | 0.03 | 100% |

### Two Profiles for Two Use Cases

**Production queries (accuracy-first, zero hallucination tolerance):**

```yaml
# STRICT-9 -- 91.1% overall, 100% fact + refusal accuracy
query:
  grounding_bias: 9
  allow_open_knowledge: false
api:
  temperature: 0.03
retrieval:
  top_k: 10
```

Use when: answering user questions in real time, compliance queries, anything
where a wrong answer is worse than no answer.

**Report generation (synthesis-first, human-reviewed output):**

```yaml
# BALANCED-6 -- 87.9% overall, 100% creative + synthesis
query:
  grounding_bias: 6
  allow_open_knowledge: true
api:
  temperature: 0.15
retrieval:
  top_k: 10
```

Use when: generating Excel/PPT reports, failure analysis, site rankings,
executive summaries -- any output a human will review before use.

### Key Tradeoff

| Setting | Accuracy | Creativity | Hallucination Risk |
|---|---|---|---|
| STRICT-9 (bias=9, open=OFF) | Best | Sometimes refuses broad queries | None observed |
| BALANCED-6 (bias=6, open=ON) | Good | Always attempts answers | Moderate (may invent data for nonexistent items) |

### Experiment Artifacts

- Full results: `logs/grounding_experiment/*_sweet_spot_results.json`
- Test tool: `tools/grounding_sweet_spot_experiment.py`
- Stress test tool: `tools/grounding_knob_stress_test.py`

## Next steps

1. Apply these winners with `python tools/run_mode_autotune.py --workflow full --mode offline --apply-winner` and the matching `--mode online` so the repo defaults match the cheat sheet.  
2. Log the pass/latency/cost details along with the cheat-sheet reference path in `primary_to_secondary.md` and the sprint tracker so future sessions can cite the exact values.  
3. When query-side tuning begins, compare new candidates back to this sheet (especially ambiguous/injection stats) to measure improvements.
