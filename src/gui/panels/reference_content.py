# ============================================================================
# HybridRAG v3 -- Embedded Reference Content
# (src/gui/panels/reference_content.py)                                 RevA
# ============================================================================
# All help/reference text lives here so the GUI is fully portable.
# No external files needed -- everything is self-contained.
#
# HOW TO ADD A NEW DOCUMENT:
#   1. Write a string constant (e.g. HELP_MY_DOC = """...""")
#   2. Add an entry to CATEGORIES: ("Display Name", HELP_MY_DOC)
#   3. Done -- the GUI picks it up automatically on next launch
#
# HOW TO REMOVE A DOCUMENT:
#   Delete the tuple from CATEGORIES. Optionally delete the constant.
#
# HOW TO EDIT CONTENT:
#   Find the string constant by name, edit the text.
#
# INTERNET ACCESS: NONE
# ============================================================================


# ---------------------------------------------------------------------------
# Getting Started
# ---------------------------------------------------------------------------

HELP_SHORTCUT_SHEET = """\
SHORTCUT SHEET
==============

SETUP (one-time):
  py -3.11 -m venv .venv
  .\\.venv\\Scripts\\Activate.ps1
  pip install -r requirements.txt
  . .\\start_hybridrag.ps1   (dot-space-dot required)
  rag-diag                   (verify install)

DAILY USE:
  rag-paths              Show paths + network status
  rag-index              Index documents (incremental)
  rag-query "question"   Ask a question
  rag-diag               Full diagnostic suite
  rag-status             Quick health check
  rag-profile            Show/switch performance profile
  rag-server             Start REST API (localhost:8000)
  rag-gui                Open the GUI

CREDENTIALS:
  rag-store-key          Store API key (encrypted)
  rag-store-endpoint     Store API endpoint URL
  rag-cred-status        Check credential status
  rag-test-api           Test API connectivity

MODE SWITCHING:
  rag-mode-online        Cloud API (needs credentials)
  rag-mode-offline       Local AI via Ollama (default)
  rag-set-model          Model selection wizard
  rag-models             Show available models

REST API ENDPOINTS:
  GET  /health, /status, /config
  POST /query  (body: {"question": "..."})
  POST /index, GET /index/status, PUT /mode

PROFILES: laptop_safe (8-16GB), desktop_power (32-64GB), server_max (64GB+)

KEY CONFIG: chunk_size=1200, overlap=200, embedding=nomic-embed-text (768d)
  top_k=12, min_score=0.10, temperature=0.05, reranker=OFF

EMERGENCY RECOVERY:
  Delete .venv, recreate, pip install, re-source start_hybridrag.ps1.
  DB recovery: python -m src.tools.rebuild_memmap_from_sqlite
"""

HELP_GUI_GUIDE = """\
GUI GUIDE
=========

LAUNCH: python src/gui/launch_gui.py
  Wait for "[OK] Backends attached to GUI" before querying.

WINDOW LAYOUT (top to bottom):
  Menu bar: File | Admin | Help
  Title bar: Mode toggle (OFFLINE/ONLINE) + Theme toggle (Dark/Light)
  Nav bar: [Query] [Settings] [Cost] [Ref]
  Content area: switches views based on nav selection
  Status bar: LLM model | Ollama status | Gate mode (auto-refreshes)

USE CASE PROFILES (9):
  sw, eng, sys, draft, log, pm, fe, cyber, gen
  Default: Engineering / STEM. Changes auto-select the best model.

MODE TOGGLE:
  OFFLINE: Queries go to local Ollama. No data leaves machine.
  ONLINE: Queries go to cloud API. Requires stored credentials.

ADMIN MENU (Admin > Admin Settings):
  top_k (1-50, default 12), min_score (0.00-1.00, default 0.10)
  Hybrid search (ON), Reranker (OFF -- keep OFF for eval accuracy)
  Max tokens (256-4096), Temperature (0.00-1.00, default 0.05)
  Timeout (10-120s), Profile selector

PM COST DASHBOARD (Admin > PM Cost Dashboard):
  Session spend, queries, avg cost/query, budget gauge.
  Token breakdown, data volume, cumulative team stats.
  Rate editor (per 1M tokens), Export CSV, ROI Calculator.

KEYBOARD: Enter=submit query, Ctrl+C=copy answer.

COMMON FIXES:
  Wait for backends (30-60s on 8GB laptop).
  Ollama Offline -> run 'ollama serve' in separate terminal.
  Credentials missing -> rag-store-key + rag-store-endpoint.
"""

