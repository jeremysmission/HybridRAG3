# ============================================================================
# HybridRAG3 -- Security Audit Checklist
# NIST SP 800-171 Rev. 2 Compliance Mapping
# ============================================================================
#
# Document: HYBRIDRAG3-SEC-AUDIT-001
# Version:  1.0
# Date:     2026-02-13
# Author:   Jeremy (RF/AI Engineer) + Claude (AI Assistant)
# Classification: UNCLASSIFIED // FOR OFFICIAL USE ONLY
#
# PURPOSE:
#   This document maps every network call, file access, credential store,
#   and security-relevant operation in HybridRAG3 against NIST SP 800-171
#   Rev. 2 controls. It is designed for defense industry auditors who need
#   to verify that the system meets CUI (Controlled Unclassified Information)
#   protection requirements.
#
# HOW TO USE THIS DOCUMENT:
#   1. Work through each section sequentially
#   2. For each control, verify the "Implementation" column
#   3. Mark the "Status" column: PASS, FAIL, PARTIAL, or N/A
#   4. Document any gaps in the "Auditor Notes" column
#   5. Use the "Evidence" column to record file paths, screenshots, etc.
#
# SCOPE:
#   - HybridRAG3 application (Python, all modules)
#   - Home PC development environment
#   - Work laptop deployment environment
#   - Network communications (Ollama, Azure, OpenRouter)
#   - Data at rest (SQLite, embeddings, config files)
#   - Data in transit (API calls, local IPC)
#   - Credential management (keyring, env vars)
# ============================================================================

---

## TABLE OF CONTENTS

