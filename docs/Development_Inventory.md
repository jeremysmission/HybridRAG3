# Development Inventory -- HybridRAG3

**Date:** 2026-03-05  
**Status:** Current design baseline

---

## Tier 1 -- Approved and Wired (Current Baseline)

### Runtime and Core Stack

| Component | Version/State | Notes |
|---|---|---|
| Python | 3.11/3.12 supported | Windows 10/11 baseline |
| openai | 1.109.1 | Pinned v1.x SDK |
| FastAPI + Uvicorn | 0.115.0 + 0.41.0 | REST API path enabled |
| SQLite + memmap | Active | Hybrid retrieval store |
| Ollama | Active default backend | Offline-first inference |

### Retrieval and Security

| Area | Current State |
|---|---|
| Retrieval | Hybrid BM25 + vector RRF (`retrieval.top_k`, `rrf_k`) |
| Offline latency cap | `retrieval.offline_top_k` available and wired |
| PII scrubber | Enabled by default (`security.pii_sanitization: true`) for online path |
| Credential handling | Windows Credential Manager (DPAPI via `keyring`) |
| Network gate | Offline-safe controls in startup + router layers |

### Role Routing ("Subagents")

HybridRAG3 currently routes by **9 use-case profiles**, including:

- **8 deployed work-role subagents:** `sw`, `eng`, `sys`, `draft`, `log`, `pm`, `fe`, `cyber`
- **1 general profile:** `gen`

Source of truth: `scripts/_model_meta.py` (`USE_CASES` with `work_only` flags).

### Offline Models (Approved Stack)

| Model | Purpose |
|---|---|
| `phi4:14b-q4_K_M` | Primary workstation reasoning |
| `mistral-nemo:12b` | Alternate / general-heavy profile |
| `phi4-mini` | Laptop fallback |
| `mistral:7b` | Alternate fallback |
| `gemma3:4b` | PM-style fast fallback |

### Parser Coverage

Extended parser dependency set is present in baseline requirements for:

- `.doc`, `.msg`, `.dxf`, `.evtx`, `.pcap`, `.psd`, `.rtf`, `.stl`, `.vsdx`
- OCR path with `pytesseract`, `pdf2image`, optional `ocrmypdf`

---

## Tier 2 -- Designed In, Disabled by Default

| Component | State | Activation Requirement |
|---|---|---|
| vLLM router path | Implemented | Install/approve `vllm`, enable `vllm.enabled: true`, provision workstation |
| Transformers direct backend | Schema retained, feature off | Additional model/runtime approvals |
| FAISS acceleration | Planned dependency | Approval + integration decision |

Notes:
- vLLM code path exists in `src/core/llm_router.py` and startup checks.
- Baseline deployments continue to use Ollama-first routing.

---

## Tier 3 -- Planned / Governance Backlog

- Multi-user tenancy and auth hardening for shared API usage
- Table-structure extraction improvements for complex PDFs
- Semantic chunking strategy beyond fixed-size chunk windows
- Scale-out database strategy beyond single-user SQLite deployment

---

## Dependency Manifest Alignment

Canonical manifests:

- `requirements.txt` (full project baseline)
- `requirements_approved.txt` (enterprise approval posture)

Both currently pin `openai==1.109.1`.

---

## Verification Snapshot

- Latest recorded full-suite baseline in handoff context: `116 passed, 0 failed` (2026-03-04 run profile).
- Additional targeted verification should be run after any runtime code changes.

