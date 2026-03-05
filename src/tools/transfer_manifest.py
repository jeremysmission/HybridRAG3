# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the transfer manifest part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Transfer Manifest Database (src/tools/transfer_manifest.py)
# ============================================================================
# SQLite database tracking every file in a bulk transfer operation.
# Tables: transfer_runs, source_manifest, transfer_log, skipped_files.
# Thread-safe (lock + WAL mode). All timestamps UTC ISO-8601.
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Module-level constants
# ============================================================================

_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS transfer_runs (
        run_id         TEXT NOT NULL PRIMARY KEY,
        started_at     TEXT NOT NULL,
        finished_at    TEXT,
        source_paths   TEXT,
        dest_path      TEXT,
        account        TEXT DEFAULT '',
        status         TEXT DEFAULT 'running',
        config_json    TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS source_manifest (
        source_path    TEXT NOT NULL,
        run_id         TEXT NOT NULL,
        file_size      INTEGER DEFAULT 0,
        file_mtime     REAL DEFAULT 0,
        file_ctime     REAL DEFAULT 0,
        extension      TEXT DEFAULT '',
        is_hidden      INTEGER DEFAULT 0,
        is_system      INTEGER DEFAULT 0,
        is_readonly    INTEGER DEFAULT 0,
        is_symlink     INTEGER DEFAULT 0,
        is_accessible  INTEGER DEFAULT 1,
        path_length    INTEGER DEFAULT 0,
        encoding_issue INTEGER DEFAULT 0,
        owner          TEXT DEFAULT '',
        content_hash   TEXT DEFAULT '',
        PRIMARY KEY (source_path, run_id)
    );

    CREATE TABLE IF NOT EXISTS transfer_log (
        source_path       TEXT NOT NULL,
        dest_path         TEXT DEFAULT '',
        run_id            TEXT NOT NULL,
        file_size_source  INTEGER DEFAULT 0,
        file_size_dest    INTEGER DEFAULT 0,
        hash_source       TEXT DEFAULT '',
        hash_dest         TEXT DEFAULT '',
        hash_match        INTEGER DEFAULT 0,
        transfer_start    TEXT DEFAULT '',
        transfer_end      TEXT DEFAULT '',
        duration_sec      REAL DEFAULT 0,
        speed_mbps        REAL DEFAULT 0,
        result            TEXT DEFAULT 'pending',
        retry_count       INTEGER DEFAULT 0,
        error_message     TEXT DEFAULT '',
        PRIMARY KEY (source_path, run_id)
    );

    CREATE TABLE IF NOT EXISTS skipped_files (
        source_path    TEXT NOT NULL,
        run_id         TEXT NOT NULL,
        file_size      INTEGER DEFAULT 0,
        extension      TEXT DEFAULT '',
        reason         TEXT NOT NULL,
        detail         TEXT DEFAULT '',
        logged_at      TEXT DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_manifest_hash
        ON source_manifest(content_hash);
    CREATE INDEX IF NOT EXISTS idx_manifest_run
        ON source_manifest(run_id);
    CREATE INDEX IF NOT EXISTS idx_transfer_result
        ON transfer_log(result);
    CREATE INDEX IF NOT EXISTS idx_transfer_run
        ON transfer_log(run_id);
    CREATE INDEX IF NOT EXISTS idx_skipped_reason
        ON skipped_files(reason);
    CREATE INDEX IF NOT EXISTS idx_skipped_run
        ON skipped_files(run_id);
"""


# ============================================================================
# Module-level helpers
# ============================================================================

def _utc_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _build_verification_report(
    conn: sqlite3.Connection,
    lock: threading.Lock,
    run_id: str,
) -> str:
    """Build a zero-gap verification report for a transfer run.

    Queries manifest, transfer log, and skip log, then checks that
    (transferred + skipped) == total discovered. Returns report text.
    """
    with lock:
        manifest_count = conn.execute(
            "SELECT COUNT(*) FROM source_manifest WHERE run_id=?",
            (run_id,),
        ).fetchone()[0]

        results = conn.execute(
            "SELECT result, COUNT(*) FROM transfer_log "
            "WHERE run_id=? GROUP BY result ORDER BY COUNT(*) DESC",
            (run_id,),
        ).fetchall()

        skip_results = conn.execute(
            "SELECT reason, COUNT(*), SUM(file_size) "
            "FROM skipped_files WHERE run_id=? "
            "GROUP BY reason ORDER BY COUNT(*) DESC",
            (run_id,),
        ).fetchall()

        skip_samples: Dict[str, List[Tuple]] = {}
        for reason, _, _ in skip_results:
            samples = conn.execute(
                "SELECT source_path, file_size, detail "
                "FROM skipped_files WHERE run_id=? AND reason=? LIMIT 5",
                (run_id, reason),
            ).fetchall()
            skip_samples[reason] = samples

        failed = conn.execute(
            "SELECT source_path, error_message, file_size_source "
            "FROM transfer_log WHERE run_id=? AND result='failed' "
            "LIMIT 20",
            (run_id,),
        ).fetchall()
        failed_total = conn.execute(
            "SELECT COUNT(*) FROM transfer_log "
            "WHERE run_id=? AND result='failed'",
            (run_id,),
        ).fetchone()[0]

    # Build report text (outside lock -- read-only from here)
    lines = [
        "", "=" * 70,
        "  TRANSFER VERIFICATION REPORT",
        "=" * 70, "",
        f"  Files in source manifest:  {manifest_count:,}",
    ]
    transfer_total = sum(r[1] for r in results)
    skip_total = sum(r[1] for r in skip_results)

    # Use DISTINCT union to avoid double-counting files that appear
    # in both transfer_log and skipped_files.
    distinct_accounted = conn.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT source_path FROM transfer_log WHERE run_id=?"
        "  UNION"
        "  SELECT source_path FROM skipped_files WHERE run_id=?"
        ")",
        (run_id, run_id),
    ).fetchone()[0]

    lines.append(f"  Files in transfer log:     {transfer_total:,}")
    lines.append(f"  Files in skip log:         {skip_total:,}")
    lines.append(f"  Total accounted:           {distinct_accounted:,}")
    gap = manifest_count - distinct_accounted
    if gap == 0:
        lines.append("  GAP:                       0 (ZERO-GAP VERIFIED)")
    else:
        lines.append(f"  GAP:                       {gap:,} [WARN] UNACCOUNTED")
    lines.append("")

    for result, count in results:
        lines.append(f"  [{result.upper()}] {count:,}")
    lines.append("")

    if skip_results:
        lines.append("  SKIPPED FILES:")
        for reason, count, size_sum in skip_results:
            sz = (size_sum or 0) / (1024 * 1024)
            lines.append(f"    [{reason}] {count:,} ({sz:.1f} MB)")
            for path, fsize, detail in skip_samples.get(reason, []):
                d = f" -- {detail}" if detail else ""
                lines.append(f"      {path}{d}")
            if count > 5:
                lines.append(f"      ... and {count - 5} more")
        lines.append("")

    if failed:
        lines.append(f"  FAILED FILES ({failed_total:,} total):")
        for path, err, sz in failed:
            lines.append(f"    {path} -- {err[:80]}")
        if failed_total > 20:
            lines.append(f"    ... and {failed_total - 20} more")
        lines.append("")

    lines.extend(["=" * 70, ""])
    return "\n".join(lines)


# ============================================================================
# TransferManifest class
# ============================================================================

class TransferManifest:
    """SQLite database tracking every file in a bulk transfer operation.

    Thread-safe. All timestamps stored in UTC ISO-8601.
    """

    def __init__(self, db_path: str) -> None:
        """Open or create the manifest database at db_path."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        self._pending_writes = 0
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the four database tables if they don't already exist."""
        with self._lock:
            self.conn.executescript(_SCHEMA_SQL)
            self.conn.commit()

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    def start_run(
        self, run_id: str, source_paths: List[str], dest_path: str,
        account: str = "", config_json: str = "{}",
    ) -> None:
        """Record the start of a new transfer run."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO transfer_runs "
                "(run_id, started_at, source_paths, dest_path, account, "
                "status, config_json) VALUES (?, ?, ?, ?, ?, 'running', ?)",
                (run_id, _utc_now(), json.dumps(source_paths),
                 dest_path, account, config_json),
            )
            self.conn.commit()

    def finish_run(self, run_id: str) -> None:
        """Mark a transfer run as complete with a finish timestamp."""
        with self._lock:
            self.conn.execute(
                "UPDATE transfer_runs SET finished_at=?, status='complete' "
                "WHERE run_id=?",
                (_utc_now(), run_id),
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Source manifest (ground truth)
    # ------------------------------------------------------------------

    def record_source_file(
        self, run_id: str, source_path: str, file_size: int = 0,
        file_mtime: float = 0, file_ctime: float = 0, extension: str = "",
        is_hidden: bool = False, is_system: bool = False,
        is_readonly: bool = False, is_symlink: bool = False,
        is_accessible: bool = True, path_length: int = 0,
        encoding_issue: bool = False, owner: str = "",
        content_hash: str = "",
    ) -> None:
        """Record a discovered file in the source manifest (ground truth)."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO source_manifest "
                "(source_path, run_id, file_size, file_mtime, file_ctime, "
                "extension, is_hidden, is_system, is_readonly, is_symlink, "
                "is_accessible, path_length, encoding_issue, owner, "
                "content_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_path, run_id, file_size, file_mtime, file_ctime,
                 extension, int(is_hidden), int(is_system), int(is_readonly),
                 int(is_symlink), int(is_accessible), path_length,
                 int(encoding_issue), owner, content_hash),
            )
            self._batch_commit()

    # ------------------------------------------------------------------
    # Transfer log (per-file result with timing)
    # ------------------------------------------------------------------

    def record_transfer(
        self, run_id: str, source_path: str, dest_path: str = "",
        file_size_source: int = 0, file_size_dest: int = 0,
        hash_source: str = "", hash_dest: str = "",
        transfer_start: str = "", transfer_end: str = "",
        duration_sec: float = 0, speed_mbps: float = 0,
        result: str = "pending", retry_count: int = 0,
        error_message: str = "",
    ) -> None:
        """Record the outcome of transferring one file."""
        hash_match = 1 if (hash_source and hash_source == hash_dest) else 0
        with self._lock:
            # Never overwrite a 'success' record with a failure
            existing = self.conn.execute(
                "SELECT result FROM transfer_log "
                "WHERE source_path=? AND run_id=?",
                (source_path, run_id),
            ).fetchone()
            if existing and existing[0] == "success" and result != "success":
                return

            self.conn.execute(
                "INSERT OR REPLACE INTO transfer_log "
                "(source_path, dest_path, run_id, file_size_source, "
                "file_size_dest, hash_source, hash_dest, hash_match, "
                "transfer_start, transfer_end, duration_sec, speed_mbps, "
                "result, retry_count, error_message) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_path, dest_path, run_id, file_size_source,
                 file_size_dest, hash_source, hash_dest, hash_match,
                 transfer_start, transfer_end, duration_sec, speed_mbps,
                 result, retry_count, error_message),
            )
            self._batch_commit()

    # ------------------------------------------------------------------
    # Skipped files
    # ------------------------------------------------------------------

    def record_skip(
        self, run_id: str, source_path: str, file_size: int = 0,
        extension: str = "", reason: str = "", detail: str = "",
    ) -> None:
        """Record a file intentionally not transferred, with reason."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO skipped_files "
                "(source_path, run_id, file_size, extension, reason, "
                "detail, logged_at) VALUES (?,?,?,?,?,?,?)",
                (source_path, run_id, file_size, extension, reason,
                 detail, _utc_now()),
            )
            self._batch_commit()

    # ------------------------------------------------------------------
    # Delta sync queries
    # ------------------------------------------------------------------

    def get_previous_manifest(self, run_id: str) -> Dict[str, str]:
        """Return {source_path: content_hash} from the most recent completed run before this one."""
        with self._lock:
            row = self.conn.execute(
                "SELECT run_id FROM transfer_runs "
                "WHERE status='complete' AND run_id < ? "
                "ORDER BY run_id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            if not row:
                return {}
            prev_run = row[0]
            rows = self.conn.execute(
                "SELECT source_path, content_hash FROM source_manifest "
                "WHERE run_id=?",
                (prev_run,),
            ).fetchall()
            return {r[0]: r[1] for r in rows}

    def get_latest_run_id_before(self, run_id: str) -> Optional[str]:
        """Return most recent run_id older than the given run_id, or None."""
        with self._lock:
            row = self.conn.execute(
                "SELECT run_id FROM transfer_runs "
                "WHERE run_id < ? "
                "ORDER BY run_id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return row[0] if row else None

    def get_pending_candidates_from_run(
        self, run_id: str, limit: int = 0,
    ) -> List[Tuple[str, float, int]]:
        """
        Return pending source files from a prior run.

        "Pending" means the file was discovered in that run but did not
        record a successful transfer result for that same run.
        """
        with self._lock:
            sql = (
                "SELECT sm.source_path, sm.file_mtime, sm.file_size "
                "FROM source_manifest sm "
                "LEFT JOIN transfer_log tl "
                "  ON tl.source_path = sm.source_path "
                " AND tl.run_id = sm.run_id "
                "WHERE sm.run_id = ? "
                "  AND sm.is_accessible = 1 "
                "  AND (tl.result IS NULL OR tl.result <> 'success') "
                "ORDER BY sm.source_path"
            )
            params: Tuple = (run_id,)
            if limit > 0:
                sql += " LIMIT ?"
                params = (run_id, int(limit))
            rows = self.conn.execute(sql, params).fetchall()
            return [(r[0], float(r[1] or 0.0), int(r[2] or 0)) for r in rows]

    def is_already_transferred(
        self, source_path: str, current_mtime: float = 0,
    ) -> bool:
        """Check if this file was already successfully transferred (and unmodified if mtime given)."""
        with self._lock:
            if current_mtime > 0:
                row = self.conn.execute(
                    "SELECT sm.file_mtime FROM transfer_log tl "
                    "JOIN source_manifest sm ON "
                    "  tl.source_path = sm.source_path AND tl.run_id = sm.run_id "
                    "WHERE tl.source_path=? AND tl.result='success' "
                    "ORDER BY tl.run_id DESC LIMIT 1",
                    (source_path,),
                ).fetchone()
                if row is None:
                    return False
                return abs(row[0] - current_mtime) < 2.0
            else:
                row = self.conn.execute(
                    "SELECT 1 FROM transfer_log "
                    "WHERE source_path=? AND result='success' LIMIT 1",
                    (source_path,),
                ).fetchone()
                return row is not None

    def find_by_hash(self, content_hash: str) -> Optional[str]:
        """Find an already-transferred file with this content hash (for dedup)."""
        with self._lock:
            row = self.conn.execute(
                "SELECT dest_path FROM transfer_log "
                "WHERE hash_source=? AND result='success' LIMIT 1",
                (content_hash,),
            ).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_verification_report(self, run_id: str) -> str:
        """Zero-gap verification report -- delegates to module-level builder."""
        return _build_verification_report(self.conn, self._lock, run_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _batch_commit(self) -> None:
        """Accumulate writes and commit every 50 rows for performance."""
        self._pending_writes += 1
        if self._pending_writes >= 50:
            self.conn.commit()
            self._pending_writes = 0

    def rotate_old_runs(self, keep: int = 10) -> int:
        """Delete data from runs older than the most recent `keep` runs. Returns count deleted."""
        with self._lock:
            keep_ids = self.conn.execute(
                "SELECT run_id FROM transfer_runs "
                "ORDER BY run_id DESC LIMIT ?",
                (keep,),
            ).fetchall()
            if not keep_ids:
                return 0
            keep_set = {r[0] for r in keep_ids}

            all_ids = self.conn.execute(
                "SELECT run_id FROM transfer_runs",
            ).fetchall()
            delete_ids = [r[0] for r in all_ids if r[0] not in keep_set]
            if not delete_ids:
                return 0

            placeholders = ",".join("?" * len(delete_ids))
            self.conn.execute(
                f"DELETE FROM source_manifest WHERE run_id IN ({placeholders})",
                delete_ids,
            )
            self.conn.execute(
                f"DELETE FROM transfer_log WHERE run_id IN ({placeholders})",
                delete_ids,
            )
            self.conn.execute(
                f"DELETE FROM skipped_files WHERE run_id IN ({placeholders})",
                delete_ids,
            )
            self.conn.execute(
                f"DELETE FROM transfer_runs WHERE run_id IN ({placeholders})",
                delete_ids,
            )
            self.conn.commit()

            try:
                self.conn.execute("VACUUM")
            except Exception:
                pass

            return len(delete_ids)

    def flush(self) -> None:
        """Force all pending writes to disk immediately."""
        with self._lock:
            self.conn.commit()
            self._pending_writes = 0

    def close(self) -> None:
        """Commit any remaining writes and close the database."""
        with self._lock:
            try:
                self.conn.commit()
            except Exception:
                pass
            finally:
                self.conn.close()
