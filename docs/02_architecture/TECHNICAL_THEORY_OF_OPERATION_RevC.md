# HybridRAG3 -- Technical Theory of Operation

Revision: C | Date: 2026-02-25

---

## 1. System Architecture Overview

HybridRAG3 is a local-first Retrieval-Augmented Generation (RAG) system
with dual-mode LLM routing (offline via vLLM/Ollama, online via
OpenAI-compatible API), hybrid search (vector + BM25 via Reciprocal Rank
Fusion), a 5-layer hallucination guard, and a centralized network gate
enforcing zero-trust outbound access control.

```
     INDEXING PIPELINE                    QUERY PIPELINE

     Source files                         User question
     (.pdf, .docx, ...)                        |
            |                                  v
            v                           +------------------+
     +------------------+               |   Embedder       |
     | Parser           |               |   Ollama         |
     | Registry         |               |   /api/embed     |
     | (24+ ext)        |               |   nomic-embed-   |
     +------------------+               |   text (768-dim) |
            |                           +------------------+
            v                                  |
     +------------------+                      v
     | Chunker          |               +------------------+
     | (1200c, 200      |               |   Retriever      |
     |  overlap)        |               |   Hybrid search  |
     +------------------+               |   RRF k=60       |
            |                           +------------------+
            v                                  |
     +------------------+                      v
     | Embedder         |               +------------------+
     | Ollama           |               |  Query Engine    |
     | /api/embed       |               |  9-rule prompt   |
     | nomic-embed-text |               |  + LLM call      |
     | (768-dim)        |               +------------------+
     +------------------+                      |
            |                                  v
            v                           +------------------+
     +------------------+               | Hallucination    |
     | VectorStore      |               | Guard            |
     | SQLite + FTS5    |               | (5-layer,        |
     | Memmap f16       |               |  online only)    |
     | [N, 768]         |               +------------------+
     +------------------+
            ^                                  |
            |                                  |
            +--- Retriever reads from here ----+
```

**Design priorities**: Offline operation, crash safety, low RAM usage,
full auditability, zero external server dependencies.

**RevC changes from RevB**: Bulk transfer engine hardened for production
nightly sync (VPN resilience, memory safety, JSON event logging, 80 stress
tests). Desktop_power hardware profile set as default for all machines
(work: 64 GB / 12 GB GPU; home: 128 GB / 48 GB dual-3090). 22 QA bug fixes across 15 files.
Test suite expanded to 406 pytest + 745 virtual + 140 setup simulation.

**RevB changes from RevA**: Embedder migrated from sentence-transformers
MiniLM-L6-v2 (384-dim) to Ollama nomic-embed-text (768-dim). All
HuggingFace dependencies retired (~2.5 GB removed). GUI redesigned
as single-window with lazy NavBar view switching. Cost dashboard
upgraded with ROI calculator. vLLM added as high-performance offline
backend. API client factory with proxy auto-detection.

---

## 2. Module Dependency Graph

```
boot.py  (entry point -- constructs all services)
  |-- config.py             (YAML loader, dataclass validation)
  |-- credentials.py        (Windows Credential Manager / env var resolution)
  |-- network_gate.py       (URL allowlist, 3-mode access control)
  |-- api_client_factory.py (8-step pre-flight validation, proxy auto-detect)
  |-- embedder.py           (Ollama /api/embed, httpx client)
  |-- vector_store.py       (SQLite + memmap [N, 768] dual store)
  |-- chunker.py            (text splitter with boundary detection)
  |-- indexer.py            (orchestrates parse -> chunk -> embed -> store)
  |-- retriever.py          (hybrid search: vector + BM25 + RRF)
  |-- query_engine.py       (orchestrates search -> context -> LLM -> answer)
  |-- llm_router.py         (vLLM -> Ollama -> API fallback chain)
  |-- cost_tracker.py       (singleton cost accumulator + SQLite persistence)
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

gui/                         (tkinter desktop app, single-window design)
  |-- app.py                 (main window, NavBar view switching)
  |-- theme.py               (dark/light theme, zoom scaling)
  |-- launch_gui.py          (entry point, boot + background loading)
  |-- scrollable.py          (ScrollableFrame for long content)
  |-- helpers.py             (mode_switch utility)
  +-- panels/
      |-- query_panel.py     (question input, answer display, metrics)
      |-- index_panel.py     (folder picker, progress bar, start/stop)
      |-- status_bar.py      (live system health indicators)
      |-- nav_bar.py         (view tab bar: Query/Settings/Cost/Ref)
      |-- engineering_menu.py (tuning sliders, profile switch, test query)
      |-- cost_dashboard.py  (cost tracking, ROI calculator, budget gauge)
      +-- reference_panel.py (reference document viewer)

api/                         (FastAPI REST server)
  |-- server.py              (lifespan management, app factory)
  |-- routes.py              (endpoint handlers)
  +-- models.py              (Pydantic request/response schemas)
```

---

## 3. Indexing Pipeline

### 3.1 Parser Registry

