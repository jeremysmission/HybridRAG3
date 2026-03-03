# Cross-AI QA: Lessons Learned -- Claude CLI vs ChatGPT
## Date: 2026-03-01
## Scope: Multi-round code review and rebuttal between Claude CLI (primary dev) and ChatGPT (external QA)

## Context

After a comprehensive audit session (retired package cleanup, waiver sheet update,
requirements reconciliation), the full codebase was sent to ChatGPT for independent
QA. Two rounds of findings and rebuttals followed.

---

## Round 1: ChatGPT Initial QA (4 "Highest-Severity" Findings)

### Finding 1: "FastAPI starts without verifying Ollama is running"
- **ChatGPT claim:** server.py calls Embedder() which probes Ollama; if Ollama is
  down, startup crashes with no user-friendly error.
- **Verdict: Design choice, not a bug.** FastAPI is a headless automation server.
  Crash-on-missing-dependency is correct for a service that cannot function without
  its backend. Adding a "friendly" degraded mode would mask the real problem.
- **Nuance found in Round 2:** ChatGPT later correctly noted that the Ollama probe
  is actually skipped when `dimension > 0` is passed from config (see Round 2).

### Finding 2: "BulkTransferV2 tests still test BulkTransfer (old class)"
- **ChatGPT claim:** Tests import the old `BulkTransfer` class, not `BulkTransferV2`.
- **Verdict: Valid.** Real test debt. BulkTransferV2 is a slim orchestrator that
  delegates to SourceDiscovery and AtomicTransferWorker. Tests cover the internals
  but not the orchestrator entry point. Acknowledged as genuine tech debt.

### Finding 3: "Docs say 9 profiles but code only has 7"
- **ChatGPT claim:** Only 7 profiles exist in code.
- **Verdict: Wrong.** All 9 profiles (sw, eng, pm, sys, log, draft, fe, cyber, gen)
  are defined in `scripts/_model_meta.py` and `scripts/_set_model.py`. ChatGPT
  miscounted. When confronted with the code, ChatGPT conceded immediately.

### Finding 4: "LLM router status inconsistency (api_configured vs mode-aware)"
- **ChatGPT claim:** APIRouter.get_status() and LLMRouter.get_status() return
  contradictory results, with specific line numbers cited.
- **Verdict: Wrong, with hallucinated line numbers.** APIRouter is a private
  internal; LLMRouter is the public consumer interface. LLMRouter.get_status()
  intentionally overrides the raw APIRouter status with mode-aware logic. The line
  numbers ChatGPT cited did not correspond to actual code. When confronted, ChatGPT
  conceded on all points.

### Round 1 Score: 1 valid / 4 findings (25% hit rate)

---

## Round 2: ChatGPT Defensive Rebuttal (2 New Claims)

After receiving the Round 1 rebuttal, a second ChatGPT instance pushed back with
two new claims.

### Finding 5: "Embedder skips Ollama probe when dimension is configured"
- **ChatGPT claim:** My characterization that "the server always probes Ollama at
  startup" was outdated. `server.py:134` passes `dimension=state.config.embedding.dimension`,
  and `embedder.py:106-116` skips the probe when `dimension > 0`.
- **Verdict: Correct.** The code at `embedder.py:106` confirms:
  ```python
  if dimension > 0:
      self.dimension = dimension
      self.logger.info("embedder_ready", ..., note="dimension from config (no probe)")
  else:
      self.dimension = self._detect_dimension()
  ```
  Since `default_config.yaml` sets `embedding.dimension: 768`, the probe is skipped
  in production. My earlier statement was partially outdated. Ollama still must be
  running for actual queries, but startup no longer requires it.

### Finding 6: "QueryAction.top_k is cosmetic -- defined and logged but never applied"
- **ChatGPT claim:** `QueryAction.top_k` (actions.py:20) is defined with default 5,
  logged in telemetry (controller.py:126), but never passed to `qe.query()`. The
  QueryEngine.query() signature only accepts `user_query: str`.
- **Verdict: Correct.** New finding that neither Claude CLI nor the first ChatGPT
  review caught. The retriever uses its own `top_k` from config, completely ignoring
  the GUI action's value. Telemetry records a parameter that has no effect.
