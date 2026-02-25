# HybridRAG3 -- Installation and Setup Guide

Last Updated: 2026-02-24

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10 or 11 |
| **Python** | 3.11 or 3.12 (work laptop: 3.12rc3 approved) |
| **Disk** | ~1 GB minimum (venv + Ollama models separate) |
| **RAM** | 8 GB minimum, 16 GB recommended |
| **GPU** | Optional (CPU works fine, GPU speeds up offline LLM) |

**Optional software:**

| Software | Purpose | License |
|----------|---------|---------|
| Ollama | Offline LLM inference + embeddings | MIT |
| Tesseract OCR | Image text extraction | Apache 2.0 |

---

## Part 1: Fresh Installation

### Step 1 -- Get the Project Files

**Home PC (with Git):**

```powershell
cd "D:\"
git clone https://github.com/jeremysmission/HybridRAG3.git
cd HybridRAG3
```

**Work PC (ZIP download only -- no Git):**

1. Open browser to the Educational repo on GitHub
2. Click **Code** then **Download ZIP**
3. Extract to `D:\HybridRAG3`

### Step 2 -- Create Virtual Environment

```powershell
cd "D:\HybridRAG3"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If you have Python 3.11 instead of 3.12, use `py -3.11` in the command above.

If the activate script fails with an execution policy error:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### Step 3 -- Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This downloads ~200 MB of packages. Takes 2-5 minutes depending on
internet speed. (PyTorch/HuggingFace were removed -- embeddings are
now served by Ollama.)

**Enterprise proxy / SSL certificate errors:**

If your corporate proxy intercepts HTTPS and pip fails with certificate
errors (common on managed laptops), use the `--trusted-host` flags:

```powershell
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

For a permanent fix (no flags needed on every install), create or edit
`%APPDATA%\pip\pip.ini`:

```ini
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
```

If pip.ini does not work (some proxies are stricter), ask IT for the
enterprise root CA bundle (.crt or .pem file) and set:

```powershell
$env:SSL_CERT_FILE = 'C:\path\to\enterprise-ca-bundle.crt'
$env:REQUESTS_CA_BUNDLE = 'C:\path\to\enterprise-ca-bundle.crt'
```

**Common install issues:**

| Problem | Fix |
|---------|-----|
| `py -3.12` not found | Install Python 3.11 or 3.12 from your software portal. Check "Add to PATH" during install. Verify with `py --list`. |
| Activate.ps1 blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| pip access denied | Run `python -m ensurepip --upgrade` first |
| numpy install fails | Verify requirements.txt has `numpy==1.26.4` |
| SSL certificate error | Use `--trusted-host` flags (see above) or set `SSL_CERT_FILE` env var |

### Step 4 -- Configure Machine-Specific Paths

Open `start_hybridrag.ps1` in a text editor and update these two lines
to match your machine:

```powershell
$DATA_DIR   = "D:\RAG Indexed Data"     # Where the search database goes
$SOURCE_DIR = "D:\RAG Source Data"       # Where your documents are
```

Create both folders if they do not exist yet. These folders live outside
the project directory so they are never affected by code updates.

**WARNING**: These paths are different on every machine. Do NOT copy
`start_hybridrag.ps1` between machines without updating them.

### Step 5 -- Launch the Environment

```powershell
. .\start_hybridrag.ps1
```

**Important**: Use dot-space (`. .`) to source the script in the current
shell. Running it without the dot (just `.\start_hybridrag.ps1`) will
not load the commands into your session.

Expected output:
- Python version confirmation
- Network lockdown status (all blocked)
- Configured paths
- List of available commands
- "API + Profile Commands loaded"

### Step 6 -- Run Diagnostics

```powershell
rag-diag
```

On a fresh install, most tests should pass. You may see:
- Embedding model: "use --test-embed for live test" (normal -- model
  downloads on first real use)
- Ollama: "not running" (normal if Ollama is not installed yet)

### Step 7 -- Index Your Documents

```powershell
rag-index
```

