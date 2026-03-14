# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the bulk transfer v2 part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Bulk Transfer Engine V2 (src/tools/bulk_transfer_v2.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Production-grade file transfer engine for copying terabytes of data
#   from network drives into HybridRAG's source folder. This is the
#   "advanced robocopy" purpose-built for RAG source preparation.
#
#   Instead of blindly copying everything (like robocopy), this engine
#   is SMART about what it copies:
#     - Only copies file types HybridRAG can actually parse
#     - Skips duplicates (same content in multiple folders)
#     - Verifies every copy with SHA-256 hashing
#     - Uses atomic file operations to prevent partial files
#     - Detects locked files before wasting time on them
#     - Catches files being written to by other processes
#     - Logs every decision so nothing is invisible
#
# HOW TO RUN IT (command line):
#   python -m src.tools.bulk_transfer_v2 \
#       --sources "\\\\Server\\Share\\Engineering" "\\\\Server\\Share\\Reports" \
#       --dest "D:\\RAG_Staging"
#
#   Optional flags:
#     --workers 8            (parallel threads, default 8)
#     --no-dedup             (disable deduplication)
#     --no-verify            (skip SHA-256 verification)
#     --no-resume            (ignore previous runs, start fresh)
#     --include-hidden       (include hidden/system files)
#     --follow-symlinks      (follow symlinks/junctions)
#     --bandwidth-limit 50   (bytes/sec limit, 0 = unlimited)
#
# KEY CAPABILITIES:
#   - Atomic copy pattern: write to .tmp, hash-verify, atomic rename
#   - Three-stage staging: incoming -> verified -> quarantine
#   - SHA-256 hash verification (source vs destination)
#   - Locked file detection with quarantine
#   - Content-hash deduplication
#   - Delta sync (mtime first-pass, hash second-pass)
#   - Renamed file detection (same hash, different path)
#   - Deletion detection (source file removed since last run)
#   - Symlink/junction loop detection
#   - Long path support (>260 chars on Windows)
#   - Hidden/system file awareness
#   - File-encoding safety checks (non-UTF-8 filenames)
#   - Per-file transfer timing and speed logging
#   - Zero-gap manifest (every file accounted for)
#   - Multi-threaded with per-thread error handling
#   - Bandwidth throttling
#   - Live statistics dashboard
#
# ARCHITECTURE:
#   This engine delegates to two helper modules:
#     - transfer_manifest.py: SQLite database tracking every file
#     - transfer_staging.py: Three-stage directory manager
#
#   The transfer happens in three phases:
#     Phase 1:  Walk every source directory, record every file in the
#               manifest, filter out non-RAG files, build a transfer queue
#     Phase 1b: Compare current manifest against previous run (delta sync)
#     Phase 2:  Copy files in parallel using atomic copy pattern
#     Phase 3:  Finalize manifest, generate verification report
#
# INTERNET ACCESS: NONE (local/network file copy only)
# ============================================================================

from __future__ import annotations

import errno
import gc
import hashlib
import json
import logging
import os
import random
import shutil
import stat
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

from .transfer_manifest import TransferManifest
from .transfer_staging import StagingManager
from .path_io import to_io_path


# ============================================================================
# Configuration
# ============================================================================

# Fallback parser extension list used only if registry import fails.
# Primary source of truth is src/parsers/registry.py.
_RAG_EXTENSIONS_FALLBACK: Set[str] = {
    # Plain text / config
    ".txt", ".md", ".csv", ".json", ".xml", ".log", ".yaml", ".yml",
    ".ini", ".cfg", ".conf", ".properties", ".reg",
    # Documents
    ".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".rtf",
    # Email
    ".html", ".htm", ".eml", ".msg", ".mbox",
    # Images (OCR)
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp",
    # CAD / engineering
    ".dxf", ".stp", ".step", ".ste", ".igs", ".iges", ".stl",
    # Diagrams
    ".vsdx",
    # Security / forensics
    ".evtx", ".pcap", ".pcapng", ".cer", ".crt", ".pem",
    # Databases
    ".accdb", ".mdb",
    # Design
    ".psd", ".ai", ".wmf", ".emf",
}


def _resolve_rag_extensions() -> Set[str]:
    """
    Resolve copy allowlist from parser registry.

    Uses parser registry as the single source of truth to prevent drift
    between downloader discovery and actual parser coverage.
    """
    try:
        from src.parsers.registry import REGISTRY
        exts = {
            str(ext).strip().lower()
            for ext in REGISTRY.supported_extensions()
            if str(ext).strip().startswith(".")
        }
        if exts:
            return exts
    except Exception as e:
        logger.warning(
            "[WARN] Could not load parser registry extensions; "
            "using fallback allowlist: %s",
            e,
        )
    return _RAG_EXTENSIONS_FALLBACK.copy()


def _resume_lookup_key(path: str) -> str:
    """Normalize source paths for stable in-memory resume lookups."""
    return os.path.normcase(os.path.normpath(str(path)))


# Default file extensions HybridRAG can parse.
# Dynamically loaded from parser registry to avoid allowlist drift.
_RAG_EXTENSIONS: Set[str] = _resolve_rag_extensions()

# Extensions that should NEVER be copied (not useful for RAG, often huge).
# .pst = Outlook data file: it's a database container that is almost always
# locked by Outlook and cannot be parsed as a single document.
_ALWAYS_SKIP: Set[str] = {
    ".exe", ".dll", ".sys", ".msi", ".cab", ".iso",
    ".mp4", ".mp3", ".avi", ".mkv", ".wav", ".flac",
    ".pst",
}

# Directories to skip during discovery (system/build artifacts).
# All comparisons are case-insensitive.
_EXCLUDED_DIRS: Set[str] = {
    ".git", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    "$recycle.bin", "system volume information", ".trash", ".tmp",
    "windowsapps", "appdata", ".cache",
}


@dataclass
class TransferConfig:
    """
    All settings for a V2 bulk transfer run.

    NON-PROGRAMMER NOTE:
      A "dataclass" is just a bundle of named settings. Think of it
      like a form you fill out before starting a transfer:
        - Where are the source directories?
        - Where should files go?
        - How many parallel workers?
        - Should we deduplicate?
        - etc.

      Default values are sensible for most enterprise environments.
      The 1 MB copy buffer is optimal for network transfers (tested
      against 64KB, 256KB, 512KB, 2MB, 4MB -- 1MB wins on SMB).
    """
    source_paths: List[str] = field(default_factory=list)
    dest_path: str = ""
    workers: int = 8                   # Capped at 32 by engine
    extensions: Set[str] = field(default_factory=lambda: _RAG_EXTENSIONS.copy())
    excluded_dirs: Set[str] = field(default_factory=lambda: _EXCLUDED_DIRS.copy())
    min_file_size: int = 100            # Skip files smaller than 100 bytes
    max_file_size: int = 500_000_000    # Skip files larger than 500 MB
    deduplicate: bool = True
    verify_copies: bool = True
    resume: bool = True                 # Skip already-transferred files
    resume_seed_from_manifest: bool = True  # Start resume from prior manifest before full crawl
    resume_seed_limit: int = 0          # 0 = no limit; >0 caps resume seed candidates
    skip_full_discovery: bool = False   # If True, transfer only resume-seeded candidates
    max_retries: int = 3
    retry_backoff: float = 2.0          # Wait 2s, 4s, 8s between retries
    copy_buffer_size: int = 1_048_576   # 1 MB (optimal for network SMB)
    bandwidth_limit: int = 0            # bytes/sec, 0 = unlimited
    include_hidden: bool = False        # Include hidden/system files?
    follow_symlinks: bool = False       # Follow symlinks/junctions?
    long_path_warn: int = 250           # Warn on paths near MAX_PATH (260)

    # --- VPN / remote-network resilience ---
    # These settings handle the reality of SMB paths over VPN/remote
    # networks where connections drop, stall, or throttle unpredictably.
    network_health_interval: float = 60.0    # Seconds between source reachability checks
    stall_timeout: float = 120.0             # Seconds before declaring a copy stalled
    max_consecutive_failures: int = 20       # Pause and wait for network recovery
    network_recovery_wait: float = 30.0      # Seconds to wait when network appears down
    network_recovery_max_wait: float = 600.0 # Max backoff for network recovery (10 min)

    # --- Memory safety for multi-day operation ---
    # 650 GB / 5 days = need careful memory management
    gc_interval: int = 10000           # Force gc.collect() every N files processed
    checkpoint_interval: float = 300.0 # Log checkpoint summary every N seconds
    max_speed_history: int = 500       # Cap speed-over-time samples
    log_file: str = ""                 # Path to JSON log file ("" = no file log)
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None


# ============================================================================
# Transfer Statistics (thread-safe)
# ============================================================================

