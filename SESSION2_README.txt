# ===========================================================================
# SESSION 2 HANDOVER — AZURE API FIX
# ===========================================================================
# Date: February 11, 2026
# Status: Tools ready, deploy and test tomorrow
# ===========================================================================

## WHAT HAPPENED TODAY

1. Downloaded Session 1 Kit to work laptop
2. Ran rag-detect-bad-chars: found 1,433 bad characters in 42 files
3. Ran rag-fix-quotes: cleaned 40 files (smart quote corruption from copy-paste)
4. rag-debug-url and rag-test-api-verbose are BROKEN because rag-fix-quotes
   stripped Python quotes inside the PowerShell here-strings
5. Ran manual diagnostic — confirmed credentials are stored and working
6. FOUND THE ROOT CAUSE of 401 errors: THREE cascading failures:
   a. Provider detected as "OpenAI" instead of "Azure" (URL has "aoai")
   b. Wrong URL path: /v1/chat/completions instead of /openai/deployments/...
   c. Wrong auth header: "Authorization: Bearer" instead of "api-key"

## WHAT'S IN THIS KIT

Four scripts in the tools\ folder:

### 1. fix_azure_detection.ps1
   - Patches llm_router_fix.py to recognize "aoai" as Azure
   - Creates backup before changing anything
   - Validates Python syntax after patching

### 2. azure_api_test.ps1
   - 4-stage diagnostic that writes temp Python files (no quoting issues)
   - Stage 1: Shows all Azure/API environment variables
   - Stage 2: Reads stored credentials from keyring
   - Stage 3: Builds the correct URL and checks for problems
   - Stage 4: Makes a REAL API call and shows full response
   - Discovers deployment name and API version from env vars

### 3. rebuilt_rag_commands.ps1
   - Replaces the broken new_commands_for_start_hybridrag.ps1
   - Same commands (rag-debug-url, rag-test-api-verbose, etc.)
   - Uses temp Python files instead of inline code — QUOTING SAFE
   - Also adds: rag-env-vars (shows all API env variables)

### 4. master_toolkit.ps1 (THE BIG ONE — 40+ commands)
   - Every command you'll ever need, all in one file
   - Replaces rebuilt_rag_commands.ps1 and all individual scripts
   - Type rag-help to see the full list
   - Categories: Credentials, API Testing, Ollama, Indexing, Querying,
     File Tools, Network, Project Info, Git, Housekeeping, Logs
   - All Python calls use temp files — zero quoting issues
   - Load with: . .\tools\master_toolkit.ps1
   - Make permanent: add that line to end of start_hybridrag.ps1

## TOMORROW'S SEQUENCE

```powershell
# Step 1: Navigate and activate
cd "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
.\.venv\Scripts\Activate

# Step 2: Copy the 4 new scripts into tools\ folder
# (download from GitHub or this zip)

# Step 3: Load the master toolkit (40+ commands)
. .\tools\master_toolkit.ps1

# Step 4: Type rag-help to see all available commands

# Step 5: Check env vars for deployment name and API version
rag-env-vars

# Step 6: If no deployment name, set it
rag-store-deployment

# Step 7: Fix Azure detection in llm_router_fix.py
. .\tools\fix_azure_detection.ps1

# Step 8: Run the pre-flight check (should now say AZURE)
rag-debug-url

# Step 9: If Step 8 looks correct, run the live test
rag-test-api-verbose

# Step 10: If that works, try a real query
rag-query-api "What is a digisonde?"
```

## IF THE DEPLOYMENT NAME IS WRONG

The scripts guess "gpt-35-turbo" if they can't find it in env vars.
If you get a 404 error, the deployment name is wrong.

To find the correct name:
- Check env vars: rag-env-vars
- Ask your IT admin what the deployment is called
- Check Azure Portal > Azure OpenAI > Deployments (if you have access)

Once you know the name, set it:
```powershell
$env:AZURE_OPENAI_DEPLOYMENT = "your-actual-deployment-name"
```

Then re-run the tests.

## IF YOU GET SSL ERRORS

Corporate proxy may be intercepting HTTPS. Try:
```powershell
$env:REQUESTS_CA_BUNDLE = ""
$env:CURL_CA_BUNDLE = ""
```
Or ask IT for the corporate CA certificate path.

## ALSO REMEMBER
- Uncheck "smart quotes" in Word/Outlook/OneNote on both machines
  (File > Options > Proofing > AutoCorrect > AutoFormat As You Type)
