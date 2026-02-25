# ============================================================================
# HybridRAG v3 -- Data Transfer Panel (src/gui/panels/data_panel.py)  RevA
# ============================================================================
# WHAT: GUI wrapper around the bulk_transfer_v2.py engine.
# WHY:  Non-technical users need a visual pipeline: Browse drives ->
#       Select folder -> Transfer to source folder -> Index into vectors.
#       The transfer engine already exists as CLI-only; this provides
#       the GUI surface.
# HOW:  Five sections stacked vertically inside a Frame:
#       A. Current Source Path (info bar)
#       B. Transfer Source Browser (drive detection + folder picker)
#       C. Source Preview (background scan with file counts)
#       D. Transfer Controls (start/stop, progress bar, live stats)
#       E. Post-Transfer Actions (navigate to Index panel)
#
# THREAD SAFETY:
#   All long operations run in daemon threads.  GUI updates via
#   self.after(0, callback).  Stop flag via threading.Event().
#   Transfer engine stats are polled every 500ms -- no callbacks
#   needed, no modifications to bulk_transfer_v2.py.
#
# INTERNET ACCESS: NONE (local/network file copy only)
# ============================================================================

import ctypes
import os
import string
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import logging

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.core.config import save_config_field

logger = logging.getLogger(__name__)


def _detect_drives():
    """Enumerate local + mapped network drives on Windows.

    Uses the Win32 API GetLogicalDrives() bitmask.  On non-Windows
    platforms, falls back to common mount points.

    Returns a list of drive root strings like ['C:\\', 'D:\\', 'E:\\'].
    """
    drives = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                letter = string.ascii_uppercase[i]
                drives.append("{}:\\".format(letter))
    except (AttributeError, OSError):
        # Non-Windows fallback
        for letter in ("C", "D", "E", "F", "G", "H"):
            path = "{}:\\".format(letter)
            if os.path.isdir(path):
                drives.append(path)
    return drives


def _fmt_size(b):
    """Format bytes as human-readable string."""
    b = float(b)
    if b < 1024:
        return "{:.0f} B".format(b)
    elif b < 1024 ** 2:
        return "{:.1f} KB".format(b / 1024)
    elif b < 1024 ** 3:
        return "{:.1f} MB".format(b / 1024 ** 2)
    return "{:.2f} GB".format(b / 1024 ** 3)


def _fmt_dur(s):
    """Format seconds as human-readable duration."""
    s = float(s)
    if s < 60:
        return "{:.0f}s".format(s)
    elif s < 3600:
        m, sec = divmod(s, 60)
        return "{}m {}s".format(int(m), int(sec))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return "{}h {}m".format(int(h), int(m))


def _theme_widget(widget, t):
    """Recursively apply theme to a widget and its children."""
    try:
        wclass = widget.winfo_class()
        if wclass == "Frame":
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Entry":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


def _scan_folder_summary(path):
    """Walk *path* and return a human-readable file/extension summary.

    Pure function -- no GUI or tkinter references.  Safe to call from
    a background thread.  Raises on OS errors so the caller can catch
    and format the message for the user.
    """
    ext_counts = {}
    total_size = 0
    file_count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [
            d for d in dirs
            if d.lower() not in (
                ".git", "__pycache__", ".venv", "node_modules",
                "$recycle.bin", "system volume information",
            )
        ]
        for fname in files:
            file_count += 1
            ext = os.path.splitext(fname)[1].lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            try:
                full = os.path.join(root, fname)
                total_size += os.path.getsize(full)
            except OSError:
                pass
    lines = [
        "{:,} files | {}".format(file_count, _fmt_size(total_size)),
        "",
        "Top extensions:",
    ]
    sorted_exts = sorted(
        ext_counts.items(), key=lambda x: x[1], reverse=True,
    )[:10]
    for ext, cnt in sorted_exts:
        display_ext = ext if ext else "(none)"
        lines.append("  {:8s} {:>8,}".format(display_ext, cnt))
    return "\n".join(lines)


