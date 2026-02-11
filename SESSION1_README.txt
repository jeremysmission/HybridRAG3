================================================================================
HYBRIDRAG v3 SESSION 1 KIT
================================================================================
Created: 2026-02-11
Purpose: Everything needed for Session 1 at work -- fix API blockers,
         prevent quoting/encoding errors, add diagnostic commands.
================================================================================


================================================================================
SECTION 1: WHAT IS IN THIS ZIP (FILE-BY-FILE)
================================================================================

  README.txt  (this file)
      You are reading it. Contains the installation map, work sequence,
      and explanation of every file in the kit.

  docs\
      HybridRAG_v3_Master_Game_Plan.docx
          The full 20-item roadmap with blockers, research findings,
          risk register, and 4-phase plan. Print this or keep it open.

      QUOTING_AND_ENCODING_SURVIVAL_GUIDE.txt
          Deep dive on why copy-paste breaks your code and how to never
          hit encoding/quoting errors again. Read this at least once.

      SECURITY_AUDIT_ROADMAP.txt
          Future reference document for Phase 4+. Covers bearer tokens
          vs subscription keys, request ID correlation, hash-chain
          tamper-evident logging, and the 3 auth architecture options
          for 10 users. DO NOT implement now -- read after API works.

  src\core\
      llm_router_fix.py
          The Python code that fixes BLOCKER-1 (401 auth) and BLOCKER-2
          (URL doubling). Every function has plain-English commentary
          explaining what it does and why. This is the most important
          file in the kit.

  tools\
      write_llm_router_fix.ps1
          PowerShell script that writes llm_router_fix.py directly to
          disk using .NET encoding. Bypasses the clipboard entirely.
          Use this instead of copy-pasting the Python file.

      fix_quotes.ps1
          Scans files and replaces all smart/curly quotes with straight
          quotes. Creates .bak backups. The nuclear option for when
          copy-paste has already corrupted a file.

      detect_bad_chars.ps1
          Finds non-ASCII characters hiding in your code files. Run this
          after any copy-paste session to catch problems before they
          cause runtime errors.

      new_commands_for_start_hybridrag.ps1
          Defines 5 new rag- commands for your PowerShell session.
          Dot-source this file or paste its contents into your
          start_hybridrag.ps1 to make the commands permanent.


================================================================================
SECTION 2: INSTALLATION MAP -- WHERE EACH FILE GOES
================================================================================

  Your HybridRAG project probably looks something like this:

      D:\HybridRAG3\                     <-- your project root
          .venv\                          <-- Python virtual environment
          src\
              core\
                  llm_router.py           <-- your existing LLM router
                  config.py
                  ...
              security\
                  credentials.py          <-- your credential manager
          tools\                          <-- may or may not exist yet
          start_hybridrag.ps1             <-- your startup script
          hybridrag.sqlite3               <-- your database
          requirements.txt

  HERE IS WHERE EACH FILE FROM THIS KIT GOES:

  FILE IN ZIP                              DROP IT HERE
  -----------------------------------------+---------------------------------------------
  src\core\llm_router_fix.py               D:\HybridRAG3\src\core\llm_router_fix.py
                                           (sits NEXT TO your existing llm_router.py)
                                           (does NOT replace it -- it is a new file)

  tools\write_llm_router_fix.ps1           D:\HybridRAG3\tools\write_llm_router_fix.ps1
  tools\fix_quotes.ps1                     D:\HybridRAG3\tools\fix_quotes.ps1
  tools\detect_bad_chars.ps1               D:\HybridRAG3\tools\detect_bad_chars.ps1
  tools\new_commands_for_start_hybridrag   D:\HybridRAG3\tools\new_commands_for_start_hybridrag.ps1

  docs\*                                   D:\HybridRAG3\docs\  (or wherever you keep docs)

  EASIEST METHOD:
      1. Unzip the entire kit into D:\HybridRAG3\
      2. The folder structure matches, so files land in the right places
      3. If the tools\ folder does not exist, the unzip will create it


