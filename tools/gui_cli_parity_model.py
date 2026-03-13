#!/usr/bin/env python3
"""
Model and persistence helpers for the GUI/CLI parity QA harness.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = PROJECT_ROOT / "output" / "gui_cli_parity_report.json"
VALID_STATUSES = ("missing", "planned", "partial", "implemented", "verified")


@dataclass
class CapabilityRecord:
    capability_id: str
    category: str
    display_name: str
    cli_command: str
    gui_target: str
    priority: str = "high"
    status: str = "missing"
    notes: str = ""
    smoke_command: list[str] = field(default_factory=list)
    last_smoke_ok: bool | None = None
    last_smoke_exit_code: int | None = None
    last_smoke_summary: str = ""
    last_smoke_at: str = ""


def build_default_catalog() -> list[CapabilityRecord]:
    python = sys.executable
    return [
        CapabilityRecord(
            capability_id="query-path-probe",
            category="Query",
            display_name="Query path probe",
            cli_command="python tools/query_path_probe.py --help",
            gui_target="Query tab / diagnostics pane",
            smoke_command=[python, "tools/query_path_probe.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="index-qc",
            category="Indexing",
            display_name="Index quality control",
            cli_command="python tools/index_qc.py --help",
            gui_target="Index tab / QC drawer",
            smoke_command=[python, "tools/index_qc.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="index-reset",
            category="Indexing",
            display_name="Index reset",
            cli_command="python tools/py/index_reset.py --help",
            gui_target="Admin / maintenance tools",
            smoke_command=[python, "tools/py/index_reset.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="bulk-transfer",
            category="Data",
            display_name="Bulk transfer",
            cli_command="python src/tools/bulk_transfer_v2.py --help",
            gui_target="Data tab / transfer workflow",
            smoke_command=[python, "src/tools/bulk_transfer_v2.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="scheduled-scan",
            category="Data",
            display_name="Scheduled scan",
            cli_command="python src/tools/scheduled_scan.py --help",
            gui_target="Data tab / schedules",
            smoke_command=[python, "src/tools/scheduled_scan.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="feature-toggles",
            category="Config",
            display_name="Feature toggles",
            cli_command="python src/core/feature_registry.py list",
            gui_target="Settings / feature toggles",
            smoke_command=[python, "src/core/feature_registry.py", "help"],
        ),
        CapabilityRecord(
            capability_id="online-api-setup",
            category="Config",
            display_name="Online API setup",
            cli_command="python tools/py/setup_online_api.py --help",
            gui_target="Admin / API setup",
            smoke_command=[python, "tools/py/setup_online_api.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="store-key",
            category="Config",
            display_name="Credential key storage",
            cli_command="python tools/py/store_key.py --help",
            gui_target="Admin / credential storage",
            smoke_command=[python, "tools/py/store_key.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="api-server",
            category="Ops",
            display_name="FastAPI server",
            cli_command="python src/api/server.py --help",
            gui_target="Admin / deployment controls",
            smoke_command=[python, "src/api/server.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="system-diagnostic",
            category="Ops",
            display_name="System diagnostic",
            cli_command="python src/tools/system_diagnostic.py --help",
            gui_target="Admin / diagnostics panel",
            smoke_command=[python, "src/tools/system_diagnostic.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="run-regression-safe",
            category="Ops",
            display_name="Regression-safe runner",
            cli_command="python tools/run_regression_safe.py --help",
            gui_target="Admin / QA tools",
            smoke_command=[python, "tools/run_regression_safe.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="eval-runner",
            category="Evaluation",
            display_name="Eval runner",
            cli_command="python tools/eval_runner.py --help",
            gui_target="Eval / tuning panel",
            smoke_command=[python, "tools/eval_runner.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="mode-autotune",
            category="Evaluation",
            display_name="Mode autotune",
            cli_command="python tools/run_mode_autotune.py --help",
            gui_target="Eval / tuning panel",
            smoke_command=[python, "tools/run_mode_autotune.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="autotune-preflight",
            category="Evaluation",
            display_name="Autotune preflight",
            cli_command="python tools/autotune_preflight.py --help",
            gui_target="Eval / tuning panel",
            smoke_command=[python, "tools/autotune_preflight.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="gui-demo-smoke",
            category="GUI QA",
            display_name="GUI demo smoke",
            cli_command="python tools/gui_demo_smoke.py --help",
            gui_target="QA harness / demo validation",
            smoke_command=[python, "tools/gui_demo_smoke.py", "--help"],
        ),
        CapabilityRecord(
            capability_id="gui-e2e",
            category="GUI QA",
            display_name="GUI E2E click-all",
            cli_command="python tools/gui_e2e/run.py --help",
            gui_target="QA harness / click-all",
            smoke_command=[python, "tools/gui_e2e/run.py", "--help"],
        ),
    ]


def normalize_status(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_STATUSES else "missing"


def load_saved_state(path: Path) -> dict[str, dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw_items = payload.get("capabilities", [])
    saved: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        capability_id = str(item.get("capability_id") or "").strip()
        if capability_id:
            saved[capability_id] = dict(item)
    return saved


def merge_saved_state(
    catalog: list[CapabilityRecord],
    saved: dict[str, dict[str, Any]],
) -> list[CapabilityRecord]:
    merged: list[CapabilityRecord] = []
    for record in catalog:
        row = CapabilityRecord(**asdict(record))
        previous = saved.get(row.capability_id, {})
        row.status = normalize_status(previous.get("status", row.status))
        row.notes = str(previous.get("notes", row.notes) or "")
        row.last_smoke_ok = previous.get("last_smoke_ok", row.last_smoke_ok)
        row.last_smoke_exit_code = previous.get("last_smoke_exit_code", row.last_smoke_exit_code)
        row.last_smoke_summary = str(previous.get("last_smoke_summary", row.last_smoke_summary) or "")
        row.last_smoke_at = str(previous.get("last_smoke_at", row.last_smoke_at) or "")
        merged.append(row)
    return merged


def summarize_records(records: list[CapabilityRecord]) -> dict[str, int]:
    summary = {status: 0 for status in VALID_STATUSES}
    for record in records:
        summary[normalize_status(record.status)] += 1
    summary["total"] = len(records)
    return summary


def run_smoke_command(
    record: CapabilityRecord,
    *,
    cwd: Path | None = None,
    timeout_s: int = 30,
) -> CapabilityRecord:
    if not record.smoke_command:
        updated = CapabilityRecord(**asdict(record))
        updated.last_smoke_ok = None
        updated.last_smoke_exit_code = None
        updated.last_smoke_summary = "No smoke command configured."
        updated.last_smoke_at = _utc_now()
        return updated

    completed = subprocess.run(
        record.smoke_command,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")

    updated = CapabilityRecord(**asdict(record))
    updated.last_smoke_ok = completed.returncode == 0
    updated.last_smoke_exit_code = int(completed.returncode)
    updated.last_smoke_summary = first_line or "Smoke command completed with no output."
    updated.last_smoke_at = _utc_now()
    return updated


def records_to_report(records: list[CapabilityRecord]) -> dict[str, Any]:
    return {
        "generated_at": _utc_now(),
        "summary": summarize_records(records),
        "capabilities": [asdict(record) for record in records],
    }


def save_report(path: Path, records: list[CapabilityRecord]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(records_to_report(records), indent=2),
        encoding="utf-8",
    )
    return target


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

