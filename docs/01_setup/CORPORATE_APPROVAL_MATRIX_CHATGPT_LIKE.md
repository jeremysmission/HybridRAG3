# Corporate Approval Matrix -- ChatGPT-Like Capability for HybridRAG3

Last Updated: 2026-03-02
Audience: Workstation/software approval reviewers, security, sysadmin, PM

---

## Goal

Use this matrix to request or validate software needed to make the HybridRAG3 GUI behave closer to a "ChatGPT-like" assistant while staying enterprise-friendly:

- Open-source or free where possible
- Permissive licenses preferred (MIT/BSD/Apache)
- Non-China-origin tooling preferred
- Local/offline-capable components preferred

Note: This document is a minimum known-needed baseline based on what has been implemented/validated so far in this repo. It is not your full enterprise approved software catalog. Final approval status is determined by your internal approved software list and security process.

---

## Status Legend

- `APPROVED-IN-REPO`: Listed as approved in `requirements_approved.txt`
- `PENDING-IN-REPO`: Listed but marked pending/applying
- `NEEDS-REQUEST`: Not currently listed; submit for approval if capability is required

---

## Catalog Merge Note

When you provide the broader internal approved software list, merge it into this matrix and reclassify entries from `NEEDS-REQUEST` or `PENDING-IN-REPO` to your actual internal status.

Quick cross-reference flow:

1. Paste internal approved software export into a working sheet.
2. Match each row in this matrix by package/software name.
3. Re-label status using your internal terms (for example: Approved / Conditional / Not Approved).
4. Keep `NEEDS-REQUEST` only for true gaps.
5. Submit one bundled request for all remaining gaps to reduce review cycles.

---

## A) Baseline Chat + RAG (already in place)

| Capability | Software | Type | License | Status | Notes |
|---|---|---|---|---|---|
| LLM API client | `openai==1.109.1` | Python package | MIT | `APPROVED-IN-REPO` | Core online endpoint client |
| Token counting | `tiktoken==0.8.0` | Python package | MIT | `APPROVED-IN-REPO` | Cost + truncation logic |
| API server | `fastapi`, `uvicorn`, `starlette` | Python packages | MIT/BSD | `APPROVED-IN-REPO` | GUI/API runtime |
| Local embeddings path | Ollama + `nomic-embed-text` | App + model | MIT (Ollama) | Existing project path | Offline-first embedding flow |

---

## B) OCR + Scanned Document Reliability

| Capability | Software | Type | License | Status | Notes |
|---|---|---|---|---|---|
| OCR wrapper | `pytesseract==0.3.13` | Python package | Apache-2.0 | `APPROVED-IN-REPO` | Python bridge only |
| OCR engine | Tesseract OCR 5.x | System binary | Apache-2.0 | Documented as approved/applying in repo notes | Required for real OCR |
| PDF-to-image for OCR | `pdf2image==1.17.0` | Python package | MIT | `APPROVED-IN-REPO` | Converts PDF pages before OCR |
| Poppler utils (`pdfinfo`, etc.) | System binary | System binary | GPL-2.0 | Documented as applying | Needed by `pdf2image` path |
| OCR enhancement pipeline | `ocrmypdf==16.10.4` | Python package | MPL-2.0 | `PENDING-IN-REPO` | Improves scan quality and text layer |

Corporate note: If GPL tools are restricted in your environment, keep OCR feature-gated and use approved alternatives.

---

## C) File Parsing Coverage (engineering/logistics/sysadmin/cyber)

All of the following are already tracked in your repo as parser-support dependencies.

| Software | Main Purpose | License | Status |
|---|---|---|---|
| `olefile`, `python-oxmsg`, `striprtf` | Legacy Office/email/text formats | BSD/MIT | `PENDING-IN-REPO` (extended parser section) |
| `ezdxf`, `numpy-stl`, `vsdx` | CAD/3D/diagram parsing | MIT/BSD | `PENDING-IN-REPO` |
| `python-evtx`, `dpkt` | Event logs + packet captures | Apache/BSD | `PENDING-IN-REPO` |
| `psd-tools` | PSD image parsing | MIT | `PENDING-IN-REPO` |