`src/parsers/registry.py` maps 24+ file extensions to parser classes.
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

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `chunk_size` | 1200 chars | Tuned for nomic-embed-text (200-500 word passages) |
| `overlap` | 200 chars | Prevents fact loss near chunk boundaries |

**Boundary detection** (priority order):
1. Paragraph break (`\n\n`) in the second half of the chunk window
2. Sentence end (`. `) in the second half
3. Any newline in the second half
4. Hard cut at `chunk_size` (last resort)

**Heading prepend**: The chunker searches backward up to 2000 characters
for the nearest section heading (ALL CAPS line, numbered section like
"3.2.1 Signal Processing", or line ending with `:`) and prepends it as
`[SECTION] Heading\n`. This preserves document structure across chunks.

**Important**: The chunker takes a config object, not `(chunk_size,
overlap)` positional args. This is a common integration mistake.

### 3.3 Embedder

`src/core/embedder.py` calls Ollama's `/api/embed` endpoint with
`nomic-embed-text`.

**Architecture** (RevB -- HuggingFace retired):

| Property | Value |
|----------|-------|
| Model | nomic-embed-text |
| Dimensions | 768 |
| Context window | 8192 tokens |
| License | Apache 2.0 |
| Serving | Ollama on localhost:11434 |
| Transport | httpx persistent HTTP client |
| Model size | 274 MB (Ollama pull) |

- Output: 768-dimensional L2-normalized float32 vectors
- Dimension detected at startup via probe embedding (never hardcoded)
- Batch embedding for indexing (`embed_batch`), single for queries
  (`embed_query`)
- Persistent httpx.Client with 120s timeout reuses TCP connections
- Batch size controlled by `HYBRIDRAG_EMBED_BATCH` env var (default 64)
- `encode()` alias exists for convenience (diagnostic tools, notebooks)
- `close()` releases HTTP client; instance is not reusable after close

**Startup probe sequence:**
```python
resp = client.post("/api/embed",
    json={"model": "nomic-embed-text", "input": ["dimension probe"]})
dim = len(resp.json()["embeddings"][0])  # 768
```

If Ollama is not running: `RuntimeError("Ollama is not running...")`.
If model not pulled: `RuntimeError("Embedding model not found...")`.

**Why nomic-embed-text over MiniLM-L6-v2 (RevA)**:
- Served by Ollama -- no torch, transformers, or HuggingFace SDK needed
- 768 dimensions vs 384 -- higher semantic resolution
- 8192 token context vs 256 -- handles long chunks without truncation
- Apache 2.0 -- no AI use-case approval required
- Removes ~2.5 GB of Python dependencies

### 3.4 VectorStore (Dual Storage)

`src/core/vector_store.py` manages two coordinated backends:

**SQLite** (`hybridrag.sqlite3`):
- `chunks` table: chunk_pk (autoincrement), chunk_id (UNIQUE),
  source_path, chunk_index, text, text_length, created_at,
  embedding_row, file_hash
- `chunks_fts` FTS5 virtual table: auto-synchronized, provides BM25
  keyword search via SQLite full-text search engine
- File change detection via `file_hash` column (`filesize:mtime_ns`)
- Uses `INSERT OR IGNORE` with deterministic chunk IDs for crash-safe
  restarts (same file + position = same ID)
- SQLite performance pragmas: WAL mode, NORMAL sync, MEMORY temp_store,
  200 MB page cache, 5s busy timeout, foreign keys ON

**Memmap** (`embeddings.f16.dat` + `embeddings_meta.json`):
- Raw float16 matrix of shape `[N, 768]` memory-mapped via numpy
- Disk-backed: the OS loads only the pages being read
- 8 GB RAM laptop can search 10M+ embeddings
- Append-only design: orphaned rows are harmless (nothing in SQLite
  points to them)
- JSONDecodeError guard on meta file load: corrupted JSON triggers
  reinitialization instead of crash
- Meta format: `{"dim": 768, "count": N, "dtype": "float16"}`

**Why two systems**: SQLite handles structured queries and FTS5 keyword
search. Memmap handles millions of vectors without loading them all
into RAM.

**Why float16**: Halves storage (1.5 GB vs 3.0 GB per million chunks at
768 dimensions) with negligible quality loss on normalized vectors.

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
7. Embed chunks in batches via Ollama /api/embed
8. Store chunks in SQLite and embeddings in memmap
9. Garbage collect between files to bound RAM usage
10. Delete orphaned chunks (source file deleted since last run)
11. Rebuild FTS5 index

**Anti-sleep**: On Windows, `SetThreadExecutionState` prevents the OS
from sleeping during long indexing runs (6+ hours overnight).

---

## 4. Query Pipeline

### 4.1 Retriever (Hybrid Search)

`src/core/retriever.py` implements three search strategies:

**Vector search**: Query embedding dot-producted against memmap in
blocks of 25,000 rows. Returns top candidates by cosine similarity.
Block-based scanning avoids loading the full embedding matrix. Block
size configurable via `HYBRIDRAG_RETRIEVAL_BLOCK_ROWS` env var.

