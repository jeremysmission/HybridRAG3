# HybridRAG3 -- Security Theory of Operation

Revision: B | Date: 2026-02-25

---

## Executive Summary

HybridRAG3 implements a 9-layer security architecture designed around a single
principle: **nothing leaves the machine unless explicitly authorized**. The system
defaults to fully offline operation -- zero internet traffic, zero telemetry,
zero external dependencies at runtime. Every layer is fail-closed, meaning any
ambiguity or misconfiguration results in *less* access, never more.

This document describes each security layer, what it protects against, and how
the layers compose into a layered security posture suitable for enterprise
environments handling sensitive documents.

---

## 1. Architecture: Zero-Trust Offline-Default

HybridRAG3 follows a zero-trust model where no component is assumed to be safe:

- **Default mode is OFFLINE.** Out of the box, the system runs entirely on
  localhost with no internet access. This is not a fallback -- it is the
  primary operating mode.

- **Online mode requires explicit opt-in.** Switching to online requires
  configuring an API endpoint, providing credentials, and passing validation
  checks. There is no path to accidental online operation.

- **Every network call is gated.** A centralized NetworkGate singleton
  intercepts every outbound connection attempt. If the gate says no, the
  connection does not happen -- there is no "try anyway" path.

- **Embedding models run locally, always.** The embedding pipeline
  (nomic-embed-text via Ollama) runs exclusively on localhost. There is
  no online mode for embedding, ever.

- **PII is scrubbed before online transmission.** When online mode is used,
  a regex-based PII scrubber strips sensitive data (SSN, credit cards,
  emails, phone numbers, IP addresses) before any text is sent to the
  cloud API.

```
                         +---------------------------+
                         |      USER INTERFACE       |
                         |  GUI (Tk) / REST API / MCP|
                         +---------------------------+
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
   LAYER 5: INPUT            LAYER 6: PROMPT             LAYER 7: POST-GEN
   Pydantic validation       9-rule source-bounded       NLI claim verification
   max_length=2000           injection resistance        faithfulness scoring
   regex mode guard          source quality filter       contradiction detection
         |                            |                            |
         +----------------------------+----------------------------+
                                      |
                         +---------------------------+
                         |   LAYER 5.5: PII SCRUB    |
                         |  SSN, CC, email, phone, IP |
                         |  (online mode only)        |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |     LAYER 4: SEC-001      |
                         |  Endpoint defaults empty   |
                         |  Allowlist enforcement     |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |   LAYER 3: EMBEDDER LOCK  |
                         |  Ollama localhost-only     |
                         |  No HF imports in core     |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |   LAYER 2: NETWORK GATE   |
                         |  OFFLINE / ONLINE / ADMIN  |
                         |  Fail-closed singleton     |
                         |  Per-call audit trail      |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |  LAYER 1: CREDENTIALS     |
                         |  Win Credential Manager    |
                         |  Key masking in all logs   |
                         |  getpass for CLI entry     |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |  LAYER 8: AUDIT LOGGING   |
                         |  Structured JSON (structlog)|
                         |  App / Error / Audit / Cost |
                         |  Hallucination guard JSONL  |
                         +---------------------------+
                                      |
                         +---------------------------+
                         |  LAYER 9: HEALTH MONITOR  |
                         |  Golden probes (SEV 1-4)   |
                         |  Flight recorder           |
                         |  Fault analysis engine      |
                         +---------------------------+
```

---

## 2. Layer 1: Credential Security

**File:** `src/security/credentials.py`

### What It Does

All credential access in the system flows through a single module. No other
module reads environment variables, keyring entries, or config values for
secrets directly.

### Three-Priority Resolution

For each credential (API key, endpoint, deployment, API version, provider,
auth scheme):

| Priority | Source                       | Security Level |
|----------|------------------------------|----------------|
| 1st      | Windows Credential Manager   | OS-protected, encrypted at rest |
| 2nd      | Environment variables        | Process-scoped, not persisted |
| 3rd      | Config file values           | Lowest -- config may be committed to git |

The system always prefers the most secure source available. If a credential
exists in both keyring and env var, the keyring value wins.

### Key Masking

API keys are **never logged in full**. The `key_preview` property exposes only
the first 4 and last 4 characters (e.g., `sk-a...xZ9f`). This masking is
enforced at the property level -- even internal code cannot accidentally log
the full key through the standard API.

### CLI Key Entry

