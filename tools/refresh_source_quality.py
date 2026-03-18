#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Refresh stored source-quality metadata for an existing HybridRAG index.
# What to read first: Start at main().
# Inputs: SQLite database path or a config file that resolves one.
# Outputs: Console summary of before/after source-quality stats.
# Safety notes: Only updates the source_quality table. It does not re-chunk or re-embed.
# ============================

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import load_config
from src.core.source_quality import (
    ensure_source_quality_schema,
    refresh_all_source_quality_records,
)


def _collect_stats(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT
            COUNT(*) AS total_rows,
            SUM(CASE WHEN retrieval_tier = 'serve' THEN 1 ELSE 0 END) AS serve_rows,
            SUM(CASE WHEN retrieval_tier = 'suspect' THEN 1 ELSE 0 END) AS suspect_rows,
            SUM(CASE WHEN retrieval_tier = 'archive' THEN 1 ELSE 0 END) AS archive_rows,
            SUM(CASE WHEN flags_json LIKE '%golden_seed_file%' THEN 1 ELSE 0 END) AS golden_seed_rows,
            SUM(CASE WHEN flags_json LIKE '%test_or_demo_artifact%' THEN 1 ELSE 0 END) AS test_demo_rows,
            SUM(CASE WHEN flags_json LIKE '%zip_bundle%' THEN 1 ELSE 0 END) AS zip_rows,
            SUM(CASE WHEN flags_json LIKE '%temp_or_pipeline_doc%' THEN 1 ELSE 0 END) AS temp_rows
        FROM source_quality
        """
    ).fetchone()
    return {
        "total_rows": int(rows[0] or 0),
        "serve_rows": int(rows[1] or 0),
        "suspect_rows": int(rows[2] or 0),
        "archive_rows": int(rows[3] or 0),
        "golden_seed_rows": int(rows[4] or 0),
        "test_demo_rows": int(rows[5] or 0),
        "zip_rows": int(rows[6] or 0),
        "temp_rows": int(rows[7] or 0),
    }


def _resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db).expanduser().resolve()

    config = load_config(str(PROJECT_ROOT))
    db_path = Path(getattr(getattr(config, "paths", None), "database", "") or "")
    if not db_path:
        raise SystemExit("No database path provided and config.paths.database is blank.")
    return db_path.resolve()


def _print_stats(label: str, stats: dict[str, int]) -> None:
    print(label)
    print(f"  total_rows:   {stats['total_rows']}")
    print(f"  serve_rows:   {stats['serve_rows']}")
    print(f"  suspect_rows: {stats['suspect_rows']}")
    print(f"  archive_rows: {stats['archive_rows']}")
    print(f"  golden_seed:  {stats['golden_seed_rows']}")
    print(f"  test_demo:    {stats['test_demo_rows']}")
    print(f"  zip_bundle:   {stats['zip_rows']}")
    print(f"  temp_doc:     {stats['temp_rows']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh source_quality rows for an existing HybridRAG SQLite index."
    )
    parser.add_argument(
        "--db",
        default="",
        help="Explicit path to hybridrag.sqlite3. Defaults to config.paths.database if set.",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Print current stats without modifying source_quality rows.",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        ensure_source_quality_schema(conn)
        before = _collect_stats(conn)
        _print_stats("Before refresh", before)

        if args.stats_only:
            return 0

        refresh_stats = refresh_all_source_quality_records(conn)
        after = _collect_stats(conn)

        print("Refresh run")
        print(f"  total_sources: {refresh_stats['total_sources']}")
        print(f"  refreshed:     {refresh_stats['refreshed']}")
        print(
            f"  skipped_manual_override: {refresh_stats['skipped_manual_override']}"
        )
        _print_stats("After refresh", after)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
