# HybridRAG3 -- Technical Theory of Operation

Revision: B | Date: 2026-02-25

---

## 1. System Architecture Overview

HybridRAG3 is a local-first Retrieval-Augmented Generation (RAG) system
with quad-mode LLM routing (Transformers direct, vLLM, Ollama, or
OpenAI-compatible API), hybrid search (vector + BM25 via Reciprocal Rank
Fusion), a semantic query cache, a 5-layer hallucination guard, PII
scrubbing, and a centralized network gate enforcing zero-trust outbound
access control.

```
     INDEXING PIPELINE                    QUERY PIPELINE

     Source files                         User question
     (.pdf, .docx, ...)                        |
            |                                  v
            v                           +----------------+
     +----------------+                 | Query Cache    |
     | Parser         |                 | (semantic LRU) |
     | Registry       |                 +----------------+
     | (28 parsers)   |                   |  miss    | hit
     +----------------+                   v          v
            |                       +-----------+  instant
            v                       | Embedder  |  return
     +----------------+             | (Ollama)  |
     | Chunker        |             +-----------+
     | (1200c, 200    |                   |
     |  overlap)      |                   v
     +----------------+             +----------------+
            |                       |   Retriever    |
            v                       |  Hybrid search |
     +----------------+             |  RRF k=60      |
     | Embedder       |             +----------------+
     | nomic-embed    |                   |
     | (768-dim)      |                   v
     +----------------+             +----------------+
            |                       |  Query Engine  |
            v                       |  9-rule prompt |
     +----------------+             |  + LLM call    |
     | VectorStore    |             |  (streaming)   |
     | SQLite + FTS5  |             +----------------+
     | Memmap f16     |                   |
     +----------------+                   v
            ^                       +----------------+
            |                       | Hallucination  |
            |                       | Guard          |
            +-- Retriever reads --> | (5-layer,      |
                from here           |  online only)  |
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
  |-- embedder.py       (Ollama HTTP wrapper for nomic-embed-text)
  |-- vector_store.py   (SQLite + memmap dual store)
  |-- chunker.py        (text splitter with boundary detection)
  |-- indexer.py        (orchestrates parse -> chunk -> embed -> store)
  |-- retriever.py      (hybrid search: vector + BM25 + RRF)
  |-- query_cache.py    (semantic LRU cache, cosine similarity keyed)
  |-- query_engine.py   (orchestrates cache -> search -> context -> LLM -> answer)
  |-- query_classifier.py (categorizes queries into 9 use-case profiles)
  |-- query_expander.py (synonym expansion, rephrasing for better recall)
  |-- llm_router.py     (TransformersRouter + vLLM + Ollama + API routing)
  |-- cost_tracker.py   (singleton cost accumulator + SQLite persistence)
  |-- fault_analysis.py (severity classification, fix suggestions, flight recorder)
  |-- golden_probe_checks.py  (automated health probes: Ollama, disk, index)
  +-- hallucination_guard/    (5-layer verification, online mode only)

security/
  |-- credentials.py         (keyring + env + config credential resolution)
  +-- pii_scrubber.py        (regex PII detection, online mode only)

parsers/registry.py  (extension -> parser class mapping, 28 parser files)
  |-- pdf_parser.py          (pdfplumber extraction)
  |-- pdf_ocr_fallback.py    (Tesseract fallback for scanned PDFs)
  |-- office_docx_parser.py  (python-docx paragraph extraction)
  |-- office_pptx_parser.py  (python-pptx slide/shape extraction)
  |-- office_xlsx_parser.py  (openpyxl row extraction, read-only mode)
  |-- eml_parser.py          (stdlib email + attachment extraction)
  |-- image_parser.py        (Tesseract OCR)
  |-- plain_text_parser.py   (direct UTF-8 read)
  +-- text_parser.py         (routing parser, delegates by extension)

tools/
  +-- bulk_transfer_v2.py    (enterprise file transfer with atomic writes)
      |-- transfer_manifest.py  (SQLite manifest tracking every file)
      +-- transfer_staging.py   (three-stage directory manager)

gui/                         (tkinter desktop application, dark/light theme)
  |-- app.py                 (main window, NavBar view switching)
  |-- theme.py               (dark/light themes, zoom scaling 50%-200%)
  |-- scrollable.py          (canvas+scrollbar wrapper for long views)
  |-- launch_gui.py          (entry point, boot + background loading)
  +-- panels/
      |-- nav_bar.py         (horizontal tab bar: Query/Data/Settings/Cost/Ref)
      |-- query_panel.py     (question input, streaming answer, metrics)
      |-- index_panel.py     (indexer progress bar, start/stop)
      |-- data_panel.py      (drive browser, bulk transfer, live progress)
      |-- status_bar.py      (live system health indicators)
      |-- tuning_tab.py      (retrieval sliders, LLM tuning, profile switch)
      |-- api_admin_tab.py   (credentials, data paths, model selection)
      |-- cost_dashboard.py  (PM cost dashboard, ROI calculator)
      |-- reference_panel.py (source document browser)
      |-- setup_wizard.py    (first-run 4-step configuration)
      +-- loading_overlay.py (splash screen during background boot)

api/                         (FastAPI REST server)
  |-- server.py              (lifespan management, app factory)
  |-- routes.py              (endpoint handlers)
  +-- models.py              (Pydantic request/response schemas)

mcp_server.py                (MCP server: JSON-RPC over stdio for AI agents)
```

