import importlib.util
import json
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
            "top_k": 4,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
        },
        "ollama": {
            "context_window": 4096,
            "num_predict": 384,
            "temperature": 0.05,
            "timeout_seconds": 180,
            "base_url": "http://127.0.0.1:11434",
            "model": "phi4-mini",
            "keep_alive": -1,
            "num_thread": 0,
        },
        "api": {
            "context_window": 128000,
            "max_tokens": 1024,
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
    assert eval_runner._runtime_config_filename(None) == "config.yaml"


def test_build_candidates_starter_grid_counts():
    autotune = _load_tool_module("mode_autotune_test_mod_counts", "tools/run_mode_autotune.py")
    offline = autotune.build_candidates("offline", "starter")
    online = autotune.build_candidates("online", "starter")

    assert len(offline) == 16
    assert len(online) == 24
    assert offline[0].mode == "offline"
    assert offline[0].bundle in {"strict", "balanced"}
    assert "np" in offline[0].name
    assert "_b" in offline[0].name
    assert "mt" in online[0].name
    assert any(candidate.bundle == "recovery" for candidate in online)
    assert any("_cr0t35_" in candidate.name for candidate in online if candidate.bundle == "strict")
    assert any(
        candidate.values.get("corrective_retrieval") is True
        and abs(float(candidate.values.get("corrective_threshold", 0.0)) - 0.50) < 1e-9
        for candidate in online
        if candidate.bundle == "recovery"
    )


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
            "corrective_retrieval": True,
            "corrective_threshold": 0.50,
            "grounding_bias": 6,
            "allow_open_knowledge": True,
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.15,
            "top_p": 0.95,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 0,
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
            "grounding_bias": 9,
            "allow_open_knowledge": False,
            "context_window": 4096,
            "num_predict": 384,
            "temperature": 0.05,
            "top_p": 0.90,
            "seed": 0,
            "timeout_seconds": 180,
        },
    )

    assert online_cfg["mode"] == "online"
    assert online_cfg["modes"]["online"]["api"]["max_tokens"] == 1024
    assert abs(online_cfg["modes"]["online"]["api"]["top_p"] - 0.95) < 1e-9
    assert online_cfg["modes"]["online"]["retrieval"]["top_k"] == 8
    assert online_cfg["modes"]["online"]["retrieval"]["corrective_retrieval"] is True
    assert abs(online_cfg["modes"]["online"]["retrieval"]["corrective_threshold"] - 0.50) < 1e-9
    assert online_cfg["modes"]["online"]["query"]["grounding_bias"] == 6
    assert online_cfg["modes"]["online"]["query"]["allow_open_knowledge"] is True
    assert offline_cfg["mode"] == "offline"
    assert offline_cfg["modes"]["offline"]["ollama"]["num_predict"] == 384
    assert abs(offline_cfg["modes"]["offline"]["ollama"]["top_p"] - 0.90) < 1e-9
    assert offline_cfg["modes"]["offline"]["retrieval"]["min_score"] == 0.15
    assert offline_cfg["modes"]["offline"]["query"]["grounding_bias"] == 9
    assert offline_cfg["modes"]["offline"]["query"]["allow_open_knowledge"] is False


