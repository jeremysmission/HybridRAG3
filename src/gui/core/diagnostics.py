# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the diagnostics part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Per-run diagnostics writer for environment snapshots, events, and logs
from __future__ import annotations
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict


class Diagnostics:
    """Plain-English: This class groups logic for diagnostics."""
    def __init__(self, run_id: str, run_dir: str) -> None:
        """Plain-English: This function handles init."""
        self.run_id = run_id
        self.run_dir = run_dir
        self._events_path = os.path.join(run_dir, "events.jsonl")
        self._manifest_path = os.path.join(run_dir, "run_manifest.json")
        self._log_path = os.path.join(run_dir, "gui.log")

    @classmethod
    def create(cls, run_id: str, run_dir: str) -> Diagnostics:
        """Plain-English: This function handles create."""
        os.makedirs(run_dir, exist_ok=True)
        return cls(run_id, run_dir)

    def write_env(self) -> None:
        """Plain-English: This function handles write env."""
        env_path = os.path.join(self.run_dir, "env.json")
        data = {
            "python": sys.executable,
            "version": sys.version,
            "platform": sys.platform,
            "cwd": os.getcwd(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(env_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def write_manifest(self, data: Dict[str, Any]) -> None:
        """Plain-English: This function handles write manifest."""
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def write_event(self, ev: Any) -> None:
        """Plain-English: This function handles write event."""
        with open(self._events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev.to_dict(), default=str) + "\n")

    def write_error(self, label: str, exc: Exception) -> str:
        """Plain-English: This function handles write error."""
        err_path = os.path.join(self.run_dir, f"error_{label}.txt")
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(f"Error: {exc}\n\n")
            f.write(traceback.format_exc())
        return err_path

    def log(self, msg: str) -> None:
        """Plain-English: This function handles log."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
