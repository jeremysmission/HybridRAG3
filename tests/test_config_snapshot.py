# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the config snapshot area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Tests for Config.snapshot() -- frozen deep-copy mechanism
# WHY:  Config is a shared mutable singleton. When the GUI toggles
#       mode while a query thread reads config, the query can see
#       inconsistent state. snapshot() gives each query thread a
#       frozen copy that cannot be modified.
# HOW:  Creates Config objects, calls snapshot(), and verifies that:
#       - snapshots are independent deep copies
#       - frozen snapshots reject attribute writes
#       - sub-configs are also frozen recursively
#       - version tracking and snapshot_id work correctly
# USAGE: pytest tests/test_config_snapshot.py -v
# ===================================================================

import sys
from pathlib import Path

import pytest

# -- sys.path setup --
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import (
    Config,
    PathsConfig,
    EmbeddingConfig,
    ChunkingConfig,
    OllamaConfig,
    APIConfig,
    RetrievalConfig,
    IndexingConfig,
    SecurityConfig,
    CostConfig,
)


# ============================================================================
# HELPERS
# ============================================================================

def _make_config(**overrides) -> Config:
    """Create a Config with sensible test defaults, allowing overrides."""
    defaults = dict(
        mode="offline",
        paths=PathsConfig(database="test.db", embeddings_cache="test_cache"),
        embedding=EmbeddingConfig(model_name="test-embed", dimension=768),
        chunking=ChunkingConfig(chunk_size=1200, overlap=200),
        ollama=OllamaConfig(base_url="http://localhost:11434", model="phi4-mini"),
        api=APIConfig(endpoint="https://test.openai.azure.com", model="gpt-35"),
        retrieval=RetrievalConfig(top_k=8, min_score=0.20),
    )
    defaults.update(overrides)
    return Config(**defaults)


# ============================================================================
# TEST 1: snapshot returns a deep copy (modifying original has no effect)
# ============================================================================

def test_snapshot_is_deep_copy():
    """Modifying the original config after snapshot must not affect the snapshot."""
    config = _make_config()
    snap = config.snapshot()

    # Mutate the original
    config.mode = "online"
    config.paths.database = "/changed/path.db"
    config.retrieval.top_k = 99

    # Snapshot should still have original values
    assert snap.mode == "offline"
    assert snap.paths.database == "test.db"
    assert snap.retrieval.top_k == 8


# ============================================================================
# TEST 2: frozen snapshot raises on attribute set
# ============================================================================

def test_frozen_snapshot_rejects_top_level_write():
    """Setting an attribute on a frozen snapshot must raise RuntimeError."""
    snap = _make_config().snapshot()
    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.mode = "online"


# ============================================================================
# TEST 3: frozen snapshot's sub-configs are also frozen
# ============================================================================

def test_frozen_subconfigs_reject_write():
    """Sub-config attribute sets on a frozen snapshot must raise RuntimeError."""
    snap = _make_config().snapshot()

    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.paths.database = "/hacked/path.db"

    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.ollama.model = "hacked-model"

    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.retrieval.top_k = 999

    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.api.endpoint = "https://evil.com"


# ============================================================================
# TEST 4: version increments on mutation
# ============================================================================

def test_version_increments_on_mutation():
    """Every attribute set on a mutable Config should bump version."""
    config = Config()
    v0 = config.version

    config.mode = "online"
    v1 = config.version
    assert v1 > v0, "version should increase after setting mode"

    config.mode = "offline"
    v2 = config.version
    assert v2 > v1, "version should increase again after second set"


# ============================================================================
# TEST 5: snapshot_id is unique per snapshot
# ============================================================================

def test_snapshot_id_unique():
    """Each snapshot must get a distinct snapshot_id (UUID4)."""
    config = _make_config()
    snap1 = config.snapshot()
    snap2 = config.snapshot()

    assert snap1.snapshot_id != ""
    assert snap2.snapshot_id != ""
    assert snap1.snapshot_id != snap2.snapshot_id


# ============================================================================
# TEST 6: deepcopy handles all nested dataclasses correctly
# ============================================================================

def test_deepcopy_all_nested_dataclasses():
    """Every sub-config in the snapshot must be a distinct object from original."""
    config = _make_config()
    snap = config.snapshot()

    # Check that sub-config objects are not the same identity
    assert snap.paths is not config.paths
    assert snap.embedding is not config.embedding
    assert snap.chunking is not config.chunking
    assert snap.ollama is not config.ollama
    assert snap.api is not config.api
    assert snap.retrieval is not config.retrieval
    assert snap.indexing is not config.indexing
    assert snap.security is not config.security
    assert snap.cost is not config.cost


# ============================================================================
# TEST 7: original config remains mutable after snapshot
# ============================================================================

def test_original_mutable_after_snapshot():
    """Taking a snapshot must not freeze the original config."""
    config = _make_config()
    _snap = config.snapshot()  # noqa: F841

    # Original should still accept writes
    config.mode = "online"
    assert config.mode == "online"

    config.paths.database = "/new/path.db"
    assert config.paths.database == "/new/path.db"

    config.retrieval.top_k = 42
    assert config.retrieval.top_k == 42


# ============================================================================
# TEST 8: snapshot of snapshot works
# ============================================================================

