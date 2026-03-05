# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the theme part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- GUI Theme Engine (src/gui/theme.py)
# ============================================================================
# WHAT: Centralized color palettes and font definitions for dark/light themes.
# WHY:  Every widget in the GUI reads its colors from here, so changing
#       one value here changes it everywhere.  This prevents the "50 shades
#       of slightly-different-gray" problem that plagues hand-coded UIs.
# HOW:  Two dictionaries (DARK, LIGHT) with identical keys.  The active
#       theme is stored in a module-level variable swapped by set_theme().
#       ttk widgets use apply_ttk_styles(); tk widgets read current_theme().
# USAGE: from src.gui.theme import current_theme, FONT, FONT_BOLD
#        t = current_theme()
#        label = tk.Label(parent, bg=t["panel_bg"], fg=t["fg"], font=FONT)
#
# COLOR SCHEME RATIONALE:
#   Dark mode default -- matches VS Code / modern tooling expectations.
#   Accent #0078d4 -- Windows system blue, universally recognized as
#                     "clickable" without accessibility issues.
#   Green/Orange/Red -- traffic light pattern for status indicators
#                       (green=good, orange=caution, red=error).
#
# FONT CHOICES:
#   Segoe UI -- Windows system font, renders crisply at all DPI levels.
#   Consolas -- monospace for code, metrics, and aligned tables.
#   11pt body -- large enough for readability at arm's length (demo use).
#
# Button hierarchy (research-based sizing):
#   Primary  (Accent.TButton):   24x10 padding, bold  -- Ask, Start Indexing
#   Secondary (TButton):         16x8 padding, normal -- Browse, Run Test
#   Tertiary (Tertiary.TButton): 12x6 padding, subtle -- Reset, Stop, Close
#
# Spacing: 8px grid (0, 4, 8, 16, 24, 32)
# ============================================================================

from tkinter import ttk

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 11

# Base sizes (unscaled) -- used to recalculate on zoom
_BASE_SIZES = {
    "FONT": 11,
    "FONT_BOLD": 11,
    "FONT_TITLE": 15,
    "FONT_SECTION": 13,
    "FONT_SMALL": 10,
    "FONT_MONO": 10,
}
_zoom_factor = 1.0

FONT = (FONT_FAMILY, FONT_SIZE)
FONT_BOLD = (FONT_FAMILY, FONT_SIZE, "bold")
FONT_TITLE = (FONT_FAMILY, 15, "bold")
FONT_SECTION = (FONT_FAMILY, 13, "bold")
FONT_SMALL = (FONT_FAMILY, 10)
FONT_MONO = ("Consolas", 10)

# --- DARK THEME (default) ---
# Modeled after VS Code's dark theme for familiarity with developers.
DARK = {
    "name": "dark",
    "bg": "#1e1e1e",
    "panel_bg": "#2d2d2d",
    "fg": "#ffffff",
    "input_bg": "#3c3c3c",
    "input_fg": "#ffffff",
    "accent": "#0078d4",
    "accent_fg": "#ffffff",
    "accent_hover": "#106ebe",
    "border": "#555555",
    "label_fg": "#a0a0a0",
    "disabled_fg": "#777777",
    "green": "#4caf50",
    "red": "#f44336",
    "orange": "#ff9800",
    "gray": "#a0a0a0",
    "menu_bg": "#2d2d2d",
    "menu_fg": "#ffffff",
    "scrollbar_bg": "#3c3c3c",
    "scrollbar_fg": "#666666",
    "separator": "#555555",
    "active_btn_bg": "#4caf50",
    "active_btn_fg": "#ffffff",
    "inactive_btn_bg": "#3c3c3c",
    "inactive_btn_fg": "#a0a0a0",
}

# --- LIGHT THEME ---
# For conference rooms with bright projectors or accessibility needs.
LIGHT = {
    "name": "light",
    "bg": "#eef1f5",
    "panel_bg": "#f8fafc",
    "fg": "#111111",
    "input_bg": "#ffffff",
    "input_fg": "#111111",
    "accent": "#006fc7",
    "accent_fg": "#ffffff",
    "accent_hover": "#005da8",
    "border": "#b8c0cc",
    "label_fg": "#3f4a5a",
    "disabled_fg": "#8a94a6",
    "green": "#2f7d32",
    "red": "#c62828",
    "orange": "#d97706",
    "gray": "#5a6472",
    "menu_bg": "#eef1f5",
    "menu_fg": "#111111",
    "scrollbar_bg": "#d7dde7",
    "scrollbar_fg": "#adb7c6",
    "separator": "#bcc5d3",
    "active_btn_bg": "#2f7d32",
    "active_btn_fg": "#ffffff",
    "inactive_btn_bg": "#dfe5ee",
    "inactive_btn_fg": "#3f4a5a",
}

# --- THEME STATE ---
# Module-level mutable -- swapped by set_theme(), read by current_theme().
_current = DARK


def current_theme():
    """Return the currently active theme dict."""
    return _current


def set_theme(theme_dict):
    """Set the active theme dict (DARK or LIGHT)."""
    global _current
    _current = theme_dict


def get_zoom():
    """Return the current zoom factor (1.0 = 100%)."""
    return _zoom_factor


