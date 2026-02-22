# Defense Industry Security Audit: AI Model Procurement Brief

## HybridRAG3 RAG Application -- Model Stack Assessment

**Date:** 2026-02-21
**Distribution:** Internal / Briefing Use
**Hardware targets:** Laptop (8GB RAM, 512MB VRAM) / Workstation (64GB RAM, 2x RTX 3090, 48GB VRAM)

---

## SECTION 1: DISQUALIFICATION CRITERIA

Before evaluating candidates, the following publishers/entities are **categorically disqualified**:

| Disqualified Entity | Reason | Regulation |
|---|---|---|
| **Meta / Facebook** | Llama license explicitly prohibits military use | License restriction |
| **Google / DeepMind** | Gemma license contains remote kill switch clause | License restriction |
| **DeepSeek** | Chinese CCP-linked entity; Pentagon banned Jan 2025; NIST found 12x higher malicious instruction compliance vs US models; proposed federal ban | NDAA / national security |
| **BAAI (Beijing Academy of AI)** | Added to US Entity List March 2025 by Commerce Dept BIS for developing military technology; Chinese government-funded | Entity List / NDAA Sec 889 analog |
| **Alibaba / Qwen** | Pentagon weighing addition to 1260H military-linked entity list (Feb 2026); White House memo alleges helping Chinese military target US | NDAA 1260H / national security |
| **Huawei / ZTE / Hikvision / Dahua / Hytera** | Explicitly named in NDAA Section 889(a)(1)(A) | NDAA Sec 889 |
| **Kaspersky** | Banned from all US Government use (FY2018 NDAA) | FAR 52.204-23 |

**Critical finding:** This disqualifies **all BGE models** (BAAI), **all Qwen models** (Alibaba), **all DeepSeek models**, **all Gemma models** (Google), and **all Llama models** (Meta). Also disqualifies **Stella embeddings** (based on Alibaba GTE architecture) and **mxbai-rerank-v2** (based on Qwen-2.5 architecture -- Alibaba dependency).

---

## SECTION 2: APPROVED PUBLISHERS

| Publisher | HQ Country | Alliance Status | License Model | Risk Level |
|---|---|---|---|---|
| **Microsoft (Azure Gov)** | Redmond, WA, USA | Domestic / Azure Gov IL6 authorized; Phi models DISA-approved Feb 2025 | MIT | LOW |
| **OpenAI (via Azure Gov)** | San Francisco, CA, USA | Domestic / Azure Gov IL6 authorized | Proprietary | LOW |
| **Mistral AI** | Paris, France | NATO ally; French MoD framework agreement (Jan 2026) | Apache 2.0 | LOW |
| **TII (Technology Innovation Institute)** | Abu Dhabi, UAE | US cooperation partner; Dassault Aviation partnership | Apache 2.0 (Falcon License) | LOW-MEDIUM |
| **Snowflake** | Bozeman, MT, USA | DoD IL5 authorized; ITAR compliant; FedRAMP Moderate | Apache 2.0 | LOW |
| **Nomic AI** | New York, NY, USA | Domestic | Apache 2.0 | LOW |
| **Mixedbread AI** | Berlin, Germany | NATO ally | Apache 2.0 (v1 models only*) | LOW |

*Note: Mixedbread mxbai-rerank-v2 and mxbai-embed-v2 are built on Qwen-2.5 architecture (Alibaba). Only v1 models (based on BERT architecture) are clear of Chinese supply chain concerns.

**SDK Constraint:** openai Python SDK PINNED to v1.45.1. Never upgrade to 2.x (breaking API syntax changes).

---

## SECTION 3: CURRENT APPROVED STACK (5 Models)

| Model | Size | License | Origin | Primary For | Ollama Tag |
|-------|------|---------|--------|-------------|------------|
| phi4-mini (3.8B) | 2.3 GB | MIT | Microsoft/USA | 7/9 profiles | `phi4-mini` |
| mistral:7b (7B) | 4.1 GB | Apache 2.0 | Mistral/France | eng/sys/fe/cyber alt | `mistral:7b` |
| phi4:14b-q4_K_M (14B) | 9.1 GB | MIT | Microsoft/USA | logistics primary, CAD alt | `phi4:14b-q4_K_M` |
| gemma3:4b (4B) | 3.3 GB | Apache 2.0 | Google/USA | PM fast summarization | `gemma3:4b` |
| mistral-nemo:12b (12B) | 7.1 GB | Apache 2.0 | Mistral+NVIDIA | upgrade for sw/eng/sys/cyber/gen | `mistral-nemo:12b` |

