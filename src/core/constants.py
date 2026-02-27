# ============================================================================
# Project-wide constants -- single source of truth for magic numbers.
# ============================================================================

# Default embedding dimension for Ollama nomic-embed-text.
# Used as fallback when config.embedding.dimension is unavailable.
# Changed from 384 (old HuggingFace) to 768 in Session 15 (2026-02-24).
DEFAULT_EMBED_DIM = 768
