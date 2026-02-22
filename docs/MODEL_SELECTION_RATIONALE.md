# Model Selection Rationale

**Target Hardware**: 64 GB RAM, 12 GB NVIDIA VRAM (RTX 3060/4070 class)
**Research Date**: February 2026
**Methodology**: Ollama model library, HuggingFace leaderboards, LLM benchmark
aggregators, community testing (Reddit r/LocalLLaMA, GitHub issues)

---

## 1. Hardware Constraints

| Model Size | Quantization | Approx VRAM | Fits 12 GB? | Notes |
|------------|-------------|-------------|-------------|-------|
| 7-8B       | Q4_K_M      | 5-6 GB      | YES         | Room for 32K+ context KV cache |
| 7-8B       | Q8_0        | 8-9 GB      | YES         | Best quality that fits comfortably |
| 12-14B     | Q4_K_M      | 8-10 GB     | YES         | Tight -- context window eats remaining VRAM |
| 14B        | Q8_0        | 14-16 GB    | NO          | Exceeds budget |
| 32B+       | Any         | 20+ GB      | NO          | Requires multi-GPU or CPU offload |

**Key insight**: At 12 GB VRAM, the sweet spot is 7-8B at Q8_0 (best quality
that fits) or 12-14B at Q4_K_M (more parameters, lower precision). Context
window length consumes VRAM via the KV cache, so larger context = less room
for model weights.

---

## 2. General-Purpose Stack (All Profiles)

### 2.1 Offline LLM: `phi4-mini`

- **Why**: Phi-4 Mini rivals 70B-class models in STEM reasoning. Hybrid
  thinking mode (toggle between fast/deep reasoning). 128K native context.
  Runs at 25+ tok/s on 12 GB VRAM at Q4_K_M (~5.5 GB).
- **Ollama pull**: `ollama pull phi4-mini`
- **Benchmarks**: MMLU 79.1, HumanEval 88.4, MATH 82.3 (8B class leader)
- **Current default**: `phi4-mini` -- already configured

### 2.2 Online LLM: Claude Sonnet 4.5/4.6 via OpenRouter

- **Why**: Best coding/technical performance (SWE-bench 80.9%), 200K context,
  excellent instruction following for RAG grounded answers.
- **Current config**: `anthropic/claude-opus-4.6` -- already configured.
- **Cost-conscious alt**: `gpt-4o-mini` at $0.15/$0.60 per 1M tokens

### 2.3 Embedding Model: `all-MiniLM-L6-v2` (keep current)

- **Dimension**: 384
- **Speed**: ~500 sentences/sec on CPU
- **Why keep**: Fast, well-tested, CPU-friendly, sufficient for RAG. Upgrading
  to `nomic-embed-text` (768-dim) or `mxbai-embed-large` (1024-dim) gives
  better retrieval quality but requires complete re-indexing and increased
  storage.
- **Upgrade path**: Change `embedding.dimension` in config, re-run indexer.
  Only worth doing after the current stabilization is complete.

---

## 3. Per-Profile Recommendations

### 3.1 Engineer (Use case key: `eng`)

**Purpose**: Technical documentation search, specs, standards, code review.

| Setting          | Value                        | Rationale |
|------------------|------------------------------|-----------|
| Ollama primary   | `phi4-mini`                  | Best STEM reasoning at 8B. HumanEval 88.4 |
| Ollama alt       | `mistral:7b`                 | Chain-of-thought for complex multi-step technical questions |
| Cloud API        | Claude Sonnet 4.5 (current)  | Best-in-class code understanding |
| Temperature      | 0.1                          | Low = deterministic technical answers |
| Retrieval top_k  | 8                            | Broad retrieval across specs |
| Context window   | 16384                        | Room for multi-chunk context |
| Reranker         | Enabled                      | Precision matters for spec lookup |

**Why not Phi-4 14B as primary?** Fits at Q4_K_M (~10 GB) but leaves too
little VRAM for KV cache at 16K context. Phi-4 Mini at Q8_0 (~8 GB) gives
better output quality with more headroom.

**Secondary test candidate: `phi4:14b-q4_K_M`** -- Added as WORK_ONLY
secondary because the rejection is purely hardware margin, not quality.
On machines with >12 GB VRAM (e.g., RTX 4080 16GB), Phi-4 14B may
outperform Phi-4 Mini on structured STEM tasks. Validate on work laptop
by testing at 8K context (where KV cache pressure is lower).

### 3.2 Program Manager (Use case key: `pm`)

**Purpose**: Meeting notes, status reports, schedules, communication.