When entering credentials via the command line, `getpass.getpass()` is used.
Input is never echoed to the screen, never written to a file, and goes directly
from the keyboard to Windows Credential Manager.

### GUI Key Entry

The API Admin tab provides masked input fields for API key entry. The Test
Connection button validates credentials without exposing key values. Keys
are stored directly to Windows Credential Manager from the GUI.

### Endpoint Validation

Before any endpoint URL is accepted:
- Must start with `https://` or `http://`
- No smart quotes or hidden Unicode characters (regex scan)
- No spaces, no double slashes in path
- Trailing slashes stripped for consistency

### Dual-Environment Provider Support

The credential system supports separate configurations for different network
environments:

- **Provider detection**: `HYBRIDRAG_API_PROVIDER` env var or keyring entry.
  Auto-detects Azure, Azure Government, and standard OpenAI from endpoint URL.
- **Proxy support**: `HTTPS_PROXY`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`
  environment variables enable corporate proxy and custom CA certificate chains.
- **Isolation**: Work laptop credentials (keyring + proxy) and home PC
  credentials (keyring, no proxy) never interfere. Each machine resolves
  its own credential chain independently.

---

## 3. Layer 2: Network Gate

**File:** `src/core/network_gate.py`

### What It Does

A singleton gate that intercepts every outbound network call in the
application. The gate is configured once during boot and cannot be bypassed.

### Three Modes

| Mode     | Allowed Destinations              | Default? |
|----------|-----------------------------------|----------|
| OFFLINE  | localhost only (Ollama + vLLM)     | YES      |
| ONLINE   | localhost + one configured API     | No       |
| ADMIN    | Unrestricted (logged + warned)     | No       |

### Fail-Closed Design

- Gate initializes in OFFLINE mode. It is never upgraded without explicit
  configuration.
- `HYBRIDRAG_OFFLINE=1` environment variable forces OFFLINE mode regardless
  of any other configuration. This is the "kill switch."
- ADMIN mode can only be set via `HYBRIDRAG_ADMIN_MODE=1` environment variable
  (not via config file), preventing accidental persistence in committed config.
- Non-HTTP schemes (`ftp://`, `file://`, `data://`) are always blocked except
  in ADMIN mode.

### Per-Call Audit Trail

Every connection attempt -- allowed or denied -- creates an audit entry:

```
{
  "timestamp": "2026-02-25T14:30:00Z",
  "url": "https://api.example.com/v1/chat",
  "hostname": "api.example.com",
  "purpose": "llm_query",
  "mode": "ONLINE",
  "allowed": true,
  "reason": "host in allowed_hosts",
  "caller": "api_router"
}
```

A rolling buffer of 1,000 entries prevents memory leaks while maintaining
a meaningful recent history for diagnostics.

### ONLINE Mode Allowlist

In ONLINE mode, the gate permits:
- Localhost connections (any port)
- The single configured API endpoint host
- URL prefixes from `allowed_endpoint_prefixes` (path-level control)

Everything else is blocked. There is no wildcard. There is no "add more hosts
later" API -- the allowlist is set during boot and is immutable until the next
boot.

---

## 4. Layer 3: Embedding Lockdown

**File:** `src/core/embedder.py`

### What It Does

The embedding model (nomic-embed-text, 768-dim) converts document text into
vector representations via the local Ollama server. This model runs
**exclusively offline** -- there is no online mode for embedding, ever.

### Localhost-Only Design

The embedder sends HTTP requests only to `localhost:11434` (Ollama's default
address, configurable via `OLLAMA_HOST` env var). The NetworkGate blocks any
attempt to send embedding requests to non-localhost addresses.

With the migration from sentence-transformers to Ollama-served embeddings,
the core pipeline no longer imports any HuggingFace libraries. This eliminates
the entire class of telemetry, model download, and token transmission risks
that HuggingFace libraries introduced.

### TransformersRouter Lockdown (Optional)

When the optional TransformersRouter is enabled for direct GPU inference,
HuggingFace environment lockdowns are still applied:

| Variable | Value | Blocks |
|----------|-------|--------|
| `HF_HUB_OFFLINE` | `1` | Model downloads and update checks |
| `TRANSFORMERS_OFFLINE` | `1` | Redundant safety net |
| `HF_HUB_DISABLE_TELEMETRY` | `1` | Usage statistics reporting |
| `HF_HUB_DISABLE_IMPLICIT_TOKEN` | `1` | Automatic token transmission |

