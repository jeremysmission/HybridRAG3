from __future__ import annotations

import os
from pathlib import Path

from src.api.query_threads import conversation_history_db_path


_TRUTHY = {"1", "true", "yes", "on"}
_ROOT_ENV_NAMES = (
    "HYBRIDRAG_PROTECTED_STORAGE_ROOTS",
    "HYBRIDRAG_PROTECTED_DATA_ROOTS",
)


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def _normalize_path(value: str) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    try:
        return str(Path(text).expanduser().resolve(strict=False))
    except Exception:
        return os.path.abspath(os.path.expanduser(text))


def _comparison_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "")))


def _unique_paths(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_path(value)
        if not normalized:
            continue
        key = _comparison_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _split_root_values(raw: str) -> list[str]:
    values: list[str] = []
    for line in str(raw or "").replace("\r", "\n").split("\n"):
        for piece in line.split(";"):
            text = piece.strip()
            if text:
                values.append(text)
    return values


def protected_storage_required() -> bool:
    """Return whether the server must reject unprotected data paths."""
    return _env_truthy("HYBRIDRAG_REQUIRE_PROTECTED_STORAGE")


def protected_storage_roots() -> list[str]:
    """Return normalized protected-root directories from env config."""
    values: list[str] = []
    for env_name in _ROOT_ENV_NAMES:
        values.extend(_split_root_values(os.environ.get(env_name) or ""))
    return _unique_paths(values)


def protected_storage_mode() -> str:
    """Summarize the active protected-storage posture for operator surfaces."""
    if protected_storage_required():
        return "required"
    if protected_storage_roots():
        return "advisory"
    return "disabled"


def tracked_storage_paths(database_path: str) -> list[str]:
    """Return the main and conversation-history SQLite paths under protection review."""
    values: list[str] = []
    primary = _normalize_path(database_path)
    if primary:
        values.append(primary)
        history = _normalize_path(conversation_history_db_path(primary))
        if history:
            values.append(history)
    return _unique_paths(values)


def _path_is_within_root(path: str, root: str) -> bool:
    normalized_path = _comparison_key(path)
    normalized_root = _comparison_key(root)
    if not normalized_path or not normalized_root:
        return False
    if normalized_path == normalized_root:
        return True
    return normalized_path.startswith(normalized_root + os.sep)


def _partition_paths(database_path: str) -> tuple[list[str], list[str], list[str]]:
    tracked = tracked_storage_paths(database_path)
    roots = protected_storage_roots()
    if not roots:
        return tracked, [], tracked

    protected: list[str] = []
    unprotected: list[str] = []
    for path in tracked:
        if any(_path_is_within_root(path, root) for root in roots):
            protected.append(path)
        else:
            unprotected.append(path)
    return tracked, protected, unprotected


def _describe_count(label: str, count: int) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {label}{suffix}"


def _build_summary(
    *,
    mode: str,
    roots: list[str],
    tracked: list[str],
    protected: list[str],
    unprotected: list[str],
) -> str:
    if not tracked:
        return "No configured data paths were available for protected-storage review."
    if not roots:
        if mode == "required":
            return (
                "Protected storage is required, but no protected roots are configured. "
                "Set HYBRIDRAG_PROTECTED_STORAGE_ROOTS before startup."
            )
        return (
            "Protected roots are not configured. Data-path review is advisory only."
        )
    if not unprotected:
        return "All tracked data paths are under configured protected roots."
    counts = (
        f"{_describe_count('tracked path', len(tracked))}, "
        f"{_describe_count('protected path', len(protected))}, "
        f"{_describe_count('unprotected path', len(unprotected))}."
    )
    if mode == "required":
        return (
            "Protected storage is required and some tracked data paths fall outside "
            f"the configured roots. {counts}"
        )
    return (
        "Some tracked data paths fall outside the configured protected roots. "
        f"{counts}"
    )


def build_storage_protection_snapshot(database_path: str) -> dict[str, object]:
    """Return the Admin-console snapshot for protected data storage posture."""
    roots = protected_storage_roots()
    tracked, protected, unprotected = _partition_paths(database_path)
    mode = protected_storage_mode()
    return {
        "mode": mode,
        "required": protected_storage_required(),
        "roots": roots,
        "tracked_paths": tracked,
        "protected_paths": protected,
        "unprotected_paths": unprotected,
        "all_paths_protected": bool(tracked) and not unprotected and bool(roots),
        "summary": _build_summary(
            mode=mode,
            roots=roots,
            tracked=tracked,
            protected=protected,
            unprotected=unprotected,
        ),
    }


def enforce_storage_protection(database_path: str) -> None:
    """Raise when protected storage is required and any tracked path is outside the roots."""
    snapshot = build_storage_protection_snapshot(database_path)
    unprotected = list(snapshot.get("unprotected_paths", []) or [])
    if snapshot.get("required") and unprotected:
        joined = "; ".join(unprotected)
        raise RuntimeError(
            "Protected storage is required, but these data paths are outside the "
            f"configured protected roots: {joined}"
        )


def harden_storage_path(path: str) -> None:
    """Best-effort restrictive permissions for one SQLite path and its parent dir."""
    target = Path(str(path or ""))
    if not str(target):
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
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


def harden_configured_storage_paths(database_path: str) -> None:
    """Apply best-effort permission tightening to the tracked SQLite files."""
    for path in tracked_storage_paths(database_path):
        harden_storage_path(path)
