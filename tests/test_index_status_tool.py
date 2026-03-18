import os
import sqlite3
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_index_status_uses_env_bound_database_path(tmp_path):
    data_dir = tmp_path / "index_data"
    data_dir.mkdir()
    db_path = data_dir / "hybridrag.sqlite3"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE chunks (
            source_file TEXT,
            indexed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE index_runs (
            run_id TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO chunks (source_file, indexed_at) VALUES (?, ?)",
        ("smoke_doc.txt", "2026-03-17T20:11:32"),
    )
    conn.execute("INSERT INTO index_runs (run_id) VALUES (?)", ("run-1",))
    conn.commit()
    conn.close()

    env = os.environ.copy()
    env["HYBRIDRAG_PROJECT_ROOT"] = str(REPO_ROOT)
    env["HYBRIDRAG_DATA_DIR"] = str(data_dir)
    env["HYBRIDRAG_INDEX_FOLDER"] = str(tmp_path / "source_data")

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "py" / "index_status.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    output = ((result.stdout or "") + (result.stderr or "")).replace("\r\n", "\n")

    assert result.returncode == 0, output
    assert f"Database: {db_path}" in output
    assert "Chunks:   1" in output
    assert "Files:    1" in output
    assert "Total runs:   1" in output