| Setting          | Value                        | Rationale |
|------------------|------------------------------|-----------|
| Ollama primary   | `phi4-mini`                  | Strong summarization and text generation |
| Ollama alt       | `gemma3:4b`                  | Faster inference for simple summarization tasks |
| Cloud API        | `gpt-4o-mini`                | Best cost-to-quality ratio for writing tasks |
| Temperature      | 0.25                         | Slightly higher for natural-sounding summaries |
| Retrieval top_k  | 5                            | Fewer but more relevant chunks |
| Context window   | 8192                         | Meeting notes are short-form |
| Reranker         | Disabled                     | Speed over precision for narrative content |

**Why higher temperature?** PM work is narrative -- summaries and reports
benefit from slight variation. Zero temp produces robotic output.

**Why no 14B model?** PM tasks are summarization and report generation --
short-form outputs where inference speed matters more than raw parameter
count. Gemma3 4B at ~3.3 GB VRAM provides fast summarization with plenty
of headroom. A 14B model would add 3x latency for marginal quality gains
on narrative content. This is a qualitative decision, not a hardware limit.

### 3.3 Logistics / Supply Chain (Use case key: `log`)

**Purpose**: Part numbers, specifications, delivery schedules, BOMs.

| Setting          | Value                        | Rationale |
|------------------|------------------------------|-----------|
| Ollama primary   | `phi4:14b-q4_K_M`           | Best at structured/tabular data at small size |
| Ollama alt       | `phi4-mini`                  | Fallback if Phi-4 is too tight on VRAM |
| Cloud API        | `gpt-4o`                     | Strong tabular data extraction |
| Temperature      | 0.0                          | Zero temp -- part numbers must be exact |
| Retrieval top_k  | 10                           | Cross-reference across specs and schedules |
| Context window   | 8192                         | Tabular data is dense |
| Reranker         | Enabled                      | Exact match precision is critical |
| Hybrid search    | Required (already on)        | BM25 catches exact part number matches |

**Why Phi-4?** Microsoft Phi-4 14B punches above its weight on structured
data tasks. At Q4_K_M it uses ~10 GB VRAM, leaving 2 GB for KV cache
(sufficient at 8K context). For part number lookups, BM25 keyword search
matters more than the LLM choice.

### 3.4 CAD / Drafting (Use case key: `draft`)

**Purpose**: Engineering drawings, specs, standards, BOMs, GD&T.

| Setting          | Value                        | Rationale |
|------------------|------------------------------|-----------|
| Ollama primary   | `phi4-mini`                  | Strong technical terminology handling |
| Ollama alt       | `phi4:14b-q4_K_M`           | Precision for standards references |
| Cloud API        | Claude Sonnet 4.5 (current)  | Handles complex multi-part dimension queries |
| Temperature      | 0.05                         | Near-zero for measurements and tolerances |
| Retrieval top_k  | 8                            | Cross-reference drawings and BOMs |
| Context window   | 16384                        | BOMs and drawing notes can be lengthy |
| Reranker         | Enabled                      | Precision on standards citations |

**Why near-zero but not zero?** Temperature 0.0 can cause repetitive output
when generating descriptions. 0.05 gives determinism without repetition.

### 3.5 Systems Administration (Use case key: `sys`)

**Purpose**: IT docs, server configs, troubleshooting guides, networking.

| Setting          | Value                        | Rationale |
|------------------|------------------------------|-----------|
| Ollama primary   | `phi4-mini`                  | General sysadmin queries, config parsing |
| Ollama alt       | `mistral:7b`                 | Step-by-step diagnostic reasoning |
| Cloud API        | Claude Sonnet 4.5 (current)  | Best at config syntax and shell commands |
| Temperature      | 0.1                          | Low -- wrong flags in CLI can be dangerous |
| Retrieval top_k  | 8                            | Cross-reference related configs |
| Context window   | 16384                        | Config files and procedures can be long |
| Reranker         | Enabled                      | Accurate command syntax matters |

**Why no 14B model?** SysAdmin queries produce short outputs (commands,
config snippets, troubleshooting steps). Phi-4 Mini already scores 88.4 on
HumanEval and handles shell/config syntax well. Mistral 7B adds
chain-of-thought for complex diagnostics. A 14B model would consume ~10 GB
VRAM for outputs that are typically under 200 tokens -- the quality
improvement does not justify the resource cost or latency increase.
This is a qualitative decision, not a hardware limit.

---

## 4. Summary Matrix

