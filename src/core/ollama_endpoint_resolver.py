# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the ollama endpoint resolver part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Helpers for Ollama endpoint normalization.

This module exists so GUI/config/router all share one canonical rule set.
"""

from __future__ import annotations


def sanitize_ollama_base_url(raw: str) -> str:
    """Normalize common Ollama base URL typos from GUI/manual input."""
    s = (raw or "").strip()
    if not s:
        return "http://127.0.0.1:11434"
    if "127.0.0:" in s:
        s = s.replace("127.0.0:", "127.0.0.1:")
    if "127.0.0/" in s:
        s = s.replace("127.0.0/", "127.0.0.1/")
    if s.startswith("127.0.0.1"):
        s = "http://" + s
    return s.rstrip("/")

