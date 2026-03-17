# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the response sanitizer part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Response Sanitizer (src/security/response_sanitizer.py)
# ============================================================================
# PURPOSE:
#   Layered guard against prompt injection echo.
#   This is NOT a content "filter"; it's a structural sanitizer that removes
#   meta-instructions and prompt-injection artifacts that occasionally leak into
#   model outputs.
#
# PRINCIPLES:
#   - Do not rewrite meaning aggressively.
#   - Remove obvious instruction/meta blocks.
#   - Remove lines that attempt to override system behavior.
#   - Portable (stdlib only).
#
# NOTE:
#   For higher assurance, couple this with retrieval-side injection rejection and
#   a scorer that penalizes repetition of injected claims (you already do some).
# ============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_INJECTION_LINE_PATTERNS = [
    r"^\s*(ignore|disregard)\s+(previous|all)\s+instructions\b.*$",
    r"^\s*system\s+prompt\b.*$",
    r"^\s*developer\s+message\b.*$",
    r"^\s*you\s+are\s+chatgpt\b.*$",
    r"^\s*BEGIN\s+PROMPT\s+INJECTION\b.*$",
    r"^\s*END\s+PROMPT\s+INJECTION\b.*$",
    r"^\s*<\/?\s*(system|assistant|developer)\s*>\s*$",
]

_BLOCK_PATTERNS = [
    r"(?is)```\s*(system|developer|assistant).*?```",  # fenced role blocks
    r"(?is)<\s*(system|developer|assistant)\s*>.*?<\s*/\s*\1\s*>",
]


@dataclass
class ResponseSanitizer:
    max_removed_lines: int = 50

    def sanitize_text(self, text: str) -> str:
        if not text:
            return text

        original = text

        # Remove role/meta blocks first.
        for bp in _BLOCK_PATTERNS:
            text = re.sub(bp, "", text)

        # Remove suspicious single lines.
        lines = text.splitlines()
        cleaned = []
        removed = 0
        for ln in lines:
            if removed < self.max_removed_lines and self._looks_like_injection_line(ln):
                removed += 1
                continue
            cleaned.append(ln)

        text = "\n".join(cleaned).strip()

        # If sanitization removed everything, return safe fallback -- never the original.
        return text if text else "[Response removed after content verification]"

    def _looks_like_injection_line(self, line: str) -> bool:
        for pat in _INJECTION_LINE_PATTERNS:
            if re.match(pat, line, flags=re.IGNORECASE):
                return True
        # Also remove explicit self-referential meta.
        if "system prompt" in line.lower() or "developer message" in line.lower():
            return True
        return False
