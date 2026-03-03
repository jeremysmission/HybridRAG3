# HybridRAG3 -- Theory of Operation (Management / Non-Technical)

Revision: C | Date: 2026-03-03

---

## Change History Link
For software evolution, decision rationale, tradeoffs, and 7-day chronology,
see `docs/02_architecture/SOFTWARE_HISTORY_AND_SCALABILITY_PLAN_2026-03-02.md`.

---

## What Is HybridRAG?

HybridRAG is a document search and question-answering system that runs on
your own computer. You give it a folder of documents -- PDFs, Word files,
spreadsheets, emails, PowerPoints, images -- and it reads every one. After
that, you can ask it questions in plain English, and it gives you a direct
answer with citations back to the exact source documents.

Think of it as a research assistant that has read every page in your
filing cabinet and can find the answer to any question in seconds. The
difference is that this assistant never forgets, never gets tired, and
can search through thousands of documents faster than any human.

The name breaks down as follows:

- **Hybrid** -- It combines two different search methods (meaning-based
  and keyword-based) for better results than either alone.
- **RAG** -- Retrieval-Augmented Generation. The industry term for
  "find relevant information first, then have an AI write an answer
  using only that information."

---

## Why Does This Exist?

Traditional keyword search (like Ctrl+F or Windows Search) only finds
exact words. If you search for "antenna frequency range" it will not find
a document that says "RF operating band" -- even though they mean the
same thing.

HybridRAG solves this by understanding meaning, not just matching words.
It also goes a step further: instead of giving you a list of documents to
read through yourself, it reads the relevant passages and writes you a
direct answer.

---

## The Two Things It Does

HybridRAG has two main operations:

### 1. Indexing (One-Time Setup)

The system reads every document in your source folder and creates a
searchable index. This is like building the index at the back of a
textbook -- it only needs to happen once (or when new documents are
added).

What happens during indexing:

1. **Read** -- Opens each file and extracts the text. It handles 49+
   file formats: PDFs, Word (.docx), PowerPoint (.pptx), Excel (.xlsx),
   emails (.eml), images (via OCR), plain text, and more.

2. **Break into pieces** -- A 500-page PDF is too large to search
   efficiently, so the text is split into small pieces called "chunks"
   (about half a printed page each). Splits happen at paragraph
   boundaries so sentences are not cut in half.

3. **Understand meaning** -- Each chunk is converted into a mathematical
   fingerprint (called an "embedding") by a small AI model running on
   your computer. Think of it like a GPS coordinate for meaning: two
   sentences about the same topic get coordinates that are close together
   on a map, even if the words are completely different.

4. **Store** -- The text and its fingerprints are saved to a local
   database. Nothing leaves your computer.

**Key fact for management**: Indexing 1,345 documents (~40,000 chunks)
takes a few hours the first time. After that, only new or changed
files are re-indexed, which takes seconds.

### 2. Querying (Daily Use)

When you ask a question:

1. **Search** -- Your question is converted into the same kind of
   fingerprint, then compared against all stored chunks. Two searches
   run at the same time:
   - A *meaning search* that finds passages with similar concepts
   - A *keyword search* that finds exact terms, part numbers, and
     acronyms
   - Results are merged so the best matches from both methods rise
     to the top (like combining Google results with a Ctrl+F search
     and keeping the best of both)

2. **Answer** -- The top matching passages are sent to an AI language
   model along with your question. The AI reads only those passages and
   writes a direct answer, citing which documents the information came
   from.

3. **Smart caching** -- If you ask the same (or a very similar) question
   again, the system recognizes it and returns the previous answer
   instantly -- no need to re-run the search or contact the AI model.
   This makes live demos and repeated workflows near-instant.

**Key fact for management**: A typical query takes 2-5 seconds in
online mode (using a cloud AI) or 5-30 seconds in offline mode (using
a local AI on your computer). Repeated questions return in under
1 millisecond from cache.

---

## How Users Interact With It

HybridRAG provides five ways to interact:

### Command Line (PowerShell)

The original interface. Users type commands like:
- `rag-index` to index documents
- `rag-query "What is the operating frequency?"` to ask a question
- `rag-status` to check system health

### Graphical Interface (GUI)

A desktop application with a navigation bar for switching between views:

