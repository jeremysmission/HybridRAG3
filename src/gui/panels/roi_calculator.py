# ============================================================================
# HybridRAG v3 -- ROI Calculator Frame (src/gui/panels/roi_calculator.py) RevA
# ============================================================================
# WHAT: Self-contained ROI calculator widget extracted from the PM Cost
#       Dashboard.  Shows time saved, dollar value saved, and net ROI
#       based on query counts and user-editable wage/team parameters.
# WHY:  Keeps the CostDashboard class under 500 lines while giving the
#       ROI subsystem its own clear boundary for testing and reuse.
# HOW:  Receives a CostTracker reference at construction time, reads
#       session query counts on each refresh, and multiplies by the
#       user-supplied hourly rate and minutes-saved-per-query values.
# DEPENDS: CostTracker (src/core/cost_tracker.py), theme helpers
# INTERNET ACCESS: NONE -- reads from CostTracker only
# ============================================================================

import tkinter as tk
import logging

from src.gui.theme import (
    current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO,
    bind_hover,
)

logger = logging.getLogger(__name__)

# Medium font for the three hero numbers inside the ROI section
FONT_MED = ("Segoe UI", 14, "bold")


def _label(parent, t, **kw):
    """Shorthand for themed tk.Label."""
    defaults = {"bg": t["panel_bg"], "fg": t["fg"], "font": FONT}
    defaults.update(kw)
    return tk.Label(parent, **defaults)


