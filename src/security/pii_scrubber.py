# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the pii scrubber part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- PII Scrubber (src/security/pii_scrubber.py)
# ============================================================================
# WHAT: Regex-based PII detection and replacement engine.
# WHY:  When queries go to online APIs (Azure/OpenAI), user text and
#       retrieved document chunks leave the machine. This module strips
#       personally identifiable information before that happens.
# HOW:  Compiled regex patterns match common PII formats and replace
#       them with bracketed placeholders ([EMAIL], [PHONE], etc.).
# USAGE: Called by APIRouter.query() when security.pii_sanitization
#        is enabled in config. Only runs on the online code path.
# ============================================================================

import re

# -- Compiled patterns (loaded once at import time) --
# Order matters: more specific patterns first to avoid partial matches.
_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_PATTERNS = [
    # SSN: xxx-xx-xxxx (must come before phone to avoid overlap)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),

    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),

    # Phone: US formats -- (xxx) xxx-xxxx, xxx-xxx-xxxx, +1xxxxxxxxxx, etc.
    (re.compile(
        r"(?:\+1[-.\s]?)?"          # optional +1 prefix
        r"(?:\(\d{3}\)|\d{3})"      # area code: (xxx) or xxx
        r"[-.\s]?"                   # separator
        r"\d{3}"                     # exchange
        r"[-.\s]?"                   # separator
        r"\d{4}\b"                   # subscriber
    ), "[PHONE]"),

    # IPv4 addresses (skip localhost 127.x.x.x)
    (re.compile(
        r"\b(?!127\.)"              # negative lookahead: skip 127.x
        r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ), "[IP]"),
]


def _luhn_valid(digits: str) -> bool:
    """Return True only for real card-like numbers, not arbitrary long IDs."""
    if not digits or not digits.isdigit():
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, char in enumerate(digits):
        digit = int(char)
        if idx % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _scrub_cards(text: str) -> tuple[str, int]:
    """Scrub only card-like numbers that pass Luhn validation."""
    count = 0

    def _replace(match):
        nonlocal count
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            count += 1
            return "[CARD]"
        return raw

    return _CARD_PATTERN.sub(_replace, text), count


def scrub_pii(text: str) -> tuple:
    """Replace PII patterns in text with bracketed placeholders.

    Args:
        text: Input string that may contain PII.

    Returns:
        Tuple of (scrubbed_text, replacement_count).
        If no PII is found, returns the original text unchanged with count 0.
    """
    if not text:
        return text, 0

    text, total = _scrub_cards(text)
    for pattern, replacement in _PATTERNS:
        text, count = pattern.subn(replacement, text)
        total += count

    return text, total
