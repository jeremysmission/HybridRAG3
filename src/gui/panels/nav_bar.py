# ============================================================================
# HybridRAG v3 -- Navigation Bar (src/gui/panels/nav_bar.py)       RevA
# ============================================================================
# Horizontal segmented control for switching content views in-place.
# Replaces the old multi-window (Toplevel) navigation pattern.
#
# INTERNET ACCESS: NONE
# ============================================================================

import tkinter as tk

from src.gui.theme import FONT, FONT_BOLD, bind_hover


class NavBar(tk.Frame):
    """Horizontal segmented control for switching content views."""

    TABS = [
        ("Query", "query"),
        ("Settings", "settings"),
        ("Cost", "cost"),
        ("Ref", "reference"),
    ]

    def __init__(self, parent, on_switch, theme):
        super().__init__(parent, bg=theme["panel_bg"])
        self._on_switch = on_switch
        self._theme = theme
        self._current = "query"
        self._tab_labels = {}

        self._build(theme)

    def _build(self, t):
        """Build tab labels and separator."""
        tab_row = tk.Frame(self, bg=t["panel_bg"])
        tab_row.pack(fill=tk.X, padx=8)

        for display, name in self.TABS:
            lbl = tk.Label(
                tab_row, text=display, font=FONT, cursor="hand2",
                bg=t["panel_bg"], fg=t["fg"],
                padx=20, pady=6,
            )
            lbl.pack(side=tk.LEFT)
            lbl.bind("<Button-1>", lambda e, n=name: self._on_tab_click(n))
            lbl.bind("<Enter>", lambda e, w=lbl, n=name: self._on_hover_enter(w, n))
            lbl.bind("<Leave>", lambda e, w=lbl, n=name: self._on_hover_leave(w, n))
            self._tab_labels[name] = lbl

        # Thin separator below the nav bar
        self._separator = tk.Frame(self, height=2, bg=t["separator"])
        self._separator.pack(fill=tk.X)

        # Accent bar under selected tab (drawn via label border trick)
        self.select("query")

    def _on_tab_click(self, name):
        """Handle tab click -- switch view."""
        if name != self._current:
            self._on_switch(name)

    def _on_hover_enter(self, widget, name):
        """Lighten background on hover (unselected tabs only)."""
        if name != self._current:
            t = self._theme
            widget.config(bg=t["input_bg"])

    def _on_hover_leave(self, widget, name):
        """Restore background on hover leave (unselected tabs only)."""
        if name != self._current:
            t = self._theme
            widget.config(bg=t["panel_bg"])

    def select(self, view_name):
        """Update all tab colors: selected = accent, others = panel_bg."""
        t = self._theme
        self._current = view_name
        for name, lbl in self._tab_labels.items():
            if name == view_name:
                lbl.config(
                    bg=t["accent"], fg=t["accent_fg"], font=FONT_BOLD,
                )
            else:
                lbl.config(
                    bg=t["panel_bg"], fg=t["fg"], font=FONT,
                )

    def apply_theme(self, t):
        """Re-apply theme colors and re-select current tab."""
        self._theme = t
        self.config(bg=t["panel_bg"])
        for child in self.winfo_children():
            if isinstance(child, tk.Frame) and child != self._separator:
                child.config(bg=t["panel_bg"])
        self._separator.config(bg=t["separator"])
        self.select(self._current)
