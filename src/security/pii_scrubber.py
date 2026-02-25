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

_PATTERNS = [
    # SSN: xxx-xx-xxxx (must come before phone to avoid overlap)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),

    # Credit card: 13-19 digits with optional separators (space or dash)
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD]"),

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

    total = 0
    for pattern, replacement in _PATTERNS:
        text, count = pattern.subn(replacement, text)
        total += count

    return text, total
