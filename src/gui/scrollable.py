# ============================================================================
# HybridRAG v3 -- ScrollableFrame (src/gui/scrollable.py)
# ============================================================================
# WHAT: Reusable canvas+scrollbar wrapper for scrollable content.
# WHY:  Multiple views need vertical scrolling when the window shrinks.
#       This extracts the boilerplate so each view gets it in ~3 lines.
# HOW:  A tk.Frame containing a Canvas + Scrollbar. Child widgets go
#       inside .inner (the frame embedded in the canvas). Mousewheel
#       binds on enter/leave; inner frame width syncs with canvas width.
# USAGE:
#       sf = ScrollableFrame(parent, bg=t["bg"])
#       sf.pack(fill=BOTH, expand=True)
#       tk.Label(sf.inner, text="Hello").pack()
#
# INTERNET ACCESS: NONE
# ============================================================================

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(tk.Frame):
    """Canvas + vertical Scrollbar with mousewheel support.

    All child widgets should be placed inside ``self.inner``.
    The inner frame width automatically matches the canvas width so
    pack(fill=X) children expand correctly.
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)

        bg = kw.get("bg", kw.get("background", ""))

        self._canvas = tk.Canvas(self, highlightthickness=0)
        if bg:
            self._canvas.configure(bg=bg)

        self._scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview)

        self.inner = tk.Frame(self._canvas)
        if bg:
            self.inner.configure(bg=bg)

        self.inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))

        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.inner, anchor="nw", tags="inner")

        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Keep inner frame width matched to canvas
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        # Mousewheel scrolling (bind on enter, unbind on leave)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_canvas_resize(self, event):
        """Sync inner frame width to canvas width.

        Also set the inner frame height to at least the canvas height so
        that pack(fill=BOTH, expand=True) children fill visible space.
        When children need more than the canvas height, the natural
        (requested) height wins and the scrollbar activates.
        """
        self._canvas.itemconfig("inner", width=event.width)
        inner_h = self.inner.winfo_reqheight()
        if inner_h < event.height:
            self._canvas.itemconfig("inner", height=event.height)
        else:
            self._canvas.itemconfig("inner", height=inner_h)

    def _bind_mousewheel(self, event):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def apply_theme(self, t):
        """Re-apply theme colors to the canvas and inner frame."""
        bg = t.get("bg", "")
        self.configure(bg=bg)
        self._canvas.configure(bg=bg)
        self.inner.configure(bg=bg)
