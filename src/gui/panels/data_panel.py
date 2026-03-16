# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the data panel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Data Transfer Panel (src/gui/panels/data_panel.py)  RevB
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
# SPLIT:
#   data_panel.py        -- class shell, __init__, module-level helpers
#   data_panel_build.py  -- widget construction (_build_* methods, apply_theme)
#   data_panel_runtime.py-- transfer logic, resume state, handlers, polling
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
import logging

from src.gui.theme import current_theme, FONT_BOLD, FONT_SMALL

logger = logging.getLogger(__name__)


# ================================================================
# MODULE-LEVEL HELPERS (used by build/runtime files via import)
# ================================================================

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


def _fmt_rate(bps):
    """Format transfer rate with explicit MB/s and GB/s values."""
    bps = float(max(0.0, bps))
    mbps = bps / (1024 ** 2)
    gbps = bps / (1024 ** 3)
    return "{:.2f} MB/s ({:.3f} GB/s)".format(mbps, gbps)


def _drive_from_path(path):
    """Return normalized drive root (e.g. 'I:\\') from a Windows path."""
    if not path:
        return ""
    drive = os.path.splitdrive(path)[0]
    if drive:
        return drive + os.sep
    return ""


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


def _resume_state_path():
    """Return path to persisted transfer resume state JSON."""
    root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
    return os.path.join(root, "config", "transfer_resume_state.json")


def _probe_source_ready(path, timeout_s=2.0):
    """Quickly validate source path can be enumerated without hanging UI."""
    result = {"ok": False, "error": ""}

    def _worker():
        """Plain-English: This function handles worker."""
        try:
            with os.scandir(path) as it:
                # Touch one entry (or none) to force a real access probe.
                next(it, None)
            result["ok"] = True
        except Exception as e:
            result["error"] = str(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        return False, "source probe timed out"
    if result["ok"]:
        return True, ""
    return False, result["error"] or "source probe failed"


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


# ================================================================
# CLASS: DataPanel
# ================================================================

class DataPanel(tk.Frame):
    """
    Data Transfer panel: drive detection, folder browser, transfer
    controls, progress display, and post-transfer navigation.

    Wraps the BulkTransferV2 engine without modifying it -- reads
    engine.stats via polling (self.after every 500ms).

    Methods are split across three files:
      data_panel.py        -- __init__ + module helpers (this file)
      data_panel_build.py  -- widget construction
      data_panel_runtime.py-- transfer logic and handlers
    """

    def __init__(self, parent, config, app_ref):
        """Plain-English: This function handles init."""
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref

        # Transfer engine state
        self._engine = None
        self._transfer_thread = None
        self._stop_event = threading.Event()
        self._poll_id = None
        self._resume_attempted = False
        self._stop_watchdog_ticks = 0
        self._stop_in_progress = False
        self._detached_worker = False
        self._estimated_total_bytes = 0
        self._resumed_run = False
        self._manifest_note_tick = 0
        self._total_copied_db_bytes = 0

        # Public testing state (same pattern as IndexPanel/QueryPanel)
        self.transfer_done_event = threading.Event()
        self.is_transferring = False
        self.last_transfer_status = ""
        self._run_id_var = tk.StringVar(value="Run ID: --")
        self._stop_ack_var = tk.StringVar(value="Stop Ack: --")
        self._last_reason_var = tk.StringVar(value="Last Manifest Reason: --")

        # Header so users can identify this as the downloader
        tk.Label(
            self, text="Downloader / Bulk Transfer",
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(8, 0))
        tk.Label(
            self,
            text="Transfer files from network drives or local folders "
                 "into your download folder. Indexer source is set separately.",
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
            anchor=tk.W, wraplength=600, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=16, pady=(0, 4))

        # Build sections
        self._build_source_path_section(t)
        self._build_browser_section(t)
        self._build_preview_section(t)
        self._build_transfer_section(t)
        self._build_post_transfer_section(t)
        self.after(600, self._maybe_resume_transfer)


# ================================================================
# BIND -- attach methods from extracted modules
# ================================================================

from src.gui.panels.data_panel_build import bind_datapanel_build_methods
from src.gui.panels.data_panel_runtime import bind_datapanel_runtime_methods

bind_datapanel_build_methods(DataPanel)
bind_datapanel_runtime_methods(DataPanel)
