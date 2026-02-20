# HybridRAG3 -- Technical Theory of Operation

Last Updated: 2026-02-20

---

## 1. System Architecture Overview

HybridRAG3 is a local-first Retrieval-Augmented Generation (RAG) system
with dual-mode LLM routing (offline via Ollama, online via OpenAI-compatible
API), hybrid search (vector + BM25 via Reciprocal Rank Fusion), and a
5-layer hallucination guard for online mode.

```
                          INDEXING PIPELINE
  +-----------+     +----------+     +---------+     +-------------+
  |  Source    | --> |  Parser  | --> | Chunker | --> |  Embedder   |
  |  Files    |     | Registry |     | (1200c, |     | MiniLM-L6   |
  | (.pdf,    |     | (24 ext) |     |  200lap)|     | (384-dim)   |
  | .docx,..) |     +----------+     +---------+     +-------------+
  +-----------+                                             |
                                                            v
                                                   +----------------+
                                                   |  VectorStore   |
                                                   | SQLite + FTS5  |
                                                   | Memmap float16 |
                                                   +----------------+
                                                            |
                          QUERY PIPELINE                    v
  +-----------+     +-----------+     +---------+     +-------------+
  |  User     | --> | Embedder  | --> |Retriever| --> |  Query      |
  |  Query    |     | (same     |     | Hybrid  |     |  Engine     |
  |           |     |  model)   |     | RRF k=60|     | + LLM call  |
  +-----------+     +-----------+     +---------+     +-------------+
                                                            |
                                                            v
                                                   +----------------+
                                                   | Hallucination  |
                                                   | Guard (5-layer)|
                                                   | (online only)  |
                                                   +----------------+
```

**Design priorities**: Offline operation, crash safety, low RAM usage,
full auditability, zero external server dependencies.

---

## 2. Module Dependency Graph

```
boot.py  (entry point -- constructs all services)
  |-- config.py         (YAML loader, dataclass validation)
  |-- credentials.py    (Windows Credential Manager / env var resolution)
  |-- network_gate.py   (URL allowlist, 3-mode access control)
  |-- api_client_factory.py  (builds httpx client with gate integration)
  |-- embedder.py       (sentence-transformers model wrapper)
  |-- vector_store.py   (SQLite + memmap dual store)
  |-- chunker.py        (text splitter with boundary detection)
  |-- indexer.py        (orchestrates parse -> chunk -> embed -> store)
  |-- retriever.py      (hybrid search: vector + BM25 + RRF)
  |-- query_engine.py   (orchestrates search -> context -> LLM -> answer)
  |-- llm_router.py     (Ollama or API routing, raw httpx)
  +-- hallucination_guard/  (5-layer verification, online mode only)

parsers/registry.py  (extension -> parser class mapping)
  |-- pdf_parser.py          (pdfplumber extraction)
  |-- pdf_ocr_fallback.py    (Tesseract fallback for scanned PDFs)
  |-- office_docx_parser.py  (python-docx paragraph extraction)
  |-- office_pptx_parser.py  (python-pptx slide/shape extraction)
  |-- office_xlsx_parser.py  (openpyxl row extraction, read-only mode)
  |-- eml_parser.py          (stdlib email + attachment extraction)
  |-- image_parser.py        (Tesseract OCR)
  |-- plain_text_parser.py   (direct UTF-8 read)
  +-- text_parser.py         (routing parser, delegates by extension)
```

---

## 3. Indexing Pipeline

### 3.1 Parser Registry

`src/parsers/registry.py` maps 24 file extensions to parser classes.
Each parser implements:

```python
def parse(self, file_path: str) -> str
def parse_with_details(self, file_path: str) -> Tuple[str, Dict[str, Any]]
```

The `parse_with_details` variant returns diagnostic metadata (character
count, page count, error info) alongside the extracted text. All parsers
are lazy-imported to avoid pulling in heavy dependencies (openpyxl,
python-pptx, etc.) when they are not needed.

Error handling: Every parser wraps its work in try/except and returns
`("", {"error": "..."})` on failure. A corrupted file never crashes the
pipeline.

