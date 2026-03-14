import json
from types import SimpleNamespace

import yaml

from src.security import credentials as credential_store
from src.security import shared_deployment_auth as shared_auth
from src.tools import shared_launch_preflight


def _clear_shared_env(monkeypatch):
    for name in (
        shared_auth.SHARED_API_AUTH_TOKEN_ENV,
        shared_auth.SHARED_API_AUTH_TOKEN_PREVIOUS_ENV,
        shared_auth.HYBRIDRAG_DEPLOYMENT_MODE_ENV,
        "HYBRIDRAG_BROWSER_SESSION_SECRET",
        "HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS",
        "HYBRIDRAG_PROJECT_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    shared_auth.invalidate_shared_auth_cache()
    credential_store.invalidate_credential_cache()


def test_resolve_shared_api_auth_status_prefers_env_over_keyring(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_ENV, "env-current")
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_PREVIOUS_ENV, "env-previous")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: "keyring-value")

    status = shared_auth.resolve_shared_api_auth_status(use_cache=False)

    assert status.current_token == "env-current"
    assert status.current_source == "env:HYBRIDRAG_API_AUTH_TOKEN"
    assert status.previous_token == "env-previous"
    assert status.previous_source == "env:HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS"
    assert status.tokens == ("env-current", "env-previous")


def test_resolve_shared_api_auth_status_falls_back_to_keyring(monkeypatch):
    _clear_shared_env(monkeypatch)

    def _fake_keyring(name):
        if name == shared_auth.SHARED_API_AUTH_TOKEN_KEYRING_NAME:
            return "keyring-current"
        if name == shared_auth.SHARED_API_AUTH_TOKEN_PREVIOUS_KEYRING_NAME:
            return "keyring-previous"
        return None

    monkeypatch.setattr(shared_auth, "_read_keyring", _fake_keyring)

    status = shared_auth.resolve_shared_api_auth_status(use_cache=False)

    assert status.current_token == "keyring-current"
    assert status.current_source == "keyring"
    assert status.previous_token == "keyring-previous"
    assert status.tokens == ("keyring-current", "keyring-previous")
    assert status.rotation_enabled is True


def test_build_shared_launch_snapshot_reports_blockers(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=False,
            source_key="",
            source_endpoint="",
            source_deployment="",
        ),
    )
    config = SimpleNamespace(
        mode="offline",
        security=SimpleNamespace(deployment_mode="development"),
    )

    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert snapshot.ready_for_shared_launch is False
    assert snapshot.api_auth_required is False
    assert snapshot.shared_online_ready is False
    assert "Shared API auth token is not configured." in snapshot.blockers
    assert "Deployment mode is not production." in snapshot.blockers
    assert "Runtime mode is not online." in snapshot.blockers
    assert "Online API credentials are not configured." in snapshot.blockers
    assert snapshot.online_api_ready is False
    assert snapshot.online_api_key_source == "disabled"
    assert snapshot.online_api_endpoint_source == "disabled"
    assert snapshot.online_api_deployment_source == "disabled"
    assert any("prompt-shared-token" in step for step in snapshot.next_steps)
    assert any("setup_online_api.py" in step for step in snapshot.next_steps)


def test_build_shared_launch_snapshot_ready_with_keyring_token(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setattr(
        shared_auth,
        "_read_keyring",
        lambda name: "keyring-current"
        if name == shared_auth.SHARED_API_AUTH_TOKEN_KEYRING_NAME
        else None,
    )
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=True,
            source_key="env:AZURE_OPENAI_API_KEY",
            source_endpoint="env:AZURE_OPENAI_ENDPOINT",
            source_deployment="env:AZURE_OPENAI_DEPLOYMENT",
        ),
    )
    config = SimpleNamespace(
        mode="online",
        security=SimpleNamespace(deployment_mode="production"),
    )

    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert snapshot.ready_for_shared_launch is True
    assert snapshot.api_auth_required is True
    assert snapshot.api_auth_source == "keyring"
    assert snapshot.shared_online_enforced is True
    assert snapshot.shared_online_ready is True
    assert snapshot.online_api_ready is True
    assert snapshot.online_api_key_source == "env:AZURE_OPENAI_API_KEY"
    assert snapshot.online_api_endpoint_source == "env:AZURE_OPENAI_ENDPOINT"
    assert snapshot.online_api_deployment_source == "env:AZURE_OPENAI_DEPLOYMENT"
    assert snapshot.browser_session_secret_source == "api_auth_token_fallback"
    assert snapshot.next_steps == ()


def test_build_shared_launch_snapshot_uses_config_object_credentials(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_ENV, "env-current")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(credential_store, "_read_keyring", lambda _name: None)
    config = SimpleNamespace(
        mode="online",
        security=SimpleNamespace(deployment_mode="production"),
        api=SimpleNamespace(
            key="config-key",
            endpoint="https://example.openai.azure.com",
            deployment="gpt-4o",
            api_version="2024-06-01",
        ),
    )

    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert snapshot.ready_for_shared_launch is True
    assert snapshot.online_api_ready is True
    assert snapshot.online_api_key_source == "config"
    assert snapshot.online_api_endpoint_source == "config"
    assert snapshot.online_api_deployment_source == "config"


def test_build_shared_launch_snapshot_requires_deployment_for_azure(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_ENV, "env-current")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(credential_store, "_read_keyring", lambda _name: None)
    config = SimpleNamespace(
        mode="online",
        security=SimpleNamespace(deployment_mode="production"),
        api=SimpleNamespace(
            key="config-key",
            endpoint="https://example.openai.azure.com",
        ),
    )

    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert snapshot.ready_for_shared_launch is False
    assert snapshot.online_api_ready is False
    assert "Online API deployment is not configured." in snapshot.blockers
    assert any("setup_online_api.py" in step for step in snapshot.next_steps)


