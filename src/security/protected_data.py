from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


HISTORY_PROTECTED_PREFIX = "enc:aesgcm:v1:"
_HISTORY_AAD = b"hybridrag:conversation-history:v1"
_TRUTHY = {"1", "true", "yes", "on"}


class ProtectedDataUnavailableError(RuntimeError):
    """Raised when protected data cannot be decrypted with current config."""


def history_encryption_enabled() -> bool:
    """Return whether new conversation-history writes are encrypted."""
    return bool(_history_primary_secret())


def history_encryption_rotation_enabled() -> bool:
    """Return whether previous history-encryption keys remain readable."""
    return bool(_history_primary_secret() and _history_previous_secret())


def history_encryption_source() -> str:
    """Describe the configured conversation-history key source."""
    if _history_primary_secret():
        return "env:HYBRIDRAG_HISTORY_ENCRYPTION_KEY"
    if _history_previous_secret():
        return "env:HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS (decrypt-only)"
    return "disabled"


def history_secure_delete_enabled() -> bool:
    """Return whether the history DB should zero deleted content when possible."""
    return history_encryption_enabled() or _env_truthy("HYBRIDRAG_HISTORY_SECURE_DELETE")


def protect_history_text(value: str | None) -> str | None:
    """Encrypt one conversation-history field when protection is enabled."""
    if value is None:
        return None
    text = str(value)
    if text.startswith(HISTORY_PROTECTED_PREFIX):
        return text
    key = _history_primary_key()
    if key is None:
        return text

    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, text.encode("utf-8"), _HISTORY_AAD)
    token = _b64url_encode(nonce + encrypted)
    return f"{HISTORY_PROTECTED_PREFIX}{token}"


def restore_history_text(value: str | None) -> str | None:
    """Decrypt one conversation-history field when it carries a protected marker."""
    if value is None:
        return None
    text = str(value)
    if not text.startswith(HISTORY_PROTECTED_PREFIX):
        return text

    payload = text[len(HISTORY_PROTECTED_PREFIX):]
    try:
        raw = _b64url_decode(payload)
    except ValueError as exc:
        raise ProtectedDataUnavailableError(
            "Conversation history contains unreadable protected data."
        ) from exc
    if len(raw) < 13:
        raise ProtectedDataUnavailableError(
            "Conversation history contains unreadable protected data."
        )

    keys = _history_secret_keys()
    if not keys:
        raise ProtectedDataUnavailableError(
            "Conversation history is encrypted at rest. "
            "Configure HYBRIDRAG_HISTORY_ENCRYPTION_KEY to read saved threads."
        )

    nonce = raw[:12]
    encrypted = raw[12:]
    for key in keys:
        try:
            plaintext = AESGCM(key).decrypt(nonce, encrypted, _HISTORY_AAD)
            return plaintext.decode("utf-8")
        except InvalidTag:
            continue
        except UnicodeDecodeError as exc:
            raise ProtectedDataUnavailableError(
                "Conversation history contains unreadable protected data."
            ) from exc

    raise ProtectedDataUnavailableError(
        "Conversation history is encrypted with a different key. "
        "Reconfigure HYBRIDRAG_HISTORY_ENCRYPTION_KEY or "
        "HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS."
    )


def rewrap_history_text(value: str | None) -> str | None:
    """Re-encrypt one history field with the current key when available."""
    if value is None:
        return None
    text = str(value)
    if text.startswith(HISTORY_PROTECTED_PREFIX):
        try:
            text = str(restore_history_text(text) or "")
        except ProtectedDataUnavailableError:
            return value
    return protect_history_text(text)


def harden_history_storage_path(path: str) -> None:
    """Best-effort restrictive permissions for the history DB and parent dir."""
    target = Path(str(path or ""))
    if not str(target):
        return
    try:
        if target.parent.exists():
            os.chmod(target.parent, 0o700)
    except Exception:
        pass
    try:
        if target.exists():
            os.chmod(target, 0o600)
    except Exception:
        pass


def _history_primary_secret() -> str:
    return (os.environ.get("HYBRIDRAG_HISTORY_ENCRYPTION_KEY") or "").strip()


def _history_previous_secret() -> str:
    return (os.environ.get("HYBRIDRAG_HISTORY_ENCRYPTION_KEY_PREVIOUS") or "").strip()


def _history_secret_keys() -> tuple[bytes, ...]:
    values: list[bytes] = []
    for raw_secret in (_history_primary_secret(), _history_previous_secret()):
        if not raw_secret:
            continue
        for secret in (piece.strip() for piece in raw_secret.split(",")):
            if not secret:
                continue
            key = hashlib.sha256(secret.encode("utf-8")).digest()
            if key not in values:
                values.append(key)
    return tuple(values)


def _history_primary_key() -> bytes | None:
    keys = _history_secret_keys()
    return keys[0] if keys else None


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY
