# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the archive parser part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Archive Parser (src/parsers/archive_parser.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Extracts text from files inside ZIP archives (.zip, .7z, .tar.gz, etc.).
#   Opens the archive, iterates over each file inside, routes each to the
#   correct parser via the registry, and combines all extracted text.
#
# HOW IT WORKS (plain English):
#   1. Open the archive (ZIP, TAR, or GZ)
#   2. Extract each file to a temp directory one at a time
#   3. Look up the file extension in the parser registry
#   4. Parse the extracted file with the appropriate parser
#   5. Collect all text with archive member markers
#   6. Clean up the temp directory
#
# SAFETY FEATURES:
#   - Max extraction size: won't extract files > 500 MB (zip bomb guard)
#   - Max member count: won't process > 5000 files per archive
#   - Temp dir cleanup: always deletes extracted files when done
#   - Nested archives: skips inner .zip files (no recursive extraction)
#   - Path traversal guard: rejects entries with ".." in the path
#
# SUPPORTED FORMATS:
#   .zip -- Python stdlib zipfile (zero deps)
#   .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz -- Python stdlib tarfile
#   .gz (single file) -- Python stdlib gzip
#
# DEPENDENCIES: None (all stdlib)
# INTERNET ACCESS: None
# ============================================================================

from __future__ import annotations

import gzip
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Safety limits
_MAX_EXTRACT_BYTES = 500 * 1024 * 1024  # 500 MB per file
_MAX_MEMBERS = 5000                      # max files to process per archive
_SKIP_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz"}


class ArchiveParser:
    """
    Extracts text from files inside ZIP and TAR archives.

    Each file inside the archive is routed to the correct parser
    based on its extension. Text from all parsable files is combined
    with markers showing which archive member it came from.
    """

    def parse(self, file_path: str) -> str:
        text, _ = self.parse_with_details(file_path)
        return text

    def parse_with_details(self, file_path: str) -> Tuple[str, Dict[str, Any]]:
        path = Path(file_path)
        details: Dict[str, Any] = {
            "file": str(path),
            "parser": "ArchiveParser",
            "archive_type": None,
            "members_found": 0,
            "members_parsed": 0,
            "members_skipped": 0,
            "total_chars": 0,
        }

        ext = path.suffix.lower()
        # .tar.gz, .tar.bz2, .tar.xz have double suffixes
        if path.name.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            ext = ".tar" + ext  # e.g. ".tar.gz"

        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="hybridrag_archive_")

            if ext == ".zip":
                details["archive_type"] = "zip"
                members = self._extract_zip(file_path, tmp_dir, details)
            elif ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
                details["archive_type"] = "tar"
                members = self._extract_tar(file_path, tmp_dir, details)
            elif ext == ".gz":
                details["archive_type"] = "gzip_single"
                members = self._extract_gz_single(file_path, tmp_dir, details)
            else:
                details["likely_reason"] = "UNSUPPORTED_ARCHIVE_FORMAT"
                return "", details

            # Parse each extracted file via the registry
            parts = self._parse_members(members, details)
            text = "\n\n".join(parts).strip()
            details["total_chars"] = len(text)
            return text, details

        except Exception as e:
            details["error"] = f"ARCHIVE_ERROR: {type(e).__name__}: {e}"
            return "", details
        finally:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _extract_zip(
        self, archive_path: str, tmp_dir: str, details: Dict
    ) -> List[Tuple[str, str]]:
        """Extract ZIP contents. Returns list of (member_name, extracted_path)."""
        members = []
        with zipfile.ZipFile(archive_path, "r") as zf:
            entries = zf.infolist()
            details["members_found"] = len(entries)

            for entry in entries[:_MAX_MEMBERS]:
                # Skip directories
                if entry.is_dir():
                    continue
                # Path traversal guard
                if ".." in entry.filename:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue
                # Size guard (zip bomb protection)
                if entry.file_size > _MAX_EXTRACT_BYTES:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue
                # Skip nested archives
                member_ext = Path(entry.filename).suffix.lower()
                if member_ext in _SKIP_EXTENSIONS:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue

                # Extract to temp dir (flat -- avoids deep nested paths)
                safe_name = Path(entry.filename).name
                if not safe_name:
                    continue
                dest = os.path.join(tmp_dir, safe_name)
                # Handle duplicate names
                counter = 1
                base, suffix = os.path.splitext(safe_name)
                while os.path.exists(dest):
                    dest = os.path.join(tmp_dir, f"{base}_{counter}{suffix}")
                    counter += 1

                try:
                    with zf.open(entry) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    members.append((entry.filename, dest))
                except Exception:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1

        return members

    def _extract_tar(
        self, archive_path: str, tmp_dir: str, details: Dict
    ) -> List[Tuple[str, str]]:
        """Extract TAR/TGZ/TBZ2/TXZ contents."""
        members = []
        with tarfile.open(archive_path, "r:*") as tf:
            entries = tf.getmembers()
            details["members_found"] = len(entries)

            for entry in entries[:_MAX_MEMBERS]:
                if not entry.isfile():
                    continue
                if ".." in entry.name:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue
                if entry.size > _MAX_EXTRACT_BYTES:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue
                member_ext = Path(entry.name).suffix.lower()
                if member_ext in _SKIP_EXTENSIONS:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
                    continue

                safe_name = Path(entry.name).name
                if not safe_name:
                    continue
                dest = os.path.join(tmp_dir, safe_name)
                counter = 1
                base, suffix = os.path.splitext(safe_name)
                while os.path.exists(dest):
                    dest = os.path.join(tmp_dir, f"{base}_{counter}{suffix}")
                    counter += 1

                try:
                    src = tf.extractfile(entry)
                    if src is None:
                        continue
                    with open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    members.append((entry.name, dest))
                except Exception:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1

        return members

    def _extract_gz_single(
        self, archive_path: str, tmp_dir: str, details: Dict
    ) -> List[Tuple[str, str]]:
        """Extract a single .gz file (not tar.gz)."""
        details["members_found"] = 1
        # Strip .gz to get the inner filename
        inner_name = Path(archive_path).stem
        if not inner_name:
            inner_name = "extracted_file"
        dest = os.path.join(tmp_dir, inner_name)

        try:
            with gzip.open(archive_path, "rb") as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return [(inner_name, dest)]
        except Exception:
            details["members_skipped"] = 1
            return []

    def _parse_members(
        self, members: List[Tuple[str, str]], details: Dict
    ) -> List[str]:
        """Route each extracted file to its parser and collect text."""
        from .registry import REGISTRY

        parts = []
        for member_name, extracted_path in members:
            ext = Path(extracted_path).suffix.lower()
            info = REGISTRY.get(ext)
            if info is None:
                details["members_skipped"] = details.get("members_skipped", 0) + 1
                continue

            try:
                parser = info.parser_cls()
                if hasattr(parser, "parse_with_details"):
                    text, _ = parser.parse_with_details(extracted_path)
                else:
                    text = parser.parse(extracted_path)

                text = (text or "").strip()
                if text:
                    parts.append(f"[ARCHIVE_MEMBER={member_name}]\n{text}")
                    details["members_parsed"] = details.get("members_parsed", 0) + 1
                else:
                    details["members_skipped"] = details.get("members_skipped", 0) + 1
            except Exception:
                details["members_skipped"] = details.get("members_skipped", 0) + 1

        return parts
