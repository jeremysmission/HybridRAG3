# Manual Install Guide

Step-by-step commands for installing HybridRAG3 by hand. Use this if
INSTALL.bat fails, if you need to troubleshoot a specific step, or if
you want to understand exactly what the automated installer does.

Two sections: **Work/Educational** (enterprise laptop with proxy/Group Policy)
and **Home/Personal** (unrestricted machine). Pick the one that matches your
environment.

---

## Important Historical Note (2026-03-01 / 2026-03-02)

Parser coverage regression was found and fixed:
- Config allowlist drifted from parser registry
- Parser dependencies were incomplete
- OCR system binaries were missing on some machines

Guardrails now added:
- `tests/test_indexing_allowlist_sync.py`
- `tests/test_parser_coverage_guard.py`
- Registry-based fallback in `src/core/indexer.py`

Postmortem:
- `docs/ClaudeCLI_Codex_Collabs/003_parser_coverage_gap_analysis.md`

---

## Prerequisites (both environments)

1. **Python 3.12** installed and on PATH
2. **Ollama** installed and running (`ollama serve`)
3. **Ollama models pulled:**
   ```
   ollama pull nomic-embed-text
   ollama pull phi4-mini
   ```

Verify Python:
```
py -3.12 --version
```
If `py` is not recognized, try `python --version` and confirm it says 3.12.x.

---

## Section A: Work / Educational Environment

Open **PowerShell** (regular user, not admin). Every command below is typed
into that same PowerShell window, in order.

