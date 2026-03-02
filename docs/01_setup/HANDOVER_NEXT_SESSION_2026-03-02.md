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
