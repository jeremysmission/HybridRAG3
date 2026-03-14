# HybridRAG3 CLI Guide

**Created:** 2026-03-13  
**Last updated:** 2026-03-13 14:15 America/Denver  
**Purpose:** explain the supported PowerShell command workflow for daily use, diagnostics, and operator actions.

## Scope

This guide focuses on the CLI commands loaded by `start_hybridrag.ps1`.

It covers:

- daily startup
- the 17 standard `rag-*` commands loaded into PowerShell
- online credentials and mode switching
- API server startup
- the shared-launch preflight tool used by operators

If you want the visual workflow instead, use [GUI_GUIDE.md](GUI_GUIDE.md).

## Daily Startup

Open PowerShell in the repo root and run:

```powershell
cd "D:\HybridRAG3"
. .\start_hybridrag.ps1
```

Important:

- the leading `dot-space` matters
- the commands exist only in the current PowerShell session
- if you open a new shell window, run the start script again

If PowerShell execution policy is locked down, use the batch launcher or the bypass path documented in [INSTALL_AND_SETUP.md](../01_setup/INSTALL_AND_SETUP.md).

## The First Session On A Machine

1. load the environment
2. run `rag-status`
3. index documents with `rag-index`
4. ask one offline question with `rag-query "..." `
5. only after that, add online credentials if you need online mode

## Command Groups

### Core Commands

| Command | What it does |
|---|---|
| `rag-paths` | show important project, data, and environment paths |
| `rag-index` | build or refresh the search index |
| `rag-query "question"` | ask a question against the indexed corpus |
| `rag-diag` | run the diagnostic suite |
| `rag-status` | quick health/status report |
| `rag-gui` | launch the desktop GUI |
| `rag-server` | start the local FastAPI server |

### Online Mode And Credentials

| Command | What it does |
|---|---|
| `rag-store-key` | store the online API key securely |
| `rag-store-endpoint` | store the online API endpoint |
| `rag-cred-status` | show whether the key and endpoint are configured |
| `rag-cred-delete` | remove the stored API credentials |
| `rag-mode-online` | switch generation to the online API path |
| `rag-mode-offline` | switch generation back to the local runtime |
| `rag-models` | show available models and current model posture |
| `rag-test-api` | send one live test request to the configured API |

### Profiles And Model Selection

| Command | What it does |
|---|---|
| `rag-profile` | show the current performance profile |
| `rag-profile laptop_safe` | set the conservative profile |
| `rag-profile desktop_power` | set the balanced desktop profile |
| `rag-profile server_max` | set the highest-throughput profile |
| `rag-set-model` | open the CLI model selection wizard |

## Core Workflows

### Index Documents

Run:

```powershell
rag-index
```

Use it when:

- the machine has never indexed the corpus
- the source folder contents changed
- answers are missing documents that should be present

### Ask A Question

Run:

```powershell
rag-query "What changed in the deployment runbook?"
```

Good habits:

- ask one clear question at a time
- use document language when possible
- re-index if the answer quality is unexpectedly weak

### Check Health Quickly

Run:

```powershell
rag-status
```

Use `rag-diag` when `rag-status` is not enough.

Useful variants:

```powershell
rag-diag --verbose
rag-diag --test-embed
```

### Launch The Desktop GUI

Run:

```powershell
rag-gui
```

Optional hidden launch:

```powershell
rag-gui -Hidden
```

### Start The Browser Server

Run:

```powershell
rag-server
```

You can override the bind settings:

```powershell
rag-server -Host 127.0.0.1 -Port 8000
```

After startup, open:

- `http://127.0.0.1:8000/dashboard`
- `http://127.0.0.1:8000/admin`

## Online Mode Workflow

### Store Credentials

Run:

```powershell
rag-store-key
rag-store-endpoint
```

Then confirm:

```powershell
rag-cred-status
```

### Switch Online

Run:

```powershell
rag-mode-online
```

What it does:

- checks that the key and endpoint exist
- writes `mode=online`
- keeps the network gate constrained to the configured endpoint

To go back:

```powershell
rag-mode-offline
```

### Test The Online Path

Run:

```powershell
rag-test-api
```

This sends one real request, so use it only when you actually want to validate the remote endpoint.

## Profile Workflow

Check the current profile:

```powershell
rag-profile
```

Switch profiles:

```powershell
rag-profile laptop_safe
rag-profile desktop_power
rag-profile server_max
```

Profile changes are useful when:

- indexing or querying is too heavy for a small laptop
- a workstation can support larger batch sizes
- you want predictable behavior across machines

## Operator-Only Shared Launch Tooling

The standard `rag-*` shell commands do not cover every shared deployment action. For shared launch posture, use the explicit preflight tool:

```powershell
python tools/shared_launch_preflight.py
```

Useful variants:

```powershell
python tools/shared_launch_preflight.py --json
python tools/shared_launch_preflight.py --fail-if-blocked
python tools/shared_launch_preflight.py --apply-online --apply-production
python tools/shared_launch_preflight.py --prompt-shared-token
```

Use this tool when you need to:

- verify shared launch readiness
- persist `online` and `production` posture
- prompt for the shared deployment token
- fail closed before a live shared soak or cutover step

## Troubleshooting

| Symptom | First move |
|---|---|
| `rag-query` or another command is not found | re-run `. .\start_hybridrag.ps1` in the current shell |
| `rag-mode-online` says credentials are missing | run `rag-store-key`, `rag-store-endpoint`, then `rag-cred-status` |
| `rag-query` returns poor or empty answers | confirm the source folder is correct, then rerun `rag-index` |
| `rag-server` starts but browser pages are blocked | check auth posture and shared token requirements |
| `rag-test-api` fails | verify the endpoint, key, and network policy |
| `rag-gui` launches but the app is not ready yet | wait for backend loading to complete |

## Printable Format

The Word-format copy of this guide lives at:

- `docs/03_guides/CLI_GUIDE.docx`