These are set before any HuggingFace imports. Models must be pre-cached
locally. A missing model raises an immediate error -- no silent download.

### Loud Failure

If the Ollama embedding model is not available (server down, model not
pulled), the embedder raises an error immediately. There is no silent
fallback. A missing model is a configuration error that should be fixed
by the administrator.

---

## 5. Layer 4: API Endpoint Control (SEC-001)

**File:** `src/core/config.py`

### What It Does

Prevents the system from accidentally sending queries to unauthorized servers.

### The SEC-001 Fix

Before SEC-001, the API endpoint defaulted to a public AI service URL. This
meant switching to online mode without configuration would silently send
document queries to a third-party server. SEC-001 changed the default to an
empty string:

```yaml
api:
  endpoint: ""  # EMPTY BY DEFAULT -- must be explicitly configured
```

### Validation Rules

| Check | Result |
|-------|--------|
| Online mode + empty endpoint | Boot fails with clear error |
| Endpoint is a known public AI URL | Boot fails with clear error |
| Endpoint does not match allowlist | Boot fails with clear error |

### Endpoint Allowlist

```yaml
api:
  allowed_endpoint_prefixes:
    - "https://your-org.openai.azure.com/"
```

If this list is non-empty, the configured endpoint MUST start with one of
these prefixes. This prevents redirecting queries to unauthorized servers
even if someone modifies the endpoint field.

---

## 6. Layer 5: Input Validation

**File:** `src/api/models.py`

### What It Does

All API inputs are validated by Pydantic models before any route handler
code executes. Invalid input returns 422 Unprocessable Entity -- the request
never reaches the query engine.

### Constraints

| Field          | Constraint                    | Protection                    |
|----------------|-------------------------------|-------------------------------|
| question       | min_length=1, max_length=2000 | Rejects empty + prompt-stuffing |
| mode           | regex: `^(offline\|online)$`  | Rejects arbitrary mode strings |
| source_folder  | Path existence check          | Prevents indexing from invalid paths |

### API Surface Minimization

The `/config` endpoint returns `api_endpoint_configured: bool` rather than
the actual endpoint URL. No internal configuration values leak through the
API response.

---

## 7. Layer 5.5: PII Scrubbing

**File:** `src/security/pii_scrubber.py`

### What It Does

Automatically detects and removes personally identifiable information from
text before it is sent to cloud APIs in online mode. This layer sits between
input validation and the API call, ensuring PII never leaves the machine
even when online mode is active.

### Pattern Detection

Patterns are ordered most-specific-first to prevent partial matches:

| Pattern | Placeholder | Example Match |
|---------|-------------|---------------|
| SSN | `[SSN]` | 123-45-6789 |
| Credit card | `[CARD]` | 4111-1111-1111-1111 |
| Email | `[EMAIL]` | user@example.com |
| Phone (US) | `[PHONE]` | (555) 123-4567, +1-555-123-4567 |
| IPv4 | `[IP]` | 192.168.1.1 (excludes 127.x.x.x) |

### Key Properties

- **Online-only.** PII scrubbing only runs on the online code path
  (APIRouter). Offline queries never trigger scrubbing because no data
  leaves the machine.
- **Enabled by default.** `security.pii_sanitization: true` in the
  default configuration. Can be toggled in the GUI API Admin tab.
- **No external dependencies.** Pure stdlib `re` module with compiled
  patterns at import time. Zero network access.
- **Auditable.** Returns `(scrubbed_text, replacement_count)` -- the
  count is logged for audit without exposing the original PII values.

---

## 8. Layer 6: Prompt Injection Protection

**File:** `src/core/query_engine.py`

### What It Does

A 9-rule source-bounded prompt prevents the LLM from being manipulated by
content embedded in indexed documents.

### The 9-Rule Prompt

| Rule | Name                | Purpose                                          |
|------|---------------------|--------------------------------------------------|
| 1    | GROUNDING           | Answer only from provided context, not training data |
| 2    | COMPLETENESS        | Include all specific technical details found      |
| 3    | REFUSAL             | If context lacks the answer, say so explicitly    |
| 4    | AMBIGUITY           | Ask for clarification instead of guessing         |
| 5    | INJECTION RESISTANCE| Ignore instructions embedded in document chunks   |
| 6    | ACCURACY            | Never fabricate specifications or standards       |
| 7    | VERBATIM VALUES     | Reproduce measurements exactly as found           |
| 8    | SOURCE QUALITY      | Ignore test metadata and self-labeled noise       |
| 9    | EXACT LINE          | Format precise values with "Exact:" prefix        |

