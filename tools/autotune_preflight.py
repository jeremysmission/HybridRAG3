#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Read-only readiness check before running the autotune batch files.
# What to read first: Start at main(), then read the helper functions it calls.
# Inputs: Config path, eval dataset path, and the current local index/runtime state.
# Outputs: Plain-English console status lines and a process exit code.
# Safety notes: This script does not modify config, mode defaults, source data, or the index.
# ============================
"""
HybridRAG3 Autotune Preflight Checker

Quick start:
  python tools/autotune_preflight.py
  python tools/autotune_preflight.py --mode both
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.index_qc import detect_index_contamination
from src.security.credentials import resolve_credentials
from tools.run_mode_autotune import (
    _load_runtime_config,
    _offline_ready,
    _online_ready,
    _resolve_existing_path,
)


def _print_status(level: str, message: str) -> None:
    print(f"[{level}] {message}", flush=True)


def _selected_modes(mode: str) -> list[str]:
    raw = str(mode).strip().lower()
    if raw == "both":
        return ["offline", "online"]
    if raw == "online":
        return ["online"]
    return ["offline"]


def _expected_source_names(dataset_path: Path) -> set[str]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    names: set[str] = set()
    if not isinstance(data, list):
        return names
    for item in data:
        if not isinstance(item, dict):
            continue
        for raw in item.get("expected_sources", []) or []:
            name = Path(str(raw).strip()).name.strip().lower()
            if name:
                names.add(name)
    return names


def _preview_names(names: Iterable[str], *, limit: int = 6) -> str:
    ordered = sorted({str(name) for name in names if str(name).strip()})
    if not ordered:
        return "(none)"
    if len(ordered) <= limit:
        return ", ".join(ordered)
    shown = ", ".join(ordered[:limit])
    return f"{shown}, ... (+{len(ordered) - limit} more)"


def _index_stats(db_path: Path) -> dict:
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception as exc:
        return {"ok": False, "reason": f"could not open SQLite database: {exc}"}
    try:
        chunk_count = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] or 0)
        source_count = int(
            conn.execute("SELECT COUNT(DISTINCT source_path) FROM chunks").fetchone()[0] or 0
        )
        rows = conn.execute("SELECT DISTINCT source_path FROM chunks").fetchall()
    except Exception as exc:
        return {"ok": False, "reason": f"database query failed: {exc}"}
    finally:
        conn.close()
    basenames = {
        Path(str(row[0])).name.strip().lower()
        for row in rows
        if row and len(row) > 0 and str(row[0]).strip()
    }
    return {
        "ok": True,
        "chunk_count": chunk_count,
        "source_count": source_count,
        "basenames": basenames,
    }


def _corpus_alignment(expected_sources: set[str], indexed_sources: set[str]) -> dict:
    if not expected_sources:
        return {
            "level": "WARN",
            "summary": "dataset does not declare expected source file names",
            "matched": [],
            "missing": [],
            "coverage_pct": 0,
        }
    matched = sorted(expected_sources & indexed_sources)
    missing = sorted(expected_sources - indexed_sources)
    coverage_pct = int(round((len(matched) / len(expected_sources)) * 100))
    if not matched:
        level = "FAIL"
        summary = "index does not appear to contain the eval corpus"
    elif not missing:
        level = "PASS"
        summary = "current index appears aligned with the eval corpus"
    else:
        level = "WARN"
        summary = "current index only partially matches the eval corpus"
    return {
        "level": level,
        "summary": summary,
        "matched": matched,
        "missing": missing,
        "coverage_pct": coverage_pct,
    }


def _ollama_model_tags(base_url: str) -> set[str] | None:
    url = (base_url or "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, method="GET")
        with opener.open(req, timeout=5) as response:
            payload = json.load(response)
    except Exception:
        return None
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return {
        str(item.get("name", "")).strip().lower()
        for item in models
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }


def _ollama_model_present(target_model: str, available: set[str]) -> bool:
    target = str(target_model).strip().lower()
    if not target:
        return False
    if target in available:
        return True
    stem = target.split(":", 1)[0]
    return any(name == stem or name.startswith(target + ":") or name.startswith(stem + ":") for name in available)


def _run_preflight(*, dataset_path: Path, config_path: Path, mode: str) -> int:
    cfg = _load_runtime_config(config_path)
    dataset_sources = _expected_source_names(dataset_path)
    source_folder = Path((getattr(getattr(cfg, "paths", None), "source_folder", "") or "").strip())
    db_path = Path((getattr(getattr(cfg, "paths", None), "database", "") or "").strip())

    failures = 0

    print("HybridRAG Autotune Preflight", flush=True)
    print(f"Dataset: {dataset_path}", flush=True)
    print(f"Config:  {config_path}", flush=True)
    print(f"Modes:   {', '.join(_selected_modes(mode))}", flush=True)
    print("", flush=True)

    _print_status("PASS", f"dataset found: {dataset_path}")
    if dataset_sources:
        _print_status(
            "PASS",
            f"dataset references {len(dataset_sources)} expected source files",
        )
    else:
        _print_status("WARN", "dataset does not list any expected source files")

    if source_folder:
        if source_folder.exists():
            _print_status("PASS", f"configured source folder exists: {source_folder}")
        else:
            _print_status(
                "WARN",
                "configured source folder does not exist: "
                + str(source_folder)
                + " (okay if you are tuning against an already-built index)",
            )
    else:
        _print_status("WARN", "source folder path is empty in config")

    if not db_path:
        _print_status("FAIL", "database path is empty in config")
        return 1

    if not db_path.exists():
        _print_status(
            "FAIL",
            "indexed database not found: "
            + str(db_path)
            + " (copy the indexed data first or run rag-index)",
        )
        return 1

    _print_status("PASS", f"indexed database found: {db_path}")
    stats = _index_stats(db_path)
    if not stats["ok"]:
        _print_status("FAIL", stats["reason"])
        return 1

    chunk_count = int(stats["chunk_count"])
    source_count = int(stats["source_count"])
    if chunk_count <= 0 or source_count <= 0:
        _print_status("FAIL", "index is present but empty")
        return 1

    _print_status(
        "PASS",
        f"index contains {chunk_count} chunks across {source_count} source files",
    )

    alignment = _corpus_alignment(dataset_sources, stats["basenames"])
    _print_status(
        alignment["level"],
        alignment["summary"]
        + f" ({alignment['coverage_pct']}% expected-source coverage)",
    )
    if alignment["matched"]:
        _print_status("INFO", "matched sources: " + _preview_names(alignment["matched"]))
    if alignment["missing"]:
        _print_status("INFO", "missing sources: " + _preview_names(alignment["missing"]))
    if alignment["level"] == "FAIL":
        failures += 1

    contamination = detect_index_contamination(
        db_path,
        source_root=str(source_folder) if source_folder else "",
    )
    _print_status(contamination["level"], contamination["summary"])
    if contamination["suspicious_count"]:
        preview = ", ".join(
            f"{Path(item['source_path']).name} [{'|'.join(item['flags'])}]"
            for item in contamination["suspicious_sources"][:5]
        )
        _print_status("INFO", "suspicious source examples: " + preview)
    if contamination["level"] == "FAIL":
        failures += 1

    for selected_mode in _selected_modes(mode):
        if selected_mode == "offline":
            ready, reason = _offline_ready(config_path)
            if ready:
                _print_status("PASS", "offline runtime looks ready")
                ollama_url = getattr(getattr(cfg, "ollama", None), "base_url", "http://127.0.0.1:11434")
                ollama_model = getattr(getattr(cfg, "ollama", None), "model", "")
                available = _ollama_model_tags(ollama_url)
                if available is None:
                    _print_status(
                        "WARN",
                        "could not list Ollama models, but Ollama is reachable",
                    )
                elif _ollama_model_present(ollama_model, available):
                    _print_status(
                        "PASS",
                        f"configured offline model is present: {ollama_model}",
                    )
                else:
                    _print_status(
                        "FAIL",
                        "configured offline model is not listed by Ollama: " + str(ollama_model),
                    )
                    failures += 1
            else:
                _print_status("FAIL", "offline runtime not ready: " + reason)
                failures += 1
            continue

        ready, reason = _online_ready(config_path)
        creds = resolve_credentials(use_cache=False)
        if ready:
            _print_status("PASS", "online runtime looks ready")
            diag = creds.to_diagnostic_dict()
            _print_status(
                "INFO",
                "online credential sources: "
                + f"key={diag['source_key']}, endpoint={diag['source_endpoint']}",
            )
        else:
            _print_status("FAIL", "online runtime not ready: " + reason)
            failures += 1

    print("", flush=True)
    if failures:
        _print_status(
            "FAIL",
            "not ready to start autotune yet",
        )
        return 1

    _print_status(
        "PASS",
        "ready to run the 50-question screen: tools\\autotune_screen_50.bat",
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only preflight checker for HybridRAG autotune.")
    ap.add_argument(
        "--dataset",
        default="Eval/golden_tuning_400.json",
        help="Golden dataset JSON. Default: Eval/golden_tuning_400.json",
    )
    ap.add_argument(
        "--config",
        default="config/config.yaml",
        help="Base config YAML. Default: config/config.yaml",
    )
    ap.add_argument(
        "--mode",
        choices=["offline", "online", "both"],
        default="offline",
        help="Which runtime(s) to check. Default: offline",
    )
    args = ap.parse_args()

    dataset_path = _resolve_existing_path(args.dataset)
    config_path = _resolve_existing_path(args.config, prefer_config_dir=True)
    return _run_preflight(dataset_path=dataset_path, config_path=config_path, mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
