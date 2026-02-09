# HybridRAG Setup Guide

Last Updated: 2026-02-07

## Prerequisites

- Windows 10/11
- Python 3.11+ (tested on 3.11.9)
- Git
- ~2GB disk space (model + dependencies)
- Ollama (for offline LLM mode)
- Tesseract (optional, for OCR on scanned documents)

## Clone and Install (New Machine)

### Step 1: Clone the repository
```powershell
cd "D:\HybridRAG2"
git clone <your-repo-url> HybridRAG
cd HybridRAG
```

### Step 2: Create virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies
```powershell
pip install torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The CPU-only PyTorch must be installed first with the special index URL.
Total download is ~800MB. The embedding model (~80MB) downloads automatically
on first `rag-index` run.

### Step 4: Install Ollama

Download from https://ollama.com and install. Then pull the model:
```powershell
ollama pull llama3
```

Verify Ollama is running:
```powershell
curl http://localhost:11434/api/tags
```

### Step 5: Install Tesseract (optional, for OCR)

Download from https://github.com/UB-Mannheim/tesseract/wiki
Install to default path. Verify:
```powershell
tesseract --version
```

### Step 6: Configure source folder

Set the environment variable for your document folder:
```powershell
$env:HYBRIDRAG_INDEX_FOLDER = "C:\path\to\your\documents"
```

Or edit `config/default_config.yaml` and set `source_folder` directly.

### Step 7: Activate HybridRAG environment
```powershell
. .\start_hybridrag.ps1
```

This sets all environment variables and creates the aliases:
- `rag-index` — Run the indexer
- `rag-query "question"` — Query your documents
- `rag-status` — Health check
- `rag-paths` — Show configured paths

### Step 8: Run first index
```powershell
rag-index
```

First run will:
1. Download embedding model (~80MB, cached after first download)
2. Parse all supported files in source folder
3. Chunk text, compute embeddings, store in SQLite + memmap
4. Auto-rebuild FTS5 keyword index

### Step 9: Add to PowerShell profile (optional)

To auto-load HybridRAG in every new terminal:
```powershell
notepad $PROFILE
```

Add this line:
```powershell
. ".\start_hybridrag.ps1"
```

## Directory Structure
```
HybridRAG/                          ← Repository root
├── config/
│   └── default_config.yaml         ← All settings (paths, models, thresholds)
├── src/
│   ├── core/
│   │   ├── config.py               ← Config loader, validation, dataclasses
│   │   ├── indexer.py              ← File scanning, parsing, chunking, embedding
│   │   ├── chunker.py             ← Text → chunks with heading detection
│   │   ├── chunk_ids.py           ← Deterministic chunk ID generation
│   │   ├── embedder.py            ← all-MiniLM-L6-v2 text → vector
│   │   ├── vector_store.py        ← SQLite + memmap storage, FTS5 search
│   │   ├── retriever.py           ← Hybrid search (vector + BM25 RRF)
│   │   ├── query_engine.py        ← Search → LLM → answer pipeline
│   │   ├── llm_router.py          ← Ollama (offline) / GPT API (online)
│   │   ├── health_checks.py       ← System health verification
│   │   └── sqlite_utils.py        ← SQLite helpers
│   ├── parsers/
│   │   ├── registry.py            ← File extension → parser mapping
│   │   ├── pdf_parser.py          ← PDF text extraction (pdfplumber)
│   │   ├── pdf_parser_utils.py    ← PDF diagnostics
│   │   ├── office_docx_parser.py  ← Word document parser
│   │   ├── office_pptx_parser.py  ← PowerPoint parser
│   │   ├── office_xlsx_parser.py  ← Excel parser
│   │   ├── eml_parser.py          ← Email parser
│   │   ├── image_ocr_parser.py    ← OCR via Tesseract
│   │   ├── plain_text_parser.py   ← TXT, MD, CSV, JSON, XML, etc.
│   │   └── text_cleaner.py        ← Post-extraction text cleanup
│   ├── tools/
│   │   ├── run_index_once.py      ← Main indexing entry point
│   │   ├── index_status.py        ← Database status checker
│   │   ├── quick_test_retrieval.py ← Retrieval testing utility
│   │   ├── migrate_embeddings_to_memmap.py  ← One-time migration
│   │   └── rebuild_memmap_from_sqlite.py    ← Memmap recovery
│   └── monitoring/
│       ├── logger.py              ← Structured logging setup
│       └── run_tracker.py         ← Indexing run audit trail
├── start_hybridrag.ps1            ← Environment setup + aliases
├── cli_test_phase1.py             ← rag-query entry point
├── requirements.txt               ← Python dependencies
└── config/default_config.yaml     ← Master configuration
```

## Data Directory (created automatically)
```
HybridRAG_IndexedData/             ← Outside repo, not committed
├── hybridrag.sqlite3              ← Chunks, metadata, FTS5, run history
├── embeddings.f16.dat             ← Memory-mapped float16 vectors
└── embeddings_meta.json           ← Memmap bookkeeping
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

## Configuration Reference

All settings in `config/default_config.yaml`. Key settings:

| Setting | Default | What it does |
|---------|---------|-------------|
| mode | offline | "offline" (Ollama) or "online" (GPT API) |
| source_folder | (env var) | Path to documents to index |
| chunk_size | 1200 | Characters per chunk |
| overlap | 200 | Overlap between chunks |
| top_k | 5 | Number of chunks returned per query |
| min_score | 0.20 | Minimum relevance threshold |
| hybrid_search | true | Enable vector + BM25 fusion |
| rrf_k | 60 | RRF smoothing parameter |
| timeout_seconds | 180 | LLM response timeout |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| HYBRIDRAG_INDEX_FOLDER | Source document folder path |
| HYBRIDRAG_DATA_DIR | Database/embeddings storage path |
| HYBRIDRAG_MIN_SCORE | Override min_score threshold |
| HYBRIDRAG_RETRIEVAL_BLOCK_ROWS | Override vector search block size |

## Troubleshooting

**"Model not found" on first run:**
The embedding model downloads automatically (~80MB). If on an offline machine,
pre-download on a connected machine and copy the cache folder:
`C:\Users\<you>\.cache\torch\sentence_transformers\`

**Ollama timeout:**
First query after model load takes longer. Default timeout is 180s.
If still timing out, increase `timeout_seconds` in config.

**Permission errors on network drives:**
Run `rag-index` as the same user who has read access to the network share.
The indexer has retry logic (3 attempts with exponential backoff) for flaky reads.

**"No relevant information found":**
Try lowering `min_score` in config (e.g., 0.10) or check that FTS rebuilt
successfully (look for `fts_rebuilt` in indexing output).