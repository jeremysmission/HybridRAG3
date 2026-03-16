# === NON-PROGRAMMER GUIDE ===
# Purpose: Transfer engine orchestration for DataPanel -- extracted to keep classes
#   under 500 code lines.
# What to read first: _start_transfer() is the main entry point; _run_transfer()
#   runs in a background thread; _poll_stats() updates the GUI every 500ms.
# Inputs: DataPanel instance (self), source/dest paths, engine stats.
# Outputs: GUI updates, transfer engine lifecycle, resume state persistence.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""Transfer engine orchestration for DataPanel.

Contains: transfer start/stop/poll, progress display, engine lifecycle,
manifest queries, and completion/error handlers.
"""

import logging
import os
import threading
from datetime import datetime
import tkinter as tk

from src.gui.helpers.safe_after import safe_after
from src.gui.theme import current_theme

logger = logging.getLogger(__name__)


# ================================================================
# Transfer start / validate / launch
# ================================================================

def _on_start_transfer(self):
    """Start transfer using values from current UI fields."""
    source = self._selected_path_var.get().strip()
    dest = self._source_path_var.get().strip()
    self._apply_estimate_value(show_status=False)
    self._start_transfer(source=source, dest=dest, resume=False)


def _apply_estimate_value(self, show_status=True):
    """Parse Estimated Total (GB) field and apply immediately."""
    from src.gui.panels.data_panel import _fmt_size

    t = current_theme()
    est_gb = (self._est_total_gb_var.get() or "").strip()
    self._estimated_total_bytes = 0
    if est_gb:
        try:
            gb = float(est_gb)
            if gb > 0:
                self._estimated_total_bytes = int(gb * (1024 ** 3))
            else:
                raise ValueError("must be > 0")
        except Exception:
            if show_status:
                self._transfer_status.config(
                    text="[WARN] Estimated total must be a positive number (GB).",
                    fg=t["orange"],
                )
            return False
    if show_status:
        if self._estimated_total_bytes > 0:
            self._transfer_status.config(
                text="[OK] ETA estimate applied: {}".format(
                    _fmt_size(self._estimated_total_bytes)
                ),
                fg=t["green"],
            )
        else:
            self._transfer_status.config(
                text="[OK] ETA estimate cleared (using discovered total).",
                fg=t["gray"],
            )
    return True


def _on_apply_estimate(self, _event=None):
    """Apply estimated total size and refresh ETA immediately."""
    self._apply_estimate_value(show_status=True)
    # If transfer is running, refresh stats line now so ETA changes immediately.
    if self._engine is not None:
        try:
            self._poll_stats()
        except Exception:
            pass


def _start_transfer(self, source, dest, resume=False):
    """Validate inputs and launch transfer in background thread."""
    from src.gui.panels.data_panel import _probe_source_ready

    t = current_theme()
    # If a previous transfer thread object exists but is no longer alive,
    # normalize UI state so Start cannot get stuck disabled.
    if self._transfer_thread is not None and not self._transfer_thread.is_alive():
        self._transfer_thread = None
        self.is_transferring = False
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)

    if self._transfer_thread is not None and self._transfer_thread.is_alive():
        self._transfer_status.config(
            text="Transfer already running. Stop it first.", fg=t["orange"]
        )
        return False

    if not source or not os.path.isdir(source):
        self._transfer_status.config(
            text="[FAIL] Select a source folder first", fg=t["red"])
        return False

    if not dest:
        self._transfer_status.config(
            text="[FAIL] Set destination source path first", fg=t["red"])
        return False

    # Prevent transferring into self
    src_norm = os.path.normcase(os.path.normpath(source))
    dst_norm = os.path.normcase(os.path.normpath(dest))
    if src_norm == dst_norm:
        self._transfer_status.config(
            text="[FAIL] Source and destination are the same", fg=t["red"])
        return False

    if self._detached_worker:
        self._transfer_status.config(
            text="[WARN] Previous transfer worker was force-detached. "
                 "Restart app before starting a new transfer.",
            fg=t["orange"],
        )
        return False

    ok, probe_err = _probe_source_ready(source, timeout_s=2.0)
    if not ok:
        self._transfer_status.config(
            text="[FAIL] Source not reachable: {}".format(probe_err[:80]),
            fg=t["red"],
        )
        return False

    # Reset UI
    self._stop_event.clear()
    self._stop_watchdog_ticks = 0
    self._stop_in_progress = False
    self._resumed_run = bool(resume)
    self._manifest_note_tick = 0
    self._start_btn.config(state=tk.DISABLED)
    self._stop_btn.config(text="Stop")
    self._stop_btn.config(state=tk.NORMAL)
    self._progress_bar["value"] = 0
    self._progress_label.config(text="0 / 0")
    self._stats_label.config(
        text="--/s | ETA -- | copied: 0 | processed: 0 | skipped: 0 | err: 0"
    )
    self._stats_detail_label.config(
        text="Elapsed 0s | Data 0 B / 0 B | discovered 0"
    )
    self._run_id_var.set("Run ID: pending...")
    self._stop_ack_var.set("Stop Ack: --")
    self._last_reason_var.set("Last Manifest Reason: --")
    skip_full_discovery = str(
        os.getenv("HYBRIDRAG_SKIP_DISCOVERY", "0")
    ).strip().lower() in ("1", "true", "yes", "on")

    if resume:
        self._transfer_status.config(
            text="Resuming transfer from saved state...", fg=t["orange"])
    elif skip_full_discovery:
        self._transfer_status.config(
            text="[WARN] Fast-start mode active: skipping full discovery; "
                 "using resume seed candidates only.",
            fg=t["orange"],
        )
    else:
        self._transfer_status.config(text="Starting transfer...", fg=t["gray"])

    # Public testing state (main thread, before thread starts)
    self.is_transferring = True
    self.transfer_done_event.clear()
    self.last_transfer_status = ""
    self._save_resume_state(source=source, dest=dest, status="running")

    # Launch in background
    self._transfer_thread = threading.Thread(
        target=self._run_transfer,
        args=(source, dest, skip_full_discovery),
        daemon=True,
    )
    self._transfer_thread.start()

    # Start polling
    self._poll_stats()
    return True


def _run_transfer(self, source, dest, skip_full_discovery=False):
    """Background thread: create engine and run transfer with diagnostics."""
    try:
        # Emit start event for observability
        try:
            from src.gui.app_context import get_controller
            from src.gui.core.events import make_event
            ctrl = get_controller()
            ctrl._emit(make_event("data_transfer_started", ctrl.diag.run_id,
                                  message=source, source=source, dest=dest))
        except Exception:
            pass

        from src.tools.bulk_transfer_v2 import BulkTransferV2, TransferConfig

        cfg = TransferConfig(
            source_paths=[source],
            dest_path=dest,
            workers=8,
            skip_full_discovery=bool(skip_full_discovery),
        )
        self._engine = BulkTransferV2(cfg)
        self._engine.run()

        # Emit completion event
        try:
            from src.gui.app_context import get_controller
            from src.gui.core.events import make_event
            ctrl = get_controller()
            stats = self._engine.stats
            ctrl._emit(make_event("data_transfer_completed", ctrl.diag.run_id,
                                  message=source, source=source, dest=dest,
                                  files_copied=getattr(stats, "files_copied", 0),
                                  files_skipped=getattr(stats, "files_skipped", 0)))
        except Exception:
            pass

        # Thread-safe completion signal + status
        self.is_transferring = False
        self.last_transfer_status = "[OK] Transfer complete"
        self.transfer_done_event.set()
        safe_after(self, 0, self._on_transfer_done)
    except Exception as e:
        # Emit error event with full traceback
        try:
            from src.gui.app_context import get_controller
            from src.gui.core.events import make_event
            ctrl = get_controller()
            err_path = ctrl.diag.write_error("data_transfer", e)
            ctrl._emit(make_event("data_transfer_failed", ctrl.diag.run_id,
                                  message=str(e), source=source, dest=dest,
                                  error_path=err_path))
        except Exception:
            pass

        msg = "[FAIL] {}: {}".format(type(e).__name__, str(e)[:80])
        try:
            self._save_resume_state(
                source=source, dest=dest, status="retry_pending",
            )
        except Exception:
            pass
        self.is_transferring = False
        self.last_transfer_status = msg
        self.transfer_done_event.set()
        safe_after(self, 0, self._on_transfer_error, msg)


# ================================================================
# Stop / cleanup
# ================================================================

def _on_stop_transfer(self):
    """Signal the transfer engine to stop."""
    t = current_theme()
    if self._transfer_thread is None or not self._transfer_thread.is_alive():
        self._stop_in_progress = False
        self._stop_btn.config(text="Stop", state=tk.DISABLED)
        self._transfer_status.config(
            text="[WARN] No active transfer to stop.", fg=t["orange"]
        )
        return

    # Second press during hang => safe UI detach.
    if self._stop_in_progress:
        self._transfer_thread = None
        self.is_transferring = False
        self._detached_worker = True
        self._stop_in_progress = False
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(text="Stop", state=tk.DISABLED)
        self._transfer_status.config(
            text="[WARN] Transfer worker detached due to stop timeout. "
                 "Restart app before next transfer.",
            fg=t["orange"],
        )
        return

    self._stop_event.set()
    self._stop_watchdog_ticks = 0
    self._stop_in_progress = True
    self._stop_ack_var.set(
        "Stop Ack: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    if self._engine is not None:
        self._engine._stop.set()
    self._clear_resume_state()
    self._stop_btn.config(state=tk.NORMAL, text="Force Stop")
    self._transfer_status.config(
        text="Stopping after current file...", fg=t["orange"])
    # Safety watchdog: if worker exits but callback path is missed, restore UI.
    self.after(800, self._ensure_transfer_cleanup)


def _ensure_transfer_cleanup(self):
    """
    Ensure UI recovers after stop requests even if callback sequencing
    is interrupted. Safe to call repeatedly.
    """
    from src.gui.panels.data_panel import _fmt_size

    t = current_theme()
    if self._transfer_thread is not None and self._transfer_thread.is_alive():
        self._stop_watchdog_ticks += 1
        if self._stop_watchdog_ticks >= 15:
            # Keep UI responsive and allow explicit operator action.
            self._start_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL, text="Force Stop")
            self._transfer_status.config(
                text="[WARN] Stop is waiting on network/file operation. "
                     "Press Force Stop to detach UI.",
                fg=t["orange"],
            )
        if self._stop_watchdog_ticks >= 75:
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED, text="Stop")
            self.is_transferring = False
            self._stop_in_progress = False
            self._transfer_status.config(
                text="[WARN] Stop timed out after 60s. Worker may still "
                     "be draining in background; restart app if needed.",
                fg=t["orange"],
            )
            return
        # Still stopping; check again shortly.
        self.after(800, self._ensure_transfer_cleanup)
        return
    self._transfer_thread = None
    self.is_transferring = False
    self._stop_in_progress = False
    self._start_btn.config(state=tk.NORMAL)
    self._stop_btn.config(state=tk.DISABLED, text="Stop")
    if self._stop_event.is_set():
        if self._engine is not None:
            stats = self._engine.stats
            self._transfer_status.config(
                text="[WARN] Transfer stopped -- {:,} files copied, {} transferred".format(
                    stats.files_copied, _fmt_size(stats.bytes_copied),
                ),
                fg=t["orange"],
            )
        else:
            self._transfer_status.config(
                text="[WARN] Transfer stopped", fg=t["orange"]
            )


# ================================================================
# Polling / progress
# ================================================================

def _poll_stats(self):
    """Poll engine.stats every 500ms and update the GUI."""
    from src.gui.panels.data_panel import _fmt_rate, _fmt_dur, _fmt_size

    if self._engine is None:
        self._poll_id = self.after(500, self._poll_stats)
        return

    stats = self._engine.stats
    t = current_theme()
    run_id = str(getattr(self._engine, "run_id", "")).strip()
    if run_id:
        suffix = " (resumed)" if self._resumed_run else ""
        self._run_id_var.set("Run ID: {}{}".format(run_id, suffix))

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
    if self._estimated_total_bytes > 0 and speed > 0:
        remaining = max(0, self._estimated_total_bytes - int(stats.bytes_copied))
        eta = float(remaining) / float(speed)
    eta_str = _fmt_dur(eta) if eta < 86400 else "---"
    skipped_total = (
        int(getattr(stats, "files_skipped_unchanged", 0))
        + int(getattr(stats, "files_skipped_ext", 0))
        + int(getattr(stats, "files_skipped_size", 0))
        + int(getattr(stats, "files_skipped_locked", 0))
        + int(getattr(stats, "files_skipped_encoding", 0))
        + int(getattr(stats, "files_skipped_symlink", 0))
        + int(getattr(stats, "files_skipped_hidden", 0))
        + int(getattr(stats, "files_skipped_inaccessible", 0))
        + int(getattr(stats, "files_skipped_long_path", 0))
    )
    processed_total = int(getattr(stats, "files_processed", 0))
    self._stats_label.config(
        text="{} | ETA {} | copied: {:,} | processed: {:,} | skipped: {:,} | err: {:,}".format(
            _fmt_rate(speed), eta_str,
            copied, processed_total, skipped_total, stats.files_failed,
        ),
        fg=t["gray"],
    )
    # Fast cumulative counter from transfer manifest DB (no source discovery).
    if self._manifest_note_tick % 4 == 0:
        self._total_copied_db_bytes = self._read_total_copied_bytes_from_manifest()
    self._stats_detail_label.config(
        text="Elapsed {} | Data {} / {} | discovered {:,} | manifest {:,} | total copied (all runs): {}".format(
            _fmt_dur(stats.elapsed),
            _fmt_size(stats.bytes_copied),
            _fmt_size(self._estimated_total_bytes if self._estimated_total_bytes > 0 else stats.bytes_source_total),
            stats.files_discovered,
            int(getattr(stats, "files_manifest", 0)),
            _fmt_size(self._total_copied_db_bytes),
        ),
        fg=t["gray"],
    )
    self._manifest_note_tick += 1
    if self._manifest_note_tick >= 4:
        self._manifest_note_tick = 0
        note = self._get_last_manifest_reason()
        if note:
            self._last_reason_var.set("Last Manifest Reason: {}".format(note))

    # Continue polling if transfer is still running
    try:
        current_status = (self._transfer_status.cget("text") or "").lower()
        if (
            ("resuming transfer" in current_status or "starting transfer" in current_status)
            and not self._stop_event.is_set()
        ):
            self._transfer_status.config(
                text="Transfer running... discovered {:,}, copied {:,}".format(
                    stats.files_discovered, stats.files_copied
                ),
                fg=t["gray"],
            )
    except Exception:
        pass

    # Continue polling if transfer is still running
    if self._transfer_thread is not None and self._transfer_thread.is_alive():
        self._poll_id = self.after(500, self._poll_stats)
    else:
        # One final update
        self._poll_id = None


# ================================================================
# Completion / error handlers
# ================================================================

def _on_transfer_done(self):
    """Transfer completed -- update UI."""
    from src.gui.panels.data_panel import _fmt_size

    t = current_theme()
    self._start_btn.config(state=tk.NORMAL)
    self._stop_btn.config(state=tk.DISABLED, text="Stop")
    self._transfer_thread = None
    self._stop_in_progress = False

    if self._engine is not None:
        stats = self._engine.stats
        if self._stop_event.is_set():
            self._transfer_status.config(
                text="[WARN] Transfer stopped -- {:,} files copied, {} transferred".format(
                    stats.files_copied, _fmt_size(stats.bytes_copied),
                ),
                fg=t["orange"],
            )
            self._clear_resume_state()
        else:
            self._transfer_status.config(
                text="[OK] Transfer complete -- {:,} files copied, {} transferred".format(
                    stats.files_copied, _fmt_size(stats.bytes_copied),
                ),
                fg=t["green"],
            )
            self._clear_resume_state()
        # Final progress update
        total = stats.files_manifest
        self._progress_bar["maximum"] = max(total, 1)
        self._progress_bar["value"] = stats.files_copied
        self._progress_label.config(
            text="{:,} / {:,}".format(stats.files_copied, total))
    else:
        self._transfer_status.config(
            text="[OK] Transfer complete", fg=t["green"])
        self._clear_resume_state()
    note = self._get_last_manifest_reason()
    if note:
        self._last_reason_var.set("Last Manifest Reason: {}".format(note))


def _on_transfer_error(self, msg):
    """Transfer failed -- update UI."""
    t = current_theme()
    self._start_btn.config(state=tk.NORMAL)
    self._stop_btn.config(state=tk.DISABLED, text="Stop")
    self._transfer_thread = None
    self._stop_in_progress = False
    self._transfer_status.config(
        text=msg + " | Resume is armed for next launch.",
        fg=t["red"],
    )
    note = self._get_last_manifest_reason()
    if note:
        self._last_reason_var.set("Last Manifest Reason: {}".format(note))


# ================================================================
# Manifest queries
# ================================================================

def _get_last_manifest_reason(self):
    """Return latest failed/locked/stopped error or skip reason for current run."""
    if self._engine is None:
        return ""
    manifest = getattr(self._engine, "manifest", None)
    run_id = str(getattr(self._engine, "run_id", "")).strip()
    if manifest is None or not run_id:
        return ""
    try:
        with manifest._lock:
            err_row = manifest.conn.execute(
                "SELECT result, error_message FROM transfer_log "
                "WHERE run_id=? AND result IN ('failed','locked','stopped') "
                "AND error_message<>'' "
                "ORDER BY rowid DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if err_row:
                result, message = err_row
                return "{}: {}".format(str(result), str(message)[:96])
            skip_row = manifest.conn.execute(
                "SELECT reason, detail FROM skipped_files "
                "WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if skip_row:
                reason, detail = skip_row
                if detail:
                    return "{}: {}".format(str(reason), str(detail)[:96])
                return str(reason)
    except Exception as e:
        logger.debug("manifest_reason_lookup_failed: %s", e)
    return ""


def _read_total_copied_bytes_from_manifest(self):
    """Return cumulative successful copied bytes from transfer manifest DB."""
    try:
        if self._engine is None:
            return 0
        manifest = getattr(self._engine, "manifest", None)
        if manifest is None:
            return 0
        with manifest._lock:
            row = manifest.conn.execute(
                "SELECT COALESCE(SUM(file_size_dest), 0) "
                "FROM transfer_log WHERE result='success'"
            ).fetchone()
        return int((row[0] if row and row[0] is not None else 0) or 0)
    except Exception as e:
        logger.debug("manifest_total_copied_lookup_failed: %s", e)
        return 0


# ================================================================
# BIND -- attach all transfer methods to DataPanel class
# ================================================================

def bind_datapanel_transfer_methods(cls):
    """Attach transfer orchestration methods to the DataPanel class."""
    cls._on_start_transfer = _on_start_transfer
    cls._apply_estimate_value = _apply_estimate_value
    cls._on_apply_estimate = _on_apply_estimate
    cls._start_transfer = _start_transfer
    cls._run_transfer = _run_transfer
    cls._on_stop_transfer = _on_stop_transfer
    cls._ensure_transfer_cleanup = _ensure_transfer_cleanup
    cls._poll_stats = _poll_stats
    cls._on_transfer_done = _on_transfer_done
    cls._on_transfer_error = _on_transfer_error
    cls._get_last_manifest_reason = _get_last_manifest_reason
    cls._read_total_copied_bytes_from_manifest = _read_total_copied_bytes_from_manifest