class TransferStats:
    """
    Thread-safe running statistics with rolling speed window.

    NON-PROGRAMMER NOTE:
      As files are being copied by 8 parallel workers, this class
      keeps a running tally of everything that's happening. It uses
      a threading lock to prevent two workers from updating the same
      counter at the same time (which would produce wrong numbers).

      The "rolling speed window" calculates speed based on the last
      30 seconds of activity rather than the overall average. This
      gives a more accurate "current speed" reading, similar to how
      a car's speedometer shows current speed, not average trip speed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.start_time: float = time.time()

        # File counters
        self.files_discovered: int = 0       # Total files found on source
        self.files_manifest: int = 0         # Total in manifest (= discovered)
        self.files_copied: int = 0           # Successfully copied + verified
        self.files_verified: int = 0         # Passed hash verification
        self.files_verify_failed: int = 0    # Hash mismatch (quarantined)
        self.files_deduplicated: int = 0     # Skipped as duplicates
        self.files_skipped_ext: int = 0      # Wrong file extension
        self.files_skipped_size: int = 0     # Too small or too large
        self.files_skipped_unchanged: int = 0  # Already transferred (resume)
        self.files_skipped_locked: int = 0   # Locked by another process
        self.files_skipped_encoding: int = 0   # Non-UTF-8 filename
        self.files_skipped_symlink: int = 0  # Symlink/junction
        self.files_skipped_hidden: int = 0   # Hidden or system file
        self.files_skipped_inaccessible: int = 0  # Permission denied
        self.files_skipped_long_path: int = 0  # Path > 260 chars
        self.files_failed: int = 0           # Copy failed after retries
        self.files_quarantined: int = 0      # Moved to quarantine/

        # Delta sync counters
        self.files_delta_new: int = 0        # New since last run
        self.files_delta_modified: int = 0   # Changed since last run
        self.files_delta_renamed: int = 0    # Same content, new path
        self.files_delta_deleted: int = 0    # Gone from source

        # Byte counters
        self.bytes_copied: int = 0           # Total bytes transferred
        self.bytes_source_total: int = 0     # Total bytes in transfer queue

        # Per-extension counts (e.g., {".pdf": 150, ".docx": 80})
        self.ext_counts: Dict[str, int] = {}

        # Per-source-root stats for multi-source breakdown
        self.source_stats: Dict[str, Dict[str, int]] = {}

        # Rolling speed window: list of (timestamp, bytes) samples
        self._speed_samples: List[Tuple[float, int]] = []

        # Speed-over-time history: sampled every 30s for final report
        self._speed_history: List[Tuple[float, float]] = []  # (elapsed, bps)
        self._max_speed_history: int = 500  # Prevent unbounded growth

        # Phase 1 discovery counters (updated from walk thread)
        self.current_source_root: str = ""
        self.dirs_walked: int = 0

        # Network health tracking
        self.network_stalls: int = 0         # Times network appeared down
        self.network_recovery_time: float = 0  # Total seconds in recovery waits
        self.consecutive_failures: int = 0   # Current consecutive failure streak

        # Memory tracking for multi-day operation
        self.gc_collections: int = 0         # Times gc.collect() was triggered
        self.peak_queue_size: int = 0        # Largest queue seen
        self.checkpoints_logged: int = 0     # Checkpoint summaries emitted

    def record_copy(
        self, file_size: int, ext: str, source_root: str = "",
    ) -> None:
        """Record a successful file copy (called from worker threads)."""
        with self._lock:
            self.files_copied += 1
            self.bytes_copied += file_size
            self.ext_counts[ext] = self.ext_counts.get(ext, 0) + 1
            now = time.time()
            self._speed_samples.append((now, file_size))
            # Per-source tracking
            if source_root:
                sr = self.source_stats.setdefault(source_root, {
                    "copied": 0, "bytes": 0, "failed": 0, "skipped": 0,
                })
                sr["copied"] += 1
                sr["bytes"] += file_size
            # Prevent unbounded growth: prune entries older than 30s,
            # then hard-cap at 500 to handle bursts within the window.
            if len(self._speed_samples) > 500:
                cutoff = now - 30.0
                self._speed_samples = [
                    (t, b) for t, b in self._speed_samples if t >= cutoff
                ]
                # Hard cap: if all entries are within 30s, keep newest 500
                if len(self._speed_samples) > 500:
                    self._speed_samples = self._speed_samples[-500:]

    def note_stream_bytes(self, byte_count: int) -> None:
        """
        Record in-flight copied bytes for live throughput telemetry.

        This updates rolling speed without incrementing final copied-byte
        totals (those are still updated only after a verified file copy).
        """
        if byte_count <= 0:
            return
        with self._lock:
            now = time.time()
            self._speed_samples.append((now, int(byte_count)))
            if len(self._speed_samples) > 500:
                cutoff = now - 30.0
                self._speed_samples = [
                    (t, b) for t, b in self._speed_samples if t >= cutoff
                ]
                if len(self._speed_samples) > 500:
                    self._speed_samples = self._speed_samples[-500:]

    def record_source_event(
        self, source_root: str, event: str, count: int = 1,
    ) -> None:
        """Record a skip/fail event for a source root."""
        with self._lock:
            sr = self.source_stats.setdefault(source_root, {
                "copied": 0, "bytes": 0, "failed": 0, "skipped": 0,
            })
            sr[event] = sr.get(event, 0) + count

    @property
    def elapsed(self) -> float:
        """Seconds since transfer started."""
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> float:
        """Estimated seconds remaining based on current speed."""
        speed = self.speed_bps
        if speed <= 0:
            return float("inf")
        with self._lock:
            remaining = self.bytes_source_total - self.bytes_copied
        return max(0, remaining / speed)

    @property
    def speed_bps(self) -> float:
        """
        Current transfer speed in bytes/second (30-second rolling window).

        NON-PROGRAMMER NOTE:
          We look at only the last 30 seconds of data to calculate
          speed. This means the speed reading is responsive -- if the
          network suddenly slows down, you'll see it quickly rather
          than it being hidden by the overall average.
        """
        with self._lock:
            now = time.time()
            cutoff = now - 30.0
            # Remove samples older than 30 seconds
            self._speed_samples = [
                (t, b) for t, b in self._speed_samples if t >= cutoff
            ]
            if not self._speed_samples:
                return 0.0
            total = sum(b for _, b in self._speed_samples)
            span = now - self._speed_samples[0][0]
            return total / max(span, 0.1)

    @property
    def files_processed(self) -> int:
        """Total files that have been handled (copied, skipped, or failed)."""
        with self._lock:
            return (
                self.files_copied + self.files_deduplicated +
                self.files_skipped_ext + self.files_skipped_size +
                self.files_skipped_unchanged + self.files_skipped_locked +
                self.files_skipped_encoding + self.files_skipped_symlink +
                self.files_skipped_hidden + self.files_skipped_inaccessible +
                self.files_skipped_long_path + self.files_failed +
                self.files_quarantined
            )

    def discovery_line(self) -> str:
        """One-line progress during Phase 1 source discovery."""
        with self._lock:
            root = self.current_source_root
            if len(root) > 50:
                root = "..." + root[-47:]
            return (
                f"Scanning... {self.files_discovered:,} files found, "
                f"{self.dirs_walked:,} dirs | {root}"
            )

    def summary_line(self) -> str:
        """One-line progress summary for the live display."""
        speed = self.speed_bps
        eta = self.eta_seconds
        s = _fmt_size
        eta_str = _fmt_dur(eta) if eta < 86400 else "???"
        with self._lock:
            return (
                f"[{self.files_copied}/{self.files_manifest}] "
                f"{s(self.bytes_copied)} | {s(speed)}/s | "
                f"ETA {eta_str} | "
                f"dedup:{self.files_deduplicated} "
                f"skip:{self.files_skipped_unchanged} "
                f"err:{self.files_failed} quar:{self.files_quarantined}"
            )

    def full_report(self) -> str:
        """
        Multi-line final statistics report printed at end of transfer.

        NON-PROGRAMMER NOTE:
          This is the "receipt" you get after the transfer completes.
          It shows everything: how many files, how fast, what was
          skipped, what failed, broken down by category.
        """
        e = self.elapsed
        avg = self.bytes_copied / max(e, 0.1)
        s = _fmt_size
        lines = [
            "", "=" * 70,
            "  BULK TRANSFER V2 -- FINAL STATISTICS",
            "=" * 70, "",
            f"  Total time:              {_fmt_dur(e)}",
            f"  Average speed:           {s(avg)}/s",
            f"  Data transferred:        {s(self.bytes_copied)}",
            "",
            f"  Source manifest:         {self.files_manifest:,}",
            f"  Successfully copied:     {self.files_copied:,}",
            f"  Hash verified:           {self.files_verified:,}",
            f"  Verification failed:     {self.files_verify_failed:,}",
            f"  Deduplicated:            {self.files_deduplicated:,}",
            "",
            f"  Skipped (wrong ext):     {self.files_skipped_ext:,}",
            f"  Skipped (size):          {self.files_skipped_size:,}",
            f"  Skipped (unchanged):     {self.files_skipped_unchanged:,}",
            f"  Skipped (locked):        {self.files_skipped_locked:,}",
            f"  Skipped (encoding):      {self.files_skipped_encoding:,}",
            f"  Skipped (symlink):       {self.files_skipped_symlink:,}",
            f"  Skipped (hidden):        {self.files_skipped_hidden:,}",
            f"  Skipped (inaccessible):  {self.files_skipped_inaccessible:,}",
            f"  Skipped (long path):     {self.files_skipped_long_path:,}",
            f"  Failed:                  {self.files_failed:,}",
            f"  Quarantined:             {self.files_quarantined:,}",
            "",
            f"  Delta new files:         {self.files_delta_new:,}",
            f"  Delta modified:          {self.files_delta_modified:,}",
            f"  Delta renamed:           {self.files_delta_renamed:,}",
            f"  Delta deleted:           {self.files_delta_deleted:,}",
        ]
        if self.ext_counts:
            lines.extend(["", "  Files by type:"])
            for ext, cnt in sorted(
                self.ext_counts.items(), key=lambda x: x[1], reverse=True
            )[:15]:
                lines.append(f"    {ext:8s} {cnt:>8,}")

        if self.source_stats:
            lines.extend(["", "  Per-source breakdown:"])
            lines.append(
                f"    {'Source':<40s} {'Copied':>8s} {'Data':>10s} "
                f"{'Failed':>8s} {'Skipped':>8s}"
            )
            lines.append("    " + "-" * 78)
            for root, sr in sorted(self.source_stats.items()):
                label = root if len(root) <= 40 else "..." + root[-37:]
                lines.append(
                    f"    {label:<40s} {sr.get('copied', 0):>8,} "
                    f"{s(sr.get('bytes', 0)):>10s} "
                    f"{sr.get('failed', 0):>8,} "
                    f"{sr.get('skipped', 0):>8,}"
                )

        # Speed-over-time sparkline (if we have history samples)
        if self._speed_history:
            lines.extend(["", "  Speed over time:"])
            speeds = [bps for _, bps in self._speed_history]
            peak = max(speeds) if speeds else 1
            for i, (elapsed_t, bps) in enumerate(self._speed_history):
                bar_len = int(40 * bps / max(peak, 1))
                bar = "#" * bar_len
                lines.append(
                    f"    {_fmt_dur(elapsed_t):>8s} | {s(bps):>10s}/s | {bar}"
                )
                if i >= 29:  # Max 30 rows
                    break

        # Network & memory health (for multi-day operation monitoring)
        if self.network_stalls or self.gc_collections:
            lines.extend(["", "  Operational health:"])
            if self.network_stalls:
                lines.append(
                    f"    Network stalls:        {self.network_stalls:,}"
                )
                lines.append(
                    f"    Recovery wait time:     "
                    f"{_fmt_dur(self.network_recovery_time)}"
                )
            if self.gc_collections:
                lines.append(
                    f"    GC collections:        {self.gc_collections:,}"
                )
            if self.checkpoints_logged:
                lines.append(
                    f"    Checkpoints logged:    {self.checkpoints_logged:,}"
                )
            if self.peak_queue_size:
                lines.append(
                    f"    Peak queue size:       {self.peak_queue_size:,}"
                )

        lines.extend(["", "=" * 70])
        return "\n".join(lines)


# ============================================================================
# Source Discovery (Phase 1)
# ============================================================================
# Walks source directories, records every file in the manifest, filters
# out non-RAG files, and builds the transfer queue.
# ============================================================================

class SourceDiscovery:
    """
    File discovery and filtering engine for Phase 1 of bulk transfer.

    Walks every source directory tree, records each file in the
    manifest database, applies extension/size/encoding/symlink filters,
    and returns a queue of files that passed all checks.
    """

    def __init__(
        self,
        config: TransferConfig,
        manifest: TransferManifest,
        stats: TransferStats,
        run_id: str,
        log_lock: threading.Lock,
        stop_event: threading.Event,
    ) -> None:
        self.config = config
        self.manifest = manifest
        self.stats = stats
        self.run_id = run_id
        self._log_lock = log_lock
        self._stop = stop_event

        # Symlink loop guard: tracks real directory paths already
        # visited so circular junctions don't cause infinite walks.
        self._visited_dirs: Set[str] = set()
        self._resume_skip_map_ready = False
        self._resume_skip_mtimes: Dict[str, float] = {}
        if self.config.resume:
            try:
                self._resume_skip_mtimes = {
                    _resume_lookup_key(source_path): float(file_mtime or 0.0)
                    for source_path, file_mtime
                    in self.manifest.get_successful_transfer_mtimes().items()
                }
                self._resume_skip_map_ready = True
            except Exception as e:
                logger.warning(
                    "[WARN] Could not preload transfer resume skip map: %s",
                    e,
                )

    def _log(self, msg: str) -> None:
        """Thread-safe print."""
        with self._log_lock:
            print(f"\n{msg}", flush=True)

    def _was_transferred_unchanged(
        self, source_path: str, file_mtime: float,
    ) -> bool:
        """Check unchanged-transfer status using the preloaded skip map when available."""
        if not self.config.resume:
            return False
        if self._resume_skip_map_ready:
            stored_mtime = self._resume_skip_mtimes.get(
                _resume_lookup_key(source_path)
            )
            return (
                stored_mtime is not None
                and abs(stored_mtime - float(file_mtime or 0.0)) < 2.0
            )
        return self.manifest.is_already_transferred(
            source_path, current_mtime=file_mtime,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def discover(self) -> List[Tuple[str, str, str, int]]:
        """Walk sources, build manifest, return transfer queue."""
        cfg = self.config
        queue: List[Tuple[str, str, str, int]] = []

        # Dedicated stop event for the progress thread so it does not
        # collide with the Phase 2 progress thread.
        self._discovery_stop = threading.Event()
        t = threading.Thread(
            target=self._discovery_progress_loop, daemon=True,
        )
        t.start()

        for source_root in cfg.source_paths:
            if self._stop.is_set():
                break
            root = Path(source_root)
            if not root.exists():
                self._log(f"  [WARN] Not accessible: {source_root}")
                continue
            self.stats.current_source_root = str(root)
            self._walk_source(root, str(root), queue)
            if self._stop.is_set():
                break

        self._discovery_stop.set()
        t.join(timeout=10.0)
        return queue

    def discover_iter(self):
        """
        Stream discovered transfer candidates as an iterator.

        This enables copy to begin before full discovery completes, which is
        critical for very large/slow network sources.
        """
        cfg = self.config
        self._discovery_stop = threading.Event()
        t = threading.Thread(
            target=self._discovery_progress_loop, daemon=True,
        )
        t.start()
        try:
            for source_root in cfg.source_paths:
                if self._stop.is_set():
                    break
                root = Path(source_root)
                if not root.exists():
                    self._log(f"  [WARN] Not accessible: {source_root}")
                    continue
                self.stats.current_source_root = str(root)
                for item in self._iter_walk_source(root, str(root)):
                    if self._stop.is_set():
                        break
                    yield item
                if self._stop.is_set():
                    break
        finally:
            self._discovery_stop.set()
            t.join(timeout=10.0)

    def resume_seed_iter(self):
        """
        Yield pending files from the most recent prior run manifest.

        This starts resumed copying immediately after restart, instead of
        waiting for a full source crawl before first transfer work begins.
        """
        cfg = self.config
        if not (cfg.resume and cfg.resume_seed_from_manifest):
            return

        prev_run = self.manifest.get_latest_run_id_before(self.run_id)
        if not prev_run:
            return

        limit = int(cfg.resume_seed_limit or 0)
        candidates = self.manifest.get_pending_candidates_from_run(
            prev_run, limit=limit,
        )
        if not candidates:
            return

        self._log(
            f"  [RESUME] Seeding {len(candidates):,} pending files "
            f"from run {prev_run} before full discovery..."
        )

        for source, _, _ in candidates:
            if self._stop.is_set():
                break
            try:
                st = _stat_with_timeout(source, timeout=5.0)
            except (OSError, PermissionError, TimeoutError):
                continue

            file_size = int(st.st_size)
            ext = os.path.splitext(source)[1].lower()
            if ext in _ALWAYS_SKIP or ext not in cfg.extensions:
                continue
            if file_size < cfg.min_file_size or file_size > cfg.max_file_size:
                continue

            source_root = self._match_source_root(source)
            if not source_root:
                continue

            # If a previous run already completed this exact mtime, skip.
            if self._was_transferred_unchanged(source, st.st_mtime):
                continue

            try:
                rel = os.path.relpath(source, source_root)
            except ValueError:
                rel = os.path.basename(source)

            if cfg.skip_full_discovery:
                # In seeded-only mode there is no later live discovery pass
                # to populate the current-run manifest, so seed candidates
                # must enter source_manifest before any transfer outcome.
                attrs = getattr(st, "st_file_attributes", 0)
                self.manifest.record_source_file(
                    self.run_id,
                    source,
                    file_size=file_size,
                    file_mtime=st.st_mtime,
                    file_ctime=getattr(st, "st_ctime", 0.0),
                    extension=ext,
                    is_hidden=(
                        bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)
                        if hasattr(stat, "FILE_ATTRIBUTE_HIDDEN") else False
                    ),
                    is_system=(
                        bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
                        if hasattr(stat, "FILE_ATTRIBUTE_SYSTEM") else False
                    ),
                    is_readonly=(
                        bool(attrs & stat.FILE_ATTRIBUTE_READONLY)
                        if hasattr(stat, "FILE_ATTRIBUTE_READONLY") else False
                    ),
                    is_symlink=os.path.islink(source),
                    is_accessible=True,
                    path_length=len(source),
                )
                self.stats.files_manifest += 1
                self.stats.bytes_source_total += file_size

            yield (source, source_root, rel, file_size)

    def _match_source_root(self, source_path: str) -> str:
        """Return best matching configured source root for a file path."""
        target = os.path.normcase(os.path.abspath(source_path))
        best = ""
        best_len = -1
        for src in self.config.source_paths:
            try:
                s = os.path.normcase(os.path.abspath(src))
            except Exception:
                continue
            if target == s or target.startswith(s + os.sep):
                if len(s) > best_len:
                    best = src
                    best_len = len(s)
        return best

    # ------------------------------------------------------------------
    # Directory walker
    # ------------------------------------------------------------------

    def _walk_source(
        self, root: Path, source_root: str,
        queue: List[Tuple[str, str, str, int]],
    ) -> None:
        """Recursively walk a source directory tree."""
        cfg = self.config
        excl = {d.lower() for d in cfg.excluded_dirs}
        walk_warnings = 0

        def _on_walk_error(err: OSError) -> None:
            nonlocal walk_warnings
            walk_warnings += 1

        for dirpath, dirnames, filenames in os.walk(
            str(root), onerror=_on_walk_error,
        ):
            if self._stop.is_set():
                break
            self.stats.dirs_walked += 1

            # Symlink loop guard
            try:
                real = os.path.realpath(dirpath)
            except OSError:
                dirnames.clear()
                continue
            if real in self._visited_dirs:
                self.manifest.record_skip(
                    self.run_id, dirpath, reason="symlink_loop",
                    detail="Circular junction/symlink detected",
                )
                dirnames.clear()
                continue
            self._visited_dirs.add(real)

            # Exclude known-useless directories
            dirnames[:] = [
                d for d in dirnames if d.lower() not in excl
            ]

            for filename in filenames:
                if self._stop.is_set():
                    break
                full = os.path.join(dirpath, filename)
                self.stats.files_discovered += 1
                try:
                    self._process_discovery(full, source_root, queue)
                except (OSError, UnicodeEncodeError):
                    self.stats.files_skipped_inaccessible += 1
            if self._stop.is_set():
                break

        if walk_warnings:
            self._log(
                f"  [WARN] {walk_warnings} directory read errors "
                f"during walk"
            )

    def _iter_walk_source(self, root: Path, source_root: str):
        """Generator variant of _walk_source that yields transfer candidates."""
        cfg = self.config
        excl = {d.lower() for d in cfg.excluded_dirs}
        walk_warnings = 0

        def _on_walk_error(err: OSError) -> None:
            nonlocal walk_warnings
            walk_warnings += 1

        for dirpath, dirnames, filenames in os.walk(
            str(root), onerror=_on_walk_error,
        ):
            if self._stop.is_set():
                break
            self.stats.dirs_walked += 1

            try:
                real = os.path.realpath(dirpath)
            except OSError:
                dirnames.clear()
                continue
            if real in self._visited_dirs:
                self.manifest.record_skip(
                    self.run_id, dirpath, reason="symlink_loop",
                    detail="Circular junction/symlink detected",
                )
                dirnames.clear()
                continue
            self._visited_dirs.add(real)

            dirnames[:] = [
                d for d in dirnames if d.lower() not in excl
            ]

            for filename in filenames:
                if self._stop.is_set():
                    break
                full = os.path.join(dirpath, filename)
                self.stats.files_discovered += 1
                tmp_q: List[Tuple[str, str, str, int]] = []
                try:
                    self._process_discovery(full, source_root, tmp_q)
                except (OSError, UnicodeEncodeError):
                    self.stats.files_skipped_inaccessible += 1
                if tmp_q:
                    yield tmp_q[0]
            if self._stop.is_set():
                break

        if walk_warnings:
            self._log(
                f"  [WARN] {walk_warnings} directory read errors "
                f"during walk"
            )

    # ------------------------------------------------------------------
    # Per-file filter pipeline
    # ------------------------------------------------------------------

    def _process_discovery(
        self, full: str, source_root: str,
        queue: List[Tuple[str, str, str, int]],
    ) -> None:
        """
        Process a single discovered file: record in manifest, apply
        filters, and optionally add to transfer queue.
        """
        cfg = self.config
        ext = os.path.splitext(full)[1].lower()
        path_len = len(full)
        safe_path = full

        # SQLite cannot store surrogate characters, so normalize the path
        # before any manifest/log write that could touch the database.
        encoding_issue = False
        try:
            full.encode("utf-8")
        except UnicodeEncodeError:
            encoding_issue = True
            safe_path = full.encode(
                "utf-8", errors="replace",
            ).decode("utf-8")

        if encoding_issue:
            self.stats.files_skipped_encoding += 1
            self.manifest.record_source_file(
                self.run_id, safe_path, extension=ext,
                is_accessible=True, path_length=path_len,
                encoding_issue=True,
            )
            self.manifest.record_skip(
                self.run_id, safe_path, 0, ext,
                "encoding_issue",
                "Filename contains non-UTF-8 characters",
            )
            return

        # Unsupported and always-skip extensions can be rejected from the
        # filename alone, which avoids a costly stat() on files we would
        # never enqueue anyway while preserving manifest ground truth.
        if ext in _ALWAYS_SKIP:
            self.stats.files_skipped_ext += 1
            self.manifest.record_source_file(
                self.run_id, safe_path, extension=ext,
                is_accessible=True, path_length=path_len,
            )
            self.manifest.record_skip(
                self.run_id, safe_path, 0, ext,
                "always_skip",
                f"Extension {ext} is in the always-skip blocklist",
            )
            return

        if ext not in cfg.extensions:
            self.stats.files_skipped_ext += 1
            self.manifest.record_source_file(
                self.run_id, safe_path, extension=ext,
                is_accessible=True, path_length=path_len,
            )
            self.manifest.record_skip(
                self.run_id, safe_path, 0, ext,
                "unsupported_extension",
                f"Extension {ext} not in RAG parser registry",
            )
            return

        # Step 1: Read file attributes
        try:
            st = _stat_with_timeout(full)
        except (OSError, PermissionError, TimeoutError) as e:
            self.stats.files_skipped_inaccessible += 1
            self.manifest.record_skip(
                self.run_id, full, extension=ext,
                reason="inaccessible", detail=str(e),
            )
            self.manifest.record_source_file(
                self.run_id, full, extension=ext, is_accessible=False,
                path_length=path_len,
            )
            return

        file_size = st.st_size
        file_mtime = st.st_mtime
        file_ctime = getattr(st, "st_ctime", 0.0)

        # Windows-specific file attributes
        attrs = getattr(st, "st_file_attributes", 0)
        is_hidden = (
            bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)
            if hasattr(stat, "FILE_ATTRIBUTE_HIDDEN") else False
        )
        is_system = (
            bool(attrs & stat.FILE_ATTRIBUTE_SYSTEM)
            if hasattr(stat, "FILE_ATTRIBUTE_SYSTEM") else False
        )
        is_readonly = (
            bool(attrs & stat.FILE_ATTRIBUTE_READONLY)
            if hasattr(stat, "FILE_ATTRIBUTE_READONLY") else False
        )
        is_symlink = os.path.islink(full)

        # Record in manifest (every file, even skipped ones)
        self.manifest.record_source_file(
            self.run_id, safe_path, file_size=file_size,
            file_mtime=file_mtime, file_ctime=file_ctime,
            extension=ext, is_hidden=is_hidden, is_system=is_system,
            is_readonly=is_readonly, is_symlink=is_symlink,
            is_accessible=True, path_length=path_len,
            encoding_issue=encoding_issue,
        )

        # Step 2: Apply filters

        if is_symlink and not cfg.follow_symlinks:
            self.stats.files_skipped_symlink += 1
            self.manifest.record_skip(
                self.run_id, full, file_size, ext,
                "symlink",
                "Symlink/junction skipped (follow_symlinks=False)",
            )
            return

        if (is_hidden or is_system) and not cfg.include_hidden:
            self.stats.files_skipped_hidden += 1
            self.manifest.record_skip(
                self.run_id, full, file_size, ext,
                "hidden_or_system",
                f"hidden={is_hidden} system={is_system}",
            )
            return

        # Do not hard-skip long paths. We preserve full folder/file names
        # and rely on Windows long-path-aware IO helpers during transfer.

        if file_size < cfg.min_file_size:
            self.stats.files_skipped_size += 1
            self.manifest.record_skip(
                self.run_id, full, file_size, ext,
                "too_small",
                f"{file_size}B < {cfg.min_file_size}B min",
            )
            return
        if file_size > cfg.max_file_size:
            self.stats.files_skipped_size += 1
            self.manifest.record_skip(
                self.run_id, full, file_size, ext,
                "too_large",
                f"{file_size}B > {cfg.max_file_size}B max",
            )
            return

        self.stats.bytes_source_total += file_size

        # Structure preservation
        try:
            rel = os.path.relpath(full, source_root)
        except ValueError:
            rel = os.path.basename(full)

        # Resume check
        if self._was_transferred_unchanged(full, file_mtime):
            self.stats.files_skipped_unchanged += 1
            self.manifest.record_skip(
                self.run_id, full, file_size, ext,
                "already_transferred",
                "Successfully transferred in a previous run",
            )
            return

        queue.append((full, source_root, rel, file_size))

    # ------------------------------------------------------------------
    # Progress display
    # ------------------------------------------------------------------

    def _discovery_progress_loop(self) -> None:
        """Print live discovery count every 2 seconds."""
        while not self._discovery_stop.is_set():
            print(
                f"\r  {self.stats.discovery_line()}",
                end="", flush=True,
            )
            self._discovery_stop.wait(timeout=2.0)
        print()


# ============================================================================
# Atomic Transfer Worker (Phase 2)
# ============================================================================
# Parallel file transfer with atomic copy pattern, deduplication,
# hash verification, and retry logic.
# ============================================================================

class AtomicTransferWorker:
    """
    Parallel file transfer engine for Phase 2 of bulk transfer.

    Copies files using the atomic pattern (write .tmp, verify hash,
    rename), handles dedup, locked-file detection, and retries.
    """

    def __init__(
        self,
        config: TransferConfig,
        manifest: TransferManifest,
        staging: StagingManager,
        stats: TransferStats,
        run_id: str,
        stop_event: threading.Event,
        log_lock: threading.Lock,
    ) -> None:
        self.config = config
        self.manifest = manifest
        self.staging = staging
        self.stats = stats
        self.run_id = run_id
        self._stop = stop_event
        self._log_lock = log_lock

        # Dedup claims coordinate same-content files discovered by
        # multiple workers. A worker claims the hash after finishing its
        # copy so other workers can wait for the first verified result
        # instead of materializing duplicate verified files.
        self._dedup_lock = threading.Lock()
        self._dedup_cond = threading.Condition(self._dedup_lock)
        self._dedup_claims: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def transfer(self, queue) -> None:
        """Transfer all files using a thread pool with backpressure.

        NON-PROGRAMMER NOTE:
          "Backpressure" means we don't dump all 2 million files into the
          thread pool at once (that would eat all the RAM). Instead we keep
          a rolling window of at most workers*4 files in flight, and only
          submit a new file when a previous one completes.

          The network recovery logic detects when too many files fail in
          a row (e.g., VPN dropped) and pauses all workers until the source
          comes back online, with exponential backoff up to 10 minutes.
        """
        # Start live progress display
        t = threading.Thread(
            target=self._progress_loop, daemon=True,
        )
        t.start()

        max_inflight = self.config.workers * 4
        cfg = self.config
        with ThreadPoolExecutor(
            max_workers=cfg.workers,
        ) as pool:
            pending: set = set()
            q_iter = iter(queue)
            exhausted = False

            def _feed_pending():
                nonlocal exhausted
                while not exhausted and len(pending) < max_inflight and not self._stop.is_set():
                    try:
                        item = next(q_iter)
                    except StopIteration:
                        exhausted = True
                        break
                    pending.add(pool.submit(self._transfer_one, *item))
                    if len(pending) > self.stats.peak_queue_size:
                        self.stats.peak_queue_size = len(pending)

            _feed_pending()

            # Drain: wait for completions, feed new items
            while pending or not exhausted:
                if self._stop.is_set():
                    break
                if not pending:
                    _feed_pending()
                    if not pending:
                        continue
                done, pending = wait(
                    pending, return_when=FIRST_COMPLETED,
                )
                for fut in done:
                    try:
                        fut.result()
                    except Exception:
                        pass  # Errors handled inside _transfer_one

                    # Network recovery: when consecutive failures exceed
                    # threshold, pause and wait for the network to recover
                    # (VPN reconnect, SMB re-establishment).
                    if self.stats.consecutive_failures >= \
                       cfg.max_consecutive_failures:
                        self._network_recovery_wait()

                    _feed_pending()

                    # Periodic GC for multi-day transfers
                    processed = self.stats.files_processed
                    if cfg.gc_interval > 0 and \
                       processed > 0 and processed % cfg.gc_interval == 0:
                        gc.collect()
                        self.stats.gc_collections += 1

        self._stop.set()

    def _network_recovery_wait(self) -> None:
        """Pause transfer and wait for network to recover.

        NON-PROGRAMMER NOTE:
          When many files fail in a row (e.g., 20 straight failures), it
          usually means the VPN dropped or the SMB server is unreachable.
          Rather than burning through the entire queue with failures, we
          pause all workers and check if the source is reachable. We start
          by waiting 30 seconds, then double the wait each time (up to 10
          minutes). As soon as the first source responds, we resume.

          Backoff sequence: 30s -> 60s -> 120s -> 240s -> 480s -> 600s (cap)
        """
        cfg = self.config
        base_wait = cfg.network_recovery_wait
        self.stats.network_stalls += 1
        with self._log_lock:
            print(
                f"\n  [WARN] {self.stats.consecutive_failures} consecutive "
                f"failures -- pausing for network recovery ({base_wait:.0f}s)"
            )

        while not self._stop.is_set():
            # Count down the current wait in 5s increments so we can
            # check the stop event frequently (responsive to Ctrl+C).
            remaining = base_wait
            while remaining > 0 and not self._stop.is_set():
                time.sleep(min(remaining, 5.0))
                remaining -= 5.0

            if self._stop.is_set():
                return

            # Check if any source path is reachable
            reachable = False
            for sp in cfg.source_paths:
                try:
                    os.listdir(sp)
                    reachable = True
                    break
                except OSError:
                    pass

            if reachable:
                self.stats.consecutive_failures = 0
                with self._log_lock:
                    print(
                        "\n  [OK] Network recovered, resuming transfer"
                    )
                return

            # Exponential backoff: double the wait each cycle
            self.stats.network_recovery_time += base_wait
            base_wait = min(base_wait * 2, cfg.network_recovery_max_wait)
            with self._log_lock:
                print(
                    f"\n  [WARN] Network still down, "
                    f"waiting {base_wait:.0f}s..."
                )

    def _discard_tmp(self, tmp_path: Path) -> None:
        """Best-effort cleanup for a duplicate or abandoned temp file."""
        try:
            tmp_path.unlink(missing_ok=True)
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug("tmp cleanup failed for %s: %s", tmp_path, e)

    def _claim_dedup_hash(
        self, content_hash: str,
    ) -> Tuple[str, Optional[object], str]:
        """
        Claim a content hash for verified promotion, or wait for the
        worker already handling that hash to finish.
        """
        with self._dedup_cond:
            while True:
                existing = self.manifest.find_by_hash(content_hash)
                if existing:
                    return ("duplicate", None, existing)

                claim = self._dedup_claims.get(content_hash)
                if claim is None or claim.get("status") == "failed":
                    token = object()
                    self._dedup_claims[content_hash] = {
                        "owner": token,
                        "status": "pending",
                        "dest_path": "",
                    }
                    return ("owner", token, "")

                if claim.get("status") == "success":
                    return (
                        "duplicate",
                        None,
                        str(claim.get("dest_path", "")),
                    )

                if self._stop.is_set():
                    return ("stopped", None, "")

                self._dedup_cond.wait(timeout=0.5)

    def _finish_dedup_claim(
        self, content_hash: str, token: object,
        *, success: bool, dest_path: str = "",
    ) -> None:
        """Resolve a hash claim and wake any waiting duplicate workers."""
        with self._dedup_cond:
            claim = self._dedup_claims.get(content_hash)
            if not claim or claim.get("owner") is not token:
                return
            claim["status"] = "success" if success else "failed"
            claim["dest_path"] = str(dest_path or "")
            self._dedup_cond.notify_all()

    # ------------------------------------------------------------------
    # Single-file atomic copy
    # ------------------------------------------------------------------

    def _transfer_one(
        self, source: str, source_root: str,
        rel: str, file_size: int,
    ) -> None:
        """Transfer one file using the atomic copy pattern."""
        cfg = self.config
        ext = os.path.splitext(source)[1].lower()
        t_start = datetime.now(timezone.utc).isoformat()
        start_time = time.monotonic()
        hash_src = ""
        claim_token: Optional[object] = None

        try:
            # Step 1: Snapshot the source before transfer
            pre_stat = _stat_with_timeout(source)

            # Step 2: Locked file detection
            if not _can_read_file(source):
                self.stats.files_skipped_locked += 1
                self.manifest.record_transfer(
                    self.run_id, source, result="locked",
                    error_message="File locked or in use",
                    transfer_start=t_start,
                )
                self.manifest.record_skip(
                    self.run_id, source, file_size, ext,
                    "locked",
                    "File locked/in-use at transfer time",
                )
                return

            # Step 3: Atomic copy (source -> incoming/.tmp) while
            # streaming the source SHA-256 so the source is read only once.
            root_name = Path(source_root).name
            if len(cfg.source_paths) > 1:
                root_key = hashlib.md5(
                    source_root.encode(),
                ).hexdigest()[:6]
                root_name = f"{root_name}_{root_key}"
            dest_rel = os.path.join(root_name, rel)
            tmp_path = self.staging.incoming_path(dest_rel)

            copied = False
            last_err = ""
            retries = 0
            # Stall timeout (not total-file timeout): fail a copy attempt if
            # no forward progress is observed for this many seconds.
            copy_timeout = 60.0
            for attempt in range(1, cfg.max_retries + 1):
                try:
                    hash_src = _buffered_copy(
                        source, str(tmp_path),
                        cfg.copy_buffer_size, cfg.bandwidth_limit,
                        timeout=copy_timeout,
                        stop_event=self._stop,
                        progress_cb=self.stats.note_stream_bytes,
                        hash_source=True,
                    )
                    # Backward-compatibility for older monkeypatched copy
                    # helpers in tests that still return None.
                    if not hash_src:
                        hash_src = _hash_file(source)
                    if not hash_src:
                        raise OSError("Cannot read source while copying")
                    copied = True
                    break
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
                    retries = attempt - 1
                    if isinstance(e, InterruptedError) or self._stop.is_set():
                        self.manifest.record_transfer(
                            self.run_id, source, result="stopped",
                            hash_source=hash_src, retry_count=retries,
                            error_message="Stopped by user during copy",
                            transfer_start=t_start,
                        )
                        return
                    # TimeoutError with an errno (e.g., ETIMEDOUT) is a
                    # network timeout -- retryable. TimeoutError without
                    # an errno is our copy-stall detector -- NOT retryable
                    # (the file is stuck on a dead network path).
                    if isinstance(e, TimeoutError) and \
                       not getattr(e, "errno", 0):
                        break
                    if isinstance(e, OSError) and \
                       getattr(e, "errno", 0) == errno.ENOSPC:
                        break
                    if attempt < cfg.max_retries:
                        base = cfg.retry_backoff ** attempt
                        time.sleep(base * random.uniform(0.5, 1.5))

            if not copied:
                self.stats.files_failed += 1
                self.stats.consecutive_failures += 1
                # Only quarantine if the .tmp file was actually created.
                # If the copy failed before writing any data (e.g.,
                # network unreachable before socket connects), the .tmp
                # file won't exist and quarantine_file would raise
                # FileNotFoundError, masking the original error.
                if tmp_path.exists():
                    self.staging.quarantine_file(
                        tmp_path, dest_rel,
                        f"Copy failed: {last_err}",
                    )
                    self.stats.files_quarantined += 1
                self.manifest.record_transfer(
                    self.run_id, source, result="failed",
                    hash_source=hash_src, retry_count=retries,
                    error_message=last_err,
                    transfer_start=t_start,
                )
                return

            # Source stability check: if the file changed while we were
            # reading it, do not trust the copied snapshot.
            try:
                post_stat = _stat_with_timeout(source)
                if post_stat.st_mtime != pre_stat.st_mtime or \
                   post_stat.st_size != pre_stat.st_size:
                    self.stats.files_quarantined += 1
                    q_path = self.staging.quarantine_file(
                        tmp_path, dest_rel,
                        "Source file modified during copy "
                        "(mtime or size changed)",
                    )
                    self.manifest.record_transfer(
                        self.run_id, source, dest_path=str(q_path),
                        file_size_source=file_size,
                        file_size_dest=_stat_with_timeout(str(q_path)).st_size,
                        hash_source=hash_src,
                        transfer_start=t_start,
                        transfer_end=datetime.now(timezone.utc).isoformat(),
                        duration_sec=time.monotonic() - start_time,
                        speed_mbps=(
                            file_size / max(time.monotonic() - start_time, 0.001)
                        ) / (1024 * 1024),
                        result="failed", retry_count=retries,
                        error_message=(
                            "Source file modified during copy "
                            "(mtime or size changed)"
                        ),
                    )
                    return
            except (OSError, TimeoutError):
                pass

            # Step 4: Deduplication check after copy. Waiting workers will
            # discard duplicate temp files once the first verified result
            # for this hash is known.
            if cfg.deduplicate:
                claim_state, claim_token, existing = self._claim_dedup_hash(
                    hash_src
                )
                if claim_state == "stopped":
                    self._discard_tmp(tmp_path)
                    self.manifest.record_transfer(
                        self.run_id, source, result="stopped",
                        hash_source=hash_src, retry_count=retries,
                        error_message="Stopped while waiting on dedup result",
                        transfer_start=t_start,
                    )
                    return
                if claim_state == "duplicate":
                    self._discard_tmp(tmp_path)
                    self.stats.files_deduplicated += 1
                    self.manifest.record_transfer(
                        self.run_id, source, dest_path=existing,
                        hash_source=hash_src,
                        result="skipped_duplicate",
                        transfer_start=t_start,
                    )
                    return

            # Step 5: Hash destination after transfer when verification is on
            hash_dst = ""
            if cfg.verify_copies:
                hash_dst = _hash_file(str(tmp_path))
            dur = time.monotonic() - start_time
            speed = (file_size / max(dur, 0.001)) / (1024 * 1024)
            t_end = datetime.now(timezone.utc).isoformat()

            # Step 6: Compare hashes
            if cfg.verify_copies and hash_src != hash_dst:
                self.stats.files_verify_failed += 1
                self.stats.files_quarantined += 1
                q_path = self.staging.quarantine_file(
                    tmp_path, dest_rel,
                    f"Hash mismatch: src={hash_src[:16]} "
                    f"dst={hash_dst[:16]}",
                )
                if claim_token is not None:
                    self._finish_dedup_claim(
                        hash_src, claim_token, success=False,
                    )
                    claim_token = None
                self.manifest.record_transfer(
                    self.run_id, source, dest_path=str(q_path),
                    file_size_source=file_size,
                    file_size_dest=_stat_with_timeout(str(q_path)).st_size,
                    hash_source=hash_src, hash_dest=hash_dst,
                    transfer_start=t_start, transfer_end=t_end,
                    duration_sec=dur, speed_mbps=speed,
                    result="hash_mismatch", retry_count=retries,
                )
                return

            if cfg.verify_copies:
                self.stats.files_verified += 1

            # Step 7: Promote to verified/
            final = self.staging.promote_to_verified(
                tmp_path, dest_rel,
            )

            # Step 8: Preserve original timestamps
            try:
                orig_st = _stat_with_timeout(source)
                os.utime(
                    to_io_path(str(final)),
                    (orig_st.st_atime, orig_st.st_mtime),
                )
            except Exception:
                pass

            # Record success
            self.stats.record_copy(file_size, ext, source_root)
            self.manifest.record_transfer(
                self.run_id, source, dest_path=str(final),
                file_size_source=file_size,
                file_size_dest=_stat_with_timeout(str(final)).st_size,
                hash_source=hash_src, hash_dest=hash_dst,
                transfer_start=t_start, transfer_end=t_end,
                duration_sec=dur, speed_mbps=speed,
                result="success", retry_count=retries,
            )
            # Update source_manifest with content_hash.
            # IMPORTANT: preserve file_mtime from the pre-transfer stat
            # so resume checks (is_already_transferred) can compare
            # mtimes on the next run.  Without this, INSERT OR REPLACE
            # clobbers file_mtime to 0 and resume never matches.
            self.manifest.record_source_file(
                self.run_id, source, file_size=file_size,
                file_mtime=pre_stat.st_mtime,
                file_ctime=getattr(pre_stat, "st_ctime", 0.0),
                content_hash=hash_src, extension=ext,
            )
            if claim_token is not None:
                self._finish_dedup_claim(
                    hash_src, claim_token, success=True,
                    dest_path=str(final),
                )
                claim_token = None

            # Reset consecutive failure counter on success (network is OK)
            self.stats.consecutive_failures = 0

        except Exception as e:
            if claim_token is not None and hash_src:
                self._finish_dedup_claim(
                    hash_src, claim_token, success=False,
                )
            self.stats.files_failed += 1
            self.stats.consecutive_failures += 1
            self.stats.record_source_event(source_root, "failed")
            self.manifest.record_transfer(
                self.run_id, source, result="failed",
                error_message=f"{type(e).__name__}: {e}",
                transfer_start=t_start,
            )

    # ------------------------------------------------------------------
    # Progress display
    # ------------------------------------------------------------------

    def _progress_loop(self) -> None:
        """Print live progress every 2 seconds."""
        sample_interval = 30.0
        last_sample = 0.0
        while not self._stop.is_set():
            print(
                f"\r  {self.stats.summary_line()}",
                end="", flush=True,
            )
            elapsed = self.stats.elapsed
            if elapsed - last_sample >= sample_interval:
                speed = self.stats.speed_bps
                history = self.stats._speed_history
                history.append((elapsed, speed))
                # Cap speed history to prevent unbounded memory growth
                # during multi-day transfers. Keep the most recent samples.
                cap = self.stats._max_speed_history
                if len(history) > cap:
                    self.stats._speed_history = history[-cap:]
                last_sample = elapsed
            self._stop.wait(timeout=2.0)
        print()


# ============================================================================
# Bulk Transfer Engine V2 (Orchestrator)
# ============================================================================
# Coordinates SourceDiscovery (Phase 1) and AtomicTransferWorker (Phase 2)
# into a three-phase transfer pipeline with delta analysis and reporting.
# ============================================================================

class BulkTransferV2:
    """
    Production-grade file transfer engine with atomic copy pattern,
    three-stage staging, delta sync, and zero-gap manifest tracking.

    Delegates discovery to SourceDiscovery and parallel transfer
    to AtomicTransferWorker, keeping this class as a slim orchestrator.
    """

    def __init__(self, config: TransferConfig) -> None:
        config.workers = min(max(config.workers, 1), 32)
        self.config = config
        # Include microseconds in run_id so rapid sequential runs
        # (e.g., nightly tests) don't collide on the same second.
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        self.stats = TransferStats()
        self.stats._max_speed_history = config.max_speed_history
        self.manifest: Optional[TransferManifest] = None
        self.staging: Optional[StagingManager] = None
        self._stop = threading.Event()
        self._checkpoint_thread: Optional[threading.Thread] = None
        self._log_lock = threading.Lock()
        self._json_log: Optional[Any] = None

    def run(self) -> TransferStats:
        """Execute the full three-phase transfer pipeline."""
        cfg = self.config
        dest = Path(cfg.dest_path)
        dest.mkdir(parents=True, exist_ok=True)

        # Initialize JSON log file if configured
        if cfg.log_file:
            self._init_json_log(cfg.log_file)

        # Initialize subsystems
        db_path = str(dest / "_transfer_manifest.db")
        self.manifest = TransferManifest(db_path)
        self.staging = StagingManager(str(dest))
        self.manifest.start_run(
            self.run_id, cfg.source_paths, cfg.dest_path,
            config_json=json.dumps({
                "workers": cfg.workers,
                "deduplicate": cfg.deduplicate,
                "verify": cfg.verify_copies,
                "extensions": len(cfg.extensions),
                "resume_seed_from_manifest": cfg.resume_seed_from_manifest,
                "resume_seed_limit": cfg.resume_seed_limit,
                "skip_full_discovery": cfg.skip_full_discovery,
            }),
        )

        # Clean leftover .tmp files from crashed runs
        cleaned = self.staging.cleanup_incoming()
        if cleaned:
            print(f"  [OK] Cleaned {cleaned} leftover .tmp files")

        # Banner
        print("=" * 70)
        print("  BULK TRANSFER V2 -- Starting")
        print("=" * 70)
        print(f"  Run ID:      {self.run_id}")
        print(f"  Sources:     {len(cfg.source_paths)}")
        for sp in cfg.source_paths:
            print(f"               {sp}")
        print(f"  Staging:     {dest}")
        print(f"  Workers:     {cfg.workers}")
        print(f"  Atomic copy: YES (.tmp -> verify -> rename)")
        print(f"  Dedup:       {'ON' if cfg.deduplicate else 'OFF'}")
        print(f"  Verify:      {'ON' if cfg.verify_copies else 'OFF'}")
        print("=" * 70)
        print()

        # Start checkpoint thread for multi-day monitoring
        self._start_checkpoint_thread()

        try:
            # Phase 1+2: Stream discovery directly into transfer workers
            print("[PHASE 1+2] Streaming discovery + transfer...")
            self._log_event("phase_start", phase=1, detail="Source discovery")
            discoverer = SourceDiscovery(
                cfg, self.manifest, self.stats,
                self.run_id, self._log_lock, self._stop,
            )
            worker = AtomicTransferWorker(
                cfg, self.manifest, self.staging, self.stats,
                self.run_id, self._stop, self._log_lock,
            )
            def _stream_candidates():
                seeded_any = False
                for item in discoverer.resume_seed_iter():
                    seeded_any = True
                    yield item
                if cfg.skip_full_discovery:
                    if not seeded_any:
                        self._log(
                            "  [WARN] skip_full_discovery=True but no resume seed "
                            "candidates were found in prior manifests. "
                            "Falling back to live discovery."
                        )
                    else:
                        return
                for item in discoverer.discover_iter():
                    yield item

            worker.transfer(_stream_candidates())
            self.stats.files_manifest = self.manifest.count_source_manifest_rows(
                self.run_id
            )
            print(
                f"  Manifest: {self.stats.files_manifest:,} files, "
                f"{_fmt_size(self.stats.bytes_source_total)}"
            )
            self._log_event(
                "discovery_complete",
                files_discovered=self.stats.files_discovered,
                queue_size=self.stats.peak_queue_size,
                bytes_total=self.stats.bytes_source_total,
            )

            # Phase 1b: Delta sync analysis
            prev = self.manifest.get_previous_manifest(self.run_id)
            if prev:
                self._delta_analysis([], prev)
            print()

            # Phase 3: Finalize
            print()
            print("[PHASE 3] Finalizing...")
            self._log_event("phase_start", phase=3, detail="Finalize")
            self.manifest.finish_run(self.run_id)
            rotated = self.manifest.rotate_old_runs(keep=10)
            if rotated:
                print(
                    f"  [OK] Rotated {rotated} old run(s) "
                    f"from manifest DB"
                )
            report = self.manifest.get_verification_report(
                self.run_id,
            )
            print(report)

            # Final GC pass
            gc.collect()
            self.stats.gc_collections += 1

        except KeyboardInterrupt:
            print("\n  [INTERRUPTED] Progress saved. Re-run to resume.")
            self._stop.set()
            self._log_event("interrupted", detail="KeyboardInterrupt")
        finally:
            self._stop_checkpoint_thread()

            # Emit final stats and complete event BEFORE closing log
            self._emit_progress()
            self._log_event("complete", **self._stats_snapshot())

            if self.manifest:
                self.manifest.flush()
                self.manifest.close()
            self._close_json_log()

        print(self.stats.full_report())
        return self.stats

    # ------------------------------------------------------------------
    # Phase 1b: Delta Analysis
    # ------------------------------------------------------------------

    def _delta_analysis(
        self,
        queue: List[Tuple[str, str, str, int]],
        prev_manifest: Dict[str, str],
    ) -> None:
        """Compare current manifest against previous run."""
        with self.manifest._lock:
            rows = self.manifest.conn.execute(
                "SELECT source_path FROM source_manifest "
                "WHERE run_id=?",
                (self.run_id,),
            ).fetchall()
        current_paths = {r[0] for r in rows}

        for prev_path in prev_manifest:
            if prev_path not in current_paths:
                self.stats.files_delta_deleted += 1

        for path in current_paths:
            if path not in prev_manifest:
                self.stats.files_delta_new += 1

        print(
            f"  Delta: {self.stats.files_delta_new:,} new, "
            f"{self.stats.files_delta_deleted:,} deleted"
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Thread-safe print."""
        with self._log_lock:
            print(f"\n{msg}", flush=True)

    # ------------------------------------------------------------------
    # JSON event log (machine-readable audit trail for nightly cron)
    # ------------------------------------------------------------------
    # Complements the SQLite manifest (per-file) and text report
    # (final summary) with timestamped operational events that a
    # monitoring script can tail during multi-day transfers.
    # ------------------------------------------------------------------

    def _init_json_log(self, path: str) -> None:
        """Open a JSON-lines log file for event recording."""
        try:
            parent = Path(path).parent
            parent.mkdir(parents=True, exist_ok=True)
            self._json_log = open(path, "a", encoding="utf-8")
        except Exception as e:
            logger.warning("Cannot open JSON log %s: %s", path, e)
            self._json_log = None

    def _close_json_log(self) -> None:
        """Flush and close the JSON event log."""
        if self._json_log:
            try:
                self._json_log.flush()
                self._json_log.close()
            except Exception:
                pass
            self._json_log = None

    def _log_event(self, event: str, **data: Any) -> None:
        """Write one JSON-lines event (timestamp + event + data)."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        if self._json_log:
            try:
                self._json_log.write(json.dumps(entry) + "\n")
                self._json_log.flush()
            except Exception:
                pass
        logger.debug("transfer_event: %s", entry)

    def _stats_snapshot(self) -> Dict[str, Any]:
        """Return a dict of current stats for logging/callbacks."""
        s = self.stats
        return {
            "elapsed": round(s.elapsed, 1),
            "files_copied": s.files_copied,
            "files_failed": s.files_failed,
            "files_skipped_unchanged": s.files_skipped_unchanged,
            "files_deduplicated": s.files_deduplicated,
            "files_quarantined": s.files_quarantined,
            "bytes_copied": s.bytes_copied,
            "bytes_total": s.bytes_source_total,
            "speed_bps": round(s.speed_bps, 0),
            "network_stalls": s.network_stalls,
            "gc_collections": s.gc_collections,
            "consecutive_failures": s.consecutive_failures,
        }

    # ------------------------------------------------------------------
    # Progress callback (GUI integration point)
    # ------------------------------------------------------------------

    def _emit_progress(self) -> None:
        """Send current stats to the progress callback if configured."""
        cb = self.config.progress_callback
        if cb:
            try:
                cb(self._stats_snapshot())
            except Exception:
                pass

    def _start_checkpoint_thread(self) -> None:
        """Start the periodic checkpoint logger for this run."""
        self._stop.clear()
        self._checkpoint_thread = threading.Thread(
            target=self._checkpoint_loop,
            daemon=True,
        )
        self._checkpoint_thread.start()

    def _stop_checkpoint_thread(self) -> None:
        """Stop and join the checkpoint thread before teardown."""
        self._stop.set()
        thread = self._checkpoint_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=10.0)
        self._checkpoint_thread = None

    # ------------------------------------------------------------------
    # Checkpoint loop (periodic summary during multi-day runs)
    # ------------------------------------------------------------------
    # The existing full_report() and verification_report only run at
    # the END of a transfer. This loop prints periodic summaries DURING
    # the transfer so you can check on a 5-day nightly run.
    # ------------------------------------------------------------------

    def _checkpoint_loop(self) -> None:
        """Periodically log checkpoint summaries and trigger GC."""
        cfg = self.config
        gc_counter = 0
        while not self._stop.is_set():
            self._stop.wait(timeout=cfg.checkpoint_interval)
            if self._stop.is_set():
                break

            self.stats.checkpoints_logged += 1
            snap = self._stats_snapshot()
            self._log_event("checkpoint", **snap)
            self._emit_progress()

            # Periodic garbage collection to prevent memory creep
            # during multi-day transfers with millions of files.
            gc_counter += 1
            if gc_counter * cfg.checkpoint_interval >= cfg.gc_interval:
                gc.collect()
                self.stats.gc_collections += 1
                gc_counter = 0


# ============================================================================
# Utility Functions (module-level, not in any class)
# ============================================================================

def _stat_with_timeout(path: str, timeout: float = 10.0) -> os.stat_result:
    """
    Run os.stat() in a daemon thread with a timeout.

    Raises TimeoutError if stat hangs (e.g., VPN disconnect on SMB path).
    Raises OSError/PermissionError if stat fails normally.
    """
    result = [None]
    error = [None]

    def _do_stat():
        try:
            result[0] = os.stat(to_io_path(path))
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_do_stat, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        raise TimeoutError(f"os.stat() timed out after {timeout}s: {path}")
    if error[0] is not None:
        raise error[0]
    return result[0]


def _hash_file(path: str, timeout: float = 120.0) -> str:
    """
    Compute SHA-256 hash of a file's contents.

    NON-PROGRAMMER NOTE:
      SHA-256 is a "fingerprint" for file contents. Two files with
      the same SHA-256 hash are identical (the probability of a false
      match is 1 in 2^256, which is effectively impossible).

      We read the file in 128 KB chunks to avoid loading multi-GB
      files entirely into memory. If reading takes longer than
      timeout seconds (default 120s), returns empty string to avoid
      hanging on stalled network reads.

      The cancel_event tells the inner thread to stop reading when the
      outer timeout fires, preventing abandoned daemon threads from
      accumulating over long transfers.

    Returns empty string if the file cannot be read.
    """
    result_holder = [None]
    error_holder = [None]
    cancel = threading.Event()

    def _do_hash():
        # Retry once on transient OSError (e.g., brief network hiccup).
        # PermissionError is not retried -- it means access denied.
        for attempt in range(2):
            h = hashlib.sha256()
            t0 = time.monotonic()
            try:
                with open(to_io_path(path), "rb") as f:
                    while not cancel.is_set():
                        chunk = f.read(131072)  # 128 KB chunks
                        if not chunk:
                            break
                        h.update(chunk)
                        if time.monotonic() - t0 > timeout:
                            error_holder[0] = "timeout"
                            return
                if cancel.is_set():
                    error_holder[0] = "cancelled"
                    return
                result_holder[0] = h.hexdigest()
                error_holder[0] = None  # Clear prior transient error on success
                return
            except PermissionError as e:
                error_holder[0] = str(e)
                return  # Not retryable
            except OSError as e:
                error_holder[0] = str(e)
                if attempt == 0 and not cancel.is_set():
                    time.sleep(0.5)  # Brief pause before retry

    t = threading.Thread(target=_do_hash, daemon=True)
    t.start()
    t.join(timeout=timeout + 5.0)
    if t.is_alive():
        # Signal the thread to stop reading and give it a moment
        cancel.set()
        t.join(timeout=2.0)
        return ""
    if error_holder[0] is not None:
        return ""
    return result_holder[0] or ""


def _can_read_file(path: str, timeout: float = 5.0) -> bool:
    """
    Test if a file can be opened for reading (not locked).

    NON-PROGRAMMER NOTE:
      Some files are "locked" by the program using them. For example,
      Outlook locks .pst files, and Word locks .docx files while
      they're open. We test by trying to read 1 byte. If even that
      fails (or hangs beyond timeout), the file is locked and we
      should skip it rather than wait or copy a corrupt partial version.
    """
    result = [False]

    def _try_read():
        try:
            with open(to_io_path(path), "rb") as f:
                f.read(1)
            result[0] = True
        except (OSError, PermissionError):
            pass

    t = threading.Thread(target=_try_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


def _buffered_copy(
    src: str, dst: str, buf_size: int = 1_048_576,
    bw_limit: int = 0, timeout: float = 0, stop_event: threading.Event = None,
    progress_cb=None, hash_source: bool = False,
) -> str:
    """
    Copy a file using buffered reads with optional bandwidth limiting.

    If timeout > 0, timeout is treated as a STALL timeout (seconds
    without forward progress). Large files are allowed to run as long
    as bytes continue flowing. If progress stalls (e.g., dead SMB read),
    TimeoutError is raised and the partial .tmp file is left for the
    caller to quarantine.
    """
    if timeout > 0:
        error_holder = [None]
        result_holder = [""]
        last_progress = [time.monotonic()]

        def _touch_progress():
            last_progress[0] = time.monotonic()

        def _do_copy():
            try:
                result_holder[0] = _buffered_copy_inner(
                    src,
                    dst,
                    buf_size,
                    bw_limit,
                    stop_event=stop_event,
                    progress_touch=_touch_progress,
                    progress_cb=progress_cb,
                    hash_source=hash_source,
                )
            except Exception as e:
                error_holder[0] = e

        t = threading.Thread(target=_do_copy, daemon=True)
        t.start()
        # Poll until done, but fail if no progress is observed.
        poll_sleep = 0.5
        while t.is_alive():
            t.join(timeout=poll_sleep)
            if (time.monotonic() - last_progress[0]) > timeout:
                raise TimeoutError(
                    f"_buffered_copy stalled for >{timeout:.0f}s: {src}"
                )
        if error_holder[0] is not None:
            raise error_holder[0]
        return result_holder[0]
    else:
        return _buffered_copy_inner(
            src, dst, buf_size, bw_limit, stop_event=stop_event,
            progress_cb=progress_cb, hash_source=hash_source,
        )


def _buffered_copy_inner(
    src: str, dst: str, buf_size: int = 1_048_576,
    bw_limit: int = 0, stop_event: threading.Event = None,
    progress_touch=None, progress_cb=None, hash_source: bool = False,
) -> str:
    """Inner copy logic (no timeout wrapper)."""
    hasher = hashlib.sha256() if hash_source else None
    with open(to_io_path(src), "rb") as fsrc, open(to_io_path(dst), "wb") as fdst:
        if progress_touch is not None:
            progress_touch()
        while True:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("copy cancelled by stop request")
            t0 = time.monotonic()
            data = fsrc.read(buf_size)
            if not data:
                break
            if hasher is not None:
                hasher.update(data)
            fdst.write(data)
            if progress_touch is not None:
                progress_touch()
            if progress_cb is not None:
                progress_cb(len(data))
            if bw_limit > 0:
                elapsed = time.monotonic() - t0
                expected = len(data) / bw_limit
                if expected > elapsed:
                    time.sleep(expected - elapsed)
        # Flush OS buffers to disk. If the system crashes between
        # close() and the OS flushing, the .tmp file is truncated.
        # The hash check would catch it on re-read, but fsync
        # eliminates the window entirely.
        fdst.flush()
        os.fsync(fdst.fileno())
    return hasher.hexdigest() if hasher is not None else ""


def _fmt_size(b) -> str:
    """Format bytes as human-readable string (KB, MB, GB)."""
    b = float(b)
    if b < 1024:
        return f"{b:.0f} B"
    elif b < 1024**2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024**3:
        return f"{b / 1024**2:.1f} MB"
    return f"{b / 1024**3:.2f} GB"


def _fmt_dur(s: float) -> str:
    """Format seconds as human-readable duration (e.g., '2m 30s')."""
    if s < 60:
        return f"{s:.1f}s"
    elif s < 3600:
        m, sec = divmod(s, 60)
        return f"{int(m)}m {int(sec)}s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h)}h {int(m)}m"


# ============================================================================
# CLI Entry Point
# ============================================================================

def main() -> None:
    """
    Command-line interface for the bulk transfer engine.

    NON-PROGRAMMER NOTE:
      Run this from the terminal:
        python -m src.tools.bulk_transfer_v2 --sources "\\\\server\\share" --dest "D:\\staging"

      Use --help to see all available options.
    """
    import argparse
    p = argparse.ArgumentParser(
        description="HybridRAG Bulk Transfer V2 -- "
                    "Production-grade file transfer for RAG source preparation",
    )
    p.add_argument(
        "--sources", nargs="+", required=True,
        help="One or more source directories (UNC paths or local)",
    )
    p.add_argument(
        "--dest", required=True,
        help="Destination staging directory",
    )
    p.add_argument(
        "--workers", type=int, default=8,
        help="Number of parallel transfer threads (default: 8)",
    )
    p.add_argument("--no-dedup", action="store_true",
                    help="Disable content deduplication")
    p.add_argument("--no-verify", action="store_true",
                    help="Skip SHA-256 hash verification")
    p.add_argument("--no-resume", action="store_true",
                    help="Ignore previous runs, transfer everything")
    p.add_argument("--no-resume-seed", action="store_true",
                    help="Disable manifest-first resume seeding")
    p.add_argument(
        "--resume-seed-limit", type=int, default=0,
        help="Cap manifest-first resume candidates (0 = unlimited)",
    )
    p.add_argument("--include-hidden", action="store_true",
                    help="Include hidden and system files")
    p.add_argument("--follow-symlinks", action="store_true",
                    help="Follow symlinks and junction points")
    p.add_argument("--bandwidth-limit", type=int, default=0,
                    help="Bandwidth limit in bytes/sec (0 = unlimited)")
    args = p.parse_args()

    cfg = TransferConfig(
        source_paths=args.sources,
        dest_path=args.dest,
        workers=args.workers,
        deduplicate=not args.no_dedup,
        verify_copies=not args.no_verify,
        resume=not args.no_resume,
        resume_seed_from_manifest=not args.no_resume_seed,
        resume_seed_limit=args.resume_seed_limit,
        include_hidden=args.include_hidden,
        follow_symlinks=args.follow_symlinks,
        bandwidth_limit=args.bandwidth_limit,
    )
    engine = BulkTransferV2(cfg)
    stats = engine.run()
    sys.exit(0 if stats.files_failed == 0 else 1)


if __name__ == "__main__":
    main()
