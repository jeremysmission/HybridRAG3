# Software Waiver Request Summary

**Date:** 2026-02-24
**Revision:** v5 (post-HuggingFace retirement, fresh deploy validated)
**Project:** HybridRAG v3 -- Offline-First RAG System
**Requested By:** Jeremy Randa

---

## Purpose

This document summarizes all software packages requiring enterprise
waiver/approval for the HybridRAG v3 knowledge retrieval system. The
system is designed for offline-first operation with zero telemetry and
no external data transmission.

Cross-referenced against waiver cheat sheet v4b on 2026-02-24.
Fresh deployment test: 373/374 tests passed (1 skipped -- Tk display).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-24 | v5: Removed 8 retired HuggingFace packages, added pytest/psutil, added all transitive deps, categorized by approval status |
| 2026-02-24 | Cross-referenced pip install against waiver_cheat_sheet_v4b.xlsx |
| 2026-02-21 | v4b: Initial waiver summary with 35 approved packages |

---

## GREEN -- Approved and Installed (No Waiver Needed)

These are installed, working, and appear on the approved software list.

### Direct Dependencies (explicitly in requirements.txt)

| Package | Version | License | Origin | Purpose |
|---------|---------|---------|--------|---------|
| Python | 3.11.9 | PSF-2.0 | Python.org/USA | Runtime |
| pip | 26.0.1 | MIT | PyPA/USA | Package installer |
| numpy | 1.26.4 | BSD-3 | NumFOCUS/USA | Vector math |
| openai | 1.51.2 | MIT | OpenAI/USA | API client (PINNED v1.x) |
| tiktoken | 0.8.0 | MIT | OpenAI/USA | Token counting (offline) |
| httpx | 0.28.1 | BSD-3 | Encode/UK | HTTP client |
| requests | 2.32.5 | Apache 2.0 | PSF/USA | HTTP client |
| urllib3 | 2.6.3 | MIT | PSF/USA | HTTP internals |
| pydantic | 2.11.1 | MIT | Pydantic/USA | Data validation |
| pyyaml | 6.0.2 | MIT | YAML/USA | Config parsing |
| cryptography | 44.0.2 | Apache 2.0 | PyCA/USA | Credential encryption |
| fastapi | 0.115.0 | MIT | Tiangolo/USA | REST API |
| uvicorn | 0.41.0 | BSD-3 | Encode/UK | ASGI server |
| starlette | 0.38.6 | BSD-3 | Encode/UK | HTTP toolkit |
| structlog | 24.4.0 | MIT | Hynek/Germany | Structured logging |
| pdfplumber | 0.11.9 | MIT | USA | PDF text extraction |
| pdfminer.six | 20251230 | MIT | USA | PDF parsing engine |
| pypdf | 6.6.2 | BSD-3 | USA | PDF metadata |
| pypdfium2 | 5.3.0 | Apache 2.0 | Google/USA | PDF rendering |
| pdf2image | 1.17.0 | MIT | USA | PDF to image conversion |
| pytesseract | 0.3.13 | Apache 2.0 | USA | OCR bridge |
| python-docx | 1.2.0 | MIT | USA | Word documents |
| python-pptx | 1.0.2 | MIT | USA | PowerPoint |
| openpyxl | 3.1.5 | MIT | USA | Excel reading |
| xlsxwriter | 3.2.9 | BSD-2 | USA | Excel writing |
| lxml | 6.0.2 | BSD-3 | USA | XML parsing |
| pillow | 12.1.0 | HPND | USA | Image processing |
| rich | 13.9.4 | MIT | USA | Console display |
| tqdm | 4.67.3 | MIT | USA | Progress bars |
| regex | 2026.1.15 | Apache 2.0 | USA | Text processing |
| colorama | 0.4.6 | BSD-3 | USA | Console colors |
| keyring | 23.13.1 | MIT | USA | Windows Credential Manager |
| python-multipart | 0.0.22 | Apache 2.0 | USA | Form data (fastapi dep) |
| click | 8.3.1 | BSD-3 | Pallets/USA | CLI toolkit (uvicorn dep) |

**Total direct: 34 packages, all open-source, all USA/EU/Allied origin**

### Transitive Dependencies (auto-installed by pip, no separate approval needed)

