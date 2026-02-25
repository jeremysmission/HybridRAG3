# Development Inventory -- HybridRAG v3

**Date:** 2026-02-23
**Status:** Living document -- updated each development session

This inventory categorizes all software, models, and infrastructure into
three tiers:

- **Tier 1 -- Approved & Wired:** Currently installed, tested, passing regression suite.
- **Tier 2 -- Designed In, Pending Approval:** Code paths exist but require hardware, license confirmation, or store approval before activation.
- **Tier 3 -- Planned, Not Yet Designed:** On the roadmap but no code written yet.

---

## Tier 1: Approved & Wired (Currently Deployed)

### Python Runtime & Core Libraries

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| Python | 3.12rc3 (work) / 3.11.9 (home) | PSF-2.0 | Runtime |
| pydantic | 2.11.1 | MIT | Data validation (config, API models) |
| pyyaml | 6.0.2 | MIT | Config file parsing |
| structlog | 24.4.0 | MIT | Structured logging |
| rich | 13.9.4 | MIT | Console formatting |
| tqdm | 4.67.3 | MIT | Progress bars (CLI) |
| cryptography | 44.0.2 | Apache 2.0 | Credential encryption |

### Embedding & NLP

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| sentence-transformers | 2.7.0 | Apache 2.0 | Embedding model loader |
| torch | 2.10.0 | BSD-3 | Tensor computation (CPU-only wheel) |
| transformers | 4.57.6 | Apache 2.0 | Model architecture definitions |
| tokenizers | 0.22.2 | Apache 2.0 | Fast tokenization |
| huggingface_hub | 0.36.1 | Apache 2.0 | One-time model download |
| safetensors | 0.7.0 | Apache 2.0 | Safe model weight loading |
| tiktoken | 0.8.0 | MIT | Token counting (offline) |
| numpy | 1.26.4 | BSD-3 | Vector operations + memmap storage |
| scipy | 1.17.0 | BSD-3 | Scientific computation |
| scikit-learn | 1.8.0 | BSD-3 | BM25 + sparse retrieval |

### Embedding Models (Local, No API)

| Model | Dimensions | Size | License | Origin | Status |
|-------|-----------|------|---------|--------|--------|
| nomic-embed-text | 768 | 274 MB | Apache 2.0 | Nomic AI/USA | INSTALLED -- served by Ollama, primary for all profiles |

### Document Parsers

| Format | Library | Version | License |
|--------|---------|---------|---------|
| PDF (primary) | pypdf | 6.6.2 | BSD-3 |
| PDF (fallback) | pdfplumber | 0.11.9 | MIT |
| PDF (mining) | pdfminer.six | 20251230 | MIT |
| PDF (rendering) | pypdfium2 | 5.3.0 | Apache 2.0 |
| PDF OCR | pytesseract | 0.3.13 | Apache 2.0 |
| Images | pillow | 12.1.0 | HPND |
| DOCX | python-docx | 1.2.0 | MIT |
| PPTX | python-pptx | 1.0.2 | MIT |
| XLSX (read) | openpyxl | 3.1.5 | MIT |
| XLSX (write) | xlsxwriter | 3.2.9 | BSD-2 |
| XML/HTML | lxml | 6.0.2 | BSD-3 |

### HTTP & Networking

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| openai | 1.45.1 | MIT | OpenAI-compatible API client (pinned v1.x) |
| httpx | 0.28.1 | BSD-3 | Async HTTP (openai dependency) |
| requests | 2.32.5 | Apache 2.0 | HTTP client (fallback) |
| urllib3 | 2.6.3 | MIT | Low-level HTTP |

### Web Server (REST API)

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| fastapi | 0.115.0 | MIT | REST API framework |
| uvicorn | 0.41.0 | BSD-3 | ASGI server |
| starlette | 0.38.6 | BSD-3 | HTTP toolkit (DoS fix in 0.38.2+) |
| python-multipart | 0.0.22 | Apache 2.0 | Form data parsing |

### Offline LLM Models (Ollama-Served)

