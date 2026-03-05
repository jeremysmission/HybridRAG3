# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the query executor part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Query Executor (src/gui/panels/query_executor.py)
# ============================================================================
# Extracted from query_panel.py. Handles background query execution,
# streaming token dispatch, and cost event emission. Uses callbacks to
# communicate with the GUI layer -- contains NO tkinter imports.
# ============================================================================

import logging
import threading
import time
from typing import Callable, Optional

from src.core.cost_tracker import get_cost_tracker

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Run queries in background threads with cancellation support.

    This class owns the query lifecycle (submit, stream, cancel, complete)
    but never touches widgets. It communicates results via callbacks.
    """

    def __init__(self):
        """Plain-English: This function handles init."""
        self._query_seq = 0
        self._active_query_id = 0
        self._cancelled_ids: set = set()
        self._thread: Optional[threading.Thread] = None
        self.is_querying = False
        self.done_event = threading.Event()
        self.last_answer_preview = ""
        self.last_query_status = ""

    def submit(
        self,
        query_engine,
        question: str,
        on_phase: Callable,
        on_token: Callable,
        on_complete: Callable,
        on_error: Callable,
    ) -> int:
        """Submit a query for background execution.

        Args:
            query_engine: QueryEngine instance with query() and query_stream().
            question: The user's question text.
            on_phase: Called with (query_id, phase_name, details_dict).
            on_token: Called with (query_id, token_str).
            on_complete: Called with (query_id, result).
            on_error: Called with (query_id, error_msg).

        Returns:
            The query_id for this submission (use with cancel()).
        """
        self._query_seq += 1
        query_id = self._query_seq
        self._active_query_id = query_id
        self._cancelled_ids.discard(query_id)
        self.is_querying = True
        self.done_event.clear()
        self.last_answer_preview = ""
        self.last_query_status = ""

        has_stream = hasattr(query_engine, "query_stream")
        if has_stream:
            self._thread = threading.Thread(
                target=self._run_stream,
                args=(query_engine, question, query_id,
                      on_phase, on_token, on_complete, on_error),
                daemon=True,
            )
        else:
            self._thread = threading.Thread(
                target=self._run_sync,
                args=(query_engine, question, query_id,
                      on_complete, on_error),
                daemon=True,
            )
        self._thread.start()
        return query_id

    def cancel(self, query_id: Optional[int] = None) -> None:
        """Soft-cancel a query by ID (or the active query if None)."""
        qid = query_id if query_id is not None else self._active_query_id
        self._cancelled_ids.add(qid)
        self.is_querying = False
        self.last_answer_preview = "[STOP] Query cancelled by user."
        self.last_query_status = "cancelled"
        self.done_event.set()

    def is_aborted(self, query_id: int) -> bool:
        """True when a query has been cancelled or superseded."""
        return (query_id != self._active_query_id) or (query_id in self._cancelled_ids)

    def _finish(self, result, is_error=False):
        """Mark query as done and update public state."""
        self.is_querying = False
        if is_error:
            self.last_answer_preview = str(result)[:200]
            self.last_query_status = "error"
        else:
            self.last_answer_preview = (getattr(result, "answer", "") or "")[:200]
            self.last_query_status = "error" if getattr(result, "error", None) else "complete"
        self.done_event.set()

    def _run_sync(self, query_engine, question, query_id, on_complete, on_error):
        """Execute query synchronously (non-streaming fallback)."""
        try:
            result = query_engine.query(question)
            if self.is_aborted(query_id):
                return
            self._finish(result)
            on_complete(query_id, result)
        except Exception as e:
            if self.is_aborted(query_id):
                return
            error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
            self._finish(error_msg, is_error=True)
            on_error(query_id, error_msg)

    def _run_stream(self, query_engine, question, query_id,
                    on_phase, on_token, on_complete, on_error):
        """Execute streaming query with phase/token/done dispatch."""
        try:
            for chunk in query_engine.query_stream(question):
                if self.is_aborted(query_id):
                    return
                if "phase" in chunk:
                    on_phase(query_id, chunk["phase"], chunk)
                elif "token" in chunk:
                    on_token(query_id, chunk["token"])
                elif chunk.get("done"):
                    result = chunk.get("result")
                    if result:
                        if self.is_aborted(query_id):
                            return
                        self._finish(result)
                        on_complete(query_id, result)
                    return

            # Generator exhausted without "done"
            if self.is_aborted(query_id):
                return
            self.is_querying = False
            self.last_query_status = "incomplete"
            self.done_event.set()
            on_phase(query_id, "incomplete", {})

        except Exception as e:
            if self.is_aborted(query_id):
                return
            error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
            self._finish(error_msg, is_error=True)
            on_error(query_id, error_msg)

    @staticmethod
    def emit_cost_event(result, model: str, profile: str) -> None:
        """Record completed query in the cost tracker for PM dashboard."""
        try:
            tracker = get_cost_tracker()
            tracker.record(
                tokens_in=getattr(result, "tokens_in", 0),
                tokens_out=getattr(result, "tokens_out", 0),
                model=model,
                mode=getattr(result, "mode", "offline"),
                profile=profile,
                latency_ms=getattr(result, "latency_ms", 0.0),
            )
        except Exception as e:
            logger.debug("Cost event emit failed: %s", e)
