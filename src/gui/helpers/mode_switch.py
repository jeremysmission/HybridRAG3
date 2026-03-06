# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the mode switch part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Mode-Switch Subsystem (src/gui/helpers/mode_switch.py)
# ============================================================================
# WHAT: Module-level functions that implement offline/online mode switching.
# WHY:  Extracted from HybridRAGApp to keep the main class under 500 lines.
#       Mode switching is a setup-time action (not query-path), so this
#       extraction has zero effect on query latency.
# HOW:  Each function takes the app instance as its first parameter.
#       The app class delegates to these functions via thin one-liners.
#
# PERFORMANCE:
#   Mode switch runs in a background thread so the GUI never freezes.
#   Credentials are cached for the session so keyring is queried once,
#   not 10-20 times per switch.  Embedder and VectorStore are sticky --
#   only the LLMRouter is rebuilt on mode change.
# ============================================================================

import tkinter as tk
from tkinter import messagebox
import logging
import threading
import os

from src.gui.helpers.safe_after import safe_after

logger = logging.getLogger(__name__)

# Guard against concurrent mode switches (double-click protection)
_switch_lock = threading.Lock()


def _rebuild_router(app, credentials=None):
    """Close old LLM router, build a new one, and propagate to query engine.

    Accepts pre-resolved credentials to avoid redundant keyring lookups.
    Returns router instance on success, or Exception on failure.
    """
    try:
        from src.core.llm_router import LLMRouter, invalidate_deployment_cache
        old_router = getattr(app, "router", None)
        if old_router and hasattr(old_router, "close"):
            old_router.close()
        invalidate_deployment_cache()
        new_router = LLMRouter(app.config, credentials=credentials)
        return new_router
    except Exception as e:
        logger.warning("Router rebuild failed: %s", e)
        return e


def _commit_router_and_mode(app, new_router, new_mode):
    """Apply router/mode mutation on GUI thread to avoid cross-thread writes."""
    from src.gui.helpers.mode_tuning import apply_mode_settings_to_config

    if new_router is not None:
        app.router = new_router
        if hasattr(app, "query_engine") and app.query_engine:
            app.query_engine.llm_router = new_router
        if hasattr(app, "status_bar"):
            app.status_bar.router = new_router
    if app.config:
        app.config.mode = new_mode
        apply_mode_settings_to_config(app.config, new_mode)
        persist_mode(app, new_mode)
    if new_mode == "online":
        os.environ["HYBRIDRAG_OFFLINE"] = "0"
        os.environ["HYBRIDRAG_NETWORK_KILL_SWITCH"] = "0"
    else:
        os.environ["HYBRIDRAG_OFFLINE"] = "1"
        os.environ["HYBRIDRAG_NETWORK_KILL_SWITCH"] = "1"


def toggle_mode(app, new_mode):
    """
    Switch between online and offline mode.

    Online: checks credentials first, shows error if missing.
    Offline: always succeeds (safe operation).
    Runs in a background thread so the GUI stays responsive.
    """
    if new_mode == "online":
        _switch_async(app, _do_switch_to_online)
    else:
        _switch_async(app, _do_switch_to_offline)


# Public aliases for app.py delegation
def switch_to_online(app):
    """Public entry point for online mode switch."""
    _switch_async(app, _do_switch_to_online)


def switch_to_offline(app):
    """Public entry point for offline mode switch."""
    _switch_async(app, _do_switch_to_offline)


def _switch_async(app, switch_fn):
    """Run a mode switch function in a background thread with UI feedback."""
    if not _switch_lock.acquire(blocking=False):
        return  # Already switching -- ignore double-click

    # Disable buttons and show status immediately (main thread)
    try:
        app.offline_btn.config(state=tk.DISABLED)
        app.online_btn.config(state=tk.DISABLED)
    except Exception as e:
        logger.debug("Mode-switch button disable skipped: %s", e)
    if hasattr(app, "status_bar"):
        try:
            app.status_bar.set_loading_stage("Switching mode...")
        except Exception as e:
            logger.debug("Mode-switch stage update skipped: %s", e)

    def _worker():
        """Plain-English: This function handles worker."""
        try:
            switch_fn(app)
        except Exception as e:
            logger.warning("Mode switch failed: %s", e)
        finally:
            _switch_lock.release()
            # Re-enable UI on main thread (via queue in headless mode)
            safe_after(app, 0, _finish_switch, app)

    threading.Thread(target=_worker, daemon=True).start()


