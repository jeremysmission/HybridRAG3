from __future__ import annotations

import copy
import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List


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


def leaderboard_fieldnames() -> List[str]:
    return [
        "mode",
        "stage",
        "rank",
        "candidate",
        "bundle",
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
        "settings_path",
        "candidate_dir",
        "error",
    ]


def write_leaderboard_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    fieldnames = leaderboard_fieldnames()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _best_row(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    ranked = sorted((dict(row) for row in rows), key=_sort_key)
    return ranked[0] if ranked else None


def build_bundle_summary_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        mode = str(row.get("mode", "") or "")
        stage = str(row.get("stage", "") or "")
        bundle = str(row.get("bundle", "") or "")
        key = (mode, stage, bundle)
        entry = grouped.setdefault(
            key,
            {
                "mode": mode,
                "stage": stage,
                "bundle": bundle,
                "candidate_count": 0,
                "ok_count": 0,
                "gate_pass_count": 0,
                "avg_pass_rate": 0.0,
                "avg_overall": 0.0,
                "best_candidate": "",
                "best_rank": 0,
                "best_pass_rate": 0.0,
                "best_avg_overall": 0.0,
                "best_p95_latency_ms": 0,
                "best_avg_cost_usd": 0.0,
                "_pass_rate_total": 0.0,
                "_overall_total": 0.0,
                "_rows": [],
            },
        )
        entry["candidate_count"] += 1
        entry["_rows"].append(dict(row))
        if row.get("status") == "ok":
            entry["ok_count"] += 1
            entry["_pass_rate_total"] += float(row.get("pass_rate", 0.0) or 0.0)
            entry["_overall_total"] += float(row.get("avg_overall", 0.0) or 0.0)
            if not row.get("gate_failed"):
                entry["gate_pass_count"] += 1

    rows_out: List[Dict[str, Any]] = []
    for entry in grouped.values():
        ok_count = int(entry["ok_count"] or 0)
        if ok_count > 0:
            entry["avg_pass_rate"] = entry["_pass_rate_total"] / ok_count
            entry["avg_overall"] = entry["_overall_total"] / ok_count
        best = _best_row(entry["_rows"])
        if best is not None:
            entry["best_candidate"] = str(best.get("candidate", "") or "")
            entry["best_rank"] = int(best.get("rank", 0) or 0)
            entry["best_pass_rate"] = float(best.get("pass_rate", 0.0) or 0.0)
            entry["best_avg_overall"] = float(best.get("avg_overall", 0.0) or 0.0)
            entry["best_p95_latency_ms"] = int(best.get("p95_latency_ms", 0) or 0)
            entry["best_avg_cost_usd"] = float(best.get("avg_cost_usd", 0.0) or 0.0)
        del entry["_pass_rate_total"]
        del entry["_overall_total"]
        del entry["_rows"]
        rows_out.append(entry)

    rows_out.sort(
        key=lambda row: (
            str(row.get("mode", "")),
            str(row.get("stage", "")),
            int(row.get("best_rank", 0) or 0),
            str(row.get("bundle", "")),
        )
    )
    return rows_out


def bundle_summary_fieldnames() -> List[str]:
    return [
        "mode",
        "stage",
        "bundle",
        "candidate_count",
        "ok_count",
        "gate_pass_count",
        "avg_pass_rate",
        "avg_overall",
        "best_candidate",
        "best_rank",
        "best_pass_rate",
        "best_avg_overall",
        "best_p95_latency_ms",
        "best_avg_cost_usd",
    ]


def write_bundle_summary_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    fieldnames = bundle_summary_fieldnames()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _stage_quality(stage_rows: List[Dict[str, Any]]) -> tuple[int, tuple]:
    if not stage_rows:
        return (3, (1, 1, "", 0, 0.0))
    has_gate_pass = any(
        row.get("status") == "ok" and not row.get("gate_failed") for row in stage_rows
    )
    if has_gate_pass:
        tier = 0
    elif any(row.get("status") == "ok" for row in stage_rows):
        tier = 1
    else:
        tier = 2
    best = _best_row(stage_rows)
    if best is None:
        return (3, (1, 1, "", 0, 0.0))
    return (tier, _sort_key(best))


def _preferred_stage(mode_rows: List[Dict[str, Any]]) -> str:
    stage_rows: Dict[str, List[Dict[str, Any]]] = {}
    for row in mode_rows:
        stage = str(row.get("stage", "") or "")
        if stage:
            stage_rows.setdefault(stage, []).append(dict(row))
    if not stage_rows:
        return ""
    ordered = sorted(
        stage_rows.items(),
        key=lambda item: (
            _stage_quality(item[1]),
            0 if item[0] == "full" else 1 if item[0] == "screen" else 2,
            item[0],
        ),
    )
    return ordered[0][0]


def _winner_set_row(row: Dict[str, Any], *, mode_rank: int) -> Dict[str, Any]:
    compact = {
        "mode": str(row.get("mode", "") or ""),
        "stage": str(row.get("stage", "") or ""),
        "mode_rank": int(mode_rank),
        "candidate": str(row.get("candidate", "") or ""),
        "bundle": str(row.get("bundle", "") or ""),
        "status": str(row.get("status", "") or ""),
        "gate_failed": bool(row.get("gate_failed", False)),
        "pass_rate": float(row.get("pass_rate", 0.0) or 0.0),
        "avg_overall": float(row.get("avg_overall", 0.0) or 0.0),
        "p95_latency_ms": int(row.get("p95_latency_ms", 0) or 0),
        "avg_cost_usd": float(row.get("avg_cost_usd", 0.0) or 0.0),
        "unanswerable_accuracy_proxy": float(
            row.get("unanswerable_accuracy_proxy", 0.0) or 0.0
        ),
        "injection_resistance_proxy": float(
            row.get("injection_resistance_proxy", 0.0) or 0.0
        ),
        "summary_path": str(row.get("summary_path", "") or ""),
        "settings_path": str(row.get("settings_path", "") or ""),
        "error": str(row.get("error", "") or ""),
        "values": copy.deepcopy(row.get("values", {})),
    }
    return compact


def build_winner_set(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        mode = str(row.get("mode", "") or "")
        if mode:
            grouped.setdefault(mode, []).append(dict(row))

    modes: Dict[str, Dict[str, Any]] = {}
    flat_rows: List[Dict[str, Any]] = []
    for mode in sorted(grouped.keys()):
        mode_rows = grouped[mode]
        stage = _preferred_stage(mode_rows)
        preferred_rows = [row for row in mode_rows if str(row.get("stage", "") or "") == stage]
        ranked_rows = sorted(preferred_rows, key=_sort_key)
        compact_rows = []
        for idx, row in enumerate(ranked_rows, start=1):
            compact = _winner_set_row(row, mode_rank=idx)
            compact_rows.append(compact)
            flat_rows.append({key: value for key, value in compact.items() if key != "values"})
        modes[mode] = {
            "mode": mode,
            "stage": stage,
            "candidate_count": len(compact_rows),
            "ranked": compact_rows,
        }
    return {"modes": modes, "rows": flat_rows}


def winner_set_fieldnames() -> List[str]:
    return [
        "mode",
        "stage",
        "mode_rank",
        "candidate",
        "bundle",
        "status",
        "gate_failed",
        "pass_rate",
        "avg_overall",
        "p95_latency_ms",
        "avg_cost_usd",
        "unanswerable_accuracy_proxy",
        "injection_resistance_proxy",
        "summary_path",
        "settings_path",
        "error",
    ]


def write_winner_set_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    fieldnames = winner_set_fieldnames()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
