# Extracted IBIT/CBIT methods for StatusBar to keep class size bounded.

from __future__ import annotations

import threading
import tkinter as tk
import logging

from src.gui.theme import current_theme
from src.gui.helpers.safe_after import safe_after

_LOG = logging.getLogger(__name__)

def set_ibit_stage(self, check_name):
    """Show the current IBIT check name during verification."""
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
    """Show final IBIT result as a persistent badge."""
    t = current_theme()
    self._loading = False
    if self._dot_timer_id is not None:
        self.after_cancel(self._dot_timer_id)
        self._dot_timer_id = None

    self._ibit_results = results

    if total <= 0:
        text = "IBIT: NOT RUN"
        fg = t["orange"]
    elif passed == total:
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

    if ibit:
        tk.Label(
            inner, text="Initial Built-In Test",
            font=("Segoe UI", 11, "bold"),
            bg=t["panel_bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(0, 4))
        self._render_check_rows(inner, ibit, t)

    if cbit:
        if ibit:
            tk.Frame(inner, height=1, bg=t["separator"]).pack(fill="x", pady=6)
        tk.Label(
            inner, text="Continuous Health Check",
            font=("Segoe UI", 11, "bold"),
            bg=t["panel_bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(0, 4))
        self._render_check_rows(inner, cbit, t)

    all_results = (ibit or []) + (cbit or [])
    total_ms = sum(r.elapsed_ms for r in all_results)
    tk.Label(
        inner, text="Total: {:.0f}ms".format(total_ms),
        font=("Segoe UI", 9), bg=t["panel_bg"], fg=t["label_fg"],
    ).pack(anchor="e", pady=(6, 0))

    popup.update_idletasks()
    x = self.loading_label.winfo_rootx()
    y = self.loading_label.winfo_rooty() - popup.winfo_reqheight() - 4
    if y < 0:
        y = self.loading_label.winfo_rooty() + self.loading_label.winfo_height() + 4
    screen_w = self.winfo_screenwidth()
    popup_w = popup.winfo_reqwidth()
    if x + popup_w > screen_w:
        x = max(0, screen_w - popup_w - 8)
    popup.geometry("+{}+{}".format(x, y))

    popup.bind("<Button-1>", lambda e: popup.destroy())
    popup.after(8000, lambda: popup.destroy() if popup.winfo_exists() else None)
    popup.focus_set()


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


def start_cbit(self, query_engine=None):
    """Begin the CBIT periodic timer after IBIT completes."""
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
            _LOG.debug("CBIT error: %s", e)

    threading.Thread(target=_do, daemon=True).start()

    if not self._stop_event.is_set():
        self._cbit_timer_id = self.after(self.CBIT_MS, self._run_cbit)


def _apply_cbit(self, results):
    """Update badge if CBIT detects degradation."""
    t = current_theme()
    self._cbit_results = results
    passed = sum(1 for r in results if r.ok)
    total = len(results)

    if passed == total:
        ibit = getattr(self, "_ibit_results", None)
        if ibit:
            ibit_passed = sum(1 for r in ibit if r.ok)
            if ibit_passed == len(ibit):
                self.loading_label.config(
                    text="IBIT: {}/{} OK".format(ibit_passed, len(ibit)),
                    fg=t["green"],
                )
        return

    if passed == 0:
        text = "CBIT: {}/{} FAIL".format(total, total)
        fg = t["red"]
    else:
        text = "CBIT: {}/{} WARN".format(total - passed, total)
        fg = t["orange"]

    self.loading_label.config(text=text, fg=fg, cursor="hand2")
    self.loading_label.bind("<Button-1>", self._show_ibit_detail)
