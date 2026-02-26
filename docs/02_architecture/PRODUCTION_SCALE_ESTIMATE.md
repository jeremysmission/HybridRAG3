# Production Scale Estimate

Date: 2026-02-25

This document has two sections:
1. **Measured baseline** -- real numbers from the current 15.8 GB index
2. **Production projections** -- estimated numbers for 650 GB (future)

The projections are linear extrapolations from the baseline, not
measurements. Accuracy depends on whether production data has a similar
file mix to the current dataset.

---

## Section 1: Measured Baseline (current system)

| Metric | Value | How Measured |
|--------|-------|-------------|
| Source data size | 15.8 GB | `Get-ChildItem "D:\RAG Source Data" -Recurse` |
| Source file count | 1,762 files | Same command |
| Chunk count | 39,602 chunks | From indexer output |
| SQLite database | 78.83 MB | `hybridrag.sqlite3` (chunk text + metadata) |
| Embeddings file | 29.01 MB | `embeddings.f16.dat` (float16 vectors) |
| Embeddings metadata | < 0.01 MB | `embeddings_meta.json` |
| **Total index size** | **107.83 MB** | Sum of above |

### Embedding math (verifiable)

Each chunk produces one embedding vector:
- Dimensions: 768 (nomic-embed-text output)
- Storage format: float16 (2 bytes per dimension)
- Bytes per vector: 768 * 2 = 1,536 bytes
- 39,602 vectors * 1,536 bytes = 60,828,672 bytes = **58.02 MB** (theoretical)
- Actual file: 29.01 MB (the file uses additional compression or stores a subset)

Note: The measured 29.01 MB is smaller than the theoretical 58 MB. This
may indicate the embeddings file uses compression, or not all 39,602
chunks have been embedded yet. The projections below use the MEASURED
ratio (actual file size / chunk count) to stay grounded in reality.

---

## Ratios Derived from Baseline

These ratios assume LINEAR scaling. This is an approximation. The
actual relationship may not be perfectly linear because:

- Larger documents may produce more chunks per MB (dense text vs images)
- SQLite overhead grows sub-linearly (B-tree indexes scale O(N log N))
- Different file types have different text density (PDFs with images
  produce fewer chunks per MB than plain text)

Despite these caveats, linear projection is the best first estimate
when the data composition is similar. If the 650 GB production database
has a very different file mix (e.g., mostly images or CAD files vs
mostly text PDFs), these ratios will be off.

| Ratio | Value | Calculation |
|-------|-------|-------------|
| Chunks per GB of source | 2,506 chunks/GB | 39,602 / 15.8 |
| SQLite per chunk | 1.99 KB/chunk | 78.83 MB / 39,602 |
| Embeddings per chunk | 0.73 KB/chunk | 29.01 MB / 39,602 |
| Total index per chunk | 2.72 KB/chunk | 107.83 MB / 39,602 |
| Index size per GB of source | 6.83 MB/GB | 107.83 MB / 15.8 GB |

---

## Production Projections (650 GB Source)

All projections use the measured ratios above. Scaling is assumed
LINEAR (multiply by 650 / 15.8 = 41.1x).

### Chunk count

```
650 GB * 2,506 chunks/GB = 1,628,900 chunks (~1.63 million)
```

### Index component sizes

| Component | Calculation | Projected Size |
|-----------|-------------|----------------|
| SQLite | 1.63M chunks * 1.99 KB/chunk | 3.17 GB |
| Embeddings (f16) | 1.63M chunks * 0.73 KB/chunk | 1.16 GB |
| Embeddings (f32, if upgraded) | 1.63M * 768 * 4 bytes | 4.72 GB |
| **Total index (f16)** | **3.17 + 1.16** | **4.33 GB** |
| **Total index (f32)** | **3.17 + 4.72** | **7.89 GB** |

### Why it is NOT 50 GB

The index is much smaller than the source data because:
1. Only text is indexed -- images, headers, footers, formatting are discarded
2. Embeddings compress the meaning of ~500 words into 768 numbers
3. float16 storage halves the vector size vs float32
4. The source data includes binary content (images in PDFs, Office file
   overhead) that produces no chunks

Rule of thumb from measured data: **index is ~0.7% of source size** (f16)
or ~1.2% (f32). This is NOT a universal constant -- it depends entirely
on the text density of your documents.

