from types import SimpleNamespace

from src.gui.panels.query_panel_query_render_runtime import (
    _grounding_status_banner,
)


def _theme():
    return {
        "green": "green",
        "orange": "orange",
        "red": "red",
        "gray": "gray",
    }


def test_grounding_status_banner_marks_open_knowledge_fallback_unverified():
    result = SimpleNamespace(
        grounding_score=-1.0,
        grounding_blocked=False,
        grounding_details={
            "verification": "skipped",
            "fallback_mode": "open_knowledge",
        },
    )

    text, color = _grounding_status_banner(result, _theme())

    assert text == "Grounding: UNVERIFIED (open-knowledge fallback)"
    assert color == "orange"


def test_grounding_status_banner_keeps_verified_scores_visible():
    result = SimpleNamespace(
        grounding_score=0.84,
        grounding_blocked=False,
        grounding_details={"claims": []},
    )

    text, color = _grounding_status_banner(result, _theme())

    assert text == "Grounding: 84% verified"
    assert color == "green"


def test_grounding_status_banner_reports_blocked_even_without_nonnegative_score():
    result = SimpleNamespace(
        grounding_score=-1.0,
        grounding_blocked=True,
        grounding_details={"reason": "no_search_results"},
    )

    text, color = _grounding_status_banner(result, _theme())

    assert text == "Grounding: BLOCKED (score n/a)"
    assert color == "red"
