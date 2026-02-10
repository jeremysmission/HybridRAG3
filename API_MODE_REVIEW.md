# ============================================================================
# HybridRAG v3 — API Mode Deployment Package
# ============================================================================
# This file contains:
#   1. CODE REVIEW: Bugs and gaps that block API mode
#   2. FILE 1: src/security/credentials.py (NEW file)
#   3. FILE 2: src/core/llm_router.py (UPDATED — full replacement)
#   4. FILE 3: api_mode_commands.ps1 (NEW file — PowerShell mode switching)
#   5. DEPLOYMENT STEPS: Exact order to deploy and test
#
# Author: Field Engineer / AI Applications Developer
# Date: February 2026
# ============================================================================


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SECTION 1: CODE REVIEW — What blocks API mode today                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
#
# I traced the full call chain from rag-query → cli_test_phase1.py →
# QueryEngine → LLMRouter → APIRouter. Here are the issues:
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ BUG 1: LLMRouter.__init__ never reads API key from environment        │
# │ File: src/core/llm_router.py                                          │
# │ Line: LLMRouter.__init__                                              │
# │                                                                       │
# │ Current: self.api = APIRouter(config, api_key) if api_key else None   │
# │ Problem: api_key parameter defaults to None, and nothing reads        │
# │          OPENAI_API_KEY from the environment. So unless the caller    │
# │          explicitly passes an API key, the APIRouter never gets       │
# │          created and online mode silently fails.                      │
# │                                                                       │
# │ Fix: Add os.environ.get("OPENAI_API_KEY") as fallback in __init__    │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ BUG 2: LLMRouter.__init__ never reads custom API endpoint from env    │
# │ File: src/core/llm_router.py                                          │
# │                                                                       │
# │ Current: APIRouter reads config.api.endpoint from YAML only           │
# │ Problem: Your work environment uses a CUSTOM API endpoint (your       │
# │          company's intranet GPT-3.5), not api.openai.com. The         │
# │          endpoint in default_config.yaml is the public OpenAI URL.    │
# │          There's no way to override it without editing the YAML.      │
# │                                                                       │
# │ Fix: Check OPENAI_API_ENDPOINT env var and override config if set     │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ BUG 3: No secure credential storage (keyring not integrated)          │
# │ File: (missing) src/security/credentials.py                           │
# │                                                                       │
# │ Current: keyring is in your requirements.txt but no code uses it      │
# │ Problem: API key must either live in env var (visible in process      │
# │          list) or be hardcoded (security nightmare). Need Windows     │
# │          Credential Manager integration.                              │
# │                                                                       │
# │ Fix: Create credentials.py that wraps keyring for store/retrieve     │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ BUG 4: cli_test_phase1.py doesn't read API key before creating       │
# │        LLMRouter                                                      │
# │ File: tests/cli_test_phase1.py                                        │
# │                                                                       │
# │ Current (from your work laptop session):                              │
# │   api_key = os.getenv("OPENAI_API_KEY")                              │
# │   llm = LLMRouter(config, api_key=api_key)                           │
# │                                                                       │
# │ This is CORRECT in your diagnostic script but needs to also try      │
# │ keyring as a fallback.                                                │
# │                                                                       │
# │ Fix: Updated LLMRouter handles this internally now (see File 2)      │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ BUG 5: NO_PROXY not set in startup script (work laptop only)          │
# │ File: start_hybridrag.ps1                                             │
# │                                                                       │
# │ Current: You manually typed $env:NO_PROXY each session                │
# │ Problem: Corporate proxy intercepts even localhost HTTP requests       │
# │                                                                       │
# │ Fix: api_mode_commands.ps1 sets this + start_hybridrag.ps1 needs     │
# │      the line added (one-line manual edit, noted in deploy steps)     │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ NOT A BUG: APIRouter.query() is already correctly implemented         │
# │ File: src/core/llm_router.py                                          │
# │                                                                       │
# │ The existing APIRouter.query() method correctly:                      │
# │   ✅ Sets Authorization: Bearer header                                │
# │   ✅ Builds OpenAI-compatible chat completion payload                 │
# │   ✅ Reads config.api.model, max_tokens, temperature                  │
# │   ✅ Parses usage.prompt_tokens / completion_tokens                   │
# │   ✅ Returns LLMResponse with all fields                              │
# │   ✅ Catches HTTPError, JSON errors, and general exceptions           │
# │                                                                       │
# │ Once the API key reaches the APIRouter, it works correctly.           │
# │ The problem is entirely in how the key gets TO the APIRouter.         │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ NOT A BUG: QueryEngine cost calculation                               │
# │ File: src/core/query_engine.py                                        │
# │                                                                       │
# │ The QueryEngine reads config.cost.input_cost_per_1k and              │
# │ output_cost_per_1k to calculate cost_usd. These are already in       │
# │ default_config.yaml set to GPT-3.5 Turbo rates.                      │
# │ ✅ No changes needed.                                                 │
# └─────────────────────────────────────────────────────────────────────────┘
