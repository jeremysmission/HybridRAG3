# HybridRAG3 Freeze-Safe Handover + Sprint Plan

## Date
- 2026-03-02

## Immediate Goal
- Stabilize downloader for multi-day 24/7 transfers.
- Improve online/offline query quality with controllable grounding behavior.

## What Was Just Added
- Query panel now has `Grounding Bias (1-10)`:
  - `1`: guard OFF (development troubleshooting only)
  - `2-5`: relaxed guard (`flag` mode)
  - `6-10`: stricter guard (`block` mode)
- The slider updates live guard settings at runtime (no restart needed):
  - guard enable/disable
  - guard threshold
  - retrieval gate min chunks
  - retrieval min score floor

## Work In Progress
- Downloader stop/resume hardening:
  - source reachability probe before start
  - auto-resume attempt cap
  - stop watchdog timeout to prevent UI deadlock

## Priority Sprint Plan
1. Downloader Reliability (P0)
- Reproduce `Resuming transfer from saved state...` loop and `Stopping after current file...` hang.
- Validate fixed behavior with cross-drive smoke copy and interrupted-run resume.
- Add explicit UI status lines for:
  - resumed run id
  - stop acknowledged timestamp
  - reason of last skip/error from manifest

2. Query Quality + Grounding Tuning (P0)
- Run same prompt set at bias 3, 6, 8, 10.
- Capture refusal rate, completeness, and source faithfulness.
- Pick demo default (likely 5-7 for balanced behavior).

3. Parser Coverage + Skip Visibility (P1)
- Build parser coverage test corpus (PDF scanned, PPTX, XLSX, CSV, images/OCR samples).
- Improve `skipped` telemetry language with reason counts in GUI.

4. Role-Specific Tuning (P1)
- Use role golden sets and matrix runner:
  - `python .\tools\build_role_golden_sets.py --dataset .\Eval\golden_tuning_400.json`
  - `python .\tools\run_role_tuning_matrix.py --mode offline`
  - `python .\tools\run_role_tuning_matrix.py --mode online`

## Freeze Recovery Checklist
1. Re-open repo and run:
- `git status --short`
- `python -m compileall src\gui\panels\query_panel.py src\gui\panels\data_panel.py src\core\query_engine.py src\core\hallucination_guard\prompt_hardener.py`
2. Launch GUI and verify:
- Query panel shows grounding slider (1-10).
- Bias change updates hint text.
- Ask query at bias 1 and bias 8 to confirm behavior difference.
3. Downloader sanity:
- Start transfer (small cross-drive folder).
- Stop transfer.
- Confirm Start button re-enables and status exits stop loop.

## Acceptance Criteria (Current Sprint)
- No infinite resume loop on startup.
- Stop button always returns UI to usable state within ~60s.
- Query panel can switch grounding strictness live (1-10) and behavior changes are observable.
- No compile errors in patched files.

## Notes
- Bias `1` is intentionally unsafe for production demos and should be considered development-only.
- Keep production defaults source-grounded (recommended bias 6-8).
