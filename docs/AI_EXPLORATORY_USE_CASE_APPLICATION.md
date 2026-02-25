# AI Exploratory Use Case -- Application Notes

| Field | Value |
|-------|-------|
| **Project Title** | HybridRAG -- Hybrid Retrieval-Augmented Generation for Engineering Program Data |
| **Use Case Category** | Exploratory / Prototype |
| **AI Technology Type** | Retrieval-Augmented Generation (RAG) -- information retrieval tool, not an autonomous agent |
| **Risk Tier (Self-Assessment)** | Low -- assists human decision-making, does not make autonomous decisions |
| **Deployment Scope** | Single-user desktop prototype; pilot planned for 5-10 engineers |
| **Data Classification** | Internal / program-specific engineering documents (unclassified) |
| **Network Posture** | Offline-first (localhost only by default); online mode adds one approved API endpoint. Designed to be adaptable for standalone offline AI use or corporate API-connected use. |
| **Submitted by** | Jeremy Randall, RF Field Engineer |
| **Accountable Owner** | Jeremy Randall |

---

## 1. Business Justification

### Primary Use Cases

1. **Research and information synthesis** -- Engineers ask natural-language questions and receive source-cited answers from program documents in seconds instead of hours.

2. **Trusted AI output** -- Every answer is constrained to retrieved source material and machine-verified against it, eliminating hallucination -- the primary barrier to AI adoption in engineering.

3. **Cross-document synthesis** -- Correlates information across specs, test reports, and procedures that would take hours to cross-reference manually.

4. **Onboarding acceleration** -- New engineers query the program knowledge base directly instead of waiting for tribal knowledge transfer.

5. **Audit-ready logging** -- Every question, answer, source citation, token cost, and latency is recorded automatically.

### The Problem

Engineering programs sit on thousands of documents -- specs, test reports, calibration guides, procedures, data sheets. The data exists. Finding it is the bottleneck. Industry research quantifies this:

- Workers spend **19% of their workday** searching for information -- nearly one full day per week (*1)
- Generative AI automates **60-70%** of information retrieval tasks (*2)
- AI-assisted retrieval recovers **50%+ of employee search time** (*3)

At median PM wages of $48.44/hr (*4), a 10-person team loses ~$4,800/week to manual search. The prototype includes a built-in ROI calculator tracking time saved, dollar value recovered, and net ROI per query in real time.

### Why RAG

RAG retrieves actual document passages and grounds AI answers in them. Unlike fine-tuning, no proprietary data is embedded in model weights. Unlike cloud AI, the data stays local. When a spec is revised, re-index and the system reflects the current version immediately -- no retraining, no ML team dependency.

**Sources:** *1 McKinsey 2012 | *2 McKinsey 2023 | *3 Bloomfire/HBR 2025 | *4 BLS OEWS May 2024

---

## 2. Architecture

### Philosophy

No framework wrappers, no hidden abstraction layers, no transitive dependency chains. Every module does one thing, stays under 500 lines, and can be read and replaced independently. This is the opposite of LangChain/LlamaIndex patchwork -- the system is maintainable because the components are clean.

### Design Principles

- **Portable** -- Runs on an 8 GB laptop or a dual-GPU workstation. Copy the folder, install deps, run.
- **Modular** -- Every component (parser, chunker, embedder, retriever, LLM router, hallucination guard) swappable independently.
- **Auditable** -- 34% documentation ratio (2x industry average), structured JSON logging, 400-question eval suite with locked scoring.
- **Secure** -- Boots offline with all outbound connections blocked. Network Gate enforces URL allowlist with full audit trail. No path for unauthorized data exfiltration.
- **Dual-mode** -- Offline LLM (zero cost, zero network) for batch indexing and routine queries. Online API for complex synthesis where capability justifies per-token cost. Same pipeline, same safeguards, seamless switching.
- **Scalable** -- Clean interfaces mean scaling is module swaps, not rewrites. FastAPI backend, vLLM GPU router, and FAISS indexing are already integrated or one-module changes.

---

## 3. System Block Diagrams

### Query Path

