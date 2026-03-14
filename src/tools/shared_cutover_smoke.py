from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import http.cookiejar
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib import error, request

from src.api.browser_session import SESSION_COOKIE_NAME
from src.tools.shared_deployment_backup import (
    default_shared_backup_dir,
    run_shared_restore_drill,
    verify_shared_backup_bundle,
)
from src.tools.shared_deployment_soak import build_request_headers


@dataclass(frozen=True)
class CutoverHttpResponse:
    status_code: int
    headers: dict[str, str]
    text: str
    payload: Any
    final_url: str
    error: str = ""


FetchCutover = Callable[..., CutoverHttpResponse]


class SharedCutoverHttpClient:
    def __init__(self) -> None:
        self._cookies = http.cookiejar.CookieJar()
        self._opener = request.build_opener(request.HTTPCookieProcessor(self._cookies))

    def fetch(
        self,
        base_url: str,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> CutoverHttpResponse:
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
            with self._opener.open(req, timeout=float(timeout_seconds)) as response:
                raw = response.read().decode("utf-8", errors="replace")
                header_map = {str(k): str(v) for k, v in response.headers.items()}
                return CutoverHttpResponse(
                    status_code=int(getattr(response, "status", 200) or 200),
                    headers=header_map,
                    text=raw,
                    payload=_parse_payload(raw, header_map),
                    final_url=str(getattr(response, "url", "") or response.geturl() or target),
                )
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            header_map = {str(k): str(v) for k, v in exc.headers.items()}
            return CutoverHttpResponse(
                status_code=int(getattr(exc, "code", 500) or 500),
                headers=header_map,
                text=raw,
                payload=_parse_payload(raw, header_map),
                final_url=str(getattr(exc, "url", "") or target),
                error=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            return CutoverHttpResponse(
                status_code=0,
                headers={},
                text="",
                payload=None,
                final_url=target,
                error=str(exc),
            )


def default_shared_cutover_report_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "output" / "shared_cutover_smoke"


def find_latest_shared_backup_bundle(project_root: str | Path | None = None) -> Path | None:
    backup_root = default_shared_backup_dir(project_root)
    if not backup_root.exists():
        return None
    bundles = sorted(
        (
            path
            for path in backup_root.iterdir()
            if path.is_dir() and path.name.endswith("_shared_deployment_backup")
        ),
        key=lambda path: path.name,
    )
    if not bundles:
        return None
    return bundles[-1]


def run_shared_cutover_smoke(
    *,
    base_url: str,
    auth_token: str = "",
    proxy_user_header: str = "",
    proxy_user_value: str = "",
    proxy_identity_secret: str = "",
    timeout_seconds: float = 30.0,
    extra_headers: dict[str, str] | None = None,
    backup_bundle: str | Path | None = None,
    run_restore_drill: bool = False,
    restore_root: str | Path | None = None,
    require_rollback_proof: bool = False,
    project_root: str | Path = ".",
    fetcher: FetchCutover | None = None,
) -> dict[str, Any]:
    client_fetch = fetcher or SharedCutoverHttpClient().fetch
    primary_headers = build_request_headers(
        auth_token=auth_token,
        proxy_user_header=proxy_user_header,
        proxy_user_value=proxy_user_value,
        proxy_identity_secret=proxy_identity_secret,
        extra_headers=extra_headers,
    )
    session_headers = build_request_headers(extra_headers=extra_headers)

    checks = {
        "health": _response_record(
            client_fetch(
                base_url,
                "/health",
                headers=primary_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
        "status": _response_record(
            client_fetch(
                base_url,
                "/status",
                headers=primary_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
        "auth_context": _response_record(
            client_fetch(
                base_url,
                "/auth/context",
                headers=primary_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
        "dashboard": _response_record(
            client_fetch(
                base_url,
                "/dashboard",
                headers=primary_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
        "session_context": _response_record(
            client_fetch(
                base_url,
                "/auth/context",
                headers=session_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
        "admin_data": _response_record(
            client_fetch(
                base_url,
                "/admin/data",
                headers=session_headers,
                timeout_seconds=timeout_seconds,
            )
        ),
    }

    rollback = _run_rollback_proof(
        backup_bundle=backup_bundle,
        run_restore_drill=run_restore_drill,
        restore_root=restore_root,
        project_root=project_root,
        require_rollback_proof=require_rollback_proof,
    )
    summary = summarize_cutover_results(checks, rollback=rollback)
    report = {
        "ok": not summary["blockers"],
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": {
            "base_url": _normalize_base_url(base_url),
        },
        "config": {
            "timeout_seconds": float(timeout_seconds),
            "auth_token_configured": bool(str(auth_token or "").strip()),
            "proxy_user_header": str(proxy_user_header or "").strip(),
            "proxy_user_value": str(proxy_user_value or "").strip(),
            "proxy_identity_secret_configured": bool(str(proxy_identity_secret or "").strip()),
            "require_rollback_proof": bool(require_rollback_proof),
            "run_restore_drill": bool(run_restore_drill),
        },
        "checks": checks,
        "rollback_proof": rollback,
        "summary": summary,
    }
    return report


def summarize_cutover_results(
    checks: dict[str, dict[str, Any]],
    *,
    rollback: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    health = checks.get("health", {})
    status = checks.get("status", {})
    auth_context = checks.get("auth_context", {})
    dashboard = checks.get("dashboard", {})
    session_context = checks.get("session_context", {})
    admin_data = checks.get("admin_data", {})

    if int(health.get("status_code", 0) or 0) != 200:
        blockers.append("GET /health did not return 200.")
    if int(status.get("status_code", 0) or 0) != 200:
        blockers.append("GET /status did not return 200.")
    if int(auth_context.get("status_code", 0) or 0) != 200:
        blockers.append("GET /auth/context did not return 200.")
    if int(dashboard.get("status_code", 0) or 0) != 200:
        blockers.append("GET /dashboard did not return 200.")
    if int(session_context.get("status_code", 0) or 0) != 200:
        blockers.append("Post-dashboard GET /auth/context did not return 200.")
    if int(admin_data.get("status_code", 0) or 0) != 200:
        blockers.append("GET /admin/data did not return 200.")

    status_payload = dict(status.get("payload", {}) or {})
    auth_payload = dict(auth_context.get("payload", {}) or {})
    session_payload = dict(session_context.get("payload", {}) or {})
    admin_payload = dict(admin_data.get("payload", {}) or {})

    if status_payload.get("mode") != "online":
        blockers.append("Shared deployment runtime mode is not online.")
    if status_payload.get("deployment_mode") != "production":
        blockers.append("Shared deployment mode is not production.")
    if auth_payload.get("auth_required") is not True:
        blockers.append("Shared API auth is not enforced.")
    if session_payload.get("auth_mode") != "session":
        blockers.append("Dashboard request did not bootstrap a browser session.")

    dashboard_title = str(dashboard.get("page_title", "") or "")
    if dashboard_title and "HybridRAG" not in dashboard_title and "Deployment" not in dashboard_title:
        blockers.append("Dashboard page title did not match the shared deployment console.")

    dashboard_body = str(dashboard.get("text_preview", "") or "")
    if dashboard_body and "login" in dashboard_body.lower() and not dashboard.get("session_cookie_seen"):
        blockers.append("Dashboard appears to be serving the login page instead of the shared console.")

    runtime_safety = dict(admin_payload.get("runtime_safety", {}) or {})
    if runtime_safety and runtime_safety.get("api_auth_required") is not True:
        blockers.append("Admin runtime safety snapshot does not show API auth enforcement.")

    if rollback.get("required") and not rollback.get("ok"):
        blockers.append("Rollback proof did not pass.")

    return {
        "endpoint_passes": sum(1 for item in checks.values() if item.get("ok")),
        "endpoint_total": len(checks),
        "deployment_mode": status_payload.get("deployment_mode", ""),
        "runtime_mode": status_payload.get("mode", ""),
        "auth_mode": auth_payload.get("auth_mode", ""),
        "actor": auth_payload.get("actor", ""),
        "session_actor": session_payload.get("actor", ""),
        "dashboard_session_bootstrap": bool(session_payload.get("auth_mode") == "session"),
        "rollback_ok": bool(rollback.get("ok")),
        "blockers": blockers,
    }


def write_shared_cutover_report(
    report: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> Path:
    report_dir = default_shared_cutover_report_dir(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = (timestamp or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    path = report_dir / "{}_shared_cutover_smoke.json".format(stamp)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def format_cutover_console_summary(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary", {}) or {})
    rollback = dict(report.get("rollback_proof", {}) or {})
    lines = [
        "HYBRIDRAG SHARED CUTOVER SMOKE",
        "Target: {}".format(str(((report.get("target") or {}).get("base_url")) or "")),
        "Endpoint checks: {}/{} passed".format(
            int(summary.get("endpoint_passes", 0) or 0),
            int(summary.get("endpoint_total", 0) or 0),
        ),
        "Posture: deployment_mode={} mode={} auth_mode={}".format(
            str(summary.get("deployment_mode", "") or ""),
            str(summary.get("runtime_mode", "") or ""),
            str(summary.get("auth_mode", "") or ""),
        ),
        "Actor: {} | Session actor: {}".format(
            str(summary.get("actor", "") or ""),
            str(summary.get("session_actor", "") or ""),
        ),
        "Dashboard session bootstrap: {}".format(
            bool(summary.get("dashboard_session_bootstrap"))
        ),
        "Rollback proof: {}".format(
            "passed" if rollback.get("ok") else str(rollback.get("status", "not_run"))
        ),
    ]
    blockers = list(summary.get("blockers", []) or [])
    if blockers:
        lines.append("Blockers:")
        lines.extend("- {}".format(item) for item in blockers)
    return "\n".join(lines)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the shared deployment cutover smoke checks and optionally "
            "reconfirm rollback proof from a backup bundle."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the shared HybridRAG API.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="HybridRAG project root for report output and latest-backup resolution.",
    )
    parser.add_argument(
        "--auth-token",
        default="",
        help="Optional shared API bearer token used to bootstrap the browser session.",
    )
    parser.add_argument(
        "--proxy-user-header",
        default="",
        help="Optional trusted proxy user header name.",
    )
    parser.add_argument(
        "--proxy-user-value",
        default="",
        help="Optional trusted proxy user value.",
    )
    parser.add_argument(
        "--proxy-identity-secret",
        default="",
        help="Optional trusted proxy identity secret value.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--backup-bundle",
        default="",
        help="Optional backup bundle directory to verify. Use 'latest' to auto-pick the newest bundle.",
    )
    parser.add_argument(
        "--run-restore-drill",
        action="store_true",
        help="Run a non-destructive restore drill after backup verification.",
    )
    parser.add_argument(
        "--restore-root",
        default="",
        help="Optional restore-drill output root.",
    )
    parser.add_argument(
        "--require-rollback-proof",
        action="store_true",
        help="Fail when backup verification or restore drill is not available/passing.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report to stdout instead of the console summary.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write a timestamped JSON report under output/shared_cutover_smoke.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_cli_parser().parse_args(argv)
    backup_bundle = args.backup_bundle.strip()
    if backup_bundle.lower() == "latest":
        latest = find_latest_shared_backup_bundle(args.project_root)
        backup_bundle = str(latest) if latest is not None else ""

    report = run_shared_cutover_smoke(
        base_url=args.base_url,
        auth_token=args.auth_token,
        proxy_user_header=args.proxy_user_header,
        proxy_user_value=args.proxy_user_value,
        proxy_identity_secret=args.proxy_identity_secret,
        timeout_seconds=args.timeout,
        backup_bundle=backup_bundle or None,
        run_restore_drill=bool(args.run_restore_drill),
        restore_root=args.restore_root or None,
        require_rollback_proof=bool(args.require_rollback_proof),
        project_root=args.project_root,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_cutover_console_summary(report))
    if not args.no_report:
        path = write_shared_cutover_report(report, project_root=args.project_root)
        print("Saved report: {}".format(path))
    return 0 if report.get("ok") else 1


def _run_rollback_proof(
    *,
    backup_bundle: str | Path | None,
    run_restore_drill: bool,
    restore_root: str | Path | None,
    project_root: str | Path,
    require_rollback_proof: bool,
) -> dict[str, Any]:
    bundle_path = Path(backup_bundle).expanduser().resolve() if backup_bundle else None
    if bundle_path is None:
        return {
            "required": bool(require_rollback_proof),
            "status": "not_run",
            "bundle_dir": "",
            "verify": None,
            "restore_drill": None,
            "ok": not require_rollback_proof,
        }

    verify = verify_shared_backup_bundle(bundle_path)
    restore = None
    if run_restore_drill and verify.get("ok"):
        restore = run_shared_restore_drill(
            bundle_path,
            restore_root=restore_root,
        )
    ok = bool(verify.get("ok")) and (restore is None or bool(restore.get("ok")))
    return {
        "required": bool(require_rollback_proof),
        "status": "passed" if ok else "failed",
        "bundle_dir": str(bundle_path),
        "verify": verify,
        "restore_drill": restore,
        "ok": ok,
        "used_latest_bundle": bundle_path == find_latest_shared_backup_bundle(project_root),
    }


def _response_record(response: CutoverHttpResponse) -> dict[str, Any]:
    header_map = {str(k).lower(): str(v) for k, v in response.headers.items()}
    record = {
        "status_code": int(response.status_code or 0),
        "ok": 200 <= int(response.status_code or 0) < 300 and not response.error,
        "content_type": header_map.get("content-type", ""),
        "final_url": str(response.final_url or ""),
        "location": header_map.get("location", ""),
        "session_cookie_seen": SESSION_COOKIE_NAME in header_map.get("set-cookie", ""),
        "error": str(response.error or ""),
    }
    if isinstance(response.payload, (dict, list)):
        record["payload"] = response.payload
    if response.text:
        record["page_title"] = _extract_html_title(response.text)
        record["text_preview"] = response.text[:200]
    return record


def _parse_payload(raw: str, headers: dict[str, str]) -> Any:
    text = str(raw or "")
    content_type = ""
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            content_type = str(value or "")
            break
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            return json.loads(text)
        except Exception:
            return None
    return None


def _extract_html_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "http://127.0.0.1:8000").rstrip("/")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