---

## 3. Indexing Pipeline

### 3.1 Parser Registry

`src/parsers/registry.py` maps 24+ file extensions to 28 parser classes.
Each parser implements:

```python
def parse(self, file_path: str) -> str
def parse_with_details(self, file_path: str) -> Tuple[str, Dict[str, Any]]
```

Supported formats: PDF, DOCX, PPTX, XLSX, DOC (legacy), RTF, EML, MSG,
MBOX, HTML, TXT, MD, CSV, JSON, XML, LOG, YAML, INI, PNG/JPG/TIFF/BMP/
GIF/WEBP (OCR), DXF, STP/STEP, IGS/IGES, STL, VSDX, EVTX, PCAP, CER/
CRT/PEM, ACCDB/MDB.

All parsers are lazy-imported to avoid pulling heavy dependencies when
not needed. Every parser wraps its work in try/except and returns
`("", {"error": "..."})` on failure -- a corrupted file never crashes
the pipeline.

### 3.2 Chunker

`src/core/chunker.py` splits raw text into overlapping chunks.

**Parameters:**
- `chunk_size`: 1200 characters (default). Tuned for nomic-embed-text
  which performs best on 200-500 word passages.
- `overlap`: 200 characters. Ensures facts near chunk boundaries are
  not lost.

**Boundary detection** (priority order):
1. Paragraph break (`\n\n`) in the second half of the chunk window
2. Sentence end (`. `) in the second half
3. Any newline in the second half
4. Hard cut at `chunk_size` (last resort)

**Heading prepend**: The chunker searches backward up to 2000 characters
for the nearest section heading (ALL CAPS line, numbered section like
"3.2.1 Signal Processing", or line ending with `:`) and prepends it as
`[SECTION] Heading\n`. This preserves document structure across chunks.

### 3.3 Embedder

`src/core/embedder.py` calls Ollama's `/api/embed` endpoint with
`nomic-embed-text`. This replaced the previous sentence-transformers
approach (MiniLM-L6-v2, 384-dim), removing ~2.5 GB of HuggingFace
dependencies (torch, transformers, sentence-transformers).

- Output: 768-dimensional L2-normalized float32 vectors
- Dimension read from model response at probe time (never hardcoded)
- Batch embedding for indexing (`embed_batch`), single for queries
  (`embed_query`)
- HTTP client: `httpx` to `localhost:11434` (Ollama default)
- Base URL configurable via `OLLAMA_HOST` environment variable
- Model must be pre-pulled: `ollama pull nomic-embed-text`
- No HuggingFace imports, no torch, no GPU required for embedding

**Why nomic-embed-text**:
- 768 dimensions: higher quality than 384-dim MiniLM
- 8192 token context: handles long chunks without truncation
- Served by Ollama: same server that runs the LLM, no extra dependencies
- Apache 2.0 license: no use-case restrictions
- ~274 MB model weight (managed by Ollama, not pip)

### 3.4 VectorStore (Dual Storage)

`src/core/vector_store.py` manages two coordinated backends:

**SQLite** (`hybridrag.sqlite3`):
- `chunks` table: id, text, source_path, chunk_index, metadata JSON
- `chunks_fts` FTS5 virtual table: auto-synchronized, provides BM25
  keyword search via SQLite full-text search engine
- `index_runs` table: run audit trail (run_id, timestamps, counts)
- Uses `INSERT OR IGNORE` with deterministic chunk IDs for crash-safe
  restarts (same file + position = same ID)

**Memmap** (`embeddings.f16.dat` + `embeddings_meta.json`):
- Raw float16 matrix of shape `[N, 768]` memory-mapped via numpy
- Disk-backed: the OS loads only the pages being read, like reading
  specific pages from a book without loading the entire book into memory
- 8 GB RAM laptop can search 10M+ embeddings
- JSONDecodeError guard on meta file load: corrupted JSON triggers
  reinitialization instead of crash

**Why two systems**: SQLite handles structured queries. Memmap handles
millions of vectors without loading them all into RAM.

**Why float16**: Halves storage (1.5 GB vs 3.0 GB per million 768-dim
chunks) with negligible quality loss. Like rounding GPS coordinates to
3 decimal places instead of 6 -- you lose sub-meter precision but still
find the right neighborhood.

**Why memmap over FAISS**: Simpler, no C++ dependencies, sufficient for
< 500K chunks. Migration to FAISS IVF planned for scale-out (see
`docs/research/FAISS_MIGRATION_PLAN.md`).

### 3.5 Indexer Orchestration

`src/core/indexer.py` ties the pipeline together:

