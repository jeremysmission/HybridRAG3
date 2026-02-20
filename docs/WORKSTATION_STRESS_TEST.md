# Workstation Stress Test Simulation Results

**Date:** 2026-02-20T15:43:07.463803

## Hardware Profile

| Component | Spec |
|-----------|------|
| CPU | 32 threads |
| RAM | 128 GB |
| GPU | 2x RTX 3090 FE (NVLink) (48 GB VRAM) |
| Storage | 2 TB NVMe SSD (5000 MB/s) |

## Index Profile

| Metric | 700 GB Source | 2 TB Source |
|--------|---------------|-------------|
| Chunks | 8,400,000 | 24,000,000 |
| Embeddings | 6.45 GB | 18.43 GB |
| SQLite DB | 4.20 GB | 12.00 GB |

## Offline/Ollama (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 16.9s | 18.5s | Good |
| 8 | 1.4s | 14.1s | 15.5s | Good |
| 6 | 1.2s | 11.3s | 12.4s | Good |
| 4 | 1.0s | 8.4s | 9.4s | Excellent |
| 3 | 1.0s | 7.0s | 8.0s | Excellent |
| 2 | 1.0s | 5.6s | 6.6s | Excellent |

## Offline/Ollama (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 29.2s | 30.8s | Acceptable |
| 8 | 1.4s | 24.3s | 25.7s | Acceptable |
| 6 | 1.2s | 19.5s | 20.7s | Acceptable |
| 4 | 1.0s | 14.6s | 15.6s | Good |
| 3 | 1.0s | 12.2s | 13.1s | Good |
| 2 | 1.0s | 9.7s | 10.7s | Good |

## vLLM Server (qwen3:8b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 10.2s | 11.8s | Good |
| 8 | 1.4s | 9.1s | 10.5s | Good |
| 6 | 1.2s | 7.8s | 9.0s | Excellent |
| 4 | 1.0s | 6.4s | 7.4s | Excellent |
| 3 | 1.0s | 5.8s | 6.8s | Excellent |
| 2 | 1.0s | 5.1s | 6.1s | Excellent |

## vLLM Server (phi4:14b) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 17.6s | 19.2s | Good |
| 8 | 1.4s | 15.1s | 16.5s | Good |
| 6 | 1.2s | 12.6s | 13.7s | Good |
| 4 | 1.0s | 10.0s | 11.0s | Good |
| 3 | 1.0s | 9.0s | 10.0s | Excellent |
| 2 | 1.0s | 8.0s | 8.9s | Excellent |

## Online (gpt-4o) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 6.5s | 8.1s | Excellent |
| 8 | 1.4s | 6.2s | 7.6s | Excellent |
| 6 | 1.2s | 6.2s | 7.4s | Excellent |
| 4 | 1.0s | 5.9s | 6.9s | Excellent |
| 3 | 1.0s | 5.9s | 6.9s | Excellent |
| 2 | 1.0s | 5.9s | 6.9s | Excellent |

## Online (gpt-4o-mini) -- 700 GB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 1.6s | 4.2s | 5.8s | Excellent |
| 8 | 1.4s | 4.0s | 5.4s | Excellent |
| 6 | 1.2s | 4.0s | 5.2s | Excellent |
| 4 | 1.0s | 3.8s | 4.8s | Excellent |
| 3 | 1.0s | 3.8s | 4.8s | Excellent |
| 2 | 1.0s | 3.8s | 4.8s | Excellent |

## Offline/Ollama (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.0s | 16.9s | 19.9s | Good |
| 8 | 2.7s | 14.1s | 16.8s | Good |
| 6 | 2.4s | 11.3s | 13.6s | Good |
| 4 | 2.1s | 8.4s | 10.5s | Good |
| 3 | 2.0s | 7.0s | 9.1s | Excellent |
| 2 | 2.0s | 5.6s | 7.7s | Excellent |

## vLLM Server (qwen3:8b) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.0s | 10.2s | 13.2s | Good |
| 8 | 2.7s | 9.1s | 11.8s | Good |
| 6 | 2.4s | 7.8s | 10.1s | Good |
| 4 | 2.1s | 6.4s | 8.5s | Excellent |
| 3 | 2.0s | 5.8s | 7.8s | Excellent |
| 2 | 2.0s | 5.1s | 7.1s | Excellent |

## Online (gpt-4o) -- 2 TB

| Users | Retrieval | LLM | Total | Rating |
|-------|-----------|-----|-------|--------|
| 10 | 3.0s | 6.5s | 9.5s | Excellent |
| 8 | 2.7s | 6.2s | 8.9s | Excellent |
| 6 | 2.4s | 6.2s | 8.5s | Excellent |
| 4 | 2.1s | 5.9s | 7.9s | Excellent |
| 3 | 2.0s | 5.9s | 7.9s | Excellent |
| 2 | 2.0s | 5.9s | 7.9s | Excellent |

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