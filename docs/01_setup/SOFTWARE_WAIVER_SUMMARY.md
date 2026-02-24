# Software Waiver Request Summary

**Date:** 2026-02-24
**Project:** HybridRAG v3 -- Offline-First RAG System
**Requested By:** Jeremy Randa

---

## Purpose

This document summarizes all software packages requiring enterprise
waiver/approval for the HybridRAG v3 knowledge retrieval system. The
system is designed for offline-first operation with zero telemetry and
no external data transmission.

---

## Currently Approved & Installed (No Waiver Needed)

These are already installed and working. Listed for reference so the
enterprise team can see the full stack.

| Package | Version | License | Origin | Purpose |
|---------|---------|---------|--------|---------|
| Python | 3.12rc3 | PSF-2.0 | Python.org/USA | Runtime |
| pip | 26.0.1 | MIT | PyPA/USA | Package installer |
| pip-system-certs | latest | MIT | PyPA/USA | Enterprise SSL cert integration |
| torch | 2.10.0 | BSD-3 | Meta/USA | Tensor computation (CPU-only) |
| numpy | 1.26.4 | BSD-3 | NumFOCUS/USA | Vector math |
| scipy | 1.17.0 | BSD-3 | NumFOCUS/USA | Scientific computing |
| scikit-learn | 1.8.0 | BSD-3 | INRIA/France | ML scoring |
| sentence-transformers | 2.7.0 | Apache 2.0 | UKP Lab/Germany | Embedding model |
| transformers | 4.57.6 | Apache 2.0 | HuggingFace/USA | Model loading |
| tokenizers | 0.22.2 | Apache 2.0 | HuggingFace/USA | Tokenization |
| huggingface_hub | 0.36.1 | Apache 2.0 | HuggingFace/USA | One-time model download |
| safetensors | 0.7.0 | Apache 2.0 | HuggingFace/USA | Safe model loading |
| tiktoken | 0.8.0 | MIT | OpenAI/USA | Token counting |
| openai | 1.45.1 | MIT | OpenAI/USA | API client |
| httpx | 0.28.1 | BSD-3 | Encode/UK | HTTP client |
| requests | 2.32.5 | Apache 2.0 | PSF/USA | HTTP client |
| urllib3 | 2.6.3 | MIT | PSF/USA | HTTP internals |
| pydantic | 2.11.1 | MIT | Pydantic/USA | Data validation |
| pyyaml | 6.0.2 | MIT | YAML/USA | Config parsing |
| cryptography | 44.0.2 | Apache 2.0 | PyCA/USA | Credential encryption |
| fastapi | 0.115.0 | MIT | Tiangolo/USA | REST API |
| uvicorn | 0.41.0 | BSD-3 | Encode/UK | API server |
| starlette | 0.38.6 | BSD-3 | Encode/UK | HTTP toolkit |
| structlog | 24.4.0 | MIT | Hynek/Germany | Logging |
| pdfplumber | 0.11.9 | MIT | USA | PDF extraction |
| pypdf | 6.6.2 | BSD-3 | USA | PDF parsing |
| python-docx | 1.2.0 | MIT | USA | Word documents |
| python-pptx | 1.0.2 | MIT | USA | PowerPoint |
| openpyxl | 3.1.5 | MIT | USA | Excel reading |
| xlsxwriter | 3.2.9 | BSD-2 | USA | Excel writing |
| lxml | 6.0.2 | BSD-3 | USA | XML parsing |
| pillow | 12.1.0 | HPND | USA | Image processing |
| rich | 13.9.4 | MIT | USA | Console display |
| tqdm | 4.67.3 | MIT | USA | Progress bars |
| regex | 2026.1.15 | Apache 2.0 | USA | Text processing |
| colorama | 0.4.6 | BSD-3 | USA | Console colors |

**Total: 35 packages, all open-source, all USA/EU/Allied origin**

---

## Waiver Request 1: Ollama (Offline LLM Server)