- **Query view** -- Type questions and view answers with source citations,
  latency metrics, and token counts. Answers stream in token-by-token
  so you see progress immediately. Includes a `Stop` button (and `Esc`)
  to cancel long-running queries during live operations.
- **Data view** -- Browse drives, select document folders, transfer files
  from network drives to the source folder with live progress and ETA,
  and run the indexer.
- **Settings view** -- Configure API credentials, data paths, model
  selection, retrieval tuning, and hardware profiles -- all without
  editing config files.
- **Cost view** -- Live session spend, budget gauge, token breakdown,
  ROI calculator, and cumulative team statistics across all sessions.
- **Reference view** -- Browse indexed source documents.
- **Status bar** -- Live system health indicators (Ollama status, LLM
  model, Network Gate mode) with color-coded green/red signals.
- **Dark mode / light mode** toggle and zoom scaling (50%-200%).
- **Setup wizard** -- First-time users are walked through data paths
  and mode selection in a 4-step guided dialog.

### REST API

A web-based interface for programmatic access. Other software tools can
send queries to HybridRAG over HTTP on localhost. This enables
integration with dashboards, automation scripts, and other internal
tools without any internet exposure.

### MCP Server (AI Agent Integration)

HybridRAG exposes itself as a Model Context Protocol (MCP) server. This
is a standard way for AI tools to search your indexed documents
programmatically. Think of it like giving a research assistant access to
the filing cabinet: AI tools can ask HybridRAG questions, check the
index status, and get answers with citations -- all through a standard
protocol. No coding required on the AI tool side.

### Bulk Transfer Tool

An enterprise file transfer utility for importing large document
collections from network drives, shared folders, or portable media.
It handles:
- Filtering by file type (only RAG-relevant formats)
- Deduplication (skips files already transferred)
- Verification (SHA-256 hash check after every copy)
- Atomic writes (a crash mid-transfer cannot corrupt a file)
- Live progress display with ETA and per-file-type breakdown

---

## Security: How It Protects Data

HybridRAG was designed from the ground up for environments where data
protection is non-negotiable.

### Nothing Leaves Your Computer (By Default)

In its default "offline" mode, HybridRAG has zero internet connectivity.
Every operation -- reading documents, searching, and generating answers --
happens entirely on the local machine. Three independent security layers
enforce this:

1. **Operating system level** -- Environment variables block AI library
   network calls before they start
2. **Application level** -- A "Network Gate" inside the software
   explicitly checks every outbound connection against an allowlist
3. **Code level** -- The AI model libraries are told to work in
   offline-only mode

All three layers must fail simultaneously before any data could leave
the machine. Think of it like a building with three locked doors between
you and the exit -- all three locks would have to break at the same time.

### PII Scrubbing (Online Mode)

When online mode is used, a PII (Personally Identifiable Information)
scrubber automatically removes sensitive data before anything is sent to
the cloud API:
- Social Security numbers
- Credit card numbers
- Email addresses
- Phone numbers
- IP addresses

These are replaced with safe placeholders like `[SSN]`, `[EMAIL]`, etc.
This runs automatically when `pii_sanitization` is enabled (on by
default) and only affects the online code path.

### Optional Online Mode

