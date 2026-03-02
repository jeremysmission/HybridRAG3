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
- **Online API Mode**: Optional mode routes queries to a cloud LLM API for faster responses (2-5 seconds vs 180 seconds)
- **Secure Credential Management**: API keys stored in Windows Credential Manager (DPAPI encrypted), never in files or git
- **Performance Profiles**: Three hardware profiles (laptop_safe, desktop_power, server_max) for different machines
- **Security Engineering**: 3-layer network lockdown, audit logging, layered security
- **Diagnostic Engineering**: Automated 3-tier test suite with hardware profiling, fault analysis, and security auditing
- **Zero External Servers**: SQLite for storage, local embedding model, optional local LLM via Ollama

## Quick Start

```powershell
# 1. Navigate to the project folder
cd "D:\HybridRAG3"

# 2. Create a virtual environment (use whichever Python you have: 3.11 or 3.12)
py -3.12 -m venv .venv

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

See `docs/01_setup/INSTALL_AND_SETUP.md` for detailed first-time installation instructions.

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
rag-mode-online        Switch to API mode (queries go to cloud LLM)
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
- Best for: Air-gapped environments (e.g. hospital networks protecting HIPAA data), restricted networks, field use

### Online Mode
- Routes queries to a cloud LLM API (OpenRouter, Azure, or compatible endpoint)
- Requires API key stored in Windows Credential Manager
- Response time: ~2-5 seconds
- Best for: Daily use when on an unrestricted network
- Cost: varies by provider and model

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
| PowerShell (start_hybridrag.ps1) | Outbound model downloads | Session environment variables |
| Python (embedder.py) | Outbound calls in ANY Python process | os.environ enforcement before import |
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
|-- config/                            Settings
|   |-- default_config.yaml            All settings (paths, models, thresholds)
|   |-- profiles.yaml                  Hardware profile definitions (3 profiles)
|   +-- system_profile.json            Auto-detected hardware fingerprint
|
|-- src/
|   |-- core/                          Core pipeline (25 modules)
|   |   |-- config.py                  Config loader, validation, dataclasses
|   |   |-- boot.py                    Startup pipeline
|   |   |-- indexer.py                 File scanning, parsing, chunking, embedding
|   |   |-- chunker.py                Text to chunks with heading detection
|   |   |-- chunk_ids.py              Deterministic chunk ID generation
|   |   |-- embedder.py               nomic-embed-text text to vector
|   |   |-- vector_store.py           SQLite + memmap storage, FTS5 search
|   |   |-- retriever.py              Hybrid search (vector + BM25 RRF)
|   |   |-- query_engine.py           Search to LLM to answer (prompt v4)
|   |   |-- grounded_query_engine.py   Source-bounded generation engine
|   |   |-- llm_router.py             Ollama / vLLM / API routing
|   |   |-- network_gate.py           Network availability control
|   |   |-- cost_tracker.py           PM cost dashboard backend (SQLite)
|   |   |-- health_checks.py          System health verification
|   |   |-- http_client.py            HTTP requests with retry
|   |   |-- sqlite_utils.py           SQLite helpers
|   |   +-- ...                        (+ exceptions, feature_registry, etc.)
|   |
|   |-- core/hallucination_guard/      Hallucination + injection guard (12 modules)
|   |   |-- hallucination_guard.py     Main guard orchestrator
|   |   |-- prompt_hardener.py         Injection hardening
|   |   |-- nli_verifier.py            Natural language inference
|   |   +-- ...                        (+ claim_extractor, golden_probes, etc.)
|   |
|   |-- parsers/                       Document parsers (28 files)
|   |   |-- registry.py               File extension to parser mapping
|   |   |-- pdf_parser.py             PDF (pdfplumber + OCR fallback)
|   |   |-- office_docx_parser.py     Word, office_pptx_parser.py (PPT),
|   |   |                              office_xlsx_parser.py (Excel)
|   |   |-- eml_parser.py             Email (.eml, .msg, .mbox)
|   |   |-- image_parser.py           OCR via Tesseract
|   |   |-- html_parser.py            HTML/HTM
|   |   |-- dxf_parser.py             CAD (DXF, STEP/IGES, STL)
|   |   |-- visio_parser.py           Visio diagrams
|   |   |-- evtx_parser.py            Windows event logs
|   |   |-- pcap_parser.py            Network captures
|   |   +-- ...                        (+ rtf, psd, access_db, plain_text, etc.)
|   |
|   |-- api/                           REST API (FastAPI)
|   |   |-- server.py                  FastAPI app + uvicorn launcher
|   |   |-- routes.py                  Endpoints: /health /status /config /query /query/stream /index /index/status /mode
|   |   +-- models.py                  Pydantic request/response models
|   |
|   |-- gui/                           Desktop GUI (tkinter)
|   |   |-- app.py                     Main window (File | Admin | Help)
|   |   |-- launch_gui.py             CLI launcher + backend loading
|   |   |-- theme.py                   Dark/light theme definitions
|   |   +-- panels/                    GUI panels (18 modules)
|   |       |-- query_panel.py         Question box, answer, sources, metrics
|   |       |-- index_panel.py         Folder picker, progress bar, start/stop
|   |       |-- status_bar.py          LLM / Ollama / Gate indicators
|   |       |-- api_admin_tab.py       Admin/API settings tab
|   |       +-- cost_dashboard.py      PM cost tracking window
|   |
|   |-- diagnostic/                    Testing and diagnostics (11 files)
|   |   |-- hybridrag_diagnostic.py    Main diagnostic runner
|   |   |-- health_tests.py           Pipeline health checks
|   |   |-- component_tests.py        Individual component tests
|   |   |-- perf_benchmarks.py        Performance benchmarks
|   |   |-- fault_analysis.py         Automated fault hypothesis engine
|   |   +-- report.py                  Report formatting and output
|   |
|   |-- tools/                         Utility scripts (16 files)
|   |   |-- bulk_transfer_v2.py       Bulk file transfer (ETA, DB rotation)
|   |   |-- transfer_manifest.py      Transfer manifest database
|   |   |-- transfer_staging.py       Three-stage staging manager
|   |   |-- run_index_once.py         Main indexing entry point
|   |   +-- ...                        (+ check_db, index_status, migrate, etc.)
|   |
|   |-- security/                      Credential management
|   |   +-- credentials.py            Windows Credential Manager integration
|   |
|   +-- monitoring/                    Logging and tracking
|       |-- logger.py                  Structured logging setup
|       +-- run_tracker.py             Indexing run audit trail
|
|-- scripts/                           PowerShell command helpers (10 files)
|   |-- _check_creds.py              Credential status
|   |-- _set_online.py / _set_offline.py   Mode switching
|   |-- _test_api.py                  API connectivity test
|   |-- _profile_status.py / _profile_switch.py   Profile management
|   |-- _model_meta.py / _set_model.py   Model definitions + switching
|   |-- _list_models.py              Available model listing
|   +-- run_eval.py                   Evaluation runner (LOCKED -- do not modify)
|
|-- tools/                             Operations and maintenance (25 files)
|   |-- sync_to_educational.py        One-way sanitized sync to Educational repo
|   |-- eval_runner.py                Evaluation execution (LOCKED)
|   |-- score_results.py              Evaluation scorer (LOCKED)
|   |-- run_all.py                    Full test suite runner (LOCKED)
|   |-- query_benchmark.py           Query performance measurement
|   |-- api_mode_commands.ps1         API mode PowerShell commands
|   |-- launch_gui.ps1               GUI launcher (PowerShell)
|   |-- master_toolkit.ps1           Unified command interface
|   |-- py/                           Python CLI utilities (13 files)
|   |   +-- store_key.py, net_check.py, ollama_test.py, ...
|   +-- work_validation/              Pre-deployment validation (6 files)
|       +-- validate_offline_models.py, check_dependencies.py, ...
|
|-- tests/                             Test suite (37 files, 84 pytest + 290 virtual)
|   |-- conftest.py                   Pytest fixtures
|   |-- test_fastapi_server.py        FastAPI endpoint tests (17 tests)
|   |-- test_query_engine.py          Query engine tests
|   |-- test_cost_tracker.py          Cost tracker tests (16 tests)
|   |-- test_gui_integration_w4.py    GUI integration tests
|   |-- stress_test_*.py              6 stress test suites
|   |-- virtual_test_*.py             Virtual test framework (290 scenarios)
|   +-- ...                            (+ indexer, credentials, ollama, vllm, etc.)
|
|-- Eval/
|   +-- golden_tuning_400.json         400-question evaluation golden set
|
|-- docs/                              Documentation (36 files)
|   +-- (see Documentation section below)
|
|-- mcp_server.py                      MCP server implementation
|-- start_hybridrag.ps1                Environment setup + aliases (machine-specific)
|-- start_rag.bat                      Double-click launcher (CLI)
|-- start_gui.bat                      Double-click launcher (GUI)
|-- requirements.txt                   Python dependencies
|-- requirements_approved.txt          Store-approved exact versions
|-- .gitignore                         Files excluded from git
+-- README.md                          This file
```

