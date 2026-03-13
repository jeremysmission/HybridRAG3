from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, Request

from src.api.access_policy import resolve_role_policy
from src.api.auth_audit import record_auth_event
from src.api.browser_session import SESSION_COOKIE_NAME, parse_browser_session
from src.security.shared_deployment_auth import configured_shared_api_auth_tokens

_DEFAULT_PROXY_USER_HEADERS = (
    "x-forwarded-user",
    "x-auth-request-user",
    "x-ms-client-principal-name",
    "remote-user",
)
_DEFAULT_TRUSTED_PROXY_HOSTS = ("127.0.0.1", "::1", "localhost")
_DEFAULT_PROXY_IDENTITY_SECRET_HEADER = "x-hybridrag-proxy-secret"
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RequestAuthContext:
    """Resolved request auth and actor context for shared deployment APIs."""

    auth_required: bool
    auth_mode: str
    actor: str
    actor_source: str
    actor_role: str
    actor_role_source: str
    allowed_doc_tags: tuple[str, ...]
    document_policy_source: str
    client_host: str
    session_cookie_active: bool
    session_issued_at: str | None
    session_expires_at: str | None
    session_ttl_seconds: int | None
    session_seconds_remaining: int | None
    proxy_identity_trusted: bool
    trusted_proxy_identity_headers: tuple[str, ...]


def client_host(request: Request) -> str:
    """Best-effort client host for shared deployment activity tracking."""
    return str(getattr(getattr(request, "client", None), "host", None) or "unknown")


def resolve_request_auth_context(request: Request) -> RequestAuthContext:
    """Validate request auth and derive the effective request actor."""
    expected_tokens = configured_api_auth_tokens()
    auth_required = bool(expected_tokens)
    provided_token = _provided_token(request)
    session = parse_browser_session(request.cookies.get(SESSION_COOKIE_NAME))
    token_authorized = api_token_matches(provided_token)
    session_authorized = session is not None
    proxy_rejection_detail, proxy_rejection_actor = _proxy_identity_rejection_detail(request)
    if proxy_rejection_detail:
        record_auth_event(
            request,
            event="proxy_identity_rejected",
            outcome="denied",
            detail=proxy_rejection_detail,
            actor=proxy_rejection_actor,
        )
    if auth_required:
        if not token_authorized and not session_authorized:
            record_auth_event(
                request,
                event="unauthorized_request",
                outcome="denied",
                detail="Request did not present a valid shared token or browser session.",
            )
            raise HTTPException(status_code=401, detail="Unauthorized")

    proxy_identity_trusted = _proxy_identity_trusted(request)
    trusted_headers = _proxy_user_headers() if proxy_identity_trusted else ()
    proxy_actor, proxy_header = _proxy_actor(request, trusted_headers)

    actor = "anonymous"
    actor_source = "anonymous"
    auth_mode = "open"
    session_cookie_active = False
    session_issued_at = None
    session_expires_at = None
    session_ttl_seconds = None
    session_seconds_remaining = None

    if auth_required:
        if session_authorized and session is not None:
            actor = session.actor
            actor_source = session.actor_source
            auth_mode = "session"
            session_cookie_active = True
            session_issued_at = _unix_to_iso(session.issued_at)
            session_expires_at = _unix_to_iso(session.expires_at)
            session_ttl_seconds = max(0, int(session.expires_at) - int(session.issued_at))
            session_seconds_remaining = max(0, int(session.expires_at) - int(_now_unix()))
        if token_authorized:
            actor = api_auth_label()
            actor_source = "api_token"
            auth_mode = "api_token"

    if proxy_actor:
        actor = proxy_actor
        actor_source = f"proxy_header:{proxy_header}"
        if auth_mode == "api_token":
            auth_mode = "token+proxy_header"
        elif auth_mode == "session":
            auth_mode = "session+proxy_header"
        else:
            auth_mode = "proxy_header"

    role_policy = resolve_role_policy(actor=actor, actor_source=actor_source)

    return RequestAuthContext(
        auth_required=auth_required,
        auth_mode=auth_mode,
        actor=actor,
        actor_source=actor_source,
        actor_role=role_policy.actor_role,
        actor_role_source=role_policy.actor_role_source,
        allowed_doc_tags=role_policy.allowed_doc_tags,
        document_policy_source=role_policy.document_policy_source,
        client_host=client_host(request),
        session_cookie_active=session_cookie_active,
        session_issued_at=session_issued_at,
        session_expires_at=session_expires_at,
        session_ttl_seconds=session_ttl_seconds,
        session_seconds_remaining=session_seconds_remaining,
        proxy_identity_trusted=proxy_identity_trusted,
        trusted_proxy_identity_headers=tuple(trusted_headers),
    )


def configured_api_auth_token() -> str:
    tokens = configured_api_auth_tokens()
    return tokens[0] if tokens else ""


def configured_api_auth_tokens() -> tuple[str, ...]:
    return configured_shared_api_auth_tokens()


