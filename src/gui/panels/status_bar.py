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
from src.gui.helpers.safe_after import safe_after

logger = logging.getLogger(__name__)


class StatusBar(tk.Frame):
    """
    Bottom status bar showing LLM, Ollama, and Gate status.

    Updates every 15 seconds by calling router.get_status().
    """

    REFRESH_MS = 15000  # 15 seconds
    CBIT_MS = 60000     # 60 seconds -- continuous health check

    def __init__(self, parent, config, router=None):
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

        # -- Mode/Selector indicator --
        self.llm_label = tk.Label(
            self, text="Mode/Selector: Unknown", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["fg"], font=FONT,
        )
        self.llm_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Separator --
        self.sep1 = tk.Frame(self, width=1, bg=t["separator"])
        self.sep1.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)

        # -- Backend health indicator --
        self.ollama_label = tk.Label(
            self, text="Backend Health: Unknown", anchor=tk.W,
            padx=8, pady=4, bg=t["panel_bg"], fg=t["fg"], font=FONT,
        )
        self.ollama_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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
        )
        self.model_label.pack(side=tk.LEFT)

        # -- Gate indicator (clickable) --
        self.gate_dot = tk.Label(self, text=" ", width=2, padx=4,
                                 bg=t["panel_bg"])
        self.gate_dot.pack(side=tk.LEFT, padx=(8, 4))

        self.gate_label = tk.Label(
            self, text="Gate: OFFLINE", anchor=tk.W,
            padx=4, pady=4, cursor="hand2",
            bg=t["panel_bg"], fg=t["gray"], font=FONT,
        )
        self.gate_label.pack(side=tk.LEFT, padx=(0, 8))
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
            self.after(self.REFRESH_MS, self._schedule_refresh)

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
            self.llm_label.config(text="Mode/Selector: Status Error", fg=t["fg"])
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["fg"])
            return

        # Mode/Selector summary line
        mode = status.get("mode", "offline")
        selector = self._read_selector_mode(mode)
        self.llm_label.config(
            text="Mode/Selector: {} | {}".format(mode.upper(), selector),
            fg=t["fg"],
        )

        # Backend health line (mode-aware)
        if mode == "online":
            if status.get("api_configured"):
                self.ollama_label.config(text="Backend Health: API Ready", fg=t["green"])
            else:
                self.ollama_label.config(text="Backend Health: API Not Configured", fg=t["orange"])
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
            self.llm_label.config(text="Mode/Selector: Loading...", fg=t["gray"])
            self.ollama_label.config(text="Backend Health: Loading...", fg=t["gray"])
        elif self._init_error:
            self.llm_label.config(
                text="Mode/Selector: Init Failed",
                fg=t["red"],
            )
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["gray"])
        else:
            self.llm_label.config(text="Mode/Selector: Not Initialized", fg=t["fg"])
            self.ollama_label.config(text="Backend Health: Unknown", fg=t["gray"])

    def _update_gate_display(self):
        """Update gate indicator from config mode."""
        t = current_theme()
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            self.gate_label.config(text="Gate: ONLINE", fg=t["green"])
            self.gate_dot.config(bg=t["green"])
        else:
            self.gate_label.config(text="Gate: OFFLINE", fg=t["gray"])
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

    # ----------------------------------------------------------------
    # IBIT display (replaces "Ready" with stepped check results)
    # ----------------------------------------------------------------

    def set_ibit_stage(self, check_name):
        """Show the current IBIT check name during verification.

        Uses accent blue (in-progress) with dot animation, matching
        the existing loading stage pattern but visually distinct.
        """
        t = current_theme()
        self._loading = True
        self._loading_dots = 0
        self.loading_label.config(
            text="IBIT: {}".format(check_name),
            fg=t["accent"],
        )
        if self._dot_timer_id is None:
            self._animate_dots()

    def set_ibit_result(self, passed, total, results=None):
        """Show final IBIT result as a persistent badge.

        Green for all-pass, red if any failures.  Clickable to show
        detail popup with individual check results.

        Parameters
        ----------
        passed : int
            Number of checks that passed.
        total : int
            Total number of checks.
        results : list[IBITCheck] or None
            Full results for the detail popup.
        """
        t = current_theme()
        self._loading = False
        if self._dot_timer_id is not None:
            self.after_cancel(self._dot_timer_id)
            self._dot_timer_id = None

        self._ibit_results = results

        if passed == total:
            text = "IBIT: {}/{} OK".format(passed, total)
            fg = t["green"]
        else:
            text = "IBIT: {}/{} FAIL".format(total - passed, total)
            fg = t["red"]

        self.loading_label.config(text=text, fg=fg, cursor="hand2")
        self.loading_label.bind("<Button-1>", self._show_ibit_detail)

    def _show_ibit_detail(self, event=None):
        """Show a tooltip-style popup with IBIT + CBIT check details."""
        ibit = getattr(self, "_ibit_results", None)
        cbit = getattr(self, "_cbit_results", None)
        if not ibit and not cbit:
            return

        t = current_theme()

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=t["border"])

        inner = tk.Frame(popup, bg=t["panel_bg"], padx=12, pady=8)
        inner.pack(padx=1, pady=1)

        # -- IBIT section --
        if ibit:
            tk.Label(
                inner, text="Initial Built-In Test",
                font=("Segoe UI", 11, "bold"),
                bg=t["panel_bg"], fg=t["fg"],
            ).pack(anchor="w", pady=(0, 4))
            self._render_check_rows(inner, ibit, t)

        # -- CBIT section (only if results exist) --
        if cbit:
            if ibit:
                tk.Frame(inner, height=1, bg=t["separator"]).pack(
                    fill="x", pady=6)
            tk.Label(
                inner, text="Continuous Health Check",
                font=("Segoe UI", 11, "bold"),
                bg=t["panel_bg"], fg=t["fg"],
            ).pack(anchor="w", pady=(0, 4))
            self._render_check_rows(inner, cbit, t)

        # -- Total timing --
        all_results = (ibit or []) + (cbit or [])
        total_ms = sum(r.elapsed_ms for r in all_results)
        tk.Label(
            inner, text="Total: {:.0f}ms".format(total_ms),
            font=("Segoe UI", 9), bg=t["panel_bg"], fg=t["label_fg"],
        ).pack(anchor="e", pady=(6, 0))

        # Position above the status bar, clamped to visible screen area
        popup.update_idletasks()
        x = self.loading_label.winfo_rootx()
        y = self.loading_label.winfo_rooty() - popup.winfo_reqheight() - 4
        # Clamp Y to stay on-screen (minimum 0)
        if y < 0:
            y = self.loading_label.winfo_rooty() + self.loading_label.winfo_height() + 4
        # Clamp X to stay on-screen
        screen_w = self.winfo_screenwidth()
        popup_w = popup.winfo_reqwidth()
        if x + popup_w > screen_w:
            x = max(0, screen_w - popup_w - 8)
        popup.geometry("+{}+{}".format(x, y))

        # Auto-close on click or after 8 seconds.
        # FocusOut is intentionally NOT bound -- it caused the popup
        # to self-destruct before the user could read it on corporate
        # Windows where focus is aggressively managed.
        popup.bind("<Button-1>", lambda e: popup.destroy())
        popup.after(8000, lambda: popup.destroy() if popup.winfo_exists() else None)
        popup.focus_set()

    @staticmethod
    def _render_check_rows(parent, results, t):
        """Render a list of IBITCheck results as [PASS]/[FAIL] rows."""
        for r in results:
            tag = "PASS" if r.ok else "FAIL"
            color = t["green"] if r.ok else t["red"]
            row = tk.Frame(parent, bg=t["panel_bg"])
            row.pack(fill="x", pady=1)
            tk.Label(
                row, text="[{}]".format(tag), font=("Consolas", 10, "bold"),
                bg=t["panel_bg"], fg=color, width=6, anchor="w",
            ).pack(side="left")
            tk.Label(
                row, text="{}: {}".format(r.name, r.detail),
                font=("Consolas", 10), bg=t["panel_bg"], fg=t["fg"],
                anchor="w",
            ).pack(side="left", fill="x")

    # ----------------------------------------------------------------
    # CBIT -- Continuous Built-In Test (60s background health check)
    # ----------------------------------------------------------------

    def start_cbit(self, query_engine=None):
        """Begin the CBIT periodic timer after IBIT completes.

        Called once from launch_gui._step_display after the final
        IBIT badge is shown.  Stores query_engine ref for CBIT use.
        """
        self._query_engine = query_engine
        if self._cbit_timer_id is None and not self._stop_event.is_set():
            self._cbit_timer_id = self.after(self.CBIT_MS, self._run_cbit)

    def _run_cbit(self):
        """Run CBIT checks in a background thread, then update badge."""
        if self._stop_event.is_set():
            return

        def _do():
            try:
                from src.core.ibit import run_cbit
                results = run_cbit(
                    self.config, self._query_engine, self.router,
                )
                safe_after(self, 0, lambda: self._apply_cbit(results))
            except Exception as e:
                logger.debug("CBIT error: %s", e)

        threading.Thread(target=_do, daemon=True).start()

        # Schedule next CBIT
        if not self._stop_event.is_set():
            self._cbit_timer_id = self.after(self.CBIT_MS, self._run_cbit)

    def _apply_cbit(self, results):
        """Update badge if CBIT detects degradation."""
        t = current_theme()
        self._cbit_results = results
        passed = sum(1 for r in results if r.ok)
        total = len(results)

        if passed == total:
            # Health OK -- restore IBIT badge if we had overridden it
            ibit = getattr(self, "_ibit_results", None)
            if ibit:
                ibit_passed = sum(1 for r in ibit if r.ok)
                if ibit_passed == len(ibit):
                    self.loading_label.config(
                        text="IBIT: {}/{} OK".format(ibit_passed, len(ibit)),
                        fg=t["green"],
                    )
            return

        # Degradation detected
        if passed == 0:
            text = "CBIT: {}/{} FAIL".format(total, total)
            fg = t["red"]
        else:
            text = "CBIT: {}/{} WARN".format(total - passed, total)
            fg = t["orange"]

        self.loading_label.config(text=text, fg=fg, cursor="hand2")
        self.loading_label.bind("<Button-1>", self._show_ibit_detail)

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
        self.model_label.config(
            text="Active Model ({}): {}".format(mode, model),
            fg=t["fg"],
        )

    def force_refresh(self):
        """Immediately refresh all indicators."""
        self._refresh_status()
        self._update_model_label()

    def stop(self):
        """Stop the periodic refresh timer, dot animation, and CBIT timer."""
        self._stop_event.set()
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