**NOTE on gemma3:4b:** Google Gemma has a license clause that warrants review for restricted environments. The 4B model is currently approved for PM summarization only. For maximum audit safety, consider replacing with Ministral-3:3b (Mistral AI, Apache 2.0) when the workstation arrives.

---

## SECTION 4: WORKSTATION UPGRADE PATH

### Tier 1: 24 GB VRAM (single RTX 3090)

| Model | Size | VRAM | Publisher | License | Replaces |
|-------|------|------|-----------|---------|----------|
| Mistral Small 3 (24B) | ~16 GB | ~20 GB | Mistral AI (France) | Apache 2.0 | phi4-mini as primary |

### Tier 2: 48 GB VRAM (dual RTX 3090)

| Model | Size | VRAM | Publisher | License | Replaces |
|-------|------|------|-----------|---------|----------|
| Mistral Small 3 (24B) | ~16 GB | ~20 GB (GPU 1) | Mistral AI | Apache 2.0 | All profile primaries |
| Phi-4-reasoning (14B) | ~10 GB | ~10 GB (GPU 2) | Microsoft | MIT | Reasoning specialist |

---

## SECTION 5: EMBEDDING MODEL UPGRADE PATH

| Model | Dims | Size | Publisher | License | MTEB Avg | Status |
|-------|------|------|-----------|---------|----------|--------|
| all-MiniLM-L6-v2 (current) | 384 | 80MB | Microsoft | MIT | ~56 | APPROVED |
| nomic-embed-text v1.5 | 768 | 0.5GB | Nomic AI (USA) | Apache 2.0 | 62+ | RECOMMENDED upgrade |
| snowflake-arctic-embed-l-v2.0 | 1024 | ~1.1GB | Snowflake (USA) | Apache 2.0 | 65+ | Workstation tier |

**Note:** Embedding model changes require full re-indexing of all chunks.

---

## SECTION 6: RERANKER STATUS

| Model | Size | Publisher | License | Status |
|-------|------|-----------|---------|--------|
| cross-encoder/ms-marco-MiniLM-L-6-v2 (current) | ~80MB | Microsoft | MIT | APPROVED, currently disabled |
| FlashRank (ONNX) | ~4MB | Open source | Apache 2.0 | CPU-only lightweight alternative |
| mxbai-rerank-large-v1 | ~1.3GB | Mixedbread (Germany) | Apache 2.0 | v1 only (BERT-based, safe) |

**WARNING:** Reranker is disabled because it destroys unanswerable (100->76%), injection (100->46%), and ambiguous (100->82%) category scores.

---

## SECTION 7: MODELS TO AVOID

| Model | Publisher | Reason |
|-------|-----------|--------|
| **Llama 1/2/3.x (any size)** | **Meta (USA)** | **Meta Acceptable Use Policy explicitly prohibits weapons/military use** |
| Qwen 2.5/3 (any size) | Alibaba (China) | 1260H military-linked entity list candidate; country-of-origin restriction |
| DeepSeek R1/V3 (any) | DeepSeek (China) | Federal ban proposed; CCP data exfiltration; country-of-origin restriction |
| BGE-M3, bge-reranker | BAAI (China) | US Entity List since March 2025; country-of-origin restriction |
| Jina embeddings v3 | Jina AI (Germany) | CC BY-NC 4.0 -- non-commercial license |
| mxbai-rerank-v2 | Mixedbread (Germany) | Built on Qwen-2.5 (Alibaba architecture) |
| Stella/Jasper | Unknown | Built on Alibaba GTE architecture |
| Any Chinese-origin model | Various | Blanket country-of-origin restriction per organizational policy |

---

## SECTION 8: OLLAMA SECURITY

**Minimum version:** v0.7.0 or later (critical CVE patches)

Mitigations:
- Bind to localhost only (`OLLAMA_HOST=127.0.0.1`)
- Never expose API to network
- Only load models from official ollama.com/library
- Document version in security plan

---

## Sources

- NDAA Section 889 (Huawei Ban)
- BAAI US Entity List (March 2025)
- Pentagon 1260H military-linked entity list reviews
- Mistral AI French MoD framework agreement (Jan 2026)
- Snowflake DoD IL5 Authorization
- Ollama CVE history (oligo.security)
- CMMC 2.0 AI security framework
- HuggingFace Open LLM Leaderboard v2
- MTEB Embedding Benchmark