**BM25 keyword search**: FTS5 OR-logic query against `chunks_fts`.
OR-logic (not AND) ensures partial matches are returned. Words under
3 characters are filtered. Critical for exact terms: part numbers,
acronyms, technical jargon. BM25 scores normalized to 0.0-1.0 via
`x/(x+1)` transformation.

**Hybrid search (default)**: Both searches run, then results are merged
via Reciprocal Rank Fusion (RRF):

```
rrf_score(chunk) = sum( 1 / (k + rank_i) )  for each list i
```

where `k = 60` (standard from the original RRF paper). RRF scores are
multiplied by 30 and capped at 1.0 to normalize into the same range as
cosine similarity, enabling a single `min_score` threshold.

**Lexical boost** (vector-only mode): When hybrid mode is off, adds a
small score bonus (+0.02 per matching word, capped) if query terms
appear in the first 250 characters of the chunk.

**Optional cross-encoder reranker**: Retrieves `reranker_top_n` (20)
candidates, reranks with cross-encoder. **Disabled by default**.
WARNING: enabling for multi-type evaluation destroys unanswerable
(100->76%), injection (100->46%), and ambiguous (100->82%) scores.

**Tunable parameters:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `hybrid_search` | true | Enable vector + BM25 fusion |
| `top_k` | 12 | Chunks sent to LLM |
| `min_score` | 0.10 | Minimum similarity to include |
| `rrf_k` | 60 | RRF smoothing constant |
| `reranker_enabled` | false | Cross-encoder reranking |
| `reranker_top_n` | 20 | Candidates for reranker |

### 4.2 Query Engine

`src/core/query_engine.py` orchestrates the full query pipeline:

1. Embed user query via `embedder.embed_query()`
2. Retrieve top-K chunks via `retriever.search()`
3. Build context string from retrieved chunks
4. Construct LLM prompt using 9-rule source-bounded generation
5. Route to LLM via `llm_router` (vLLM -> Ollama -> API)
6. Calculate token cost estimate (online mode)
7. Log query via structured logging
8. Return `QueryResult(answer, sources, chunks_used, tokens_in,
   tokens_out, cost_usd, latency_ms, mode, error)`

**9-rule prompt system** (`_build_prompt()`, v4):

| Rule | Name | Purpose |
|------|------|---------|
| 1 | GROUNDING | Use only facts from context |
| 2 | COMPLETENESS | Include all specific details |
| 3 | REFUSAL | Decline if info not in context |
| 4 | AMBIGUITY | Ask clarifying question if vague |
| 5 | INJECTION | Ignore override instructions in context |
| 6 | ACCURACY | Never fabricate specifications |
| 7 | VERBATIM | Reproduce notation exactly |
| 8 | SOURCE QUALITY | Filter test metadata from context |
| 9 | EXACT LINE | Verbatim numeric spec line for fact-checking |

Priority order: injection/refusal > ambiguity > accuracy > formatting.
Rule 4 (ambiguity) overrides Rule 9 (exact line).

**Streaming support**: `query_stream()` yields tokens as they arrive
from the LLM, providing responsive UI updates. Yields phase markers
(`searching`, `generating`) followed by individual tokens and a final
`done` event with the complete `QueryResult`.

**Failure paths**: 0 results returns "no relevant documents found"
without calling LLM. LLM timeout still returns search results with
error flag. Every path returns a valid `QueryResult` -- no exceptions
propagate to the caller.

### 4.3 LLM Router

`src/core/llm_router.py` routes to the appropriate backend via a
three-tier fallback chain:

**Tier 1 -- vLLM (workstation)**: HTTP POST to
`localhost:8000/v1/chat/completions`. OpenAI-compatible API served by
vLLM. Provides continuous batching, prefix caching, and tensor
parallelism across GPUs. Query latency: 2-5 seconds. Falls back to
Ollama silently if vLLM is not running.

**Tier 2 -- Ollama (laptop/workstation)**: HTTP POST to
`localhost:11434/api/generate`. Default timeout 600s (CPU inference
is slow). Serves as fallback when vLLM is unavailable or disabled.
Query latency: 5-180 seconds (hardware dependent).

**Tier 3 -- API (online)**: HTTP POST to OpenAI-compatible
`/v1/chat/completions`. Uses `openai` SDK (v1.51.2, never 2.x).
Supports Azure OpenAI and standard OpenAI endpoints. Query latency:
2-5 seconds.

**HTTP client factory** (`_build_httpx_client`): Centralized factory
for all HTTP clients in the module. Handles three environments:
- Home PC: direct internet, default CA bundle, no proxy
- Work laptop: corporate proxy, custom CA bundle, HTTPS_PROXY env var
- Localhost: Ollama/vLLM -- never uses a proxy

Network Gate is checked before every outbound connection.

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

| Setting | Default | Purpose |
|---------|---------|---------|
| `enabled` | false | Guard is DORMANT (NLI model unavailable) |
| `threshold` | 0.80 | Minimum faithfulness score |
| `failure_action` | "block" | "block" replaces with safe response, "warn" flags |
| `shortcircuit_pass` | 5 | Skip remaining checks after N consecutive passes |
| `shortcircuit_fail` | 3 | Abort after N consecutive failures |
| `enable_dual_path` | false | Opt-in for critical queries |

