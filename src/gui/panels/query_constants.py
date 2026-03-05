# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the query constants part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Query Panel Constants (src/gui/panels/query_constants.py)
# ============================================================================
# Extracted from query_panel.py to keep the panel class under 500 lines.
# Contains per-use-case tuning presets, grounding/reasoning dial metadata,
# and profile-specific task playbooks.
# ============================================================================

from scripts._model_meta import USE_CASES

# Per-use-case ONLINE tuning presets. These are applied when the user
# changes profession/use-case in online mode so model + retrieval settings
# move together as a bundle.
ONLINE_USE_CASE_TUNING = {
    "sw":    {"temperature": 0.10, "max_tokens": 2048, "timeout_seconds": 90,  "top_k": 8,  "min_score": 0.08},
    "eng":   {"temperature": 0.08, "max_tokens": 2048, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "sys":   {"temperature": 0.08, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 9,  "min_score": 0.08},
    "draft": {"temperature": 0.05, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "log":   {"temperature": 0.05, "max_tokens": 1536, "timeout_seconds": 90,  "top_k": 12, "min_score": 0.06},
    "pm":    {"temperature": 0.20, "max_tokens": 2048, "timeout_seconds": 120, "top_k": 8,  "min_score": 0.06},
    "fe":    {"temperature": 0.10, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "cyber": {"temperature": 0.08, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 9,  "min_score": 0.08},
    "gen":   {"temperature": 0.30, "max_tokens": 2048, "timeout_seconds": 120, "top_k": 6,  "min_score": 0.05},
}

# Safe development defaults for independent dial controls.
# Values are intentionally conservative for demo reliability.
PROFILE_DIAL_DEFAULTS = {
    "offline": {
        "sw":    {"grounding": 8, "reasoning": 2},
        "eng":   {"grounding": 8, "reasoning": 2},
        "sys":   {"grounding": 8, "reasoning": 2},
        "draft": {"grounding": 7, "reasoning": 3},
        "log":   {"grounding": 8, "reasoning": 2},
        "pm":    {"grounding": 7, "reasoning": 3},
        "fe":    {"grounding": 8, "reasoning": 2},
        "cyber": {"grounding": 9, "reasoning": 1},
        "gen":   {"grounding": 6, "reasoning": 4},
    },
    "online": {
        "sw":    {"grounding": 7, "reasoning": 5},
        "eng":   {"grounding": 7, "reasoning": 5},
        "sys":   {"grounding": 8, "reasoning": 4},
        "draft": {"grounding": 7, "reasoning": 5},
        "log":   {"grounding": 7, "reasoning": 5},
        "pm":    {"grounding": 6, "reasoning": 6},
        "fe":    {"grounding": 7, "reasoning": 5},
        "cyber": {"grounding": 9, "reasoning": 3},
        "gen":   {"grounding": 5, "reasoning": 7},
    },
}

# Development grounding-bias scale (1..10).
# 1 = max synthesis freedom, 10 = strict source lock.
GROUNDING_BIAS_HINTS = {
    0: "Grounding 0/10 - OFF",
    1: "Grounding 1/10 - Generative (guard OFF, dev only)",
    2: "Grounding 2/10 - Very relaxed",
    3: "Grounding 3/10 - Relaxed",
    4: "Grounding 4/10 - Moderate relaxed",
    5: "Grounding 5/10 - Balanced",
    6: "Grounding 6/10 - Balanced+",
    7: "Grounding 7/10 - Strong grounding",
    8: "Grounding 8/10 - Strict",
    9: "Grounding 9/10 - Very strict",
    10: "Grounding 10/10 - Evidence locked",
}
REASONING_DIAL_HINTS = {
    0: "Reasoning 0/10 - OFF (context-only)",
    1: "Reasoning 1/10 - Minimal",
    2: "Reasoning 2/10 - Very low",
    3: "Reasoning 3/10 - Low",
    4: "Reasoning 4/10 - Light",
    5: "Reasoning 5/10 - Balanced",
    6: "Reasoning 6/10 - Moderate",
    7: "Reasoning 7/10 - Strong",
    8: "Reasoning 8/10 - High",
    9: "Reasoning 9/10 - Very high",
    10: "Reasoning 10/10 - Max",
}

PROFILE_TASK_PLAYBOOK = {
    "log": [
        "1) Reconcile received vs required parts -- Grounding 8 / Reasoning 4",
        "2) Build shortage report by part number -- Grounding 9 / Reasoning 3",
        "3) Cross-check procurement status across files -- Grounding 7 / Reasoning 6",
        "4) Extract lead times and vendor constraints -- Grounding 8 / Reasoning 4",
        "5) Generate weekly logistics summary -- Grounding 6 / Reasoning 7",
    ],
    "pm": [
        "1) Build status report from multiple documents -- Grounding 6 / Reasoning 7",
        "2) Summarize risks, owners, due dates -- Grounding 7 / Reasoning 6",
        "3) Draft executive one-pager -- Grounding 5 / Reasoning 8",
        "4) Compare baseline vs current milestones -- Grounding 7 / Reasoning 6",
        "5) Create action-item register -- Grounding 6 / Reasoning 7",
    ],
    "eng": [
        "1) Extract specs/tolerances/part numbers -- Grounding 9 / Reasoning 2",
        "2) Compare interfaces across drawings/manuals -- Grounding 8 / Reasoning 5",
        "3) Generate subsystem technical summary -- Grounding 7 / Reasoning 6",
        "4) Identify conflicts between revisions -- Grounding 8 / Reasoning 5",
        "5) Produce test readiness checklist -- Grounding 7 / Reasoning 6",
    ],
    "draft": [
        "1) Extract dimensions/callouts from docs -- Grounding 9 / Reasoning 2",
        "2) Build drawing package index -- Grounding 8 / Reasoning 4",
        "3) Cross-reference drawing to BOM entries -- Grounding 8 / Reasoning 5",
        "4) Generate revision-impact notes -- Grounding 7 / Reasoning 6",
        "5) Produce release checklist -- Grounding 7 / Reasoning 6",
    ],
    "sys": [
        "1) Extract configuration values exactly -- Grounding 9 / Reasoning 2",
        "2) Build troubleshooting decision tree -- Grounding 7 / Reasoning 6",
        "3) Compare system states across docs -- Grounding 8 / Reasoning 5",
        "4) Draft change-implementation steps -- Grounding 7 / Reasoning 6",
        "5) Summarize operational constraints -- Grounding 8 / Reasoning 4",
    ],
    "cyber": [
        "1) Extract controls/findings exactly -- Grounding 10 / Reasoning 1",
        "2) Map findings to mitigations -- Grounding 8 / Reasoning 5",
        "3) Generate incident summary report -- Grounding 7 / Reasoning 6",
        "4) Compare policy vs implementation docs -- Grounding 8 / Reasoning 5",
        "5) Build audit evidence checklist -- Grounding 9 / Reasoning 3",
    ],
    "fe": [
        "1) Extract field procedures and limits -- Grounding 9 / Reasoning 2",
        "2) Build troubleshooting flow from manuals -- Grounding 7 / Reasoning 6",
        "3) Cross-link parts to installation steps -- Grounding 8 / Reasoning 5",
        "4) Generate shift handoff summary -- Grounding 6 / Reasoning 7",
        "5) Create field readiness checklist -- Grounding 7 / Reasoning 6",
    ],
    "sw": [
        "1) Extract exact API/config requirements -- Grounding 9 / Reasoning 2",
        "2) Summarize architecture from docs -- Grounding 7 / Reasoning 6",
        "3) Generate implementation plan -- Grounding 6 / Reasoning 7",
        "4) Build dependency/risk report -- Grounding 7 / Reasoning 6",
        "5) Draft test strategy summary -- Grounding 6 / Reasoning 7",
    ],
    "gen": [
        "1) Quick doc summary -- Grounding 5 / Reasoning 7",
        "2) Cross-doc synthesis answer -- Grounding 5 / Reasoning 8",
        "3) Report draft from mixed sources -- Grounding 4 / Reasoning 8",
        "4) Block diagram text from context -- Grounding 4 / Reasoning 9",
        "5) Executive brief + action items -- Grounding 5 / Reasoning 8",
    ],
}
