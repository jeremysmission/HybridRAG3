# HybridRAG3 Pipeline Flow and Bottlenecks

Date: 2026-02-25

This document maps every stage of a query through the system, identifies
the chokepoint at each stage, and shows what upgrades affect what.

---

## Query Pipeline (what happens when a user asks a question)

```
USER QUERY
    |
    v
[1. EMBED QUERY] -----> Ollama nomic-embed-text (GPU)
    |                    Input:  user question (text)
    |                    Output: 768-dim vector
    |                    Time:   50-100 ms
    |
    v
[2. VECTOR SEARCH] ---> FAISS index (CPU or GPU)
    |                    Input:  query vector + index
    |                    Output: top-k chunk IDs + scores
    |                    Time:   1-20 ms (depends on index size + type)
    |
    v
[3. CHUNK RETRIEVAL] -> SQLite database (disk -> RAM)
    |                    Input:  chunk IDs from FAISS
    |                    Output: actual text chunks
    |                    Time:   1-5 ms
    |
    v
[4. PROMPT BUILD] ----> Python (CPU)
    |                    Input:  query + retrieved chunks + 9-rule prompt
    |                    Output: formatted prompt for LLM
    |                    Time:   < 1 ms
    |
    v
[5. LLM GENERATION] --> Ollama phi4-mini / mistral / etc (GPU)
    |                    Input:  full prompt
    |                    Output: answer text
    |                    Time:   2-10 SECONDS  <<<< BOTTLENECK
    |
    v
ANSWER TO USER
```

**The bottleneck is always Stage 5.** Everything else combined is under
200 ms. The LLM takes 2-10 seconds. Every hardware and model upgrade
should be evaluated by how it affects Stage 5.

---

## Indexing Pipeline (one-time, when source data changes)

```
SOURCE DOCUMENTS (PDF, DOCX, PPTX, XLSX, TXT)
    |
    v
[A. PARSE] -----------> pdfplumber, python-docx, etc (CPU)
    |                    Input:  raw files
    |                    Output: extracted text
    |                    Time:   ~1 sec/file (CPU-bound)
    |
    v
[B. CHUNK] -----------> Python chunker (CPU)
    |                    Input:  extracted text
    |                    Output: text chunks (~500 words each)
    |                    Time:   < 1 ms/chunk
    |
    v
[C. EMBED CHUNKS] ----> Ollama nomic-embed-text (GPU)
    |                    Input:  each chunk
    |                    Output: 768-dim vector per chunk
    |                    Time:   ~5-10 ms/chunk  <<<< BOTTLENECK
    |                    At 1.63M chunks: 2.3-4.5 HOURS
    |
    v
[D. STORE] -----------> FAISS index + SQLite (disk)
    |                    Input:  vectors + chunk text
    |                    Output: searchable index
    |                    Time:   minutes (I/O bound)
    |
    v
INDEX READY
```

**Indexing bottleneck is Stage C.** Parsing and chunking are fast.
Embedding 1.63M chunks through Ollama takes hours. A bigger/better
embedder makes this slower but produces better vectors.

---

## Stage-by-Stage: Current vs Upgrades

### Stage 1: Embed Query

| Config | Model | Dims | Time/query | Re-index? |
|--------|-------|------|-----------|-----------|
| **Current** | nomic-embed-text (137M) | 768 | 50-100 ms | -- |
| Upgrade A | snowflake-arctic-embed:l (335M) | 1024 | 80-150 ms | YES |
| Upgrade B | snowflake-arctic-embed2:568m | 1024 | 100-200 ms | YES |
| Upgrade C | mxbai-embed-large (335M) | 1024 | 80-150 ms | YES |

Tradeoffs:
- Bigger embedder = better retrieval quality = slower per query
- Any dimension change (768 -> 1024) requires FULL re-index
- At query time the difference is 50-200 ms -- not user-noticeable
- At index time the difference matters: 1.63M chunks * extra ms = hours

**Recommendation:** Upgrade embedder for quality. The query latency
increase is invisible next to the 2-10 second LLM wait. Budget extra
time for the one-time re-index.

### Stage 2: Vector Search (FAISS)

| Config | Type | 39K chunks | 1.63M chunks | VRAM used |
|--------|------|-----------|-------------|-----------|
| **Current** | faiss-cpu flat | 1-2 ms | 5-20 ms | 0 |
| Upgrade A | faiss-cpu IVF | 1 ms | 2-5 ms | 0 |
| Upgrade B | faiss-gpu flat | < 1 ms | 1-2 ms | 1.2-4.7 GB |
| Upgrade C | faiss-gpu IVF | < 1 ms | < 1 ms | 1.2-4.7 GB |

Tradeoffs:
- At 39K chunks (current): ALL options are < 5 ms. No upgrade needed.
- At 1.63M chunks (production): IVF on CPU gets you 2-5 ms without
  burning VRAM. GPU only saves another 1-3 ms.
- faiss-gpu eats VRAM that the LLM needs (Stage 5).
- IVF requires a training step during indexing (adds minutes, not hours).

**Recommendation:** Switch to IVF indexing at production scale.
Stay on faiss-cpu unless search latency is measured as a problem
under concurrent load.

### Stage 3: Chunk Retrieval (SQLite)

| Config | 39K chunks | 1.63M chunks |
|--------|-----------|-------------|
| **Current** | 1-2 ms | 3-10 ms |

Not a bottleneck at any scale. SQLite handles millions of rows fine.

### Stage 4: Prompt Build

