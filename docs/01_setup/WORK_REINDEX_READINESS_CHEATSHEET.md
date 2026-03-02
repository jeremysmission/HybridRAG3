# Work Re-Index Readiness Cheat Sheet
## Date: 2026-03-02
## Purpose
Quick preflight before large indexing runs on work laptop/workstation.

---

## 1) Python Parser Dependencies
Run:

```powershell
python - <<'PY'
mods = ["olefile","ezdxf","Evtx","oxmsg","dpkt","psd_tools","striprtf","stl","vsdx","pdf2image","pytesseract","PIL"]
import importlib.util
for m in mods:
    print(f"{m:14} {'OK' if importlib.util.find_spec(m) else 'MISSING'}")
PY
```

Pass condition:
- All modules show `OK`.

If fail:
- Install missing packages in active `.venv` and re-run check.

---

## 2) OCR Binary Toolchain
Run:

```powershell
tesseract --version
pdfinfo -v
```

Pass condition:
- Both commands print version output.

If fail:
- OCR-heavy scans/PDFs will produce high `"no text extracted"` skip rates.
- Install Tesseract and Poppler utilities on that machine.

---

## 3) Active Extension Allowlist
Run:

```powershell
python - <<'PY'
from src.core.config import load_config
c = load_config(".")
exts = set(c.indexing.supported_extensions)
for e in [".msg",".mbox",".dxf",".vsdx",".evtx",".pcap",".accdb",".mdb",".psd",".rtf",".doc"]:
    print(e, "OK" if e in exts else "MISSING")
print("total_exts:", len(exts))
PY
```

Pass condition:
- All listed extensions show `OK`.
- `total_exts` is not suspiciously low.

Whitelist note:
- The indexer whitelist is `config.indexing.supported_extensions`.
- CI guard enforces sync with parser registry (`src/parsers/registry.py`), so
  update both only through parser registration + config sync checks.

---

## 4) CI Drift Guard
Run:

```powershell
python -m pytest tests/test_indexing_allowlist_sync.py -q
```

Pass condition:
- `2 passed` (or equivalent passing status).

If fail:
- Config allowlist drifted from parser registry.
- Fix `IndexingConfig.supported_extensions` to match `src/parsers/registry.py`.

---

## 5) Spot-Probe Real Skipped Files
Run against real skipped files from your ingest set:

```powershell
rag-diag --test-parse "FULL\PATH\TO\FILE.pdf" --verbose
rag-diag --test-parse "FULL\PATH\TO\FILE.dxf" --verbose
rag-diag --test-parse "FULL\PATH\TO\FILE.msg" --verbose
```

Use this to classify root cause:
- OCR dependency/toolchain issue
- parser dependency issue
- genuinely image-only/metadata-only content
- unsupported/corrupt file

---

## 6) Recommended Runtime OCR Settings (Scanned Docs)
Set before indexing (PowerShell session):

```powershell
$env:HYBRIDRAG_OCR_DPI = "300"
$env:HYBRIDRAG_OCR_TIMEOUT_S = "30"
$env:HYBRIDRAG_OCR_MAX_PAGES = "5"
$env:HYBRIDRAG_OCR_LANG = "eng"
```

Notes:
- Raise `MAX_PAGES` if many multi-page scans contain useful text beyond page 5.
- Higher DPI improves OCR but increases runtime.

---

## 7) Go / No-Go
Go when:
- Parser deps all `OK`
- OCR binaries available
- Allowlist sync test passes
- Spot probes return expected text on representative files

No-Go when:
- Any parser deps missing
- OCR binaries missing
- Allowlist drift detected
- Spot probes show systemic empty output on supported files

---

## 8) Safe Full Regression (Temp-Lock Resistant)
Run:

```powershell
python tools/run_regression_safe.py
```

Why:
- Uses a unique workspace temp base each run (`output/pytest_tmp_run_*`).
- Avoids `%TEMP%` lock collisions that can break large pytest suites.

---

## 9) New Skip Telemetry (Use This During Long Runs)
`Indexer.index_folder(...)` now returns two diagnostic maps:
- `skip_reason_counts`
- `skip_extension_counts`

Quick example:

```powershell
python - <<'PY'
from src.core.indexer import Indexer
from src.core.config import load_config
from src.core.vector_store import VectorStore
from src.core.embedder import Embedder
from src.core.chunker import Chunker, ChunkerConfig

cfg = load_config(".")
vs = VectorStore(cfg.paths.vector_db)
emb = Embedder(model=cfg.embedding.model_name, base_url=cfg.ollama.base_url, dimension=cfg.embedding.dimension)
chk = Chunker(ChunkerConfig(chunk_size=cfg.chunking.chunk_size, overlap=cfg.chunking.overlap))

idx = Indexer(cfg, vs, emb, chk)
res = idx.index_folder(cfg.paths.source_dir)
print("Top reasons:", list(res.get("skip_reason_counts", {}).items())[:10])
print("Top skipped extensions:", list(res.get("skip_extension_counts", {}).items())[:10])
idx.close()
PY
```

Interpretation:
- If one extension dominates `skip_extension_counts`, parser/deps/format quality is the likely issue.
- If one reason dominates `skip_reason_counts`, tune that specific root cause first.
