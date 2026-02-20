# Workstation Stress Test Simulation Results

**Date:** 2026-02-20T15:34:22.115643

## Hardware Profile

| Component | Spec |
|-----------|------|
| CPU | 28 threads |
| RAM | 64 GB |
| GPU | RTX Blackwell Desktop 12GB (12 GB VRAM) |
| Storage | 2 TB NVMe SSD (7250 MB/s) |

## Index Profile

| Metric | 700 GB Source | 2 TB Source |
|--------|---------------|-------------|
| Chunks | 8,400,000 | 24,000,000 |
| Embeddings | 6.45 GB | 18.43 GB |
| SQLite DB | 4.20 GB | 12.00 GB |

## Offline/Ollama (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 45.8s | 47.3s | Slow |
| 8 | 1.3s | 37.5s | 38.8s | Acceptable |
| 6 | 1.1s | 29.2s | 30.2s | Acceptable |
| 4 | 0.9s | 20.8s | 21.7s | Acceptable |
| 3 | 0.9s | 16.7s | 17.5s | Good |
| 2 | 0.8s | 12.5s | 13.3s | Good |

## Offline/Ollama (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 79.3s | 80.7s | Slow |
| 8 | 1.3s | 64.9s | 66.1s | Slow |
| 6 | 1.1s | 50.4s | 51.5s | Slow |
| 4 | 0.9s | 36.0s | 36.9s | Acceptable |
| 3 | 0.9s | 28.8s | 29.7s | Acceptable |
| 2 | 0.8s | 21.6s | 22.5s | Acceptable |

## vLLM Server (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 13.0s | 14.5s | Good |
| 8 | 1.3s | 11.2s | 12.4s | Good |
| 6 | 1.1s | 9.3s | 10.4s | Good |
| 4 | 0.9s | 7.4s | 8.3s | Excellent |
| 3 | 0.9s | 6.7s | 7.5s | Excellent |
| 2 | 0.8s | 5.9s | 6.8s | Excellent |

## vLLM Server (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 29.2s | 30.6s | Acceptable |
| 8 | 1.3s | 24.3s | 25.6s | Acceptable |
| 6 | 1.1s | 19.4s | 20.5s | Acceptable |
| 4 | 0.9s | 14.6s | 15.4s | Good |
| 3 | 0.9s | 12.2s | 13.0s | Good |
| 2 | 0.8s | 9.7s | 10.6s | Good |

## Online (gpt-4o) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 6.5s | 7.9s | Excellent |
| 8 | 1.3s | 6.2s | 7.4s | Excellent |
| 6 | 1.1s | 6.2s | 7.2s | Excellent |
| 4 | 0.9s | 5.9s | 6.7s | Excellent |
| 3 | 0.9s | 5.9s | 6.7s | Excellent |
| 2 | 0.8s | 5.9s | 6.7s | Excellent |

## Online (gpt-4o-mini) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.5s | 4.2s | 5.7s | Excellent |
| 8 | 1.3s | 4.0s | 5.3s | Excellent |
| 6 | 1.1s | 4.0s | 5.1s | Excellent |
| 4 | 0.9s | 3.8s | 4.7s | Excellent |
| 3 | 0.9s | 3.8s | 4.7s | Excellent |
| 2 | 0.8s | 3.8s | 4.7s | Excellent |

## Offline/Ollama (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 2.6s | 45.8s | 48.4s | Slow |
| 8 | 2.3s | 37.5s | 39.8s | Acceptable |
| 6 | 2.0s | 29.2s | 31.2s | Acceptable |
| 4 | 1.7s | 20.8s | 22.5s | Acceptable |
| 3 | 1.7s | 16.7s | 18.3s | Good |
| 2 | 1.7s | 12.5s | 14.2s | Good |

## vLLM Server (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 2.6s | 13.0s | 15.6s | Good |
| 8 | 2.3s | 11.2s | 13.5s | Good |
| 6 | 2.0s | 9.3s | 11.3s | Good |
| 4 | 1.7s | 7.4s | 9.1s | Excellent |
| 3 | 1.7s | 6.7s | 8.4s | Excellent |
| 2 | 1.7s | 5.9s | 7.6s | Excellent |

## Online (gpt-4o) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 2.6s | 6.5s | 9.1s | Excellent |
| 8 | 2.3s | 6.2s | 8.5s | Excellent |
| 6 | 2.0s | 6.2s | 8.2s | Excellent |
| 4 | 1.7s | 5.9s | 7.6s | Excellent |
| 3 | 1.7s | 5.9s | 7.6s | Excellent |
| 2 | 1.7s | 5.9s | 7.6s | Excellent |

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