# ============================================================================
# HybridRAG v3 -- Startup Validator (src/core/bootstrap/startup_validator.py)
# ============================================================================
# Military-aligned intent:
#   - IBIT/CBIT are runtime BITs (in src/core/ibit.py)
#   - This validator is *pre-mission / pre-boot* readiness gating:
#       "Do we have valid configuration + paths to operate?"
#
# Responsibilities:
#   - Read YAML quickly and safely
#   - Resolve configured paths (relative -> absolute)
#   - Decide if Setup Wizard must run (self-healing)
#   - Emit fault codes + human messages for GUI / logs
#
# No side effects:
#   - Does NOT create directories
#   - Does NOT write config
#   - Does NOT touch network
# ============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # already a dependency


@dataclass(frozen=True)
class Fault:
    code: str
    message: str


@dataclass
class StartupStatus:
    requires_setup: bool = False
    faults: List[Fault] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.requires_setup and not self.faults


class StartupValidator:
    def __init__(self, project_root: Path, config_path: Path):
        self.project_root = project_root
        self.config_path = config_path

    def validate(self) -> StartupStatus:
        status = StartupStatus()

        # If caller explicitly provided HYBRIDRAG_DATA_DIR, we assume a managed deployment
        # and skip the wizard (but still allow faults to surface during IBIT).
        if os.environ.get("HYBRIDRAG_DATA_DIR"):
            return status

        cfg = self._load_yaml(status)
        if cfg is None:
            status.requires_setup = True
            return status

        # setup_complete is a hint, never an authority.
        setup_complete = bool(cfg.get("setup_complete", False))

        paths = cfg.get("paths") or {}
        db = paths.get("database")
        src = paths.get("source_folder")
        cache = paths.get("embeddings_cache")

        resolved_db = self._resolve_path(db)
        resolved_src = self._resolve_path(src)
        resolved_cache = self._resolve_path(cache)

        # Missing essentials -> wizard required
        if not db or not src:
            status.faults.append(Fault("CFG_PATHS_MISSING", "Config is missing database and/or source_folder paths."))
            status.requires_setup = True
            return status

        # Paths exist?
        if resolved_db is None:
            status.faults.append(Fault("CFG_DB_INVALID", f"Database path is invalid: {db!r}"))
            status.requires_setup = True
        else:
            db_dir = resolved_db.parent
            if not db_dir.exists():
                status.faults.append(Fault("FS_DB_DIR_MISSING", f"Database directory does not exist: {str(db_dir)}"))
                status.requires_setup = True

        if resolved_src is None:
            status.faults.append(Fault("CFG_SRC_INVALID", f"Source folder path is invalid: {src!r}"))
            status.requires_setup = True
        else:
            if not resolved_src.exists():
                status.faults.append(Fault("FS_SRC_MISSING", f"Source folder does not exist: {str(resolved_src)}"))
                status.requires_setup = True

        # Cache folder is optional but recommended for latency.
        if resolved_cache is None:
            status.warnings.append("Embeddings cache path is not configured; first query may be slower.")
        else:
            cache_dir = resolved_cache
            if not cache_dir.exists():
                status.warnings.append(f"Embeddings cache folder does not exist yet: {str(cache_dir)} (will be created during boot)")

        # If config claims complete but reality disagrees, force setup.
        if setup_complete and status.requires_setup:
            status.warnings.append("setup_complete was true, but paths are invalid; forcing Setup Wizard for recovery.")

        # If config is portable-relative but user moved repo, still OK.
        return status

    def _load_yaml(self, status: StartupStatus) -> Optional[Dict[str, Any]]:
        if not self.config_path.exists():
            status.faults.append(Fault("CFG_MISSING", f"Missing config file: {str(self.config_path)}"))
            return None
        try:
            raw = self.config_path.read_text(encoding="utf-8")
        except Exception as e:
            status.faults.append(Fault("CFG_READ_FAIL", f"Could not read config: {e}"))
            return None
        try:
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                status.faults.append(Fault("CFG_PARSE_FAIL", "Config YAML did not parse into a mapping."))
                return None
            return data
        except Exception as e:
            status.faults.append(Fault("CFG_PARSE_FAIL", f"Config YAML parse error: {e}"))
            return None

    def _resolve_path(self, p: Any) -> Optional[Path]:
        if not p or not isinstance(p, str):
            return None
        try:
            pp = Path(p).expanduser()
            if not pp.is_absolute():
                pp = (self.project_root / pp).resolve()
            else:
                pp = pp.resolve()
            return pp
        except Exception:
            return None
