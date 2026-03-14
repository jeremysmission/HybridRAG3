from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pytest

from src.tools.shared_cutover_smoke import (
    CutoverHttpResponse,
    find_latest_shared_backup_bundle,
    format_cutover_console_summary,
    run_shared_cutover_smoke,
    write_shared_cutover_report,
)
from src.tools.shared_deployment_backup import create_shared_backup_bundle


def test_write_shared_cutover_report_uses_timestamped_name(tmp_path: Path) -> None:
    report = {"ok": True, "summary": {"endpoint_total": 6}}

    path = write_shared_cutover_report(
        report,
        project_root=tmp_path,
        timestamp=datetime(2026, 3, 13, 18, 0, 0),
    )

    assert path.name == "2026-03-13_180000_shared_cutover_smoke.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["endpoint_total"] == 6


def test_find_latest_shared_backup_bundle_returns_newest(tmp_path: Path) -> None:
    backup_root = tmp_path / "output" / "shared_backups"
    (backup_root / "2026-03-13_103253_shared_deployment_backup").mkdir(parents=True)
    latest = backup_root / "2026-03-13_104241_shared_deployment_backup"
    latest.mkdir()

    found = find_latest_shared_backup_bundle(tmp_path)

    assert found == latest


def test_run_shared_cutover_smoke_captures_session_bootstrap_and_rollback(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_fetcher(base_url, path, *, method="GET", headers=None, payload=None, timeout_seconds=0):
        calls.append((path, dict(headers or {})))
        if path == "/health":
            return CutoverHttpResponse(200, {"Content-Type": "application/json"}, '{"status":"ok"}', {"status": "ok"}, base_url + path)
        if path == "/status":
            return CutoverHttpResponse(
                200,
                {"Content-Type": "application/json"},
                '{"status":"ok","mode":"online","deployment_mode":"production"}',
                {"status": "ok", "mode": "online", "deployment_mode": "production"},
                base_url + path,
            )
        if path == "/auth/context" and headers and headers.get("Authorization"):
            return CutoverHttpResponse(
                200,
                {"Content-Type": "application/json"},
                '{"auth_required":true,"auth_mode":"api_token","actor":"ops-dashboard"}',
                {"auth_required": True, "auth_mode": "api_token", "actor": "ops-dashboard"},
                base_url + path,
            )
        if path == "/dashboard":
            return CutoverHttpResponse(
                200,
                {
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": "hybridrag_browser_session=abc123; Path=/; HttpOnly",
                },
                "<html><head><title>HybridRAG Shared Console</title></head><body>Deployment dashboard</body></html>",
                None,
                base_url + path,
            )
        if path == "/auth/context":
            return CutoverHttpResponse(
                200,
                {"Content-Type": "application/json"},
                '{"auth_required":true,"auth_mode":"session","actor":"ops-dashboard"}',
                {"auth_required": True, "auth_mode": "session", "actor": "ops-dashboard"},
                base_url + path,
            )
        if path == "/admin/data":
            return CutoverHttpResponse(
                200,
                {"Content-Type": "application/json"},
                '{"runtime_safety":{"api_auth_required":true}}',
                {"runtime_safety": {"api_auth_required": True}},
                base_url + path,
            )
        raise AssertionError("unexpected path: {}".format(path))

    project_root, main_db = _make_shared_project(tmp_path / "project")
    backup = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 18, 1, 0),
        include_logs=False,
    )

    report = run_shared_cutover_smoke(
        base_url="http://127.0.0.1:8000",
        auth_token="test-token",
        backup_bundle=backup["bundle_dir"],
        run_restore_drill=True,
        require_rollback_proof=True,
        project_root=project_root,
        fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    assert report["summary"]["dashboard_session_bootstrap"] is True
    assert report["summary"]["deployment_mode"] == "production"
    assert report["checks"]["dashboard"]["session_cookie_seen"] is True
    assert report["checks"]["session_context"]["payload"]["auth_mode"] == "session"
    assert report["rollback_proof"]["ok"] is True
    assert [path for path, _headers in calls] == [
        "/health",
        "/status",
        "/auth/context",
        "/dashboard",
        "/auth/context",
        "/admin/data",
    ]


def test_format_cutover_console_summary_mentions_posture_and_rollback() -> None:
    summary = format_cutover_console_summary(
        {
            "target": {"base_url": "http://127.0.0.1:8000"},
            "summary": {
                "endpoint_passes": 6,
                "endpoint_total": 6,
                "deployment_mode": "production",
                "runtime_mode": "online",
                "auth_mode": "api_token",
                "actor": "ops-dashboard",
                "session_actor": "ops-dashboard",
                "dashboard_session_bootstrap": True,
                "blockers": [],
            },
            "rollback_proof": {"ok": True, "status": "passed"},
        }
    )

    assert "Endpoint checks: 6/6 passed" in summary
    assert "Posture: deployment_mode=production mode=online auth_mode=api_token" in summary
    assert "Rollback proof: passed" in summary


def test_run_shared_cutover_smoke_hits_live_fastapi_surfaces_in_process(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    from src.api.server import app, state
    from src.core.network_gate import get_gate
    from src.security import shared_deployment_auth as shared_auth

    original_mode = None
    original_deployment_mode = None
    try:
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("HYBRIDRAG_API_AUTH_LABEL", "shared-dashboard")
        monkeypatch.setenv("HYBRIDRAG_ROLE_MAP", "shared-dashboard=admin")
        monkeypatch.setenv("HYBRIDRAG_ROLE_TAGS", "admin=*")
        shared_auth.invalidate_shared_auth_cache()
        gate = get_gate()
        gate.configure("online")
        gate.clear_audit_log()

        with fastapi_testclient.TestClient(app) as client:
            original_mode = state.config.mode
            original_deployment_mode = state.config.security.deployment_mode
            monkeypatch.setattr(state.config, "mode", "online")
            monkeypatch.setattr(state.config.security, "deployment_mode", "production")

            def client_fetcher(base_url, path, *, method="GET", headers=None, payload=None, timeout_seconds=0):
                assert base_url == "http://testserver"
                response = client.get(path, headers=headers, follow_redirects=True)
                content_type = response.headers.get("content-type", "")
                parsed = None
                if "json" in content_type:
                    parsed = response.json()
                return CutoverHttpResponse(
                    response.status_code,
                    dict(response.headers),
                    response.text,
                    parsed,
                    str(response.url),
                )

            report = run_shared_cutover_smoke(
                base_url="http://testserver",
                auth_token="test-token",
                fetcher=client_fetcher,
            )

        assert report["checks"]["health"]["status_code"] == 200
        assert report["checks"]["status"]["status_code"] == 200
        assert report["checks"]["dashboard"]["status_code"] == 200
        assert report["checks"]["session_context"]["payload"]["auth_mode"] == "session"
        assert report["checks"]["admin_data"]["status_code"] == 200
        assert report["summary"]["session_actor"] == "shared-dashboard"
    finally:
        if state.config is not None and original_mode is not None:
            state.config.mode = original_mode
        if state.config is not None and original_deployment_mode is not None:
            state.config.security.deployment_mode = original_deployment_mode
        shared_auth.invalidate_shared_auth_cache()


def _make_shared_project(project_root: Path) -> tuple[Path, Path]:
    from tests.test_shared_deployment_backup_tool import _create_history_db, _create_main_db
    from src.api.query_threads import conversation_history_db_path

    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "logs").mkdir(parents=True, exist_ok=True)
    (project_root / "source").mkdir(parents=True, exist_ok=True)
    (project_root / "data").mkdir(parents=True, exist_ok=True)

    main_db = project_root / "data" / "hybridrag.sqlite3"
    history_db = Path(conversation_history_db_path(str(main_db)))
    _create_main_db(main_db)
    _create_history_db(history_db)

    config_yaml = "\n".join(
        [
            "paths:",
            "  source_folder: {}".format((project_root / "source").as_posix()),
            "  database: {}".format(main_db.as_posix()),
            "  embeddings_cache: {}".format((project_root / "data" / "_embeddings").as_posix()),
            "mode: online",
            "security:",
            "  deployment_mode: production",
            "",
        ]
    )
    (project_root / "config" / "config.yaml").write_text(config_yaml, encoding="utf-8")
    (project_root / "config" / "user_modes.yaml").write_text("modes: {}\n", encoding="utf-8")
    (project_root / "logs" / "runtime.log").write_text("cutover test log\n", encoding="utf-8")
    return project_root, main_db
