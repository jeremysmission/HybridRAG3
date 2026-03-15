# HybridRAG3 Gap Analysis vs State-of-Art Research (March 2026)

## Current Strengths (keep as-is)
- **Hybrid RRF search**: FTS5 + vector cosine with k=60 RRF fusion. Industry standard, well-tuned.
- **9-rule prompt v4**: Priority ordering (injection > ambiguity > accuracy). 98% pass rate on 400q golden set.
- **Smart boundary chunking**: Paragraph/sentence-aware splits with heading prepend. Good for engineering prose.
- **Dual eval systems**: run_eval.py (real-time) + score_results.py (post-hoc) with complementary weightings.

## Gap 1: Reranker is Dead Code (HIGHEST PRIORITY)
- **Current**: sentence-transformers retired. _rerank() always returns hits unchanged.
- **Research**: Cross-encoder reranking improves NDCG@10 by 8-48% (Databricks, Voyage research).
- **Fix**: Replace sentence-transformers with Ollama-based reranking.
  - Use phi4:14b as cross-encoder: score each chunk's relevance to query on 0-1 scale
  - Retrieve top-20 via RRF, rerank to top-k with LLM scoring
  - On toaster: budget to top-10 candidates only (latency constraint)
  - On BEAST/workstation: full top-20 reranking
  - Config: reranker_enabled stays opt-in, reranker_backend="ollama"
- **Impact**: +8-48% retrieval quality on the same index. No re-indexing needed.
- **Risk**: Latency increases. Must be opt-in, not default. Eval-mode and batch-mode benefit most.

## Gap 2: No Corrective Retrieval (HIGH PRIORITY)
- **Current**: If min_score filtering drops all chunks, falls back to open knowledge or refusal. No retry.
- **Research**: CRAG (Corrective RAG) paper shows retrieve-evaluate-retry catches 15-20% of misses.
- **Fix**: Add confidence evaluation after retrieval:
  1. If best chunk score < confidence_threshold (e.g., 0.35): low confidence
  2. Reformulate query: expand terms, add synonyms from query context
  3. Retry retrieval once with reformulated query
  4. Cap at 2 retrieval rounds max (latency budget)
- **Impact**: Catches queries where user phrasing doesn't match document terminology.
- **Where**: query_engine.py, between retrieval and generation steps.

## Gap 3: FTS5 Source Path Indexing (MEDIUM PRIORITY)
- **Current**: FTS5 indexes chunk text only. source_path is in base table but not searchable.
- **Research**: Structural metadata (file path, type) as FTS5 fields improves precision for multi-doc queries.
- **Fix**: Add source_path as second FTS5 column:
  ```sql
  CREATE VIRTUAL TABLE chunks_fts USING fts5(text, source_path, content='chunks', content_rowid='chunk_pk')
  ```
  - At query time, chunks from files whose path matches query terms get FTS5 boost
  - "calibration procedure" matches chunks from Calibration_Guide.pdf higher
- **Impact**: Better precision on domain-specific queries. Free at query time.
- **Cost**: Requires re-indexing (one-time).

## Gap 4: Parent-Child Chunk Hierarchy (MEDIUM PRIORITY)
- **Current**: Flat chunks with heading prepend and adjacent-chunk augmentation.
- **Research**: Search small precise chunks, return large parent context. +recall.
- **Assessment**: Heading prepend partially compensates for engineering prose.
  For code docs this matters less than for actual code. Adjacent-chunk augmentation
  already provides +-1 neighbor expansion. Lower priority than gaps 1-3.
- **If implemented**: Add parent_id column to chunks table. During chunking, create
  100-200 word "child" chunks inside 1200-char "parent" chunks. Search children,
  return parents.

## Gap 5: Query Decomposition (MEDIUM PRIORITY)
- **Current**: Single query -> single retrieval. Complex queries may miss relevant docs.
- **Research**: Decompose "how does auth flow work?" into sub-queries, retrieve for each, merge.
- **Assessment**: Most HybridRAG3 queries are specific ("what is the torque spec for X?").
  Decomposition helps more for architectural questions. Lower priority for current use case.

## Gap 6: AST-Aware Chunking (LOW for HybridRAG3, HIGH for JCoder)
- **Current**: Size-based with smart boundary detection.
- **Research**: cAST (EMNLP 2025) shows +5.5 on code benchmarks with AST chunking.
- **Assessment**: HybridRAG3 indexes engineering documents (PDFs, manuals), not source code.
  AST chunking is irrelevant for prose. Smart boundary chunking is the right approach.
  **This improvement applies to JCoder, not HybridRAG3.**

## Implementation Priority for BEAST Deployment

### Phase 1: Quick Wins
1. FTS5 source_path indexing (re-index once, permanent benefit)
2. Reranker revival with Ollama backend (code exists, just needs new backend)

### Phase 2: Pipeline Enhancement
3. Corrective retrieval loop (new code in query_engine.py)
4. Query reformulation on low-confidence retrieval

### Phase 3: If Needed
5. Parent-child chunking (requires re-indexing + schema change)
6. Query decomposition (requires LLM call before retrieval)

## Eval Impact Estimates
- Reranker revival: Likely recovers 2-4 of the 8 known failures (6 log retention + 2 calibration)
- Corrective retrieval: Likely catches 1-2 additional edge cases
- FTS5 source_path: Helps with document-specific queries, may fix calibration failures
- Combined: Could push from 98% to 99%+ on 400q golden set
