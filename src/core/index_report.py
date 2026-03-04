# ============================================================================
# HybridRAG -- Indexing Report Writer (src/core/index_report.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   After an indexing run finishes, this module writes a single consolidated
#   report file to logs/. The report is a human-readable data sheet with
#   every skip, error, OCR attempt, and timing detail in one place.
#
#   Open this file the morning after an overnight index run to see exactly
#   what happened, what failed, what needs attention, and what to tweak.
#
# REPORT SECTIONS:
#   1. Summary -- total files, chunks, timing
#   2. Skip reasons -- sorted by count, shows why files were skipped
#   3. Extension breakdown -- which file types got skipped most
#   4. OCR activity -- triggered/succeeded/failed/chars recovered
#   5. Preflight blocks -- files blocked before parsing (corrupt, zero-byte)
#   6. Files with no text -- potential OCR or parser issues
#   7. Errors -- files that threw exceptions during parsing
#   8. Per-file details (JSON) -- machine-readable section at the bottom
#
# OUTPUT:
#   logs/index_report_YYYY-MM-DD_HHMMSS.txt
#   logs/index_report_latest.json  (symlink/copy to latest JSON)
#
# INTERNET ACCESS: NONE
# DEPENDENCIES: NONE (all stdlib)
# ============================================================================

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class FileRecord:
    """One file's processing result during indexing."""

    __slots__ = (
        "path", "extension", "status", "skip_reason", "chunks_added",
        "chars_extracted", "parser_used", "parse_time_ms",
        "ocr_triggered", "ocr_used", "ocr_status", "ocr_chars",
        "ocr_method", "error_msg", "parse_details", "quality_score",
    )

    def __init__(self, path: str, extension: str) -> None:
        self.path = path
        self.extension = extension
        self.status = "pending"          # indexed | skipped | error
        self.skip_reason = ""
        self.chunks_added = 0
        self.chars_extracted = 0
        self.parser_used = ""
        self.parse_time_ms = 0.0
        self.ocr_triggered = False
        self.ocr_used = False
        self.ocr_status = ""
        self.ocr_chars = 0
        self.ocr_method = ""             # tesseract | ocrmypdf
        self.error_msg = ""
        self.parse_details: Dict[str, Any] = {}
        self.quality_score: int = -1     # 0-100, -1 = not scored

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "path": self.path,
            "extension": self.extension,
            "status": self.status,
            "chunks_added": self.chunks_added,
            "chars_extracted": self.chars_extracted,
            "parser": self.parser_used,
            "parse_time_ms": round(self.parse_time_ms, 1),
            "quality_score": self.quality_score,
        }
        if self.skip_reason:
            d["skip_reason"] = self.skip_reason
        if self.error_msg:
            d["error"] = self.error_msg
        if self.ocr_triggered:
            d["ocr"] = {
                "triggered": self.ocr_triggered,
                "used": self.ocr_used,
                "status": self.ocr_status,
                "chars": self.ocr_chars,
                "method": self.ocr_method,
            }
        return d


def populate_from_parse_details(
    record: FileRecord,
    parse_details: Dict[str, Any],
    text_len: int,
) -> None:
    """Extract OCR and parser info from parse_details into a FileRecord."""
    record.parse_details = parse_details
    record.chars_extracted = text_len
    record.parser_used = parse_details.get("parser", "")
    record.quality_score = int(parse_details.get("quality_score", -1))

    # OCR details (from pdf_parser.py)
    ocr = parse_details.get("ocr_fallback", {})
    if isinstance(ocr, dict):
        record.ocr_triggered = bool(ocr.get("triggered", False))
        record.ocr_used = bool(ocr.get("used", False))
        record.ocr_status = str(ocr.get("status", ""))
        # OCR chars from either ocrmypdf or page-by-page stats
        if ocr.get("ocrmypdf_chars"):
            record.ocr_chars = int(ocr["ocrmypdf_chars"])
            record.ocr_method = "ocrmypdf"
        else:
            stats = ocr.get("stats", {})
            if isinstance(stats, dict):
                record.ocr_chars = int(stats.get("total_chars", 0))
                record.ocr_method = "tesseract"


