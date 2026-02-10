# HybridRAG v3 -- Personal Learning Project

> **Educational / Personal Development Project**
> Built as a hands-on learning exercise in AI systems engineering, Python
> development, and secure application design. This project demonstrates
> Retrieval-Augmented Generation (RAG) concepts through a working prototype
> that indexes documents and answers natural language questions about them.
>
> All packages are open-source from PyPI (Python Package Index), managed by
> the Python Software Foundation. All processing runs locally with no cloud
> dependencies at runtime.

## What This Project Demonstrates

- **RAG Pipeline Architecture**: Document parsing, chunking, embedding, vector storage, semantic retrieval, LLM-augmented answers
- **Hybrid Search**: Combining vector similarity (semantic) with keyword matching (FTS5) via Reciprocal Rank Fusion
- **Offline-First Design**: Runs entirely on a local machine with no internet dependency after initial setup
- **Online API Mode**: Optional mode routes queries to company GPT-3.5 Turbo for faster responses (2-5 seconds vs 180 seconds)
- **Secure Credential Management**: API keys stored in Windows Credential Manager (DPAPI encrypted), never in files or git
- **Performance Profiles**: Three hardware profiles (laptop_safe, desktop_power, server_max) for different machines
- **Security Engineering**: 3-layer network lockdown, audit logging, defense-in-depth
- **Diagnostic Engineering**: Automated 3-tier test suite with hardware profiling, fault analysis, and security auditing
- **Zero External Servers**: SQLite for storage, local embedding model, optional local LLM via Ollama

## Quick Start

```powershell
# 1. Navigate to the project folder
cd "D:\HybridRAG3"

# 2. Create a virtual environment (match Python version across machines)
py -3.11 -m venv .venv

# 3. Activate it
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies (one-time, requires internet)
pip install -r requirements.txt

# 5. Launch the environment (sets security lockdown + paths)
. .\start_hybridrag.ps1

# 6. Run diagnostics to verify installation
rag-diag
```

After initial setup, steps 2-4 are never needed again. Daily use starts at step 5.

See `docs/SETUP.md` for detailed first-time installation instructions.

## Daily Use

```powershell
# Launch environment (always run first)
. .\start_hybridrag.ps1

# Or double-click start_rag.bat from File Explorer

# Index your documents
rag-index

# Query
rag-query "What is the operating frequency range?"

# Check system health
rag-diag
rag-status
```

## Commands Reference

### Core Commands
```
rag-paths              Show configured paths + network status
rag-index              Start indexing
rag-query "question"   Query the index
rag-diag               Run diagnostics (add --verbose, --test-embed)
rag-status             Quick health check
```

### API Mode Commands
```
rag-store-key          Store API key (DPAPI encrypted in Windows Credential Manager)
rag-store-endpoint     Store custom API endpoint URL
rag-cred-status        Check what credentials are stored and where
rag-cred-delete        Remove stored credentials
rag-mode-online        Switch to API mode (queries go to company GPT)
rag-mode-offline       Switch to Ollama mode (queries stay local)
rag-test-api           Test API connectivity (sends one test prompt)
```

### Performance Profile Commands
```
rag-profile            Show current profile
rag-profile status     Show current profile (same as above)
rag-profile laptop_safe       8-16GB RAM, batch=16, conservative
rag-profile desktop_power     32-64GB RAM, batch=64, aggressive
rag-profile server_max        64GB+ RAM, batch=128, maximum throughput
```

## Modes of Operation

### Offline Mode (default)
- Uses Ollama running locally (localhost:11434)
- No internet required after setup
- Response time: ~5-10 seconds (GPU) or ~180 seconds (CPU only)
- Best for: Air-gapped environments, SCIFs, field use

### Online Mode
- Uses company GPT-3.5 Turbo API via intranet
- Requires API key stored in Windows Credential Manager
- Response time: ~2-5 seconds
- Best for: Daily use when on company network
- Cost: ~$0.002 per query ($1 buys ~500 queries)

## Configuration

### Machine-Specific Paths

Edit `start_hybridrag.ps1` to set your data and source paths:

```powershell
# These paths are different on each machine:
$DATA_DIR   = "D:\RAG Indexed Data"     # Where SQLite + embeddings go
$SOURCE_DIR = "D:\RAG Source Data"       # Where your documents are
```

### Performance Profiles

Switch profiles based on your hardware:

```powershell
rag-profile laptop_safe       # Work laptop (16GB RAM)
rag-profile desktop_power     # Power desktop (32-64GB RAM)
rag-profile server_max        # Server/workstation (64GB+ RAM)
```

## Security Model

Three independent layers prevent any accidental network calls at runtime:

