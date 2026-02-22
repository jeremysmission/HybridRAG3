# ============================================================================
# HybridRAG v3 -- GUI Theme Engine (src/gui/theme.py)
# ============================================================================
# Centralized dark/light theme with ttk clam styling.
# No external dependencies -- uses ttk built-in clam theme + manual colors.
#
# Palette (dark):
#   Background:  #1e1e1e
#   Panel bg:    #2d2d2d
#   Text:        #ffffff
#   Input bg:    #3c3c3c
#   Accent:      #0078d4
#   Font:        Segoe UI 10pt
#   Buttons:     flat, rounded, 6px padding
# ============================================================================

from tkinter import ttk

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
FONT = (FONT_FAMILY, FONT_SIZE)
FONT_BOLD = (FONT_FAMILY, FONT_SIZE, "bold")
FONT_TITLE = (FONT_FAMILY, 14, "bold")
FONT_SMALL = (FONT_FAMILY, 9)

DARK = {
    "name": "dark",
    "bg": "#1e1e1e",
    "panel_bg": "#2d2d2d",
    "fg": "#ffffff",
    "input_bg": "#3c3c3c",
    "input_fg": "#ffffff",
    "accent": "#0078d4",
    "accent_fg": "#ffffff",
    "accent_hover": "#1a8ae8",
    "border": "#555555",
    "label_fg": "#cccccc",
    "disabled_fg": "#777777",
    "green": "#2ea043",
    "red": "#f85149",
    "orange": "#d29922",
    "gray": "#888888",
    "menu_bg": "#2d2d2d",
    "menu_fg": "#ffffff",
    "scrollbar_bg": "#3c3c3c",
    "scrollbar_fg": "#666666",
    "separator": "#555555",
    "active_btn_bg": "#2ea043",
    "active_btn_fg": "#ffffff",
    "inactive_btn_bg": "#3c3c3c",
    "inactive_btn_fg": "#cccccc",
}

LIGHT = {
    "name": "light",
    "bg": "#f0f0f0",
    "panel_bg": "#ffffff",
    "fg": "#000000",
    "input_bg": "#ffffff",
    "input_fg": "#000000",
    "accent": "#0078d4",
    "accent_fg": "#ffffff",
    "accent_hover": "#1a8ae8",
    "border": "#cccccc",
    "label_fg": "#333333",
    "disabled_fg": "#999999",
    "green": "#008000",
    "red": "#cc0000",
    "orange": "#cc8800",
    "gray": "#888888",
    "menu_bg": "#f0f0f0",
    "menu_fg": "#000000",
    "scrollbar_bg": "#e0e0e0",
    "scrollbar_fg": "#b0b0b0",
    "separator": "#cccccc",
    "active_btn_bg": "#008000",
    "active_btn_fg": "#ffffff",
    "inactive_btn_bg": "#e0e0e0",
    "inactive_btn_fg": "#333333",
}

# Default theme
_current = DARK


def current_theme():
    """Return the currently active theme dict."""
    return _current


def set_theme(theme_dict):
    """Set the active theme dict (DARK or LIGHT)."""
    global _current
    _current = theme_dict


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

    # TLabelframe
    style.configure("TLabelframe", background=t["panel_bg"],
                     foreground=t["fg"], bordercolor=t["border"],
                     relief="groove")
    style.configure("TLabelframe.Label", background=t["panel_bg"],
                     foreground=t["accent"], font=FONT_BOLD)

    # TButton
    style.configure("TButton", background=t["accent"],
                     foreground=t["accent_fg"], font=FONT,
                     padding=(6, 4), relief="flat", borderwidth=0)
    style.map("TButton",
              background=[("active", t["accent_hover"]),
                          ("disabled", t["disabled_fg"])],
              foreground=[("disabled", t["bg"])])

    # Accent.TButton (for the main action buttons)
    style.configure("Accent.TButton", background=t["accent"],
                     foreground=t["accent_fg"], font=FONT_BOLD,
                     padding=(6, 4), relief="flat")
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