| Model | Parameters | Size (GB) | VRAM (GB) | License | Origin | Status |
|-------|-----------|----------|----------|---------|--------|--------|
| phi4-mini | 3.8B | 2.3 | 5.5 | MIT | Microsoft/USA | INSTALLED -- primary for 7/9 profiles |
| mistral:7b | 7B | 4.1 | 5.5 | Apache 2.0 | Mistral/France | INSTALLED -- alt for eng/sys/fe/cyber |
| phi4:14b-q4_K_M | 14B | 9.1 | 11.0 | MIT | Microsoft/USA | DOWNLOADING -- logistics primary, CAD alt |
| gemma3:4b | 4B | 3.3 | 4.0 | Apache 2.0 | Google/USA | DOWNLOADING -- PM fast summarization |
| mistral-nemo:12b | 12B | 7.1 | 10.0 | Apache 2.0 | Mistral+NVIDIA | DOWNLOADING -- upgrade path (128K ctx) |

**Total approved stack: ~26 GB**

### Retrieval Engine

| Component | Technology | Notes |
|-----------|-----------|-------|
| Vector store | SQLite + NumPy memmap | Custom, public domain + BSD |
| Full-text search | SQLite FTS5 (BM25) | Built-in, no extra dependency |
| Hybrid retrieval | Vector + BM25 via Reciprocal Rank Fusion (RRF) | k=60 |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Available, disabled for eval stability |
| Embeddings | float16 memmap (~50% storage vs float32) | 78.83 MB for 39,602 chunks |

### GUI

| Component | Technology | Notes |
|-----------|-----------|-------|
| Framework | tkinter (Python stdlib) | Zero external dependencies |
| Panels | Query, Data, Index, Settings, Cost, Reference | Single-window view switching |
| Theme | Dark/Light toggle | VS Code-style dark default |

### Security Infrastructure

| Layer | Mechanism | Notes |
|-------|----------|-------|
| Network gate | HF_HUB_OFFLINE=1 + empty API default | 3-layer lockdown |
| Credential storage | Windows Credential Manager | OS-level encryption |
| Audit logging | structlog | app/error/audit/cost log rotation |
| API endpoint validation | SEC-001 fail-closed | Empty default = no leakage |

### Bulk Transfer Engine

| Component | Status | Notes |
|-----------|--------|-------|
| bulk_transfer_v2.py | COMPLETE | 8-thread parallel, atomic copy, SHA-256 verify |
| transfer_manifest.py | COMPLETE | SQLite tracking, delta sync, resume support |
| transfer_staging.py | COMPLETE | 3-stage: incoming -> verified -> quarantine |
| GUI wrapper (data_panel.py) | COMPLETE | Drive detection, progress polling, live stats |

---

## Tier 2: Designed In, Pending Approval

These have code paths written and configurations defined, but require
hardware delivery, license paperwork, or store approval before activation.

### vLLM Inference Server

| Item | Detail |
|------|--------|
| Package | vllm==0.10.1 |
| License | Apache 2.0 (UC Berkeley/USA) |
| Config | src/core/config.py VLLMConfig (enabled: false) |
| Purpose | OpenAI-compatible local API with continuous batching, prefix caching, tensor parallelism |
| Blocker 1 | Requires dual RTX 3090 workstation (arriving soon) |
| Blocker 2 | Requires openai>=1.99.1 (conflicts with current openai==1.45.1 pin) |
| Waiver Note | **Must request vllm AND openai>=1.99.1 together** -- both packages needed on same waiver |
| Activation | Set `vllm.enabled: true` in YAML once hardware verified |
| Current Status | Commented out of requirements_approved.txt -- not needed for demo |

### Direct HuggingFace Transformers Inference

| Item | Detail |
|------|--------|
| Package | transformers==4.57.6 (already installed) |
| Config | src/core/config.py TransformersConfig (enabled: false) |
| Purpose | Load models directly into GPU without Ollama/vLLM server |
| Feature | 4-bit quantization (bitsandbytes) to fit 14B models in 12GB VRAM |
| Blocker | Requires GPU workstation + bitsandbytes store approval |

### Desktop/Server Embedding Upgrades

