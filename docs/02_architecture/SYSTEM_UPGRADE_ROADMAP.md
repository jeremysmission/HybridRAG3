# HybridRAG3 -- System Upgrade Roadmap

Date: 2026-02-25 | Audience: Technical leads, architects, management

This document provides:
1. A high-level block diagram of the current system
2. Upgrade annotations on every component
3. Current bottlenecks and what limits scale
4. What we can fix with software today (free)
5. What requires hardware investment
6. Next scale-up targets with justification

---

## 1. System Block Diagram (Current State + Upgrade Targets)

```
+===================================================================+
|                    HYBRIDRAG3 SYSTEM ARCHITECTURE                  |
|                  Current: Desktop Power (64 GB / 48 GB GPU)        |
+===================================================================+

  SOURCE DATA (650 GB target)          USERS
  D:\RAG Source Data                   (GUI / CLI / REST API)
        |                                    |
        |                                    v
        v                            +--------------+
  +==============+                   |  QUERY INPUT |
  | NIGHTLY SYNC |<--[UPGRADE 1]    +--------------+
  | bulk_transfer|                         |
  | _v2.py       |                         v
  |              |                   +==============+
  | Atomic copy  |                   | EMBED QUERY  |<--[UPGRADE 2]
  | SHA-256 hash |                   | Ollama       |
  | VPN resilient|                   | nomic-embed  |
  | Resume/dedup |                   | 768-dim      |
  +==============+                   | 50-100 ms    |
        |                            +==============+
        v                                  |
  +==============+                         v
  | PARSE        |                   +==============+
  | 49+ formats  |                   | VECTOR SEARCH|<--[UPGRADE 3]
  | pdfplumber,  |                   | Memmap f16   |
  | docx, xlsx,  |                   | brute-force  |
  | OCR, CAD,    |                   | [N, 768]     |
  | email, etc   |                   | 1-20 ms      |
  | ~1 sec/file  |                   +==============+
  +==============+                         |
        |                                  v
        v                            +==============+
  +==============+                   | BM25 KEYWORD |
  | CHUNK        |                   | SQLite FTS5  |
  | 1200 chars   |                   | OR-logic     |
  | 200 overlap  |                   | < 10 ms      |
  | heading      |                   +==============+
  | prepend      |                         |
  | < 1 ms/chunk |                         v
  +==============+                   +==============+
        |                            | RRF FUSION   |
        v                            | k=60         |
  +==============+                   | Merge+rank   |
  | EMBED CHUNKS |<--[UPGRADE 2]    | < 5 ms       |
  | Ollama       |                   +==============+
  | nomic-embed  |                         |
  | 768-dim      |                         v
  | ~100 ch/sec  |                   +==============+
  | BOTTLENECK   |                   | LLM GENERATE |<--[UPGRADE 4]
  | for indexing  |                   | Ollama/vLLM  |
  +==============+                   | phi4-mini or |
        |                            | mistral-nemo |
        v                            | 2-10 SEC     |
  +==============+                   | >>BOTTLENECK<<|
  | STORE        |                   +==============+
  | SQLite+FTS5  |                         |
  | Memmap f16   |                         v
  | WAL mode     |                   +==============+
  | Crash-safe   |                   | HALLUCINATION|
  +==============+                   | GUARD        |
        |                            | 5-layer      |
        v                            | (online only)|
  +==============+                   +==============+
  | INDEX READY  |                         |
  | ~4.3 GB at   |                         v
  | 650 GB src   |                   +--------------+
  +==============+                   |    ANSWER    |
                                     | + citations  |
                                     +--------------+

  +==============+     +==============+     +==============+
  | COST TRACKER |     | NETWORK GATE |     | CREDENTIALS  |
  | SQLite DB    |     | 3-mode       |     | Win Cred Mgr |
  | ROI calc     |     | offline/     |     | DPAPI encrypt|
  | Budget gauge |     | online/admin |     | Never logged |
  +==============+     +==============+     +==============+
       [stable]            [stable]             [stable]
```

---

## 2. Upgrade Targets Identified

### UPGRADE 1: Nightly Data Sync (Bulk Transfer v2) -- DONE

| Aspect | Before | After |
|--------|--------|-------|
| Transfer method | Manual file copy | Atomic copy with SHA-256 verification |
| Network resilience | None | VPN drop detection, exponential backoff, 20-failure threshold |
| Resume capability | None | SQLite manifest with mtime tracking, content-hash dedup |
| File integrity | Trust filesystem | Hash-before + hash-after, quarantine on mismatch |
| Multi-day operation | Not supported | GC scheduling, speed history caps, checkpoint logging |
| Monitoring | Manual | JSON event log, progress callbacks, structured reports |
| Scale tested | N/A | 1000+ files, chaos injection, 80 stress tests |

