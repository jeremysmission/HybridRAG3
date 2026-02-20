# Work Laptop Validation -- Quick Start

**Date**: February 2026
**Hardware target**: 64 GB RAM, 12 GB NVIDIA VRAM

---

## Prerequisites

1. Python 3.10+ installed and on PATH
2. Ollama installed (https://ollama.com)
3. Git (to clone/copy the project)
4. Enterprise VPN connected (for online API tests)

---

## Step 1: Copy Files to Work Laptop

Copy this entire `work_validation/` folder to the work laptop.
If you have the full project, the scripts can also import from `src/`.

---

## Step 2: Setup Models (One Time)

Open PowerShell (elevated):

```powershell
cd work_validation
.\setup_work_models.ps1
```

This will:
- Install Python packages (sentence-transformers, numpy, keyring, httpx)
- Pull 4 Ollama models (~23 GB total download)
- Verify all models are installed

**Estimated time**: 15-30 minutes (depends on download speed)

---

## Step 3: Run Offline Validation

```powershell
python validate_offline_models.py --log offline_results.log
```

This will:
- Test each model against each of 5 work profiles (Engineer, PM, Logistics, CAD, SysAdmin)
- Send a test query per profile and check response quality
- Log [OK]/[FAIL]/[WARN] for each model-profile combination
- Write results to `offline_results.log`

**What to look for**:
- All primary models should show [OK]
- Alt models should show [OK] or [WARN] (keyword matching is approximate)
- [FAIL] means the model did not respond or gave empty output

**Estimated time**: 5-15 minutes (models load on first query)

---

## Step 4: Run Online API Validation

```powershell
python validate_online_api.py --log online_results.log
```

This will:
- Resolve API credentials from Windows Credential Manager or env vars
- Probe the Azure endpoint for available models
- Test confirmed deployments (GPT-3.5 Turbo, GPT-4) with a simple query
- Probe for optional deployments (GPT-4o, etc.)
- Test online/offline mode switching
- Log all results with full error diagnostics

**If you get a 401 error**: The script will print detailed diagnostics including:
- The exact URL that was attempted
- Which auth header was used
- Where the API key came from
- Suggested troubleshooting steps

**Override endpoint**: If the default credential resolution does not find your
work endpoint, pass it explicitly:

```powershell
python validate_online_api.py --endpoint https://your-company.openai.azure.com --log online_results.log
```

---

## Step 5: Review Results

Check the log files for [FAIL] entries:

```powershell
Select-String -Path offline_results.log -Pattern '\[FAIL\]'
Select-String -Path online_results.log -Pattern '\[FAIL\]'
```

---

## Troubleshooting

### Ollama not running
```powershell
ollama serve
```

### Model not found
```powershell
ollama pull qwen3:8b
ollama pull deepseek-r1:8b
ollama pull phi4:14b-q4_K_M
ollama pull gemma3:4b
```

### API key not set
```powershell
# Option 1: Use HybridRAG credential store
python -m src.security.credentials store

# Option 2: Set environment variable
$env:AZURE_OPENAI_API_KEY = "your-key-here"
$env:AZURE_OPENAI_ENDPOINT = "https://your-endpoint.openai.azure.com"
```

### Enterprise SSL/proxy issues
If you see SSL certificate errors, your enterprise proxy may require
a custom CA certificate. Ask IT for the enterprise root CA and set:

```powershell
$env:SSL_CERT_FILE = "C:\path\to\enterprise-ca-bundle.crt"
$env:REQUESTS_CA_BUNDLE = "C:\path\to\enterprise-ca-bundle.crt"
```

---

## Model Summary

| Model              | Size   | Profiles Using It           |
|--------------------|--------|------------------------------|
| qwen3:8b           | 5.2 GB | Primary: eng, pm, draft, sys |
| deepseek-r1:8b     | 5.2 GB | Alt: eng, sys (reasoning)    |
| phi4:14b-q4_K_M    | 9.1 GB | Primary: log; Alt: draft, eng|
| gemma3:4b          | 3.3 GB | Alt: pm (fast summarization) |

Total disk: ~23 GB
