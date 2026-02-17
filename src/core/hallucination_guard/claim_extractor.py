#!/usr/bin/env python3
"""
claim_extractor.py -- Layer 2a: Claim Extraction
==================================================

PURPOSE:
    Decomposes an LLM response into individual factual claims that can
    each be verified independently against source documents.

WHY SENTENCE-LEVEL VERIFICATION:
    A response can be 90% accurate but contain one hallucinated sentence
    that changes the entire conclusion. For example:

        "The radar operates at 10 MHz [correct] with a range of 200 km
        [correct] and was upgraded in 2024 [HALLUCINATION]."

    If we only check the response as a whole, we might miss that one bad
    sentence. By splitting into individual claims, we catch it.

HOW IT WORKS:
    1. Split response text into sentences (abbreviation-aware)
    2. For each sentence, decide if it is a factual claim or trivial
       (greetings, headers, markdown formatting, etc.)
    3. Extract any citation markers [Source: chunk_N] from each sentence
    4. Return a structured list of claims ready for NLI verification

NETWORK ACCESS: None. This module is 100% offline, pure string/regex work.

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""

import re


class ClaimExtractor:
    """
    Decomposes an LLM response into individual factual claims.

    All methods are @staticmethod -- no state needed, just text processing.
    """

    # -------------------------------------------------------------------------
    # NON-CLAIM PATTERNS
    # -------------------------------------------------------------------------
    # These regex patterns identify sentences that are NOT factual claims.
    # We skip these during verification because flagging "Here is what I found"
    # as UNSUPPORTED would be silly and waste NLI model cycles.
    #
    # Categories:
    #   - Transitional phrases ("here is", "below", "as follows")
    #   - Summaries ("in summary", "to summarize")
    #   - Politeness ("I hope", "please", "feel free")
    #   - Labels/notes ("Note:", "Warning:", "Disclaimer:")
    #   - Short affirmatives ("yes", "no", "sure")
    #   - Markdown formatting (headers, bold lines, bullets, code fences)
    #   - The refusal phrase we taught the LLM in prompt hardening
    NON_CLAIM_PATTERNS = [
        r"^(here|below|above|the following|as follows)",
        r"^(in summary|to summarize|in conclusion|overall)",
        r"^(i hope|i trust|please|let me|feel free)",
        r"^(note:|warning:|important:|disclaimer:)",
        r"^(yes|no|sure|okay|understood)[.,!]?\s*$",
        r"^#{1,6}\s",          # Markdown headers: # Title, ## Subtitle
        r"^\*\*.*\*\*$",       # Bold-only lines: **Something**
        r"^[-*]\s",            # Bullet points: - item, * item
        r"^---+$",             # Horizontal rules: ---
        r"^\d+\.\s*$",         # Bare numbered list markers: 1.
        r"^```",               # Code fences
        r"^INSUFFICIENT SOURCE DATA",  # Our taught refusal phrase
    ]

    # Regex to find citation markers like [Source: chunk_1] in the response.
    # These were requested by our prompt hardening in Layer 1.
    # We extract them so we can cross-check: did the LLM cite the right chunk?
    CITATION_PATTERN = re.compile(
        r"\[Source:\s*chunk_(\d+)\]", re.IGNORECASE
    )

    @staticmethod
    def split_into_sentences(text):
        """
        Split text into sentences, handling abbreviations correctly.

        REDESIGNED (Feb 2026 -- found during simulation testing):
            Old design: blindly replaced ALL abbreviation periods with a
            placeholder. BUG: "300 MHz. It uses..." lost the sentence break
            because "MHz." was treated as mid-sentence even at end of sentence.

            New design: only protect abbreviation periods when followed by
            lowercase, digit, or comma (meaning it IS mid-sentence). If
            followed by uppercase or end-of-text, it IS a sentence boundary.

            "operates at 300 MHz. It uses..."  -> SPLITS (MHz. + uppercase I)
            "See Fig. 3 for details."          -> no split (Fig. + digit 3)
            "e.g. the antenna gain..."         -> no split (e.g. + lowercase t)

        PARAMETERS:
            text: str -- The full LLM response text

        RETURNS:
            list of str -- Individual sentences
        """
        protected = text

        # Common abbreviations in defense/engineering context.
        # Each one has a period that could cause a false sentence split.
        abbreviations = [
            "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Sr.", "Jr.",
            "vs.", "etc.", "i.e.", "e.g.", "approx.", "dept.",
            "Fig.", "fig.", "No.", "no.", "Vol.", "vol.",
            "Rev.", "Gen.", "Col.", "Sgt.", "Corp.",
            "MHz.", "GHz.", "dB.", "dBm.", "km.", "ft.", "lb.",
        ]
        for abbr in abbreviations:
            # Only protect if followed by: lowercase, digit, comma, or paren
            # This means "MHz. The" is NOT protected (sentence boundary)
            # But "Fig. 3" and "e.g. the" ARE protected (mid-sentence)
            pattern = re.escape(abbr) + r'(?=\s+[a-z0-9,(])'
            protected = re.sub(pattern, abbr.replace(".", "<DOT>"), protected)

        # Split on sentence-ending punctuation (.!?) followed by whitespace
        # and a capital letter, quote, or opening bracket.
        raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\047([])', protected)

        # Restore abbreviations and filter out tiny fragments
        sentences = []
        for s in raw:
            restored = s.replace("<DOT>", ".").strip()
            if restored and len(restored) > 5:
                sentences.append(restored)
        return sentences

    @staticmethod
    def is_factual_claim(sentence):
        """
        Determine if a sentence is a factual claim that needs verification.

        A sentence is NOT a factual claim if:
            - It matches any NON_CLAIM_PATTERN (structural/transitional)
            - It ends with a question mark (questions aren't claims)
            - It has fewer than 4 words (too short to be meaningful)
            - It contains our taught refusal phrase

        PARAMETERS:
            sentence: str -- A single sentence from the LLM response

        RETURNS:
            bool -- True if this needs NLI verification, False if trivial
        """
        s_lower = sentence.lower().strip()

        # Check against all non-claim patterns
        for pattern in ClaimExtractor.NON_CLAIM_PATTERNS:
            if re.match(pattern, s_lower):
                return False

        # Questions are not factual assertions
        if s_lower.endswith("?"):
            return False

        # Very short fragments are usually noise
        if len(s_lower.split()) < 4:
            return False

        # Our refusal phrase from prompt hardening is not a claim
        if "insufficient source data" in s_lower:
            return False

        return True

    @staticmethod
    def extract_claims(response_text):
        """
        Extract all factual claims from an LLM response.

        This is the main method called by the hallucination guard.
        It splits the response into sentences, classifies each one,
        and extracts citation markers.

        PARAMETERS:
            response_text: str -- The complete LLM response

        RETURNS:
            list of dict, each with:
                text:          str       -- Cleaned claim text (no citation markers)
                cited_chunks:  list[int] -- Chunk numbers cited (from [Source: chunk_N])
                is_trivial:    bool      -- True if non-factual (skip verification)
                original_index: int      -- Position in the response (for reconstruction)
                original_text: str       -- Raw sentence before cleaning
        """
        sentences = ClaimExtractor.split_into_sentences(response_text)
        claims = []

        for i, sentence in enumerate(sentences):
            # Extract any citation markers like [Source: chunk_3]
            cited = ClaimExtractor.CITATION_PATTERN.findall(sentence)
            cited_chunks = [int(c) for c in cited]

            # Clean the sentence: remove citation markers and unsourced tags
            clean = ClaimExtractor.CITATION_PATTERN.sub("", sentence).strip()
            clean = clean.replace("[UNSOURCED INFERENCE]", "").strip()

            # Classify: is this a factual claim that needs checking?
            is_trivial = not ClaimExtractor.is_factual_claim(clean)

            claims.append({
                "text": clean,
                "cited_chunks": cited_chunks,
                "is_trivial": is_trivial,
                "original_index": i,
                "original_text": sentence,
            })

        return claims
