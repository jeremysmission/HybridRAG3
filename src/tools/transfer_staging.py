# ============================================================================
# HybridRAG -- Transfer Staging Manager (src/tools/transfer_staging.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Manages the three-stage directory structure that prevents partial or
#   corrupt files from ever reaching the ingestion pipeline.
#
#   Think of it like an airport security checkpoint for files:
#     1. /incoming/    -- The "arrivals hall." Files land here during
#                         transfer. They might be partial, corrupted,
#                         or still being written.
#     2. /verified/    -- The "cleared" area. Files move here ONLY after
#                         their SHA-256 hash is verified. The RAG indexer
#                         reads exclusively from this folder.
#     3. /quarantine/  -- The "detained" area. Files that failed hash
#                         verification, were locked, or had other
#                         problems are moved here for manual review.
#
# WHY THIS MATTERS:
#   Without staging, a file that is mid-copy when the process crashes
#   looks like a valid file to the indexer. It has a valid name, a
#   reasonable size, and sits in the source folder. But it is truncated
#   garbage that produces garbage embeddings -- your RAG system would
#   confidently return nonsense answers based on half a document.
#
#   Staging prevents this by ensuring the indexer ONLY sees files that
#   have passed hash verification.
#
# HOW THE ATOMIC RENAME WORKS:
#   When a file finishes copying to /incoming/, we call os.rename()
#   to move it to /verified/. On the same filesystem, os.rename() is
#   ATOMIC -- it either completes fully or not at all. There is no
#   possible state where the file is "half moved." This is the same
#   technique used by databases, package managers, and web browsers
#   for safe file updates.
#
#   Exception: if incoming/ and verified/ are on different drives
#   (different filesystems), os.rename() fails and we fall back to
#   copy+delete. This is rare in practice because both directories
#   are under the same staging base path.
#
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional

from .path_io import to_io_path

logger = logging.getLogger(__name__)