================================================================================
SECTION 3: WORK SEQUENCE (STEP BY STEP AT YOUR DESK)
================================================================================

  BEFORE YOU START:
      - Pull the zip from GitHub to your work laptop
      - Unzip into your HybridRAG3 project root

  STEP 1: OPEN POWERSHELL AND NAVIGATE TO YOUR PROJECT
      cd D:\HybridRAG3

  STEP 2: ACTIVATE YOUR VIRTUAL ENVIRONMENT
      .\.venv\Scripts\Activate.ps1
      (You should see (.venv) appear in your prompt)

  STEP 3: LOAD THE NEW COMMANDS INTO YOUR SESSION
      . .\tools\new_commands_for_start_hybridrag.ps1
      (The dot-space at the start is required. It means "run in my session.")
      (You should see a list of 5 new commands printed in green.)

  STEP 4: SCAN YOUR EXISTING CODE FOR BAD CHARACTERS
      rag-detect-bad-chars
      (This scans all .py and .ps1 files for smart quotes and other
       invisible bad characters. If it finds any, go to Step 5.
       If it says ALL CLEAN, skip to Step 6.)

  STEP 5: FIX ANY BAD CHARACTERS FOUND (only if Step 4 found problems)
      rag-fix-quotes
      (This replaces all smart quotes with straight quotes and creates
       .bak backups of every file it modifies.)

  STEP 6: VERIFY YOUR API CONFIGURATION (PRE-FLIGHT CHECK)
      rag-debug-url
      (This shows you EXACTLY what URL and auth headers will be sent,
       WITHOUT making an actual API call. Check that:
         - "Detected provider" says "azure"
         - "Constructed URL" matches your Postman URL
         - "Auth header name" says "api-key" (NOT "Authorization")
         - No PROBLEMS FOUND at the bottom)

  STEP 7: TEST ON DIRECT CORPORATE LAN (IMPORTANT!)
      ** DISCONNECT FROM VPN FIRST **
      ** CONNECT TO DIRECT CORPORATE NETWORK **
      (VPN and direct LAN may have different API access permissions.
       Test on direct LAN first to eliminate network as a variable.)

  STEP 8: TEST THE API CONNECTION
      rag-test-api-verbose
      (This makes a real API call with a simple test message.
       If it works, you will see SUCCESS and the AI response.
       If it fails, the error message includes specific troubleshooting.)

  STEP 9: IF API TEST SUCCEEDS -- INTEGRATE INTO YOUR PIPELINE
      Two options:

      Option A (quickest): Import from the new file
          In your existing llm_router.py, add at the top:
              from src.core.llm_router_fix import call_llm_api
          Then use call_llm_api() where you currently call the API.

      Option B (cleaner): Replace functions in llm_router.py
          Copy the detect_provider, build_api_url, build_headers, and
          call_llm_api functions from llm_router_fix.py into your
          existing llm_router.py, replacing the old versions.

  STEP 10: ENABLE WAL MODE ON SQLITE (one-time, only after indexing works)
      rag-enable-wal
      (This enables Write-Ahead Logging on your SQLite database.
       WAL mode allows multiple readers at the same time, which is
       required for the future 10-user scale-up. Safe to run now.)

  STEP 11: TEST A FULL QUERY
      Run a real question through your RAG pipeline:
          embed -> retrieve -> API generate -> answer
      Verify the answer comes back with source citations.

  STEP 12: IF ALL WORKS -- COMMIT TO GIT
      git add -A
      git commit -m "Session 1: Fix API auth + URL doubling, add diagnostics"
      git push origin main

  IF THINGS GO WRONG:
      - 401 error: Run rag-debug-url, verify api-key header not Bearer
      - 404 error: Run rag-debug-url, compare URL with Postman character by character
      - SSL error: pip install pip-system-certs --break-system-packages
      - Timeout: Check firewall, try direct LAN
      - Syntax error in .py file: Run rag-fix-quotes, re-check encoding


================================================================================
SECTION 4: HOW TO INTEGRATE llm_router_fix.py INTO YOUR EXISTING CODE
================================================================================

  The llm_router_fix.py file is designed to work TWO ways:

  WAY 1: STANDALONE MODULE (recommended for first test)
      Keep it as src\core\llm_router_fix.py alongside your existing code.
      Import what you need:

          from src.core.llm_router_fix import call_llm_api
          from src.core.llm_router_fix import debug_api_config

      Your existing llm_router.py stays untouched. If the new code
      has problems, you just stop importing from it.

  WAY 2: MERGE INTO EXISTING llm_router.py (after testing)
      Once you confirm the fix works, copy these functions into your
      existing llm_router.py:
          - detect_provider()
          - build_api_url()
          - build_headers()
          - call_llm_api()
          - debug_api_config()

      Then delete llm_router_fix.py (it was a temporary scaffold).

  RECOMMENDATION: Start with Way 1. Switch to Way 2 after the demo.


================================================================================
SECTION 5: MAKING THE NEW COMMANDS PERMANENT
================================================================================

  The commands from Step 3 (rag-debug-url, rag-test-api-verbose, etc.)
  only last for your current PowerShell session. When you close the
  window, they disappear.

  TO MAKE THEM PERMANENT:
      1. Open start_hybridrag.ps1 in your editor
      2. At the BOTTOM of the file (before any final lines), paste
         the entire contents of tools\new_commands_for_start_hybridrag.ps1
      3. Save the file
      4. Now every time you run . .\start_hybridrag.ps1, the commands load

  OR, add this one line to start_hybridrag.ps1:
      . .\tools\new_commands_for_start_hybridrag.ps1

  This is called "dot-sourcing" and means "run that script in my session."


================================================================================
SECTION 6: QUICK REFERENCE -- ALL NEW COMMANDS
================================================================================

  COMMAND                    WHAT IT DOES
  -------------------------+--------------------------------------------------
  rag-debug-url             Shows the API URL and headers that WOULD be sent.
                            Run BEFORE rag-test-api to catch config problems.

  rag-test-api-verbose      Makes a real API call with full debug output.
                            Shows exact URL, headers (masked key), and result.

  rag-fix-quotes            Scans all project files and replaces smart quotes
                            with straight quotes. Creates .bak backups.

  rag-detect-bad-chars      Scans all project files for non-ASCII characters
                            that could cause syntax errors. No modifications.

  rag-enable-wal            Enables SQLite WAL mode for concurrent reads.
                            Run once after database exists. Safe to re-run.


================================================================================
END OF README
================================================================================