def set_zoom(factor):
    """Recalculate all FONT tuples for the given zoom factor.

    Args:
        factor: Float zoom multiplier (0.5 = 50%, 1.0 = 100%, 2.0 = 200%).
    """
    global _zoom_factor, FONT, FONT_BOLD, FONT_TITLE, FONT_SECTION
    global FONT_SMALL, FONT_MONO, FONT_SIZE

    _zoom_factor = factor

    def _sz(key):
        """Plain-English: This function handles sz."""
        return max(7, int(_BASE_SIZES[key] * factor))

    FONT_SIZE = _sz("FONT")
    FONT = (FONT_FAMILY, _sz("FONT"))
    FONT_BOLD = (FONT_FAMILY, _sz("FONT_BOLD"), "bold")
    FONT_TITLE = (FONT_FAMILY, _sz("FONT_TITLE"), "bold")
    FONT_SECTION = (FONT_FAMILY, _sz("FONT_SECTION"), "bold")
    FONT_SMALL = (FONT_FAMILY, _sz("FONT_SMALL"))
    FONT_MONO = ("Consolas", _sz("FONT_MONO"))


def apply_ttk_styles(theme_dict):
    """Configure ttk styles for the given theme palette."""
    style = ttk.Style()
    style.theme_use("clam")
    t = theme_dict

    # General
    style.configure(".", background=t["bg"], foreground=t["fg"],
                     font=FONT, borderwidth=0)

    # TFrame
    style.configure("TFrame", background=t["bg"])

    # TLabel
    style.configure("TLabel", background=t["bg"], foreground=t["fg"],
                     font=FONT)

    # TLabelframe (flat border, modern card style)
    style.configure("TLabelframe", background=t["panel_bg"],
                     foreground=t["fg"], bordercolor=t["border"],
                     relief="flat")
    style.configure("TLabelframe.Label", background=t["panel_bg"],
                     foreground=t["accent"], font=FONT_BOLD)

    # TButton (secondary actions: Browse, Run Test)
    style.configure("TButton", background=t["accent"],
                     foreground=t["accent_fg"], font=FONT,
                     padding=(16, 8), relief="flat", borderwidth=0)
    style.map("TButton",
              background=[("active", t["accent_hover"]),
                          ("disabled", t["disabled_fg"])],
              foreground=[("disabled", t["bg"])])

    # Accent.TButton (primary actions: Ask, Start Indexing)
    style.configure("Accent.TButton", background=t["accent"],
                     foreground=t["accent_fg"], font=FONT_BOLD,
                     padding=(24, 10), relief="flat")

    # Tertiary.TButton (subtle actions: Reset, Stop, Close, Theme)
    style.configure("Tertiary.TButton", background=t["input_bg"],
                     foreground=t["fg"], font=FONT,
                     padding=(12, 6), relief="flat", borderwidth=0)
    style.map("Tertiary.TButton",
              background=[("active", t["border"]),
                          ("disabled", t["disabled_fg"])],
              foreground=[("disabled", t["bg"])])
    style.map("Accent.TButton",
              background=[("active", t["accent_hover"])])

    # TCombobox
    style.configure("TCombobox", fieldbackground=t["input_bg"],
                     background=t["input_bg"], foreground=t["input_fg"],
                     arrowcolor=t["fg"], bordercolor=t["border"],
                     selectbackground=t["accent"],
                     selectforeground=t["accent_fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", t["input_bg"])],
              foreground=[("readonly", t["input_fg"])],
              selectbackground=[("readonly", t["accent"])],
              selectforeground=[("readonly", t["accent_fg"])])

    # Horizontal.TProgressbar
    style.configure("Horizontal.TProgressbar",
                     troughcolor=t["input_bg"],
                     background=t["accent"],
                     bordercolor=t["border"],
                     lightcolor=t["accent"],
                     darkcolor=t["accent"])

    # TCheckbutton
    style.configure("TCheckbutton", background=t["panel_bg"],
                     foreground=t["fg"], font=FONT,
                     indicatorcolor=t["input_bg"])
    style.map("TCheckbutton",
              background=[("active", t["panel_bg"])],
              indicatorcolor=[("selected", t["accent"])])

    # TScale
    style.configure("TScale", background=t["panel_bg"],
                     troughcolor=t["input_bg"],
                     bordercolor=t["border"],
                     sliderrelief="flat")
    style.map("TScale",
              background=[("active", t["accent"])])

    # TScrollbar
    style.configure("TScrollbar", background=t["scrollbar_bg"],
                     troughcolor=t["bg"],
                     arrowcolor=t["fg"],
                     bordercolor=t["border"])
    style.map("TScrollbar",
              background=[("active", t["scrollbar_fg"])])


def _lighten_hex(hex_color, factor=0.15):
    """Lighten a hex color by blending toward white."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def bind_hover(widget, normal_bg=None, normal_fg=None):
    """Bind Enter/Leave events for hover feedback on a tk.Button.

    Call this after creating any tk.Button to give it a visible hover
    state.  On mouse enter the background lightens slightly; on leave
    it reverts.  Disabled buttons are skipped automatically.
    """
    if normal_bg is None:
        normal_bg = str(widget.cget("bg"))
    if normal_fg is None:
        normal_fg = str(widget.cget("fg"))
    hover_bg = _lighten_hex(normal_bg)

    def on_enter(event):
        """Plain-English: This function handles on enter."""
        if str(widget.cget("state")) != "disabled":
            widget.config(bg=hover_bg)

    def on_leave(event):
        """Plain-English: This function handles on leave."""
        if str(widget.cget("state")) != "disabled":
            widget.config(bg=normal_bg)

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)
    # Store refs so theme changes can rebind
    widget._hover_normal_bg = normal_bg
    widget._hover_normal_fg = normal_fg
