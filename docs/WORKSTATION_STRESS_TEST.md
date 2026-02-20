# Workstation Stress Test Simulation Results

**Date:** 2026-02-20T15:04:19.087689

## Hardware Profile

| Component | Spec |
|-----------|------|
| CPU | 16 threads |
| RAM | 64 GB |
| GPU | NVIDIA 12GB (12 GB VRAM) |
| Storage | 2 TB HDD (150 MB/s) |

## Index Profile

| Metric | 700 GB Source | 2 TB Source |
|--------|---------------|-------------|
| Chunks | 8,400,000 | 24,000,000 |
| Embeddings | 6.45 GB | 18.43 GB |
| SQLite DB | 4.20 GB | 12.00 GB |

## Offline (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 114.6s | 145.4s | Poor |
| 8 | 30.7s | 93.8s | 124.4s | Poor |
| 6 | 30.6s | 72.9s | 103.5s | Poor |
| 4 | 30.4s | 52.1s | 82.5s | Slow |
| 3 | 30.4s | 41.7s | 72.1s | Slow |
| 2 | 30.4s | 31.3s | 61.7s | Slow |

## Offline (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 198.2s | 229.0s | Unusable |
| 8 | 30.7s | 162.1s | 192.8s | Unusable |
| 6 | 30.6s | 126.1s | 156.7s | Poor |
| 4 | 30.4s | 90.1s | 120.5s | Poor |
| 3 | 30.4s | 72.1s | 102.5s | Poor |
| 2 | 30.4s | 54.0s | 84.4s | Slow |

## Online (gpt-4o) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 6.5s | 37.3s | Acceptable |
| 8 | 30.7s | 6.2s | 36.9s | Acceptable |
| 6 | 30.6s | 6.2s | 36.7s | Acceptable |
| 4 | 30.4s | 5.9s | 36.3s | Acceptable |
| 3 | 30.4s | 5.9s | 36.3s | Acceptable |
| 2 | 30.4s | 5.9s | 36.3s | Acceptable |

## Online (gpt-4o-mini) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 4.2s | 35.0s | Acceptable |
| 8 | 30.7s | 4.0s | 34.7s | Acceptable |
| 6 | 30.6s | 4.0s | 34.6s | Acceptable |
| 4 | 30.4s | 3.8s | 34.2s | Acceptable |
| 3 | 30.4s | 3.8s | 34.2s | Acceptable |
| 2 | 30.4s | 3.8s | 34.2s | Acceptable |

## Offline (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 114.6s | 145.4s | Poor |
| 8 | 30.7s | 93.8s | 124.5s | Poor |
| 6 | 30.6s | 72.9s | 103.5s | Poor |
| 4 | 30.4s | 52.1s | 82.5s | Slow |
| 3 | 30.4s | 41.7s | 72.1s | Slow |
| 2 | 30.4s | 31.3s | 61.7s | Slow |

## Online (gpt-4o) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 30.8s | 6.5s | 37.3s | Acceptable |
| 8 | 30.7s | 6.2s | 36.9s | Acceptable |
| 6 | 30.6s | 6.2s | 36.7s | Acceptable |
| 4 | 30.4s | 5.9s | 36.3s | Acceptable |
| 3 | 30.4s | 5.9s | 36.3s | Acceptable |
| 2 | 30.4s | 5.9s | 36.3s | Acceptable |

## Improvement Recommendations

### #1. Replace HDD with NVMe SSD
- **Cost:** $100-200 for 2 TB NVMe
- **Impact:** Vector search: 15-20x faster (HDD 150 MB/s -> SSD 3500 MB/s). Memmap reads go from seconds to milliseconds. This is the SINGLE BIGGEST hardware improvement.
- **Offline gain:** 5-10s saved per query at 700 GB, 20-40s at 2 TB
- **Online gain:** Same improvement for retrieval stage

### #2. Upgrade GPU to 24 GB VRAM (RTX 4090 / A5000)
- **Cost:** $1,200-2,000
- **Impact:** Enables qwen3:32b (much better quality), 2x faster token generation, and model stays in VRAM without swapping. Also enables batch inference for 2-3 concurrent GPU users.
- **Offline gain:** 2-3x faster inference, better answer quality
- **Online gain:** No change (cloud GPU already fast)

### #3. Add request queuing with priority (software change)
- **Cost:** Free (code change)
- **Impact:** FastAPI backend with asyncio queue. Prevents GPU starvation. Priority queue lets urgent queries skip ahead. Shows estimated wait time in UI.
- **Offline gain:** Better UX, not faster raw throughput
- **Online gain:** Prevents rate limit errors under burst load

### #4. Enable embedding cache (query-level caching)
- **Cost:** Free (code change)
- **Impact:** Cache recent query embeddings + search results. If users ask similar questions, skip retrieval entirely. 80% cache hit rate for teams asking related questions about same documents.
- **Offline gain:** Retrieval drops to ~0ms for cached queries
- **Online gain:** Same benefit for retrieval stage

### #5. Switch to FAISS or Hnswlib for vector search
- **Cost:** Free (code change, adds dependency)
- **Impact:** Replace brute-force memmap scan with approximate nearest neighbor (ANN) index. Searches 8M chunks in <50ms instead of seconds. Critical for 2 TB scale.
- **Offline gain:** Vector search drops from seconds to <50ms
- **Online gain:** Same benefit

### #6. Use vLLM instead of Ollama for multi-user serving
- **Cost:** Free (Apache 2.0), but more complex setup
- **Impact:** vLLM supports continuous batching -- processes multiple requests on GPU simultaneously instead of queuing them. 10 users get near-single-user speed. Requires Linux or WSL2.
- **Offline gain:** 3-5x throughput improvement at 10 concurrent users
- **Online gain:** N/A (already using cloud batching)

### #7. Add second GPU (multi-GPU inference)
- **Cost:** $800-2,000
- **Impact:** Two 12 GB GPUs can serve two models simultaneously, halving queue wait. Or one 24 GB model via tensor parallel.
- **Offline gain:** 2x concurrent throughput
- **Online gain:** No change

### #8. Precompute common queries (scheduled batch)
- **Cost:** Free (code change)
- **Impact:** Run top-50 anticipated queries overnight, cache results. Morning users get instant answers for common questions.
- **Offline gain:** Instant for precomputed queries
- **Online gain:** Same benefit, also saves API cost

---
*Generated by stress_test_workstation_simulation.py*