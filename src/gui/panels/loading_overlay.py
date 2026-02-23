# ============================================================================
# HybridRAG v3 -- Vector Field Loading Overlay                        RevA
# (src/gui/panels/loading_overlay.py)
# ============================================================================
# WHAT: Animated "vector field" overlay that plays during query execution.
# WHY:  Users perceive animated waits as shorter than static spinners
#       (research: motion creates "time distortion" that compresses
#       perceived duration).  The node-and-spark visual also reinforces
#       the "vector search" concept, making the tool feel purposeful
#       rather than just "loading."
# HOW:  Pure tkinter Canvas drawing at ~30fps via after().  Nodes drift
#       around the canvas, connections form between nearby nodes, and
#       bright sparks travel along connections.  A banner at the bottom
#       shows the current phase text.  On completion, "Complete!" flashes
#       green and the overlay slides up to reveal the answer.
# USAGE: Created by QueryPanel, placed over the answer area.
#        query_panel._overlay.start("Searching...")
#        query_panel._overlay.stop()   # triggers slide-up animation
#
# Uses pure tkinter Canvas + after() -- no external files, no GIFs,
# no licensing concerns, fully theme-aware.
#
# INTERNET ACCESS: NONE
# ============================================================================

import math
import random
import tkinter as tk

from src.gui.theme import FONT_BOLD, current_theme

# -- Animation constants ----------------------------------------------------
# These control the look and feel of the vector field animation.
# Tuned by hand for a calm, professional appearance at ~30fps.
NODE_COUNT = 25           # number of drifting dots on screen
NODE_MIN_R = 3            # smallest node radius (px)
NODE_MAX_R = 6            # largest node radius (px)
DRIFT_MIN = 0.3           # slowest drift speed (px/frame)
DRIFT_MAX = 0.8           # fastest drift speed (px/frame)
CONN_DIST = 120           # max px between nodes to draw a connection line
SPARK_TRAVEL = 30         # frames for a spark to travel one connection
SPARK_SPAWN_INTERVAL = 18 # frames between new sparks (~600ms at 30fps)
FRAME_MS = 33             # milliseconds per frame (~30 fps)
FADEOUT_HOLD_MS = 400     # hold "Complete!" banner before slide-up begins
FADEOUT_STEPS = 6         # number of slide-up animation steps
FADEOUT_STEP_MS = 50      # milliseconds between slide-up steps


def _lerp_color(hex_a, hex_b, t):
    """Linearly interpolate between two hex colors. t in [0, 1]."""
    ra, ga, ba = int(hex_a[1:3], 16), int(hex_a[3:5], 16), int(hex_a[5:7], 16)
    rb, gb, bb = int(hex_b[1:3], 16), int(hex_b[3:5], 16), int(hex_b[5:7], 16)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


class _Node:
    """A single drifting node in the vector field."""
    __slots__ = ("x", "y", "vx", "vy", "r", "brightness")

    def __init__(self, w, h):
        self.x = random.uniform(20, w - 20)
        self.y = random.uniform(20, h - 20)
        speed = random.uniform(DRIFT_MIN, DRIFT_MAX)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)
        self.r = random.randint(NODE_MIN_R, NODE_MAX_R)
        self.brightness = random.uniform(0.4, 1.0)


class _Spark:
    """A bright dot traveling along a connection between two nodes."""
    __slots__ = ("a", "b", "frame", "total")

    def __init__(self, node_a, node_b):
        self.a = node_a
        self.b = node_b
        self.frame = 0
        self.total = SPARK_TRAVEL

    @property
    def done(self):
        return self.frame >= self.total

    def pos(self):
        t = self.frame / self.total
        x = self.a.x + (self.b.x - self.a.x) * t
        y = self.a.y + (self.b.y - self.a.y) * t
        return x, y


