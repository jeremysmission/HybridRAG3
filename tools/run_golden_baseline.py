#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the golden baseline operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Run the Golden Baseline evaluation pack end-to-end.

What this does
- Runs eval_runner.py on Eval/golden_baseline/golden_baseline_24.json
- Runs score_results.py on produced results.jsonl
- Prints final summary location

Usage
  python tools/run_golden_baseline.py --mode offline
  python tools/run_golden_baseline.py --mode online --config config/config.yaml
"""

import argparse
import json
import os
import subprocess
import sys


def run(cmd):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="offline", choices=["offline", "online"])
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument(
        "--dataset",
        default="Eval/golden_baseline/golden_baseline_24.json",
    )
    ap.add_argument("--outroot", default="eval_out/golden_baseline")
    args = ap.parse_args()

    outdir = os.path.join(args.outroot, args.mode)
    scored = os.path.join(outdir, "scored")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(scored, exist_ok=True)

    run(
        [
            sys.executable,
            "tools/eval_runner.py",
            "--dataset",
            args.dataset,
            "--outdir",
            outdir,
            "--config",
            args.config,
            "--mode",
            args.mode,
        ]
    )

    results_jsonl = os.path.join(outdir, "results.jsonl")
    run(
        [
            sys.executable,
            "tools/score_results.py",
            "--golden",
            args.dataset,
            "--results",
            results_jsonl,
            "--outdir",
            scored,
        ]
    )

    summary_path = os.path.join(scored, "summary.json")
    print("\nGolden baseline complete.")
    print("Summary:", summary_path)
    if os.path.isfile(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        print(json.dumps(summary.get("overall", {}), indent=2))


if __name__ == "__main__":
    main()
