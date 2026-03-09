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
            top_p=1.0,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            seed=0,
            timeout_seconds=45,
        ),
        ollama=SimpleNamespace(
            context_window=4096,
            num_predict=512,
            temperature=0.1,
            top_p=0.90,
            seed=0,
            timeout_seconds=180,
        ),
        query=SimpleNamespace(
            grounding_bias=8,
            allow_open_knowledge=True,
        ),
        hallucination_guard=SimpleNamespace(
            enabled=False,
            threshold=0.8,
            failure_action="block",
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

            assert state["defaults"]["top_k"] == 6
            assert abs(state["defaults"]["min_score"] - 0.08) < 1e-9
            assert state["defaults"]["context_window"] == 128000
            assert state["defaults"]["max_tokens"] == 1024
            assert abs(state["defaults"]["top_p"] - 1.0) < 1e-9
            assert state["defaults"]["seed"] == 0

            store.apply_to_config(cfg, "online")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert cfg.retrieval.top_k == 6
    assert abs(cfg.retrieval.min_score - 0.08) < 1e-9
    assert cfg.api.context_window == 128000
    assert cfg.api.max_tokens == 1024
    assert abs(cfg.api.top_p - 1.0) < 1e-9
    assert cfg.api.seed == 0


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
    assert abs(offline_state["values"]["top_p"] - 0.90) < 1e-9
    assert online_state["values"]["top_k"] == 6
    assert abs(online_state["values"]["min_score"] - 0.08) < 1e-9
    assert online_state["values"]["context_window"] == 128000
    assert online_state["values"]["max_tokens"] == 1024
    assert abs(online_state["values"]["top_p"] - 1.0) < 1e-9


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


def test_legacy_reasoning_dial_migrates_to_open_knowledge_flag():
    cfg = _make_config()

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            cfg_dir = Path(temp_root) / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            (cfg_dir / "config.yaml").write_text(
                "\n".join(
                    [
                        "mode: offline",
                        "modes:",
                        "  offline:",
                        "    values:",
                        "      grounding_bias: 8",
                        "      reasoning_dial: 0",
                        "    defaults:",
                        "      grounding_bias: 7",
                        "      reasoning_dial: 3",
                        "    locks:",
                        "      grounding_bias: false",
                        "      reasoning_dial: true",
                    ]
                ),
                encoding="utf-8",
            )

            store = ModeTuningStore()
            state = store.get_mode_state(cfg, "offline")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert state["values"]["allow_open_knowledge"] is False
    assert state["defaults"]["allow_open_knowledge"] is True
    assert state["locks"]["allow_open_knowledge"] is True
    assert "reasoning_dial" not in state["values"]
    assert "reasoning_dial" not in state["defaults"]
    assert "reasoning_dial" not in state["locks"]


def test_apply_to_config_pushes_query_mode_settings_into_runtime_config():
    cfg = _make_config()

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            store = ModeTuningStore()
            store.update_value(cfg, "offline", "grounding_bias", 9)
            store.update_value(cfg, "offline", "allow_open_knowledge", False)
            store.apply_to_config(cfg, "offline")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert cfg.query.grounding_bias == 9
    assert cfg.query.allow_open_knowledge is False


def test_snapshot_config_captures_query_values_from_live_config():
    cfg = _make_config()
    cfg.query.grounding_bias = 3
    cfg.query.allow_open_knowledge = False

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            store = ModeTuningStore()
            snapshot = store.snapshot_config(cfg, "offline")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    assert snapshot["grounding_bias"] == 3
    assert snapshot["allow_open_knowledge"] is False