| Field | Detail |
|-------|--------|
| Software | Ollama |
| Version | Latest stable |
| License | MIT |
| Publisher | Ollama Inc. / USA |
| Purpose | Run AI language models locally -- no cloud, no internet required |
| Data Flow | localhost only (127.0.0.1:11434), never contacts external servers |
| Network | Zero outbound connections during operation |
| Justification | Enables fully offline AI-powered document search and Q&A |

### Models to Run on Ollama

| Model | Size | License | Publisher | Purpose |
|-------|------|---------|-----------|---------|
| phi4-mini | 2.3 GB | MIT | Microsoft/USA | Primary Q&A model |
| mistral:7b | 4.1 GB | Apache 2.0 | Mistral AI/France | Engineering alternate |
| phi4:14b-q4_K_M | 9.1 GB | MIT | Microsoft/USA | High-accuracy model |
| gemma3:4b | 3.3 GB | Apache 2.0 | Google/USA | Fast summarization |
| mistral-nemo:12b | 7.1 GB | Apache 2.0 | Mistral+NVIDIA | Long documents (128K) |

**All models:** open-source, USA/EU origin, no NDAA-restricted publishers.

---

## Waiver Request 2: vLLM + OpenAI SDK Upgrade (Future -- Workstation)

**IMPORTANT:** These two packages must be approved together. vLLM
depends on openai>=1.99.1 and cannot install without it.

| Field | Detail |
|-------|--------|
| Package 1 | vllm==0.10.1 |
| License | Apache 2.0 |
| Publisher | UC Berkeley / USA |
| Purpose | GPU-optimized model serving with batching and caching |
| Requirement | Dual RTX 3090 workstation (on order) |
| Package 2 | openai>=1.99.1 (upgrade from current 1.45.1) |
| License | MIT |
| Publisher | OpenAI / USA |
| Purpose | Required dependency for vLLM; API client for cloud models |
| Impact | Code changes needed to migrate from openai 1.x to 2.x API |
| Timeline | Not needed until workstation hardware arrives |

---

## Waiver Request 3: FAISS Vector Search (Future -- Workstation)

| Field | Detail |
|-------|--------|
| Package | faiss-cpu==1.9.0 |
| License | MIT |
| Publisher | Meta AI Research / USA |
| Purpose | Fast vector similarity search (10-100x faster than current SQLite) |
| Note | Library is MIT-licensed; does not include any AI models |
| Timeline | After workstation arrives; current system works without it |

---

## Waiver Request 4: AI Use Case Registration

| Field | Detail |
|-------|--------|
| System Name | HybridRAG v3 |
| Type | Retrieval-Augmented Generation (RAG) |
| Function | Searches indexed documents and generates answers using AI |
| Data Scope | Internal project documents only (no PII, no customer data) |
| AI Models | See Ollama models above (all run locally, no cloud) |
| Online Mode | Optional -- routes through approved API endpoint only |
| User Count | Single-user (no multi-tenant) |
| Network | Offline by default; online mode uses one configurable endpoint |
| Telemetry | Zero -- all telemetry disabled (HF_HUB_DISABLE_TELEMETRY=1) |
| Data Storage | Local only (SQLite + flat files on local disk) |
| Credentials | Windows Credential Manager (OS-level DPAPI encryption) |

---

## Excluded Software (Compliance Reference)

The following were evaluated and explicitly rejected:

| Software | Publisher | Reason for Rejection |
|----------|-----------|---------------------|
| Qwen (all) | Alibaba/China | NDAA restricted entity |
| DeepSeek (all) | DeepSeek/China | NDAA restricted entity |
| BGE embeddings | BAAI/China | NDAA restricted entity |
| Llama (all) | Meta/USA | AUP restricts weapons/military use |
| LangChain | LangChain Inc | 200+ dependencies, version instability |
| ChromaDB | Chroma | Windows compatibility issues |
| PyMuPDF | Artifex | AGPL copyleft license |

---

## Enterprise SSL Setup (Already Resolved)

The work laptop uses `pip-system-certs` to integrate with the
corporate proxy certificate chain. This was installed using a one-time
`--trusted-host` bootstrap and now all pip operations use full SSL
verification through the Windows certificate store. No security
bypass is in place.

---

## Contact

For technical questions about any package, its data flow, or security
posture, contact the project developer.
