# HybridRAG3 -- Software Selection Tradeoffs

Revision: A | Date: 2026-02-25

---

## Purpose

This document records the engineering rationale behind every major software
choice in HybridRAG3. Each section follows a consistent structure:

- **What We Chose** -- the component that ships in production.
- **What We Considered** -- alternatives evaluated during design.
- **Why We Chose It** -- the deciding factors.
- **What We Gave Up** -- honest tradeoffs accepted.

Selection criteria are weighted by operational context: offline-first
operation, zero-trust network posture, regulated-industry supply chain
compliance, minimal dependency footprint, and laptop-to-workstation
scalability.

---

## 1. Embedding Model: nomic-embed-text (via Ollama)

**What We Chose:** Nomic AI's nomic-embed-text served through Ollama,
producing 768-dimensional vectors.

**What We Considered:**

| Model | Source | Dimensions | Size |
|---|---|---|---|
| sentence-transformers/MiniLM-L6-v2 | HuggingFace | 384 | 87 MB |
| text-embedding-3-small | OpenAI | 1536 | Cloud-only |
| embed-english-v3.0 | Cohere | 1024 | Cloud-only |
| bge-base-en-v1.5 | BAAI (Beijing) | 768 | 440 MB |

**Why We Chose It:**

- 768 dimensions -- double the MiniLM vector width, measurably better
  separation on technical vocabulary (part numbers, acronyms, spec terms).
- Runs locally via Ollama with a single `ollama pull` command. No
  HuggingFace Transformers stack, no torch, no tokenizers library.
- Apache 2.0 license from a US-based company (Nomic AI, Virginia).
- Sidesteps the HuggingFace AI Use Case approval process entirely --
  Ollama pulls model weights directly without the HuggingFace Hub SDK.
- 274 MB download, single binary serving, no Python process required.

**What We Gave Up:**

- HuggingFace ecosystem integration (fine-tuning pipelines, model hub
  versioning, community adapters). If we need domain-adapted embeddings
  later, this path is harder.
- MiniLM is 87 MB vs 274 MB -- a 3x size penalty. On bandwidth-limited
  installs this matters.
- Requires the Ollama runtime to be installed and running. This is an
  additional system dependency beyond Python.
- BGE/BAAI (bge-base-en-v1.5) was disqualified outright: BAAI is a
  China-origin entity subject to federal supply chain restrictions.

---

## 2. LLM Inference: Ollama + vLLM

**What We Chose:** Ollama for single-GPU and laptop inference, with vLLM
as the high-throughput backend for dual-GPU workstation deployments.

**What We Considered:**

| Runtime | Notes |
|---|---|
| llama.cpp (direct) | C++ inference engine, maximum control |
| HuggingFace Transformers | Python-native, broadest model support |
| TGI (Text Generation Inference) | HuggingFace's production server |
| OpenLLM (BentoML) | Serving framework with model management |
| Commercial APIs only | OpenAI, Azure OpenAI, etc. |

**Why We Chose It:**

- Ollama wraps llama.cpp with zero-config model management (`ollama pull`,
  `ollama run`). No GGUF file wrangling, no quantization scripts.
- Supports all five approved models out of the box.
- vLLM adds continuous batching, PagedAttention, and tensor parallelism --
  critical for dual-RTX 3090 throughput under concurrent queries.
- Both are Apache 2.0 licensed. Both run fully offline.

**What We Gave Up:**

- Direct llama.cpp gives finer control over context window management,
  KV cache sizing, and quantization parameters. We accept Ollama's
  defaults for simplicity.
- Commercial-only (GPT-4, Azure OpenAI) would give better answer quality
  but eliminates offline capability -- a hard requirement for air-gapped
  and zero-trust deployments.
- TGI is mature but pulls in the HuggingFace dependency chain we retired.

---

## 3. Language Models: Approved 5-Model Stack

**What We Chose:**

