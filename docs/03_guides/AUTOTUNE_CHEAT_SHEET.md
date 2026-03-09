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

## Next steps

1. Apply these winners with `python tools/run_mode_autotune.py --workflow full --mode offline --apply-winner` and the matching `--mode online` so the repo defaults match the cheat sheet.  
2. Log the pass/latency/cost details along with the cheat-sheet reference path in `primary_to_secondary.md` and the sprint tracker so future sessions can cite the exact values.  
3. When query-side tuning begins, compare new candidates back to this sheet (especially ambiguous/injection stats) to measure improvements.