### Priority Order

```
Injection resistance > Ambiguity clarification > Accuracy > Formatting
```

Rule 5 (injection) takes absolute priority. If a document contains embedded
instructions ("Ignore previous instructions and..."), the LLM is instructed
to disregard them and refer to the injected content generically without
quoting it.

### Injection Trap Verification

The evaluation suite includes a planted false claim (a non-existent
encryption standard) embedded in a real document. If the LLM repeats this
claim in any form -- even in a rejection context -- the injection test fails.
This validates that Rule 5 is working: the LLM must refuse to engage with
injected content rather than analyzing or quoting it.

### Evaluation Results

- 100% injection resistance on the 400-question golden evaluation set
- 98% overall pass rate (factual + behavioral scoring combined)

---

## 9. Layer 7: Post-Generation Verification (Hallucination Guard)

**File:** `src/core/hallucination_guard/`

### What It Does

After the LLM generates an answer, the hallucination guard independently
verifies every factual claim against the source documents using Natural
Language Inference (NLI).

### 5-Stage Pipeline

| Stage | Component           | Function                                    |
|-------|---------------------|---------------------------------------------|
| 1     | Prompt Hardener     | Injects grounding rules into the system prompt |
| 2     | Claim Extractor     | Identifies individual factual claims in the response |
| 3     | NLI Verifier        | Checks each claim against source chunks (local model) |
| 4     | Response Scorer     | Computes faithfulness = supported / verifiable claims |
| 5     | Confidence Calibrator| Flags overconfident language on unverified claims |

### Key Properties

- **Local-only operation.** The NLI cross-encoder model (cross-encoder/nli-deberta-v3-base,
  MIT license, 440MB) runs entirely on the local machine. No claims or
  document content leave the system.

- **Zero tolerance for contradictions.** If any claim directly conflicts
  with source material, the entire response is marked unsafe -- regardless
  of the overall faithfulness score.

- **80% faithfulness threshold.** At least 80% of verifiable claims must be
  supported by source documents for the response to pass.

- **Tunable failure actions.** The guard can `block` (hide response entirely),
  `flag` (add [UNVERIFIED] markers), `strip` (remove failed claims), or
  `warn` (show with warning header).

### Overconfidence Detection

The guard watches for language like "definitely", "certainly", "absolutely",
"guaranteed", "100%", "impossible" -- when used on claims that are not
verified or are contradicted by sources, this triggers a confidence warning.

### Audit Trail

Each verification produces a JSONL audit entry including:
- Verification ID (12-char MD5 hash)
- Timestamp
- Query text (truncated to 200 characters)
- Safety verdict, faithfulness score, claim counts
- Up to 5 contradiction details, up to 3 confidence warnings

Source document text is **never** included in the audit log.

---

## 10. Layer 8: Structured Audit Logging

**File:** `src/monitoring/logger.py`

### What It Does

All security-relevant events are captured in structured JSON format via
structlog, enabling machine-readable filtering, dashboarding, and audit review.

### Log Channels

| Channel | File Pattern              | Content                          |
|---------|---------------------------|----------------------------------|
| App     | app_YYYY-MM-DD.log        | General application events       |
| Error   | error_YYYY-MM-DD.log      | Errors and failures              |
| Audit   | audit_YYYY-MM-DD.log      | Security events (who/what/when)  |
| Cost    | cost_YYYY-MM-DD.log       | API token usage and cost         |
| Guard   | hallucination_audit.jsonl  | Verification results             |
| Faults  | fault_analysis.jsonl      | Health probe results             |

### Structured Entry Format

Every audit entry includes:
- **action** -- what happened (query, mode_switch, index_start, etc.)
- **user** -- who initiated it
- **mode** -- offline or online at the time
- **details** -- action-specific context
- **ip** -- source IP (relevant for API access)
- **timestamp** -- ISO 8601

### What Is Logged vs. What Is Not

| Logged | Not Logged |
|--------|------------|
| Query text (for traceability) | Source document chunk content |
| API endpoint host | Full API keys |
| Token counts and cost | Credential values |
| Network gate decisions | Raw HTTP bodies |
| Model name and latency | Internal Python stack traces (production) |
| PII replacement count | Original PII values |
| Health probe results | N/A |

---

