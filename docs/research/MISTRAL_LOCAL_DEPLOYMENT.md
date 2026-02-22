# Mistral-Small-24B (mistral-small3.1:24b) Local Deployment on Dual RTX 3090

**Research Date:** 2026-02-21
**Target Hardware:** Dual NVIDIA RTX 3090 (24GB VRAM each, 48GB total), 64GB system RAM
**Model:** mistral-small3.1:24b (Mistral Small 3.1, 24B parameters, Apache 2.0)
**Deployment Stack:** Ollama (llama.cpp backend)
**Purpose:** RAG system inference for defense contractor use

---

## Table of Contents

1. [Running via Ollama -- Does It Work Out of the Box?](#1-running-via-ollama----does-it-work-out-of-the-box)
2. [Quantization Options and VRAM Requirements](#2-quantization-options-and-vram-requirements)
3. [Expected Performance (Tokens per Second)](#3-expected-performance-tokens-per-second)
4. [Can 48GB Run FP16?](#4-can-48gb-run-fp16)
5. [Multi-GPU Split Configuration in Ollama](#5-multi-gpu-split-configuration-in-ollama)
6. [Ollama Multi-GPU Performance Characteristics](#6-ollama-multi-gpu-performance-characteristics)
7. [Defense Contractor Approval Considerations](#7-defense-contractor-approval-considerations)
8. [Context Window and Memory Scaling](#8-context-window-and-memory-scaling)
9. [Comparison with Alternatives (phi4:14b, mistral-nemo:12b)](#9-comparison-with-alternatives-phi414b-mistral-nemo12b)
10. [Known Issues, Bugs, and Gotchas](#10-known-issues-bugs-and-gotchas)
11. [Recommended Configuration](#11-recommended-configuration)
12. [Sources](#12-sources)

---

## 1. Running via Ollama -- Does It Work Out of the Box?

### Model Tag

The official Ollama library tag is:

```bash
ollama pull mistral-small3.1:24b
```

This pulls the default Q4_K_M quantization (15 GB). The model requires **Ollama 0.6.5 or higher**.

### Available Official Tags

| Tag | Quant | Size | Hash |
|-----|-------|------|------|
| `mistral-small3.1:24b` (default) | Q4_K_M | 15 GB | b9aaf0c2586a |
| `mistral-small3.1:24b-instruct-2503-q4_K_M` | Q4_K_M | 15 GB | b9aaf0c2586a |
| `mistral-small3.1:24b-instruct-2503-q8_0` | Q8_0 | 26 GB | 79252b8a3eb5 |
| `mistral-small3.1:24b-instruct-2503-fp16` | FP16 | 48 GB | 5b05d65a969a |

**Note:** Q5_K_M is NOT available in the official Ollama library for mistral-small3.1. Community models (e.g., `JollyLlama/Mistral-Small-3.1-24B`) provide Q5_K_M, Q6_K, and other variants. Alternatively, bartowski and Unsloth provide GGUF files on HuggingFace for manual import.

Source: https://ollama.com/library/mistral-small3.1/tags

### Architecture Note

**[NOVEL FIND]** The mistral-small3.1 model uses the `mistral3` architecture in Ollama, while the older mistral-small:24b (v3.0) used the `llama` architecture. Community reports confirm that the mistral3 architecture variant is **significantly slower** than the llama architecture variant for the same model weights. This is a critical performance consideration.

Source: https://github.com/ollama/ollama/issues/10553

### Does It Work Out of the Box?

**Partially.** The Q4_K_M variant (15 GB) loads and runs on a single RTX 3090 at default context (4096 tokens) without issues. However, multiple bugs affect GPU utilization, VRAM estimation, and multi-GPU splitting. See Section 10 for the full bug list.

---

## 2. Quantization Options and VRAM Requirements

### GGUF File Sizes (Model Weights Only)

Data from Unsloth and bartowski HuggingFace GGUF repositories:

| Quantization | File Size | Bits/Weight | Quality Impact |
|-------------|-----------|-------------|----------------|
| IQ1_S | 5.56 GB | ~1 bit | Severe degradation |
| IQ2_XXS | 6.75 GB | ~2 bit | Major degradation |
| Q2_K | 8.89 GB | ~2.5 bit | Significant degradation |
| Q3_K_S | 10.4 GB | ~3 bit | Noticeable degradation |
| Q3_K_M | 11.5 GB | ~3.5 bit | Moderate degradation |
| **Q4_K_S** | **13.5 GB** | ~4 bit | Minimal degradation |
| **Q4_K_M** | **14.3 GB** | ~4.5 bit | **Recommended -- minimal quality loss** |
| **Q5_K_S** | **16.3 GB** | ~5 bit | Very minor quality loss |
| **Q5_K_M** | **16.8 GB** | ~5.25 bit | Very minor quality loss |
| Q6_K | 19.3 GB | ~6 bit | Near-lossless |
| **Q8_0** | **25.1 GB** | 8 bit | Near-original quality |
| Q8_K_XL | 29 GB | ~8.5 bit | Near-original quality |
| BF16/FP16 | 47.2 GB | 16 bit | Original quality |

Sources:
- https://huggingface.co/unsloth/Mistral-Small-3.1-24B-Instruct-2503-GGUF
- https://huggingface.co/bartowski/mistralai_Mistral-Small-3.1-24B-Instruct-2503-GGUF

### Total VRAM Requirements (Weights + KV Cache + Overhead)

The numbers below include model weights, KV cache at various context lengths, and Ollama runtime overhead. The vision projector adds approximately 738 MB in weights plus up to 8.8 GB for the compute graph (see Section 10).

| Quantization | 4K Context | 8K Context | 32K Context | 56K Context | 128K Context |
|-------------|-----------|-----------|------------|------------|-------------|
| Q4_K_M | ~17-20 GB | ~18-22 GB | ~22-26 GB | ~27-31 GB | ~36 GB |
| Q5_K_M | ~19-22 GB | ~20-24 GB | ~24-28 GB | ~29-33 GB | ~38 GB |
| Q8_0 | ~28-30 GB | ~29-32 GB | ~33-36 GB | ~38-41 GB | ~46 GB |
| FP16 | ~50-55 GB | ~51-56 GB | ~55-60 GB | ~60-65 GB | ~70+ GB |

**[NOVEL FIND]** Ollama issue #10177 reports that mistral-small3.1 in Q4 uses **double the expected VRAM** at default 4096 context (~29 GB observed vs ~17 GB expected). One commenter noted Ollama reports 32 GB usage but nvidia-smi shows only ~20 GB actual allocation. The discrepancy is attributed to the vision projector's worst-case compute graph estimate. Other vision models (Gemma3, Llama3.2-vision) do not exhibit this problem.

Sources:
- https://github.com/ollama/ollama/issues/10177
- https://github.com/ollama/ollama/issues/10615

---

## 3. Expected Performance (Tokens per Second)

### Single RTX 3090 (Q4_K_M, Default Context)

No exact community benchmark exists for this precise combination. Estimates are derived from related data points:

| Source/Method | Estimated tok/s | Notes |
|--------------|----------------|-------|
| Bandwidth-limited theoretical | 45-65 tok/s | 936 GB/s / 14.3 GB model, ~70% efficiency |
| RTX 4090 community reports (Q4_K_M) | 30-50 tok/s | 3090 is ~80% of 4090 bandwidth |
| RTX 5090 Ollama benchmark (Q4, mistral-small:24b) | ~93 tok/s | Extrapolate ~40-50% of this for 3090 |
| General 3090 community reports (24B class) | 25-35 tok/s | Conservative real-world range |
| **Best estimate for RTX 3090 + Q4_K_M** | **30-45 tok/s** | **Generation speed (not prompt processing)** |

### Prompt Processing Speed

Prompt processing (prefill) is compute-bound rather than bandwidth-bound and benefits from the 3090's 35.6 TFLOPS FP16. Expect roughly **200-400 tokens/sec** for prompt ingestion at Q4_K_M, depending on batch size and context length.

### Performance by Quantization Level (Single RTX 3090, Estimated)

| Quantization | Generation (tok/s) | Prompt Processing (tok/s) | Fits Single 3090? |
|-------------|-------------------|--------------------------|-------------------|
| Q4_K_M | 30-45 | 200-400 | Yes (at 4K-32K ctx) |
| Q5_K_M | 25-40 | 180-350 | Yes (at 4K-16K ctx) |
| Q8_0 | 20-30 | 150-300 | No (26 GB > 24 GB) |
| FP16 | 10-15 (split) | 100-200 (split) | No (48 GB, needs 2 GPUs) |

### Dual RTX 3090 (Layer Split, No NVLink)

When splitting across two GPUs via PCIe, expect a **10-30% performance penalty** on generation speed vs single-GPU due to inter-GPU communication overhead. The penalty is worse without NVLink.

| Quantization | Dual-GPU Generation (tok/s) | Notes |
|-------------|---------------------------|-------|
| Q4_K_M | 25-40 | May not need split; single GPU fits |
| Q8_0 | 18-28 | Split across 2 GPUs |
| FP16 | 8-15 | Tight fit in 48 GB, minimal headroom |

### Dual RTX 3090 (NVLink)

If you have an NVLink bridge (RTX 3090 is the last consumer GPU to support NVLink 3.0 at 112.5 GB/s bidirectional), expect **40-60% improvement** over PCIe-only multi-GPU:

| Quantization | NVLink Dual-GPU Generation (tok/s) | Notes |
|-------------|-----------------------------------|-------|
| Q8_0 | 22-35 | Good quality/speed tradeoff |
| FP16 | 12-20 | Possible but tight on VRAM |

Sources:
- https://www.hardware-corner.net/gpu-ranking-local-llm/
- https://www.ikangai.com/the-complete-guide-to-running-llms-locally-hardware-software-and-performance-essentials/
- https://localaimaster.com/blog/best-gpus-for-ai-2025
- https://github.com/ollama/ollama/issues/9701
- https://www.servethehome.com/dual-nvidia-geforce-rtx-3090-nvlink-performance-review-asus-zotac/

---

## 4. Can 48GB Run FP16?

### Short Answer: Barely, and Not Recommended

The FP16 model weights alone are **47.2 GB**. With 48 GB total VRAM across two GPUs, the math is extremely tight:

- Model weights: 47.2 GB
- KV cache at 4K context: ~2-3 GB
- Vision projector graph: ~8.8 GB (worst case)
- Ollama runtime overhead: ~0.5-1 GB
- **Total needed: ~58-60 GB at 4K context**

**FP16 does NOT fit in 48 GB VRAM** when running through Ollama with the vision projector loaded. Even without the vision projector overhead, the model weights alone (47.2 GB) plus minimal KV cache (~2 GB) exceed 48 GB.

### Possible Workaround

If you use a text-only GGUF without the vision projector (from HuggingFace), the overhead drops significantly. However, model weights (47.2 GB) plus even minimal KV cache still make this impractical. **Q8_0 is the highest practical quantization for dual 3090s.**

### Recommendation

Use **Q8_0 (26 GB)** for near-original quality, which fits comfortably in 48 GB with room for 32K+ context. For maximum context length, use **Q4_K_M (15 GB)**.

---

## 5. Multi-GPU Split Configuration in Ollama

### Automatic Behavior

Ollama automatically detects multiple GPUs. Its default behavior:

1. If the model fits on a single GPU, it loads entirely on one GPU (best performance).
2. If the model exceeds one GPU's VRAM, Ollama splits layers across all available GPUs.
3. If total GPU VRAM is insufficient, remaining layers spill to system RAM (CPU inference -- very slow).

### Key Environment Variables

```bash
# Make both GPUs visible (usually automatic)
export CUDA_VISIBLE_DEVICES=0,1

# Force spreading across all GPUs (even if model fits on one)
export OLLAMA_SCHED_SPREAD=1

# Set number of layers to offload to GPU (-1 = all)
export OLLAMA_NUM_GPU=-1

# Enable flash attention (reduces VRAM, required for KV cache quantization)
export OLLAMA_FLASH_ATTENTION=1

# Quantize KV cache to reduce VRAM (options: f16, q8_0, q4_0)
export OLLAMA_KV_CACHE_TYPE=q8_0

# Reserve VRAM headroom per GPU (in bytes, e.g., 512MB)
export OLLAMA_GPU_OVERHEAD=536870912

# Disable new engine if performance is degraded (see Section 10)
export OLLAMA_NEW_ENGINE=false
```

### Modelfile Configuration

You can also control GPU offloading via a Modelfile:

```
FROM mistral-small3.1:24b-instruct-2503-q8_0
PARAMETER num_gpu 999
PARAMETER num_ctx 32768
```

Setting `num_gpu` to 999 tells Ollama to offload as many layers as possible to GPU(s).

### Recommended Setup for Dual 3090s

For a systemd service (Linux) or environment configuration (Windows):

```bash
CUDA_VISIBLE_DEVICES=0,1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_GPU=-1
```

### GPU UUID Selection

For precise GPU control, use UUIDs instead of numeric IDs:

```bash
nvidia-smi -L
# Output: GPU 0: NVIDIA GeForce RTX 3090 (UUID: GPU-xxxxx)
#         GPU 1: NVIDIA GeForce RTX 3090 (UUID: GPU-yyyyy)

export CUDA_VISIBLE_DEVICES=GPU-xxxxx,GPU-yyyyy
```

### Alternative: Two Separate Ollama Instances

Instead of splitting one model across two GPUs, run two independent Ollama servers:

- Instance A: GPU 0, port 11434
- Instance B: GPU 1, port 11435

Then load-balance with nginx or HAProxy. This avoids inter-GPU communication overhead entirely and is ideal for concurrent RAG queries.

Sources:
- https://docs.ollama.com/gpu
- https://docs.ollama.com/faq
- https://gist.github.com/pykeras/0b1e32b92b87cdce1f7195ea3409105c
- https://markaicode.com/multi-gpu-ollama-setup-large-model-inference/
- https://github.com/ollama/ollama/issues/7104
- https://dasroot.net/posts/2025/12/ollama-multi-gpu-setup-larger-models/

---

## 6. Ollama Multi-GPU Performance Characteristics

### What Ollama Does: Layer-Wise Splitting (Naive Pipeline Parallelism)

Ollama (via llama.cpp) distributes model layers sequentially across GPUs. GPU 0 gets layers 0-N, GPU 1 gets layers N+1-M. This is NOT tensor parallelism -- each layer's computation happens entirely on one GPU.

**Key limitation:** During generation, only one GPU computes at a time for each token. The other GPU waits. Data must cross the PCIe bus (or NVLink) between layer groups, adding latency per token.

### What Ollama Does NOT Do: Tensor Parallelism

Ollama/llama.cpp does **not** support tensor parallelism, where each layer's matrix multiplications are split across GPUs to run in parallel. This means:

- **Adding a second GPU does NOT double speed.** It primarily allows fitting larger models.
- **Inter-GPU communication is sequential,** not pipelined.
- **PCIe overhead can negate gains.** Some users report performance DROP when adding a second GPU for models that already fit on one.

### Actual Speedup (or Lack Thereof)

| Scenario | Speedup from 2nd GPU |
|----------|---------------------|
| Model fits on 1 GPU | Negative (slower due to split overhead) |
| Model needs 2 GPUs, PCIe only | ~0.7-0.9x vs CPU offload baseline |
| Model needs 2 GPUs, NVLink | ~1.3-1.6x vs PCIe split |
| Two instances, one per GPU (concurrency) | 2x throughput (not latency) |

### When Dual GPUs Help

1. **Fitting larger models:** Q8_0 (26 GB) or FP16 (48 GB) that exceed single-GPU VRAM.
2. **Concurrent serving:** Run two separate model instances for parallel RAG queries.
3. **Different models simultaneously:** Run mistral-small3.1 on GPU 0 and a smaller model (phi4-mini) on GPU 1.

### When Dual GPUs Hurt

1. **Q4_K_M already fits on one GPU:** Splitting a 15 GB model across two GPUs adds latency with no benefit.
2. **Without NVLink:** PCIe 4.0 x16 provides ~32 GB/s vs NVLink's 112.5 GB/s. The 3.5x bandwidth difference matters.

### Alternatives for True Multi-GPU Speed

| Tool | Parallelism | Best For |
|------|------------|---------|
| **vLLM** | Tensor parallelism | Production serving, max throughput |
| **ExLlamaV2** | Tensor parallelism | Quantized models (EXL2 format) |
| **TensorRT-LLM** | Tensor parallelism | NVIDIA-optimized, up to 70% faster than llama.cpp |
| **Ollama** | Layer split only | Single GPU, ease of use |

**[NOVEL FIND]** A community-contributed PR for llama.cpp (#5527) tested row-split mode (`-sm row`) on 3x P40 24GB GPUs and found **40-70% improvement** over layer-split mode. Row split distributes matrix multiplications across GPUs at the row level, closer to tensor parallelism. However, this mode puts all KV cache on GPU 0, creating lopsided memory utilization.

Sources:
- https://www.ahmadosman.com/blog/do-not-use-llama-cpp-or-ollama-on-multi-gpus-setups-use-vllm-or-exllamav2/
- https://www.arsturn.com/blog/will-a-second-gpu-speed-up-ollama-the-surprising-truth
- https://www.arsturn.com/blog/multi-gpu-showdown-benchmarking-vllm-llama-cpp-ollama-for-maximum-performance
- https://github.com/ollama/ollama/pull/5527
- https://ai-box.eu/en/large-language-models-en/empowering-process-automation-with-n8n-ollama-and-open-source-llms/how-to-scale-ollama-with-two-or-more-gpus/1803/

---

## 7. Defense Contractor Approval Considerations

### Mistral AI Corporate Profile

| Attribute | Detail |
|-----------|--------|
| **Company** | Mistral AI |
| **Founded** | April 2023, Paris, France |
| **Founders** | Arthur Mensch, Guillaume Lample, Timothee Lacroix (ex-Google DeepMind and Meta) |
| **Headquarters** | Paris, France |
| **Jurisdiction** | European Union (French law) |
| **Valuation** | EUR 12 billion ($14 billion) as of September 2025 |
| **Major Investors** | ASML (Netherlands, 11%), Brookfield (Canada), UAE sovereign fund |
| **NATO Member State** | Yes -- France is a founding NATO member |
| **NDAA Section 889** | NOT subject to ban (applies only to Chinese entities: Huawei, ZTE, Hikvision, Dahua, Hytera) |
| **ITAR/EAR** | Not applicable -- Mistral AI is a French commercial entity, not a U.S. person/entity |
| **Chinese Origin** | NO -- French company, French founders, EU jurisdiction |
| **Five Eyes/Allied** | France is not Five Eyes but is NATO and EU ally |

### License: Apache 2.0

The Apache 2.0 license is one of the most permissive open-source licenses:

- **Commercial use:** Allowed without restriction
- **Modification:** Allowed
- **Distribution:** Allowed
- **Patent grant:** Explicit patent license included
- **Attribution:** Required (include license notice)
- **No copyleft:** No requirement to open-source derivative works
- **No remote kill switch:** Unlike Google's Gemma terms, no clause allowing remote revocation
- **No usage restrictions:** Unlike Meta's Llama license, no ITAR-triggering usage restrictions

### Defense Partnerships

Mistral AI has active defense partnerships that strengthen its credibility:

- **French Ministry of Armed Forces:** Framework agreement (2026-2030) for AI integration across all branches. Models deployed on French sovereign infrastructure.
- **Helsing:** Partnership with German defense AI startup (EUR 5 billion valuation).
- **Singapore Home Team Science and Technology Agency:** Robotics and cybersecurity.

The French government explicitly chose Mistral for "technological sovereignty" -- keeping AI models and data on national infrastructure, reducing exposure to foreign jurisdictions.

### Compliance Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Not Chinese origin | PASS | French company, EU jurisdiction |
| Not NDAA-banned entity | PASS | NDAA Section 889 targets only specific Chinese companies |
| Permissive license | PASS | Apache 2.0, no usage restrictions |
| No ITAR implications | PASS | Open-source model, no controlled technical data |
| NATO-allied origin | PASS | France is founding NATO member |
| Defense sector track record | PASS | Active French military contract |
| No remote kill switch | PASS | Apache 2.0 has no revocation clause |
| Air-gapped deployment | PASS | GGUF format runs fully offline via Ollama |
| EU AI Act compliant | PASS | Mistral actively designs for EU regulatory compliance |

**Recommendation:** Mistral-small3.1:24b is APPROVED for defense contractor use. It is from a NATO-allied nation (France), released under the permissive Apache 2.0 license, has an active contract with the French military, and can be deployed fully air-gapped with no phone-home requirements.

Sources:
- https://en.wikipedia.org/wiki/Mistral_AI
- https://mistral.ai/about
- https://www.techrepublic.com/article/news-mistral-french-military-ai-deal/
- https://www.tekedia.com/france-taps-mistral-ai-for-military-use-marking-a-strategic-shift-toward-sovereign-artificial-intelligence/
- https://thedefensepost.com/2026/01/15/mistral-ai-france-defense/
- https://legal.mistral.ai/terms/license-notice
- https://www.theregister.com/2025/12/02/mistral_3/

---

## 8. Context Window and Memory Scaling

### Maximum Context Window

Mistral Small 3.1 officially supports **128K tokens** (131,072). However, achievable context length depends on available VRAM and quantization.

### KV Cache Memory Scaling

The KV cache grows linearly with context length. For a 24B-parameter model:

| Context Length | Estimated KV Cache (FP16) | KV Cache (Q8_0) | KV Cache (Q4_0) |
|---------------|--------------------------|-----------------|-----------------|
| 4,096 | ~2-3 GB | ~1-1.5 GB | ~0.5-0.75 GB |
| 8,192 | ~4-6 GB | ~2-3 GB | ~1-1.5 GB |
| 32,768 | ~16-20 GB | ~8-10 GB | ~4-5 GB |
| 65,536 | ~32-40 GB | ~16-20 GB | ~8-10 GB |
| 131,072 | ~64-80 GB | ~32-40 GB | ~16-20 GB |

### Practical Context Limits on Dual 3090s (48 GB Total VRAM)

**[NOVEL FIND]** A user with dual RTX 3090s (48 GB total) found that the **maximum context for mistral-small3.1:24b Q4_K_M is approximately 56K tokens** before it spills to CPU. At 128K context, the total memory requirement jumps to ~36 GB for model + KV cache + overhead, but the vision projector's 9.5 GB overhead pushes it beyond what Ollama can allocate to GPU layers.

| Quantization | Max Context (Single 3090) | Max Context (Dual 3090, 48 GB) | Max Context (with KV Q8_0) |
|-------------|--------------------------|-------------------------------|---------------------------|
| Q4_K_M | ~24K-32K | ~56K | ~72K-80K |
| Q5_K_M | ~16K-24K | ~48K | ~64K-72K |
| Q8_0 | Does not fit single | ~32K-40K | ~48K-56K |
| FP16 | Does not fit | Does not fit | Does not fit |

### Enabling KV Cache Quantization

To maximize context length, enable flash attention and KV cache quantization:

```bash
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0   # Halves KV cache memory, minimal quality loss
# OR
export OLLAMA_KV_CACHE_TYPE=q4_0   # Quarters KV cache, some quality loss
```

**Important:** KV cache quantization requires flash attention to be enabled. If the model architecture does not support flash attention, Ollama silently falls back to FP16 KV cache. Verify in logs that quantization is actually applied (look for `K (q8_0) / V (q8_0)` in server output).

### RAG-Specific Context Recommendation

For a RAG system with `top_k=12` chunks at ~500 tokens each plus query overhead, typical context usage is 6,000-10,000 tokens. This fits comfortably in any quantization level on a single RTX 3090. The 128K window is only needed for full-document analysis or very long conversation histories.

**Recommended context for RAG:** Set `num_ctx` to **8192 or 16384** to keep VRAM usage manageable while providing ample room for RAG context.

Sources:
- https://github.com/ollama/ollama/issues/10615
- https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/
- https://mitjamartini.com/posts/ollama-kv-cache-quantization/
- https://localllm.in/blog/ollama-vram-requirements-for-local-llms
- https://github.com/ollama/ollama/issues/10177

---

## 9. Comparison with Alternatives (phi4:14b, mistral-nemo:12b)

### Head-to-Head Comparison

| Attribute | mistral-small3.1:24b | phi4:14b-q4_K_M | mistral-nemo:12b |
|-----------|---------------------|-----------------|-----------------|
| **Parameters** | 24B | 14B | 12B |
| **GGUF Size (Q4_K_M)** | 14.3 GB | 9.1 GB | 7.1 GB |
| **License** | Apache 2.0 | MIT | Apache 2.0 |
| **Publisher** | Mistral AI (France) | Microsoft (USA) | Mistral AI / NVIDIA |
| **Context Window** | 128K | 16K | 128K |
| **MMLU** | ~81%+ | ~80.3% | Lower (~70s) |
| **HellaSwag** | High | 85.6% (best) | Lower |
| **Math/Logic** | Strong | Best in class | Good |
| **Multilingual** | Good | Good | Best in class |
| **Coding** | Strong (84.8% HumanEval) | Strong | Good |
| **Vision** | Yes (multimodal) | No | No |
| **Fits Single 3090?** | Yes (Q4_K_M, short ctx) | Yes (all quants) | Yes (all quants) |
| **Est. tok/s (3090)** | 30-45 | 50-70 | 55-75 |
| **VRAM at 8K ctx** | ~18-22 GB | ~11-13 GB | ~9-11 GB |

### When Is the 24B Model Worth the Extra VRAM?

**Use mistral-small3.1:24b when:**
- Quality matters most (RAG answers on complex engineering topics)
- You need vision/multimodal capability
- You need very long context (128K vs phi4's 16K limit)
- Your RAG queries are domain-complex (24B has more knowledge density)
- You can dedicate a GPU to it (or use dual GPUs for larger quants)

**Use phi4:14b when:**
- Speed is critical (50-70 tok/s vs 30-45 tok/s)
- Math/logic/structured reasoning is the primary task
- VRAM is constrained (only one GPU available for inference)
- 16K context is sufficient (typical for RAG with 12 chunks)
- You need to run other models concurrently on the second GPU

**Use mistral-nemo:12b when:**
- Multilingual content is common
- Maximum speed is needed (55-75 tok/s)
- You want 128K context without the VRAM cost of 24B
- You need a lightweight fallback/secondary model
- Both GPUs should run independent model instances for throughput

### Recommended Dual-3090 Strategy

**GPU 0:** mistral-small3.1:24b (Q4_K_M) as primary RAG inference model
**GPU 1:** phi4-mini or mistral-nemo:12b as secondary/concurrent model

This gives you the best of both worlds -- high-quality 24B inference on one GPU and fast secondary inference on the other, without the overhead and bugs of multi-GPU splitting.

Sources:
- https://blog.belsterns.com/post/slm-gemma3-vs-phi4-vs-mistralnemo
- https://llm-stats.com/models/compare/mistral-small-3.1-24b-base-2503-vs-phi-4
- https://artificialanalysis.ai/models/mistral-small-3-1
- https://artificialanalysis.ai/models/mistral-nemo
- https://mistral.ai/news/mistral-small-3

---

## 10. Known Issues, Bugs, and Performance Gotchas

### Critical Bugs

#### Bug 1: Vision Projector VRAM Overhead (~9.5 GB)

**Impact: HIGH**
Ollama reserves approximately 9.5 GB of GPU memory for the Mistral Small 3.1 vision projector compute graph, even when only processing text queries. This causes Ollama to refuse loading layers onto GPUs or underutilize available VRAM.

**Symptoms:**
- Ollama reports "not enough VRAM" despite sufficient memory
- Only 12 GB of 24 GB VRAM utilized on single GPU
- Model loads to CPU instead of GPU

**Workarounds:**
1. Manually set `num_gpu` to force GPU offloading
2. Use a text-only GGUF from HuggingFace (loses vision capability)
3. Use llama.cpp directly with `--no-mmproj-offload`
4. Use `OLLAMA_GPU_OVERHEAD` to reduce reserved headroom

**[NOVEL FIND]** There is an open feature request (GitHub #10889) for Ollama to add an option to not offload the vision projector to GPU. As of February 2026, this is NOT implemented.

Sources: GitHub Issues #10177, #10167, #10296, #10231, #10217, #10889

#### Bug 2: New Engine Performance Regression (10x Slower)

**Impact: HIGH**
The new Ollama engine (introduced around v0.9) causes severe performance degradation on RTX 3090/3090 Ti hardware. Inference drops from ~100 tok/s to 12-60 tok/s.

**Workaround:**
```bash
export OLLAMA_NEW_ENGINE=false
```

**Status:** Closed as NOT_PLANNED (July 2025). The Ollama team did not fix this regression.

Source: https://github.com/ollama/ollama/issues/11060

#### Bug 3: Dual 3090 Underutilization

**Impact: MEDIUM**
Multiple users report inability to get Ollama to fully utilize dual RTX 3090s. nvidia-smi shows brief spikes that quickly fall away, with most processing happening on CPU.

Source: https://github.com/ollama/ollama/issues/10916

#### Bug 4: 128K Context Falls Back to CPU

**Impact: MEDIUM**
When setting `num_ctx=131072` on dual 3090s (48 GB total), the model falls to 100% CPU. The practical maximum is approximately 56K tokens on dual 3090s with Q4_K_M.

Source: https://github.com/ollama/ollama/issues/10615

#### Bug 5: CUDA Device Ordering Inconsistency

**Impact: LOW (identical GPUs)**
In mixed-GPU setups, CUDA device ordering between runtime and management library can differ, causing incorrect layer split predictions. This is less relevant for identical dual 3090s but worth noting.

Source: https://github.com/ollama/ollama/issues/7429

#### Bug 6: Ollama Silently Falls Back to CPU

**Impact: HIGH**
Recent Ollama versions (post-Dec 2025) have been reported to silently stop using GPU during inference. `ollama ps` shows "GPU 100%" but actual GPU utilization is zero. This affects multiple models including Mistral Small 3.1.

**Workaround:** Downgrade Ollama to version 0.13.1 or earlier.

Source: https://github.com/ollama/ollama/issues/13814

### Performance Gotchas

1. **Architecture speed difference:** The `mistral3` architecture used by mistral-small3.1 in Ollama is slower than the `llama` architecture used by the older mistral-small:24b (v3.0). If you do not need vision and want maximum speed, consider using the v3.0 model tag `mistral-small:24b` instead.

2. **Repetition penalty harms quality:** Community reports that setting repetition penalty (e.g., 1.2) causes output degradation with Mistral Small models. Avoid unless specifically needed.

3. **Image analysis VRAM spike:** Processing even a single image can cause VRAM to spike dramatically, potentially causing OOM on 24 GB GPUs.

4. **KV cache quantization silently disabled:** If the model architecture is not in Ollama's flash attention allowlist, `OLLAMA_KV_CACHE_TYPE` is silently ignored and KV cache uses FP16, causing unexpected OOM.

5. **Context above 512K breaks flash attention:** If `num_ctx` exceeds 512K, Ollama attempts to run without flash attention and KV quantization, then crashes.

---

## 11. Recommended Configuration

### Primary Recommendation: Q4_K_M on Single GPU

For a RAG system with typical 8K-16K context windows:

```bash
# Environment variables for Ollama
CUDA_VISIBLE_DEVICES=0,1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_NUM_GPU=-1
```

```bash
# Pull and run
ollama pull mistral-small3.1:24b
# Default is Q4_K_M (15 GB), fits on single 3090
```

**Expected performance:** 30-45 tok/s generation, ~18-22 GB VRAM at 8K context, leaving GPU 1 free for secondary models.

### Secondary Recommendation: Q8_0 Split Across Both GPUs

For maximum quality when both GPUs can be dedicated:

```bash
ollama pull mistral-small3.1:24b-instruct-2503-q8_0
```

```bash
# Modelfile
FROM mistral-small3.1:24b-instruct-2503-q8_0
PARAMETER num_gpu 999
PARAMETER num_ctx 32768
```

**Expected performance:** 18-28 tok/s generation, ~33-36 GB VRAM at 32K context, split across both GPUs.

### Optimal Dual-GPU Strategy for RAG

**GPU 0:** `mistral-small3.1:24b` (Q4_K_M, 15 GB) -- primary RAG inference
**GPU 1:** `phi4-mini` or `mistral-nemo:12b` -- fallback/secondary or concurrent queries

This avoids multi-GPU split bugs entirely while maximizing hardware utilization.

### Pre-Flight Checklist

1. Install Ollama 0.6.5+ (verify with `ollama --version`)
2. Verify both GPUs visible: `nvidia-smi` should show two RTX 3090s
3. Set environment variables (flash attention, KV cache quant)
4. Pull model: `ollama pull mistral-small3.1:24b`
5. Test with: `ollama run mistral-small3.1:24b "Hello, test prompt"`
6. Monitor VRAM: `watch -n1 nvidia-smi` during inference
7. If GPU underutilized, try setting `num_gpu` manually in Modelfile
8. If performance is slow, try `OLLAMA_NEW_ENGINE=false`
9. If vision projector wastes VRAM and you only need text, consider `mistral-small:24b` (v3.0, llama architecture, no vision)

---

## 12. Sources

### Official Documentation
- [Ollama mistral-small3.1:24b Model Page](https://ollama.com/library/mistral-small3.1:24b)
- [Ollama mistral-small3.1 Tags](https://ollama.com/library/mistral-small3.1/tags)
- [Ollama GPU Hardware Support](https://docs.ollama.com/gpu)
- [Ollama FAQ](https://docs.ollama.com/faq)
- [Ollama Blog: New Model Scheduling](https://ollama.com/blog/new-model-scheduling)
- [Mistral AI: Mistral Small 3.1 Announcement](https://mistral.ai/news/mistral-small-3-1)
- [Mistral AI: Mistral Small 3 Announcement](https://mistral.ai/news/mistral-small-3)
- [Mistral AI: About Us](https://mistral.ai/about)
- [Mistral AI License Notice](https://legal.mistral.ai/terms/license-notice)
- [Mistral AI Official Benchmarks](https://docs.mistral.ai/getting-started/models/benchmark/)

### HuggingFace GGUF Repositories
- [Unsloth GGUF (Mistral Small 3.1)](https://huggingface.co/unsloth/Mistral-Small-3.1-24B-Instruct-2503-GGUF)
- [bartowski GGUF (Mistral Small 3.1)](https://huggingface.co/bartowski/mistralai_Mistral-Small-3.1-24B-Instruct-2503-GGUF)
- [Mungert GGUF (Mistral Small 3.1)](https://huggingface.co/Mungert/Mistral-Small-3.1-24B-Instruct-2503-GGUF)
- [Mistral HuggingFace Model Card](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503)

### GitHub Issues (Ollama)
- [#10177 -- mistral-small3.1 using too much VRAM](https://github.com/ollama/ollama/issues/10177)
- [#10167 -- Quantized version doesn't utilize NVIDIA GPUs](https://github.com/ollama/ollama/issues/10167)
- [#10296 -- Error running (GPU+CPU split needed)](https://github.com/ollama/ollama/issues/10296)
- [#10377 -- RTX 4090 OOM on image analysis](https://github.com/ollama/ollama/issues/10377)
- [#10231 -- Not fully utilizing A10 GPU](https://github.com/ollama/ollama/issues/10231)
- [#10175 -- Crashes on prompt](https://github.com/ollama/ollama/issues/10175)
- [#10217 -- Not loaded fully to GPU on RX 7900 XTX](https://github.com/ollama/ollama/issues/10217)
- [#10553 -- Architecture mistral3 speed issue](https://github.com/ollama/ollama/issues/10553)
- [#10615 -- Q4 uses 100% CPU at 128K context](https://github.com/ollama/ollama/issues/10615)
- [#10889 -- Option to not offload vision to GPU](https://github.com/ollama/ollama/issues/10889)
- [#11060 -- New engine 10x performance degradation](https://github.com/ollama/ollama/issues/11060)
- [#11354 -- Crashes with OOM on dual GPU](https://github.com/ollama/ollama/issues/11354)
- [#10916 -- Cannot utilize two 3090s](https://github.com/ollama/ollama/issues/10916)
- [#13814 -- Ollama stopped using GPU](https://github.com/ollama/ollama/issues/13814)
- [#9462 -- GPU choice logic suboptimal](https://github.com/ollama/ollama/issues/9462)
- [#7429 -- CUDA device ordering inconsistent](https://github.com/ollama/ollama/issues/7429)
- [#5543 -- Slow inference on RTX 3090](https://github.com/ollama/ollama/issues/5543)
- [#5271 -- Low VRAM utilization on split](https://github.com/ollama/ollama/issues/5271)
- [#7104 -- Splitting workloads across GPUs](https://github.com/ollama/ollama/issues/7104)
- [#5527 -- Row split PR (40-70% improvement)](https://github.com/ollama/ollama/pull/5527)
- [#13337 -- Flash attention architecture support](https://github.com/ollama/ollama/issues/13337)
- [#6279 -- KV cache quantization PR](https://github.com/ollama/ollama/pull/6279)

### Multi-GPU Analysis
- [Stop Wasting Multi-GPU with llama.cpp (Ahmad Osman)](https://www.ahmadosman.com/blog/do-not-use-llama-cpp-or-ollama-on-multi-gpus-setups-use-vllm-or-exllamav2/)
- [Does a 2nd GPU Speed Up Ollama? (Arsturn)](https://www.arsturn.com/blog/will-a-second-gpu-speed-up-ollama-the-surprising-truth)
- [vLLM vs llama.cpp vs Ollama Multi-GPU (Arsturn)](https://www.arsturn.com/blog/multi-gpu-showdown-benchmarking-vllm-llama-cpp-ollama-for-maximum-performance)
- [Splitting LLMs Across GPUs (DigitalOcean)](https://www.digitalocean.com/community/tutorials/splitting-llms-across-multiple-gpus)
- [Ollama Multi-GPU Setup Guide (dasroot.net)](https://dasroot.net/posts/2025/12/ollama-multi-gpu-setup-larger-models/)
- [Multi-GPU Ollama Setup (Markaicode)](https://markaicode.com/multi-gpu-ollama-setup-large-model-inference/)
- [Scale Ollama with Two or More GPUs (AI-Box)](https://ai-box.eu/en/large-language-models-en/empowering-process-automation-with-n8n-ollama-and-open-source-llms/how-to-scale-ollama-with-two-or-more-gpus/1803/)

### Hardware Benchmarks and Guides
- [RTX 3090 and Local LLMs: What Fits in 24GB (Hardware Corner)](https://www.hardware-corner.net/guides/rtx-3090-local-llms-24gb-vram/)
- [GPU Ranking for LLMs (Hardware Corner)](https://www.hardware-corner.net/gpu-ranking-local-llm/)
- [Mistral Hardware Requirements (Hardware Corner)](https://www.hardware-corner.net/llm-database/Mistral/)
- [Best GPU for Local AI 2026 (Local AI Master)](https://localaimaster.com/blog/best-gpus-for-ai-2025)
- [Ollama VRAM Requirements 2026 (LocalLLM.in)](https://localllm.in/blog/ollama-vram-requirements-for-local-llms)
- [Local LLM Deployment on 24GB GPUs (IntuitionLabs)](https://intuitionlabs.ai/articles/local-llm-deployment-24gb-gpu-optimization)
- [Complete Guide to Running LLMs Locally (ikangai)](https://www.ikangai.com/the-complete-guide-to-running-llms-locally-hardware-software-and-performance-essentials/)
- [Dual RTX 3090 NVLink Review (ServeTheHome)](https://www.servethehome.com/dual-nvidia-geforce-rtx-3090-nvlink-performance-review-asus-zotac/)
- [RTX 3090 AI Inference Benchmarks 2024 (ywian)](https://www.ywian.com/blog/rtx-3090-ai-inference-benchmarks-2024)
- [Home GPU LLM Leaderboard (Awesome Agents)](https://awesomeagents.ai/leaderboards/home-gpu-llm-leaderboard/)

### KV Cache Quantization
- [Bringing KV Context Quantisation to Ollama (smcleod.net)](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/)
- [KV Cache Quantization in Ollama (Mitja Martini)](https://mitjamartini.com/posts/ollama-kv-cache-quantization/)
- [Ollama VRAM Fine-Tuning with KV Cache (Peddals)](https://blog.peddals.com/en/ollama-vram-fine-tune-with-kv-cache/)

### Defense and Licensing
- [Mistral AI Wikipedia](https://en.wikipedia.org/wiki/Mistral_AI)
- [France Taps Mistral for Military Use (Tekedia)](https://www.tekedia.com/france-taps-mistral-ai-for-military-use-marking-a-strategic-shift-toward-sovereign-artificial-intelligence/)
- [France $14B AI Deal with Mistral (WebProNews)](https://www.webpronews.com/france-signs-14b-ai-deal-with-mistral-for-military-defense-boost/)
- [Mistral Wins French Defence Framework (gend.co)](https://www.gend.co/blog/mistral-ai-french-defence-framework)
- [Mistral Arms France with AI for Defense (TheDefensePost)](https://thedefensepost.com/2026/01/15/mistral-ai-france-defense/)
- [Mistral French Military Deal (TechRepublic)](https://www.techrepublic.com/article/news-mistral-french-military-ai-deal/)
- [Europe's Push for Autonomous AI (Sovereign Magazine)](https://www.sovereignmagazine.com/eu-focus/mistral-ai-europes-push-autonomous-ai-systems/)

### Community Discussions
- [Hacker News: Mistral Small 3](https://news.ycombinator.com/item?id=42877860)
- [Hacker News: Mistral 3 Family Released](https://news.ycombinator.com/item?id=46121889)
- [Hacker News: 25L Portable NV-linked Dual 3090 LLM Rig](https://news.ycombinator.com/item?id=45300668)
- [HuggingFace Discussion: Optimal Ollama Settings](https://huggingface.co/mistralai/Mistral-Small-24B-Instruct-2501/discussions/14)

### Model Benchmarks and Comparisons
- [Mistral Small 3.1 Analysis (Artificial Analysis)](https://artificialanalysis.ai/models/mistral-small-3-1)
- [Mistral Small 3.2 Analysis (Artificial Analysis)](https://artificialanalysis.ai/models/mistral-small-3-2)
- [Mistral NeMo Analysis (Artificial Analysis)](https://artificialanalysis.ai/models/mistral-nemo)
- [Mistral Small 3.1 vs Phi-4 (llm-stats.com)](https://llm-stats.com/models/compare/mistral-small-3.1-24b-base-2503-vs-phi-4)
- [Gemma3 vs Phi4 vs Mistral NeMo (Belsterns)](https://blog.belsterns.com/post/slm-gemma3-vs-phi4-vs-mistralnemo)
- [AI Model Benchmarks (LangDB)](https://langdb.ai/app/models/benchmarks)
- [Mistral Small 3.1 (OpenRouter)](https://openrouter.ai/mistralai/mistral-small-3.1-24b-instruct:free)

---

## Summary of Novel Findings

1. **[NOVEL FIND]** The `mistral3` architecture used by mistral-small3.1 in Ollama is significantly slower than the `llama` architecture used by the older mistral-small:24b. For text-only RAG, consider using the v3.0 model for speed.

2. **[NOVEL FIND]** The vision projector reserves ~9.5 GB of VRAM overhead even for text-only queries. There is no official Ollama option to disable this. Feature request #10889 is still open.

3. **[NOVEL FIND]** Row-split mode in llama.cpp (`-sm row`) provides 40-70% improvement over layer-split on multi-GPU. Ollama does not expose this option but it may become available in future versions.

4. **[NOVEL FIND]** The maximum practical context length for Q4_K_M on dual 3090s (48 GB) is approximately 56K tokens, not the advertised 128K.

5. **[NOVEL FIND]** The OLLAMA_NEW_ENGINE regression (10x slowdown) was closed as NOT_PLANNED. Users on RTX 3090 hardware should set `OLLAMA_NEW_ENGINE=false` indefinitely.

6. **[NOVEL FIND]** Ollama's VRAM reporting for mistral-small3.1 is inaccurate -- it reports ~32 GB usage while nvidia-smi shows ~20 GB actual allocation. Other vision models do not exhibit this discrepancy.