1. Scan source folder recursively for supported extensions
2. Compute file hash (size + mtime) for change detection
3. Skip files whose hash matches stored hash (already indexed)
4. Parse to raw text via ParserRegistry
5. Process in 200K character blocks to cap peak RAM
6. Chunk text into overlapping segments
7. Embed chunks in batches via Ollama
8. Store chunks in SQLite and embeddings in memmap
9. Garbage collect between files to bound RAM usage
10. Delete orphaned chunks (source file deleted since last run)
11. Rebuild FTS5 index

**Anti-sleep**: On Windows, `SetThreadExecutionState` prevents the OS
from sleeping during long indexing runs (6+ hours overnight).

---

## 4. Query Pipeline

### 4.1 Semantic Query Cache

`src/core/query_cache.py` -- LRU cache keyed by embedding cosine
similarity. Checked before the full retrieval + LLM pipeline runs.

**Key properties:**
- Semantic matching: compares 768-dim query embeddings via cosine
  similarity, threshold 0.95 (conservative). "What is the max temp?"
  matches "What is the maximum temperature?" without exact string match.
- LRU eviction: monotonic access counter breaks ties on Windows (where
  `time.time()` has ~15ms resolution). Max 500 entries default.
- Thread-safe: `threading.Lock` on all get/put operations.
- Disabled during eval: `cache.enabled = False` prevents masking
  regressions in the evaluation harness.
- Pure in-memory: ephemeral, dies with process. Stale cached answers
  are worse than no cache at all.

**Performance**: Similarity search is O(N) where N = cache size. With
768-dim normalized vectors, numpy dot product over 500 entries < 0.1ms.

### 4.2 Retriever (Hybrid Search)

`src/core/retriever.py` implements three search strategies:

**Vector search**: Query embedding dot-producted against memmap in
blocks of 25,000 rows. Returns top candidates by cosine similarity.
Block-based scanning avoids loading the full embedding matrix.

**BM25 keyword search**: FTS5 OR-logic query against `chunks_fts`.
OR-logic (not AND) ensures partial matches are returned. Critical for
exact terms: part numbers, acronyms, technical jargon.

**Hybrid search (default)**: Both searches run, then results are merged
via Reciprocal Rank Fusion (RRF). RRF works like combining two judges'
rankings: if Judge A ranks a chunk #1 and Judge B ranks it #3, that chunk
scores higher than one ranked #5 by both. The formula:

```
rrf_score(chunk) = sum( 1 / (k + rank_i) )  for each list i
```

where `k = 60` (standard from the original RRF paper). RRF scores are
multiplied by 30 and capped at 1.0 to normalize into the same range as
cosine similarity, enabling a single `min_score` threshold.

**Optional cross-encoder reranker**: Retrieves `reranker_top_n` (20)
candidates, reranks with cross-encoder. Disabled by default. WARNING:
enabling for multi-type evaluation destroys unanswerable (100->76%),
injection (100->46%), and ambiguous (100->82%) scores.

**Tunable parameters:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `hybrid_search` | true | Enable vector + BM25 fusion |
| `top_k` | 5 | Chunks sent to LLM |
| `min_score` | 0.10 | Minimum similarity to include |
| `rrf_k` | 60 | RRF smoothing constant |
| `reranker_enabled` | false | Cross-encoder reranking |
| `reranker_top_n` | 20 | Candidates for reranker |

### 4.3 Query Engine

`src/core/query_engine.py` orchestrates the full query:

1. Check semantic cache for near-identical previous query
2. If cache miss: embed user query via `embedder.embed_query()`
3. Classify query into use-case profile via `query_classifier`
4. Optionally expand query with synonyms via `query_expander`
5. Retrieve top-K chunks via `retriever.search()`
6. Build context string from retrieved chunks
7. Construct LLM prompt using 9-rule source-bounded generation
8. Route to LLM via `llm_router` (offline or online, streaming or batch)
9. Calculate token cost estimate (online mode)
10. Store result in semantic cache
11. Return `QueryResult(answer, sources, tokens, cost, latency, mode)`

**9-rule prompt system** (`_build_prompt()`):
- Priority: injection/refusal > ambiguity > accuracy > formatting
- Rule 5 (injection): refer to false claims generically, never name them
- Rule 8 (source quality): filters indexed test metadata
- Rule 9 (exact line): subordinate to Rule 4 (ambiguity)

**Failure paths**: 0 results returns "no relevant documents found"
without calling LLM. LLM timeout still returns search results with
error flag. Every path returns a valid `QueryResult` -- no exceptions
propagate.

### 4.4 LLM Router

`src/core/llm_router.py` routes to the appropriate backend. Four router
classes, one orchestrator:

- **Offline (TransformersRouter)**: Loads a HuggingFace model directly
  into GPU memory using 4-bit quantization (bitsandbytes). Fits 14B
  parameter models into 12 GB VRAM. Highest priority in offline mode
  when `transformers_llm.enabled=true`. Dependencies lazy-imported
  (transformers, torch, accelerate, bitsandbytes -- only when enabled).
  Config: `transformers_llm.model`, `load_in_4bit`, `device_map`.
- **Offline (VLLMRouter)**: HTTP POST to `localhost:8000/v1/chat/completions`.
  OpenAI-compatible API served by vLLM. Provides continuous batching,
  prefix caching, and tensor parallelism across GPUs. Falls back to
  Ollama silently if vLLM is not running.
