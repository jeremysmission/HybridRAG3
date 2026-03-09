#!/usr/bin/env python
"""
Synchronize the mirrored per-mode overrides inside config/config.yaml.

Run this after you update the admin panel knobs or want to hard-reset both
offline and online sections to the tuned March 7 winners.

Examples:
  python tools/sync_mode_overrides.py --api-endpoint https://openrouter.example/v1/chat/completions --api-model gpt-4o-mini
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

DEFAULTS = {
    "tuned_date": "2026-03-07",
    "offline": {
        "retrieval": {
            "hybrid_search": True,
            "top_k": 4,
            "min_score": 0.10,
            "reranker_enabled": False,
            "reranker_top_n": 20,
        },
        "ollama": {
            "model": "phi4-mini",
            "context_window": 4096,
            "timeout_seconds": 180,
            "temperature": 0.05,
            "base_url": "http://127.0.0.1:11434",
            "num_predict": 384,
        },
        "query": {
            "grounding_bias": 8,
            "allow_open_knowledge": True,
        },
    },
    "online": {
        "retrieval": {
            "hybrid_search": True,
            "top_k": 6,
            "min_score": 0.08,
            "reranker_enabled": False,
            "reranker_top_n": 20,
        },
        "api": {
            "max_tokens": 1024,
            "context_window": 128000,
            "temperature": 0.05,
            "timeout_seconds": 180,
            "model": "",
            "deployment": "",
        },
        "query": {
            "grounding_bias": 7,
            "allow_open_knowledge": True,
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

    config_path = Path("config/config.yaml")
    overrides = load_yaml(config_path)

    overrides["mode_store_version"] = 2
    overrides["mode"] = overrides.get("mode", "offline")
    overrides.setdefault("embedding", {})
    overrides.setdefault("indexing", overrides.get("indexing", {}))

    online_api = overrides.get("api", {})
    if args.api_endpoint:
        online_api["endpoint"] = args.api_endpoint
    if args.api_model:
        online_api["model"] = args.api_model
    overrides["api"] = online_api
    modes = overrides.setdefault("modes", {})
    if not isinstance(modes, dict):
        modes = {}
        overrides["modes"] = modes

    for mode_name in ("offline", "online"):
        entry = modes.setdefault(mode_name, {})
        if not isinstance(entry, dict):
            entry = {}
            modes[mode_name] = entry
        for section_name, values in DEFAULTS[mode_name].items():
            section = entry.setdefault(section_name, {})
            if not isinstance(section, dict):
                section = {}
                entry[section_name] = section
            section.update(values)
        defaults = entry.setdefault("defaults", {})
        locks = entry.setdefault("locks", {})
        for section_name, values in DEFAULTS[mode_name].items():
            if section_name == "query":
                continue
            for key, value in values.items():
                defaults[key] = value
                locks.setdefault(key, False)
        for key, value in DEFAULTS[mode_name]["query"].items():
            defaults[key] = value
            locks.setdefault(key, False)

    if args.api_model:
        modes["online"]["api"]["model"] = args.api_model
        modes["online"]["api"]["deployment"] = args.api_model

    overrides["tuned_baseline"] = {
        "date": args.tune_date,
        "offline": "tk4_ms10_np384",
        "online": "tk6_ms08_mt1024",
    }

    save_yaml(config_path, overrides)
    print("Updated", config_path.resolve())
    print("Offline defaults point to", modes["offline"]["ollama"]["model"], "with", modes["offline"]["retrieval"])
    print("Online defaults point to", modes["online"]["api"].get("model", "<unset>"), "with", modes["online"]["retrieval"])


if __name__ == "__main__":
    main()