| Model | Dimensions | Size | License | Origin | Profile |
|-------|-----------|------|---------|--------|---------|
| nomic-ai/nomic-embed-text-v1.5 | 768 | 274 MB | Apache 2.0 | Nomic AI/USA | desktop_power |
| snowflake-arctic-embed-l-v2.0 | 1024 | 1.1 GB | Apache 2.0 | Snowflake/USA | server_max |

Both are wired into `config/profiles.yaml` but require CUDA hardware to activate.

### FAISS Vector Index

| Item | Detail |
|------|--------|
| Package | faiss-cpu==1.9.0 |
| License | MIT (Meta, but library itself is MIT-licensed) |
| Purpose | GPU-accelerated approximate nearest neighbor search |
| Config | Listed in requirements_approved.txt |
| Blocker | Currently using SQLite+memmap; migration planned for workstation |

### Larger Offline Model Tier

| Model | Parameters | Size (GB) | VRAM (GB) | License | Origin |
|-------|-----------|----------|----------|---------|--------|
| mistral-small3.1:24b | 24B | 14 | 16 | Apache 2.0 | Mistral/France |

Fits on a single RTX 3090. Defined in `scripts/_model_meta.py` PERSONAL_FUTURE dict.

### Online Model Knowledge Base (40+ Models)

The `scripts/_model_meta.py` KNOWN_MODELS dict contains curated metadata for
40+ cloud models from OpenAI, Mistral, Google, Amazon, and xAI. These are
used for the GUI's model selection treeview when running in online mode.
Use-case scoring and ranking are fully wired. Activation requires:

- Store-approved API endpoint
- API key stored in Windows Credential Manager
- Mode switch to "online" in GUI

### Hardware Profiles (3 Tiers)

| Profile | RAM | GPU | Default LLM | Embedding | Status |
|---------|-----|-----|-------------|-----------|--------|
| laptop_safe | 8-16 GB | None/iGPU | phi4-mini (CPU) | MiniLM-L6 (384d, CPU) | ACTIVE |
| desktop_power | 64 GB | 12 GB VRAM | mistral-nemo:12b | nomic-embed (768d, CUDA) | DESIGNED |
| server_max | 64+ GB | 24+ GB VRAM | phi4:14b-q4_K_M | arctic-embed-l (1024d, CUDA) | DESIGNED |

Profile switching is wired in `scripts/_set_model.py` and the GUI TuningTab.

---

## Tier 3: Planned, Not Yet Designed

These appear on the roadmap or in architecture docs but have no code paths yet.

### PII Sanitization Pipeline -- IMPLEMENTED

| Item | Detail |
|------|--------|
| Config flag | security.pii_sanitization: true |
| Module | src/security/pii_scrubber.py (~65 lines, pure regex) |
| Purpose | Auto-redact emails, phones, SSNs, credit cards, IPv4 before online API calls |
| Scope | Wired into APIRouter.query() in src/core/llm_router.py (online path only) |
| GUI | Toggle in Settings > API & Admin > Security & Privacy section |
| Dependencies | None (stdlib re module only) |
| Tests | tests/test_pii_scrubber.py (16 tests, all passing) |

### Hallucination Guard (Full Implementation)

| Item | Detail |
|------|--------|
| Config | hallucination_guard section exists with all parameters |
| Stub | guard_config.py has dataclass, but NLI model inference is not wired |
| Model | cross-encoder/nli-deberta-v3-base (config reference) |
| Features defined | Dual-path verification, chunk pruning, short-circuit thresholds |
| Blocker | NLI model adds 200+ MB download + inference latency |

### Enterprise Credential Store (HashiCorp Vault)

Referenced in architecture docs as future enterprise option. Currently
using Windows Credential Manager (sufficient for single-user deployment).

### Multi-User Concurrent Access

Current architecture is single-user (one SQLite database, one Ollama
instance). Multi-user would require:
- Database connection pooling or migration to PostgreSQL
- Auth layer on FastAPI endpoints
- Per-user query isolation

### Semantic Chunking

Current chunker is character-based (1200 chars, 200 overlap). Semantic
chunking (split on topic/paragraph boundaries) is referenced in architecture
docs but not implemented. Would require:
- Sentence boundary detection
- Topic segmentation model
- Recursive splitting fallback

### PDF Table Extraction

