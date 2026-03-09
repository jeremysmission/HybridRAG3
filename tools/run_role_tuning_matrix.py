#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the role tuning matrix operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Run eval+scoring per profession golden set.

Prereq:
  python tools/build_role_golden_sets.py --dataset Eval/golden_tuning_400.json

Usage:
  python tools/run_role_tuning_matrix.py --mode offline
  python tools/run_role_tuning_matrix.py --mode online
"""

import argparse
import json
import os
import subprocess
import sys


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="Eval/role_sets/manifest.json")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--mode", choices=["offline", "online"], default="offline")
    ap.add_argument("--outroot", default="eval_out/role_tuning")
    ap.add_argument("--roles", default="", help="Comma list of role keys from manifest")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    roles = manifest.get("roles", {})
    if not roles:
        raise SystemExit("No role sets found in manifest")

    selected = set()
    if args.roles.strip():
        selected = {r.strip() for r in args.roles.split(",") if r.strip()}

    rows = []
    for role_key in sorted(roles.keys()):
        if selected and role_key not in selected:
            continue
        dataset = roles[role_key]["path"]
        outdir = os.path.join(args.outroot, args.mode, role_key)
        scored = os.path.join(outdir, "scored")
        os.makedirs(scored, exist_ok=True)

        cmd_eval = [
            sys.executable, "tools/eval_runner.py",
            "--dataset", dataset,
            "--outdir", outdir,
            "--config", args.config,
            "--mode", args.mode,
        ]
        if args.limit > 0:
            cmd_eval += ["--limit", str(args.limit)]
        run(cmd_eval)

        results_jsonl = os.path.join(outdir, "results.jsonl")
        run([
            sys.executable, "tools/score_results.py",
            "--golden", dataset,
            "--results", results_jsonl,
            "--outdir", scored,
        ])

        summary_path = os.path.join(scored, "summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        overall = summary.get("overall", {})
        rows.append({
            "role": role_key,
            "count": int(overall.get("count", 0)),
            "avg_overall": float(overall.get("avg_overall", 0.0)),
            "pass_rate": float(overall.get("pass_rate", 0.0)),
            "p95_latency_ms": int(overall.get("p95_latency_ms", 0)),
            "avg_cost_usd": float(overall.get("avg_cost_usd", 0.0)),
            "summary": summary_path,
        })

    matrix_path = os.path.join(args.outroot, args.mode, "matrix_summary.json")
    os.makedirs(os.path.dirname(matrix_path), exist_ok=True)
    out = {"mode": args.mode, "rows": rows}
    with open(matrix_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("\nRole tuning matrix:")
    for r in rows:
        print(
            f"  {r['role']}: pass={r['pass_rate']:.3f} "
            f"avg={r['avg_overall']:.3f} p95={r['p95_latency_ms']}ms"
        )
    print("Saved:", matrix_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

