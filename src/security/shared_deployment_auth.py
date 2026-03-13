from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from src.security.credentials import KEYRING_SERVICE, _read_keyring


SHARED_API_AUTH_TOKEN_ENV = "HYBRIDRAG_API_AUTH_TOKEN"
SHARED_API_AUTH_TOKEN_PREVIOUS_ENV = "HYBRIDRAG_API_AUTH_TOKEN_PREVIOUS"
SHARED_API_AUTH_TOKEN_KEYRING_NAME = "shared_api_auth_token"
SHARED_API_AUTH_TOKEN_PREVIOUS_KEYRING_NAME = "shared_api_auth_token_previous"
HYBRIDRAG_DEPLOYMENT_MODE_ENV = "HYBRIDRAG_DEPLOYMENT_MODE"
_VALID_DEPLOYMENT_MODES = {"development", "production"}
_cache_lock = threading.Lock()
_shared_auth_cache: "SharedApiAuthStatus | None" = None
_shared_auth_cache_env: tuple[str, str] | None = None


@dataclass(frozen=True)
class SharedApiAuthStatus:
    """Resolved shared-deployment token posture."""

    current_token: str = ""
    current_source: str = ""
    previous_token: str = ""
    previous_source: str = ""
    tokens: tuple[str, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.tokens)

    @property
    def rotation_enabled(self) -> bool:
        return bool(self.previous_token)

    @property
    def primary_source(self) -> str:
        return self.current_source or "disabled"


@dataclass(frozen=True)
class SharedLaunchSnapshot:
    """Operator-facing snapshot of shared launch readiness."""

    project_root: str
    mode: str
    deployment_mode: str
    api_auth_required: bool
    api_auth_source: str
    api_auth_rotation_enabled: bool
    shared_online_enforced: bool
    shared_online_ready: bool
    browser_session_secret_source: str
    ready_for_shared_launch: bool
    blockers: tuple[str, ...]


def invalidate_shared_auth_cache() -> None:
    """Clear the session cache for shared-deployment token lookups."""
    global _shared_auth_cache, _shared_auth_cache_env
    with _cache_lock:
        _shared_auth_cache = None
        _shared_auth_cache_env = None


def resolve_shared_api_auth_status(*, use_cache: bool = True) -> SharedApiAuthStatus:
    """Resolve the shared API token ring from env first, then keyring."""
    global _shared_auth_cache, _shared_auth_cache_env
    env_fingerprint = _env_fingerprint()
    with _cache_lock:
        if (
            use_cache
            and _shared_auth_cache is not None
            and _shared_auth_cache_env == env_fingerprint
        ):
            return _shared_auth_cache

    current_token, current_source = _resolve_secret(
        SHARED_API_AUTH_TOKEN_ENV,
        SHARED_API_AUTH_TOKEN_KEYRING_NAME,
    )
    previous_token, previous_source = _resolve_secret(
        SHARED_API_AUTH_TOKEN_PREVIOUS_ENV,
        SHARED_API_AUTH_TOKEN_PREVIOUS_KEYRING_NAME,
    )
    tokens = _dedupe_non_empty(current_token, previous_token)
    status = SharedApiAuthStatus(
        current_token=current_token,
        current_source=current_source,
        previous_token=previous_token,
        previous_source=previous_source,
        tokens=tokens,
    )
    with _cache_lock:
        _shared_auth_cache = status
        _shared_auth_cache_env = env_fingerprint
    return status


def configured_shared_api_auth_token() -> str:
    """Return the primary configured shared API token, if any."""
    return resolve_shared_api_auth_status().current_token


def configured_shared_api_auth_tokens() -> tuple[str, ...]:
    """Return the accepted shared API token ring."""
    return resolve_shared_api_auth_status().tokens


def shared_api_auth_required() -> bool:
    """Return whether the shared API token ring is configured."""
    return resolve_shared_api_auth_status().configured


def shared_api_auth_rotation_enabled() -> bool:
    """Return whether a previous shared token is accepted."""
    return resolve_shared_api_auth_status().rotation_enabled


def shared_api_auth_source() -> str:
    """Describe where the active shared API token came from."""
    return resolve_shared_api_auth_status().primary_source


def browser_session_fallback_source() -> str:
    """Describe the fallback secret source for browser sessions."""
    if (os.environ.get("HYBRIDRAG_BROWSER_SESSION_SECRET") or "").strip():
        return "browser_session_secret"
    if shared_api_auth_required():
        return "api_auth_token_fallback"
    return "disabled"


def resolve_deployment_mode(config=None) -> str:
    """Resolve deployment mode from env override plus config security section."""
    configured = "development"
    security = getattr(config, "security", None) if config is not None else None
    if security is not None:
        configured = str(getattr(security, "deployment_mode", "development") or "development")
    raw = (os.environ.get(HYBRIDRAG_DEPLOYMENT_MODE_ENV) or configured or "development").strip().lower()
    if raw not in _VALID_DEPLOYMENT_MODES:
        return "development"
    return raw


def shared_online_enforced(config=None) -> bool:
    """Return whether shared traffic must stay online-only."""
    return resolve_deployment_mode(config) == "production" or shared_api_auth_required()


def shared_online_ready(config=None) -> bool:
    """Return whether the runtime mode is online."""
    raw = str(getattr(config, "mode", "offline") or "offline").strip().lower()
    return raw == "online"


