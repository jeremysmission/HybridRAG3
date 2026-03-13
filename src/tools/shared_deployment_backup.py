from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

from src.api.query_threads import conversation_history_db_path
from src.core.config import load_config
from src.core.index_qc import build_index_fingerprint, compare_fingerprints, inspect_index_database


_MAIN_DB_FINGERPRINT_LABEL = "database/main.sqlite3"
_HISTORY_DB_FINGERPRINT_LABEL = "history/query_history.sqlite3"


def default_shared_backup_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "output" / "shared_backups"


def default_shared_restore_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / "output" / "shared_restore_drills"


def create_shared_backup_bundle(
    *,
    project_root: str | Path = ".",
    database_path: str | Path | None = None,
    output_root: str | Path | None = None,
    timestamp: datetime | None = None,
    include_logs: bool = True,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    created_at = _normalize_timestamp(timestamp)
    main_db = _resolve_main_database_path(root, database_path)
    history_db = Path(conversation_history_db_path(str(main_db))).resolve()
    bundle_root = Path(output_root).resolve() if output_root else default_shared_backup_dir(root)
    bundle_dir = bundle_root / "{}_shared_deployment_backup".format(
        created_at.strftime("%Y-%m-%d_%H%M%S")
    )
    payload_dir = bundle_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []

    for category, path in [
        ("database", main_db),
        ("history", history_db),
        ("config", root / "config" / "config.yaml"),
        ("config", root / "config" / "user_modes.yaml"),
    ]:
        record = _copy_target(
            category=category,
            source_path=Path(path),
            payload_dir=payload_dir,
        )
        if record is None:
            missing.append({"category": category, "source_path": str(Path(path).resolve())})
        else:
            entries.append(record)

    if include_logs:
        logs_root = root / "logs"
        if logs_root.exists():
            for file_path in sorted(p for p in logs_root.rglob("*") if p.is_file()):
                record = _copy_target(
                    category="logs",
                    source_path=file_path,
                    payload_dir=payload_dir,
                    relative_root=logs_root,
                )
                if record is not None:
                    entries.append(record)

    summary = _build_backup_summary(main_db, history_db, entries, missing)
    manifest = {
        "bundle_schema_version": 1,
        "created_at": created_at.isoformat(timespec="seconds"),
        "project_root": str(root),
        "bundle_dir": str(bundle_dir),
        "payload_dir": str(payload_dir),
        "main_database_path": str(main_db),
        "history_database_path": str(history_db),
        "include_logs": bool(include_logs),
        "secret_inventory_required": True,
        "secret_inventory_note": (
            "Shared auth tokens, browser session secrets, proxy secrets, and "
            "history encryption keys are not copied into the repo backup bundle. "
            "Store them in the approved secure operator inventory."
        ),
        "files": entries,
        "missing": missing,
        "summary": summary,
    }
    manifest_path = bundle_dir / "backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "bundle_dir": str(bundle_dir),
        "manifest_path": str(manifest_path),
        "summary": summary,
        "missing": missing,
    }