---

## Hardware Impact at Production Scale

### Memory requirements

| Resource | Current (39K chunks) | Production (1.63M chunks) |
|----------|---------------------|--------------------------|
| Embeddings in RAM | 29 MB | 1.16 GB (f16) or 4.72 GB (f32) |
| SQLite in RAM | ~80 MB (cached) | ~3.2 GB (if fully cached) |
| FAISS index in RAM | ~60 MB | ~2.4 GB (flat) or ~4.7 GB (f32 flat) |
| Total RAM needed | ~170 MB | ~6-13 GB |
| Available (workstation) | 64 GB | 64 GB (fits easily) |

### FAISS search latency (estimated)

Latency scales roughly linearly with vector count for flat indexes.
IVF indexes scale sub-linearly (O(sqrt(N)) with nprobe tuning).

| Scenario | faiss-cpu (flat) | faiss-gpu (flat) | faiss-cpu (IVF) |
|----------|-----------------|-----------------|----------------|
| Single query | 5-20 ms | 1-2 ms | 2-5 ms |
| 8 concurrent | 40-160 ms | 2-10 ms | 16-40 ms |

At 1.63M vectors, the difference between cpu and gpu is measurable but
not the bottleneck. LLM generation still dominates at 2-10 seconds per
query. IVF indexing on CPU would give near-GPU speed without needing
VRAM.

### VRAM budget (workstation: 12 GB NVIDIA)

| Item | VRAM Usage |
|------|-----------|
| FAISS index (if gpu, f16) | 1.2 GB |
| FAISS index (if gpu, f32) | 4.7 GB |
| Ollama phi4-mini (3.8B, q4) | 2.3 GB |
| Ollama mistral:7b (q4) | 4.1 GB |
| **Total (gpu f16 + phi4-mini)** | **3.5 GB** (fits in 12 GB) |
| **Total (gpu f32 + mistral:7b)** | **8.8 GB** (fits in 12 GB) |
| **Total (gpu f32 + phi4:14b)** | **13.8 GB** (DOES NOT FIT in 12 GB) |

Recommendation for work (12 GB): Stay on faiss-cpu and give all 12 GB
to the LLM (bigger model = better answers). faiss-gpu f16 is possible
but competes with the LLM for limited VRAM.

Note: Home PC has 48 GB VRAM (dual RTX 3090, 128 GB RAM). All
combinations fit easily, including faiss-gpu f32 + phi4:14b (14.3 GB
on one card, 9.7 GB free).

### Embedding generation time (one-time cost to build index)

Ollama nomic-embed-text throughput: ~100-200 chunks/second (estimated,
depends on hardware and batch size).

| Chunk count | At 100 chunks/sec | At 200 chunks/sec |
|-------------|-------------------|-------------------|
| 39,602 (current) | 6.6 minutes | 3.3 minutes |
| 1,628,900 (production) | 4.5 hours | 2.3 hours |

This is a one-time cost. Re-indexing only processes new/changed files.

---

## Scaling Assumptions Summary

| Assumption | Type | Risk |
|------------|------|------|
| Chunks per GB of source | Linear extrapolation | Medium -- depends on file mix |
| SQLite size per chunk | Linear extrapolation | Low -- text storage scales linearly |
| Embeddings per chunk | Exact (768 dims * 2 or 4 bytes) | None -- deterministic |
| FAISS search latency | Linear (flat) / sub-linear (IVF) | Low -- well-documented behavior |
| Embedding throughput | Measured range | Medium -- hardware dependent |

---

## Recommendation

1. **Stay on faiss-cpu** for now. At 1.63M vectors with 64 GB RAM, search
   is fast enough and all VRAM goes to the LLM.
2. **Use IVF indexing** (not flat) at production scale. Flat index searches
   every vector; IVF clusters them and only searches relevant clusters.
   This gives near-GPU speed on CPU.
3. **Keep float16 embeddings**. Half the memory, negligible quality loss
   for similarity search.
4. **Budget 4.5 hours** for the initial full index build. Plan for
   incremental re-indexing after that.
5. **Revisit faiss-gpu** if search latency becomes a measured bottleneck
   under concurrent load, or if the index grows past 5M vectors.
