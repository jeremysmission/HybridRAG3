# Checkpoint: Sprint 16 -- Reranker Revival + Retrieval Improvements

**Date**: 2026-03-15
**Regression**: 777 passed, 7 skipped, 0 failed

## What Changed

### 1. Ollama-Based Reranker (NEW)
- **File**: `src/core/ollama_reranker.py` (new, ~150 lines)
- Replaces the retired sentence-transformers cross-encoder
- Uses local Ollama model to score (query, document) relevance 0-10
- Thread-pooled parallel scoring (default 4 workers)
- Scores centered at 0 for sigmoid normalization compatibility
- Network gate integration (respects offline mode)
- Health check on load -- returns None if Ollama is down
- **Tests**: `tests/test_ollama_reranker.py` (13 tests, all pass)

### 2. Retriever Wiring
- **File**: `src/core/retriever.py`
- `RERANKER_AVAILABLE` set to `True` (was `False`)
- `_load_reranker()` now creates `OllamaReranker` from config
- `refresh_settings()` lazy-loads reranker on first enable
- Falls back gracefully if Ollama unavailable

### 3. Corrective Retrieval Reformulation
- **File**: `src/core/query_engine.py`
- Added `_STOP_WORDS` set (80+ common English stopwords)
- Reformulation now: strips question patterns, removes stopwords,
  sorts by term length (most specific first)
- Before: "What is the frequency range of the AN/TPS-80 radar?"
  After:  "frequency TPS-80 range radar"

## What Did NOT Change
- `reranker_enabled` default remains `False` (opt-in only)
- Eval pipeline untouched (reranker never activates during eval)
- RRF fusion weights unchanged (0.4 vector + 0.6 RRF)
- Config schema unchanged

## BEAST Readiness
- Reranker is BEAST-optimized: GPU Ollama will score 20 pairs in ~1s
- On toaster CPU: ~10s for 20 pairs (acceptable for non-interactive use)
- Enable via `config.retrieval.reranker_enabled: true`

## Next Steps
- Source path search improvement (FTS5 on paths)
- Conditional reranker activation (uncertain-middle gate)
- QLoRA fine-tuning prep (BEAST day-one)