def _finish_switch(app):
    """Re-enable UI after mode switch completes (called on main thread)."""
    update_mode_buttons(app)
    if hasattr(app, "status_bar"):
        # Clear transient mode-switch loading text without clobbering IBIT.
        try:
            txt = str(app.status_bar.loading_label.cget("text"))
            if txt.startswith("Loading:"):
                app.status_bar.set_ready()
        except Exception as e:
            logger.debug("Status bar loading clear skipped: %s", e)
        app.status_bar.force_refresh()
    if hasattr(app, "query_panel"):
        app.query_panel._on_use_case_change()
    tuning = getattr(app, "_tuning_panel", None)
    if tuning is not None and hasattr(tuning, "_sync_sliders_to_config"):
        try:
            tuning._sync_sliders_to_config()
        except Exception as e:
            logger.debug("Settings tuning refresh skipped: %s", e)
    # Refresh credential display and mode state in admin panel
    admin = getattr(app, "_admin_panel", None)
    if admin is not None:
        try:
            if hasattr(admin, "_refresh_credential_status"):
                admin._refresh_credential_status()
            if hasattr(admin, "_apply_mode_state"):
                admin._apply_mode_state()
        except Exception as e:
            logger.debug("Admin panel refresh skipped: %s", e)


def _do_switch_to_online(app):
    """Switch to online mode (runs in background thread)."""
    prior_mode = getattr(app.config, "mode", "offline") if app.config else "offline"

    # Check credentials using cached resolution
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(use_cache=True)

        if not creds.has_key or not creds.has_endpoint:
            missing = []
            if not creds.has_key:
                missing.append("API key")
            if not creds.has_endpoint:
                missing.append("API endpoint")
            safe_after(app, 0, messagebox.showwarning,
                      "Credentials Missing",
                      "Cannot switch to online mode.\n\n"
                      "Missing: {}\n\n"
                      "Run rag-store-key and rag-store-endpoint from "
                      "PowerShell first, then try again.".format(", ".join(missing)))
            return
    except Exception as e:
        safe_after(app, 0, messagebox.showwarning,
                   "Credential Check Failed",
                   "Could not verify credentials: {}\n\n"
                   "Run rag-store-key and rag-store-endpoint from "
                   "PowerShell first, then try again.".format(e))
        return

    # -- Transactional mode switch: do NOT mutate config.mode until
    #    both gate and router succeed.  On failure, mode stays offline.

    try:
        from src.core.network_gate import configure_gate
        configure_gate(
            mode="online",
            api_endpoint=creds.endpoint or "",
            allowed_prefixes=getattr(
                getattr(app.config, "api", None),
                "allowed_endpoint_prefixes", [],
            ) if app.config else [],
        )
    except Exception as e:
        logger.warning("Gate reconfiguration failed: %s", e)
        safe_after(app, 0, messagebox.showwarning,
                   "Gate Configuration Failed",
                   "Could not configure network gate for online mode:\n\n"
                   "{}\n\nMode remains offline.".format(e))
        return

    # Rebuild router with cached credentials (no keyring re-lookup)
    result = _rebuild_router(app, credentials=creds)
    if isinstance(result, Exception):
        # Revert gate to prior mode since router rebuild failed.
        try:
            if prior_mode == "online":
                configure_gate(
                    mode="online",
                    api_endpoint=creds.endpoint or "",
                    allowed_prefixes=getattr(
                        getattr(app.config, "api", None),
                        "allowed_endpoint_prefixes", [],
                    ) if app.config else [],
                )
            else:
                configure_gate(mode="offline")
        except Exception:
            logger.debug("Gate rollback to prior mode failed", exc_info=True)
        safe_after(app, 0, messagebox.showwarning,
                   "Router Rebuild Failed",
                   "Could not rebuild LLM router:\n\n{}\n\n"
                   "Mode remains offline.".format(result))
        return

    # -- Success: commit mode change now (on GUI thread) --
    safe_after(app, 0, _commit_router_and_mode, app, result, "online")

    logger.info("Switched to ONLINE mode")