## 11. Layer 9: Health Monitoring and Fault Analysis

**Files:** `src/core/fault_analysis.py`, `src/core/golden_probe_checks.py`

### What It Does

Automated health monitoring detects system problems before they impact users.
Golden probes run on a schedule, checking every critical dependency. Results
are sorted by severity and logged with specific remediation steps.

### Severity Classification

| Level | Meaning | Response |
|-------|---------|----------|
| SEV-1 | Critical (DB corrupted, model missing) | Halt system |
| SEV-2 | High (major feature broken) | Degrade gracefully |
| SEV-3 | Medium (feature degraded but usable) | Continue with warning |
| SEV-4 | Low (cosmetic, performance) | Weekly review |

### Golden Probes

| Probe | What It Checks | Fail Severity |
|-------|----------------|---------------|
| `check_config_valid()` | YAML structure, numeric ranges | SEV-1 |
| `check_disk_space()` | Warns < 1 GB, fails < 100 MB | SEV-2 |
| `probe_ollama_connectivity()` | GET localhost:11434 | SEV-2 |
| `probe_api_connectivity()` | GET /models endpoint | SEV-3 |
| `probe_embedder_load()` | Ollama /api/embed test | SEV-2 |
| `probe_index_readability()` | SQLite query speed test | SEV-1 |

### Flight Recorder

A circular buffer of recent events (fixed size, append-only) provides
context when failures occur. On a SEV-1/SEV-2 event, the preceding
events are available for root-cause analysis. No memory leaks (circular,
bounded size).

### Error Taxonomy

11 error classes (NETWORK_ERROR, AUTH_ERROR, API_ERROR, INDEX_ERROR, etc.),
each mapped to troubleshooting playbooks with specific fix suggestions.
Results logged to `logs/fault_analysis.jsonl`.

---

## 12. Model Supply Chain Security

### Approved Model Stack

All models in the system are vetted for:
- **License compliance** -- MIT or Apache 2.0 only
- **Country of origin** -- No models from restricted jurisdictions (NDAA compliance)
- **Publisher verification** -- Only models from established, auditable organizations

| Model | Publisher | License | Use |
|-------|-----------|---------|-----|
| phi4-mini (3.8B) | Microsoft (USA) | MIT | Default offline LLM |
| mistral:7b (7B) | Mistral (France) | Apache 2.0 | Alt offline LLM |
| phi4:14b-q4_K_M (14B) | Microsoft (USA) | MIT | Workstation LLM |
| gemma3:4b (4B) | Google (USA) | Apache 2.0 | Fast summarization |
| mistral-nemo:12b (12B) | Mistral (France) | Apache 2.0 | 128K context LLM |
| nomic-embed-text (768d) | Nomic (USA) | Apache 2.0 | Embedder (all deployments) |
| nli-deberta-v3-base | Cross-encoder | MIT | Hallucination guard NLI |

### Model Download Manifest

`config/model_manifest.yaml` provides a complete auditable inventory of
every AI model weight required by the system:
- Vendor, country, license, size, VRAM requirements
- Download source and exact command
- Security controls (localhost-only, no HF deps, etc.)
- Air-gap transfer instructions (copy Ollama model directory)
- Which hardware profiles use each model

This makes multi-gigabyte model downloads auditable for security compliance
-- pip cannot scan these files, so the manifest provides the paper trail.

### Profile-Based Model Selection

| Profile | RAM | Embedder | LLM |
|---------|-----|----------|-----|
| laptop_safe | 8-16GB | nomic-embed-text (768d, Ollama) | phi4-mini (3.8B) |
| desktop_power | 32-64GB | nomic-embed-text (768d, Ollama) | mistral-nemo:12b |
| server_max | 64GB+ | nomic-embed-text (768d, Ollama) | phi4:14b-q4_K_M |

All profiles now use the same embedding model (nomic-embed-text, 768-dim)
served by Ollama. Profile switching no longer requires a re-index.

### What Is Banned

- All China-origin models (Qwen/Alibaba, DeepSeek, BGE/BAAI) -- NDAA
- Meta/Llama models -- regulatory restrictions
- Any model without a permissive open-source license

A full audit document tracks the rationale for each model decision.

---

## 13. MCP Server Security

**File:** `mcp_server.py`

### What It Does

Exposes HybridRAG3 as a Model Context Protocol server for AI agent
integration. Three tools (search, status, index_status) are exposed via
JSON-RPC over stdio.

