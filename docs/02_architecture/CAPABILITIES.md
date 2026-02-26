# HybridRAG3 -- Product Capabilities

**Revision A** | 2026-02-25

---

## Document Processing

- **49+ file formats** supported: PDF, DOCX, PPTX, XLSX, EML, MSG, HTML, TXT, MD, CSV, JSON, XML, YAML, LOG, RTF, DXF, STP/STEP, IGS/IGES, STL, VSDX, EVTX, PCAP, images (PNG/JPG/TIFF/BMP/GIF/WEBP via OCR), certificates (CER/CRT/PEM), databases (ACCDB/MDB).
- **Intelligent chunking** with paragraph boundary detection and heading preservation.
- **Incremental indexing** -- only re-indexes changed files, skipping unchanged content.
- **Crash-safe indexing** with automatic resume from the last successful checkpoint.
- **OCR fallback** for scanned documents via Tesseract.
- **File validation pre-flight** catches corrupt or unreadable files before processing begins.
- **Scale**: 1,345+ documents / 40,000+ chunks currently indexed.

## Search and Retrieval

- **Hybrid search**: semantic (meaning-based) + keyword (BM25 via FTS5) run in parallel.
- **Reciprocal Rank Fusion** merges both result sets into a single ranked list.
- **Sub-200ms search latency** on 40,000 chunks.
- **Synonym handling** -- "RF band" finds "frequency range" and similar terms.
- **Exact term matching** for part numbers, acronyms, and technical jargon.
- **Configurable** relevance threshold and result count per query.

## AI Question Answering

- **Direct answers** in plain English with source citations.
- **9-rule prompt system** covering injection protection, ambiguity handling, and fact grounding.
- **98% accuracy** on a 400-question golden evaluation set.
- **5-layer hallucination guard**: prompt rules, claim extraction, fact verification, confidence scoring, dual-path consensus.
- **Dual-mode**: offline (free, local AI) or online (cloud API, faster).
- **Query time**: 2-5 seconds (online) or 5-30 seconds (offline/Ollama).

## Security

- **Offline by default** -- zero internet connectivity out of the box.
- **Three-layer network lockdown**: OS-level, application-level, and code-level enforcement.
- **Centralized Network Gate** with URL allowlist -- all outbound calls pass through a single checkpoint.
- **API key encryption** via Windows DPAPI (Credential Manager).
- **Full JSON audit trail** for every query, index run, and network connection.
- **PII sanitization** in all log output.
- **Approved publishers only** -- all AI models sourced from US/EU vendors.
- **No China-origin software** -- federal procurement compliance enforced at dependency level.
- **USB installer** for air-gapped deployment in restricted facilities.

## User Interfaces

- **Desktop GUI** (tkinter) with dark/light themes.
- **NavBar view switching**: Query, Settings, Cost Dashboard, Reference.
- **Command-line interface** via PowerShell functions for scripted workflows.
- **REST API** (FastAPI, localhost-only, 7 endpoints) for programmatic integration.
- **Status bar** with live system health indicators.

## AI Model Management

- **5-model approved stack**: phi4-mini, mistral:7b, phi4:14b, gemma3:4b, mistral-nemo:12b.
- **9 role-specific profiles**: sw, eng, pm, sys, log, draft, fe, cyber, gen.
- **Dual ENG/GEN scoring** ranks models per job function automatically.
- **Interactive model wizard** with hardware-aware recommendations.
- **Seamless offline/online switching** -- no reconfiguration needed.

## Program Management

- **Real-time cost tracking** for tokens, dollars, and latency per query.
- **Budget gauge** with green/yellow/red thresholds.
- **ROI calculator** with editable parameters: hourly rate, team size, minutes saved per query.
- **Team monthly projection** with ROI percentage.
- **CSV export** of all cost data for external reporting.
- **Citations** to McKinsey, BLS, and HBR studies supporting ROI methodology.

## Deployment and Scalability

- **Minimum hardware**: runs on 8GB RAM laptops.
- **Maximum hardware**: scales from 12 GB single-GPU workstations to 48 GB dual-GPU home rigs.
- **Three hardware profiles**: laptop_safe, desktop_power, server_max.
- **USB offline installer** for security-conscious and restricted facilities.
- **Corporate proxy auto-detection** and CA bundle handling for regulated environments.
- **Separate home/work deployment paths** with automated setup scripts.

## Testing and Evaluation

- **373 automated pytest tests** -- all passing.
- **745 virtual simulation tests** covering edge cases and integration paths.
- **140 setup simulation tests** validating installation across environments.
- **400-question golden evaluation set** with multi-type scoring.
- **Scoring dimensions**: factual accuracy, behavioral correctness, citation accuracy.
- **Injection trap testing** -- planted false claims (AES-512) verified as caught and rejected.

## Compatibility

- **OS**: Windows 10 / Windows 11
- **Runtime**: Python 3.11+
- **Offline AI**: Ollama required for offline mode
- **Online AI**: Azure OpenAI (commercial or government endpoints)