- **Offline (OllamaRouter)**: HTTP POST to `localhost:11434/api/generate`.
  Default timeout 600s (CPU inference is slow). Serves as universal
  fallback when vLLM and Transformers are unavailable.
- **Online (APIRouter)**: HTTP POST to OpenAI-compatible
  `/v1/chat/completions`. Uses `openai` SDK. Supports Azure OpenAI,
  Azure Government, and standard OpenAI endpoints with deployment
  discovery. PII scrubbing runs before any data is sent (see section 6.1).

**Priority order**: TransformersRouter > VLLMRouter > OllamaRouter
(offline mode). APIRouter used only in online mode.

Network Gate is checked before every outbound connection.

**Streaming support:**

| Backend | Streaming | Mechanism |
|---------|-----------|-----------|
| OllamaRouter | Yes | `httpx.stream()` + `iter_lines()`, `"stream": true` in payload |
| VLLMRouter | Yes | SSE via `/v1/chat/completions` with `"stream": true` |
| TransformersRouter | No | Falls back to single-chunk yield |
| APIRouter | No | Single-chunk yield |

All backends expose `query_stream(prompt)` returning a `Generator` that
yields `{"token": text}` dicts for incremental display and a final
`{"done": True, "tokens_in": N, "tokens_out": N, "latency_ms": N}`.

**Dual-environment proxy support** (online mode):
- `_build_httpx_client()` reads `HTTPS_PROXY`, `REQUESTS_CA_BUNDLE`,
  and `SSL_CERT_FILE` environment variables
- Auto-detects provider (Azure, Azure Government, standard OpenAI)
  from endpoint URL
- Separate config for home network (direct) vs work network (proxy +
  custom CA bundle)

**Deployment discovery** (online mode):
- `_deployment_cache`: caches available deployments
- `is_azure_endpoint()`: detects Azure vs standard OpenAI
- `get_available_deployments()`: lists chat/embedding models

---

## 5. Hallucination Guard

`src/core/hallucination_guard/` -- 6 files, each under 500 lines.
Active only in online mode.

| Layer | Module | Function |
|-------|--------|----------|
| 1 | `prompt_hardener.py` | Injects grounding instructions into system prompt |
| 2a | `claim_extractor.py` | Splits response into individual factual claims |
| 2b | `nli_verifier.py` | NLI model checks each claim vs source chunks |
| 3-4 | `response_scoring.py` | Scores faithfulness, constructs safe response |
| 5 | `dual_path.py` | Optional dual-model consensus for critical queries |

**Configuration:**
- `threshold`: 0.80 default (minimum faithfulness score)
- `failure_action`: "block" (replace with safe response) or "warn" (flag)
- `shortcircuit_pass`: 5 (skip remaining checks after N consecutive passes)
- `shortcircuit_fail`: 3 (abort after N consecutive failures)
- `enable_dual_path`: false (opt-in for critical queries)

**Built-In Test**: Runs on first import (< 50ms, no model loading, no
network). Validates all guard components are importable and intact.

---

## 6. Security Architecture

### 6.1 PII Scrubber

`src/security/pii_scrubber.py` -- Regex-based PII detection and
replacement. Active only on the online code path when
`security.pii_sanitization` is enabled (default: true).

**Patterns** (order matters -- most specific first):

| Pattern | Placeholder | Example |
|---------|-------------|---------|
| SSN | `[SSN]` | 123-45-6789 |
| Credit card | `[CARD]` | 4111-1111-1111-1111 |
| Email | `[EMAIL]` | user@example.com |
| Phone (US) | `[PHONE]` | (555) 123-4567, +1-555-123-4567 |
| IPv4 | `[IP]` | 192.168.1.1 (skips 127.x.x.x) |

`scrub_pii(text) -> (scrubbed_text, replacement_count)`. Compiled regex
patterns at module load time. No external dependencies (stdlib re only).
Called by `APIRouter.query()` before sending to the cloud API.

### 6.2 Network Gate

`src/core/network_gate.py` -- Centralized outbound access control.

| Mode | Allowed Destinations | Use Case |
|------|---------------------|----------|
| `offline` | `localhost`, `127.0.0.1` only | Default. Air-gapped use. |
| `online` | Localhost + configured API endpoint | Daily use on network |
| `admin` | Unrestricted (with logging) | Maintenance only |

`gate.check_allowed(url, purpose, caller)` raises `NetworkBlockedError`
if URL is not in allowlist. Works like a building security desk: every
visitor (URL) is checked against the guest list, and every visit
(allowed or denied) is written in the log book.

### 6.3 Network Lockdown

| Layer | Mechanism | Blocks |
|-------|-----------|--------|
| 1. Application | NetworkGate URL allowlist | All outbound URLs |
| 2. Configuration | SEC-001: API endpoint defaults to empty | Accidental cloud calls |

With the migration from sentence-transformers to Ollama-served embeddings,
the HuggingFace lockdown layers (HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE)
are no longer required for the core pipeline. These environment variables
are still set when the optional TransformersRouter is enabled (4-bit GPU
inference) to prevent model downloads at runtime.