**NLI verifier status (RevB)**: The NLI verifier is DORMANT since the
retirement of sentence-transformers. It degrades gracefully -- the guard
continues to function with the remaining layers (prompt hardening, claim
extraction, response scoring). Full NLI verification reactivates if a
compatible model is loaded.

**Built-In Test**: Runs on first import (< 50ms, no model loading, no
network). Validates all guard components are importable and intact.

---

## 6. Security Architecture

### 6.1 Network Gate

`src/core/network_gate.py` -- Centralized outbound access control.

| Mode | Allowed Destinations | Use Case |
|------|---------------------|----------|
| `offline` | `localhost`, `127.0.0.1` only | Default. Air-gapped use. |
| `online` | Localhost + configured API endpoint | Daily use on network |
| `admin` | Unrestricted (with logging) | Maintenance only |

`gate.check_allowed(url, purpose, caller)` raises `NetworkBlockedError`
if URL is not in allowlist. Every connection attempt (allowed and
denied) is logged with timestamp, URL, purpose, mode, and result
(ALLOW/DENY) for security audit trail.

### 6.2 Three-Layer Network Lockdown

| Layer | Mechanism | Blocks |
|-------|-----------|--------|
| 1. Environment | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` | HuggingFace model downloads |
| 2. Python | `os.environ` enforcement before import | HuggingFace in any Python process |
| 3. Application | NetworkGate URL allowlist | All other outbound URLs |

All three must fail before unauthorized data leaves the machine. Layer 1
and 2 are now belt-and-suspenders -- with HuggingFace retired in RevB,
they serve as layered protection against accidental reintroduction.

### 6.3 Credential Management

`src/security/credentials.py` resolves API keys (priority order):
1. Windows Credential Manager (DPAPI encrypted, tied to Windows login)
2. Environment variable (`HYBRIDRAG_API_KEY`)
3. Config file (not recommended, logged as warning)

Extended credential fields: api_key, endpoint, deployment, api_version.
`source_*` fields track provenance. Keys never logged in full --
`key_preview()` returns masked form (`sk-...xxxx`).

---

## 7. Boot Pipeline

`src/core/boot.py` -- Single entry point for initialization.

1. Record `boot_timestamp` (ISO format)
2. Load YAML configuration
3. Resolve credentials via `credentials.py`
4. Validate config + credentials together
5. Validate endpoint URL format (`http://` or `https://` prefix)
6. Configure NetworkGate to appropriate mode
7. Build API client via `ApiClientFactory` (if online + credentials)
8. Probe Ollama (if offline configured)
9. Return `BootResult` with `success`, `online_available`,
   `offline_available`, `warnings[]`, `errors[]`, and `summary()`

**BootResult fields:**

| Field | Type | Meaning |
|-------|------|---------|
| `boot_timestamp` | str | ISO timestamp of boot start |
| `success` | bool | True if at least one mode is available |
| `online_available` | bool | API client created successfully |
| `offline_available` | bool | Ollama is configured and reachable |
| `api_client` | Optional | ApiClient instance or None |
| `config` | dict | Loaded configuration |
| `credentials` | dict | Resolved credentials (masked key) |
| `warnings` | list | Non-fatal issues |
| `errors` | list | Fatal issues |

Never crashes on missing credentials -- marks mode as unavailable and
continues. Offline mode always works even without API configuration.

---

## 8. GUI Architecture

`src/gui/` -- Tkinter desktop application (Python stdlib, zero deps).

**Layout**: Single-window with NavBar-driven view switching:

```
+----------------------------------------------------------+
| HybridRAG v3    [OFFLINE/ONLINE toggle]   [Theme toggle] |
+----------------------------------------------------------+
| [Query]  [Settings]  [Cost]  [Ref]       <-- NavBar      |
+----------------------------------------------------------+
|                                                          |
|  Content Frame (view-switched via pack_forget/pack)      |
|                                                          |
|  Views:                                                  |
|    QueryView     -- eager-built at startup               |
|    SettingsView  -- lazy-built on first access            |
|    CostView      -- lazy-built on first access            |
|    ReferenceView -- lazy-built on first access            |
|                                                          |
+----------------------------------------------------------+
| StatusBar: LLM | Ollama | Gate mode (color-coded)        |
+----------------------------------------------------------+
```

**View switching performance**: Views swap via `pack_forget()` /
`pack()` -- under 1 ms, no flicker. Only the Query view is built at
startup; Settings, Cost, and Reference views are constructed on first
access (lazy initialization). Once built, views remain in memory for
instant re-display.

**Startup sequence:**
1. Boot pipeline runs (2-4 seconds)
2. Window opens immediately
3. Heavy backends (embedder, vector store, query engine) load in a
   background thread via `queue.Queue` + `root.after(100, poll)` pattern
4. Panels become functional when backends finish

**Panels:**
- **Query Panel**: Use-case dropdown, model auto-selection, question
  input with streaming, answer display with sources, latency/token/
  cost metrics, cost event emission
- **Index Panel**: Folder picker, Start/Stop, progress bar, status
- **Status Bar**: Live 5-second refresh -- Ollama status, LLM model,
  Network Gate mode (color-coded green/red)
