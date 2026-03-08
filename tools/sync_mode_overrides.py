#!/usr/bin/env python
"""
Synchronize the single mode config overrides for both offline and online.

Run this after you update the admin panel knobs or want to hard-reset both
sections to the tuned March 7 winners.

Examples:
  python tools/sync_mode_overrides.py --api-endpoint https://openrouter.example/v1/chat/completions --api-model gpt-4o-mini

By default it preserves whatever endpoint/key you already configured and only
overwrites the other tuned fields (top_k, min_score, num_predict/max_tokens,
colorspace of timeouts, etc.).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

DEFAULTS = {
    "tuned_date": "2026-03-07",
    "offline": {
        "ollama": {
            "model": "phi4:14b-q4_K_M",
            "context_window": 4096,
            "timeout_seconds": 180,
            "temperature": 0.05,
            "base_url": "http://localhost:11434",
            "num_predict": 384,
        },
        "retrieval": {
            "hybrid_search": True,
            "top_k": 4,
            "min_score": 0.10,
        },
    },
    "online": {
        "api": {
            "max_tokens": 1024,
            "temperature": 0.05,
            "timeout_seconds": 180,
        },
        "retrieval": {
            "hybrid_search": True,
            "top_k": 6,
            "min_score": 0.08,
        },
    },
}


def load_yaml(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}
    return {}


def save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        yaml.dump(data, stream, default_flow_style=False, sort_keys=False)
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-endpoint", help="Explicit online API endpoint")
    parser.add_argument("--api-model", help="Model name for online mode")
    parser.add_argument("--tune-date", default=DEFAULTS["tuned_date"])
    args = parser.parse_args()

    overrides_path = Path("config/user_overrides.yaml")
    overrides = load_yaml(overrides_path)

    overrides["mode"] = overrides.get("mode", "offline")
    overrides.setdefault("embedding", {})
    overrides.setdefault("indexing", overrides.get("indexing", {}))

    offline = overrides.get("ollama", {})
    offline.update(DEFAULTS["offline"]["ollama"])
    overrides["ollama"] = offline
    overrides.setdefault("retrieval", {}).update(DEFAULTS["offline"]["retrieval"])

    online_api = overrides.get("api", {})
    online_api.update(DEFAULTS["online"]["api"])
    if args.api_endpoint:
        online_api["endpoint"] = args.api_endpoint
    if args.api_model:
        online_api["model"] = args.api_model
    overrides["api"] = online_api

    online_retrieval = overrides.setdefault("retrieval_online", {})
    online_retrieval.update(DEFAULTS["online"]["retrieval"])

    overrides["tuned_baseline"] = {
        "date": args.tune_date,
        "offline": "tk4_ms10_np384",
        "online": "tk6_ms08_mt1024",
    }

    save_yaml(overrides_path, overrides)
    print("Updated", overrides_path.resolve())
    print("Offline defaults point to", overrides["ollama"]["model"], "with", overrides["retrieval"])
    print("Online defaults point to", online_api.get("model", "<unset>"), "with", online_retrieval)


if __name__ == "__main__":
    main()