- **Severity: Medium.** The telemetry creates a false impression that top_k is
  being applied per-query when it actually comes from static config.

### Round 2 Score: 2 valid / 2 findings (100% hit rate)

---

## Cumulative Scorecard

| # | Finding | Source | Verdict | Severity |
|---|---------|--------|---------|----------|
| 1 | FastAPI/Ollama startup | ChatGPT R1 | Design choice | Low |
| 2 | BulkTransferV2 test gap | ChatGPT R1 | Valid | Medium |
| 3 | "Only 7 profiles" | ChatGPT R1 | Wrong (9 exist) | N/A |
| 4 | LLM router status | ChatGPT R1 | Wrong (hallucinated lines) | N/A |
| 5 | Embedder probe skip | ChatGPT R2 | Correct | Low |
| 6 | QueryAction.top_k unused | ChatGPT R2 | Correct (new find) | Medium |

**Overall: 3 valid, 1 design-choice, 2 wrong out of 6 total findings.**

---

## Lessons Learned

### 1. Cross-AI QA works, but requires validation
External AI review caught real issues (bulk-transfer test debt, top_k telemetry
mismatch) that the primary developer missed. However, 2/6 findings were factually
wrong, and 1 was a design choice mischaracterized as a bug. Blind trust in any
single AI reviewer would have created false work items.

### 2. Confidence does not correlate with correctness
ChatGPT presented all 6 findings with equal confidence and "highest severity"
labels. The two wrong findings (profile count, LLM router status) were stated just
as assertively as the correct ones. Line numbers were hallucinated for Finding 4.
**Takeaway:** Always verify AI claims against actual code before acting on them.

### 3. Second-pass reviews are more accurate
Round 1 had 25% accuracy; Round 2 had 100%. When the second ChatGPT instance had
to defend specific claims against a rebuttal, it dug deeper and found real things.
**Takeaway:** Adversarial review (claim -> rebuttal -> counter) produces better
results than single-pass review.

### 4. "No Answer > Wrong Answer" applies to AI reviewers too
In engineering, a wrong answer is worse than no answer because it misdirects effort.
An AI reviewer that confidently declares 4 "highest-severity" findings when only 1
is genuinely actionable wastes more time than one that says "I found 1 issue and
I'm uncertain about 3 others." Calibrated uncertainty is a feature, not a weakness.

### 5. Different AI instances have different strengths
The first ChatGPT instance cast a wide net (4 findings, 1 hit). The second instance
was more targeted (2 findings, 2 hits). Claude CLI's strength was verification
against actual code with exact line references. The combination produced better
coverage than any single reviewer.

### 6. Hallucinated line numbers are a red flag
When an AI cites specific line numbers that don't match the actual code, treat the
entire finding as suspect. Finding 4 cited lines that didn't exist in the file.
This is a known failure mode of LLMs doing code review from memory rather than
from actual file reads.

### 7. Telemetry-implementation mismatches are easy to miss
Finding 6 (top_k logged but not applied) is a class of bug that's invisible in
normal testing because the telemetry *looks* correct. The parameter exists, it has
a value, it gets recorded. Only by tracing the data flow end-to-end do you discover
it never reaches the engine. **Takeaway:** Audit telemetry fields against actual
implementation, not just against schema definitions.

### 8. Design choices vs bugs: framing matters
Finding 1 (crash on missing Ollama) is reasonable behavior for a headless server.
Labeling it "highest severity" reflects a different architectural philosophy
(graceful degradation) rather than an actual defect. **Takeaway:** When reviewing
findings, separate "I would have designed it differently" from "this is broken."

---

## Action Items from This Review

| Item | Status | Priority |
|------|--------|----------|
| Wire QueryAction.top_k through to QueryEngine | Open | Medium |
| Add BulkTransferV2 orchestrator-level tests | Open | Medium |
| Document that embedder probe is skipped when dimension is configured | Done (this doc) | Low |
| Verify telemetry fields match actual implementation (broader audit) | Open | Low |

---

## Process Recommendation

For future cross-AI QA sessions:
1. Send codebase to external AI for initial review
2. Validate every finding against actual code before accepting
3. Send rebuttal back -- adversarial rounds improve accuracy
4. Document validated findings with action items
5. Never accept "highest severity" labels at face value -- re-triage independently
