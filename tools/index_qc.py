#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Run index contamination and fingerprint checks from the command line.
# What to read first: Start at main().
# Inputs: Config path plus optional fingerprint baseline path.
# Outputs: PASS/WARN/FAIL console lines and optional fingerprint JSON.
# Safety notes: Read-only unless --write-baseline is used.
# ============================

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.index_qc import (
    build_index_fingerprint,
    compare_fingerprints,
    detect_index_contamination,
    load_fingerprint,
    write_fingerprint,
)
from tools.run_mode_autotune import _load_runtime_config


def _print_status(level: str, message: str) -> None:
    print(f"[{level}] {message}", flush=True)


def _preview_paths(items: list[str], limit: int = 5) -> str:
    if not items:
        return "(none)"
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f", ... (+{len(items) - limit} more)"


def main() -> int:
    ap = argparse.ArgumentParser(description="HybridRAG index quality-control checker.")
    ap.add_argument(
        "--config",
        default="config/default_config.yaml",
        help="Config YAML path. Default: config/default_config.yaml",
    )
    ap.add_argument(
        "--baseline",
        default="logs/index_qc/index_fingerprint.json",
        help="Fingerprint baseline JSON path. Default: logs/index_qc/index_fingerprint.json",
    )
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write the current fingerprint to the baseline path.",
    )
    args = ap.parse_args()

    cfg = _load_runtime_config(Path(args.config))
    db_path = Path(getattr(getattr(cfg, "paths", None), "database", "") or "")
    source_root = str(getattr(getattr(cfg, "paths", None), "source_folder", "") or "")
    embeddings_cache = Path(
        getattr(getattr(cfg, "paths", None), "embeddings_cache", "") or ""
    )

    if not db_path:
        _print_status("FAIL", "database path is empty in config")
        return 1
    if not db_path.exists():
        _print_status("FAIL", f"indexed database not found: {db_path}")
        return 1

    _print_status("PASS", f"indexed database found: {db_path}")
    contamination = detect_index_contamination(db_path, source_root=source_root)
    _print_status(contamination["level"], contamination["summary"])
    if contamination["suspicious_count"]:
        preview = [
            f"{Path(item['source_path']).name} [{'|'.join(item['flags'])}]"
            for item in contamination["suspicious_sources"][:5]
        ]
        _print_status("INFO", "suspicious examples: " + _preview_paths(preview))

    fingerprint = build_index_fingerprint(db_path, embeddings_cache)
    _print_status(
        "PASS",
        "current fingerprint: "
        + fingerprint["combined_sha256"][:16]
        + f" ({fingerprint['artifact_count']} artifacts)",
    )

    baseline_path = Path(args.baseline)
    if args.write_baseline:
        write_fingerprint(baseline_path, fingerprint)
        _print_status("PASS", f"baseline written: {baseline_path}")
        return 0 if contamination["level"] != "FAIL" else 1

    if baseline_path.exists():
        baseline = load_fingerprint(baseline_path)
        diff = compare_fingerprints(fingerprint, baseline)
        if diff["matches"]:
            _print_status("PASS", "fingerprint matches baseline")
        else:
            _print_status("WARN", "fingerprint drift detected vs baseline")
            if diff["added"]:
                _print_status("INFO", "added artifacts: " + _preview_paths(diff["added"]))
            if diff["removed"]:
                _print_status("INFO", "removed artifacts: " + _preview_paths(diff["removed"]))
            if diff["changed"]:
                _print_status("INFO", "changed artifacts: " + _preview_paths(diff["changed"]))
    else:
        _print_status(
            "WARN",
            f"baseline file not found: {baseline_path} (run with --write-baseline after a known-clean rebuild)",
        )

    if contamination["level"] == "FAIL":
        _print_status("FAIL", "recommended action: flush index and rebuild from a clean source folder")
        return 1

    _print_status("PASS", "index quality-control checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
