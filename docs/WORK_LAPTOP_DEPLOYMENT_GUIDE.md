# HybridRAG3 -- Work Laptop Deployment Guide
# ============================================================================
# DATE: 2026-02-20
# PURPOSE: Step-by-step guide for deploying HybridRAG3 (with expanded
#          parsing) to the work laptop, including corporate software
#          store approval tracking.
#
# NON-PROGRAMMER NOTE:
#   This guide assumes you are deploying to a corporate Windows laptop
#   where software installation may be restricted. Some tools need
#   corporate software store approval. This guide tracks what is
#   approved, what needs approval, and what alternatives exist.
# ============================================================================


## TABLE OF CONTENTS

1. [Pre-Flight Checklist](#1-pre-flight-checklist)
2. [Step 1: Sync to Educational Repo](#2-step-1-sync-to-educational-repo)
3. [Step 2: Download on Work Laptop](#3-step-2-download-on-work-laptop)
4. [Step 3: Python Environment Setup](#4-step-3-python-environment-setup)
5. [Step 4: Install Core Dependencies](#5-step-4-install-core-dependencies)
6. [Step 5: Install Expanded Parser Dependencies](#6-step-5-install-expanded-parser-dependencies)
7. [Step 6: Install External Tools](#7-step-6-install-external-tools)
8. [Step 7: Validate Installation](#8-step-7-validate-installation)
9. [Step 8: Ollama Model Setup](#9-step-8-ollama-model-setup)
10. [Corporate Software Audit Tracker](#10-corporate-software-audit-tracker)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. PRE-FLIGHT CHECKLIST

Before starting, confirm these on the work laptop:

- [ ] Python 3.11 installed (check: `py -3.11 --version`)
- [ ] pip accessible (check: `py -3.11 -m pip --version`)
- [ ] PyPI reachable (check: `py -3.11 -m pip install --dry-run requests`)
- [ ] D: drive available with write access
- [ ] Browser can reach github.com (for zip download)
- [ ] Ollama installed (check: `ollama --version`) -- if not, see Step 6

If PyPI is blocked by corporate firewall, you will need the offline
wheel bundle method. See Section 11 (Troubleshooting).

---

## 2. STEP 1: SYNC TO EDUCATIONAL REPO (Home PC)

Run these commands on your HOME PC (never git from work laptop).

```powershell
# 1. Make sure HybridRAG3 is up to date
cd D:\HybridRAG3
git status
# Should show: "Your branch is up to date with 'origin/main'"

# 2. Run the sync script to sanitize and copy to Educational
python tools\sync_to_educational.py

# 3. Review the sync output for any warnings or banned words
# If clean, commit and push the Educational repo:
cd D:\HybridRAG3_Educational
git add -A
git status
# Review staged files -- make sure no HANDOVER, no secrets
git commit -m "Sync: expanded parsing (14 new parsers, 63 extensions)"
git push origin main
```

### What gets synced:
- All 14 new parser files in src/parsers/
- Updated registry.py
- docs/FORMAT_SUPPORT.md
- tests/stress_test_expanded_parsers.py

### What does NOT sync (by design):
- HANDOVER docs (SKIP_PATTERNS)
- .venv, .model_cache, data/, logs/
- start_hybridrag.ps1 (machine-specific)
- API keys, credentials

---

## 3. STEP 2: DOWNLOAD ON WORK LAPTOP

On the WORK LAPTOP browser:

1. Go to: https://github.com/jeremysmission/HybridRAG3_Educational
2. Click the green **Code** button
3. Click **Download ZIP**
4. Save to `Downloads\HybridRAG3_Educational-main.zip`
5. Right-click the zip, select **Extract All**
6. Extract to `D:\` (creates `D:\HybridRAG3_Educational-main\`)
7. Rename the folder:

```powershell
# If D:\HybridRAG3 already exists, back it up first:
Rename-Item "D:\HybridRAG3" "D:\HybridRAG3_backup_$(Get-Date -Format yyyyMMdd)"

# Then rename the download:
Rename-Item "D:\HybridRAG3_Educational-main" "D:\HybridRAG3"
```

### IMPORTANT: Do NOT use `git clone` on the work laptop.
Download via browser only. No git credentials on the work machine.

---

## 4. STEP 3: PYTHON ENVIRONMENT SETUP

```powershell
cd D:\HybridRAG3

# Create virtual environment with Python 3.11
py -3.11 -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# Verify
python --version
# Should show: Python 3.11.x

# Upgrade pip
python -m pip install --upgrade pip
```

If `.venv\Scripts\Activate.ps1` fails due to execution policy:
```powershell
# Read the script content and execute it (bypasses policy)
$code = [IO.File]::ReadAllText("$pwd\.venv\Scripts\Activate.ps1")
Invoke-Expression $code
```

---

## 5. STEP 4: INSTALL CORE DEPENDENCIES

These are the original HybridRAG3 dependencies. Most are pure Python
packages available from PyPI.

```powershell
# Make sure venv is activated first
pip install -r requirements.txt
```

### If PyPI is blocked (corporate firewall):

Use the offline wheel bundle method:

```powershell
# ON HOME PC: build the wheel bundle
python tools\work_validation\build_wheels_bundle.py

# Transfer the resulting .zip to work laptop (USB, email, etc.)
# ON WORK LAPTOP:
pip install --no-index --find-links=path\to\wheels\ -r requirements.txt
```

### Verify core install:
```powershell
python -c "import pdfplumber, docx, pptx, openpyxl, PIL, yaml; print('[OK] Core deps installed')"
```

---

## 6. STEP 5: INSTALL EXPANDED PARSER DEPENDENCIES

These are the NEW dependencies added for expanded parsing. All use
permissive licenses (MIT, BSD, Apache). No GPL in production.

### Install command (if PyPI is reachable):

```powershell
pip install ezdxf numpy-stl striprtf olefile python-oxmsg psd-tools vsdx python-evtx dpkt access-parser
```

### If PyPI is blocked, install one at a time or use wheels:

```powershell
# On HOME PC, download wheels:
pip download ezdxf numpy-stl striprtf olefile python-oxmsg psd-tools vsdx python-evtx dpkt access-parser -d wheels_expanded\

# Zip and transfer to work laptop, then:
pip install --no-index --find-links=wheels_expanded\ ezdxf numpy-stl striprtf olefile python-oxmsg psd-tools vsdx python-evtx dpkt access-parser
```

### Verify expanded parser install:

```powershell
python -c "
libs = {
    'ezdxf': 'DXF parser',
    'stl': 'STL parser (numpy-stl)',
    'striprtf': 'RTF parser',
    'olefile': 'DOC/MSG fallback',
    'oxmsg': 'MSG parser (python-oxmsg)',
    'psd_tools': 'PSD parser',
    'vsdx': 'Visio parser',
    'Evtx': 'EVTX parser (python-evtx)',
    'dpkt': 'PCAP parser',
    'cryptography': 'Certificate parser',
    'access_parser': 'Access DB parser',
}
for mod, desc in libs.items():
    try:
        __import__(mod)
        print(f'[OK] {desc} ({mod})')
    except ImportError as e:
        print(f'[FAIL] {desc} ({mod}): {e}')
"
```

### What if some libraries fail to install?

That is OK. HybridRAG3 uses graceful degradation. If a library is
missing, the parser for that format returns an empty string with an
IMPORT_ERROR message. All other formats still work normally.

Priority order for installation (highest value first):
1. **ezdxf** -- DXF files from CAD team (most requested)
2. **olefile** -- .doc fallback (common legacy format)
3. **cryptography** -- already in requirements.txt (certificates)
4. **striprtf** -- RTF files (common in engineering)
5. **python-oxmsg** -- .msg files (Outlook emails)
6. **psd-tools** -- PSD files (design team)
7. **numpy-stl** -- STL files (3D printing)
8. **dpkt** -- packet captures (cybersecurity)
9. **python-evtx** -- Windows event logs (sysadmin)
10. **vsdx** -- Visio diagrams
11. **access-parser** -- Access databases

---

## 7. STEP 6: INSTALL EXTERNAL TOOLS

These are standalone programs (not pip packages) that some parsers need.
Each requires corporate software store approval or manual installation.

### 6A. Tesseract OCR (for image text extraction)

**What it does:** Reads text from images (.png, .jpg, .bmp, .gif, etc.)
**License:** Apache 2.0 (permissive, corporate-friendly)
**Corp approval:** LIKELY APPROVED -- widely used, backed by Google
**Status:** [ ] Approved  [ ] Pending  [ ] Denied

**Official download:**
  https://tesseract-ocr.github.io/tessdoc/Downloads.html
  (Windows installer maintained by UB Mannheim)

**Installation:**
1. Download the installer (.exe) from the link above
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR`)
3. Add to PATH or set environment variable:

```powershell
# Add Tesseract to PATH for current session
$env:PATH += ";C:\Program Files\Tesseract-OCR"

# Verify
tesseract --version
```

4. For permanent PATH, add via System Properties > Environment Variables

**If denied:** Image OCR will not work, but all other parsers still
function. Text-based formats (DXF, STEP, IGES, etc.) do not need OCR.

**Alternative if denied:** Azure AI Document Intelligence (cloud API)
can be used instead of local Tesseract. Requires Azure subscription.


### 6B. Ollama (for offline LLM inference)

**What it does:** Runs LLM models locally for offline RAG queries
**License:** MIT (permissive, corporate-friendly)
**Corp approval:** LIKELY APPROVED -- MIT license, no telemetry
**Status:** [ ] Approved  [ ] Pending  [ ] Denied

**Official download:**
  https://ollama.com/download/windows

**Installation:**
1. Download `OllamaSetup.exe` from the link above
2. Run the installer
3. Verify: `ollama --version`
4. Pull models (see Step 8)

**If denied:** HybridRAG3 falls back to Azure OpenAI API (online mode).
Offline mode requires Ollama. If Ollama is denied, use online-only
mode by setting `offline_mode: false` in config.

**Alternative if denied:** LM Studio (free, GUI-based) or vLLM
(Apache 2.0, production-grade). Both serve OpenAI-compatible APIs.


### 6C. ODA File Converter (for DWG -> DXF conversion)

**What it does:** Converts proprietary .dwg files to open .dxf format
**License:** Proprietary (free for non-commercial use)
**Corp approval:** NEEDS REVIEW -- free tier is non-commercial only
**Status:** [ ] Approved  [ ] Pending  [ ] Denied

**Official download:**
  https://www.opendesign.com/guestfiles/oda_file_converter

**IMPORTANT:** The free version is restricted to non-commercial use.
For production/commercial deployment, an ODA membership is required.
Check with legal/procurement before installing.

**If denied or not applicable:** DWG files will use the PlaceholderParser
(recognized by name/type but content not extracted). The CAD team can
export DWG to DXF from AutoCAD before ingestion -- DXF is fully supported.

**Alternative:** Ask CAD team to batch-export DWG to DXF from AutoCAD.
This is often the simplest approach regardless of ODA availability.


### 6D. Antiword (optional, for better .doc extraction)

**What it does:** Extracts text from legacy Word 97-2003 .doc files
**License:** GPL (copyleft -- problematic for corporate distribution)
**Corp approval:** UNLIKELY -- GPL license, legacy unmaintained tool
**Status:** [ ] Approved  [ ] Pending  [ ] Denied

**Source (if needed):**
  https://github.com/grobian/antiword

**If denied (expected):** The DocParser has TWO fallback strategies
that work without antiword: (1) olefile OLE2 extraction, (2) raw
binary text scanning. Quality is slightly lower than antiword but
still functional. No action needed if denied.

**Alternative:** Convert .doc to .docx using LibreOffice or Word
before ingestion. The .docx parser uses python-docx (MIT, no issues).


### 6E. Ghostscript (for EPS rendering -- NOT RECOMMENDED)

**What it does:** Renders PostScript/EPS files to raster images
**License:** AGPL-3.0 (viral license -- MAJOR corporate risk)
**Corp approval:** UNLIKELY -- AGPL requires source code disclosure
**Status:** [ ] Not pursuing  [ ] Applied anyway  [ ] Denied

**Official download (for reference only):**
  https://ghostscript.com/releases/gsdnld.html

**We do NOT recommend installing Ghostscript** due to AGPL licensing.
EPS files use the PlaceholderParser instead. If EPS content extraction
is critical, consider:
- Commercial Ghostscript license ($25,000/year from Artifex)
- Converting EPS to PDF using Adobe Illustrator before ingestion
- Using the .ai -> PDFParser route (modern .ai files contain PDF)

---

## 8. STEP 7: VALIDATE INSTALLATION

Run the expanded parser stress test to verify everything works:

```powershell
cd D:\HybridRAG3
python tests\stress_test_expanded_parsers.py
```

**Expected output:**
```
STRESS TEST SUMMARY
Total tests:  189
  PASS:       189
  FAIL:       0
  WARN:       0
  SKIP:       0
RESULT: ALL TESTS PASSED (no failures)
```

Parsers with missing dependencies will show "Graceful degradation:
IMPORT_ERROR" in the detail column -- this is PASS, not FAIL.

### Also run the regression suite:

```powershell
python tests\virtual_test_phase4_exhaustive.py
```

**Expected:** 163/163 PASS

### Quick registry check:

```powershell
python -c "
from src.parsers.registry import REGISTRY
full = REGISTRY.fully_supported_extensions()
ph = REGISTRY.placeholder_extensions()
print(f'Fully supported: {len(full)} extensions')
print(f'Placeholders:    {len(ph)} extensions')
print(f'Total:           {len(full) + len(ph)} extensions')
"
```

**Expected:** 52 fully supported, 11 placeholders, 63 total

---

## 9. STEP 8: OLLAMA MODEL SETUP

If Ollama is installed and approved, pull the work profile models:

```powershell
# Primary models (must-have)
ollama pull qwen3:8b            # 5.2 GB -- primary for eng, pm, draft, sys
ollama pull phi4:14b-q4_K_M     # 9.1 GB -- primary for logistics

# Alternative models (nice-to-have)
ollama pull deepseek-r1:8b      # 5.2 GB -- alt for eng, sys (reasoning)
ollama pull gemma3:4b           # 3.3 GB -- alt for pm (fast summarization)

# Total download: ~23 GB
# Verify:
ollama list
```

If download is slow on corporate network, pull one model at a time
during off-hours. The qwen3:8b model is the highest priority (covers
the most work profiles).

---

## 10. CORPORATE SOFTWARE AUDIT TRACKER

Use this table to track approval status for each piece of software.
Update as you submit requests and get responses.

### Python Packages (pip install)

| Package          | License    | Corp Likelihood | Status     | Notes |
|------------------|------------|-----------------|------------|-------|
| pdfplumber       | MIT        | APPROVED        | [ ] OK     | PDF text extraction |
| python-docx      | MIT        | APPROVED        | [ ] OK     | DOCX reading |
| python-pptx      | MIT        | APPROVED        | [ ] OK     | PPTX reading |
| openpyxl         | MIT        | APPROVED        | [ ] OK     | XLSX reading |
| beautifulsoup4   | MIT        | APPROVED        | [ ] OK     | HTML parsing |
| Pillow           | MIT        | APPROVED        | [ ] OK     | Image handling |
| pytesseract      | Apache 2.0 | APPROVED        | [ ] OK     | OCR bridge |
| PyYAML           | MIT        | APPROVED        | [ ] OK     | Config reading |
| requests         | Apache 2.0 | APPROVED        | [ ] OK     | HTTP client |
| sentence-transformers | Apache 2.0 | APPROVED  | [ ] OK     | Embeddings |
| torch            | BSD        | APPROVED        | [ ] OK     | ML framework |
| cryptography     | Apache/BSD | APPROVED        | [ ] OK     | Cert parsing (already in reqs) |
| ezdxf            | MIT        | APPROVED        | [ ] OK     | DXF/AutoCAD exchange parsing |
| numpy-stl        | BSD        | APPROVED        | [ ] OK     | STL 3D mesh parsing |
| striprtf         | BSD        | APPROVED        | [ ] OK     | RTF text extraction |
| olefile          | BSD        | APPROVED        | [ ] OK     | OLE2 file reading (.doc/.msg) |
| python-oxmsg     | MIT        | APPROVED        | [ ] OK     | Outlook .msg reading |
| psd-tools        | MIT        | APPROVED        | [ ] OK     | Photoshop PSD layers |
| vsdx             | BSD        | APPROVED        | [ ] OK     | Visio .vsdx reading |
| python-evtx      | Apache 2.0 | APPROVED        | [ ] OK     | Windows event log reading |
| dpkt             | BSD        | APPROVED        | [ ] OK     | Network capture parsing |
| access-parser    | Apache 2.0 | APPROVED        | [ ] OK     | Access DB reading |

> **All Python packages use MIT, BSD, or Apache licenses.** These are
> permissive open-source licenses that allow commercial use with no
> source disclosure requirements. Corporate legal typically pre-approves
> these license types. If your corp requires per-package approval, submit
> them as a batch -- they are all the same license class.

### Standalone Software (require installer)

| Software            | License       | Corp Likelihood     | Status     | Notes |
|---------------------|---------------|---------------------|------------|-------|
| Python 3.11         | PSF (permissive) | APPROVED         | [ ] OK     | Already installed |
| Tesseract OCR       | Apache 2.0    | LIKELY APPROVED     | [ ] Pending | Image OCR, Google-backed |
| Ollama              | MIT           | LIKELY APPROVED     | [ ] Pending | Local LLM, no telemetry |
| ODA File Converter  | Proprietary   | NEEDS LEGAL REVIEW  | [ ] Pending | Free=non-commercial only |
| Antiword            | GPL           | UNLIKELY            | [ ] Skip   | Fallbacks exist, not needed |
| Ghostscript         | AGPL          | NOT PURSUING        | [ ] Skip   | AGPL too risky, placeholder instead |

### Approval Decision Tree

```
Is it a pip package with MIT/BSD/Apache license?
  YES -> Install it. These are standard open-source packages.
         Corp legal pre-approves these license classes.
  NO  -> Is it Tesseract or Ollama?
           YES -> Submit to software store. Apache/MIT, widely used.
                  Mention: "Used by Google (Tesseract) / MIT license (Ollama)"
           NO  -> Is it ODA File Converter?
                    YES -> Check with legal. Free tier = non-commercial only.
                           Alternative: CAD team exports DWG to DXF manually.
                    NO  -> Is it Antiword or Ghostscript?
                             YES -> Skip. Fallbacks exist. GPL/AGPL not worth the risk.
```

### If You Need to Apply for Production-Level Approval

For software that needs formal approval (Tesseract, Ollama, ODA):

1. **Tesseract OCR** -- Frame as: "Industry-standard OCR engine, Apache 2.0
   license, originally developed by HP Labs, maintained by Google 2006-2017,
   currently maintained by University of Mannheim. Used by thousands of
   enterprises worldwide. No telemetry, no network access, processes files
   locally only."

2. **Ollama** -- Frame as: "Local AI inference engine, MIT license, runs
   LLM models entirely offline on the local machine. No data leaves the
   laptop. No cloud connection required. No telemetry. Used for document
   search and question-answering against local engineering documents."

3. **ODA File Converter** -- Frame as: "Batch conversion tool for AutoCAD
   DWG files. Converts proprietary DWG format to open DXF format for
   indexing. Free tier available for evaluation. If production use requires
   commercial license, alternative is to have CAD team export DWG to DXF
   from AutoCAD before ingestion."

---

## 11. TROUBLESHOOTING

### PyPI is blocked by corporate firewall

Build wheel bundles on home PC and transfer via USB:

```powershell
# ON HOME PC:
cd D:\HybridRAG3
pip download -r requirements.txt -d wheels_core\
pip download ezdxf numpy-stl striprtf olefile python-oxmsg psd-tools vsdx python-evtx dpkt access-parser -d wheels_expanded\

# Zip both folders, transfer to work laptop

# ON WORK LAPTOP:
pip install --no-index --find-links=wheels_core\ -r requirements.txt
pip install --no-index --find-links=wheels_expanded\ ezdxf numpy-stl striprtf olefile python-oxmsg psd-tools vsdx python-evtx dpkt access-parser
```

### Tesseract not found after install

```powershell
# Set the path explicitly
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"

# Or add to system PATH permanently via:
# System Properties > Advanced > Environment Variables > Path > Edit > New
# Add: C:\Program Files\Tesseract-OCR
```

### Ollama models download too slowly

Pull one model at a time during off-hours. Priority order:
1. qwen3:8b (covers most profiles)
2. phi4:14b-q4_K_M (logistics profile)
3. deepseek-r1:8b (if time allows)
4. gemma3:4b (smallest, fastest to download)

### Parser returns IMPORT_ERROR

This means the optional library is not installed. It is NOT a bug.
The parser gracefully degrades. Install the missing library:

```powershell
# Check which parser needs what
python -c "
from src.parsers.registry import REGISTRY
for ext in REGISTRY.supported_extensions():
    info = REGISTRY.get(ext)
    try:
        parser = info.parser_cls()
        text, details = parser.parse_with_details('nonexistent.tmp')
        if 'IMPORT_ERROR' in details.get('error', ''):
            print(f'{ext}: {details[\"error\"][:80]}')
    except:
        pass
"
```

### Registry shows fewer than 63 extensions

The registry always shows 63 extensions regardless of installed
libraries. The library check happens at parse time, not import time.
If you see fewer than 63, there may be an import error in registry.py
itself. Check:

```powershell
python -c "from src.parsers.registry import REGISTRY; print(f'{len(REGISTRY.supported_extensions())} extensions loaded')"
```

### OneDrive locks .git/objects

If the work laptop syncs the project folder via OneDrive, you may
see permission errors. Solution: exclude the project folder from
OneDrive sync, or do not use git on the work laptop (download via
browser zip only, as recommended).

### venv activation fails (execution policy)

```powershell
# Workaround for restricted execution policy
$code = [IO.File]::ReadAllText("D:\HybridRAG3\.venv\Scripts\Activate.ps1")
Invoke-Expression $code
```

---

## QUICK REFERENCE: WHAT WORKS WITHOUT EXTERNAL TOOLS

Even if Tesseract, Ollama, and ODA are all denied, HybridRAG3 still
indexes the following formats with ZERO external dependencies:

| Format Category        | Extensions                                     | Notes |
|------------------------|-------------------------------------------------|-------|
| Plain text (13 types)  | .txt .md .csv .json .xml .log .yaml .yml .ini .cfg .conf .properties .reg | Just reads the file |
| Office documents       | .docx .pptx .xlsx                               | pip packages only |
| Legacy documents       | .doc .rtf                                        | pip packages only |
| Email                  | .eml .mbox                                       | Python stdlib |
| HTML                   | .html .htm                                       | pip package only |
| CAD exchange           | .dxf .stp .step .ste .igs .iges                 | pip/text parsing |
| 3D mesh                | .stl                                             | pip package only |
| Outlook email          | .msg                                             | pip package only |
| Photoshop              | .psd                                             | pip package only |
| Visio diagrams         | .vsdx                                            | pip package only |
| Event logs             | .evtx                                            | pip package only |
| Network captures       | .pcap .pcapng                                    | pip package only |
| Certificates           | .cer .crt .pem                                   | pip package (already installed) |
| Access databases       | .accdb .mdb                                      | pip package only |
| Adobe Illustrator      | .ai                                              | Same as PDF parser |

**Only these need Tesseract:** .png .jpg .jpeg .tif .tiff .bmp .gif .webp .wmf .emf
**Only DWG->DXF needs ODA:** .dwg .dwt (or use placeholder)
**Only offline LLM needs Ollama:** Query engine inference (not parsing)

---

*Last updated: 2026-02-20*
