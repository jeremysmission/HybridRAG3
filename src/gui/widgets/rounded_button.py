# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the rounded button part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Rounded Button Widget (src/gui/widgets/rounded_button.py)
# ============================================================================
# WHAT: A button with rounded corners, drawn on a tkinter Canvas.
# WHY:  Standard tk.Button only supports rectangular shapes with hard edges.
#       Modern UI conventions expect subtle rounding (4px radius) on
#       interactive elements.  This widget provides that without any
#       external dependencies -- pure tkinter Canvas drawing.
# HOW:  Draws a smooth polygon (rounded rectangle) on a Canvas, places
#       text in the center, and handles Enter/Leave/Click events manually.
#       Auto-sizes based on text measurement if width/height not given.
# USAGE: from src.gui.widgets import RoundedButton
#        btn = RoundedButton(parent, text="Click Me", command=callback)
# ============================================================================
import tkinter as tk
from src.gui.theme import FONT, _lighten_hex


class RoundedButton(tk.Canvas):
    """A flat button with rounded corners drawn on a Canvas.

    Supports hover effect (lighten on mouse enter), disabled state,
    theme switching, and configure() for dynamic updates.
    """

    def __init__(self, parent, *, text="", command=None, font=None,
                 bg="#0078d4", fg="#ffffff", hover_bg=None,
                 padx=16, pady=8, width=None, height=None, **kw):
        """Plain-English: This function handles init."""
        self._text = text
        self._command = command
        self._font = font or FONT
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg or _lighten_hex(bg)
        self._padx, self._pady = padx, pady
        self._radius = 4
        self._disabled = False
        self._disabled_bg = "#555555"
        self._disabled_fg = "#999999"
        # Measure text to auto-size if width/height not given
        _tmp = tk.Label(parent, text=text, font=self._font)
        tw, th = _tmp.winfo_reqwidth(), _tmp.winfo_reqheight()
        _tmp.destroy()
        self._w = width or (tw + padx * 2)
        self._h = height or (th + pady * 2)
        super().__init__(parent, width=self._w, height=self._h,
                         highlightthickness=0, borderwidth=0, **kw)
        self._rect_id = None
        self._text_id = None
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    # -- drawing --------------------------------------------------------

    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle using a smooth polygon.

        The 12-point polygon with smooth=True produces curved corners
        that approximate a true rounded rectangle at the given radius r.
        """
        pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
               x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
               x1, y2, x1, y2-r, x1, y1+r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kwargs)

    def _draw(self):
        """Redraw the button with current colors and text."""
        self.delete("all")
        bg = self._disabled_bg if self._disabled else self._bg
        fg = self._disabled_fg if self._disabled else self._fg
        canvas_bg = self.master.cget("bg") if self.master else "#1e1e1e"
        super().configure(bg=canvas_bg)
        self._rect_id = self._rounded_rect(
            0, 0, self._w, self._h, self._radius, fill=bg, outline=bg)
        self._text_id = self.create_text(
            self._w // 2, self._h // 2, text=self._text,
            fill=fg, font=self._font)

    # -- events ---------------------------------------------------------

    def _on_enter(self, _event):
        """Plain-English: This function handles on enter."""
        if not self._disabled:
            self.itemconfig(self._rect_id, fill=self._hover_bg,
                            outline=self._hover_bg)

    def _on_leave(self, _event):
        """Plain-English: This function handles on leave."""
        if not self._disabled:
            self.itemconfig(self._rect_id, fill=self._bg, outline=self._bg)

    def _on_click(self, _event):
        """Plain-English: This function handles on click."""
        if not self._disabled and self._command:
            self._command()

    # -- public API -----------------------------------------------------

    def set_disabled(self, disabled: bool):
        """Enable or disable the button."""
        self._disabled = disabled
        self._draw()

    def apply_theme(self, t: dict):
        """Re-skin using a theme dict (DARK or LIGHT)."""
        self._bg = t.get("accent", self._bg)
        self._fg = t.get("accent_fg", self._fg)
        self._hover_bg = t.get("accent_hover", _lighten_hex(self._bg))
        self._disabled_bg = t.get("disabled_fg", "#555555")
        self._disabled_fg = t.get("bg", "#999999")
        self._draw()

    def configure(self, **kw):
        """Override to handle text, bg, fg, command, font, state."""
        need_redraw = False
        for key in ("text", "bg", "fg", "command", "font", "state", "hover_bg"):
            if key not in kw:
                continue
            val = kw.pop(key)
            if key == "text":
                self._text = val
            elif key == "bg":
                self._bg = val
                self._hover_bg = _lighten_hex(val)
            elif key == "fg":
                self._fg = val
            elif key == "command":
                self._command = val
            elif key == "font":
                self._font = val
            elif key == "state":
                self._disabled = (val == tk.DISABLED)
            elif key == "hover_bg":
                self._hover_bg = val
            need_redraw = True
        if kw:
            super().configure(**kw)
        if need_redraw:
            self._draw()

    config = configure