### 6.4 Credential Management

`src/security/credentials.py` resolves API keys (priority order):
1. Windows Credential Manager (DPAPI encrypted, tied to Windows login)
2. Environment variable (`HYBRIDRAG_API_KEY`)
3. Config file (not recommended, logged as warning)

Extended credential fields: api_key, endpoint, deployment, api_version,
provider, auth_scheme. `source_*` fields track provenance. Keys never
logged in full -- `key_preview()` returns masked form (`sk-...xxxx`).

Provider resolution supports dual-environment deployment:
- `HYBRIDRAG_API_PROVIDER` env var or keyring entry
- Auto-detection from endpoint URL (Azure vs Azure Government vs OpenAI)

---

## 7. Boot Pipeline

`src/core/boot.py` -- Single entry point for initialization.

1. Record `boot_timestamp` (ISO format)
2. Load YAML configuration
3. Resolve credentials via `credentials.py` (including provider)
4. Validate config + credentials together
5. Validate endpoint URL format (`http://` or `https://` prefix)
6. Configure NetworkGate to appropriate mode
7. Build API client (if online + credentials available)
8. Probe Ollama (if offline configured)
9. Probe vLLM (if enabled, non-blocking)
10. Return `BootResult` with `success`, `online_available`,
    `offline_available`, `warnings[]`, `errors[]`, and `summary()`

Never crashes on missing credentials -- marks mode as unavailable and
continues. Like a car that starts even if the GPS is not connected.
Offline mode always works even without API configuration.

---

## 8. GUI Architecture

`src/gui/` -- Tkinter desktop application (Python stdlib, zero extra GUI deps).

### 8.1 Startup Sequence

1. Check if first-run setup is needed (`needs_setup()`)
2. If needed, show Setup Wizard (4-step modal: welcome, data paths,
   mode selection, review/confirm)
3. Boot pipeline runs (2-4 seconds)
4. Main window opens with loading overlay
5. Heavy backends (embedder, vector store, query engine) load in a
   background thread via `queue.Queue` + `root.after(100, poll)` pattern
6. Loading overlay dismisses when backends finish
7. Views become functional

### 8.2 NavBar View Switching

`src/gui/panels/nav_bar.py` -- Horizontal segmented control at the top
of the main window. Replaces old multi-window navigation.

Tabs: **Query** | **Data** | **Settings** | **Cost** | **Ref**

Visual feedback: colored background + bold font + 3px accent underline
for the active tab. Tab switching via `pack_forget()`/`pack()` -- instant,
no rebuilding. Lazy-built views: Settings, Cost, Ref built on first access;
Query built eagerly on startup.

### 8.3 Views

- **Query View** (`query_panel.py`): Use-case dropdown, model auto-selection,
  question input, streaming answer display with sources, latency/token/cost
  metrics. Answers stream token-by-token in offline mode (Ollama/vLLM).
- **Data View** (`data_panel.py` + `index_panel.py`): Drive browser, folder
  picker, bulk transfer from network drives with live progress/ETA/per-extension
  breakdown. Indexer panel with Start/Stop and progress bar.
- **Settings View** (`tuning_tab.py` + `api_admin_tab.py`):
  - Tuning tab: Retrieval sliders (top_k, min_score, rrf_k), LLM tuning
    (temperature, timeout), hardware profile switching, model ranking table
  - API Admin tab: API credentials with Test Connection, data paths with
    folder pickers, PII scrubber toggle, online model selection with
    benchmark scores, save/restore admin defaults
- **Cost View** (`cost_dashboard.py`): Live session spend, budget gauge bar
  (green/yellow/red at 60%/85%), token breakdown (input/output with rate
  math), data volume, cumulative team stats, ROI calculator (time saved,
  value saved, net ROI with team monthly projection), export CSV, editable
  rate spinboxes.
- **Reference View** (`reference_panel.py`): Source document browser.
- **Status Bar** (`status_bar.py`): Live 5-second refresh -- Ollama status,
  LLM model, Network Gate mode (color-coded green/red).

### 8.4 GUI Infrastructure

- **Theme** (`theme.py`): Dark/light toggle. Zoom scaling 50%-200% via
  View menu. Recalculates all font tuples (FONT, FONT_BOLD, FONT_TITLE,
  FONT_SECTION) on zoom change. `_theme_widget()` recursively applies
  colors to frame hierarchies.
- **Scrollable** (`scrollable.py`): `ScrollableFrame` wraps
  Canvas + Scrollbar. Mousewheel binds on enter/leave. Inner frame width
  syncs with canvas. Used by Settings, Cost, API Admin, and Data views.
- **Loading Overlay** (`loading_overlay.py`): Splash screen during
  background boot. Dismisses when backends finish loading.
- **Setup Wizard** (`setup_wizard.py`): 4-page modal dialog for first-run
  configuration. Bypassed when `setup_complete: true` in config or
  `HYBRIDRAG_DATA_DIR` env var is set.