HELP_USER_GUIDE = """\
USER GUIDE
==========

STARTUP:
  . .\\start_hybridrag.ps1
  python src/gui/launch_gui.py

INDEXING:
  CLI: rag-index
  GUI: Index Panel > Browse > Start Indexing
  First run: few hours for large collections. After: only changed files.
  49+ formats: PDF, DOCX, PPTX, XLSX, EML, MSG, images (OCR), TXT,
  CSV, HTML, DXF, STP, STL, VSDX, EVTX, PCAP, ACCDB, and more.

QUERYING:
  CLI: rag-query "question"
  GUI: Type question + Enter
  Tips: Be specific, use document terminology, one question at a time.

MODES:
  Offline (Ollama, free, 5-180s) | Online (API, 2-5s, costs money)
  Switch: rag-mode-online / rag-mode-offline, or GUI toggle button.

TUNING TIPS:
  "No results"        -> lower min_score to 0.05
  Irrelevant info     -> raise min_score to 0.25-0.30
  Missing context     -> raise top_k to 12-15
  Too verbose         -> lower top_k to 5-8
  Reranker: keep OFF  (degrades unanswerable/injection/ambiguous scores)

DIAGNOSTICS: rag-diag, rag-diag --verbose, rag-status
"""


# ---------------------------------------------------------------------------
# Technical
# ---------------------------------------------------------------------------

HELP_FORMAT_SUPPORT = """\
FORMAT SUPPORT
==============
49 FULLY SUPPORTED formats, 11 placeholder, 60 total registered.

PLAIN TEXT:
  .txt .md .csv .json .xml .log .yaml .yml .ini .cfg .conf .properties .reg

DOCUMENTS:
  .pdf .docx .pptx .xlsx .doc (legacy) .rtf .ai (PDF-embedded)

EMAIL:
  .eml .msg .mbox

WEB:
  .html .htm

IMAGES (OCR via Tesseract):
  .png .jpg .jpeg .tif .tiff .bmp .gif .webp .wmf .emf

DESIGN:
  .psd (layer names + text layers)

CAD:
  .dxf (annotations/dims), .stp/.step/.ste (STEP metadata)
  .igs/.iges (IGES metadata), .stl (mesh stats)

DIAGRAMS:
  .vsdx (Visio 2013+)

SECURITY LOGS:
  .evtx (Windows Event Log), .pcap/.pcapng (network captures)
  .cer/.crt/.pem (X.509 certificates)

DATABASE:
  .accdb .mdb (Access, up to 50 rows/table)

PLACEHOLDER (recognized, filename-only search):
  .prt .sldprt .asm .sldasm .dwg .dwt .mpp .vsd .one .ost .eps

ALL DEPENDENCIES: MIT, BSD, or Apache 2.0 licensed.
Parsers use lazy imports -- missing library returns empty text, never crashes.
"""

HELP_ARCHITECTURE = """\
ARCHITECTURE OVERVIEW
=====================

BOOT SEQUENCE:
  Load config (YAML) -> Resolve credentials (keyring/env)
  -> Configure network gate -> Probe backends -> BootResult

QUERY PATH:
  User question -> Query Engine -> Embedder (768-dim vector)
  -> Retriever: BM25 keyword (FTS5) + Vector cosine (memmap)
  -> RRF Fusion + min_score filter -> top_k chunks
  -> Prompt Builder (9-rule template) -> LLM Router
  -> OFFLINE (vLLM preferred, Ollama fallback) or ONLINE (API)
  -> QueryResult (answer, sources, tokens, cost, latency)

INDEXING PATH:
  Source folder -> File scan + hash check (skip unchanged)
  -> Parser (49+ formats) -> Chunker (1200c, 200 overlap)
  -> Embedder (batch, 768d) -> VectorStore -> SQLite + Memmap

STORAGE:
  hybridrag.sqlite3 (chunks + FTS5 index)
  embeddings.f16.dat + embeddings_meta.json (vector memmap)
  logs/cost_tracking.db (cost events)

USER INTERFACES:
  PowerShell CLI, tkinter GUI, REST API (localhost:8000)
  All three use the same query engine pipeline.
"""

