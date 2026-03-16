# === NON-PROGRAMMER GUIDE ===
# Purpose: Runtime methods for ApiAdminTab, extracted to keep class under 500 lines.
# What to read first: See api_admin_tab.py for the main class definitions.
# Inputs: Called as bound methods on ApiAdminTab instances.
# Outputs: UI updates, config persistence, credential management.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- API Admin Tab Runtime (src/gui/panels/api_admin_tab_runtime.py)
# ============================================================================
# Extracted methods for ApiAdminTab, bound at import time via
# bind_api_admin_tab_runtime_methods().
#
# Pattern: each function takes `self` as first arg and is attached to
# ApiAdminTab by the bind function at the bottom. This keeps the main
# file under the 500-line class body limit.
# ============================================================================

import logging
import os
import re
import subprocess
import threading
import time
import tkinter as tk

import psutil

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.core.model_identity import canonicalize_model_name
from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url
from src.core.query_trace import format_query_trace_text
from src.core.mode_config import MODE_TUNED_DEFAULTS
# NOTE: Credential functions (resolve_credentials, validate_endpoint, etc.)
# are NOT imported here. They are imported lazily inside each function that
# needs them, via `from src.gui.panels.api_admin_tab import <name>`.
# This ensures test patches targeting `src.gui.panels.api_admin_tab.resolve_credentials`
# are picked up by the runtime functions. See test_gui_integration_w4.py.

logger = logging.getLogger(__name__)


# --- Theme helper (shared with main module) ---

