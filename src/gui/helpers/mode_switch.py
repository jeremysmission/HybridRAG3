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
    """Update mode button colors to reflect current state."""
    t = app._theme
    mode = getattr(app.config, "mode", "offline") if app.config else "offline"
    if mode == "online":
        app.online_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                              relief=tk.FLAT)
        app.offline_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                               relief=tk.FLAT)
    else:
        app.offline_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                               relief=tk.FLAT)
        app.online_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                              relief=tk.FLAT)
