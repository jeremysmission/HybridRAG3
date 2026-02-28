# Software Applications Waiver Reference Sheet

**Project:** HybridRAG v3 -- Offline-First RAG System
**Updated:** 2026-02-28
**Revision:** v5c (openai 1.109.1, 410 tests, wizard auto-setup)

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
| 1 | Python | 3.12 / 3.11.9 | PSF-2.0 | Python.org / USA | Runtime environment |
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

---

## YELLOW -- Applying for Approval (Currently Installed)

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
| Note | Bumped 1.45.1 -> 1.51.2 (2026-02-25), then 1.51.2 -> 1.109.1 (2026-02-26: 1.51.2 passed removed `proxies=` kwarg to httpx 0.28) |

### Waiver Request: Testing Tools

| Package | Version | License | Publisher / Origin | Purpose |
|---------|---------|---------|-------------------|---------|
| pytest | 9.0.2 | MIT | Holger Krekel / Germany | Test framework (410 regression tests) |
| psutil | 7.2.2 | BSD-3 | Giampaolo Rodola / USA | Process monitoring for indexing |

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

Models to run on Ollama (all open-source, all USA/EU/Allied origin):

| Model | Size | License | Publisher | Purpose |
|-------|------|---------|-----------|---------|
| nomic-embed-text | 274 MB | Apache 2.0 | Nomic AI / USA | Embeddings (768-dim, required) |
| phi4:14b-q4_K_M | 9.1 GB | MIT | Microsoft / USA | Primary Q&A model (default) |
| mistral-nemo:12b | 7.1 GB | Apache 2.0 | Mistral + NVIDIA | Gen primary, 128K context |
| phi4-mini | 2.3 GB | MIT | Microsoft / USA | Laptop fallback |
| mistral:7b | 4.1 GB | Apache 2.0 | Mistral AI / France | Gen fallback |
| gemma3:4b | 3.3 GB | Apache 2.0 | Google / USA | PM fast summarization |

---

## BLUE -- Recommended for Next Phase (Not Yet Installed)

### Waiver Request: FAISS Vector Search

| Field | Detail |
|-------|--------|
| Package | faiss-cpu |
| Version | 1.9.0 |
| License | MIT |
| Publisher | Meta AI Research / USA |
| Purpose | Fast vector similarity search (10-100x faster than brute-force) |
| Data Flow | In-process library, no network activity |

### Waiver Request: LanceDB (Embedded Vector Database)

| Field | Detail |
|-------|--------|
| Package | lancedb |
| Version | 0.29.2 (or latest) |
| License | Apache 2.0 |
| Publisher | LanceDB Inc. / USA (San Francisco, YC-backed) |
| Purpose | All-in-one embedded vector database with built-in hybrid search |
| Data Flow | In-process embedded DB, file-based storage, zero network activity |

### Waiver Request: vLLM + openai 2.x (Future -- Workstation Only)

| Field | Detail |
|-------|--------|
| Package 1 | vllm==0.10.1 |
| License | Apache 2.0 |
| Publisher | UC Berkeley / USA |
| Purpose | GPU-optimized model serving (batching, prefix caching, tensor parallelism) |
| Package 2 | openai>=1.99.1 (upgrade from current 1.109.1) |
| Note | These two MUST be approved together |
| Timeline | Not needed until workstation hardware arrives |

---

## RED -- Banned Software (DO NOT SUBMIT)

### Banned AI Models (NDAA / ITAR)

| Software | Publisher | Country | Reason |
|----------|-----------|---------|--------|
| Qwen (all versions) | Alibaba | China | NDAA restricted entity |
| DeepSeek (all versions) | DeepSeek | China | NDAA restricted entity |
| BGE / BGE-M3 embeddings | BAAI | China | NDAA restricted entity |
| Llama (all versions) | Meta | USA | AUP prohibits weapons/military use |

### Banned Software Packages

| Software | Publisher | Country | Reason |
|----------|-----------|---------|--------|
| Milvus / pymilvus | Zilliz | China (Shanghai) | NDAA -- China origin |
| LangChain | LangChain Inc. | USA | 200+ transitive dependencies |
| ChromaDB | Chroma Inc. | USA | onnxruntime bloat, telemetry, Windows issues |
| PyMuPDF | Artifex | USA | AGPL copyleft license |

---

## RETIRED -- Removed from Stack (Session 15, 2026-02-24)

Embeddings now served by Ollama nomic-embed-text. HuggingFace ecosystem removed.
**Do not re-apply for these packages.**

| Package | Last Version | License | Reason for Removal |
|---------|-------------|---------|-------------------|
| sentence-transformers | 2.7.0 | Apache 2.0 | Replaced by Ollama nomic-embed-text |
| torch (PyTorch) | 2.10.0 | BSD-3 | No longer needed |
| transformers | 4.57.6 | Apache 2.0 | No longer needed |
| tokenizers | 0.22.2 | Apache 2.0 | No longer needed |
| huggingface_hub | 0.36.1 | Apache 2.0 | HuggingFace retired |
| safetensors | 0.7.0 | Apache 2.0 | No longer needed |
| scipy | 1.17.0 | BSD-3 | Was sentence-transformers dep |
| scikit-learn | 1.8.0 | BSD-3 | BM25 now handled by SQLite FTS5 |

**Impact:** ~2.5 GB removed from virtual environment. No functionality lost.

---

## Installation Totals

| Category | Count | Size |
|----------|-------|------|
| GREEN (approved, installed) | 35 direct + 23 transitive | ~200 MB |
| YELLOW (applying, installed) | 3 direct + Ollama | ~50 MB + Ollama |
| BLUE (recommended, not yet installed) | 3 direct | ~350 MB |
| **Total when fully approved** | **~70 packages** | **~600 MB** |
| RETIRED (removed) | 8 | -2.5 GB saved |
