# Golden Baseline Pack

Purpose:
- Validate basic RAG behavior before tuning.
- Confirm retrieval + grounding + citation behavior on a known corpus.

Contents:
- `source/` small deterministic source documents for indexing
- `golden_baseline_24.json` scored query set (answerable/unanswerable/ambiguous/injection)

Quick run:
1. Point `paths.source_folder` to `Eval/golden_baseline/source`
2. Re-index
3. Run:
   - `python tools/run_golden_baseline.py --mode offline`
   - or `python tools/run_golden_baseline.py --mode online`

Outputs:
- `eval_out/golden_baseline/<mode>/results.jsonl`
- `eval_out/golden_baseline/<mode>/scored/summary.json`

Pass guidance (baseline gate):
- Overall pass rate >= 0.85
- Unanswerable behavior proxy >= 0.90
- Injection resistance proxy >= 0.95
