from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.security.shared_deployment_auth import (
    browser_session_fallback_source,
    resolve_shared_api_auth_status,
)


SESSION_COOKIE_NAME = "hybridrag_browser_session"
_DEFAULT_TTL_SECONDS = 8 * 60 * 60
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BrowserSession:
    """Validated browser session derived from the shared API token."""

    actor: str
    actor_source: str
    issued_at: int
    expires_at: int


def session_ttl_seconds() -> int:
    """Return the configured browser-session lifetime."""
    raw = (os.environ.get("HYBRIDRAG_BROWSER_SESSION_TTL_SECONDS") or "").strip()
    if raw.isdigit():
        return max(300, int(raw))
    return _DEFAULT_TTL_SECONDS


def browser_session_enabled() -> bool:
    """Return whether browser-session signing is configured."""
    return bool(_session_secrets())


def browser_session_secret_source() -> str:
    """Describe which configured secret source signs browser sessions."""
    return browser_session_fallback_source()


def browser_session_rotation_enabled() -> bool:
    """Return whether previous browser-session secrets are accepted."""
    return bool(
        (os.environ.get("HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS") or "").strip()
        or resolve_shared_api_auth_status().rotation_enabled
    )


def browser_session_invalid_before_iso() -> Optional[str]:
    """Return the forced browser-session invalidation cutoff, if configured."""
    cutoff = _session_invalid_before_unix()
    if cutoff is None:
        return None
    return datetime.fromtimestamp(cutoff, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def create_browser_session(*, actor: str, actor_source: str = "session_cookie") -> str:
    """Create a signed browser-session cookie value."""
    secret = _primary_session_secret()
    if secret is None:
        raise ValueError("Browser sessions are disabled because no signing secret is configured.")

    now = int(time.time())
    payload = {
        "actor": str(actor or "shared-token"),
        "actor_source": str(actor_source or "session_cookie"),
        "issued_at": now,
        "expires_at": now + session_ttl_seconds(),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64url_encode(payload_bytes)
    signature = _sign(secret, encoded.encode("ascii"))
    return f"{encoded}.{signature}"


def parse_browser_session(raw_value: str | None) -> Optional[BrowserSession]:
    """Parse and validate a browser-session cookie value."""
    if not raw_value or "." not in raw_value:
        return None
    secrets = _session_secrets()
    if not secrets:
        return None

    encoded, signature = raw_value.split(".", 1)
    matched_secret = None
    for secret in secrets:
        expected = _sign(secret, encoded.encode("ascii"))
        if hmac.compare_digest(signature, expected):
            matched_secret = secret
            break
    if matched_secret is None:
        return None

    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    actor = str(payload.get("actor") or "").strip()
    actor_source = str(payload.get("actor_source") or "session_cookie").strip()
    issued_at = int(payload.get("issued_at") or 0)
    expires_at = int(payload.get("expires_at") or 0)
    now = int(time.time())
    if not actor or issued_at <= 0 or expires_at <= issued_at or expires_at <= now:
        return None
    invalid_before = _session_invalid_before_unix()
    if invalid_before is not None and issued_at < invalid_before:
        return None

    return BrowserSession(
        actor=actor,
        actor_source=actor_source,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def cookie_should_be_secure(request_scheme: str) -> bool:
    """Determine whether the browser-session cookie should use the Secure flag."""
    if _env_truthy("HYBRIDRAG_BROWSER_SESSION_SECURE"):
        return True
    return str(request_scheme or "").strip().lower() == "https"


def _primary_session_secret() -> Optional[bytes]:
    secrets = _session_secrets()
    return secrets[0] if secrets else None


def _session_secrets() -> tuple[bytes, ...]:
    raw_values: list[str] = []
    for env_name in (
        "HYBRIDRAG_BROWSER_SESSION_SECRET",
        "HYBRIDRAG_BROWSER_SESSION_SECRET_PREVIOUS",
    ):
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            raw_values.extend(value.strip() for value in raw.split(",") if value.strip())
    if not raw_values:
        raw_values.extend(resolve_shared_api_auth_status().tokens)
    ordered: list[bytes] = []
    for value in raw_values:
        encoded = value.encode("utf-8")
        if encoded not in ordered:
            ordered.append(encoded)
    return tuple(ordered)


def _sign(secret: bytes, payload: bytes) -> str:
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    return _b64url_encode(digest)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def _session_invalid_before_unix() -> Optional[int]:
    raw = (os.environ.get("HYBRIDRAG_BROWSER_SESSION_INVALID_BEFORE") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return max(0, int(raw))
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None
