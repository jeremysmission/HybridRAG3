# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the status bar part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Status Bar Panel (src/gui/panels/status_bar.py)
# ============================================================================
# Displays live system status: LLM backend, Ollama, and network gate state.
# Updates every 15 seconds via a background timer.
#
# CBIT (Continuous BIT) runs every 60 seconds after IBIT completes,
# checking database reachability, LLM backend, and disk space.
# If CBIT detects degradation the IBIT badge transitions from green
# to orange (partial) or red (critical).
#
# INTERNET ACCESS: NONE (reads local state only)
# ============================================================================

import tkinter as tk
import threading
import logging

from src.gui.theme import current_theme, FONT

logger = logging.getLogger(__name__)


class StatusBar(tk.Frame):
    """
    Bottom status bar showing LLM, Ollama, and Gate status.

    Updates every 15 seconds by calling router.get_status().
    """

    REFRESH_MS = 15000  # 15 seconds
    CBIT_MS = 60000     # 60 seconds -- continuous health check

    def __init__(self, parent, config, router=None):
        """Plain-English: This function handles init."""
        t = current_theme()
        super().__init__(parent, relief=tk.FLAT, bd=1,
                         bg=t["panel_bg"])
        self.config = config
        self.router = router
        self._stop_event = threading.Event()
        self._loading = True
        self._loading_dots = 0
        self._dot_timer_id = None
        self._cbit_timer_id = None
        self._refresh_timer_id = None
        self._cbit_results = None   # Latest CBIT results
        self._query_engine = None   # Set by _attach() for CBIT use
        self._init_error = None     # Set by _load_backends on failure

        self._build_widgets(t)

        # -- Start periodic refresh --
        self._schedule_refresh()

    def _build_widgets(self, t):
        """Build all child widgets with theme colors."""
        # -- Loading indicator (left-most) --
        self.loading_label = tk.Label(
            self, text="Loading...", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["orange"], font=FONT,
        )
        self.loading_label.pack(side=tk.LEFT)

        self.sep_loading = tk.Frame(self, width=1, bg=t["separator"])
        self.sep_loading.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # -- Model fallback warning (global visibility across tabs) --
        self.alert_label = tk.Label(
            self, text="", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["red"], font=FONT,
        )
        self.alert_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.sep_alert = tk.Frame(self, width=1, bg=t["separator"])
        self.sep_alert.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # -- Mode/Selection indicator --
        self.llm_label = tk.Label(
            self, text="Mode/Selection: Unknown", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["fg"], font=FONT,
            justify=tk.LEFT, wraplength=1,
        )
        self.llm_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.llm_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(120, e.width - 10)),
        )

        # -- Separator --
        self.sep1 = tk.Frame(self, width=1, bg=t["separator"])
        self.sep1.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # -- Backend health indicator --
        self.ollama_label = tk.Label(
            self, text="Backend Health: Unknown", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["fg"], font=FONT,
            justify=tk.LEFT, wraplength=1,
        )
        self.ollama_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ollama_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(120, e.width - 10)),
        )

        # -- Separator --
        self.sep2 = tk.Frame(self, width=1, bg=t["separator"])
        self.sep2.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # -- Active model indicator --
        self.sep3 = tk.Frame(self, width=1, bg=t["separator"])
        self.sep3.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        model_name = self._read_active_model()
        self.model_label = tk.Label(
            self, text="Active Model: {}".format(model_name), anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["fg"], font=FONT,
            justify=tk.LEFT, wraplength=1,
        )
        self.model_label.pack(side=tk.LEFT)
        self.model_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(120, e.width - 10)),
        )

        # -- Gate indicator (clickable) --
        self.gate_dot = tk.Label(self, text=" ", width=2, padx=4,
                                 bg=t["panel_bg"])
        self.gate_dot.pack(side=tk.LEFT, padx=(8, 4))

        self.gate_label = tk.Label(
            self, text="Gate: OFFLINE", anchor=tk.W,
            padx=4, pady=4, cursor="hand2",
            bg=t["panel_bg"], fg=t["gray"], font=FONT,
            justify=tk.LEFT, wraplength=1,
        )
        self.gate_label.pack(side=tk.LEFT, padx=(0, 8))
        self.gate_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(120, e.width - 10)),
        )
        self.gate_label.bind("<Button-1>", self._on_gate_click)

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["panel_bg"])
        self.loading_label.configure(bg=t["panel_bg"])
        if self._loading:
            self.loading_label.configure(fg=t["orange"])
        elif hasattr(self, "_ibit_results") and self._ibit_results:
            all_ok = all(r.ok for r in self._ibit_results)
            self.loading_label.configure(fg=t["green"] if all_ok else t["red"])
        else:
            self.loading_label.configure(fg=t["green"])
        self.sep_loading.configure(bg=t["separator"])
        self.alert_label.configure(bg=t["panel_bg"], fg=t["red"])
        self.sep_alert.configure(bg=t["separator"])
        self.llm_label.configure(bg=t["panel_bg"])
        self.ollama_label.configure(bg=t["panel_bg"])
        self.model_label.configure(bg=t["panel_bg"], fg=t["fg"])
        self.gate_label.configure(bg=t["panel_bg"])
        self.gate_dot.configure(bg=t["panel_bg"])
        self.sep1.configure(bg=t["separator"])
        self.sep2.configure(bg=t["separator"])
        self.sep3.configure(bg=t["separator"])
        # Refresh status to set correct colors
        self._refresh_status()

    def _schedule_refresh(self):
        """Schedule next status refresh."""
        if not self._stop_event.is_set():
            self._refresh_status()
            self._refresh_timer_id = self.after(
                self.REFRESH_MS, self._schedule_refresh
            )

    def _refresh_status(self):
        """Update all status indicators from current state."""
        try:
            self._update_gate_display()
            self._update_model_label()
            self._update_fallback_alert()
            if self.router:
                self._update_from_router()
            else:
                self._update_no_router()
        except Exception as e:
            logger.debug("Status bar refresh error: %s", e)

    def _update_fallback_alert(self):
        """Mirror query-panel fallback warning to status bar."""
        t = current_theme()
        try:
            app = self._find_app()
            qp = getattr(app, "query_panel", None) if app else None
            if qp is None:
                self.alert_label.config(text="", fg=t["red"])
                return
            text = getattr(qp, "primary_alert_var", None)
            msg = text.get().strip() if text else ""
            self.alert_label.config(text=msg, fg=t["red"] if msg else t["fg"])
        except Exception:
            self.alert_label.config(text="", fg=t["red"])

    def _update_from_router(self):
        """Update LLM and Ollama indicators from router status."""
        t = current_theme()
        try:
            status = self.router.get_status()
        except Exception as e:
            logger.debug("Router status error: %s", e)
            self.llm_label.config(text="Mode/Selection: Status Error", fg=t["fg"])
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["fg"])
            return

        # Mode/Selection summary line
        mode = status.get("mode", "offline")
        selector = self._read_selector_mode(mode)
        self.llm_label.config(
            text="Mode/Selection: {} | {}".format(mode.upper(), selector),
            fg=t["fg"],
        )

        # Backend health line (mode-aware)
        if mode == "online":
            if status.get("api_configured"):
                self.ollama_label.config(
                    text="Backend Health: Application Programming Interface (API) Ready",
                    fg=t["green"],
                )
            else:
                # If creds are present but runtime client isn't attached yet,
                # avoid a hard "not configured" false alarm.
                creds_present = False
                try:
                    from src.security.credentials import resolve_credentials
                    c = resolve_credentials(use_cache=True)
                    creds_present = bool(getattr(c, "has_key", False) and getattr(c, "has_endpoint", False))
                except Exception:
                    creds_present = False
                if creds_present:
                    self.ollama_label.config(
                        text="Backend Health: API Init Pending",
                        fg=t["orange"],
                    )
                else:
                    self.ollama_label.config(
                        text="Backend Health: API Not Configured",
                        fg=t["orange"],
                    )
        elif mode == "offline":
            ollama_up = status.get("ollama_available", False)
            if ollama_up:
                self.ollama_label.config(text="Backend Health: Ollama Ready", fg=t["green"])
            else:
                self.ollama_label.config(text="Backend Health: Ollama Offline", fg=t["gray"])
        else:
            self.ollama_label.config(text="Backend Health: Unknown Mode", fg=t["orange"])

    def _read_selector_mode(self, mode):
        """Best-effort selector mode detection from query panel state."""
        try:
            app = self._find_app()
            qp = getattr(app, "query_panel", None) if app else None
            if qp is None:
                return "AUTO"
            if mode == "online":
                mv = getattr(qp, "model_var", None)
                text = mv.get() if mv else ""
                return "AUTO" if "Auto" in text else "MANUAL"
            return "AUTO" if bool(getattr(qp, "_model_auto", True)) else "MANUAL"
        except Exception:
            return "AUTO"

    def set_init_error(self, error_text):
        """Store an init error message for display in status indicators."""
        self._init_error = error_text

    def _update_no_router(self):
        """Display when no router is available."""
        t = current_theme()
        if self._loading:
            self.llm_label.config(text="Mode/Selection: Loading...", fg=t["gray"])
            self.ollama_label.config(text="Backend Health: Loading...", fg=t["gray"])
        elif self._init_error:
            self.llm_label.config(
                text="Mode/Selection: Init Failed",
                fg=t["red"],
            )
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["gray"])
        else:
            self.llm_label.config(text="Mode/Selection: Not Initialized", fg=t["fg"])
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["gray"])

    def _update_gate_display(self):
        """Update gate indicator from config mode."""
        t = current_theme()
        mode = getattr(self.config, "mode", "offline")
        if mode not in ("online", "offline", "admin"):
            try:
                from src.core.network_gate import get_gate
                gate_mode = (get_gate().mode_name or "").strip().lower()
                if gate_mode:
                    mode = gate_mode
            except Exception:
                pass
        if mode == "online":
            self.gate_label.config(
                text="Gate: ONLINE | Policy: Whitelist Only",
                fg=t["green"],
            )
            self.gate_dot.config(bg=t["green"])
        else:
            self.gate_label.config(
                text="Gate: OFFLINE | Policy: Localhost Only",
                fg=t["gray"],
            )
            self.gate_dot.config(bg=t["gray"])

    def _on_gate_click(self, event=None):
        """Toggle gate mode when clicked. Delegates to parent app."""
        parent_app = self._find_app()
        if parent_app and hasattr(parent_app, "toggle_mode"):
            current = getattr(self.config, "mode", "offline")
            new_mode = "offline" if current == "online" else "online"
            parent_app.toggle_mode(new_mode)

    def _find_app(self):
        """Walk up widget tree to find the HybridRAGApp instance."""
        widget = self.master
        while widget is not None:
            if hasattr(widget, "toggle_mode"):
                return widget
            widget = getattr(widget, "master", None)
        return None

    def set_loading_stage(self, stage_text):
        """Update the loading indicator with the current stage."""
        t = current_theme()
        self._loading = True
        self._loading_dots = 0
        self.loading_label.config(text="Loading: {}".format(stage_text),
                                  fg=t["orange"])
        # Start dot animation if not already running
        if self._dot_timer_id is None:
            self._animate_dots()

    def set_ready(self):
        """Mark loading as complete -- show green Ready text."""
        t = current_theme()
        self._loading = False
        # Cancel dot animation
        if self._dot_timer_id is not None:
            self.after_cancel(self._dot_timer_id)
            self._dot_timer_id = None
        self.loading_label.config(text="Ready", fg=t["green"])

    def _animate_dots(self):
        """Cycle dots (. -> .. -> ...) on the loading label."""
        if not self._loading or self._stop_event.is_set():
            self._dot_timer_id = None
            return
        self._loading_dots = (self._loading_dots % 3) + 1
        current_text = self.loading_label.cget("text")
        # Strip trailing dots and re-add
        base = current_text.rstrip(".")
        self.loading_label.config(text=base + "." * self._loading_dots)
        self._dot_timer_id = self.after(500, self._animate_dots)

    # IBIT/CBIT wrappers keep this class readable while preserving
    # explicit method names expected by diagnostics and tests.
    # Theme note: IBIT in-progress uses t["accent"] blue.
    # Popup section label retained: "Continuous Health Check".
    def set_ibit_stage(self, check_name):
        return _ibit.set_ibit_stage(self, check_name)

    def set_ibit_result(self, passed, total, results=None):
        return _ibit.set_ibit_result(self, passed, total, results)

    def _show_ibit_detail(self, event=None):
        return _ibit._show_ibit_detail(self, event)

    @staticmethod
    def _render_check_rows(parent, results, t):
        return _ibit._render_check_rows(parent, results, t)

    def start_cbit(self, query_engine=None):
        return _ibit.start_cbit(self, query_engine)

    def _run_cbit(self):
        return _ibit._run_cbit(self)

    def _apply_cbit(self, results):
        return _ibit._apply_cbit(self, results)

    def _read_active_model(self):
        """Return active model/deployment based on current mode."""
        try:
            mode = getattr(self.config, "mode", "offline")
            if mode == "online":
                # Prefer live router status when available.
                if self.router:
                    try:
                        status = self.router.get_status()
                        dep = status.get("api_deployment", "")
                        if dep:
                            return dep
                    except Exception:
                        pass
                api = getattr(self.config, "api", None)
                if api:
                    dep = getattr(api, "deployment", "")
                    if dep:
                        return dep
                return "online (not set)"

            ollama = getattr(self.config, "ollama", None)
            if ollama:
                return getattr(ollama, "model", "unknown") or "unknown"
        except Exception:
            pass
        return "unknown"

    def _update_model_label(self):
        """Refresh the active model indicator from live config/router."""
        t = current_theme()
        mode = getattr(self.config, "mode", "offline")
        model = self._read_active_model()
        model_text = str(model)
        if len(model_text) > 36:
            model_text = model_text[:33] + "..."
        self.model_label.config(
            text="Active Model ({}): {}".format(mode, model_text),
            fg=t["fg"],
        )

    def force_refresh(self):
        """Immediately refresh all indicators."""
        self._refresh_status()
        self._update_model_label()

    def stop(self):
        """Stop the periodic refresh timer, dot animation, and CBIT timer."""
        self._stop_event.set()
        # Cancel refresh timer
        if self._refresh_timer_id is not None:
            try:
                self.after_cancel(self._refresh_timer_id)
            except Exception:
                pass
            self._refresh_timer_id = None
        # Cancel dot animation timer (F14 fix)
        if self._dot_timer_id is not None:
            try:
                self.after_cancel(self._dot_timer_id)
            except Exception:
                pass
            self._dot_timer_id = None
        # Cancel CBIT timer
        if self._cbit_timer_id is not None:
            try:
                self.after_cancel(self._cbit_timer_id)
            except Exception:
                pass
            self._cbit_timer_id = None


from src.gui.panels import status_bar_ibit as _ibit