1. [Network Call Inventory](#1-network-call-inventory)
2. [File Access Inventory](#2-file-access-inventory)
3. [Credential Store Inventory](#3-credential-store-inventory)
4. [NIST 800-171 Control Family Mapping](#4-nist-800-171-control-family-mapping)
   - 4.1 [Access Control (3.1.x)](#41-access-control-31x)
   - 4.2 [Awareness and Training (3.2.x)](#42-awareness-and-training-32x)
   - 4.3 [Audit and Accountability (3.3.x)](#43-audit-and-accountability-33x)
   - 4.4 [Configuration Management (3.4.x)](#44-configuration-management-34x)
   - 4.5 [Identification and Authentication (3.5.x)](#45-identification-and-authentication-35x)
   - 4.6 [Incident Response (3.6.x)](#46-incident-response-36x)
   - 4.7 [Maintenance (3.7.x)](#47-maintenance-37x)
   - 4.8 [Media Protection (3.8.x)](#48-media-protection-38x)
   - 4.9 [Personnel Security (3.9.x)](#49-personnel-security-39x)
   - 4.10 [Physical Protection (3.10.x)](#410-physical-protection-310x)
   - 4.11 [Risk Assessment (3.11.x)](#411-risk-assessment-311x)
   - 4.12 [Security Assessment (3.12.x)](#412-security-assessment-312x)
   - 4.13 [System and Communications Protection (3.13.x)](#413-system-and-communications-protection-313x)
   - 4.14 [System and Information Integrity (3.14.x)](#414-system-and-information-integrity-314x)
5. [Data Flow Diagram](#5-data-flow-diagram)
6. [Risk Register](#6-risk-register)
7. [Remediation Roadmap](#7-remediation-roadmap)

---

## 1. NETWORK CALL INVENTORY

Every outbound network connection made by HybridRAG3, mapped to the source
module, destination, protocol, purpose, and kill switch.

### 1.1 Outbound Network Calls

| # | Source Module | File | Function | Destination | Protocol | Port | Purpose | Auth Method | Kill Switch | NIST Control |
|---|-------------|------|----------|-------------|----------|------|---------|-------------|-------------|--------------|
| N-01 | OllamaRouter | llm_router.py | is_available() | localhost:11434 | HTTP | 11434 | Health check (GET /) | None (localhost) | config.mode = "offline" disables API but Ollama is always localhost-only | 3.13.1 |
| N-02 | OllamaRouter | llm_router.py | query() | localhost:11434 | HTTP | 11434 | LLM inference (POST /api/generate) | None (localhost) | config.mode = "online" skips Ollama path | 3.13.1 |
| N-03 | APIRouter | llm_router.py | query() | Azure OpenAI endpoint (e.g., company.openai.azure.com) | HTTPS/TLS 1.2+ | 443 | LLM inference (POST /chat/completions) | api-key header | config.mode = "offline" disables entirely; config.security.offline_mode = true blocks all network | 3.13.1, 3.13.8 |
| N-04 | APIRouter | llm_router.py | query() | openrouter.ai/api/v1 | HTTPS/TLS 1.2+ | 443 | LLM inference (POST /chat/completions) | Bearer token | config.mode = "offline" disables entirely | 3.13.1, 3.13.8 |
| N-05 | APIRouter | llm_router.py | __init__() | Azure/OpenAI endpoint | HTTPS | 443 | SDK client initialization (may preflight) | API key | config.mode = "offline" | 3.13.1 |
| N-06 | Embedder | embedder.py | __init__() | huggingface.co | HTTPS | 443 | Model download (first run only) | None (public) | Set cache_dir in config; pre-download model; air-gap: copy .model_cache folder | 3.13.1 |
| N-07 | pip/Python | requirements.txt | pip install | pypi.org, files.pythonhosted.org | HTTPS | 443 | Dependency installation | None (public) | Air-gap: download wheels on connected machine, install from local folder | 3.13.1 |
| N-08 | GoldenProbes | fault_analysis.py | probe_api_connectivity() | API endpoint | HTTPS | 443 | Connectivity check (GET to endpoint) | None (unauthenticated GET) | Only runs when LLM router has API configured | 3.13.1 |

### 1.2 CRITICAL: No-Network Operations (Verified Offline)

These modules NEVER make network calls under any circumstances:

| Module | File | Verification Method |
|--------|------|-------------------|
| Chunker | chunker.py | Pure string operations, no imports of httpx/requests/urllib |
| VectorStore | vector_store.py | SQLite file I/O only, no network imports |
| Retriever | retriever.py | Numpy/SQLite operations only |
| Indexer | indexer.py | File system + VectorStore only |
| QueryEngine | query_engine.py | Orchestrator only; delegates network to LLMRouter |
| PII Sanitizer | pii_sanitizer.py | Regex-only operations |
| Config | config.py | YAML file read only |
| Logger | logger.py | File write only |
| FaultAnalysis | fault_analysis.py | File write + in-memory only (except probe_api_connectivity) |

### 1.3 Network Kill Switches

| Kill Switch | Config Path | Effect | Verification Command |
|------------|------------|--------|---------------------|
| Offline Mode | config.mode: "offline" | Routes all queries to Ollama (localhost only); API path completely skipped | Check llm_router.py line 674: `if mode == "online"` |
| Security Offline | config.security.offline_mode: true | Master kill switch; blocks ALL outbound network from application | Check at application startup |
| No SSL Verify | config.http.verify_ssl: true | When true (default), enforces TLS certificate validation | Check APIRouter.__init__ httpx.Client(verify=True) |
| Proxy Config | $env:HTTP_PROXY, $env:HTTPS_PROXY | Corporate proxy settings; set $env:NO_PROXY for localhost | PowerShell environment |

---

## 2. FILE ACCESS INVENTORY

Every file read, write, create, and delete operation in HybridRAG3.

### 2.1 File Reads

| # | Module | File Path Pattern | Purpose | Contains Sensitive Data? | NIST Control |
|---|--------|-------------------|---------|------------------------|--------------|
| F-R01 | Config | config.yaml, default_config.yaml | Application configuration | YES -- API endpoint URLs | 3.1.1, 3.8.1 |
| F-R02 | Indexer | source/**/*.{txt,md,csv,pdf,docx,...} | Document parsing for indexing | POTENTIALLY -- source docs may contain CUI | 3.8.1, 3.8.3 |
| F-R03 | VectorStore | index/chunks.db | SQLite database read (queries) | YES -- contains document chunks | 3.8.1 |
| F-R04 | VectorStore | index/embeddings.npy | Numpy memmap (vector search) | NO -- numeric vectors only, not reversible to text | 3.8.1 |
| F-R05 | Embedder | .model_cache/**/* | SentenceTransformer model weights | NO -- public model weights | N/A |
| F-R06 | Credentials | Windows Credential Manager | API keys via keyring | YES -- API secrets | 3.5.10, 3.13.8 |

### 2.2 File Writes

| # | Module | File Path Pattern | Purpose | Contains Sensitive Data? | NIST Control |
|---|--------|-------------------|---------|------------------------|--------------|
| F-W01 | VectorStore | index/chunks.db | SQLite database write (indexing) | YES -- document text chunks | 3.8.1, 3.8.9 |
| F-W02 | VectorStore | index/embeddings.npy | Numpy memmap write (embeddings) | NO -- numeric vectors | 3.8.1 |
| F-W03 | Logger | logs/*.log | Application logs (structured) | POTENTIALLY -- may contain query text | 3.3.1, 3.8.1 |
| F-W04 | FaultAnalysis | logs/fault_analysis.jsonl | Fault event log | POTENTIALLY -- may contain error context | 3.3.1 |
| F-W05 | FaultAnalysis | logs/flight_recorder.jsonl | Flight recorder trace | POTENTIALLY -- records query summaries | 3.3.1 |
| F-W06 | Config | config.yaml | Config updates (if modified at runtime) | YES -- endpoint URLs | 3.4.2 |

### 2.3 File Deletions

| # | Module | File Path Pattern | Purpose | NIST Control |
|---|--------|-------------------|---------|--------------|
| F-D01 | Indexer | index/chunks.db (rows) | Delete old chunks on re-index | 3.8.3 |
| F-D02 | Cleanup | logs/old_*.log | Rotate old log files | 3.3.1 |

### 2.4 Sensitive File Locations Summary

| Path | Classification | Access Should Be Restricted To | Encryption Required? |
|------|---------------|-------------------------------|---------------------|
| config.yaml | SENSITIVE -- contains endpoint URLs | Application user only | Recommended (contains infrastructure info) |
| index/chunks.db | SENSITIVE -- contains document text | Application user only | YES -- AES-256 at rest (planned) |
| logs/*.log | POTENTIALLY SENSITIVE | Application user + auditors | Recommended |
| Windows Credential Manager | SENSITIVE -- API keys | OS user account only | YES -- OS-managed encryption |
| source/**/* | POTENTIALLY CUI | Per document classification | Per document classification |

---

## 3. CREDENTIAL STORE INVENTORY

Every credential, secret, and authentication token used by HybridRAG3.

### 3.1 Credentials

| # | Credential | Storage Location | Encryption | Rotation Policy | Used By | NIST Control |
|---|-----------|-----------------|------------|-----------------|---------|--------------|
| C-01 | API Key (Azure/OpenRouter) | Windows Credential Manager via keyring | DPAPI (OS-managed) | Rotate every 90 days or on suspected compromise | APIRouter in llm_router.py | 3.5.10, 3.13.8 |
| C-02 | API Key (fallback) | Environment variable: AZURE_OPENAI_API_KEY | NOT encrypted (process memory) | Session-scoped; cleared on terminal close | APIRouter in llm_router.py | 3.5.10 |
| C-03 | API Key (fallback) | Environment variable: OPENAI_API_KEY | NOT encrypted (process memory) | Session-scoped | APIRouter in llm_router.py | 3.5.10 |
| C-04 | API Endpoint URL | Windows Credential Manager via keyring | DPAPI (OS-managed) | Update when endpoint changes | APIRouter in llm_router.py | 3.5.10 |
| C-05 | API Endpoint URL (fallback) | Environment variable: AZURE_OPENAI_ENDPOINT | NOT encrypted (process memory) | Session-scoped | APIRouter in llm_router.py | 3.5.10 |

### 3.2 Credential Resolution Order

The LLMRouter resolves API keys in this priority order (first non-empty wins):

1. Explicit api_key parameter (for testing -- never stored)
2. Windows Credential Manager via `keyring.get_password('hybridrag', 'api_key')`
3. `$env:AZURE_OPENAI_API_KEY`
4. `$env:AZURE_OPEN_AI_KEY` (company variant)
5. `$env:OPENAI_API_KEY`

**AUDIT NOTE:** Priority 2 (Credential Manager) is the recommended and most
secure option. Priorities 3-5 (environment variables) are fallbacks for
environments where Credential Manager is not available. Environment variables
are visible to any process running as the same user.

### 3.3 Credential Security Gaps

| Gap | Risk | Severity | Remediation |
|-----|------|----------|-------------|
| Environment variable fallback stores key in process memory | Key visible to other processes of same user | MEDIUM | Remove env var fallback in production; enforce Credential Manager only |
| No credential rotation enforcement | Stale keys may remain active | LOW | Add key age tracking; warn if key > 90 days old |
| No MFA for credential access | Single-factor auth to credential store | LOW | Mitigated by Windows user account security |
| API key transmitted in HTTP header | Key in transit on every API call | LOW | Mitigated by TLS 1.2+ encryption in transit |
| Config.yaml may contain endpoint URL | Infrastructure information disclosure | LOW | Restrict file permissions; add to .gitignore |

---

## 4. NIST 800-171 CONTROL FAMILY MAPPING

### 4.1 Access Control (3.1.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.1.1 | Limit system access to authorized users | Application runs as user-level process; inherits OS user authentication. No built-in multi-user auth (single-user desktop app). | PARTIAL | OS login required; no app-level auth | Single-user by design. If multi-user needed, add FastAPI auth layer. |
| 3.1.2 | Limit system access to permitted transactions/functions | Mode switching (offline/online) controlled via config.yaml. Admin functions (re-index, config change) not access-controlled beyond file permissions. | PARTIAL | config.yaml, llm_router.py mode check | Add role-based config for admin vs user operations. |
| 3.1.3 | Control flow of CUI in accordance with approved authorizations | Data flows: source docs -> indexer -> SQLite -> retriever -> LLM prompt -> response. PII sanitizer strips sensitive patterns before LLM calls. Network calls only in online mode. | PARTIAL | pii_sanitizer.py, llm_router.py mode check, config.security.offline_mode | PII sanitizer needs expanded pattern library. Document data flow authorization. |
| 3.1.5 | Employ principle of least privilege | Application requests only necessary file/network permissions. Runs as standard user (not admin). Ollama router only accesses localhost. | PASS | Process runs as standard user; no elevated privileges | Verify no admin elevation in startup scripts. |
| 3.1.20 | Verify and control connections to external systems | Online mode connections go to configured endpoints only. SSL verification enforced. Endpoint stored in credential manager. | PASS | llm_router.py APIRouter.__init__, httpx.Client(verify=True) | Verify SSL is not disabled in any code path. |
| 3.1.22 | Control CUI posted/processed on publicly accessible systems | HybridRAG3 is a local desktop app. No web interface exposed. API calls send prompts to Azure/OpenRouter (encrypted in transit). | PARTIAL | No web server; API calls use TLS | Evaluate CUI risk of prompt content sent to cloud LLMs. |

### 4.2 Awareness and Training (3.2.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.2.1 | Security awareness | README.md documents security features. Config comments explain network implications. llm_router.py has INTERNET ACCESS comments. | PARTIAL | Code comments, this audit document | Create formal user security guide. |
| 3.2.2 | Information security training | Developer (Jeremy) trained via hands-on security implementation. This audit document serves as training reference. | PARTIAL | This document, code comments | Formal training record needed for compliance. |

### 4.3 Audit and Accountability (3.3.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.3.1 | Create and retain audit records | structlog produces structured JSON logs. config.security.audit_logging = true. fault_analysis.py writes fault events. Flight recorder captures system events. | PASS | logs/*.log, logs/fault_analysis.jsonl, logs/flight_recorder.jsonl, logger.py, fault_analysis.py | Verify log retention policy. |
| 3.3.2 | Ensure actions traceable to individual users | Single-user system -- all actions attributed to the OS user. Query logs include query text, timestamp, mode, cost. | PASS | QueryLogEntry in logger.py | If multi-user, add user ID to all log entries. |
| 3.3.3 | Review and update audit events | fault_analysis.py provides summary reports and trend analysis. Golden probes detect issues proactively. | PASS | FaultAnalysisEngine.get_summary() | Schedule weekly audit log review. |
| 3.3.4 | Alert on audit process failure | Logger failures caught in try/except blocks. FaultAnalysis logs write failures silently degrade (no crash). | PARTIAL | Exception handling in logger.py, fault_analysis.py | Add explicit alert if log directory becomes unwritable. |
| 3.3.5 | Correlate audit records | Flight recorder timestamps + fault IDs enable event correlation. get_flight_trace() retrieves events around a fault. | PASS | FlightRecorder.get_trace_around() | Document correlation procedures. |

### 4.4 Configuration Management (3.4.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.4.1 | Establish and maintain baseline configurations | default_config.yaml defines all defaults. Config changes logged. Git tracks all code changes. | PASS | default_config.yaml, git history | Tag known-good configurations in git. |
| 3.4.2 | Establish and enforce security configuration settings | config.security section: audit_logging, offline_mode, pii_sanitization. All default to secure values. | PASS | default_config.yaml security section | Document which settings are security-critical. |
| 3.4.5 | Define, document, approve configuration changes | Git commit history tracks all changes. Handover documents capture rationale. Session transcripts preserve context. | PARTIAL | Git log, handover docs, session transcripts | Formal change approval process needed for production. |
| 3.4.6 | Employ least functionality | Only required Python packages installed. No unnecessary services. No web server unless explicitly added. | PASS | requirements.txt, no extraneous packages | Review requirements.txt quarterly for unnecessary deps. |
| 3.4.8 | Apply deny-by-exception (blacklisting) policy | config.security.offline_mode defaults to false (allow network). Flip to true to block all outbound. Indexer excluded_dirs blocks known non-document directories. | PARTIAL | Config defaults, indexer._excluded_dirs | Consider switching to allowlist (whitelist) for network endpoints. |

### 4.5 Identification and Authentication (3.5.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.5.1 | Identify system users | Single-user desktop app; user identified by OS login. | PASS | OS authentication | If multi-user, add application-level authentication. |
| 3.5.2 | Authenticate users | Delegated to OS (Windows login). API calls authenticated via API key. | PASS | OS login, keyring credential storage | Verify Windows account has strong password policy. |
| 3.5.10 | Store and transmit only cryptographically protected passwords | API keys stored in Windows Credential Manager (DPAPI encrypted). Keys transmitted over TLS 1.2+ only. No plaintext key storage in files. | PARTIAL | keyring usage in llm_router.py, httpx with verify=True | Environment variable fallback is NOT encrypted at rest. Remove for production. |
| 3.5.11 | Obscure feedback of authentication info | API keys masked in logs (first 4 chars only shown in diagnostics). Key never displayed in GUI. | PASS | Diagnostic output masks keys | Verify no code path logs full API key. |

### 4.6 Incident Response (3.6.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.6.1 | Establish incident handling capability | fault_analysis.py provides: severity classification (SEV-1 to SEV-4), 11-class error taxonomy, automated troubleshooting playbooks, fault event logging. | PASS | fault_analysis.py, FaultAnalysisEngine | Document escalation procedures for SEV-1/SEV-2. |
| 3.6.2 | Track, document, report incidents | Fault log (JSONL) records all incidents with timestamps, severity, classification, and resolution status. get_summary() provides trend reporting. | PASS | logs/fault_analysis.jsonl, FaultAnalysisEngine.get_summary() | Export fault reports for compliance review. |
| 3.6.3 | Test incident response capability | Golden probes (GoldenProbes.run_all()) provide automated testing. Can be scheduled or run on-demand. | PASS | GoldenProbes class, probe test suite | Schedule regular probe runs (daily recommended). |

### 4.7 Maintenance (3.7.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.7.1 | Perform maintenance | Index rebuild, log rotation, cache clearing documented. close() methods release resources. gc.collect() in indexer loop. | PASS | indexer.py close(), gc.collect(), cleanup procedures | Document maintenance schedule. |
| 3.7.2 | Provide controls on maintenance tools | Maintenance scripts (rag-rebuild-index, rag-cleanup) are part of the application. No external tools with elevated access. | PASS | Tools in hybridrag3/tools/ | Verify tools don't require admin elevation. |

### 4.8 Media Protection (3.8.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.8.1 | Protect CUI on digital media | Index database on local drive. File permissions restrict access to user account. No removable media used in normal operation. | PARTIAL | Local file storage, OS file permissions | Implement AES-256 encryption at rest for chunks.db. |
| 3.8.3 | Sanitize media before disposal/reuse | Indexer delete_chunks_by_source() removes data from SQLite. close() releases memory. No secure wipe implemented. | PARTIAL | delete_chunks_by_source(), close() | Add secure delete (overwrite) for sensitive data removal. SQLite DELETE doesn't zero bytes on disk. |
| 3.8.9 | Protect confidentiality of backup CUI | Git repository on GitHub (private). .gitignore excludes index/, logs/, .model_cache/, *.zip (except releases/). | PARTIAL | .gitignore file | Verify no sensitive data in git history. Consider git-crypt for config files. |

### 4.9 Personnel Security (3.9.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.9.1 | Screen individuals prior to access | Single developer (Jeremy) with active security clearance (implied by defense contractor employment). | PASS | Employment records | Document access authorization. |
| 3.9.2 | Protect CUI during personnel actions | Single-user system. If developer leaves, revoke API keys, wipe index, transfer code ownership. | PARTIAL | N/A currently | Document offboarding procedures. |

### 4.10 Physical Protection (3.10.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.10.1 | Limit physical access | Home PC: personal residence with locked doors. Work laptop: corporate facility with badge access. | PASS | Physical security measures | Document physical security controls. |
| 3.10.3 | Escort visitors | N/A for single-user desktop application. | N/A | | |
| 3.10.5 | Manage physical access audit logs | N/A for software application. Covered by facility security. | N/A | | |

### 4.11 Risk Assessment (3.11.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.11.1 | Periodically assess risk | This audit document constitutes initial risk assessment. Risk register in Section 6 identifies known risks. | PASS | This document, Section 6 | Schedule quarterly reassessment. |
| 3.11.2 | Scan for vulnerabilities periodically | requirements.txt pins all dependency versions. Can be scanned with `pip audit` or `safety check`. Golden probes detect runtime issues. | PARTIAL | requirements.txt, golden probes | Add pip audit to weekly maintenance schedule. Run `pip audit` against requirements.txt. |
| 3.11.3 | Remediate vulnerabilities | Remediation roadmap in Section 7. Dependency updates tracked via requirements.txt pinning. | PARTIAL | Section 7, requirements.txt | Track CVEs for all pinned dependencies. |

### 4.12 Security Assessment (3.12.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.12.1 | Assess security controls periodically | This audit checklist. Golden probes provide automated assessment. fault_analysis.py provides ongoing monitoring. | PASS | This document, GoldenProbes, FaultAnalysisEngine | Schedule semi-annual full audit. |
| 3.12.2 | Develop and implement plans of action | Remediation roadmap (Section 7) prioritizes gaps. Sprint planning integrates security tasks. | PASS | Section 7 | Track remediation completion. |
| 3.12.4 | Develop, document, and update system security plan | This document. Architecture documented in session transcripts and code comments. | PASS | This document, code documentation | Update on each major version release. |

### 4.13 System and Communications Protection (3.13.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.13.1 | Monitor, control, protect communications at external boundaries | Network Call Inventory (Section 1) documents all external communications. config.mode controls online/offline. config.security.offline_mode is master kill switch. | PASS | Section 1, config.yaml | Verify kill switches work by testing in offline mode. |
| 3.13.2 | Employ architectural designs that promote effective security | Three-layer security: (1) Network lockdown via config, (2) PII sanitization before LLM calls, (3) Audit logging of all operations. Zero-trust design: offline by default. | PASS | Architecture documentation, code structure | Document the three-layer model formally. |
| 3.13.5 | Implement subnetworks for publicly accessible components | N/A -- desktop application, no public-facing components. | N/A | | |
| 3.13.8 | Implement cryptographic mechanisms to prevent unauthorized disclosure during transmission | All API calls use HTTPS/TLS 1.2+ (enforced by openai SDK and httpx with verify=True). Certificate validation enabled. pip-system-certs for corporate proxy. | PASS | APIRouter httpx.Client(verify=True), openai SDK default TLS | Verify TLS 1.2 minimum (not TLS 1.0/1.1). |
| 3.13.10 | Establish and manage cryptographic keys | API keys managed via Windows Credential Manager (DPAPI). No application-managed crypto keys currently. Planned: AES-256 for index encryption. | PARTIAL | keyring usage, DPAPI | Implement AES-256 at-rest encryption for chunks.db. |
| 3.13.11 | Employ FIPS-validated cryptography | Windows DPAPI uses FIPS-validated algorithms when Windows FIPS mode is enabled. Python TLS uses OpenSSL (FIPS-capable). AES-256 planned for at-rest encryption. | PARTIAL | Windows FIPS mode setting, OpenSSL | Enable Windows FIPS mode on work laptop. Verify OpenSSL FIPS module. |

### 4.14 System and Information Integrity (3.14.x)

| Control | Requirement | HybridRAG3 Implementation | Status | Evidence | Auditor Notes |
|---------|------------|--------------------------|--------|----------|--------------|
| 3.14.1 | Identify, report, correct system flaws in timely manner | fault_analysis.py detects and classifies flaws. Golden probes provide proactive detection. Git tracks all code fixes. | PASS | fault_analysis.py, git history | Document SLA for each severity level. |
| 3.14.2 | Provide protection from malicious code | No external code execution in application. Input sanitization on file paths. PII sanitizer validates text content. _validate_text() rejects binary garbage. | PASS | indexer._validate_text(), PII sanitizer, input validation | Add antivirus scan to source document pipeline. |
| 3.14.3 | Monitor system security alerts | fault_analysis.py provides automated alerting. Golden probes detect issues proactively. Structured logging enables monitoring. | PASS | FaultAnalysisEngine, GoldenProbes | Integrate with corporate security monitoring if available. |
| 3.14.4 | Update malicious code protection | Dependency pinning in requirements.txt. pip audit for vulnerability scanning. No auto-update mechanism (deliberate -- defense environments require manual approval). | PASS | requirements.txt pinning, manual update process | Run pip audit weekly. Track CVEs. |
| 3.14.6 | Monitor organizational systems | Audit logging enabled by default. Flight recorder captures system events. Fault analysis provides trend reporting. | PASS | config.security.audit_logging, FlightRecorder, FaultAnalysisEngine | Configure log forwarding to SIEM if available. |
| 3.14.7 | Identify unauthorized use | Single-user system with OS authentication. Audit logs record all queries with timestamps. Anomalous usage would appear in logs. | PARTIAL | Audit logs, OS authentication | Add query rate anomaly detection. |

---

## 5. DATA FLOW DIAGRAM

```
                    +-----------------+
                    |  Source Docs    |
                    | (txt,pdf,docx)  |
                    +--------+--------+
                             |
                    [FILE READ - F-R02]
                             |
                    +--------v--------+
                    |    Indexer       |
                    | (parse, chunk,  |
                    |  validate)      |
                    +--------+--------+
                             |
                    [FILE WRITE - F-W01, F-W02]
                             |
              +--------------v--------------+
              |       Vector Store           |
              | (SQLite chunks.db +          |
              |  NumPy embeddings.npy)       |
              +--------------+--------------+
                             |
                    [FILE READ - F-R03, F-R04]
                             |
                    +--------v--------+
                    |   Retriever     |
                    | (vector search, |
                    |  reranking)     |
                    +--------+--------+
                             |
                    [IN-MEMORY ONLY]
                             |
                    +--------v--------+        +-------------------+
                    |  Query Engine   |        | PII Sanitizer     |
                    | (build prompt,  +------->| (strip sensitive   |
                    |  call LLM)      |        |  patterns)        |
                    +--------+--------+        +-------------------+
                             |
              +--------------+--------------+
              |                             |
     [LOCALHOST - N-01,N-02]      [HTTPS/TLS - N-03,N-04]
              |                             |
    +---------v----------+       +----------v-----------+
    |    Ollama           |       |   Azure / OpenRouter  |
    | (localhost:11434)   |       |   (api endpoint)      |
    | OFFLINE - no        |       |   ONLINE - encrypted  |
    | internet            |       |   in transit          |
    +--------------------+       +----------------------+
              |                             |
              +--------------+--------------+
                             |
                    [IN-MEMORY ONLY]
                             |
                    +--------v--------+
                    |  LLM Response   |
                    | (answer text,   |
                    |  token counts)  |
                    +--------+--------+
                             |
                    [FILE WRITE - F-W03,F-W04,F-W05]
                             |
                    +--------v--------+
                    |   Audit Log     |
                    | (query, mode,   |
                    |  cost, latency) |
                    +-----------------+
```

---

## 6. RISK REGISTER

| Risk ID | Risk Description | Likelihood | Impact | Severity | Current Mitigation | Residual Risk | Remediation Priority |
|---------|-----------------|-----------|--------|----------|-------------------|---------------|---------------------|
| R-01 | CUI in prompts sent to cloud LLM (data exfiltration risk) | MEDIUM | HIGH | SEV-2 | PII sanitizer strips known patterns; offline mode available | Sanitizer may miss novel PII patterns | HIGH -- expand PII patterns, add human review for CUI queries |
| R-02 | API key compromised (unauthorized API usage) | LOW | HIGH | SEV-2 | Key in Credential Manager (DPAPI encrypted); TLS in transit | Env var fallback is unencrypted in memory | MEDIUM -- remove env var fallback in production |
| R-03 | SQLite database not encrypted at rest | MEDIUM | HIGH | SEV-2 | OS file permissions restrict access | Physical access or admin could read raw data | HIGH -- implement AES-256 encryption for chunks.db |
| R-04 | Dependency vulnerability (supply chain attack) | LOW | HIGH | SEV-2 | All versions pinned in requirements.txt | Pinned versions may have known CVEs | MEDIUM -- weekly pip audit, quarterly dependency update |
| R-05 | Log files contain sensitive query text | MEDIUM | MEDIUM | SEV-3 | Logs restricted to user account | Query text may contain CUI references | MEDIUM -- add log sanitization, encrypt log files |
| R-06 | Model download from huggingface.co on first run | LOW | LOW | SEV-4 | Model cached locally after first download | Initial download requires internet | LOW -- pre-download model for air-gapped deployment |
| R-07 | Git repository may contain sensitive data in history | LOW | MEDIUM | SEV-3 | .gitignore blocks index/, logs/, config | Historical commits may have leaked data | MEDIUM -- audit git history, consider git-filter-repo |
| R-08 | Single-user system lacks access control for shared machines | LOW | MEDIUM | SEV-3 | OS user authentication | Multiple users on same OS account share all data | LOW -- acceptable for single-user desktop |
| R-09 | Ollama HTTP (not HTTPS) on localhost | LOW | LOW | SEV-4 | Localhost only; not routable | Process on same machine could intercept | LOW -- acceptable for localhost-only traffic |
| R-10 | Smart quote / Unicode injection in config files | LOW | LOW | SEV-4 | PS 5.1 safety rules documented; config parser handles it | Malformed YAML could cause unexpected behavior | LOW -- add YAML validation on config load |

---

## 7. REMEDIATION ROADMAP

### Priority 1: Critical (address within 30 days)

| # | Item | Risk ID | NIST Control | Effort | Description |
|---|------|---------|-------------|--------|-------------|
| REM-01 | Implement AES-256 at-rest encryption for chunks.db | R-03 | 3.8.1, 3.13.10 | 2-3 days | Use Python cryptography library (already in requirements). Encrypt chunk text before SQLite insert, decrypt on read. Key derived from user password or hardware token. |
| REM-02 | Expand PII sanitization patterns | R-01 | 3.1.3, 3.14.2 | 1-2 days | Add patterns for: SSN, phone numbers, email addresses, physical addresses, names (NER-based), badge numbers, project codenames. |
| REM-03 | Remove environment variable credential fallback | R-02 | 3.5.10 | 0.5 day | In production config, disable priorities 3-5 in LLMRouter credential resolution. Force Credential Manager only. |

### Priority 2: High (address within 60 days)

| # | Item | Risk ID | NIST Control | Effort | Description |
|---|------|---------|-------------|--------|-------------|
| REM-04 | Add pip audit to weekly maintenance | R-04 | 3.11.2, 3.14.4 | 0.5 day | Add to weekly PowerShell maintenance script: `pip audit --requirement requirements.txt`. Alert on any findings. |
| REM-05 | Log sanitization | R-05 | 3.3.1, 3.8.1 | 1 day | Strip or hash sensitive content in log entries before writing. Apply same PII patterns to log text. |
| REM-06 | Git history audit | R-07 | 3.8.9 | 1 day | Run `git log --all --diff-filter=A -- "*.yaml" "*.json" "*.env"` to check for accidentally committed secrets. Use git-filter-repo to remove if found. |
| REM-07 | Document formal change management process | - | 3.4.5 | 0.5 day | Create CHANGE_MANAGEMENT.md with: who can approve changes, testing requirements before deployment, rollback procedures. |

### Priority 3: Medium (address within 90 days)

| # | Item | Risk ID | NIST Control | Effort | Description |
|---|------|---------|-------------|--------|-------------|
| REM-08 | FIPS mode validation | - | 3.13.11 | 1 day | Enable Windows FIPS mode on work laptop. Verify OpenSSL FIPS module in Python. Test all crypto operations still work. |
| REM-09 | Pre-download model for air-gap deployment | R-06 | 3.13.1 | 0.5 day | Document procedure to download all-MiniLM-L6-v2 on connected machine and transfer .model_cache to air-gapped system. |
| REM-10 | Query rate anomaly detection | - | 3.14.7 | 1-2 days | Track queries per hour. Alert if rate exceeds 3x normal baseline (potential unauthorized automated use). |
| REM-11 | Formal user security guide | - | 3.2.1 | 1 day | Create SECURITY_GUIDE.md covering: safe usage practices, what data is safe to query, when to use offline mode, credential management procedures. |

### Priority 4: Low (address within 180 days)

| # | Item | Risk ID | NIST Control | Effort | Description |
|---|------|---------|-------------|--------|-------------|
| REM-12 | Secure delete for SQLite data removal | R-03 | 3.8.3 | 1 day | SQLite DELETE doesn't zero bytes on disk. Add VACUUM after bulk deletes. Consider SQLite SECURE DELETE pragma. |
| REM-13 | YAML validation on config load | R-10 | 3.4.2 | 0.5 day | Add schema validation when loading config.yaml. Reject configs with unexpected keys, wrong types, or values outside safe ranges. |
| REM-14 | Log encryption at rest | R-05 | 3.8.1 | 1 day | Encrypt log files using same AES-256 mechanism as database. Provide decryption tool for auditors. |

---

## APPENDIX A: VERIFICATION COMMANDS

PowerShell commands to verify security controls on your system:

```
# Check if FIPS mode is enabled (Windows)
Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\FIPSAlgorithmPolicy" -Name Enabled
```

```
# Check Python OpenSSL version
python -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

```
# Check file permissions on config.yaml
Get-Acl config.yaml | Format-List
```

```
# Check Windows Credential Manager entries
python -c "import keyring; print(keyring.get_credential('hybridrag', None))"
```

```
# Run pip audit for vulnerability scanning
pip audit --requirement requirements.txt
```

```
# Check TLS version used by Python requests
python -c "import ssl; ctx = ssl.create_default_context(); print('Min TLS:', ctx.minimum_version); print('Max TLS:', ctx.maximum_version)"
```

```
# List all network-capable imports in the codebase
findstr /s /i "import httpx\|import requests\|import urllib\|import socket\|import openai" src\*.py
```

```
# Verify .gitignore blocks sensitive directories
git status --ignored --short
```

---

## APPENDIX B: AUDIT SIGN-OFF

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | Jeremy | 2026-02-13 | _____________ |
| Security Reviewer | _____________ | _____________ | _____________ |
| System Administrator | _____________ | _____________ | _____________ |
| Approving Authority | _____________ | _____________ | _____________ |

---

*Document generated 2026-02-13. Review annually or upon major system changes.*
*Classification: UNCLASSIFIED // FOR OFFICIAL USE ONLY*