```
  User Question
       |
  [ EMBEDDER ] --> 768-dim vector (nomic-embed-text via Ollama)
       |
  [ RETRIEVER ] --> Hybrid: vector (semantic) + BM25 (keyword) merged via RRF
       |
  [ PROMPT BUILDER ] --> 9-rule source-bounded template
       |
  [ LLM ROUTER ] --> Offline (Ollama/vLLM) or Online (approved API)
       |
  [ HALLUCINATION GUARD ] --> Claim extraction + NLI verification + scoring
       |
  Answer + source citations + cost
```

### Indexing Path

```
  Source Documents (49 supported formats)
       |
  [ PARSER REGISTRY ] --> Isolated per-format parsers
       |
  [ CHUNKER ] --> 1,200 char chunks, 200 overlap, heading prepend
       |
  [ EMBEDDER ] --> nomic-embed-text via Ollama, 768-dim
       |
  [ SQLite + Memmap Vectors ] --> FTS5 keyword index + float16 vector store
```

### Security (8 Layers)

```
  1. Credential security     -- DPAPI-encrypted key storage
  2. Network Gate            -- URL allowlist, all attempts logged
  3. Embedding lockdown      -- No runtime model downloads
  4. API endpoint control    -- Single approved endpoint in online mode
  5. Input sanitization      -- Path traversal and injection rejection
  5b. PII scrubbing          -- Regex-based redaction of emails, phones, SSNs, cards, IPs before online API calls
  6. Prompt hardening        -- 9-rule injection-resistant template
  7. Output verification     -- NLI claim checking, golden probes, contradiction policy
  8. Audit logging           -- Every query, response, cost, and security event
```

---

## 4. Technology Stack

All Python. All open-source. All company-approved with versions pinned to approved releases.

| Component | Package | License |
|-----------|---------|---------|
| Embeddings | nomic-embed-text via Ollama (768-dim) | Apache 2.0 |
| Vectors/search | NumPy 1.26.4, SQLite FTS5 | BSD-3, Public domain |
| Local LLM | Ollama (MIT), vLLM 0.10.1 (Apache 2.0) | MIT, Apache 2.0 |
| Online API | openai SDK 1.51.2 | Apache 2.0 |
| GUI | tkinter (stdlib) | PSF |
| REST API | FastAPI 0.115.0 | MIT |
| Credentials | keyring 23.13.1 (Windows DPAPI) | MIT |
| Logging | structlog 24.4.0 | MIT |
| PII scrubbing | Built-in regex engine (stdlib re) | N/A (no dependency) |
| Parsing | pdfplumber, python-docx, openpyxl, python-pptx, pytesseract + stdlib | MIT/Apache/BSD |

**System metrics:** 42,298 lines production code | 207 files | 491 tests (201 pytest + 290 virtual) | 49 file formats | 98% eval pass rate on 400-question set

---

## 5. Model Compliance

All offline models from US/EU publishers with permissive licenses. Full audit document prepared.

| Model | Publisher | Origin | License | Role |
|-------|-----------|--------|---------|------|
| phi4-mini (3.8B) | Microsoft | USA | MIT | Primary |
| mistral:7b (7B) | Mistral AI | France | Apache 2.0 | Technical alternate |
| phi4:14b (14B) | Microsoft | USA | MIT | Workstation primary |
| gemma3:4b (4B) | Google | USA | Apache 2.0 | Fast summarization |
| mistral-nemo:12b (12B) | Mistral/NVIDIA | France+USA | Apache 2.0 | Extended context |

**Excluded:** Qwen/Alibaba, DeepSeek, BAAI (China-origin, NDAA) | Meta/Llama (ITAR)

---

## 6. Data Assessment

- Ingests only internal, unclassified engineering documents from local file servers
- In offline mode: **no data leaves the machine**
- In online mode: only the query + retrieved passages sent to approved endpoint (not the full corpus)
- PII scrubber auto-strips emails, phone numbers, SSNs, credit cards, and IP addresses from prompts before online API transmission (configurable toggle)
- No PHI, no restricted material, no external data sources
- Decommissioning = delete the folder. No residual data in cloud services or model weights.

---

## 7. Human Oversight

