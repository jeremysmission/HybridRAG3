# QueryPanel runtime: query execution, cancellation, and streaming flow.
from __future__ import annotations

import logging
import time
import threading
import tkinter as tk

from src.gui.helpers.safe_after import safe_after
from src.gui.theme import current_theme

logger = logging.getLogger(__name__)


def _call_engine_with_optional_cancel(method, question, cancel_event):
    """Call query/query_stream with cancel_event when supported."""
    try:
        return method(question, cancel_event=cancel_event)
    except TypeError as exc:
        if "cancel_event" not in str(exc):
            raise
        return method(question)


def _resolve_query_engine(self):
    """Return a usable query engine, healing stale panel references."""
    if self.query_engine is not None:
        return self.query_engine

    # Mode switches can briefly desync panel-local reference from app-level
    # engine; pull from toplevel app if available.
    try:
        app = self.winfo_toplevel()
        engine = getattr(app, "query_engine", None)
        if engine is not None:
            self.query_engine = engine
            return engine
    except Exception:
        pass
    return None


def _on_ask(self, event=None):
    """Handle Ask button click or Enter key.

    State transition: IDLE -> SEARCHING
    The query runs in a background thread to keep the GUI responsive.
    """
    question = self.question_entry.get().strip()
    if not question or question == "Type your question here...":
        return

    engine = _resolve_query_engine(self)
    if engine is None:
        self._show_error("[FAIL] Query engine not initialized. Run boot first.")
        return
    if self.is_querying:
        return
    # Enforce current grounding bias before each query execution.
    self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

    # --- Transition to SEARCHING state ---
    self._set_query_controls(running=True)
    self._stream_start = time.time()
    self._query_seq += 1
    query_id = self._query_seq
    self._active_query_id = query_id
    self._cancelled_query_ids.discard(query_id)
    self._query_cancel_event = threading.Event()

    # Public testing state (main thread, before thread starts)
    self.is_querying = True
    self.query_done_event.clear()
    self.last_answer_preview = ""
    self.last_query_status = ""

    # Clear previous answer for fresh output
    self.answer_text.config(state=tk.NORMAL)
    self.answer_text.delete("1.0", tk.END)
    self.answer_text.config(state=tk.DISABLED)
    self.sources_label.config(text="Sources: (none)", fg=current_theme()["gray"])
    self.metrics_label.config(text="")

    # Show immediate visual feedback: status text + animated overlay
    t = current_theme()
    self.network_label.config(text="Searching documents...", fg=t["gray"])
    self._overlay.start("Searching documents...")

    # Choose streaming path (token-by-token) or fallback (wait for full result)
    has_stream = hasattr(engine, "query_stream")
    if has_stream:
        self._query_thread = threading.Thread(
            target=self._run_query_stream,
            args=(question, query_id, self._query_cancel_event),
            daemon=True,
        )
    else:
        self._query_thread = threading.Thread(
            target=self._run_query,
            args=(question, query_id, self._query_cancel_event),
            daemon=True,
        )
    self._query_thread.start()


def _run_query(self, question, query_id, cancel_event=None):
    """Execute query in background thread (non-streaming fallback)."""
    try:
        result = _call_engine_with_optional_cancel(
            self.query_engine.query, question, cancel_event
        )
        if self._is_query_aborted(query_id):
            return
        # Thread-safe completion signal + status
        self.is_querying = False
        self.last_answer_preview = (result.answer or "")[:200]
        self.last_query_status = "error" if result.error else "complete"
        self.query_done_event.set()
        safe_after(self, 0, self._display_result, result)
    except Exception as e:
        if self._is_query_aborted(query_id):
            return
        error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
        self.is_querying = False
        self.last_answer_preview = error_msg
        self.last_query_status = "error"
        self.query_done_event.set()
        safe_after(self, 0, self._show_error, error_msg)


