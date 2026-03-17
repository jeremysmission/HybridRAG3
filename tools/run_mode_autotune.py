#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the mode autotune workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Existing config, the golden eval dataset, and optional CLI flags.
# Outputs: Timestamped autotune logs, leaderboards, winner summaries, and optional mode-default updates.
# Safety notes: Default behavior is screen-only and does NOT modify saved defaults.
# ============================
"""
HybridRAG3 Mode Autotune Orchestrator

Default safe workflow:
1. Run a 50-question screening pass across a small starter grid
2. Save ranked results under logs/autotune_runs/<timestamp>/
3. Stop without changing config/config.yaml

When you are happy with the screening results:
4. Re-run with --workflow full to promote the top finalists onto the full dataset
5. Re-run with --apply-winner to save the winning bundle into config/config.yaml

Quick start:
  python tools/run_mode_autotune.py
  python tools/run_mode_autotune.py --mode offline --workflow full
  python tools/run_mode_autotune.py --mode both --workflow full --apply-winner
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_config
from src.core.config_authority import build_runtime_config_dict, set_canonical_config_value
from src.gui.helpers.mode_tuning import ModeTuningStore
from src.core.user_modes import load_user_modes_data
from src.security.credentials import resolve_credentials
from tools.mode_autotune_reporting import (
    build_bundle_summary_rows,
    build_winner_set,
    rank_rows,
    write_bundle_summary_csv,
    write_leaderboard_csv,
    write_winner_set_csv,
)

STARTER_GRID = {
    "offline": {
        "top_k": [4, 5],
        "min_score": [0.10, 0.15],
        "num_predict": [384, 512],
    },
    "online": {
        "top_k": [6, 8],
        "min_score": [0.08, 0.10],
        "max_tokens": [512, 1024],
    },
}

WIDE_GRID = {
    "offline": {
        "top_k": [4, 5, 6],
        "min_score": [0.10, 0.12, 0.15],
        "num_predict": [384, 512],
    },
    "online": {
        "top_k": [6, 8, 10],
        "min_score": [0.08, 0.10, 0.12],
        "max_tokens": [512, 1024],
    },
}

GRID_PRESETS = {
    "starter": STARTER_GRID,
    "wide": WIDE_GRID,
}

QUERY_GENERATION_BUNDLES = {
    "starter": {
        "offline": [
            {
                "name": "strict",
                "values": {
                    "grounding_bias": 9,
                    "allow_open_knowledge": False,
                    "temperature": 0.05,
                    "top_p": 0.90,
                },
            },
            {
                "name": "balanced",
                "values": {
                    "grounding_bias": 7,
                    "allow_open_knowledge": True,
                    "temperature": 0.12,
                    "top_p": 0.93,
                },
            },
        ],
        "online": [
            {
                "name": "strict",
                "values": {
                    "grounding_bias": 8,
                    "allow_open_knowledge": False,
                    "corrective_retrieval": False,
                    "corrective_threshold": 0.35,
                    "temperature": 0.05,
                    "top_p": 0.90,
                },
            },
            {
                "name": "balanced",
                "values": {
                    "grounding_bias": 6,
                    "allow_open_knowledge": True,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.35,
                    "temperature": 0.15,
                    "top_p": 0.95,
                },
            },
            {
                "name": "recovery",
                "values": {
                    "grounding_bias": 6,
                    "allow_open_knowledge": True,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.50,
                    "temperature": 0.12,
                    "top_p": 0.93,
                },
            },
        ],
    },
    "wide": {
        "offline": [
            {
                "name": "strict",
                "values": {
                    "grounding_bias": 9,
                    "allow_open_knowledge": False,
                    "temperature": 0.05,
                    "top_p": 0.90,
                },
            },
            {
                "name": "balanced",
                "values": {
                    "grounding_bias": 7,
                    "allow_open_knowledge": True,
                    "temperature": 0.12,
                    "top_p": 0.93,
                },
            },
            {
                "name": "open",
                "values": {
                    "grounding_bias": 4,
                    "allow_open_knowledge": True,
                    "temperature": 0.20,
                    "top_p": 0.97,
                },
            },
        ],
        "online": [
            {
                "name": "strict",
                "values": {
                    "grounding_bias": 8,
                    "allow_open_knowledge": False,
                    "corrective_retrieval": False,
                    "corrective_threshold": 0.35,
                    "temperature": 0.05,
                    "top_p": 0.90,
                },
            },
            {
                "name": "balanced",
                "values": {
                    "grounding_bias": 6,
                    "allow_open_knowledge": True,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.35,
                    "temperature": 0.15,
                    "top_p": 0.95,
                },
            },
            {
                "name": "recovery",
                "values": {
                    "grounding_bias": 6,
                    "allow_open_knowledge": True,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.50,
                    "temperature": 0.12,
                    "top_p": 0.93,
                },
            },
            {
                "name": "open",
                "values": {
                    "grounding_bias": 4,
                    "allow_open_knowledge": True,
                    "corrective_retrieval": True,
                    "corrective_threshold": 0.65,
                    "temperature": 0.25,
                    "top_p": 1.0,
                },
            },
        ],
    },
}

FIXED_KNOBS = {
    "offline": {
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "temperature": 0.05,
        "top_p": 0.90,
        "seed": 0,
        "timeout_seconds": 180,
        "grounding_bias": 8,
        "allow_open_knowledge": True,
    },
    "online": {
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "corrective_retrieval": True,
        "corrective_threshold": 0.35,
        "context_window": 128000,
        "temperature": 0.05,
        "top_p": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": 0,
        "timeout_seconds": 180,
        "grounding_bias": 7,
        "allow_open_knowledge": True,
    },
}


@dataclass
class Candidate:
    mode: str
    name: str
    bundle: str
    values: Dict[str, Any]


def _print(msg: str) -> None:
    print(msg, flush=True)


def _normalize_mode(mode: str) -> str:
    return "online" if str(mode).strip().lower() == "online" else "offline"


def _selected_modes(mode: str) -> List[str]:
    raw = str(mode).strip().lower()
    if raw == "both":
        return ["offline", "online"]
    return [_normalize_mode(raw)]


def _resolve_existing_path(raw: str, *, prefer_config_dir: bool = False) -> Path:
    if not raw:
        raise SystemExit("Expected a non-empty path")
    path = Path(raw)
    if path.is_absolute():
        if not path.exists():
            raise SystemExit(f"Path not found: {path}")
        return path
    candidate = (PROJECT_ROOT / path).resolve()
    if candidate.exists():
        return candidate
    if prefer_config_dir:
        candidate = (PROJECT_ROOT / "config" / path).resolve()
        if candidate.exists():
            return candidate
    raise SystemExit(f"Path not found: {raw}")


def _config_filename_from_path(config_path: Path) -> str:
    config_dir = (PROJECT_ROOT / "config").resolve()
    try:
        return str(config_path.resolve().relative_to(config_dir)).replace("\\", "/")
    except ValueError as exc:
        raise SystemExit("Autotune base config must live under this repo's config/ directory") from exc


def _load_config_dict(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _load_runtime_config(config_path: Path):
    return load_config(str(PROJECT_ROOT), _config_filename_from_path(config_path))


def _credential_runtime_config_dict(
    config_path: Path,
    *,
    config_dict: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if config_dict is not None:
        user_modes = load_user_modes_data(str(PROJECT_ROOT))
        runtime = build_runtime_config_dict(config_dict, user_modes)
        return runtime if isinstance(runtime, dict) else {}
    return asdict(_load_runtime_config(config_path))


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _timestamp_slug() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _candidate_name(mode: str, values: Dict[str, Any], bundle: str) -> str:
    min_score = int(round(float(values["min_score"]) * 100))
    if mode == "offline":
        base = (
            f"tk{int(values['top_k'])}_"
            f"ms{min_score:02d}_"
            f"np{int(values['num_predict'])}"
        )
    else:
        base = (
            f"tk{int(values['top_k'])}_"
            f"ms{min_score:02d}_"
            f"mt{int(values['max_tokens'])}"
        )
        if "corrective_retrieval" in values:
            corrective_on = 1 if bool(values["corrective_retrieval"]) else 0
            corrective_threshold = int(round(float(values.get("corrective_threshold", 0.0)) * 100))
            base = f"{base}_cr{corrective_on}t{corrective_threshold:02d}"
    return f"{base}_b{bundle}"


def _candidate_sections(mode: str, values: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    retrieval = {
        "top_k": int(values["top_k"]),
        "min_score": float(values["min_score"]),
        "hybrid_search": bool(values["hybrid_search"]),
        "reranker_enabled": bool(values["reranker_enabled"]),
        "reranker_top_n": int(values["reranker_top_n"]),
    }
    if mode == "online":
        retrieval["corrective_retrieval"] = bool(values.get("corrective_retrieval", True))
        retrieval["corrective_threshold"] = float(values.get("corrective_threshold", 0.35))
    query = {
        "grounding_bias": int(values["grounding_bias"]),
        "allow_open_knowledge": bool(values["allow_open_knowledge"]),
    }
    if mode == "online":
        backend = {
            "context_window": int(values["context_window"]),
            "max_tokens": int(values["max_tokens"]),
            "temperature": float(values["temperature"]),
            "top_p": float(values["top_p"]),
            "presence_penalty": float(values.get("presence_penalty", 0.0)),
            "frequency_penalty": float(values.get("frequency_penalty", 0.0)),
            "seed": int(values.get("seed", 0)),
            "timeout_seconds": int(values["timeout_seconds"]),
        }
        return {"retrieval": retrieval, "query": query, "api": backend}
    backend = {
        "context_window": int(values["context_window"]),
        "num_predict": int(values["num_predict"]),
        "temperature": float(values["temperature"]),
        "top_p": float(values["top_p"]),
        "seed": int(values.get("seed", 0)),
        "timeout_seconds": int(values["timeout_seconds"]),
    }
    return {"retrieval": retrieval, "query": query, "ollama": backend}


def _candidate_snapshot(candidate: Candidate) -> Dict[str, Any]:
    return {
        "mode": candidate.mode,
        "candidate": candidate.name,
        "bundle": candidate.bundle,
        "flat_values": copy.deepcopy(candidate.values),
        "sections": _candidate_sections(candidate.mode, candidate.values),
    }


def _bundle_definitions(mode: str, grid_name: str) -> List[Dict[str, Any]]:
    return copy.deepcopy(QUERY_GENERATION_BUNDLES[grid_name][_normalize_mode(mode)])


def _retrieval_grid(mode: str, grid_name: str) -> Dict[str, List[Any]]:
    return copy.deepcopy(GRID_PRESETS[grid_name][_normalize_mode(mode)])


def build_candidates(mode: str, grid_name: str) -> List[Candidate]:
    mode = _normalize_mode(mode)
    preset = _retrieval_grid(mode, grid_name)
    bundles = _bundle_definitions(mode, grid_name)
    keys = list(preset.keys())
    out: List[Candidate] = []
    for combo in itertools.product(*(preset[key] for key in keys)):
        base_values = copy.deepcopy(FIXED_KNOBS[mode])
        for key, value in zip(keys, combo):
            base_values[key] = value
        for bundle in bundles:
            values = copy.deepcopy(base_values)
            values.update(copy.deepcopy(bundle["values"]))
            out.append(
                Candidate(
                    mode=mode,
                    name=_candidate_name(mode, values, bundle["name"]),
                    bundle=str(bundle["name"]),
                    values=values,
                )
            )
    return out


def _build_candidate_config(
    base_config: Dict[str, Any],
    mode: str,
    candidate_values: Dict[str, Any],
) -> Dict[str, Any]:
    mode = _normalize_mode(mode)
    data = copy.deepcopy(base_config)
    data["mode"] = mode

    sections = _candidate_sections(mode, candidate_values)
    for key, value in sections["retrieval"].items():
        data = set_canonical_config_value(data, f"modes.{mode}.retrieval.{key}", value)
    for key, value in sections["query"].items():
        data = set_canonical_config_value(data, f"modes.{mode}.query.{key}", value)
    backend_section = "api" if mode == "online" else "ollama"
    for key, value in sections[backend_section].items():
        data = set_canonical_config_value(
            data,
            f"modes.{mode}.{backend_section}.{key}",
            value,
        )
    return data


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _command_log_text(cmd: List[str], result: subprocess.CompletedProcess[str]) -> str:
    return (
        "COMMAND\n"
        + " ".join(cmd)
        + "\n\nRETURN CODE\n"
        + str(result.returncode)
        + "\n\nSTDOUT\n"
        + (result.stdout or "")
        + "\n\nSTDERR\n"
        + (result.stderr or "")
    )


def _run_command(cmd: List[str], *, cwd: Path, log_path: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(_command_log_text(cmd, result), encoding="utf-8")
    return result


def _candidate_row_from_summary(
    *,
    mode: str,
    stage: str,
    candidate: Candidate,
    candidate_dir: Path,
    temp_config_rel: str,
    summary: Dict[str, Any],
    status: str,
    error: str = "",
) -> Dict[str, Any]:
    overall = summary.get("overall", {}) if isinstance(summary, dict) else {}
    gates = summary.get("acceptance_gates", {}) if isinstance(summary, dict) else {}
    row = {
        "mode": mode,
        "stage": stage,
        "candidate": candidate.name,
        "bundle": candidate.bundle,
        "status": status,
        "error": error,
        "count": int(overall.get("count", 0) or 0),
        "pass_rate": float(overall.get("pass_rate", 0.0) or 0.0),
        "avg_overall": float(overall.get("avg_overall", 0.0) or 0.0),
        "p50_latency_ms": int(overall.get("p50_latency_ms", 0) or 0),
        "p95_latency_ms": int(overall.get("p95_latency_ms", 0) or 0),
        "avg_cost_usd": float(overall.get("avg_cost_usd", 0.0) or 0.0),
        "unanswerable_accuracy_proxy": float(
            gates.get("unanswerable_accuracy_proxy", 0.0) or 0.0
        ),
        "injection_resistance_proxy": float(
            gates.get("injection_resistance_proxy", 0.0) or 0.0
        ),
        "summary_path": str(candidate_dir / "scored" / "summary.json"),
        "settings_path": str(candidate_dir / "effective_settings.json"),
        "candidate_dir": str(candidate_dir),
        "temp_config": temp_config_rel,
        "values": copy.deepcopy(candidate.values),
        "rank": 0,
        "gate_failed": False,
    }
    return row


def _read_summary_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _candidate_from_ranked_row(mode: str, row: Dict[str, Any]) -> Candidate:
    return Candidate(
        mode=mode,
        name=str(row["candidate"]),
        bundle=str(row.get("bundle", "") or ""),
        values=copy.deepcopy(row["values"]),
    )


def _dataset_count(dataset_path: Path) -> int:
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return len(data) if isinstance(data, list) else 0


def _database_ready(config_path: Path) -> tuple[bool, str]:
    cfg = _load_runtime_config(config_path)
    db_path = (getattr(getattr(cfg, "paths", None), "database", "") or "").strip()
    if not db_path:
        return False, "database path is empty in config"
    if not Path(db_path).exists():
        return (
            False,
            "indexed database not found: "
            + db_path
            + " (copy the indexed data first, or build the index on that machine)",
        )
    return True, ""


def _ollama_available(base_url: str) -> bool:
    import urllib.request

    url = (base_url or "http://127.0.0.1:11434").rstrip("/")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, method="GET")
        with opener.open(req, timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def _offline_ready(config_path: Path) -> tuple[bool, str]:
    db_ready, db_reason = _database_ready(config_path)
    if not db_ready:
        return False, db_reason
    cfg = _load_runtime_config(config_path)
    ollama_url = getattr(getattr(cfg, "ollama", None), "base_url", "http://127.0.0.1:11434")
    if not _ollama_available(ollama_url):
        return (
            False,
            "Ollama is not reachable at "
            + str(ollama_url)
            + " (start Ollama and make sure the offline model is available)",
        )
    return True, ""


def _online_ready(
    config_path: Path,
    *,
    config_dict: Dict[str, Any] | None = None,
) -> tuple[bool, str]:
    db_ready, db_reason = _database_ready(config_path)
    if not db_ready:
        return False, db_reason
    resolved_config = _credential_runtime_config_dict(
        config_path,
        config_dict=config_dict,
    )
    try:
        creds = resolve_credentials(config_dict=resolved_config, use_cache=False)
    except Exception as exc:
        return False, f"credential resolution failed: {exc}"
    if creds.is_online_ready:
        return True, ""
    if not creds.has_key and not creds.has_endpoint:
        return False, "missing API key and endpoint"
    if not creds.has_key:
        return False, "missing API key"
    if not creds.has_endpoint:
        return False, "missing API endpoint"
    return False, "credentials incomplete"


def _apply_candidate_to_mode_store(
    *,
    mode: str,
    values: Dict[str, Any],
    lock_winner: bool,
) -> Dict[str, Any]:
    store = ModeTuningStore(str(PROJECT_ROOT))
    cfg = load_config(str(PROJECT_ROOT), "config.yaml")
    applied = {}
    for key, value in values.items():
        store.update_value(cfg, mode, key, value)
        store.update_default(cfg, mode, key, value)
        store.set_lock(cfg, mode, key, bool(lock_winner))
        applied[key] = value
    return applied


def _winner_from_mode_rows(
    *,
    mode: str,
    rows: List[Dict[str, Any]],
    workflow: str,
) -> Dict[str, Any]:
    winner_set = build_winner_set(rows)
    mode_entry = winner_set.get("modes", {}).get(mode, {})
    ranked = mode_entry.get("ranked", [])
    if not ranked:
        return {
            "mode": mode,
            "status": "failed",
            "reason": "no ranked candidates",
            "apply_eligible": False,
        }
    winner = copy.deepcopy(ranked[0])
    winner["mode"] = mode
    winner["candidate_count"] = int(mode_entry.get("candidate_count", len(ranked)) or 0)
    winner["apply_eligible"] = bool(workflow == "full" and winner.get("stage") == "full")
    if workflow == "full" and winner.get("stage") != "full":
        winner["reason"] = "preferred screen fallback; no successful full-stage winner"
    return winner


def _apply_winners(
    *,
    winners: Dict[str, Dict[str, Any]],
    lock_winner: bool,
    run_dir: Path,
) -> Dict[str, Any]:
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    backup_path = run_dir / "config_backup.yaml"
    if config_path.exists():
        shutil.copyfile(config_path, backup_path)

    applied = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "lock_winner": bool(lock_winner),
        "modes": {},
        "skipped_modes": {},
    }
    applied_any = False
    for mode, winner in winners.items():
        if winner.get("status") != "ok":
            applied["skipped_modes"][mode] = winner.get("reason", "winner not available")
            continue
        if not bool(winner.get("apply_eligible", True)):
            applied["skipped_modes"][mode] = winner.get(
                "reason",
                "winner is not eligible to apply",
            )
            continue
        applied["modes"][mode] = {
            "candidate": winner["candidate"],
            "values": _apply_candidate_to_mode_store(
                mode=mode,
                values=winner["values"],
                lock_winner=lock_winner,
            ),
        }
        applied_any = True
    if not applied_any:
        raise SystemExit("No successful winners were available to apply")
    return applied


def _write_next_steps(path: Path, args: argparse.Namespace, winners: Dict[str, Any]) -> None:
    lines = [
        "HybridRAG3 autotune run complete.",
        "",
        f"Workflow: {args.workflow}",
        f"Mode: {args.mode}",
        f"Grid: {args.grid}",
        f"Screen limit: {args.screen_limit}",
        "",
        "Recommended next steps:",
        "1. Open leaderboard.csv, winner_set.json, bundle_summary.csv, winners.json, and the per-candidate effective_settings.json files in this run folder.",
    ]
    if args.workflow == "screen":
        lines.extend(
            [
                "2. Re-run the finalists on the full set when the screen results look good:",
                "   python tools/run_mode_autotune.py --workflow full --mode both",
                "3. Apply winners only after reviewing the full-run leaderboard:",
                "   python tools/run_mode_autotune.py --workflow full --mode both --apply-winner",
            ]
        )
    else:
        lines.extend(
            [
                "2. Review winners.json and the scored summaries for the finalists.",
                "3. If the winners look good, save them to config.yaml:",
                "   python tools/run_mode_autotune.py --workflow full --mode both --apply-winner",
            ]
        )
    if any(winner.get("status") != "ok" for winner in winners.values()):
        lines.extend(
            [
                "",
                "Warning: at least one mode had no successful winner. Check the candidate logs first.",
            ]
        )
    if args.workflow == "full" and any(
        winner.get("status") == "ok" and winner.get("stage") != "full"
        for winner in winners.values()
    ):
        lines.extend(
            [
                "",
                "Note: at least one mode fell back to a screen-stage winner.",
                "Those fallbacks are reviewable in winner_set.json but are not auto-applied by --apply-winner.",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_stage(
    *,
    mode: str,
    stage: str,
    candidates: List[Candidate],
    dataset_rel: str,
    limit: int,
    base_config: Dict[str, Any],
    run_dir: Path,
    config_tmp_root: Path,
    config_arg_prefix: str,
    min_unanswerable_proxy: float,
    min_injection_proxy: float,
) -> List[Dict[str, Any]]:
    stage_dir = run_dir / mode / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_rows: List[Dict[str, Any]] = []

    for index, candidate in enumerate(candidates, start=1):
        candidate_dir = stage_dir / candidate.name
        candidate_dir.mkdir(parents=True, exist_ok=True)
        rel_config_path = Path(config_arg_prefix) / mode / stage / f"{candidate.name}.yaml"
        temp_config_path = config_tmp_root / mode / stage / f"{candidate.name}.yaml"

        candidate_config = _build_candidate_config(base_config, mode, candidate.values)
        _write_yaml(temp_config_path, candidate_config)
        _write_json(candidate_dir / "candidate_config.json", candidate.values)
        _write_json(candidate_dir / "effective_settings.json", _candidate_snapshot(candidate))

        _print(
            f"[{mode} {stage}] {index}/{len(candidates)} {candidate.name} "
            f"(limit={limit if limit > 0 else 'all'})"
        )

        eval_outdir = candidate_dir / "eval"
        scored_outdir = candidate_dir / "scored"
        eval_cmd = [
            sys.executable,
            "tools/eval_runner.py",
            "--dataset",
            dataset_rel,
            "--outdir",
            str(eval_outdir),
            "--config",
            str(rel_config_path).replace("\\", "/"),
            "--mode",
            mode,
        ]
        if limit > 0:
            eval_cmd += ["--limit", str(limit)]
        eval_result = _run_command(
            eval_cmd,
            cwd=PROJECT_ROOT,
            log_path=candidate_dir / "eval_command.log",
        )
        if eval_result.returncode != 0:
            stage_rows.append(
                _candidate_row_from_summary(
                    mode=mode,
                    stage=stage,
                    candidate=candidate,
                    candidate_dir=candidate_dir,
                    temp_config_rel=str(rel_config_path).replace("\\", "/"),
                    summary={},
                    status="failed",
                    error=f"eval_runner failed ({eval_result.returncode})",
                )
            )
            continue

        score_cmd = [
            sys.executable,
            "tools/score_results.py",
            "--golden",
            dataset_rel,
            "--results",
            str(eval_outdir / "results.jsonl"),
            "--outdir",
            str(scored_outdir),
        ]
        score_result = _run_command(
            score_cmd,
            cwd=PROJECT_ROOT,
            log_path=candidate_dir / "score_command.log",
        )
        if score_result.returncode != 0:
            stage_rows.append(
                _candidate_row_from_summary(
                    mode=mode,
                    stage=stage,
                    candidate=candidate,
                    candidate_dir=candidate_dir,
                    temp_config_rel=str(rel_config_path).replace("\\", "/"),
                    summary={},
                    status="failed",
                    error=f"score_results failed ({score_result.returncode})",
                )
            )
            continue

        summary = _read_summary_json(scored_outdir / "summary.json")
        stage_rows.append(
            _candidate_row_from_summary(
                mode=mode,
                stage=stage,
                candidate=candidate,
                candidate_dir=candidate_dir,
                temp_config_rel=str(rel_config_path).replace("\\", "/"),
                summary=summary,
                status="ok",
            )
        )

    ranked = rank_rows(
        stage_rows,
        min_unanswerable_proxy=min_unanswerable_proxy,
        min_injection_proxy=min_injection_proxy,
    )
    bundle_summary = build_bundle_summary_rows(ranked)
    _write_json(stage_dir / "leaderboard.json", ranked)
    write_leaderboard_csv(stage_dir / "leaderboard.csv", ranked)
    _write_json(stage_dir / "bundle_summary.json", bundle_summary)
    write_bundle_summary_csv(stage_dir / "bundle_summary.csv", bundle_summary)
    return ranked


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["offline", "online", "both"],
        default="both",
        help="Which mode(s) to tune. Default: both",
    )
    ap.add_argument(
        "--workflow",
        choices=["screen", "full"],
        default="screen",
        help="screen = 50-question starter pass only; full = screen then finalists on the full dataset.",
    )
    ap.add_argument(
        "--grid",
        choices=sorted(GRID_PRESETS.keys()),
        default="starter",
        help="starter = small fast grid; wide = broader overnight grid.",
    )
    ap.add_argument(
        "--dataset",
        default="Eval/golden_tuning_400.json",
        help="Golden dataset JSON. Default: Eval/golden_tuning_400.json",
    )
    ap.add_argument(
        "--config",
        default="config/config.yaml",
        help="Base config YAML to copy and override for each candidate.",
    )
    ap.add_argument(
        "--outroot",
        default="logs/autotune_runs",
        help="Root folder for timestamped autotune outputs.",
    )
    ap.add_argument(
        "--screen-limit",
        type=int,
        default=50,
        help="Questions per candidate in the screening phase. Default: 50",
    )
    ap.add_argument(
        "--finalists",
        type=int,
        default=2,
        help="How many screen winners per mode advance to the full pass. Default: 2",
    )
    ap.add_argument(
        "--full-limit",
        type=int,
        default=0,
        help="Optional cap for the full finalist pass. 0 = use the whole dataset.",
    )
    ap.add_argument(
        "--apply-winner",
        action="store_true",
        help="Write the full-run winner into config/config.yaml.",
    )
    ap.add_argument(
        "--lock-winner",
        action="store_true",
        help="When applying, lock the tuned keys to the saved defaults.",
    )
    ap.add_argument(
        "--min-unanswerable-proxy",
        type=float,
        default=0.0,
        help="Optional acceptance gate for unanswerable_accuracy_proxy.",
    )
    ap.add_argument(
        "--min-injection-proxy",
        type=float,
        default=0.0,
        help="Optional acceptance gate for injection_resistance_proxy.",
    )
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    if args.screen_limit <= 0:
        raise SystemExit("--screen-limit must be > 0")
    if args.finalists <= 0:
        raise SystemExit("--finalists must be > 0")
    if args.apply_winner and args.workflow != "full":
        raise SystemExit("--apply-winner requires --workflow full")

    dataset_path = _resolve_existing_path(args.dataset)
    config_path = _resolve_existing_path(args.config, prefer_config_dir=True)
    dataset_rel = str(dataset_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    outroot = (PROJECT_ROOT / args.outroot).resolve()
    run_dir = outroot / _timestamp_slug()
    run_dir.mkdir(parents=True, exist_ok=True)

    config_tmp_root = PROJECT_ROOT / "config" / ".tmp_autotune" / run_dir.name
    config_tmp_root.mkdir(parents=True, exist_ok=True)
    config_arg_prefix = Path("config") / ".tmp_autotune" / run_dir.name

    base_config = _load_config_dict(config_path)

    dataset_total = _dataset_count(dataset_path)
    selected_modes = _selected_modes(args.mode)
    skipped_modes: Dict[str, str] = {}
    filtered_modes: List[str] = []
    for mode in selected_modes:
        if mode == "offline":
            ready, reason = _offline_ready(config_path)
        else:
            ready, reason = _online_ready(config_path, config_dict=base_config)
        if ready:
            filtered_modes.append(mode)
        else:
            skipped_modes[mode] = reason
    selected_modes = filtered_modes
    candidate_counts = {
        mode: len(build_candidates(mode, args.grid))
        for mode in selected_modes
    }

    manifest = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workflow": args.workflow,
        "grid": args.grid,
        "dataset": dataset_rel,
        "dataset_total_questions": dataset_total,
        "screen_limit": args.screen_limit,
        "full_limit": args.full_limit,
        "finalists": args.finalists,
        "config": str(config_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "git_head": _git_head(),
        "platform": platform.platform(),
        "python": sys.executable,
        "selected_modes": selected_modes,
        "candidate_counts": candidate_counts,
        "skipped_modes": skipped_modes,
        "apply_winner": bool(args.apply_winner),
        "lock_winner": bool(args.lock_winner),
    }
    _write_json(run_dir / "manifest.json", manifest)

    if not selected_modes:
        _print("[FAIL] No modes selected for execution.")
        if skipped_modes:
            for mode, reason in skipped_modes.items():
                _print(f"  skipped {mode}: {reason}")
        return 1

    all_rows: List[Dict[str, Any]] = []
    winners: Dict[str, Dict[str, Any]] = {}

    for mode in selected_modes:
        candidates = build_candidates(mode, args.grid)
        _print(
            f"[START] {mode}: {len(candidates)} candidates, "
            f"{args.screen_limit} questions each in the screening pass"
        )
        screen_rows = run_stage(
            mode=mode,
            stage="screen",
            candidates=candidates,
            dataset_rel=dataset_rel,
            limit=args.screen_limit,
            base_config=base_config,
            run_dir=run_dir,
            config_tmp_root=config_tmp_root,
            config_arg_prefix=str(config_arg_prefix).replace("\\", "/"),
            min_unanswerable_proxy=args.min_unanswerable_proxy,
            min_injection_proxy=args.min_injection_proxy,
        )
        all_rows.extend(screen_rows)

        successful_screen = [
            row for row in screen_rows if row["status"] == "ok" and not row["gate_failed"]
        ]
        if not successful_screen:
            successful_screen = [row for row in screen_rows if row["status"] == "ok"]

        if not successful_screen:
            winners[mode] = {
                "mode": mode,
                "status": "failed",
                "reason": "no successful screen candidates",
                "apply_eligible": False,
            }
            _print(f"[WARN] {mode}: no successful screen candidates")
            continue

        if args.workflow == "screen":
            winners[mode] = _winner_from_mode_rows(
                mode=mode,
                rows=screen_rows,
                workflow=args.workflow,
            )
            _print(
                f"[WINNER] {mode} {winners[mode]['stage']} -> {winners[mode]['candidate']} "
                f"(pass={winners[mode]['pass_rate']:.3f}, "
                f"avg={winners[mode]['avg_overall']:.3f})"
            )
            continue

        finalists = successful_screen[: args.finalists]
        finalist_candidates = [_candidate_from_ranked_row(mode, row) for row in finalists]
        full_rows = run_stage(
            mode=mode,
            stage="full",
            candidates=finalist_candidates,
            dataset_rel=dataset_rel,
            limit=args.full_limit,
            base_config=base_config,
            run_dir=run_dir,
            config_tmp_root=config_tmp_root,
            config_arg_prefix=str(config_arg_prefix).replace("\\", "/"),
            min_unanswerable_proxy=args.min_unanswerable_proxy,
            min_injection_proxy=args.min_injection_proxy,
        )
        all_rows.extend(full_rows)
        if any(row["status"] == "ok" for row in full_rows):
            winners[mode] = _winner_from_mode_rows(
                mode=mode,
                rows=screen_rows + full_rows,
                workflow=args.workflow,
            )
            stage_label = str(winners[mode].get("stage", "") or "unknown")
            if stage_label != "full":
                stage_label = f"{stage_label} fallback"
            _print(
                f"[WINNER] {mode} {stage_label} -> {winners[mode]['candidate']} "
                f"(pass={winners[mode]['pass_rate']:.3f}, "
                f"avg={winners[mode]['avg_overall']:.3f})"
            )
        else:
            winners[mode] = _winner_from_mode_rows(
                mode=mode,
                rows=screen_rows + full_rows,
                workflow=args.workflow,
            )
            if winners[mode].get("status") == "ok":
                _print(
                    f"[WINNER] {mode} screen fallback -> {winners[mode]['candidate']} "
                    f"(pass={winners[mode]['pass_rate']:.3f}, "
                    f"avg={winners[mode]['avg_overall']:.3f})"
                )
            else:
                winners[mode] = {
                    "mode": mode,
                    "status": "failed",
                    "reason": "no successful finalists",
                    "apply_eligible": False,
                }
                _print(f"[WARN] {mode}: no successful finalists")

    for mode, reason in skipped_modes.items():
        winners[mode] = {
            "mode": mode,
            "status": "skipped",
            "reason": reason,
            "apply_eligible": False,
        }

    ranked_all = rank_rows(
        all_rows,
        min_unanswerable_proxy=args.min_unanswerable_proxy,
        min_injection_proxy=args.min_injection_proxy,
    )
    bundle_summary = build_bundle_summary_rows(ranked_all)
    winner_set = build_winner_set(ranked_all)
    write_leaderboard_csv(run_dir / "leaderboard.csv", ranked_all)
    _write_json(run_dir / "leaderboard.json", ranked_all)
    _write_json(run_dir / "bundle_summary.json", bundle_summary)
    write_bundle_summary_csv(run_dir / "bundle_summary.csv", bundle_summary)
    _write_json(run_dir / "winner_set.json", winner_set)
    write_winner_set_csv(run_dir / "winner_set.csv", winner_set["rows"])
    _write_json(run_dir / "winners.json", winners)

    if args.apply_winner:
        applied = _apply_winners(
            winners=winners,
            lock_winner=args.lock_winner,
            run_dir=run_dir,
        )
        _write_json(run_dir / "applied_defaults.json", applied)
        _print("[APPLY] Winners saved to config/config.yaml")

    _write_next_steps(run_dir / "README_NEXT_STEPS.txt", args, winners)

    _print("")
    _print(f"Run folder: {run_dir}")
    _print(f"Leaderboard: {run_dir / 'leaderboard.csv'}")
    _print(f"Winner set: {run_dir / 'winner_set.json'}")
    _print(f"Winners: {run_dir / 'winners.json'}")
    if args.apply_winner:
        _print(f"Applied defaults: {run_dir / 'applied_defaults.json'}")
    if skipped_modes:
        for mode, reason in skipped_modes.items():
            _print(f"Skipped {mode}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
