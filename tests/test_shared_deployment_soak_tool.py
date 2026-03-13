from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.tools.shared_deployment_soak import (
    JsonHttpResponse,
    build_request_headers,
    format_soak_console_summary,
    load_soak_questions,
    run_shared_deployment_soak,
    summarize_soak_results,
    write_shared_soak_report,
)


def test_load_soak_questions_reads_text_file_and_skips_comments(tmp_path):
    path = tmp_path / "questions.txt"
    path.write_text(
        "# comment\nWhat changed in the latest index?\n\nShow queue status.\n",
        encoding="utf-8",
    )

    questions = load_soak_questions(path)

    assert questions == [
        "What changed in the latest index?",
        "Show queue status.",
    ]


def test_load_soak_questions_reads_demo_pack_prompts_from_json(tmp_path):
    path = tmp_path / "pack.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {"id": "one", "prompt": "How do leaders and managers differ?"},
                    {"id": "two", "prompt": "What is the calibration review cadence?"},
                    {"id": "three", "title": "ignored without prompt"},
                ]
            }
        ),
        encoding="utf-8",
    )

    questions = load_soak_questions(path)

    assert questions == [
        "How do leaders and managers differ?",
        "What is the calibration review cadence?",
    ]


def test_build_request_headers_supports_auth_and_proxy_identity():
    headers = build_request_headers(
        auth_token="shared-token",
        proxy_user_header="X-Forwarded-User",
        proxy_user_value="soak-user-01",
        proxy_identity_secret="proxy-secret",
        extra_headers={"X-Test": "1"},
    )

    assert headers["Authorization"] == "Bearer shared-token"
    assert headers["X-Forwarded-User"] == "soak-user-01"
    assert headers["X-HybridRAG-Proxy-Secret"] == "proxy-secret"
    assert headers["X-Test"] == "1"


def test_summarize_soak_results_computes_latency_and_queue_peaks():
    summary = summarize_soak_results(
        [
            {
                "ok": True,
                "status_code": 200,
                "client_latency_ms": 100.0,
                "server_latency_ms": 90.0,
                "mode": "online",
                "error": None,
            },
            {
                "ok": False,
                "status_code": 503,
                "client_latency_ms": 250.0,
                "server_latency_ms": None,
                "mode": "",
                "error": "Query queue is full. Retry later.",
            },
        ],
        queue_samples=[
            {
                "snapshot": {
                    "active_queries": 2,
                    "waiting_queries": 1,
                    "total_rejected": 0,
                    "max_waiting_seen": 1,
                }
            },
            {
                "snapshot": {
                    "active_queries": 3,
                    "waiting_queries": 2,
                    "total_rejected": 1,
                    "max_waiting_seen": 2,
                }
            },
        ],
    )

    assert summary["total_requests"] == 2
    assert summary["successful_requests"] == 1
    assert summary["failed_requests"] == 1
    assert summary["http_error_responses"] == 1
    assert summary["client_latency_ms"]["p50"] == 175.0
    assert summary["server_latency_ms"]["max"] == 90.0
    assert summary["modes"] == {"online": 1}
    assert summary["errors"]["Query queue is full. Retry later."] == 1
    assert summary["queue"]["peak_active_queries"] == 3
    assert summary["queue"]["peak_waiting_queries"] == 2
    assert summary["queue"]["peak_total_rejected"] == 1


def test_write_shared_soak_report_uses_timestamped_name(tmp_path):
    report = {
        "ok": True,
        "summary": {"total_requests": 2},
    }

    path = write_shared_soak_report(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 13, 6, 30, 0),
    )

    assert path.name == "2026-03-13_063000_shared_deployment_soak.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_requests"] == 2