**Threading safety**: All background work uses `queue.Queue` for
thread-to-GUI communication. `threading.Event` for cancellation.
Never `after_idle()` (known Tcl memory-exhaustion hazard). All long
operations (indexing, bulk transfer, API calls) run in daemon threads
with GUI updates via `self.after(0, callback)`.

### 8.5 Cost Tracking Subsystem

`src/core/cost_tracker.py` -- In-memory cost accumulator with SQLite
persistence for program management oversight.

**Architecture:**
- Thread-safe singleton accessed via `get_cost_tracker()` factory
- Each application launch generates a unique `session_id` (12-char hex)
- Per-query cost events accumulate in memory for instant GUI display
- SQLite provides durable cross-session storage for team-wide reporting
- Auto-flush timer persists in-memory events to SQLite every 30 seconds
- Explicit `shutdown()` flushes remaining events and cancels the timer

**Data classes:**

| Class | Purpose |
|-------|---------|
| `CostEvent` | Single API cost record: session, model, mode, tokens in/out, cost, latency, data bytes |
| `SessionSummary` | Aggregated stats for current session: query count, total cost, avg latency, avg cost/query |
| `CumulativeSummary` | All-time stats across all sessions: total sessions, queries, cost, date range |
| `CostRates` | Token pricing per 1M tokens (input and output), with label |

**SQLite tables** (`logs/cost_tracking.db`):

| Table | Columns | Purpose |
|-------|---------|---------|
| `cost_events` | id, session_id, timestamp, profile, model, mode, tokens_in, tokens_out, input_cost_usd, output_cost_usd, total_cost_usd, data_bytes_in, data_bytes_out, latency_ms | Per-query cost log |
| `cost_rates` | id, timestamp, input_rate_per_1m, output_rate_per_1m, label | Rate change audit trail |

Deduplication: `cost_events` has a UNIQUE constraint on
`(session_id, timestamp, tokens_in, tokens_out)` with `INSERT OR IGNORE`,
so repeated flushes of the same events are idempotent.

**Listener pattern**: GUI components register callbacks via
`add_listener(callback)`. When `record()` creates a new CostEvent, all
registered listeners are invoked synchronously. The CostDashboard uses
`self.after(0, self._refresh_all)` inside its listener to marshal the
update onto the Tk main thread safely.

**Data flow:**
```
query_panel.py  --record()--> CostTracker (in-memory)
                                   |
                              flush (30s timer)
                                   |
                                   v
                          cost_tracking.db (SQLite)
                                   ^
                                   |
                          CostDashboard reads summaries
```

---

## 9. REST API

`src/api/server.py` -- FastAPI with lifespan management.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server status + versions |
| `/status` | GET | Index status, LLM status, Gate mode |
| `/config` | GET | Current configuration |
| `/query` | POST | Execute a query |
| `/index` | POST | Start background indexing |
| `/index/status` | GET | Indexing progress |
| `/mode` | POST | Switch OFFLINE/ONLINE |

Binds to `127.0.0.1:8000` only (no network exposure). TestClient MUST
use context manager: `with TestClient(app) as client:` for lifespan.

---

## 10. MCP Server

`mcp_server.py` -- Model Context Protocol server for AI agent integration.

**Three tools exposed:**

| Tool | Purpose |
|------|---------|
| `hybridrag_search(query)` | Search knowledge base, return answer + source citations |
| `hybridrag_status()` | Return mode, model, availability status |
| `hybridrag_index_status()` | Return document count and index statistics |

**Key design:**
- Lazy initialization: boots HybridRAG on first tool call, not at import
  time. MCP clients checking tool availability do not trigger model loading.
- Thread-safe: boot lock prevents race conditions on first concurrent call.
- Logging to stderr (stdout reserved for MCP JSON-RPC protocol).
- Protocol: JSON-RPC over stdio via FastMCP library.
- No modifications to core modules needed -- imports and calls existing APIs.
- Spawned by MCP clients (IDE extensions, AI tools), not run directly.

---

## 11. Bulk Transfer Engine

`src/tools/bulk_transfer_v2.py` -- Enterprise file transfer for importing
large document collections from network drives.

**Key classes** (all under 500 lines):

| Class | Purpose |
|-------|---------|
| `TransferConfig` | Settings: 8 workers, extension filter, size limits, bandwidth throttle |
| `TransferStats` | Thread-safe counters with 30-second rolling speed window |
| `SourceDiscovery` | Phase 1: walks sources, builds manifest, filters non-RAG files |
| `AtomicTransferWorker` | Phase 2: per-file copy with retry, jitter, hash verification |
| `BulkTransferV2` | Orchestrator coordinating discovery + workers |

**Key capabilities:**
- Atomic copy: write to `.tmp`, SHA-256 verify, atomic rename
- Three-stage staging: incoming, verified, quarantine
- Content-hash deduplication (O(1) manifest lookup)
- Delta sync: mtime first-pass, hash second-pass
- Symlink/junction loop detection
- Long path support (>260 chars on Windows)
- Live progress every 500ms with ETA from rolling speed
- Per-source breakdown stats (copied, bytes, failures, skips)

