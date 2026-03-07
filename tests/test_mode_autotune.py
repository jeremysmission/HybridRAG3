import importlib.util
import sys
from pathlib import Path

import yaml

from src.core.config import load_config
from src.gui.helpers.mode_tuning import ModeTuningStore


ROOT = Path(__file__).resolve().parent.parent


def _load_tool_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_default_config(root: Path) -> None:
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "mode": "offline",
        "retrieval": {
            "top_k": 5,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
        },
        "ollama": {
            "context_window": 4096,
            "num_predict": 512,
            "temperature": 0.05,
            "timeout_seconds": 180,
            "base_url": "http://127.0.0.1:11434",
            "model": "phi4-mini",
            "keep_alive": -1,
            "num_thread": 0,
        },
        "api": {
            "context_window": 128000,
            "max_tokens": 16384,
            "temperature": 0.05,
            "timeout_seconds": 180,
            "endpoint": "",
            "model": "",
            "deployment": "",
            "api_version": "",
            "provider": "",
            "auth_scheme": "",
        },
        "embedding": {
            "model_name": "nomic-embed-text",
            "dimension": 768,
            "batch_size": 16,
            "device": "cpu",
        },
        "paths": {
            "database": str(root / "data" / "hybridrag.sqlite3"),
            "embeddings_cache": str(root / "data" / "_embeddings"),
            "source_folder": str(root / "data" / "source"),
            "download_folder": str(root / "data" / "source"),
            "transfer_source_folder": "",
        },
        "chunking": {"chunk_size": 1200, "overlap": 200, "max_heading_len": 160},
        "cost": {
            "track_enabled": True,
            "input_cost_per_1k": 0.0015,
            "output_cost_per_1k": 0.002,
            "daily_budget_usd": 5.0,
        },
        "indexing": {"block_chars": 200000, "max_chars_per_file": 2000000},
        "security": {"audit_logging": True, "pii_sanitization": True},
        "performance": {
            "gc_between_blocks": True,
            "gc_between_files": True,
            "max_concurrent_files": 1,
        },
        "hallucination_guard": {
            "enabled": False,
            "threshold": 0.8,
            "failure_action": "block",
        },
        "vllm": {
            "enabled": False,
            "base_url": "http://localhost:8000",
            "model": "phi4:14b-q4_K_M",
            "timeout_seconds": 120,
            "context_window": 16384,
        },
        "transformers_llm": {
            "enabled": False,
            "model": "microsoft/phi-4",
            "max_new_tokens": 2048,
            "temperature": 0.05,
            "load_in_4bit": True,
            "device_map": "auto",
            "trust_remote_code": False,
        },
    }
    with open(cfg_dir / "default_config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def test_runtime_config_filename_strips_repo_config_prefix():
    eval_runner = _load_tool_module("eval_runner_test_mod", "tools/eval_runner.py")
    assert (
        eval_runner._runtime_config_filename("config/.tmp_autotune/run1/candidate.yaml")
        == ".tmp_autotune/run1/candidate.yaml"
    )
    assert eval_runner._runtime_config_filename("default_config.yaml") == "default_config.yaml"


def test_build_candidates_starter_grid_counts():
    autotune = _load_tool_module("mode_autotune_test_mod_counts", "tools/run_mode_autotune.py")
    offline = autotune.build_candidates("offline", "starter")
    online = autotune.build_candidates("online", "starter")

    assert len(offline) == 8
    assert len(online) == 8
    assert offline[0].mode == "offline"
    assert "np" in offline[0].name
    assert "mt" in online[0].name


def test_build_candidate_config_writes_mode_specific_knobs():
    autotune = _load_tool_module("mode_autotune_test_mod_cfg", "tools/run_mode_autotune.py")
    base = {
        "mode": "offline",
        "retrieval": {},
        "ollama": {},
        "api": {},
    }

    online_cfg = autotune._build_candidate_config(
        base,
        "online",
        {
            "top_k": 8,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.05,
            "timeout_seconds": 180,
        },
    )
    offline_cfg = autotune._build_candidate_config(
        base,
        "offline",
        {
            "top_k": 4,
            "min_score": 0.15,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "context_window": 4096,
            "num_predict": 384,
            "temperature": 0.05,
            "timeout_seconds": 180,
        },
    )

    assert online_cfg["mode"] == "online"
    assert online_cfg["api"]["max_tokens"] == 1024
    assert online_cfg["retrieval"]["top_k"] == 8
    assert offline_cfg["mode"] == "offline"
    assert offline_cfg["ollama"]["num_predict"] == 384
    assert offline_cfg["retrieval"]["min_score"] == 0.15


def test_apply_winners_updates_mode_store_values_defaults_and_locks(tmp_path):
    autotune = _load_tool_module("mode_autotune_test_mod_apply", "tools/run_mode_autotune.py")
    _write_default_config(tmp_path)
    autotune.PROJECT_ROOT = tmp_path

    winners = {
        "offline": {
            "status": "ok",
            "candidate": "tk4_ms15_np384",
            "values": {
                "top_k": 4,
                "min_score": 0.15,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "context_window": 4096,
                "num_predict": 384,
                "temperature": 0.05,
                "timeout_seconds": 180,
            },
        },
        "online": {
            "status": "ok",
            "candidate": "tk8_ms10_mt1024",
            "values": {
                "top_k": 8,
                "min_score": 0.10,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "context_window": 128000,
                "max_tokens": 1024,
                "temperature": 0.05,
                "timeout_seconds": 180,
            },
        },
    }

    applied = autotune._apply_winners(
        winners=winners,
        lock_winner=True,
        run_dir=tmp_path / "logs",
    )

    cfg = load_config(str(tmp_path), "default_config.yaml")
    store = ModeTuningStore(str(tmp_path))
    offline_state = store.get_mode_state(cfg, "offline")
    online_state = store.get_mode_state(cfg, "online")

    assert applied["modes"]["offline"]["candidate"] == "tk4_ms15_np384"
    assert offline_state["values"]["top_k"] == 4
    assert offline_state["defaults"]["num_predict"] == 384
    assert offline_state["locks"]["top_k"] is True
    assert online_state["values"]["max_tokens"] == 1024
    assert online_state["defaults"]["context_window"] == 128000
    assert online_state["locks"]["max_tokens"] is True
