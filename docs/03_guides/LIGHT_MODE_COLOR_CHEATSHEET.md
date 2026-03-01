# Light Mode Color Cheat Sheet

Purpose: quick reference for fixing light-mode readability issues (especially white-on-white boxes).

## Where to Edit

- Theme source: `src/gui/theme.py`
- Light palette dictionary: `LIGHT = { ... }`
- ttk widget paint logic: `apply_ttk_styles(theme_dict)`

## Fastest Fixes (Most Impact)

Edit these keys in `LIGHT` first:

- `bg`: app background
- `panel_bg`: panel/card background
- `input_bg`: text entry / combobox field background
- `border`: outlines between similar light surfaces
- `separator`: status-bar and panel separators
- `label_fg`: secondary text contrast
- `gray`: tertiary/status text contrast

Recommended high-clarity light palette:

```python
LIGHT = {
    "name": "light",
    "bg": "#eef1f5",          # app chrome
    "panel_bg": "#f8fafc",    # panel cards (not pure white)
    "fg": "#111111",
    "input_bg": "#ffffff",    # keep inputs white for affordance
    "input_fg": "#111111",
    "accent": "#006fc7",
    "accent_fg": "#ffffff",
    "accent_hover": "#005da8",
    "border": "#b8c0cc",      # stronger outlines
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
```

## Why White-on-White Happens

- Current light mode uses both:
  - `panel_bg = #ffffff`
  - `input_bg = #ffffff`
- If `border` is also light (`#cccccc`), entry boxes can visually blend into panel cards.

## ttk Caveat (Important)

`tk` and `ttk` widgets are styled in different places:

- `tk.*` widgets read color values directly in each panel.
- `ttk.*` widgets (Combobox, Progressbar, etc.) are controlled by `apply_ttk_styles()`.

If you only change `LIGHT` but do not ensure `apply_ttk_styles()` uses those keys for ttk states, some controls can still look stale.

## High-Value ttk Checks

In `apply_ttk_styles()` verify:

- `TCombobox`
  - `fieldbackground = t["input_bg"]`
  - `bordercolor = t["border"]`
  - `foreground = t["input_fg"]`
- `TScrollbar`
  - `background = t["scrollbar_bg"]`
  - `troughcolor = t["bg"]`
- `TLabelframe`
  - `bordercolor = t["border"]`

## Quick QA Pass (2 minutes)

1. Launch GUI, switch to Light mode.
2. Check Query panel:
   - question box edge is obvious
   - model/use-case comboboxes are clearly bounded
3. Check Downloader panel:
   - path entry is visually distinct from panel background
4. Check Status bar:
   - separators are visible
   - gray informational text is readable
5. Hover buttons:
   - hover state is visible but not jarring

## Safe Adjustment Order

Use this order to avoid over-tuning:

1. `border` and `separator`
2. `panel_bg` (off pure white)
3. `label_fg` and `gray`
4. `scrollbar_bg` / `inactive_btn_bg`
5. Accent shades last

## If You Want a One-Line Rule

Keep `panel_bg` slightly darker than white, keep `input_bg` pure white, and make `border` at least medium contrast.
