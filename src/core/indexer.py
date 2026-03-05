# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the indexer part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Indexer (src/core/indexer.py)
# ============================================================================
#
# Orchestrates: scan folder -> preflight -> parse -> chunk -> embed -> store
#
# Key design: block-based processing (200K chars at a time for stable RAM),
# deterministic chunk IDs (crash-safe resume), hash-based skip (size+mtime),
# never crash on single file failure, pre-flight integrity checks.
#
# After each run, writes a consolidated report to logs/index_report_*.txt
# with skip reasons, OCR stats, errors, and tuning hints.
#
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import logging
import os
import time
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
from .index_report import FileRecord, populate_from_parse_details, write_report
from .ocr_cleanup import clean_ocr_text, score_text_quality
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
        """Plain-English: Responds to the file start event and updates state or UI accordingly."""
        pass

    def on_file_complete(self, file_path: str, chunks_created: int) -> None:
        """Plain-English: Responds to the file complete event and updates state or UI accordingly."""
        pass

    def on_file_skipped(self, file_path: str, reason: str) -> None:
        """Plain-English: Responds to the file skipped event and updates state or UI accordingly."""
        pass

    def on_indexing_complete(self, total_chunks: int, elapsed_seconds: float) -> None:
        """Plain-English: Responds to the indexing complete event and updates state or UI accordingly."""
        pass

    def on_error(self, file_path: str, error: str) -> None:
        """Plain-English: Responds to the error event and updates state or UI accordingly."""
        pass

    def on_discovery_progress(self, files_found: int) -> None:
        """Plain-English: Responds to the discovery progress event and updates state or UI accordingly."""
        pass


# -------------------------------------------------------------------
# Indexer
# -------------------------------------------------------------------

