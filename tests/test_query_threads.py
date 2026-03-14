import sqlite3

from src.api.query_threads import ConversationThreadStore
from src.security.protected_data import HISTORY_PROTECTED_PREFIX, restore_history_text


class _Result:
    def __init__(self, *, answer: str, mode: str = "online") -> None:
        self.answer = answer
        self.sources = []
        self.chunks_used = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.latency_ms = 1.0
        self.mode = mode
        self.error = None
        self.debug_trace = {}


def test_store_prunes_old_threads_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HYBRIDRAG_HISTORY_MAX_THREADS", "2")
    monkeypatch.setenv("HYBRIDRAG_HISTORY_MAX_TURNS_PER_THREAD", "10")
    store = ConversationThreadStore(str(tmp_path / "history.sqlite3"))

    first = store.record_completed_turn(
        thread_id=None,
        question="first",
        result=_Result(answer="a1"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )
    second = store.record_completed_turn(
        thread_id=None,
        question="second",
        result=_Result(answer="a2"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )
    third = store.record_completed_turn(
        thread_id=None,
        question="third",
        result=_Result(answer="a3"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )

    listing = store.list_threads(limit=10)
    ids = [item["thread_id"] for item in listing["threads"]]
    assert first["thread_id"] not in ids
    assert second["thread_id"] in ids
    assert third["thread_id"] in ids
    assert listing["total_threads"] == 2
    assert listing["max_threads"] == 2
    assert listing["max_turns_per_thread"] == 10


def test_store_prunes_old_turns_per_thread_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HYBRIDRAG_HISTORY_MAX_THREADS", "10")
    monkeypatch.setenv("HYBRIDRAG_HISTORY_MAX_TURNS_PER_THREAD", "2")
    store = ConversationThreadStore(str(tmp_path / "history.sqlite3"))

    first = store.record_completed_turn(
        thread_id=None,
        question="first",
        result=_Result(answer="a1"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )
    thread_id = first["thread_id"]
    store.record_completed_turn(
        thread_id=thread_id,
        question="second",
        result=_Result(answer="a2"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )
    store.record_completed_turn(
        thread_id=thread_id,
        question="third",
        result=_Result(answer="a3"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )

    detail = store.get_thread(thread_id)
    assert detail is not None
    turns = detail["turns"]
    assert [turn["question_text"] for turn in turns] == ["second", "third"]
    assert detail["thread"]["turn_count"] == 2
    listing = store.list_threads(limit=10)
    assert listing["max_threads"] == 10
    assert listing["max_turns_per_thread"] == 2


def test_store_encrypts_history_fields_when_key_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-secret")
    db_path = tmp_path / "history.sqlite3"
    store = ConversationThreadStore(str(db_path))

    saved = store.record_completed_turn(
        thread_id=None,
        question="first",
        result=_Result(answer="a1"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )

    con = sqlite3.connect(str(db_path))
    try:
        thread_row = con.execute(
            """
            SELECT title, created_by_actor, last_question_preview
            FROM conversation_threads
            WHERE thread_id = ?
            """,
            (saved["thread_id"],),
        ).fetchone()
        turn_row = con.execute(
            """
            SELECT question_text, answer_text, source_paths_json, sources_json
            FROM conversation_turns
            WHERE thread_id = ? AND turn_index = 1
            """,
            (saved["thread_id"],),
        ).fetchone()
    finally:
        con.close()

    assert thread_row is not None
    assert turn_row is not None
    assert all(str(value or "").startswith(HISTORY_PROTECTED_PREFIX) for value in thread_row)
    assert str(turn_row[0]).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(turn_row[1]).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(turn_row[2]).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(turn_row[3]).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(turn_row[0]) != "first"
    assert str(turn_row[1]) != "a1"
    assert restore_history_text(str(turn_row[0])) == "first"
    assert restore_history_text(str(turn_row[1])) == "a1"
    con = store._connect()
    try:
        secure_delete = con.execute("PRAGMA secure_delete").fetchone()[0]
    finally:
        con.close()
    assert secure_delete == 1

    detail = store.get_thread(saved["thread_id"])
    assert detail is not None
    assert detail["thread"]["title"] == "first"
    assert detail["thread"]["created_by_actor"] == "alice"
    assert detail["turns"][0]["question_text"] == "first"
    assert detail["turns"][0]["answer_text"] == "a1"


def test_store_reads_encrypted_history_after_key_rotation(monkeypatch, tmp_path):
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-old")
    store = ConversationThreadStore(str(db_path))
    saved = store.record_completed_turn(
        thread_id=None,
        question="rotation question",
        result=_Result(answer="rotation answer"),
        transport="sync",
        actor="alice",
        actor_source="session",
        actor_role="viewer",
        allowed_doc_tags=["shared"],
        document_policy_source="default",
    )
    con = sqlite3.connect(str(db_path))
    try:
        old_cipher = con.execute(
            """
            SELECT question_text
            FROM conversation_turns
            WHERE thread_id = ? AND turn_index = 1
            """,
            (saved["thread_id"],),
        ).fetchone()[0]
    finally:
        con.close()

    monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY", "history-new")
    monkeypatch.setenv("HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS", "history-old")
    rotated = ConversationThreadStore(str(db_path))
    con = sqlite3.connect(str(db_path))
    try:
        new_cipher = con.execute(
            """
            SELECT question_text
            FROM conversation_turns
            WHERE thread_id = ? AND turn_index = 1
            """,
            (saved["thread_id"],),
        ).fetchone()[0]
    finally:
        con.close()

    detail = rotated.get_thread(saved["thread_id"])
    assert detail is not None
    assert str(old_cipher).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(new_cipher).startswith(HISTORY_PROTECTED_PREFIX)
    assert str(new_cipher) != str(old_cipher)
    assert detail["turns"][0]["question_text"] == "rotation question"
    assert detail["turns"][0]["answer_text"] == "rotation answer"

    follow_up = rotated.build_follow_up_query(saved["thread_id"], "what changed next?")
    assert "rotation question" in follow_up
    assert "rotation answer" in follow_up
