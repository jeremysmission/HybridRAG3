# ============================================================================
# HybridRAG -- Indexer (src/core/indexer.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   This is the "brain" of the indexing pipeline. It orchestrates:
#     scan folder -> preflight check -> parse each file -> chunk -> embed -> store
#
#   This is the module that runs for your week-long indexing job.
#
# KEY DESIGN DECISIONS:
#
#   1. Process files in blocks (not all text at once)
#      WHY: A single 500-page PDF can produce 2 million characters of text.
#      Loading that all into RAM, chunking it, and embedding it would spike
#      memory. Instead we break the text into blocks of ~200K chars, process
#      each block, write to disk, then move on. RAM stays stable.
#
#   2. Deterministic chunk IDs (from chunk_ids.py)
#      WHY: If indexing crashes at file #4,000 out of 10,000 and you restart,
#      deterministic IDs mean "INSERT OR IGNORE" in SQLite skips the first
#      4,000 files' chunks automatically. No duplicates, no manual cleanup.
#
#   3. Skip unchanged files (hash-based change detection)
#      WHY: Your enterprise drive has 100GB of documents. Most don't change
#      week to week. We store a hash (size + mtime) with each file's chunks.
#      On restart, we compare the stored hash to the current file. If they
#      match, skip it. If they differ, the file was modified -- delete old
#      chunks and re-index. This turns a 7-day re-index into minutes.
#
#   4. Never crash on a single file failure
#      WHY: File #3,000 might be a corrupted PDF. If we crash, you lose
#      3 days of indexing progress. Instead, we log the error and continue
#      to file #3,001. You can review failures in the log after.
#
#   5. Pre-flight integrity checks (NEW 2026-02-15)
#      WHY: BUG-004 showed that _validate_text() only checks the first
#      2000 chars of parsed output. Corrupt files (incomplete torrents,
#      Word temp files, broken ZIPs) can pass that check but still
#      produce garbage that pollutes the vector store. The pre-flight
#      gate catches these BEFORE the parser even runs -- zero wasted time,
#      zero garbage in the index. Results are logged to the indexing
#      summary so the admin knows what was blocked and why.
#
# BUGS FIXED (2026-02-08):
#   BUG-001: Hash detection uses vector_store.get_file_hash() in index_folder()
#            of raw SQL against a column that didn't exist.
#   BUG-002: Change detection logic inlined in index_folder() using
#            _compute_file_hash() + get_file_hash(). Dead _file_changed()
#            method removed 2026-02-14.
#            Previously only _file_already_indexed() was called, which just
#            checked "do chunks exist?" without checking if the file changed.
#   BUG-003: Added close() method to release the embedder model from RAM.
#   BUG-004: Added _validate_text() to catch binary garbage before chunking.
#   BUG-004b: Added _preflight_check() to catch corrupt files before parsing.
#             This catches Word temp files, zero-byte, broken ZIPs, truncated
#             PDFs, and high null-byte ratios BEFORE the parser runs.
#
# ALTERNATIVES CONSIDERED:
#   - LangChain DirectoryLoader: hides logic in "magic" class, impossible
#     to debug. We control every step.
#   - Async/parallel indexing: faster but much harder to debug and resume.
#   - Hash-based detection using xxhash on file content: more accurate but
#     reads every file on every run. Size+mtime is instant and good enough.
# ============================================================================

from __future__ import annotations

import logging
import os
import time
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from .config import Config
from .vector_store import VectorStore, ChunkMetadata
from .chunker import Chunker, ChunkerConfig
from .embedder import Embedder
from .chunk_ids import make_chunk_id
from .file_validator import FileValidator
from .indexing.cancel import IndexCancelled
import gc


# -------------------------------------------------------------------
# Progress callback interface
# -------------------------------------------------------------------

class IndexingProgressCallback:
    """
    Override these methods to receive progress updates during indexing.

    Default implementations do nothing (safe no-op). Subclass this and
    override methods for progress bars, GUI updates, or logging.
    """

    def on_file_start(self, file_path: str, file_num: int, total_files: int) -> None:
        pass

    def on_file_complete(self, file_path: str, chunks_created: int) -> None:
        pass

    def on_file_skipped(self, file_path: str, reason: str) -> None:
        pass

    def on_indexing_complete(self, total_chunks: int, elapsed_seconds: float) -> None:
        pass

    def on_error(self, file_path: str, error: str) -> None:
        pass

    def on_discovery_progress(self, files_found: int) -> None:
        pass