def _theme_widget(widget, t):
    """Recursively apply theme to a widget and its children.

    Walks the entire widget tree starting from `widget` and sets
    background/foreground colors based on each widget's class.
    This is necessary because tk (not ttk) widgets do not inherit
    theme changes automatically -- each one must be touched manually.
    """
    try:
        wclass = widget.winfo_class()
        if wclass == "Frame":
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Entry":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
        elif wclass == "Checkbutton":
            widget.configure(
                bg=t["panel_bg"], fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"])
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


# ---------------------------------------------------------------------------
# ApiAdminTab runtime methods
# ---------------------------------------------------------------------------

def _api_admintab__build_dev_hidden_notice(self, t):
    """Show a small notice when dev-only tuning controls are hidden."""
    frame = tk.LabelFrame(
        self._inner, text="Development Controls", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(4, 8))
    tk.Label(
        frame,
        text=(
            "Advanced tuning is hidden in standard mode. "
            "Set HYBRIDRAG_DEV_UI=1 to show Development-only controls."
        ),
        anchor=tk.W, justify=tk.LEFT, wraplength=760,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(fill=tk.X)

def _api_admintab__build_credentials_section(self, t):
    """Build API credential entry fields and action buttons."""
    frame = tk.LabelFrame(
        self._inner, text="API Credentials", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(8, 4))
    self._cred_frame = frame

    # Endpoint URL
    row_ep = tk.Frame(frame, bg=t["panel_bg"])
    row_ep.pack(fill=tk.X, pady=4)
    tk.Label(
        row_ep, text="Endpoint URL:", width=14, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)
    self.endpoint_var = tk.StringVar()
    self.endpoint_entry = tk.Entry(
        row_ep, textvariable=self.endpoint_var, font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    )
    self.endpoint_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    # API Key
    row_key = tk.Frame(frame, bg=t["panel_bg"])
    row_key.pack(fill=tk.X, pady=4)
    tk.Label(
        row_key, text="API Key:", width=14, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)
    self.key_var = tk.StringVar()
    self.key_entry = tk.Entry(
        row_key, textvariable=self.key_var, show="*", font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    )
    self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

    self._key_visible = False
    # Security-first default: do not allow API key reveal in an
    # unprotected Admin screen. To intentionally re-enable reveal:
    #   HYBRIDRAG_ALLOW_KEY_REVEAL=1
    allow_key_reveal = os.environ.get(
        "HYBRIDRAG_ALLOW_KEY_REVEAL", ""
    ).strip().lower() in ("1", "true", "yes")
    self.toggle_key_btn = tk.Button(
        row_key,
        text="Show" if allow_key_reveal else "Reveal Locked",
        width=11,
        font=FONT_SMALL,
        command=self._toggle_key_visibility if allow_key_reveal else None,
        state=tk.NORMAL if allow_key_reveal else tk.DISABLED,
        bg=t["input_bg"], fg=t["fg"], relief=tk.FLAT, bd=0,
    )
    self.toggle_key_btn.pack(side=tk.LEFT, padx=(4, 0))

    # Button row
    btn_row = tk.Frame(frame, bg=t["panel_bg"])
    btn_row.pack(fill=tk.X, pady=(8, 4))

    self.save_cred_btn = tk.Button(
        btn_row, text="Save Credentials", command=self._on_save_credentials,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self.save_cred_btn.pack(side=tk.LEFT, padx=(0, 8))
    bind_hover(self.save_cred_btn)

    # Safety-first default: hide manual connection test button to prevent
    # accidental clicks that can disrupt live demo state.
    #
    # To re-enable intentionally, set:
    #   HYBRIDRAG_ENABLE_CONN_TEST=1
    allow_conn_test = os.environ.get(
        "HYBRIDRAG_ENABLE_CONN_TEST", ""
    ).strip().lower() in ("1", "true", "yes")
    self.test_btn = tk.Button(
        btn_row, text="Test Connection", command=self._on_test_connection,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    if allow_conn_test:
        self.test_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.test_btn)
    else:
        self.test_btn.config(state=tk.DISABLED)
        self.test_disabled_label = tk.Label(
            btn_row, text="Connection test hidden (safety mode)",
            anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.test_disabled_label.pack(side=tk.LEFT, padx=(0, 8))

    self.clear_cred_btn = tk.Button(
        btn_row, text="Clear Credentials", command=self._on_clear_credentials,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
    )
    self.clear_cred_btn.pack(side=tk.LEFT)
    bind_hover(self.clear_cred_btn)

    # Status label
    self.cred_status_label = tk.Label(
        frame, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self.cred_status_label.pack(fill=tk.X, pady=(2, 0))

    # Plain-English network policy line for non-technical users.
    self.network_policy_label = tk.Label(
        frame, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["label_fg"], font=FONT_SMALL,
        justify=tk.LEFT, wraplength=1,
    )
    self.network_policy_label.pack(fill=tk.X, pady=(2, 0))
    self.network_policy_label.bind(
        "<Configure>",
        lambda e: e.widget.config(wraplength=max(200, e.width - 8)),
    )
    self._refresh_network_policy_label()

def _api_admintab__toggle_key_visibility(self):
    """Toggle between masked (****) and plain-text API key display."""
    self._key_visible = not self._key_visible
    if self._key_visible:
        self.key_entry.config(show="")
        self.toggle_key_btn.config(text="Hide")
    else:
        self.key_entry.config(show="*")
        self.toggle_key_btn.config(text="Show")

def _api_admintab__refresh_credential_status(self):
    """Load current credential status and pre-populate fields."""
    from src.gui.panels.api_admin_tab import resolve_credentials
    try:
        creds = resolve_credentials()
        if creds.endpoint:
            self.endpoint_var.set(creds.endpoint)
        if creds.api_key:
            self.key_var.set(creds.api_key)

        def _source_label(raw):
            """Plain-English: This function handles source label."""
            src = (raw or "?").strip()
            if src.lower() == "keyring":
                return "Credential Manager"
            return src

        parts = []
        if creds.has_key:
            parts.append("Key: {} (from {})".format(
                creds.key_preview, _source_label(creds.source_key)))
        else:
            parts.append("Key: NOT SET")
        if creds.has_endpoint:
            parts.append("Endpoint: SET (from {})".format(
                _source_label(creds.source_endpoint)))
        else:
            parts.append("Endpoint: NOT SET")

        t = current_theme()
        color = t["green"] if creds.is_online_ready else t["orange"]
        self.cred_status_label.config(text="  |  ".join(parts), fg=color)
        self._refresh_network_policy_label()
    except Exception as e:
        logger.warning("Could not load credential status: %s", e)
        self.cred_status_label.config(
            text="[WARN] Could not load status: {}".format(str(e)[:60]),
            fg=current_theme()["red"],
        )
        self._refresh_network_policy_label()

def _api_admintab__refresh_network_policy_label(self):
    """Show current gate policy in plain language."""
    t = current_theme()
    mode = getattr(self.config, "mode", "offline") if self.config else "offline"
    gate_mode = ""
    try:
        from src.core.network_gate import get_gate
        gate_mode = (get_gate().mode_name or "").strip().lower()
    except Exception:
        gate_mode = ""

    effective = gate_mode or mode
    if effective == "online":
        text = "Network Policy: Online Mode = Whitelist Only (approved endpoint + localhost)"
        color = t["green"]
    else:
        text = "Network Policy: Offline Mode = Localhost Only (internet blocked)"
        color = t["gray"]
    if gate_mode and gate_mode != mode:
        text = "{} | Effective Gate: {}".format(text, gate_mode.upper())
        color = t["orange"]
    self.network_policy_label.config(text=text, fg=color)

def _api_admintab__on_save_credentials(self):
    """Save endpoint and API key to credential manager."""
    from src.gui.panels.api_admin_tab import (
        validate_endpoint, store_endpoint, store_api_key,
        invalidate_credential_cache,
    )
    t = current_theme()
    endpoint = self.endpoint_var.get().strip()
    key = self.key_var.get().strip()
    if not endpoint and not key:
        self.cred_status_label.config(
            text="[WARN] Nothing to save -- both fields are empty.",
            fg=t["orange"])
        return
    errors = []
    if endpoint:
        try:
            endpoint = validate_endpoint(endpoint)
            store_endpoint(endpoint)
            self.endpoint_var.set(endpoint)
        except Exception as e:
            errors.append("Endpoint: {}".format(str(e)[:60]))
    if key:
        try:
            store_api_key(key)
        except Exception as e:
            errors.append("Key: {}".format(str(e)[:60]))
    if errors:
        self.cred_status_label.config(
            text="[FAIL] {}".format("; ".join(errors)), fg=t["red"])
    else:
        self.cred_status_label.config(
            text="[OK] Credentials saved to Credential Manager.",
            fg=t["green"])
        invalidate_credential_cache()
        try:
            from src.core.llm_router import invalidate_deployment_cache
            invalidate_deployment_cache()
        except Exception:
            logger.debug("Deployment cache invalidation skipped", exc_info=True)
        try:
            app = getattr(self, "_app", None)
            live_router = None
            if app is not None:
                live_router = getattr(getattr(app, "query_engine", None), "llm_router", None)
                if live_router is None:
                    live_router = getattr(app, "router", None)
            if (
                live_router is not None
                and getattr(self.config, "mode", "offline") == "online"
            ):
                api_router = getattr(live_router, "api", None)
                if api_router is not None:
                    try:
                        client = getattr(api_router, "client", None)
                        if client is not None and hasattr(client, "close"):
                            client.close()
                    except Exception:
                        logger.debug("Live API SDK client close skipped", exc_info=True)
                    try:
                        http_client = getattr(api_router, "http_api_client", None)
                        if http_client is not None and hasattr(http_client, "close"):
                            http_client.close()
                    except Exception:
                        logger.debug("Live API HTTP fallback close skipped", exc_info=True)
                live_router.api = None
                live_router.last_error = ""
        except Exception:
            logger.debug("Live API router invalidation skipped", exc_info=True)
        self._refresh_credential_status()

def _api_admintab__on_test_connection(self):
    """Test API connection in a background thread."""
    t = current_theme()
    endpoint = self.endpoint_var.get().strip()
    key = self.key_var.get().strip()
    if not endpoint or not key:
        self.cred_status_label.config(
            text="[WARN] Enter endpoint and key before testing.",
            fg=t["orange"])
        return
    self.test_btn.config(state=tk.DISABLED)
    self.cred_status_label.config(text="Testing connection...", fg=t["gray"])
    threading.Thread(target=self._do_test_connection,
                     args=(endpoint, key), daemon=True).start()

def _api_admintab__do_test_connection(self, endpoint, key):
    """Background thread: verify the endpoint by fetching its model list.

    A successful model fetch proves the endpoint URL is correct and the
    API key has valid permissions.  As a bonus, the fetched models are
    forwarded to the model selection panel so the admin sees them
    immediately without clicking Refresh again.
    """
    from src.gui.helpers.safe_after import safe_after
    from src.gui.panels.api_admin_tab import (
        validate_endpoint, store_endpoint, store_api_key,
        invalidate_credential_cache, resolve_credentials,
    )
    try:
        # Test what the app will really use: persist creds, resolve fresh,
        # then run provider-aware discovery (Azure deployments or /models).
        from src.core.llm_router import (
            invalidate_deployment_cache,
            refresh_deployments,
            _build_httpx_client,
            _is_azure_endpoint,
        )
        endpoint = validate_endpoint(endpoint)
        store_endpoint(endpoint)
        store_api_key(key)
        invalidate_credential_cache()
        creds = resolve_credentials(use_cache=False)
        # Ensure endpoint probe runs with online gate policy, using the
        # same allowlist config as normal online query traffic.
        try:
            from src.core.network_gate import configure_gate
            configure_gate(
                mode="online",
                api_endpoint=creds.endpoint or endpoint,
                allowed_prefixes=getattr(
                    getattr(self.config, "api", None),
                    "allowed_endpoint_prefixes", [],
                ) if self.config else [],
            )
        except Exception:
            pass
        cfg_api = getattr(self.config, "api", None)
        cfg_dep = (getattr(cfg_api, "deployment", "") or "").strip() if cfg_api else ""
        cfg_model = (getattr(cfg_api, "model", "") or "").strip() if cfg_api else ""
        cfg_ver = (getattr(cfg_api, "api_version", "") or "").strip() if cfg_api else ""
        cfg_provider = (getattr(cfg_api, "provider", "") or "").strip() if cfg_api else ""

        if not creds.has_endpoint or not creds.has_key:
            safe_after(
                self, 0, self._test_failed,
                "Credentials not stored/resolved correctly",
            )
            return

        # Stage 1: connectivity/auth probe with explicit HTTP status.
        probe_ok, probe_msg = self._probe_online_endpoint(
            creds.endpoint or endpoint,
            creds.api_key or key,
            creds.api_version or "2024-02-02",
            _build_httpx_client,
            _is_azure_endpoint,
        )
        if not probe_ok:
            if "HTTP 500" in probe_msg:
                # Some Azure environments block/alter deployment listing
                # but still allow chat completions. Try a direct model call.
                chat_ok, chat_msg = self._probe_online_chat(
                    creds,
                    deployment_override=(cfg_dep or cfg_model),
                    api_version_override=cfg_ver,
                    provider_override=cfg_provider,
                )
                if chat_ok:
                    safe_after(
                        self, 0, self._test_done, [], 0,
                        chat_msg + " | Deployment listing unavailable",
                    )
                    return
                # Keep this as a warning, not a hard fail. In many
                # enterprise Azure environments, deployment listing
                # returns 500 while chat calls remain the real signal.
                safe_after(
                    self, 0, self._test_warn,
                    "{} | {}".format(probe_msg, chat_msg),
                )
                return
            safe_after(self, 0, self._test_failed, probe_msg)
            return

        # Stage 2: model/deployment discovery (may legitimately return 0).
        invalidate_deployment_cache()
        deployments = refresh_deployments()
        if deployments:
            models = self._deployments_to_models(deployments)
            safe_after(
                self, 0, self._test_done, models, len(deployments), probe_msg
            )
        else:
            safe_after(
                self, 0, self._test_done, [], 0,
                probe_msg + " | Connected, but no deployments visible",
            )
    except Exception as e:
        safe_after(self, 0, self._test_failed, str(e)[:80])

def _api_admintab__probe_online_endpoint(
    self, endpoint, api_key, api_version, client_factory, is_azure_endpoint,
):
    """Probe endpoint with provider-appropriate auth and return status text."""
    try:
        ep = (endpoint or "").rstrip("/")
        if is_azure_endpoint(ep):
            base = re.split(r"/openai/|\?", ep, maxsplit=1)[0]
            url = f"{base}/openai/deployments?api-version={api_version}"
            with client_factory(timeout=10) as client:
                resp = client.get(
                    url,
                    headers={
                        "api-key": api_key,
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 200:
                return True, "Connected (Azure endpoint reachable)"
            if resp.status_code in (401, 403):
                return False, f"Auth/RBAC failed (HTTP {resp.status_code})"
            if resp.status_code == 404:
                return False, "Endpoint/API version not valid for Azure deployment list (HTTP 404)"
            return False, f"Azure probe failed (HTTP {resp.status_code})"

        url = f"{ep}/models"
        with client_factory(timeout=10) as client:
            resp = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code == 200:
            return True, "Connected (/models reachable)"
        if resp.status_code in (401, 403):
            return False, f"Auth failed (HTTP {resp.status_code})"
        if resp.status_code == 404:
            return False, "Endpoint path is not OpenAI-compatible /models (HTTP 404)"
        return False, f"Probe failed (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"Connection probe error: {type(e).__name__}: {e}"

def _api_admintab__probe_online_chat(
    self,
    creds,
    deployment_override="",
    api_version_override="",
    provider_override="",
):
    """Fallback probe: run one minimal online completion call."""
    try:
        from src.core.llm_router import APIRouter

        dep = (
            deployment_override
            or getattr(creds, "deployment", "")
            or getattr(getattr(self.config, "api", None), "deployment", "")
            or getattr(getattr(self.config, "api", None), "model", "")
            or ""
        )
        ver = (
            api_version_override
            or getattr(creds, "api_version", "")
            or getattr(getattr(self.config, "api", None), "api_version", "")
            or ""
        )
        provider = (
            provider_override
            or getattr(creds, "provider", "")
            or getattr(getattr(self.config, "api", None), "provider", "")
            or ""
        )
        api = APIRouter(
            self.config,
            creds.api_key or "",
            endpoint=creds.endpoint or "",
            deployment_override=dep,
            api_version_override=ver,
            provider_override=provider,
        )

        # Azure requires a deployment name for chat completions.
        if getattr(api, "is_azure", False) and not getattr(api, "deployment", ""):
            return False, "Azure chat probe needs deployment name (not set)"

        resp = api.query("Reply with OK.")
        if resp and (resp.text or "").strip():
            return True, "Connected (chat completion probe succeeded)"

        err = getattr(api, "last_error", "") or "unknown error"
        return False, "Chat probe failed: {}".format(str(err)[:120])
    except Exception as e:
        return False, "Chat probe error: {}: {}".format(type(e).__name__, str(e)[:80])

def _api_admintab__deployments_to_models(self, deployments):
    """Convert deployment names into ModelSelectionPanel row dicts."""
    from scripts._model_meta import lookup_known_model
    out = []
    for dep in deployments:
        kb = lookup_known_model(dep) or {}
        out.append({
            "id": dep,
            "ctx": kb.get("ctx", 0),
            "price_in": kb.get("price_in", 0),
            "price_out": kb.get("price_out", 0),
            "tier_eng": kb.get("tier_eng", 45),
            "tier_gen": kb.get("tier_gen", 45),
            "source": "discovery",
        })
    return out

def _api_admintab__test_done(self, models, total, detail=""):
    """Main-thread callback: connection test succeeded."""
    t = current_theme()
    msg = detail or "Connected"
    if total > 0:
        msg = "{} -- {} models available.".format(msg, total)
    else:
        msg = "{} -- 0 models/deployments listed.".format(msg)
    self.cred_status_label.config(text="[OK] {}".format(msg), fg=t["green"])
    self.test_btn.config(state=tk.NORMAL)
    self._model_panel.set_models(models)

def _api_admintab__test_failed(self, msg):
    """Main-thread callback: connection test failed."""
    t = current_theme()
    self.cred_status_label.config(text="[FAIL] {}".format(msg), fg=t["red"])
    self.test_btn.config(state=tk.NORMAL)

def _api_admintab__test_warn(self, msg):
    """Main-thread callback: connection test has non-fatal warnings."""
    t = current_theme()
    self.cred_status_label.config(text="[WARN] {}".format(msg), fg=t["orange"])
    self.test_btn.config(state=tk.NORMAL)

def _api_admintab__on_clear_credentials(self):
    """Wipe all stored credentials from Windows Credential Manager."""
    from src.gui.panels.api_admin_tab import clear_credentials
    t = current_theme()
    try:
        clear_credentials()
        self.endpoint_var.set("")
        self.key_var.set("")
        self._model_panel.set_models([])
        self.cred_status_label.config(
            text="[OK] All credentials cleared.", fg=t["green"])
    except Exception as e:
        self.cred_status_label.config(
            text="[FAIL] {}".format(str(e)[:60]), fg=t["red"])

def _api_admintab__build_security_section(self, t):
    """Build security toggle for PII scrubbing.

    One Checkbutton that controls whether emails, phone numbers,
    SSNs, credit cards, and IP addresses are stripped from prompts
    before they leave the machine via online API calls.
    """
    frame = tk.LabelFrame(
        self._inner, text="Security & Privacy", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._security_frame = frame

    row = tk.Frame(frame, bg=t["panel_bg"])
    row.pack(fill=tk.X, pady=4)

    # Read current value from config
    security = getattr(self.config, "security", None)
    initial = getattr(security, "pii_sanitization", True) if security else True

    self._pii_var = tk.BooleanVar(value=initial)
    self._pii_cb = tk.Checkbutton(
        row, text="PII Scrubber", variable=self._pii_var,
        command=self._on_pii_toggle,
        bg=t["panel_bg"], fg=t["fg"],
        selectcolor=t["input_bg"], activebackground=t["panel_bg"],
        activeforeground=t["fg"], font=FONT,
    )
    self._pii_cb.pack(side=tk.LEFT)

    self._pii_hint = tk.Label(
        row,
        text="Strips emails, phones, SSNs before sending to online APIs",
        anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._pii_hint.pack(side=tk.LEFT, padx=(8, 0))

def _api_admintab__on_pii_toggle(self):
    """Write PII sanitization toggle to config and persist to YAML."""
    value = self._pii_var.get()

    # Update live config object
    security = getattr(self.config, "security", None)
    if security:
        security.pii_sanitization = value

    # Persist to config/config.yaml (single config authority)
    try:
        from src.core.config import save_config_field
        save_config_field("security.pii_sanitization", value)
    except Exception as e:
        logger.warning("pii_toggle_save_failed: %s", e)

def _api_admintab__build_troubleshoot_section(self, t):
    """Build quick verification controls (manual, on-demand)."""
    frame = tk.LabelFrame(
        self._inner, text="Quick Troubleshoot", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._trouble_frame = frame

    row = tk.Frame(frame, bg=t["panel_bg"])
    row.pack(fill=tk.X, pady=(0, 4))

    self._verify_btn = tk.Button(
        row, text="Run Quick Verification",
        command=self._on_run_quick_verify,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self._verify_btn.pack(side=tk.LEFT)
    bind_hover(self._verify_btn)

    self._verify_status = tk.Label(
        row, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._verify_status.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

    self._verify_text = tk.Text(
        frame, height=7, wrap=tk.WORD, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=1,
        state=tk.DISABLED,
    )
    self._verify_text.pack(fill=tk.X)


def _api_admintab__build_resource_monitor_section(self, t):
    """Build resource monitoring line (RAM, CPU, optional GPU)."""
    frame = tk.LabelFrame(
        self._inner, text="Resource Monitor", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._resource_monitor_label = tk.Label(
        frame, text="Gathering resource usage...", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT,
    )
    self._resource_monitor_label.pack(fill=tk.X)

    self._resource_monitor_after_id = None
    self._refresh_resource_section()


def _api_admintab__build_query_debug_section(self, t):
    """Build an Admin-only retrieval/query trace viewer for development."""
    frame = tk.LabelFrame(
        self._inner, text="Retrieval Debug", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._query_debug_frame = frame

    row = tk.Frame(frame, bg=t["panel_bg"])
    row.pack(fill=tk.X, pady=(0, 4))

    self._query_debug_refresh_btn = tk.Button(
        row, text="Refresh Latest",
        command=self._refresh_query_debug_from_app,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self._query_debug_refresh_btn.pack(side=tk.LEFT)
    bind_hover(self._query_debug_refresh_btn)

    self._query_debug_clear_btn = tk.Button(
        row, text="Clear",
        command=self._clear_query_debug_trace,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
    )
    self._query_debug_clear_btn.pack(side=tk.LEFT, padx=(8, 0))
    bind_hover(self._query_debug_clear_btn)

    self._query_debug_status = tk.Label(
        row, text="No query trace captured yet.", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._query_debug_status.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

    self._query_debug_text = tk.Text(
        frame, height=20, wrap=tk.WORD, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=1,
        state=tk.DISABLED,
    )
    self._query_debug_text.pack(fill=tk.X)
    self._set_query_debug_text("No query trace captured yet.\n")
    self._refresh_query_debug_from_app()


def _api_admintab__refresh_query_debug_from_app(self):
    """Reload the latest query trace from the live app shell."""
    trace = getattr(self._app, "_last_query_trace", None)
    if not trace:
        self._query_debug_status.config(
            text="No query trace captured yet.",
            fg=current_theme()["gray"],
        )
        self._set_query_debug_text("No query trace captured yet.\n")
        return
    self._update_query_debug_trace(trace)


def _api_admintab__update_query_debug_trace(self, trace):
    """Render a new query trace into the debug text panel."""
    t = current_theme()
    text = format_query_trace_text(trace)
    retrieval = trace.get("retrieval", {})
    counts = retrieval.get("counts", {})
    decision = trace.get("decision", {}).get("path", "")
    status = "{} | {} | final hits={} | latency={} ms".format(
        str(trace.get("mode", "") or "").upper(),
        decision or "unknown",
        counts.get("final_hits", 0),
        trace.get("result", {}).get("latency_ms", 0.0),
    )
    self._query_debug_status.config(text=status, fg=t["gray"])
    self._set_query_debug_text(text)


def _api_admintab__clear_query_debug_trace(self):
    """Forget the cached latest query trace from the app shell."""
    if hasattr(self._app, "_last_query_trace"):
        self._app._last_query_trace = None
    self._query_debug_status.config(
        text="No query trace captured yet.",
        fg=current_theme()["gray"],
    )
    self._set_query_debug_text("No query trace captured yet.\n")


def _api_admintab__set_query_debug_text(self, text):
    """Set retrieval debug text box content safely."""
    self._query_debug_text.config(state=tk.NORMAL)
    self._query_debug_text.delete("1.0", tk.END)
    self._query_debug_text.insert("1.0", text)
    self._query_debug_text.config(state=tk.DISABLED)


def _api_admintab__refresh_resource_section(self):
    if not hasattr(self, "_resource_monitor_label"):
        return
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    gpu = _query_gpu_status()
    cpu_text = f"{cpu:.0f}% CPU"
    ram_text = f"{ram.percent:.0f}% RAM ({_format_bytes(ram.used)} / {_format_bytes(ram.total)})"
    text = f"{cpu_text} | {ram_text} | {gpu}"
    self._resource_monitor_label.config(
        text=text,
        fg=_resource_color(cpu, ram.percent),
    )
    if self._resource_monitor_after_id is not None:
        self.after_cancel(self._resource_monitor_after_id)
    self._resource_monitor_after_id = self.after(5000, self._refresh_resource_section)


# --- Module-level helper utilities for resource monitor ---

def _resource_color(cpu_pct, ram_pct):
    if cpu_pct > 90 or ram_pct > 90:
        return current_theme()["red"]
    if cpu_pct > 75 or ram_pct > 80:
        return current_theme()["orange"]
    return current_theme()["green"]


def _format_bytes(value):
    units = ["B", "KB", "MB", "GB"]
    i = 0
    v = float(value)
    while v >= 1024 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    return f"{v:,.1f}{units[i]}"


def _query_gpu_status():
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if output.returncode == 0:
            usage = output.stdout.strip().splitlines()[0]
            used, total = [part.strip() for part in usage.split(",")]
            return f"GPU {used}/{total} MiB"
    except Exception:
        pass
    return "GPU N/A"


def _api_admintab__on_run_quick_verify(self):
    """Start quick verification in a background thread."""
    t = current_theme()
    self._verify_btn.config(state=tk.DISABLED)
    self._verify_status.config(text="Running checks...", fg=t["gray"])
    self._set_verify_text("Running quick verification...\n")
    threading.Thread(target=self._do_quick_verify, daemon=True).start()

def _api_admintab__do_quick_verify(self):
    """Background thread: run fast wiring checks used for troubleshooting."""
    from src.gui.helpers.safe_after import safe_after
    from src.gui.panels.api_admin_tab import (
        invalidate_credential_cache, resolve_credentials,
    )

    checks = []
    started = time.time()

    def _ok(msg):
        """Plain-English: This function handles ok."""
        checks.append(("OK", msg))

    def _warn(msg):
        """Plain-English: This function handles warn."""
        checks.append(("WARN", msg))

    def _fail(msg):
        """Plain-English: This function handles fail."""
        checks.append(("FAIL", msg))

    try:
        mode = getattr(self.config, "mode", "offline")
        _ok("Mode: {}".format(mode))

        # Path integrity checks
        paths = getattr(self.config, "paths", None)
        source = getattr(paths, "source_folder", "") if paths else ""
        db = getattr(paths, "database", "") if paths else ""
        dl = getattr(paths, "download_folder", "") if paths else ""

        if source and os.path.isdir(source):
            _ok("Source path exists")
        else:
            _warn("Source path missing or not set")

        if db:
            db_dir = os.path.dirname(db)
            if os.path.isdir(db_dir):
                _ok("Index directory exists")
            else:
                _warn("Index directory missing")
            if os.path.isfile(db):
                _ok("Index DB file exists")
            else:
                _warn("Index DB file missing")
        else:
            _warn("Index DB path not set")

        emb = getattr(paths, "embeddings_cache", "") if paths else ""
        if emb and os.path.isdir(emb):
            _ok("Embeddings cache exists")
        elif emb:
            _warn("Embeddings cache folder missing")

        if dl:
            if os.path.isdir(dl):
                _ok("Download folder exists")
            else:
                _warn("Download folder missing")

        # Credential + endpoint checks
        invalidate_credential_cache()
        creds = resolve_credentials(use_cache=False)
        if creds.has_key:
            _ok("API key resolved ({})".format(creds.source_key or "unknown"))
        else:
            _warn("API key not resolved")
        if creds.has_endpoint:
            _ok("API endpoint resolved ({})".format(creds.source_endpoint or "unknown"))
        else:
            _warn("API endpoint not resolved")

        # Backend checks by mode
        if mode == "online":
            if creds.has_key and creds.has_endpoint:
                try:
                    from src.core.llm_router import (
                        invalidate_deployment_cache,
                        refresh_deployments,
                    )
                    invalidate_deployment_cache()
                    deps = refresh_deployments()
                    _ok("Online discovery returned {} deployments/models".format(len(deps)))
                except Exception as e:
                    _fail("Online discovery failed: {}".format(str(e)[:80]))
            else:
                _fail("Online mode active but credentials are incomplete")
        else:
            try:
                from src.core.llm_router import _build_httpx_client
                base = sanitize_ollama_base_url(
                    getattr(getattr(self.config, "ollama", None), "base_url", "")
                )
                with _build_httpx_client(timeout=5, localhost_only=True) as client:
                    resp = client.get(base, timeout=5)
                if resp.status_code == 200:
                    _ok("Ollama reachable at {}".format(base))
                else:
                    _warn("Ollama probe HTTP {}".format(resp.status_code))
            except Exception as e:
                _warn("Ollama probe failed: {}".format(str(e)[:80]))

    except Exception as e:
        _fail("Verifier error: {}: {}".format(type(e).__name__, str(e)[:80]))

    elapsed_ms = int((time.time() - started) * 1000)
    safe_after(self, 0, self._on_quick_verify_done, checks, elapsed_ms)

def _api_admintab__on_quick_verify_done(self, checks, elapsed_ms):
    """Render quick verification results in the admin tab."""
    t = current_theme()
    ok_n = sum(1 for c, _ in checks if c == "OK")
    warn_n = sum(1 for c, _ in checks if c == "WARN")
    fail_n = sum(1 for c, _ in checks if c == "FAIL")
    if fail_n > 0:
        color = t["red"]
    elif warn_n > 0:
        color = t["orange"]
    else:
        color = t["green"]
    self._verify_status.config(
        text="{} OK | {} WARN | {} FAIL | {} ms".format(
            ok_n, warn_n, fail_n, elapsed_ms,
        ),
        fg=color,
    )
    lines = []
    for level, msg in checks:
        lines.append("[{}] {}".format(level, msg))
    self._set_verify_text("\n".join(lines))
    self._verify_btn.config(state=tk.NORMAL)

def _api_admintab__set_verify_text(self, text):
    """Set troubleshoot text box content safely."""
    self._verify_text.config(state=tk.NORMAL)
    self._verify_text.delete("1.0", tk.END)
    self._verify_text.insert("1.0", text)
    self._verify_text.config(state=tk.DISABLED)

def _api_admintab__build_offline_runtime_section(self, t):
    """Build offline runtime controls for Ollama."""
    frame = tk.LabelFrame(
        self._inner, text="Offline Runtime (Ollama)", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(4, 8))
    self._offline_runtime_frame = frame

    tk.Label(
        frame,
        text="Default is 4096. Increase only when hardware capacity is validated.",
        anchor=tk.W, justify=tk.LEFT, wraplength=760,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(0, 6))

    ollama = getattr(self.config, "ollama", None)
    self.ollama_context_var = tk.StringVar(
        value=str(getattr(ollama, "context_window", 4096) if ollama else 4096)
    )
    self.persist_ollama_context_var = tk.BooleanVar(value=False)

    row_ctx = tk.Frame(frame, bg=t["panel_bg"])
    row_ctx.pack(fill=tk.X, pady=3)
    tk.Label(
        row_ctx, text="Context window:", width=14, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)
    self.ollama_context_entry = tk.Entry(
        row_ctx, textvariable=self.ollama_context_var, width=12, font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    )
    self.ollama_context_entry.pack(side=tk.LEFT, padx=(4, 8))
    tk.Label(
        row_ctx, text="(1024-131072)", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(side=tk.LEFT)

    self.persist_ollama_context_cb = tk.Checkbutton(
        frame, text="Set as default",
        variable=self.persist_ollama_context_var,
        bg=t["panel_bg"], fg=t["fg"],
        selectcolor=t["input_bg"], activebackground=t["panel_bg"],
        activeforeground=t["fg"], font=FONT_SMALL,
    )
    self.persist_ollama_context_cb.pack(anchor=tk.W, pady=(2, 2))

    self.save_offline_runtime_btn = tk.Button(
        frame, text="Save Offline Runtime", command=self._on_save_offline_runtime,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self.save_offline_runtime_btn.pack(anchor=tk.W, pady=(2, 2))
    bind_hover(self.save_offline_runtime_btn)

    self.offline_runtime_status_label = tk.Label(
        frame, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self.offline_runtime_status_label.pack(fill=tk.X, pady=(2, 0))

def _api_admintab__on_save_offline_runtime(self):
    """Apply offline runtime settings with optional persistence."""
    t = current_theme()
    try:
        context_window = int((self.ollama_context_var.get() or "").strip())
    except Exception:
        self.offline_runtime_status_label.config(
            text="[FAIL] Context window must be an integer.",
            fg=t["red"],
        )
        return

    if context_window < 1024 or context_window > 131072:
        self.offline_runtime_status_label.config(
            text="[FAIL] context_window must be between 1024 and 131072.",
            fg=t["red"],
        )
        return

    ollama = getattr(self.config, "ollama", None)
    if not ollama:
        self.offline_runtime_status_label.config(
            text="[FAIL] Ollama config section is missing.",
            fg=t["red"],
        )
        return

    ollama.context_window = context_window

    if self.persist_ollama_context_var.get():
        try:
            from src.gui.helpers.mode_tuning import update_mode_setting

            update_mode_setting(self.config, "offline", "context_window", context_window)
            self.offline_runtime_status_label.config(
                text="[OK] Context window set to {} and saved as default.".format(
                    context_window
                ),
                fg=t["green"],
            )
        except Exception as e:
            self.offline_runtime_status_label.config(
                text="[FAIL] {}".format(str(e)[:80]),
                fg=t["red"],
            )
    else:
        self.offline_runtime_status_label.config(
            text="[OK] Context window set to {} (session only).".format(
                context_window
            ),
            fg=t["green"],
        )

def _api_admintab__apply_mode_state(self):
    """Refresh labels while keeping Admin controls editable in both modes."""
    t = current_theme()
    mode = getattr(self.config, "mode", "offline") if self.config else "offline"

    for widget in (getattr(self, "endpoint_entry", None), getattr(self, "key_entry", None)):
        if widget is not None:
            widget.config(state=tk.NORMAL, fg=t["input_fg"])
    for btn in (
        getattr(self, "save_cred_btn", None),
        getattr(self, "test_btn", None),
        getattr(self, "clear_cred_btn", None),
    ):
        if btn is not None:
            btn.config(state=tk.NORMAL)
    if hasattr(self, "_pii_cb"):
        self._pii_cb.config(state=tk.NORMAL)
    if hasattr(self, "_offline_model_panel"):
        self._offline_model_panel.uc_dropdown.config(state="readonly")
        self._offline_model_panel._populate()
    self._refresh_credential_status()
    current_text = self.cred_status_label.cget("text")
    if current_text:
        self.cred_status_label.config(
            text=current_text + "  |  Runtime mode: {}".format(str(mode).upper()),
            fg=t["gray"],
        )
    self._refresh_network_policy_label()

def _api_admintab__build_chunking_section(self, t):
    """Build chunking controls kept separate from query-time tuning.

    Chunking changes affect indexing output (future chunks), not live
    query behavior. Re-index is required for changes to take effect.
    """
    frame = tk.LabelFrame(
        self._inner, text="Chunking (Re-Index Required)", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(4, 8))
    self._chunking_frame = frame

    tk.Label(
        frame,
        text="These settings apply to future indexing only. Re-index after changes.",
        anchor=tk.W, justify=tk.LEFT, wraplength=760,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(0, 6))

    chunking = getattr(self.config, "chunking", None)
    self.chunk_size_var = tk.StringVar(
        value=str(getattr(chunking, "chunk_size", 1200))
    )
    self.overlap_var = tk.StringVar(
        value=str(getattr(chunking, "overlap", 200))
    )

    row_cs = tk.Frame(frame, bg=t["panel_bg"])
    row_cs.pack(fill=tk.X, pady=3)
    tk.Label(
        row_cs, text="Chunk size:", width=14, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)
    tk.Entry(
        row_cs, textvariable=self.chunk_size_var, width=10, font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    ).pack(side=tk.LEFT, padx=(4, 0))

    row_ov = tk.Frame(frame, bg=t["panel_bg"])
    row_ov.pack(fill=tk.X, pady=3)
    tk.Label(
        row_ov, text="Overlap:", width=14, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)
    tk.Entry(
        row_ov, textvariable=self.overlap_var, width=10, font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    ).pack(side=tk.LEFT, padx=(4, 0))

    btn_row = tk.Frame(frame, bg=t["panel_bg"])
    btn_row.pack(fill=tk.X, pady=(6, 2))
    self.save_chunking_btn = tk.Button(
        btn_row, text="Save Chunking", command=self._on_save_chunking,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self.save_chunking_btn.pack(side=tk.LEFT)
    bind_hover(self.save_chunking_btn)

    self.chunking_status_label = tk.Label(
        frame, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self.chunking_status_label.pack(fill=tk.X, pady=(2, 0))

def _api_admintab__on_save_chunking(self):
    """Validate + persist chunking fields to config and YAML."""
    t = current_theme()
    try:
        chunk_size = int(self.chunk_size_var.get().strip())
        overlap = int(self.overlap_var.get().strip())
    except Exception:
        self.chunking_status_label.config(
            text="[FAIL] Chunk size and overlap must be integers.",
            fg=t["red"],
        )
        return

    if chunk_size < 200 or chunk_size > 4000:
        self.chunking_status_label.config(
            text="[FAIL] chunk_size must be between 200 and 4000.",
            fg=t["red"],
        )
        return
    if overlap < 0 or overlap >= chunk_size:
        self.chunking_status_label.config(
            text="[FAIL] overlap must be >= 0 and less than chunk_size.",
            fg=t["red"],
        )
        return

    chunking = getattr(self.config, "chunking", None)
    if chunking:
        chunking.chunk_size = chunk_size
        chunking.overlap = overlap

    try:
        from src.core.config import save_config_field
        save_config_field("chunking.chunk_size", chunk_size)
        save_config_field("chunking.overlap", overlap)
        self.chunking_status_label.config(
            text="[OK] Chunking saved (re-index required).",
            fg=t["green"],
        )
    except Exception as e:
        self.chunking_status_label.config(
            text="[FAIL] {}".format(str(e)[:80]),
            fg=t["red"],
        )

def _api_admintab__build_defaults_section(self, t):
    """Build admin defaults save/restore controls."""
    frame = tk.LabelFrame(
        self._inner, text="Admin Defaults", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(8, 16))
    self._defaults_frame = frame

    btn_row = tk.Frame(frame, bg=t["panel_bg"])
    btn_row.pack(fill=tk.X, pady=4)

    self.save_defaults_btn = tk.Button(
        btn_row, text="Save Current as Default",
        command=self._on_save_defaults,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    self.save_defaults_btn.pack(side=tk.LEFT, padx=(0, 8))
    bind_hover(self.save_defaults_btn)

    self.restore_defaults_btn = tk.Button(
        btn_row, text="Restore Defaults",
        command=self._on_restore_defaults,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
    )
    self.restore_defaults_btn.pack(side=tk.LEFT)
    bind_hover(self.restore_defaults_btn)

    self.defaults_status_label = tk.Label(
        frame, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self.defaults_status_label.pack(fill=tk.X, pady=(2, 0))
    self._refresh_defaults_status()

def _api_admintab__on_save_defaults(self):
    """Save the current system state as the admin baseline.

    This lets admins set up the system once and restore it after
    experiments or accidental changes. The baseline now lives in
    config/config.yaml so the admin GUI and YAML share one path.
    """
    t = current_theme()
    status_label = getattr(self, "defaults_status_label", None)
    try:
        from src.gui.helpers.mode_tuning import ModeTuningStore

        snapshot = ModeTuningStore().save_admin_defaults(self.config)
        if status_label is not None:
            status_label.config(
                text="[OK] Defaults saved at {}".format(snapshot["saved_at"]),
                fg=t["green"],
            )
        logger.info("Admin defaults saved to config/config.yaml")
    except Exception as e:
        if status_label is not None:
            status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"],
            )
        else:
            raise

def _api_admintab__on_restore_defaults(self):
    """Restore all settings from the previously saved admin defaults.

    Reads the YAML-backed admin defaults, writes values back into the live config,
    syncs the tuning tab sliders, and refreshes the path entries --
    so the entire UI reflects the restored state immediately.
    """
    t = current_theme()
    status_label = getattr(self, "defaults_status_label", None)
    try:
        from src.gui.helpers.mode_tuning import ModeTuningStore

        store = ModeTuningStore()
        snapshot = store.restore_admin_defaults(self.config)
        if snapshot is None:
            if status_label is not None:
                status_label.config(
                    text="[WARN] No defaults saved yet. Save defaults first.",
                    fg=t["orange"],
                )
            return
        p_snap = snapshot.get("paths", {})
        c_snap = snapshot.get("chunking", {})

        # Sync tuning tab sliders
        sv = self._app._views.get("settings") if hasattr(self._app, "_views") else None
        if sv and hasattr(sv, "_tuning_tab"):
            sv._tuning_tab._sync_sliders_to_config()

        # Sync path entries
        pp = getattr(self, "_paths_panel", None)
        if pp and p_snap:
            pp.source_var.set(p_snap.get("source_folder", ""))
            db = p_snap.get("database", "")
            pp.index_var.set(os.path.dirname(db) if db else "")
            pp._refresh_info()

        if hasattr(self, "chunk_size_var") and hasattr(self, "overlap_var"):
            c_snap = snapshot.get("chunking", {})
            if c_snap:
                self.chunk_size_var.set(str(c_snap.get("chunk_size", "")))
                self.overlap_var.set(str(c_snap.get("overlap", "")))
        if hasattr(self, "ollama_context_var"):
            self.ollama_context_var.set(
                str(snapshot.get("ollama", {}).get("context_window", MODE_TUNED_DEFAULTS["offline"]["context_window"]))
            )

        self._apply_mode_state()

        saved_at = snapshot.get("saved_at", "?")
        if status_label is not None:
            status_label.config(
                text="[OK] Defaults restored (saved {})".format(saved_at),
                fg=t["green"],
            )
        logger.info("Admin defaults restored from config/config.yaml")
    except Exception as e:
        if status_label is not None:
            status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"],
            )
        else:
            raise

def _api_admintab__refresh_defaults_status(self):
    """Show when defaults were last saved (or 'not saved yet')."""
    t = current_theme()
    status_label = getattr(self, "defaults_status_label", None)
    if status_label is None:
        return
    try:
        from src.gui.helpers.mode_tuning import ModeTuningStore

        snapshot = ModeTuningStore().get_admin_defaults()
    except Exception:
        snapshot = None

    if not snapshot:
        status_label.config(
            text="No defaults saved yet.", fg=t["gray"])
        return

    status_label.config(
        text="Last saved: {}".format(snapshot.get("saved_at", "unknown")),
        fg=t["gray"])

def _api_admintab_apply_theme(self, t):
    """Plain-English: This function handles apply theme."""
    self.configure(bg=t["panel_bg"])
    self._scroll.apply_theme({"bg": t["panel_bg"]})
    self._paths_panel.apply_theme(t)
    if hasattr(self, "_offline_model_panel"):
        self._offline_model_panel.apply_theme(t)
    self._model_panel.apply_theme(t)
    for frame_attr in (
        "_cred_frame", "_security_frame", "_chunking_frame",
        "_offline_runtime_frame", "_defaults_frame", "_query_debug_frame",
    ):
        frame = getattr(self, frame_attr, None)
        if frame:
            frame.configure(bg=t["panel_bg"], fg=t["accent"])
            _theme_widget(frame, t)


# ---------------------------------------------------------------------------
# Bind function -- attaches all methods to ApiAdminTab at import time
# ---------------------------------------------------------------------------

def bind_api_admin_tab_runtime_methods(cls) -> None:
    """Attach extracted ApiAdminTab methods at import time."""
    cls._build_dev_hidden_notice = _api_admintab__build_dev_hidden_notice
    cls._build_credentials_section = _api_admintab__build_credentials_section
    cls._toggle_key_visibility = _api_admintab__toggle_key_visibility
    cls._refresh_credential_status = _api_admintab__refresh_credential_status
    cls._refresh_network_policy_label = _api_admintab__refresh_network_policy_label
    cls._on_save_credentials = _api_admintab__on_save_credentials
    cls._on_test_connection = _api_admintab__on_test_connection
    cls._do_test_connection = _api_admintab__do_test_connection
    cls._probe_online_endpoint = _api_admintab__probe_online_endpoint
    cls._probe_online_chat = _api_admintab__probe_online_chat
    cls._deployments_to_models = _api_admintab__deployments_to_models
    cls._test_done = _api_admintab__test_done
    cls._test_failed = _api_admintab__test_failed
    cls._test_warn = _api_admintab__test_warn
    cls._on_clear_credentials = _api_admintab__on_clear_credentials
    cls._build_security_section = _api_admintab__build_security_section
    cls._on_pii_toggle = _api_admintab__on_pii_toggle
    cls._build_troubleshoot_section = _api_admintab__build_troubleshoot_section
    cls._build_query_debug_section = _api_admintab__build_query_debug_section
    cls._refresh_query_debug_from_app = _api_admintab__refresh_query_debug_from_app
    cls._update_query_debug_trace = _api_admintab__update_query_debug_trace
    cls._clear_query_debug_trace = _api_admintab__clear_query_debug_trace
    cls._set_query_debug_text = _api_admintab__set_query_debug_text
    cls._on_run_quick_verify = _api_admintab__on_run_quick_verify
    cls._do_quick_verify = _api_admintab__do_quick_verify
    cls._on_quick_verify_done = _api_admintab__on_quick_verify_done
    cls._set_verify_text = _api_admintab__set_verify_text
    cls._build_offline_runtime_section = _api_admintab__build_offline_runtime_section
    cls._on_save_offline_runtime = _api_admintab__on_save_offline_runtime
    cls._build_resource_monitor_section = _api_admintab__build_resource_monitor_section
    cls._refresh_resource_section = _api_admintab__refresh_resource_section
    cls._apply_mode_state = _api_admintab__apply_mode_state
    cls._build_chunking_section = _api_admintab__build_chunking_section
    cls._on_save_chunking = _api_admintab__on_save_chunking
    cls._build_defaults_section = _api_admintab__build_defaults_section
    cls._on_save_defaults = _api_admintab__on_save_defaults
    cls._on_restore_defaults = _api_admintab__on_restore_defaults
    cls._refresh_defaults_status = _api_admintab__refresh_defaults_status
    cls.apply_theme = _api_admintab_apply_theme
