# Parser Coverage Gap Analysis -- Critical Finding
## Date: 2026-03-01
## Severity: HIGH -- Root cause of massive indexing skip rates
## Discovered by: Claude CLI + Codex (independent parallel analysis)

---

## Executive Summary

Three independent failure layers were silently preventing file indexing across all
domains (engineering, logistics, PM, sys admin, cybersecurity). Each layer alone
would cause files to be skipped. All three active simultaneously meant broad
categories of files were completely invisible to the RAG system.

**Impact**: Estimated 30-60% of source files never indexed despite having parsers
written for them.

---

## The Three-Layer Failure

### Layer 1: Indexer Extension Allowlist Too Narrow (config.py:394)

The indexer has a hardcoded allowlist of supported extensions. Files not on this
list are **rejected before the parser is ever called** (indexer.py:266).

**Before (only 24 extensions):**
```python
[".txt", ".md", ".csv", ".json", ".xml", ".log",
 ".pdf", ".docx", ".pptx", ".xlsx", ".eml",
 ".html", ".htm",
 ".yaml", ".yml", ".ini",
 ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"]
```

**Missing (35+ extensions with working parsers):**
- Documents: .doc, .rtf, .ai
- Email: .msg, .mbox
- Text: .cfg, .conf, .properties, .reg
- Images: .wmf, .emf, .psd
- CAD: .dxf, .stp, .step, .ste, .igs, .iges, .stl
- Diagrams: .vsdx
- Cybersecurity: .evtx, .pcap, .pcapng, .cer, .crt, .pem
- Database: .accdb, .mdb
- Placeholder: .prt, .sldprt, .asm, .sldasm, .dwg, .dwt, .mpp, .vsd, .one, .ost, .eps

**After (63 extensions -- matches full parser registry):**
All registered extensions now included. See config.py supported_extensions.

**Root cause:** Parsers were built and tested individually (each parser has its own
unit tests), but nobody updated the config allowlist when new parsers were added.
The indexer and registry were developed independently without a cross-check.

**Fix applied:** config.py supported_extensions updated to include all 63 registered
extensions from registry.py.

---

### Layer 2: Parser Dependencies Not Installed

9 parser-specific Python packages were never added to requirements.txt or
requirements_approved.txt. The parsers import them with try/except, so missing deps
cause **silent empty text return** rather than crashes.

| Package | Version | License | Parser | File Types |
|---------|---------|---------|--------|------------|
| olefile | 0.47 | BSD | DocParser, MsgParser | .doc, .msg |
| ezdxf | 1.4.3 | MIT | DxfParser | .dxf |
| python-evtx | 0.8.1 | Apache 2.0 | EvtxParser | .evtx |
| python-oxmsg | 0.0.2 | MIT | MsgParser | .msg |
| dpkt | 1.9.8 | BSD | PcapParser | .pcap, .pcapng |
| psd-tools | 1.13.1 | MIT | PsdParser | .psd |
| striprtf | 0.0.29 | BSD-3 | RtfParser | .rtf |
| numpy-stl | 3.2.0 | BSD | StlParser | .stl |
| vsdx | 0.6.1 | BSD-3 | VsdxParser | .vsdx |

**All licenses are permissive (MIT/BSD/Apache). No GPL. No China-origin.**

**Root cause:** Parsers were designed for graceful degradation (no crash on missing
deps). This is good for resilience but meant missing deps were invisible -- no error
message, no crash, just "no text extracted" in telemetry.

**Fix applied:** All 9 packages + 8 transitive deps added to requirements.txt and
requirements_approved.txt with YELLOW status (applying for waiver approval).

---

### Layer 3: OCR System Binaries Not Installed on Work Laptop

The OCR pipeline requires two system-level binaries that are NOT pip-installable:

| Binary | Purpose | License | Status |
|--------|---------|---------|--------|
| Tesseract OCR 5.x | OCR engine (reads images to text) | Apache 2.0 | APPLYING via software store |
| Poppler (pdftoppm) | PDF page to image converter | GPL-2.0 | APPLYING via software store |

**Python wrappers** (pytesseract, pdf2image) were in requirements but the binaries
they call were not installed on the work laptop. Home PC has both via Tesseract
installer and scoop.

**Impact:** Every scanned PDF, image-heavy drawing, and scan-to-PDF document
silently returned empty text. The OCR fallback at pdf_parser.py:297 returned
`OCR_DEPS_MISSING` status and empty string.

