# === NON-PROGRAMMER GUIDE ===
# Purpose: Runtime handlers for DataPanel -- extracted to keep class under 500 lines.
# What to read first: Methods here handle resume state, browsing, preview scanning,
#   and post-transfer navigation. Transfer engine orchestration is in
#   data_panel_transfer.py.
# Inputs: DataPanel instance (self) and various arguments per method.
# Outputs: GUI updates, resume state persistence, folder scanning.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Runtime handlers for DataPanel -- extracted to keep class under 500 lines.

Contains: resume state management, folder browsing handlers, preview scanning,
and post-transfer navigation. Transfer engine orchestration (start/stop/poll)
lives in data_panel_transfer.py.
"""

import json
import logging
import os
import threading
from datetime import datetime

from src.core.config import save_config_field
from src.gui.helpers.safe_after import safe_after
from src.gui.theme import current_theme

logger = logging.getLogger(__name__)


# ================================================================
# RESUME STATE (persist + auto-resume on next GUI launch)
# ================================================================

def _load_resume_state(self):
    """Load persisted transfer resume state, or None if unavailable."""
    from src.gui.panels.data_panel import _resume_state_path

    path = _resume_state_path()
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("resume_state_load_failed: %s", e)
    return None


def _save_resume_state(
    self, source, dest, status="running", auto_resume_attempts=None
):
    """Persist current transfer state for crash-safe resume."""
    from src.gui.panels.data_panel import _resume_state_path

    path = _resume_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        previous = self._load_resume_state() or {}
        payload = {
            "status": status,
            "source": source,
            "dest": dest,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "auto_resume_attempts": int(
                previous.get("auto_resume_attempts", 0)
                if auto_resume_attempts is None
                else auto_resume_attempts
            ),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning("resume_state_save_failed: %s", e)


def _clear_resume_state(self):
    """Remove persisted transfer state so next launch does not auto-resume."""
    from src.gui.panels.data_panel import _resume_state_path

    path = _resume_state_path()
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as e:
        logger.warning("resume_state_clear_failed: %s", e)


def _maybe_resume_transfer(self):
    """Auto-resume interrupted transfer from persisted state."""
    if self._resume_attempted:
        return
    self._resume_attempted = True
    if self.is_transferring:
        return

    state = self._load_resume_state()
    if not state:
        return
    state_status = str(state.get("status", "")).lower()
    if state_status not in ("running", "retry_pending", "interrupted"):
        return

    source = str(state.get("source", "")).strip()
    dest = str(state.get("dest", "")).strip()
    auto_attempts = int(state.get("auto_resume_attempts", 0))
    t = current_theme()

    if auto_attempts >= 3:
        self._transfer_status.config(
            text="[WARN] Auto-resume disabled after 3 failed attempts. "
                 "Click Start Transfer manually.",
            fg=t["orange"],
        )
        self._clear_resume_state()
        return

    if not source or not os.path.isdir(source):
        self._transfer_status.config(
            text="[WARN] Saved resume source missing; auto-resume skipped.",
            fg=t["orange"],
        )
        self._clear_resume_state()
        return
    if not dest:
        self._transfer_status.config(
            text="[WARN] Saved resume destination missing; auto-resume skipped.",
            fg=t["orange"],
        )
        self._clear_resume_state()
        return

    self._selected_path_var.set(source)
    self._source_path_var.set(dest)
    if state_status == "retry_pending":
        msg = "Resuming transfer after previous failure..."
    elif state_status == "interrupted":
        msg = "Resuming interrupted transfer..."
    else:
        msg = "Resuming previous transfer..."
    self._transfer_status.config(text=msg, fg=t["orange"])
    self._save_resume_state(
        source=source,
        dest=dest,
        status=state_status,
        auto_resume_attempts=auto_attempts + 1,
    )
    started = self._start_transfer(source=source, dest=dest, resume=True)
    if not started:
        self._clear_resume_state()
        self._transfer_status.config(
            text="[WARN] Auto-resume failed to start. "
                 "Verify source path, then click Start Transfer.",
            fg=t["orange"],
        )


# ================================================================
# SECTION A handler: Change source
# ================================================================

def _on_change_source(self):
    """Open folder picker for the download destination folder."""
    from tkinter import filedialog

    current = self._source_path_var.get().strip()
    initial = current if current and os.path.isdir(current) else ""
    folder = filedialog.askdirectory(
        title="Select Download Destination Folder",
        initialdir=initial,
    )
    if folder:
        norm = os.path.normpath(folder)
        self._source_path_var.set(norm)

        # Update live config (download_folder only, not source_folder)
        paths = getattr(self.config, "paths", None)
        if paths:
            paths.download_folder = norm

        # Persist to YAML
        if bool(self._persist_download_var.get()):
            try:
                save_config_field("paths.download_folder", norm)
            except Exception as e:
                logger.warning("Could not persist download path: %s", e)


# ================================================================
# SECTION B handler: Browse
# ================================================================

def _on_browse(self):
    """Open native folder picker starting at selected drive."""
    from tkinter import filedialog

    drive = self._drive_var.get()
    initial = drive if os.path.isdir(drive) else ""
    folder = filedialog.askdirectory(
        title="Select Folder to Transfer FROM", initialdir=initial,
    )
    if folder:
        norm = os.path.normpath(folder)
        self._selected_path_var.set(norm)
        self._persist_transfer_source_path(norm)
        # Update drive combo to match the selected folder's drive
        # so the display stays consistent (e.g. user browses to E:\)
        folder_drive = os.path.splitdrive(norm)[0]
        if folder_drive:
            folder_drive = folder_drive + os.sep
            if folder_drive != self._drive_var.get():
                self._drive_var.set(folder_drive)
        self._on_preview()


# ================================================================
# SECTION C handlers: Preview + scan
# ================================================================

def _on_preview(self):
    """Scan selected folder in a background thread."""
    path = self._selected_path_var.get().strip()
    if not path or not os.path.isdir(path):
        self._set_preview_text("[WARN] Folder does not exist: {}".format(path))
        return
    self._persist_transfer_source_path(os.path.normpath(path))
    self._set_preview_text("Scanning {}...".format(path))
    threading.Thread(
        target=self._scan_preview, args=(path,), daemon=True,
    ).start()


def _persist_transfer_source_path(self, path):
    """Persist transfer-source path when default toggle is enabled."""
    if not bool(self._persist_transfer_source_var.get()):
        return
    paths = getattr(self.config, "paths", None)
    if paths:
        paths.transfer_source_folder = path
    try:
        save_config_field("paths.transfer_source_folder", path)
    except Exception as e:
        logger.warning("Could not persist transfer source path: %s", e)


def _scan_preview(self, path):
    """Background thread: delegate to pure function, schedule UI update."""
    from src.gui.panels.data_panel import _scan_folder_summary

    try:
        summary = _scan_folder_summary(path)
        safe_after(self, 0, self._set_preview_text, summary)
    except Exception as e:
        safe_after(self, 0, self._set_preview_text,
                   "[FAIL] Scan error: {}".format(str(e)[:80]))


# ================================================================
# SECTION E handler: Post-transfer navigation
# ================================================================

def _goto_index(self):
    """Switch to the Index panel view."""
    if hasattr(self._app, "show_view"):
        self._app.show_view("index")


# ================================================================
# BIND -- attach all runtime methods to DataPanel class
# ================================================================

def bind_datapanel_runtime_methods(cls):
    """Attach runtime + transfer methods to the DataPanel class.

    Delegates transfer orchestration to data_panel_transfer.py.
    """
    from src.gui.panels.data_panel_transfer import bind_datapanel_transfer_methods

    # Resume state
    cls._load_resume_state = _load_resume_state
    cls._save_resume_state = _save_resume_state
    cls._clear_resume_state = _clear_resume_state
    cls._maybe_resume_transfer = _maybe_resume_transfer
    # Section A handler
    cls._on_change_source = _on_change_source
    # Section B handler
    cls._on_browse = _on_browse
    # Section C handlers
    cls._on_preview = _on_preview
    cls._persist_transfer_source_path = _persist_transfer_source_path
    cls._scan_preview = _scan_preview
    # Section E handler
    cls._goto_index = _goto_index
    # Delegate transfer orchestration (Section D)
    bind_datapanel_transfer_methods(cls)
