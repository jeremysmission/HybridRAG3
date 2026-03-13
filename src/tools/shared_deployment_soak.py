from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Sequence
from urllib import error, request


@dataclass(frozen=True)
class JsonHttpResponse:
    """Minimal JSON HTTP response wrapper for soak-tool requests."""

    status_code: int
    payload: dict[str, Any]


FetchJson = Callable[..., JsonHttpResponse]


def default_shared_soak_report_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "output" / "shared_soak"


def load_soak_questions(path: str | Path) -> list[str]:
    source = Path(path).expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        payload = json.loads(text)
        questions = _questions_from_json(payload)
    else:
        questions = _questions_from_text(text)
    if not questions:
        raise ValueError("No soak questions were found in {}".format(source))
    return questions


def build_request_headers(
    *,
    auth_token: str = "",
    proxy_user_header: str = "",
    proxy_user_value: str = "",
    proxy_identity_secret: str = "",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    token = str(auth_token or "").strip()
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    proxy_header = str(proxy_user_header or "").strip()
    proxy_value = str(proxy_user_value or "").strip()
    if proxy_header and proxy_value:
        headers[proxy_header] = proxy_value
    proxy_secret = str(proxy_identity_secret or "").strip()
    if proxy_secret:
        headers["X-HybridRAG-Proxy-Secret"] = proxy_secret
    if extra_headers:
        for key, value in extra_headers.items():
            normalized_key = str(key or "").strip()
            normalized_value = str(value or "").strip()
            if normalized_key and normalized_value:
                headers[normalized_key] = normalized_value
    return headers


def fetch_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> JsonHttpResponse:
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    target = "{}{}".format(_normalize_base_url(base_url), path)
    req = request.Request(
        target,
        data=body,
        method=str(method or "GET").upper(),
        headers=dict(headers or {}),
    )
    try:
        with request.urlopen(req, timeout=float(timeout_seconds)) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return JsonHttpResponse(
                status_code=int(getattr(response, "status", 200) or 200),
                payload=_parse_json_payload(raw),
            )
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return JsonHttpResponse(
            status_code=int(getattr(exc, "code", 500) or 500),
            payload=_parse_json_payload(raw),
        )


def run_shared_deployment_soak(
    *,
    base_url: str,
    questions: Sequence[str],
    concurrency: int = 4,
    rounds: int = 1,
    timeout_seconds: float = 60.0,
    auth_token: str = "",
    proxy_user_header: str = "",
    proxy_identity_secret: str = "",
    poll_interval_seconds: float = 0.5,
    extra_headers: dict[str, str] | None = None,
    fetcher: FetchJson = fetch_json,
) -> dict[str, Any]:
    prompts = [str(item or "").strip() for item in questions if str(item or "").strip()]
    if not prompts:
        raise ValueError("At least one soak question is required")

    total_requests = len(prompts) * max(1, int(rounds or 1))
    worker_count = max(1, min(int(concurrency or 1), total_requests))

    preflight_health = _safe_fetch(
        fetcher,
        base_url,
        "/health",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )
    preflight_status = _safe_fetch(
        fetcher,
        base_url,
        "/status",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )
    preflight_auth = _safe_fetch(
        fetcher,
        base_url,
        "/auth/context",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )
    initial_queue = _safe_fetch(
        fetcher,
        base_url,
        "/activity/query-queue",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )

    queue_samples: list[dict[str, Any]] = []
    poll_stop = threading.Event()
    monitor_thread: threading.Thread | None = None
    if poll_interval_seconds > 0:
        monitor_thread = threading.Thread(
            target=_queue_poll_loop,
            kwargs={
                "samples": queue_samples,
                "stop_event": poll_stop,
                "fetcher": fetcher,
                "base_url": base_url,
                "auth_token": auth_token,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
                "extra_headers": extra_headers,
            },
            daemon=True,
        )
        monitor_thread.start()

    scheduled = [
        prompts[index % len(prompts)]
        for index in range(total_requests)
    ]
    results: list[dict[str, Any]] = []
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = []
            for index, prompt in enumerate(scheduled, start=1):
                proxy_user_value = ""
                if proxy_user_header:
                    proxy_user_value = "soak-user-{:02d}".format(
                        ((index - 1) % worker_count) + 1
                    )
                futures.append(
                    pool.submit(
                        _run_one_query,
                        fetcher,
                        base_url,
                        prompt,
                        request_id="req-{:04d}".format(index),
                        timeout_seconds=timeout_seconds,
                        auth_token=auth_token,
                        proxy_user_header=proxy_user_header,
                        proxy_user_value=proxy_user_value,
                        proxy_identity_secret=proxy_identity_secret,
                        extra_headers=extra_headers,
                    )
                )
            for future in as_completed(futures):
                results.append(future.result())
    finally:
        poll_stop.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=max(1.0, poll_interval_seconds * 4.0))

    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    final_status = _safe_fetch(
        fetcher,
        base_url,
        "/status",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )
    final_queue = _safe_fetch(
        fetcher,
        base_url,
        "/activity/query-queue",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )
    final_activity = _safe_fetch(
        fetcher,
        base_url,
        "/activity/queries",
        timeout_seconds=timeout_seconds,
        headers=build_request_headers(
            auth_token=auth_token,
            extra_headers=extra_headers,
        ),
    )

    summary = summarize_soak_results(results, queue_samples=queue_samples)
    report = {
        "ok": summary["failed_requests"] == 0,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": {
            "started_at": started_at,
            "finished_at": finished_at,
        },
        "target": {
            "base_url": _normalize_base_url(base_url),
            "health": _response_record(preflight_health),
            "status": _response_record(preflight_status),
            "auth_context": _response_record(preflight_auth),
        },
        "config": {
            "concurrency": worker_count,
            "rounds": max(1, int(rounds or 1)),
            "question_count": len(prompts),
            "total_requests": total_requests,
            "timeout_seconds": float(timeout_seconds),
            "poll_interval_seconds": float(poll_interval_seconds),
            "proxy_user_header": str(proxy_user_header or ""),
            "proxy_identity_secret_configured": bool(
                str(proxy_identity_secret or "").strip()
            ),
        },
        "questions": [
            {
                "index": index + 1,
                "prompt": prompt,
            }
            for index, prompt in enumerate(prompts)
        ],
        "summary": summary,
        "requests": sorted(results, key=lambda item: str(item.get("request_id", ""))),
        "queue_samples": list(queue_samples),
        "post_run": {
            "status": _response_record(final_status),
            "query_queue": _response_record(final_queue),
            "query_activity": _response_record(final_activity),
            "initial_queue": _response_record(initial_queue),
        },
    }
    return report


