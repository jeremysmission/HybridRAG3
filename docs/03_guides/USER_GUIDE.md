# HybridRAG3 User Guide

**Created:** 2026-03-13  
**Last updated:** 2026-03-13 14:15 America/Denver  
**Purpose:** one landing guide for everyday HybridRAG3 users across the CLI, desktop GUI, and shared browser surfaces.

## Start Here

Use this page as the front door. Then jump to the guide that matches how you work:

- [CLI Guide](CLI_GUIDE.md) for PowerShell-first use, automation, diagnostics, and operator commands
- [GUI Guide](GUI_GUIDE.md) for the desktop application, Command Center, and browser dashboard/admin surfaces
- [INSTALL_AND_SETUP.md](../01_setup/INSTALL_AND_SETUP.md) if this machine is not ready yet
- [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) if you want the outcome-based learning sequence instead of ad hoc reference reading

Printable copies are also available:

- `USER_GUIDE.docx`
- `CLI_GUIDE.docx`
- `GUI_GUIDE.docx`
- numbered packet copies also exist for the landing and GUI guides:
  - `docs/_printable/20_User_Guide.docx`
  - `docs/_printable/21_GUI_Guide.docx`

## Which Interface To Use

| Interface | Use it when | Start with |
|---|---|---|
| CLI | You want the fastest path, exact commands, diagnostics, or scripting | `. .\start_hybridrag.ps1` |
| Desktop GUI | You want a visual workflow for questions, indexing, tuning, and cost review | `start_gui.bat` or `start_gui.bat --detach` |
| Browser dashboard | You are running the shared FastAPI server for browser users | `rag-server`, then open `/dashboard` or `/admin` |

## Five-Minute Quick Start

1. Open PowerShell and go to the repo:

```powershell
cd "D:\HybridRAG3"
```

2. Load the HybridRAG shell commands:

```powershell
. .\start_hybridrag.ps1
```

3. Verify the machine is healthy:

```powershell
rag-status
```

4. Build or refresh the search index:

```powershell
rag-index
```

5. Pick your interface:

- CLI:

```powershell
rag-query "What changed in the launch checklist?"
```

- Desktop GUI:

```bat
start_gui.bat
```

Detached launch:

```bat
start_gui.bat --detach
```

PowerShell users can also launch the desktop app with:

```powershell
rag-gui
```

- Shared browser GUI:

```powershell
rag-server
```

Then browse to:

- `http://127.0.0.1:8000/dashboard`
- `http://127.0.0.1:8000/admin`

## Shared Concepts

### Offline vs Online

- `offline` keeps generation local through Ollama or local runtime surfaces
- `online` uses the configured API endpoint
- the same indexed document store is used in both modes
- switching modes changes generation behavior, not your indexed corpus

### You Must Index Before Querying

If the database is empty, both the CLI and GUI will return weak or empty results. The first real workflow on a new machine is:

```powershell
rag-index
```

### Credentials Matter Only For Online Mode

These commands are the normal online setup path:

```powershell
rag-store-key
rag-store-endpoint
rag-cred-status
rag-mode-online
```

If you stay offline, you do not need API credentials.

### Grounding and Creativity (Online Mode)

When using online API mode, two knobs control the balance between accuracy and creativity:

- **Accuracy-first** (grounding_bias=9, open_knowledge=OFF, temp=0.03): best for real-time Q&A. Zero hallucinations; may refuse broad creative queries.
- **Creativity-first** (grounding_bias=6, open_knowledge=ON, temp=0.15): best for report generation and synthesis. Always attempts answers; outputs should be human-reviewed.

See [AUTOTUNE_CHEAT_SHEET.md](AUTOTUNE_CHEAT_SHEET.md) for full per-query-type recommendations and [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) Section 6 for the quick reference table.

### Profiles Affect Performance, Not Permissions

Use profiles to match the machine:

```powershell
rag-profile laptop_safe
rag-profile desktop_power
rag-profile server_max
```

## Common Tasks

| Task | CLI | GUI |
|---|---|---|
| Ask a question | `rag-query "question"` | Query view -> type question -> Ask |
| Index documents | `rag-index` | Index view -> Browse -> Start Indexing |
| Switch to online | `rag-mode-online` | Title bar -> `ONLINE` |
| Switch to offline | `rag-mode-offline` | Title bar -> `OFFLINE` |
| Check health | `rag-status` or `rag-diag` | Status bar, Cost view, Admin view, or Command Center |
| Store API credentials | `rag-store-key` and `rag-store-endpoint` | Admin view or Command Center |
| Launch another GUI window | `rag-gui` | not needed; already in GUI |
| Start the browser surfaces | `rag-server` | Command Center -> `rag-server` |

## Recommended Reading Order

1. [CLI Guide](CLI_GUIDE.md) if you are learning the core commands first
2. [GUI Guide](GUI_GUIDE.md) if you will work mainly from the desktop app
3. [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) for a fast reference card after you know the basics
4. [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) if you want the full repo-first curriculum
5. [GLOSSARY.md](GLOSSARY.md) if you need the plain-English definitions for terms like RAG, chunk, BM25, and token

## Troubleshooting Shortlist

| Symptom | First move |
|---|---|
| `rag-*` command is not recognized | Re-run `. .\start_hybridrag.ps1` in the current PowerShell window |
| GUI opens but querying is not ready | Wait for backend attach to finish, then retry |
| Online mode will not enable | Run `rag-cred-status`, then store the missing key or endpoint |
| Answers have no useful sources | Run `rag-index` again and confirm the source folder is correct |
| Browser dashboard does not load | Start `rag-server` first, then open `/dashboard` |
| Admin browser page denies access | Shared auth or role mapping is blocking you; use the shared deployment token/login path |

## Printable Format

If you need Word-format copies for review or handoff, use the generated `.docx` files next to the markdown guides:

- `USER_GUIDE.docx`
- `CLI_GUIDE.docx`
- `GUI_GUIDE.docx`

Additional numbered packet copies also exist for the landing guide and GUI guide:

- `docs/_printable/20_User_Guide.docx`
- `docs/_printable/21_GUI_Guide.docx`
