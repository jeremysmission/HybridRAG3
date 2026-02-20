# Workstation Stress Test Simulation Results

**Date:** 2026-02-20T15:20:07.283095

## Hardware Profile

| Component | Spec |
|-----------|------|
| CPU | 16 threads |
| RAM | 64 GB |
| GPU | NVIDIA 12GB (12 GB VRAM) |
| Storage | 2 TB NVMe SSD (3500 MB/s) |

## Index Profile

| Metric | 700 GB Source | 2 TB Source |
|--------|---------------|-------------|
| Chunks | 8,400,000 | 24,000,000 |
| Embeddings | 6.45 GB | 18.43 GB |
| SQLite DB | 4.20 GB | 12.00 GB |

## Offline/Ollama (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 114.6s | 116.4s | Poor |
| 8 | 1.6s | 93.8s | 95.3s | Poor |
| 6 | 1.4s | 72.9s | 74.3s | Slow |
| 4 | 1.2s | 52.1s | 53.2s | Slow |
| 3 | 1.2s | 41.7s | 42.8s | Acceptable |
| 2 | 1.1s | 31.3s | 32.4s | Acceptable |

## Offline/Ollama (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 198.2s | 199.9s | Unusable |
| 8 | 1.6s | 162.1s | 163.7s | Poor |
| 6 | 1.4s | 126.1s | 127.5s | Poor |
| 4 | 1.2s | 90.1s | 91.2s | Poor |
| 3 | 1.2s | 72.1s | 73.2s | Slow |
| 2 | 1.1s | 54.0s | 55.2s | Slow |

## vLLM Server (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 21.1s | 22.9s | Acceptable |
| 8 | 1.6s | 18.1s | 19.7s | Good |
| 6 | 1.4s | 15.1s | 16.5s | Good |
| 4 | 1.2s | 12.1s | 13.2s | Good |
| 3 | 1.2s | 10.8s | 12.0s | Good |
| 2 | 1.1s | 9.6s | 10.7s | Good |

## vLLM Server (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 53.5s | 55.3s | Slow |
| 8 | 1.6s | 44.6s | 46.2s | Slow |
| 6 | 1.4s | 35.7s | 37.0s | Acceptable |
| 4 | 1.2s | 26.8s | 27.9s | Acceptable |
| 3 | 1.2s | 22.3s | 23.5s | Acceptable |
| 2 | 1.1s | 17.8s | 19.0s | Good |

## Online (gpt-4o) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 6.5s | 8.3s | Excellent |
| 8 | 1.6s | 6.2s | 7.7s | Excellent |
| 6 | 1.4s | 6.2s | 7.5s | Excellent |
| 4 | 1.2s | 5.9s | 7.0s | Excellent |
| 3 | 1.2s | 5.9s | 7.0s | Excellent |
| 2 | 1.1s | 5.9s | 7.0s | Excellent |

## Online (gpt-4o-mini) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.8s | 4.2s | 6.0s | Excellent |
| 8 | 1.6s | 4.0s | 5.6s | Excellent |
| 6 | 1.4s | 4.0s | 5.4s | Excellent |
| 4 | 1.2s | 3.8s | 5.0s | Excellent |
| 3 | 1.2s | 3.8s | 5.0s | Excellent |
| 2 | 1.1s | 3.8s | 5.0s | Excellent |

## Offline/Ollama (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.5s | 114.6s | 118.1s | Poor |
| 8 | 3.2s | 93.8s | 97.0s | Poor |
| 6 | 2.9s | 72.9s | 75.8s | Slow |
| 4 | 2.6s | 52.1s | 54.6s | Slow |
| 3 | 2.5s | 41.7s | 44.2s | Acceptable |
| 2 | 2.5s | 31.3s | 33.8s | Acceptable |