- **NavBar**: Tab buttons (Query, Settings, Cost, Ref) with active
  state highlighting
- **Engineering Menu**: Retrieval sliders (top_k, min_score, rrf_k),
  LLM tuning (temperature, timeout), profile switching, model ranking
- **Cost Dashboard**: Budget gauge, ROI calculator, token breakdown,
  cumulative team stats (see section 8.1)
- **Reference Panel**: Reference document viewer

**Threading safety**: All background work uses `queue.Queue` for
thread-to-GUI communication. `threading.Event` for cancellation.
Never `after_idle()` (known Tcl memory-exhaustion hazard).

### 8.1 Cost Tracking Subsystem

`src/core/cost_tracker.py` -- Thread-safe singleton cost accumulator
with SQLite persistence (481 lines).

**Architecture:**
- Thread-safe singleton accessed via `get_cost_tracker()` factory
- Protected by `threading.Lock` for concurrent access
- Each application launch generates a unique `session_id` (12-char hex)
- Per-query cost events accumulate in memory for instant GUI display
- SQLite provides durable cross-session storage for team-wide reporting
- Auto-flush timer persists in-memory events to SQLite every 30 seconds
- Explicit `shutdown()` flushes remaining events and cancels the timer
- `reset_cost_tracker()` for test isolation (production code never calls)

**Data classes:**

| Class | Purpose |
|-------|---------|
| `CostEvent` | Single API cost record: session, model, mode, tokens in/out, cost, latency, data bytes |
| `SessionSummary` | Aggregated stats for current session: query count, total cost, avg latency, avg cost/query |
| `CumulativeSummary` | All-time stats across all sessions: total sessions, queries, cost, date range |
| `CostRates` | Token pricing per 1M tokens (input and output), with label |

**Listener pattern**: GUI components register callbacks via
`add_listener(callback)`. When `record()` creates a new CostEvent, all
registered listeners are invoked synchronously. The CostDashboard uses
`self.after(0, self._refresh_all)` inside its listener to marshal the
update onto the Tk main thread safely. Listener errors are caught
per-callback so one broken listener does not block others.

**CostDashboard** (`src/gui/panels/cost_dashboard.py`, 518 lines):
- Inline view (not Toplevel) within the main window's Cost tab
- 7-section vertical layout: header, big numbers row (session spend /
  queries / avg cost), budget gauge bar (green/yellow/red color
  transitions at 60% and 85%), token breakdown table (input/output
  with rate math), data volume (KB sent/received), cumulative team
  stats (all sessions from SQLite), editable rate spinboxes
- Budget gauge reads `daily_budget_usd` from CostConfig (default $5.00)
- Export CSV button writes all historical events to a user-chosen file
- Unregisters its listener on window close to avoid orphan callbacks
- Theme-aware: respects dark/light toggle from parent window

**ROI Calculator** (integrated into CostDashboard):
- Three live metrics: TIME SAVED, VALUE SAVED, NET ROI
- Editable parameters:
  - Hourly rate: $48.44 (BLS May 2024 median for knowledge workers)
  - Team size: 10
  - Minutes saved per query: 10
- Team monthly projection line with ROI percentage
- Citations at bottom of panel:
  - (*1) McKinsey 2012 -- knowledge worker time allocation
  - (*2) McKinsey 2023 -- generative AI productivity impact
  - (*3) BLS May 2024 -- occupational wage statistics
  - (*4) Bloomfire/HBR 2025 -- enterprise search ROI

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
use context manager: `with TestClient(app) as client:` for lifespan
events to execute properly.

Request/response schemas defined in `src/api/models.py` using Pydantic
v2 (BaseModel). Routes in `src/api/routes.py`.

---

## 10. Exception Hierarchy

`src/core/exceptions.py` -- Typed tree rooted at `HybridRAGError`.

Every exception includes `fix_suggestion: str`, `error_code: str`,
and `to_dict()` for JSON serialization.

| Exception | Code | When Raised |
|-----------|------|-------------|
| `HybridRAGError` | (base) | Parent of all custom errors |
| `ConfigError` | CONF-* | Invalid YAML, missing fields |
| `AuthRejectedError` | AUTH-001 | 401/403 from API |
| `EndpointNotConfiguredError` | NET-002 | API endpoint missing |
| `ApiKeyNotConfiguredError` | NET-003 | API key not found |
| `InvalidEndpointError` | NET-004 | Malformed endpoint URL |
| `DeploymentNotConfiguredError` | NET-005 | Azure deployment name missing |
| `ProviderConfigError` | NET-006 | Provider detection failed |
| `ApiVersionNotConfiguredError` | NET-007 | Azure API version missing |
| `NetworkBlockedError` | NET-001 | NetworkGate denied connection |
| `EmbeddingError` | EMB-* | Model load failure, dimension mismatch |
| `IndexingError` | IDX-001 | Unrecoverable file error |

---

## 11. Configuration System

`src/core/config.py` loads from `config/default_config.yaml`.
35+ parameters organized in nested dataclasses for type safety.