| Model | Publisher | Params | Size | License | Role |
|---|---|---|---|---|---|
| phi4-mini | Microsoft | 3.8B | 2.3 GB | MIT | Laptop primary |
| mistral:7b | Mistral AI | 7B | 4.1 GB | Apache 2.0 | Laptop alternate |
| phi4:14b-q4_K_M | Microsoft | 14B | 9.1 GB | MIT | Workstation primary |
| gemma3:4b | Google | 4B | 3.3 GB | Apache 2.0 | PM summarization |
| mistral-nemo:12b | Mistral AI | 12B | 7.1 GB | Apache 2.0 | Workstation upgrade |

**What We Considered:**

| Model | Publisher | Why Disqualified |
|---|---|---|
| Llama 3.1 8B | Meta | License prohibits military use (ITAR conflict) |
| Qwen 3 8B | Alibaba | China-origin (supply chain ban) |
| DeepSeek-R1 8B | DeepSeek | China-origin (supply chain ban) |
| GPT-4 / GPT-4o | OpenAI | Cloud-only, per-token cost, no offline mode |

**Why We Chose It:**

- All publishers are US or EU headquartered (Microsoft, Mistral AI, Google).
- MIT and Apache 2.0 licenses carry no military-use or government-use
  restrictions.
- The stack scales from a laptop with 8 GB RAM (phi4-mini at 2.3 GB) to
  a dual-3090 workstation (mistral-nemo:12b at 7.1 GB, 128K context).
- Nine role-based profiles select the optimal model per use case without
  user intervention.

**What We Gave Up:**

- Meta Llama 3.1 has the best published benchmarks in the 7-13B range.
  Its Acceptable Use Policy explicitly prohibits use "by or for" military
  organizations, creating ITAR compliance risk. Performance loss is real.
- DeepSeek-R1 and Qwen 3 are competitive on reasoning benchmarks but are
  categorically excluded under supply chain policy.
- GPT-4 class quality is unmatched but requires internet connectivity and
  ongoing per-token spend. We support it as an optional online mode but do
  not depend on it.

---

## 4. Vector Storage: SQLite + Memmap (float16)

**What We Chose:** SQLite for metadata and BM25 search (via FTS5), with
memory-mapped float16 NumPy arrays for vector storage.

**What We Considered:**

| Solution | Type | License |
|---|---|---|
| FAISS | Library (Meta) | MIT |
| ChromaDB | Embedded vector DB | Apache 2.0 |
| Pinecone | Managed cloud | Proprietary |
| Weaviate | Self-hosted/cloud | BSD-3 |
| Qdrant | Self-hosted/cloud | Apache 2.0 |
| Milvus | Distributed vector DB | Apache 2.0 |
| pgvector | PostgreSQL extension | PostgreSQL License |

**Why We Chose It:**

- SQLite is Python stdlib (`sqlite3`) -- zero additional dependencies.
- Runs on 8 GB laptops without a database server process.
- FTS5 provides free keyword search that feeds the BM25 side of hybrid
  retrieval. One database file, one dependency.
- Crash-safe writes with deterministic chunk IDs enable incremental
  re-indexing without full rebuilds.
- Memmap float16 halves vector storage (768 dims x 2 bytes = 1.5 KB/vector
  vs 3 KB at float32) with negligible retrieval quality loss.

**What We Gave Up:**

- FAISS IVF indexing would be faster above 500K vectors. At our current
  scale (~40K chunks) brute-force cosine similarity over memmap is fast
  enough (<50ms). FAISS migration is planned if the corpus grows 10x.
- ChromaDB, Weaviate, and Qdrant add convenience APIs but require
  additional processes or cloud accounts.
- Milvus (Zilliz) was flagged for China-origin supply chain review and
  dropped from consideration.
- pgvector requires a PostgreSQL server -- too heavy for laptop deployment.

---

## 5. Search Strategy: Reciprocal Rank Fusion (RRF)

**What We Chose:** RRF with k=60 merging vector similarity and BM25
keyword ranked lists.

