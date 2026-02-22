# RAG Latest Techniques Research (2025-2026)

> **Date**: 2026-02-21
> **Author**: Research Agent (automated web search)
> **Scope**: RAG improvements, embedding models, retrieval techniques
> **Baseline**: HybridRAG3 -- BM25+vector hybrid, all-MiniLM-L6-v2, 39,602 chunks, 98% eval pass rate

---

## TABLE OF CONTENTS

1. [TOPIC 1: RAG Improvements](#topic-1-rag-improvements)
   - [1.1 GraphRAG vs Standard RAG](#11-graphrag-vs-standard-rag)
   - [1.2 HyDE (Hypothetical Document Embeddings)](#12-hyde-hypothetical-document-embeddings)
   - [1.3 RAPTOR (Recursive Abstractive Processing)](#13-raptor-recursive-abstractive-processing)
   - [1.4 Rerankers: Cross-Encoder vs Bi-Encoder](#14-rerankers-cross-encoder-vs-bi-encoder)
   - [1.5 Chunking Strategies](#15-chunking-strategies)
   - [1.6 Hybrid Search Beyond BM25+Vector](#16-hybrid-search-beyond-bm25vector)
   - [1.7 Other Accuracy-Improving Techniques](#17-other-accuracy-improving-techniques)
2. [TOPIC 2: Embedding Model Improvements](#topic-2-embedding-model-improvements)
   - [2.1 MTEB Leaderboard Top Performers](#21-mteb-leaderboard-top-performers)
   - [2.2 Approved Models (Non-China, Non-Meta)](#22-approved-models-non-china-non-meta)
   - [2.3 Banned Models (Documented for Reference)](#23-banned-models-documented-for-reference)
   - [2.4 Matryoshka Representation Learning](#24-matryoshka-representation-learning)
   - [2.5 Instruction-Tuned Embeddings](#25-instruction-tuned-embeddings)
3. [Priority Matrix for HybridRAG3](#priority-matrix-for-hybridrag3)
4. [Sources](#sources)

---

## TOPIC 1: RAG IMPROVEMENTS

### 1.1 GraphRAG vs Standard RAG

**What it is**: GraphRAG extends vector-based RAG by organizing documents into a
knowledge graph of entities (nodes) and relationships (edges). Instead of flat
similarity search, it performs graph traversal and relevance expansion.

**When to use which**:

| Criterion | Standard RAG | GraphRAG |
|-----------|-------------|----------|
| Query type | Single-hop factual Q&A | Multi-hop reasoning, relational queries |
| Data structure | Unstructured text, FAQs | Entity-rich, relational (supply chain, org charts) |
| Entity count | 1-4 entities per query | 5+ entities per query |
| Speed priority | High (ms latency) | Lower (graph traversal overhead) |
| Cost | Low | High (entity extraction, graph DB) |

**Measured results**:
- Diffbot KG-LM Benchmark: GraphRAG outperforms vector RAG **3.4x**
- Vector RAG degrades to **0% accuracy** on queries with 5+ entities
- GraphRAG sustains stable accuracy even at 10+ entities per query
- [NOVEL FIND] **LazyGraphRAG** (Microsoft, June 2025): defers community summarization to
  query time, reduces indexing cost by **99.9%**, comparable quality at **700x lower query cost**
- [NOVEL FIND] **LightRAG**: uses **6,000x fewer tokens** per query (100 vs 610,000),
  **30% lower latency**, Apache 2.0, incremental updates without full rebuild

**Microsoft GraphRAG status**: v2.7.0 (January 2026), active development, GitHub:
microsoft/graphrag. Supports local + global search, community summaries, drift search.

**HybridRAG3 applicability**: LOW priority. Current data (engineering docs, procedures)
is mostly flat text, not heavily relational. Would benefit only if querying
cross-document entity relationships becomes a requirement.

---

### 1.2 HyDE (Hypothetical Document Embeddings)

**What it is**: Before retrieval, an LLM generates a "hypothetical" answer document
for the query. This fake document is embedded and used for similarity search instead
of the raw query. The hypothesis lives closer in embedding space to real answers.

**How it works**:
1. User query enters system
2. LLM generates hypothetical answer (fake but plausible)
3. Hypothetical document is embedded
4. Embedding used for similarity search against real corpus
5. Retrieved real documents passed to LLM for final answer

**Measured results**:
- HyPE study (2025): up to **+42pp precision** and **+45pp recall** on certain datasets
- HyDE re-ranked: **+14pp accuracy** over query-only approaches
- Latency penalty: **+25-60%** over standard RAG (extra LLM call)

**Critical limitations**:
- **Hallucination compounding**: wrong hypothesis retrieves wrong documents
- **Domain-dependent**: works only when LLM has baseline knowledge of the topic
- **Not for fact-critical**: unsuitable for compliance, engineering specs, legal
- Multilingual weakness: encoder saturates with many languages

**HybridRAG3 applicability**: LOW priority. Our queries are fact-bound engineering
lookups where HyDE's hallucination risk is unacceptable. The latency penalty on
phi4-mini would be significant. Could be useful as a fallback for exploratory queries
where standard retrieval returns low-confidence results.

---

### 1.3 RAPTOR (Recursive Abstractive Processing)

**What it is**: Recursively embeds, clusters, and summarizes document chunks bottom-up,
building a tree with multiple abstraction levels. Retrieval can target any level --
from fine-grained leaf chunks to high-level summaries.

**Measured results**:
- **+20% absolute accuracy** on QuALITY benchmark (with GPT-4)
- **55.7% F1** on QASPER (SOTA at publication)
- F1 at least **+1.8%** over DPR, **+5.3%** over BM25 across all tested LMs

**Limitations**:
- Produces relatively flat trees that may miss document complexity
- Fixed chunking disrupts contextual relationships
- High cost: LLM calls for clustering + summarization at each tree level
- [NOVEL FIND] DOS RAG (2025 study): simple retrieve-then-read with 128K+ context
  models consistently **matches or outperforms** RAPTOR on long-context QA

**HybridRAG3 applicability**: LOW priority. Our 39K chunks are already well-structured
engineering documents. Long-context models (phi4-mini 128K context) may make RAPTOR
redundant. High indexing cost not justified at current scale.

---

### 1.4 Rerankers: Cross-Encoder vs Bi-Encoder

**Architecture comparison**:

| Feature | Bi-Encoder | Cross-Encoder | ColBERT (Late Interaction) |
|---------|-----------|---------------|---------------------------|
| Speed | Fast (independent encoding) | Slow (joint encoding) | Medium (token-level interaction) |
| Accuracy | Good | Best | Near cross-encoder |
| Scalability | Millions of docs | Top-K only (reranking) | Full retrieval possible |
| Use case | Initial retrieval | Second-stage reranking | Both retrieval and reranking |

**Best practice (2025-2026)**: Two-stage pipeline. Bi-encoder retrieves top-50,
cross-encoder reranks to top-5/10. MIT study: **+33-40% accuracy** for only
**+120ms latency**.

**[UPGRADE CANDIDATE] NDAA-compliant reranker models**:

| Model | Origin | License | Size | Score | Notes |
|-------|--------|---------|------|-------|-------|
| **mxbai-rerank-large-v2** | Germany (Mixedbread) | Apache 2.0 | 1.5B | NDCG@10: 57.49 BEIR | Best open-source |
| **mxbai-rerank-base-v2** | Germany (Mixedbread) | Apache 2.0 | 0.5B | NDCG@10: 55.57 BEIR | Smaller, faster |
| **FlashRank** | Open | Open Source | ~4-34MB | Good | CPU-only, no torch needed |
| **answerai-colbert-small** | USA (Answer.AI) | MIT | Small | Beats 10x larger | Late interaction |
| Cohere Rerank 4 | Canada | Proprietary | Cloud | 1627 ELO | Top commercial |
| Voyage AI rerank-2.5 | USA | Proprietary | Cloud | +7.94% over Cohere v3.5 | Best quality/latency |
| Jina Reranker v2 | Germany | CC-BY-NC-4.0 | Base | 6x faster than v1 | Non-commercial |

**BANNED**: BGE rerankers (BAAI, China origin). Use Mixedbread mxbai-rerank instead.

**[UPGRADE CANDIDATE] FlashRank for HybridRAG3**:
- 4MB smallest model, CPU-only, no PyTorch/Transformers dependency
- Zero GPU requirement -- runs on 8GB laptop
- Apache 2.0 license
- Drop-in reranker for existing top-K pipeline

**IMPORTANT CAVEAT for HybridRAG3**: Current eval shows reranker **destroys**
unanswerable (100->76%), injection (100->46%), ambiguous (100->82%) scores.
Any reranker integration MUST be tested against full 400q golden set with
behavioral categories before deployment. Consider reranking only factual
queries, not behavioral test categories.

---

### 1.5 Chunking Strategies

#### 1.5.1 Late Chunking (Jina AI)

**What it is**: Feed entire document through long-context embedding model first,
get token-level embeddings, THEN chunk and apply mean pooling. Each chunk retains
full document context awareness.

**Measured improvement**: **+24.47%** average relative improvement over naive chunking.
Similarity scores rise from ~70% to **82-84%** for relevant chunks.

**Requirements**: Long-context embedding model (jina-embeddings-v2/v3, 8192+ tokens).
Cannot use with all-MiniLM-L6-v2 (512 token limit).

**[UPGRADE CANDIDATE]** If switching to jina-embeddings-v3, late chunking comes free.

#### 1.5.2 Contextual Chunking

**[UPGRADE CANDIDATE] What it is**: After standard chunking, an LLM generates a brief
context summary for each chunk (e.g., "This chunk is from Section 3.2 of the
Calibration Guide and discusses sensor offset procedures"). Summary is prepended
to the chunk before embedding.

**Measured improvement**:
- Contextual embeddings alone: **-35%** retrieval failure rate
- Contextual embeddings + contextual BM25: **-49%** retrieval failure rate
- With reranking: **-67%** retrieval failure rate total

**Cost**: One LLM call per chunk during indexing. For 39,602 chunks with phi4-mini,
this is a one-time batch job (~6-12 hours on laptop). Could use a hosted LLM API
for higher quality context summaries.

**HybridRAG3 applicability**: HIGH priority. Our engineering documents often have
chunks that lose context when separated from their parent section. Contextual
prepending would directly address this. One-time re-indexing cost.

#### 1.5.3 Semantic Chunking

**What it is**: Split documents by meaning (embedding similarity between adjacent
sentences) rather than fixed token count.

**Measured improvement**: Up to **+9% recall** over fixed-size. Page-level chunking
achieved 0.648 accuracy with lowest variance in NVIDIA benchmarks.

**Practical recommendation**: RecursiveCharacterTextSplitter with **400-512 tokens**
delivers **85-90% recall** without computational overhead -- solid default.

**HybridRAG3 applicability**: MEDIUM. Current chunking is likely fixed-size. Semantic
chunking could help with heterogeneous document types (mixing procedures, specs,
training materials).

---

### 1.6 Hybrid Search Beyond BM25+Vector

#### 1.6.1 SPLADE (Learned Sparse Retrieval)

**[NOVEL FIND] What it is**: Neural "learned BM25" -- uses BERT to expand both query
and document vocabularies into sparse vectors. Solves vocabulary mismatch problem
(user says "calibration" but document says "offset adjustment").

**Key variants**:
- **SPLADE-v3** (2024): higher retrieval via better distillation
- **SPLADE-doc**: document-only, zero GPU at query time, <4ms latency
- **Echo-Mistral-SPLADE** (2024): decoder-only backbone, surpasses all prior on BEIR

**Performance**: <4ms difference from BM25 latency while matching SOTA neural rankers.

**Platform support**: Qdrant (FastEmbed), Elasticsearch (ELSER), OpenSearch, Pinecone.

#### 1.6.2 ColBERT / ColBERTv2 (Late Interaction)

**[NOVEL FIND] What it is**: Stores token-level embeddings per document. At query time,
computes maximum-similarity aggregation between query tokens and document tokens.
Near-cross-encoder accuracy at near-bi-encoder speed.

**Key models**:
- **answerai-colbert-small** (Answer.AI, MIT): beats 110M ColBERTv2, beats models 10x larger
- **Jina ColBERT v2**: multilingual
- **PLAID engine**: **7x faster GPU, 45x faster CPU** vs vanilla ColBERTv2

**RAGatouille**: Python wrapper making ColBERT easy in any RAG pipeline.
`pip install ragatouille`. Supports indexing, search, fine-tuning.

#### 1.6.3 Three-Way Hybrid (The New Standard)

**[NOVEL FIND] [UPGRADE CANDIDATE]** IBM research found optimal retrieval is:
**BM25 + dense vectors + sparse vectors (SPLADE)**

- Dense vectors: semantic meaning
- Sparse vectors (SPLADE): precise keyword recall with learned expansion
- BM25/full-text: robustness across diverse scenarios
- Fusion: Reciprocal Rank Fusion (RRF), score = 1/(k+r) summed across lists

**Typical improvements**: recall from ~0.72 (BM25 alone) to **~0.91** (hybrid),
precision from ~0.68 to **~0.87**.

**HybridRAG3 applicability**: MEDIUM-HIGH. We already do BM25+vector. Adding SPLADE
as a third signal with RRF fusion is the logical next step. Requires SPLADE model
(non-China) and sparse vector support in our index.

---

### 1.7 Other Accuracy-Improving Techniques

#### 1.7.1 Corrective RAG (CRAG)

**[UPGRADE CANDIDATE] What it is**: Adds a retrieval evaluator that grades documents as
Correct/Incorrect/Ambiguous before passing to LLM. If "Incorrect", triggers corrective
actions: query reformulation, expanded retrieval, web search fallback.

**Measured improvement**: Reduces hallucinations by up to **78%** vs static RAG.

**Implementation**: Available as LangGraph workflow. Components: retrieval, grading,
conditional web search, query rewriting, generation.

**HybridRAG3 applicability**: MEDIUM. Could help with the 2% failure cases. The grading
step aligns with our existing behavioral scoring. Would need to ensure grader doesn't
interfere with injection/unanswerable handling.

#### 1.7.2 Self-RAG

**What it is**: Trains a single LM with "reflection tokens" to decide: (1) whether
retrieval is needed, (2) document relevance (ISREL), (3) support assessment (ISSUP),
(4) response utility (ISUSE). Adapts retrieval on-demand.

**Complexity**: VERY HIGH. Requires custom model training with reflection token pipeline.

**HybridRAG3 applicability**: LOW. Requires model fine-tuning we can't do on current
hardware. Interesting for workstation era but not near-term.

#### 1.7.3 Agentic RAG

**What it is**: Hierarchy of AI agents orchestrating RAG: task decomposition, retrieval
strategy planning, tool calling, result reflection, iterative refinement.

**Measured improvement**: 25-40% reduction in irrelevant retrievals. Production
deployments report significant reliability gains through iterative verification.

**Clinical example**: Self-correcting Agentic Graph RAG achieved faithfulness 0.94,
context recall 0.92, answer relevancy 0.91.

**HybridRAG3 applicability**: MEDIUM for workstation era. Could orchestrate multi-source
retrieval across engineering doc types.

#### 1.7.4 Query Decomposition

**[UPGRADE CANDIDATE] What it is**: Complex queries broken into simpler sub-queries by
LLM. Each sub-query retrieves independently, results aggregated.

**Measured improvement**:
- **-40% retrieval-related hallucinations** for complex questions (Haystack/Deepset 2025)
- **+15-20% NDCG** from hybrid retrieval, **+10-15% additional** from decomposition
- Clinical: accuracy from 33% to **77.5%** on 3-field queries (+44.5pp)
- DecomposeRAG: handles complex questions **50% better**

**Complexity**: LOW. Single LLM call to decompose, parallel retrieval, result fusion.

**HybridRAG3 applicability**: MEDIUM-HIGH. Our engineering queries sometimes span
multiple document types (e.g., "What is the calibration procedure for X and what
are the safety requirements?"). Query decomposition could split this into targeted
sub-queries.

---

## TOPIC 2: EMBEDDING MODEL IMPROVEMENTS

### 2.1 MTEB Leaderboard Top Performers (Retrieval Focus)

Current MTEB retrieval leaderboard (as of early 2026):

| Rank | Model | Publisher | Params | Dims | MTEB Score | Retrieval | License | Origin |
|------|-------|-----------|--------|------|------------|-----------|---------|--------|
| 1 | NV-Embed-v2 | NVIDIA | 7.1B | 4096 | 69.32 | SOTA | CC-BY-NC-4.0 | USA |
| 2 | Qwen3-Embedding-8B | Alibaba | 8B | - | 70.58 (multilingual) | SOTA | Apache 2.0 | CHINA - BANNED |
| 3 | Cohere embed-v4 | Cohere | Proprietary | - | 65.2 | High | Proprietary | Canada |
| 4 | text-embedding-3-large | OpenAI | Proprietary | 3072 | 64.6 | High | Proprietary | USA |
| 5 | BGE-M3 | BAAI | 568M | 1024 | 63.0 | High | MIT | CHINA - BANNED |
| 6 | jina-embeddings-v3 | Jina AI | 570M | 1024 | 65.52 | High | CC-BY-NC-4.0 | Germany |
| 7 | nomic-embed-text-v2 | Nomic AI | ~137M MoE | 768 | High | High | Apache 2.0 | USA |
| 8 | snowflake-arctic-embed-l-v2.0 | Snowflake | 334M | 1024 | High | 55.9+ | Apache 2.0 | USA |
| 9 | E5-large-v2 | Microsoft | 335M | 1024 | High | BEIR leader | MIT | USA |
| 10 | all-MiniLM-L6-v2 | Microsoft | 22M | 384 | Low | 56% Top-5 | Apache 2.0 | USA |

**Key takeaway**: all-MiniLM-L6-v2 (our current model) achieves only **56% Top-5
accuracy** and **28% Top-1** in modern benchmarks. Its 2019 architecture cannot
compete with 2024-2026 retrieval-optimized models.

---

### 2.2 Approved Models (Non-China, Non-Meta)

#### [UPGRADE CANDIDATE] nomic-embed-text-v1.5

| Property | Value |
|----------|-------|
| Publisher | Nomic AI (USA) |
| License | Apache 2.0 |
| Parameters | 137M |
| Dimensions | 64-768 (Matryoshka) |
| Context | 8192 tokens |
| MTEB | ~81.2% overall, outperforms OpenAI |
| Speed | 100+ qps on M2 MacBook |
| Ollama | `nomic-embed-text` |
| NDAA Status | APPROVED |

**Why upgrade**: 6x the context window (8192 vs 512), Matryoshka variable dims,
Apache 2.0, runs on 8GB laptop. **81.2% vs 80.04% on overall MTEB**, but
significantly better on retrieval-specific tasks. Available in Ollama.

#### [UPGRADE CANDIDATE] nomic-embed-text-v2-moe

| Property | Value |
|----------|-------|
| Publisher | Nomic AI (USA) |
| License | Apache 2.0 |
| Parameters | 475M total, 305M active (MoE) |
| Dimensions | 768 (MRL: truncatable to 256) |
| Context | 8192 tokens |
| MTEB | Outperforms all sub-500M on BEIR retrieval |
| Multilingual | ~100 languages (1.6B training pairs) |
| Format | GGUF available for llama.cpp |
| NDAA Status | APPROVED |

**Why upgrade**: First MoE embedding model. 305M active params means near-large-model
quality at medium-model compute. Better multilingual support. Apache 2.0.
Available as GGUF. Latest from Nomic (2025).

#### [UPGRADE CANDIDATE] snowflake-arctic-embed-l-v2.0

| Property | Value |
|----------|-------|
| Publisher | Snowflake (USA, San Mateo CA) |
| License | Apache 2.0 |
| Parameters | 568M (303M non-embedding) |
| Dimensions | 1024 (MRL: truncatable to 256) |
| Context | 8192 tokens |
| MTEB Retrieval (nDCG@10) | 55.98 (SOTA for open-source retrieval-focused) |
| VRAM | ~2.3GB |
| Ollama | `snowflake-arctic-embed2` |
| NDAA Status | APPROVED |

**Why upgrade**: Highest retrieval scores among approved open-source models. MRL
support. 8192 context. Instruction-aware. Compression to 128 bytes per vector with
int4 quantization. Apache 2.0. Available in Ollama. Fits on laptop with GPU.

#### [UPGRADE CANDIDATE] snowflake-arctic-embed-m-v2.0

| Property | Value |
|----------|-------|
| Publisher | Snowflake (USA) |
| License | Apache 2.0 |
| Parameters | 305M (113M non-embedding) |
| Dimensions | 768 (MRL: truncatable to 256) |
| Context | 8192 tokens |
| MTEB Retrieval (nDCG@10) | 55.4 (only ~2% behind large variant) |
| VRAM | ~1.2GB |
| NDAA Status | APPROVED |

**Why upgrade**: Sweet spot of size vs retrieval performance. Only ~2% behind the
large variant but nearly half the parameters. 8192 context, MRL support. Runs
easily on 8GB laptop. **+30% relative retrieval improvement over all-MiniLM-L6-v2**.

#### E5-large-v2 (Microsoft)

| Property | Value |
|----------|-------|
| Publisher | Microsoft (USA) |
| License | MIT |
| Parameters | 335M |
| Dimensions | 1024 |
| Context | 512 |
| MTEB | First to beat BM25 zero-shot on BEIR |
| NDAA Status | APPROVED |

**Why upgrade**: MIT license (maximum permissiveness), Microsoft origin (approved
publisher), strong zero-shot retrieval. Instruction-tuned variant (E5-instruct)
achieved **100% Top-5 accuracy** in benchmarks.

#### [UPGRADE CANDIDATE] E5-base-instruct / E5-small

| Property | Value |
|----------|-------|
| Publisher | Microsoft (USA) |
| License | MIT |
| Parameters | 110M / 33M |
| Dimensions | 768 / 384 |
| Accuracy | 100% Top-5 in RAG eval |
| Latency | <30ms |
| NDAA Status | APPROVED |

**Why upgrade**: E5-small at 33M params achieves **100% Top-5 accuracy** with <30ms
latency. Nearly same size as all-MiniLM-L6-v2 but dramatically better retrieval.
E5-base-instruct also hits 100% Top-5 with 768 dims.

#### jina-embeddings-v3

| Property | Value |
|----------|-------|
| Publisher | Jina AI (Germany) |
| License | CC-BY-NC-4.0 |
| Parameters | 570M |
| Dimensions | Up to 1024 |
| Context | 8192 tokens |
| MTEB | 65.52 overall, beats OpenAI and Cohere |
| Features | Task LoRA adapters, late chunking support |
| NDAA Status | APPROVED (but non-commercial license) |

**Why upgrade**: Best overall MTEB score among approved models. Task-specific LoRA
adapters (retrieval, classification, clustering). Native late chunking support.
**Caveat**: CC-BY-NC-4.0 license restricts commercial use.

#### E5-Mistral-7B-Instruct (Microsoft, Workstation Only)

| Property | Value |
|----------|-------|
| Publisher | Microsoft (USA), based on Mistral-7B |
| License | MIT |
| Parameters | 7.1B |
| Dimensions | 4096 |
| Context | 4096 tokens |
| MTEB Overall | ~66.6 |
| MTEB Retrieval (nDCG@10) | ~56-58 on BEIR |
| VRAM | ~15GB (fits one RTX 3090) |
| NDAA Status | APPROVED (Microsoft + Mistral) |

**Why upgrade**: LLM-based embedding model. +30-40% retrieval accuracy over
all-MiniLM-L6-v2. Instruction-tuned for query understanding. MIT license.
**NOT for 8GB laptop** -- requires dual-3090 workstation.

#### multilingual-e5-large-instruct (Microsoft)

| Property | Value |
|----------|-------|
| Publisher | Microsoft (USA) |
| License | MIT |
| Parameters | 560M |
| Dimensions | 1024 |
| Context | 514 tokens |
| MTEB Overall | ~64.4 |
| MTEB Retrieval (nDCG@10) | ~52-55 |
| VRAM | ~2.2GB |
| NDAA Status | APPROVED |

**Why upgrade**: Best in the 500M-class from an approved publisher. Instruction-tuned
variant dramatically outperforms non-instruct version. 100+ languages. MIT license.
Fits on either laptop or workstation.

#### Jina Embeddings v5-text (Latest, Non-Commercial)

| Property | Value |
|----------|-------|
| Publisher | Jina AI (Germany) |
| License | CC-BY-NC-4.0 (non-commercial) |
| Variants | v5-text-small (677M), v5-text-nano (239M) |
| Dimensions | up to 4096 (MRL) |
| Context | 32K tokens |
| Features | Task LoRA, GGUF/MLX, SOTA sub-1B |
| NDAA Status | APPROVED origin but non-commercial license |

**Why consider**: Latest from Jina (2026). SOTA for sub-1B models. 32K context.
**Caveat**: CC-BY-NC-4.0 restricts commercial use. Same as v3/v4.

#### EmbeddingGemma-300M (Google DeepMind)

| Property | Value |
|----------|-------|
| Publisher | Google DeepMind (USA) |
| License | Check (Google terms) |
| Parameters | 300M |
| Dimensions | - |
| Features | On-device optimized, multilingual |
| NDAA Status | CONDITIONAL (Google remote kill switch concern) |

**Why consider**: Lightweight, multilingual, on-device. Same concerns as other
Google models re: remote kill switch.

---

### 2.3 Banned Models (Documented for Reference Only)

These models are BANNED per NDAA/ITAR constraints but documented for benchmark
comparison purposes:

| Model | Publisher | Origin | MTEB Score | Why Banned |
|-------|-----------|--------|------------|------------|
| Qwen3-Embedding-8B | Alibaba | China | 70.58 | NDAA (China) |
| BGE-M3 | BAAI | China | 63.0 | NDAA (China) |
| BGE-large-en-v1.5 | BAAI | China | High | NDAA (China) |
| GTE-large | Alibaba | China | High | NDAA (China) |
| GTE-multilingual-base | Alibaba | China | High | NDAA (China) |
| Any Llama-based embed | Meta | USA | Varies | ITAR (Meta ban) |

**Also notable**:
- **NV-Embed-v2** (NVIDIA, USA, 7.1B): MTEB #1 at 72.31 overall, 62.65 retrieval.
  NOT origin-banned but **CC-BY-NC-4.0** (non-commercial). Cannot use commercially.
- **Jina Embeddings v4**: Built on **Qwen2.5-VL-3B-Instruct** backbone. Double-banned:
  CC-BY-NC license + Qwen/Alibaba origin makes it China-derived.

**Note**: BGE-M3 is frequently cited as "best open-source" but is BAAI (Beijing
Academy of AI). All BGE models are banned.

---

### 2.4 Matryoshka Representation Learning

**What it is**: Training technique that makes embedding dimensions "nested" -- you can
truncate a 768-dim vector to 256 or 128 dims with minimal accuracy loss. Early
dimensions carry core semantics; later dimensions add detail.

**Benefits**:
- Up to **14x smaller** representation at same accuracy (ImageNet-1K)
- Up to **100x reduction** in vector storage costs
- Flexible quality/cost tradeoff at query time
- No separate models needed for different dimension targets

**Models supporting Matryoshka (approved)**:
- nomic-embed-text-v1.5 (64-768 dims)
- nomic-embed-text-v2-moe (256-768 dims)
- snowflake-arctic-embed-l-v2.0 (256-1024 dims)
- snowflake-arctic-embed-m-v2.0 (256-768 dims)
- OpenAI text-embedding-3-large (API only)

**HybridRAG3 applicability**: [UPGRADE CANDIDATE] If switching to nomic-embed-text-v1.5,
could use 256-dim embeddings for fast approximate search, then 768-dim for final
ranking. Reduces index size by ~67% with minimal accuracy loss.

---

### 2.5 Instruction-Tuned Embeddings

**What it is**: Embedding models that accept task-specific prefixes at inference time,
improving performance by signaling intent:
- `search_query: <query>` for retrieval queries
- `search_document: <text>` for document indexing
- `classification: <text>` for classification tasks

**Measured improvement**: E5-instruct models achieved **100% Top-5 accuracy** vs
lower scores without instruction prefix. Nomic-embed requires `search_query:` /
`search_document:` prefixes for optimal RAG performance.

**Models supporting instruction-tuning (approved)**:
- E5-instruct family (Microsoft, MIT)
- nomic-embed-text v1/v1.5/v2 (Nomic, Apache 2.0)
- jina-embeddings-v3 (Jina, CC-BY-NC-4.0)

**HybridRAG3 applicability**: [UPGRADE CANDIDATE] HIGH. Current all-MiniLM-L6-v2 does
NOT support instruction tuning. Switching to any instruction-aware model would improve
retrieval quality. Easy to implement: just prepend prefix strings during embedding.

---

## PRIORITY MATRIX FOR HYBRIDRAG3

Ranked by expected impact, implementation effort, and compatibility with current
constraints (8GB laptop, NDAA compliance, 98% baseline).

### Tier 1: High Impact, Low-Medium Effort

| # | Technique | Expected Gain | Effort | Risk | Action |
|---|-----------|---------------|--------|------|--------|
| 1 | **Upgrade embedding model** (nomic-embed-text-v1.5 or E5-small-instruct) | Major retrieval improvement (56% -> 81%+ Top-5) | Medium (re-index all 39K chunks) | Low | Replace all-MiniLM-L6-v2. nomic-embed-text available in Ollama. |
| 2 | **Contextual chunking** | -35 to -49% retrieval failures | Medium (one-time re-index) | Low | Prepend context summaries to chunks before embedding. |
| 3 | **Query decomposition** | -40% hallucinations on complex queries | Low (single LLM call) | Low | Add pre-retrieval query analysis step. |
| 4 | **Instruction-tuned prefixes** | Significant retrieval boost (free with model upgrade) | Trivial | None | Add search_query:/search_document: prefixes. |

### Tier 2: Medium Impact, Medium Effort

| # | Technique | Expected Gain | Effort | Risk | Action |
|---|-----------|---------------|--------|------|--------|
| 5 | **Three-way hybrid** (add SPLADE) | Recall 0.72 -> 0.91 | Medium | Low | Add SPLADE sparse vectors alongside BM25+dense. |
| 6 | **CRAG loop** | -78% hallucinations | Medium | Medium | Needs evaluator model. Test against behavioral categories. |
| 7 | **Reranker** (FlashRank, 4MB CPU) | +33-40% accuracy | Low | HIGH | Current eval shows reranker destroys behavioral scores. MUST test carefully. |
| 8 | **Late chunking** | +24% embedding quality | Medium | Low | Requires switching to jina-embeddings-v3 or similar. |

### Tier 3: Lower Priority / Future (Workstation Era)

| # | Technique | Expected Gain | Effort | Risk | Action |
|---|-----------|---------------|--------|------|--------|
| 9 | **Matryoshka dims** | -67% index size, flexible quality | Low | Low | Free with nomic-embed-text-v1.5 upgrade. |
| 10 | **ColBERT reranking** | Near cross-encoder accuracy, fast | Medium | Medium | answerai-colbert-small (MIT). RAGatouille wrapper. |
| 11 | **GraphRAG / LazyGraphRAG** | 3.4x for relational queries | High | Medium | Only if relational queries become a requirement. |
| 12 | **Agentic RAG** | 25-40% fewer irrelevant retrievals | High | Medium | Multi-agent orchestration for workstation deployment. |
| 13 | **RAPTOR** | +20% on long-doc QA | High | Low | Long-context models may make this unnecessary. |
| 14 | **Self-RAG** | Adaptive retrieval | Very High | Medium | Requires model fine-tuning. Research-grade. |
| 15 | **HyDE** | +42pp precision (exploratory only) | Low | HIGH | Hallucination risk for fact-bound queries. Fallback only. |

### Recommended Upgrade Path

**Phase 1 (Now - Laptop, 8GB RAM)**:
1. Replace all-MiniLM-L6-v2 with **snowflake-arctic-embed-m-v2.0** (Apache 2.0, ~1.2GB,
   768-dim, 8192 ctx, MRL, +30% retrieval) OR **nomic-embed-text-v1.5** (Apache 2.0,
   Ollama, 137M, 768-dim, 8192 ctx, Matryoshka)
2. Add instruction prefixes (`search_query:` / `search_document:`)
3. Implement **contextual chunking** (prepend context to each chunk)
4. Re-index all 39,602 chunks with new model + contextual prefixes
5. Add **query decomposition** for multi-part queries
6. Validate against full 400q golden set
7. Update `config/default_config.yaml`: model_name + dimension (384 -> 768)

**Phase 2 (Workstation - Dual 3090, 48GB GPU)**:
1. Upgrade to **snowflake-arctic-embed-l-v2.0** (568M, 1024-dim, nDCG@10: 55.98)
2. Add **SPLADE** as third retrieval signal (three-way hybrid)
3. Test **FlashRank** or **mxbai-rerank-base-v2** reranking (carefully, with behavioral eval)
4. Implement **CRAG loop** for low-confidence retrievals
5. Consider **ColBERT** via RAGatouille for late-interaction retrieval
6. Evaluate **E5-Mistral-7B-Instruct** (7.1B, MIT, fits one 3090) for maximum retrieval quality

### Migration Notes

Changing embedding models requires **complete re-indexing of all 39,602 chunks**.
New embeddings are vector-incompatible with existing indices. Plan for:
1. Update `config/default_config.yaml` line 22: `model_name` and line 21: `dimension`
2. Re-run full indexing pipeline on D:\RAG Source Data
3. Re-validate with 400-question golden set eval
4. The 98% pass rate will likely change (expected to improve with better embeddings)
5. Budget ~6-12 hours for full re-index on laptop (or ~1-2 hours on workstation)

---

## SOURCES

### RAG Techniques
- [Microsoft GraphRAG GitHub](https://github.com/microsoft/graphrag)
- [LazyGraphRAG - Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
- [GraphRAG Accuracy Benchmark - FalkorDB](https://www.falkordb.com/blog/graphrag-accuracy-diffbot-falkordb/)
- [Knowledge Graph vs Vector RAG - Neo4j](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)
- [RAG vs GraphRAG 2025 Field Guide](https://medium.com/@Quaxel/rag-vs-graphrag-in-2025-a-builders-field-guide-82bb33efed81)
- [HyDE Hypothetical Document Embeddings - Zilliz](https://zilliz.com/learn/improve-rag-and-information-retrieval-with-hyde-hypothetical-document-embeddings)
- [HyDE - Haystack Documentation](https://docs.haystack.deepset.ai/docs/hypothetical-document-embeddings-hyde)
- [RAPTOR Paper - arXiv:2401.18059](https://arxiv.org/abs/2401.18059)
- [Enhanced RAPTOR 2025 - Frontiers](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1710121/full)
- [Reranking +40% Accuracy Guide 2025](https://app.ailog.fr/en/blog/guides/reranking)
- [Cross-Encoders, ColBERT, and LLM Rerankers](https://medium.com/@aimichael/cross-encoders-colbert-and-llm-based-re-rankers-a-practical-guide-a23570d88548)
- [Top 7 Rerankers for RAG 2025](https://www.analyticsvidhya.com/blog/2025/06/top-rerankers-for-rag/)
- [Best Reranking Model Guide - ZeroEntropy](https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025)
- [Mixedbread mxbai-rerank-large-v2 - HuggingFace](https://huggingface.co/mixedbread-ai/mxbai-rerank-large-v2)
- [FlashRank Lightweight Reranker - GitHub](https://github.com/PrithivirajDamodaran/FlashRank)
- [Cohere Rerank 4](https://cohere.com/blog/rerank-4)
- [Voyage AI rerank-2.5](https://blog.voyageai.com/2025/08/11/rerank-2-5/)
- [Contextual Chunking - Unstructured Platform](https://unstructured.io/blog/contextual-chunking-in-unstructured-platform-boost-your-rag-retrieval-accuracy)
- [Late Chunking - Jina AI](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [Late Chunking Paper - arXiv:2409.04701](https://arxiv.org/pdf/2409.04701)
- [Best Chunking Strategies 2025 - Firecrawl](https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025)
- [SPLADE Neural Sparse Retrieval - Qdrant](https://qdrant.tech/articles/modern-sparse-neural-retrieval/)
- [SPLADE Explained - Pinecone](https://www.pinecone.io/learn/splade/)
- [SPLADE GitHub - Naver](https://github.com/naver/splade)
- [ColBERT GitHub - Stanford](https://github.com/stanford-futuredata/ColBERT)
- [ColBERT in Practice 2025 - Sease](https://sease.io/2025/11/colbert-in-practice-bridging-research-and-industry.html)
- [answerai-colbert-small - Answer.AI](https://www.answer.ai/posts/2024-08-13-small-but-mighty-colbert.html)
- [RAGatouille - GitHub](https://github.com/AnswerDotAI/RAGatouille)
- [ModernBERT + ColBERT for RAG - arXiv:2510.04757](https://arxiv.org/abs/2510.04757)
- [Dense-Sparse Hybrid Retrieval - InfinityFlow](https://infiniflow.org/blog/best-hybrid-search-solution)
- [Hybrid Search RAG Tutorial 2025](https://app.ailog.fr/en/blog/guides/hybrid-search-rag)
- [CRAG Tutorial - DataCamp](https://www.datacamp.com/tutorial/corrective-rag-crag)
- [Self-RAG Project](https://selfrag.github.io/)
- [Agentic RAG Survey - arXiv:2501.09136](https://arxiv.org/html/2501.09136v3)
- [Agentic RAG Enterprise Guide 2026](https://datanucleus.dev/rag-and-agentic-ai/agentic-rag-enterprise-guide-2026)
- [Query Decomposition for RAG - NVIDIA](https://docs.nvidia.com/rag/latest/query_decomposition.html)
- [Query Decomposition Research - Ailog](https://app.ailog.fr/en/blog/news/query-decomposition-research)
- [Query Decomposition - Haystack](https://haystack.deepset.ai/blog/query-decomposition)

### Embedding Models
- [MTEB Leaderboard - HuggingFace](https://huggingface.co/spaces/mteb/leaderboard)
- [Top MTEB Embedding Models - Modal](https://modal.com/blog/mteb-leaderboard-article)
- [Best Open-Source Embedding Models 2026 - BentoML](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [16 Best Open Source Embedding Models - AIMultiple](https://research.aimultiple.com/open-source-embedding-models/)
- [Open-Source Embeddings Benchmarked - Supermemory](https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/)
- [nomic-embed-text-v1.5 - HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [nomic-embed-text-v2-moe - HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)
- [Nomic Embed MTEB Arena Elo](https://www.nomic.ai/blog/posts/evaluating-embedding-models)
- [Snowflake Arctic Embed - GitHub](https://github.com/Snowflake-Labs/arctic-embed)
- [snowflake-arctic-embed-l-v2.0 - HuggingFace](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0)
- [Snowflake Arctic Embed Launch Blog](https://www.snowflake.com/en/engineering-blog/introducing-snowflake-arctic-embed-snowflakes-state-of-the-art-text-embedding-family-of-models/)
- [Microsoft E5 Embedding - Research](https://www.microsoft.com/en-us/research/publication/text-embeddings-by-weakly-supervised-contrastive-pre-training/)
- [E5 Text Embeddings DeepWiki](https://deepwiki.com/microsoft/unilm/3.4-e5:-text-embeddings)
- [jina-embeddings-v3 - Jina AI](https://jina.ai/news/jina-embeddings-v3-a-frontier-multilingual-embedding-model/)
- [jina-embeddings-v3 Paper - arXiv:2409.10173](https://arxiv.org/abs/2409.10173)
- [NVIDIA NV-Embed MTEB Blog](https://developer.nvidia.com/blog/nvidia-text-embedding-model-tops-mteb-leaderboard/)
- [Matryoshka Representation Learning - arXiv:2205.13147](https://arxiv.org/abs/2205.13147)
- [Matryoshka Embeddings Guide - HuggingFace](https://huggingface.co/blog/matryoshka)
- [Matryoshka Guide - Supermemory](https://supermemory.ai/blog/matryoshka-representation-learning-the-ultimate-guide-how-we-use-it/)
- [Choosing Embedding Models - Pinecone](https://www.pinecone.io/learn/series/rag/embedding-models-rundown/)
- [MMTEB Benchmark - OpenReview](https://openreview.net/forum?id=zl3pfz4VCV)