**Status: Complete.** No further investment needed for v1.0 operation.

### UPGRADE 2: Embedder -- PLANNED

| Aspect | Current | Upgrade Option A | Upgrade Option B |
|--------|---------|-----------------|-----------------|
| Model | nomic-embed-text (137M) | snowflake-arctic-embed:l (335M) | mxbai-embed-large (335M) |
| Dimensions | 768 | 1024 | 1024 |
| Query latency | 50-100 ms | 80-150 ms | 80-150 ms |
| Index time (1.63M) | 2.3-4.5 hrs | 4-8 hrs | 4-8 hrs |
| Retrieval quality | Good | Better | Better |
| Re-index required | -- | YES (dimension change) | YES (dimension change) |

**Why upgrade:** Better retrieval quality means the LLM gets better context, improving answer accuracy. The query latency increase (50ms) is invisible next to the 2-10 second LLM wait.

**Why not yet:** Requires full re-index (4-8 hours at production scale). Should batch with any other index-breaking change. Current 98% accuracy on 400-question eval may not justify the re-index cost until we have the full 650 GB dataset.

### UPGRADE 3: Vector Search -- PLANNED

| Aspect | Current | Phase 1 | Phase 2 |
|--------|---------|---------|---------|
| Index type | Memmap brute-force | FAISS IVF256,SQ8 | FAISS GPU |
| Scale limit | ~500K vectors | ~5M vectors | 50M+ vectors |
| Search latency | 1-20 ms (linear) | 2-5 ms (sub-linear) | < 1 ms |
| RAM usage (1.63M) | ~1.2 GB | ~3.7 GB | GPU VRAM |
| VRAM cost | 0 | 0 | 1.2-4.7 GB |
| Recall | 100% (exact) | ~95% (approximate) | 95%+ |
| Software change | None | Code change only | Requires Linux/WSL2 |

**Why upgrade:** At 1.63M chunks (production), brute-force scan takes 5-20 ms. Still not the bottleneck (LLM is 2-10 sec). But IVF is free on CPU and future-proofs for 5M+ vectors.

**Trigger:** Upgrade when vector count exceeds 500K or when search latency under concurrent load becomes measurable.

### UPGRADE 4: LLM Generation -- THE CRITICAL PATH

| Aspect | Current (laptop) | Current (workstation) | Next Scale-Up |
|--------|-----------------|----------------------|---------------|
| Model | phi4-mini (3.8B) | mistral-nemo:12b | mistral-small3.1:24b |
| VRAM | 2.3 GB | 7.1 GB | 15 GB (one 3090) |
| Speed | 30-50 tok/s | 12-25 tok/s | 8-15 tok/s |
| Quality | Good | Great | Excellent |
| Query time | 3-6 sec | 6-12 sec | 8-18 sec |
| Serving | Ollama | Ollama or vLLM | vLLM (batching) |

**Why this matters most:** LLM generation is 95%+ of total query time. A user asking a question waits 2-10 seconds, and all of that is LLM. Everything else combined (embed + search + build) is under 200 ms.

**Next scale-up:** mistral-small3.1:24b fits on one RTX 3090 (15 GB). Use the second 3090 for a parallel instance. This gives 2x concurrent throughput with excellent answer quality.

---

## 3. Current Bottlenecks

### Bottleneck 1: LLM Generation (Query Time) -- HARDWARE LIMITED

```
Query Pipeline Time Budget:

  Embed query:     |##|                               50-100 ms (1-5%)
  Vector search:   |#|                                1-20 ms   (<1%)
  Chunk retrieval: |#|                                1-5 ms    (<1%)
  Prompt build:    |#|                                < 1 ms    (<1%)
  LLM generation:  |#################################| 2-10 SEC  (95%+)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                   THIS IS THE BOTTLENECK
```

**Can software fix it?** Partially.
- Response caching: instant for repeated queries (software, free)
- vLLM batching: serves multiple users on same GPU pass (software, free)
- Streaming: user sees tokens arrive progressively (already implemented)

**Requires hardware:**
- Bigger model = better answers but slower per query
- More VRAM = can run bigger model
- Dual GPU = 2x concurrent throughput

### Bottleneck 2: Embedding Generation (Index Time) -- HARDWARE LIMITED

```
Indexing Pipeline Time Budget (1.63M chunks):

  Parse:          |###|                               ~27 min
  Chunk:          |#|                                 < 1 min
  Embed chunks:   |############################|      2.3-4.5 HOURS
  Store:          |##|                                ~15 min
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                  THIS IS THE BOTTLENECK
```