**What We Considered:**

| Strategy | Notes |
|---|---|
| Vector-only | Pure semantic search |
| BM25-only | Pure keyword search |
| SPLADE | Learned sparse retrieval |
| Weighted score fusion | Linear combination of normalized scores |

**Why We Chose It:**

- RRF merges ranked lists without requiring comparable score scales.
  Vector cosine similarity (0.0-1.0) and BM25 scores (unbounded positive)
  cannot be directly combined without normalization. RRF sidesteps this
  entirely by operating on rank positions.
- The single parameter k=60 comes from the original Cormack et al. paper
  and works well without per-dataset tuning.
- Hybrid retrieval catches both semantic matches ("RF band" retrieves
  "frequency range") and exact matches (part numbers like "XR-7742",
  acronyms like "MTBF").

**What We Gave Up:**

- SPLADE achieves better scores on BEIR benchmarks but requires training
  a sparse encoder -- adding model complexity and a HuggingFace dependency.
- Weighted score fusion can outperform RRF when weights are tuned per
  dataset, but our corpus spans 24+ document types with varying vocabulary
  density. Static weights would not generalize.
- Vector-only search misses exact part numbers. BM25-only search misses
  semantic paraphrases. Neither alone achieves our 98% pass rate.

---

## 6. Web Framework: FastAPI

**What We Chose:** FastAPI 0.115.0 with uvicorn ASGI server, binding to
localhost only (127.0.0.1:8000).

**What We Considered:**

| Framework | License | Notes |
|---|---|---|
| Flask | BSD-3 | Mature, sync-only WSGI |
| Django | BSD-3 | Full-stack, heavyweight |
| Starlette (raw) | BSD-3 | FastAPI's foundation |
| aiohttp | Apache 2.0 | Async HTTP client+server |

**Why We Chose It:**

- MIT license with no usage restrictions.
- Async-native: indexing operations run in background tasks without
  blocking the query endpoint.
- Automatic OpenAPI/Swagger documentation at /docs -- no manual spec
  maintenance.
- Pydantic v2 validation built into request/response models. Type errors
  are caught before hitting business logic.
- Lightweight: ~200 KB installed. uvicorn adds ~500 KB.

**What We Gave Up:**

- Flask has the largest Python web ecosystem (extensions, tutorials,
  hiring pool) but its synchronous WSGI model requires threading or
  Celery for concurrent indexing. Not worth the complexity.
- Django's ORM, admin panel, and auth system are unused -- pure overhead
  for a REST API serving a single application.
- Raw Starlette removes the Pydantic integration and dependency injection
  that make FastAPI ergonomic. Marginal performance gain is not worth the
  boilerplate.

---

## 7. GUI: tkinter

**What We Chose:** Python's built-in tkinter with ttk themed widgets and
lazy view switching.

**What We Considered:**

| Toolkit | License | Install Size |
|---|---|---|
| PyQt5/6 | GPL or Commercial | ~100 MB |
| PySide6 | LGPL | ~100 MB |
| wxPython | wxWindows License | ~50 MB |
| Electron | MIT | ~150 MB + Node.js |
| Web-based (Flask+browser) | Various | Requires browser |

**Why We Chose It:**

- Python stdlib: zero additional dependencies, zero additional download.
- Works fully offline with no browser, no JavaScript runtime, no Qt.
- No license fees. PyQt requires either GPL (copyleft, incompatible with
  proprietary distribution) or a commercial license (~$550/year).
- Lazy view switching delivers <1 ms panel transitions. Panels are built
  once on first access and swapped via `tkraise()`.
- Fast startup: the GUI loads in under 2 seconds on an 8 GB laptop.

**What We Gave Up:**

- Modern aesthetics. tkinter looks dated compared to Qt or Electron UIs.
  ttk themes help but do not close the gap.