**Fix:** Software store request submitted for both. Environment variables available
as fallback if PATH doesn't find them:
- `HYBRIDRAG_TESSERACT_CMD=/path/to/tesseract.exe`
- `HYBRIDRAG_POPPLER_BIN=/path/to/poppler/bin/`

---

## Domain Impact Assessment

| Domain | Affected File Types | Layers Hit | Estimated Impact |
|--------|-------------------|------------|-----------------|
| **Engineering** | .dxf, .stl, .stp, .igs, .dwg*, .prt*, .vsdx, scanned PDFs | All 3 | Very High |
| **Logistics** | .doc, .msg, .rtf, scanned BOLs/manifests (PDF) | Layers 1+2+3 | High |
| **Program Mgmt** | .doc, .msg, .vsdx, .mpp*, .rtf | Layers 1+2 | High |
| **Sys Admin** | .evtx, .reg, .cfg, .conf | Layers 1+2 | Medium |
| **Cybersecurity** | .evtx, .pcap, .pcapng, .cer, .crt, .pem | Layers 1+2 | High |

*Placeholder parsers (metadata only) -- still affected by Layer 1 (not in allowlist)

---

## How This Was Missed

1. **Parsers tested in isolation**: Each parser has its own unit test that imports
   the dep directly. Unit tests pass because they test the parser, not the indexer's
   extension filter.

2. **Graceful degradation hid failures**: try/except on imports meant no crash, no
   error log, just empty text. The system appeared to work.

3. **Config and registry developed independently**: The parser registry (registry.py)
   knows about 63 extensions. The config allowlist (config.py) only had 24. No
   cross-validation between them.

4. **Integration testing gap**: No test verifies "file with extension X actually
   produces indexed chunks end-to-end." Tests check parsing, tests check indexing,
   but no test checks the full chain from config allowlist through parser selection
   through dep availability through text extraction.

5. **Requirements files maintained manually**: Parser devs added parsers but not
   their pip dependencies to requirements.txt. The waiver process creates overhead
   that discourages adding "optional" packages.

---

## Fixes Applied (2026-03-01)

| Fix | File | Status |
|-----|------|--------|
| Extension allowlist expanded to 63 | src/core/config.py:394 | DONE |
| 9 parser deps added to requirements.txt | requirements.txt | DONE |
| 9 parser deps added to requirements_approved.txt | requirements_approved.txt | DONE (YELLOW) |
| Tesseract + Poppler binary entries added | requirements_approved.txt | APPLYING |
| All deps installed in home venv | .venv/ | DONE |

---

## Remaining Action Items

| Item | Priority | Status |
|------|----------|--------|
| Install 9 parser deps on work laptop venv | HIGH | Pending (pip install) |
| Install Tesseract binary on work laptop | HIGH | Pending (software store) |
| Install Poppler binary on work laptop | HIGH | Pending (software store) |
| Re-index source data after fixes | HIGH | Pending |
| Add integration test: extension -> parser -> chunks | MEDIUM | Open |
| Add registry/config cross-validation check | MEDIUM | Open |
| Submit waiver for 9 new packages | MEDIUM | In progress |

---

## Test Data Resources for Parser Stress Testing

### OCR / Scanned Document Benchmarks
- [olmOCR-bench](https://huggingface.co/datasets/allenai/olmOCR-bench) -- 1,403 PDFs (arXiv, tables, old scans)
- [OmniDocBench](https://github.com/opendatalab/OmniDocBench) -- 9 document types, 200 DPI scans
- [DocLayNet](https://github.com/DS4SD/DocLayNet) -- Finance, law, manuals, tenders
- [RVL-CDIP](https://adamharley.com/rvl-cdip/) -- 400k scanned business documents
- [FUNSD](https://github.com/crcresearch/FUNSD) -- Noisy scanned forms

### Engineering / CAD
- [Autodesk Sample Files](https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/6XGQklp3ZcBFqljLPjrnQ9.html)
- [FileSamplesHub DWG](https://www.filesampleshub.com/format/image/dwg)
- [AxiomCpl Structural Details](https://www.axiomcpl.com/samples.php)

### Cybersecurity
- [Wireshark Sample Captures](https://wiki.wireshark.org/samplecaptures) -- .pcap/.pcapng
- [NIST CFReDS](https://www.nist.gov/itl/ssd/software-quality-group/computer-forensics-tool-testing-program-cftt/cfreds)