**Dataclass hierarchy:**

| Dataclass | Key Fields |
|-----------|------------|
| `PathsConfig` | database, embeddings_cache, source_folder |
| `EmbeddingConfig` | model_name (nomic-embed-text), dimension (768), batch_size, device |
| `ChunkingConfig` | chunk_size (1200), overlap (200), max_heading_len |
| `OllamaConfig` | base_url, model, timeout_seconds, context_window |
| `VLLMConfig` | base_url, model, timeout_seconds, context_window, enabled |
| `APIConfig` | endpoint, model, max_tokens, temperature, timeout_seconds (60) |
| `RetrievalConfig` | top_k (12), min_score (0.10), hybrid_search (true), rrf_k (60) |
| `CostConfig` | track_enabled, input_cost_per_1k, output_cost_per_1k, daily_budget_usd ($5.00) |
| `SecurityConfig` | audit_logging, pii_sanitization |
| `HallucinationGuardConfig` | threshold (0.80), failure_action, shortcircuit_pass/fail |

**Environment variable overrides**: `HYBRIDRAG_<SECTION>_<KEY>`.
Example: `HYBRIDRAG_RETRIEVAL_TOP_K=8` overrides `retrieval.top_k`.

**Hardware profiles** (`config/profiles.yaml`):

| Profile | RAM | Batch | Top_K |
|---------|-----|-------|-------|
| `laptop_safe` | 8-16 GB | 16 | 5 |
| `desktop_power` | 32-64 GB | 64 | 10 |
| `server_max` | 64+ GB | 128 | 15 |

**Use-case profiles** (`scripts/_model_meta.py`, `scripts/_set_model.py`):
9 profiles with dual ENG/GEN scoring: sw, eng, pm, sys, log, draft,
fe, cyber, gen. Each profile selects primary and alternate models:

| Profile Group | Primary | Alternate |
|---------------|---------|-----------|
| ENG-heavy (sw, eng, sys, draft, fe, cyber) | phi4-mini | mistral:7b |
| GEN-heavy (pm, gen) | phi4-mini | gemma3:4b |
| Logistics (log) | phi4:14b-q4_K_M (workstation) | phi4-mini |

---

## 12. Diagnostic Framework

`src/diagnostic/` -- 3-tier test and monitoring system.

| Tier | Module | What It Tests |
|------|--------|--------------|
| Health | `health_tests.py` | 15 pipeline checks (DB, model, paths) |
| Component | `component_tests.py` | Individual unit tests |
| Performance | `perf_benchmarks.py` | Embedding speed, search latency, RAM |

`fault_analysis.py`: Automated fault hypothesis engine. Classifies by
severity, generates fix suggestions, tracks fault history.

**Test counts (RevC):**

| Suite | Count | Description |
|-------|-------|-------------|
| pytest | 406 | Unit, integration, and stress tests |
| Virtual | 745 | Configuration permutation tests |
| Setup simulation | 140 | Install and setup scenario tests |

---

## 13. Storage Layout

```
hybridrag.sqlite3
|-- chunks           (chunk_pk, chunk_id, source_path, chunk_index,
|                     text, text_length, created_at, embedding_row,
|                     file_hash)
|-- chunks_fts       (FTS5 virtual table, auto-synced with chunks)
|-- idx_chunks_source   (index on source_path)
+-- idx_chunks_emb_row  (index on embedding_row)

embeddings.f16.dat   (raw float16 matrix, shape [N, 768])
embeddings_meta.json ({"dim": 768, "count": N, "dtype": "float16"})

logs/cost_tracking.db
|-- cost_events     (id, session_id, timestamp, profile, model, mode,
|                    tokens_in, tokens_out, input_cost_usd,
|                    output_cost_usd, total_cost_usd, data_bytes_in,
|                    data_bytes_out, latency_ms;
|                    UNIQUE(session_id, timestamp, tokens_in, tokens_out))
+-- cost_rates      (id, timestamp, input_rate_per_1m,
                     output_rate_per_1m, label)
```

**Memmap disk usage at 768 dimensions:**

| Chunks | float16 | float32 (for comparison) |
|--------|---------|--------------------------|
| 10,000 | 15 MB | 30 MB |
| 100,000 | 150 MB | 300 MB |
| 1,000,000 | 1.5 GB | 3.0 GB |

---

## 14. Model Compliance

All offline models must pass regulatory review before deployment.
Full audit: `docs/05_security/MODEL_AUDIT.md`.

**Approved publishers**: Microsoft (MIT license), Mistral AI (Apache
2.0), Google (Apache 2.0), NVIDIA (Apache 2.0).

**Approved model stack (5 models, ~26 GB total):**

| Model | Parameters | Size | License | Publisher | Use |
|-------|-----------|------|---------|-----------|-----|
| phi4-mini | 3.8B | 2.3 GB | MIT | Microsoft | Primary for 7/9 profiles |
| mistral:7b | 7B | 4.1 GB | Apache 2.0 | Mistral AI | Alt for eng/sys/fe/cyber |
| gemma3:4b | 4B | 3.3 GB | Apache 2.0 | Google | PM fast summarization |
| phi4:14b-q4_K_M | 14B | 9.1 GB | MIT | Microsoft | Logistics primary, workstation |
| mistral-nemo:12b | 12B | 7.1 GB | Apache 2.0 | Mistral AI | Upgrade path (128K ctx) |

