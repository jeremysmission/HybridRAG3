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
3. Stop without changing config or mode_tuning.yaml

When you are happy with the screening results:
4. Re-run with --workflow full to promote the top finalists onto the full dataset
5. Re-run with --apply-winner to save the winning bundle into config/mode_tuning.yaml

Quick start:
  python tools/run_mode_autotune.py
  python tools/run_mode_autotune.py --mode offline --workflow full
  python tools/run_mode_autotune.py --mode both --workflow full --apply-winner
"""

from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_config
from src.gui.helpers.mode_tuning import ModeTuningStore
from src.security.credentials import resolve_credentials

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

FIXED_KNOBS = {
    "offline": {
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 4096,
        "temperature": 0.05,
        "timeout_seconds": 180,
    },
    "online": {
        "hybrid_search": True,
        "reranker_enabled": False,
        "reranker_top_n": 20,
        "context_window": 128000,
        "temperature": 0.05,
        "timeout_seconds": 180,
    },
}


@dataclass
class Candidate:
    mode: str
    name: str
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


def _load_runtime_config(config_path: Path):
    return load_config(str(PROJECT_ROOT), _config_filename_from_path(config_path))


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


def _candidate_name(mode: str, values: Dict[str, Any]) -> str:
    min_score = int(round(float(values["min_score"]) * 100))
    if mode == "offline":
        return (
            f"tk{int(values['top_k'])}_"
            f"ms{min_score:02d}_"
            f"np{int(values['num_predict'])}"
        )
    return (
        f"tk{int(values['top_k'])}_"
        f"ms{min_score:02d}_"
        f"mt{int(values['max_tokens'])}"
    )


def build_candidates(mode: str, grid_name: str) -> List[Candidate]:
    mode = _normalize_mode(mode)
    preset = GRID_PRESETS[grid_name][mode]
    keys = list(preset.keys())
    out: List[Candidate] = []
    for combo in itertools.product(*(preset[key] for key in keys)):
        values = copy.deepcopy(FIXED_KNOBS[mode])
        for key, value in zip(keys, combo):
            values[key] = value
        out.append(Candidate(mode=mode, name=_candidate_name(mode, values), values=values))
    return out


def _build_candidate_config(
    base_config: Dict[str, Any],
    mode: str,
    candidate_values: Dict[str, Any],
) -> Dict[str, Any]:
    data = copy.deepcopy(base_config)
    data["mode"] = mode

    retrieval = data.setdefault("retrieval", {})
    retrieval["top_k"] = int(candidate_values["top_k"])
    retrieval["min_score"] = float(candidate_values["min_score"])
    retrieval["hybrid_search"] = bool(candidate_values["hybrid_search"])
    retrieval["reranker_enabled"] = bool(candidate_values["reranker_enabled"])
    retrieval["reranker_top_n"] = int(candidate_values["reranker_top_n"])

    if mode == "online":
        api = data.setdefault("api", {})
        api["context_window"] = int(candidate_values["context_window"])
        api["max_tokens"] = int(candidate_values["max_tokens"])
        api["temperature"] = float(candidate_values["temperature"])
        api["timeout_seconds"] = int(candidate_values["timeout_seconds"])
    else:
        ollama = data.setdefault("ollama", {})
        ollama["context_window"] = int(candidate_values["context_window"])
        ollama["num_predict"] = int(candidate_values["num_predict"])
        ollama["temperature"] = float(candidate_values["temperature"])
        ollama["timeout_seconds"] = int(candidate_values["timeout_seconds"])

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
        "candidate_dir": str(candidate_dir),
        "temp_config": temp_config_rel,
        "values": copy.deepcopy(candidate.values),
        "rank": 0,
        "gate_failed": False,
    }
    return row


def _sort_key(row: Dict[str, Any]) -> tuple:
    failed = 1 if row.get("status") != "ok" else 0
    gate_failed = 1 if row.get("gate_failed") else 0
    return (
        failed,
        gate_failed,
        -float(row.get("pass_rate", 0.0) or 0.0),
        -float(row.get("avg_overall", 0.0) or 0.0),
        int(row.get("p95_latency_ms", 0) or 0),
        float(row.get("avg_cost_usd", 0.0) or 0.0),
        str(row.get("candidate", "")),
    )


def rank_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    min_unanswerable_proxy: float,
    min_injection_proxy: float,
) -> List[Dict[str, Any]]:
    ranked = []
    for row in rows:
        clone = dict(row)
        clone["gate_failed"] = (
            clone.get("status") == "ok"
            and (
                float(clone.get("unanswerable_accuracy_proxy", 0.0) or 0.0)
                < float(min_unanswerable_proxy)
                or float(clone.get("injection_resistance_proxy", 0.0) or 0.0)
                < float(min_injection_proxy)
            )
        )
        ranked.append(clone)
    ranked.sort(key=_sort_key)
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
    return ranked


def _read_summary_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _leaderboard_fieldnames() -> List[str]:
    return [
        "mode",
        "stage",
        "rank",
        "candidate",
        "status",
        "gate_failed",
        "count",
        "pass_rate",
        "avg_overall",
        "p50_latency_ms",
        "p95_latency_ms",
        "avg_cost_usd",
        "unanswerable_accuracy_proxy",
        "injection_resistance_proxy",
        "temp_config",
        "summary_path",
        "candidate_dir",
        "error",
    ]


def _write_leaderboard_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    fieldnames = _leaderboard_fieldnames()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


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


def _online_ready(config_path: Path) -> tuple[bool, str]:
    db_ready, db_reason = _database_ready(config_path)
    if not db_ready:
        return False, db_reason
    try:
        creds = resolve_credentials(use_cache=False)
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
    cfg = load_config(str(PROJECT_ROOT), "default_config.yaml")
    applied = {}
    for key, value in values.items():
        store.update_value(cfg, mode, key, value)
        store.update_default(cfg, mode, key, value)
        store.set_lock(cfg, mode, key, bool(lock_winner))
        applied[key] = value
    return applied


def _apply_winners(
    *,
    winners: Dict[str, Dict[str, Any]],
    lock_winner: bool,
    run_dir: Path,
) -> Dict[str, Any]:
    mode_tuning_path = PROJECT_ROOT / "config" / "mode_tuning.yaml"
    backup_path = run_dir / "mode_tuning_backup.yaml"
    if mode_tuning_path.exists():
        shutil.copyfile(mode_tuning_path, backup_path)

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
        "1. Open leaderboard.csv and winners.json in this run folder.",
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
                "3. If the winners look good, save them to mode_tuning.yaml:",
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
    _write_json(stage_dir / "leaderboard.json", ranked)
    _write_leaderboard_csv(stage_dir / "leaderboard.csv", ranked)
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
        default="config/default_config.yaml",
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
        help="Write the full-run winner into config/mode_tuning.yaml.",
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

    with open(config_path, "r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f) or {}

    dataset_total = _dataset_count(dataset_path)
    selected_modes = _selected_modes(args.mode)
    skipped_modes: Dict[str, str] = {}
    filtered_modes: List[str] = []
    for mode in selected_modes:
        if mode == "offline":
            ready, reason = _offline_ready(config_path)
        else:
            ready, reason = _online_ready(config_path)
        if ready:
            filtered_modes.append(mode)
        else:
            skipped_modes[mode] = reason
    selected_modes = filtered_modes

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
            }
            _print(f"[WARN] {mode}: no successful screen candidates")
            continue

        if args.workflow == "screen":
            winners[mode] = dict(successful_screen[0])
            _print(
                f"[WINNER] {mode} screen -> {successful_screen[0]['candidate']} "
                f"(pass={successful_screen[0]['pass_rate']:.3f}, "
                f"avg={successful_screen[0]['avg_overall']:.3f})"
            )
            continue

        finalists = successful_screen[: args.finalists]
        finalist_candidates = [
            Candidate(mode=mode, name=row["candidate"], values=row["values"])
            for row in finalists
        ]
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
        successful_full = [
            row for row in full_rows if row["status"] == "ok" and not row["gate_failed"]
        ]
        if not successful_full:
            successful_full = [row for row in full_rows if row["status"] == "ok"]
        if successful_full:
            winners[mode] = dict(successful_full[0])
            _print(
                f"[WINNER] {mode} full -> {successful_full[0]['candidate']} "
                f"(pass={successful_full[0]['pass_rate']:.3f}, "
                f"avg={successful_full[0]['avg_overall']:.3f})"
            )
        else:
            winners[mode] = {
                "mode": mode,
                "status": "failed",
                "reason": "no successful finalists",
            }
            _print(f"[WARN] {mode}: no successful finalists")

    for mode, reason in skipped_modes.items():
        winners[mode] = {
            "mode": mode,
            "status": "skipped",
            "reason": reason,
        }

    ranked_all = rank_rows(
        all_rows,
        min_unanswerable_proxy=args.min_unanswerable_proxy,
        min_injection_proxy=args.min_injection_proxy,
    )
    _write_leaderboard_csv(run_dir / "leaderboard.csv", ranked_all)
    _write_json(run_dir / "leaderboard.json", ranked_all)
    _write_json(run_dir / "winners.json", winners)

    if args.apply_winner:
        applied = _apply_winners(
            winners=winners,
            lock_winner=args.lock_winner,
            run_dir=run_dir,
        )
        _write_json(run_dir / "applied_defaults.json", applied)
        _print("[APPLY] Winners saved to config/mode_tuning.yaml")

    _write_next_steps(run_dir / "README_NEXT_STEPS.txt", args, winners)

    _print("")
    _print(f"Run folder: {run_dir}")
    _print(f"Leaderboard: {run_dir / 'leaderboard.csv'}")
    _print(f"Winners: {run_dir / 'winners.json'}")
    if args.apply_winner:
        _print(f"Applied defaults: {run_dir / 'applied_defaults.json'}")
    if skipped_modes:
        for mode, reason in skipped_modes.items():
            _print(f"Skipped {mode}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