**Can software fix it?** Partially.
- Incremental indexing: only re-embed new/changed files (already implemented)
- Batch size tuning: maximize GPU utilization per call (already tuned)
- Anti-sleep: prevent OS sleep during long runs (already implemented)

**Requires hardware:**
- Faster GPU = more embeddings/second
- More VRAM = larger batch sizes = better throughput

### Bottleneck 3: Concurrent Users -- HARDWARE LIMITED

```
8 users simultaneously:

  Embed queries:  All 8 in ~200 ms (batched)     -- NOT bottleneck
  Vector search:  All 8 in ~20 ms (parallel CPU)  -- NOT bottleneck
  SQLite reads:   All 8 in ~10 ms (concurrent)    -- NOT bottleneck
  LLM generation: QUEUED SEQUENTIALLY              -- BOTTLENECK
    User 1: 2-10 sec
    User 2: 4-20 sec (waits for user 1)
    ...
    User 8: 16-80 sec (waits for users 1-7)
```

**Can software fix it?** Partially.
- Response caching eliminates repeated queries
- vLLM continuous batching serves multiple prompts per GPU pass
- Priority queue can put critical queries first

**Requires hardware:**
- Second GPU = second Ollama/vLLM instance = 2x throughput
- User 8 wait drops from 16-80 sec to 8-40 sec

---

## 4. Software Improvements (Free -- Do Now)

These require NO hardware investment. They are code or configuration changes.

| # | Improvement | Affects | Impact | Effort |
|---|------------|---------|--------|--------|
| 1 | Response caching | Query (Stage 5) | Instant for repeated queries, eliminates LLM call entirely | Medium |
| 2 | vLLM serving (enable) | Query (Stage 5) | Continuous batching, prefix caching, 2-3x throughput per GPU | Low (config) |
| 3 | IVF indexing | Search (Stage 2) | Sub-linear search at 1M+ vectors, near-GPU speed on CPU | Medium |
| 4 | Parallel parsing | Index (Stage A) | Multi-process file parsing, better CPU utilization during index | Medium |
| 5 | Nightly sync scheduling | Data freshness | Windows Task Scheduler triggers bulk_transfer_v2, auto-incremental | Low |
| 6 | Query priority queue | Concurrent users | Admin/critical queries jump the LLM queue | Low |
| 7 | Warm model keep-alive | Query (Stage 5) | Ollama keep_alive=-1 prevents model unload between queries | Done |

### Priority order for software improvements:

1. **vLLM serving** -- Already installed, just needs `vllm.enabled: true` in config. Biggest free win for workstation throughput.
2. **Response caching** -- Repeat queries are common in team use. Cache hit = 0 ms instead of 2-10 sec.
3. **Nightly sync scheduling** -- Data freshness drives the whole system's value. Without fresh data, answers are stale.
4. **IVF indexing** -- Only matters at 500K+ vectors. Low priority until production scale.

---

## 5. Hardware Limitations (Requires Investment)

### Current Hardware: Dual-RTX-3090 Workstation

| Resource | Available | Currently Used | Headroom |
|----------|-----------|---------------|----------|
| System RAM | 64 GB | ~6 GB (search) | 58 GB free |
| GPU VRAM (card 1) | 24 GB | ~9 GB (mistral-nemo:12b + nomic-embed) | 15 GB free |
| GPU VRAM (card 2) | 24 GB | 0 (idle) | 24 GB free |
| Total VRAM | 48 GB | ~9 GB | 39 GB free |
| Storage | SSD | ~16 GB index data | Ample |

### What the hardware limits:

| Limitation | Why | What fixes it |
|-----------|-----|---------------|
| LLM quality ceiling | Bigger models need more VRAM | Already have headroom: 24B fits on one 3090 |
| Concurrent LLM throughput | One Ollama instance = sequential | Use second GPU for parallel LLM instance |
| Embedding speed | GPU-bound during index build | Second GPU or faster GPU |
| Maximum model size | 24 GB per card | NVLink or A100 (80 GB) for 70B+ models |

### Hardware scale-up path:

```
CURRENT (Dual RTX 3090)                    NEXT SCALE-UP
48 GB GPU, 64 GB RAM                       (no hardware purchase needed)
=========================                   ============================

GPU 1: mistral-nemo:12b (7.1 GB)    -->    GPU 1: mistral-small3.1:24b (15 GB)
        + nomic-embed-text (0.5 GB)                 + nomic-embed-text (0.5 GB)
        = 7.6 GB / 24 GB                           = 15.5 GB / 24 GB

GPU 2: idle                          -->    GPU 2: mistral-nemo:12b (7.1 GB)
        = 0 GB / 24 GB                             + nomic-embed-text (0.5 GB)
                                                    = 7.6 GB / 24 GB

Throughput: 1x (sequential)          -->    Throughput: 2x (parallel instances)
Quality: Great (12B)                 -->    Quality: Excellent (24B primary)
Concurrent: 1 at a time             -->    Concurrent: 2 at a time
```