# -------------------------------------------------------------------
# Indexer
# -------------------------------------------------------------------

class Indexer:
    """
    Scans a folder, parses files, chunks text, embeds, and stores.

    Designed for multi-day indexing runs on laptops (24/7 for a week),
    resumable-safe operation, low memory usage, and auditable environments.
    """

    def __init__(
        self,
        config: Config,
        vector_store: VectorStore,
        embedder: Embedder,
        chunker: Chunker,
    ):
        self.config = config
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = chunker

        idx_cfg = config.indexing if config else None

        # max_chars_per_file: Safety limit -- truncate files larger than this.
        # 2 million chars ~ a 1,000-page document.
        self.max_chars_per_file = getattr(idx_cfg, "max_chars_per_file", 2_000_000)

        # block_chars: How much text to process at a time before writing to
        # disk. 200K chars ~ 100 pages. Keeps RAM usage predictable.
        self.block_chars = getattr(idx_cfg, "block_chars", 200_000)

        # File extensions we know how to parse.
        # Primary source: config. Fallback: parser registry (single source of truth).
        from src.parsers.registry import REGISTRY
        cfg_exts = getattr(idx_cfg, "supported_extensions", None)
        self._supported_extensions = set(cfg_exts) if cfg_exts else set(REGISTRY.supported_extensions())

        # Directories to skip (virtual environments, git history, etc.)
        self._excluded_dirs = set(
            getattr(idx_cfg, "excluded_dirs", [
                ".venv", "venv", "__pycache__", ".git", ".idea", ".vscode",
                "node_modules", "_quarantine",
            ])
        )

        # File validation (extracted from Indexer to keep class under 500 lines)
        self._file_validator = FileValidator(excluded_dirs=self._excluded_dirs)
        # Fallback text read should only run for text-like formats.
        self._fallback_text_extensions = {
            ".txt", ".md", ".csv", ".json", ".xml", ".log",
            ".yaml", ".yml", ".ini", ".cfg", ".conf", ".properties",
            ".reg", ".html", ".htm", ".rtf",
        }
        # OCR diversion: copy OCR-dependent no-text files into a triage folder.
        paths_cfg = getattr(config, "paths", None)
        self._ocr_diversion_folder = Path(
            getattr(paths_cfg, "ocr_diversion_folder", "") or ""
        )
        self._ocr_diversion_enabled = str(
            os.getenv("HYBRIDRAG_OCR_DIVERT_ENABLED", "1")
        ).strip().lower() in ("1", "true", "yes", "on")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(self, file_path: str) -> Dict[str, Any]:
        """
        Index a single file. Convenience method for debugging and testing.

        Returns dict with: indexed (bool), chunks_added (int),
        skipped_reason (str or None), elapsed_seconds (float).
        """
        start_time = time.time()
        fp = Path(file_path)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError("File not found: {}".format(file_path))

        chunks_added, reason, _ = self._process_single_file(fp)
        elapsed = time.time() - start_time
        if reason:
            return {"indexed": False, "chunks_added": 0,
                    "skipped_reason": reason, "elapsed_seconds": elapsed}
        logger.info("[OK] Indexed %s: %d chunks in %.1fs",
                    fp.name, chunks_added, elapsed)
        return {"indexed": True, "chunks_added": chunks_added,
                "skipped_reason": None, "elapsed_seconds": elapsed}

    def index_folder(
        self,
        folder_path: str,
        progress_callback: Optional[IndexingProgressCallback] = None,
        recursive: bool = True,
        stop_flag: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Index all supported files in a folder.

        Parameters
        ----------
        stop_flag : threading.Event or None
            If set, indexing aborts cleanly by raising IndexCancelled.
            Checked during discovery (every 500 files) and before each
            file is processed.

        Returns dict with: total_files_scanned, total_files_indexed,
        total_files_skipped, total_chunks_added, elapsed_seconds,
        preflight_blocked (list of files blocked by pre-flight checks).
        """
        if progress_callback is None:
            progress_callback = IndexingProgressCallback()

        start_time = time.time()
        total_chunks = 0
        total_files_indexed = 0
        total_files_skipped = 0
        total_files_reindexed = 0
        preflight_blocked = []  # NEW: tracks files blocked by pre-flight
        skip_reason_counts: Dict[str, int] = {}
        skip_extension_counts: Dict[str, int] = {}

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Source folder not found: {folder_path}")
        if self._ocr_diversion_enabled and not self._ocr_diversion_folder:
            self._ocr_diversion_folder = folder / "_ocr_diversions"
        if self._ocr_diversion_enabled:
            try:
                self._ocr_diversion_folder.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning("[WARN] Could not create OCR diversion folder: %s", e)

        # --- Step 1: Discover all supported files ---
        # Lazy iteration avoids materializing the full rglob list,
        # saving memory on large directories and providing live
        # feedback via the discovery callback.
        #
        # The rglob generator can raise PermissionError or OSError
        # mid-iteration (e.g., on network paths with restricted
        # subdirectories). We catch these so a single inaccessible
        # folder does not abort the entire discovery.
        supported_files: List[Path] = []
        _discovery_count = 0
        _glob_iter = folder.rglob("*") if recursive else folder.glob("*")
        while True:
            # Check cancellation every discovery iteration for responsive stop.
            self._raise_if_cancelled(stop_flag, "during discovery")
            try:
                f = next(_glob_iter)
            except StopIteration:
                break
            except (PermissionError, OSError) as e:
                logger.warning("[WARN] Discovery skipped inaccessible path: %s", e)
                continue
            _discovery_count += 1
            if _discovery_count % 500 == 0:
                progress_callback.on_discovery_progress(_discovery_count)
            try:
                if not f.is_file():
                    continue
            except (PermissionError, OSError):
                continue
            if self._is_excluded(f):
                continue
            if f.suffix.lower() not in self._supported_extensions:
                continue
            supported_files.append(f)

        # Final discovery callback with exact count
        progress_callback.on_discovery_progress(_discovery_count)
        logger.info("Found %d supported files in %s", len(supported_files), folder)

        # --- Step 2: Process each file ---
        for idx, file_path in enumerate(supported_files, start=1):
            # Cancel check at the top of the loop -- before any work.
            # IndexCancelled inherits BaseException so it propagates
            # through the "except Exception" handler below.
            if stop_flag is not None and stop_flag.is_set():
                raise IndexCancelled("Cancelled before file {}".format(idx))

            try:
                progress_callback.on_file_start(
                    str(file_path), idx, len(supported_files)
                )
                chunks_added, skip_reason, was_reindex = (
                    self._process_single_file(file_path, stop_flag=stop_flag)
                )
                if skip_reason:
                    self._maybe_divert_ocr_dependent_file(file_path, skip_reason, folder)
                    total_files_skipped += 1
                    skip_reason_counts[skip_reason] = (
                        skip_reason_counts.get(skip_reason, 0) + 1
                    )
                    ext = file_path.suffix.lower() or "<no_ext>"
                    skip_extension_counts[ext] = (
                        skip_extension_counts.get(ext, 0) + 1
                    )
                    if skip_reason.startswith("preflight:"):
                        preflight_blocked.append(
                            (str(file_path), skip_reason[11:])
                        )
                    progress_callback.on_file_skipped(
                        str(file_path), skip_reason
                    )
                else:
                    total_files_indexed += 1
                    total_chunks += chunks_added
                    if was_reindex:
                        total_files_reindexed += 1
                    progress_callback.on_file_complete(
                        str(file_path), chunks_added
                    )
            except Exception as e:
                error_msg = "{}: {}".format(type(e).__name__, e)
                logger.error("[FAIL] %s: %s", file_path.name, error_msg)
                progress_callback.on_error(str(file_path), error_msg)

        # --- Done ---
        elapsed = time.time() - start_time
        progress_callback.on_indexing_complete(total_chunks, elapsed)

        result = {
            "total_files_scanned": len(supported_files),
            "total_files_indexed": total_files_indexed,
            "total_files_skipped": total_files_skipped,
            "total_files_reindexed": total_files_reindexed,
            "total_chunks_added": total_chunks,
            "preflight_blocked": preflight_blocked,
            "skip_reason_counts": dict(
                sorted(skip_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "skip_extension_counts": dict(
                sorted(skip_extension_counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "elapsed_seconds": elapsed,
        }

        logger.info("Indexing complete:")
        logger.info("  Files scanned:    %d", result['total_files_scanned'])
        logger.info("  Files indexed:    %d", result['total_files_indexed'])
        logger.info("  Files re-indexed: %d", result['total_files_reindexed'])
        logger.info("  Files skipped:    %d", result['total_files_skipped'])
        logger.info("  Chunks added:     %d", result['total_chunks_added'])
        logger.info("  Time: %.1fs", elapsed)
        if result["skip_reason_counts"]:
            logger.info("  Top skip reasons:")
            for reason, count in list(result["skip_reason_counts"].items())[:10]:
                logger.info("    - %s: %d", reason, count)
        if result["skip_extension_counts"]:
            logger.info("  Top skipped extensions:")
            for ext, count in list(result["skip_extension_counts"].items())[:10]:
                logger.info("    - %s: %d", ext, count)

        # --- Pre-flight report (if any files were blocked) ---
        if preflight_blocked:
            logger.warning("[WARN] PRE-FLIGHT BLOCKED: %d files", len(preflight_blocked))
            logger.warning("  These files were caught before parsing and did NOT enter the vector store:")
            for blocked_path, blocked_reason in preflight_blocked:
                blocked_name = Path(blocked_path).name
                logger.warning("    - %s: %s", blocked_name, blocked_reason)
            logger.info("  To review and clean up, run:  rag-scan --deep")
            logger.info("  To quarantine automatically:  rag-scan --auto-quarantine")

        return result

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _preflight_check(self, file_path: Path) -> Optional[str]:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.preflight_check(file_path)

    def _process_single_file(
        self,
        file_path: Path,
        stop_flag: Optional[Any] = None,
    ) -> Tuple[int, Optional[str], bool]:
        """
        Process one file: preflight -> hash check -> parse -> validate ->
        chunk -> embed -> store.

        Returns (chunks_added, skip_reason, was_reindex).
        skip_reason is None on success. was_reindex is True when old
        chunks were deleted before re-indexing a modified file.
        """
        was_reindex = False
        self._raise_if_cancelled(stop_flag, f"before preflight: {file_path.name}")

        preflight_reason = self._preflight_check(file_path)
        if preflight_reason:
            logger.info("BLOCKED: %s -- %s", file_path.name, preflight_reason)
            return 0, "preflight: {}".format(preflight_reason), False

        self._raise_if_cancelled(stop_flag, f"before hash check: {file_path.name}")
        current_hash = self._compute_file_hash(file_path)
        stored_hash = self.vector_store.get_file_hash(str(file_path))
        if stored_hash:
            if stored_hash == current_hash:
                return 0, "unchanged (hash match)", False
            deleted = self.vector_store.delete_chunks_by_source(
                str(file_path)
            )
            logger.info(
                "RE-INDEX: %s changed (deleted %d old chunks)",
                file_path.name, deleted,
            )
            was_reindex = True

        self._raise_if_cancelled(stop_flag, f"before parse: {file_path.name}")
        text, parse_details = self._process_file_with_retry(
            file_path, stop_flag=stop_flag
        )
        if not text or not text.strip():
            return 0, self._build_no_text_reason(file_path, parse_details), False

        if not self._validate_text(text):
            logger.warning(
                "[WARN] %s -- text looks like binary garbage, skipping",
                file_path.name,
            )
            return 0, "binary garbage detected", False

        if len(text) > self.max_chars_per_file:
            logger.warning(
                "[WARN] Clamping %s from %s to %s chars",
                file_path.name,
                "{:,}".format(len(text)),
                "{:,}".format(self.max_chars_per_file),
            )
            text = text[: self.max_chars_per_file]

        try:
            file_mtime_ns = file_path.stat().st_mtime_ns
        except Exception:
            file_mtime_ns = 0

        chunks_added = 0
        char_offset = 0
        for block in self._iter_text_blocks(text):
            self._raise_if_cancelled(stop_flag, f"during chunk loop: {file_path.name}")
            if not block.strip():
                char_offset += len(block)
                continue
            chunks = self.chunker.chunk_text(block)
            if not chunks:
                char_offset += len(block)
                continue
            self._raise_if_cancelled(stop_flag, f"before embed: {file_path.name}")
            embeddings = self.embedder.embed_batch(chunks)
            metadata_list = []
            chunk_ids = []
            for i, chunk_text in enumerate(chunks):
                chunk_size = self.config.chunking.chunk_size
                chunk_overlap = self.config.chunking.overlap
                chunk_start = char_offset + (
                    i * (chunk_size - chunk_overlap)
                )
                chunk_end = chunk_start + len(chunk_text)
                cid = make_chunk_id(
                    file_path=str(file_path),
                    file_mtime_ns=file_mtime_ns,
                    chunk_start=chunk_start,
                    chunk_end=chunk_end,
                    chunk_text=chunk_text,
                )
                chunk_ids.append(cid)
                metadata_list.append(
                    ChunkMetadata(
                        source_path=str(file_path),
                        chunk_index=chunks_added + i,
                        text_length=len(chunk_text),
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
            self.vector_store.add_embeddings(
                embeddings, metadata_list,
                texts=chunks, chunk_ids=chunk_ids,
                file_hash=current_hash,
            )
            chunks_added += len(chunks)
            char_offset += len(block)

        if chunks_added == 0:
            return 0, "no chunks produced", was_reindex

        gc.collect()
        return chunks_added, None, was_reindex

    def _process_file_with_retry(
        self,
        file_path: Path,
        max_retries: int = 3,
        stop_flag: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Retry file processing up to max_retries times with backoff."""
        last_error = None
        for attempt in range(1, max_retries + 1):
            self._raise_if_cancelled(stop_flag, f"before parse retry {attempt}: {file_path.name}")
            try:
                return self._parse_file(file_path)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "[WARN] Retry %d/%d for %s in %ds: %s",
                        attempt, max_retries, file_path.name, wait, e,
                    )
                    self._sleep_with_cancel(wait, stop_flag, file_path.name)
        raise last_error

    def _raise_if_cancelled(self, stop_flag: Optional[Any], where: str = "") -> None:
        """Raise IndexCancelled when cooperative stop was requested."""
        if stop_flag is not None and stop_flag.is_set():
            where_suffix = f" ({where})" if where else ""
            raise IndexCancelled(f"Cancelled{where_suffix}")

    def _sleep_with_cancel(
        self,
        seconds: float,
        stop_flag: Optional[Any],
        file_name: str = "",
    ) -> None:
        """Sleep in short slices so stop requests interrupt retry backoff."""
        if seconds <= 0:
            return
        end = time.monotonic() + float(seconds)
        while True:
            self._raise_if_cancelled(stop_flag, f"during retry backoff: {file_name}")
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))

    # =================================================================
    # BUG-001 FIX: _compute_file_hash unchanged but now USED properly
    # =================================================================
    def _compute_file_hash(self, file_path):
        """
        Compute a fast fingerprint of a file: "filesize:mtime_nanoseconds".

        Example: "284519:132720938471230000"

        WHY size + mtime instead of reading file content?
          Reading file content (e.g., SHA-256) would require reading every
          byte of every file on every indexing run -- that's 100GB+ of I/O
          on an enterprise network drive. Size + mtime is instant (just a
          stat() call) and catches the vast majority of real modifications.

        WHEN THIS FAILS:
          If someone modifies a file but the OS doesn't update mtime (rare),
          or if a file is replaced with a same-size different file at the
          exact same nanosecond (essentially impossible). For higher
          assurance, we could add SHA-256 as a future config option.
        """
        stat = file_path.stat()
        fast_key = f"{stat.st_size}:{stat.st_mtime_ns}"
        return fast_key

    def _parse_file(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from a file using the parser registry.

        Falls back to reading as plain text if no specialized parser
        is available. Returns (text, details) on all paths.
        """
        ext = file_path.suffix.lower()
        details: Dict[str, Any] = {
            "file": str(file_path),
            "extension": ext,
            "parser": "unknown",
            "mode": "registry",
        }
        try:
            from ..parsers.text_parser import TextParser
            text, parsed = TextParser().parse_with_details(str(file_path))
            if isinstance(parsed, dict):
                details.update(parsed)
            if text and text.strip():
                return text, details
        except ImportError:
            details["error"] = "IMPORT_ERROR: parser stack unavailable"
        except Exception as e:
            logger.warning("[WARN] Parser error on %s: %s", file_path.name, e)
            details["error"] = f"RUNTIME_ERROR: {type(e).__name__}: {e}"

        # Fallback: only for text-like extensions.
        if ext not in self._fallback_text_extensions:
            details.setdefault("likely_reason", "PARSER_RETURNED_NO_TEXT")
            details["mode"] = "no_fallback_for_binary_like_extension"
            return "", details

        details["mode"] = "fallback_plain_text"
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return text, details
        except Exception:
            try:
                details["fallback_encoding"] = "latin-1"
                text = file_path.read_text(encoding="latin-1", errors="replace")
                return text, details
            except Exception:
                details["fallback_encoding"] = "none"
                details.setdefault("error", "FALLBACK_READ_FAILED")
                return "", details

    def _build_no_text_reason(self, file_path: Path, details: Dict[str, Any]) -> str:
        """
        Build a compact, operator-friendly skip reason for empty extraction.
        """
        parser_name = details.get("parser") or "unknown_parser"
        likely = details.get("likely_reason")
        error = details.get("error")
        extension = file_path.suffix.lower() or "<no_ext>"

        if likely:
            return f"no text extracted ({extension}, {parser_name}, {likely})"
        if error:
            # Keep first token to avoid giant log lines.
            err_token = str(error).split(":")[0][:64]
            return f"no text extracted ({extension}, {parser_name}, {err_token})"
        return f"no text extracted ({extension}, {parser_name})"

    def _is_ocr_dependent_skip(self, file_path: Path, skip_reason: str) -> bool:
        """Heuristic: identify skips likely requiring OCR/manual triage."""
        if not skip_reason.startswith("no text extracted"):
            return False
        ext = file_path.suffix.lower()
        if ext in {
            ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
            ".gif", ".webp", ".wmf", ".emf", ".psd",
        }:
            return True
        if ext == ".pdf":
            s = skip_reason.upper()
            return (
                "LIKELY_SCANNED" in s
                or "OCR_" in s
                or "IMAGE_ONLY" in s
                or "UNUSUAL_ENCODING" in s
            )
        return False

    def _maybe_divert_ocr_dependent_file(
        self,
        file_path: Path,
        skip_reason: str,
        source_root: Path,
    ) -> None:
        """
        Copy (never move) OCR-dependent skipped files to diversion folder,
        preserving relative path and writing a .reason sidecar.
        """
        if not self._ocr_diversion_enabled:
            return
        if not self._ocr_diversion_folder:
            return
        if not self._is_ocr_dependent_skip(file_path, skip_reason):
            return
        try:
            rel = file_path.relative_to(source_root)
        except Exception:
            rel = Path(file_path.name)
        dest = self._ocr_diversion_folder / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # COPY ONLY: original source data is never moved or deleted.
            if not dest.exists():
                shutil.copy2(str(file_path), str(dest))
            reason_path = dest.with_name(dest.name + ".reason.txt")
            if not reason_path.exists():
                reason_path.write_text(
                    f"source={file_path}\nreason={skip_reason}\n",
                    encoding="utf-8",
                )
        except Exception as e:
            logger.warning(
                "[WARN] OCR diversion copy failed for %s: %s",
                file_path.name,
                e,
            )

    def _validate_text(self, text: str) -> bool:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.validate_text(text)

    def _is_excluded(self, file_path: Path) -> bool:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.is_excluded(file_path)

    def _iter_text_blocks(self, text: str):
        """
        Yield text in blocks of self.block_chars.

        Breaks on newlines when possible to avoid splitting mid-sentence.
        200K chars ~ 100 pages. Keeps RAM usage predictable.
        """
        n = len(text)
        start = 0
        while start < n:
            end = min(start + self.block_chars, n)
            if end < n:
                nl = text.rfind("\n", start, end)
                if nl != -1 and nl > start + 10_000:
                    end = nl
            yield text[start:end]
            start = end

    # =================================================================
    # BUG-003 FIX: close() to release the embedding model from RAM
    # =================================================================
    def close(self) -> None:
        """
        Release resources held by the indexer.

        BUG-003 FIX: The embedding model (SentenceTransformer) stays in
        RAM (~100MB) until explicitly deleted. Over repeated indexing
        runs without restarting Python, this leaks memory. The embedder
        and vector_store now have close() methods that this calls.

        Safe to call multiple times. Call in a "finally" block.
        """
        if hasattr(self, 'embedder') and self.embedder is not None:
            self.embedder.close()
        if hasattr(self, 'vector_store') and self.vector_store is not None:
            self.vector_store.close()