HELP_SOFTWARE_STACK = """\
SOFTWARE STACK
==============

CORE: Python 3.12, numpy 1.26.4, httpx, pyyaml
EMBEDDING: nomic-embed-text (768d, 274MB, Apache 2.0, served by Ollama)
STORAGE: SQLite + NumPy memmap (float16). No external DB server.
RETRIEVAL: Hybrid vector + BM25 via RRF (k=60). Reranker available but OFF.
CHUNKING: 1200 chars, 200 overlap, smart boundary detection, heading prepend.
LLM OFFLINE: Ollama (phi4-mini default). vLLM on workstation.
LLM ONLINE: OpenRouter / Azure OpenAI / OpenAI (openai SDK 1.45.1).
GUI: tkinter (stdlib, zero deps). REST API: FastAPI 0.115.0 + Uvicorn.
PARSING: pdfplumber, python-docx, openpyxl, python-pptx, pytesseract, Pillow.
CREDENTIALS: keyring (Windows Credential Manager, DPAPI encrypted).
NETWORK: Centralized NetworkGate, 3-layer lockdown, fail-closed default.
CONFIG: YAML + Python dataclasses. Env override: HYBRIDRAG_<SECTION>_<KEY>.

APPROVED OFFLINE MODELS (5):
  phi4-mini (2.3GB, MIT), mistral:7b (4.1GB, Apache)
  phi4:14b-q4_K_M (9.1GB, MIT), gemma3:4b (3.3GB, Apache)
  mistral-nemo:12b (7.1GB, Apache). All US/EU origin.
"""

HELP_INTERFACES = """\
INTERFACES
==========
All interfaces are STABLE (no breaking changes without version bump).

BOOT: boot_hybridrag(config_path) -> BootResult
  success, online_available, offline_available, config, warnings[], errors[]

CONFIG: load_config(project_dir) -> Config
  Sub-configs: paths, embedding, chunking, ollama, vllm, api, retrieval

INDEXER: Indexer(config, vector_store, embedder, chunker)
  index_folder(folder, callback, recursive) -> dict

VECTOR STORE: VectorStore(db_path, embedding_dim)
  search(query_vec, top_k), fts_search(query_text, top_k), get_stats()

EMBEDDER: Embedder(model_name)
  embed_batch(texts) -> ndarray[N,768], embed_query(text) -> ndarray[768]

QUERY ENGINE: QueryEngine(config, vector_store, embedder, llm_router)
  query(question) -> QueryResult(answer, sources, tokens, cost, latency)

LLM ROUTER: LLMRouter(config, api_key)
  query(prompt) -> LLMResponse(text, tokens_in/out, model, latency_ms)

RETRIEVER: Retriever(vector_store, embedder, config)
  search(query) -> [SearchHit(score, source_path, chunk_index, text)]

NETWORK GATE: configure_gate(mode, api_endpoint, allowed_prefixes)
  gate.check_allowed(url, purpose, caller) -- raises NetworkBlockedError

CREDENTIALS: resolve_credentials(config_dict) -> ApiCredentials
  api_key, endpoint, has_key, has_endpoint, is_online_ready, key_preview
"""


# ---------------------------------------------------------------------------
# Security & Compliance
# ---------------------------------------------------------------------------

HELP_SECURITY = """\
SECURITY OVERVIEW
=================

NETWORK LOCKDOWN (3 layers):
  Layer 1: PowerShell env vars (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1)
  Layer 2: Python env vars checked at import time
  Layer 3: NetworkGate (fail-closed, audits every outbound connection)

OFFLINE MODE: Only localhost:11434 (Ollama) reachable. Nothing else.
ONLINE MODE: Localhost + configured API endpoint only. HuggingFace still blocked.

CREDENTIALS:
  Stored in Windows Credential Manager (DPAPI encrypted).
  3-layer resolution: keyring > env var > config file.
  Keys never logged in full (only first 8 chars shown).

EMBEDDING MODEL: nomic-embed-text served by Ollama (localhost:11434).
  No HuggingFace dependency. Model pulled via: ollama pull nomic-embed-text

DATA SOVEREIGNTY: All documents indexed locally. Vector store is local SQLite
  + memmap files. No cloud storage. No telemetry.

HALLUCINATION GUARD (online mode, 5 layers):
  Prompt hardener, claim extractor, NLI verifier, response scoring,
  dual-path consensus. Threshold: 0.80 faithfulness.
"""