def summarize_soak_results(
    results: Sequence[dict[str, Any]],
    *,
    queue_samples: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entries = [dict(item) for item in results]
    client_latencies = [
        float(item["client_latency_ms"])
        for item in entries
        if item.get("client_latency_ms") is not None
    ]
    server_latencies = [
        float(item["server_latency_ms"])
        for item in entries
        if item.get("server_latency_ms") is not None
    ]
    success_count = sum(1 for item in entries if item.get("ok"))
    failure_count = len(entries) - success_count
    http_errors = sum(
        1
        for item in entries
        if int(item.get("status_code", 0) or 0) >= 400
    )
    mode_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for item in entries:
        mode = str(item.get("mode", "") or "").strip()
        if mode:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        error_text = str(item.get("error", "") or "").strip()
        if error_text:
            error_counts[error_text] = error_counts.get(error_text, 0) + 1

    queue_snapshots = [
        dict(item.get("snapshot", {}))
        for item in (queue_samples or [])
        if isinstance(item.get("snapshot", {}), dict)
    ]
    peak_active = max(
        [int(item.get("active_queries", 0) or 0) for item in queue_snapshots] or [0]
    )
    peak_waiting = max(
        [int(item.get("waiting_queries", 0) or 0) for item in queue_snapshots] or [0]
    )
    peak_rejected = max(
        [int(item.get("total_rejected", 0) or 0) for item in queue_snapshots] or [0]
    )
    peak_waiting_seen = max(
        [int(item.get("max_waiting_seen", 0) or 0) for item in queue_snapshots] or [0]
    )

    return {
        "total_requests": len(entries),
        "successful_requests": success_count,
        "failed_requests": failure_count,
        "http_error_responses": http_errors,
        "client_latency_ms": _latency_summary(client_latencies),
        "server_latency_ms": _latency_summary(server_latencies),
        "modes": mode_counts,
        "errors": error_counts,
        "queue": {
            "sample_count": len(queue_snapshots),
            "peak_active_queries": peak_active,
            "peak_waiting_queries": peak_waiting,
            "peak_total_rejected": peak_rejected,
            "peak_max_waiting_seen": peak_waiting_seen,
        },
    }


def write_shared_soak_report(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    report_dir = default_shared_soak_report_dir(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    path = report_dir / "{}_shared_deployment_soak.json".format(stamp)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def format_soak_console_summary(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary", {}) or {})
    client = dict(summary.get("client_latency_ms", {}) or {})
    server = dict(summary.get("server_latency_ms", {}) or {})
    queue = dict(summary.get("queue", {}) or {})
    lines = [
        "HYBRIDRAG SHARED DEPLOYMENT SOAK",
        "Target: {}".format(
            str(
                ((report.get("target") or {}).get("base_url"))
                or ""
            )
        ),
        "Requests: {}/{} successful".format(
            int(summary.get("successful_requests", 0) or 0),
            int(summary.get("total_requests", 0) or 0),
        ),
        "Client latency ms: p50={:.1f} p95={:.1f} max={:.1f}".format(
            float(client.get("p50", 0.0) or 0.0),
            float(client.get("p95", 0.0) or 0.0),
            float(client.get("max", 0.0) or 0.0),
        ),
        "Server latency ms: p50={:.1f} p95={:.1f} max={:.1f}".format(
            float(server.get("p50", 0.0) or 0.0),
            float(server.get("p95", 0.0) or 0.0),
            float(server.get("max", 0.0) or 0.0),
        ),
        "Queue peak: active={} waiting={} rejected={}".format(
            int(queue.get("peak_active_queries", 0) or 0),
            int(queue.get("peak_waiting_queries", 0) or 0),
            int(queue.get("peak_total_rejected", 0) or 0),
        ),
    ]
    errors = dict(summary.get("errors", {}) or {})
    if errors:
        lines.append("Errors: {}".format(json.dumps(errors, sort_keys=True)))
    return "\n".join(lines)


def _run_one_query(
    fetcher: FetchJson,
    base_url: str,
    prompt: str,
    *,
    request_id: str,
    timeout_seconds: float,
    auth_token: str,
    proxy_user_header: str,
    proxy_user_value: str,
    proxy_identity_secret: str,
    extra_headers: dict[str, str] | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    response = _safe_fetch(
        fetcher,
        base_url,
        "/query",
        method="POST",
        headers=build_request_headers(
            auth_token=auth_token,
            proxy_user_header=proxy_user_header,
            proxy_user_value=proxy_user_value,
            proxy_identity_secret=proxy_identity_secret,
            extra_headers=extra_headers,
        ),
        payload={"question": prompt},
        timeout_seconds=timeout_seconds,
    )
    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    client_latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    payload = dict(response.payload or {})
    server_latency = payload.get("latency_ms")
    if server_latency is not None:
        server_latency = round(float(server_latency), 2)
    error_text = str(payload.get("error", "") or payload.get("detail", "") or "").strip()
    ok = int(response.status_code or 0) < 400 and not error_text
    return {
        "request_id": request_id,
        "question": prompt,
        "question_preview": _preview_text(prompt, 120),
        "proxy_user": proxy_user_value or None,
        "status_code": int(response.status_code or 0),
        "ok": ok,
        "client_latency_ms": client_latency_ms,
        "server_latency_ms": server_latency,
        "chunks_used": int(payload.get("chunks_used", 0) or 0),
        "source_count": len(list(payload.get("sources", []) or [])),
        "mode": str(payload.get("mode", "") or ""),
        "error": error_text or None,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _queue_poll_loop(
    *,
    samples: list[dict[str, Any]],
    stop_event: threading.Event,
    fetcher: FetchJson,
    base_url: str,
    auth_token: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    extra_headers: dict[str, str] | None,
) -> None:
    while not stop_event.is_set():
        response = _safe_fetch(
            fetcher,
            base_url,
            "/activity/query-queue",
            timeout_seconds=timeout_seconds,
            headers=build_request_headers(
                auth_token=auth_token,
                extra_headers=extra_headers,
            ),
        )
        samples.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status_code": int(response.status_code or 0),
                "snapshot": dict(response.payload or {}),
            }
        )
        if stop_event.wait(poll_interval_seconds):
            break


def _safe_fetch(
    fetcher: FetchJson,
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> JsonHttpResponse:
    try:
        return fetcher(
            base_url,
            path,
            method=method,
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return JsonHttpResponse(
            status_code=599,
            payload={"detail": "{}: {}".format(type(exc).__name__, exc)},
        )


def _response_record(response: JsonHttpResponse) -> dict[str, Any]:
    return {
        "status_code": int(response.status_code or 0),
        "payload": dict(response.payload or {}),
    }


def _normalize_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("base_url is required")
    return value


def _parse_json_payload(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"detail": text}
    if isinstance(data, dict):
        return data
    return {"data": data}


def _questions_from_text(text: str) -> list[str]:
    return [
        line.strip()
        for line in str(text or "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _questions_from_json(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return _dedupe_questions(_coerce_question(item) for item in payload)
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list):
            return _dedupe_questions(_coerce_question(item) for item in questions)
    raise ValueError("JSON soak file must be a list or an object with a questions list")


def _coerce_question(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("prompt", "question", "text"):
            value = str(item.get(key, "") or "").strip()
            if value:
                return value
    return ""


def _dedupe_questions(items: Sequence[str] | Any) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in items:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(item) for item in values)
    if not ordered:
        return {
            "count": 0.0,
            "min": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }
    total = sum(ordered)
    return {
        "count": float(len(ordered)),
        "min": round(ordered[0], 2),
        "mean": round(total / len(ordered), 2),
        "p50": round(_percentile(ordered, 50), 2),
        "p95": round(_percentile(ordered, 95), 2),
        "max": round(ordered[-1], 2),
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    rank = (max(0.0, min(100.0, float(percentile))) / 100.0) * (len(values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(values[lower])
    fraction = rank - lower
    return float(values[lower]) + (float(values[upper]) - float(values[lower])) * fraction


def _preview_text(value: str, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 3)].rstrip() + "..."