class ROICalculatorFrame(tk.Frame):
    """Self-contained ROI calculator widget for the PM Cost Dashboard.

    Calculates time saved, dollar value saved, and net ROI based on
    query counts from CostTracker and user-editable parameters (hourly
    wage, team size, minutes saved per query).  All numbers are backed
    by cited BLS/McKinsey research shown in the parent dashboard.

    INTERNET ACCESS: NONE -- reads from CostTracker only
    """

    # Default parameters (BLS May 2024 median PM: $48.44/hr)
    DEFAULT_HOURLY = 48.44
    DEFAULT_TEAM = 10
    DEFAULT_MIN_SAVED = 10

    def __init__(self, parent, cost_tracker, **kw):
        """Create the ROI calculator frame.

        Args:
            parent: Parent tk widget (the inner scrollable frame).
            cost_tracker: CostTracker singleton for session query data.
        """
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"], **kw)

        self._tracker = cost_tracker
        self.roi_hourly = self.DEFAULT_HOURLY
        self.roi_team = self.DEFAULT_TEAM
        self.roi_min_saved = self.DEFAULT_MIN_SAVED

        self._build(t)

    def _build(self, t):
        """Build the ROI calculator UI with editable hourly rate, team size,
        and time savings.

        The ROI logic: each query saves X minutes of manual searching.
        Multiply by the hourly wage rate to get dollar value saved.
        Subtract API cost to get net ROI.  All backed by cited research.
        """
        frame = tk.LabelFrame(self, text="ROI Calculator -- Productivity Savings *",
                              padx=16, pady=8, bg=t["panel_bg"], fg=t["accent"],
                              font=FONT_BOLD)
        frame.pack(fill=tk.X)

        nums = tk.Frame(frame, bg=t["panel_bg"])
        nums.pack(fill=tk.X, pady=(0, 4))

        c1 = tk.Frame(nums, bg=t["panel_bg"])
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _label(c1, t, text="TIME SAVED *1", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self.roi_time_label = _label(c1, t, text="0h 0m", font=FONT_MED, fg=t["green"])
        self.roi_time_label.pack()

        c2 = tk.Frame(nums, bg=t["panel_bg"])
        c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _label(c2, t, text="VALUE SAVED *3", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self.roi_value_label = _label(c2, t, text="$0.00", font=FONT_MED, fg=t["green"])
        self.roi_value_label.pack()

        c3 = tk.Frame(nums, bg=t["panel_bg"])
        c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _label(c3, t, text="NET ROI", font=FONT_SMALL, fg=t["label_fg"]).pack()
        self.roi_net_label = _label(c3, t, text="$0.00", font=FONT_MED, fg=t["accent"])
        self.roi_net_label.pack()

        prow = tk.Frame(frame, bg=t["panel_bg"])
        prow.pack(fill=tk.X, pady=(4, 2))
        _label(prow, t, text="Hourly rate *3: $", font=FONT_SMALL).pack(side=tk.LEFT)
        self.roi_hourly_var = tk.StringVar(value="{:.2f}".format(self.roi_hourly))
        tk.Entry(prow, textvariable=self.roi_hourly_var, width=7, font=FONT_MONO,
                 bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
                 relief=tk.FLAT, bd=2).pack(side=tk.LEFT, padx=(0, 10))
        _label(prow, t, text="Team:", font=FONT_SMALL).pack(side=tk.LEFT)
        self.roi_team_var = tk.StringVar(value=str(self.roi_team))
        tk.Entry(prow, textvariable=self.roi_team_var, width=4, font=FONT_MONO,
                 bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
                 relief=tk.FLAT, bd=2).pack(side=tk.LEFT, padx=(0, 10))
        _label(prow, t, text="Min saved/query *2:", font=FONT_SMALL).pack(side=tk.LEFT)
        self.roi_minsaved_var = tk.StringVar(value=str(self.roi_min_saved))
        tk.Entry(prow, textvariable=self.roi_minsaved_var, width=4, font=FONT_MONO,
                 bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
                 relief=tk.FLAT, bd=2).pack(side=tk.LEFT, padx=(0, 10))
        upd_btn = tk.Button(prow, text="Update", font=FONT_SMALL, width=7,
                            command=self.on_update, bg=t["accent"],
                            fg=t["accent_fg"], relief=tk.FLAT, bd=0)
        upd_btn.pack(side=tk.LEFT)
        bind_hover(upd_btn)

        self.roi_projection = _label(frame, t, text="", font=FONT_MONO, fg=t["fg"])
        self.roi_projection.pack(fill=tk.X, pady=(4, 0))

    def refresh(self):
        """Recalculate and display ROI numbers from current session data."""
        s = self._tracker.get_session_summary()
        t = current_theme()
        h = self.roi_hourly
        m = self.roi_min_saved
        team = self.roi_team

        value_per_query = (m / 60.0) * h
        time_saved_min = s.query_count * m
        value_saved = s.query_count * value_per_query
        net_roi = value_saved - s.total_cost_usd

        hrs = time_saved_min // 60
        mins = time_saved_min % 60
        self.roi_time_label.config(text="{}h {}m".format(hrs, mins))
        self.roi_value_label.config(text="${:,.2f}".format(value_saved))
        self.roi_net_label.config(text="${:,.2f}".format(net_roi))
        self.roi_net_label.config(fg=t["green"] if net_roi >= 0 else t["red"])

        qpd = max(s.query_count, 1)
        monthly_queries = qpd * team * 22
        monthly_value = monthly_queries * value_per_query
        monthly_cost = monthly_queries * s.avg_cost_per_query
        if monthly_cost > 0:
            roi_pct = ((monthly_value / monthly_cost) - 1) * 100
            self.roi_projection.config(
                text="Team of {} @ {} queries/day: ~${:,.0f}/mo saved "
                     "vs ~${:,.2f}/mo API cost ({:,.0f}% ROI)".format(
                    team, qpd, monthly_value, monthly_cost, roi_pct))
        else:
            self.roi_projection.config(
                text="Team of {} @ {} queries/day: ~${:,.0f}/mo "
                     "productivity value (offline = $0 API cost)".format(
                    team, qpd, monthly_value))

    def on_update(self):
        """Parse user-edited parameters and recalculate ROI."""
        try:
            self.roi_hourly = float(self.roi_hourly_var.get())
            self.roi_team = int(self.roi_team_var.get())
            self.roi_min_saved = int(self.roi_minsaved_var.get())
            if self.roi_hourly < 0 or self.roi_team < 1 or self.roi_min_saved < 1:
                raise ValueError("Values must be positive")
            self.refresh()
        except ValueError:
            pass