- Rich widgets. No built-in chart library, no sortable table widget, no
  syntax-highlighted code views. We built a cost dashboard gauge and token
  breakdown manually.
- PySide6 (LGPL) was the closest runner-up but adds ~100 MB to the
  install and introduces C++ binary compatibility concerns across Windows
  versions.

---

## 8. HTTP Client: httpx

**What We Chose:** httpx 0.28.1 for all outbound HTTP communication.

**What We Considered:**

| Library | License | Async | HTTP/2 |
|---|---|---|---|
| requests | Apache 2.0 | No | No |
| urllib3 | MIT | No | No |
| aiohttp | Apache 2.0 | Yes | No |
| httpx | BSD-3 | Yes | Yes |

**Why We Chose It:**

- Dual-mode: synchronous and asynchronous APIs in a single library. The
  embedder uses sync calls; the API server uses async.
- HTTP/2 support reduces connection overhead for repeated calls to the
  same Ollama or Azure endpoint.
- Explicit timeout management with `httpx.Timeout` -- avoids the default
  5-second timeout that caused Azure OpenAI failures in production.
- Proxy auto-detection from Windows registry (corporate environments).
- BSD-3 license.

**What We Gave Up:**

- requests is the most popular Python HTTP library with the largest
  ecosystem of auth handlers and adapters. It lacks async support and
  HTTP/2 -- both features we actively use.
- aiohttp provides async but its API differs from requests, requiring
  developers to learn a new interface. httpx mirrors the requests API
  closely.

---

## 9. PDF Parsing: pdfplumber

**What We Chose:** pdfplumber for text and table extraction from PDF files,
with Tesseract OCR as a fallback for scanned documents.

**What We Considered:**

| Library | License | Notes |
|---|---|---|
| PyPDF2 | BSD-3 | Basic text extraction |
| pymupdf (fitz) | AGPL-3.0 | Fast, good quality, copyleft |
| pdfminer.six | MIT | Low-level PDF parsing |
| Camelot | MIT | Table-focused |
| tabula-py | MIT | Java dependency (tabula-java) |

**Why We Chose It:**

- MIT license -- no copyleft restrictions on distribution.
- Accurate table extraction preserving row/column structure. Critical for
  engineering specs with parameter tables.
- Text position preservation enables layout-aware chunking (headers,
  footers, columns detected by coordinate analysis).
- Pure Python -- no Java runtime (tabula-py) or C++ build tools required.

**What We Gave Up:**

- pymupdf (AGPL-3.0) is faster and produces higher-quality text output,
  especially for complex layouts. The AGPL license requires releasing
  source code of any application that uses it over a network --
  incompatible with proprietary deployment.
- PyPDF2 is simpler but produces lower-quality text extraction, especially
  for multi-column layouts and embedded tables.
- Camelot excels at table extraction but does not handle general text,
  requiring a second library for non-table content.

---

## 10. Credential Storage: Windows Credential Manager (keyring)

**What We Chose:** The `keyring` library (v23.13.1) backed by Windows
Credential Manager (DPAPI encryption).

**What We Considered:**

| Method | Encryption | Offline |
|---|---|---|
| .env files | None (plaintext) | Yes |
| Environment variables | None (process memory) | Yes |
| HashiCorp Vault | AES-256-GCM | Requires server |
| AWS Secrets Manager | AWS KMS | Requires internet |

**Why We Chose It:**

- DPAPI encryption tied to the Windows user login -- credentials are
  encrypted at rest and decryptable only by the logged-in user.
- No external server or cloud account required. Works fully offline.
- The `keyring` library provides a cross-platform abstraction. If the
  system moves to macOS (Keychain) or Linux (SecretService), no code
  changes are needed.
- Graceful fallback: if keyring is unavailable, the system prompts for
  credentials at runtime rather than failing silently.

**What We Gave Up:**

- Vault and AWS Secrets Manager provide audit trails, access policies,
  and secret rotation. These features are valuable at scale but require
  infrastructure we do not have in a single-user laptop deployment.