The system retrieves and presents. The human decides.

| Step | Actor | Action |
|------|-------|--------|
| 1 | Human | Asks a question |
| 2 | System | Retrieves document passages, generates source-cited answer |
| 3 | System | Hallucination guard verifies claims against sources (online mode) |
| 4 | Human | Reviews answer and cited sources, decides whether to use it |

No autonomous decisions. No integration with any system of record. No mechanism to take action beyond displaying text. If wrong, source citations make verification a 10-second task.

**Accountability:** Jeremy Randall (owner) > Program Manager > AI Governance Engineer

---

## 8. Evaluation and QA

- **400-question golden eval set** covering factual, unanswerable, ambiguous, and injection attack categories
- **98% pass rate** including 100% on injection detection and unanswerable refusal
- **491 automated tests** (201 pytest + 290 virtual framework) for regression coverage
- Eval files integrity-protected -- cannot be modified to inflate scores
- IBIT startup diagnostics: 15 health checks in ~4 seconds before accepting queries

---

## 9. Risk Assessment

### Risk Tier: Low

| Criterion | Assessment |
|-----------|-----------|
| Autonomous decisions? | No -- retrieval and display only |
| Affects fundamental rights? | No |
| Processes PII/PHI? | No |
| Data leaves network? | No (offline); query+context only (online) |
| Human reviews all outputs? | Yes |

SP 800-171 Rev. 2 control family mapping prepared. Supply chain security enforced: all dependencies pinned to approved versions, model manifest documents origin/license for every AI model.

### Mitigations

- **Valid/Reliable:** 400-question eval, 491 automated tests, source-grounded answers, integrity-protected scoring
- **Safe:** Offline-first, 9-rule prompt, 5-layer hallucination guard with NLI verification and golden probes, IBIT startup diagnostics
- **Secure:** 8-layer security architecture, DPAPI credentials, Network Gate audit trail, crash-safe indexing, supply chain pinning
- **Fair:** Retrieval-based (returns document passages, not opinions), no profiling or personalization
- **Transparent:** Source citations on every answer, structured JSON audit logs, 34% documentation ratio, known-issue registry
- **Privacy:** No telemetry, no analytics, no third-party data collection

---

## 10. Deployment Approach

| Phase | Scope | Key Capabilities |
|-------|-------|-----------------|
| **Exploratory** (current) | Single-user desktop | Local LLM, controlled corpus, eval-driven development |
| **Pilot** | 5-10 engineers | Approved API endpoint, centralized logging, program corpus |
| **Scale-Up** | Multi-user | FastAPI backend, corporate auth, tamper-evident logging |
| **Production** | Enterprise | SSO, GPU inference, full compliance audit trail |

**Monitoring:** Per-query structured logging, re-runnable eval suite for accuracy drift, real-time cost dashboard.
**Exit plan:** Delete application folder and database files. No residual data in cloud services, model weights, or third-party systems.

---

## 11. Supporting Evidence

| Document | Description |
|----------|-------------|
| Technical Theory of Operation (RevA) | Full architecture, module graph, data flow |
| Model Compliance Audit | NDAA/ITAR analysis with disqualification rationale |
| Software Stack Decisions | Every tech choice with alternatives and rationale |
| SP 800-171 Control Mapping | Security controls mapped to architecture |
| Security Theory of Operation | Layered security analysis and threat model |
| Codebase Size Breakdown | Line counts by function, open-source RAG comparison |
| Evaluation Results | 400-question golden set with pass rates by category |
| IBIT Diagnostic Report | Startup health check results |
| GUI Guide / User Guide / Demo Prep | Operational and demonstration documentation |

---

## 12. Contact

| Role | Name | Title |
|------|------|-------|
| **Accountable Owner** | Jeremy Randall | RF Field Engineer |
| **Technical Contact** | Jeremy Randall | RF Field Engineer |

**Requested action:** Review of this exploratory use case registration for AI governance intake.

Supporting documentation, evaluation results, and a live demonstration available upon request. Accountable owner commits to quarterly governance review, annual risk re-assessment, and prompt incident reporting per organizational AI policy.
