# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies per-mode tuning persistence and protects against cross-mode leakage.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Temporary project roots and lightweight fake config objects.
# Outputs: Assertions that online/offline defaults, values, and locks stay independent.
# Safety notes: Writes only to pytest tmp_path.
# ============================

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.gui.helpers.mode_tuning import ModeTuningStore


def _make_config():
    return SimpleNamespace(
        mode="offline",
        retrieval=SimpleNamespace(
            top_k=5,
            min_score=0.10,
            hybrid_search=True,
            reranker_enabled=False,
            reranker_top_n=20,
        ),
        api=SimpleNamespace(
            context_window=4096,
            max_tokens=1024,
            temperature=0.2,
            timeout_seconds=45,
        ),
        ollama=SimpleNamespace(
            context_window=4096,
            num_predict=512,
            temperature=0.1,
            timeout_seconds=180,
        ),
    )


def _make_local_temp_root() -> str:
    base = Path(".tmp_pytest_mode_tuning").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix="mode_tuning_", dir=str(base))


def test_online_mode_bootstraps_from_online_defaults_not_shared_runtime_values():
    cfg = _make_config()
    cfg.retrieval.top_k = 5
    cfg.retrieval.min_score = 0.20
    cfg.api.context_window = 4096
    cfg.api.max_tokens = 1024

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            store = ModeTuningStore()
            state = store.get_mode_state(cfg, "online")

            assert state["defaults"]["top_k"] == 8
            assert abs(state["defaults"]["min_score"] - 0.10) < 1e-9
            assert state["defaults"]["context_window"] == 128000
            assert state["defaults"]["max_tokens"] == 16384

            store.apply_to_config(cfg, "online")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert cfg.retrieval.top_k == 8
    assert abs(cfg.retrieval.min_score - 0.10) < 1e-9
    assert cfg.api.context_window == 128000
    assert cfg.api.max_tokens == 16384


def test_first_active_mode_bootstraps_from_live_config_values():
    cfg = _make_config()
    cfg.mode = "offline"
    cfg.retrieval.top_k = 12
    cfg.retrieval.min_score = 0.15
    cfg.ollama.context_window = 8192
    cfg.ollama.num_predict = 1024

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            store = ModeTuningStore()
            offline_state = store.get_mode_state(cfg, "offline")
            online_state = store.get_mode_state(cfg, "online")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert offline_state["values"]["top_k"] == 12
    assert abs(offline_state["values"]["min_score"] - 0.15) < 1e-9
    assert offline_state["values"]["context_window"] == 8192
    assert offline_state["values"]["num_predict"] == 1024
    assert online_state["values"]["top_k"] == 8
    assert abs(online_state["values"]["min_score"] - 0.10) < 1e-9
    assert online_state["values"]["context_window"] == 128000
    assert online_state["values"]["max_tokens"] == 16384


def test_mode_values_and_locks_stay_independent_between_online_and_offline():
    cfg = _make_config()

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            store = ModeTuningStore()
            store.update_value(cfg, "offline", "top_k", 4)
            store.update_value(cfg, "online", "top_k", 12)
            store.update_default(cfg, "online", "top_k", 11)
            store.set_lock(cfg, "online", "top_k", True)

            store.apply_to_config(cfg, "offline")
            assert cfg.retrieval.top_k == 4

            store.apply_to_config(cfg, "online")
            assert cfg.retrieval.top_k == 11

            offline_state = store.get_mode_state(cfg, "offline")
            online_state = store.get_mode_state(cfg, "online")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert offline_state["values"]["top_k"] == 4
    assert online_state["values"]["top_k"] == 12
    assert online_state["defaults"]["top_k"] == 11
    assert online_state["locks"]["top_k"] is True