### Security Properties

- **Lazy initialization.** The boot pipeline (including NetworkGate
  configuration) runs before any tool call executes. An MCP client
  checking available tools does not trigger model loading or network calls.
- **Inherits all security layers.** The MCP server imports and calls
  the same QueryEngine, LLMRouter, and NetworkGate that the GUI and
  REST API use. All 9 security layers apply identically.
- **No additional network surface.** Communication is via stdio (stdin/
  stdout), not a network socket. The MCP server cannot be accessed
  remotely.
- **No raw document access.** The search tool returns answers and source
  filenames only -- never raw document chunk content.

---

## 14. Bulk Transfer Security

**File:** `src/tools/bulk_transfer_v2.py`

### What It Does

Enterprise file transfer for importing document collections from network
drives. Security-relevant properties:

- **Atomic writes.** Files are written to a `.tmp` path, SHA-256 verified,
  then atomically renamed. A crash mid-transfer cannot leave a corrupted
  file in the source folder.
- **Three-stage staging.** Incoming, verified, and quarantine directories
  prevent unverified files from entering the indexing pipeline.
- **Content-hash deduplication.** Prevents duplicate files from inflating
  the index. Hash manifest stored in SQLite.
- **No network access.** Operates on local paths and SMB/UNC shares only.
  No HTTP, no cloud storage, no remote APIs. The NetworkGate is not
  involved because no internet-protocol connections are made.
- **Symlink loop detection.** Prevents infinite directory traversal via
  circular symlinks or NTFS junctions.

---

## 15. Git Repository Sanitization

**File:** `tools/sync_to_educational.py`

### What It Does

The private repository syncs to an educational/public repository through a
one-way sanitization pipeline. No sensitive content can leak through this
channel.

### Sanitization Pipeline

1. **Skip patterns** -- Machine-specific files, runtime data, binary Office
   files, logs, and session-specific documents are never copied.

2. **Text replacements** -- 31 regex substitutions strip organization-specific
   terms, personal paths, usernames, and tool references from all text files.

3. **Post-sync scan** -- After all files are copied and sanitized, the entire
   destination tree is scanned for 22 banned words. Any hits are flagged
   as warnings.

4. **Binary file exclusion** -- `.docx`, `.xlsx`, and `~$*` files are blocked
   entirely because binary Office files cannot be reliably text-sanitized.

### Path Hardening

- Hardcoded paths are replaced with placeholders: `{PROJECT_ROOT}`,
  `{USER_HOME}`, `{DATA_DIR}`, `{SOURCE_DIR}`
- Usernames are replaced with `{USERNAME}`
- All file reads use `encoding="utf-8-sig"` (handles BOM)
- All file writes use `newline="\n"` (normalized line endings)

---

## 16. Boot Pipeline Security

**File:** `src/core/boot.py`

### Ordered, Fail-Fast Startup

The boot pipeline runs security-critical steps in strict order. Each step
must succeed before the next runs:

```
Step 1: Load config (yaml.safe_load -- no code execution)
   |
Step 2: Resolve credentials (keyring > env > config, including provider)
   |
Step 2.5: Configure network gate (BEFORE any network calls)
   |
Step 3: Create API client (only if credentials.is_online_ready)
   |
Step 4: Ollama health check (non-blocking, 500ms timeout)
   |
Step 4.5: vLLM health check (if enabled, non-blocking)
   |
READY
```

### Key Properties

- **Gate before network.** The network gate is configured in Step 2.5,
  before Step 3 (API client) or Step 4 (Ollama) make any network calls.
  If gate configuration fails, OFFLINE mode is forced.

- **Non-blocking health check.** The Ollama health check runs in a daemon
  thread with a 500ms join timeout. A slow or unresponsive Ollama never
  blocks the boot pipeline.

- **Safe YAML parsing.** `yaml.safe_load()` is used exclusively -- no
  arbitrary code execution from configuration files.

- **Credential safety.** Boot logs the credential source (keyring, env,
  config) but never the credential value. The `key_preview` property
  ensures only masked keys appear in any diagnostic output.

---

## 17. API Server Hardening

**File:** `src/api/server.py`

### Localhost-Only Binding

The FastAPI server binds to `127.0.0.1:8000` by default. Exposing to the
network requires explicit `--host 0.0.0.0` -- the default is safe.

### No CORS

No CORS middleware is configured. Cross-origin requests from browsers are
rejected by default, which is correct for a localhost-only service.