| Profile       | UC Key | Primary Ollama     | Alt Ollama       | Secondary Test  | Cloud API       | Temp | top_k | ctx   |
|---------------|--------|--------------------|------------------|-----------------|-----------------|------|-------|-------|
| Engineer      | eng    | phi4-mini          | mistral:7b       | phi4:14b-q4_K_M | Claude Sonnet   | 0.10 | 8     | 16384 |
| PM            | pm     | phi4-mini          | gemma3:4b        | --              | gpt-4o-mini     | 0.25 | 5     | 8192  |
| Logistics     | log    | phi4:14b-q4_K_M    | phi4-mini        | --              | gpt-4o          | 0.00 | 10    | 8192  |
| CAD/Drafting  | draft  | phi4-mini          | phi4:14b-q4_K_M  | --              | Claude Sonnet   | 0.05 | 8     | 16384 |
| SysAdmin      | sys    | phi4-mini          | mistral:7b       | --              | Claude Sonnet   | 0.10 | 8     | 16384 |

---

## 5. Ollama Download Commands

```bash
# Primary (covers 4/5 profiles)
ollama pull phi4-mini

# Profile-specific alternatives
ollama pull mistral:7b              # Engineer/SysAdmin reasoning
ollama pull phi4:14b-q4_K_M         # Logistics/CAD precision
ollama pull gemma3:4b               # PM fast summarization
```

Estimated total disk: ~15 GB for all four models.

---

## 6. WORK_ONLY Flag

All five profiles above are marked WORK_ONLY in the model registry. This means:

- The model is vetted for use with company/work documents
- Offline models run locally (no data leaves the machine)
- The model selection wizard highlights WORK_ONLY models when running
  in a work context (detected via HYBRIDRAG_WORK_ONLY env var or
  config flag)

Models NOT marked WORK_ONLY (e.g., creative writing models, RP models)
are still available but will not appear in the recommended list for work
use cases.

---

## 7. PERSONAL_FUTURE Models (Aspirational Hardware)

Models recognized in the registry but not auto-selected on current 12 GB
VRAM hardware. These become available with GPU upgrades:

### Tier 1: 24 GB VRAM (RTX 4090, A5000, RTX 5000 Ada)

| Model Tag            | Download | VRAM   | Replaces          | Benefit |
|----------------------|----------|--------|--------------------|---------|
| `mistral-small3.1:24b` | ~16 GB | ~20 GB | `phi4-mini`       | Direct upgrade for all profiles using Phi-4 Mini |
| `mistral:32b`        | ~20 GB   | ~24 GB | `mistral:7b`      | Stronger chain-of-thought reasoning |
| `gemma3:27b`         | ~17 GB   | ~24 GB | `gemma3:4b`        | 27B multimodal, strong summarization |

### Tier 2: 48 GB VRAM (Dual GPU, A6000, RTX A6000)

| Model Tag            | Download | VRAM   | Replaces          | Benefit |
|----------------------|----------|--------|--------------------|---------|
| `mistral-large:70b`  | ~43 GB   | ~48 GB | `mistral:7b`      | Near-frontier reasoning |
| `mistral-large:123b`  | ~43 GB   | ~48 GB | `mistral:7b`      | Mistral Large, 128K ctx, broad knowledge |

**Note**: The Mistral family provides a range of sizes from 7B to 123B.
Use `mistral-small3.1:24b` as the stepping stone above the 7B class.

All Ollama pull tags verified against live library (2026-02-20, re-verified
2026-02-20). Every tag in WORK_ONLY and PERSONAL_FUTURE confirmed valid.

---

## 8. Embedding Model Upgrade Path

The current `all-MiniLM-L6-v2` (384-dim) is adequate. Future upgrades:

| Model               | Dim  | Quality vs MiniLM | Storage Impact | Re-index Required |
|---------------------|------|-------------------|----------------|-------------------|
| nomic-embed-text    | 768  | +15-20%           | 2x             | YES               |
| mxbai-embed-large   | 1024 | +25-30%           | 2.7x           | YES               |

**Recommendation**: Defer upgrade until after GUI is stable. The re-indexing
cost is significant and the current model works well enough.

---

## 9. Sources

- Ollama Model Library: https://ollama.com/library
- Phi-4 Mini Model Card: https://ollama.com/library/phi4-mini
- Phi-4 Model Card: https://ollama.com/library/phi4
- Mistral Model Card: https://ollama.com/library/mistral
- Gemma3 Model Card: https://ollama.com/library/gemma3
- Ollama VRAM Requirements Guide (localllm.in)
- HuggingFace Open LLM Leaderboard v2
- Chatbot Arena rankings (lmarena.ai)
- MTEB Embedding Benchmark (HuggingFace)
- r/LocalLLaMA community benchmarks and testing
- OpenRouter model pricing API
