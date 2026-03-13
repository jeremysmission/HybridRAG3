from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from src.security.protected_data import (
    harden_history_storage_path,
    history_encryption_enabled,
    history_secure_delete_enabled,
    protect_history_text,
    restore_history_text,
    rewrap_history_text,
)


_NOW_LOCK = threading.Lock()
_LAST_NOW: Optional[datetime] = None


def _now_iso() -> str:
    global _LAST_NOW
    with _NOW_LOCK:
        current = datetime.now().astimezone()
        if _LAST_NOW is not None and current <= _LAST_NOW:
            current = _LAST_NOW + timedelta(microseconds=1)
        _LAST_NOW = current
        return current.isoformat(timespec="microseconds")


def _compact_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _text_preview(value: str, max_len: int = 160) -> str:
    compact = _compact_text(value)
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def _protect_text(value: str | None) -> str | None:
    return protect_history_text(value)


def _restore_text(value: str | None) -> str | None:
    return restore_history_text(value)


def _rewrap_text(value: str | None) -> str | None:
    return rewrap_history_text(value)


def _load_protected_json(value: str | None, default: Any) -> Any:
    text = _restore_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def conversation_history_db_path(database_path: str) -> str:
    """Place the conversation-history DB beside the main configured data DB."""
    db_path = Path(str(database_path or "")).expanduser()
    parent = db_path.parent if str(db_path) else Path.cwd() / "data"
    return str(parent / "hybridrag_query_history.sqlite3")


def _env_positive_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return max(1, int(default))


