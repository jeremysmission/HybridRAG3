# Demo Day Speedup Tips

Last Updated: 2026-02-24

---

## OVERVIEW

Offline mode (Ollama + phi4-mini) runs entirely on the local machine with zero
internet. The tradeoff is latency -- local inference is slower than cloud APIs.
This guide covers every lever available to minimize wait times during a live
customer demo.

---

## SECTION 1: CODE-LEVEL OPTIMIZATIONS (ALREADY APPLIED)

These changes are live in `src/core/llm_router.py`, `config/default_config.yaml`,
`src/core/config.py`, and `src/gui/launch_gui.py` as of Session 16.

### 1.1 keep_alive = -1 (Eliminate Cold Start)

| Before | After |
|--------|-------|
| Not set (Ollama default: 5min idle timeout) | `-1` (never unload) |

**Why it matters:** When Ollama unloads a model after 5 minutes of idle time,
the next query pays a 5-15 second cold start to reload weights into GPU/CPU
memory. Setting `keep_alive: -1` keeps the model resident permanently. During a
demo, you never want the audience watching a loading spinner because you paused
to take a question.

**Config location:** `config/default_config.yaml` > `ollama.keep_alive`

### 1.2 num_ctx = 4096 (Smaller Context Window)

| Before | After |
|--------|-------|
| 16384 (full model default) | 4096 |

**Why it matters:** Prompt evaluation time scales with context window size.
RAG queries rarely exceed 3K tokens (system prompt + retrieved chunks + user
question). Cutting the window from 16K to 4K gives 20-40% faster prompt
evaluation with zero quality loss for typical queries.

**Tradeoff:** If a query retrieves many large chunks that exceed 4K tokens
total, the model will silently truncate. For the demo's standard questions this
will not happen. Increase to 8192 if you plan to demo with unusually long
source documents.

**Config location:** `config/default_config.yaml` > `ollama.context_window`

### 1.3 num_predict = 512 (Cap Output Length)

| Before | After |
|--------|-------|
| Not set (unbounded -- model decides when to stop) | 512 tokens max |

**Why it matters:** Without a cap, the model can generate 2000+ tokens on
open-ended questions, adding 10-30 seconds of unnecessary generation time.
512 tokens is roughly 400 words -- more than enough for a RAG answer with
citations. The model still stops naturally at shorter lengths when appropriate;
this just prevents runaway generation.

**Config location:** `config/default_config.yaml` > `ollama.num_predict`

### 1.4 temperature = 0.05 (From Config, Not Ollama Default)

| Before | After |
|--------|-------|
| Not set (Ollama default: 0.8) | 0.05 (from api.temperature) |

**Why it matters:** Lower temperature means less random sampling, which is
slightly faster and produces more deterministic, factual answers -- exactly
what you want in a demo where consistency matters. The config already had
`api.temperature: 0.05` but it was never being sent to Ollama.

### 1.5 num_thread = 0 (Auto-Detect, Configurable)

| Before | After |
|--------|-------|
| Not set (Ollama picks) | 0 (auto-detect, override in config) |

**Why it matters:** On hybrid Intel CPUs (P-cores + E-cores), Ollama's auto-
detection is usually correct. On the dual-3090 workstation, you may want to
pin this to the P-core count (e.g., 8) to avoid scheduling on slow E-cores.
Set to 0 and let Ollama decide unless you benchmark a specific value.

**Config location:** `config/default_config.yaml` > `ollama.num_thread`

### 1.6 Warmup Improvements

The GUI launcher (`src/gui/launch_gui.py`) now sends the full options payload
during the startup warmup call, including `keep_alive: -1`. This means:
- The model loads into memory at GUI startup
- It stays loaded indefinitely
- The first real query pays zero cold-start cost
- Warmup timeout increased from 10s to 30s (first load is slow)

---

## SECTION 2: ENVIRONMENT VARIABLES

Set these in your PowerShell launcher or system environment before starting
Ollama. These are server-level settings that apply to all models.

### 2.1 OLLAMA_FLASH_ATTENTION = 1

```powershell
$env:OLLAMA_FLASH_ATTENTION = "1"
```

**Impact:** 30-40% faster attention computation on supported models (phi4-mini
supports this). Flash attention uses an optimized memory access pattern that
reduces GPU memory bandwidth bottleneck.

**Compatibility:** Requires CUDA 11.8+ or compatible CPU backend. If your
hardware doesn't support it, Ollama silently falls back to standard attention.

### 2.2 OLLAMA_KV_CACHE_TYPE = q8_0

