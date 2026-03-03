# Handover -- Resume Next Session
## Date: 2026-03-02

## What Was Updated
- OCR diversion process doc:
  - `docs/01_setup/OCR_DIVERSION_PROCESS_FLOW_CHEATSHEET.md`
- OCR tooling + install docs:
  - `requirements_approved.txt` (added `ocrmypdf==16.10.4` as pending approval/validation)
  - `docs/01_setup/INSTALL_AND_SETUP.md`
  - `docs/01_setup/MANUAL_INSTALL.md`
- Setup scripts now create OCR diversion folder and write it into config:
  - `tools/setup_home.ps1`
  - `tools/setup_work.ps1`
- New OCR routing tool:
  - `tools/route_ocr_dependent_files.py`
- Config defaults include OCR diversion folder:
  - `config/default_config.yaml`
  - `src/core/config.py`

## Important Note
- `pytesseract` and `ocrmypdf` are pip packages.
- The Tesseract engine itself is a separate system install (not pip).

## Reinstall Checklist (Work Machine)
1. Pull latest repo updates.
2. Run installer (`INSTALL.bat`) and choose Work/Educational flow.
3. Confirm these paths exist after setup:
   - source folder
   - source `\\_ocr_diversions`
4. Verify OCR stack:
   - `tesseract --version`
   - `pdfinfo -v`
5. Run:
   - `rag-diag`
   - `python -m pytest tests/test_parser_coverage_guard.py -q`

## Operational Flow
1. Index primary source.
2. Review top skip reasons/extensions.
3. Triage `_ocr_diversions`.
4. OCR-fix high-value scans (OCRmyPDF, rescans, cleanup).
5. Move fixed files back and re-index.

## Quick Commands
```powershell
python tools/route_ocr_dependent_files.py --source "D:\RAG Source Data" --queue-output "D:\RAG Source Data\_ocr_diversions" --mode move --pdf-min-native-chars 40 --pdf-probe-pages 3
```

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