HELP_GIT_RULES = """\
GIT REPOSITORY RULES
=====================

THREE-REPO STRUCTURE:
  1. Private development repo (home, full access)
  2. Educational repo (public, sanitized for distribution)
  3. Separate application repo

TRANSFER RULES:
  Home: git commit/push ONLY from here.
  Work: browser ZIP download from Educational repo ONLY. No git.
  Sync: tools/sync_to_educational.py (one-way, sanitized)

SANITIZATION:
  All commits checked for banned words before push.
  See docs/05_security/ for the full banned-word checklist.

MACHINE-SPECIFIC (never sync):
  start_hybridrag.ps1, .venv/, .model_cache/,
  API credentials, config/system_profile.json

CREDENTIAL SAFETY:
  Stored in Windows Credential Manager (encrypted).
  Cleanup scripts NEVER purge credentials, .git/, or .gitconfig.
"""

HELP_MODEL_AUDIT = """\
MODEL COMPLIANCE AUDIT
======================

APPROVED MODELS (5-model stack, ~26 GB total):
  phi4-mini     3.8B  MIT        Microsoft/USA  2.3GB  Primary
  mistral:7b    7B    Apache 2.0 Mistral/France 4.1GB  Alt (eng-heavy)
  gemma3:4b     4B    Apache 2.0 Google/USA     3.3GB  PM summarization
  phi4:14b      14B   MIT        Microsoft/USA  9.1GB  Workstation
  mistral-nemo  12B   Apache 2.0 Mistral/France 7.1GB  128K ctx upgrade

BANNED MODELS:
  Qwen / Alibaba     -- China origin (NDAA)
  DeepSeek           -- China origin (NDAA)
  BGE / BAAI         -- China origin (NDAA)
  Llama / Meta       -- ITAR restriction

SELECTION CRITERIA:
  License must be MIT, Apache 2.0, or BSD (no AGPL, no custom EULA).
  Publisher must be US or allied-nation company.
  Model must run on approved hardware profiles.
"""


# ---------------------------------------------------------------------------
# Demo & Evaluation
# ---------------------------------------------------------------------------

HELP_DEMO_PREP = """\
DEMO PREPARATION
================

ELEVATOR PITCH:
  Local-first document search + QA system. Reads PDFs, Word, spreadsheets,
  emails, images. Answers in seconds with citations. No data leaves machine.
  98% accuracy on 400-question eval. Open-source US/EU models.

5-MINUTE DEMO FLOW:
  1. The Problem (30s): Many docs, keyword search fails on synonyms.
  2. Offline Query (90s): Show OFFLINE mode, phi4-mini, type question.
  3. PM Cost Dashboard (60s): Show $0 offline cost, budget gauge.
  4. Admin Menu (30s): Show top_k, min_score, temperature sliders.
  5. Online Mode (60s): One-click switch, faster response, same sources.
  6. Index a Folder (60s): Browse, Start, 24+ formats, incremental.
  7. Wrap-Up (30s): Meaning-based search, 98% accuracy, audit trail.

KEY NUMBERS:
  1345 docs, 39602 chunks, 24+ formats, 98% accuracy,
  100% injection resistance, <100ms vector search, 5 approved models,
  9 profiles, 135+ tests, $0 offline cost.

IF SOMETHING GOES WRONG:
  Ollama down -> switch to online mode.
  GUI won't launch -> use CLI (rag-query).
  Slow -> "8GB laptop; workstation is 3-5x faster."
  Wrong answer -> "98% means 2% failure. Let me try another question."
"""

