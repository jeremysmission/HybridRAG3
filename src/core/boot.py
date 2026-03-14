# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the boot part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===========================================================================
# HybridRAG v3 -- BOOT PIPELINE
# ===========================================================================
# FILE: src/core/boot.py
#
# WHAT THIS IS:
#   The single entry point that starts HybridRAG. It runs every
#   validation step in the correct order and either produces a fully
#   working system or tells you exactly what's broken.
#
# WHY THIS MATTERS:
#   Before this redesign, startup was scattered across multiple files:
#     - start_hybridrag.ps1 set env vars
#     - config.py loaded the YAML
#     - llm_router.py built clients (sometimes with missing credentials)
#     - various modules validated things at different times
#
#   This meant "it works if you do things in the right order" -- but
#   if you forgot a step, you'd get mysterious failures much later.
#
#   Now there's ONE pipeline that runs ALL checks upfront:
#     1. Load config
#     2. Resolve credentials
#     3. Validate config + credentials together
#     4. Construct services (API client, Ollama client, etc.)
#     5. Return a ready-to-use HybridRAG instance
#
# ANALOGY:
#   Like a car's startup sequence: turn key -> check battery -> fuel pump
#   prime -> engine crank -> oil pressure check -> ready to drive.
#   Each step must pass before the next one runs.
#
# USAGE:
#   from src.core.boot import boot_hybridrag
#
#   rag = boot_hybridrag()  # Validates everything
#   # rag.query("What is X?", mode="api")
#   # rag.query("What is X?", mode="offline")
#
# DESIGN DECISIONS:
#   - Returns a HybridRAGInstance that holds all initialized services
#   - Does NOT crash on missing API credentials -- just marks online
#     mode as unavailable (offline mode still works)
#   - Logs every step so you can see exactly what happened during boot
#   - boot_hybridrag() is the ONLY function that creates services
# ===========================================================================

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def _sanitize_boot_ollama_base_url(config: dict | None) -> str:
    """Normalize boot-time Ollama base URLs before any localhost probe."""
    from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url

    base_url = "http://127.0.0.1:11434"
    if not isinstance(config, dict):
        return base_url

    ollama_cfg = config.setdefault("ollama", {})
    if not isinstance(ollama_cfg, dict):
        ollama_cfg = {}
        config["ollama"] = ollama_cfg

    base_url = sanitize_ollama_base_url(ollama_cfg.get("base_url", base_url))
    ollama_cfg["base_url"] = base_url
    return base_url


