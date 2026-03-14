# HybridRAG3 GUI Guide

**Created:** 2026-03-13  
**Last updated:** 2026-03-13 14:15 America/Denver  
**Purpose:** explain the current desktop GUI and shared browser GUI surfaces for operators and daily users.

## Scope

This guide covers two visual interfaces:

- the desktop tkinter application launched from `src/gui/launch_gui.py`
- the shared browser dashboard and admin console served by `rag-server`

If you want the PowerShell command flow instead, use [CLI_GUIDE.md](CLI_GUIDE.md).

## Launch The Desktop GUI

Recommended launcher:

```bat
start_gui.bat
```

Detached launcher:

```bat
start_gui.bat --detach
```

These are the preferred everyday launch paths because the batch launcher:

- resolves the repo root from the launcher location
- validates the local `.venv`
- sets `HYBRIDRAG_PROJECT_ROOT`
- gives plain-English startup errors if the GUI cannot boot

From the repo root after loading the environment:

```powershell
. .\start_hybridrag.ps1
rag-gui
```

You can also launch it directly:

```powershell
python src/gui/launch_gui.py
```

What to expect:

1. the window appears quickly
2. heavy backends continue loading in the background
3. querying and indexing are fully ready only after backend attach completes

If the machine is slow, give the GUI a short warm-up period before the first query.

Printable Word copy of this guide:

- `docs/_printable/21_GUI_Guide.docx`

## Desktop Window Map

The current desktop shell is organized like this:

1. Menu bar: `File | View | Admin | Help`
2. Title bar: app title, `OFFLINE` / `ONLINE` toggle, theme toggle
3. Nav bar: view tabs such as `Query`, `Index`, `Cost`, `Admin`, `Command Center`, `Reference`, and `Settings`
4. Main content area: the active view
5. Status bar: model, Ollama/runtime state, and gate mode

An optional `Downloader (Data)` tab may appear when that module is available in the current checkout.

## Title Bar Controls

### Mode Toggle

- `OFFLINE` keeps generation local
- `ONLINE` uses the configured API endpoint

Use offline when data must stay local or the machine has no working API credentials. Use online when you want faster remote generation and credentials are already configured.

### Theme Toggle

The desktop app supports dark and light themes. The theme switch updates the window in place without relaunching the app.

## Query View

Use the `Query` view for normal question answering.

Typical workflow:

1. choose the use case or role that best matches the question
2. confirm the current mode in the title bar
3. type the question
4. submit it
5. review the answer, sources, and metrics

What the view is for:

- daily document question answering
- citation review
- quick answer checks after indexing or tuning

## Index View

Use the `Index` view to point HybridRAG3 at a document folder and build or refresh the local search database.

Typical workflow:

1. browse to the source folder
2. click `Start Indexing`
3. monitor progress and last-run status
4. use `Stop` only if you need a cooperative stop after the current file

Use this view when:

- a new machine has never been indexed
- the source corpus changed
- answers are clearly missing documents that should be present

## Cost View

Use the `Cost` view for online-usage visibility.

It is most useful for:

- session cost monitoring
- cumulative spend review
- rate changes when the provider pricing changes
- export of usage data for reporting

Offline usage remains free and is shown separately from online activity.

## Admin View

Use the `Admin` view for the technical controls that should not live in the normal query path.

Current responsibilities include:

- API credential status and connectivity checks
- security and privacy controls
- online endpoint and model setup
- runtime and troubleshooting surfaces
- retrieval and trace visibility
- profile/default controls

This is the view to open when the desktop app is healthy enough to run, but the online path, auth posture, or runtime configuration needs inspection.

## Command Center

The `Command Center` is the bridge between CLI workflows and the GUI.

Use it when you want GUI access to command-line tasks such as:

- `rag-query`
- `rag-index`
- `rag-mode-online`
- `rag-mode-offline`
- `rag-profile`
- `rag-status`
- `rag-diag`
- `rag-server`
- `rag-shared-launch` readiness checks

Important behavior:

- native GUI workflows are reused where they already exist
- CLI-style processes stream their output in the panel
- long-running commands can be stopped from the same screen

This is the fastest GUI route for operators who know the CLI names already.

## Reference View

The `Reference` view is the embedded documentation shelf inside the desktop app.

Use it when you need:

- shortcut sheets
- architecture notes
- security notes
- demo prep notes
- embedded help without leaving the app

## Settings View

Use the `Settings` view for lightweight system and environment information:

- current mode
- offline model
- Python and OS details
- project/config/database path visibility
- backend reset action

This is the safest view for simple "what machine am I actually running on?" checks.

## Menu Bar

### File

- `Exit` closes the desktop app

### View

- zoom presets change UI scale for readability and projector use

### Admin

- `Open Admin Tab` jumps straight to the Admin view
- `Reference` jumps to the embedded docs
- `Production API Auth Guard` toggles development vs production guard posture for the API auth requirement

### Help

- `About` shows the app summary

## Shared Browser GUI

The browser surfaces are separate from the desktop app. They are served by the FastAPI server.

Start them with:

```powershell
rag-server
```

Then open:

- `http://127.0.0.1:8000/dashboard`
- `http://127.0.0.1:8000/admin`

### Dashboard

Use `/dashboard` for the shared user-facing browser console. It is designed for:

- browser-based query access
- shared deployment status visibility
- team-friendly query history and queue awareness

If shared auth is configured, `/dashboard` redirects through `/auth/login`.

### Admin Console

Use `/admin` for operator-only browser controls. It is designed for:

- runtime safety review
- alerts and freshness checks
- queue pressure and activity inspection
- indexing controls and admin-only diagnostics

When shared auth is enabled, the browser actor must resolve to the `admin` role to open this page.

## Common GUI Workflows

### Ask A Question In The Desktop App

1. open the `Query` view
2. choose `OFFLINE` or `ONLINE`
3. type the question
4. submit
5. review sources and metrics before trusting the answer

### Go Online From The Desktop App

1. open `Admin` or `Command Center`
2. confirm the API key and endpoint are stored
3. switch the title bar to `ONLINE`
4. run a simple test question

### Start Shared Browser Use

1. run `rag-server`
2. open `/dashboard`
3. verify `/admin` only from an admin-authorized actor
4. monitor queue and status during use

## Troubleshooting

| Symptom | What it usually means | First move |
|---|---|---|
| GUI opens but query buttons feel dead | backend attach is still in progress | wait, then retry |
| `ONLINE` refuses to stay active | credentials or mode guard failed | use Admin or Command Center to inspect auth and endpoint posture |
| Browser dashboard redirects to login | shared token auth is enabled | complete the login flow or use the required auth header |
| Browser admin returns 403 | actor is authenticated but not admin | check role mapping or use an admin account/token |
| Indexing appears stalled | large files or slow embedding path | let the current file finish before assuming a hang |
| Command Center process exits nonzero | underlying CLI tool failed | read the streamed output in the panel and fix that command path directly |

## Printable Format

The Word-format copy of this guide lives at:

- `docs/_printable/21_GUI_Guide.docx`