class DataPanel(tk.Frame):
    """
    Data Transfer panel: drive detection, folder browser, transfer
    controls, progress display, and post-transfer navigation.

    Wraps the BulkTransferV2 engine without modifying it -- reads
    engine.stats via polling (self.after every 500ms).
    """

    def __init__(self, parent, config, app_ref):
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref

        # Transfer engine state
        self._engine = None
        self._transfer_thread = None
        self._stop_event = threading.Event()
        self._poll_id = None

        # Build sections
        self._build_source_path_section(t)
        self._build_browser_section(t)
        self._build_preview_section(t)
        self._build_transfer_section(t)
        self._build_post_transfer_section(t)

    # ================================================================
    # SECTION A: Current Source Path
    # ================================================================

    def _build_source_path_section(self, t):
        """Info bar showing the current config source folder."""
        frame = tk.LabelFrame(
            self, text="Current Source Path", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=(8, 4))
        self._source_path_frame = frame

        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X)

        source = getattr(
            getattr(self.config, "paths", None), "source_folder", ""
        ) or "(not set)"
        self._source_path_var = tk.StringVar(value=source)

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

    def _on_change_source(self):
        """Open folder picker for the destination source folder."""
        current = self._source_path_var.get().strip()
        initial = current if current and os.path.isdir(current) else ""
        folder = filedialog.askdirectory(
            title="Select Source Documents Folder (Transfer Destination)",
            initialdir=initial,
        )
        if folder:
            norm = os.path.normpath(folder)
            self._source_path_var.set(norm)

            # Update live config
            paths = getattr(self.config, "paths", None)
            if paths:
                paths.source_folder = norm

            # Persist to YAML
            try:
                save_config_field("paths.source_folder", norm)
            except Exception as e:
                logger.warning("Could not persist source path: %s", e)

            # Sync to Index Panel
            if hasattr(self._app, "index_panel"):
                self._app.index_panel.folder_var.set(norm)

    # ================================================================
    # SECTION B: Transfer Source Browser
    # ================================================================

    def _build_browser_section(self, t):
        """Drive detection + folder picker for the source to transfer FROM."""
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
        self._drive_var = tk.StringVar(value=drives[0] if drives else "C:\\")
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

        self._selected_path_var = tk.StringVar()
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

    def _on_browse(self):
        """Open native folder picker starting at selected drive."""
        drive = self._drive_var.get()
        initial = drive if os.path.isdir(drive) else ""
        folder = filedialog.askdirectory(
            title="Select Folder to Transfer FROM", initialdir=initial,
        )
        if folder:
            self._selected_path_var.set(os.path.normpath(folder))
            self._on_preview()

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

    def _on_preview(self):
        """Scan selected folder in a background thread."""
        path = self._selected_path_var.get().strip()
        if not path or not os.path.isdir(path):
            self._set_preview_text("[WARN] Folder does not exist: {}".format(path))
            return
        self._set_preview_text("Scanning {}...".format(path))
        threading.Thread(
            target=self._scan_preview, args=(path,), daemon=True,
        ).start()

    def _scan_preview(self, path):
        """Background thread: delegate to pure function, schedule UI update."""
        try:
            summary = _scan_folder_summary(path)
            self.after(0, self._set_preview_text, summary)
        except Exception as e:
            self.after(0, self._set_preview_text,
                       "[FAIL] Scan error: {}".format(str(e)[:80]))

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
        self._stats_label = tk.Label(
            frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._stats_label.pack(fill=tk.X)

    def _on_start_transfer(self):
        """Validate inputs and launch transfer in background thread."""
        t = current_theme()
        source = self._selected_path_var.get().strip()
        dest = self._source_path_var.get().strip()

        if not source or not os.path.isdir(source):
            self._transfer_status.config(
                text="[FAIL] Select a source folder first", fg=t["red"])
            return

        if not dest:
            self._transfer_status.config(
                text="[FAIL] Set destination source path first", fg=t["red"])
            return

        # Prevent transferring into self
        src_norm = os.path.normcase(os.path.normpath(source))
        dst_norm = os.path.normcase(os.path.normpath(dest))
        if src_norm == dst_norm:
            self._transfer_status.config(
                text="[FAIL] Source and destination are the same", fg=t["red"])
            return

        # Reset UI
        self._stop_event.clear()
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._progress_bar["value"] = 0
        self._progress_label.config(text="0 / 0")
        self._stats_label.config(text="")
        self._transfer_status.config(text="Starting transfer...", fg=t["gray"])

        # Launch in background
        self._transfer_thread = threading.Thread(
            target=self._run_transfer, args=(source, dest), daemon=True,
        )
        self._transfer_thread.start()

        # Start polling
        self._poll_stats()

    def _run_transfer(self, source, dest):
        """Background thread: create engine and run transfer."""
        try:
            from src.tools.bulk_transfer_v2 import BulkTransferV2, TransferConfig

            cfg = TransferConfig(
                source_paths=[source],
                dest_path=dest,
                workers=8,
            )
            self._engine = BulkTransferV2(cfg)
            self._engine.run()
            self.after(0, self._on_transfer_done)
        except Exception as e:
            msg = "[FAIL] {}: {}".format(type(e).__name__, str(e)[:80])
            self.after(0, self._on_transfer_error, msg)

    def _on_stop_transfer(self):
        """Signal the transfer engine to stop."""
        t = current_theme()
        self._stop_event.set()
        if self._engine is not None:
            self._engine._stop.set()
        self._stop_btn.config(state=tk.DISABLED)
        self._transfer_status.config(
            text="Stopping after current file...", fg=t["orange"])

    def _poll_stats(self):
        """Poll engine.stats every 500ms and update the GUI."""
        if self._engine is None:
            self._poll_id = self.after(500, self._poll_stats)
            return

        stats = self._engine.stats
        t = current_theme()

        copied = stats.files_copied
        total = stats.files_manifest if stats.files_manifest > 0 else stats.files_discovered

        # Progress bar
        if total > 0:
            self._progress_bar["maximum"] = total
            self._progress_bar["value"] = copied
            self._progress_label.config(
                text="{:,} / {:,}".format(copied, total))
        else:
            self._progress_label.config(
                text="Scanning... {:,} found".format(stats.files_discovered))

        # Speed + ETA
        speed = stats.speed_bps
        eta = stats.eta_seconds
        eta_str = _fmt_dur(eta) if eta < 86400 else "---"
        self._stats_label.config(
            text="{}/s | ETA {} | copied: {:,} | dedup: {:,} | skip: {:,} | err: {:,}".format(
                _fmt_size(speed), eta_str,
                copied, stats.files_deduplicated,
                stats.files_skipped_unchanged, stats.files_failed,
            ),
            fg=t["gray"],
        )

        # Continue polling if transfer is still running
        if self._transfer_thread is not None and self._transfer_thread.is_alive():
            self._poll_id = self.after(500, self._poll_stats)
        else:
            # One final update
            self._poll_id = None

    def _on_transfer_done(self):
        """Transfer completed -- update UI."""
        t = current_theme()
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)

        if self._engine is not None:
            stats = self._engine.stats
            self._transfer_status.config(
                text="[OK] Transfer complete -- {:,} files copied, {} transferred".format(
                    stats.files_copied, _fmt_size(stats.bytes_copied),
                ),
                fg=t["green"],
            )
            # Final progress update
            total = stats.files_manifest
            self._progress_bar["maximum"] = max(total, 1)
            self._progress_bar["value"] = stats.files_copied
            self._progress_label.config(
                text="{:,} / {:,}".format(stats.files_copied, total))
        else:
            self._transfer_status.config(
                text="[OK] Transfer complete", fg=t["green"])

    def _on_transfer_error(self, msg):
        """Transfer failed -- update UI."""
        t = current_theme()
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._transfer_status.config(text=msg, fg=t["red"])

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

    def _goto_index(self):
        """Switch to the Query view (which contains the Index panel)."""
        if hasattr(self._app, "show_view"):
            self._app.show_view("query")

    # ================================================================
    # THEME
    # ================================================================

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
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