def build_shared_launch_snapshot(config, *, project_root: str | Path | None = None) -> SharedLaunchSnapshot:
    """Build the shared launch snapshot used by tools and runtime surfaces."""
    root = Path(project_root or os.environ.get("HYBRIDRAG_PROJECT_ROOT") or ".").resolve()
    status = resolve_shared_api_auth_status()
    deployment_mode = resolve_deployment_mode(config)
    online_ready = shared_online_ready(config)
    enforced = deployment_mode == "production" or status.configured
    blockers: list[str] = []
    if not status.configured:
        blockers.append("Shared API auth token is not configured.")
    if deployment_mode != "production":
        blockers.append("Deployment mode is not production.")
    if not online_ready:
        blockers.append("Runtime mode is not online.")
    return SharedLaunchSnapshot(
        project_root=str(root),
        mode=str(getattr(config, "mode", "offline") or "offline").strip().lower(),
        deployment_mode=deployment_mode,
        api_auth_required=status.configured,
        api_auth_source=status.primary_source,
        api_auth_rotation_enabled=status.rotation_enabled,
        shared_online_enforced=enforced,
        shared_online_ready=online_ready,
        browser_session_secret_source=browser_session_fallback_source(),
        ready_for_shared_launch=not blockers,
        blockers=tuple(blockers),
    )


def format_shared_launch_snapshot(snapshot: SharedLaunchSnapshot) -> str:
    """Render a human-readable shared launch readiness report."""
    lines = [
        "Shared Launch Preflight",
        "-----------------------",
        "Project root: {}".format(snapshot.project_root),
        "Runtime mode: {}".format(snapshot.mode),
        "Deployment mode: {}".format(snapshot.deployment_mode),
        "Shared auth: {}".format(
            "configured ({})".format(snapshot.api_auth_source)
            if snapshot.api_auth_required
            else "disabled"
        ),
        "Auth rotation: {}".format("enabled" if snapshot.api_auth_rotation_enabled else "disabled"),
        "Browser session secret: {}".format(snapshot.browser_session_secret_source),
        "Shared online enforced: {}".format(snapshot.shared_online_enforced),
        "Shared online ready: {}".format(snapshot.shared_online_ready),
        "Launch ready: {}".format(snapshot.ready_for_shared_launch),
    ]
    if snapshot.blockers:
        lines.extend(["", "Blockers", "--------"])
        lines.extend("- {}".format(item) for item in snapshot.blockers)
    return "\n".join(lines)


def load_shared_launch_snapshot(project_root: str | Path | None = None) -> SharedLaunchSnapshot:
    """Load config for a project root and build the shared launch snapshot."""
    from src.core.config import load_config

    root = Path(project_root or os.environ.get("HYBRIDRAG_PROJECT_ROOT") or ".").resolve()
    config = load_config(str(root))
    return build_shared_launch_snapshot(config, project_root=root)


def apply_shared_launch_profile(
    project_root: str | Path | None = None,
    *,
    set_online: bool = False,
    set_production: bool = False,
) -> SharedLaunchSnapshot:
    """Persist the launch-mode posture and return the refreshed snapshot."""
    from src.core.config import save_config_field

    root = Path(project_root or os.environ.get("HYBRIDRAG_PROJECT_ROOT") or ".").resolve()
    original_root = os.environ.get("HYBRIDRAG_PROJECT_ROOT")
    os.environ["HYBRIDRAG_PROJECT_ROOT"] = str(root)
    try:
        if set_online:
            save_config_field("mode", "online")
        if set_production:
            save_config_field("security.deployment_mode", "production")
    finally:
        if original_root is None:
            os.environ.pop("HYBRIDRAG_PROJECT_ROOT", None)
        else:
            os.environ["HYBRIDRAG_PROJECT_ROOT"] = original_root
    return load_shared_launch_snapshot(root)


def store_shared_api_auth_token(token: str, *, previous: bool = False) -> None:
    """Store the shared API token in Windows Credential Manager."""
    import keyring

    value = str(token or "").strip()
    if not value:
        raise ValueError("Shared API token is required.")
    name = (
        SHARED_API_AUTH_TOKEN_PREVIOUS_KEYRING_NAME
        if previous
        else SHARED_API_AUTH_TOKEN_KEYRING_NAME
    )
    keyring.set_password(KEYRING_SERVICE, name, value)
    invalidate_shared_auth_cache()


def clear_shared_api_auth_tokens() -> None:
    """Remove stored shared API tokens from Windows Credential Manager."""
    import keyring

    for name in (
        SHARED_API_AUTH_TOKEN_KEYRING_NAME,
        SHARED_API_AUTH_TOKEN_PREVIOUS_KEYRING_NAME,
    ):
        try:
            keyring.delete_password(KEYRING_SERVICE, name)
        except Exception:
            pass
    invalidate_shared_auth_cache()


def _resolve_secret(env_name: str, keyring_name: str) -> tuple[str, str]:
    value = (os.environ.get(env_name) or "").strip()
    if value:
        return value, "env:{}".format(env_name)
    value = str(_read_keyring(keyring_name) or "").strip()
    if value:
        return value, "keyring"
    return "", ""


def _dedupe_non_empty(*values: str) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return tuple(ordered)


def _env_fingerprint() -> tuple[str, str]:
    return (
        str(os.environ.get(SHARED_API_AUTH_TOKEN_ENV) or "").strip(),
        str(os.environ.get(SHARED_API_AUTH_TOKEN_PREVIOUS_ENV) or "").strip(),
    )