HELP_DEMO_GUIDE = """\
DEMO GUIDE
==========

BIGGEST SELLING POINTS:
  1. Hybrid search: MRR +18.5% over vector-only.
  2. Source citations: Every answer traceable to source doc.
  3. Air-gapped / offline-first: 100% on-prem, no cloud.
  4. Hallucination resistance: 9-rule prompt, 100% injection refusal.
  5. Cost efficiency: $0 per offline query. No vendor lock-in.

DEMO NARRATIVE ARC:
  Act 1: The Problem (60s) -- empathy, not features.
  Act 2: The Solution (90s) -- WOW moment with best query.
  Act 3: The Proof (3-4 min) -- factual, cross-doc, ambiguous queries.
  Act 4: The Numbers (60s) -- 98% accuracy, 39602 chunks, zero cloud.
  Act 5: Vision & Ask (60s) -- next step: 2-week pilot.

DOs:
  Rehearse exact queries. Use their data. Show citations.
  Show a failure gracefully. Keep under 10 min. Backup video.
DON'Ts:
  No feature tours. No jargon without translating. Don't oversell.
  Don't skip "why should I care." Don't end without call to action.

AUDIENCE ANGLES:
  Executives: cost savings, risk reduction, time-to-answer.
  IT/Security: air-gapped, data sovereignty, no vendor lock-in.
  End users: speed, accuracy, familiar documents.
  Technical: hybrid search, eval methodology, prompt engineering.
"""

HELP_DEMO_QA = """\
DEMO Q&A PREPARATION
=====================

TOP QUESTIONS (ranked by frequency):

TIER 1 (asked at every demo):
  "Can I trust these answers?"
    -> 98% eval accuracy, source citations, "I don't know" behavior.
  "Does data leave the machine?"
    -> Zero. Localhost only. Three blocking layers.
  "What if it's wrong?"
    -> Citations let you verify. Research assistant, not authority.
  "How do you validate accuracy?"
    -> 400-question eval, 98% pass, includes injection + ambiguity.
  "What's the ROI?"
    -> Seconds vs 30 min per lookup. $0 offline. No subscriptions.
  "Prompt injection?"
    -> 9 rules, injection refusal highest priority, 100% on eval.
  "Why not ChatGPT?"
    -> Can't search YOUR docs, sends data to cloud, no citations.

TIER 2 (7/10 demos):
  "Who maintains it?"
    -> Documented, YAML config, any Python dev can maintain.
  "File types?"
    -> 49+ formats, all common office + CAD + email + security logs.
  "Replace jobs?"
    -> Replaces folder-digging, not judgment or hands-on work.
  "Models vetted?"
    -> phi4-mini (Microsoft, MIT). Full compliance audit available.

DEMO-KILLERS TO PREPARE FOR:
  1. "Has IT approved?" -> Not yet, here's the security posture.
  2. "What if hallucination hurts someone?" -> Citations + human verify.
  3. "AI made something up" -> That's why sources shown. Human in loop.
  4. Injection succeeds live -> Test exhaustively before every demo.
"""


# ---------------------------------------------------------------------------
# CATEGORIES: Master list that drives the GUI.
# Add/remove entries here to change what appears in the Docs viewer.
# ---------------------------------------------------------------------------

CATEGORIES = [
    ("Getting Started", [
        ("Shortcut Sheet", HELP_SHORTCUT_SHEET),
        ("GUI Guide", HELP_GUI_GUIDE),
        ("User Guide", HELP_USER_GUIDE),
    ]),
    ("Technical", [
        ("Format Support", HELP_FORMAT_SUPPORT),
        ("Architecture", HELP_ARCHITECTURE),
        ("Software Stack", HELP_SOFTWARE_STACK),
        ("Interfaces", HELP_INTERFACES),
    ]),
    ("Security and Compliance", [
        ("Security Overview", HELP_SECURITY),
        ("Git Repository Rules", HELP_GIT_RULES),
        ("Model Compliance Audit", HELP_MODEL_AUDIT),
    ]),
    ("Demo and Evaluation", [
        ("Demo Preparation", HELP_DEMO_PREP),
        ("Demo Guide", HELP_DEMO_GUIDE),
        ("Demo Q and A", HELP_DEMO_QA),
    ]),
]