| Package | Version | License | Pulled In By |
|---------|---------|---------|-------------|
| annotated-types | 0.7.0 | MIT | pydantic |
| anyio | 4.12.1 | MIT | httpx |
| certifi | 2026.1.4 | MPL-2.0 | requests |
| cffi | 2.0.0 | MIT | cryptography |
| chardet | 5.2.0 | LGPL-2.1 | pdfminer.six |
| charset-normalizer | 3.4.4 | MIT | requests |
| distro | 1.9.0 | Apache 2.0 | openai |
| et_xmlfile | 2.0.0 | MIT | openpyxl |
| h11 | 0.16.0 | MIT | uvicorn |
| httpcore | 1.0.9 | BSD-3 | httpx |
| idna | 3.11 | BSD-3 | requests |
| jaraco.classes | 3.4.0 | MIT | keyring |
| jiter | 0.13.0 | MIT | pydantic |
| markdown-it-py | 4.0.0 | MIT | rich |
| mdurl | 0.1.2 | MIT | markdown-it-py |
| more-itertools | 10.8.0 | MIT | keyring |
| packaging | 26.0 | Apache 2.0 | pytest |
| pycparser | 3.0 | BSD-3 | cffi |
| pydantic_core | 2.33.0 | MIT | pydantic |
| Pygments | 2.19.2 | BSD-2 | rich |
| pywin32-ctypes | 0.2.3 | BSD-3 | keyring (Windows) |
| setuptools | 65.5.0 | MIT | Ships with Python |
| sniffio | 1.3.1 | MIT | httpx |
| typing_extensions | 4.15.0 | PSF-2.0 | pydantic |
| typing-inspection | 0.4.2 | MIT | pydantic |

**Total transitive: 25 packages**

---

## YELLOW -- Applying for Approval

These packages are installed and working but not yet on the approved
software list. Waiver applications in progress.

### Testing and Development Tools

| Package | Version | License | Origin | Purpose | Status |
|---------|---------|---------|--------|---------|--------|
| pytest | 9.0.2 | MIT | USA | Test framework (regression suite) | Applying |
| psutil | 7.2.2 | BSD-3 | USA | Process monitoring (live indexing test) | Applying |
| iniconfig | 2.3.0 | MIT | USA | pytest dependency | Applying (transitive) |
| pluggy | 1.6.0 | MIT | USA | pytest dependency | Applying (transitive) |
| importlib_metadata | 8.7.1 | Apache 2.0 | USA | pytest dependency | Applying (transitive) |
| zipp | 3.23.0 | MIT | USA | importlib_metadata dependency | Applying (transitive) |

**Justification:** pytest is the standard Python test framework. All
373 regression tests depend on it. psutil is used by the live indexing
test to monitor system resources during index builds. Both are MIT/BSD
licensed, USA origin, zero network activity.

---

## Waiver Request 1: Ollama (Offline LLM Server)

| Field | Detail |
|-------|--------|
| Software | Ollama |
| Version | Latest stable |
| License | MIT |
| Publisher | Ollama Inc. / USA |
| Purpose | Run AI language models locally -- no cloud, no internet required |
| Data Flow | localhost only (127.0.0.1:11434), never contacts external servers |
| Network | Zero outbound connections during operation |
| Justification | Enables fully offline AI-powered document search and Q&A |

### Models to Run on Ollama

| Model | Size | License | Publisher | Purpose |
|-------|------|---------|-----------|---------|
| nomic-embed-text | 274 MB | Apache 2.0 | Nomic AI/USA | **Embeddings (required)** |
| phi4-mini | 2.3 GB | MIT | Microsoft/USA | Primary Q&A model |
| mistral:7b | 4.1 GB | Apache 2.0 | Mistral AI/France | Engineering alternate |
| phi4:14b-q4_K_M | 9.1 GB | MIT | Microsoft/USA | High-accuracy model |
| gemma3:4b | 3.3 GB | Apache 2.0 | Google/USA | Fast summarization |
| mistral-nemo:12b | 7.1 GB | Apache 2.0 | Mistral+NVIDIA | Long documents (128K) |

**All models:** open-source, USA/EU origin, no NDAA-restricted publishers.

---

## Waiver Request 2: vLLM + OpenAI SDK Upgrade (Future -- Workstation)

**IMPORTANT:** These two packages must be approved together. vLLM
depends on openai>=1.99.1 and cannot install without it.