| Layer | What It Blocks | How |
|-------|---------------|-----|
| PowerShell (start_hybridrag.ps1) | HuggingFace + transformers | Session environment variables |
| Python (embedder.py) | HuggingFace in ANY Python process | os.environ enforcement before import |
| Config (SEC-001) | LLM queries to public endpoints | Empty API endpoint default |

All three must fail before data leaves the machine.

### Credential Security
- API keys stored in Windows Credential Manager (DPAPI encrypted)
- Keys tied to your Windows login -- other users cannot read them
- Keys never appear in config files, logs, or git history
- rag-cred-status shows masked preview only (first 8 + last 4 characters)

## Project Structure

```
HybridRAG3/
|
|-- config/                         Settings
|   |-- default_config.yaml         All settings (paths, models, thresholds)
|   |-- profiles.yaml               Hardware profile definitions
|   +-- system_profile.json         Auto-detected hardware fingerprint
|
|-- src/
|   |-- core/                       Core pipeline
|   |   |-- config.py               Config loader, validation, dataclasses
|   |   |-- indexer.py              File scanning, parsing, chunking, embedding
|   |   |-- chunker.py             Text to chunks with heading detection
|   |   |-- chunk_ids.py           Deterministic chunk ID generation
|   |   |-- embedder.py            all-MiniLM-L6-v2 text to vector
|   |   |-- vector_store.py        SQLite + memmap storage, FTS5 search
|   |   |-- retriever.py           Hybrid search (vector + BM25 RRF)
|   |   |-- query_engine.py        Search to LLM to answer pipeline
|   |   |-- llm_router.py          Ollama (offline) / GPT API (online) routing
|   |   |-- health_checks.py       System health verification
|   |   +-- sqlite_utils.py        SQLite helpers
|   |
|   |-- parsers/                    Document parsers
|   |   |-- registry.py            File extension to parser mapping
|   |   |-- pdf_parser.py          PDF text extraction (pdfplumber)
|   |   |-- pdf_ocr_fallback.py    OCR fallback for scanned PDFs
|   |   |-- office_docx_parser.py  Word document parser
|   |   |-- office_pptx_parser.py  PowerPoint parser
|   |   |-- office_xlsx_parser.py  Excel parser
|   |   |-- eml_parser.py          Email parser
|   |   |-- image_parser.py        OCR via Tesseract
|   |   +-- plain_text_parser.py   TXT, MD, CSV, JSON, XML, LOG, etc.
|   |
|   |-- security/                   Credential management
|   |   |-- __init__.py            Package marker
|   |   +-- credentials.py         Windows Credential Manager integration
|   |
|   |-- diagnostic/                 Testing and diagnostics
|   |   |-- hybridrag_diagnostic.py Main diagnostic runner
|   |   |-- health_tests.py        Pipeline health checks (15 tests)
|   |   |-- component_tests.py     Individual component tests
|   |   |-- perf_benchmarks.py     Performance benchmarks
|   |   |-- fault_analysis.py      Automated fault hypothesis engine
|   |   +-- report.py              Report formatting and output
|   |
|   |-- tools/                      Utility scripts
|   |   |-- system_diagnostic.py   Diagnostic entry point
|   |   |-- run_index_once.py      Main indexing entry point
|   |   |-- index_status.py        Database status checker
|   |   |-- quick_test_retrieval.py Retrieval testing utility
|   |   |-- check_db_status.py     Database health check
|   |   |-- migrate_embeddings_to_memmap.py  One-time migration tool
|   |   |-- rebuild_memmap_from_sqlite.py    Memmap recovery tool
|   |   +-- scan_model_caches.ps1  Find model cache locations
|   |
|   |-- monitoring/                 Logging and tracking
|   |   |-- logger.py              Structured logging setup
|   |   +-- run_tracker.py         Indexing run audit trail
|   |
|   +-- gui/                        GUI (placeholder for future)
|       +-- __init__.py            Package marker
|
|-- scripts/                        Helper scripts for PowerShell commands
|   |-- _check_creds.py           Check credential status
|   |-- _set_online.py            Set config mode to online
|   |-- _set_offline.py           Set config mode to offline
|   |-- _test_api.py              API connectivity test
|   |-- _profile_status.py        Show current performance profile
|   +-- _profile_switch.py        Switch performance profile
|
|-- tests/
|   +-- cli_test_phase1.py         rag-query entry point
|
|-- docs/                           Documentation
|   |-- ARCHITECTURE.md            System design, security model
|   |-- SETUP.md                   Detailed installation instructions
|   |-- NETWORK_SECURITY_EXPLAINER.md  Network isolation design
|   |-- PERFORMANCE_BASELINE.md    Performance benchmarks and tuning
|   |-- SOURCE_BOUNDED_GENERATION.md   LLM context grounding
|   |-- SYSTEM_STATE.md            Current system state
|   +-- schematic_conversion_schema.md  Schema documentation
|
|-- api_mode_commands.ps1           API mode + profile PowerShell commands
|-- api_mode_simulation.py          Deployment dry-run diagnostic
|-- API_MODE_REVIEW.md              API mode code review and bug analysis
|-- start_hybridrag.ps1             Environment setup + aliases (machine-specific)
|-- start_rag.bat                   Double-click launcher for start_hybridrag.ps1
|-- requirements.txt                Python dependencies (what we want)
|-- requirements-lock.txt           Python dependencies (exact versions installed)
|-- .gitignore                      Files excluded from git
+-- README.md                       This file
```

