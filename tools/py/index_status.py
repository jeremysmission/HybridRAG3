from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[2]
if str(PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT))


def _configured_database_path() -> Path | None:
    try:
        from src.core.config import load_config

        cfg = load_config(str(PROJ_ROOT))
        db_path = (getattr(getattr(cfg, "paths", None), "database", "") or "").strip()
        if db_path:
            return Path(db_path)
    except Exception:
        return None
    return None


def _candidate_databases() -> list[Path]:
    configured = _configured_database_path()
    candidates: list[Path] = []
    if configured:
        candidates.append(configured)

    fallback_names = (
        PROJ_ROOT / "data" / "index" / "hybridrag.sqlite3",
        PROJ_ROOT / "data" / "hybridrag.sqlite3",
        PROJ_ROOT / "rag_data.db",
    )
    for path in fallback_names:
        if path not in candidates:
            candidates.append(path)
    return candidates


def main() -> int:
    candidates = [path for path in _candidate_databases() if path.exists()]
    if not candidates:
        print("  No database found.")
        return 0

    db = candidates[0]
    print(f"  Database: {db}")
    size_mb = db.stat().st_size / (1024 * 1024)
    print(f"  Size:     {size_mb:.1f} MB")

    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()

        try:
            cur.execute("SELECT COUNT(*) FROM chunks")
            chunks = cur.fetchone()[0]
            print(f"  Chunks:   {chunks}")
        except Exception:
            pass

        try:
            cur.execute("SELECT COUNT(DISTINCT source_file) FROM chunks")
            files = cur.fetchone()[0]
            print(f"  Files:    {files}")
        except Exception:
            pass

        try:
            cur.execute("SELECT MAX(indexed_at) FROM chunks")
            last = cur.fetchone()[0]
            if last:
                print(f"  Last indexed: {last}")
        except Exception:
            pass

        try:
            cur.execute("SELECT COUNT(*) FROM index_runs")
            runs = cur.fetchone()[0]
            print(f"  Total runs:   {runs}")
        except Exception:
            pass

        conn.close()
    except Exception as exc:
        print(f"  [ERROR] {exc}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