def test_snapshot_of_snapshot():
    """
    Taking a snapshot of a mutable config, then snapshotting again
    from the original, should produce independent frozen copies.
    """
    config = _make_config()
    snap1 = config.snapshot()

    config.mode = "online"
    snap2 = config.snapshot()

    assert snap1.mode == "offline"
    assert snap2.mode == "online"
    assert snap1.snapshot_id != snap2.snapshot_id

    # Both should be frozen
    with pytest.raises(RuntimeError):
        snap1.mode = "changed"
    with pytest.raises(RuntimeError):
        snap2.mode = "changed"


# ============================================================================
# TEST 9: __init__ still works (frozen flag doesn't block construction)
# ============================================================================

def test_init_works_normally():
    """Config() must construct without errors despite __setattr__ override."""
    config = Config()
    assert config.mode == "offline"
    assert config.frozen is False
    assert config.snapshot_id == ""
    assert isinstance(config.paths, PathsConfig)
    assert isinstance(config.embedding, EmbeddingConfig)


# ============================================================================
# TEST 10: frozen flag is True on snapshot
# ============================================================================

def test_snapshot_frozen_flag():
    """The frozen field must be True on snapshots, False on originals."""
    config = _make_config()
    assert config.frozen is False

    snap = config.snapshot()
    assert snap.frozen is True


# ============================================================================
# TEST 11: snapshot preserves all field values
# ============================================================================

def test_snapshot_preserves_values():
    """All config values should be identical between original and snapshot."""
    config = _make_config(mode="online")
    snap = config.snapshot()

    assert snap.mode == "online"
    assert snap.paths.database == config.paths.database
    assert snap.embedding.model_name == config.embedding.model_name
    assert snap.embedding.dimension == config.embedding.dimension
    assert snap.chunking.chunk_size == config.chunking.chunk_size
    assert snap.ollama.model == config.ollama.model
    assert snap.api.endpoint == config.api.endpoint
    assert snap.api.model == config.api.model
    assert snap.retrieval.top_k == config.retrieval.top_k
    assert snap.retrieval.min_score == config.retrieval.min_score


# ============================================================================
# TEST 12: version is preserved in snapshot
# ============================================================================

def test_snapshot_preserves_version():
    """Snapshot should capture the current version at time of copy."""
    config = _make_config()
    v_before = config.version

    snap = config.snapshot()
    assert snap.version == v_before


# ============================================================================
# TEST 13: multiple snapshots at different mutation stages
# ============================================================================

def test_multiple_snapshots_track_mutations():
    """Snapshots taken at different times should reflect the state at that time."""
    config = _make_config()
    config.mode = "offline"
    snap_a = config.snapshot()

    config.mode = "online"
    config.retrieval.top_k = 20
    snap_b = config.snapshot()

    config.mode = "offline"
    config.retrieval.top_k = 5
    snap_c = config.snapshot()

    assert snap_a.mode == "offline"
    assert snap_a.retrieval.top_k == 8

    assert snap_b.mode == "online"
    assert snap_b.retrieval.top_k == 20

    assert snap_c.mode == "offline"
    assert snap_c.retrieval.top_k == 5

    # All three should have different snapshot_ids
    ids = {snap_a.snapshot_id, snap_b.snapshot_id, snap_c.snapshot_id}
    assert len(ids) == 3


# ============================================================================
# TEST 14: frozen snapshot allows property reads
# ============================================================================

def test_frozen_allows_property_reads():
    """Convenience properties on frozen snapshots should still work."""
    config = _make_config()
    snap = config.snapshot()

    # These are @property methods, not attribute sets -- should work fine
    _ = snap.hallucination_guard_enabled
    _ = snap.hallucination_guard_threshold
    _ = snap.hallucination_guard_action


# ============================================================================
# TEST 15: frozen snapshot rejects setting frozen itself
# ============================================================================

def test_cannot_unfreeze_snapshot():
    """Attempting to set frozen=False on a snapshot must raise."""
    snap = _make_config().snapshot()
    with pytest.raises(RuntimeError, match="Cannot modify frozen config snapshot"):
        snap.frozen = False


# ============================================================================
# TEST 16: list fields in sub-configs are independent copies
# ============================================================================

def test_list_fields_are_independent():
    """List fields like supported_extensions should be independent copies."""
    config = _make_config()
    snap = config.snapshot()

    # Mutate the original's list
    config.indexing.supported_extensions.append(".custom")

    # Snapshot's list should be unaffected (deep copy)
    assert ".custom" not in snap.indexing.supported_extensions


# ============================================================================
# TEST 17: concurrent snapshot safety (basic check)
# ============================================================================

def test_concurrent_snapshots_independent():
    """
    Multiple snapshots created from the same config should not
    interfere with each other.
    """
    config = _make_config()
    snaps = [config.snapshot() for _ in range(10)]

    # All should have unique IDs
    ids = {s.snapshot_id for s in snaps}
    assert len(ids) == 10

    # All should have same values
    for s in snaps:
        assert s.mode == "offline"
        assert s.frozen is True


# ============================================================================
# TEST 18: version does not increment for metadata fields
# ============================================================================

def test_version_skips_metadata_fields():
    """Setting frozen, version, or snapshot_id should not bump version."""
    config = Config()
    v = config.version

    # These are metadata fields -- version should not change
    config.snapshot_id = "test-id"
    assert config.version == v

    config.frozen = False  # already False, but setting it again
    assert config.version == v