class VectorFieldOverlay(tk.Canvas):
    """Animated vector field overlay for long-running queries.

    Place this over the answer area during query execution.  Call
    start() to show it, set_phase() to update the banner, and stop()
    to slide it away and reveal the answer beneath.
    """

    def __init__(self, parent, theme=None):
        t = theme or current_theme()
        super().__init__(
            parent, bg=t["bg"], highlightthickness=0, bd=0,
        )
        self._theme = t
        self._parent = parent
        self._nodes = []
        self._sparks = []
        self._connections = []
        self._running = False
        self._anim_id = None
        self._phase_text = ""
        self._frame_count = 0
        self._full_height = 0     # remembered for slide-up restore
        self._fadeout_id = None

    # ----------------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------------

    def start(self, phase_text="Searching documents..."):
        """Show the overlay and begin animation."""
        self._phase_text = phase_text
        self._running = True
        self._frame_count = 0
        self._sparks.clear()

        # Place over the answer area using place() geometry manager
        self.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        self.lift()   # ensure on top

        # Build nodes once we know actual size (after place renders)
        self.update_idletasks()
        w = self.winfo_width() or 400
        h = self.winfo_height() or 200
        self._full_height = h
        self._nodes = [_Node(w, h) for _ in range(NODE_COUNT)]

        self._schedule_frame()

    def set_phase(self, text):
        """Update the banner text to reflect a new processing phase."""
        self._phase_text = text

    def stop(self, on_complete=None):
        """Stop animation, show 'Complete!', then slide away."""
        if not self._running:
            # Already stopped or never started
            self.place_forget()
            if on_complete:
                on_complete()
            return

        self._running = False
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

        # Flash "Complete!" banner
        t = self._theme
        self.delete("all")
        w = self.winfo_width() or 400
        h = self.winfo_height() or 200
        self.create_text(
            w // 2, h // 2, text="Complete!",
            fill=t["green"], font=FONT_BOLD, tags="banner",
        )

        # After a brief hold, begin slide-up
        self._fadeout_id = self.after(
            FADEOUT_HOLD_MS,
            lambda: self._slide_up(0, on_complete),
        )

    def apply_theme(self, t):
        """Update theme colors for the overlay."""
        self._theme = t
        self.configure(bg=t["bg"])

    # ----------------------------------------------------------------
    # ANIMATION LOOP
    # ----------------------------------------------------------------

    def _schedule_frame(self):
        """Schedule the next animation frame."""
        if self._running:
            self._anim_id = self.after(FRAME_MS, self._animate)

    def _animate(self):
        """Single animation frame: move, connect, spark, draw."""
        if not self._running:
            return

        w = self.winfo_width() or 400
        h = self.winfo_height() or 200
        t = self._theme
        self._frame_count += 1

        # -- Move nodes (wrap at edges) --
        for n in self._nodes:
            n.x += n.vx
            n.y += n.vy
            if n.x < 0:
                n.x += w
            elif n.x > w:
                n.x -= w
            if n.y < 0:
                n.y += h
            elif n.y > h:
                n.y -= h

        # -- Find connections (pairs within CONN_DIST) --
        self._connections.clear()
        for i in range(len(self._nodes)):
            for j in range(i + 1, len(self._nodes)):
                a, b = self._nodes[i], self._nodes[j]
                dx = a.x - b.x
                dy = a.y - b.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < CONN_DIST:
                    self._connections.append((a, b, dist))

        # -- Spawn sparks --
        if (self._frame_count % SPARK_SPAWN_INTERVAL == 0
                and self._connections):
            pair = random.choice(self._connections)
            self._sparks.append(_Spark(pair[0], pair[1]))

        # -- Advance sparks --
        for s in self._sparks:
            s.frame += 1
        self._sparks = [s for s in self._sparks if not s.done]

        # -- Draw everything --
        self.delete("all")

        # Connections (dim lines)
        conn_color = t.get("border", "#555555")
        for a, b, dist in self._connections:
            # Fade line opacity based on distance
            alpha = 1.0 - (dist / CONN_DIST)
            line_color = _lerp_color(t["bg"], conn_color, alpha * 0.6)
            self.create_line(a.x, a.y, b.x, b.y, fill=line_color, width=1)

        # Nodes (accent-colored circles)
        accent = t.get("accent", "#0078d4")
        for n in self._nodes:
            node_color = _lerp_color(t["bg"], accent, n.brightness)
            self.create_oval(
                n.x - n.r, n.y - n.r, n.x + n.r, n.y + n.r,
                fill=node_color, outline="",
            )

        # Sparks (bright traveling dots)
        spark_color = "#ffffff"
        for s in self._sparks:
            sx, sy = s.pos()
            sr = 2
            self.create_oval(
                sx - sr, sy - sr, sx + sr, sy + sr,
                fill=spark_color, outline="",
            )

        # Banner text
        banner_y = h - 24
        self.create_text(
            w // 2, banner_y, text=self._phase_text,
            fill=t.get("accent", "#0078d4"), font=FONT_BOLD,
        )

        self._schedule_frame()

    # ----------------------------------------------------------------
    # SLIDE-UP FADEOUT
    # ----------------------------------------------------------------

    def _slide_up(self, step, on_complete):
        """Progressively reduce height to simulate slide-up removal."""
        if step >= FADEOUT_STEPS:
            self.place_forget()
            if on_complete:
                on_complete()
            return

        # Reduce relheight each step
        frac = 1.0 - ((step + 1) / FADEOUT_STEPS)
        self.place_configure(relheight=max(frac, 0.0))

        self._fadeout_id = self.after(
            FADEOUT_STEP_MS,
            lambda: self._slide_up(step + 1, on_complete),
        )

    # ----------------------------------------------------------------
    # CLEANUP
    # ----------------------------------------------------------------

    def cancel(self):
        """Hard-cancel without animation (for error paths)."""
        self._running = False
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        if self._fadeout_id is not None:
            self.after_cancel(self._fadeout_id)
            self._fadeout_id = None
        self.place_forget()
