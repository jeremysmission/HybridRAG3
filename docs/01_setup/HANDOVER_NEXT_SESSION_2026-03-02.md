# Handover -- Resume Next Session
## Date: 2026-03-02

## What Was Updated
- OCR tooling + install docs:
  - `requirements_approved.txt` (added `ocrmypdf==16.10.4` as pending approval/validation)
  - `docs/01_setup/INSTALL_AND_SETUP.md`
  - `docs/01_setup/MANUAL_INSTALL.md`
- Setup scripts:
  - `tools/setup_home.ps1`
  - `tools/setup_work.ps1`
- OCR diversion system REMOVED (replaced by index report):
  - `src/core/index_report.py` -- writes consolidated data sheet to `logs/`
  - Review `logs/index_report_*.txt` after each run

## Important Note
- `pytesseract` and `ocrmypdf` are pip packages.
- The Tesseract engine itself is a separate system install (not pip).

## Reinstall Checklist (Work Machine)
1. Pull latest repo updates.
2. Run installer (`INSTALL.bat`) and choose Work/Educational flow.
3. Confirm source folder exists after setup.
4. Verify OCR stack:
   - `tesseract --version`
   - `pdfinfo -v`
5. Run:
   - `rag-diag`
   - `python -m pytest tests/test_parser_coverage_guard.py -q`

## Operational Flow
1. Index primary source.
2. Review `logs/index_report_*.txt` for skip reasons, OCR failures, and tuning hints.
3. Fix high-value scans (OCRmyPDF, rescans, cleanup).
4. Re-index after fixes.

```powershell
$env:HYBRIDRAG_OCR_DPI="300"
$env:HYBRIDRAG_OCR_TIMEOUT_S="45"
$env:HYBRIDRAG_OCR_MAX_PAGES="20"
$env:HYBRIDRAG_OCR_LANG="eng"
```

## New To-Do (Added 2026-03-03) -- Demo Stability + Profile Tuning

Goal: maximize demo quality without triggering workstation instability.

1. Build a single "Demo Impact Settings Guide" doc:
   - What each setting changes in demo behavior:
     - `ollama.model`
     - `ollama.context_window`
     - `ollama.timeout_seconds`
     - `retrieval.top_k`
     - `retrieval.min_score`
     - `retrieval.hybrid_search`
   - For each setting include:
     - visible demo impact
     - stability/latency tradeoff
     - safe range for workstation
2. Create per-profile demo question pack:
   - one "quick win" question per profile
   - one "stress" question per profile
   - one "citation confidence" question per profile
3. Define workstation safe-zone operations policy:
   - no indexing during live demos
   - no bulk downloading/transfers during live demos
   - pin `phi4-mini` + `context_window: 4096` for live reliability baseline
4. Run overnight autonomous tuning/eval data collection:
   - Role matrix:
     - `python tools/run_role_tuning_matrix.py --mode offline`
   - Baseline benchmark:
     - `python tools/query_benchmark.py`
   - GUI demo reliability smoke:
     - `python tools/gui_demo_smoke.py`
   - Capture artifacts:
     - `eval_out/role_tuning/*`
     - `logs/query_benchmark_*.json`
     - `output/gui_demo_smoke_report.json`
5. Next-session decision gate:
   - pick default demo profile using evidence:
     - no 500/timeouts
     - acceptable p95 latency
     - best answer quality on profile question pack