### 3.2 Chunker

`src/core/chunker.py` splits raw text into overlapping chunks.

**Parameters:**
- `chunk_size`: 1200 characters (default). Tuned for all-MiniLM-L6-v2
  which performs best on 200-500 word passages.
- `overlap`: 200 characters (default). Ensures facts near chunk
  boundaries are not lost.

**Boundary detection** (priority order):
1. Paragraph break (`\n\n`) in the second half of the chunk window
2. Sentence end (`. `) in the second half
3. Any newline in the second half
4. Hard cut at `chunk_size` (last resort)

**Heading prepend**: The chunker looks backward up to 2000 characters
for the nearest section heading (ALL CAPS line, numbered section like
"3.2.1 Signal Processing", or line ending with `:`) and prepends it
as `[SECTION] Heading\n` to the chunk. This preserves document structure
across chunk boundaries.

### 3.3 Embedder

`src/core/embedder.py` wraps `sentence-transformers/all-MiniLM-L6-v2`.

- Output: 384-dimensional normalized float32 vectors
- Dimension is read from the model at load time (never hardcoded)
- Batch embedding for indexing (`embed_batch`), single for queries
  (`embed_query`)
- Model loaded once, held in memory (~100 MB), released with `close()`
- HuggingFace Hub downloads are blocked at runtime via environment
  variables (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`); the model
  must be pre-downloaded to `.model_cache/`

### 3.4 VectorStore (Dual Storage)

`src/core/vector_store.py` manages two coordinated storage backends:

**SQLite** (`hybridrag.sqlite3`):
- `chunks` table: id, text, source_path, chunk_index, metadata JSON
- `chunks_fts` FTS5 virtual table: auto-synchronized with `chunks`,
  provides BM25 keyword search via SQLite's full-text search engine
- `index_runs` table: run audit trail (run_id, timestamps, counts)
- Uses `INSERT OR IGNORE` with deterministic chunk IDs for crash-safe
  restarts (same file + position = same ID)

**Memmap** (`embeddings.f16.dat` + `embeddings_meta.json`):
- Raw float16 matrix of shape `[N, 384]` memory-mapped via numpy
- Disk-backed: only active rows are loaded into RAM during search
- A laptop with 8 GB RAM can search 10M+ embeddings
- `embeddings_meta.json` tracks dimension, count, and dtype
- **Hardening (v3.1)**: JSONDecodeError guard on meta file load --
  corrupted JSON (from power failure or disk-full) triggers
  reinitialization instead of crash

### 3.5 Indexer Orchestration

`src/core/indexer.py` ties the pipeline together:

1. Scan source folder recursively for supported extensions
2. For each file, compute a hash (file size + mtime) for change detection
3. Skip files whose hash matches the stored hash (already indexed)
4. Parse file to raw text via `TextParser` (which routes to the correct
   specialized parser via the Registry)
5. Chunk text into overlapping segments
6. Embed chunks in batches
7. Store chunks in SQLite and embeddings in memmap
8. Run garbage collection between files to bound RAM usage

**Block-based processing**: Large files (500-page PDFs producing 200K+
characters) are processed in 200K character blocks to cap peak RAM.

**Anti-sleep**: On Windows, `SetThreadExecutionState` prevents the OS
from sleeping during long indexing runs (6+ hours overnight).

---

## 4. Query Pipeline

### 4.1 Retriever (Hybrid Search)

`src/core/retriever.py` implements three search strategies:

**Vector search**: Query embedding dot-producted against memmap in
blocks. Returns top candidates by cosine similarity. Block-based
scanning avoids loading the full embedding matrix into RAM.

**BM25 keyword search**: FTS5 OR-logic query against the `chunks_fts`
virtual table. OR-logic (not AND) ensures partial matches are returned.
Critical for exact terms: part numbers, acronyms, technical jargon.

**Hybrid search (default)**: Both searches run, results merged via
Reciprocal Rank Fusion (RRF):

```
rrf_score(chunk) = sum( 1 / (k + rank_i) )  for each list i
```

where `k = 60` (standard smoothing constant from the original RRF paper).
Chunks appearing in both lists get boosted. RRF scores are multiplied
by 30 and capped at 1.0 to normalize into the same range as cosine
similarity scores (enabling a single `min_score` threshold).

**Optional cross-encoder reranker**: Retrieves 20 candidates, then
reranks with a cross-encoder model for more accurate relevance scoring.
Disabled by default (adds ~500ms latency).

### 4.2 Query Engine

`src/core/query_engine.py` orchestrates the full query:

1. Embed user query via `embedder.embed_query()`
2. Retrieve top-K chunks via `retriever.search()`
3. Build context string from retrieved chunks
4. Construct LLM prompt (system prompt + context + user question)
5. Route to LLM via `llm_router` (offline or online)
6. Calculate token cost estimate
7. Return structured `QueryResult` (answer, sources, tokens, latency)

**Failure paths**: If retrieval returns 0 results, a "no relevant
documents found" message is returned without calling the LLM. If the
LLM times out, the search results are still returned with an error flag.
Every failure path returns a valid `QueryResult` -- no exceptions
propagate to the caller.

### 4.3 LLM Router

`src/core/llm_router.py` routes to the appropriate LLM backend:

- **Offline**: HTTP POST to Ollama's `/api/generate` endpoint
  (localhost:11434). Default timeout: 300 seconds (CPU inference is slow).
- **Online**: HTTP POST to OpenAI-compatible `/v1/chat/completions`.
  API key from credentials, endpoint from config.

All HTTP calls use `httpx` directly -- no OpenAI SDK, no LangChain, no
hidden magic. Full control over timeouts, retries, and error handling.
The Network Gate is checked before every outbound connection.

---

## 5. Hallucination Guard

`src/core/hallucination_guard/` -- 6 files, each under 500 lines.

Active only in online mode (offline LLMs are assumed to be under the
operator's control). Architecture:

| Layer | Module | Function |
|-------|--------|----------|
| 1 | `prompt_hardener.py` | Injects grounding instructions into system prompt |
| 2a | `claim_extractor.py` | Splits LLM response into individual factual claims |
| 2b | `nli_verifier.py` | Runs NLI model on each claim vs source chunks |
| 3-4 | `response_scoring.py` | Scores faithfulness, constructs safe response |
| 5 | `dual_path.py` | Optional dual-model consensus for critical queries |

**GuardConfig** controls thresholds:
- `faithfulness_threshold`: Minimum score (default 0.90) for a response
  to be considered safe
- `failure_action`: "warn" (flag but show) or "block" (replace with
  safe response)

**Built-In Test (BIT)**: Runs automatically on first import (< 50ms,
no model loading, no network). Validates that all guard components are
importable and structurally intact.

**Version**: `GUARD_VERSION = "1.1.0"` exposed at package level for
runtime version checking.

---

## 6. Security Architecture

### 6.1 Network Gate

`src/core/network_gate.py` -- Centralized access control for all
outbound connections.

**Three modes**:

| Mode | Allowed Destinations | Use Case |
|------|---------------------|----------|
| `offline` | `localhost`, `127.0.0.1` only | Default. Air-gapped, SCIF, field use |
| `online` | Localhost + configured API endpoint | Daily use on company network |
| `admin` | Unrestricted (with logging) | Maintenance: pip install, model downloads |

**Enforcement**:
- `gate.check_allowed(url, purpose, caller)` -- raises
  `NetworkBlockedError` if URL is not in the allowlist
- `gate.is_allowed(url)` -- non-raising boolean check
- Every attempt (allowed AND denied) is logged to an audit trail with
  timestamp, URL, purpose, mode, and result

**URL validation (v3.1)**: Boot pipeline validates that configured
endpoints start with `http://` or `https://` before passing them to
the gate. Malformed URLs are cleared with a warning.

### 6.2 Three-Layer Network Lockdown

| Layer | Mechanism | Blocks |
|-------|-----------|--------|
| 1. PowerShell | `$env:HF_HUB_OFFLINE=1`, `$env:TRANSFORMERS_OFFLINE=1` | HuggingFace model downloads |
| 2. Python | `os.environ` enforcement before sentence-transformers import | HuggingFace in any Python process |
| 3. Application | NetworkGate URL allowlist | All other outbound URLs |

All three must fail before unauthorized data leaves the machine.

### 6.3 Credential Management

`src/security/credentials.py` resolves API keys from (in priority order):
1. Windows Credential Manager (DPAPI encrypted, tied to Windows login)
2. Environment variable (`HYBRIDRAG_API_KEY`)
3. Config file (not recommended, logged as warning)

Keys are never logged in full. `key_preview` produces a masked form
(`sk-...xxxx`) for diagnostic output.

---

## 7. Boot Pipeline

`src/core/boot.py` -- Single entry point for system initialization.

**Sequence**:
1. Record `boot_timestamp` (ISO format)
2. Load configuration from YAML (`config/default_config.yaml`)
3. Resolve credentials via `credentials.py`
4. Validate config + credentials together
5. Validate endpoint URL format (must be `http://` or `https://`)
6. Configure NetworkGate to appropriate mode
7. Build API client (if online mode and credentials available)
8. Probe Ollama (if offline mode configured)
9. Return `BootResult` with `success`, `online_available`,
   `offline_available`, `warnings[]`, `errors[]`, and `summary()`

**Design**: Never crashes on missing credentials -- marks the
corresponding mode as unavailable and continues. This ensures offline
mode always works even if API credentials are not configured.

---

## 8. Exception Hierarchy

`src/core/exceptions.py` defines a typed exception tree rooted at
`HybridRAGError(Exception)`.

Every custom exception includes:
- `fix_suggestion: str` -- Human-readable remediation instruction
- `error_code: str` -- Machine-readable code (e.g., `CONF-001`,
  `NET-001`, `IDX-001`) for logging and dashboards

Key exception classes:

| Exception | Code | When Raised |
|-----------|------|-------------|
| `ConfigError` | CONF-* | Invalid YAML, missing required fields |
| `AuthRejectedError` | AUTH-001 | 401/403 from API endpoint |
| `EndpointNotConfiguredError` | NET-002 | API endpoint missing |
| `NetworkBlockedError` | NET-001 | NetworkGate denied connection |
| `EmbeddingError` | EMB-* | Model load failure, dimension mismatch |
| `IndexingError` | IDX-001 | Unrecoverable file error during indexing |

All exceptions are catchable with `except HybridRAGError` as a group,
or individually by specific type.

---

## 9. HTTP Client

`src/core/http_client.py` -- Shared HTTP client with retry logic.

**HttpResponse dataclass** includes:
- `status_code`, `body`, `headers`, `elapsed_ms`
- `retry_count: int` -- Number of retries that occurred before success
  (zero on first attempt). Zero-cost observability field for monitoring
  flaky endpoints.

**Retry policy**: Exponential backoff with jitter. Configurable max
retries, timeout per request, and total timeout.

**Network Gate integration**: Every request passes through the gate
before the connection is made. `NetworkBlockedError` is raised before
any bytes leave the machine.

---

## 10. Diagnostic Framework

`src/diagnostic/` provides a 3-tier test and monitoring system:

| Tier | Module | What It Tests |
|------|--------|--------------|
| Health | `health_tests.py` | 15 pipeline health checks (DB exists, model loads, etc.) |
| Component | `component_tests.py` | Individual component unit tests |
| Performance | `perf_benchmarks.py` | Embedding speed, search latency, RAM usage |

`fault_analysis.py` provides automated fault hypothesis generation:
- Accepts exceptions from any module
- Classifies by severity (`critical`, `degraded`, `warning`)
- Generates fix suggestions
- Maintains fault history for trend analysis

**Note**: `FaultAnalyzer` is 656 lines and is flagged for decomposition
into `FaultAnalyzer` (hypothesis engine) and `FaultReporter`
(formatting/output) when next modified.

---

## 11. Storage Layout

```
hybridrag.sqlite3
|-- chunks           (id, text, source_path, chunk_index, metadata JSON)
|-- chunks_fts       (FTS5 virtual table, auto-synced with chunks)
|-- index_runs       (run_id, start_time, end_time, file counts)
+-- query_log        (planned: query audit trail)

embeddings.f16.dat   (raw float16 matrix, shape [N, 384])
embeddings_meta.json ({"dim": 384, "count": N, "dtype": "float16"})
```

**Why SQLite**: Single-file, zero-config, portable, XCOPY-deployable.
No database server to install or maintain.

**Why memmap over FAISS**: Simpler, no C++ dependencies, sufficient
for < 10M chunks. Memory-mapped access means the OS handles paging
automatically -- only accessed rows enter RAM.

**Why float16**: Halves storage (0.75 GB vs 1.5 GB per million chunks)
with negligible quality loss for cosine similarity on normalized vectors.

---

## 12. Configuration System

`src/core/config.py` loads from `config/default_config.yaml`.

**Nested dataclasses** for type safety:
- `PathsConfig` -- database, embeddings_cache, source_folder
- `EmbeddingConfig` -- model_name, dimension, batch_size, device
- `ChunkingConfig` -- chunk_size, overlap, max_heading_len
- `OllamaConfig` -- base_url, model, timeout_seconds, context_window
- `APIConfig` -- endpoint, model, max_tokens, temperature
- `RetrievalConfig` -- top_k, min_score, hybrid_search, rrf_k
- `IndexingConfig` -- supported_extensions, excluded_dirs, ocr settings
- `CostConfig` -- track_enabled, daily_budget_usd
- `SecurityConfig` -- audit_logging, pii_sanitization
- `HallucinationGuardConfig` -- thresholds, failure_action

**Environment variable overrides**: Any config value can be overridden
by setting `HYBRIDRAG_<SECTION>_<KEY>` (e.g., `HYBRIDRAG_OLLAMA_MODEL`).

**Hardware profiles** (`config/profiles.yaml`):
- `laptop_safe` -- 8-16 GB RAM, batch=16, conservative
- `desktop_power` -- 32-64 GB RAM, batch=64, aggressive
- `server_max` -- 64 GB+ RAM, batch=128, maximum throughput

---

## 13. Performance Characteristics

| Metric | Value | Conditions |
|--------|-------|-----------|
| Embedding speed | ~100 chunks/sec | CPU, all-MiniLM-L6-v2 |
| Vector search | < 100 ms | 2000 chunks, block scan |
| FTS5 keyword search | < 10 ms | 2000 chunks |
| Index skip (unchanged file) | < 1 sec | Hash-based change detection |
| RAM during indexing | ~500 MB | Model + active block buffers |
| RAM during search | ~300 MB | Model + memmap overhead |
| Disk per 1M chunks | ~0.75 GB | float16 embeddings only |
| Online query latency | 2-5 sec | GPT-3.5 Turbo via API |
| Offline query latency | 5-180 sec | Ollama, hardware dependent |

---

## 14. Version History (Hardening Changes)

### v3.1 (Session 9 -- 2026-02-20)

8 hardening improvements applied from iterative simulation testing:

1. **JSONDecodeError guard** (`vector_store.py`) -- Corrupted
   `embeddings_meta.json` triggers reinitialization instead of crash
2. **HttpResponse.retry_count** (`http_client.py`) -- Zero-cost
   observability for retry tracking on HTTP calls
3. **boot_timestamp** (`boot.py`) -- ISO timestamp recorded on every
   boot for correlation with logs
4. **URL format validation** (`boot.py`) -- Validates `http://` or
   `https://` prefix before configuring the network gate
5. **GUARD_VERSION** (`hallucination_guard/__init__.py`) -- Runtime
   version string for the hallucination guard package
6. **IndexingError** (`exceptions.py`) -- Typed exception for
   unrecoverable file errors during indexing
7. **FaultAnalyzer architecture note** (`fault_analysis.py`) -- Flags
   656-line class for decomposition when next modified
8. **Non-programmer commentary** -- All modules and parsers annotated
   with plain-English explanations of what each file does and why