class ConversationThreadStore:
    """Persistent thread-safe store for shared conversation history."""

    def __init__(self, db_path: str) -> None:
        self.db_path = os.path.normpath(str(db_path))
        self._lock = threading.Lock()
        self.max_threads = _env_positive_int("HYBRIDRAG_HISTORY_MAX_THREADS", 200)
        self.max_turns_per_thread = _env_positive_int(
            "HYBRIDRAG_HISTORY_MAX_TURNS_PER_THREAD",
            50,
        )
        self._ensure_schema()
        self._rewrap_existing_rows()

    @classmethod
    def from_database_path(cls, database_path: str) -> "ConversationThreadStore":
        return cls(conversation_history_db_path(database_path))

    def reset(self) -> None:
        with self._lock:
            con = self._connect()
            try:
                con.execute("DELETE FROM conversation_turns")
                con.execute("DELETE FROM conversation_threads")
                con.commit()
            finally:
                con.close()

    def thread_exists(self, thread_id: str) -> bool:
        with self._lock:
            con = self._connect()
            try:
                row = con.execute(
                    "SELECT 1 FROM conversation_threads WHERE thread_id = ? LIMIT 1",
                    (str(thread_id or "").strip(),),
                ).fetchone()
                return bool(row)
            finally:
                con.close()

    def record_completed_turn(
        self,
        *,
        thread_id: Optional[str],
        question: str,
        result: Any,
        transport: str,
        actor: str,
        actor_source: str,
        actor_role: str,
        allowed_doc_tags: list[str],
        document_policy_source: str,
    ) -> dict[str, Any]:
        debug_trace = getattr(result, "debug_trace", None) or {}
        retrieval = debug_trace.get("retrieval", {}) if isinstance(debug_trace, dict) else {}
        access_control = (
            retrieval.get("access_control", {}) if isinstance(retrieval, dict) else {}
        )
        error = str(getattr(result, "error", "") or "").strip() or None
        sources = list(getattr(result, "sources", []) or [])
        return self._record_turn(
            thread_id=thread_id,
            question=question,
            answer=getattr(result, "answer", "") or "",
            mode=str(getattr(result, "mode", "") or ""),
            transport=transport,
            actor=actor,
            actor_source=actor_source,
            actor_role=actor_role,
            allowed_doc_tags=allowed_doc_tags,
            document_policy_source=document_policy_source,
            status="error" if error else "completed",
            latency_ms=getattr(result, "latency_ms", None),
            chunks_used=int(getattr(result, "chunks_used", 0) or 0),
            source_count=len(sources),
            source_paths=[
                str(source.get("path") or "").strip()
                for source in sources
                if str(source.get("path") or "").strip()
            ],
            sources=sources,
            denied_hits=int(access_control.get("denied_hits", 0) or 0),
            error=error,
        )

    def record_failed_turn(
        self,
        *,
        thread_id: Optional[str],
        question: str,
        error: str,
        mode: str,
        transport: str,
        actor: str,
        actor_source: str,
        actor_role: str,
        allowed_doc_tags: list[str],
        document_policy_source: str,
        latency_ms: Optional[float] = None,
    ) -> dict[str, Any]:
        return self._record_turn(
            thread_id=thread_id,
            question=question,
            answer="",
            mode=mode,
            transport=transport,
            actor=actor,
            actor_source=actor_source,
            actor_role=actor_role,
            allowed_doc_tags=allowed_doc_tags,
            document_policy_source=document_policy_source,
            status="error",
            latency_ms=latency_ms,
            chunks_used=0,
            source_count=0,
            source_paths=[],
            sources=[],
            denied_hits=0,
            error=str(error or "").strip() or "query_failed",
        )

    def list_threads(self, limit: int = 20) -> dict[str, Any]:
        effective_limit = max(1, min(int(limit or 20), 100))
        with self._lock:
            con = self._connect()
            try:
                total = int(
                    con.execute("SELECT COUNT(*) FROM conversation_threads").fetchone()[0] or 0
                )
                rows = con.execute(
                    """
                    SELECT
                        thread_id,
                        title,
                        created_at,
                        updated_at,
                        created_by_actor,
                        created_by_source,
                        created_by_role,
                        last_actor,
                        last_actor_source,
                        last_actor_role,
                        turn_count,
                        last_question_preview,
                        last_answer_preview,
                        last_mode,
                        last_status
                    FROM conversation_threads
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (effective_limit,),
                ).fetchall()
            finally:
                con.close()
        return {
            "total_threads": total,
            "max_threads": self.max_threads,
            "max_turns_per_thread": self.max_turns_per_thread,
            "threads": [self._thread_row_to_dict(row) for row in rows],
        }

    def get_thread(self, thread_id: str) -> Optional[dict[str, Any]]:
        key = str(thread_id or "").strip()
        if not key:
            return None
        with self._lock:
            con = self._connect()
            try:
                thread_row = con.execute(
                    """
                    SELECT
                        thread_id,
                        title,
                        created_at,
                        updated_at,
                        created_by_actor,
                        created_by_source,
                        created_by_role,
                        last_actor,
                        last_actor_source,
                        last_actor_role,
                        turn_count,
                        last_question_preview,
                        last_answer_preview,
                        last_mode,
                        last_status
                    FROM conversation_threads
                    WHERE thread_id = ?
                    """,
                    (key,),
                ).fetchone()
                if thread_row is None:
                    return None
                turn_rows = con.execute(
                    """
                    SELECT
                        thread_id,
                        turn_index,
                        created_at,
                        completed_at,
                        question_text,
                        question_preview,
                        answer_text,
                        answer_preview,
                        mode,
                        transport,
                        actor,
                        actor_source,
                        actor_role,
                        allowed_doc_tags_json,
                        document_policy_source,
                        status,
                        latency_ms,
                        chunks_used,
                        source_count,
                        source_paths_json,
                        sources_json,
                        denied_hits,
                        error
                    FROM conversation_turns
                    WHERE thread_id = ?
                    ORDER BY turn_index ASC
                    """,
                    (key,),
                ).fetchall()
            finally:
                con.close()
        return {
            "thread": self._thread_row_to_dict(thread_row),
            "turns": [self._turn_row_to_dict(row) for row in turn_rows],
        }

    def build_follow_up_query(
        self,
        thread_id: str,
        question: str,
        *,
        max_turns: int = 3,
    ) -> str:
        """Project recent turns into a bounded prompt for follow-up questions."""
        key = str(thread_id or "").strip()
        current_question = _compact_text(question)
        if not key:
            return current_question
        with self._lock:
            con = self._connect()
            try:
                rows = con.execute(
                    """
                    SELECT turn_index, question_text, answer_text, answer_preview, error
                    FROM conversation_turns
                    WHERE thread_id = ?
                    ORDER BY turn_index DESC
                    LIMIT ?
                    """,
                    (key, max(1, int(max_turns or 3))),
                ).fetchall()
            finally:
                con.close()
        if not rows:
            raise KeyError("conversation_thread_not_found")

        lines = [
            "Conversation context from the same thread:",
        ]
        for row in reversed(rows):
            turn_index = int(row["turn_index"] or 0)
            prior_question = _text_preview(_restore_text(str(row["question_text"] or "")) or "", max_len=280)
            prior_answer = (
                _restore_text(str(row["answer_text"] or ""))
                or _restore_text(str(row["answer_preview"] or ""))
                or _restore_text(str(row["error"] or ""))
            )
            prior_answer = _text_preview(prior_answer, max_len=360)
            lines.append(f"Turn {turn_index} user: {prior_question}")
            if prior_answer:
                lines.append(f"Turn {turn_index} assistant: {prior_answer}")
        lines.extend(
            [
                "",
                "Current follow-up question:",
                current_question,
                "",
                "Answer the current follow-up using retrieved corpus evidence. "
                "Use the history only as conversational context, not as source evidence.",
            ]
        )
        return "\n".join(lines)

    def _record_turn(
        self,
        *,
        thread_id: Optional[str],
        question: str,
        answer: str,
        mode: str,
        transport: str,
        actor: str,
        actor_source: str,
        actor_role: str,
        allowed_doc_tags: list[str],
        document_policy_source: str,
        status: str,
        latency_ms: Optional[float],
        chunks_used: int,
        source_count: int,
        source_paths: list[str],
        sources: list[dict[str, Any]],
        denied_hits: int,
        error: Optional[str],
    ) -> dict[str, Any]:
        question_text = _compact_text(question)
        question_preview = _text_preview(question_text)
        answer_text = str(answer or "")
        answer_preview = _text_preview(answer_text, max_len=280) if answer_text else None
        current = _now_iso()
        effective_thread_id = str(thread_id or "").strip()
        created_new = False

        with self._lock:
            con = self._connect()
            try:
                if effective_thread_id:
                    existing = con.execute(
                        """
                        SELECT title, created_at, created_by_actor, created_by_source, created_by_role
                        FROM conversation_threads
                        WHERE thread_id = ?
                        """,
                        (effective_thread_id,),
                    ).fetchone()
                    if existing is None:
                        raise KeyError("conversation_thread_not_found")
                    title = _restore_text(str(existing[0] or "")) or question_preview or "Conversation"
                    created_at = str(existing[1] or "") or current
                    created_by_actor = _restore_text(str(existing[2] or "")) or str(actor or "anonymous")
                    created_by_source = _restore_text(str(existing[3] or "")) or str(actor_source or "anonymous")
                    created_by_role = _restore_text(str(existing[4] or "")) or str(actor_role or "viewer")
                else:
                    effective_thread_id = uuid.uuid4().hex[:16]
                    title = question_preview or "Conversation"
                    created_at = current
                    created_by_actor = str(actor or "anonymous")
                    created_by_source = str(actor_source or "anonymous")
                    created_by_role = str(actor_role or "viewer")
                    created_new = True
                    con.execute(
                        """
                        INSERT INTO conversation_threads (
                            thread_id,
                            title,
                            created_at,
                            updated_at,
                            created_by_actor,
                            created_by_source,
                            created_by_role,
                            last_actor,
                            last_actor_source,
                            last_actor_role,
                            turn_count,
                            last_question_preview,
                            last_answer_preview,
                            last_mode,
                            last_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', NULL, '', '')
                        """,
                        (
                            effective_thread_id,
                            _protect_text(title),
                            created_at,
                            current,
                            _protect_text(created_by_actor),
                            _protect_text(created_by_source),
                            _protect_text(created_by_role),
                            _protect_text(str(actor or "anonymous")),
                            _protect_text(str(actor_source or "anonymous")),
                            _protect_text(str(actor_role or "viewer")),
                        ),
                    )

                turn_index = int(
                    con.execute(
                        """
                        SELECT COALESCE(MAX(turn_index), 0) + 1
                        FROM conversation_turns
                        WHERE thread_id = ?
                        """,
                        (effective_thread_id,),
                    ).fetchone()[0]
                    or 1
                )
                con.execute(
                    """
                    INSERT INTO conversation_turns (
                        thread_id,
                        turn_index,
                        created_at,
                        completed_at,
                        question_text,
                        question_preview,
                        answer_text,
                        answer_preview,
                        mode,
                        transport,
                        actor,
                        actor_source,
                        actor_role,
                        allowed_doc_tags_json,
                        document_policy_source,
                        status,
                        latency_ms,
                        chunks_used,
                        source_count,
                        source_paths_json,
                        sources_json,
                        denied_hits,
                        error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        effective_thread_id,
                        turn_index,
                        current,
                        current,
                        _protect_text(question_text),
                        _protect_text(question_preview),
                        _protect_text(answer_text) if answer_text else None,
                        _protect_text(answer_preview) if answer_preview else None,
                        _protect_text(str(mode or "")),
                        _protect_text(str(transport or "sync")),
                        _protect_text(str(actor or "anonymous")),
                        _protect_text(str(actor_source or "anonymous")),
                        _protect_text(str(actor_role or "viewer")),
                        _protect_text(json.dumps(list(allowed_doc_tags or []))),
                        _protect_text(str(document_policy_source or "")),
                        str(status or "completed"),
                        None if latency_ms is None else round(float(latency_ms), 2),
                        max(0, int(chunks_used or 0)),
                        max(0, int(source_count or 0)),
                        _protect_text(json.dumps(list(source_paths or []))),
                        _protect_text(json.dumps(list(sources or []))),
                        max(0, int(denied_hits or 0)),
                        _protect_text(error) if error else None,
                    ),
                )
                con.execute(
                    """
                    UPDATE conversation_threads
                    SET
                        title = ?,
                        updated_at = ?,
                        last_actor = ?,
                        last_actor_source = ?,
                        last_actor_role = ?,
                        turn_count = ?,
                        last_question_preview = ?,
                        last_answer_preview = ?,
                        last_mode = ?,
                        last_status = ?
                    WHERE thread_id = ?
                    """,
                    (
                        _protect_text(title),
                        current,
                        _protect_text(str(actor or "anonymous")),
                        _protect_text(str(actor_source or "anonymous")),
                        _protect_text(str(actor_role or "viewer")),
                        turn_index,
                        _protect_text(question_preview),
                        _protect_text(answer_preview) if answer_preview else None,
                        _protect_text(str(mode or "")),
                        str(status or "completed"),
                        effective_thread_id,
                    ),
                )
                self._apply_retention(con, effective_thread_id)
                con.commit()
            finally:
                con.close()

        return {
            "thread_id": effective_thread_id,
            "turn_index": turn_index,
            "thread_created": created_new,
        }

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        if history_secure_delete_enabled():
            con.execute("PRAGMA secure_delete = ON")
        if history_encryption_enabled():
            con.execute("PRAGMA temp_store = MEMORY")
        return con

    def _ensure_schema(self) -> None:
        with self._lock:
            con = self._connect()
            try:
                con.execute("PRAGMA journal_mode = WAL")
                con.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS conversation_threads (
                        thread_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        created_by_actor TEXT NOT NULL,
                        created_by_source TEXT NOT NULL,
                        created_by_role TEXT NOT NULL,
                        last_actor TEXT NOT NULL,
                        last_actor_source TEXT NOT NULL,
                        last_actor_role TEXT NOT NULL,
                        turn_count INTEGER NOT NULL DEFAULT 0,
                        last_question_preview TEXT NOT NULL DEFAULT '',
                        last_answer_preview TEXT,
                        last_mode TEXT NOT NULL DEFAULT '',
                        last_status TEXT NOT NULL DEFAULT ''
                    );
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        thread_id TEXT NOT NULL,
                        turn_index INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        question_text TEXT NOT NULL,
                        question_preview TEXT NOT NULL,
                        answer_text TEXT,
                        answer_preview TEXT,
                        mode TEXT NOT NULL,
                        transport TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        actor_source TEXT NOT NULL,
                        actor_role TEXT NOT NULL,
                        allowed_doc_tags_json TEXT NOT NULL,
                        document_policy_source TEXT NOT NULL,
                        status TEXT NOT NULL,
                        latency_ms REAL,
                        chunks_used INTEGER NOT NULL DEFAULT 0,
                        source_count INTEGER NOT NULL DEFAULT 0,
                        source_paths_json TEXT NOT NULL,
                        sources_json TEXT NOT NULL,
                        denied_hits INTEGER NOT NULL DEFAULT 0,
                        error TEXT,
                        PRIMARY KEY (thread_id, turn_index),
                        FOREIGN KEY (thread_id) REFERENCES conversation_threads(thread_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_conversation_threads_updated_at
                    ON conversation_threads(updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_conversation_turns_thread
                    ON conversation_turns(thread_id, turn_index);
                    """
                )
                con.commit()
                harden_history_storage_path(self.db_path)
            finally:
                con.close()

    def _rewrap_existing_rows(self) -> None:
        with self._lock:
            con = self._connect()
            try:
                thread_rows = con.execute(
                    """
                    SELECT
                        thread_id,
                        title,
                        created_by_actor,
                        created_by_source,
                        created_by_role,
                        last_actor,
                        last_actor_source,
                        last_actor_role,
                        last_question_preview,
                        last_answer_preview,
                        last_mode
                    FROM conversation_threads
                    """
                ).fetchall()
                for row in thread_rows:
                    con.execute(
                        """
                        UPDATE conversation_threads
                        SET
                            title = ?,
                            created_by_actor = ?,
                            created_by_source = ?,
                            created_by_role = ?,
                            last_actor = ?,
                            last_actor_source = ?,
                            last_actor_role = ?,
                            last_question_preview = ?,
                            last_answer_preview = ?,
                            last_mode = ?
                        WHERE thread_id = ?
                        """,
                        (
                            _rewrap_text(str(row["title"] or "")) or "",
                            _rewrap_text(str(row["created_by_actor"] or "")) or "",
                            _rewrap_text(str(row["created_by_source"] or "")) or "",
                            _rewrap_text(str(row["created_by_role"] or "")) or "",
                            _rewrap_text(str(row["last_actor"] or "")) or "",
                            _rewrap_text(str(row["last_actor_source"] or "")) or "",
                            _rewrap_text(str(row["last_actor_role"] or "")) or "",
                            _rewrap_text(str(row["last_question_preview"] or "")) or "",
                            _rewrap_text(
                                None if row["last_answer_preview"] is None else str(row["last_answer_preview"] or "")
                            ),
                            _rewrap_text(str(row["last_mode"] or "")) or "",
                            str(row["thread_id"] or ""),
                        ),
                    )

                turn_rows = con.execute(
                    """
                    SELECT
                        thread_id,
                        turn_index,
                        question_text,
                        question_preview,
                        answer_text,
                        answer_preview,
                        mode,
                        transport,
                        actor,
                        actor_source,
                        actor_role,
                        allowed_doc_tags_json,
                        document_policy_source,
                        source_paths_json,
                        sources_json,
                        error
                    FROM conversation_turns
                    """
                ).fetchall()
                for row in turn_rows:
                    con.execute(
                        """
                        UPDATE conversation_turns
                        SET
                            question_text = ?,
                            question_preview = ?,
                            answer_text = ?,
                            answer_preview = ?,
                            mode = ?,
                            transport = ?,
                            actor = ?,
                            actor_source = ?,
                            actor_role = ?,
                            allowed_doc_tags_json = ?,
                            document_policy_source = ?,
                            source_paths_json = ?,
                            sources_json = ?,
                            error = ?
                        WHERE thread_id = ? AND turn_index = ?
                        """,
                        (
                            _rewrap_text(str(row["question_text"] or "")) or "",
                            _rewrap_text(str(row["question_preview"] or "")) or "",
                            _rewrap_text(None if row["answer_text"] is None else str(row["answer_text"] or "")),
                            _rewrap_text(None if row["answer_preview"] is None else str(row["answer_preview"] or "")),
                            _rewrap_text(str(row["mode"] or "")) or "",
                            _rewrap_text(str(row["transport"] or "")) or "",
                            _rewrap_text(str(row["actor"] or "")) or "",
                            _rewrap_text(str(row["actor_source"] or "")) or "",
                            _rewrap_text(str(row["actor_role"] or "")) or "",
                            _rewrap_text(str(row["allowed_doc_tags_json"] or "")) or "[]",
                            _rewrap_text(str(row["document_policy_source"] or "")) or "",
                            _rewrap_text(str(row["source_paths_json"] or "")) or "[]",
                            _rewrap_text(str(row["sources_json"] or "")) or "[]",
                            _rewrap_text(None if row["error"] is None else str(row["error"] or "")),
                            str(row["thread_id"] or ""),
                            int(row["turn_index"] or 0),
                        ),
                    )
                con.commit()
                harden_history_storage_path(self.db_path)
            finally:
                con.close()

    def _apply_retention(self, con: sqlite3.Connection, thread_id: str) -> None:
        if self.max_turns_per_thread > 0:
            con.execute(
                """
                DELETE FROM conversation_turns
                WHERE thread_id = ?
                  AND turn_index NOT IN (
                      SELECT turn_index
                      FROM conversation_turns
                      WHERE thread_id = ?
                      ORDER BY turn_index DESC
                      LIMIT ?
                  )
                """,
                (
                    thread_id,
                    thread_id,
                    self.max_turns_per_thread,
                ),
            )
            self._refresh_thread_summary(con, thread_id)

        if self.max_threads > 0:
            stale_rows = con.execute(
                """
                SELECT thread_id
                FROM conversation_threads
                ORDER BY updated_at DESC, created_at DESC
                LIMIT -1 OFFSET ?
                """,
                (self.max_threads,),
            ).fetchall()
            if stale_rows:
                con.executemany(
                    "DELETE FROM conversation_threads WHERE thread_id = ?",
                    [(str(row["thread_id"] or ""),) for row in stale_rows],
                )

    def _refresh_thread_summary(self, con: sqlite3.Connection, thread_id: str) -> None:
        count_row = con.execute(
            "SELECT COUNT(*) AS count FROM conversation_turns WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        turn_count = int(count_row["count"] or 0)
        if turn_count <= 0:
            con.execute(
                "DELETE FROM conversation_threads WHERE thread_id = ?",
                (thread_id,),
            )
            return

        latest = con.execute(
            """
            SELECT
                completed_at,
                question_preview,
                answer_preview,
                mode,
                status,
                actor,
                actor_source,
                actor_role
            FROM conversation_turns
            WHERE thread_id = ?
            ORDER BY turn_index DESC
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        if latest is None:
            return

        con.execute(
            """
            UPDATE conversation_threads
            SET
                updated_at = ?,
                last_actor = ?,
                last_actor_source = ?,
                last_actor_role = ?,
                turn_count = ?,
                last_question_preview = ?,
                last_answer_preview = ?,
                last_mode = ?,
                last_status = ?
            WHERE thread_id = ?
            """,
            (
                str(latest["completed_at"] or _now_iso()),
                _protect_text(str(latest["actor"] or "")) or "",
                _protect_text(str(latest["actor_source"] or "")) or "",
                _protect_text(str(latest["actor_role"] or "")) or "",
                turn_count,
                _protect_text(str(latest["question_preview"] or "")) or "",
                _protect_text(str(latest["answer_preview"] or "")) or None,
                _protect_text(str(latest["mode"] or "")) or "",
                str(latest["status"] or ""),
                thread_id,
            ),
        )

    @staticmethod
    def _thread_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "thread_id": str(row["thread_id"] or ""),
            "title": _restore_text(str(row["title"] or "")) or "",
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "created_by_actor": _restore_text(str(row["created_by_actor"] or "")) or "",
            "created_by_source": _restore_text(str(row["created_by_source"] or "")) or "",
            "created_by_role": _restore_text(str(row["created_by_role"] or "")) or "",
            "last_actor": _restore_text(str(row["last_actor"] or "")) or "",
            "last_actor_source": _restore_text(str(row["last_actor_source"] or "")) or "",
            "last_actor_role": _restore_text(str(row["last_actor_role"] or "")) or "",
            "turn_count": int(row["turn_count"] or 0),
            "last_question_preview": _restore_text(str(row["last_question_preview"] or "")) or "",
            "last_answer_preview": _restore_text(str(row["last_answer_preview"] or "")) or None,
            "last_mode": _restore_text(str(row["last_mode"] or "")) or "",
            "last_status": str(row["last_status"] or ""),
        }

    @staticmethod
    def _turn_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "thread_id": str(row["thread_id"] or ""),
            "turn_index": int(row["turn_index"] or 0),
            "created_at": str(row["created_at"] or ""),
            "completed_at": str(row["completed_at"] or "") or None,
            "question_text": _restore_text(str(row["question_text"] or "")) or "",
            "question_preview": _restore_text(str(row["question_preview"] or "")) or "",
            "answer_text": _restore_text(str(row["answer_text"] or "")) or None,
            "answer_preview": _restore_text(str(row["answer_preview"] or "")) or None,
            "mode": _restore_text(str(row["mode"] or "")) or "",
            "transport": _restore_text(str(row["transport"] or "")) or "",
            "actor": _restore_text(str(row["actor"] or "")) or "",
            "actor_source": _restore_text(str(row["actor_source"] or "")) or "",
            "actor_role": _restore_text(str(row["actor_role"] or "")) or "",
            "allowed_doc_tags": _load_protected_json(str(row["allowed_doc_tags_json"] or "[]"), []),
            "document_policy_source": _restore_text(str(row["document_policy_source"] or "")) or "",
            "status": str(row["status"] or ""),
            "latency_ms": None if row["latency_ms"] is None else float(row["latency_ms"]),
            "chunks_used": int(row["chunks_used"] or 0),
            "source_count": int(row["source_count"] or 0),
            "source_paths": _load_protected_json(str(row["source_paths_json"] or "[]"), []),
            "sources": _load_protected_json(str(row["sources_json"] or "[]"), []),
            "denied_hits": int(row["denied_hits"] or 0),
            "error": _restore_text(str(row["error"] or "")) or None,
        }
