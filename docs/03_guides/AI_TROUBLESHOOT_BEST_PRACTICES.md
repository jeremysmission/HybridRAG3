# AI Troubleshoot Best Practices
Last Updated: 2026-03-03

## Purpose
Use this guide to get reliable debugging help from any AI assistant without wasting time on guesswork.

## 1) Set the Rules Up Front
Paste this at the start of troubleshooting:

1. "Use evidence-first debugging. No guessing."
2. "Reproduce issue first, then propose cause."
3. "Show exact commands run and what they proved."
4. "Cite logs/files/lines for every root-cause claim."
5. "Give safe defaults and rollback steps."

## 2) Require a Standard Output Format
Ask the AI to always answer with:

1. Symptoms observed
2. Reproduction steps
3. Evidence collected (commands + logs)
4. Root cause (with confidence level)
5. Fix applied
6. Verification results
7. Residual risks
8. Next monitoring checks

If any section is missing, ask it to complete before moving on.

## 3) Force Local Validation Before Theory
Tell the AI:

1. "Check runtime state first."
2. "Check direct backend endpoint behavior."
3. "Check process status/resource path (CPU/GPU)."
4. "Check logs for the exact error signature."
5. "Only then suggest fixes."

This prevents generic internet-style advice from dominating.

## 4) Ask for Ranked Fixes, Not Brainstorm Lists
Require:

1. High impact + low risk first
2. Reversible changes first
3. Safety defaults before aggressive tuning
4. One change set at a time with verification

## 5) Treat Config as Layered
Always ask:

1. "Which file is authoritative?"
2. "Which overrides win?"
3. "What current effective values are loaded right now?"

Many failures come from editing defaults while overrides remain active.

## 6) Demand Operational Guardrails
Ask the AI to add:

1. Error popups with exact remediation values
2. Runbooks with numbered steps
3. Preconditions/checklists before demo or production use
4. Safety policy rules (example: no indexing during live demos)

## 7) Require Verification Artifacts
Before considering a fix "done", require:

1. Passing targeted tests
2. Smoke run of the affected workflow
3. Command outputs summarized
4. File references for all edits

## 8) Use a Short Prompt Template
Use this template for future incidents:

```text
Investigate this issue using evidence-first debugging only.
No guessing. Reproduce first.

Deliver in this exact order:
1) Symptoms
2) Reproduction
3) Evidence (commands/logs/files)
4) Root cause with confidence
5) Minimal safe fix
6) Verification
7) Safe defaults for reliability
8) What to monitor next

Also update docs/runbook with numbered steps and exact config values.
```

## 9) Red Flags the AI Is Guessing
Stop and reset if you see:

1. "Probably", "maybe", "usually" without evidence
2. No command output or log references
3. Large fix lists before reproduction
4. Advice that ignores your actual runtime state

## 10) Success Criteria
A troubleshooting session is successful when:

1. Root cause is tied to direct evidence
2. Fix is minimal and validated
3. Reliable fallback defaults are documented
4. Future you can recover in minutes using the runbook

