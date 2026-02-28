# Software Applications Waiver Reference Sheet

**Project:** HybridRAG v3 -- Offline-First RAG System
**Updated:** 2026-02-28
**Revision:** v5c (openai 1.109.1 httpx compat fix, 410 tests, wizard auto-setup)

---

## How to Use This Document

1. Each row below maps to one waiver request in the enterprise software portal
2. GREEN = already approved or ships with approved software (no new waiver needed)
3. YELLOW = currently installed, applying for approval
4. BLUE = recommended for next phase, not yet installed
5. RED = banned, do NOT submit (listed for audit completeness only)

---

## Approval Leverage (Already-Approved Anchors)

Use these relationships in your waiver justification:

| If This Is Approved | Then These Are Already Covered |
|---------------------|-------------------------------|
| Python 3.x | typing_extensions, pip, setuptools (ship with Python) |
| pip | cryptography, urllib3, requests (pip's own dependencies) |
| Chrome / Edge | pypdfium2 (same Google PDFium engine as Chrome's PDF viewer) |
| Microsoft Office | python-docx, python-pptx, openpyxl (just READ Office file formats) |
| Any AI/ML approval | numpy is the universal foundation for all Python numerical work |

---

## GREEN -- Approved and Installed

These are installed, working, and appear on the approved software list or
ship with already-approved software. **No new waiver needed.**

### Core Runtime

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 1 | Python | 3.11.9 | PSF-2.0 | Python.org / USA | Runtime environment |
| 2 | pip | 26.0.1 | MIT | PyPA / USA | Package installer (ships with Python) |
| 3 | setuptools | 65.5.0 | MIT | PyPA / USA | Build tools (ships with Python) |

### AI / Model APIs

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 4 | numpy | 1.26.4 | BSD-3 | NumFOCUS / USA | Vector math, embedding storage |
| 5 | tiktoken | 0.8.0 | MIT | OpenAI / USA | Token counting (offline, no network) |

### HTTP and Networking

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 6 | httpx | 0.28.1 | BSD-3 | Encode / UK | HTTP client (embedder + openai dep) |
| 7 | requests | 2.32.5 | Apache 2.0 | PSF / USA | HTTP client (pre-installed with pip) |
| 8 | urllib3 | 2.6.3 | MIT | PSF / USA | HTTP internals (pre-installed with pip) |
| 9 | cryptography | 44.0.2 | Apache 2.0 | PyCA / USA | AES encryption (pre-installed with pip) |
| 10 | certifi | 2026.1.4 | MPL-2.0 | Kenneth Reitz / USA | SSL certificates (requests dep) |

### Data Validation

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 11 | pydantic | 2.11.1 | MIT | Pydantic / USA | Data validation (openai SDK dep) |
| 12 | pyyaml | 6.0.2 | MIT | Kirill Simonov / USA | YAML config parsing |

### Document Parsers

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 13 | pdfplumber | 0.11.9 | MIT | Jeremy Singer-Vine / USA | PDF text extraction |
| 14 | pdfminer.six | 20251230 | MIT | USA | PDF parsing engine (pdfplumber dep) |
| 15 | pypdf | 6.6.2 | BSD-3 | USA | PDF metadata and page counting |
| 16 | pypdfium2 | 5.3.0 | Apache 2.0 | Google / USA | PDF rendering (same engine as Chrome) |
| 17 | pdf2image | 1.17.0 | MIT | USA | PDF to image conversion |
| 18 | pytesseract | 0.3.13 | Apache 2.0 | USA | OCR bridge (reads scanned PDFs) |
| 19 | python-docx | 1.2.0 | MIT | USA | Word .docx reader |
| 20 | python-pptx | 1.0.2 | MIT | USA | PowerPoint .pptx reader |
| 21 | openpyxl | 3.1.5 | MIT | USA | Excel .xlsx reader |
| 22 | xlsxwriter | 3.2.9 | BSD-2 | USA | Excel .xlsx writer |
| 23 | lxml | 6.0.2 | BSD-3 | USA | XML/HTML parsing (Office XML dep) |
| 24 | pillow | 12.1.0 | HPND | PIL / USA | Image processing |

### Web Server / API

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 25 | fastapi | 0.115.0 | MIT | Tiangolo / USA | REST API framework |
| 26 | uvicorn | 0.41.0 | BSD-3 | Encode / UK | ASGI server |
| 27 | starlette | 0.38.6 | BSD-3 | Encode / UK | ASGI toolkit (fastapi dep) |

### Configuration and Logging

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 28 | structlog | 24.4.0 | MIT | Hynek Schlawack / Germany | Structured JSON logging |
| 29 | rich | 13.9.4 | MIT | Will McGugan / UK | Console formatting (display only) |
| 30 | tqdm | 4.67.3 | MIT | USA | Progress bars (display only) |
| 31 | regex | 2026.1.15 | Apache 2.0 | USA | Enhanced text processing |
| 32 | colorama | 0.4.6 | BSD-3 | USA | Console colors (Windows) |

### Credential Storage

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 33 | keyring | 23.13.1 | MIT | Jason R. Coombs / USA | Windows Credential Manager access |

### Other Direct Dependencies

| # | Package | Version | License | Publisher / Origin | Purpose |
|---|---------|---------|---------|-------------------|---------|
| 34 | python-multipart | 0.0.22 | Apache 2.0 | USA | Form data parsing (fastapi dep) |
| 35 | click | 8.3.1 | BSD-3 | Pallets / USA | CLI toolkit (uvicorn dep) |

**Total GREEN: 35 packages (all MIT/BSD/Apache, all USA/UK/EU/Allied)**

### Transitive Dependencies (auto-installed, no separate waiver)

These are pulled in automatically by the packages above. They do not need
separate waivers because they are dependencies of already-approved software.

| Package | Version | License | Pulled In By |
|---------|---------|---------|-------------|
| annotated-types | 0.7.0 | MIT | pydantic |
| anyio | 4.12.1 | MIT | httpx |
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
| sniffio | 1.3.1 | MIT | httpx |
| typing_extensions | 4.15.0 | PSF-2.0 | pydantic |
| typing-inspection | 0.4.2 | MIT | pydantic |

---

## YELLOW -- Applying for Approval (Currently Installed)

These are installed and working but need waiver approval.

### Waiver Request: openai SDK

| Field | Detail |
|-------|--------|
| Package | openai |
| Version | 1.109.1 (PINNED v1.x -- never upgrade to 2.x) |
| License | MIT |
| Publisher | OpenAI / USA |
| Purpose | API client for Azure OpenAI cloud queries |
| Data Flow | HTTPS to single configured Azure endpoint only |
| Network | One outbound connection per query (when online mode enabled) |
| Justification | Industry-standard SDK for OpenAI-compatible APIs. Used by Azure Government OpenAI service. MIT licensed, zero telemetry, USA publisher. |
| Note | Bumped 1.45.1 -> 1.51.2 (2026-02-25, mirror purged old version), then 1.51.2 -> 1.109.1 (2026-02-26, 1.51.2 passed removed `proxies=` kwarg to httpx 0.28.1) |

### Waiver Request: Testing Tools

| Package | Version | License | Publisher / Origin | Purpose |
|---------|---------|---------|-------------------|---------|
| pytest | 9.0.2 | MIT | Holger Krekel / Germany | Test framework (410 regression tests) |
| psutil | 7.2.2 | BSD-3 | Giampaolo Rodola / USA | Process monitoring for indexing |

Transitive dependencies of pytest (apply together):

| Package | Version | License | Pulled In By |
|---------|---------|---------|-------------|
| iniconfig | 2.3.0 | MIT | pytest |
| pluggy | 1.6.0 | MIT | pytest |
| importlib_metadata | 8.7.1 | Apache 2.0 | pytest |
| zipp | 3.23.0 | MIT | importlib_metadata |

**Justification:** pytest is the standard Python test framework used by 90%+ of
Python projects. All 410 regression tests depend on it. psutil monitors system
resources during index builds. Both are MIT/BSD licensed, zero network activity.

### Waiver Request: Ollama (Offline LLM Server)

| Field | Detail |
|-------|--------|
| Software | Ollama |
| Version | Latest stable |
| License | MIT |
| Publisher | Ollama Inc. / USA |
| Purpose | Run AI language models locally -- no cloud, no internet required |
| Data Flow | localhost only (127.0.0.1:11434), never contacts external servers |
| Network | Zero outbound connections during operation |
| Justification | Enables fully offline AI-powered document search and Q&A. All models run locally with no data leaving the machine. |

Models to run on Ollama (all open-source, all USA/EU/Allied origin):

| Model | Size | License | Publisher | Purpose |
|-------|------|---------|-----------|---------|
| nomic-embed-text | 274 MB | Apache 2.0 | Nomic AI / USA | Embeddings (required) |
| phi4-mini | 2.3 GB | MIT | Microsoft / USA | Primary Q&A model |
| mistral:7b | 4.1 GB | Apache 2.0 | Mistral AI / France | Engineering alternate |
| phi4:14b-q4_K_M | 9.1 GB | MIT | Microsoft / USA | High-accuracy (workstation) |
| gemma3:4b | 3.3 GB | Apache 2.0 | Google / USA | Fast summarization |
| mistral-nemo:12b | 7.1 GB | Apache 2.0 | Mistral + NVIDIA | Long documents (128K ctx) |

---

## BLUE -- Recommended for Next Phase (Not Yet Installed)

These packages are recommended for the next development phase.
Apply for approval now so they are ready when needed.

### Waiver Request: FAISS Vector Search

| Field | Detail |
|-------|--------|
| Package | faiss-cpu |
| Version | 1.9.0 |
| License | MIT |
| Publisher | Meta AI Research / USA |
| pip install | `pip install faiss-cpu==1.9.0` |
| Dependencies | numpy (already approved) |
| Purpose | Fast vector similarity search (10-100x faster than current brute-force) |
| Data Flow | In-process library, no network activity, no server process |
| Justification | Industry-standard vector search library. Pure MIT license (no AI model restrictions). Single dependency (numpy, already approved). Current brute-force search will not scale beyond 500K documents. |
| Hardware | Runs on CPU. GPU version (faiss-gpu) available for workstation RTX 3090 |

### Waiver Request: LanceDB (Embedded Vector Database)

| Field | Detail |
|-------|--------|
| Package | lancedb |
| Version | 0.29.2 (or latest) |
| License | Apache 2.0 |
| Publisher | LanceDB Inc. / USA (San Francisco, YC-backed) |
| pip install | `pip install lancedb` |
| Dependencies | pyarrow (Apache Foundation), pydantic (already approved), numpy (already approved), tqdm (already approved) |
| Purpose | All-in-one embedded vector database with built-in hybrid search |
| Data Flow | In-process embedded DB, file-based storage, zero network activity |
| Server Required | No -- fully embedded, serverless, like SQLite |
| Justification | Replaces current SQLite + memmap + FTS5 triple-store with a single embedded database that handles vector search, keyword search, and metadata in one store. Apache 2.0 license, USA company, zero telemetry. 4 MB idle memory, file-based persistence, fully offline. Designed as "the SQLite of vector databases." |

LanceDB transitive dependencies requiring approval:

| Package | Version | License | Publisher / Origin | Purpose |
|---------|---------|---------|-------------------|---------|
| pyarrow | >=16.0 | Apache 2.0 | Apache Software Foundation / USA | Columnar data format |
| lance | (bundled) | Apache 2.0 | LanceDB Inc. / USA | Lance storage engine |

### Waiver Request: vLLM + openai 2.x (Future -- Workstation Only)

| Field | Detail |
|-------|--------|
| Package 1 | vllm==0.10.1 |
| License | Apache 2.0 |
| Publisher | UC Berkeley / USA |
| Purpose | GPU-optimized model serving (batching, prefix caching, tensor parallelism) |
| Requirement | Dual RTX 3090 workstation (48 GB VRAM) |
| Package 2 | openai>=1.99.1 (upgrade from current 1.109.1) |
| License | MIT |
| Publisher | OpenAI / USA |
| Purpose | Required dependency for vLLM; API client for cloud models |
| Impact | Code changes needed to migrate from openai 1.x to 2.x API syntax |
| Note | These two MUST be approved together (vLLM depends on openai>=1.99.1) |
| Timeline | Not needed until workstation hardware arrives |

---

## RED -- Banned Software (DO NOT SUBMIT)

These were evaluated and explicitly rejected. Listed for audit completeness
so procurement does not re-evaluate them.

### Banned AI Models (NDAA / ITAR)

| Software | Publisher | Country | Reason |
|----------|-----------|---------|--------|
| Qwen (all versions) | Alibaba | China | NDAA restricted entity |
| DeepSeek (all versions) | DeepSeek | China | NDAA restricted entity |
| BGE / BGE-M3 embeddings | BAAI | China | NDAA restricted entity |
| Llama (all versions) | Meta | USA | AUP prohibits weapons/military use (ITAR conflict) |

### Banned Software Packages

| Software | Publisher | Country | Reason |
|----------|-----------|---------|--------|
| Milvus / pymilvus | Zilliz | China (Shanghai) | NDAA -- China origin, engineering in China |
| LangChain | LangChain Inc. | USA | 200+ transitive dependencies, version instability |
| ChromaDB | Chroma Inc. | USA | onnxruntime bloat, posthog telemetry, Windows issues |
| PyMuPDF | Artifex | USA | AGPL copyleft license (viral, incompatible) |

### Disqualified Database Options

| Software | Publisher | Country | Reason |
|----------|-----------|---------|--------|
| DuckDB + VSS | DuckDB Foundation | Netherlands | VSS extension is experimental -- data corruption risk on crash |
| Qdrant (local) | Qdrant GmbH | Germany | Local mode explicitly "dev only"; 400 MB constant RAM overhead |
| PostgreSQL + pgvector | Community | International | Requires separate server process (violates embedded/portable requirement) |

---

## RETIRED -- Removed from Stack (Session 15, 2026-02-24)

These were previously installed but have been removed. Embeddings are now
served by Ollama (nomic-embed-text) instead of HuggingFace/PyTorch.
**No longer needed -- do not re-apply.**

| Package | Last Version | License | Reason for Removal |
|---------|-------------|---------|-------------------|
| sentence-transformers | 2.7.0 | Apache 2.0 | Replaced by Ollama nomic-embed-text |
| torch (PyTorch) | 2.10.0 | BSD-3 | No longer needed without HuggingFace |
| transformers | 4.57.6 | Apache 2.0 | No longer needed without HuggingFace |
| tokenizers | 0.22.2 | Apache 2.0 | No longer needed without HuggingFace |
| huggingface_hub | 0.36.1 | Apache 2.0 | HuggingFace models retired entirely |
| safetensors | 0.7.0 | Apache 2.0 | No longer needed without HuggingFace |
| scipy | 1.17.0 | BSD-3 | Was sentence-transformers dependency |
| scikit-learn | 1.8.0 | BSD-3 | BM25 now handled by SQLite FTS5 |

**Impact:** ~2.5 GB removed from virtual environment. No functionality lost.

---

## Summary: What to Apply for Tomorrow

### Priority 1 (Needed Now)

| Package | Version | License | Action |
|---------|---------|---------|--------|
| openai | 1.109.1 | MIT | Apply for approval (bumped from 1.51.2 for httpx 0.28 compat) |
| pytest | 9.0.2 | MIT | Apply for approval (test framework) |
| psutil | 7.2.2 | BSD-3 | Apply for approval (process monitoring) |
| Ollama | latest | MIT | Apply for approval (offline LLM server) |

### Priority 2 (Needed for Scale-Out)

| Package | Version | License | Action |
|---------|---------|---------|--------|
| faiss-cpu | 1.9.0 | MIT | Apply for approval (vector search) |
| lancedb | 0.29.2 | Apache 2.0 | Apply for approval (embedded vector DB) |
| pyarrow | >=16.0 | Apache 2.0 | Apply for approval (lancedb dependency) |

### Priority 3 (Future -- Workstation Hardware)

| Package | Version | License | Action |
|---------|---------|---------|--------|
| vllm | 0.10.1 | Apache 2.0 | Apply when workstation arrives |
| openai | >=1.99.1 | MIT | Apply together with vLLM |

---

## Installation Totals

| Category | Count | Size |
|----------|-------|------|
| GREEN (approved, installed) | 35 direct + 23 transitive | ~200 MB |
| YELLOW (applying, installed) | 3 direct + 4 transitive + Ollama | ~50 MB + Ollama |
| BLUE (recommended, not yet installed) | 3 direct + 2 transitive | ~350 MB |
| **Total when fully approved** | **~70 packages** | **~600 MB** |
| RETIRED (removed) | 8 | -2.5 GB saved |

---

## Case Commentary Template

Use this template when filling out the waiver justification field:

```
[PACKAGE_NAME] v[VERSION] is a [LICENSE]-licensed Python package published
by [PUBLISHER] ([COUNTRY]). It is used by HybridRAG v3 for [PURPOSE].
Zero telemetry, zero outbound network activity during operation. [PACKAGE]
has zero known CVEs on the NVD and is not on the CISA KEV list.
[ANCHOR_RELATIONSHIP if applicable].
```

Example for openai:
```
openai v1.109.1 is an MIT-licensed Python package published by OpenAI (USA).
It is used by HybridRAG v3 as the API client for Azure OpenAI cloud queries.
Zero telemetry. Network activity limited to one HTTPS request per user query
(online mode only; offline mode uses no network). openai has zero known CVEs
on the NVD and is not on the CISA KEV list. openai is the standard SDK
recommended by Microsoft for Azure OpenAI Service.
```

---

## Contact

For technical questions about any package, its data flow, or security
posture, contact the project developer.