**Integration:**
- SQLite manifest tracks every file (`transfer_manifest.py`)
- Three-stage directory manager (`transfer_staging.py`)
- GUI Data Panel polls stats live via `TransferStats` object

---

## 12. Health Monitoring (Golden Probes)

`src/core/fault_analysis.py` + `src/core/golden_probe_checks.py` --
Automated health monitoring system.

**Severity levels:**

| Level | Meaning | Action |
|-------|---------|--------|
| SEV-1 | Critical (DB corrupted) | Halt system |
| SEV-2 | High (major feature broken) | Degrade gracefully |
| SEV-3 | Medium (feature degraded) | Continue with warning |
| SEV-4 | Low (cosmetic) | Weekly review |

**Golden probes:**
- `check_config_valid()` -- mode, nested objects, numeric ranges
- `check_disk_space()` -- warns < 1 GB, fails < 100 MB
- `probe_ollama_connectivity()` -- GET localhost:11434
- `probe_api_connectivity()` -- GET /models endpoint
- `probe_embedder_load()` -- Ollama /api/embed test
- `probe_index_readability()` -- SQLite query speed test

**Flight recorder**: Circular buffer of recent events (append-only,
fixed size). Rewindable on failure to show events leading up to crash.
Results logged to `logs/fault_analysis.jsonl`.

**Error taxonomy** (11 classes): NETWORK_ERROR, AUTH_ERROR, API_ERROR,
INDEX_ERROR, and 7 more, each mapped to troubleshooting playbooks with
specific fix suggestions.

---

## 13. Exception Hierarchy

`src/core/exceptions.py` -- Typed tree rooted at `HybridRAGError`.

Every exception includes `fix_suggestion: str` and `error_code: str`.

| Exception | Code | When Raised |
|-----------|------|-------------|
| `ConfigError` | CONF-* | Invalid YAML, missing fields |
| `AuthRejectedError` | AUTH-001 | 401/403 from API |
| `EndpointNotConfiguredError` | NET-002 | API endpoint missing |
| `NetworkBlockedError` | NET-001 | NetworkGate denied connection |
| `EmbeddingError` | EMB-* | Model load failure, dimension mismatch |
| `IndexingError` | IDX-001 | Unrecoverable file error |

---

## 14. Configuration System

`src/core/config.py` loads from `config/default_config.yaml`.

**Nested dataclasses** for type safety:
- `PathsConfig` -- database, embeddings_cache, source_folder
- `EmbeddingConfig` -- model_name, dimension, batch_size, device
- `ChunkingConfig` -- chunk_size, overlap, max_heading_len
- `OllamaConfig` -- base_url, model, timeout_seconds, context_window,
  keep_alive, num_predict, num_thread
- `VLLMConfig` -- base_url, model, timeout_seconds, context_window, enabled
- `TransformersLLMConfig` -- model, max_new_tokens, temperature,
  load_in_4bit, device_map, trust_remote_code, enabled
- `APIConfig` -- endpoint, model, max_tokens, temperature, provider,
  auth_scheme, api_version, timeout_seconds
- `RetrievalConfig` -- top_k, min_score, hybrid_search, rrf_k,
  reranker_enabled, reranker_model, reranker_top_n, min_chunks
- `CostConfig` -- track_enabled, input_cost_per_1k, output_cost_per_1k,
  daily_budget_usd. Persistence file: `logs/cost_tracking.db`
- `SecurityConfig` -- audit_logging, pii_sanitization
- `HallucinationGuardConfig` -- threshold, failure_action, nli_model,
  chunk_prune_k, shortcircuit_pass/fail, enable_dual_path, enabled

**Environment variable overrides**: `HYBRIDRAG_<SECTION>_<KEY>`.

**Hardware profiles** (`config/profiles.yaml`):

| Profile | RAM | Batch | Top_K |
|---------|-----|-------|-------|
| `laptop_safe` | 8-16 GB | 16 | 5 |
| `desktop_power` | 32-64 GB | 64 | 10 |
| `server_max` | 64+ GB | 128 | 15 |

**Model download manifest** (`config/model_manifest.yaml`): Complete
inventory of all AI model weights (embedding, LLM, optional NLI/reranker)
with vendor, country, license, size, download source, air-gap transfer
instructions, and security controls. Makes multi-GB model downloads
auditable for compliance.

---

## 15. Diagnostic Framework

`src/diagnostic/` -- 3-tier test and monitoring system.

| Tier | Module | What It Tests |
|------|--------|--------------|
| Health | `health_tests.py` | 15 pipeline checks (DB, model, paths) |
| Component | `component_tests.py` | Individual unit tests |
| Performance | `perf_benchmarks.py` | Embedding speed, search latency, RAM |

`fault_analysis.py`: Automated fault hypothesis engine. Classifies by
severity (SEV-1 through SEV-4), generates fix suggestions, tracks fault
history via flight recorder. See section 12 for details.

---

## 16. Storage Layout