def test_build_candidate_config_updates_mode_scoped_runtime_sections():
    autotune = _load_tool_module("mode_autotune_test_mod_mode_scoped", "tools/run_mode_autotune.py")
    base_config = {
        "mode": "offline",
        "modes": {
            "offline": {
                "retrieval": {
                    "top_k": 5,
                    "min_score": 0.10,
                    "hybrid_search": True,
                    "reranker_enabled": False,
                    "reranker_top_n": 20,
                },
                "query": {
                    "grounding_bias": 8,
                    "allow_open_knowledge": True,
                },
                "ollama": {
                    "context_window": 4096,
                    "num_predict": 2048,
                    "temperature": 0.20,
                    "top_p": 0.99,
                    "seed": 99,
                    "timeout_seconds": 60,
                },
            },
            "online": {
                "retrieval": {
                    "top_k": 10,
                    "min_score": 0.12,
                    "hybrid_search": True,
                    "reranker_enabled": False,
                    "reranker_top_n": 20,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.35,
                },
                "query": {
                    "grounding_bias": 3,
                    "allow_open_knowledge": True,
                },
                "api": {
                    "context_window": 128000,
                    "max_tokens": 2048,
                    "temperature": 0.30,
                    "top_p": 1.0,
                    "presence_penalty": 0.0,
                    "frequency_penalty": 0.0,
                    "seed": 7,
                    "timeout_seconds": 45,
                },
            },
        },
    }

    offline_candidate = autotune.Candidate(
        mode="offline",
        name="tk4_ms15_np384_bstrict",
        bundle="strict",
        values={
            "top_k": 4,
            "min_score": 0.15,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "grounding_bias": 9,
            "allow_open_knowledge": False,
            "context_window": 4096,
            "num_predict": 384,
            "temperature": 0.05,
            "top_p": 0.90,
            "seed": 0,
            "timeout_seconds": 180,
        },
    )
    online_candidate = autotune.Candidate(
        mode="online",
        name="tk8_ms10_mt1024_bbalanced",
        bundle="balanced",
        values={
            "top_k": 8,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "corrective_retrieval": False,
            "corrective_threshold": 0.35,
            "grounding_bias": 6,
            "allow_open_knowledge": True,
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.15,
            "top_p": 0.95,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 0,
            "timeout_seconds": 180,
        },
    )

    offline_cfg = autotune._build_candidate_config(base_config, "offline", offline_candidate.values)
    offline_runtime = autotune.build_runtime_config_dict(offline_cfg, {})
    online_cfg = autotune._build_candidate_config(base_config, "online", online_candidate.values)
    online_runtime = autotune.build_runtime_config_dict(online_cfg, {})

    assert offline_cfg["modes"]["offline"]["retrieval"]["top_k"] == 4
    assert offline_cfg["modes"]["offline"]["query"]["grounding_bias"] == 9
    assert offline_cfg["modes"]["offline"]["ollama"]["num_predict"] == 384
    assert offline_runtime["retrieval"]["top_k"] == 4
    assert offline_runtime["query"]["grounding_bias"] == 9
    assert offline_runtime["ollama"]["num_predict"] == 384

    assert online_cfg["modes"]["online"]["retrieval"]["top_k"] == 8
    assert online_cfg["modes"]["online"]["retrieval"]["corrective_retrieval"] is False
    assert online_cfg["modes"]["online"]["query"]["grounding_bias"] == 6
    assert online_cfg["modes"]["online"]["api"]["max_tokens"] == 1024
    assert online_runtime["retrieval"]["top_k"] == 8
    assert online_runtime["retrieval"]["corrective_retrieval"] is False
    assert online_runtime["query"]["grounding_bias"] == 6
    assert online_runtime["api"]["max_tokens"] == 1024


def test_build_candidate_config_ignores_runtime_active_mode_env(monkeypatch):
    autotune = _load_tool_module("mode_autotune_test_mod_env_guard", "tools/run_mode_autotune.py")
    monkeypatch.setenv("HYBRIDRAG_ACTIVE_MODE", "offline")

    base_config = {
        "mode": "offline",
        "modes": {
            "offline": {
                "retrieval": {"top_k": 5, "min_score": 0.10},
                "query": {"grounding_bias": 8, "allow_open_knowledge": True},
            },
            "online": {
                "retrieval": {"top_k": 10, "min_score": 0.12},
                "query": {"grounding_bias": 3, "allow_open_knowledge": False},
                "retrieval": {"top_k": 10, "min_score": 0.12, "corrective_retrieval": True, "corrective_threshold": 0.35},
                "api": {"max_tokens": 2048},
            },
        },
    }

    candidate_cfg = autotune._build_candidate_config(
        base_config,
        "online",
        {
            "top_k": 8,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "corrective_retrieval": False,
            "corrective_threshold": 0.35,
            "grounding_bias": 6,
            "allow_open_knowledge": True,
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.15,
            "top_p": 0.95,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 0,
            "timeout_seconds": 180,
        },
    )

    assert candidate_cfg["modes"]["offline"]["retrieval"]["top_k"] == 5
    assert candidate_cfg["modes"]["offline"]["query"]["grounding_bias"] == 8
    assert candidate_cfg["modes"]["online"]["retrieval"]["top_k"] == 8
    assert candidate_cfg["modes"]["online"]["retrieval"]["corrective_retrieval"] is False
    assert candidate_cfg["modes"]["online"]["query"]["grounding_bias"] == 6
    assert candidate_cfg["modes"]["online"]["api"]["max_tokens"] == 1024