def test_run_shared_deployment_soak_captures_preflight_and_results():
    queue_calls = [0]

    def fake_fetcher(base_url, path, *, method="GET", headers=None, payload=None, timeout_seconds=0):
        assert base_url == "http://127.0.0.1:8000"
        if path == "/health":
            return JsonHttpResponse(200, {"status": "ok", "version": "3.1.0"})
        if path == "/status":
            return JsonHttpResponse(
                200,
                {
                    "status": "ok",
                    "mode": "online",
                    "query_queue": {"active_queries": 0, "waiting_queries": 0},
                },
            )
        if path == "/auth/context":
            return JsonHttpResponse(
                200,
                {
                    "auth_required": False,
                    "auth_mode": "open",
                    "actor": "anonymous",
                },
            )
        if path == "/activity/query-queue":
            queue_calls[0] += 1
            return JsonHttpResponse(
                200,
                {
                    "active_queries": 0,
                    "waiting_queries": 0,
                    "total_rejected": 0,
                    "max_waiting_seen": 0,
                },
            )
        if path == "/activity/queries":
            return JsonHttpResponse(
                200,
                {
                    "active_queries": 0,
                    "total_completed": 2,
                    "total_failed": 0,
                    "active": [],
                    "recent": [],
                },
            )
        if path == "/query":
            return JsonHttpResponse(
                200,
                {
                    "answer": "ok",
                    "sources": [{"path": r"D:\Corpus\Leadership.pdf"}],
                    "chunks_used": 1,
                    "tokens_in": 10,
                    "tokens_out": 20,
                    "cost_usd": 0.0,
                    "latency_ms": 45.0,
                    "mode": "online",
                    "error": None,
                },
            )
        raise AssertionError("unexpected path: {}".format(path))

    report = run_shared_deployment_soak(
        base_url="http://127.0.0.1:8000",
        questions=["How do leaders and managers differ?", "What changed in the latest run?"],
        concurrency=2,
        rounds=1,
        timeout_seconds=15.0,
        poll_interval_seconds=0.0,
        fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    assert report["target"]["health"]["status_code"] == 200
    assert report["target"]["auth_context"]["payload"]["auth_mode"] == "open"
    assert report["summary"]["total_requests"] == 2
    assert report["summary"]["successful_requests"] == 2
    assert report["summary"]["server_latency_ms"]["p50"] == 45.0
    assert report["post_run"]["query_activity"]["payload"]["total_completed"] == 2
    assert queue_calls[0] == 2
    assert len(report["requests"]) == 2
    assert all(item["mode"] == "online" for item in report["requests"])


def test_format_soak_console_summary_mentions_request_and_queue_totals():
    summary = format_soak_console_summary(
        {
            "target": {"base_url": "http://127.0.0.1:8000"},
            "summary": {
                "total_requests": 4,
                "successful_requests": 3,
                "client_latency_ms": {"p50": 120.0, "p95": 180.0, "max": 200.0},
                "server_latency_ms": {"p50": 90.0, "p95": 140.0, "max": 160.0},
                "queue": {
                    "peak_active_queries": 2,
                    "peak_waiting_queries": 1,
                    "peak_total_rejected": 0,
                },
                "errors": {"Query queue is full. Retry later.": 1},
            },
        }
    )

    assert "Requests: 3/4 successful" in summary
    assert "Queue peak: active=2 waiting=1 rejected=0" in summary
    assert "Errors:" in summary


def test_run_shared_deployment_soak_hits_live_fastapi_surfaces_in_process(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    from src.api.server import app, state
    from src.api.query_queue import QueryQueueTracker
    from src.core.query_engine import QueryResult

    original_mode = None
    original_query = None

    with fastapi_testclient.TestClient(app) as client:
        if state.query_activity is not None:
            state.query_activity.reset()
        state.query_queue = QueryQueueTracker(max_concurrent=2, max_queue=4)
        state.query_queue.reset()

        original_mode = state.config.mode
        original_query = state.query_engine.query
        monkeypatch.setattr(state.config, "mode", "online")
        state.query_engine.query = lambda question: QueryResult(
            answer="answer for {}".format(question),
            sources=[{"path": r"D:\Corpus\Leadership.pdf"}],
            chunks_used=1,
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.01,
            latency_ms=12.5,
            mode="online",
            error=None,
        )

        def client_fetcher(base_url, path, *, method="GET", headers=None, payload=None, timeout_seconds=0):
            assert base_url == "http://testserver"
            if method == "POST":
                response = client.post(path, json=payload, headers=headers)
            else:
                response = client.get(path, headers=headers)
            return JsonHttpResponse(response.status_code, response.json())

        try:
            report = run_shared_deployment_soak(
                base_url="http://testserver",
                questions=["How do leaders and managers differ?"],
                concurrency=1,
                rounds=2,
                timeout_seconds=10.0,
                poll_interval_seconds=0.0,
                fetcher=client_fetcher,
            )

            assert report["ok"] is True
            assert report["summary"]["successful_requests"] == 2
            assert report["post_run"]["query_activity"]["payload"]["total_completed"] == 2
            assert report["post_run"]["query_queue"]["payload"]["total_completed"] == 2
            assert report["requests"][0]["mode"] == "online"
        finally:
            if original_query is not None:
                state.query_engine.query = original_query
            if original_mode is not None:
                state.config.mode = original_mode
