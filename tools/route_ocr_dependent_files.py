#!/usr/bin/env python3
"""
Route OCR-dependent files into a dedicated queue for separate processing.

WHY:
    In restricted environments (e.g., no Tesseract approval), OCR-dependent
    files can dominate skips and obscure native-text indexing progress.
    This tool isolates likely OCR-required files (images + scan-like PDFs)
    into a separate folder while preserving relative paths.

USAGE:
    python tools/route_ocr_dependent_files.py --source "D:\\RAG Source Data"
    python tools/route_ocr_dependent_files.py --source "D:\\RAG Source Data" --mode move
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".wmf", ".emf", ".psd",
}


def _pdf_native_text_probe(pdf_path: Path, max_pages: int = 3) -> Tuple[int, str]:
    """
    Return (native_char_count, method) using lightweight native extraction only.
    This intentionally does NOT use OCR.
    """
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        chars = 0
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            try:
                chars += len((page.extract_text() or "").strip())
            except Exception:
                continue
        return chars, "pypdf"
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        chars = 0
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                try:
                    chars += len((page.extract_text() or "").strip())
                except Exception:
                    continue
        return chars, "pdfplumber"
    except Exception:
        return 0, "none"


def classify_ocr_dependency(path: Path, pdf_min_chars: int, pdf_probe_pages: int) -> Tuple[bool, str]:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return True, "image_extension_requires_ocr"
    if ext == ".pdf":
        chars, method = _pdf_native_text_probe(path, max_pages=pdf_probe_pages)
        if chars < pdf_min_chars:
            return True, f"pdf_native_text_low(chars={chars},method={method})"
        return False, f"pdf_native_text_ok(chars={chars},method={method})"
    return False, "non_ocr_format"


def copy_or_move(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "move":
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(str(src), str(dst))


def run(
    source: Path,
    out_root: Path,
    mode: str,
    pdf_min_chars: int,
    pdf_probe_pages: int,
) -> Dict[str, object]:
    out_root.mkdir(parents=True, exist_ok=True)

    routed: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        # Never recurse into queue folder itself when queue is inside source
        try:
            if out_root in p.parents:
                continue
        except Exception:
            pass
        if out_root.name in p.parts:
            continue

        is_ocr_dep, reason = classify_ocr_dependency(
            p, pdf_min_chars=pdf_min_chars, pdf_probe_pages=pdf_probe_pages
        )
        rel = p.relative_to(source)
        if is_ocr_dep:
            dst = out_root / rel
            copy_or_move(p, dst, mode=mode)
            routed.append(
                {"file": str(p), "relative": str(rel), "destination": str(dst), "reason": reason}
            )
        else:
            skipped.append({"file": str(p), "relative": str(rel), "reason": reason})

    manifest = {
        "source": str(source),
        "queue_folder": str(out_root),
        "mode": mode,
        "pdf_min_chars": pdf_min_chars,
        "pdf_probe_pages": pdf_probe_pages,
        "routed_count": len(routed),
        "non_routed_count": len(skipped),
        "routed": routed,
    }
    manifest_path = out_root / "ocr_queue_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Route OCR-dependent files into a queue folder.")
    p.add_argument("--source", required=True, help="Source folder to scan")
    p.add_argument(
        "--queue-output",
        default="",
        help="Output folder for OCR queue. Default: <source>\\_ocr_queue",
    )
    p.add_argument(
        "--mode",
        choices=["copy", "move"],
        default="copy",
        help="Copy keeps originals in place; move removes from source",
    )
    p.add_argument(
        "--pdf-min-native-chars",
        type=int,
        default=40,
        help="PDFs with fewer native chars than this threshold are routed as OCR-dependent",
    )
    p.add_argument(
        "--pdf-probe-pages",
        type=int,
        default=3,
        help="How many pages to sample for native PDF text probing",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    source = Path(args.source).resolve()
    if not source.exists() or not source.is_dir():
        print(f"[ERROR] Source folder not found: {source}")
        return 2

    result = run(
        source=source,
        out_root=(Path(args.queue_output).resolve() if args.queue_output else (source / "_ocr_queue")),
        mode=args.mode,
        pdf_min_chars=args.pdf_min_native_chars,
        pdf_probe_pages=args.pdf_probe_pages,
    )
    print(f"[OK] Routed {result['routed_count']} OCR-dependent files")
    print(f"[OK] Non-routed files: {result['non_routed_count']}")
    print(f"[OK] Queue folder: {result['queue_folder']}")
    print(f"[OK] Manifest: {Path(result['queue_folder']) / 'ocr_queue_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