## Data Directories (not in git, local to each machine)

```
.venv/                              Python virtual environment
.model_cache/                       Embedding model (all-MiniLM-L6-v2, 87MB)
.hf_cache/                          HuggingFace cache
.torch_cache/                       PyTorch cache
logs/                               Diagnostic and run logs

D:\RAG Indexed Data\                Outside the project folder
|-- hybridrag.sqlite3               Chunks, metadata, FTS5, run history
|-- embeddings.f16.dat              Memory-mapped float16 vectors
+-- embeddings_meta.json            Memmap bookkeeping
```

## Supported File Formats

| Format | Extensions | Parser | Notes |
|--------|-----------|--------|-------|
| PDF | .pdf | pdfplumber | Text-based PDFs. OCR fallback for scanned. |
| Word | .docx | python-docx | |
| PowerPoint | .pptx | python-pptx | |
| Excel | .xlsx | openpyxl | |
| Email | .eml | stdlib email | Extracts body + attachments |
| Images | .png .jpg .tif .bmp .gif .webp | Tesseract OCR | Requires Tesseract installed |
| Plain text | .txt .md .csv .json .xml .log .yaml .ini | direct read | |

## Technology Stack

All packages sourced from PyPI (pypi.org) -- open-source with permissive licenses.

| Component | Package | License | Purpose |
|-----------|---------|---------|---------|
| Embeddings | sentence-transformers | Apache 2.0 | Text to vector conversion |
| ML Backend | torch (PyTorch) | BSD-3 | Tensor computation (CPU + GPU) |
| Tokenizer | transformers | Apache 2.0 | Text tokenization |
| Vector Math | numpy | BSD-3 | Numerical computation |
| ML Utilities | scikit-learn | BSD-3 | Distance metrics |
| Database | sqlite3 (built-in) | Public Domain | Metadata + keyword search |
| PDF Parsing | pdfplumber, pypdf | MIT | Document text extraction |
| Office Docs | python-docx, python-pptx, openpyxl | MIT | Word, PowerPoint, Excel |
| Imaging | pillow | MIT-like | Image processing for OCR |
| XML/HTML | lxml | BSD-3 | Document parsing |
| HTTP Client | httpx | BSD-3 | API calls (online mode only) |
| Credentials | keyring | MIT | Windows Credential Manager access |
| Encryption | cryptography | Apache 2.0 / BSD-3 | Credential encryption |
| Logging | structlog | Apache 2.0 | Structured event logging |
| Config | PyYAML | MIT | YAML configuration files |
| Token Count | tiktoken | MIT | Token counting for cost estimates |

## Requirements

- Windows 10/11
- Python 3.11 (tested on 3.11.9, must match across machines)
- ~3 GB disk space (venv + model cache)
- Ollama (optional, for offline LLM mode)
- Tesseract (optional, for OCR on scanned documents)
- See `requirements.txt` for Python dependencies

## Documentation

- `docs/SETUP.md` -- Detailed installation and deployment instructions
- `docs/ARCHITECTURE.md` -- System design, security model, technical decisions
- `docs/NETWORK_SECURITY_EXPLAINER.md` -- Network isolation design
- `docs/PERFORMANCE_BASELINE.md` -- Performance benchmarks and tuning
- `docs/SOURCE_BOUNDED_GENERATION.md` -- LLM context grounding design
- `API_MODE_REVIEW.md` -- API mode code review and bug analysis
- `config/profiles.yaml` -- Hardware performance profiles

## Multi-Machine Deployment

This project runs on multiple machines. Code syncs via GitHub, but some files
are machine-specific:

**Syncs via git (same on all machines):**
- All source code (src/, scripts/, tests/)
- Config templates (config/default_config.yaml, config/profiles.yaml)
- Documentation (docs/, README.md)
- Requirements files

**Machine-specific (do NOT overwrite between machines):**
- start_hybridrag.ps1 (different paths per machine)
- .gitignore (may have machine-specific entries)
- .venv/ (different Python builds)
- .model_cache/, .hf_cache/, .torch_cache/ (downloaded locally)
- API keys (stored in Windows Credential Manager, local to each login)

## License

Educational and personal learning use.
