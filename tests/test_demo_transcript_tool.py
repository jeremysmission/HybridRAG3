from types import SimpleNamespace

from tools import demo_transcript


def test_online_query_ready_requires_key_and_endpoint():
    assert demo_transcript._online_query_ready(None) is False
    assert demo_transcript._online_query_ready(
        SimpleNamespace(has_key=False, endpoint="https://example.test")
    ) is False
    assert demo_transcript._online_query_ready(
        SimpleNamespace(has_key=True, endpoint="")
    ) is False
    assert demo_transcript._online_query_ready(
        SimpleNamespace(has_key=True, endpoint="https://example.test")
    ) is True


def test_result_has_error_detects_error_field_and_error_answer():
    assert demo_transcript._result_has_error(None) is True
    assert demo_transcript._result_has_error(
        SimpleNamespace(answer="ok", error="boom")
    ) is True
    assert demo_transcript._result_has_error(
        SimpleNamespace(answer="Error processing query: LLM call failed", error="")
    ) is True
    assert demo_transcript._result_has_error(
        SimpleNamespace(answer="Leadership styles differ in emphasis.", error="")
    ) is False


def test_build_operator_notes_emits_skip_prefix():
    notes = demo_transcript._build_operator_notes(
        [{"step": "Query/Online", "detail": "online credentials not configured", "ok": None, "status": "skip"}],
        [],
    )

    assert notes == ["SKIP: Query/Online -- online credentials not configured"]