- .env files are simpler and widely understood but store secrets in
  plaintext on disk. A single `git add .env` mistake exposes everything.
- Environment variables persist in process memory and are visible via
  `/proc` on Linux or Task Manager on Windows.

---

## 11. Structured Logging: structlog

**What We Chose:** structlog for all application logging, producing JSON
output with context binding.

**What We Considered:**

| Library | License | Output Format |
|---|---|---|
| stdlib logging | PSF | Text (configurable) |
| loguru | MIT | Text (colored) |
| python-json-logger | BSD-2 | JSON |

**Why We Chose It:**

- JSON-structured output enables machine parsing and SIEM integration
  without log parsing rules.
- Context binding attaches metadata (session ID, query hash, model name)
  to every log entry within a processing scope.
- Apache 2.0 license.
- Composable processors: the same log event can be formatted as JSON for
  files and as colored text for console output simultaneously.

**What We Gave Up:**

- loguru has a simpler API (`logger.info("msg")` vs structlog's
  bound logger pattern) and produces attractive colored console output.
  It does not produce structured JSON natively.
- stdlib logging is zero-dependency but requires significant boilerplate
  to produce structured output and bind context.

---

## 12. Token Counting: tiktoken

**What We Chose:** tiktoken for accurate token counting and cost estimation
across all OpenAI-compatible models.

**What We Considered:**

| Library | License | Offline | Speed |
|---|---|---|---|
| transformers tokenizer | Apache 2.0 | Requires downloads | Moderate |
| sentencepiece | Apache 2.0 | Yes | Fast |
| Manual estimation | N/A | Yes | Instant |

**Why We Chose It:**

- MIT license with no usage restrictions.
- Fully offline: tokenizer data is bundled, no model downloads at runtime.
- Fast C extension: tokenizes 1M tokens/second, negligible overhead on
  query latency.
- Accurate for OpenAI model families (GPT-3.5, GPT-4, embeddings) which
  share the cl100k_base encoding. Cost estimates in the PM dashboard
  depend on exact token counts.

**What We Gave Up:**

- The `transformers` tokenizer supports every HuggingFace model but would
  re-introduce the HuggingFace dependency chain we retired in Session 15.
  This is a hard constraint, not a preference.
- sentencepiece handles Llama/Mistral tokenization natively but does not
  cover OpenAI encodings. Since we use tiktoken for cost tracking (which
  maps to OpenAI pricing), this gap is disqualifying.
- Manual estimation (~4 chars/token) introduces 10-20% error on technical
  documents with long compound words and abbreviations.

---

## Summary Table

| # | Component | Chosen | Primary Alternative | Key Decision Factor |
|---|---|---|---|---|
| 1 | Embedding model | nomic-embed-text | MiniLM-L6-v2 | 768 dims, no HuggingFace dependency |
| 2 | LLM inference | Ollama + vLLM | llama.cpp direct | Zero-config model management |
| 3 | Language models | phi4-mini + 4 others | Llama 3.1 8B | License and supply chain compliance |
| 4 | Vector storage | SQLite + memmap f16 | FAISS | Zero dependencies, runs on 8 GB laptop |
| 5 | Search strategy | RRF (k=60) | Weighted score fusion | No score normalization needed |
| 6 | Web framework | FastAPI | Flask | Async-native, auto OpenAPI docs |
| 7 | GUI toolkit | tkinter | PySide6 | Python stdlib, zero install, no GPL |
| 8 | HTTP client | httpx | requests | Async + sync, HTTP/2 support |
| 9 | PDF parser | pdfplumber | pymupdf | MIT license (vs AGPL) |
| 10 | Credentials | keyring (Win DPAPI) | .env files | Encrypted at rest, offline |
| 11 | Logging | structlog | loguru | JSON output, context binding |
| 12 | Token counting | tiktoken | transformers tokenizer | Offline, no HuggingFace dependency |

---

*End of document.*
