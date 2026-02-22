# Window 5 Research Summary

Generated: 2026-02-21

---

## 1. Claude Code CLI Productivity

The single most important finding is that **CLAUDE.md should be kept under 50-100 lines** with critical rules front-loaded -- the model pays decreasing attention to content further down the file. Community-discovered patterns like Boris Cherny's self-improving CLAUDE.md (where Claude updates its own instructions as it learns project conventions) and the "smart handoff" timing at 70-80% context usage (before auto-compaction fires and loses nuance) are the highest-leverage productivity techniques not found in official docs. Permission prompts are the #1 productivity killer and should be eliminated via `settings.json` allow rules or `--dangerously-skip-permissions`, and `/clear` between tasks saves 50-70% of wasted context tokens.

**Project impact:** Restructure CLAUDE.md to be shorter and front-load the standing rules. Add a handover template to docs/ for session continuity. Configure settings.json allow rules to eliminate permission prompts for approved tools.

## 2. Claude Code settings.json Specification

The most important finding is that **subagent permission inheritance is severely broken** in v2.1.x -- five open GitHub issues document subagents failing to inherit parent permissions (causing unexpected prompts) and in some cases bypassing deny rules entirely (a security risk). The settings system has a four-tier precedence hierarchy (Managed > Project Local > Project Shared > User) with ~60 documented keys and 22 built-in tool names. The `permissions` object format with `allow`/`deny` arrays is the current standard, replacing the legacy `allowedTools` array. There is no official JSON Schema from Anthropic; the community-maintained one at json.schemastore.org is the best available.

**Project impact:** Pin specific tool+command allow rules in `.claude/settings.json` rather than relying on broad wildcards (which have known bugs). Do not rely on deny rules for security-critical restrictions until the subagent bypass bug is fixed. Verify settings are loaded with `claude config list`.

## 3. tkinter Threading Best Practices

The most important finding is that **tkinter silently swallows exceptions in button callbacks** (no dialog, only a stderr traceback that's invisible in production), making threaded GUI bugs extremely hard to diagnose. The canonical safe pattern is `queue.Queue` + `root.after(100, poll_queue)` polling, with a safety valve limiting queue drain to N items per cycle to prevent main-thread stalls. For cancellation, `threading.Event.wait(timeout)` replaces `time.sleep()` with instant cancellation support. The `after_idle()` recursive scheduling pattern is a documented production hazard -- it can cause memory-exhaustion `abort()` in real Tcl applications.

**Project impact:** The GUI prototype must use queue-based threading exclusively. Wrap all callback functions in try/except to surface errors. Use `after(100, ...)` polling, never `after_idle()` recursion. Implement `threading.Event` for clean cancellation of background RAG queries.

## 4. FAISS IVF Migration Plan

The most important finding is that **650GB of source documents translates to approximately 50-130M vectors**, which exceeds what a flat numpy memmap index can serve from 64GB RAM (~73GB at 384-dim float32 for 50M vectors). The recommended index is `IVF4096,SQ8` which compresses to ~18.6GB at 50M vectors while maintaining 90-95% recall@10 -- more than sufficient for RAG with top_k=12. FAISS CPU indexes are thread-safe for concurrent reads (GIL released during search), so 10 concurrent users work without locking. However, **FAISS-GPU has no official Windows support** -- WSL2 or native Linux is required for GPU-accelerated search on the dual 3090 workstation.

**Project impact:** Migration from numpy memmap to FAISS is mandatory at scale. Start with `faiss-cpu` on the current 40K vectors using `IVF256,SQ8` as a drop-in replacement. Plan WSL2 or Linux dual-boot on the workstation for GPU acceleration. The `autofaiss` library from Criteo can automate index parameter selection.

## 5. Mistral-Small-24B on Dual RTX 3090

The most important finding is that **FP16 does NOT fit on 48GB VRAM** (model weights alone are 47.2GB, plus KV cache and a 9.5GB vision projector overhead pushes total to ~58-60GB). The practical deployment is Q4_K_M quantization at ~15GB, which fits on a single RTX 3090 with room for KV cache. Ollama's multi-GPU support uses naive layer splitting (not tensor parallelism), so the second GPU is better used for a concurrent smaller model than for splitting one model. A critical bug exists: the `mistral3` architecture + vision projector causes Ollama to underestimate available VRAM and refuse to load layers to GPU -- set `OLLAMA_NEW_ENGINE=false` as a workaround. Defense approval is clean: Apache 2.0 license, French/NATO-allied origin, active French military contract, fully air-gappable.

**Project impact:** Deploy mistral-small3.1:24b at Q4_K_M on GPU 0, and phi4-mini or mistral-nemo:12b on GPU 1 for concurrent serving. Do NOT attempt FP16 or dual-GPU splitting for this model. Set `OLLAMA_NEW_ENGINE=false` until the engine regression is fixed. Defense approval is confirmed with no blockers.
