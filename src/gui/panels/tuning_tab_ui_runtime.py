# TuningTab runtime: widget factories (slider/entry/check rows) and theme.
from __future__ import annotations

import tkinter as tk

from src.gui.panels.settings_view import _theme_widget
from src.gui.theme import FONT, FONT_SMALL
from src.gui.panels.tuning_tab_sections_runtime import (
    bind_tuning_tab_sections_runtime_methods,
)

# ------------------------------------------------------------------
# Widget factory helpers
# ------------------------------------------------------------------


def _build_slider_row(self, parent, theme, key, label, var, from_, to_, resolution=1, on_change=None):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)
    self._row_frames[key] = row

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    scale = tk.Scale(
        row,
        from_=from_,
        to=to_,
        resolution=resolution,
        orient=tk.HORIZONTAL,
        variable=var,
        command=lambda _value: on_change() if on_change else None,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        troughcolor=theme["input_bg"],
        highlightthickness=0,
        font=FONT,
    )
    scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def_var = tk.BooleanVar(value=False)
    checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._scales[key] = scale
    return scale


def _build_entry_row(self, parent, theme, key, label, var, on_change=None, width=12):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)
    self._row_frames[key] = row

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    entry = tk.Entry(
        row,
        textvariable=var,
        width=width,
        bg=theme["input_bg"],
        fg=theme["fg"],
        insertbackground=theme["fg"],
        relief=tk.FLAT,
        font=FONT,
    )
    entry.pack(side=tk.LEFT, padx=(0, 8))
    if on_change is not None:
        entry.bind("<FocusOut>", lambda _event: on_change())
        entry.bind("<Return>", lambda _event: on_change())

    def_var = tk.BooleanVar(value=False)
    checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._scales[key] = entry
    return entry


def _build_check_row(self, parent, theme, key, label, var, on_change=None):
    row = tk.Frame(parent, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=3)
    self._row_frames[key] = row

    tk.Label(row, text=label, width=16, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT).pack(
        side=tk.LEFT
    )

    checkbox = tk.Checkbutton(
        row,
        variable=var,
        command=on_change,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT,
    )
    checkbox.pack(side=tk.LEFT)

    def_var = tk.BooleanVar(value=False)
    default_checkbox = tk.Checkbutton(
        row,
        text="Default",
        variable=def_var,
        command=lambda: self._on_default_toggle(key, var, def_var, on_change),
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    )
    default_checkbox.pack(side=tk.RIGHT, padx=(4, 0))

    self._default_vars[key] = def_var
    self._check_widgets[key] = checkbox
    return checkbox


# ------------------------------------------------------------------
# Theme application
# ------------------------------------------------------------------


def apply_theme(self, theme):
    self.configure(bg=theme["panel_bg"])
    if hasattr(self, "_editor_split"):
        self._editor_split.configure(bg=theme["panel_bg"])
    if hasattr(self, "_retrieval_column"):
        self._retrieval_column.configure(bg=theme["panel_bg"])
    if hasattr(self, "_query_column"):
        self._query_column.configure(bg=theme["panel_bg"])
    for frame_attr in ("_retrieval_frame", "_query_policy_frame", "_generation_frame", "_profile_frame"):
        frame = getattr(self, frame_attr, None)
        if frame:
            frame.configure(bg=theme["panel_bg"], fg=theme["accent"])
            for child in frame.winfo_children():
                _theme_widget(child, theme)
    if hasattr(self, "_reset_frame"):
        self._reset_frame.configure(bg=theme["panel_bg"])
        self._save_mode_defaults_btn.configure(bg=theme["accent"], fg=theme["accent_fg"])
        self._reset_btn.configure(bg=theme["inactive_btn_bg"], fg=theme["inactive_btn_fg"])
        self._lock_all_btn.configure(bg=theme["inactive_btn_bg"], fg=theme["inactive_btn_fg"])
    if hasattr(self, "_mode_row"):
        self._mode_row.configure(bg=theme["panel_bg"])
        self._mode_banner.configure(bg=theme["panel_bg"], fg=theme["accent"])
        self._mode_status.configure(bg=theme["panel_bg"], fg=theme["gray"])


# ------------------------------------------------------------------
# Bind -- widget factories + theme, then delegate section builders
# ------------------------------------------------------------------


def bind_tuning_tab_ui_runtime_methods(tab_cls):
    """Bind UI-building runtime methods to TuningTab."""
    tab_cls._build_slider_row = _build_slider_row
    tab_cls._build_entry_row = _build_entry_row
    tab_cls._build_check_row = _build_check_row
    tab_cls.apply_theme = apply_theme
    # Section builders live in their own sub-module
    bind_tuning_tab_sections_runtime_methods(tab_cls)
