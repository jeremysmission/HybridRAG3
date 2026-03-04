# Clean Rebuild Checklist (Enterprise Repo)

Last Updated: 2026-03-03

Use this for a clean reinstall on the work machine after pulling latest Educational repo updates.

---

## 1) Get Fresh Code

1. Download latest ZIP of `HybridRAG3_Educational` on work machine.
2. Extract to a clean folder, e.g. `D:\HybridRAG3`.
3. Do not reuse old `.venv` from previous installs.

---

## 2) Clean Old Environment (if reusing same folder)

```powershell
cd D:\HybridRAG3
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
```

---

## 3) Run Installer

From Explorer: double-click `INSTALL.bat`

Or PowerShell:

```powershell
cd D:\HybridRAG3
.\INSTALL.bat
```

Expected branch:
- `Enterprise / Educational repository`
- Uses `requirements_approved.txt`

---

## 4) Verify Core Runtime

Open PowerShell in repo root:

```powershell
cd D:\HybridRAG3
.\.venv\Scripts\Activate.ps1
python --version
pip --version
```

---

## 5) Verify OCR Stack

```powershell
python -c "import pytesseract, pdf2image, PIL; print('ocr wrappers ok')"
tesseract --version
pdfinfo -v
```

Notes:
- `pytesseract` is Python wrapper.
- Tesseract/Poppler are system binaries.

---

## 6) Run Required Diagnostics

```powershell
rag-diag
pytest tests/test_indexing_allowlist_sync.py -q
pytest tests/test_parser_coverage_guard.py -q
```

If full regression is needed:

```powershell
pytest tests -q --ignore=tests/test_fastapi_server.py
```

---

## 7) Verify Indexing Behavior Before Full Corpus

1. Index a small mixed sample set first.
2. Confirm skip-reason output shows specific reasons (not opaque failures).
3. Review `logs/index_report_*.txt` for skip reasons and OCR failures.

---

## 8) Rebuild Complete Criteria

Mark complete only if all are true:

- Installer completed with no fatal errors.
- `rag-diag` passes critical checks.
- Parser guard tests pass.
- OCR wrappers import and binaries respond.
- Small pilot indexing run behaves as expected.

---

## 9) If Something Fails

Capture and keep:

- Full terminal output
- `rag-diag` output
- Failing pytest output
- 5 sample file paths that reproduce issue

Then troubleshoot from:
- `docs/01_setup/INSTALL_AND_SETUP.md`
- `docs/01_setup/MANUAL_INSTALL.md`
- `docs/01_setup/WORK_REINDEX_READINESS_CHEATSHEET.md`
