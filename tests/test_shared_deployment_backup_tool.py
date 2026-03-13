from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import src.tools.shared_deployment_backup as backup_tool
from src.api.query_threads import conversation_history_db_path
from src.tools.shared_deployment_backup import (
    create_shared_backup_bundle,
    default_shared_backup_dir,
    default_shared_restore_dir,
    run_shared_restore_drill,
    verify_shared_backup_bundle,
)


def test_default_backup_and_restore_dirs(tmp_path: Path) -> None:
    assert default_shared_backup_dir(tmp_path) == tmp_path / "output" / "shared_backups"
    assert default_shared_restore_dir(tmp_path) == tmp_path / "output" / "shared_restore_drills"


def test_create_shared_backup_bundle_copies_runtime_files(tmp_path: Path) -> None:
    project_root, main_db, _history_db = _make_shared_project(tmp_path / "project")

    result = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 10, 45, 0),
        include_logs=True,
    )

    bundle_dir = Path(result["bundle_dir"])
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert bundle_dir.exists()
    assert manifest["summary"]["main_database"]["chunk_count"] == 3
    assert manifest["summary"]["history_database"]["turn_count"] == 2
    assert manifest["summary"]["main_database"]["fingerprint"]["artifact_count"] == 1
    assert manifest["summary"]["history_database"]["fingerprint"]["artifact_count"] == 1
    assert "not copied into the repo backup bundle" in manifest["secret_inventory_note"]
    assert {
        entry["relative_path"] for entry in manifest["files"]
    } >= {
        "database/hybridrag.sqlite3",
        "history/hybridrag_query_history.sqlite3",
        "config/config.yaml",
        "config/user_modes.yaml",
        "logs/runtime.log",
    }


def test_create_shared_backup_bundle_uses_project_config_by_default(tmp_path: Path) -> None:
    project_root, main_db, _history_db = _make_shared_project(tmp_path / "project_config")

    result = create_shared_backup_bundle(
        project_root=project_root,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 10, 46, 0),
        include_logs=False,
    )

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["main_database_path"] == str(main_db.resolve())
    assert manifest["summary"]["copied_files"] == 4
    assert manifest["include_logs"] is False


def test_verify_shared_backup_bundle_reports_missing_copied_file(tmp_path: Path) -> None:
    project_root, main_db, _history_db = _make_shared_project(tmp_path / "project_verify")

    result = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 10, 47, 0),
        include_logs=False,
    )

    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    broken_path = Path(manifest["files"][0]["backup_path"])
    broken_path.unlink()

    verify = verify_shared_backup_bundle(Path(result["bundle_dir"]))
    assert verify["ok"] is False
    assert verify["files_missing"] == 1


def test_restore_drill_restores_bundle_and_matches_fingerprints(tmp_path: Path) -> None:
    project_root, main_db, _history_db = _make_shared_project(tmp_path / "project_restore")

    result = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 10, 48, 0),
        include_logs=True,
    )

    restore = run_shared_restore_drill(
        result["bundle_dir"],
        restore_root=tmp_path / "restore",
        timestamp=datetime(2026, 3, 13, 10, 49, 0),
    )

    assert restore["ok"] is True
    assert restore["files_restored"] == 5
    assert restore["files_missing"] == 0
    assert restore["hash_mismatches"] == 0
    assert restore["sqlite_failures"] == []
    assert restore["main_database_compare"]["matches"] is True
    assert restore["history_database_compare"]["matches"] is True


def test_backup_summary_uses_copied_history_snapshot_when_live_history_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, main_db, history_db = _make_shared_project(tmp_path / "project_race")
    original_copy_target = backup_tool._copy_target

    def racing_copy_target(**kwargs):
        record = original_copy_target(**kwargs)
        if kwargs.get("category") == "history":
            _append_history_turn(history_db, "turn-3", "assistant", "post-copy drift")
        return record

    monkeypatch.setattr(backup_tool, "_copy_target", racing_copy_target)

    result = create_shared_backup_bundle(
        project_root=project_root,
        database_path=main_db,
        output_root=tmp_path / "backups",
        timestamp=datetime(2026, 3, 13, 10, 48, 30),
        include_logs=False,
    )

    verify = verify_shared_backup_bundle(Path(result["bundle_dir"]))
    assert verify["ok"] is True
    assert verify["history_database_compare"]["matches"] is True


