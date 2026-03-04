# ============================================================================
# HybridRAG -- Image OCR Parser (src/parsers/image_parser.py)
# ============================================================================
#
# WHAT: Extracts text from image files using Optical Character Recognition (OCR)
# WHY:  Engineers often scan paper documents, take photos of whiteboards, or
#       receive screenshots. These images contain valuable text that RAG
#       cannot search unless we "read" it with OCR. Without this parser,
#       all image-based knowledge is invisible to search.
# HOW:  Opens the image with Pillow (Python Imaging Library), converts to
#       RGB, then feeds it to Tesseract OCR -- the industry-standard open
#       source text recognition engine. Tesseract identifies letters/words
#       in the image and returns them as a text string.
#
# SUPPORTED FORMATS:
#   .png, .jpg, .jpeg, .tif, .tiff, .bmp, .gif, .webp
#
# DEPENDENCIES (TWO separate installs):
#   1. Python packages:  pip install pillow pytesseract
#   2. Tesseract binary: Must install the Tesseract OCR application
#      separately (the .exe is NOT installed by pip).
#      Windows: available via Software Center or https://github.com/tesseract-ocr
#      Set TESSERACT_CMD env var if not on PATH.
#
# GRACEFUL FALLBACK:
#   If either Pillow or Tesseract is missing, the parser returns empty
#   text with a diagnostic reason in the details dict. The indexer logs
#   it and moves on -- no crash.
#
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple


def _try_import_pil():
    try:
        from PIL import Image  # type: ignore
        return True, Image, None
    except Exception as e:
        return False, None, f"IMPORT_ERROR: {type(e).__name__}: {e}"


def _try_import_pytesseract():
    try:
        import pytesseract  # type: ignore
        return True, pytesseract, None
    except Exception as e:
        return False, None, f"IMPORT_ERROR: {type(e).__name__}: {e}"


class ImageOCRParser:
    """
    OCR parser for images using Tesseract (via pytesseract).
    """

    def parse(self, file_path: str) -> str:
        text, _ = self.parse_with_details(file_path)
        return text

    def parse_with_details(self, file_path: str) -> Tuple[str, Dict[str, Any]]:
        path = Path(file_path)
        details: Dict[str, Any] = {
            "file": str(path),
            "parser": "ImageOCRParser",
        }

        ok_pil, Image, pil_err = _try_import_pil()
        ok_ts, pytesseract, ts_err = _try_import_pytesseract()

        details["pillow_installed"] = bool(ok_pil)
        details["pytesseract_installed"] = bool(ok_ts)

        if not ok_pil:
            details["winner"] = "none"
            details["likely_reason"] = "PILLOW_NOT_INSTALLED"
            details["error"] = pil_err
            return self._metadata_fallback(path, details, None)

        if not ok_ts:
            details["winner"] = "none"
            details["likely_reason"] = "PYTESSERACT_NOT_INSTALLED"
            details["error"] = ts_err
            return self._metadata_fallback(path, details, None)

        # Optional: allow user to configure tesseract.exe path via env var
        # Example:
        #   $env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
        tcmd = (str(Path(pytesseract.pytesseract.tesseract_cmd)) if hasattr(pytesseract, "pytesseract") else "")
        env_cmd = (Path(str(Path.cwd())) / "tesseract.exe")  # not used, just a placeholder

        tesseract_cmd_env = (str(Path(Path.cwd())) if False else None)  # placeholder to keep comments clear
        tesseract_cmd_env = None  # actual env read below

        tesseract_cmd_env = os.getenv("TESSERACT_CMD")

        if tesseract_cmd_env:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_env
                details["tesseract_cmd_source"] = "env:TESSERACT_CMD"
                details["tesseract_cmd"] = tesseract_cmd_env
            except Exception:
                # If that fails, we keep default and let OCR attempt reveal error
                details["tesseract_cmd_source"] = "env:TESSERACT_CMD (failed_to_set)"
                details["tesseract_cmd"] = tesseract_cmd_env
        else:
            details["tesseract_cmd_source"] = "pytesseract_default"
            details["tesseract_cmd"] = tcmd

        try:
            img = Image.open(path)

            # Preprocess for better OCR accuracy on scanned documents
            img = self._preprocess(img)

            # OCR with LSTM engine + auto page segmentation
            tess_config = "--oem 1 --psm 3"
            text = pytesseract.image_to_string(img, config=tess_config)

            text = (text or "").strip()
            details["total_len"] = len(text)
            details["winner"] = "tesseract"

            if not text:
                details["likely_reason"] = "OCR_RETURNED_EMPTY_TEXT"
                return self._metadata_fallback(path, details, img)
            return text, details

        except Exception as e:
            details["winner"] = "none"
            details["likely_reason"] = "OCR_UNAVAILABLE_OR_FAILED"
            details["error"] = f"RUNTIME_ERROR: {type(e).__name__}: {e}"
            return self._metadata_fallback(path, details, None)

    @staticmethod
    def _preprocess(pil_image):
        """Clean up image for better OCR: grayscale, contrast, sharpen."""
        try:
            from PIL import ImageFilter, ImageOps
            img = pil_image.convert("L")
            img = ImageOps.autocontrast(img, cutoff=1)
            img = img.filter(ImageFilter.SHARPEN)
            threshold = int(os.getenv("HYBRIDRAG_OCR_BIN_THRESHOLD", "130"))
            img = img.point(lambda px: 255 if px > threshold else 0, mode="1")
            return img
        except Exception:
            return pil_image

    def _metadata_fallback(
        self,
        path: Path,
        details: Dict[str, Any],
        img_obj: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Optional fallback that emits image metadata as text when OCR fails.
        Enable with HYBRIDRAG_IMAGE_METADATA_FALLBACK=1 (default enabled).
        """
        if os.getenv("HYBRIDRAG_IMAGE_METADATA_FALLBACK", "1").strip().lower() not in (
            "1", "true", "yes", "on",
        ):
            return "", details

        meta_lines = [f"[IMAGE_METADATA] file={path.name} ext={path.suffix.lower()}"]
        try:
            st = path.stat()
            meta_lines.append(f"size_bytes={st.st_size}")
            meta_lines.append(f"modified_ts={int(st.st_mtime)}")
        except Exception:
            pass

        img = img_obj
        if img is None:
            try:
                from PIL import Image  # type: ignore
                img = Image.open(path)
            except Exception:
                img = None

        if img is not None:
            try:
                meta_lines.append(f"format={getattr(img, 'format', 'unknown')}")
                meta_lines.append(f"mode={getattr(img, 'mode', 'unknown')}")
                if hasattr(img, "size") and img.size:
                    meta_lines.append(f"width={img.size[0]}")
                    meta_lines.append(f"height={img.size[1]}")
            except Exception:
                pass

        details["metadata_fallback_used"] = True
        details["winner"] = "metadata_fallback"
        details.setdefault("likely_reason", "OCR_FAILED_METADATA_FALLBACK_USED")
        return "\n".join(meta_lines), details
