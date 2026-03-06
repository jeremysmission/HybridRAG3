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
# Contains per-use-case tuning presets, grounding/fallback control metadata,
# and profile-specific task playbooks.
# ============================================================================

from scripts._model_meta import USE_CASES

# Per-use-case ONLINE tuning presets. These are applied when the user
# changes profession/use-case in online mode so model + retrieval settings
# move together as a bundle.
ONLINE_USE_CASE_TUNING = {
    "sw":    {"temperature": 0.10, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 8,  "min_score": 0.10},
    "eng":   {"temperature": 0.08, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 10, "min_score": 0.10},
    "sys":   {"temperature": 0.08, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 9,  "min_score": 0.10},
    "draft": {"temperature": 0.05, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 10, "min_score": 0.10},
    "log":   {"temperature": 0.05, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 12, "min_score": 0.10},
    "pm":    {"temperature": 0.20, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 8,  "min_score": 0.10},
    "fe":    {"temperature": 0.10, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 10, "min_score": 0.10},
    "cyber": {"temperature": 0.08, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 9,  "min_score": 0.10},
    "gen":   {"temperature": 0.30, "max_tokens": 16384, "timeout_seconds": 180, "top_k": 6,  "min_score": 0.10},
}

# Safe development defaults for query-side grounding and fallback controls.
PROFILE_DIAL_DEFAULTS = {
    "offline": {
        "sw":    {"grounding": 8, "open_knowledge": True},
        "eng":   {"grounding": 8, "open_knowledge": True},
        "sys":   {"grounding": 8, "open_knowledge": True},
        "draft": {"grounding": 7, "open_knowledge": True},
        "log":   {"grounding": 8, "open_knowledge": True},
        "pm":    {"grounding": 7, "open_knowledge": True},
        "fe":    {"grounding": 8, "open_knowledge": True},
        "cyber": {"grounding": 9, "open_knowledge": True},
        "gen":   {"grounding": 6, "open_knowledge": True},
    },
    "online": {
        "sw":    {"grounding": 7, "open_knowledge": True},
        "eng":   {"grounding": 7, "open_knowledge": True},
        "sys":   {"grounding": 8, "open_knowledge": True},
        "draft": {"grounding": 7, "open_knowledge": True},
        "log":   {"grounding": 7, "open_knowledge": True},
        "pm":    {"grounding": 6, "open_knowledge": True},
        "fe":    {"grounding": 7, "open_knowledge": True},
        "cyber": {"grounding": 9, "open_knowledge": True},
        "gen":   {"grounding": 5, "open_knowledge": True},
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
OPEN_KNOWLEDGE_HINTS = {
    False: "Open knowledge OFF - context only",
    True: "Open knowledge ON - fallback allowed when retrieval is weak",
}

PROFILE_TASK_PLAYBOOK = {
    "log": [
        "1) Reconcile received vs required parts -- Grounding 8",
        "2) Build shortage report by part number -- Grounding 9",
        "3) Cross-check procurement status across files -- Grounding 7",
        "4) Extract lead times and vendor constraints -- Grounding 8",
        "5) Generate weekly logistics summary -- Grounding 6",
    ],
    "pm": [
        "1) Build status report from multiple documents -- Grounding 6",
        "2) Summarize risks, owners, due dates -- Grounding 7",
        "3) Draft executive one-pager -- Grounding 5",
        "4) Compare baseline vs current milestones -- Grounding 7",
        "5) Create action-item register -- Grounding 6",
    ],
    "eng": [
        "1) Extract specs/tolerances/part numbers -- Grounding 9",
        "2) Compare interfaces across drawings/manuals -- Grounding 8",
        "3) Generate subsystem technical summary -- Grounding 7",
        "4) Identify conflicts between revisions -- Grounding 8",
        "5) Produce test readiness checklist -- Grounding 7",
    ],
    "draft": [
        "1) Extract dimensions/callouts from docs -- Grounding 9",
        "2) Build drawing package index -- Grounding 8",
        "3) Cross-reference drawing to BOM entries -- Grounding 8",
        "4) Generate revision-impact notes -- Grounding 7",
        "5) Produce release checklist -- Grounding 7",
    ],
    "sys": [
        "1) Extract configuration values exactly -- Grounding 9",
        "2) Build troubleshooting decision tree -- Grounding 7",
        "3) Compare system states across docs -- Grounding 8",
        "4) Draft change-implementation steps -- Grounding 7",
        "5) Summarize operational constraints -- Grounding 8",
    ],
    "cyber": [
        "1) Extract controls/findings exactly -- Grounding 10",
        "2) Map findings to mitigations -- Grounding 8",
        "3) Generate incident summary report -- Grounding 7",
        "4) Compare policy vs implementation docs -- Grounding 8",
        "5) Build audit evidence checklist -- Grounding 9",
    ],
    "fe": [
        "1) Extract field procedures and limits -- Grounding 9",
        "2) Build troubleshooting flow from manuals -- Grounding 7",
        "3) Cross-link parts to installation steps -- Grounding 8",
        "4) Generate shift handoff summary -- Grounding 6",
        "5) Create field readiness checklist -- Grounding 7",
    ],
    "sw": [
        "1) Extract exact API/config requirements -- Grounding 9",
        "2) Summarize architecture from docs -- Grounding 7",
        "3) Generate implementation plan -- Grounding 6",
        "4) Build dependency/risk report -- Grounding 7",
        "5) Draft test strategy summary -- Grounding 6",
    ],
    "gen": [
        "1) Quick doc summary -- Grounding 5",
        "2) Cross-doc synthesis answer -- Grounding 5",
        "3) Report draft from mixed sources -- Grounding 4",
        "4) Block diagram text from context -- Grounding 4",
        "5) Executive brief + action items -- Grounding 5",
    ],
}