def test_online_ready_normalizes_mode_scoped_config_credentials(tmp_path, monkeypatch):
    autotune = _load_tool_module("mode_autotune_test_mod_online_ready", "tools/run_mode_autotune.py")
    autotune.PROJECT_ROOT = tmp_path
    config_path = tmp_path / "config" / "custom.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "mode": "offline",
                "modes": {
                    "online": {
                        "api": {
                            "key": "config-only-key",
                            "endpoint": "https://example.invalid/openai",
                        }
                    }
                },
                "paths": {
                    "database": str(tmp_path / "data" / "hybridrag.sqlite3"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(autotune, "_database_ready", lambda _: (True, ""))

    seen: dict[str, object] = {}

    class _FakeCreds:
        def __init__(self, config_dict):
            api_cfg = (config_dict or {}).get("api", {})
            self.has_key = bool(api_cfg.get("key"))
            self.has_endpoint = bool(api_cfg.get("endpoint"))
            self.is_online_ready = self.has_key and self.has_endpoint

    def _fake_resolve_credentials(config_dict=None, use_cache=True):
        seen["config_dict"] = config_dict
        seen["use_cache"] = use_cache
        return _FakeCreds(config_dict)

    monkeypatch.setattr(autotune, "resolve_credentials", _fake_resolve_credentials)
    raw_config = autotune._load_config_dict(config_path)

    ready, reason = autotune._online_ready(config_path, config_dict=raw_config)

    assert ready is True
    assert reason == ""
    assert seen["use_cache"] is False
    assert seen["config_dict"]["api"]["key"] == "config-only-key"
    assert seen["config_dict"]["api"]["endpoint"] == "https://example.invalid/openai"


def test_candidate_snapshot_includes_partitioned_query_and_generation_sections():
    autotune = _load_tool_module("mode_autotune_test_mod_snapshot", "tools/run_mode_autotune.py")
    candidate = autotune.Candidate(
        mode="online",
        name="tk8_ms10_mt1024_bbalanced",
        bundle="balanced",
        values={
            "top_k": 8,
            "min_score": 0.10,
            "hybrid_search": True,
            "reranker_enabled": False,
            "reranker_top_n": 20,
            "grounding_bias": 6,
            "allow_open_knowledge": True,
            "context_window": 128000,
            "max_tokens": 1024,
            "temperature": 0.15,
            "top_p": 0.95,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 0,
            "timeout_seconds": 180,
        },
    )

    snapshot = autotune._candidate_snapshot(candidate)

    assert snapshot["bundle"] == "balanced"
    assert snapshot["sections"]["retrieval"]["top_k"] == 8
    assert snapshot["sections"]["query"]["grounding_bias"] == 6
    assert abs(snapshot["sections"]["api"]["top_p"] - 0.95) < 1e-9


def test_candidate_from_ranked_row_preserves_bundle_for_full_workflow():
    autotune = _load_tool_module("mode_autotune_test_mod_finalist", "tools/run_mode_autotune.py")
    finalist = autotune._candidate_from_ranked_row(
        "online",
        {
            "candidate": "tk8_ms10_mt1024_bbalanced",
            "bundle": "balanced",
            "values": {
                "top_k": 8,
                "min_score": 0.10,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "grounding_bias": 6,
                "allow_open_knowledge": True,
                "context_window": 128000,
                "max_tokens": 1024,
                "temperature": 0.15,
                "top_p": 0.95,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "seed": 0,
                "timeout_seconds": 180,
            },
        },
    )

    assert finalist.mode == "online"
    assert finalist.name == "tk8_ms10_mt1024_bbalanced"
    assert finalist.bundle == "balanced"
    assert finalist.values["grounding_bias"] == 6


def test_winner_set_prefers_full_stage_when_available():
    reporting = _load_tool_module(
        "mode_autotune_reporting_test_mod_winners",
        "tools/mode_autotune_reporting.py",
    )
    winner_set = reporting.build_winner_set(
        [
            {
                "mode": "offline",
                "stage": "screen",
                "candidate": "tk4_ms10_np384_bstrict",
                "bundle": "strict",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.80,
                "avg_overall": 0.70,
                "p95_latency_ms": 800,
                "avg_cost_usd": 0.0,
                "summary_path": "screen_summary.json",
                "settings_path": "screen_settings.json",
                "values": {"grounding_bias": 9},
            },
            {
                "mode": "offline",
                "stage": "full",
                "candidate": "tk4_ms15_np384_bbalanced",
                "bundle": "balanced",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.90,
                "avg_overall": 0.82,
                "p95_latency_ms": 850,
                "avg_cost_usd": 0.0,
                "summary_path": "full_summary.json",
                "settings_path": "full_settings.json",
                "values": {"grounding_bias": 7},
            },
            {
                "mode": "online",
                "stage": "screen",
                "candidate": "tk8_ms10_mt1024_bbalanced",
                "bundle": "balanced",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.88,
                "avg_overall": 0.81,
                "p95_latency_ms": 1200,
                "avg_cost_usd": 0.02,
                "summary_path": "online_summary.json",
                "settings_path": "online_settings.json",
                "values": {"grounding_bias": 6},
            },
        ]
    )

    assert winner_set["modes"]["offline"]["stage"] == "full"
    assert winner_set["modes"]["offline"]["ranked"][0]["candidate"] == "tk4_ms15_np384_bbalanced"
    assert winner_set["modes"]["offline"]["ranked"][0]["bundle"] == "balanced"
    assert winner_set["modes"]["online"]["stage"] == "screen"
    assert winner_set["modes"]["online"]["ranked"][0]["candidate"] == "tk8_ms10_mt1024_bbalanced"


def test_winner_set_falls_back_to_screen_when_full_stage_only_failed():
    reporting = _load_tool_module(
        "mode_autotune_reporting_test_mod_stage_fallback",
        "tools/mode_autotune_reporting.py",
    )
    winner_set = reporting.build_winner_set(
        [
            {
                "mode": "offline",
                "stage": "screen",
                "candidate": "tk4_ms10_np384_bstrict",
                "bundle": "strict",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.84,
                "avg_overall": 0.76,
                "p95_latency_ms": 810,
                "avg_cost_usd": 0.0,
                "summary_path": "screen_summary.json",
                "settings_path": "screen_settings.json",
                "values": {"grounding_bias": 9},
            },
            {
                "mode": "offline",
                "stage": "full",
                "candidate": "tk4_ms15_np384_bbalanced",
                "bundle": "balanced",
                "status": "failed",
                "gate_failed": False,
                "pass_rate": 0.0,
                "avg_overall": 0.0,
                "p95_latency_ms": 0,
                "avg_cost_usd": 0.0,
                "summary_path": "full_summary.json",
                "settings_path": "full_settings.json",
                "error": "eval failed",
                "values": {"grounding_bias": 7},
            },
        ]
    )

    assert winner_set["modes"]["offline"]["stage"] == "screen"
    assert winner_set["modes"]["offline"]["ranked"][0]["candidate"] == "tk4_ms10_np384_bstrict"
    assert winner_set["modes"]["offline"]["ranked"][0]["status"] == "ok"


def test_bundle_summary_rows_aggregate_candidates_by_bundle():
    reporting = _load_tool_module(
        "mode_autotune_reporting_test_mod_bundle",
        "tools/mode_autotune_reporting.py",
    )
    rows = reporting.build_bundle_summary_rows(
        [
            {
                "mode": "offline",
                "stage": "screen",
                "rank": 1,
                "candidate": "tk4_ms15_np384_bstrict",
                "bundle": "strict",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.91,
                "avg_overall": 0.84,
                "p95_latency_ms": 780,
                "avg_cost_usd": 0.0,
            },
            {
                "mode": "offline",
                "stage": "screen",
                "rank": 2,
                "candidate": "tk5_ms15_np384_bstrict",
                "bundle": "strict",
                "status": "ok",
                "gate_failed": True,
                "pass_rate": 0.75,
                "avg_overall": 0.70,
                "p95_latency_ms": 760,
                "avg_cost_usd": 0.0,
            },
            {
                "mode": "offline",
                "stage": "screen",
                "rank": 3,
                "candidate": "tk4_ms10_np384_bbalanced",
                "bundle": "balanced",
                "status": "failed",
                "gate_failed": False,
                "pass_rate": 0.0,
                "avg_overall": 0.0,
                "p95_latency_ms": 0,
                "avg_cost_usd": 0.0,
            },
        ]
    )

    strict = [row for row in rows if row["bundle"] == "strict"][0]
    balanced = [row for row in rows if row["bundle"] == "balanced"][0]

    assert strict["candidate_count"] == 2
    assert strict["ok_count"] == 2
    assert strict["gate_pass_count"] == 1
    assert strict["best_candidate"] == "tk4_ms15_np384_bstrict"
    assert balanced["candidate_count"] == 1
    assert balanced["ok_count"] == 0


def test_winner_from_mode_rows_marks_screen_fallback_not_apply_eligible():
    autotune = _load_tool_module(
        "mode_autotune_test_mod_winner_fallback",
        "tools/run_mode_autotune.py",
    )
    winner = autotune._winner_from_mode_rows(
        mode="offline",
        workflow="full",
        rows=[
            {
                "mode": "offline",
                "stage": "screen",
                "candidate": "tk4_ms10_np384_bstrict",
                "bundle": "strict",
                "status": "ok",
                "gate_failed": False,
                "pass_rate": 0.84,
                "avg_overall": 0.76,
                "p95_latency_ms": 810,
                "avg_cost_usd": 0.0,
                "summary_path": "screen_summary.json",
                "settings_path": "screen_settings.json",
                "values": {"grounding_bias": 9},
            },
            {
                "mode": "offline",
                "stage": "full",
                "candidate": "tk4_ms15_np384_bbalanced",
                "bundle": "balanced",
                "status": "failed",
                "gate_failed": False,
                "pass_rate": 0.0,
                "avg_overall": 0.0,
                "p95_latency_ms": 0,
                "avg_cost_usd": 0.0,
                "summary_path": "full_summary.json",
                "settings_path": "full_settings.json",
                "values": {"grounding_bias": 7},
            },
        ],
    )

    assert winner["status"] == "ok"
    assert winner["stage"] == "screen"
    assert winner["candidate"] == "tk4_ms10_np384_bstrict"
    assert winner["apply_eligible"] is False
    assert "screen fallback" in winner["reason"]


def test_apply_winners_updates_mode_store_values_defaults_and_locks(tmp_path):
    autotune = _load_tool_module("mode_autotune_test_mod_apply", "tools/run_mode_autotune.py")
    _write_default_config(tmp_path)
    autotune.PROJECT_ROOT = tmp_path

    winners = {
        "offline": {
            "status": "ok",
            "candidate": "tk4_ms15_np384_bstrict",
            "values": {
                "top_k": 4,
                "min_score": 0.15,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "grounding_bias": 9,
                "allow_open_knowledge": False,
                "context_window": 4096,
                "num_predict": 384,
                "temperature": 0.05,
                "top_p": 0.90,
                "seed": 0,
                "timeout_seconds": 180,
            },
        },
        "online": {
            "status": "ok",
            "candidate": "tk8_ms10_mt1024_bbalanced",
            "values": {
                "top_k": 8,
                "min_score": 0.10,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "corrective_retrieval": False,
                "corrective_threshold": 0.50,
                "grounding_bias": 6,
                "allow_open_knowledge": True,
                "context_window": 128000,
                "max_tokens": 1024,
                "temperature": 0.15,
                "top_p": 0.95,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "seed": 0,
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

    assert applied["modes"]["offline"]["candidate"] == "tk4_ms15_np384_bstrict"
    assert offline_state["values"]["top_k"] == 4
    assert offline_state["values"]["grounding_bias"] == 9
    assert offline_state["values"]["allow_open_knowledge"] is False
    assert offline_state["defaults"]["num_predict"] == 384
    assert abs(offline_state["defaults"]["top_p"] - 0.90) < 1e-9
    assert offline_state["locks"]["top_k"] is True
    assert offline_state["locks"]["grounding_bias"] is True
    assert online_state["values"]["max_tokens"] == 1024
    assert online_state["values"]["corrective_retrieval"] is False
    assert abs(online_state["values"]["corrective_threshold"] - 0.50) < 1e-9
    assert online_state["values"]["grounding_bias"] == 6
    assert online_state["values"]["allow_open_knowledge"] is True
    assert online_state["defaults"]["context_window"] == 128000
    assert abs(online_state["defaults"]["corrective_threshold"] - 0.50) < 1e-9
    assert abs(online_state["defaults"]["top_p"] - 0.95) < 1e-9
    assert online_state["locks"]["max_tokens"] is True
    assert online_state["locks"]["corrective_retrieval"] is True


def test_apply_winners_skips_screen_fallbacks_not_eligible_for_apply(tmp_path):
    autotune = _load_tool_module("mode_autotune_test_mod_apply_skip", "tools/run_mode_autotune.py")
    _write_default_config(tmp_path)
    autotune.PROJECT_ROOT = tmp_path

    winners = {
        "offline": {
            "status": "ok",
            "stage": "screen",
            "candidate": "tk4_ms10_np384_bstrict",
            "reason": "preferred screen fallback; no successful full-stage winner",
            "apply_eligible": False,
            "values": {
                "top_k": 4,
                "min_score": 0.10,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "grounding_bias": 9,
                "allow_open_knowledge": False,
                "context_window": 4096,
                "num_predict": 384,
                "temperature": 0.05,
                "top_p": 0.90,
                "seed": 0,
                "timeout_seconds": 180,
            },
        },
        "online": {
            "status": "ok",
            "stage": "full",
            "candidate": "tk8_ms10_mt1024_bbalanced",
            "apply_eligible": True,
            "values": {
                "top_k": 8,
                "min_score": 0.10,
                "hybrid_search": True,
                "reranker_enabled": False,
                "reranker_top_n": 20,
                "corrective_retrieval": False,
                "corrective_threshold": 0.50,
                "grounding_bias": 6,
                "allow_open_knowledge": True,
                "context_window": 128000,
                "max_tokens": 1024,
                "temperature": 0.15,
                "top_p": 0.95,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "seed": 0,
                "timeout_seconds": 180,
            },
        },
    }

    applied = autotune._apply_winners(
        winners=winners,
        lock_winner=False,
        run_dir=tmp_path / "logs",
    )

    cfg = load_config(str(tmp_path), "default_config.yaml")
    store = ModeTuningStore(str(tmp_path))
    offline_state = store.get_mode_state(cfg, "offline")
    online_state = store.get_mode_state(cfg, "online")

    assert "offline" not in applied["modes"]
    assert applied["skipped_modes"]["offline"] == (
        "preferred screen fallback; no successful full-stage winner"
    )
    assert applied["modes"]["online"]["candidate"] == "tk8_ms10_mt1024_bbalanced"
    assert offline_state["values"]["grounding_bias"] != 9
    assert online_state["values"]["grounding_bias"] == 6
    assert online_state["values"]["corrective_retrieval"] is False


def test_main_writes_screen_fallback_winner_as_not_apply_eligible(tmp_path, monkeypatch):
    autotune = _load_tool_module("mode_autotune_test_mod_main_fallback", "tools/run_mode_autotune.py")
    _write_default_config(tmp_path)
    autotune.PROJECT_ROOT = tmp_path

    dataset_path = tmp_path / "Eval" / "golden_tuning_400.json"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        autotune,
        "_parse_args",
        lambda: autotune.argparse.Namespace(
            mode="offline",
            workflow="full",
            grid="starter",
            dataset=str(dataset_path),
            config=str(tmp_path / "config" / "default_config.yaml"),
            outroot="logs/autotune_runs",
            screen_limit=50,
            finalists=2,
            full_limit=0,
            apply_winner=False,
            lock_winner=False,
            min_unanswerable_proxy=0.0,
            min_injection_proxy=0.0,
        ),
    )
    monkeypatch.setattr(autotune, "_offline_ready", lambda config_path: (True, ""))
    monkeypatch.setattr(autotune, "_timestamp_slug", lambda: "test_run")
    monkeypatch.setattr(autotune, "_git_head", lambda: "deadbee")

    def _fake_run_stage(**kwargs):
        if kwargs["stage"] == "screen":
            return [
                {
                    "mode": "offline",
                    "stage": "screen",
                    "rank": 1,
                    "candidate": "tk4_ms10_np384_bstrict",
                    "bundle": "strict",
                    "status": "ok",
                    "gate_failed": False,
                    "count": 50,
                    "pass_rate": 0.84,
                    "avg_overall": 0.76,
                    "p50_latency_ms": 700,
                    "p95_latency_ms": 810,
                    "avg_cost_usd": 0.0,
                    "unanswerable_accuracy_proxy": 1.0,
                    "injection_resistance_proxy": 1.0,
                    "temp_config": "config/.tmp_autotune/test_run/offline/screen/one.yaml",
                    "summary_path": "screen_summary.json",
                    "settings_path": "screen_settings.json",
                    "candidate_dir": "offline/screen/tk4_ms10_np384_bstrict",
                    "error": "",
                    "values": {
                        "top_k": 4,
                        "min_score": 0.10,
                        "hybrid_search": True,
                        "reranker_enabled": False,
                        "reranker_top_n": 20,
                        "grounding_bias": 9,
                        "allow_open_knowledge": False,
                        "context_window": 4096,
                        "num_predict": 384,
                        "temperature": 0.05,
                        "top_p": 0.90,
                        "seed": 0,
                        "timeout_seconds": 180,
                    },
                }
            ]
        return [
            {
                "mode": "offline",
                "stage": "full",
                "rank": 1,
                "candidate": "tk4_ms15_np384_bbalanced",
                "bundle": "balanced",
                "status": "failed",
                "gate_failed": False,
                "count": 0,
                "pass_rate": 0.0,
                "avg_overall": 0.0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "avg_cost_usd": 0.0,
                "unanswerable_accuracy_proxy": 0.0,
                "injection_resistance_proxy": 0.0,
                "temp_config": "config/.tmp_autotune/test_run/offline/full/two.yaml",
                "summary_path": "full_summary.json",
                "settings_path": "full_settings.json",
                "candidate_dir": "offline/full/tk4_ms15_np384_bbalanced",
                "error": "eval failed",
                "values": {
                    "top_k": 4,
                    "min_score": 0.15,
                    "hybrid_search": True,
                    "reranker_enabled": False,
                    "reranker_top_n": 20,
                    "grounding_bias": 7,
                    "allow_open_knowledge": True,
                    "context_window": 4096,
                    "num_predict": 384,
                    "temperature": 0.12,
                    "top_p": 0.93,
                    "seed": 0,
                    "timeout_seconds": 180,
                },
            }
        ]

    monkeypatch.setattr(autotune, "run_stage", _fake_run_stage)

    assert autotune.main() == 0

    run_dir = tmp_path / "logs" / "autotune_runs" / "test_run"
    winners = json.loads((run_dir / "winners.json").read_text(encoding="utf-8"))
    readme_text = (run_dir / "README_NEXT_STEPS.txt").read_text(encoding="utf-8")

    assert winners["offline"]["status"] == "ok"
    assert winners["offline"]["stage"] == "screen"
    assert winners["offline"]["apply_eligible"] is False
    assert "screen fallback" in winners["offline"]["reason"]
    assert "fell back to a screen-stage winner" in readme_text


def test_write_next_steps_does_not_report_fallback_for_screen_workflow(tmp_path):
    autotune = _load_tool_module("mode_autotune_test_mod_next_steps_screen", "tools/run_mode_autotune.py")
    readme_path = tmp_path / "README_NEXT_STEPS.txt"
    args = autotune.argparse.Namespace(
        workflow="screen",
        mode="offline",
        grid="starter",
        screen_limit=50,
        finalists=2,
        full_limit=0,
    )

    autotune._write_next_steps(
        readme_path,
        args,
        winners={
            "offline": {
                "status": "ok",
                "stage": "screen",
                "candidate": "tk4_ms10_np384_bstrict",
                "apply_eligible": False,
            }
        },
    )

    readme_text = readme_path.read_text(encoding="utf-8")

    assert "fell back to a screen-stage winner" not in readme_text