class StagingManager:
    """
    Three-stage directory manager for transfer integrity.

    incoming/   -- Active transfers land here as .tmp files.
                   No other process should read from this folder.
    verified/   -- Hash-verified complete files (ready for indexing).
                   The RAG indexer's source folder points HERE.
    quarantine/ -- Failed verification, corrupt, or locked files.
                   Check this folder after a transfer to see what
                   went wrong.

    NON-PROGRAMMER NOTE:
      You create one StagingManager per transfer destination.
      It automatically creates the three subdirectories on first use.
      You never need to create them manually.
    """

    def __init__(self, base_path: str) -> None:
        # base_path is the top-level staging directory.
        # Example: D:\\RAG_Staging
        # This creates:
        #   D:\\RAG_Staging\\incoming\\
        #   D:\\RAG_Staging\\verified\\
        #   D:\\RAG_Staging\\quarantine\\
        self.base = Path(base_path)
        self.incoming = self.base / "incoming"
        self.verified = self.base / "verified"
        self.quarantine = self.base / "quarantine"
        self._promote_lock = threading.Lock()
        # In-memory collision counters: {relative_path: next_counter}
        # Avoids O(n^2) filesystem scans when many files share a name
        self._collision_counters: Dict[str, int] = {}
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create all three staging directories if they don't exist."""
        for d in [self.incoming, self.verified, self.quarantine]:
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Incoming: where files land during transfer
    # ------------------------------------------------------------------

    def incoming_path(self, relative_path: str) -> Path:
        """
        Get the .tmp path in incoming/ for a file being transferred.

        NON-PROGRAMMER NOTE:
          When copying "Reports/Q1.pdf" from the network drive, the
          file first lands as "incoming/Reports/Q1.pdf.tmp". The .tmp
          extension is a signal: "I am not done yet, do not read me."

          If the transfer crashes, cleanup_incoming() will find and
          remove all .tmp files, keeping the staging area clean.
        """
        dest = self.incoming / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest.with_suffix(dest.suffix + ".tmp")

    # ------------------------------------------------------------------
    # Promotion: incoming -> verified (the critical step)
    # ------------------------------------------------------------------

    def promote_to_verified(self, tmp_path: Path, relative_path: str) -> Path:
        """
        Atomically move a verified file from incoming/ to verified/.

        This is the KEY safety mechanism:
          1. File arrives in incoming/ as .tmp (may be partial)
          2. SHA-256 hash is computed and compared to source
          3. If hashes match: this method renames it to verified/
          4. The rename is atomic -- the file appears in verified/
             instantaneously, fully formed.

        NON-PROGRAMMER NOTE:
          os.rename() on the same filesystem is like flipping a switch.
          The file doesn't "travel" from one folder to another -- the
          filesystem just updates its directory listing. It takes
          microseconds regardless of file size (even for a 2 GB file).

          If the rename fails (e.g., different drives), we fall back to
          shutil.move() which does a copy+delete. This is slower but
          the hash has already been verified, so the file is known-good.

        Returns the final path in verified/.
        """
        final = self.verified / relative_path
        final.parent.mkdir(parents=True, exist_ok=True)

        # Lock prevents TOCTOU race: without this, 8 threads checking
        # exists() simultaneously all see False, then all rename to
        # the same path, silently overwriting each other's files.
        with self._promote_lock:
            if final.exists() or relative_path in self._collision_counters:
                stem = final.stem
                suffix = final.suffix
                # O(1) lookup: use in-memory counter instead of scanning disk
                counter = self._collision_counters.get(relative_path, 1)
                final = final.parent / f"{stem}_{counter}{suffix}"
                self._collision_counters[relative_path] = counter + 1
            else:
                # First use of this relative_path -- mark it as "seen"
                # so the next file with the same name gets _1 appended.
                self._collision_counters[relative_path] = 1

            try:
                os.replace(to_io_path(str(tmp_path)), to_io_path(str(final)))
            except OSError:
                try:
                    shutil.move(to_io_path(str(tmp_path)), to_io_path(str(final)))
                except Exception as e:
                    logger.error(
                        "promote_to_verified failed for %s: %s",
                        relative_path, e,
                    )
                    raise

        return final

    # ------------------------------------------------------------------
    # Quarantine: where problem files go
    # ------------------------------------------------------------------

    def quarantine_file(
        self, file_path: Path, relative_path: str, reason: str = ""
    ) -> Path:
        """
        Move a file to quarantine/ with an optional reason tag.

        NON-PROGRAMMER NOTE:
          Quarantined files are NOT deleted -- they are preserved for
          inspection. Each quarantined file gets a companion .reason
          file explaining what went wrong. Example:

            quarantine/Reports/Q1.pdf
            quarantine/Reports/Q1.pdf.reason  (contains "Hash mismatch: ...")

          After a transfer, check the quarantine/ folder. Common reasons:
            - "Hash mismatch" -- file was corrupted during copy
            - "File locked" -- another process had the file open
            - "Copy failed" -- network error during transfer
        """
        dest = self.quarantine / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        with self._promote_lock:
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest.parent / f"{stem}_{counter}{suffix}"
                    counter += 1

            try:
                os.replace(to_io_path(str(file_path)), to_io_path(str(dest)))
            except OSError:
                try:
                    shutil.move(to_io_path(str(file_path)), to_io_path(str(dest)))
                except Exception as e:
                    logger.error(
                        "quarantine_file failed for %s: %s",
                        relative_path, e,
                    )
                    raise

        if reason:
            reason_path = dest.with_suffix(dest.suffix + ".reason")
            try:
                reason_path.write_text(reason, encoding="utf-8")
            except Exception:
                pass

        return dest

    # ------------------------------------------------------------------
    # Cleanup: remove leftovers from crashed transfers
    # ------------------------------------------------------------------

    def cleanup_incoming(self) -> int:
        """
        Remove any leftover .tmp files from a crashed transfer.

        NON-PROGRAMMER NOTE:
          If the transfer process crashes (power failure, Ctrl+C, etc.),
          partial .tmp files may remain in incoming/. These are useless
          and should be cleaned up before the next run. This method
          finds and deletes all of them.

          Returns the number of .tmp files removed.
        """
        count = 0
        for tmp in self.incoming.rglob("*.tmp"):
            try:
                tmp.unlink()
                count += 1
            except Exception:
                pass  # File may be locked by another process
        return count

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def verified_path(self) -> str:
        """
        Path string for use as HybridRAG source folder.

        NON-PROGRAMMER NOTE:
          Point HybridRAG's source_folder config at this path.
          The indexer will only see hash-verified, complete files.
        """
        return str(self.verified)
