# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the constants part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Project-wide constants -- single source of truth for magic numbers.
# ============================================================================

# Default embedding dimension for Ollama nomic-embed-text.
# Used as fallback when config.embedding.dimension is unavailable.
# Changed from 384 (old HuggingFace) to 768 in Session 15 (2026-02-24).
DEFAULT_EMBED_DIM = 768