class Indexer:
    """Scans a folder, parses files, chunks text, embeds, and stores."""

    def __init__(
        self,
        config: Config,
        vector_store: VectorStore,
        embedder: Embedder,
        chunker: Chunker,
    ):
        """Plain-English: Sets up the Indexer object and prepares state used by its methods."""
        self.config = config
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = chunker

        idx_cfg = config.indexing if config else None
        perf_cfg = getattr(config, "performance", None) if config else None

        self.max_chars_per_file = getattr(idx_cfg, "max_chars_per_file", 2_000_000)
        self.block_chars = getattr(idx_cfg, "block_chars", 200_000)
        self.max_concurrent_files = int(getattr(perf_cfg, "max_concurrent_files", 1))
        self.gc_between_files = bool(getattr(perf_cfg, "gc_between_files", True))
        self.gc_between_blocks = bool(getattr(perf_cfg, "gc_between_blocks", True))

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(self, file_path: str) -> Dict[str, Any]:
        """Index a single file. Returns dict with indexed, chunks_added, etc."""
        start_time = time.time()
        fp = Path(file_path)
        if not fp.exists() or not fp.is_file():
            raise FileNotFoundError("File not found: {}".format(file_path))

        chunks_added, reason, _, _details = self._process_single_file(fp)
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
        """Index all supported files in a folder. Writes report to logs/ when done."""
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
        # --- Step 1: Discover all supported files ---
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
        if self.max_concurrent_files > 1:
            logger.info(
                "Indexer profile requests max_concurrent_files=%d (single-worker mode active).",
                self.max_concurrent_files,
            )

        # --- Step 2: Process each file ---
        file_records: List[FileRecord] = []
        for idx, file_path in enumerate(supported_files, start=1):
            if stop_flag is not None and stop_flag.is_set():
                raise IndexCancelled("Cancelled before file {}".format(idx))

            ext = file_path.suffix.lower() or "<no_ext>"
            record = FileRecord(str(file_path), ext)
            file_start = time.time()

            try:
                progress_callback.on_file_start(
                    str(file_path), idx, len(supported_files)
                )
                if stop_flag is None:
                    chunks_added, skip_reason, was_reindex, parse_details = (
                        self._process_single_file(file_path)
                    )
                else:
                    chunks_added, skip_reason, was_reindex, parse_details = (
                        self._process_single_file(file_path, stop_flag=stop_flag)
                    )

                record.parse_time_ms = (time.time() - file_start) * 1000
                if parse_details:
                    text_len = parse_details.get(
                        "normal_extract", {}
                    ).get("chars", 0)
                    populate_from_parse_details(record, parse_details, text_len)

                if skip_reason:
                    total_files_skipped += 1
                    record.status = "skipped"
                    record.skip_reason = skip_reason
                    skip_reason_counts[skip_reason] = (
                        skip_reason_counts.get(skip_reason, 0) + 1
                    )
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
                    record.status = "indexed"
                    record.chunks_added = chunks_added
                    if was_reindex:
                        total_files_reindexed += 1
                    progress_callback.on_file_complete(
                        str(file_path), chunks_added
                    )
            except Exception as e:
                error_msg = "{}: {}".format(type(e).__name__, e)
                record.status = "error"
                record.error_msg = error_msg
                record.parse_time_ms = (time.time() - file_start) * 1000
                logger.error("[FAIL] %s: %s", file_path.name, error_msg)
                progress_callback.on_error(str(file_path), error_msg)

            file_records.append(record)
            if self.gc_between_files:
                gc.collect()

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
            "max_concurrent_files": self.max_concurrent_files,
            "gc_between_files": self.gc_between_files,
            "gc_between_blocks": self.gc_between_blocks,
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

        # --- Write consolidated index report ---
        try:
            report_path = write_report(
                result, file_records, str(folder), logs_dir="logs"
            )
            logger.info("[OK] Index report: %s", report_path)
        except Exception as e:
            logger.warning("[WARN] Could not write index report: %s", e)

        return result

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _preflight_check(self, file_path: Path) -> Optional[str]:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.preflight_check(file_path)

    def _process_single_file(
        self, file_path: Path, stop_flag: Optional[Any] = None,
    ) -> Tuple[int, Optional[str], bool, Dict[str, Any]]:
        """Returns (chunks_added, skip_reason, was_reindex, parse_details)."""
        was_reindex = False
        self._raise_if_cancelled(stop_flag, f"before preflight: {file_path.name}")

        preflight_reason = self._preflight_check(file_path)
        if preflight_reason:
            logger.info("BLOCKED: %s -- %s", file_path.name, preflight_reason)
            return 0, "preflight: {}".format(preflight_reason), False, {}

        self._raise_if_cancelled(stop_flag, f"before hash check: {file_path.name}")
        current_hash = self._compute_file_hash(file_path)
        stored_hash = self.vector_store.get_file_hash(str(file_path))
        if stored_hash:
            if stored_hash == current_hash:
                return 0, "unchanged (hash match)", False, {}
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
            return (0, self._build_no_text_reason(file_path, parse_details),
                    False, parse_details)

        text = clean_ocr_text(text)
        parse_details["quality_score"] = score_text_quality(text)
        parse_details["chars_after_cleanup"] = len(text)

        if not self._validate_text(text):
            logger.warning(
                "[WARN] %s -- text looks like binary garbage, skipping",
                file_path.name,
            )
            return 0, "binary garbage detected", False, parse_details

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
            chunk_offsets = self._locate_chunk_offsets(block, chunks)
            for i, chunk_text in enumerate(chunks):
                chunk_start = char_offset + chunk_offsets[i]
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
            if self.gc_between_blocks:
                gc.collect()

        if chunks_added == 0:
            return 0, "no chunks produced", was_reindex, parse_details

        if self.gc_between_files:
            gc.collect()
        return chunks_added, None, was_reindex, parse_details

    def _locate_chunk_offsets(self, block: str, chunks: List[str]) -> List[int]:
        """
        Locate chunk start offsets within the block text.

        Smart chunking does not guarantee fixed stride spacing, so we
        compute offsets from actual text positions to keep chunk IDs
        deterministic across re-index runs.
        """
        offsets: List[int] = []
        search_from = 0
        for i, chunk_text in enumerate(chunks):
            idx = block.find(chunk_text, search_from)
            if idx < 0:
                idx = block.find(chunk_text)
            if idx < 0:
                # Fallback keeps deterministic monotonic offsets even if
                # chunk text was normalized by parser/chunker internals.
                prev = offsets[-1] if offsets else 0
                idx = min(len(block), prev + max(1, len(chunk_text) // 2))
            offsets.append(idx)
            search_from = min(len(block), idx + max(1, len(chunk_text)))
        return offsets

    def _process_file_with_retry(
        self, file_path: Path, max_retries: int = 3,
        stop_flag: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Retry file parsing up to max_retries times with exponential backoff."""
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
        self, seconds: float, stop_flag: Optional[Any],
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

    def _compute_file_hash(self, file_path):
        """Fast fingerprint: 'filesize:mtime_ns'. Instant stat() call."""
        stat = file_path.stat()
        return f"{stat.st_size}:{stat.st_mtime_ns}"

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

    def _validate_text(self, text: str) -> bool:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.validate_text(text)

    def _is_excluded(self, file_path: Path) -> bool:
        """Delegate to FileValidator. See file_validator.py for details."""
        return self._file_validator.is_excluded(file_path)

    def _iter_text_blocks(self, text: str):
        """Yield text in blocks of self.block_chars, breaking on newlines."""
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

    def close(self) -> None:
        """Release resources (embedder + vector_store). Safe to call multiple times."""
        if hasattr(self, 'embedder') and self.embedder is not None:
            self.embedder.close()
        if hasattr(self, 'vector_store') and self.vector_store is not None:
            self.vector_store.close()