def write_report(
    result: Dict[str, Any],
    file_records: List[FileRecord],
    source_folder: str,
    logs_dir: str = "logs",
) -> str:
    """
    Write the indexing report to logs/.

    Parameters
    ----------
    result : dict
        The summary dict returned by Indexer.index_folder().
    file_records : list[FileRecord]
        Per-file processing records collected during indexing.
    source_folder : str
        The folder that was indexed.
    logs_dir : str
        Directory to write the report to (default: logs/).

    Returns
    -------
    str
        Path to the written report file.
    """
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    report_file = logs_path / f"index_report_{timestamp}.txt"
    json_file = logs_path / "index_report_latest.json"

    lines: List[str] = []
    _w = lines.append

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    _w("=" * 78)
    _w("HYBRIDRAG INDEXING REPORT")
    _w("=" * 78)
    _w(f"Generated:     {now.strftime('%Y-%m-%d %H:%M:%S')}")
    _w(f"Source folder:  {source_folder}")

    elapsed = result.get("elapsed_seconds", 0)
    _w(f"Duration:       {_fmt_duration(elapsed)}")
    _w("")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    scanned = result.get("total_files_scanned", 0)
    indexed = result.get("total_files_indexed", 0)
    skipped = result.get("total_files_skipped", 0)
    reindexed = result.get("total_files_reindexed", 0)
    chunks = result.get("total_chunks_added", 0)

    _w("SUMMARY")
    _w("-" * 40)
    _w(f"  Files scanned:     {scanned:>8,}")
    _w(f"  Files indexed:     {indexed:>8,}  ({_pct(indexed, scanned)})")
    _w(f"  Files re-indexed:  {reindexed:>8,}  ({_pct(reindexed, scanned)})")
    _w(f"  Files skipped:     {skipped:>8,}  ({_pct(skipped, scanned)})")
    _w(f"  Chunks created:    {chunks:>8,}")
    _w("")

    # ------------------------------------------------------------------
    # OCR Activity
    # ------------------------------------------------------------------
    ocr_triggered = [r for r in file_records if r.ocr_triggered]
    ocr_used = [r for r in file_records if r.ocr_used]
    ocr_success = [r for r in ocr_used if r.ocr_chars > 0]
    ocr_fail = [r for r in ocr_used if r.ocr_chars == 0]
    ocr_chars_total = sum(r.ocr_chars for r in file_records)
    ocr_deps_missing = [
        r for r in ocr_triggered
        if r.ocr_status == "OCR_DEPS_MISSING"
    ]

    _w("OCR ACTIVITY")
    _w("-" * 40)
    _w(f"  OCR triggered:     {len(ocr_triggered):>8}")
    _w(f"  OCR executed:      {len(ocr_used):>8}")
    _w(f"  OCR success:       {len(ocr_success):>8}  ({_pct(len(ocr_success), len(ocr_used))})")
    _w(f"  OCR no text:       {len(ocr_fail):>8}")
    _w(f"  OCR deps missing:  {len(ocr_deps_missing):>8}")
    _w(f"  Total chars via OCR: {ocr_chars_total:>8,}")
    if ocr_used:
        methods = {}
        for r in ocr_used:
            m = r.ocr_method or "unknown"
            methods[m] = methods.get(m, 0) + 1
        _w(f"  OCR methods:       {methods}")
    _w("")

    # ------------------------------------------------------------------
    # Skip Reasons (sorted by count)
    # ------------------------------------------------------------------
    skip_reasons = result.get("skip_reason_counts", {})
    if skip_reasons:
        _w("SKIP REASONS (sorted by count)")
        _w("-" * 60)
        for reason, count in skip_reasons.items():
            _w(f"  {count:>6}  {reason}")
        _w("")

    # ------------------------------------------------------------------
    # Skipped Extensions (sorted by count)
    # ------------------------------------------------------------------
    skip_exts = result.get("skip_extension_counts", {})
    if skip_exts:
        _w("SKIPPED EXTENSIONS")
        _w("-" * 40)
        for ext, count in skip_exts.items():
            _w(f"  {count:>6}  {ext}")
        _w("")

    # ------------------------------------------------------------------
    # Preflight Blocks
    # ------------------------------------------------------------------
    preflight = result.get("preflight_blocked", [])
    if preflight:
        _w(f"PREFLIGHT BLOCKED ({len(preflight)} files)")
        _w("-" * 60)
        for blocked_path, blocked_reason in preflight:
            name = Path(blocked_path).name
            _w(f"  {name}")
            _w(f"    Reason: {blocked_reason}")
        _w("")

    # ------------------------------------------------------------------
    # Files With No Text (potential OCR/parser issues)
    # ------------------------------------------------------------------
    no_text = [
        r for r in file_records
        if r.status == "skipped"
        and r.skip_reason.startswith("no text extracted")
    ]
    if no_text:
        _w(f"FILES WITH NO TEXT ({len(no_text)} files)")
        _w("-" * 78)
        _w("  These files were parsed but produced zero usable text.")
        _w("  Review for OCR needs, corrupt content, or missing parser deps.")
        _w("")
        for r in no_text:
            name = Path(r.path).name
            _w(f"  {name}")
            _w(f"    Extension: {r.extension}  |  Parser: {r.parser_used}")
            _w(f"    Reason: {r.skip_reason}")
            if r.ocr_triggered:
                _w(f"    OCR: triggered={r.ocr_triggered}, used={r.ocr_used}, "
                   f"status={r.ocr_status}, chars={r.ocr_chars}")
            if r.error_msg:
                _w(f"    Error: {r.error_msg}")
        _w("")

    # ------------------------------------------------------------------
    # OCR Triggered Files (detail)
    # ------------------------------------------------------------------
    if ocr_triggered:
        _w(f"OCR DETAIL ({len(ocr_triggered)} files)")
        _w("-" * 78)
        for r in ocr_triggered:
            name = Path(r.path).name
            icon = "[OK]" if r.ocr_chars > 0 else "[FAIL]"
            _w(f"  {icon} {name}")
            _w(f"    Method: {r.ocr_method or 'none'}  |  "
               f"Status: {r.ocr_status}  |  Chars: {r.ocr_chars:,}")
        _w("")

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------
    errors = [r for r in file_records if r.status == "error"]
    if errors:
        _w(f"ERRORS ({len(errors)} files)")
        _w("-" * 78)
        for r in errors:
            name = Path(r.path).name
            _w(f"  {name}")
            _w(f"    {r.error_msg}")
        _w("")

    # ------------------------------------------------------------------
    # Extension Summary (indexed vs skipped)
    # ------------------------------------------------------------------
    ext_stats: Dict[str, Dict[str, int]] = {}
    for r in file_records:
        e = r.extension or "<no_ext>"
        if e not in ext_stats:
            ext_stats[e] = {"indexed": 0, "skipped": 0, "error": 0, "chunks": 0}
        ext_stats[e][r.status] = ext_stats[e].get(r.status, 0) + 1
        ext_stats[e]["chunks"] += r.chunks_added

    if ext_stats:
        _w("EXTENSION SUMMARY")
        _w("-" * 78)
        _w(f"  {'Ext':<10} {'Indexed':>8} {'Skipped':>8} {'Error':>8} {'Chunks':>8}")
        _w(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for ext in sorted(ext_stats.keys()):
            s = ext_stats[ext]
            _w(f"  {ext:<10} {s.get('indexed',0):>8} {s.get('skipped',0):>8} "
               f"{s.get('error',0):>8} {s['chunks']:>8}")
        _w("")

    # ------------------------------------------------------------------
    # Quality Scores (lowest first -- files that need attention)
    # ------------------------------------------------------------------
    scored = [r for r in file_records if r.quality_score >= 0 and r.status == "indexed"]
    if scored:
        low_quality = sorted(
            [r for r in scored if r.quality_score < 70],
            key=lambda r: r.quality_score,
        )
        avg_score = sum(r.quality_score for r in scored) / len(scored)
        _w("TEXT QUALITY SCORES")
        _w("-" * 78)
        _w(f"  Average quality:   {avg_score:.0f}/100")
        _w(f"  Files scored:      {len(scored)}")
        _w(f"  Below 70 (noisy):  {len(low_quality)}")
        _w("")
        if low_quality:
            _w("  Lowest quality files (may hurt retrieval):")
            _w(f"  {'Score':>5}  {'Ext':<6}  File")
            _w(f"  {'-'*5}  {'-'*6}  {'-'*50}")
            for r in low_quality[:30]:
                name = Path(r.path).name
                _w(f"  {r.quality_score:>5}  {r.extension:<6}  {name}")
            if len(low_quality) > 30:
                _w(f"  ... and {len(low_quality) - 30} more")
        _w("")

    # ------------------------------------------------------------------
    # Tuning Hints
    # ------------------------------------------------------------------
    hints = _generate_hints(result, file_records, ocr_deps_missing, no_text, errors)
    if hints:
        _w("TUNING HINTS")
        _w("-" * 60)
        for hint in hints:
            _w(f"  [!] {hint}")
        _w("")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    _w("=" * 78)
    _w(f"Report: {report_file}")
    _w(f"JSON:   {json_file}")
    _w("=" * 78)

    # Write the text report
    report_text = "\n".join(lines) + "\n"
    try:
        report_file.write_text(report_text, encoding="utf-8")
    except Exception:
        pass

    # Write machine-readable JSON
    json_data = {
        "generated": now.isoformat(),
        "source_folder": source_folder,
        "summary": {
            "files_scanned": scanned,
            "files_indexed": indexed,
            "files_skipped": skipped,
            "files_reindexed": reindexed,
            "chunks_created": chunks,
            "elapsed_seconds": round(elapsed, 1),
        },
        "ocr": {
            "triggered": len(ocr_triggered),
            "executed": len(ocr_used),
            "success": len(ocr_success),
            "no_text": len(ocr_fail),
            "deps_missing": len(ocr_deps_missing),
            "chars_recovered": ocr_chars_total,
        },
        "skip_reasons": skip_reasons,
        "skip_extensions": skip_exts,
        "files": [r.to_dict() for r in file_records if r.status != "indexed"
                  or r.ocr_triggered or r.quality_score < 70],
    }
    try:
        json_file.write_text(
            json.dumps(json_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    return str(report_file)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def _pct(part: int, total: int) -> str:
    """Format a percentage string."""
    if total == 0:
        return "--"
    return f"{100 * part / total:.1f}%"


def _generate_hints(
    result: Dict[str, Any],
    records: List[FileRecord],
    ocr_deps_missing: List[FileRecord],
    no_text: List[FileRecord],
    errors: List[FileRecord],
) -> List[str]:
    """Generate actionable tuning hints based on indexing results."""
    hints = []

    # OCR deps missing
    if ocr_deps_missing:
        exts = set(r.extension for r in ocr_deps_missing)
        hints.append(
            f"{len(ocr_deps_missing)} files triggered OCR but deps are missing "
            f"(pytesseract/pdf2image). Extensions: {', '.join(sorted(exts))}"
        )

    # Many no-text PDFs
    no_text_pdfs = [r for r in no_text if r.extension == ".pdf"]
    if len(no_text_pdfs) > 5:
        hints.append(
            f"{len(no_text_pdfs)} PDFs produced no text. "
            "Check OCR pipeline: pip install pytesseract pdf2image pypdf"
        )

    # Many no-text images
    img_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    no_text_imgs = [r for r in no_text if r.extension in img_exts]
    if len(no_text_imgs) > 3:
        hints.append(
            f"{len(no_text_imgs)} images produced no text. "
            "Verify Tesseract is installed and in PATH: tesseract --version"
        )

    # High skip rate
    scanned = result.get("total_files_scanned", 0)
    skipped = result.get("total_files_skipped", 0)
    if scanned > 0 and skipped / scanned > 0.25:
        hints.append(
            f"Skip rate is {100*skipped/scanned:.0f}% ({skipped}/{scanned}). "
            "Review skip reasons above to identify fixable gaps."
        )

    # Errors
    if len(errors) > 5:
        err_exts: Dict[str, int] = {}
        for r in errors:
            err_exts[r.extension] = err_exts.get(r.extension, 0) + 1
        top = sorted(err_exts.items(), key=lambda kv: -kv[1])[:3]
        top_str = ", ".join(f"{e}({c})" for e, c in top)
        hints.append(
            f"{len(errors)} files threw errors. Top extensions: {top_str}"
        )

    # Hash-match skips (unchanged files)
    skip_reasons = result.get("skip_reason_counts", {})
    hash_skipped = skip_reasons.get("unchanged (hash match)", 0)
    if hash_skipped > 0 and scanned > 0:
        hints.append(
            f"{hash_skipped} files skipped (unchanged). "
            "To force re-index: delete the SQLite DB and re-run."
        )

    # Low quality text (noisy OCR)
    scored = [r for r in records if r.quality_score >= 0 and r.status == "indexed"]
    low_q = [r for r in scored if r.quality_score < 50]
    if len(low_q) > 5:
        hints.append(
            f"{len(low_q)} indexed files scored below 50/100 quality. "
            "These files have noisy text that may hurt retrieval accuracy. "
            "Consider re-scanning or manual cleanup for high-value documents."
        )

    return hints