Not a bottleneck. Pure CPU string formatting, < 1 ms always.

### Stage 5: LLM Generation (THE BOTTLENECK)

| Config | Model | VRAM | Speed (tokens/sec) | Quality | Time/query |
|--------|-------|------|--------------------|---------|-----------|
| **Current** | phi4-mini (3.8B, q4) | 2.3 GB | 30-50 t/s | Good | 3-6 sec |
| Upgrade A | mistral:7b (q4) | 4.1 GB | 20-35 t/s | Better | 4-8 sec |
| Upgrade B | mistral-nemo:12b (q4) | 7.1 GB | 12-25 t/s | Great | 6-12 sec |
| Upgrade C | phi4:14b (q4_K_M) | 9.1 GB | 10-20 t/s | Great | 6-14 sec |
| Beast only | mistral-small3.1:24b | 15 GB | 8-15 t/s | Excellent | 8-18 sec |

Tradeoffs:
- Bigger model = better answers = slower generation
- Each model size roughly halves the tokens/second
- On workstation (12 GB VRAM): max is phi4:14b (9.1 GB)
- On beast (48 GB VRAM): can run 24B models, or run 2 models in parallel
- This stage is 95%+ of total query time

**Recommendation:** Use the biggest model that fits in VRAM while keeping
response time under 10 seconds. For demos, phi4:14b gives the best
quality-to-speed ratio on 12 GB VRAM.

---

## Concurrent Users: Where It Breaks

```
8 USERS ASKING SIMULTANEOUSLY
    |
    +---> [Embed] 8 queries -> Ollama batches them -> ~200 ms total
    |     NOT a bottleneck
    |
    +---> [FAISS] 8 searches -> CPU handles in parallel -> ~20 ms total
    |     NOT a bottleneck
    |
    +---> [SQLite] 8 reads -> concurrent readers fine -> ~10 ms total
    |     NOT a bottleneck
    |
    +---> [LLM] 8 generations -> QUEUED SEQUENTIALLY -> 16-80 SECONDS
          ^^^^ THIS IS THE BOTTLENECK
          User #1: 2-10 sec
          User #8: 16-80 sec (waits for users 1-7)
```

### Solutions for concurrent LLM bottleneck

| Solution | Hardware needed | Effect |
|----------|----------------|--------|
| Response caching | Any | Instant for repeated queries |
| Dual GPU (2 instances) | Beast (dual 3090) | 2x throughput, user #8 waits 8-40 sec |
| Smaller model | Any | Faster per query but worse answers |
| Online API fallback | Internet | Offload to Azure OpenAI, near-instant |
| vllm batching | 24+ GB VRAM | Batches multiple prompts on one GPU |

---

## Hardware Comparison: What Runs Where

```
                    LAPTOP          WORKSTATION       BEAST
                    (8GB/512MB)     (64GB/12GB)       (128GB/48GB)
                    -----------     -----------       -----------
Embedder:
  nomic (137M)      Yes             Yes               Yes
  arctic:l (335M)   Slow (CPU)      Yes               Yes
  arctic2:568m      No              Yes               Yes

FAISS:
  faiss-cpu flat    Yes             Yes               Yes
  faiss-cpu IVF     Yes             Yes               Yes
  faiss-gpu         No              Maybe (12GB)      Yes (48GB)

LLM:
  phi4-mini (3.8B)  Yes (slow)      Yes               Yes
  mistral:7b        No              Yes               Yes
  phi4:14b          No              Yes               Yes
  mistral-nemo:12b  No              Yes               Yes
  mistral-small:24b No              No (>12GB)        Yes (one 3090)
  Two models at     No              No                Yes (two 3090s)
  once

Concurrent users:
  1 user            Fine            Fine              Fine
  2 users           Slow            Fine              Fine
  8 users           No              LLM queues        LLM queues (2x GPU helps)
```

---

## Upgrade Priority (biggest impact first)

| Priority | Upgrade | Affects Stage | Impact |
|----------|---------|---------------|--------|
| 1 | Bigger LLM (phi4:14b) | Stage 5 | Better answers (95% of user experience) |
| 2 | Better embedder (arctic:l) | Stages 1, C | Better retrieval (finds right chunks) |
| 3 | IVF indexing | Stage 2 | Needed at 1M+ chunks, free on CPU |
| 4 | Response caching | Stage 5 | Instant for repeat queries |
| 5 | Dual GPU serving | Stage 5 | 2x concurrent throughput |
| 6 | faiss-gpu | Stage 2 | Marginal gain, costs VRAM |

---

## Running Two HybridRAG Instances Simultaneously

Yes, possible. They share the same Ollama server on port 11434.

| Resource | Instance 1 | Instance 2 | Conflict? |
|----------|-----------|-----------|-----------|
| Ollama (LLM) | Uses GPU | QUEUED behind #1 | Yes -- sequential |
| Ollama (embedder) | Uses GPU | QUEUED behind #1 | Yes -- sequential |
| FAISS search | Uses CPU/RAM | Uses CPU/RAM | No -- independent |
| SQLite | Read lock | Read lock | No -- concurrent reads OK |
| FastAPI server | Port 8000 | Port 8001 (change config) | No -- different ports |
| RAM | ~2 GB | ~2 GB | No (you have 128 GB) |

The only real conflict is Ollama queuing. Both instances share one
Ollama server, so LLM requests are serialized. On the beast with dual
3090s, you could run two Ollama instances on different GPUs to avoid this.
