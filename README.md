# HybridRAG v3 — Personal Learning Project

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

- **RAG Pipeline Architecture**: Document parsing → chunking → embedding → vector storage → semantic retrieval → LLM-augmented answers
- **Hybrid Search**: Combining vector similarity (semantic) with keyword matching (FTS5) via Reciprocal Rank Fusion
- **Offline-First Design**: Runs entirely on a local machine with no internet dependency after initial setup
- **Security Engineering**: 3-layer network lockdown, audit logging, defense-in-depth
- **Diagnostic Engineering**: Automated 3-tier test suite with hardware profiling and security auditing
- **Zero External Servers**: SQLite for storage, local embedding model, optional local LLM via Ollama

## Setup (First Time)

```powershell
# 1. Navigate to the project folder
cd "C:\path\to\HybridRAG3"

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
. .\.venv\Scripts\Activate.ps1

# 4. Install dependencies from PyPI (one-time, requires internet)
pip install -r requirements.txt

# 5. Download the embedding model (one-time, requires internet)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 6. Launch the environment (sets security lockdown + paths)
. .\start_hybridrag.ps1

# 7. Run diagnostics to verify installation
python -m src.tools.system_diagnostic --tier 2
```

After initial setup, steps 4-5 are never needed again. Daily use starts at step 6.

## Daily Use

```powershell
# Launch environment (always run first)
. .\start_hybridrag.ps1

# Run diagnostics
python -m src.tools.system_diagnostic --tier 2

# Index your documents
rag-index

# Query
rag-query "What is the operating frequency range?"
```

## Commands Reference

```powershell
# --- Startup (always run first) ---
. .\start_hybridrag.ps1

# --- Diagnostics ---
python -m src.tools.system_diagnostic                # Tier 1: instant schema tests
python -m src.tools.system_diagnostic --tier 2       # Tier 1+2: loads model, tests pipeline
python -m src.tools.system_diagnostic --tier 3       # All tiers: stress test
python -m src.tools.system_diagnostic --hardware-only # Hardware fingerprint only

# --- Daily use ---
rag-paths              # Show configured paths + network status
rag-index              # Start indexing
rag-query "question"   # Query the index
rag-diag               # Run diagnostics
rag-status             # Quick health check
```

## Configuration

Edit `start_hybridrag.ps1` to set your data and source paths:

```powershell
# Local folders:
$DATA_DIR   = "C:\Users\you\RAG_Data"
$SOURCE_DIR = "C:\Users\you\Documents"

# Network drive:
$SOURCE_DIR = "\\server\share\documents"

# Mapped drive:
$SOURCE_DIR = "Z:\Program Documents"
```

## Security Model

Three independent layers prevent any accidental network calls at runtime:

| Layer | What It Blocks | How |
|-------|---------------|-----|
| PowerShell (start_hybridrag.ps1) | HuggingFace + transformers | Session environment variables |
| Python (embedder.py) | HuggingFace in ANY Python process | os.environ enforcement before import |
| Config (SEC-001) | LLM queries to public endpoints | Empty API endpoint default |

All three must fail before data leaves the machine.

## Project Structure

```
src/core/        — Config, embedder, indexer, retriever, vector store, LLM router
src/parsers/     — PDF, DOCX, PPTX, XLSX, EML, image OCR parsers
src/tools/       — System diagnostic, indexing runner, status tools
src/diagnostic/  — Component tests, health checks, performance benchmarks
src/monitoring/  — Structured logging, run tracker
config/          — YAML configuration, performance profiles
docs/            — Architecture diagrams, technical documentation
```

## Technology Stack

All packages sourced from PyPI (pypi.org) — open-source with permissive licenses.

| Component | Package | License | Purpose |
|-----------|---------|---------|---------|
| Embeddings | sentence-transformers | Apache 2.0 | Text → vector conversion |
| ML Backend | torch (PyTorch) | BSD-3 | Tensor computation |
| Tokenizer | transformers | Apache 2.0 | Text tokenization |
| Vector Math | numpy | BSD-3 | Numerical computation |
| ML Utilities | scikit-learn | BSD-3 | Distance metrics |
| Database | sqlite3 (built-in) | Public Domain | Metadata + keyword search |
| PDF Parsing | pdfplumber, pypdf | MIT | Document text extraction |
| Office Docs | python-docx, python-pptx, openpyxl | MIT | Word, PowerPoint, Excel |
| Imaging | pillow | MIT-like | Image processing for OCR |
| XML/HTML | lxml | BSD-3 | Document parsing |
| HTTP Client | httpx | BSD-3 | API calls (online mode only) |
| Encryption | cryptography | Apache 2.0 / BSD-3 | Credential encryption |
| Logging | structlog | Apache 2.0 | Structured event logging |
| Config | PyYAML | MIT | YAML configuration files |

## Requirements

- Python 3.10+ (tested on 3.10.1 and 3.11.9)
- ~3 GB disk space (venv + model cache)
- Ollama (optional, for offline LLM mode)
- Tesseract (optional, for OCR)
- See `requirements.txt` for Python dependencies

## Documentation

- `docs/ARCHITECTURE.md` — System design, security model, technical decisions
- `docs/SETUP.md` — Detailed installation instructions
- `docs/NETWORK_SECURITY_EXPLAINER.md` — Network isolation design
- `docs/PERFORMANCE_BASELINE.md` — Performance benchmarks and tuning
- `config/profiles.yaml` — Hardware performance profiles

## License

Educational and personal learning use.