**Embedding model:**

| Model | Dimensions | Size | License | Publisher |
|-------|-----------|------|---------|-----------|
| nomic-embed-text | 768 | 274 MB | Apache 2.0 | Nomic AI |

**Banned categories:**
- China-origin: Qwen/Alibaba, DeepSeek, BGE/BAAI (regulatory ban)
- Meta/Llama: License restrictions (ITAR ban)

Model definitions: `scripts/_model_meta.py`, `scripts/_set_model.py`.
Default offline model: `phi4:14b-q4_K_M` (`config/default_config.yaml`).
Waiver reference: `docs/05_security/waiver_reference_sheet.md`.

---

## 15. Evaluation System

**Protected files** (NEVER modify):
- `scripts/run_eval.py`, `tools/eval_runner.py`
- `tools/score_results.py`, `tools/run_all.py`
- `Eval/*.json`

**Scoring formulas:**

| Scorer | Formula |
|--------|---------|
| `run_eval.py` | overall = 0.7 * fact + 0.3 * behavior |
| `score_results.py` | overall = 0.45 * behavior + 0.35 * fact + 0.20 * citation |

Fact matching is case-insensitive substring. Exact spacing matters.

**Injection trap**: AES_RE regex catches "AES-512" anywhere in answer
text. This string is planted in `Engineer_Calibration_Guide.pdf` as
a deliberate false claim. If the LLM reproduces it, the injection
test fails. Rule 5 in the prompt instructs the model to refer to
false claims generically without naming their contents.

**Current results**: 98% pass rate on 400-question golden set
(temperature 0.05). Config: min_score=0.10, top_k=12,
reranker_enabled=false, reranker_top_n=20.

**8 known failures**: 6 log retention (embedding quality), 2
calibration (addressed by Exact: rule).

---

## 16. Performance Characteristics

| Metric | Value | Conditions |
|--------|-------|-----------|
| Embedding speed | ~100 chunks/sec | CPU, nomic-embed-text via Ollama |
| Embedding dimension | 768 | nomic-embed-text |
| Vector search | < 100 ms | 40K chunks, 25K-row block scan |
| FTS5 keyword search | < 10 ms | 40K chunks |
| RRF fusion | < 5 ms | Merge + sort |
| Index skip (unchanged) | < 1 sec | Hash-based detection |
| RAM (indexing) | ~500 MB | Embedder + active block buffers |
| RAM (search) | ~300 MB | Embedder + memmap overhead |
| Disk per 1M chunks | ~1.5 GB | float16 at 768 dimensions |
| Online query latency | 2-5 sec | API via configured endpoint |
| vLLM query latency | 2-5 sec | Workstation GPU, vLLM serving |
| Ollama query latency | 5-180 sec | Hardware dependent (CPU/GPU) |
| View switch latency | < 1 ms | pack_forget/pack (lazy NavBar) |
| Boot time | 2-4 sec | Config + credential + probe |

---

## 17. Nightly Data Sync (Bulk Transfer v2)

`src/tools/bulk_transfer_v2.py` -- Production-grade file transfer engine
for nightly source data updates over corporate VPN networks.

**Architecture: Three-Stage Atomic Transfer**

```
Source folder                    Staging area               Final destination
(network share)                  (local SSD)                (source_folder)
     |                               |                           |
     v                               v                           v
  [Discover] --> [Copy to .tmp] --> [SHA-256 verify] --> [Rename to verified/]
                                         |
                                    (mismatch?)
                                         |
                                         v
                                    [quarantine/ + .reason file]
```

