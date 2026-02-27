# ============================================================================
# HybridRAG v3 -- Startup Health Probe (src/core/bootstrap/startup_health_probe.py)
# ============================================================================
# PURPOSE:
#   Fast, bounded pre-flight checks for demo-day reliability.
#   This is distinct from IBIT:
#     - Probe runs early and must be fast (<~1s typical).
#     - IBIT can be more thorough and user-visible.
#
# OUTPUT:
#   ProbeResult: errors + warnings suitable for GUI display.
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import socket


@dataclass
class ProbeResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_startup_probe(database_path: str, source_folder: str, ollama_host: str = "127.0.0.1", ollama_port: int = 11434) -> ProbeResult:
    errors: list[str] = []
    warnings: list[str] = []

    # Filesystem sanity
    try:
        dbp = Path(database_path)
        dbp.parent.mkdir(parents=True, exist_ok=True)
        testfile = dbp.parent / ".write_test"
        testfile.write_text("ok", encoding="utf-8")
        testfile.unlink(missing_ok=True)
    except Exception as e:
        errors.append(f"DB directory not writable: {e}")

    try:
        src = Path(source_folder)
        src.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        errors.append(f"Source folder not creatable: {e}")

    # Ollama reachability (warning only; online mode still works)
    # Validate host is loopback -- embeddings must never leave the machine
    _loopback = {"localhost", "127.0.0.1", "::1", "[::1]"}
    if ollama_host not in _loopback:
        warnings.append(
            f"Ollama host '{ollama_host}' is not loopback -- "
            f"skipping probe (network gate policy)"
        )
    else:
        try:
            sock = socket.create_connection((ollama_host, ollama_port), timeout=0.5)
            sock.close()
        except Exception:
            warnings.append(f"Ollama not reachable at {ollama_host}:{ollama_port} (offline mode may be unavailable)")

    return ProbeResult(ok=(len(errors) == 0), errors=errors, warnings=warnings)
