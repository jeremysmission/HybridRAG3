# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the model identity part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Model name canonicalization and resolution helpers.
"""

from __future__ import annotations


def canonicalize_model_name(name: str) -> str:
    """Normalize known aliases to a stable label used across config/UI."""
    n = str(name or "").strip()
    if not n:
        return n
    lowered = n.lower()
    if lowered == "phi4-mini" or lowered.startswith("phi4-mini:"):
        return "phi4-mini"
    # Keep the full approved 14B tag as the canonical identity so
    # config/UI/manifest checks use one consistent string.
    if lowered in ("phi4", "phi4:latest", "phi4:14b"):
        return "phi4:14b-q4_K_M"
    if lowered.startswith("phi4:14b"):
        return "phi4:14b-q4_K_M"
    return n


def _ordered_unique(values):
    """Plain-English: This function handles ordered unique."""
    seen = set()
    out = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def build_ollama_aliases(requested: str) -> list[str]:
    """Build ordered alias candidates for an Ollama model request."""
    req = str(requested or "").strip()
    if not req:
        return []

    base = req.split(":")[0]
    aliases = [
        req,
        canonicalize_model_name(req),
        req.replace(":latest", ""),
        base,
    ]
    if req.startswith("phi4:14b") or req in ("phi4", "phi4:latest"):
        aliases.extend(["phi4:14b-q4_K_M", "phi4:14b", "phi4", "phi4:latest"])
    if req.startswith("phi4-mini"):
        aliases.extend(["phi4-mini:3.8b", "phi4-mini", "phi4-mini:latest"])
    return _ordered_unique(aliases)


def resolve_ollama_model_name(requested: str, available_models: list[str]) -> str:
    """Resolve requested model to an installed Ollama tag when possible."""
    req = str(requested or "").strip()
    if not req:
        return req

    available = [str(m).strip() for m in (available_models or []) if str(m).strip()]
    if not available:
        return req
    if req in available:
        return req

    for alias in build_ollama_aliases(req):
        if alias in available:
            return alias
        hits = [m for m in available if m.startswith(alias + ":")]
        if hits:
            preferred = [m for m in hits if m.endswith(":latest")]
            return preferred[0] if preferred else hits[0]

    base = req.split(":")[0]
    if base:
        hits = [m for m in available if m.split(":")[0] == base]
        if hits:
            return hits[0]
    return req
