# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the settings panel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Settings panel UI for viewing and editing application configuration
from __future__ import annotations

import os
import sys
import platform
import tkinter as tk
import logging

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover

logger = logging.getLogger(__name__)


def _theme_widget(widget, t):
    """Recursively apply theme to a widget and its children."""
    try:
        wclass = widget.winfo_class()
        if wclass == "Frame":
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


class SettingsPanel(tk.Frame):
    """Lightweight system-info and preferences panel.

    Shows current mode, offline model, Python/OS versions, config paths,
    and cache management. Distinct from Tuning (parameter sliders) and
    Admin (API credentials, model selection, data paths).
    """

    def __init__(self, parent, config=None, app_ref=None):
        """Plain-English: Sets up the SettingsPanel object and prepares state used by its methods."""
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref
        self._build(t)

    def _build(self, t):
        # -- Header --
        """Plain-English: Creates this panel's widgets and lays them out in the visible UI."""
        tk.Label(
            self, text="System Settings", font=FONT_BOLD,
            bg=t["panel_bg"], fg=t["fg"],
        ).pack(anchor=tk.W, padx=16, pady=(16, 8))

        # -- System Info --
        info_frame = tk.LabelFrame(
            self, text="System Information", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        info_frame.pack(fill=tk.X, padx=16, pady=4)

        rows = [
            ("Python", "{} ({})".format(
                platform.python_version(), sys.executable)),
            ("Platform", "{} {}".format(platform.system(), platform.release())),
            ("Architecture", platform.machine()),
        ]

        # Current mode
        mode = "unknown"
        if self.config:
            mode = getattr(self.config, "mode", "unknown")
        rows.append(("Mode", mode.upper()))

        # Current offline model
        model = "unknown"
        if self.config:
            ollama = getattr(self.config, "ollama", None)
            if ollama:
                model = getattr(ollama, "model", "unknown")
        rows.append(("Offline Model", model))

        for label_text, value_text in rows:
            row = tk.Frame(info_frame, bg=t["panel_bg"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row, text="{}:".format(label_text), width=16, anchor=tk.W,
                bg=t["panel_bg"], fg=t["label_fg"], font=FONT,
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=value_text, anchor=tk.W,
                bg=t["panel_bg"], fg=t["fg"], font=FONT_MONO,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Config Paths --
        paths_frame = tk.LabelFrame(
            self, text="Configuration Paths", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        paths_frame.pack(fill=tk.X, padx=16, pady=4)

        root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
        path_rows = [
            ("Project Root", root),
            ("Config", os.path.join(root, "config", "default_config.yaml")),
        ]
        if self.config:
            paths = getattr(self.config, "paths", None)
            if paths:
                path_rows.append(("Source Folder", getattr(paths, "source_folder", "")))
                path_rows.append(("Database", getattr(paths, "database", "")))

        for label_text, value_text in path_rows:
            row = tk.Frame(paths_frame, bg=t["panel_bg"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row, text="{}:".format(label_text), width=16, anchor=tk.W,
                bg=t["panel_bg"], fg=t["label_fg"], font=FONT,
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=value_text or "(not set)", anchor=tk.W,
                bg=t["panel_bg"], fg=t["fg"], font=FONT_SMALL,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Actions --
        actions_frame = tk.LabelFrame(
            self, text="Actions", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        actions_frame.pack(fill=tk.X, padx=16, pady=4)

        btn_row = tk.Frame(actions_frame, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=4)

        reset_btn = tk.Button(
            btn_row, text="Reset Backends", width=16, font=FONT,
            command=self._on_reset,
            bg=t["accent"], fg=t["accent_fg"],
            relief=tk.FLAT, bd=0, padx=12, pady=6,
        )
        reset_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(reset_btn)

        self._status_label = tk.Label(
            actions_frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._status_label.pack(fill=tk.X)

    def _on_reset(self):
        """Plain-English: Resets setting controls back to defaults and refreshes visible values."""
        if self._app and hasattr(self._app, "reset_backends"):
            self._app.reset_backends()
            self._status_label.config(text="Backends reset -- reloading...")

    def apply_theme(self, t):
        """Plain-English: Reapplies colors and style settings so the view matches the active theme."""
        self.configure(bg=t["panel_bg"])
        _theme_widget(self, t)