def test_cli_create_verify_and_restore_drill_round_trip(tmp_path: Path) -> None:
    project_root, main_db, _history_db = _make_shared_project(tmp_path / "project_cli")
    repo_root = Path(__file__).resolve().parents[1]
    backup_root = tmp_path / "cli_backups"
    restore_root = tmp_path / "cli_restore"
    bundle_dir = backup_root / "2026-03-13_105000_shared_deployment_backup"
    script = repo_root / "tools" / "shared_deployment_backup.py"

    create = subprocess.run(
        [
            sys.executable,
            str(script),
            "create",
            "--project-root",
            str(project_root),
            "--database-path",
            str(main_db),
            "--output-root",
            str(backup_root),
            "--timestamp",
            "2026-03-13_105000",
            "--skip-logs",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert create.returncode == 0, create.stderr
    assert "HYBRIDRAG SHARED DEPLOYMENT BACKUP" in create.stdout
    assert bundle_dir.exists()

    verify = subprocess.run(
        [sys.executable, str(script), "verify", str(bundle_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr
    assert "HYBRIDRAG BACKUP VERIFY" in verify.stdout
    assert "Main DB fingerprint match: True" in verify.stdout

    restore = subprocess.run(
        [
            sys.executable,
            str(script),
            "restore-drill",
            str(bundle_dir),
            "--restore-root",
            str(restore_root),
            "--timestamp",
            "2026-03-13_105100",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert restore.returncode == 0, restore.stderr
    assert "HYBRIDRAG RESTORE DRILL" in restore.stdout
    assert "History DB fingerprint match: True" in restore.stdout


def _make_shared_project(project_root: Path) -> tuple[Path, Path, Path]:
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
            "mode: offline",
            "",
        ]
    )
    (project_root / "config" / "config.yaml").write_text(config_yaml, encoding="utf-8")
    (project_root / "config" / "user_modes.yaml").write_text("modes: {}\n", encoding="utf-8")
    (project_root / "logs" / "runtime.log").write_text("backup test log\n", encoding="utf-8")
    return project_root, main_db, history_db


def _create_main_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, source_path TEXT)")
        con.executemany(
            "INSERT INTO chunks (source_path) VALUES (?)",
            [
                ("docs/alpha.txt",),
                ("docs/alpha.txt",),
                ("docs/beta.txt",),
            ],
        )
        con.commit()
    finally:
        con.close()


def _create_history_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE conversation_threads (
                thread_id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE conversation_turns (
                turn_id TEXT PRIMARY KEY,
                thread_id TEXT,
                role TEXT,
                message_text TEXT,
                created_at TEXT
            )
            """
        )
        con.execute(
            "INSERT INTO conversation_threads (thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("thread-1", "Backup test", "2026-03-13T10:00:00", "2026-03-13T10:00:00"),
        )
        con.executemany(
            "INSERT INTO conversation_turns (turn_id, thread_id, role, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("turn-1", "thread-1", "user", "hello", "2026-03-13T10:00:01"),
                ("turn-2", "thread-1", "assistant", "hi", "2026-03-13T10:00:02"),
            ],
        )
        con.commit()
    finally:
        con.close()


def _append_history_turn(
    path: Path,
    turn_id: str,
    role: str,
    message_text: str,
) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            "INSERT INTO conversation_turns (turn_id, thread_id, role, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (turn_id, "thread-1", role, message_text, "2026-03-13T10:00:03"),
        )
        con.commit()
    finally:
        con.close()
