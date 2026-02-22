# FAISS IVF Migration Plan for HybridRAG3

**Date:** 2026-02-21
**Author:** Claude Opus 4.6 (research agent)
**Status:** Research Complete -- Ready for Engineering Review

## Executive Summary

This document evaluates migrating HybridRAG3's vector storage from numpy memmap
(current) to FAISS IVF-based indexing. The system currently indexes ~39,602 chunks
at 384 dimensions using float16 memmap with brute-force cosine similarity search.
The target scale is ~650GB of source documents on a dual RTX 3090 workstation
(48GB VRAM, 64GB RAM) with 10 concurrent users.

**Bottom-line recommendation:** Migrate to `IVF4096,SQ8` for the initial deployment,
with a future path to `IVF16384,PQ48` or GPU-accelerated CAGRA if latency requirements
tighten. The current memmap brute-force approach will not scale beyond ~500K vectors
without unacceptable query latency.

---

## Table of Contents

1. [Current System Baseline](#1-current-system-baseline)
2. [Scale Estimation: 650GB to Vector Count](#2-scale-estimation-650gb-to-vector-count)
3. [FAISS IVF Index Types Comparison](#3-faiss-ivf-index-types-comparison)
4. [Build Time Estimates](#4-build-time-estimates)
5. [Memory Requirements (Build vs Query)](#5-memory-requirements-build-vs-query)
6. [Approximate vs Exact Search Tradeoffs](#6-approximate-vs-exact-search-tradeoffs)
7. [Migration Interface: Memmap to FAISS](#7-migration-interface-memmap-to-faiss)
8. [Concurrent Query Performance (10 Users)](#8-concurrent-query-performance-10-users)
9. [GPU Acceleration with Dual RTX 3090s](#9-gpu-acceleration-with-dual-rtx-3090s)
10. [Python 3.11 Compatibility](#10-python-311-compatibility)
11. [Recommended nprobe and nlist Configuration](#11-recommended-nprobe-and-nlist-configuration)
12. [Alternatives: HNSW, ScaNN, Flat+GPU](#12-alternatives-hnsw-scann-flatgpu)
13. [Novel and Undocumented Findings](#13-novel-and-undocumented-findings)
14. [Recommended Migration Plan](#14-recommended-migration-plan)
15. [Sources](#15-sources)

---

## 1. Current System Baseline

The existing HybridRAG3 vector storage is defined in `src/core/vector_store.py`:

- **Storage:** numpy memmap (`embeddings.f16.dat`) with float16 precision
- **Dimensions:** 384 (all-MiniLM-L6-v2 model)
- **Current scale:** ~39,602 chunks (~39,602 vectors)
- **Search method:** Brute-force cosine similarity in blocks of 25,000 rows
- **Metadata:** SQLite3 with FTS5 full-text index
- **Memory model:** Block-read from disk, normalize, dot product, keep top-k

Current file sizes at 39,602 vectors:
- `embeddings.f16.dat`: 39,602 x 384 x 2 bytes = ~29 MB
- Search scans all vectors on every query (O(N) complexity)

The system already notes FAISS as a "future option" in the source code comments
(line 47 of `vector_store.py`).

---

## 2. Scale Estimation: 650GB to Vector Count

### Document-to-Vector Ratio

The conversion from raw document bytes to vector count depends on chunking strategy:

| Metric | Conservative | Moderate | Aggressive |
|--------|-------------|----------|------------|
| Chunk size (tokens) | 500 (~400 words) | 250 (~200 words) | 128 (~100 words) |
| Overlap | 10% | 15% | 20% |
| Vectors per GB of raw text | ~375K-500K | ~750K-1M | ~1.5M-2M |
| **650GB total estimate** | **~244M-325M** | **~488M-650M** | **~975M-1.3B** |

However, 650GB of "source documents" includes PDFs, DOCX, XLSX, images, and
other binary formats. Extractable text is typically 10-30% of raw file size for
mixed-format corporate document sets.

**Realistic extractable text from 650GB:** ~65-195GB of plain text.

| Scenario | Text extracted | Chunk size | Estimated vectors |
|----------|---------------|------------|-------------------|
| Low density (many images/PDFs) | ~65 GB | 250 tokens | ~49M-65M |
| Medium density | ~130 GB | 250 tokens | ~98M-130M |
| High density (mostly text) | ~195 GB | 250 tokens | ~146M-195M |

**Working estimate: ~50M to 130M vectors at 384 dimensions.**

If the embedding model is upgraded to 768-dim (e.g., BGE-base, gte-base) or
1024-dim (e.g., gte-large), memory requirements double or triple respectively.

### Raw Memory at Scale (Flat Index, No Compression)

| Vectors | 384-dim (float32) | 768-dim (float32) | 1024-dim (float32) |
|---------|-------------------|--------------------|--------------------|
| 39,602 (current) | 58 MB | 116 MB | 155 MB |
| 50M | 73 GB | 146 GB | 195 GB |
| 100M | 146 GB | 293 GB | 390 GB |
| 130M | 190 GB | 380 GB | 507 GB |

At 384-dim, 50M vectors in a flat index require 73 GB -- already exceeding the
64GB system RAM. Compression is mandatory at this scale.

---

## 3. FAISS IVF Index Types Comparison

### IVF_Flat (IndexIVFFlat)

- **Compression:** None -- stores raw float32 vectors in inverted lists
- **Memory per vector:** 4 x dim + 8 bytes (ID) = 1,544 bytes at 384-dim
- **Recall:** Identical to brute-force within searched clusters
- **Best for:** Datasets that fit in RAM where accuracy is paramount
- **Verdict for this project:** Too memory-hungry at 50M+ vectors

### IVF_SQ8 (IndexIVFScalarQuantizer)

- **Compression:** 4x reduction (float32 -> uint8 per dimension)
- **Memory per vector:** 1 x dim + 8 bytes = 392 bytes at 384-dim
- **Recall:** At most 1% lower than IVF_Flat (from Milvus benchmarks)
- **Recall at 768-dim (Contriever dataset):** 0.843 (1-recall@1), 0.872 (10-recall@10) per FAISS codec benchmarks
- **Best for:** Balance of accuracy and memory efficiency
- **Verdict for this project:** RECOMMENDED as the primary index type

**[NOVEL FIND]** IVF_SQ8 at 384 dimensions performs even better than at 768
dimensions because lower-dimensional vectors have less quantization noise per
dimension. Community reports (FAISS GitHub issue #1559) indicate that SQ8 recall
at 384-dim is typically 0.95+ for 10-recall@10, significantly better than the
0.872 reported for 768-dim Contriever vectors.

### IVFPQ (IndexIVFPQ)

- **Compression:** Heavy -- subdivides vector into M subvectors, quantizes each
- **Memory per vector:** M bytes + 8 bytes (ID), e.g., PQ48 = 56 bytes at 384-dim
- **Recall:** ~50-70% for recall@1, varies by M and nbits
- **Best for:** Memory-constrained, billion-scale, where some recall loss is acceptable
- **Training time:** Significantly longer (PQ codebook training)
- **Verdict for this project:** Future option when scaling beyond 100M vectors

### IVF_SQ8 Memory Budget at Target Scale

| Vectors | IVF_Flat (384d) | IVF_SQ8 (384d) | IVFPQ48 (384d) |
|---------|-----------------|-----------------|-----------------|
| 50M | ~73 GB | ~18.6 GB | ~2.7 GB |
| 100M | ~146 GB | ~37.2 GB | ~5.3 GB |
| 130M | ~190 GB | ~48.4 GB | ~6.9 GB |

IVF_SQ8 at 50M vectors fits comfortably in 64GB RAM. At 100M+, it needs
on-disk inverted lists or PQ compression.

### IVFADC (IVF + Asymmetric Distance Computation)

IVFADC combines IVF with asymmetric distance computation using PQ codes. It
provides better recall than symmetric PQ at the same compression ratio because
the query vector is not quantized -- only database vectors are. This is the
default behavior of IndexIVFPQ in FAISS.

### RaBitQ (New in FAISS 1.11+)

**[NOVEL FIND]** RaBitQ was introduced in FAISS 1.11.0 (April 2025) and rapidly
improved through 1.12 (SIMD optimization) and 1.13 (FastScan + IVF integration).
It encodes vectors at approximately `(d/8 + 8)` bytes per vector -- for 384-dim,
that is ~56 bytes, comparable to PQ48 but with reportedly better recall at the
same code size. The `IndexIVFRaBitQFastScan` in FAISS 1.13 is worth benchmarking
as a potential alternative to both SQ8 and PQ.

Source: [FAISS CHANGELOG](https://github.com/facebookresearch/faiss/blob/main/CHANGELOG.md)

---

## 4. Build Time Estimates

### IVF Training Phase (K-Means Clustering)

IVF training runs k-means on a subset of vectors to find cluster centroids.

| nlist | Training vectors needed | CPU time (est.) | GPU time (est.) |
|-------|------------------------|-----------------|-----------------|
| 4,096 | 1.2M - 4M | 5-20 min | 1-5 min |
| 16,384 | 5M - 16M | 30-120 min | 5-15 min |
| 65,536 | 20M - 65M | 2-8 hours | 15-60 min |
| 262,144 | 80M+ | 8-24 hours | 1-4 hours |

Training recommendations from FAISS wiki:
- Below 1M vectors: `nlist = 4*sqrt(N)` to `16*sqrt(N)`, needs 30K-256K training vectors
- 1M-10M vectors: `nlist = 65,536`, needs 2M-17M training vectors
- 10M-100M vectors: `nlist = 262,144` (2^18), needs substantial training data

**[NOVEL FIND]** FAISS GitHub issue #949 documents a user training
`OPQ64_128,IVF1048576_HNSW32,Flat` where the GPU only worked for the initial
phase, then fell back to single-CPU training for 15+ hours. The HNSW coarse
quantizer training cannot be GPU-accelerated in older FAISS versions. With
FAISS 1.10+ and cuVS, IVF training is up to 4.7x faster on GPU.

### Vector Addition Phase

After training, adding vectors to the index is relatively fast:

| Vectors | IVF_SQ8 add time (CPU) | IVF_SQ8 add time (GPU) |
|---------|----------------------|----------------------|
| 1M | 30-60 seconds | 5-10 seconds |
| 10M | 5-10 minutes | 1-2 minutes |
| 50M | 30-60 minutes | 5-10 minutes |
| 100M | 1-2 hours | 10-20 minutes |

Note: vectors should be added in batches of ~8,192 for optimal GPU performance
(from FAISS GPU wiki). The add phase requires the training data distribution to
be representative of the full dataset.

**[NOVEL FIND]** FAISS GitHub issue #3094 confirms that training on 5M vectors
and then adding 95M more gives acceptable results IF the training sample is
representative. One user reports training on 1% of the dataset works well for
uniformly distributed embedding data, but domain-specific data with clusters
may need 5-10% for good centroid placement.

### Total Build Time Estimates for 50M Vectors

| Configuration | Training | Adding | Total (CPU) | Total (GPU) |
|--------------|----------|--------|-------------|-------------|
| IVF4096,SQ8 | 10 min | 30 min | ~40 min | ~10 min |
| IVF16384,SQ8 | 45 min | 30 min | ~75 min | ~20 min |
| IVF65536,PQ48 | 3 hours | 45 min | ~4 hours | ~45 min |

Source: [FAISS Wiki - Guidelines to choose an index](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index)

---

## 5. Memory Requirements (Build vs Query)

### Build Phase (Training + Add)

| Phase | RAM Required | VRAM Required | Notes |
|-------|-------------|---------------|-------|
| Training (k-means) | Training sample in RAM (e.g., 5M x 384 x 4 = 7.3GB for 5M vectors) | ~2-4 GB if GPU training | All training vectors must be contiguous in memory |
| Adding (CPU) | Index grows linearly; IVF_SQ8 at 50M = ~18.6GB | N/A | Batch add in chunks of 100K-1M |
| Adding (GPU) | Same as CPU for final index | GPU memory grows linearly per FAISS issue #1448 | Batch add in chunks of 8,192 |
| Index serialization | Peak: 2x index size during write | N/A | `faiss.write_index` needs buffer space |

**Critical warning from FAISS issue #1448:** In FAISS versions 1.6.3+, GPU memory
usage increases linearly when adding vectors to an IVF index and is never released.
This means you should build on CPU and transfer to GPU for serving, or use the
latest FAISS (1.13+) which may have fixed this regression.

### Query Phase (Serving)

| Configuration | RAM for 50M vectors | VRAM for 50M vectors | Notes |
|--------------|--------------------|--------------------|-------|
| IVF4096,Flat (CPU) | ~73 GB | N/A | Exceeds 64GB RAM |
| IVF4096,SQ8 (CPU) | ~18.6 GB | N/A | Comfortable fit in 64GB |
| IVF4096,PQ48 (CPU) | ~2.7 GB | N/A | Fits easily |
| IVF4096,SQ8 (GPU) | ~2 GB (centroids) | ~18.6 GB (index) | Fits in single 3090 |
| IVF4096,SQ8 (GPU, sharded) | ~2 GB | ~9.3 GB per GPU | Split across two 3090s |

### On-Disk Option (OnDiskInvertedLists)

For indexes exceeding RAM, FAISS supports memory-mapped inverted lists:

```python
index = faiss.read_index("large_index.faiss", faiss.IO_FLAG_MMAP | faiss.IO_FLAG_READ_ONLY)
```

The indirection table (mapping list ID to file offset) stays in RAM (~100 MB for
65K lists) while actual vector data stays on disk. At query time, only the nprobe
clusters are read from disk. On SSD, this adds ~1-5ms latency per query.

**[NOVEL FIND]** FAISS GitHub issue #3165 requests `IO_FLAG_MMAP` support for
`IndexFlat` (not just IVF), specifically for multi-process deployments where N
workers share the same index. Currently, only IVF indexes support mmap loading.
This is relevant if the project runs multiple FastAPI workers.

Source: [FAISS Wiki - Indexes that do not fit in RAM](https://github.com/facebookresearch/faiss/wiki/Indexes-that-do-not-fit-in-RAM)

---

## 6. Approximate vs Exact Search Tradeoffs

### Current System (Exact Search)

The current numpy memmap approach is exact brute-force search:
- **Recall@k:** 1.0 (guaranteed exact results)
- **Latency:** O(N) -- scales linearly with vector count
- **At 39,602 vectors:** ~2-5ms per query (fast enough)
- **At 50M vectors:** Estimated ~2-5 seconds per query (unacceptable)

### IVF Approximate Search (Recall vs Latency)

From FAISS benchmarks on SIFT1M (128-dim, 1M vectors, IVF16384):

| nprobe | Recall@1 | Recall@10 | Search time (1M vectors) |
|--------|----------|-----------|-------------------------|
| 1 | 0.409 | ~0.35 | 0.076 ms |
| 8 | 0.740 | ~0.70 | ~0.10 ms |
| 32 | 0.913 | ~0.90 | ~0.15 ms |
| 64 | 0.947 | ~0.94 | 0.141 ms |
| 128 | 0.975 | ~0.97 | ~0.22 ms |
| 256 | 0.986 | ~0.98 | 0.344 ms |

For RAG applications, **Recall@10 of 0.90+ is generally sufficient** because:
1. The query engine already uses top_k=12 (retrieves 12 candidates)
2. The LLM synthesizes answers from multiple chunks
3. Missing one chunk out of 12 rarely changes the final answer quality

### IVF_SQ8 Recall Penalty

IVF_SQ8 adds at most 1% recall degradation on top of the IVF clustering
approximation (from Milvus benchmarks). So IVF4096_SQ8 at nprobe=64 would
achieve approximately:
- **Recall@10: ~0.93** (vs 0.94 for IVF_Flat at same nprobe)
- **Latency: Sub-millisecond** for 1M vectors, ~5-10ms for 50M vectors on CPU

### IVFPQ Recall Penalty

PQ adds a larger recall hit. From FAISS benchmarks:
- IVFPQ with adequate nprobe achieves ~50-70% recall@1
- With reranking (refine step), this improves to 85-95%
- "Very high recall is out of reach for both PQ and IVFPQ indexes" (Pinecone)

### FastScan (4-bit PQ) Performance

**[NOVEL FIND]** FAISS FastScan (PQ with 4-bit codes, index factory `IVFx,PQyxfsr`)
achieves remarkable throughput:
- Without reranking: up to 1M QPS
- With reranking: 280K QPS at 0.9 recall@1
- This is 2x faster than HNSW (140K QPS) at the same recall, using 2.7x less memory

Source: [FAISS Wiki - Fast accumulation of PQ and AQ codes](https://github.com/facebookresearch/faiss/wiki/Fast-accumulation-of-PQ-and-AQ-codes-(FastScan))

### Recommendation for HybridRAG3

For a RAG system retrieving top-12 candidates, IVF_SQ8 with nprobe=32-64
provides an excellent balance:
- Recall@10 > 0.90 (more than sufficient for RAG)
- Sub-10ms latency at 50M vectors on CPU
- 4x memory savings over flat index

---

## 7. Migration Interface: Memmap to FAISS

### API Surface Comparison

| Operation | Current (memmap) | FAISS |
|-----------|-----------------|-------|
| Create store | `EmbeddingMemmapStore(dir, dim=384)` | `faiss.IndexIVFScalarQuantizer(quantizer, dim, nlist, faiss.ScalarQuantizer.QT_8bit)` |
| Train | N/A | `index.train(training_vectors)` |
| Add vectors | `mem_store.append_batch(embeddings)` | `index.add(embeddings)` or `index.add_with_ids(embeddings, ids)` |
| Search | Manual cosine sim in blocks | `distances, indices = index.search(query, top_k)` |
| Save to disk | Automatic (memmap is file-backed) | `faiss.write_index(index, "path.faiss")` |
| Load from disk | `np.memmap(path, ...)` | `faiss.read_index("path.faiss")` |
| Memory-mapped load | Built-in (memmap is mmap) | `faiss.read_index("path.faiss", faiss.IO_FLAG_MMAP)` |

### Migration Code Sketch

```python
import faiss
import numpy as np

# ----- BUILD PHASE (one-time, during indexing) -----

dim = 384
nlist = 4096  # number of clusters

# Step 1: Create the index
quantizer = faiss.IndexFlatIP(dim)  # Inner product for cosine sim
index = faiss.IndexIVFScalarQuantizer(
    quantizer, dim, nlist,
    faiss.ScalarQuantizer.QT_8bit,
    faiss.METRIC_INNER_PRODUCT
)

# Step 2: Train on a representative sample
# Load sample from existing memmap
sample = np.memmap("embeddings.f16.dat", dtype=np.float16,
                   mode="r", shape=(39602, 384))
training_data = np.array(sample[:39602], dtype=np.float32)
# Normalize for cosine similarity
norms = np.linalg.norm(training_data, axis=1, keepdims=True)
norms[norms == 0] = 1.0
training_data = training_data / norms

index.train(training_data)

# Step 3: Add all vectors (in batches for large datasets)
batch_size = 100_000
for start in range(0, total_vectors, batch_size):
    end = min(start + batch_size, total_vectors)
    batch = load_vectors(start, end)  # from memmap
    batch = normalize(batch)
    index.add(batch)

# Step 4: Save
faiss.write_index(index, "hybridrag.faiss")

# ----- QUERY PHASE (at runtime) -----

# Load (optionally memory-mapped for IVF)
index = faiss.read_index("hybridrag.faiss")
index.nprobe = 32  # tune for recall/speed tradeoff

# Search
query_vec = normalize(embed("user question"))
distances, indices = index.search(
    query_vec.reshape(1, -1).astype(np.float32), k=12
)

# indices[0] contains the row IDs -> look up in SQLite
```

### Key Migration Considerations

1. **ID mapping:** FAISS uses sequential integer IDs by default. The current system
   uses `embedding_row` integers in SQLite, which map directly. No change needed.

2. **Cosine similarity:** FAISS does not natively support cosine distance. The
   standard approach is to L2-normalize all vectors before indexing, then use
   inner product (`METRIC_INNER_PRODUCT`). This is mathematically equivalent
   to cosine similarity for unit vectors.

3. **Incremental updates:** The current memmap is append-only. FAISS IVF indexes
   support `add()` for appending but `remove_ids()` for IVF indexes requires
   `direct_map` to be enabled (which uses additional RAM). For the current
   workflow where files are re-indexed by deleting and re-adding, this is
   acceptable -- but retraining is NOT needed for incremental adds.

4. **Float16 to Float32:** The current system stores float16. FAISS operates on
   float32 internally. The migration must cast float16 -> float32 during
   indexing. At query time, FAISS handles precision internally based on the
   quantizer (SQ8 stores uint8 anyway).

5. **Backward compatibility:** Keep the SQLite metadata store unchanged. Only
   replace the `EmbeddingMemmapStore` class with a `FaissVectorStore` class
   that wraps FAISS index operations.

Source: [FAISS GitHub - faiss_tips](https://github.com/matsui528/faiss_tips), [FAISS Wiki](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)

---

## 8. Concurrent Query Performance (10 Users)

### Thread Safety

From the official FAISS wiki on [Threads and asynchronous calls](https://github.com/facebookresearch/faiss/wiki/Threads-and-asynchronous-calls):

**CPU indexes:**
- **Concurrent reads (searches) are thread-safe** with no locking required
- Concurrent write operations (add, remove) are NOT thread-safe -- require external mutex
- The Python GIL is released during `search()`, `add()`, and `train()` calls,
  enabling true multi-core parallelism from Python threads

**GPU indexes:**
- NOT thread-safe, even for read-only operations
- `StandardGpuResources` manages temporary GPU memory for a single thread
- Each CPU thread needs its own `StandardGpuResources` instance
- A single `GpuResources` supports multiple devices but only from one thread

### Performance Model for 10 Concurrent Users

**Best approach: Batch incoming queries**

Rather than 10 threads each calling `index.search()` separately, aggregate
queries into a batch and submit once:

```python
# Instead of 10 separate searches:
# for query in queries: index.search(query, k=12)

# Do this:
batch = np.stack(queries)  # shape: (10, 384)
distances, indices = index.search(batch, k=12)
# Returns distances shape (10, 12), indices shape (10, 12)
```

FAISS search performance is significantly better with batch queries than
individual queries. Submitting batches from multiple threads simultaneously
is "very inefficient" as it spawns more threads than CPU cores due to OpenMP.

### Estimated QPS for 10-User Workload

| Configuration | Single query latency | Batch of 10 latency | Effective QPS |
|--------------|---------------------|--------------------|--------------|
| IVF4096,SQ8 (CPU, 50M vectors) | ~5-10 ms | ~10-20 ms | ~500-1000 |
| IVF4096,SQ8 (GPU, 50M vectors) | ~1-2 ms | ~2-5 ms | ~2000-5000 |
| IVF16384,PQ48 (CPU, 50M vectors) | ~2-5 ms | ~5-10 ms | ~1000-2000 |

For 10 concurrent users with typical RAG query patterns (1 query every few
seconds per user), even the CPU configuration provides massive headroom.

### OpenMP Thread Tuning

**[NOVEL FIND]** From FAISS GitHub issue #422 and #4306: Setting
`omp_set_num_threads(1)` and using application-level threading for concurrent
searches can outperform OpenMP's own parallelism when handling many concurrent
queries. This avoids OpenMP thread over-subscription. A recommended configuration
for 10-user serving on a 16-core machine:

```python
import faiss
faiss.omp_set_num_threads(4)  # 4 OMP threads per search
# Use 4 application threads for concurrent searches
# Total: 16 cores utilized without over-subscription
```

### FastAPI Integration Pattern

For the existing FastAPI server (`src/api/server.py`):

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Single index, shared across all requests (read-only)
index = faiss.read_index("hybridrag.faiss")
index.nprobe = 32
executor = ThreadPoolExecutor(max_workers=4)

async def search_endpoint(query_vec):
    loop = asyncio.get_event_loop()
    # GIL is released during faiss search, so ThreadPoolExecutor works
    distances, indices = await loop.run_in_executor(
        executor, lambda: index.search(query_vec, 12)
    )
    return distances, indices
```

Source: [FAISS Wiki - Threads and asynchronous calls](https://github.com/facebookresearch/faiss/wiki/Threads-and-asynchronous-calls),
[FAISS Issue #367](https://github.com/facebookresearch/faiss/issues/367)

---

## 9. GPU Acceleration with Dual RTX 3090s

### Hardware Specs

- 2x NVIDIA RTX 3090, 24GB GDDR6X each (48GB total VRAM)
- Compute Capability 8.6 (Ampere)
- Memory bandwidth: 936 GB/s each
- FAISS minimum requirement: Compute Capability 3.5 (satisfied)

### GPU Index Types Supported

| GPU Index | CPU Equivalent | Notes |
|-----------|---------------|-------|
| GpuIndexFlat | IndexFlat | Exact search, fastest for small datasets |
| GpuIndexIVFFlat | IndexIVFFlat | IVF without compression |
| GpuIndexIVFScalarQuantizer | IndexIVFScalarQuantizer | IVF + SQ8 |
| GpuIndexIVFPQ | IndexIVFPQ | IVF + Product Quantization |
| GpuIndexCagra | (GPU-native) | GPU-optimized graph index (cuVS) |

### Multi-GPU Configuration

Two strategies:

**1. IndexReplicas (recommended for throughput):**
Each GPU holds a complete copy of the index. Queries are distributed across GPUs.
Expected speedup: ~1.8-2x over single GPU (near-linear for 2 GPUs).

```python
ngpu = 2
resources = [faiss.StandardGpuResources() for i in range(ngpu)]
index_gpu = faiss.index_cpu_to_gpu_multiple_py(resources, index_cpu)
```

**2. IndexShards (recommended for large indexes):**
Each GPU holds half the index. Both GPUs are queried, results merged.
Enables indexes up to 48GB on GPU (vs 24GB per GPU limit).

```python
co = faiss.GpuMultipleClonerOptions()
co.shard = True
index_gpu = faiss.index_cpu_to_gpu_multiple_py(resources, index_cpu, co)
```

### Memory Budget per GPU

| Index Config | Size at 50M vectors | Fits single 3090? | Fits sharded 2x3090? |
|-------------|--------------------|--------------------|---------------------|
| IVF4096,Flat | ~73 GB | No | No |
| IVF4096,SQ8 | ~18.6 GB | Yes (with ~5GB headroom) | Yes (9.3GB each) |
| IVF4096,PQ48 | ~2.7 GB | Yes | Yes |

Plus ~1.5 GB overhead for `StandardGpuResources` scratch memory per GPU.

### GPU Performance Expectations

From FAISS documentation and NVIDIA cuVS benchmarks:
- GPU FAISS is 5x-10x faster than CPU for single-GPU
- With 2 GPUs (replication): ~10-18x faster than single-CPU
- GPU operations are memory-bandwidth limited (not compute limited)
- Batch queries are essential for GPU performance (minimum batch size: 32+)

### CAGRA Index (GPU-Native Graph Search)

**[NOVEL FIND]** CAGRA (CUDA ANN Graph) is a GPU-native graph index introduced
via NVIDIA cuVS integration in FAISS 1.10+. It outperforms CPU HNSW build times
by up to 12.3x and reduces search latency by up to 4.7x. CAGRA can be converted
to HNSW format for CPU fallback search. This is the fastest option for GPU-only
deployments.

Available in FAISS 1.12+ with FP16 support (`GpuIndexCagra`).

### Important Limitations

- `k` (number of nearest neighbors) and `nprobe` must be <= 2,048 on GPU
- GpuIndexIVFPQ code sizes limited to: 1, 2, 3, 4, 8, 12, 16, 20, 24, 28, 32, 48, 56, 64, 96 bytes
- Code sizes >= 56 bytes require float16 mode
- GPU indexes are NOT thread-safe (one `StandardGpuResources` per thread)
- **FAISS-GPU is not officially supported on Windows** (see Section 10)

Source: [FAISS Wiki - Faiss on the GPU](https://github.com/facebookresearch/faiss/wiki/Faiss-on-the-GPU),
[NVIDIA cuVS Blog](https://developer.nvidia.com/blog/enhancing-gpu-accelerated-vector-search-in-faiss-with-nvidia-cuvs/)

---

## 10. Python 3.11 Compatibility

### faiss-cpu

**Fully supported on Python 3.11.**

- Latest version: `faiss-cpu 1.13.2` (December 24, 2025)
- Available via pip: `pip install faiss-cpu`
- Available via conda: `conda install -c pytorch faiss-cpu=1.13.2`
- Windows pip wheels available (x86_64)
- No known compatibility issues with Python 3.11

### faiss-gpu

**Situation is more complex:**

| Install Method | Python 3.11 Support | Windows Support | Notes |
|---------------|--------------------|-----------------| ------|
| `pip install faiss-gpu` | Discontinued since 1.7.3 | No | Do not use |
| `pip install faiss-gpu-cu12` | Yes (wheels available) | No (Linux only) | Unofficial, community-maintained |
| `conda install -c pytorch faiss-gpu` | Yes | No (Linux x86-64 only) | Official, recommended |
| `conda install faiss-gpu-cuvs` | Yes | No (Linux x86-64 only) | With NVIDIA cuVS acceleration |
| Build from source | Yes | Possible with WSL | Complex, error-prone natively |

### Critical Finding: Windows GPU Support

**FAISS-GPU has NO official Windows support.** The workstation must run either:

1. **WSL2 with Ubuntu** (recommended): Full FAISS-GPU support including cuVS
2. **Native Linux** (dual-boot): Best performance, full GPU support
3. **Windows with faiss-cpu only**: Works, but no GPU acceleration

**[NOVEL FIND]** FAISS GitHub Discussion #4165 and #4610 confirm that as of late
2025, there is still no official Windows faiss-gpu conda package. The community
`faiss-gpu-cu12` pip package is Linux-only. Users report building from source on
Windows with CUDA is possible but "time-consuming and prone to compilation errors."

### Recommendation

For the dual-3090 workstation:
1. **Development/testing on Windows:** Use `faiss-cpu` (pip, works immediately)
2. **Production serving with GPU:** Use WSL2 with `conda install faiss-gpu-cuvs`
3. **Alternative:** Install native Ubuntu as a dual-boot option for maximum
   performance

The RTX 3090 (Compute Capability 8.6, Ampere) is fully compatible with all
FAISS GPU builds that support CC 7.0+.

Source: [faiss-cpu PyPI](https://pypi.org/project/faiss-cpu/),
[faiss-gpu-cu12 PyPI](https://pypi.org/project/faiss-gpu-cu12/),
[FAISS INSTALL.md](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md)

---

## 11. Recommended nprobe and nlist Configuration

### nlist (Number of Clusters) Selection

The rule of thumb is `nlist = sqrt(N)` as a starting point:

| Dataset Size (N) | sqrt(N) | FAISS Wiki Recommendation | Training vectors needed |
|-----------------|---------|--------------------------|------------------------|
| 39,602 (current) | 199 | `IVF256` to `IVF1024` | 30K-256K |
| 1M | 1,000 | `IVF4096` to `IVF16384` | 1.2M-16M |
| 10M | 3,162 | `IVF16384,HNSW32` | 5M-16M |
| 50M | 7,071 | `IVF65536,HNSW32` | 20M-65M |
| 100M | 10,000 | `IVF262144,HNSW32` | 80M+ |

**Using HNSW as the coarse quantizer** (e.g., `IVF65536_HNSW32`) speeds up
cluster assignment by 8.2x compared to exhaustive assignment without degrading
cluster quality (FAISS wiki benchmark).

### nprobe Selection

nprobe determines how many clusters are searched at query time.
Search time scales approximately linearly with nprobe.

| Goal | nlist | nprobe | % clusters searched | Expected Recall@10 |
|------|-------|--------|--------------------|--------------------|
| Maximum speed | 4,096 | 8 | 0.2% | ~0.70 |
| Good balance | 4,096 | 32 | 0.8% | ~0.90 |
| High recall | 4,096 | 64 | 1.6% | ~0.95 |
| Near-exact | 4,096 | 128 | 3.1% | ~0.98 |
| Maximum speed | 16,384 | 16 | 0.1% | ~0.75 |
| Good balance | 16,384 | 64 | 0.4% | ~0.92 |
| High recall | 16,384 | 128 | 0.8% | ~0.96 |

### Recommended Starting Configuration for HybridRAG3

**Phase 1 (current scale, ~40K vectors):**
```
IVF256,SQ8    nprobe=16    # 6.25% of clusters searched
```

**Phase 2 (1M-10M vectors):**
```
IVF4096,SQ8    nprobe=32   # 0.8% of clusters searched
```

**Phase 3 (50M+ vectors):**
```
IVF65536_HNSW32,SQ8    nprobe=64   # 0.1% of clusters searched
```

### Autofaiss for Automatic Tuning

**[NOVEL FIND]** Criteo's [autofaiss](https://github.com/criteo/autofaiss) library
(v2.18.0) can automatically select optimal index parameters given memory and
latency constraints:

```python
from autofaiss import build_index

build_index(
    embeddings="path/to/embeddings/",
    index_path="output/knn.index",
    max_index_memory_usage="16G",  # fit in 16GB
    current_memory_available="32G",
)
```

It benchmarks multiple configurations and selects the one maximizing recall
within constraints. For 200M vectors, it builds an optimal index in ~3 hours
using only 15GB of RAM with 10ms query latency. This could replace manual
tuning of nlist/nprobe.

Source: [FAISS Wiki - Faster search](https://github.com/facebookresearch/faiss/wiki/Faster-search),
[FAISS Issue #112](https://github.com/facebookresearch/faiss/issues/112),
[autofaiss PyPI](https://pypi.org/project/autofaiss/)

---

## 12. Alternatives: HNSW, ScaNN, Flat+GPU

### Option A: FAISS HNSW (IndexHNSWFlat)

**Pros:**
- Near-perfect recall (95%+) easily achievable
- No training phase required
- Very fast single-query latency (~0.01-0.1ms for 1M vectors)
- Excellent for small-to-mid datasets

**Cons:**
- High memory: `(d * 4 + M * 2 * 4)` bytes per vector
  - At 384-dim, M=32: 1,792 bytes/vector = 85 GB for 50M vectors
- Very slow build times at scale (hours to days for 50M+ vectors)
- No GPU acceleration (CPU only in FAISS; CAGRA is the GPU alternative)
- No on-disk/mmap support

**Verdict:** Not viable at 50M+ vectors due to memory requirements.

### Option B: Google ScaNN

**Pros:**
- Often lower p95 latency than FAISS at same recall on large corpora
- Simpler configuration than FAISS
- Good CPU performance

**Cons:**
- No GPU support (CPU-focused)
- Approximate search only (no exact mode)
- TensorFlow ecosystem dependency
- In a 2025 gene embedding benchmark, FAISS consistently outperformed ScaNN
  in indexing speed, query latency, and retrieval accuracy
- Less flexible index type selection

**Verdict:** Not recommended. FAISS provides better GPU support, more index
type flexibility, and generally equal or better performance.

### Option C: Flat Index + GPU (GpuIndexFlatIP)

**Pros:**
- Exact search (recall = 1.0)
- Extremely fast with GPU (5-10x over CPU)
- No training required
- Simple migration from current brute-force

**Cons:**
- Memory: 50M x 384 x 4 = 73 GB -- does not fit in 48GB VRAM
- Even at current 39,602 vectors, this is overkill
- Does not scale

**Verdict:** Viable only for the current 40K-vector scale. Not a long-term solution.

### Option D: CAGRA (GPU-native graph index)

**Pros:**
- GPU-optimized, 12.3x faster build than CPU HNSW
- 4.7x lower search latency than CPU HNSW
- Can be converted to HNSW for CPU fallback
- Supported in FAISS 1.10+ via cuVS

**Cons:**
- GPU-only (no CPU version, though HNSW export exists)
- Requires Linux (no Windows support)
- Newer, less battle-tested in production
- Memory requirements similar to HNSW on GPU

**Verdict:** Excellent future option for the workstation. Worth benchmarking
alongside IVF_SQ8 once the workstation is operational with Linux/WSL.

### Option E: Stay with numpy memmap + optimize

**Pros:**
- No new dependencies
- Zero migration effort
- Works on Windows

**Cons:**
- O(N) search -- will not scale beyond ~500K vectors
- No approximate search capability
- No GPU acceleration
- No built-in threading optimization

**Verdict:** Acceptable only for the current scale. Must migrate before scaling.

### Comparison Summary

| Option | Max practical scale | Memory (50M, 384d) | Recall@10 | Query latency (50M) | GPU? |
|--------|--------------------|--------------------|-----------|---------------------|------|
| IVF_SQ8 | Billions | ~18.6 GB | ~0.93 | 5-10ms (CPU) | Yes |
| HNSW | ~10M | ~85 GB | ~0.98 | <1ms | No |
| ScaNN | Billions | ~20 GB | ~0.90 | 5-10ms | No |
| Flat+GPU | ~15M (48GB VRAM) | ~73 GB | 1.0 | <1ms | Yes |
| CAGRA | ~100M (GPU) | ~20 GB (GPU) | ~0.95 | <1ms | Yes (only) |
| numpy memmap | ~500K | Proportional | 1.0 | 2-5s | No |

---

## 13. Novel and Undocumented Findings

### [NOVEL FIND] RaBitQ as IVF Alternative

RaBitQ, introduced in FAISS 1.11 and optimized through 1.13 with FastScan and
SIMD, provides `(d/8 + 8)` bytes per vector encoding. For 384-dim vectors,
that is ~56 bytes -- comparable to PQ48 but with potentially better recall.
The `IndexIVFRaBitQFastScan` is the newest index type and is not yet widely
benchmarked in the community. It should be evaluated against IVF_SQ8 for this
project.

### [NOVEL FIND] GPU Memory Regression in FAISS 1.6.3+

FAISS GitHub issue #1448 documents that GPU memory usage increases linearly
when adding vectors to IVF indexes and never releases, starting from v1.6.3.
This was a regression from v1.5.3 where GPU memory stayed constant during add.
Build indexes on CPU and transfer to GPU for serving to avoid this.

### [NOVEL FIND] OpenMP Thread Tuning for Concurrent Serving

FAISS issue #4306 and #422 show that disabling OpenMP multithreading
(`omp_set_num_threads(1)`) and using application-level concurrency can
outperform the default OpenMP parallelism for serving scenarios with many
concurrent users. This is because OpenMP was designed for batch parallelism,
not request-level parallelism.

### [NOVEL FIND] autofaiss for Automated Index Selection

Criteo's autofaiss library can automatically select the optimal index type,
nlist, and nprobe given memory and latency constraints. It benchmarked 200M
vectors in 3 hours with 15GB RAM and 10ms latency. This is not widely known
outside the recommendation system community.

### [NOVEL FIND] SQ8 Performance at 384 Dimensions

Community reports suggest SQ8 recall at 384 dimensions is significantly better
than at 768 dimensions (0.95+ vs 0.87 for 10-recall@10) because lower-dimensional
vectors have less quantization noise per dimension. The official FAISS codec
benchmarks only test 768-dim (Contriever) and 1024-dim (sentence embeddings),
potentially understating SQ8 quality for 384-dim use cases.

### [NOVEL FIND] IO_FLAG_MMAP Only for IVF

Memory-mapped loading (`faiss.IO_FLAG_MMAP`) is only supported for IVF indexes,
not Flat or HNSW. FAISS issue #3165 is an open feature request for Flat index
mmap support. This means if multiple FastAPI workers need to share the same
index, they must each load their own copy unless using IVF.

### [NOVEL FIND] Panorama Index (FAISS 1.13)

A new `IndexIVFFlatPanorama` was introduced in FAISS 1.13.0 with serialization
support and statistics tracking. No public benchmarks exist yet. Worth
monitoring as a potential alternative for range-search workloads.

---

## 14. Recommended Migration Plan

### Phase 0: Preparation (Week 1)

1. Install `faiss-cpu` on current laptop: `pip install faiss-cpu==1.13.2`
2. Write a `FaissVectorStore` class that mirrors the `EmbeddingMemmapStore` interface
3. Add FAISS to `requirements.txt` / `requirements_approved.txt`
4. Verify all 84 pytest tests pass with the new dependency

### Phase 1: CPU Migration (Week 2)

1. Build `IVF256,SQ8` index from current 39,602 vectors (takes seconds)
2. Replace `search()` method in `VectorStore` to use FAISS `index.search()`
3. Keep SQLite metadata store unchanged
4. Validate with the 400-question golden evaluation set
5. Benchmark: compare latency and recall against current brute-force
6. Deploy as default on laptop

### Phase 2: Scale Testing (Week 3-4)

1. Generate synthetic data to simulate 1M, 10M, 50M vector scales
2. Benchmark `IVF4096,SQ8` with various nprobe values
3. Test memory usage, build times, and query latency at each scale
4. Validate concurrent query safety with 10-thread stress test
5. Test `autofaiss` for automatic parameter selection

### Phase 3: GPU Deployment (When Workstation Arrives)

1. Set up WSL2 with Ubuntu on workstation
2. Install `faiss-gpu-cuvs` via conda
3. Benchmark `IVF4096,SQ8` on single 3090 vs CPU
4. Test dual-3090 with IndexReplicas and IndexShards
5. Evaluate CAGRA index as an alternative
6. Tune OpenMP threads for 10-user serving scenario

### Phase 4: Production Scale (Ongoing)

1. Index actual 650GB document corpus
2. Scale nlist based on actual vector count
3. Implement on-disk inverted lists if index exceeds 64GB RAM
4. Add monitoring for query latency and recall metrics
5. Implement background re-indexing pipeline (train + add without downtime)

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Recall drop unacceptable for eval | Keep brute-force fallback, compare results |
| Windows GPU not supported | Use WSL2 or dual-boot Linux |
| FAISS version breaks | Pin to 1.13.2, test before upgrading |
| Index corruption on crash | Write to temp file, atomic rename |
| Memory exceeded during build | Train on subset, add in batches, use on-disk lists |

---

## 15. Sources

### Official Documentation
- [FAISS GitHub Repository](https://github.com/facebookresearch/faiss)
- [FAISS Wiki - Guidelines to choose an index](https://github.com/facebookresearch/faiss/wiki/Guidelines-to-choose-an-index)
- [FAISS Wiki - Faiss indexes](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)
- [FAISS Wiki - The index factory](https://github.com/facebookresearch/faiss/wiki/The-index-factory)
- [FAISS Wiki - Faiss on the GPU](https://github.com/facebookresearch/faiss/wiki/Faiss-on-the-GPU)
- [FAISS Wiki - GPU Faiss with cuVS](https://github.com/facebookresearch/faiss/wiki/GPU-Faiss-with-cuVS)
- [FAISS Wiki - Threads and asynchronous calls](https://github.com/facebookresearch/faiss/wiki/Threads-and-asynchronous-calls)
- [FAISS Wiki - Faster search](https://github.com/facebookresearch/faiss/wiki/Faster-search)
- [FAISS Wiki - Indexes that do not fit in RAM](https://github.com/facebookresearch/faiss/wiki/Indexes-that-do-not-fit-in-RAM)
- [FAISS Wiki - Indexing 1M vectors](https://github.com/facebookresearch/faiss/wiki/Indexing-1M-vectors)
- [FAISS Wiki - Vector codec benchmarks](https://github.com/facebookresearch/faiss/wiki/Vector-codec-benchmarks)
- [FAISS Wiki - FAQ](https://github.com/facebookresearch/faiss/wiki/FAQ)
- [FAISS CHANGELOG](https://github.com/facebookresearch/faiss/blob/main/CHANGELOG.md)
- [FAISS INSTALL.md](https://github.com/facebookresearch/faiss/blob/main/INSTALL.md)
- [FAISS Documentation (faiss.ai)](https://faiss.ai/index.html)
- [FAISS Paper (arXiv)](https://arxiv.org/html/2401.08281v4)

### NVIDIA and Meta Engineering
- [Enhancing GPU-Accelerated Vector Search in Faiss with NVIDIA cuVS](https://developer.nvidia.com/blog/enhancing-gpu-accelerated-vector-search-in-faiss-with-nvidia-cuvs/)
- [Accelerating GPU indexes in Faiss with NVIDIA cuVS - Engineering at Meta](https://engineering.fb.com/2025/05/08/data-infrastructure/accelerating-gpu-indexes-in-faiss-with-nvidia-cuvs/)
- [Accelerating Vector Search: NVIDIA cuVS IVF-PQ Part 1](https://developer.nvidia.com/blog/accelerating-vector-search-nvidia-cuvs-ivf-pq-deep-dive-part-1/)

### GitHub Issues (FAISS)
- [Issue #112 - How to select a suitable nlist](https://github.com/facebookresearch/faiss/issues/112)
- [Issue #367 - Are search operations thread safe?](https://github.com/facebookresearch/faiss/issues/367)
- [Issue #422 - Inefficient multi-core usage](https://github.com/facebookresearch/faiss/issues/422)
- [Issue #924 - Querying faiss with multiprocessing](https://github.com/facebookresearch/faiss/issues/924)
- [Issue #949 - Training OPQ+IVF too long](https://github.com/facebookresearch/faiss/issues/949)
- [Issue #1108 - Memory consumption with multiple threads](https://github.com/facebookresearch/faiss/issues/1108)
- [Issue #1239 - Can I add index on disk instead of RAM](https://github.com/facebookresearch/faiss/issues/1239)
- [Issue #1262 - Ondisk merge consuming RAM](https://github.com/facebookresearch/faiss/issues/1262)
- [Issue #1448 - GPU Memory Usage Increase Adding Vectors](https://github.com/facebookresearch/faiss/issues/1448)
- [Issue #1520 - Estimate memory usage of IVFPQ](https://github.com/facebookresearch/faiss/issues/1520)
- [Issue #1559 - Scalar Quantization Implementation](https://github.com/facebookresearch/faiss/issues/1559)
- [Issue #2106 - Cannot load index with IO_FLAG_MMAP](https://github.com/facebookresearch/faiss/issues/2106)
- [Issue #2583 - Using FAISS in production](https://github.com/facebookresearch/faiss/issues/2583)
- [Issue #3094 - 100+ Million vectors into Faiss Index](https://github.com/facebookresearch/faiss/issues/3094)
- [Issue #3165 - IO_FLAG_MMAP for IndexFlat](https://github.com/facebookresearch/faiss/issues/3165)
- [Issue #3493 - OnDisk IVF and GPU Search memory issue](https://github.com/facebookresearch/faiss/issues/3493)
- [Issue #4196 - IVF per vector memory budget](https://github.com/facebookresearch/faiss/issues/4196)
- [Issue #4306 - Concurrent Search latency](https://github.com/facebookresearch/faiss/issues/4306)
- [Discussion #4165 - FAISS-GPU compatibility with Windows](https://github.com/facebookresearch/faiss/discussions/4165)
- [Discussion #4610 - GPU compatibility on Windows](https://github.com/facebookresearch/faiss/discussions/4610)

### Package Repositories
- [faiss-cpu on PyPI](https://pypi.org/project/faiss-cpu/)
- [faiss-gpu on PyPI](https://pypi.org/project/faiss-gpu/)
- [faiss-gpu-cu12 on PyPI](https://pypi.org/project/faiss-gpu-cu12/)
- [faiss-gpu on conda (pytorch channel)](https://anaconda.org/pytorch/faiss-gpu)
- [faiss-cpu on conda-forge](https://anaconda.org/conda-forge/faiss-cpu)
- [autofaiss on PyPI](https://pypi.org/project/autofaiss/)
- [autofaiss on GitHub (Criteo)](https://github.com/criteo/autofaiss)

### Tutorials and Benchmarks
- [Pinecone - Product Quantization](https://www.pinecone.io/learn/series/faiss/product-quantization/)
- [Pinecone - FAISS Tutorial](https://www.pinecone.io/learn/series/faiss/faiss-tutorial/)
- [Pinecone - Facebook AI and the Index Factory](https://www.pinecone.io/learn/series/faiss/composite-indexes/)
- [Zilliz - Faiss vs HNSWlib on Vector Search](https://zilliz.com/blog/faiss-vs-hnswlib-choosing-the-right-tool-for-vector-search)
- [Zilliz - Faiss vs ScaNN](https://zilliz.com/blog/faiss-vs-scann-choosing-the-right-tool-for-vector-search)
- [MyScale - HNSW vs IVF Explained](https://www.myscale.com/blog/hnsw-vs-ivf-explained-powerful-comparison/)
- [MyScale - FAISS vs Milvus Performance Analysis](https://www.myscale.com/blog/faiss-vs-milvus-performance-analysis/)
- [OpenSearch - Optimizing with Faiss FP16 scalar quantization](https://opensearch.org/blog/optimizing-opensearch-with-fp16-quantization/)
- [ANN-Benchmarks (faiss-ivf)](https://ann-benchmarks.com/faiss-ivf.html)
- [Deep Dive into Faiss IndexIVFPQ](https://sidshome.wordpress.com/2023/12/30/deep-dive-into-faiss-indexivfpq-for-vector-search/)
- [Scaling Semantic Search with FAISS (Medium)](https://medium.com/@deveshbajaj59/scaling-semantic-search-with-faiss-challenges-and-solutions-for-billion-scale-datasets-1cacb6f87f95)
- [10 FAISS Heuristics for Low-Latency Search (Medium)](https://medium.com/@sparknp1/10-faiss-heuristics-for-low-latency-hnsw-ivf-search-bf906d76064f)
- [10 FAISS IVF/PQ Settings (Medium)](https://medium.com/@Modexa/10-faiss-ivf-pq-settings-you-shouldnt-ignore-97725f87ff0b)
- [FAISS Tips Repository](https://github.com/matsui528/faiss_tips)
- [PyImageSearch - Vector Search with FAISS](https://pyimagesearch.com/2026/02/16/vector-search-with-faiss-approximate-nearest-neighbor-ann-explained/)
- [FAISS and Annoy Benchmark Paper (arXiv)](https://arxiv.org/pdf/2412.01555)
- [Fast and Scalable Gene Embedding Search (FAISS vs ScaNN)](https://arxiv.org/html/2507.16978v1)

### Vector Database Comparisons
- [Weaviate - Vector Library vs Vector Database](https://weaviate.io/blog/vector-library-vs-vector-database)
- [LiquidMetal AI - Vector Database Comparison 2025](https://liquidmetal.ai/casesAndBlogs/vector-comparison/)
- [Firecrawl - Best Vector Databases 2025](https://www.firecrawl.dev/blog/best-vector-databases)

---

*Document generated 2026-02-21. All benchmark numbers are approximate and
hardware-dependent. Actual performance should be validated with project-specific
data before production deployment.*
