from __future__ import annotations

from datetime import datetime


def _iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def build_network_activity_snapshot(limit: int = 50) -> dict:
    """Return a deployment-facing snapshot of recent network-gate activity."""
    from src.core.network_gate import get_gate

    gate = get_gate()
    summary = gate.get_audit_summary()
    entries = gate.get_audit_log(last_n=limit)
    recent = [
        {
            "timestamp": float(entry.timestamp),
            "timestamp_iso": _iso_timestamp(float(entry.timestamp)),
            "url": str(entry.url),
            "host": str(entry.host),
            "purpose": str(entry.purpose),
            "mode": str(entry.mode),
            "allowed": bool(entry.allowed),
            "reason": str(entry.reason),
            "caller": str(entry.caller),
        }
        for entry in reversed(entries)
    ]
    return {
        "mode": str(summary.get("mode", "")),
        "total_checks": int(summary.get("total_checks", 0) or 0),
        "allowed": int(summary.get("allowed", 0) or 0),
        "denied": int(summary.get("denied", 0) or 0),
        "allowed_hosts": list(summary.get("allowed_hosts", []) or []),
        "unique_hosts_contacted": list(summary.get("unique_hosts_contacted", []) or []),
        "entries": recent,
    }