@dataclass
class BootResult:
    """
    Result of the boot pipeline.

    Attributes:
        success: True if at least offline mode is available.
        online_available: True if API client was created successfully.
        offline_available: True if Ollama is configured.
        offline_probe_pending: True if the Ollama availability check has
            not finished yet within the fast boot window.
        api_client: The ApiClient instance, or None if not available.
        config: The loaded configuration dictionary.
        credentials: Resolved credentials (with masked key).
        warnings: Non-fatal issues found during boot.
        errors: Fatal issues that prevented a mode from starting.
    """
    boot_timestamp: str = ""
    success: bool = False
    online_available: bool = False
    offline_available: bool = False
    offline_probe_pending: bool = False
    api_client: Optional[Any] = None  # ApiClient instance
    config: Dict[str, Any] = field(default_factory=dict)
    credentials: Optional[Any] = None  # ApiCredentials instance
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable boot summary for console/GUI display."""
        lines = []
        overall_state = "READY" if (
            self.online_available or self.offline_available
        ) else ("PENDING" if self.offline_probe_pending else "FAILED")
        lines.append("=" * 50)
        lines.append("  HYBRIDRAG BOOT STATUS")
        lines.append("=" * 50)
        lines.append(f"  Overall:  {overall_state}")
        lines.append(f"  Online:   {'AVAILABLE' if self.online_available else 'NOT AVAILABLE'}")
        offline_state = "AVAILABLE" if self.offline_available else (
            "PENDING" if self.offline_probe_pending else "NOT AVAILABLE"
        )
        lines.append(f"  Offline:  {offline_state}")

        if self.warnings:
            lines.append("")
            lines.append("  WARNINGS:")
            for w in self.warnings:
                lines.append(f"    [!] {w}")

        if self.errors:
            lines.append("")
            lines.append("  ERRORS:")
            for e in self.errors:
                lines.append(f"    [X] {e}")

        lines.append("=" * 50)
        return "\n".join(lines)


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. overlay wins on conflicts."""
    merged = dict(base)
    for k, v in overlay.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge_dict(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(config_path=None) -> dict:
    """
    Load configuration from YAML file.

    Search order:
      1. Explicit path argument
      2. config/config.yaml (relative to project root)

    Returns:
        Dict of configuration values.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    try:
        from src.core.config_files import load_primary_config_dict
        from src.core.config import normalize_config_dict

        raw = load_primary_config_dict(str(project_root), config_path)
        if not raw:
            logger.warning("[BOOT:CONFIG] No config file found -- using defaults")
            return {}
        return normalize_config_dict(str(project_root), raw)
    except Exception as exc:
        logger.warning("[BOOT:CONFIG] Failed to load config: %s", exc)
        return {}


def _boot_step(msg):
    """Print boot step to console for startup hang diagnosis."""
    import time
    ts = time.strftime("%H:%M:%S")
    print("[BOOT    {}] {}".format(ts, msg), flush=True)


def boot_hybridrag(config_path=None) -> BootResult:
    """
    Run the complete boot pipeline.

    Steps:
      1. Load configuration from YAML
      2. Resolve credentials from keyring/env/config
      3. Attempt to build API client (online mode)
      4. Check Ollama availability (offline mode)
      5. Return BootResult with status of everything

    This function NEVER crashes. It catches all exceptions and
    records them in BootResult.errors so the caller can decide
    what to do.

    Args:
        config_path: Optional path to config YAML file.

    Returns:
        BootResult with all status information.
    """
    _boot_step("boot_hybridrag() entered")
    result = BootResult(
        boot_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # === STEP 1: Load Configuration ===
    _boot_step("Step 1: loading config...")
    try:
        config = load_config(config_path)
        _sanitize_boot_ollama_base_url(config)
        result.config = config
        _boot_step("Step 1 done")
    except Exception as e:
        result.errors.append(f"Config load failed: {e}")
        _boot_step("Step 1 FAILED: {}".format(e))
        return result

    # === STEP 2: Resolve Credentials ===
    _boot_step("Step 2: resolving credentials...")
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(config, use_cache=False)
        result.credentials = creds

        if creds.has_endpoint:
            logger.info("BOOT Step 2: Endpoint found (source: %s)", creds.source_endpoint)
        else:
            result.warnings.append("No API endpoint configured -- online mode unavailable")

        if creds.has_key:
            logger.info("BOOT Step 2: API key found (source: %s)", creds.source_key)
        else:
            result.warnings.append("No API key configured -- online mode unavailable")

        _boot_step("Step 2 done")
    except Exception as e:
        result.warnings.append(f"Credential resolution failed: {e}")
        _boot_step("Step 2 WARNING: {}".format(e))

    # === STEP 2.5: Configure Network Gate ===
    # The gate must be configured BEFORE any network calls (Steps 3-4).
    # It reads the mode from config and the endpoint from credentials
    # to build the access control policy.
    _boot_step("Step 2.5: configuring network gate...")
    try:
        from src.core.network_gate import configure_gate

        # Determine the mode and endpoint for the gate
        boot_mode = config.get("mode", "offline") if isinstance(config, dict) else "offline"
        boot_endpoint = ""
        if result.credentials and result.credentials.endpoint:
            boot_endpoint = result.credentials.endpoint
        elif isinstance(config, dict):
            boot_endpoint = config.get("api", {}).get("endpoint", "")

        # Get allowed_endpoint_prefixes from config if available
        allowed_prefixes = []
        if isinstance(config, dict):
            allowed_prefixes = config.get("api", {}).get("allowed_endpoint_prefixes", [])

        # Validate endpoint URL format before using it.
        # Catches "openai.azure.com" (missing https://) with a clear
        # message instead of a 30-second mystery timeout.
        if boot_endpoint and not (
            boot_endpoint.startswith("http://") or
            boot_endpoint.startswith("https://")):
            result.warnings.append(
                f"Invalid endpoint format: {boot_endpoint}. "
                f"Expected http:// or https://")
            boot_endpoint = ""

        gate = configure_gate(
            mode=boot_mode,
            api_endpoint=boot_endpoint,
            allowed_prefixes=allowed_prefixes,
        )
        logger.info(
            "BOOT Step 2.5: Network gate configured (mode=%s, endpoint=%s)",
            boot_mode, boot_endpoint[:50] if boot_endpoint else "(none)",
        )
        _boot_step("Step 2.5 done")
    except Exception as e:
        # If the gate fails to configure, we continue with it in OFFLINE
        # mode (the safe default). This is fail-closed behavior.
        result.warnings.append(f"Network gate configuration failed: {e}")
        _boot_step("Step 2.5 WARNING: {}".format(e))

    # === STEP 3: Build API Client (Online Mode) ===
    _boot_step("Step 3: building API client...")
    if result.credentials and result.credentials.is_online_ready:
        try:
            from src.core.api_client_factory import ApiClientFactory
            factory = ApiClientFactory(config)
            client = factory.build(result.credentials)
            result.api_client = client
            # Only report online_available if the gate actually allows
            # online traffic.  Creating the client proves the credentials
            # are valid, but if the gate is in offline mode the client
            # won't be usable until mode is switched.
            from src.core.network_gate import get_gate, NetworkMode
            result.online_available = get_gate().mode != NetworkMode.OFFLINE
            logger.info("BOOT Step 3: API client created successfully")

            # Log diagnostic info (safe -- no secrets)
            diag = client.get_diagnostic_info()
            logger.info("BOOT Step 3: Provider=%s, Auth=%s", diag["provider"], diag["auth_header"])

        except Exception as e:
            error_msg = str(e)
            fix = getattr(e, "fix_suggestion", None)
            result.errors.append(f"API client creation failed: {error_msg}")
            if fix:
                result.errors.append(f"  Fix: {fix}")
            logger.error("BOOT Step 3 FAILED: %s", e)
        _boot_step("Step 3 done")
    else:
        result.warnings.append("Skipping API client -- credentials incomplete")
        _boot_step("Step 3 skipped (no credentials)")

    # === STEP 4: Check Ollama (non-blocking) ===
    # Ollama is localhost -- responds in <50ms when running. Run the check
    # in a daemon thread with a short join timeout so boot is not blocked
    # for 3s if Ollama is down or slow to respond.
    _boot_step("Step 4: checking Ollama (2s timeout)...")

    ollama_probe = {"available": False, "warning": ""}

    def _check_ollama():
        """Plain-English: This function handles check ollama."""
        try:
            import urllib.request
            import urllib.error
            from src.core.network_gate import get_gate
            ollama_host = _sanitize_boot_ollama_base_url(config)
            get_gate().check_allowed(
                ollama_host, "ollama_boot_check", "boot",
            )
            # Use the lightweight root health endpoint here instead of
            # /api/tags. The tags route can exceed the 2s boot join window
            # on cold local workstations even when Ollama is healthy.
            # ProxyHandler({}) bypasses managed-network proxy for loopback.
            # Without this, transparent proxy intercepts 127.0.0.1.
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({})
            )
            req = urllib.request.Request(
                ollama_host, method="GET",
            )
            with opener.open(req, timeout=3) as response:
                if response.status == 200:
                    ollama_probe["available"] = True
                    logger.info("BOOT Step 4: Ollama is running")
                else:
                    ollama_probe["warning"] = (
                        "Ollama responded but with unexpected status"
                    )
        except Exception:
            ollama_probe["warning"] = (
                "Ollama is not running -- offline mode unavailable"
            )
            logger.info("BOOT Step 4: Ollama not reachable")

    ollama_thread = threading.Thread(target=_check_ollama, daemon=True)
    ollama_thread.start()
    ollama_thread.join(timeout=2.0)

    if ollama_thread.is_alive():
        # Ollama check did not complete in time. Do NOT assume available
        # -- an optimistic True here masks real failures and causes the
        # first offline query to crash instead of showing a clear message.
        # Status bar CBIT will detect Ollama within 30s and update.
        result.offline_probe_pending = True
        result.warnings.append(
            "Ollama health check timed out (2s). "
            "Offline mode will activate when Ollama responds."
        )
        logger.info("BOOT Step 4: Ollama check timed out, NOT assuming available")
    else:
        result.offline_available = bool(ollama_probe["available"])
        if ollama_probe["warning"]:
            result.warnings.append(ollama_probe["warning"])

    # === STEP 4.5: Check vLLM (if enabled) ===
    vllm_cfg = config.get("vllm", {}) if isinstance(config, dict) else {}
    if vllm_cfg.get("enabled", False):
        logger.info("BOOT Step 4.5: Checking vLLM...")
        vllm_url = vllm_cfg.get("base_url", "http://localhost:8000").rstrip("/")
        try:
            import urllib.request
            from src.core.network_gate import get_gate
            get_gate().check_allowed(
                f"{vllm_url}/health", "vllm_boot_check", "boot",
            )
            # ProxyHandler({}) bypasses managed-network proxy for loopback,
            # matching the Ollama boot check pattern above.
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({})
            )
            req = urllib.request.Request(f"{vllm_url}/health", method="GET")
            with opener.open(req, timeout=3) as response:
                if response.status == 200:
                    logger.info("[OK] vLLM available at %s", vllm_url)
                else:
                    result.warnings.append(
                        "vLLM responded with unexpected status (Ollama fallback)"
                    )
        except Exception:
            result.warnings.append(
                "[WARN] vLLM not running at " + vllm_url + " (Ollama fallback)"
            )
            logger.info("BOOT Step 4.5: vLLM not reachable, Ollama fallback active")
    else:
        logger.info("BOOT Step 4.5: vLLM disabled in config, skipping")

    _boot_step("Step 4 done (offline={})".format(result.offline_available))

    # === FINAL: Determine overall success ===
    result.success = (
        result.online_available
        or result.offline_available
        or result.offline_probe_pending
    )

    if not result.success:
        result.errors.append(
            "Neither online nor offline mode is available. "
            "Run 'rag-status' for diagnostics."
        )

    logger.info("BOOT Complete: success=%s, online=%s, offline=%s",
                result.success, result.online_available, result.offline_available)

    return result