| Field | Detail |
|-------|--------|
| Package 1 | vllm==0.10.1 |
| License | Apache 2.0 |
| Publisher | UC Berkeley / USA |
| Purpose | GPU-optimized model serving with batching and caching |
| Requirement | Dual RTX 3090 workstation (on order) |
| Package 2 | openai>=1.99.1 (upgrade from current 1.51.2) |
| License | MIT |
| Publisher | OpenAI / USA |
| Purpose | Required dependency for vLLM; API client for cloud models |
| Impact | Code changes needed to migrate from openai 1.x to 2.x API |
| Timeline | Not needed until workstation hardware arrives |

---

## Waiver Request 3: FAISS Vector Search (Future -- Workstation)

| Field | Detail |
|-------|--------|
| Package | faiss-cpu==1.9.0 |
| License | MIT |
| Publisher | Meta AI Research / USA |
| Purpose | Fast vector similarity search (10-100x faster than current SQLite) |
| Note | Library is MIT-licensed; does not include any AI models |
| Timeline | After workstation arrives; current system works without it |

---

## Waiver Request 4: AI Use Case Registration

| Field | Detail |
|-------|--------|
| System Name | HybridRAG v3 |
| Type | Retrieval-Augmented Generation (RAG) |
| Function | Searches indexed documents and generates answers using AI |
| Data Scope | Internal project documents only (no PII, no customer data) |
| AI Models | See Ollama models above (all run locally, no cloud) |
| Online Mode | Optional -- routes through approved API endpoint only |
| User Count | Single-user (no multi-tenant) |
| Network | Offline by default; online mode uses one configurable endpoint |
| Telemetry | Zero -- all telemetry disabled (HF_HUB_DISABLE_TELEMETRY=1) |
| Data Storage | Local only (SQLite + flat files on local disk) |
| Credentials | Windows Credential Manager (OS-level DPAPI encryption) |

---

## RETIRED -- Removed from Stack (Session 15, 2026-02-24)

These packages were previously approved but have been removed. They
are no longer installed or required. Embeddings are now served by
Ollama (nomic-embed-text) instead of HuggingFace/PyTorch.

| Package | Previous Version | Reason for Removal |
|---------|-----------------|-------------------|
| torch | 2.10.0 | HuggingFace retired; Ollama replaces local inference |
| sentence-transformers | 2.7.0 | Replaced by Ollama nomic-embed-text |
| transformers | 4.57.6 | HuggingFace retired |
| tokenizers | 0.22.2 | HuggingFace retired |
| huggingface_hub | 0.36.1 | HuggingFace retired |
| safetensors | 0.7.0 | HuggingFace retired |
| scipy | 1.17.0 | Was sentence-transformers dependency |
| scikit-learn | 1.8.0 | Was sentence-transformers dependency |

**Impact:** ~2.5 GB removed from virtual environment. No functionality
lost -- Ollama provides equivalent embedding quality with 768-dimension
vectors (up from 384).

---

## Excluded Software (Compliance Reference)

The following were evaluated and explicitly rejected:

| Software | Publisher | Reason for Rejection |
|----------|-----------|---------------------|
| Qwen (all) | Alibaba/China | NDAA restricted entity |
| DeepSeek (all) | DeepSeek/China | NDAA restricted entity |
| BGE embeddings | BAAI/China | NDAA restricted entity |
| Llama (all) | Meta/USA | AUP restricts weapons/military use |
| LangChain | LangChain Inc | 200+ dependencies, version instability |
| ChromaDB | Chroma | Windows compatibility issues |
| PyMuPDF | Artifex | AGPL copyleft license |

---

## Installation Totals

| Category | Count | Size |
|----------|-------|------|
| Direct dependencies (GREEN) | 34 | ~200 MB |
| Transitive dependencies (GREEN) | 25 | included above |
| Applying for approval (YELLOW) | 6 | ~2 MB |
| **Total installed** | **65** | **~200 MB** |
| Retired (removed) | 8 | -2.5 GB saved |

---

## Enterprise SSL Setup (Already Resolved)

The work laptop uses `pip-system-certs` to integrate with the
corporate proxy certificate chain. This was installed using a one-time
`--trusted-host` bootstrap and now all pip operations use full SSL
verification through the Windows certificate store. No security
bypass is in place.

---

## Contact

For technical questions about any package, its data flow, or security
posture, contact the project developer.