def api_token_matches(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    return _matches_secret_ring(candidate, configured_api_auth_tokens())


def api_auth_label() -> str:
    label = (os.environ.get("HYBRIDRAG_API_AUTH_LABEL") or "").strip()
    return label or "shared-token"


def proxy_identity_headers_enabled() -> bool:
    return _env_truthy("HYBRIDRAG_TRUST_PROXY_IDENTITY_HEADERS")


def proxy_identity_rotation_enabled() -> bool:
    return bool((os.environ.get("HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS") or "").strip())


def proxy_user_headers() -> tuple[str, ...]:
    return _proxy_user_headers()


def trusted_proxy_hosts() -> tuple[str, ...]:
    return _trusted_proxy_hosts()


def _unix_to_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp)).astimezone().isoformat(timespec="seconds")


def _now_unix() -> int:
    return int(datetime.now().astimezone().timestamp())


def _env_truthy(name: str) -> bool:
    value = (os.environ.get(name) or "").strip().lower()
    return value in _TRUTHY


def _provided_token(request: Request) -> str:
    auth_header = (request.headers.get("authorization") or "").strip()
    api_key_header = (request.headers.get("x-api-key") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    if api_key_header:
        return api_key_header
    return ""


def _proxy_identity_trusted(request: Request) -> bool:
    if not proxy_identity_headers_enabled():
        return False
    if client_host(request).strip().lower() not in _trusted_proxy_hosts():
        return False
    expected_secrets = _proxy_identity_secrets()
    provided_secret = _provided_proxy_identity_secret(request)
    return bool(
        expected_secrets
        and provided_secret
        and _matches_secret_ring(provided_secret, expected_secrets)
    )


def _proxy_user_headers() -> tuple[str, ...]:
    raw = (os.environ.get("HYBRIDRAG_PROXY_USER_HEADERS") or "").strip()
    if not raw:
        return _DEFAULT_PROXY_USER_HEADERS
    headers = tuple(
        header.strip().lower()
        for header in re.split(r"[,\s;]+", raw)
        if header.strip()
    )
    return headers or _DEFAULT_PROXY_USER_HEADERS


def _proxy_identity_secret() -> str:
    secrets = _proxy_identity_secrets()
    return secrets[0] if secrets else ""


def _proxy_identity_secrets() -> tuple[str, ...]:
    return _secret_ring(
        primary_env="HYBRIDRAG_PROXY_IDENTITY_SECRET",
        previous_env="HYBRIDRAG_PROXY_IDENTITY_SECRET_PREVIOUS",
    )


def _proxy_identity_secret_header() -> str:
    header = (os.environ.get("HYBRIDRAG_PROXY_IDENTITY_SECRET_HEADER") or "").strip().lower()
    return header or _DEFAULT_PROXY_IDENTITY_SECRET_HEADER


def _provided_proxy_identity_secret(request: Request) -> str:
    return (request.headers.get(_proxy_identity_secret_header()) or "").strip()


def _trusted_proxy_hosts() -> tuple[str, ...]:
    raw = (os.environ.get("HYBRIDRAG_TRUSTED_PROXY_HOSTS") or "").strip()
    if not raw:
        return _DEFAULT_TRUSTED_PROXY_HOSTS
    hosts = tuple(
        host.strip().lower()
        for host in re.split(r"[,\s;]+", raw)
        if host.strip()
    )
    return hosts or _DEFAULT_TRUSTED_PROXY_HOSTS


def _proxy_actor(
    request: Request,
    trusted_headers: tuple[str, ...],
) -> tuple[str, str]:
    for header_name in trusted_headers:
        value = (request.headers.get(header_name) or "").strip()
        if value:
            return value, header_name
    return "", ""


def _proxy_identity_rejection_detail(request: Request) -> tuple[str, str]:
    actor = ""
    for header_name in _proxy_user_headers():
        value = (request.headers.get(header_name) or "").strip()
        if value:
            actor = value
            break
    if not actor:
        return "", ""
    if not proxy_identity_headers_enabled():
        return "Proxy identity headers were supplied while trust is disabled.", actor
    host = client_host(request).strip().lower()
    if host not in _trusted_proxy_hosts():
        return f"Proxy identity headers were supplied from untrusted host '{host or 'unknown'}'.", actor
    expected_secrets = _proxy_identity_secrets()
    if not expected_secrets:
        return "Proxy identity headers were supplied but no proxy proof secret is configured.", actor
    provided_secret = _provided_proxy_identity_secret(request)
    if not provided_secret:
        return "Proxy identity headers were supplied without the proxy proof secret header.", actor
    if not _matches_secret_ring(provided_secret, expected_secrets):
        return "Proxy identity headers were supplied with an invalid proxy proof secret.", actor
    return "", ""


def _secret_ring(*, primary_env: str, previous_env: str) -> tuple[str, ...]:
    values: list[str] = []
    for env_name in (primary_env, previous_env):
        raw = (os.environ.get(env_name) or "").strip()
        if not raw:
            continue
        for value in re.split(r"[,\s;]+", raw):
            secret = value.strip()
            if secret and secret not in values:
                values.append(secret)
    return tuple(values)


def _matches_secret_ring(value: str, secrets: tuple[str, ...]) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    return any(hmac.compare_digest(candidate, secret) for secret in secrets)
