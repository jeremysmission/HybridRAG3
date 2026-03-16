"""Widget construction for IndexPanel -- extracted to keep class under 500 lines.

Called once from IndexPanel.__init__. All widgets are assigned as attributes
on the panel instance so the rest of the class can reference them.
"""

import os
import tkinter as tk
from tkinter import ttk

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover


def _build_index_panel_widgets(panel, t):
    """Build all child widgets for an IndexPanel instance."""

    # -- Row 0: Source folder --
    row0 = tk.Frame(panel, bg=t["panel_bg"])
    row0.pack(fill=tk.X, pady=(0, 4))

    panel.folder_label = tk.Label(row0, text="Source:",
                                  bg=t["panel_bg"], fg=t["label_fg"],
                                  font=FONT)
    panel.folder_label.pack(side=tk.LEFT)

    default_source = getattr(
        getattr(panel.config, "paths", None), "source_folder", ""
    ) or ""

    panel.folder_var = tk.StringVar(value=default_source)
    panel.folder_display = tk.Label(
        row0, textvariable=panel.folder_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    )
    panel.folder_display.pack(side=tk.LEFT, fill=tk.X, expand=True,
                              padx=(8, 0))

    panel._change_source_btn = tk.Button(
        row0, text="Change...", command=panel._on_change_source, width=10,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=4,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    panel._change_source_btn.pack(side=tk.RIGHT, padx=(8, 0))
    bind_hover(panel._change_source_btn)

    # -- Row 0b: Index folder --
    row0b = tk.Frame(panel, bg=t["panel_bg"])
    row0b.pack(fill=tk.X, pady=(0, 8))

    panel.index_label = tk.Label(row0b, text="Index:",
                                 bg=t["panel_bg"], fg=t["label_fg"],
                                 font=FONT)
    panel.index_label.pack(side=tk.LEFT)

    db_path = getattr(
        getattr(panel.config, "paths", None), "database", ""
    ) or ""
    index_default = os.path.dirname(db_path) if db_path else "(not set)"

    panel.index_var = tk.StringVar(value=index_default)
    panel.index_display = tk.Label(
        row0b, textvariable=panel.index_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    )
    panel.index_display.pack(side=tk.LEFT, fill=tk.X, expand=True,
                             padx=(8, 0))

    panel._change_index_btn = tk.Button(
        row0b, text="Change...", command=panel._on_change_index, width=10,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=4,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    panel._change_index_btn.pack(side=tk.RIGHT, padx=(8, 0))
    bind_hover(panel._change_index_btn)

    panel.paths_hint = tk.Label(
        row0b, text="",
        bg=t["panel_bg"], fg=t["gray"], font=("Segoe UI", 8),
    )
    panel.paths_hint.pack(side=tk.RIGHT)

    # -- Status indicator --
    panel._status_var = tk.StringVar(value="Waiting for backends...")
    panel._status_label = tk.Label(
        panel, textvariable=panel._status_var,
        bg=t["panel_bg"], fg=t.get("yellow", "#e8a838"),
        font=FONT_SMALL, anchor=tk.W,
    )
    panel._status_label.pack(fill=tk.X, pady=(0, 4))

    # -- Row 1: Controls --
    row1 = tk.Frame(panel, bg=t["panel_bg"])
    row1.pack(fill=tk.X, pady=(0, 8))

    panel.start_btn = tk.Button(
        row1, text="Start Indexing", command=panel._on_start, width=14,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
        font=FONT_BOLD, relief=tk.FLAT, bd=0,
        padx=24, pady=8, state=tk.DISABLED,
        activebackground=t["accent_hover"],
        activeforeground=t["accent_fg"],
    )
    panel.start_btn.pack(side=tk.LEFT)

    panel.stop_btn = tk.Button(
        row1, text="Stop Indexing", command=panel._on_stop, width=12,
        state=tk.DISABLED,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
        font=FONT_BOLD, relief=tk.FLAT, bd=0, padx=16, pady=8,
    )
    panel.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

    if panel._dev_ui_enabled:
        panel._clear_armed_var = tk.BooleanVar(value=False)
        panel.clear_btn = tk.Button(
            row1, text="Clear Index (Dev)", command=panel._on_clear_index,
            width=14,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
            state=tk.DISABLED,
        )
        panel.clear_btn.pack(side=tk.LEFT, padx=(8, 0))
        panel.clear_guard_cb = tk.Checkbutton(
            row1,
            text="Unlock Clear",
            variable=panel._clear_armed_var,
            command=panel._on_toggle_clear_guard,
            bg=t["panel_bg"],
            fg=t["fg"],
            selectcolor=t["input_bg"],
            activebackground=t["panel_bg"],
            activeforeground=t["fg"],
            font=FONT_SMALL,
        )
        panel.clear_guard_cb.pack(side=tk.LEFT, padx=(8, 0))

    panel.progress_file_label = tk.Label(
        row1, text="", anchor=tk.W, fg=t["gray"],
        bg=t["panel_bg"], font=FONT,
    )
    panel.progress_file_label.pack(side=tk.LEFT, padx=(16, 0),
                                   fill=tk.X, expand=True)

    # -- Row 2: Progress bar --
    row2 = tk.Frame(panel, bg=t["panel_bg"])
    row2.pack(fill=tk.X, pady=(0, 8))

    panel.progress_bar = ttk.Progressbar(
        row2, mode="determinate", length=400,
    )
    panel.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

    panel.progress_count_label = tk.Label(
        row2, text="0 / 0 files", anchor=tk.W, padx=8,
        bg=t["panel_bg"], fg=t["fg"], font=FONT_MONO,
    )
    panel.progress_count_label.pack(side=tk.LEFT)

    # -- Row 3: Last run info --
    panel.last_run_label = tk.Label(
        panel, text="Last run: (none)", anchor=tk.W, fg=t["gray"],
        bg=t["panel_bg"], font=FONT,
    )
    panel.last_run_label.pack(fill=tk.X)

    # -- Row 4: Live telemetry --
    panel.index_stats_label = tk.Label(
        panel,
        text="Telemetry: chunks 0 | files skipped 0 | file errors 0 | rate -- chunks/s | ETA --",
        anchor=tk.W, fg=t["gray"], bg=t["panel_bg"], font=FONT_SMALL,
    )
    panel.index_stats_label.pack(fill=tk.X, pady=(2, 0))