```powershell
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
```

**Impact:** 15-20% less memory usage for the KV cache, with negligible quality
loss. This lets you run larger context windows or frees memory for other
processes. Slight speed improvement from reduced memory traffic.

### 2.3 OLLAMA_KEEP_ALIVE = -1

```powershell
$env:OLLAMA_KEEP_ALIVE = "-1"
```

**Impact:** Server-level backup for the per-request `keep_alive: -1` already
set in the code. Belt and suspenders -- if the code somehow doesn't send the
parameter, the server default still keeps models loaded.

### 2.4 All-In-One Launcher Block

Add this to your PowerShell startup script or `start_hybridrag.ps1`:

```powershell
# -- Ollama performance tuning --
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
$env:OLLAMA_KEEP_ALIVE = "-1"
```

---

## SECTION 3: WINDOWS SYSTEM SETTINGS

### 3.1 High Performance Power Plan

Windows power saving throttles CPU frequency. During a demo, force full speed:

```
Settings > System > Power > Power mode > Best performance
```

Or via PowerShell:

```powershell
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
```

**Impact:** Prevents CPU throttling that can add 20-50% latency on battery or
"Balanced" power plans. Essential on laptops.

### 3.2 Close Background Apps

Before the demo, close:
- Browser tabs (especially Chrome -- heavy memory/CPU)
- Teams / Slack / Outlook (background sync)
- OneDrive sync
- Windows Update (can grab CPU at worst times)
- Antivirus real-time scanning (if policy allows temporary disable)

### 3.3 Disable Sleep/Screen Lock

Nothing kills a demo like the laptop going to sleep mid-presentation:

```
Settings > System > Power > Screen and sleep > Never (while plugged in)
```

---

## SECTION 4: DEMO-DAY CHECKLIST

Run this 30 minutes before the demo:

```
[ ] 1. Set Windows to High Performance power plan
[ ] 2. Set Ollama environment variables (Section 2.4)
[ ] 3. Restart Ollama service (picks up env vars)
        ollama serve
[ ] 4. Verify model is loaded:
        ollama list    (should show phi4-mini)
[ ] 5. Launch HybridRAG GUI:
        python src/gui/launch_gui.py
[ ] 6. Wait for status bar to show green "Ready"
[ ] 7. Run one throwaway query ("What is HybridRAG?")
        -- confirms model is warm, first-query latency is paid
[ ] 8. Check response time on status bar (target: under 8s)
[ ] 9. Close unnecessary apps
[ ] 10. Disable sleep/screen lock
```

---

## SECTION 5: EXPECTED LATENCY TARGETS

After all optimizations, expected latency per query on phi4-mini:

| Hardware | Cold Start | Warm Query | With Flash Attn |
|----------|-----------|------------|-----------------|
| Laptop (8GB, CPU-only) | 12-18s | 6-10s | 5-8s |
| Workstation (RTX 3090) | 3-5s | 1.5-3s | 1-2s |
| Workstation (dual 3090) | 2-4s | 1-2s | 0.8-1.5s |

**"Cold start" = first query after model load.** With `keep_alive: -1` and
the warmup call, every demo query should be a "warm query" -- no cold starts.

---

## SECTION 6: FALLBACK -- IF OFFLINE MODE IS STILL TOO SLOW

If latency is still unacceptable during the demo:

1. **Switch to online mode** (Admin > Settings > Mode: Online) -- cloud API
   responds in 1-3s regardless of local hardware
2. **Use streaming mode** -- the GUI already supports streaming; first tokens
   appear in <1s even if total generation takes 8s. Audience sees immediate
   response, which feels faster.
3. **Pre-cache key demo queries** -- run your planned demo questions once
   before the audience arrives. The semantic cache (query_cache.py) will
   serve exact or near-exact repeats instantly.
4. **Use the smaller context window** -- if you set `num_ctx: 4096` and
   queries still feel slow, try `2048` for maximum speed at the cost of
   fewer retrieved chunks in context.

---

## SECTION 7: CONFIG REFERENCE

All Ollama performance settings in `config/default_config.yaml`:

```yaml
ollama:
  base_url: http://localhost:11434
  context_window: 4096      # num_ctx sent to Ollama
  keep_alive: -1             # never unload model (-1 = forever)
  model: phi4-mini
  num_predict: 512           # max output tokens
  num_thread: 0              # 0 = auto-detect
  timeout_seconds: 600
```

Temperature is inherited from `api.temperature: 0.05` and sent in the Ollama
options dict automatically.