**Key insight:** The next scale-up requires NO hardware purchase. We have 39 GB of unused VRAM. The upgrade is purely software configuration: deploy a bigger model on GPU 1 and use GPU 2 for a parallel instance.

---

## 6. Next Scale-Up Plan

### Phase 1: Software Only (This Quarter)

| Action | Component | Before | After | Effort |
|--------|-----------|--------|-------|--------|
| Enable vLLM | LLM serving | Ollama (sequential) | vLLM (batched) | 1 day |
| Deploy 24B model | LLM quality | mistral-nemo:12b | mistral-small3.1:24b | 1 hour (pull) |
| Dual-GPU serving | Throughput | 1x sequential | 2x parallel | 1 day |
| Schedule nightly sync | Data freshness | Manual copy | Auto overnight | 1 hour |

**Expected result:** 2x throughput, better answer quality, automated data updates.

### Phase 2: Index Scale-Up (When Hitting 500K Chunks)

| Action | Component | Before | After | Effort |
|--------|-----------|--------|-------|--------|
| Switch to FAISS IVF | Vector search | O(N) brute-force | O(sqrt(N)) approximate | 1 week |
| Upgrade embedder | Retrieval quality | nomic 768-dim | arctic:l 1024-dim | 1 week + re-index |
| Full 650 GB index | Scale | 15.8 GB / 39K chunks | 650 GB / 1.63M chunks | 4-8 hours |

**Expected result:** Production-scale index, better retrieval, sub-linear search.

### Phase 3: Team Deployment (When Serving 5+ Users)

| Action | Component | Before | After | Effort |
|--------|-----------|--------|-------|--------|
| Add response cache | Query latency | 2-10 sec always | 0 ms for repeats | 1 week |
| Query priority queue | User experience | FIFO | Priority by role/urgency | 2 days |
| Load balancer | Availability | Single instance | Failover between GPUs | 1 week |

**Expected result:** Team-ready service with sub-second cached responses.

---

## 7. Quick Reference: Component Status

| Component | Status | Bottleneck? | Next Upgrade | Trigger |
|-----------|--------|------------|-------------|---------|
| Nightly Sync | DONE | No | -- | -- |
| Parser Registry | Stable | No | -- | New format needed |
| Chunker | Stable | No | -- | Retrieval quality study |
| Embedder (nomic) | Stable | Index time | arctic:l (1024-dim) | 650 GB dataset ready |
| Vector Search (memmap) | Stable | No (at 39K) | FAISS IVF | 500K+ chunks |
| BM25 Search (FTS5) | Stable | No | -- | -- |
| RRF Fusion | Stable | No | -- | -- |
| LLM Generation | BOTTLENECK | YES | 24B model + dual GPU | Team deployment |
| Hallucination Guard | Stable | No | Reactivate NLI | Model available |
| Cost Tracker | Stable | No | -- | -- |
| Network Gate | Stable | No | -- | -- |
| Credentials | Stable | No | -- | -- |
| REST API | Stable | No | -- | -- |
| GUI | Stable | No | -- | -- |

---

## 8. Cost vs Impact Matrix

```
HIGH IMPACT
     ^
     |  [Enable vLLM]     [24B Model]     [Dual-GPU LLM]
     |       $0              $0               $0
     |
     |  [Response Cache]   [Nightly Sched]
     |       $0              $0
     |
     |  [FAISS IVF]        [Better Embedder]
     |       $0              $0 + re-index time
     |
     |                     [Query Priority]
     |                          $0
     |
     |                                      [A100 80GB]
     |                                       ~$10,000
     |
LOW  |  [NVLink bridge]
     |       ~$200
     +-------------------------------------------------->
   $0 cost                                     HIGH COST
```

**Every high-impact upgrade is free.** The hardware we have (dual 3090, 48 GB VRAM, 64 GB RAM) is sufficient for the next 2-3 scale-up phases. The only hardware investment that would provide meaningful capability beyond our current ceiling is an A100 (80 GB unified VRAM for 70B+ models), which is not needed at current scale.

---

*For detailed pipeline timing, see PIPELINE_FLOW_AND_BOTTLENECKS.md.*
*For production scale math, see PRODUCTION_SCALE_ESTIMATE.md.*
*For full technical architecture, see TECHNICAL_THEORY_OF_OPERATION_RevC.md.*