## vLLM Server (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.5s | 21.1s | 24.7s | Acceptable |
| 8 | 3.2s | 18.1s | 21.3s | Acceptable |
| 6 | 2.9s | 15.1s | 18.0s | Good |
| 4 | 2.6s | 12.1s | 14.6s | Good |
| 3 | 2.5s | 10.8s | 13.4s | Good |
| 2 | 2.5s | 9.6s | 12.1s | Good |

## Online (gpt-4o) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.5s | 6.5s | 10.0s | Excellent |
| 8 | 3.2s | 6.2s | 9.4s | Excellent |
| 6 | 2.9s | 6.2s | 9.1s | Excellent |
| 4 | 2.6s | 5.9s | 8.4s | Excellent |
| 3 | 2.5s | 5.9s | 8.4s | Excellent |
| 2 | 2.5s | 5.9s | 8.4s | Excellent |

## Improvement Recommendations

### #1. Replace Ollama with vLLM (Docker or bare metal)
- **Cost:** Free (Apache 2.0 license)
- **Impact:** BIGGEST win for multi-user offline. vLLM continuous batching processes multiple GPU requests simultaneously instead of queuing serially. Docker setup: one command. Requires Linux or WSL2 for GPU passthrough.
- **Offline gain:** 3-5x throughput at 10 concurrent users
- **Online gain:** N/A (already using cloud batching)

### #2. Switch to FAISS or Hnswlib for vector search
- **Cost:** Free (code change, adds dependency)
- **Impact:** Replace brute-force memmap scan with approximate nearest neighbor (ANN) index. Searches 8M chunks in <50ms instead of 1-2s. Critical for scaling to 2 TB. faiss-cpu is BSD licensed, hnswlib is Apache.
- **Offline gain:** Vector search drops from ~1.3s to <50ms
- **Online gain:** Same benefit for retrieval stage

### #3. Enable embedding cache (query-level caching)
- **Cost:** Free (code change)
- **Impact:** Cache recent query embeddings + search results. If users ask similar questions, skip retrieval entirely. 80% cache hit rate for teams asking related questions about same documents.
- **Offline gain:** Retrieval drops to ~0ms for cached queries
- **Online gain:** Same benefit for retrieval stage

### #4. Upgrade GPU to 24 GB VRAM (RTX 4090 / A5000)
- **Cost:** $1,200-2,000
- **Impact:** Enables qwen3:32b (much better quality), 2x faster token generation, and model stays in VRAM without swapping. More VRAM also means vLLM can batch more concurrent requests.
- **Offline gain:** 2-3x faster inference, better answer quality
- **Online gain:** No change (cloud GPU already fast)

### #5. Add request queuing with priority (software change)
- **Cost:** Free (code change)
- **Impact:** FastAPI backend with asyncio queue. Prevents GPU starvation. Priority queue lets urgent queries skip ahead. Shows estimated wait time in UI.
- **Offline gain:** Better UX, not faster raw throughput
- **Online gain:** Prevents rate limit errors under burst load

### #6. Precompute common queries (scheduled batch)
- **Cost:** Free (code change)
- **Impact:** Run top-50 anticipated queries overnight, cache results. Morning users get instant answers for common questions.
- **Offline gain:** Instant for precomputed queries
- **Online gain:** Same benefit, also saves API cost

### #7. Add second GPU (multi-GPU inference)
- **Cost:** $800-2,000
- **Impact:** Two 12 GB GPUs can serve two models simultaneously, halving queue wait. Or one 24 GB model via tensor parallel. vLLM supports tensor parallel natively.
- **Offline gain:** 2x concurrent throughput
- **Online gain:** No change

### #8. Dedicated inference server (separate machine)
- **Cost:** $2,000-5,000 (used workstation with GPU)
- **Impact:** Offload all LLM inference to a separate machine on LAN. Main workstation handles only retrieval. Both machines work at full speed without competing for resources.
- **Offline gain:** Near-online-mode speed for local inference
- **Online gain:** N/A

---
*Generated by stress_test_workstation_simulation.py*