### A1. Group Policy bypass (allow scripts for this session only)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
```

If this errors with "access denied", your Group Policy is strict. Instead,
launch PowerShell from cmd with the bypass flag:

```
powershell -ExecutionPolicy Bypass -NoProfile
```

### A2. Set UTF-8 encoding (prevents garbled characters)

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

### A3. Navigate to project root

```powershell
cd "D:\HybridRAG3"
```

Replace with your actual path. Verify you see `requirements_approved.txt`:

```powershell
Test-Path requirements_approved.txt
```

Should return `True`.

### A4. Create virtual environment

```powershell
py -3.12 -m venv .venv
```

Verify it worked:

```powershell
Test-Path .venv\Scripts\python.exe
```

### A5. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

Your prompt should now show `(.venv)` at the beginning.

### A6. Detect proxy (work networks only)

Check if your machine has a system proxy:

```powershell
(Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings").ProxyServer
```

If that returns a value like `proxy.company.com:8080`, set it:

```powershell
$env:HTTP_PROXY  = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"
$env:NO_PROXY    = "localhost,127.0.0.1"
```

Replace `proxy.company.com:8080` with whatever the command above returned.

If the command returned blank/nothing, skip this step (no proxy).

### A7. Create pip.ini (proxy-safe pip defaults)

```powershell
$pipIniContent = @"
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
timeout = 120
retries = 3
"@
```

If you set a proxy in A6, add it:

```powershell
$pipIniContent += "`nproxy = $($env:HTTPS_PROXY)"
```

Write the file (BOM-safe for Python):

```powershell
[System.IO.File]::WriteAllText("$PWD\.venv\pip.ini", $pipIniContent)
```

Verify pip can read it:

```powershell
python -m pip config list
```

You should see your trusted-host and timeout values.

### A8. Upgrade pip

```powershell
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

### A9. Install pip-system-certs (corporate SSL)

This makes Python trust certificates in the Windows certificate store,
which corporate proxies use for SSL inspection:

```powershell
pip install pip-system-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

### A10. Install packages (grouped for proxy resilience)

Work environments install in small groups so if the proxy drops a
connection you know exactly which group failed. Run each block one at a time.

**Group 7A -- Config basics:**
```powershell
pip install pyyaml==6.0.2 numpy==1.26.4 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7B -- Typing support:**
```powershell
pip install typing_extensions==4.15.0 annotated-types==0.7.0 typing-inspection==0.4.2 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7C -- Data validation:**
```powershell
pip install pydantic==2.11.1 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7D -- HTTP async:**
```powershell
pip install httpx==0.28.1 sniffio==1.3.1 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7E -- HTTP sync:**
```powershell
pip install requests==2.32.5 urllib3==2.6.3 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7F -- Encryption:**
```powershell
pip install cryptography==44.0.2 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7G -- PDF parsing:**
```powershell
pip install pdfplumber==0.11.9 pdfminer.six==20251230 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7H -- PDF utilities:**
```powershell
pip install pypdf==6.6.2 pypdfium2==5.3.0 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7I -- Office documents:**
```powershell
pip install python-docx==1.2.0 python-pptx==1.0.2 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7J -- Excel support:**
```powershell
pip install openpyxl==3.1.5 xlsxwriter==3.2.9 et_xmlfile==2.0.0 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7K -- XML, images, and OCR bridge:**
```powershell
pip install lxml==6.0.2 pillow==12.1.0 pdf2image==1.17.0 pytesseract==0.3.13 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7L -- Web framework:**
```powershell
pip install fastapi==0.115.0 starlette==0.38.6 python-multipart==0.0.22 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7M -- Web server:**
```powershell
pip install uvicorn==0.41.0 click==8.3.1 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7N -- Credential storage:**
```powershell
pip install keyring==23.13.1 jaraco.classes==3.4.0 more-itertools==10.8.0 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7O -- Utilities:**
```powershell
pip install structlog==24.4.0 rich==13.9.4 tqdm==4.67.3 regex==2026.1.15 colorama==0.4.6 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7P -- AI core (install last, no-deps to avoid conflicts):**
```powershell
pip install openai==1.109.1 tiktoken==0.8.0 --no-deps --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

**Group 7R -- Extended parser dependencies (added 2026-03-02):**
```powershell
pip install olefile==0.47 ezdxf==1.4.3 python-evtx==0.8.1 python-oxmsg==0.0.2 dpkt==1.9.8 psd-tools==1.13.1 striprtf==0.0.29 numpy-stl==3.2.0 vsdx==0.6.1 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```
Without these, .doc, .msg, .dxf, .evtx, .pcap, .psd, .rtf, .stl, and .vsdx files
silently return empty text during indexing. See `docs/ClaudeCLI_Codex_Collabs/003_parser_coverage_gap_analysis.md`.

**Group 7Q -- Final dependency check (catches anything the groups missed):**
```powershell
pip install -r requirements_approved.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

### A11. Install test tools (optional but recommended)

```powershell
pip install pytest==9.0.2 psutil==7.2.2 --trusted-host pypi.org --trusted-host files.pythonhosted.org --timeout 120 --retries 3
```

### A12. Configure default_config.yaml

Set your paths. Replace the example paths with your actual directories:

```powershell
$configPath = "config\default_config.yaml"
$content = Get-Content $configPath -Raw -Encoding UTF8

$content = $content -replace '(?m)^(\s*database:\s*).*$', '$1D:\RAG Indexed Data\hybridrag.sqlite3'
$content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', '$1D:\RAG Indexed Data\_embeddings'
$content = $content -replace '(?m)^(\s*source_folder:\s*).*$', '$1D:\RAG Source Data'

[System.IO.File]::WriteAllText("$PWD\$configPath", $content)
```

**Important:** Use `[System.IO.File]::WriteAllText()` -- not `Set-Content`.
PowerShell 5.1's `Set-Content -Encoding UTF8` writes a BOM that breaks Python's
YAML parser.

### A13. Create start script from template

```powershell
$content = Get-Content "start_hybridrag.ps1.template" -Raw -Encoding UTF8
$content = $content -replace 'C:\\path\\to\\HybridRAG3', 'D:\HybridRAG3'
$content = $content -replace 'C:\\path\\to\\data', 'D:\RAG Indexed Data'
$content = $content -replace 'C:\\path\\to\\source_docs', 'D:\RAG Source Data'
Set-Content -Path "start_hybridrag.ps1" -Value $content -Encoding UTF8
```

Replace the paths above with your actual directories.

### A14. Store API credentials (optional)

Store the Azure OpenAI endpoint:

```powershell
python tools/py/store_endpoint.py "https://your-resource.openai.azure.com"
```

Store the API key (passed via env var, not command line, for security):

```powershell
$env:HYBRIDRAG_API_KEY = "your-api-key-here"
python tools/py/store_key.py
$env:HYBRIDRAG_API_KEY = $null
```

Both are stored in Windows Credential Manager.

### A15. Verify Ollama

```powershell
$env:NO_PROXY = "localhost,127.0.0.1"
Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Proxy ([System.Net.WebProxy]::new())
```

You should see a list of models including `nomic-embed-text`.

Note: The `-Proxy ([System.Net.WebProxy]::new())` creates an empty proxy
object so PowerShell does not route localhost through the corporate proxy.

### A16. Run diagnostics

Verify imports:

```powershell
python -c "import fastapi; print('fastapi OK')"
python -c "import httpx; print('httpx OK')"
python -c "import openai; print('openai OK')"
python -c "import pydantic; print('pydantic OK')"
python -c "import numpy; print('numpy OK')"
python -c "import yaml; print('yaml OK')"
python -c "import uvicorn; print('uvicorn OK')"
python -c "import cryptography; print('cryptography OK')"
```

Boot test:

```powershell
python -c "from src.core.config import Config; c = Config(); print('Config OK')"
```

Full regression tests:

```powershell
python -m pytest tests/ --ignore=tests/test_fastapi_server.py --tb=short
```

---

## Section B: Home / Personal Environment

Open **PowerShell**. No Group Policy bypass needed on personal machines.

### B1. Set UTF-8 encoding

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

### B2. Navigate to project root

```powershell
cd "D:\HybridRAG3"
```

Verify you see `requirements.txt`:

```powershell
Test-Path requirements.txt
```

### B3. Create virtual environment

```powershell
py -3.12 -m venv .venv
```

Verify:

```powershell
Test-Path .venv\Scripts\python.exe
```

### B4. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### B5. Upgrade pip

```powershell
python -m pip install --upgrade pip
```

### B6. Install all packages (single command)

Home machines have direct internet access, so bulk install works fine:

```powershell
pip install -r requirements.txt
```

If this fails partway through, just run it again. pip resumes from its
download cache.

### B7. Configure default_config.yaml

```powershell
$configPath = "config\default_config.yaml"
$content = Get-Content $configPath -Raw -Encoding UTF8

$content = $content -replace '(?m)^(\s*database:\s*).*$', '$1D:\RAG Indexed Data\hybridrag.sqlite3'
$content = $content -replace '(?m)^(\s*embeddings_cache:\s*).*$', '$1D:\RAG Indexed Data\_embeddings'
$content = $content -replace '(?m)^(\s*source_folder:\s*).*$', '$1D:\RAG Source Data'

[System.IO.File]::WriteAllText("$PWD\$configPath", $content)
```

Replace paths with your actual directories.

### B8. Configure start_hybridrag.ps1

```powershell
$content = Get-Content "start_hybridrag.ps1" -Raw -Encoding UTF8
$content = $content -replace '(?m)^\$DATA_DIR\s*=\s*"[^"]*"', '$DATA_DIR   = "D:\RAG Indexed Data"'
$content = $content -replace '(?m)^\$SOURCE_DIR\s*=\s*"[^"]*"', '$SOURCE_DIR = "D:\RAG Source Data"'
Set-Content -Path "start_hybridrag.ps1" -Value $content -Encoding UTF8
```

### B9. Create directories and logs folder

```powershell
New-Item -ItemType Directory -Path "D:\RAG Indexed Data" -Force | Out-Null
New-Item -ItemType Directory -Path "D:\RAG Source Data" -Force | Out-Null
New-Item -ItemType Directory -Path "logs" -Force | Out-Null
```

### B10. Verify Ollama

```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
```

You should see `nomic-embed-text` and `phi4-mini` in the model list.

### B11. Run diagnostics

Verify imports:

```powershell
python -c "import fastapi; print('fastapi OK')"
python -c "import httpx; print('httpx OK')"
python -c "import openai; print('openai OK')"
python -c "import pydantic; print('pydantic OK')"
python -c "import numpy; print('numpy OK')"
python -c "import yaml; print('yaml OK')"
python -c "import uvicorn; print('uvicorn OK')"
python -c "import cryptography; print('cryptography OK')"
python -c "import pytest; print('pytest OK')"
```

Boot test:

```powershell
python -c "from src.core.config import Config; c = Config(); print('Config OK')"
```

Full regression tests:

```powershell
python -m pytest tests/ --ignore=tests/test_fastapi_server.py --tb=short
```

---

## Starting HybridRAG3

After install, start the app with any of these methods:

**Double-click** (easiest):
```
start_gui.bat
```

**From CMD:**
```
cd /d D:\HybridRAG3
.venv\Scripts\activate.bat
python src/gui/launch_gui.py
```

**From PowerShell:**
```powershell
cd D:\HybridRAG3
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
. .\start_hybridrag.ps1
```

---

## Troubleshooting (Work Environment -- Section A only)

### "Running scripts is disabled on this system"

Group Policy is blocking PowerShell scripts. Use the bypass:

```
powershell -ExecutionPolicy Bypass -NoProfile
```

Then retry from step A1.

### pip timeout or connection reset

Your proxy is dropping the connection. Make sure A6 and A7 are done
(proxy env vars and pip.ini). Then retry the failed package with longer
timeout:

```powershell
pip install <package>==<version> --timeout 120 --retries 10 --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

### "SSL: CERTIFICATE_VERIFY_FAILED"

SSL inspection is intercepting the connection. Install pip-system-certs
(step A9) and make sure your pip.ini has trusted-host entries (step A7).

---

## Troubleshooting (Both Environments)

### Import fails after install

The package may have installed but a dependency is missing. Install the
specific package again without `--no-deps`:

```powershell
pip install <package>==<version>
```

### YAML config breaks after editing

If you used `Set-Content -Encoding UTF8` to write the YAML file, it has a
BOM (Byte Order Mark) that Python cannot parse. Fix:

```powershell
$content = Get-Content config\default_config.yaml -Raw -Encoding UTF8
[System.IO.File]::WriteAllText("$PWD\config\default_config.yaml", $content)
```

This reads the file and rewrites it without BOM.

### Ollama not responding

Make sure Ollama is running:

```
ollama serve
```

Then pull the required models:

```
ollama pull nomic-embed-text
ollama pull phi4-mini
```
