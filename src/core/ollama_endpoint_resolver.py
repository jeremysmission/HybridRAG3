# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the ollama endpoint resolver part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Helpers for Ollama endpoint normalization.

This module exists so GUI/config/router all share one canonical rule set.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit


_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_DEFAULT_OLLAMA_PORT = 11434


def _repair_common_loopback_typos(raw: str) -> str:
    """Fix the loopback typos most often introduced in manual config edits."""
    s = (raw or "").strip()
    if "127.0.0:" in s:
        s = s.replace("127.0.0:", "127.0.0.1:")
    if "127.0.0/" in s:
        s = s.replace("127.0.0/", "127.0.0.1/")
    return s


def _normalize_host(host: str) -> str:
    """Normalize host casing and repair common loopback shorthand."""
    value = (host or "").strip().rstrip(".")
    if not value:
        return ""
    if value == "127.0.0":
        return "127.0.0.1"
    if value.lower() == "localhost":
        return "localhost"
    return value.lower()


def _is_loopback_host(host: str) -> bool:
    """Return True when the host resolves to loopback-only traffic."""
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _strip_ollama_api_suffix(path: str) -> str:
    """Drop endpoint-level API suffixes so callers always get the base URL."""
    normalized = (path or "").strip().replace("\\", "/")
    if not normalized or normalized == "/":
        return ""

    lowered = normalized.lower()
    api_index = lowered.find("/api/")
    if api_index == -1 and lowered.endswith("/api"):
        api_index = lowered.rfind("/api")
    if api_index != -1:
        normalized = normalized[:api_index]

    normalized = normalized.rstrip("/")
    return normalized if normalized not in ("", "/") else ""


def _format_netloc(host: str, port: int | None) -> str:
    """Build a netloc string that preserves IPv6 bracket syntax."""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is None:
        return host
    return f"{host}:{port}"


def sanitize_ollama_base_url(raw: str) -> str:
    """Normalize Ollama base URLs and force loopback traffic to plain HTTP."""
    s = _repair_common_loopback_typos(raw)
    if not s:
        return _DEFAULT_OLLAMA_BASE_URL

    if "://" not in s:
        s = "http://" + s

    parts = urlsplit(s)
    host = _normalize_host(parts.hostname or "")
    if not host:
        return _DEFAULT_OLLAMA_BASE_URL

    scheme = (parts.scheme or "http").lower()
    try:
        port = parts.port
    except ValueError:
        port = None

    if _is_loopback_host(host):
        scheme = "http"
        if port is None:
            port = _DEFAULT_OLLAMA_PORT

    path = _strip_ollama_api_suffix(parts.path)
    if _is_loopback_host(host):
        path = ""
    return urlunsplit((scheme, _format_netloc(host, port), path, "", "")).rstrip("/")

