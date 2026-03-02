#!/usr/bin/env python3
"""
Build profession-specific golden datasets from a master golden JSON.

Usage:
  python tools/build_role_golden_sets.py \
    --dataset Eval/golden_tuning_400.json \
    --outdir Eval/role_sets
"""

import argparse
import json
import os
import re
from collections import defaultdict


def slugify_role(role: str) -> str:
    s = (role or "unknown").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="Eval/golden_tuning_400.json")
    ap.add_argument("--outdir", default="Eval/role_sets")
    args = ap.parse_args()

    with open(args.dataset, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise SystemExit("Dataset must be a JSON list")

    by_role = defaultdict(list)
    for row in rows:
        role = str(row.get("role", "")).strip() or "Unknown"
        by_role[role].append(row)

    os.makedirs(args.outdir, exist_ok=True)
    manifest = {"dataset": args.dataset, "total": len(rows), "roles": {}}

    for role, items in sorted(by_role.items(), key=lambda kv: kv[0].lower()):
        key = slugify_role(role)
        out_path = os.path.join(args.outdir, f"{key}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        manifest["roles"][key] = {
            "role_label": role,
            "count": len(items),
            "path": out_path,
        }

    manifest_path = os.path.join(args.outdir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