Current PDF parsers extract text but do not preserve table structure.
Dedicated table extraction (e.g., camelot, tabula) would improve accuracy
for engineering specs with data tables.

### Real-Time Index Updates

Current indexing is batch-only (user clicks "Start Indexing"). File system
watching for incremental updates is planned but not designed.

---

## Disqualified Software (Reference Only)

The following were evaluated and rejected. Retained here so procurement
does not re-evaluate them.

### Banned Model Families

| Family | Publisher | Reason | Status |
|--------|-----------|--------|--------|
| Qwen (all variants) | Alibaba | NDAA compliance | PERMANENTLY BANNED |
| DeepSeek (all variants) | DeepSeek | NDAA compliance | PERMANENTLY BANNED |
| BGE/BAAI embeddings | BAAI | NDAA compliance | PERMANENTLY BANNED |
| Llama (all Meta models) | Meta | ITAR AUP restriction | PERMANENTLY BANNED |

### Banned Libraries

| Library | Reason |
|---------|--------|
| LangChain | Dependency hell (200+ transitive deps), version churn |
| ChromaDB | Windows compatibility issues, heavy dependencies |
| PyMuPDF (fitz) | AGPL license (copyleft, incompatible with deployment) |

### Version-Locked Packages

| Package | Pinned At | Reason |
|---------|----------|--------|
| openai | 1.45.1 | v2.x has breaking changes; pinned to 1.x until vllm waiver requires upgrade to >=1.99.1 |
| numpy | 1.26.4 | Last 1.x release; 2.x has breaking API changes |
| pydantic | 2.11.1 | Store-approved version |
| cryptography | 44.0.2 | Store-approved version |

---

## Test Baseline (as of 2026-02-23)

| Suite | Pass | Fail | Skip | Duration |
|-------|------|------|------|----------|
| Regression (pytest) | 199 | 0 | 2 | 30s |
| Virtual tests | 540 | 4 | -- | -- |
| Diagnostics | 15 | 0 | -- | 20s |
| FastAPI server | 17 | 0 | -- | separate |

**Indexed corpus:** 39,602 chunks from 1,345 source files (78.83 MB)

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| HYBRIDRAG_DATA_DIR | Sets database + embeddings_cache paths | (none) |
| HYBRIDRAG_INDEX_FOLDER | Sets source_folder path | (none) |
| HYBRIDRAG_API_ENDPOINT | API endpoint for online mode | (none) |
| HYBRIDRAG_PROJECT_ROOT | Project root for config file resolution | "." |
| HYBRIDRAG_EMBED_BATCH | Embedding batch size override | 16 |
| HYBRIDRAG_RETRIEVAL_BLOCK_ROWS | Memmap block size override | 25000 |
| HYBRIDRAG_OCR_FALLBACK | Enable OCR for scanned PDFs | false |
| HYBRIDRAG_ADMIN_MODE | Bypass network gate for maintenance | false |
| HF_HUB_OFFLINE | Block HuggingFace Hub network access | 1 |

---

## Recent Hardware & Software Changes (Session Log)

### Session 12 (2026-02-21): Software Audit & Model Replacement

**Software Version Downgrades (Store Compliance):**

| Package | Before | After | Impact |
|---------|--------|-------|--------|
| openai | 2.20.0 | 1.45.1 | Zero code changes; v1.x API pinned permanently |
| pydantic | 2.12.5 | 2.11.1 | Zero code changes; store-approved version |
| cryptography | 46.0.4 | 44.0.2 | Zero code changes; store-approved version |

All 84 pytest tests passed after downgrade. Zero regressions.

**Model Stack Replacement:**

Removed 3 non-compliant models and replaced with approved alternatives:

| Removed | Replaced With | Reason |
|---------|--------------|--------|
| qwen3:8b (Alibaba/China) | phi4-mini (Microsoft/USA) | NDAA compliance |
| deepseek-r1:8b (China) | mistral:7b (Mistral/France) | NDAA compliance |
| llama3.1:8b (Meta) | phi4-mini (Microsoft/USA) | ITAR AUP restriction |

All 9 profiles updated across `_model_meta.py`, `_set_model.py`, and
`validate_offline_models.py`. Net result: 5-model approved stack (26 GB total).