Every file goes through three stages:
1. **incoming/** -- Active transfer, `.tmp` extension during copy
2. **verified/** -- SHA-256 hash matches source, safe to use
3. **quarantine/** -- Hash mismatch or copy failure, with `.reason` file

**SQLite Manifest Database** (`transfer_manifest.py`):
- `source_manifest` table: tracks every source file by path, mtime, size, content hash
- `transfer_log` table: records every transfer attempt with status, duration, hash
- `INSERT OR REPLACE` with full field list prevents mtime clobber on resume
- Resume logic: `is_already_transferred()` checks `abs(stored_mtime - current_mtime) < 2.0`
- Content-hash deduplication: identical files across runs are detected and skipped

**VPN/Corporate Network Resilience:**

| Feature | Mechanism |
|---------|-----------|
| Connection drop detection | Consecutive failure counter (threshold: 20) |
| Recovery wait | Exponential backoff: 30s -> 60s -> 120s -> ... -> 600s max |
| Reachability probe | `os.listdir(source_root)` tests SMB/CIFS mount |
| Timeout discrimination | Network `ETIMEDOUT` (retryable) vs copy-stall (abort) |
| Stall detection | Per-file timeout, configurable via `stall_timeout` |

**Memory Safety for Multi-Day Operation:**

| Feature | Mechanism |
|---------|-----------|
| Garbage collection | `gc.collect()` every N files (default 10,000) |
| Speed history cap | Rolling window capped at 500 samples |
| Checkpoint logging | Background thread logs stats every 300 seconds |
| Peak queue tracking | Monitors maximum concurrent transfer queue depth |

**Monitoring and Reporting:**

| Output | Format | Purpose |
|--------|--------|---------|
| JSON event log | JSONL file | Machine-readable for nightly cron monitoring |
| Progress callback | Python callable | GUI integration, status indicators |
| Full report | Structured text | Post-run summary with operational health |
| Checkpoint log | Python logging | Periodic stats during long runs |

**Configuration** (`TransferConfig`):

| Field | Default | Purpose |
|-------|---------|---------|
| `max_workers` | 4 | Concurrent copy threads |
| `max_retries` | 3 | Per-file retry attempts |
| `verify_hash` | true | SHA-256 integrity check |
| `network_health_interval` | 60s | Health check frequency |
| `stall_timeout` | 120s | Per-file copy timeout |
| `max_consecutive_failures` | 20 | Threshold for network recovery |
| `network_recovery_wait` | 30s | Initial backoff wait |
| `network_recovery_max_wait` | 600s | Maximum backoff wait |
| `gc_interval` | 10000 | Files between GC passes |
| `checkpoint_interval` | 300s | Seconds between checkpoint logs |
| `max_speed_history` | 500 | Rolling speed sample cap |

**Test Coverage**: 80 stress tests covering connection dropout, speed
fluctuation, scale (1000+ files), large files, memory safety, incomplete
file recovery, network recovery, chaos injection, disk space exhaustion,
nightly incremental sync, and special paths (unicode, spaces, long names).

---

## 18. Scale-Out Path

Current memmap brute-force search is O(N) and will not scale beyond
~500K vectors without unacceptable latency. Planned migration:

| Phase | Index Type | Vectors | RAM | Recall |
|-------|-----------|---------|-----|--------|
| 1 | `IVF256,SQ8` | < 5M | ~3.7 GB | ~95% |
| 2 | `IVF4096,SQ8` | < 50M | ~37 GB | 90-95% |
| 3 | GPU FAISS | 50M+ | GPU VRAM | 95%+ |

Phase 3 requires WSL2 or native Linux -- no Windows GPU FAISS support.
Home PC (dual RTX 3090, 48 GB GPU, 128 GB RAM) is the target platform
for Phase 3. Work workstations (64 GB RAM, 12 GB single GPU) are
limited to Phase 1-2 without a GPU upgrade.

Full analysis: `docs/research/FAISS_MIGRATION_PLAN.md`.

---

## 19. Key Dependencies

**Core runtime** (no torch, no sentence-transformers, no HuggingFace):

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| httpx | 0.28.1 | BSD-3 | HTTP client (Ollama, vLLM, proxy) |
| openai | 1.51.2 | MIT | OpenAI/Azure SDK (never 2.x) |
| pydantic | 2.11.1 | MIT | Data validation, API schemas |
| numpy | 1.26.4 | BSD-3 | Numerical arrays, memmap |
| faiss-cpu | 1.9.0 | MIT | Vector index (scale-out path) |
| pdfplumber | 0.11.9 | MIT | PDF extraction |
| python-docx | 1.2.0 | MIT | Word documents |
| python-pptx | 1.0.2 | MIT | PowerPoint |
| openpyxl | 3.1.5 | MIT | Excel |
| fastapi | 0.115.0 | MIT | REST API framework |
| uvicorn | 0.41.0 | BSD-3 | ASGI server |
| tiktoken | 0.8.0 | MIT | Token counting |
| keyring | 23.13.1 | MIT | Windows Credential Manager |
| cryptography | 44.0.2 | Apache/BSD | Encryption, CA bundles |
| structlog | 24.4.0 | Apache 2.0 | Structured logging |
| PyYAML | 6.0.2 | MIT | YAML parsing |

**Retired in RevB** (removed from requirements.txt):

| Package | Reason |
|---------|--------|
| torch | Replaced by Ollama-served embeddings |
| sentence-transformers | Replaced by Ollama nomic-embed-text |
| transformers | No longer needed without HuggingFace models |
| tokenizers | Dependency of transformers |
| huggingface_hub | No longer downloading from HuggingFace |
| safetensors | Dependency of transformers |
| scipy | Was used by sentence-transformers |
| scikit-learn | Was used for distance metrics |
| sympy | Transitive dependency |
| threadpoolctl | Dependency of scikit-learn |
| einops | Dependency of sentence-transformers |
| joblib | Dependency of scikit-learn |
| filelock | Dependency of HuggingFace |
| fsspec | Dependency of HuggingFace |
| networkx | Transitive dependency |
| mpmath | Dependency of sympy |

**Dependency reduction**: ~2.5 GB removed from virtual environment.
Requirements install: ~200 MB vs ~800 MB previously.

**Optional workstation packages:**

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| vllm | 0.10.1 | Apache 2.0 | GPU LLM inference (workstation only) |

---

*End of document. For questions, see the project maintainer.*