Ollama must be running with `nomic-embed-text` pulled before indexing.
The indexer sends text to Ollama for embedding, then stores vectors
locally.

**First-run timing**: ~1,345 files / ~40,000 chunks takes a few hours
on a laptop. After that, only new or changed files are re-indexed
(seconds).

---

## Part 2: Ollama Setup (Offline LLM Mode)

Ollama runs AI models locally so you can generate answers without
internet access.

### Install Ollama

Download from https://ollama.com and run the installer.

### Pull Approved Models

Open a **separate terminal** and pull the embedding model (required) plus
the LLM models you need:

```powershell
ollama pull nomic-embed-text   # 274 MB -- REQUIRED for all indexing/search
ollama pull phi4-mini          # 2.3 GB -- primary LLM (recommended)
ollama pull mistral:7b         # 4.1 GB -- engineering alternate
```

**IMPORTANT**: `nomic-embed-text` is required. Without it, indexing and
search will not work. The LLM models are for answer generation.

**Full workstation stack** (all five approved LLM models + embedder, ~26 GB total):

| Model | Size | Publisher | License | Best For |
|-------|------|-----------|---------|----------|
| nomic-embed-text | 274 MB | Nomic AI | Apache 2.0 | **Embeddings (required)** |
| phi4-mini | 2.3 GB | Microsoft | MIT | Default for 7 of 9 profiles |
| mistral:7b | 4.1 GB | Mistral AI | Apache 2.0 | Engineering, cyber, systems |
| phi4:14b-q4_K_M | 9.1 GB | Microsoft | MIT | Logistics, CAD |
| gemma3:4b | 3.3 GB | Google | Apache 2.0 | PM summarization |
| mistral-nemo:12b | 7.1 GB | Mistral/NVIDIA | Apache 2.0 | Long-context (128K) |

### Start Ollama

```powershell
ollama serve
```

Leave this terminal open. Ollama must be running for offline queries
to work.

### Verify

```powershell
curl http://localhost:11434/api/tags
```

You should see a JSON list of your pulled models.

---

## Part 3: API Credentials (Online Mode -- Optional)

Online mode sends queries to a cloud API for faster, higher-quality
answers. Credentials are encrypted and stored in Windows Credential
Manager.

### Store Your API Key

```powershell
rag-store-key
```

You are prompted to enter the key. Input is hidden (not echoed). The
key is encrypted with Windows DPAPI and tied to your Windows login.

### Store the Endpoint URL

```powershell
rag-store-endpoint
```

