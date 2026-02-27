# ============================================================================
# HybridRAG v3 -- Environment Resolver (src/core/bootstrap/environment.py)
# ============================================================================
# Purpose:
#   Resolve all filesystem and environment bindings deterministically and
#   portably (Windows/macOS/Linux). This is the single source of truth for:
#     - project root
#     - data root
#     - index root
#     - default config path
#
# Notes:
#   - No YAML writes.
#   - No GUI logic.
#   - No network calls.
#   - Safe to import early for boot/IBIT.
# ============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Environment:
    project_root: Path
    config_path: Path
    data_root: Path
    index_root: Path
    source_root: Path

    @staticmethod
    def detect(project_root_hint: str | None = None) -> "Environment":
        # 1) explicit param
        if project_root_hint:
            pr = Path(project_root_hint).expanduser().resolve()
        else:
            # 2) env override
            env_pr = os.environ.get("HYBRIDRAG_PROJECT_ROOT")
            if env_pr:
                pr = Path(env_pr).expanduser().resolve()
            else:
                # 3) derive from file location: .../src/core/bootstrap/environment.py
                pr = Path(__file__).resolve().parents[3]

        config_path = pr / "config" / "default_config.yaml"

        # Data root convention:
        # - If HYBRIDRAG_DATA_DIR is set, we treat it as the *index root*
        #   (historical naming). Otherwise use repo-local ./data.
        env_data_dir = os.environ.get("HYBRIDRAG_DATA_DIR")
        if env_data_dir:
            index_root = Path(env_data_dir).expanduser().resolve()
            data_root = index_root.parent
        else:
            data_root = pr / "data"
            index_root = data_root / "index"

        # Source root convention:
        # - Prefer HYBRIDRAG_SOURCE_DIR (new)
        # - Accept HYBRIDRAG_INDEX_FOLDER (legacy misnomer used as source folder)
        env_src = os.environ.get("HYBRIDRAG_SOURCE_DIR") or os.environ.get("HYBRIDRAG_INDEX_FOLDER")
        if env_src:
            source_root = Path(env_src).expanduser().resolve()
        else:
            source_root = data_root / "source"

        return Environment(
            project_root=pr,
            config_path=config_path,
            data_root=data_root,
            index_root=index_root,
            source_root=source_root,
        )

    def ensure_directories(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.source_root.mkdir(parents=True, exist_ok=True)
