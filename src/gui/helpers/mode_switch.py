# ============================================================================
# HybridRAG v3 -- Mode-Switch Subsystem (src/gui/helpers/mode_switch.py)
# ============================================================================
# WHAT: Module-level functions that implement offline/online mode switching.
# WHY:  Extracted from HybridRAGApp to keep the main class under 500 lines.
#       Mode switching is a setup-time action (not query-path), so this
#       extraction has zero effect on query latency.
# HOW:  Each function takes the app instance as its first parameter.
#       The app class delegates to these functions via thin one-liners.
# ============================================================================

import tkinter as tk
from tkinter import messagebox
import logging

logger = logging.getLogger(__name__)


def _rebuild_router(app):
    """Close old LLM router, build a new one, and propagate to query engine.

    Returns True on success, False on failure.  On failure shows a
    messagebox so the user knows why the mode switch didn't work.
    """
    try:
        from src.core.llm_router import LLMRouter, invalidate_deployment_cache
        old_router = getattr(app, "router", None)
        if old_router and hasattr(old_router, "close"):
            old_router.close()
        invalidate_deployment_cache()
        new_router = LLMRouter(app.config)
        app.router = new_router
        if hasattr(app, "query_engine") and app.query_engine:
            app.query_engine.llm_router = new_router
        if hasattr(app, "status_bar"):
            app.status_bar.router = new_router
        return True
    except Exception as e:
        logger.warning("Router rebuild failed: %s", e)
        messagebox.showwarning(
            "Router Rebuild Failed",
            "Could not rebuild LLM router:\n\n{}\n\n"
            "Check that Ollama is running.".format(e),
        )
        return False


def toggle_mode(app, new_mode):
    """
    Switch between online and offline mode.

    Online: checks credentials first, shows error if missing.
    Offline: always succeeds (safe operation).
    """
    if new_mode == "online":
        switch_to_online(app)
    else:
        switch_to_offline(app)


def switch_to_online(app):
    """Attempt to switch to online mode."""
    try:
        from src.security.credentials import credential_status
        status = credential_status()

        if not status.get("api_key_set") or not status.get("api_endpoint_set"):
            missing = []
            if not status.get("api_key_set"):
                missing.append("API key")
            if not status.get("api_endpoint_set"):
                missing.append("API endpoint")
            messagebox.showwarning(
                "Credentials Missing",
                "Cannot switch to online mode.\n\n"
                "Missing: {}\n\n"
                "Run rag-store-key and rag-store-endpoint from "
                "PowerShell first, then try again.".format(", ".join(missing)),
            )
            return
    except Exception as e:
        messagebox.showwarning(
            "Credential Check Failed",
            "Could not verify credentials: {}\n\n"
            "Run rag-store-key and rag-store-endpoint from "
            "PowerShell first, then try again.".format(e),
        )
        return

    if app.config:
        app.config.mode = "online"
        persist_mode(app, "online")

    try:
        from src.core.network_gate import configure_gate
        from src.security.credentials import resolve_credentials
        creds = resolve_credentials()
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
        # Revert to offline -- gate is in inconsistent state
        if app.config:
            app.config.mode = "offline"
            persist_mode(app, "offline")
        messagebox.showwarning(
            "Gate Configuration Failed",
            "Could not configure network gate for online mode:\n\n"
            "{}\n\nReverted to offline mode.".format(e),
        )
        update_mode_buttons(app)
        return

    # Rebuild LLM router so online mode actually has API credentials
    _rebuild_router(app)

    update_mode_buttons(app)
    app.status_bar.force_refresh()
    if hasattr(app, "query_panel"):
        app.query_panel._on_use_case_change()

    # Refresh credential display in settings if it exists
    settings = getattr(app, "_settings_view", None)
    if settings is not None and hasattr(settings, "refresh_credential_status"):
        settings.refresh_credential_status()
    # Update API field state (enable for online)
    if settings is not None and hasattr(settings, "_api_admin_tab"):
        settings._api_admin_tab._apply_mode_state()

    logger.info("Switched to ONLINE mode")


def persist_mode(app, new_mode):
    """Write mode change to YAML so it survives restart."""
    try:
        from src.core.config import save_config_field
        save_config_field("mode", new_mode)
    except Exception as e:
        logger.warning("Could not persist mode to YAML: %s", e)


def switch_to_offline(app):
    """Switch to offline mode (always safe)."""
    if app.config:
        app.config.mode = "offline"
        persist_mode(app, "offline")

    try:
        from src.core.network_gate import configure_gate
        configure_gate(mode="offline")
    except Exception as e:
        logger.warning("Gate reconfiguration failed: %s", e)
        messagebox.showwarning(
            "Gate Configuration Failed",
            "Could not configure network gate:\n\n{}\n\n"
            "Continuing in offline mode.".format(e),
        )

    # Rebuild LLM router for offline mode
    _rebuild_router(app)

    update_mode_buttons(app)
    app.status_bar.force_refresh()
    if hasattr(app, "query_panel"):
        app.query_panel._on_use_case_change()
    # Update API field state (gray out for offline)
    settings = getattr(app, "_settings_view", None)
    if settings is not None and hasattr(settings, "_api_admin_tab"):
        settings._api_admin_tab._apply_mode_state()
    logger.info("Switched to OFFLINE mode")


def update_mode_buttons(app):
    """Update mode button colors to reflect current state.

    Disables the ONLINE button when no API credentials are stored,
    so users get a visual cue instead of a confusing error popup.
    """
    t = app._theme
    mode = getattr(app.config, "mode", "offline") if app.config else "offline"

    # Check if online mode is possible (credentials exist)
    has_creds = False
    try:
        from src.security.credentials import credential_status
        status = credential_status()
        has_creds = status.get("api_key_set") and status.get("api_endpoint_set")
    except Exception:
        pass

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