When faster answers are needed, an "online" mode sends questions (and
the relevant document passages) to a configured API endpoint. This mode:
- Must be explicitly activated by the user
- Only connects to one pre-configured endpoint (nothing else)
- Requires an API key stored in Windows Credential Manager (encrypted,
  tied to the user's Windows login)
- Logs every connection attempt for audit review
- Supports dual-environment deployment (e.g., home network with
  commercial API and work network with government API through
  corporate proxy)

### Credential Security

- API keys are never stored in files, environment variables, or code
- Keys are encrypted using Windows DPAPI (the same system that protects
  your saved browser passwords)
- Only the logged-in Windows user can access their own keys
- Diagnostic output shows only a masked preview (e.g., `sk-abc...xyz`)

### Audit Trail

Every operation is logged: indexing runs (what files, when, how many
chunks), queries (what was asked, what was found), and network
connections (allowed and denied). This creates a reviewable record of
everything the system has done.

---

## Where Data Lives

```
Your Computer
|
|-- HybridRAG3/                    The software (code, config, scripts)
|   This is what gets version-controlled in Git.
|
|-- RAG Source Data/               Your original documents
|   PDFs, Word docs, spreadsheets, etc.
|   HybridRAG reads these but NEVER modifies them.
|
|-- RAG Indexed Data/              The search database
|   Created by HybridRAG during indexing.
|   Contains the text chunks and their meaning fingerprints.
|   This is what makes searching fast.
```

**Key fact for management**: Original documents are never modified,
moved, or deleted. The indexed data can be rebuilt from scratch at any
time by re-running the indexer.

---

## AI Models: What Runs and Where

HybridRAG uses two types of AI model:

### 1. Embedding Model (Always Local)

A small model (~274 MB) that converts text into 768-dimensional meaning
fingerprints. It runs on the CPU of any modern laptop via the Ollama
server and never requires internet.

- **Model**: nomic-embed-text (768 dimensions, served by Ollama)
- **Publisher**: Nomic AI (open-source, Apache 2.0 license)
- **Runs**: Always locally, never sends data anywhere
- **Advantage**: Higher quality embeddings than the previous 384-dim
  model, with a smaller install footprint (removed ~2.5 GB of
  HuggingFace dependencies)

### 2. Language Model (Generates Answers)

A larger model that reads the retrieved passages and writes answers.
Four backend options:

| Mode | Where It Runs | Speed | Internet Required? |
|------|--------------|-------|--------------------|
| **Offline (Transformers)** | Direct GPU on your computer | 2-5 sec | No |
| **Offline (vLLM)** | On workstation via vLLM server | 2-5 sec | No |
| **Offline (Ollama)** | On your computer via Ollama | 5-30 sec | No |
| **Online** | Cloud API (company endpoint) | 2-5 sec | Yes (configured endpoint only) |

The system automatically selects the best available backend. If vLLM is
running, it uses vLLM. Otherwise it falls back to Ollama. Online mode
requires explicit activation.

**Streaming responses**: In offline mode (Ollama and vLLM), answers
stream token-by-token to the screen. You see the answer building in
real time instead of waiting for the full response.

**Approved offline models** (all open-source, US/EU publishers):

| Model | Size | Publisher | License |
|-------|------|-----------|---------|
| phi4-mini | 2.3 GB | Microsoft (USA) | MIT |
| mistral:7b | 4.1 GB | Mistral AI (France) | Apache 2.0 |
| phi4:14b-q4_K_M | 9.1 GB | Microsoft (USA) | MIT |
| gemma3:4b | 3.3 GB | Google (USA) | Apache 2.0 |
| mistral-nemo:12b | 7.1 GB | Mistral/NVIDIA | Apache 2.0 |

A **model download manifest** (`config/model_manifest.yaml`) documents
every model weight file required by the system, including vendor, license,
size, download source, and air-gap transfer instructions. This makes
multi-gigabyte model downloads auditable for security compliance.

**Banned models** (regulatory/licensing restrictions):
- No China-origin software (Qwen/Alibaba, DeepSeek, BGE/BAAI)
- No Meta/Llama models (license restrictions)

---

## The Hallucination Guard

"Hallucination" is when an AI makes up information that sounds plausible
but is not in the source documents. Think of it like an employee who
confidently gives you an answer that is not in any manual -- it sounds
right, but it is fabricated. HybridRAG has a 5-layer protection system to
prevent this:

1. **Prompt instructions** -- The AI is explicitly told: "Only use
   information from the provided documents. If the answer is not in the
   documents, say so."

2. **Claim extraction** -- After the AI responds, the system breaks the
   answer into individual factual statements.

3. **Fact checking** -- Each statement is automatically checked against
   the source documents using a verification model.

4. **Confidence scoring** -- Statements are scored for accuracy. If the
   overall score is below the threshold, the answer is flagged or
   blocked.

5. **Dual-path consensus** -- For critical questions, the query can be
   sent to two different AI models. If they disagree, the system returns
   a conservative, safe response.

**Note:** Layers 2-5 require an online connection and are active only in
online mode. In offline mode, Layer 1 (prompt instructions) is always
active and provides the first line of protection.

---

## System Health Monitoring

HybridRAG continuously monitors its own health through an automated
probe system (similar to how a car dashboard warns you about low oil
before the engine fails):

- **Ollama connectivity** -- Can the system reach the local AI server?
- **Embedding model** -- Is the embedding model loaded and responding?
- **Index readability** -- Can the search database be read?
- **Disk space** -- Is there enough room for new documents?
- **API connectivity** -- (Online mode) Can the cloud endpoint be reached?

Problems are sorted by severity (critical, high, medium, low) and
the system provides specific fix suggestions for each issue. A flight
recorder keeps a rolling history of recent events so that when something
goes wrong, the events leading up to the failure are available for
diagnosis.

---

## Performance at a Glance

| What | How Long | Notes |
|------|----------|-------|
| First-time indexing | A few hours | 1,345 documents, ~40,000 chunks |
| Re-indexing (changed files only) | Seconds | Skips unchanged files automatically |
| Query (online mode) | 2-5 seconds | Cloud AI, requires network |
| Query (offline / vLLM) | 2-5 seconds | Workstation GPU, no network |
| Query (offline / Ollama) | 5-30 seconds | Local AI, no network needed |
| Repeated query (cached) | < 1 millisecond | Semantic cache, no AI call needed |

**Hardware requirements**:
- Minimum: Any Windows 10/11 laptop with 8 GB RAM
- Recommended: 16+ GB RAM for faster performance
- Work workstation: 64 GB RAM, 12 GB single GPU with Ollama/vLLM
- Home PC: Dual RTX 3090 (48 GB GPU, 128 GB RAM) for max throughput

---

## Reliability Features

| Feature | What It Means |
|---------|---------------|
| **Crash-safe indexing** | If the power goes out during indexing, restart and it picks up where it left off. No data lost. |
| **Change detection** | Only re-indexes files that have actually changed. Saves hours on repeat runs. |
| **Graceful degradation** | If one document is corrupted, it skips that file and continues with the rest. |
| **Boot validation** | On startup, checks that everything is configured correctly. Tells you exactly what to fix if something is wrong. |
| **Low memory usage** | Processes large documents in small blocks. An 8 GB laptop can index thousands of documents. |
| **Health monitoring** | Automated probes detect problems (lost Ollama connection, low disk space, corrupted index) before users notice. |
| **Streaming responses** | Answers appear token-by-token in offline mode, so you see progress immediately instead of waiting for the full response. |
| **Semantic caching** | Repeated or near-identical questions return instantly from cache without re-running the AI pipeline. |

---

## Hardware Profiles

Three pre-configured profiles adapt the system to different hardware:

| Profile | Target Hardware | Behavior |
|---------|----------------|----------|
| **laptop_safe** | 8-16 GB RAM | Conservative. Slower but stable on limited hardware. |
| **desktop_power** | 32-64 GB RAM | Balanced speed and resource usage. |
| **server_max** | 64+ GB RAM | Maximum throughput for workstation/server hardware. |

Switching profiles is one command: `rag-profile desktop_power`

---

## Dual-Environment Support

HybridRAG supports deployment across different network environments
without code changes. For example:

- **Home network**: Connects to a commercial cloud API endpoint directly
- **Work network**: Connects to a government cloud API through a
  corporate proxy with custom SSL certificates

The system auto-detects the provider (Azure, Azure Government, standard
OpenAI) from the endpoint URL and handles proxy configuration, SSL
certificate bundles, and authentication schemes automatically. This
means the same software installation works in both environments --
just change the configuration.

---

## What Makes HybridRAG Different

| Capability | HybridRAG | Traditional Search |
|------------|-----------|-------------------|
| Understands meaning | Yes (semantic search) | No (keywords only) |
| Handles synonyms | Yes ("RF band" finds "frequency range") | No |
| Gives direct answers | Yes, with citations | No, returns document list |
| Works offline | Yes (default) | Depends |
| Handles 49+ file formats | Yes (PDF, DOCX, PPTX, XLSX, EML, images...) | Limited |
| Audit trail | Yes (every operation logged) | Rarely |
| Crash recovery | Yes (automatic) | Rarely |
| PII protection | Yes (automatic scrubbing in online mode) | No |
| AI agent integration | Yes (MCP server) | No |
| Health monitoring | Yes (automated probes) | Rarely |
| Smart caching | Yes (semantic similarity) | Basic (exact match) |

---

## Current Scale

- **Documents indexed**: ~1,345 files
- **Text chunks stored**: ~39,602
- **File formats supported**: 49+
- **Evaluation accuracy**: 98% on a 400-question test set
- **Test coverage**: 550+ automated tests passing (47 test files)

---

## Glossary

See the [Glossary](GLOSSARY.md) for definitions of all technical terms
and acronyms used in this document and throughout the project.
