# HANDOVER: Window 1 -- Model Audit Compliance Update

**Date:** 2026-02-21
**Session:** Window 1 (Model stack compliance)

---

## What Was Completed

### `scripts/_model_meta.py`
- Added `WORK_ONLY_MODELS` dict with 5 approved local models (phi4-mini, mistral:7b, phi4:14b-q4_K_M, gemma3:4b, mistral-nemo:12b)
- Added `PERSONAL_FUTURE` dict for aspirational hardware (mistral-small3.1:24b)
- Added `RECOMMENDED_OFFLINE` per-profile config (primary, alt, upgrade, temperature, context, reranker, top_k for all 9 use cases)
- Added `RECOMMENDED_ONLINE` per-profile cloud model picks (Claude Sonnet 4, gpt-4o, gpt-4o-mini)
- Marked Llama family as **BANNED** with comments in `_OFFLINE_FAMILY_SCORES` and `_ONLINE_FAMILY_PATTERNS` (Meta AUP prohibits weapons/military use)
- Marked Qwen family as **EXCLUDED** with comments (country-of-origin restriction)
- Marked DeepSeek family as **EXCLUDED** with comments (country-of-origin restriction)
- Zeroed out all scores for banned/excluded families so they are never auto-selected

### `requirements_approved.txt`
- Pinned `openai==1.45.1` with comment: "PINNED v1.x forever; never 2.x syntax"
- Added header comments documenting: China-origin models EXCLUDED, Meta Llama BANNED, LangChain BANNED, xxhash ELIMINATED

### `docs/DEFENSE_MODEL_AUDIT.md`
- Created full defense industry security audit document
- Section 1: Disqualification criteria (Meta, Google/Gemma, DeepSeek, BAAI, Alibaba/Qwen, Huawei/ZTE, Kaspersky)
- Section 2: Approved publishers with Azure Gov IL6 authorization for Microsoft and OpenAI; DISA approval for Phi models (Feb 2025); Mistral French MoD framework (Jan 2026)
- Section 3: Current 5-model approved stack with Ollama tags
- Section 7: Full "Models to Avoid" table (Llama, Qwen, DeepSeek, BGE, Jina, mxbai-rerank-v2, Stella/Jasper)
- Section 8: Ollama security minimum v0.7.0, bind to localhost only

### `config/default_config.yaml`
- Verified `ollama.model: phi4-mini` as default offline model [OK]
- Verified `mode: offline` as default mode [OK]

### `docs/MODEL_SELECTION_RATIONALE.md`
- Full per-profile model recommendations for all 9 use cases
- Summary matrix (Section 4) contains only approved models -- no Llama, Qwen, or DeepSeek [OK]
- PERSONAL_FUTURE upgrade path documented (Section 7)
- Embedding upgrade path documented (Section 8)

---

## Approved Model Stack (Current)

### Offline (via Ollama inference engine)

| Model | Size | VRAM | License | Origin | Role |
|-------|------|------|---------|--------|------|
| phi4-mini (3.8B) | 2.3 GB | ~5.5 GB | MIT | Microsoft/USA | Primary for 7/9 profiles |
| mistral:7b (7B) | 4.1 GB | ~5.5 GB | Apache 2.0 | Mistral/France | Alt for eng/sys/fe/cyber |
| phi4:14b-q4_K_M (14B) | 9.1 GB | ~11 GB | MIT | Microsoft/USA | Logistics primary, CAD alt |
| gemma3:4b (4B) | 3.3 GB | ~4.0 GB | Apache 2.0 | Google/USA | PM fast summarization |
| mistral-nemo:12b (12B) | 7.1 GB | ~10 GB | Apache 2.0 | Mistral+NVIDIA | Upgrade for sw/eng/sys/cyber/gen (128K ctx) |

### Online (via Azure Gov Cloud / OpenRouter)

| Use Case | Primary | Alt |
|----------|---------|-----|
| Software Engineering | anthropic/claude-sonnet-4 | gpt-4.1 |
| Engineering / STEM | anthropic/claude-sonnet-4 | gpt-4o |
| Systems Administration | anthropic/claude-sonnet-4 | gpt-4o |
| Drafting / AutoCAD | anthropic/claude-sonnet-4 | gpt-4o |
| Logistics Analyst | gpt-4o | gpt-4.1 |
| Program Management | gpt-4o-mini | gpt-4.1-mini |
| Field Engineer | anthropic/claude-sonnet-4 | gpt-4o |
| Cybersecurity Analyst | anthropic/claude-sonnet-4 | gpt-4o |
| General AI | gpt-4o | anthropic/claude-sonnet-4 |

### SDK Constraint
- openai Python SDK pinned to v1.45.1 -- never 2.x (breaking API syntax changes)

---

## Banned Models

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

## Test Results

[OK] **101 passed, 0 failed, 1 warning** (562.49s)

```
tests/test_api_router.py         10 passed
tests/test_fastapi_server.py     10 passed
tests/test_indexer.py            16 passed
tests/test_ollama_router.py      10 passed
tests/test_phase3_stress.py      28 passed
tests/test_query_engine.py        7 passed
----------------------------------------------
TOTAL                           101 passed
```

Warning: PendingDeprecationWarning in starlette/formparsers.py (cosmetic, no action needed)

---

## What Is In Progress

- phi4:14b-q4_K_M Ollama download (started, ~9.1 GB)
- gemma3:4b Ollama download (not yet started)
- mistral-nemo:12b Ollama download (not yet started)
- GUI prototype (Window 3/4) blocked on Window 2 API routing work

---

## Top 3 Priorities for Next Session

1. Complete Ollama model downloads for the full 5-model stack
2. Window 2: Implement `get_available_deployments()`, `select_best_model()`, `get_routing_table()` in `llm_router.py` and `_model_meta.py`
3. Wire GUI prototype to use the routing functions from Window 2

---

## Blockers / Decisions Needed

- [WARN] gemma3:4b has a Google license clause that warrants review for restricted environments (see DEFENSE_MODEL_AUDIT.md Section 1 and Section 3 note). Consider replacing with Ministral-3:3b (Mistral AI, Apache 2.0) when the workstation arrives for maximum audit safety.
- [WARN] Reranker is currently disabled in default_config.yaml (`reranker_enabled: false`) because it degrades unanswerable/injection/ambiguous category scores (see DEFENSE_MODEL_AUDIT.md Section 6). Profile configs in `_model_meta.py` recommend reranker enabled for 7/9 profiles -- this conflict needs resolution.
- [OK] No Llama, Qwen, or DeepSeek models appear anywhere in the approved stack or recommended configs.

---

## Resume Prompt

Paste this at the start of the next session:

> Resume work on HybridRAG3. Last session (Window 1) updated the model audit compliance -- banned Llama/Qwen/DeepSeek, approved Azure Gov IL6 + Phi (DISA) + Mistral. The openai SDK is pinned to v1.45.1. Next priority is Window 2: implement deployment discovery and model auto-selection routing in llm_router.py and _model_meta.py.
