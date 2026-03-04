# ============================================================================
# HybridRAG -- OCR Text Cleanup (src/core/ocr_cleanup.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Cleans up raw OCR text BEFORE it enters the chunker and embedder.
#   OCR engines produce noisy text: broken words, phantom characters,
#   garbled punctuation, repeated page headers, and junk lines from
#   scan edges. These errors cascade through the RAG pipeline --
#   the chunker splits on wrong boundaries, the embedder indexes
#   misspelled terms, and retrieval fails when users search for the
#   correct spelling.
#
#   This module applies safe, conservative regex fixes that improve
#   text quality without risking false corrections. Every rule is
#   designed to fix patterns that are ALWAYS wrong (not ambiguous).
#
# WHERE IT RUNS:
#   Called by the indexer after parsing and before chunking/embedding.
#   parse -> clean_ocr_text() -> validate -> chunk -> embed -> store
#
# ALSO PROVIDES:
#   score_text_quality() -- returns 0-100 quality score for the
#   index report. Helps identify which files need attention.
#
# DEPENDENCIES: NONE (all stdlib -- re module only)
# INTERNET ACCESS: NONE
# ============================================================================

from __future__ import annotations

import re
from typing import Tuple


# -- Control characters that are never useful in extracted text ----------
# Keep: \n (newline), \t (tab), \r (carriage return, normalized later)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# -- Excessive whitespace patterns --------------------------------------
_MULTI_SPACE = re.compile(r"[ \t]{2,}")  # 2+ spaces/tabs -> single space
_MULTI_BLANK = re.compile(r"\n{4,}")     # 4+ blank lines -> 2 blank lines
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)

# -- Broken hyphenation across lines ------------------------------------
# Pattern: "calibra-\n  tion" -> "calibration"
# Only join when the second line starts with a lowercase letter
# (avoids breaking "self-\nAwareness" style constructs)
_BROKEN_HYPHEN = re.compile(r"(\w)-\s*\n\s*([a-z])")

# -- Isolated single characters on their own line -----------------------
# These are almost always scan noise from page edges or artifacts.
# Excludes "I" and "a" (valid English words) and list markers.
_JUNK_LINE = re.compile(
    r"^[ \t]*[^IiAa0-9\n\-\*\u2022][ \t]*$", re.MULTILINE
)

# -- Missing space after sentence punctuation ---------------------------
# "word.Another" -> "word. Another" (but not "3.14" or "file.txt")
_MISSING_SPACE = re.compile(r"([a-z])\.([A-Z])")

# -- Repeated page header/footer detection ------------------------------
# If the same line appears 3+ times in a document, it's likely a
# header or footer that was OCR'd on every page.
_MIN_REPEAT_FOR_HEADER = 3
_MIN_HEADER_LEN = 10  # ignore short repeats like "Page"

# -- Unicode normalization (smart quotes, special dashes) ---------------
_UNICODE_MAP = {
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2013": "-",   # en-dash
    "\u2014": "--",  # em-dash
    "\u2026": "...", # ellipsis
    "\u00a0": " ",   # non-breaking space
    "\ufeff": "",    # BOM
    "\u200b": "",    # zero-width space
    "\u200c": "",    # zero-width non-joiner
    "\u200d": "",    # zero-width joiner
    "\ufffd": "",    # replacement character (OCR garbage)
}
_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_MAP))


def clean_ocr_text(text: str) -> str:
    """
    Clean OCR artifacts from extracted text.

    Safe, conservative fixes only -- no dictionary lookups, no ML models,
    no ambiguous corrections. Every rule targets patterns that are
    ALWAYS wrong in natural text.

    Parameters
    ----------
    text : str
        Raw text from parser (may be clean digital text or noisy OCR).

    Returns
    -------
    str
        Cleaned text, ready for chunking and embedding.
    """
    if not text:
        return text

    # 1. Strip control characters (null bytes, form feeds, etc.)
    text = _CONTROL_CHARS.sub("", text)

    # 2. Normalize line endings (CRLF -> LF)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Normalize unicode artifacts (smart quotes, special dashes)
    text = _UNICODE_RE.sub(lambda m: _UNICODE_MAP[m.group()], text)

    # 4. Fix broken hyphenation across lines
    #    "calibra-\n  tion" -> "calibration"
    text = _BROKEN_HYPHEN.sub(r"\1\2", text)

    # 5. Strip trailing whitespace from each line
    text = _TRAILING_WS.sub("", text)

    # 6. Remove isolated single-character junk lines (scan noise)
    text = _JUNK_LINE.sub("", text)

    # 7. Collapse excessive blank lines (4+ -> 2)
    text = _MULTI_BLANK.sub("\n\n\n", text)

    # 8. Fix missing space after sentence punctuation
    #    "word.Another" -> "word. Another"
    text = _MISSING_SPACE.sub(r"\1. \2", text)

    # 9. Strip repeated page headers/footers
    text = _strip_repeated_headers(text)

    # 10. Final whitespace cleanup -- collapse runs of spaces
    #     but preserve leading indentation (important for tables)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if not line.strip():
            cleaned.append("")
            continue
        # Preserve leading whitespace, collapse internal spaces
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        stripped = _MULTI_SPACE.sub(" ", stripped)
        cleaned.append(indent + stripped)
    text = "\n".join(cleaned)

    return text.strip()


