# === NON-PROGRAMMER GUIDE ===
# Purpose: Shares the background indexing-launch logic between manual and scheduled triggers.
# What to read first: Start at start_background_indexing(), then read the small callback helper.
# Inputs: App state plus a validated source folder.
# Outputs: Starts a daemon indexing worker and updates shared progress counters.
# Safety notes: This module does not validate auth or request paths; callers handle that boundary.
# ============================

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from src.core.indexer import IndexingProgressCallback


logger = logging.getLogger(__name__)


class APIProgressCallback(IndexingProgressCallback):
    """Capture indexing progress into the shared API state object."""

    def __init__(self, state: Any) -> None:
        self._state = state

    def on_file_start(self, file_path: str, file_num: int, total_files: int) -> None:
        _ = file_num
        with self._state.indexing_lock:
            self._state.index_progress["current_file"] = os.path.basename(file_path)
            self._state.index_progress["files_total"] = total_files

    def on_file_complete(self, file_path: str, chunks_created: int) -> None:
        _ = file_path, chunks_created
        with self._state.indexing_lock:
            self._state.index_progress["files_processed"] += 1

    def on_file_skipped(self, file_path: str, reason: str) -> None:
        _ = file_path, reason
        with self._state.indexing_lock:
            self._state.index_progress["files_skipped"] += 1

    def on_error(self, file_path: str, error: str) -> None:
        _ = file_path, error
        with self._state.indexing_lock:
            self._state.index_progress["files_errored"] += 1


def _reset_index_progress(state: Any) -> None:
    with state.indexing_lock:
        state.index_progress.update(
            {
                "files_processed": 0,
                "files_total": 0,
                "files_skipped": 0,
                "files_errored": 0,
                "current_file": "",
                "start_time": time.time(),
            }
        )


def start_background_indexing(
    state: Any,
    source_folder: str,
    *,
    on_complete: Callable[[bool, str], None] | None = None,
    trigger: str = "manual",
) -> bool:
    """Start a background indexing run if the state is currently idle."""
    if (
        not getattr(state, "config", None)
        or not getattr(state, "vector_store", None)
        or not getattr(state, "embedder", None)
    ):
        return False

    with state.indexing_lock:
        if state.indexing_active:
            return False
        state.indexing_active = True
        state.indexing_stop_event.clear()
    tracker = getattr(state, "index_schedule", None)

    def _run_indexing() -> None:
        from src.core.chunker import Chunker
        from src.core.indexer import Indexer

        success = False
        error_message = ""
        try:
            _reset_index_progress(state)
            chunker = Chunker(state.config.chunking)
            indexer = Indexer(state.config, state.vector_store, state.embedder, chunker)
            callback = APIProgressCallback(state)
            indexer.index_folder(
                source_folder,
                callback,
                stop_flag=state.indexing_stop_event,
            )
            success = True
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.error("[FAIL] Indexing error: %s", exc, exc_info=True)
        finally:
            with state.indexing_lock:
                state.indexing_active = False
            if tracker is not None:
                tracker.record_run_finished(
                    success=success,
                    error=error_message,
                    stopped=bool(
                        not success
                        and getattr(state, "indexing_stop_event", None)
                        and state.indexing_stop_event.is_set()
                    ),
                )
            if on_complete is not None:
                on_complete(success, error_message)

    thread = threading.Thread(target=_run_indexing, daemon=True)
    state.indexing_thread = thread
    thread.start()
    if tracker is not None:
        tracker.record_run_started(
            trigger=trigger,
            source_folder=source_folder,
        )
    return True