def verify_shared_backup_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    root = Path(bundle_dir).resolve()
    manifest = _load_manifest(root)
    if manifest is None:
        return {
            "ok": False,
            "bundle_dir": str(root),
            "detail": "backup_manifest.json not found",
            "files_checked": 0,
            "files_missing": 0,
            "hash_mismatches": 0,
            "sqlite_failures": [],
            "main_database_compare": {"matches": False, "detail": "manifest missing"},
            "history_database_compare": {"matches": False, "detail": "manifest missing"},
        }

    files = list(manifest.get("files", []) or [])
    files_checked = 0
    files_missing = 0
    hash_mismatches = 0
    sqlite_failures: list[dict[str, str]] = []

    for entry in files:
        backup_path = Path(str(entry.get("backup_path", ""))).resolve()
        files_checked += 1
        if not backup_path.exists():
            files_missing += 1
            continue
        expected_hash = str(entry.get("sha256", "")).strip().lower()
        actual_hash = _sha256_file(backup_path)
        if expected_hash and actual_hash != expected_hash:
            hash_mismatches += 1
        if str(entry.get("category", "")) in ("database", "history"):
            quick_check = _sqlite_quick_check(backup_path)
            if quick_check != "ok":
                sqlite_failures.append({"path": str(backup_path), "detail": quick_check})

    summary = dict(manifest.get("summary", {}) or {})
    main_entry = _find_file_entry(files, "database")
    history_entry = _find_file_entry(files, "history")
    main_compare = _compare_saved_fingerprint(
        expected_summary=dict(summary.get("main_database", {}) or {}),
        path=Path(str(main_entry.get("backup_path", ""))).resolve() if main_entry else None,
        label=_MAIN_DB_FINGERPRINT_LABEL,
    )
    history_compare = _compare_saved_fingerprint(
        expected_summary=dict(summary.get("history_database", {}) or {}),
        path=Path(str(history_entry.get("backup_path", ""))).resolve() if history_entry else None,
        label=_HISTORY_DB_FINGERPRINT_LABEL,
    )
    return {
        "ok": (
            files_missing == 0
            and hash_mismatches == 0
            and not sqlite_failures
            and bool(main_compare.get("matches"))
            and bool(history_compare.get("matches"))
        ),
        "bundle_dir": str(root),
        "manifest_path": str(root / "backup_manifest.json"),
        "files_checked": files_checked,
        "files_missing": files_missing,
        "hash_mismatches": hash_mismatches,
        "sqlite_failures": sqlite_failures,
        "missing_declared": list(manifest.get("missing", []) or []),
        "main_database_compare": main_compare,
        "history_database_compare": history_compare,
    }


def run_shared_restore_drill(
    bundle_dir: str | Path,
    *,
    restore_root: str | Path | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    bundle_root = Path(bundle_dir).resolve()
    manifest = _load_manifest(bundle_root)
    if manifest is None:
        return {
            "ok": False,
            "bundle_dir": str(bundle_root),
            "detail": "backup_manifest.json not found",
            "files_restored": 0,
            "files_missing": 0,
            "hash_mismatches": 0,
            "sqlite_failures": [],
            "main_database_compare": {"matches": False, "detail": "manifest missing"},
            "history_database_compare": {"matches": False, "detail": "manifest missing"},
        }

    project_root = Path(str(manifest.get("project_root", "."))).resolve()
    restored_at = _normalize_timestamp(timestamp)
    target_root = Path(restore_root).resolve() if restore_root else default_shared_restore_dir(project_root)
    restore_dir = target_root / "{}_shared_restore_drill".format(
        restored_at.strftime("%Y-%m-%d_%H%M%S")
    )
    restored_payload_dir = restore_dir / "payload"
    restored_payload_dir.mkdir(parents=True, exist_ok=True)

    files = list(manifest.get("files", []) or [])
    files_restored = 0
    files_missing = 0
    hash_mismatches = 0
    sqlite_failures: list[dict[str, str]] = []
    restored_files: list[dict[str, Any]] = []

    for entry in files:
        backup_path = Path(str(entry.get("backup_path", ""))).resolve()
        relative_path = str(entry.get("relative_path", "")).strip()
        if not backup_path.exists():
            files_missing += 1
            continue
        destination = restored_payload_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, destination)
        files_restored += 1

        actual_hash = _sha256_file(destination)
        expected_hash = str(entry.get("sha256", "")).strip().lower()
        if expected_hash and actual_hash != expected_hash:
            hash_mismatches += 1

        if str(entry.get("category", "")) in ("database", "history"):
            quick_check = _sqlite_quick_check(destination)
            if quick_check != "ok":
                sqlite_failures.append({"path": str(destination), "detail": quick_check})

        restored_files.append(
            {
                "category": str(entry.get("category", "")),
                "relative_path": relative_path,
                "restored_path": str(destination.resolve()),
                "sha256": actual_hash,
            }
        )

    summary = dict(manifest.get("summary", {}) or {})
    restored_main = _find_restored_path(restored_files, "database")
    restored_history = _find_restored_path(restored_files, "history")
    main_compare = _compare_saved_fingerprint(
        expected_summary=dict(summary.get("main_database", {}) or {}),
        path=restored_main,
        label=_MAIN_DB_FINGERPRINT_LABEL,
    )
    history_compare = _compare_saved_fingerprint(
        expected_summary=dict(summary.get("history_database", {}) or {}),
        path=restored_history,
        label=_HISTORY_DB_FINGERPRINT_LABEL,
    )
    return {
        "ok": (
            files_missing == 0
            and hash_mismatches == 0
            and not sqlite_failures
            and bool(main_compare.get("matches"))
            and bool(history_compare.get("matches"))
        ),
        "bundle_dir": str(bundle_root),
        "restore_dir": str(restore_dir),
        "manifest_path": str(bundle_root / "backup_manifest.json"),
        "files_restored": files_restored,
        "files_missing": files_missing,
        "hash_mismatches": hash_mismatches,
        "sqlite_failures": sqlite_failures,
        "main_database_compare": main_compare,
        "history_database_compare": history_compare,
        "restored_files": restored_files,
    }