def persist_mode(app, new_mode):
    """Write mode change to YAML so it survives restart."""
    try:
        from src.core.config import save_config_field
        save_config_field("mode", new_mode)
    except Exception as e:
        logger.warning("Could not persist mode to YAML: %s", e)


def _do_switch_to_offline(app):
    """Switch to offline mode (runs in background thread).

    Transactional: config.mode is only committed after gate + router succeed.
    Offline switch is inherently safer (no credentials needed), but we still
    defer the commit for consistency.
    """
    prior_mode = getattr(app.config, "mode", "offline") if app.config else "offline"

    try:
        from src.core.network_gate import configure_gate
        configure_gate(mode="offline")
    except Exception as e:
        logger.warning("Gate reconfiguration failed: %s", e)
        safe_after(app, 0, messagebox.showwarning,
                   "Gate Configuration Failed",
                   "Could not configure network gate:\n\n{}\n\n"
                   "Continuing in current mode.".format(e))
        return

    # Rebuild router with cached credentials (avoids 5+ keyring lookups)
    from src.security.credentials import resolve_credentials
    creds = resolve_credentials(use_cache=True)
    result = _rebuild_router(app, credentials=creds)
    if isinstance(result, Exception):
        # Revert gate back to prior mode if router rebuild failed.
        try:
            if prior_mode == "online":
                from src.core.network_gate import configure_gate
                configure_gate(
                    mode="online",
                    api_endpoint=(getattr(creds, "endpoint", "") or ""),
                    allowed_prefixes=getattr(
                        getattr(app.config, "api", None),
                        "allowed_endpoint_prefixes", [],
                    ) if app.config else [],
                )
            else:
                from src.core.network_gate import configure_gate
                configure_gate(mode="offline")
        except Exception:
            logger.debug("Gate rollback to prior mode failed", exc_info=True)
        safe_after(app, 0, messagebox.showwarning,
                   "Router Rebuild Failed",
                   "Could not rebuild LLM router:\n\n{}\n\n"
                   "Check that Ollama is running.".format(result))
        return

    # -- Success: commit mode change now (on GUI thread) --
    safe_after(app, 0, _commit_router_and_mode, app, result, "offline")

    logger.info("Switched to OFFLINE mode")


def update_mode_buttons(app):
    """Update mode button colors to reflect current state.

    Disables the ONLINE button when no API credentials are stored,
    so users get a visual cue instead of a confusing error popup.
    Uses cached credentials to avoid keyring lookups on every UI refresh.
    """
    t = app._theme
    mode = getattr(app.config, "mode", "offline") if app.config else "offline"

    # Check if online mode is possible (use cached credentials)
    has_creds = False
    try:
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials(use_cache=True)
        has_creds = creds.has_key and creds.has_endpoint
    except Exception:
        logger.debug("Credential probe failed during mode-button refresh", exc_info=True)

    if mode == "online":
        app.online_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                              relief=tk.FLAT, state=tk.NORMAL)
        app.offline_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                               relief=tk.FLAT, state=tk.NORMAL)
    else:
        app.offline_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                               relief=tk.FLAT, state=tk.NORMAL)
        if has_creds:
            app.online_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                                  relief=tk.FLAT, state=tk.NORMAL)
        else:
            app.online_btn.config(bg=t.get("disabled_bg", t["inactive_btn_bg"]),
                                  fg=t.get("disabled_fg", t["gray"]),
                                  relief=tk.FLAT, state=tk.DISABLED)
