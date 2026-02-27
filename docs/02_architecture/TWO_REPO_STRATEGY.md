# Two-Repo Strategy: Personal vs Work

## Why Two Repos

HybridRAG3 runs in two environments with fundamentally different security
postures.  One codebase serves both, but the work environment cannot receive
the full private repo because it contains real machine paths, session
artifacts, security-context documentation, and AI-assistant references that
must never appear on a government terminal.

The solution is a private repo (source of truth) and a sanitized public
clone (the "Educational" repo) that the work laptop downloads as a ZIP
through a browser -- zero git credentials on the work machine.

| Property | Personal (HybridRAG3) | Work (HybridRAG3_Educational) |
|----------|----------------------|-------------------------------|
| Location | `D:\HybridRAG3` | `D:\HybridRAG3_Educational` |
| Visibility | Private GitHub | Public GitHub |
| Transfer method | `git push` | Browser ZIP download |
| Git credentials | Yes | None -- zero-trust |

## What Gets Synced

`tools/sync_to_educational.py` is a denylist mirror: everything copies
except items on the skip list.  This means new files are included by
default so the work copy stays complete.

### Skipped entirely

| Category | Examples | Why |
|----------|----------|-----|
| Build artifacts | `.venv/`, `__pycache__/`, `wheels/`, `*.pyc` | Rebuilt on target |
| Runtime data | `data/`, `logs/`, `temp_diag/` | Machine-specific |
| Machine scripts | `start_hybridrag.ps1`, `.claude/`, `deploy_comments.ps1` | Contains real paths / AI workspace |
| Session artifacts | `HANDOVER*/`, `SESSION*/`, `virtual_test/` | Development-internal |
| Security docs | `docs/05_security/` | Too dense with restricted terms |
| Career docs | `docs/07_career/` | Personal |
| Project mgmt | `docs/09_project_mgmt/` | Internal planning |
| Binary Office | `*.docx`, `*.xlsx`, `~$*` | Cannot text-sanitize |
| Home requirements | `requirements.txt` | Work uses `requirements_approved.txt` |
| The sync script itself | `sync_to_educational.py` | Contains banned terms in its config |
| "Bond" marker files | Any file with "Bond" in the first 5 lines | Content kill-switch for private docs |

### Text sanitized (41 regex passes)

Every copied text file runs through pattern replacements:

| Pattern class | Example replacement |
|---------------|-------------------|
| Corporate names | `Northrop Grumman` -> `Organization` |
| Standards refs | `NIST SP 800-171` -> `security compliance standard` |
| Military terms | `DoD`, `ITAR`, `CMMC` -> `industry` / `regulatory` / `compliance framework` |
| Classification | `classified` -> `restricted`, `UNCLASSIFIED` -> `UNRESTRICTED` |
| Machine paths | `D:\HybridRAG3` -> `{PROJECT_ROOT}`, `D:\RAG Source Data` -> `{SOURCE_DIR}` |
| User names | `jerem`, `randaje` -> `{USERNAME}` |
| AI references | `Claude` -> `AI assistant`, `Anthropic` -> `AI provider` |

### Post-sync banned word scan

After copying, the script scans the Educational destination for leaked
terms.  If any match is found the script prints `[WARN]` and aborts before
commit.

## API Layer Differences

The core RAG pipeline is identical.  The only infrastructure difference is
how the online-mode API connection is configured.

### Home PC (Commercial Azure OpenAI)

- Endpoint pattern: `*.openai.azure.com`
- Networking: direct internet, no proxy
- CA bundle: system default
- Provider config: auto-detect from URL (leave `HYBRIDRAG_API_PROVIDER` empty)

### Work Laptop (Azure Government OpenAI)

- Endpoint pattern: `*.openai.azure.us`
- Networking: corporate HTTPS proxy (`HTTPS_PROXY` env var)
- CA bundle: custom corporate root CA (`REQUESTS_CA_BUNDLE`)
- Provider config: force `HYBRIDRAG_API_PROVIDER=azure_gov`

The code handles both through `_build_httpx_client()` in `llm_router.py`,
which reads proxy and CA settings from environment variables.  Ollama and
vLLM calls force `localhost_only=True` so the corporate proxy never
interferes with local model serving.

Work-specific environment variables:

```
HYBRIDRAG_API_PROVIDER=azure_gov
HTTPS_PROXY=http://proxy.corp.internal:8080
REQUESTS_CA_BUNDLE=C:\corp\ca-bundle.crt
```

These are set in the Educational repo's startup script and never appear in
the private repo's config or code.

## Offline Mode (No Difference)

Offline mode is identical in both repos.  Ollama serves models on
localhost:11434 with no network calls.  The approved model stack is the
same:

- phi4-mini (primary, 7/9 profiles)
- mistral:7b (alt for eng-heavy profiles)
- phi4:14b-q4_K_M (logistics primary, workstation)
- gemma3:4b (PM fast summarization)
- mistral-nemo:12b (upgrade path, 128K context)

## Dependencies

| File | Repo | Purpose |
|------|------|---------|
| `requirements.txt` | Personal only | Full dependency list including dev/test |
| `requirements_approved.txt` | Both (Educational uses this) | Pre-vetted subset for restricted environments |

The Educational repo's setup instructions point to `requirements_approved.txt`.
The personal repo keeps both files so the full dev environment works locally.

## Configuration Templates

The personal repo has a real `start_hybridrag.ps1` with actual paths.
This file is excluded from sync.  The Educational repo instead gets a
`start_hybridrag.ps1.template` with `{PLACEHOLDER}` values that the user
copies and edits.

`config/default_config.yaml` syncs normally but all hardcoded paths
(`D:\RAG Indexed Data`, etc.) are replaced with `{DATA_DIR}` and
`{SOURCE_DIR}` placeholders by the sanitization pass.

## Push Sequence

Every push follows this sequence with no exceptions:

1. `pytest tests/ --ignore=tests/test_fastapi_server.py` (regression)
2. Banned word scan on changed files
3. `git push origin main` (HybridRAG3)
4. `python tools/sync_to_educational.py` (sanitize + scan)
5. `cd D:\HybridRAG3_Educational && git add -A && git commit && git push origin main`

If steps 4-5 are skipped, the work laptop gets stale code on next ZIP
download.

## Summary

The two repos exist because work security requires zero-trust isolation.
The private repo is the single source of truth.  The Educational repo is a
derived artifact produced by an automated, auditable sanitization pipeline.
Code must never be comingled in the other direction -- proxy/government
configuration stays in the Educational fork only.