def format_backup_console_summary(result: dict[str, Any]) -> str:
    summary = dict(result.get("summary", {}) or {})
    lines = [
        "HYBRIDRAG SHARED DEPLOYMENT BACKUP",
        "Bundle: {}".format(str(result.get("bundle_dir", ""))),
        "Files copied: {}".format(int(summary.get("copied_files", 0) or 0)),
        "Missing optional files: {}".format(int(summary.get("missing_files", 0) or 0)),
    ]
    main_db = dict(summary.get("main_database", {}) or {})
    history_db = dict(summary.get("history_database", {}) or {})
    if main_db:
        lines.append(
            "Main DB: chunks={} sources={} quick_check={}".format(
                int(main_db.get("chunk_count", 0) or 0),
                int(main_db.get("source_count", 0) or 0),
                str(main_db.get("quick_check", "")),
            )
        )
    if history_db:
        lines.append(
            "History DB: threads={} turns={} quick_check={}".format(
                int(history_db.get("thread_count", 0) or 0),
                int(history_db.get("turn_count", 0) or 0),
                str(history_db.get("quick_check", "")),
            )
        )
    return "\n".join(lines)


def format_backup_verify_summary(result: dict[str, Any]) -> str:
    main_compare = dict(result.get("main_database_compare", {}) or {})
    history_compare = dict(result.get("history_database_compare", {}) or {})
    lines = [
        "HYBRIDRAG BACKUP VERIFY",
        "Bundle: {}".format(str(result.get("bundle_dir", ""))),
        "Files checked: {}".format(int(result.get("files_checked", 0) or 0)),
        "Files missing: {}".format(int(result.get("files_missing", 0) or 0)),
        "Hash mismatches: {}".format(int(result.get("hash_mismatches", 0) or 0)),
        "SQLite failures: {}".format(len(list(result.get("sqlite_failures", []) or []))),
        "Main DB fingerprint match: {}".format(bool(main_compare.get("matches"))),
        "History DB fingerprint match: {}".format(bool(history_compare.get("matches"))),
    ]
    return "\n".join(lines)