def test_previous_token_only_does_not_count_as_shared_launch_ready(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_PREVIOUS_ENV, "previous-only")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=True,
            source_key="env:AZURE_OPENAI_API_KEY",
            source_endpoint="env:AZURE_OPENAI_ENDPOINT",
            source_deployment="env:AZURE_OPENAI_DEPLOYMENT",
        ),
    )
    config = SimpleNamespace(
        mode="online",
        security=SimpleNamespace(deployment_mode="production"),
    )

    status = shared_auth.resolve_shared_api_auth_status(use_cache=False)
    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert status.current_token == ""
    assert status.previous_token == "previous-only"
    assert status.tokens == ()
    assert status.configured is False
    assert status.rotation_enabled is False
    assert snapshot.ready_for_shared_launch is False
    assert snapshot.api_auth_required is False
    assert snapshot.online_api_ready is True
    assert snapshot.shared_api_previous_configured is True
    assert snapshot.shared_api_previous_source == "env:HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS"
    assert snapshot.browser_session_secret_source == "disabled"
    assert "Shared API auth token is not configured." in snapshot.blockers


def test_shared_launch_snapshot_requires_online_api_credentials(monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_ENV, "env-current")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=False,
            source_key="disabled",
            source_endpoint="disabled",
            source_deployment="disabled",
        ),
    )
    config = SimpleNamespace(
        mode="online",
        security=SimpleNamespace(deployment_mode="production"),
    )

    snapshot = shared_auth.build_shared_launch_snapshot(config, project_root="D:/HybridRAG3")

    assert snapshot.api_auth_required is True
    assert snapshot.shared_online_ready is True
    assert snapshot.online_api_ready is False
    assert snapshot.ready_for_shared_launch is False
    assert snapshot.blockers == ("Online API credentials are not configured.",)
    assert any("setup_online_api.py" in step for step in snapshot.next_steps)


def test_apply_shared_launch_profile_persists_online_and_production(tmp_path, monkeypatch):
    _clear_shared_env(monkeypatch)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=True,
            source_key="env:AZURE_OPENAI_API_KEY",
            source_endpoint="env:AZURE_OPENAI_ENDPOINT",
            source_deployment="env:AZURE_OPENAI_DEPLOYMENT",
        ),
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "mode": "offline",
                "security": {"deployment_mode": "development"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_ENV, "env-current")

    snapshot = shared_auth.apply_shared_launch_profile(
        tmp_path,
        set_online=True,
        set_production=True,
    )

    assert snapshot.ready_for_shared_launch is True
    assert snapshot.mode == "online"
    assert snapshot.deployment_mode == "production"
    saved = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
    assert saved["mode"] == "online"
    assert saved["security"]["deployment_mode"] == "production"


def test_shared_launch_preflight_main_emits_json_and_fail_code(tmp_path, monkeypatch, capsys):
    _clear_shared_env(monkeypatch)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=False,
            source_key="",
            source_endpoint="",
            source_deployment="",
        ),
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump({"mode": "offline", "security": {"deployment_mode": "development"}}, sort_keys=False),
        encoding="utf-8",
    )

    code = shared_launch_preflight.main(
        ["--project-root", str(tmp_path), "--json", "--fail-if-blocked"]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ready_for_shared_launch"] is False
    assert "Runtime mode is not online." in payload["blockers"]
    assert "Online API credentials are not configured." in payload["blockers"]
    assert payload["online_api_ready"] is False


def test_shared_launch_preflight_previous_token_only_fails_in_production_online_mode(
    tmp_path, monkeypatch, capsys
):
    _clear_shared_env(monkeypatch)
    monkeypatch.setenv(shared_auth.SHARED_API_AUTH_TOKEN_PREVIOUS_ENV, "previous-only")
    monkeypatch.setattr(shared_auth, "_read_keyring", lambda _name: None)
    monkeypatch.setattr(
        shared_auth,
        "resolve_credentials",
        lambda config_dict=None, use_cache=False: SimpleNamespace(
            is_online_ready=True,
            source_key="env:AZURE_OPENAI_API_KEY",
            source_endpoint="env:AZURE_OPENAI_ENDPOINT",
            source_deployment="env:AZURE_OPENAI_DEPLOYMENT",
        ),
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        yaml.safe_dump({"mode": "online", "security": {"deployment_mode": "production"}}, sort_keys=False),
        encoding="utf-8",
    )

    code = shared_launch_preflight.main(
        ["--project-root", str(tmp_path), "--json", "--fail-if-blocked"]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "online"
    assert payload["deployment_mode"] == "production"
    assert payload["shared_online_ready"] is True
    assert payload["online_api_ready"] is True
    assert payload["api_auth_required"] is False
    assert payload["api_auth_rotation_enabled"] is False
    assert payload["ready_for_shared_launch"] is False
    assert payload["blockers"] == ["Shared API auth token is not configured."]


def test_store_shared_api_auth_token_uses_keyring_and_invalidates_cache(monkeypatch):
    _clear_shared_env(monkeypatch)
    calls = []

    class FakeKeyring:
        @staticmethod
        def set_password(service, name, value):
            calls.append((service, name, value))

    monkeypatch.setitem(__import__("sys").modules, "keyring", FakeKeyring)

    shared_auth.store_shared_api_auth_token("shared-token")

    assert calls == [
        (
            shared_auth.KEYRING_SERVICE,
            shared_auth.SHARED_API_AUTH_TOKEN_KEYRING_NAME,
            "shared-token",
        )
    ]
