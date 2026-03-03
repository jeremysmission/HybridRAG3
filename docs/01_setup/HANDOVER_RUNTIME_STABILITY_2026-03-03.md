# Handover -- Runtime Stability / 500 Errors / Demo Safe-Zone
## Date: 2026-03-03

## Initial Problems Observed
1. Query failures with HTTP 500 / timeout behavior in offline mode.
2. GUI launch felt unstable on some runs (pop/disappear/focus odd behavior).
3. Downloader/operator confusion during large-source transfer (discovery behavior and live rate visibility).
4. High-risk operator mode: indexing/downloading while live querying.

## Root Cause Summary
Primary runtime issue was not parser logic. It was local LLM runtime pressure:
1. Ollama frequently running CPU path (`100% CPU`) instead of GPU offload.
2. Heavy model/context settings increased load churn and startup/query instability.
3. Concurrent heavy operations (index/download/query) amplified contention.

## How It Was Found (Evidence Path)
1. Reproduced failures directly against Ollama endpoints.
2. Checked process/runtime state (`ollama ps`) for active processor path.
3. Reviewed Ollama server logs for timeout/runner/memory pressure signals.
4. Traced GUI + query error surfacing paths in code to ensure actionable UX.
5. Verified behavior after changes with focused compile/tests/smoke checks.

## Fixes Applied
1. Safe offline defaults:
   - `ollama.model: phi4-mini`
   - `ollama.context_window: 4096`
   - `ollama.timeout_seconds: 180`
2. GUI query error hardening:
   - Added targeted popup for offline 500/timeout patterns with exact remediation settings.
3. Startup/runtime hardening:
   - Added Ollama runtime probe path and safer launcher behavior controls.
4. Downloader UX:
   - Fast-start discovery warning retained.
   - Live transfer telemetry now displays explicit `MB/s` and `GB/s`.
5. Documentation/runbook updates:
   - CUDA enable/verify steps.
   - Numbered 500 recovery playbook.
   - Demo safe-zone operating rules.

## What Was Intentionally Kept vs Dropped
Kept:
1. Runtime safety and operator-facing remediation.
2. Explicit docs and in-app reference guidance.
3. Downloader visibility improvements.

Dropped as low-trust/noise:
1. Unrelated theme styling edits.
2. Unrelated test churn not required for this incident fix.
3. Unrelated boot timeout tweak not validated in this pass.

## Recommended Operations Policy (Prevent Recurrence)
1. No indexing during live demo/query windows.
2. No bulk download/transfer during live demo/query windows.
3. Keep offline demo baseline pinned (`phi4-mini`, `4096`, `180`).
4. Verify runtime before demos:
   - `ollama run phi4-mini "OK"`
   - `ollama ps`
5. Only raise context above 4096 after preflight checks and only for specific long-context demo asks.

## Next Improvements (Planned)
1. Build per-profile demo question packs (quick-win + stress + citation-confidence).
2. Run overnight autonomous tuning matrix + benchmark collection.
3. Choose default live profile by evidence (p95 latency, no 500s, answer quality).

