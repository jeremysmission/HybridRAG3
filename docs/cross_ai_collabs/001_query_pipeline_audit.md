# Query Pipeline Audit -- Claude Code
## Date: 2026-02-28
## Scope: All query paths from user question to displayed answer

## CRITICAL ISSUES

### 1. Online Streaming Missing "done" Event
- **File:** src/core/llm_router.py, lines 1741-1751
- When streaming in online mode, if query() returns None, the generator
  ends silently with no "done" event. UI hangs indefinitely.
- **Impact:** Streaming queries in online mode that fail freeze the GUI

### 2. Empty Answer Not Re-Yielded in Streaming
- **File:** src/core/query_engine.py, lines 329-330
- If LLM returns empty tokens, the fallback answer "Error calling LLM"
  is set on the result but never yielded as tokens. User sees blank box.
- **Impact:** Blank answer area during streaming, then error text appears
  in final result only

## MEDIUM ISSUES

### 3. Online Streaming Returns Single Token
- **File:** src/core/llm_router.py, line 1744
- Online streaming yields entire answer as one token, defeating the
  purpose of streaming (no visual progress for 30s, then wall of text)

### 4. APIRouter Init Failure Silent
- **File:** src/core/llm_router.py, lines 1060-1062
- If API client init fails, self.client=None. User sees "Online mode
  available" but first query fails silently.

### 5. Empty Chunks in Context
- **File:** src/core/retriever.py, lines 456-461
- build_context() doesn't validate h.text is non-empty. Corrupted index
  entries with empty text waste context window.

### 6. Context Trimming Too Aggressive
- **File:** src/core/query_engine.py, line 382
- Estimates 800 tokens for 9-rule prompt overhead, actual is ~370 tokens.
  Context is trimmed too conservatively, losing relevant chunks.

### 7. Cost Not Tracked on Error
- **File:** src/gui/panels/query_panel.py, lines 620-683
- _finish_stream() returns early on error before _emit_cost_event().
  Failed queries not recorded in cost tracker.

## LOW ISSUES

### 8. No Retry Logic for LLM Timeouts
- All routers fail immediately on timeout. No exponential backoff.

### 9. NLI Verifier No Timeout
- grounded_query_engine.py line 483: verify_batch has no timeout.
  If NLI model hangs, UI freezes.

### 10. Model List Silent Failure
- query_panel.py lines 295-297: Ollama model list failure logged at
  debug level, user gets no indication.

### 11. Cost Emit Error Swallowed
- query_panel.py lines 816-817: Cost tracker exceptions silently dropped.

## UNTESTED PATHS (Zero Coverage)

- Online mode queries (all tests use mode="offline")
- Streaming failure paths (empty tokens, generator exceptions)
- Grounded streaming edge cases (empty answer, gate blocking)
- Concurrent query cost tracking (thread safety)

## EDGE CASES

- Retrieval hits with empty text pass through to LLM prompt
- Whitespace-only LLM response passes "if not answer" check
- Negative/zero token counts from online API not validated
- Rapid duplicate queries may race on embedding cache