def _run_query_stream(self, question, query_id, cancel_event=None):
    """Execute streaming query in background thread.

    State transitions driven by the query engine's yield chunks:
      "searching" phase -> stay in SEARCHING state
      "generating" phase -> transition to GENERATING state
      "token" chunks -> append tokens (GENERATING)
      "done" chunk -> transition to COMPLETE state
    """
    try:
        for chunk in _call_engine_with_optional_cancel(
            self.query_engine.query_stream, question, cancel_event
        ):
            if self._is_query_aborted(query_id):
                return
            if "phase" in chunk:
                if chunk["phase"] == "searching":
                    # Still in SEARCHING -- update status text
                    safe_after(
                        self,
                        0,
                        self._set_status_if_active,
                        query_id,
                        "Searching documents...",
                    )
                elif chunk["phase"] == "generating":
                    # --- Transition: SEARCHING -> GENERATING ---
                    n = chunk.get("chunks", 0)
                    ms = chunk.get("retrieval_ms", 0)
                    msg = "Found {} chunks ({:.0f}ms) -- Generating answer...".format(
                        n, ms
                    )
                    safe_after(self, 0, self._set_status_if_active, query_id, msg)
                    safe_after(self, 0, self._start_elapsed_timer_if_active, query_id)
                    safe_after(self, 0, self._prepare_streaming_if_active, query_id)
                    safe_after(self, 0, self._stop_overlay_if_active, query_id)
            elif "token" in chunk:
                safe_after(
                    self, 0, self._append_token_if_active, query_id, chunk["token"]
                )
            elif chunk.get("done"):
                result = chunk.get("result")
                if result:
                    if self._is_query_aborted(query_id):
                        return
                    # Thread-safe completion signal + status
                    self.is_querying = False
                    self.last_answer_preview = (result.answer or "")[:200]
                    self.last_query_status = "error" if result.error else "complete"
                    self.query_done_event.set()
                    safe_after(self, 0, self._finish_stream_if_active, query_id, result)
                return
        # If generator exhausted without "done"
        if self._is_query_aborted(query_id):
            return
        self.is_querying = False
        self.last_query_status = "incomplete"
        self.query_done_event.set()
        safe_after(self, 0, self._stop_elapsed_timer)
        safe_after(self, 0, self._stop_overlay_if_active, query_id)
        safe_after(self, 0, self._set_query_controls, False)
    except Exception as e:
        if self._is_query_aborted(query_id):
            return
        error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
        self.is_querying = False
        self.last_answer_preview = error_msg
        self.last_query_status = "error"
        self.query_done_event.set()
        safe_after(self, 0, self._stop_elapsed_timer)
        safe_after(self, 0, self._overlay.cancel)
        safe_after(self, 0, self._show_error, error_msg)


def _is_query_aborted(self, query_id):
    """True when a query is stale/cancelled and its UI updates must be ignored."""
    return (query_id != self._active_query_id) or (query_id in self._cancelled_query_ids)


def _set_query_controls(self, running):
    """Toggle Ask/Stop buttons for in-flight query UX."""
    t = current_theme()
    if running:
        self.ask_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
        self.stop_btn.config(state=tk.NORMAL, bg=t["red"], fg=t["accent_fg"])
    else:
        self.ask_btn.config(state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])


def _on_stop_query(self, event=None):
    """Soft-cancel current query: restore control immediately and ignore late results."""
    if not self.is_querying:
        return
    qid = self._active_query_id
    self._cancelled_query_ids.add(qid)
    if hasattr(self, "_query_cancel_event") and self._query_cancel_event is not None:
        self._query_cancel_event.set()
    self.is_querying = False
    self._streaming = False
    self.last_answer_preview = "[STOP] Query cancelled by user."
    self.last_query_status = "cancelled"
    self.query_done_event.set()
    self._stop_elapsed_timer()
    self._overlay.cancel()
    self._set_query_controls(running=False)
    t = current_theme()
    self.network_label.config(text="Query stopped.", fg=t["orange"])


def _set_status_if_active(self, query_id, text):
    """Plain-English: Updates status text only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._set_status(text)


def _start_elapsed_timer_if_active(self, query_id):
    """Plain-English: Starts the elapsed-time indicator only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._start_elapsed_timer()


def _prepare_streaming_if_active(self, query_id):
    """Plain-English: Prepares streaming output buffers only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._prepare_streaming()


def _append_token_if_active(self, query_id, token):
    """Plain-English: Appends streamed tokens only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._append_token(token)


def _finish_stream_if_active(self, query_id, result):
    """Plain-English: Finalizes stream rendering only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._finish_stream(result)


def _stop_overlay_if_active(self, query_id):
    """Plain-English: Hides the loading overlay only if this panel still owns the active request."""
    if self._is_query_aborted(query_id):
        return
    self._overlay.stop()


def bind_query_panel_query_flow_runtime_methods(cls):
    """Bind query-flow runtime methods to QueryPanel."""
    cls._on_ask = _on_ask
    cls._run_query = _run_query
    cls._run_query_stream = _run_query_stream
    cls._is_query_aborted = _is_query_aborted
    cls._set_query_controls = _set_query_controls
    cls._on_stop_query = _on_stop_query
    cls._set_status_if_active = _set_status_if_active
    cls._start_elapsed_timer_if_active = _start_elapsed_timer_if_active
    cls._prepare_streaming_if_active = _prepare_streaming_if_active
    cls._append_token_if_active = _append_token_if_active
    cls._finish_stream_if_active = _finish_stream_if_active
    cls._stop_overlay_if_active = _stop_overlay_if_active