def format_restore_drill_summary(result: dict[str, Any]) -> str:
    main_compare = dict(result.get("main_database_compare", {}) or {})
    history_compare = dict(result.get("history_database_compare", {}) or {})
    lines = [
        "HYBRIDRAG RESTORE DRILL",
        "Bundle: {}".format(str(result.get("bundle_dir", ""))),
        "Restore dir: {}".format(str(result.get("restore_dir", ""))),
        "Files restored: {}".format(int(result.get("files_restored", 0) or 0)),
        "Files missing: {}".format(int(result.get("files_missing", 0) or 0)),
        "Hash mismatches: {}".format(int(result.get("hash_mismatches", 0) or 0)),
        "SQLite failures: {}".format(len(list(result.get("sqlite_failures", []) or []))),
        "Main DB fingerprint match: {}".format(bool(main_compare.get("matches"))),
        "History DB fingerprint match: {}".format(bool(history_compare.get("matches"))),
    ]
    return "\n".join(lines)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create, verify, and non-destructively restore HybridRAG shared "
            "deployment backup bundles."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create a timestamped backup bundle.")
    create_parser.add_argument("--project-root", default=".", help="HybridRAG project root.")
    create_parser.add_argument("--database-path", default="", help="Optional override for the main SQLite DB.")
    create_parser.add_argument("--output-root", default="", help="Optional backup output root.")
    create_parser.add_argument(
        "--timestamp",
        default="",
        help="Optional timestamp override, for example 2026-03-13_104500.",
    )
    create_parser.add_argument(
        "--skip-logs",
        action="store_true",
        help="Do not copy the repo logs directory into the bundle.",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify an existing backup bundle.")
    verify_parser.add_argument("bundle_dir", help="Path to the backup bundle directory.")

    restore_parser = subparsers.add_parser(
        "restore-drill",
        help="Stage a non-destructive restore drill from an existing backup bundle.",
    )
    restore_parser.add_argument("bundle_dir", help="Path to the backup bundle directory.")
    restore_parser.add_argument("--restore-root", default="", help="Optional restore output root.")
    restore_parser.add_argument(
        "--timestamp",
        default="",
        help="Optional timestamp override, for example 2026-03-13_105500.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv if argv is not None else sys.argv[1:])
    if not args_list or args_list[0].startswith("-"):
        args_list = ["create", *args_list]
    parser = build_cli_parser()
    args = parser.parse_args(args_list)

    if args.command == "create":
        result = create_shared_backup_bundle(
            project_root=args.project_root,
            database_path=args.database_path or None,
            output_root=args.output_root or None,
            timestamp=_parse_timestamp(args.timestamp),
            include_logs=not bool(args.skip_logs),
        )
        print(format_backup_console_summary(result))
        print("Saved manifest: {}".format(str(result.get("manifest_path", ""))))
        return 0 if result.get("ok") else 1

    if args.command == "verify":
        result = verify_shared_backup_bundle(args.bundle_dir)
        print(format_backup_verify_summary(result))
        return 0 if result.get("ok") else 1

    if args.command == "restore-drill":
        result = run_shared_restore_drill(
            args.bundle_dir,
            restore_root=args.restore_root or None,
            timestamp=_parse_timestamp(args.timestamp),
        )
        print(format_restore_drill_summary(result))
        return 0 if result.get("ok") else 1

    parser.print_help()
    return 1


def _parse_timestamp(raw_value: str) -> datetime | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d_%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(raw)


def _normalize_timestamp(value: datetime | None) -> datetime:
    current = value or datetime.now().astimezone()
    return current.astimezone()


def _resolve_main_database_path(
    project_root: Path,
    database_path: str | Path | None,
) -> Path:
    if database_path:
        return Path(database_path).expanduser().resolve()
    config = load_config(str(project_root))
    resolved = str(config.paths.database or "").strip()
    if not resolved:
        raise ValueError("No database path configured for the shared deployment backup.")
    return Path(resolved).expanduser().resolve()


def _copy_target(
    *,
    category: str,
    source_path: Path,
    payload_dir: Path,
    relative_root: Path | None = None,
) -> dict[str, Any] | None:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        return None
    relative = Path(source.name)
    if relative_root is not None:
        relative = source.relative_to(relative_root)
    relative_path = Path(category) / relative
    destination = payload_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    stat = destination.stat()
    return {
        "category": category,
        "relative_path": str(relative_path).replace("\\", "/"),
        "source_path": str(source),
        "backup_path": str(destination.resolve()),
        "size_bytes": int(stat.st_size),
        "sha256": _sha256_file(destination),
    }


def _build_backup_summary(
    main_db: Path,
    history_db: Path,
    entries: list[dict[str, Any]],
    missing: list[dict[str, str]],
) -> dict[str, Any]:
    main_summary_path = _entry_backup_path(entries, "database") or main_db
    history_summary_path = _entry_backup_path(entries, "history") or history_db
    return {
        "copied_files": len(entries),
        "missing_files": len(missing),
        "main_database": _main_database_summary(main_summary_path),
        "history_database": _history_database_summary(history_summary_path),
    }


def _main_database_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    stats = inspect_index_database(path)
    return {
        "exists": True,
        "quick_check": _sqlite_quick_check(path),
        "chunk_count": int(stats.get("chunk_count", 0) or 0),
        "source_count": int(stats.get("source_count", 0) or 0),
        "fingerprint": _logical_database_fingerprint(path, _MAIN_DB_FINGERPRINT_LABEL),
    }


def _history_database_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    thread_count = 0
    turn_count = 0
    con = sqlite3.connect(str(path))
    try:
        thread_count = int(
            con.execute("SELECT COUNT(*) FROM conversation_threads").fetchone()[0] or 0
        )
        turn_count = int(
            con.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0] or 0
        )
    finally:
        con.close()
    return {
        "exists": True,
        "quick_check": _sqlite_quick_check(path),
        "thread_count": thread_count,
        "turn_count": turn_count,
        "fingerprint": _logical_database_fingerprint(path, _HISTORY_DB_FINGERPRINT_LABEL),
    }


def _load_manifest(bundle_dir: Path) -> dict[str, Any] | None:
    manifest_path = bundle_dir / "backup_manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _find_file_entry(files: list[dict[str, Any]], category: str) -> dict[str, Any] | None:
    for entry in files:
        if str(entry.get("category", "")) == category:
            return entry
    return None


def _entry_backup_path(entries: list[dict[str, Any]], category: str) -> Path | None:
    entry = _find_file_entry(entries, category)
    if entry is None:
        return None
    backup_path = str(entry.get("backup_path", "")).strip()
    if not backup_path:
        return None
    return Path(backup_path).resolve()


def _find_restored_path(files: list[dict[str, Any]], category: str) -> Path | None:
    for entry in files:
        if str(entry.get("category", "")) == category:
            return Path(str(entry.get("restored_path", ""))).resolve()
    return None


def _compare_saved_fingerprint(
    *,
    expected_summary: dict[str, Any],
    path: Path | None,
    label: str,
) -> dict[str, Any]:
    expected_fingerprint = dict(expected_summary.get("fingerprint", {}) or {})
    if not expected_fingerprint:
        return {"matches": False, "detail": "expected fingerprint missing"}
    if path is None or not path.exists():
        return {"matches": False, "detail": "target file missing"}
    current = _logical_database_fingerprint(path, label)
    comparison = compare_fingerprints(current, expected_fingerprint)
    comparison["matches"] = bool(comparison.get("matches"))
    comparison["current_combined_sha256"] = current.get("combined_sha256", "")
    comparison["expected_combined_sha256"] = expected_fingerprint.get("combined_sha256", "")
    return comparison


def _logical_database_fingerprint(path: Path, label: str) -> dict[str, Any]:
    fingerprint = build_index_fingerprint(path)
    files: list[dict[str, Any]] = []
    combined = hashlib.sha256()
    for item in list(fingerprint.get("files", []) or []):
        record = {
            "path": label,
            "size_bytes": int(item.get("size_bytes", 0) or 0),
            "sha256": str(item.get("sha256", "")),
        }
        files.append(record)
        combined.update(record["path"].encode("utf-8"))
        combined.update(str(record["size_bytes"]).encode("ascii"))
        combined.update(record["sha256"].encode("ascii"))
    return {
        "artifact_count": len(files),
        "combined_sha256": combined.hexdigest(),
        "files": files,
    }


def _sqlite_quick_check(path: Path) -> str:
    con = sqlite3.connect(str(path))
    try:
        row = con.execute("PRAGMA quick_check").fetchone()
        return str((row or ["unknown"])[0] or "unknown")
    except Exception as exc:
        return "error: {}".format(exc)
    finally:
        con.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
