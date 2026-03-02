# Bundle Build and Dependency Install (Numbered)
Last Updated: 2026-03-02

Use this as the single end-to-end checklist for:
- Python parser dependencies
- OCR binaries
- Offline bundle build
- Post-build verification

---

## 1. Open Terminal and Activate Venv
```powershell
cd D:\HybridRAG3
.\.venv\Scripts\Activate.ps1
```

## 2. Use Approved Download Sources
- Python packages: `https://pypi.org` and `https://files.pythonhosted.org`
- Tesseract OCR (Windows): official Tesseract/UB Mannheim releases
- Poppler tools (`pdfinfo`): official Poppler Windows releases

## 3. Install Core Python Requirements
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

## 4. Install Parser/OCR Python Packages Explicitly (if needed)
```powershell
pip install olefile ezdxf python-evtx python-oxmsg dpkt psd-tools striprtf numpy-stl vsdx pdf2image pytesseract pillow pdfplumber --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

## 5. Verify Python Parser/OCR Modules
```powershell
python - <<'PY'
mods=["olefile","ezdxf","Evtx","oxmsg","dpkt","psd_tools","striprtf","stl","vsdx","pdf2image","pytesseract","PIL","pdfplumber"]
import importlib.util
missing=[]
for m in mods:
    ok=importlib.util.find_spec(m) is not None
    print(f"{m:14} {'OK' if ok else 'MISSING'}")
    if not ok:
        missing.append(m)
print("MISSING_COUNT:", len(missing))
PY
```

Pass condition:
- `MISSING_COUNT: 0`

## 6. Verify OCR Binaries
```powershell
tesseract --version
pdfinfo -v
```

Pass condition:
- Both commands return version output.

## 7. Verify Allowlist/Registry Drift Guard
```powershell
python -m pytest tests/test_indexing_allowlist_sync.py -q --basetemp output/pytest_tmp_check
```

Pass condition:
- Test suite passes.

## 8. Build Offline Bundle (Standard)
```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_usb_deploy_bundle.ps1 -DownloadWheels
```

## 9. Build Offline Bundle (With Ollama Models)
```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_usb_deploy_bundle.ps1 -DownloadWheels -IncludeOllamaModels
```

## 10. Verify Bundle Output Exists
Confirm generated root includes:
- `HybridRAG3\`
- `scripts\`
- `INSTALL.bat`
- `MANIFEST.txt`
- `MANIFEST_SHA256.txt`
- optional: `wheels\`, `cache\`, `installers\`

## 11. Prestage to Target Machine
Copy all media contents into one folder, example:
- `D:\HybridRAG3_PRESTAGE`

Then run:
```cmd
D:\HybridRAG3_PRESTAGE\INSTALL.bat
```

## 12. Post-Install Smoke Test
```powershell
cd D:\HybridRAG3
.\.venv\Scripts\Activate.ps1
. .\start_hybridrag.ps1
rag-diag
```

Optional parser spot-probes:
```powershell
rag-diag --test-parse "FULL\PATH\TO\FILE.pdf" --verbose
rag-diag --test-parse "FULL\PATH\TO\FILE.dxf" --verbose
rag-diag --test-parse "FULL\PATH\TO\FILE.msg" --verbose
```