**New Infrastructure Added:**

| Component | Purpose | Improvement |
|-----------|---------|-------------|
| FastAPI REST API | Remote query access | 7 endpoints, localhost-only, 17 tests |
| vLLM config | Workstation inference | Continuous batching, tensor parallelism (not yet active) |
| TransformersRouter | Direct GPU inference | No Ollama server needed, 4-bit quantization support |
| Network gate v2 | 3-layer lockdown | Offline mode blocks ALL outbound by default |
| Credential Manager | OS-level encryption | Replaced env-var-only approach |

### Session 13 (2026-02-22): PM Cost Dashboard

| Component | Lines | Improvement |
|-----------|-------|-------------|
| cost_tracker.py | 481 | Singleton SQLite + in-memory, auto-flush, listener pattern |
| cost_dashboard.py | 518 | Big numbers, budget gauge, ROI calculator, CSV export |
| 19 new tests | -- | Full coverage of cost tracking + ROI calculations |

**Business Impact:** Real-time visibility into API spend with team-level
projection. ROI calculator uses BLS and McKinsey benchmarks.

### Session 14 (2026-02-23): GUI Wiring Fixes + Data Panel

| Change | Before | After | Improvement |
|--------|--------|-------|-------------|
| Mode persistence | Reverts on restart | Saved to YAML | Mode survives app restart |
| Offline API fields | Editable but useless | Grayed out with note | No user confusion |
| Data Transfer panel | CLI-only | Full GUI wrapper | Browse -> Transfer -> Index pipeline |
| NavBar | 4 tabs | 5 tabs (added "Data") | Complete workflow in GUI |

**Data Panel features:**
- Windows drive detection (GetLogicalDrives API)
- Folder browser with UNC path support
- Background source preview (file count, size, top-10 extensions)
- Live transfer progress (speed, ETA, copied/dedup/skip/err)
- 500ms polling of thread-safe engine stats
- Post-transfer navigation to Index panel

### Workstation Upgrade Path (Hardware Arriving)

**Current laptop limitations:**
- 8 GB RAM, 512 MB VRAM (Intel Iris Xe)
- Cannot run Ollama 3B+ models locally
- CPU-only embedding (batch size 16)
- Single-thread query processing

**Workstation capabilities (when delivered):**

| Capability | Current (Laptop) | Workstation | Multiplier |
|-----------|-------------------|-------------|------------|
| GPU VRAM | 512 MB (iGPU) | 48 GB (dual 3090) | 96x |
| System RAM | 8 GB | 64 GB | 8x |
| LLM model size | 3.8B (phi4-mini, CPU) | 14B (phi4:14b, GPU) | 3.7x params |
| Embedding model | MiniLM-L6 (384d, 80MB) | Arctic-embed-L (1024d, 1.1GB) | 2.7x dims |
| Embedding batch | 16 | 128 | 8x throughput |
| Context window | 8,192 tokens | 16,384+ tokens | 2x |
| Inference engine | Ollama (single model) | vLLM (batched, 2-GPU parallel) | ~3x speed |
| Concurrent files | 1 | 4 | 4x indexing speed |

**Designed-in code paths ready to activate:**
1. `vllm.enabled: true` in config YAML
2. `desktop_power` or `server_max` profile in GUI
3. TransformersRouter for direct GPU loading with 4-bit quantization
4. Larger embedding models (768d or 1024d) via profile switch

---

## Quick Reference: File Locations

| Component | Path |
|-----------|------|
| Main config | config/default_config.yaml |
| Hardware profiles | config/profiles.yaml |
| Model metadata | scripts/_model_meta.py |
| Model setter | scripts/_set_model.py |
| Query engine | src/core/query_engine.py |
| Transfer engine | src/tools/bulk_transfer_v2.py |
| REST API | src/api/server.py, routes.py, models.py |
| GUI entry | src/gui/launch_gui.py |
| GUI app | src/gui/app.py |
| Cost tracker | src/core/cost_tracker.py |
| Network gate | src/core/network_gate.py |
| Credentials | src/security/credentials.py |
| Requirements | requirements.txt, requirements_approved.txt |
