# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the index panel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Index Panel (src/gui/panels/index_panel.py)
# ============================================================================
# Folder picker, indexing progress bar, start/stop controls.
#
# INTERNET ACCESS: NONE (indexing is purely local)
# ============================================================================

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from datetime import datetime

from tkinter import filedialog

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.helpers.safe_after import safe_after
from src.core.config import save_config_field

logger = logging.getLogger(__name__)


class IndexPanel(tk.LabelFrame):
    """
    Index management panel with folder picker, progress bar, and controls.
    """

    def __init__(self, parent, config, indexer=None):
        """Plain-English: Sets up the IndexPanel object and prepares state used by its methods."""
        t = current_theme()
        super().__init__(parent, text="Index Panel", padx=16, pady=8,
                         bg=t["panel_bg"], fg=t["accent"],
                         font=FONT_BOLD)
        self.config = config
        self.indexer = indexer
        self._stop_flag = threading.Event()
        self._index_thread = None
        self._dev_ui_enabled = os.environ.get(
            "HYBRIDRAG_DEV_UI", ""
        ).strip().lower() in ("1", "true", "yes")

        # Public testing state -- poll these from harness/tools.
        # Event is the thread-safe completion signal; plain attrs are
        # convenience for assertions after the event fires.
        self.index_done_event = threading.Event()
        self.is_indexing = False
        self.last_index_status = ""

        self._build_widgets(t)

    def _build_widgets(self, t):
        """Build all child widgets with theme colors."""
        # -- Row 0: Source folder (changeable independently of downloader) --
        row0 = tk.Frame(self, bg=t["panel_bg"])
        row0.pack(fill=tk.X, pady=(0, 4))

        self.folder_label = tk.Label(row0, text="Source:",
                                     bg=t["panel_bg"], fg=t["label_fg"],
                                     font=FONT)
        self.folder_label.pack(side=tk.LEFT)

        default_source = getattr(
            getattr(self.config, "paths", None), "source_folder", ""
        ) or ""

        self.folder_var = tk.StringVar(value=default_source)
        self.folder_display = tk.Label(
            row0, textvariable=self.folder_var, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        )
        self.folder_display.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                 padx=(8, 0))

        self._change_source_btn = tk.Button(
            row0, text="Change...", command=self._on_change_source, width=10,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=4,
            activebackground=t.get("accent_hover", t["accent"]),
            activeforeground=t["accent_fg"],
        )
        self._change_source_btn.pack(side=tk.RIGHT, padx=(8, 0))
        bind_hover(self._change_source_btn)

        # -- Row 0b: Index folder (changeable from the main panel) --
        row0b = tk.Frame(self, bg=t["panel_bg"])
        row0b.pack(fill=tk.X, pady=(0, 8))

        self.index_label = tk.Label(row0b, text="Index:",
                                    bg=t["panel_bg"], fg=t["label_fg"],
                                    font=FONT)
        self.index_label.pack(side=tk.LEFT)

        db_path = getattr(
            getattr(self.config, "paths", None), "database", ""
        ) or ""
        index_default = os.path.dirname(db_path) if db_path else "(not set)"

        self.index_var = tk.StringVar(value=index_default)
        self.index_display = tk.Label(
            row0b, textvariable=self.index_var, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        )
        self.index_display.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                padx=(8, 0))

        self._change_index_btn = tk.Button(
            row0b, text="Change...", command=self._on_change_index, width=10,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=4,
            activebackground=t.get("accent_hover", t["accent"]),
            activeforeground=t["accent_fg"],
        )
        self._change_index_btn.pack(side=tk.RIGHT, padx=(8, 0))
        bind_hover(self._change_index_btn)

        self.paths_hint = tk.Label(
            row0b, text="",
            bg=t["panel_bg"], fg=t["gray"], font=("Segoe UI", 8),
        )
        self.paths_hint.pack(side=tk.RIGHT)

        # -- Status indicator (shows why indexing is disabled) --
        self._status_var = tk.StringVar(value="Waiting for backends...")
        self._status_label = tk.Label(
            self, textvariable=self._status_var,
            bg=t["panel_bg"], fg=t.get("yellow", "#e8a838"),
            font=FONT_SMALL, anchor=tk.W,
        )
        self._status_label.pack(fill=tk.X, pady=(0, 4))

        # -- Row 1: Controls --
        row1 = tk.Frame(self, bg=t["panel_bg"])
        row1.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = tk.Button(
            row1, text="Start Indexing", command=self._on_start, width=14,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT_BOLD, relief=tk.FLAT, bd=0,
            padx=24, pady=8, state=tk.DISABLED,
            activebackground=t["accent_hover"],
            activeforeground=t["accent_fg"],
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = tk.Button(
            row1, text="Stop Indexing", command=self._on_stop, width=12,
            state=tk.DISABLED,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT_BOLD, relief=tk.FLAT, bd=0, padx=16, pady=8,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        if self._dev_ui_enabled:
            self._clear_armed_var = tk.BooleanVar(value=False)
            self.clear_btn = tk.Button(
                row1, text="Clear Index (Dev)", command=self._on_clear_index,
                width=14,
                bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                font=FONT, relief=tk.FLAT, bd=0, padx=12, pady=8,
                state=tk.DISABLED,
            )
            self.clear_btn.pack(side=tk.LEFT, padx=(8, 0))
            self.clear_guard_cb = tk.Checkbutton(
                row1,
                text="Unlock Clear",
                variable=self._clear_armed_var,
                command=self._on_toggle_clear_guard,
                bg=t["panel_bg"],
                fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"],
                font=FONT_SMALL,
            )
            self.clear_guard_cb.pack(side=tk.LEFT, padx=(8, 0))

        self.progress_file_label = tk.Label(
            row1, text="", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT,
        )
        self.progress_file_label.pack(side=tk.LEFT, padx=(16, 0),
                                      fill=tk.X, expand=True)

        # -- Row 2: Progress bar --
        row2 = tk.Frame(self, bg=t["panel_bg"])
        row2.pack(fill=tk.X, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(
            row2, mode="determinate", length=400,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_count_label = tk.Label(
            row2, text="0 / 0 files", anchor=tk.W, padx=8,
            bg=t["panel_bg"], fg=t["fg"], font=FONT_MONO,
        )
        self.progress_count_label.pack(side=tk.LEFT)

        # -- Row 3: Last run info --
        self.last_run_label = tk.Label(
            self, text="Last run: (none)", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT,
        )
        self.last_run_label.pack(fill=tk.X)

        # -- Row 4: Live telemetry (indexing) --
        self.index_stats_label = tk.Label(
            self,
            text="Telemetry: chunks 0 | files skipped 0 | file errors 0 | rate -- chunks/s | ETA --",
            anchor=tk.W, fg=t["gray"], bg=t["panel_bg"], font=FONT_SMALL,
        )
        self.index_stats_label.pack(fill=tk.X, pady=(2, 0))

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["panel_bg"], fg=t["accent"])

        for row in self.winfo_children():
            if isinstance(row, tk.Frame):
                row.configure(bg=t["panel_bg"])
                for child in row.winfo_children():
                    if isinstance(child, tk.Label):
                        child.configure(bg=t["panel_bg"])
                        cur_fg = str(child.cget("fg"))
                        if cur_fg in ("#888888", "gray"):
                            child.configure(fg=t["gray"])
                        elif cur_fg not in ("green", "red", "orange",
                                            t["green"], t["red"], t["orange"]):
                            child.configure(fg=t["fg"])
                    elif isinstance(child, tk.Button):
                        if str(child.cget("state")) == "disabled":
                            child.configure(bg=t["inactive_btn_bg"],
                                            fg=t["inactive_btn_fg"])
                        else:
                            child.configure(bg=t["accent"], fg=t["accent_fg"],
                                            activebackground=t["accent_hover"])

        # Path labels
        self.folder_label.configure(bg=t["panel_bg"], fg=t["label_fg"])
        self.folder_display.configure(bg=t["panel_bg"], fg=t["fg"])
        self.index_label.configure(bg=t["panel_bg"], fg=t["label_fg"])
        self.index_display.configure(bg=t["panel_bg"], fg=t["fg"])
        self.paths_hint.configure(bg=t["panel_bg"], fg=t["gray"])

        self.last_run_label.configure(bg=t["panel_bg"])
        if "none" in self.last_run_label.cget("text"):
            self.last_run_label.configure(fg=t["gray"])
        else:
            self.last_run_label.configure(fg=t["fg"])
        if hasattr(self, "index_stats_label"):
            self.index_stats_label.configure(bg=t["panel_bg"], fg=t["gray"])
        self.progress_count_label.configure(bg=t["panel_bg"], fg=t["fg"])
        if hasattr(self, "clear_guard_cb"):
            self.clear_guard_cb.configure(
                bg=t["panel_bg"],
                fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"],
            )
        if hasattr(self, "_clear_armed_var"):
            self._on_toggle_clear_guard()

    def set_ready(self, enabled, reason=""):
        """Enable or disable the Start Indexing button based on backend readiness."""
        t = current_theme()
        if enabled:
            self.start_btn.config(state=tk.NORMAL, bg=t["accent"],
                                  fg=t["accent_fg"])
            self._update_status("Ready to index", t.get("green", "#4ec96f"))
        else:
            self.start_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                                  fg=t["inactive_btn_fg"])
            self._update_status(
                reason or self._diagnose_disabled_reason(),
                t.get("yellow", "#e8a838"),
            )

    def _update_status(self, text, color):
        """Update the status indicator label."""
        if hasattr(self, "_status_var"):
            self._status_var.set(text)
            self._status_label.configure(fg=color)

    def _on_change_source(self):
        """Open folder picker to change the indexer source folder."""
        current = self.folder_var.get().strip()
        initial = current if current and os.path.isdir(current) else ""
        folder = filedialog.askdirectory(
            title="Select Source Folder to Index From",
            initialdir=initial,
        )
        if folder:
            norm = os.path.normpath(folder)
            self.folder_var.set(norm)

            # Update live config
            paths = getattr(self.config, "paths", None)
            if paths:
                paths.source_folder = norm

            # Persist to YAML
            try:
                save_config_field("paths.source_folder", norm)
            except Exception as e:
                logger.warning("Could not persist source path: %s", e)

    def _on_change_index(self):
        """Open folder picker to change the index-data folder."""
        current = self.index_var.get().strip()
        initial = current if current and os.path.isdir(current) else ""
        folder = filedialog.askdirectory(
            title="Select Index Data Folder",
            initialdir=initial,
        )
        if not folder:
            return

        norm = os.path.normpath(folder)
        db_path = os.path.join(norm, "hybridrag.sqlite3")
        embeddings_cache = os.path.join(norm, "_embeddings")

        self.index_var.set(norm)

        paths = getattr(self.config, "paths", None)
        if paths:
            paths.database = db_path
            paths.embeddings_cache = embeddings_cache

        try:
            save_config_field("paths.database", db_path)
            save_config_field("paths.embeddings_cache", embeddings_cache)
        except Exception as e:
            logger.warning("Could not persist index path: %s", e)

    def _diagnose_disabled_reason(self):
        """Return a human-readable reason why indexing is disabled."""
        if self.indexer is None:
            return "Backends loading... (embedder or database not ready)"
        source = getattr(
            getattr(self.config, "paths", None), "source_folder", ""
        )
        if not source:
            return "Source folder not set (configure in Index Panel or Admin tab)"
        if not os.path.isdir(source):
            return "Source folder not found: {}".format(source)
        db = getattr(getattr(self.config, "paths", None), "database", "")
        if not db:
            return "Database path not set (configure in Index Panel or Admin tab)"
        return "Unknown reason -- check logs"

    def _on_start(self):
        """Start indexing in a background thread."""
        t = current_theme()
        if self._index_thread is not None and not self._index_thread.is_alive():
            self._index_thread = None
            self.is_indexing = False

        if self.is_indexing or (
            self._index_thread is not None and self._index_thread.is_alive()
        ):
            self.progress_file_label.config(
                text="Indexing already running. Stop it first.",
                fg=t["orange"],
            )
            return

        folder = self.folder_var.get().strip()
        if not folder:
            self.progress_file_label.config(
                text="[FAIL] No folder selected", fg=t["red"],
            )
            return

        if not os.path.isdir(folder):
            self.progress_file_label.config(
                text="[FAIL] Folder does not exist: {}".format(folder),
                fg=t["red"],
            )
            return

        if self.indexer is None:
            self.progress_file_label.config(
                text="[FAIL] Indexer not initialized. Run boot first.",
                fg=t["red"],
            )
            return

        # Reset UI
        self._stop_flag.clear()
        self.start_btn.config(state=tk.DISABLED,
                              bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
        self.stop_btn.config(state=tk.NORMAL,
                             bg=t.get("red", "#e05555"),
                             fg="#ffffff",
                             activebackground=t.get("red_hover", "#c04040"),
                             activeforeground="#ffffff")
        bind_hover(self.stop_btn)
        self.progress_bar["value"] = 0
        self.progress_count_label.config(text="0 / 0 files")
        self.progress_file_label.config(text="Starting...", fg=t["gray"])
        if hasattr(self, "index_stats_label"):
            self.index_stats_label.config(
                text="Telemetry: chunks 0 | files skipped 0 | file errors 0 | rate -- chunks/s | ETA --",
                fg=t["gray"],
            )

        # Public testing state (main thread, before thread starts)
        self.is_indexing = True
        self.index_done_event.clear()
        self.last_index_status = ""

        # Run in background
        self._index_thread = threading.Thread(
            target=self._run_indexing, args=(folder,), daemon=True,
        )
        self._index_thread.start()

    def _on_stop(self):
        """Signal the indexing thread to stop after current file."""
        t = current_theme()
        self._stop_flag.set()
        self.stop_btn.config(state=tk.DISABLED,
                             bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])
        self.progress_file_label.config(text="Stopping after current file...",
                                        fg=t["orange"])

    def _on_clear_index(self):
        """Development-only helper: wipe DB + embeddings cache quickly."""
        t = current_theme()
        if not getattr(self, "_clear_armed_var", tk.BooleanVar(value=False)).get():
            self.progress_file_label.config(
                text="[WARN] Unlock Clear first.",
                fg=t["orange"],
            )
            return
        if self.is_indexing:
            self.progress_file_label.config(
                text="[FAIL] Stop indexing before clearing index.",
                fg=t["red"],
            )
            return

        db_path = getattr(getattr(self.config, "paths", None), "database", "") or ""
        emb_path = getattr(
            getattr(self.config, "paths", None), "embeddings_cache", ""
        ) or ""

        if not db_path and not emb_path:
            self.progress_file_label.config(
                text="[FAIL] No index paths configured.",
                fg=t["red"],
            )
            return

        ok = messagebox.askyesno(
            "Clear Index (Development)",
            "Delete local index data now?\n\n"
            "- SQLite index DB\n"
            "- Embeddings cache folder\n\n"
            "This cannot be undone. You must re-index afterward.",
        )
        if not ok:
            self._reset_clear_guard()
            return

        # Try to release local file handles first.
        try:
            if self.indexer is not None and hasattr(self.indexer, "close"):
                self.indexer.close()
        except Exception:
            pass

        errors = []
        removed = []

        if db_path and os.path.isfile(db_path):
            try:
                os.remove(db_path)
                removed.append("DB")
            except Exception as e:
                errors.append("DB: {}".format(str(e)[:120]))

        if emb_path and os.path.isdir(emb_path):
            try:
                shutil.rmtree(emb_path)
                removed.append("Embeddings")
            except Exception as e:
                errors.append("Embeddings: {}".format(str(e)[:120]))

        if errors:
            self._reset_clear_guard()
            self.progress_file_label.config(
                text="[FAIL] Clear index partial. {}. If locked, restart app and retry.".format(
                    " | ".join(errors)
                ),
                fg=t["red"],
            )
            return

        self.indexer = None
        self.set_ready(False, "Index cleared. Rebuild backends or restart app.")
        self.progress_bar["value"] = 0
        self.progress_count_label.config(text="0 / 0 files")
        self.progress_file_label.config(
            text="[OK] Cleared: {}. Re-index required.".format(", ".join(removed) or "nothing"),
            fg=t["green"],
        )
        self._reset_clear_guard()

    def _on_toggle_clear_guard(self):
        """Require an explicit arm step before destructive index clearing."""
        t = current_theme()
        if not hasattr(self, "clear_btn"):
            return
        armed = bool(self._clear_armed_var.get())
        if armed:
            self.clear_btn.config(
                state=tk.NORMAL,
                bg=t.get("red", "#e05555"),
                fg="#ffffff",
                activebackground=t.get("red_hover", "#c04040"),
                activeforeground="#ffffff",
            )
        else:
            self.clear_btn.config(
                state=tk.DISABLED,
                bg=t["inactive_btn_bg"],
                fg=t["inactive_btn_fg"],
            )

    def _reset_clear_guard(self):
        """Return destructive clear controls to the safe locked state."""
        if hasattr(self, "_clear_armed_var"):
            self._clear_armed_var.set(False)
        self._on_toggle_clear_guard()

    def _run_indexing(self, folder):
        """Execute indexing in background thread with progress callback."""
        from src.core.indexing.cancel import IndexCancelled
        try:
            callback = _GUIProgressCallback(self)
            result = self.indexer.index_folder(
                folder, progress_callback=callback, recursive=True,
                stop_flag=self._stop_flag,
            )
            # Thread-safe completion signal + status (before safe_after
            # so headless harnesses can poll without after() firing)
            self.is_indexing = False
            self.last_index_status = "[OK] Indexing complete"
            self.index_done_event.set()
            safe_after(self, 0, self._on_indexing_done, result)
        except IndexCancelled:
            self.is_indexing = False
            self.last_index_status = "[OK] Indexing cancelled by user"
            self.index_done_event.set()
            safe_after(self, 0, self._on_indexing_cancelled)
        except Exception as e:
            error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
            self.is_indexing = False
            self.last_index_status = error_msg
            self.index_done_event.set()
            safe_after(self, 0, self._on_indexing_error, error_msg)

    def _on_indexing_done(self, result):
        """Handle indexing completion (called on main thread)."""
        try:
            self._on_indexing_done_inner(result)
        except Exception as e:
            logger.error("Indexing done handler failed: %s", e)
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def _on_indexing_done_inner(self, result):
        """Inner handler (separated so outer can catch and re-enable)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL, bg=t["accent"],
                              fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])

        total_chunks = result.get("total_chunks_added", 0)
        elapsed = result.get("elapsed_seconds", 0)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        self.last_run_label.config(
            text="Last run: {} | {:,} chunks indexed | {:.0f}s".format(
                now, total_chunks, elapsed
            ),
            fg=t["fg"],
        )
        self.progress_file_label.config(
            text="[OK] Indexing complete", fg=t["green"],
        )

    def _on_indexing_cancelled(self):
        """Handle clean cancellation (called on main thread)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL, bg=t["accent"],
                              fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])
        self.progress_file_label.config(
            text="[OK] Indexing cancelled by user", fg=t["orange"],
        )

    def _on_indexing_error(self, error_msg):
        """Handle indexing error (called on main thread)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL, bg=t["accent"],
                              fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])
        self.progress_file_label.config(text=error_msg, fg=t["red"])


class _GUIProgressCallback:
    """
    Indexing progress callback that updates the GUI panel.

    Methods are called from the indexing background thread,
    so all GUI updates use panel.after() to run on the main thread.

    Throttling: GUI updates fire at most every _THROTTLE_SEC (100ms).
    The latest state is always stored so the final update is never lost.
    Without throttling, indexing 1000+ files queues 2000+ after() events,
    flooding the tkinter event loop and freezing the UI.
    """

    _THROTTLE_SEC = 0.1  # max 10 GUI updates per second

    def __init__(self, panel):
        """Plain-English: Sets up the _GUIProgressCallback object and prepares state used by its methods."""
        self.panel = panel
        self._start_time = time.monotonic()
        self._file_count = 0
        self._total_files = 0
        self._chunks_total = 0
        self._skipped_count = 0
        self._error_count = 0
        self._skip_reasons = {}
        self._last_gui_update = 0.0
        self._pending_fname = None
        self._pending_file_num = 0
        self._pending_total = 0

    def _should_update(self):
        """Return True if enough time has passed since the last GUI update."""
        now = time.monotonic()
        if now - self._last_gui_update >= self._THROTTLE_SEC:
            self._last_gui_update = now
            return True
        return False

    def _flush_pending(self):
        """Push the latest stored state to the GUI (called at end of indexing)."""
        if self._pending_fname is not None:
            safe_after(
                self.panel, 0, self._update_file_start,
                self._pending_fname, self._pending_file_num,
                self._pending_total,
            )
            safe_after(self.panel, 0, self._update_file_complete)

    def on_file_start(self, file_path, file_num, total_files):
        """Called when a file starts processing."""
        self._total_files = total_files
        fname = os.path.basename(file_path)

        # Stop flag is now checked in indexer.index_folder() at the top
        # of the file loop, raising IndexCancelled (BaseException).
        # No need to raise from the callback.

        # Always store latest state; only push to GUI if throttle allows
        self._pending_fname = fname
        self._pending_file_num = file_num
        self._pending_total = total_files

        if self._should_update():
            safe_after(self.panel, 0, self._update_file_start, fname, file_num, total_files)
            safe_after(self.panel, 0, self._update_telemetry)

    def _update_file_start(self, fname, file_num, total_files):
        """Plain-English: Updates progress UI when indexing starts for an individual file."""
        t = current_theme()
        self.panel.progress_file_label.config(
            text="Processing: {}".format(fname), fg=t["gray"],
        )
        self.panel.progress_count_label.config(
            text="{} / {} files".format(file_num, total_files),
        )
        if total_files > 0:
            self.panel.progress_bar["maximum"] = total_files
            self.panel.progress_bar["value"] = file_num - 1

    def on_file_complete(self, file_path, chunks_created):
        """Called when a file finishes processing."""
        self._file_count += 1
        self._chunks_total += int(chunks_created or 0)
        if self._should_update():
            safe_after(self.panel, 0, self._update_file_complete)
            safe_after(self.panel, 0, self._update_telemetry)

    def _update_file_complete(self):
        """Plain-English: Updates progress UI when an individual file finishes indexing."""
        self.panel.progress_bar["value"] = self._file_count

    def _update_telemetry(self):
        """Update live indexing telemetry line."""
        if not hasattr(self.panel, "index_stats_label"):
            return
        elapsed = max(0.001, time.monotonic() - self._start_time)
        rate = self._chunks_total / elapsed
        eta_txt = "--"
        if self._total_files > 0 and rate > 0:
            # ETA is still file-based because total chunk count is unknown
            # until files are parsed/chunked.
            file_rate = self._file_count / elapsed
            remaining = max(0, self._total_files - self._file_count)
            eta_s = (remaining / file_rate) if file_rate > 0 else float("inf")
            if eta_s < 60:
                eta_txt = "{:.0f}s".format(eta_s)
            elif eta_s < 3600:
                m, s = divmod(int(eta_s), 60)
                eta_txt = "{}m {}s".format(m, s)
            else:
                h, rem = divmod(int(eta_s), 3600)
                m = rem // 60
                eta_txt = "{}h {}m".format(h, m)
        self.panel.index_stats_label.config(
            text=(
                "Telemetry: chunks {:,} | files skipped {:,} | file errors {:,} | "
                "rate {:.2f} chunks/s | ETA {}"
            ).format(
                self._chunks_total, self._skipped_count,
                self._error_count, rate, eta_txt,
            )
        )
        if self._skip_reasons:
            top = sorted(
                self._skip_reasons.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )[:3]
            top_txt = ", ".join(
                "{} ({})".format(reason, count) for reason, count in top
            )
            self.panel.index_stats_label.config(
                text=(
                    "Telemetry: chunks {:,} | files skipped {:,} | file errors {:,} | "
                    "rate {:.2f} chunks/s | ETA {} | top skip reasons: {}"
                ).format(
                    self._chunks_total, self._skipped_count,
                    self._error_count, rate, eta_txt, top_txt,
                )
            )

    def on_file_skipped(self, file_path, reason):
        """Called when a file is skipped."""
        self._file_count += 1
        self._skipped_count += 1
        reason_key = (reason or "unknown").strip()
        self._skip_reasons[reason_key] = self._skip_reasons.get(reason_key, 0) + 1
        if self._should_update():
            safe_after(self.panel, 0, self._update_file_complete)
            safe_after(self.panel, 0, self._update_telemetry)

    def on_indexing_complete(self, total_chunks, elapsed_seconds):
        """Called when indexing finishes. Flush final state to GUI."""
        self._chunks_total = max(self._chunks_total, int(total_chunks or 0))
        self._flush_pending()
        safe_after(self.panel, 0, self._update_telemetry)

    def on_discovery_progress(self, files_found):
        """Called periodically during folder discovery (before indexing starts)."""
        if self._should_update():
            safe_after(self.panel, 0, self._update_discovery, files_found)

    def _update_discovery(self, files_found):
        """Plain-English: Refreshes discovery counters as the scanner finds candidate files."""
        t = current_theme()
        self.panel.progress_file_label.config(
            text="Scanning folder... {:,} files found".format(files_found),
            fg=t["gray"],
        )

    def on_error(self, file_path, error):
        """Called when a file has an error -- always shown (errors are rare)."""
        t = current_theme()
        fname = os.path.basename(file_path)
        self._error_count += 1
        safe_after(self.panel, 0, self._update_telemetry)
        safe_after(
            self.panel, 0,
            lambda: self.panel.progress_file_label.config(
                text="[WARN] Error on {}: {}".format(fname, error[:60]),
                fg=t["orange"],
            ),
        )
