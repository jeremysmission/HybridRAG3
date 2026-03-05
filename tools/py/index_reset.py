# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the index reset operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."))

from src.core.config import load_config  # noqa: E402


def _project_root() -> Path:
    return Path(os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")).resolve()


def _safe_delete(path: Path, root: Path) -> bool:
    try:
        real = path.resolve()
    except FileNotFoundError:
        return False
    if not str(real).startswith(str(root) + os.sep):
        print(f"  [SKIP] Outside project root: {real}")
        return False
    if real.is_file():
        size_mb = real.stat().st_size / (1024 * 1024)
        real.unlink()
        print(f"  [DELETED] {real} ({size_mb:.1f} MB)")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely reset HybridRAG index files.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Without this flag the script performs a dry-run only.",
    )
    args = parser.parse_args()

    root = _project_root()
    cfg = load_config(str(root))

    db_path = Path(getattr(getattr(cfg, "paths", None), "database", "") or "")
    emb_dir = Path(getattr(getattr(cfg, "paths", None), "embeddings_cache", "") or "")

    candidates: list[Path] = []
    if db_path:
        candidates.append(db_path)
    if emb_dir and emb_dir.exists():
        candidates.extend(emb_dir.glob("*.npy"))
        candidates.extend(emb_dir.glob("*.dat"))
        candidates.extend(emb_dir.glob("*.json"))

    if not candidates:
        print("  No configured index files found.")
        return 0

    print("  Planned deletions:")
    for p in candidates:
        print(f"    - {p}")
    print()

    if not args.confirm:
        print("  Dry run only. Re-run with --confirm to delete.")
        return 2

    deleted = 0
    for p in candidates:
        if _safe_delete(p, root):
            deleted += 1

    if deleted == 0:
        print("  No files deleted.")
    else:
        print()
        print("  Index cleared. Run rag-index to rebuild.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