---

## D) "Create Diagrams/PPT/Visio" Tooling (new approvals likely needed)

### Recommended minimum (corporate-friendly first)

| Capability | Software | Type | License | Status | Why |
|---|---|---|---|---|---|
| Diagram generation via text DSL | Mermaid (CLI or embedded renderer) | Node package / frontend lib | MIT | `NEEDS-REQUEST` | Deterministic diagram output from model reasoning |
| Diagram rendering fallback | Graphviz | System binary + Python wrapper optional | EPL-1.0 | `NEEDS-REQUEST` | Stable SVG/PNG generation |
| PowerPoint creation/edit | `python-pptx` | Python package | MIT | `APPROVED-IN-REPO` | Generate PPTs from model plans |

### Optional for native Visio workflows

| Capability | Software | Type | License | Status | Notes |
|---|---|---|---|---|---|
| Native Visio automation | Microsoft Visio Desktop | Commercial app | Proprietary | `NEEDS-REQUEST` | Needed for true native `.vsdx` authoring/editing |
| COM bridge from Python | `pywin32` | Python package | PSF-like | `NEEDS-REQUEST` | Scripted export/edit in Office/Visio stack |

Practical guidance: use Mermaid/Graphviz + PPT export first; add native Visio automation only if business workflow requires strict `.vsdx` editing.

---

## E) "ChatGPT Website-Like" Feature Gaps to Approve at Platform Level

Software approval alone is not enough. You also need endpoint/platform permissions:

| Feature | Approval Needed | Status |
|---|---|---|
| Advanced reasoning models | Access to capable model on enterprise endpoint | Verify with AI platform team |
| Vision/image understanding | Model deployment that accepts image input | Verify with AI platform team |
| Image generation | Deployment/route that allows image generation API | Verify with AI platform team |
| Web browsing / live search | External network policy + explicit tool integration | Verify with security/network team |
| File generation/download in GUI | Local policy permitting generated artifacts | Verify with endpoint/security team |

---

## F) Non-China-Origin / Enterprise Preference Checklist

Use this when choosing between alternatives:

1. Prefer US/EU origin project governance and transparent maintainers.
2. Prefer permissive licenses: MIT, BSD, Apache-2.0.
3. Avoid viral/copyleft where policy disallows it.
4. Require pinned versions and hash-locked installs for production.
5. Require SBOM and vulnerability scan before rollout.
6. Prefer offline-capable/local tools over cloud-only dependencies.

---

## G) Recommended Approval Package (submit as one bundle)

1. OCR stack:
   - `pytesseract`, `pdf2image`, `ocrmypdf` (pending), Tesseract binary, Poppler binary.
2. Diagram + artifact generation:
   - Mermaid renderer (or Graphviz), keep `python-pptx`.
3. Optional native Visio automation:
   - Visio Desktop + `pywin32` only if required.
4. Platform permissions:
   - Model access for reasoning + vision + image generation routes.

---

## H) Quick Validation Commands (after approval/install)

```powershell
python -c "import openai, pytesseract, pdf2image, pptx; print('core ok')"
python -c "import vsdx, ezdxf, dpkt; print('extended parsers ok')"
tesseract --version
pdfinfo -v
pytest tests/test_parser_coverage_guard.py -q
pytest tests/test_indexing_allowlist_sync.py -q
```

---

## Related Docs

- `requirements_approved.txt`
- `docs/01_setup/INSTALL_AND_SETUP.md`
- `docs/01_setup/MANUAL_INSTALL.md`
- `docs/01_setup/OCR_DIVERSION_PROCESS_FLOW_CHEATSHEET.md`
- `docs/ClaudeCLI_Codex_Collabs/003_parser_coverage_gap_analysis.md`