## Data Directories (not in git, local to each machine)

```
.venv/                              Python virtual environment
.model_cache/                       Embedding model cache (legacy)
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
| Embeddings | nomic-embed-text (Ollama) | Apache 2.0 | Text to 768-dim vectors (served by Ollama) |
| Vector Math | numpy | BSD-3 | Numerical computation |
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
- Python 3.11 or 3.12 (work laptop: 3.12rc3, home: 3.11.9)
- ~3 GB disk space (venv + model cache)
- Ollama (optional, for offline LLM mode)
- Tesseract (optional, for OCR on scanned documents)
- See `requirements.txt` for Python dependencies

## Documentation

### Getting Started
- `docs/01_setup/INSTALL_AND_SETUP.md` -- Full installation and deployment guide (10 parts)
- `docs/03_guides/USER_GUIDE.md` -- Daily use, all commands, tuning, troubleshooting
- `docs/03_guides/SHORTCUT_SHEET.md` -- Quick reference card (phone-friendly)

### Understanding the System
- `docs/02_architecture/THEORY_OF_OPERATION_RevA.md` -- High-level overview for non-programmers
- `docs/02_architecture/TECHNICAL_THEORY_OF_OPERATION_RevA.md` -- Developer-focused technical reference
- `docs/02_architecture/SECURITY_THEORY_OF_OPERATION_RevA.md` -- Security design and threat model
- `docs/02_architecture/ARCHITECTURE_DIAGRAM.md` -- System architecture diagram

### Reference
- `docs/03_guides/GUI_GUIDE.md` -- Graphical interface walkthrough
- `docs/02_architecture/INTERFACES.md` -- Stable public API reference for all modules
- `docs/02_architecture/FORMAT_SUPPORT.md` -- All 49+ supported file formats
- `docs/03_guides/GLOSSARY.md` -- Every acronym and term defined
- `docs/Development_Inventory.md` -- Current dependency and model inventory

### Configuration
- `config/default_config.yaml` -- All runtime settings
- `config/profiles.yaml` -- Hardware performance profiles (laptop / desktop / server)

### Additional Guides
- `docs/04_demo/DEMO_PREP.md` -- Demo preparation checklist
- `docs/04_demo/DEMO_GUIDE.md` -- Demo walkthrough script
- `docs/HANDOVER_AND_SPRINT_PLAN_FREEZE_SAFE.md` -- Active handoff and sprint planning notes
- `docs/05_security/GIT_REPO_RULES.md` -- Git workflow and sync rules
- `docs/05_security/DEFENSE_MODEL_AUDIT.md` -- Approved model stack and audit trail

Older documents that have been superseded live in `docs/archive/`.

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
- .model_cache/ (legacy, downloaded locally)
- API keys (stored in Windows Credential Manager, local to each login)

## License

Educational and personal learning use.
