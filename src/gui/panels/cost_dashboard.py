# ============================================================================
# HybridRAG v3 -- PM Cost Dashboard (src/gui/panels/cost_dashboard.py) RevA
# ============================================================================
# WHAT: Live cost tracking dashboard for program managers and team leads.
# WHY:  PMs need to justify RAG tool spending vs. manual research costs.
#       This dashboard shows real-time API spend, calculates ROI using
#       BLS wage data, and projects monthly team savings -- all the
#       numbers a PM needs for a budget review or executive briefing.
# HOW:  Reads token counts and cost data from CostTracker (SQLite-backed
#       singleton).  Registers as a listener so numbers update live after
#       every query without polling.  All calculations are local -- no
#       network calls.
# USAGE: Navigate via NavBar > Cost, or Admin > PM Cost Dashboard.
#
# LAYOUT: Header | Big Numbers | Budget Gauge | Token Breakdown |
#         Data Volume | Cumulative Team | ROI Calculator | Rate Editor |
#         Citations | Export/Refresh footer
#
# All content is inside a scrollable Canvas+Frame wrapper because the
# dashboard is taller than a typical window.
#
# INTERNET ACCESS: NONE -- reads from CostTracker only
# ============================================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from datetime import datetime

from src.gui.theme import (
    current_theme, FONT, FONT_BOLD, FONT_TITLE, FONT_SMALL, FONT_MONO,
    bind_hover,
)
from src.gui.scrollable import ScrollableFrame
from src.gui.panels.roi_calculator import ROICalculatorFrame

logger = logging.getLogger(__name__)

# Large font sizes for the "big numbers" hero section at the top
FONT_BIG = ("Segoe UI", 22, "bold")
FONT_MED = ("Segoe UI", 14, "bold")


def _label(parent, t, **kw):
    """Shorthand for themed tk.Label."""
    defaults = {"bg": t["panel_bg"], "fg": t["fg"], "font": FONT}
    defaults.update(kw)
    return tk.Label(parent, **defaults)