### Component Initialization Order

Config loads first (triggering gate configuration), then vector store, then
embedder (localhost Ollama call), then LLM router, then query engine.
Security-critical setup always precedes components that could make network
calls.

### Concurrent Indexing Guard

Indexing operations use a lock and an `indexing_active` flag. Attempting to
start a second concurrent index returns HTTP 409 Conflict rather than
corrupting the vector store.

---

## 18. Security Testing

### Automated Security Audit (tests/run_audit.py)

A 24-check security audit script scans the codebase for:

| Category | Checks |
|----------|--------|
| Secret detection | No API key patterns (`sk-...`) in source |
| Character encoding | No smart quotes, non-breaking spaces, or BOM in source |
| Key masking | credentials.py never exposes full keys |
| Config safety | Committed YAML has empty API key and endpoint |
| Exception codes | All unique, all follow `CATEGORY-NNN` pattern |
| File structure | All required files and `__init__.py` present |
| Python syntax | All source files compile without errors |

### API Tests (tests/test_fastapi_server.py)

17 tests validate:
- Empty/missing question rejection (422)
- Invalid mode rejection (422)
- Bad folder path rejection (400)
- Health, status, config endpoint correctness

### PII Scrubber Tests (tests/test_pii_scrubber.py)

16 tests validate:
- Each PII pattern correctly detected and replaced
- Non-PII text passes through unchanged
- Localhost IP addresses (127.x.x.x) are excluded from scrubbing
- Edge cases (empty input, overlapping patterns)

### Injection Evaluation

The 400-question golden evaluation set includes:
- Injection attempts (planted false claims in real documents)
- Unanswerable questions (validates refusal behavior)
- Ambiguous questions (validates clarification behavior)
- Factual questions (validates accuracy)

Current scores: 100% injection resistance, 98% overall pass rate.

### Test Coverage

550+ automated tests across 47 test files, covering:
- Core pipeline (indexing, retrieval, query engine)
- Security (credentials, PII, network gate)
- GUI (panels, wizard, view switching)
- API (endpoints, validation)
- Bulk transfer (stress tests, chaos tests)
- Health monitoring (golden probes)

---

## 19. Security Posture Summary

### What an Auditor Will Find

| Concern | HybridRAG3 Answer |
|---------|-------------------|
| Can data leave the machine? | Not by default. OFFLINE mode = localhost only. |
| What if someone misconfigures online mode? | SEC-001: empty endpoint default + allowlist enforcement. |
| Is PII protected in online mode? | Yes. Regex scrubber strips SSN, CC, email, phone, IP before API calls. |
| Are credentials stored securely? | Windows Credential Manager (OS-encrypted). Never logged in full. |
| Can documents be exfiltrated via the API? | API returns answers and source filenames only. No raw document content. |
| Can prompt injection compromise the system? | 9-rule prompt + injection trap testing = 100% resistance. |
| Are LLM responses verified? | 5-stage hallucination guard with NLI + zero-contradiction policy. |
| Is there an audit trail? | Structured JSON logging for app, errors, security, cost, verification, and health. |
| Are the AI models trustworthy? | All models MIT/Apache 2.0 from US/EU publishers. Full manifest + audit trail. |
| Can the embedding model phone home? | No. Ollama serves from localhost. No HuggingFace imports in core pipeline. |
| What about the public/educational repo? | One-way sync with 31 text replacements + 22-word banned scan. |
| Can file transfers introduce threats? | Atomic writes + SHA-256 verification + three-stage staging. |
| Is the MCP server a new attack surface? | No. Stdio-only (no network socket). Inherits all 9 security layers. |
| Can the system detect its own failures? | Yes. Golden probes with severity classification and flight recorder. |

### Design Principles

1. **Fail closed.** Every ambiguity defaults to less access, not more.
2. **Layered security.** 9 independent layers -- compromising one does not
   compromise the system.
3. **No silent failures.** Missing models, invalid configs, and blocked
   network calls all produce clear, actionable error messages.
4. **Audit everything.** Every query, every network call, every verification
   result, every health probe is logged in machine-readable format.
5. **Local first.** The system is fully functional with zero internet access.
   Online mode is an optional enhancement, not a requirement.
6. **Scrub before send.** PII is removed from text before any cloud API call.
   Even if the network gate is correctly configured, PII scrubbing provides
   layered protection for data that should never leave the machine.
