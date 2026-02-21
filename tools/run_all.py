#!/usr/bin/env python3
"""
One-command convenience wrapper.

Runs:
1) tuning set evaluation + scoring
2) hidden set evaluation + scoring

Usage:
  python tools/run_all.py --config config/default_config.yaml

Outputs:
  eval_out/tuning/*
  eval_out/hidden/*
"""
import argparse, os, subprocess, sys

def run(cmd):
    print(">>>", " ".join(cmd))
    subprocess.check_call(cmd)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="Config path/filename")
    ap.add_argument("--mode", default=None, help="Optional: online/offline")
    args = ap.parse_args()

    os.makedirs("eval_out/tuning", exist_ok=True)
    os.makedirs("eval_out/hidden", exist_ok=True)
    os.makedirs("scored_out/tuning", exist_ok=True)
    os.makedirs("scored_out/hidden", exist_ok=True)

    run([sys.executable, "tools/eval_runner.py", "--dataset", "datasets/golden_tuning_400.json", "--outdir", "eval_out/tuning", "--config", args.config] + (["--mode", args.mode] if args.mode else []))
    run([sys.executable, "tools/score_results.py", "--golden", "datasets/golden_tuning_400.json", "--results", "eval_out/tuning/results.jsonl", "--outdir", "scored_out/tuning"])

    run([sys.executable, "tools/eval_runner.py", "--dataset", "datasets/golden_hidden_validation_100.json", "--outdir", "eval_out/hidden", "--config", args.config] + (["--mode", args.mode] if args.mode else []))
    run([sys.executable, "tools/score_results.py", "--golden", "datasets/golden_hidden_validation_100.json", "--results", "eval_out/hidden/results.jsonl", "--outdir", "scored_out/hidden"])

    print("\nDONE. See scored_out/*/summary.json\n")

if __name__ == "__main__":
    main()