class CostDashboard(tk.Frame):
    """PM Cost Dashboard view. Updates live as queries execute."""

    def __init__(self, parent, cost_tracker):
        """Create the cost dashboard.

        Args:
            parent: Parent tk widget (the content frame in HybridRAGApp).
            cost_tracker: CostTracker singleton that records all query costs.
                          The dashboard registers as a listener to get live
                          updates after every query completes.
        """
        t = current_theme()
        super().__init__(parent, bg=t["bg"])

        self._tracker = cost_tracker
        self._refresh_id = None

        # Scrollable container
        self._scroll = ScrollableFrame(self, bg=t["bg"])
        self._scroll.pack(fill=tk.BOTH, expand=True)
        self._inner = self._scroll.inner

        # Build all sections into self._inner
        self._build_header(t)
        self._build_big_numbers(t)
        self._build_budget_gauge(t)
        self._build_token_breakdown(t)
        self._build_data_volume(t)
        self._build_cumulative(t)
        self._roi = ROICalculatorFrame(self._inner, cost_tracker)
        self._roi.pack(fill=tk.X, padx=16, pady=4)
        self._build_rate_editor(t)
        self._build_citations(t)
        self._build_footer(t)
        self._refresh_all()

        # Register as a cost tracker listener so we refresh automatically
        # after every query.  The lambda wraps the refresh in after() to
        # ensure it runs on the GUI main thread (cost events fire from
        # background query threads).
        self._listener = lambda event: self.after(0, self._refresh_all)
        self._tracker.add_listener(self._listener)

    # -- Build sections (all into self._inner) ----------------------------

    def _build_header(self, t):
        """Build the title row with session ID and start time."""
        frame = tk.Frame(self._inner, bg=t["panel_bg"], padx=16, pady=12)
        frame.pack(fill=tk.X)
        _label(frame, t, text="PM Cost Dashboard", font=FONT_TITLE).pack(side=tk.LEFT)
        self._session_label = _label(frame, t, text="Session: ---",
                                     font=FONT_SMALL, fg=t["label_fg"])
        self._session_label.pack(side=tk.RIGHT)

    def _build_big_numbers(self, t):
        """Build the three hero numbers: session spend, query count, avg cost.

        These are the first thing a PM sees -- large, color-coded numbers
        that answer "how much have we spent?" at a glance.
        """
        frame = tk.Frame(self._inner, bg=t["bg"], padx=16, pady=4)
        frame.pack(fill=tk.X)

        col1 = tk.Frame(frame, bg=t["panel_bg"], padx=16, pady=12)
        col1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        _label(col1, t, text="SESSION SPEND", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self._spend_label = _label(col1, t, text="$0.0000", font=FONT_BIG, fg=t["green"])
        self._spend_label.pack()

        col2 = tk.Frame(frame, bg=t["panel_bg"], padx=16, pady=12)
        col2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        _label(col2, t, text="QUERIES", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self._queries_label = _label(col2, t, text="0", font=FONT_BIG, fg=t["accent"])
        self._queries_label.pack()

        col3 = tk.Frame(frame, bg=t["panel_bg"], padx=16, pady=12)
        col3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
        _label(col3, t, text="AVG COST/QUERY", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self._avg_label = _label(col3, t, text="$0.0000", font=FONT_MED)
        self._avg_label.pack()

    def _build_budget_gauge(self, t):
        """Build the budget progress bar (green/yellow/red based on % used)."""
        frame = tk.LabelFrame(self._inner, text="Daily Budget", padx=16, pady=8,
                              bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=4)

        self._gauge_canvas = tk.Canvas(frame, height=32, bg=t["input_bg"],
                                       highlightthickness=0, bd=0)
        self._gauge_canvas.pack(fill=tk.X, pady=(4, 2))
        self._budget_text = _label(frame, t, text="$0.00 / $5.00 (0%)", font=FONT_MONO)
        self._budget_text.pack()
        self._savings_label = _label(frame, t, text="", font=FONT_SMALL, fg=t["green"])
        self._savings_label.pack()

    def _build_token_breakdown(self, t):
        """Build the input/output token table with rates and per-direction costs."""
        frame = tk.LabelFrame(self._inner, text="Token Breakdown (Session)", padx=16, pady=8,
                              bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=4)

        hdr = tk.Frame(frame, bg=t["panel_bg"])
        hdr.pack(fill=tk.X, pady=(0, 4))
        for col, w in [("", 10), ("Tokens", 14), ("Rate/1M", 12), ("Cost", 12)]:
            _label(hdr, t, text=col, font=FONT_BOLD, width=w, anchor=tk.W,
                   fg=t["label_fg"]).pack(side=tk.LEFT)

        r1 = tk.Frame(frame, bg=t["panel_bg"])
        r1.pack(fill=tk.X)
        _label(r1, t, text="Input", width=10, anchor=tk.W).pack(side=tk.LEFT)
        self._tin_label = _label(r1, t, text="0", font=FONT_MONO, width=14, anchor=tk.W)
        self._tin_label.pack(side=tk.LEFT)
        self._tin_rate = _label(r1, t, text="$1.50", font=FONT_MONO, width=12,
                                anchor=tk.W, fg=t["label_fg"])
        self._tin_rate.pack(side=tk.LEFT)
        self._tin_cost = _label(r1, t, text="$0.0000", font=FONT_MONO, width=12, anchor=tk.W)
        self._tin_cost.pack(side=tk.LEFT)

        r2 = tk.Frame(frame, bg=t["panel_bg"])
        r2.pack(fill=tk.X)
        _label(r2, t, text="Output", width=10, anchor=tk.W).pack(side=tk.LEFT)
        self._tout_label = _label(r2, t, text="0", font=FONT_MONO, width=14, anchor=tk.W)
        self._tout_label.pack(side=tk.LEFT)
        self._tout_rate = _label(r2, t, text="$2.00", font=FONT_MONO, width=12,
                                 anchor=tk.W, fg=t["label_fg"])
        self._tout_rate.pack(side=tk.LEFT)
        self._tout_cost = _label(r2, t, text="$0.0000", font=FONT_MONO, width=12, anchor=tk.W)
        self._tout_cost.pack(side=tk.LEFT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        r3 = tk.Frame(frame, bg=t["panel_bg"])
        r3.pack(fill=tk.X)
        _label(r3, t, text="Total", font=FONT_BOLD, width=10, anchor=tk.W).pack(side=tk.LEFT)
        self._ttotal_label = _label(r3, t, text="0", font=FONT_MONO, width=14, anchor=tk.W)
        self._ttotal_label.pack(side=tk.LEFT)
        _label(r3, t, text="", width=12).pack(side=tk.LEFT)
        self._ttotal_cost = _label(r3, t, text="$0.0000", font=FONT_MONO, width=12,
                                   anchor=tk.W, fg=t["accent"])
        self._ttotal_cost.pack(side=tk.LEFT)

    def _build_data_volume(self, t):
        """Build the data volume row (KB sent/received/total)."""
        frame = tk.LabelFrame(self._inner, text="Data Volume (Session)", padx=16, pady=8,
                              bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=4)
        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X)

        _label(row, t, text="Sent:").pack(side=tk.LEFT)
        self._data_in_label = _label(row, t, text="0.00 KB", font=FONT_MONO)
        self._data_in_label.pack(side=tk.LEFT, padx=(4, 24))
        _label(row, t, text="Received:").pack(side=tk.LEFT)
        self._data_out_label = _label(row, t, text="0.00 KB", font=FONT_MONO)
        self._data_out_label.pack(side=tk.LEFT, padx=(4, 24))
        _label(row, t, text="Total:", font=FONT_BOLD).pack(side=tk.LEFT)
        self._data_total_label = _label(row, t, text="0.00 KB", font=FONT_MONO, fg=t["accent"])
        self._data_total_label.pack(side=tk.LEFT, padx=4)

    def _build_cumulative(self, t):
        """Build the all-time cumulative stats section (persists across sessions)."""
        frame = tk.LabelFrame(self._inner, text="Cumulative (All Sessions / Team)", padx=16,
                              pady=8, bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=4)
        self._cum_text = _label(frame, t, text="Loading...", font=FONT_MONO,
                                justify=tk.LEFT, anchor=tk.W)
        self._cum_text.pack(fill=tk.X)

    def _build_rate_editor(self, t):
        """Build the token rate editor for custom pricing.

        Rates are stored per 1M tokens (industry standard for 2026 pricing).
        Admins can adjust these when the provider changes pricing tiers.
        """
        frame = tk.LabelFrame(self._inner, text="Token Pricing (per 1M tokens)", padx=16,
                              pady=8, bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        frame.pack(fill=tk.X, padx=16, pady=4)
        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X)

        rates = self._tracker.get_rates()
        _label(row, t, text="Input rate: $").pack(side=tk.LEFT)
        self._input_rate_var = tk.StringVar(value="{:.4f}".format(rates.input_rate_per_1m))
        tk.Entry(row, textvariable=self._input_rate_var, width=10, font=FONT_MONO,
                 bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
                 relief=tk.FLAT, bd=2).pack(side=tk.LEFT, padx=(0, 16))

        _label(row, t, text="Output rate: $").pack(side=tk.LEFT)
        self._output_rate_var = tk.StringVar(value="{:.4f}".format(rates.output_rate_per_1m))
        tk.Entry(row, textvariable=self._output_rate_var, width=10, font=FONT_MONO,
                 bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
                 relief=tk.FLAT, bd=2).pack(side=tk.LEFT, padx=(0, 16))

        self._apply_btn = tk.Button(row, text="Apply", font=FONT, width=8,
                                    command=self._on_apply_rates, bg=t["accent"],
                                    fg=t["accent_fg"], relief=tk.FLAT, bd=0)
        self._apply_btn.pack(side=tk.LEFT)
        bind_hover(self._apply_btn)
        self._rate_status = _label(frame, t, text="", font=FONT_SMALL, fg=t["green"])
        self._rate_status.pack(anchor=tk.W, pady=(4, 0))

    def _build_citations(self, t):
        """Build the research citation footnotes that back the ROI methodology."""
        frame = tk.Frame(self._inner, bg=t["bg"], padx=16, pady=2)
        frame.pack(fill=tk.X)
        citations = (
            "*1 McKinsey Global Institute, \"The Social Economy,\" 2012"
            " -- workers spend 19% of workday searching for information\n"
            "*2 McKinsey Global Institute, \"Economic Potential of"
            " Generative AI,\" 2023 -- AI automates 60-70% of retrieval tasks\n"
            "*3 U.S. Bureau of Labor Statistics, OEWS May 2024"
            " (SOC 13-1082) -- PM median wage $48.44/hr\n"
            "*4 Bloomfire / Harvard Business Review, 2025"
            " -- AI recovers 50%+ of employee search time"
        )
        self._citations_label = _label(frame, t, text=citations, font=FONT_SMALL,
                                       fg=t["label_fg"], justify=tk.LEFT,
                                       anchor=tk.W, bg=t["bg"])
        self._citations_label.pack(fill=tk.X)

    def _build_footer(self, t):
        """Build the Export CSV and manual Refresh buttons at the bottom."""
        frame = tk.Frame(self._inner, bg=t["bg"], padx=16, pady=8)
        frame.pack(fill=tk.X)

        self._export_btn = tk.Button(frame, text="Export CSV", font=FONT, width=14,
                                     command=self._on_export_csv, bg=t["accent"],
                                     fg=t["accent_fg"], relief=tk.FLAT, bd=0,
                                     padx=12, pady=6)
        self._export_btn.pack(side=tk.LEFT)
        bind_hover(self._export_btn)

        self._refresh_btn = tk.Button(frame, text="Refresh", font=FONT, width=10,
                                      command=self._refresh_all, bg=t["input_bg"],
                                      fg=t["fg"], relief=tk.FLAT, bd=0, padx=12, pady=6)
        self._refresh_btn.pack(side=tk.LEFT, padx=8)
        bind_hover(self._refresh_btn)

    # -- Refresh methods --------------------------------------------------

    def _refresh_all(self):
        """Refresh all dashboard sections from tracker data."""
        try:
            self._refresh_session()
            self._refresh_gauge()
            self._refresh_cumulative()
            self._roi.refresh()
        except tk.TclError:
            pass

    def _refresh_session(self):
        """Update session-level stats."""
        s = self._tracker.get_session_summary()
        rates = self._tracker.get_rates()
        t = current_theme()

        self._session_label.config(text="Session: {} | Started: {}".format(
            s.session_id, s.start_time[:19]))
        self._spend_label.config(text="${:.4f}".format(s.total_cost_usd))
        self._queries_label.config(text="{:,}".format(s.query_count))
        self._avg_label.config(text="${:.4f}".format(s.avg_cost_per_query))

        # Color-code the spend number: green=safe, orange=caution, red=over budget
        if s.total_cost_usd < 2.5:
            self._spend_label.config(fg=t["green"])
        elif s.total_cost_usd < 4.0:
            self._spend_label.config(fg=t["orange"])
        else:
            self._spend_label.config(fg=t["red"])

        in_cost = (s.total_tokens_in / 1_000_000) * rates.input_rate_per_1m
        out_cost = (s.total_tokens_out / 1_000_000) * rates.output_rate_per_1m
        self._tin_label.config(text="{:,}".format(s.total_tokens_in))
        self._tin_rate.config(text="${:.2f}".format(rates.input_rate_per_1m))
        self._tin_cost.config(text="${:.4f}".format(in_cost))
        self._tout_label.config(text="{:,}".format(s.total_tokens_out))
        self._tout_rate.config(text="${:.2f}".format(rates.output_rate_per_1m))
        self._tout_cost.config(text="${:.4f}".format(out_cost))
        self._ttotal_label.config(text="{:,}".format(s.total_tokens_in + s.total_tokens_out))
        self._ttotal_cost.config(text="${:.4f}".format(in_cost + out_cost))

        di_kb = s.total_data_in_bytes / 1024.0
        do_kb = s.total_data_out_bytes / 1024.0
        self._data_in_label.config(text="{:.2f} KB".format(di_kb))
        self._data_out_label.config(text="{:.2f} KB".format(do_kb))
        self._data_total_label.config(text="{:.2f} KB".format(di_kb + do_kb))

        events = self._tracker.get_session_events()
        offline_count = sum(1 for e in events if e.mode == "offline")
        if offline_count > 0:
            self._savings_label.config(
                text="[OK] {} offline queries -- $0.00 local inference".format(offline_count))
        else:
            self._savings_label.config(text="")

    def _refresh_gauge(self):
        """Redraw the budget gauge bar."""
        s = self._tracker.get_session_summary()
        t = current_theme()

        budget = 5.0
        # Walk up to find the app's config for budget setting
        try:
            app = self.winfo_toplevel()
            parent_config = getattr(app, "config", None)
            if parent_config:
                cost_cfg = getattr(parent_config, "cost", None)
                if cost_cfg:
                    budget = getattr(cost_cfg, "daily_budget_usd", 5.0)
        except Exception:
            pass

        spent = s.total_cost_usd
        pct = min(spent / budget, 1.0) if budget > 0 else 0.0

        self._budget_text.config(
            text="${:.4f} / ${:.2f}  ({:.1f}%)".format(spent, budget, pct * 100))

        canvas = self._gauge_canvas
        canvas.delete("all")
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 680)
        h = canvas.winfo_height()
        canvas.create_rectangle(0, 0, w, h, fill=t["input_bg"], outline="")

        # Traffic-light color thresholds for the budget gauge bar
        if pct < 0.60:
            fill_color = t["green"]    # Under 60% -- comfortable
        elif pct < 0.85:
            fill_color = t["orange"]   # 60-85% -- caution
        else:
            fill_color = t["red"]      # Over 85% -- nearing/exceeding budget

        fill_w = int(w * pct)
        if fill_w > 0:
            canvas.create_rectangle(0, 0, fill_w, h, fill=fill_color, outline="")
        canvas.create_text(w // 2, h // 2, text="{:.1f}%".format(pct * 100),
                           fill=t["fg"], font=FONT_BOLD)

    def _refresh_cumulative(self):
        """Update cumulative team stats."""
        c = self._tracker.get_cumulative_summary()
        lines = [
            "Sessions: {:,}    Queries: {:,}    Total: ${:.4f}".format(
                c.total_sessions, c.total_queries, c.total_cost_usd),
            "Tokens:   {:,} in / {:,} out".format(c.total_tokens_in, c.total_tokens_out),
            "Data:     {:.2f} KB in / {:.2f} KB out".format(
                c.total_data_in_bytes / 1024.0, c.total_data_out_bytes / 1024.0),
            "Avg/query: ${:.4f}    Avg/session: ${:.4f}".format(
                c.avg_cost_per_query, c.avg_cost_per_session),
        ]
        if c.first_event:
            lines.append("Range: {} to {}".format(c.first_event[:19], c.last_event[:19]))
        self._cum_text.config(text="\n".join(lines))

    # -- ROI proxy properties (backward compat for tests) --------------------

    @property
    def _roi_hourly(self):
        return self._roi.roi_hourly

    @_roi_hourly.setter
    def _roi_hourly(self, v):
        self._roi.roi_hourly = v

    @property
    def _roi_team(self):
        return self._roi.roi_team

    @_roi_team.setter
    def _roi_team(self, v):
        self._roi.roi_team = v

    @property
    def _roi_min_saved(self):
        return self._roi.roi_min_saved

    @_roi_min_saved.setter
    def _roi_min_saved(self, v):
        self._roi.roi_min_saved = v

    @property
    def _roi_hourly_var(self):
        return self._roi.roi_hourly_var

    @property
    def _roi_team_var(self):
        return self._roi.roi_team_var

    @property
    def _roi_minsaved_var(self):
        return self._roi.roi_minsaved_var

    @property
    def _roi_time_label(self):
        return self._roi.roi_time_label

    @property
    def _roi_value_label(self):
        return self._roi.roi_value_label

    @property
    def _roi_net_label(self):
        return self._roi.roi_net_label

    @property
    def _roi_projection(self):
        return self._roi.roi_projection

    def _on_update_roi(self):
        """Delegate to ROICalculatorFrame."""
        self._roi.on_update()

    # -- Actions -----------------------------------------------------------

    def _on_apply_rates(self):
        """Apply new token rates from the entry fields."""
        try:
            in_rate = float(self._input_rate_var.get())
            out_rate = float(self._output_rate_var.get())
            if in_rate < 0 or out_rate < 0:
                raise ValueError("Rates must be non-negative")
            self._tracker.set_rates(in_rate, out_rate, "Custom")
            self._rate_status.config(
                text="[OK] Rates updated: ${:.4f} / ${:.4f} per 1M tokens".format(
                    in_rate, out_rate),
                fg=current_theme()["green"])
            self._refresh_all()
        except ValueError as e:
            self._rate_status.config(text="[FAIL] Invalid rate: {}".format(e),
                                     fg=current_theme()["red"])

    def _on_export_csv(self):
        """Export all cost events to CSV file."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="hybridrag_cost_export_{}.csv".format(
                datetime.now().strftime("%Y%m%d_%H%M%S")))
        if not filepath:
            return
        count = self._tracker.export_csv(filepath)
        if count > 0:
            messagebox.showinfo("Export Complete",
                                "Exported {:,} cost events to:\n{}".format(count, filepath))
        else:
            messagebox.showwarning("No Data",
                                   "No cost events to export yet.\nRun some queries first.")

    # -- Lifecycle ---------------------------------------------------------

    def cleanup(self):
        """Unregister listener and cancel pending refreshes."""
        try:
            self._tracker.remove_listener(self._listener)
        except Exception:
            pass
        if self._refresh_id:
            try:
                self.after_cancel(self._refresh_id)
            except Exception:
                pass

    def apply_theme(self, t):
        """Re-apply theme to dashboard."""
        self.configure(bg=t["bg"])
        self._scroll.apply_theme(t)
        self._refresh_all()