Enter the endpoint URL for your API provider (e.g.,
`https://openrouter.ai/api/v1` or your company's Azure endpoint).

### Verify Credentials

```powershell
rag-cred-status
```

Shows a masked preview of stored credentials:

```
API Key:       SET (source: keyring)     sk-abc1...wxyz
API Endpoint:  SET (source: keyring)     https://openrouter.ai/api/v1
Deployment:    NOT SET
API Version:   NOT SET
```

### Test Connectivity

```powershell
rag-test-api
```

Sends one test prompt to the API and reports success or failure with
latency and cost estimate.

### Switch to Online Mode

```powershell
rag-mode-online
```

To switch back:

```powershell
rag-mode-offline
```

---

## Part 4: Performance Profiles

Three profiles adapt the system to different hardware.

| Profile | RAM | Batch Size | Search top_k | Use Case |
|---------|-----|-----------|-------------|----------|
| `laptop_safe` | 8-16 GB | 16 | 5 | Default. Slow but stable. |
| `desktop_power` | 32-64 GB | 64 | 10 | Faster indexing and search. |
| `server_max` | 64+ GB | 128 | 15 | Maximum throughput. |

### Check Current Profile

```powershell
rag-profile
```

### Switch Profile

```powershell
rag-profile laptop_safe
rag-profile desktop_power
rag-profile server_max
```

The system auto-detects your hardware on first run and writes a
recommendation to `config/system_profile.json`.

---

## Part 5: Environment Variables

`start_hybridrag.ps1` sets these automatically when sourced:

| Variable | Purpose |
|----------|---------|
| `HYBRIDRAG_PROJECT_ROOT` | Project folder path |
| `HYBRIDRAG_INDEX_FOLDER` | Source documents folder |
| `HYBRIDRAG_DATA_DIR` | SQLite + embeddings storage |
| `OLLAMA_HOST` | Ollama server URL (default: http://localhost:11434) |
| `NO_PROXY=localhost,127.0.0.1` | Prevent proxy from intercepting localhost |
| `HYBRIDRAG_NETWORK_KILL_SWITCH=true` | Master network kill switch |

---

## Part 6: Configuration

All settings live in `config/default_config.yaml`. Key sections:

```yaml
mode: offline                        # offline or online

embedding:
  model_name: nomic-embed-text       # Served by Ollama (768 dimensions)
  batch_size: 64                     # Texts per Ollama API call
  device: cpu                        # Unused (Ollama manages device)

chunking:
  chunk_size: 1200                   # Characters per chunk
  overlap: 200                       # Overlap between chunks

retrieval:
  top_k: 12                         # Chunks sent to LLM
  min_score: 0.1                    # Minimum relevance score
  hybrid_search: true               # Vector + BM25 fusion
  reranker_enabled: false           # Keep OFF (see warnings below)

ollama:
  base_url: http://localhost:11434
  model: phi4-mini                  # Which Ollama model to use
  timeout_seconds: 600              # 10 min timeout for CPU inference

api:
  endpoint: ''                       # Set via rag-store-endpoint
  temperature: 0.05                  # Low = deterministic answers
  max_tokens: 2048                   # Max answer length in tokens
```

Any setting can be overridden with an environment variable:
`HYBRIDRAG_<SECTION>_<KEY>` (e.g., `HYBRIDRAG_OLLAMA_MODEL=mistral:7b`).

---

## Part 7: Work Laptop Deployment

Corporate environments often have restricted internet and software
approval requirements.

### Pre-Flight Checklist

- [ ] Python 3.11 or 3.12 installed (`py --list` to check)
- [ ] pip accessible (`python -m pip --version`)
- [ ] PyPI reachable OR wheel bundles prepared
- [ ] D: drive available with write access
- [ ] Browser can reach GitHub (for ZIP download)

### Offline Installation (If PyPI Is Blocked)

**On the home PC** (with internet):

```powershell
pip download -r requirements.txt -d wheels\
```

Transfer the `wheels\` folder to the work laptop via USB.

**On the work laptop:**

```powershell
pip install --no-index --find-links=wheels\ -r requirements_approved.txt
```

**IMPORTANT:** On the work laptop, always use `requirements_approved.txt`
(the software-cleared package list), not `requirements.txt`.

### Air-Gapped Model Caching

Ollama models must be downloaded once. For air-gapped machines, copy
the Ollama model directory from a connected machine:

| Folder | Contents | Size |
|--------|----------|------|
| Ollama model directory | LLM + embedding model files | 2-26 GB |

Ollama stores models in `%USERPROFILE%\.ollama\models` on Windows.

### Machine-Specific Files (Never Sync Between Machines)

| File | Why |
|------|-----|
| `start_hybridrag.ps1` | Contains machine-specific paths |
| `.venv/` | Different Python builds |
| `config/system_profile.json` | Auto-detected hardware fingerprint |
| API credentials | In Windows Credential Manager, per-user |

**Before updating code on a work laptop**, always save
`start_hybridrag.ps1` first, then restore it after extracting the
new ZIP.

---

## Part 8: Updating an Existing Installation

### Home PC (Git)

```powershell
cd "D:\HybridRAG3"
git pull origin main
. .\start_hybridrag.ps1
rag-diag
```

### Work PC (ZIP)

```powershell
# Save machine-specific file
Copy-Item start_hybridrag.ps1 start_hybridrag_KEEP.ps1

# Extract new ZIP over project folder (overwrite all)

# Restore machine-specific file
Copy-Item start_hybridrag_KEEP.ps1 start_hybridrag.ps1 -Force
Remove-Item start_hybridrag_KEEP.ps1

# Verify
. .\start_hybridrag.ps1
rag-diag
```

---

## Part 9: Verification Checklist

After completing installation, run through this checklist:

```
[ ] python --version                      Shows 3.11.x or 3.12.x
[ ] .\.venv\Scripts\Activate.ps1          Activates without error
[ ] . .\start_hybridrag.ps1               Commands load, paths shown
[ ] rag-diag                              Most tests pass
[ ] rag-paths                             Paths correct for this machine
[ ] rag-profile                           Shows a valid profile
[ ] rag-index                             Indexing starts (Ctrl+C to stop early)
[ ] rag-query "test"                      Returns an answer (or "no results")
[ ] rag-cred-status                       Shows credential state
```

Ollama (required for embeddings and offline LLM):

```
[ ] ollama serve                          Starts without error
[ ] ollama pull nomic-embed-text          Embedding model pulled
[ ] curl http://localhost:11434/api/tags  Shows pulled models
[ ] rag-mode-offline                      Sets offline mode
[ ] rag-query "test"                      Gets answer from Ollama
```

If using online API:

```
[ ] rag-store-key                         Stores API key
[ ] rag-store-endpoint                    Stores endpoint
[ ] rag-test-api                          API responds successfully
[ ] rag-mode-online                       Sets online mode
[ ] rag-query "test"                      Gets answer from API
```

---

## Part 10: Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Python not found | Python not installed | Install 3.11 or 3.12 from software portal, check "Add to PATH" |
| `rag-diag` not found | Script not sourced | Run `. .\start_hybridrag.ps1` (dot-space) |
| Execution policy error | PowerShell blocks scripts | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Embedder fails at startup | Ollama not running or model not pulled | Run `ollama serve` and `ollama pull nomic-embed-text` |
| Ollama timeout | Model takes time to load on first query | Default timeout is 600s. Wait or increase `ollama.timeout_seconds`. |
| Corporate proxy blocks Ollama | Proxy intercepting localhost | `start_hybridrag.ps1` sets `NO_PROXY=localhost,127.0.0.1` |
| "Database locked" | Another rag-index process running | Wait for it to finish or kill the process |
| Out of memory during indexing | Batch size too large for RAM | Switch to `laptop_safe` profile |
| Queries return no results | Documents not indexed | Run `rag-index` first |
| Poor answer quality | min_score too low, top_k wrong | Adjust in Admin menu or config |

---

## Quick Reference: All Commands

### Core

```
rag-index              Index documents
rag-query "question"   Ask a question
rag-diag               Run diagnostics (add --verbose, --test-embed)
rag-status             Quick health check
rag-paths              Show configured paths
rag-server             Start REST API server (localhost:8000)
```

### Credentials and Mode

```
rag-store-key          Store API key (encrypted)
rag-store-endpoint     Store API endpoint URL
rag-cred-status        Check credential status
rag-cred-delete        Remove stored credentials
rag-mode-online        Switch to online (API) mode
rag-mode-offline       Switch to offline (Ollama) mode
rag-test-api           Test API connectivity
```

### Profiles

```
rag-profile            Show current profile
rag-profile laptop_safe       8-16 GB RAM
rag-profile desktop_power     32-64 GB RAM
rag-profile server_max        64+ GB RAM
```

### GUI

```
python src/gui/launch_gui.py      Launch desktop GUI (dark/light theme)
.\tools\launch_gui.ps1            Launch desktop GUI (PowerShell)
```

For full GUI documentation, see [GUI_GUIDE.md](GUI_GUIDE.md).

---

## See Also

- [../START_HERE.txt](../START_HERE.txt) -- Plain-language entry point (read this first)
- [USER_GUIDE.md](USER_GUIDE.md) -- Daily use, all commands, tuning, troubleshooting
- [SHORTCUT_SHEET.md](SHORTCUT_SHEET.md) -- Quick reference card
- [GUI_GUIDE.md](GUI_GUIDE.md) -- Graphical interface walkthrough
- [FORMAT_SUPPORT.md](FORMAT_SUPPORT.md) -- All 49+ supported file formats