```
hybridrag.sqlite3
|-- chunks           (id, text, source_path, chunk_index, metadata JSON)
|-- chunks_fts       (FTS5 virtual table, auto-synced with chunks)
|-- index_runs       (run_id, start_time, end_time, file counts)
+-- query_log        (planned: query audit trail)

embeddings.f16.dat   (raw float16 matrix, shape [N, 768])
embeddings_meta.json ({"dim": 768, "count": N, "dtype": "float16"})

logs/cost_tracking.db
|-- cost_events     (per-query cost log: session, tokens, cost, latency)
+-- cost_rates      (rate change audit trail: input/output per 1M tokens)
```

---

## 17. Model Compliance

All offline models must pass regulatory review before deployment.
Full audit: `docs/05_security/DEFENSE_MODEL_AUDIT.md`.

**Approved publishers**: Microsoft (MIT), Mistral AI (Apache 2.0),
Google (Apache 2.0), NVIDIA (Apache 2.0), Nomic AI (Apache 2.0).

**Banned**: All China-origin (Alibaba, DeepSeek, BAAI). Meta/Llama
(license restrictions).

Model definitions: `scripts/_model_meta.py`, `scripts/_set_model.py`.
Model manifest: `config/model_manifest.yaml`.
Default offline model: `phi4-mini` (`config/default_config.yaml`).
9 use-case profiles: sw, eng, pm, sys, log, draft, fe, cyber, gen.

---

## 18. Evaluation System

**Protected files** (NEVER modify):
- `scripts/run_eval.py`, `tools/eval_runner.py`
- `tools/score_results.py`, `tools/run_all.py`
- `Eval/*.json`

**Scoring formulas:**
- `run_eval.py`: overall = 0.7 * fact + 0.3 * behavior
- `score_results.py`: overall = 0.45 * behavior + 0.35 * fact + 0.20 * citation

Fact matching is case-insensitive substring. Exact spacing matters.
Injection trap: AES_RE regex catches "AES-512" anywhere in answer text.

**Current results**: 98% pass rate on 400-question golden set.

---

## 19. Performance Characteristics

| Metric | Value | Conditions |
|--------|-------|-----------|
| Embedding speed | ~100 chunks/sec | CPU, nomic-embed-text via Ollama |
| Vector search | < 100 ms | 40K chunks, block scan |
| FTS5 keyword search | < 10 ms | 40K chunks |
| Cache hit | < 0.1 ms | Semantic LRU, 768-dim cosine |
| Index skip (unchanged) | < 1 sec | Hash-based detection |
| RAM (indexing) | ~500 MB | Ollama + active block buffers |
| RAM (search) | ~300 MB | Ollama + memmap overhead |
| Disk per 1M chunks | ~1.5 GB | float16, 768-dim embeddings |
| Online query latency | 2-5 sec | API via configured endpoint |
| Offline query latency (vLLM) | 2-5 sec | Workstation GPU, vLLM serving |
| Offline query latency (Ollama) | 5-180 sec | Ollama, hardware dependent |

---

## 20. Scale-Out Path

Current memmap brute-force search is O(N) and will not scale beyond
~500K vectors without unacceptable latency. Planned migration:

- **Phase 1**: `faiss-cpu` with `IVF256,SQ8` as drop-in replacement
- **Phase 2**: `IVF4096,SQ8` for 50M+ vectors (~18.6 GB, 90-95% recall)
- **Phase 3**: GPU-accelerated FAISS on dual RTX 3090 workstation
  (requires WSL2 or native Linux -- no Windows GPU FAISS support)

Full analysis: `docs/research/FAISS_MIGRATION_PLAN.md`.

---

## 21. Key Dependencies

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| numpy | 1.26.4 | BSD-3 | Numerical arrays, memmap |
| pdfplumber | 0.11.9 | MIT | PDF extraction |
| python-docx | 1.2.0 | MIT | Word documents |
| python-pptx | 1.0.2 | MIT | PowerPoint |
| openpyxl | 3.1.5 | MIT | Excel |
| httpx | 0.28.1 | BSD-3 | HTTP client (Ollama, vLLM) |
| openai | 1.45.1 | MIT | OpenAI/Azure SDK |
| fastapi | 0.115.0 | MIT | REST API framework |
| uvicorn | 0.41.0 | BSD-3 | ASGI server |
| keyring | 23.13.1 | MIT | Windows Credential Manager |
| cryptography | 44.0.2 | Apache/BSD | Encryption |
| pydantic | 2.11.1 | MIT | Data validation |
| structlog | 24.4.0 | Apache 2.0 | Structured logging |
| PyYAML | 6.0.2 | MIT | YAML parsing |
| tiktoken | 0.8.0 | MIT | Token counting |
| lxml | 6.0.2 | BSD-3 | XML/HTML parsing |
| pytesseract | 0.3.13 | Apache 2.0 | OCR via Tesseract |
| pillow | 12.1.0 | PIL | Image processing |

**Runtime servers** (not pip packages):
- Ollama (serves nomic-embed-text embeddings + LLM inference)
- vLLM (optional, workstation GPU inference)

**Removed in RevB** (HuggingFace retirement):
- torch, sentence-transformers, transformers, scikit-learn, accelerate
- Install size reduced from ~800 MB to ~200 MB