def _strip_repeated_headers(text: str) -> str:
    """
    Remove lines that appear 3+ times in the document.

    These are almost always page headers/footers that OCR picked up
    on every page (e.g., "Company Confidential", "Page X of Y",
    document titles repeated on every page).
    """
    lines = text.split("\n")
    if len(lines) < 20:
        return text

    # Count exact line occurrences (stripped, case-sensitive)
    line_counts: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if len(stripped) >= _MIN_HEADER_LEN:
            line_counts[stripped] = line_counts.get(stripped, 0) + 1

    # Find lines that repeat too often
    headers = {
        line for line, count in line_counts.items()
        if count >= _MIN_REPEAT_FOR_HEADER
    }

    if not headers:
        return text

    # Remove those lines
    filtered = [
        line for line in lines
        if line.strip() not in headers
    ]
    return "\n".join(filtered)


def score_text_quality(text: str) -> int:
    """
    Score extracted text quality on a 0-100 scale.

    Used in the index report to flag files needing attention.
    Higher = cleaner text. Lower = likely OCR noise or garbage.

    Scoring factors:
      - Alphabetic ratio (what % of chars are letters)
      - Average word length (short words = broken OCR)
      - Line density (chars per line -- very short = noise)
      - Punctuation sanity (reasonable ratio of periods/commas)

    Returns
    -------
    int
        Quality score 0-100. Rough guide:
        90-100: Clean digital text
        70-89:  Decent OCR, minor artifacts
        50-69:  Noisy OCR, some retrieval impact
        30-49:  Poor OCR, significant retrieval impact
        0-29:   Garbage, likely needs manual review
    """
    if not text or not text.strip():
        return 0

    total_chars = len(text)
    if total_chars == 0:
        return 0

    # --- Factor 1: Alphabetic ratio (0-30 points) ---
    alpha_count = sum(1 for c in text if c.isalpha())
    alpha_ratio = alpha_count / total_chars
    # Good text is 60-80% alphabetic. Below 40% is suspicious.
    alpha_score = min(30, int(alpha_ratio * 50))

    # --- Factor 2: Average word length (0-25 points) ---
    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        # English averages ~5 chars/word. OCR noise has 1-2 char fragments.
        if avg_word_len >= 4.0:
            word_score = 25
        elif avg_word_len >= 3.0:
            word_score = 18
        elif avg_word_len >= 2.0:
            word_score = 10
        else:
            word_score = 3
    else:
        word_score = 0

    # --- Factor 3: Line density (0-25 points) ---
    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        avg_line_len = sum(len(l) for l in lines) / len(lines)
        # Good text: 40-80 chars/line. Very short lines = noise.
        if avg_line_len >= 30:
            line_score = 25
        elif avg_line_len >= 15:
            line_score = 15
        elif avg_line_len >= 8:
            line_score = 8
        else:
            line_score = 2
    else:
        line_score = 0

    # --- Factor 4: Junk character ratio (0-20 points) ---
    # Control chars, replacement chars, excessive symbols
    junk_count = len(_CONTROL_CHARS.findall(text))
    junk_count += text.count("\ufffd")
    junk_ratio = junk_count / total_chars if total_chars > 0 else 0
    if junk_ratio < 0.001:
        junk_score = 20
    elif junk_ratio < 0.01:
        junk_score = 14
    elif junk_ratio < 0.05:
        junk_score = 7
    else:
        junk_score = 0

    return min(100, alpha_score + word_score + line_score + junk_score)
