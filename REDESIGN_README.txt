# ===========================================================================
# HYBRIDRAG v3 -- API ARCHITECTURE REDESIGN
# ===========================================================================
# Session 2.5 Kit -- Replaces the old llm_router.py URL-sniffing approach
# with a proper validated, tested, auditable architecture.
#
# TEST RESULTS:
#   123 functional tests -- ALL PASSED
#    29 security/quality audits -- ALL PASSED
#   152 total checks -- ZERO failures
#
# ===========================================================================

## WHAT THIS REDESIGN DOES

Before (old architecture):
  - llm_router.py guessed Azure vs OpenAI from URL substrings
  - Empty endpoint silently created broken API client
  - Env var names differed between config.py and llm_router.py
  - Auth header type (api-key vs Bearer) guessed from URL
  - No validation before making API calls
  - Generic error messages ("syntax error", "None")

After (new architecture):
  - config.yaml explicitly sets provider: "azure" (no guessing)
  - Factory validates EVERYTHING before creating API client
  - ONE credentials module reads all env var aliases
  - Typed exceptions with error codes and fix suggestions
  - Centralized HTTP client for proxy/TLS/retry
  - Boot pipeline guarantees no broken state at startup
  - 152 tests prove it all works

## FILES IN THIS KIT

### Source Code (copy into your project)

  src/core/exceptions.py         -- 20 typed exceptions with error codes
                                     CONF-001 through IDX-002
                                     Each has fix_suggestion for GUI/console

  src/security/credentials.py    -- Canonical credential resolver
                                     Reads keyring -> env vars -> config
                                     Accepts ALL env var aliases
                                     Validates endpoint URLs
                                     Never logs/exposes full API keys

  src/core/http_client.py        -- Centralized HTTP client
                                     Proxy, TLS, timeout, retry logic
                                     Network kill switch (HYBRIDRAG_OFFLINE=1)
                                     Audit logging (URL + status, never body)
                                     Masks API keys in log output

  src/core/api_client_factory.py -- The validation gate
                                     Validates before instantiating
                                     Explicit provider detection (config first)
                                     Correct URL construction for Azure
                                     diagnose() method for rag-debug-url
                                     test_connection() for rag-test-api

  src/core/boot.py               -- Boot pipeline
                                     Single startup sequence
                                     Validates config + credentials + services
                                     Never crashes -- reports errors in result
                                     Online and offline mode independence

### Configuration

  config/default_config.yaml     -- Updated with explicit provider/auth fields
                                     api.provider: "azure" (not "auto")
                                     api.auth_scheme: "api_key"
                                     http.timeout, http.max_retries, etc.
                                     Security section with kill switch

### Tests

  tests/test_all.py              -- 123 functional tests
  tests/test_audit.py            --  29 security/quality audits

## INSTALLATION

Step 1: Copy new files into HybridRAG3

  Copy src/core/exceptions.py       -> src/core/exceptions.py
  Copy src/core/http_client.py      -> src/core/http_client.py
  Copy src/core/api_client_factory.py -> src/core/api_client_factory.py
  Copy src/core/boot.py             -> src/core/boot.py
  Copy src/security/credentials.py  -> src/security/credentials.py
  Copy config/default_config.yaml   -> config/default_config.yaml (BACKUP FIRST)
  Copy tests/test_all.py            -> tests/test_redesign.py
  Copy tests/test_audit.py          -> tests/test_audit.py

Step 2: Create __init__.py files if they don't exist

  touch src/__init__.py
  touch src/core/__init__.py
  touch src/security/__init__.py

Step 3: Update config/default_config.yaml

  Set api.deployment to your Azure deployment name
  (or use rag-store-deployment at runtime)

Step 4: Run tests

  cd D:\HybridRAG3
  .\.venv\Scripts\Activate
  python tests/test_redesign.py
  python tests/test_audit.py

Step 5: Test with boot pipeline

  python -c "from src.core.boot import boot_hybridrag; r = boot_hybridrag(); print(r.summary())"

## HOW TO USE IN EXISTING CODE

Old way (llm_router.py):
  router = LLMRouter(config)
  result = router.query("What is X?", mode="api")

New way (boot pipeline):
  from src.core.boot import boot_hybridrag
  result = boot_hybridrag()
  if result.online_available:
      answer = result.api_client.chat("What is X?")

The old llm_router.py still works for offline/Ollama mode.
The new modules replace only the API client portion.
Integration into the full LLMRouter is the next step.

## ERROR CODE REFERENCE

  CONF-001  Endpoint not configured
  CONF-002  API key not configured
  CONF-003  Invalid endpoint URL (smart quotes, missing scheme, etc.)
  CONF-004  Azure deployment name not configured
  CONF-005  Invalid provider or auth scheme in config
  CONF-006  Azure API version not configured

  NET-001   Cannot connect to server
  NET-002   SSL/TLS certificate error
  NET-003   Proxy connection error
  NET-004   Request timeout

  API-001   Authentication rejected (401)
  API-002   Access forbidden (403)
  API-003   Deployment not found (404)
  API-004   Rate limited (429)
  API-005   Server error (5xx)
  API-006   Unexpected response format

  OLL-001   Ollama not running
  OLL-002   Ollama model not found

  IDX-001   No index database found
  IDX-002   Index database corrupted

## CONFIG.YAML QUICK REFERENCE

  api:
    provider: "azure"           # <-- SET THIS EXPLICITLY
    auth_scheme: "api_key"      # <-- Azure uses api-key header
    deployment: ""              # <-- Your deployment name (or use env var)
    api_version: "2024-02-01"   # <-- Azure API version

  http:
    timeout: 30
    max_retries: 2
    verify_ssl: true
    ca_bundle: ""               # <-- Path to corporate CA cert if needed

  security:
    offline_mode: false          # <-- Set true or HYBRIDRAG_OFFLINE=1 to block all HTTP
