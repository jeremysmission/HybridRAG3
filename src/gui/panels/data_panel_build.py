# === NON-PROGRAMMER GUIDE ===
# Purpose: Widget construction for DataPanel -- extracted to keep class under 500 lines.
# What to read first: Called from DataPanel.__init__ via the 5 _build_*_section methods.
# Inputs: DataPanel instance (self) and theme dict (t).
# Outputs: Creates and packs all tkinter widgets as attributes on self.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Widget construction for DataPanel -- extracted to keep class under 500 lines.

Called during DataPanel.__init__. All widgets are assigned as attributes
on the panel instance so the rest of the class can reference them.
"""

import os
import tkinter as tk
from tkinter import ttk

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover


# ================================================================
# SECTION A: Current Source Path
# ================================================================

def _build_source_path_section(self, t):
    """Info bar showing where downloads/transfers land."""
    frame = tk.LabelFrame(
        self, text="Download Destination", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=(8, 4))
    self._source_path_frame = frame

    row = tk.Frame(frame, bg=t["panel_bg"])
    row.pack(fill=tk.X)

    dl_folder = getattr(
        getattr(self.config, "paths", None), "download_folder", ""
    ) or getattr(
        getattr(self.config, "paths", None), "source_folder", ""
    ) or "(not set)"
    self._source_path_var = tk.StringVar(value=dl_folder)

    self._source_path_label = tk.Label(
        row, textvariable=self._source_path_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    )
    self._source_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    self._change_source_btn = tk.Button(
        row, text="Change...", command=self._on_change_source, width=10,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=4,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    self._change_source_btn.pack(side=tk.RIGHT, padx=(8, 0))
    bind_hover(self._change_source_btn)

    # Default persistence toggle (checked by default).
    self._persist_download_var = tk.BooleanVar(value=True)
    self._persist_download_cb = tk.Checkbutton(
        frame, text="Set downloader path as default",
        variable=self._persist_download_var,
        bg=t["panel_bg"], fg=t["fg"],
        selectcolor=t["input_bg"], activebackground=t["panel_bg"],
        activeforeground=t["fg"], font=FONT_SMALL,
    )
    self._persist_download_cb.pack(anchor=tk.W, pady=(4, 0))


# ================================================================
# SECTION B: Transfer Source Browser
# ================================================================

def _build_browser_section(self, t):
    """Drive detection + folder picker for the source to transfer FROM."""
    from src.gui.panels.data_panel import _detect_drives, _drive_from_path

    frame = tk.LabelFrame(
        self, text="Transfer Source (copy FROM here)", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=4)
    self._browser_frame = frame

    # Drive combobox row
    drive_row = tk.Frame(frame, bg=t["panel_bg"])
    drive_row.pack(fill=tk.X, pady=(0, 4))

    tk.Label(
        drive_row, text="Drive:", anchor=tk.W, width=8,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)

    drives = _detect_drives()
    default_transfer_source = getattr(
        getattr(self.config, "paths", None), "transfer_source_folder", ""
    ) or getattr(
        getattr(self.config, "paths", None), "source_folder", ""
    ) or getattr(
        getattr(self.config, "paths", None), "download_folder", ""
    ) or ""
    preferred_drive = _drive_from_path(default_transfer_source)
    # Keep configured/default mapped drive visible even if startup
    # drive detection missed it (common on slow network login).
    if preferred_drive and preferred_drive not in drives:
        drives = [preferred_drive] + drives
    initial_drive = preferred_drive if preferred_drive else (drives[0] if drives else os.environ.get("SystemDrive", "C:") + "\\")
    self._drive_var = tk.StringVar(value=initial_drive)
    self._drive_combo = ttk.Combobox(
        drive_row, textvariable=self._drive_var, values=drives,
        state="readonly", width=8, font=FONT,
    )
    self._drive_combo.pack(side=tk.LEFT, padx=(4, 8))

    self._browse_btn = tk.Button(
        drive_row, text="Browse...", command=self._on_browse, width=10,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=4,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    self._browse_btn.pack(side=tk.LEFT)
    bind_hover(self._browse_btn)

    # UNC / manual path row
    unc_row = tk.Frame(frame, bg=t["panel_bg"])
    unc_row.pack(fill=tk.X, pady=4)

    tk.Label(
        unc_row, text="Path:", anchor=tk.W, width=8,
        bg=t["panel_bg"], fg=t["fg"], font=FONT,
    ).pack(side=tk.LEFT)

    self._selected_path_var = tk.StringVar(value=default_transfer_source)
    self._path_entry = tk.Entry(
        unc_row, textvariable=self._selected_path_var, font=FONT,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
    )
    self._path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))

    self._preview_btn = tk.Button(
        unc_row, text="Preview", command=self._on_preview, width=10,
        bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=4,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    self._preview_btn.pack(side=tk.LEFT)
    bind_hover(self._preview_btn)

    self._persist_transfer_source_var = tk.BooleanVar(value=True)
    self._persist_transfer_source_cb = tk.Checkbutton(
        frame, text="Set transfer source as default",
        variable=self._persist_transfer_source_var,
        bg=t["panel_bg"], fg=t["fg"],
        selectcolor=t["input_bg"], activebackground=t["panel_bg"],
        activeforeground=t["fg"], font=FONT_SMALL,
    )
    self._persist_transfer_source_cb.pack(anchor=tk.W, pady=(2, 0))


# ================================================================
# SECTION C: Source Preview
# ================================================================

def _build_preview_section(self, t):
    """Preview area showing file counts and extension breakdown."""
    frame = tk.LabelFrame(
        self, text="Source Preview", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=4)
    self._preview_frame = frame

    self._preview_text = tk.Text(
        frame, height=6, wrap=tk.WORD, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        state=tk.DISABLED,
    )
    self._preview_text.pack(fill=tk.X)


def _set_preview_text(self, text):
    """Update the preview text widget (main thread)."""
    self._preview_text.config(state=tk.NORMAL)
    self._preview_text.delete("1.0", tk.END)
    self._preview_text.insert("1.0", text)
    self._preview_text.config(state=tk.DISABLED)


# ================================================================
# SECTION D: Transfer Controls
# ================================================================

def _build_transfer_section(self, t):
    """Start/stop buttons, progress bar, live stats."""
    frame = tk.LabelFrame(
        self, text="Transfer", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    frame.pack(fill=tk.X, padx=16, pady=4)
    self._transfer_frame = frame

    # Button row
    btn_row = tk.Frame(frame, bg=t["panel_bg"])
    btn_row.pack(fill=tk.X, pady=(0, 4))

    self._start_btn = tk.Button(
        btn_row, text="Start Transfer", command=self._on_start_transfer,
        width=14, bg=t["accent"], fg=t["accent_fg"], font=FONT_BOLD,
        relief=tk.FLAT, bd=0, padx=24, pady=8,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    self._start_btn.pack(side=tk.LEFT)
    bind_hover(self._start_btn)

    self._stop_btn = tk.Button(
        btn_row, text="Stop", command=self._on_stop_transfer,
        width=8, state=tk.DISABLED,
        bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=8,
    )
    self._stop_btn.pack(side=tk.LEFT, padx=(8, 0))

    tk.Label(
        btn_row, text="Estimated total (GB, optional):",
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(side=tk.LEFT, padx=(12, 4))
    self._est_total_gb_var = tk.StringVar(value="")
    self._est_total_gb_entry = tk.Entry(
        btn_row, textvariable=self._est_total_gb_var, width=8,
        bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"],
        relief=tk.FLAT, bd=1, font=FONT_SMALL,
    )
    self._est_total_gb_entry.pack(side=tk.LEFT)
    self._est_total_gb_entry.bind("<Return>", self._on_apply_estimate)
    self._est_total_gb_entry.bind("<FocusOut>", self._on_apply_estimate)

    self._apply_est_btn = tk.Button(
        btn_row, text="Apply ETA", command=self._on_apply_estimate,
        width=9, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
        font=FONT_SMALL, relief=tk.FLAT, bd=0, padx=8, pady=4,
    )
    self._apply_est_btn.pack(side=tk.LEFT, padx=(6, 0))

    self._transfer_status = tk.Label(
        btn_row, text="", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._transfer_status.pack(side=tk.LEFT, padx=(16, 0),
                                fill=tk.X, expand=True)

    # Progress bar
    bar_row = tk.Frame(frame, bg=t["panel_bg"])
    bar_row.pack(fill=tk.X, pady=4)

    self._progress_bar = ttk.Progressbar(
        bar_row, mode="determinate", length=400,
    )
    self._progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

    self._progress_label = tk.Label(
        bar_row, text="0 / 0", anchor=tk.W, padx=8,
        bg=t["panel_bg"], fg=t["fg"], font=FONT_MONO,
    )
    self._progress_label.pack(side=tk.LEFT)

    # Stats line
    self._stats_hint = tk.Label(
        frame, text="Live telemetry: rate | ETA | copied | processed | skipped | err (ETA uses estimate if provided)",
        anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._stats_hint.pack(fill=tk.X)

    self._stats_label = tk.Label(
        frame, text="--/s | ETA -- | copied: 0 | processed: 0 | skipped: 0 | err: 0", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._stats_label.pack(fill=tk.X)
    self._stats_detail_label = tk.Label(
        frame, text="Elapsed 0s | Data 0 B / 0 B | discovered 0", anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._stats_detail_label.pack(fill=tk.X)
    self._run_id_label = tk.Label(
        frame, textvariable=self._run_id_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._run_id_label.pack(fill=tk.X)
    self._stop_ack_label = tk.Label(
        frame, textvariable=self._stop_ack_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._stop_ack_label.pack(fill=tk.X)
    self._last_reason_label = tk.Label(
        frame, textvariable=self._last_reason_var, anchor=tk.W,
        bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    )
    self._last_reason_label.pack(fill=tk.X)


# ================================================================
# SECTION E: Post-Transfer Actions
# ================================================================

def _build_post_transfer_section(self, t):
    """Navigation button to jump to Index panel after transfer."""
    frame = tk.Frame(self, bg=t["panel_bg"])
    frame.pack(fill=tk.X, padx=16, pady=(4, 16))
    self._post_frame = frame

    self._goto_index_btn = tk.Button(
        frame, text="Go to Index Panel", command=self._goto_index,
        width=18, bg=t["accent"], fg=t["accent_fg"], font=FONT,
        relief=tk.FLAT, bd=0, padx=12, pady=6,
        activebackground=t.get("accent_hover", t["accent"]),
        activeforeground=t["accent_fg"],
    )
    self._goto_index_btn.pack(side=tk.LEFT)
    bind_hover(self._goto_index_btn)

    tk.Label(
        frame, text="After transfer completes, index the data to make it searchable.",
        anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
    ).pack(side=tk.LEFT, padx=(12, 0))


# ================================================================
# THEME
# ================================================================

def apply_theme(self, t):
    """Re-apply theme colors to all widgets."""
    from src.gui.panels.data_panel import _theme_widget

    self.configure(bg=t["panel_bg"])
    for frame_attr in (
        "_source_path_frame", "_browser_frame",
        "_preview_frame", "_transfer_frame", "_post_frame",
    ):
        frame = getattr(self, frame_attr, None)
        if frame:
            if isinstance(frame, tk.LabelFrame):
                frame.configure(bg=t["panel_bg"], fg=t["accent"])
            else:
                frame.configure(bg=t["panel_bg"])
            _theme_widget(frame, t)
    # Fix text widget colors
    self._preview_text.config(bg=t["input_bg"], fg=t["input_fg"])


# ================================================================
# BIND -- attach all build methods to DataPanel class
# ================================================================

def bind_datapanel_build_methods(cls):
    """Attach widget-building methods to the DataPanel class."""
    cls._build_source_path_section = _build_source_path_section
    cls._build_browser_section = _build_browser_section
    cls._build_preview_section = _build_preview_section
    cls._set_preview_text = _set_preview_text
    cls._build_transfer_section = _build_transfer_section
    cls._build_post_transfer_section = _build_post_transfer_section
    cls.apply_theme = apply_theme
