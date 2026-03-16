"""Print DB chunk/source counts for rag-status (called from start_hybridrag.ps1)."""
from __future__ import annotations

import os
import sqlite3
import sys


def main() -> None:
    db = os.path.join(os.getenv("HYBRIDRAG_DATA_DIR", ""), "hybridrag.sqlite3")
    if not os.path.exists(db):
        print("DB not found at:", db)
        print("Run rag-index first.")
        return
    con = sqlite3.connect(db)
    try:
        count = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        sources = con.execute(
            "SELECT COUNT(DISTINCT source_path) FROM chunks"
        ).fetchone()[0]
        print(f"DB: {db}")
        print(f"Chunks: {count}")
        print(f"Source files: {sources}")
    except Exception as e:
        print("DB exists but chunks table missing:", e)
    finally:
        con.close()


if __name__ == "__main__":
    main()
