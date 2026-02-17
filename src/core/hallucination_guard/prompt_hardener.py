#!/usr/bin/env python3
"""
prompt_hardener.py -- Layer 1: Prompt Hardening
=================================================

PURPOSE:
    Rewrites system prompts to force the LLM to stay grounded in
    retrieved context documents. This is the cheapest and most effective
    first line of defense against hallucinations.

WHY THIS MATTERS:
    Research shows prompt engineering ALONE reduces hallucinations by
    40-60%. This layer costs nothing (just a longer prompt) and catches
    the majority of casual hallucinations before they even happen.

HOW IT WORKS:
    1. Wraps the system prompt with DEFENSE ENVIRONMENT grounding rules
    2. Forces the LLM to cite sources using [Source: chunk_N] format
    3. Adds a refusal protocol ("INSUFFICIENT SOURCE DATA") for gaps
    4. Requires uncertainty language on non-definitive claims
    5. Numbers each context chunk for citation tracking

USAGE:
    from prompt_hardener import PromptHardener

    # Get a hardened prompt package ready for the API call
    pkg = PromptHardener.build_hardened_prompt(
        system_prompt="You are a defense analyst.",
        user_query="What frequency does the radar use?",
        chunks=["The radar operates at 10 MHz.", "Range is 200 km."],
        source_files=["radar_specs.md", "system_overview.md"],
    )
    # pkg["system"] = hardened system prompt
    # pkg["user"]   = user query with numbered context chunks

NETWORK ACCESS: None. This module is 100% offline, pure string manipulation.

AUTHOR: Jeremy (AI-assisted development)
VERSION: 1.0.0
DATE: 2026-02-14
"""


class PromptHardener:
    """
    Rewrites system prompts to force LLMs to stay grounded in context.

    All methods are @staticmethod because the hardener has no state --
    it just transforms strings. No need to create an instance.
    """

    # -------------------------------------------------------------------------
    # GROUNDING PREAMBLE
    # -------------------------------------------------------------------------
    # This text gets prepended to every system prompt when online mode is active.
    # It establishes 5 rules the LLM must follow, written as clearly as possible
    # so the model cannot "creatively interpret" around them.
    #
    # WHY SO AGGRESSIVE:
    #   Polite instructions like "please try to cite sources" don't work reliably.
    #   Defense context demands absolute language: MUST, NEVER, ONLY, ALWAYS.
    #   The "people's lives depend on it" framing activates safety training in
    #   most LLMs (online LLMs, GPT) making them more cautious.
    GROUNDING_PREAMBLE = """CRITICAL INSTRUCTION -- FACTUAL GROUNDING PROTOCOL:

You are operating in a DEFENSE ENVIRONMENT where inaccurate information
can directly endanger human lives. You MUST follow these rules:

1. ONLY USE INFORMATION FROM THE PROVIDED CONTEXT DOCUMENTS.
   - Every factual statement MUST come from the retrieved context below.
   - Do NOT use your training data to fill in gaps.
   - Do NOT infer, extrapolate, or guess beyond what the sources say.
   - If a question cannot be answered from the context, say exactly:
     "INSUFFICIENT SOURCE DATA: The provided documents do not contain
     information to answer this question."

2. CITE YOUR SOURCES.
   - For every factual claim, indicate which chunk it came from.
   - Use: [Source: chunk_N] where N is the chunk number.
   - If you cannot cite a chunk, prefix with: "[UNSOURCED INFERENCE]"

3. DISTINGUISH FACT FROM INFERENCE.
   - Direct from source: state as fact.
   - Logical inference FROM source: prefix with "Based on the source
     material, it appears that..."
   - NEVER present inference as definitive fact.

4. USE APPROPRIATE UNCERTAINTY LANGUAGE.
   - Ambiguous source data: "the sources are unclear on this point."
   - Incomplete source data: "the sources do not address this fully."
   - NEVER use "definitely", "certainly", "obviously", "always",
     "never", or "guaranteed" unless the source uses those exact words.

5. WHEN IN DOUBT, REFUSE.
   - It is ALWAYS safer to say "I don't have sufficient source data"
     than to guess.
   - An incomplete factual answer beats a complete fabricated one.
   - You will NOT be penalized for saying "I don't know from these sources."

REMEMBER: People's lives depend on the accuracy of your response.
"""

    # -------------------------------------------------------------------------
    # CITATION FORMAT
    # -------------------------------------------------------------------------
    # Tells the LLM exactly how to cite. Placed AFTER the preamble so the LLM
    # sees the rules first, then the format to follow.
    CITATION_FORMAT = """
CITATION FORMAT:
  [Source: chunk_1] for the first context chunk
  [Source: chunk_2] for the second, etc.
Place citation IMMEDIATELY after the fact it supports.
"""

    # -------------------------------------------------------------------------
    # CONTEXT WRAPPER
    # -------------------------------------------------------------------------
    # Template for wrapping the actual retrieved chunks. The numbered format
    # makes it easy for both the LLM to cite and for us to verify citations.
    CONTEXT_WRAPPER = """
=== BEGIN RETRIEVED SOURCE DOCUMENTS ===
{chunk_count} context chunks retrieved. Use ONLY these. Each is numbered.

{numbered_chunks}
=== END RETRIEVED SOURCE DOCUMENTS ===

REMINDER: If the answer is not in the chunks above, say "INSUFFICIENT SOURCE DATA."
"""

    @staticmethod
    def harden_system_prompt(original_prompt):
        """
        Wrap an existing system prompt with anti-hallucination instructions.

        WHAT IT DOES:
            Takes your normal system prompt (e.g., "You are a helpful analyst")
            and prepends the grounding preamble + citation format to it.
            The original prompt is preserved under a "ORIGINAL TASK INSTRUCTIONS"
            header so the LLM still knows its role.

        PARAMETERS:
            original_prompt: str -- Your normal system prompt

        RETURNS:
            str -- The hardened system prompt (much longer, more restrictive)
        """
        return (
            PromptHardener.GROUNDING_PREAMBLE + "\n"
            + PromptHardener.CITATION_FORMAT + "\n"
            + "--- ORIGINAL TASK INSTRUCTIONS ---\n"
            + original_prompt
        )

    @staticmethod
    def wrap_context_chunks(chunks, source_files=None):
        """
        Wrap retrieved chunks with numbering for citation tracking.

        WHAT IT DOES:
            Takes the raw text chunks from the vector search and wraps each
            one with a numbered header. If source file names are provided,
            those are included for traceability.

        PARAMETERS:
            chunks:       list of str -- The retrieved context chunks
            source_files: list of str -- Optional file names per chunk

        RETURNS:
            str -- Formatted context block ready for the user message

        EXAMPLE OUTPUT:
            --- CHUNK 1 (from: radar_specs.md) ---
            The radar operates at 10 MHz with a range of 200 km.

            --- CHUNK 2 (from: system_overview.md) ---
            The system was deployed in 2019.
        """
        parts = []
        for i, chunk in enumerate(chunks):
            # Add source file name if available
            src = ""
            if source_files and i < len(source_files):
                src = f" (from: {source_files[i]})"
            parts.append(f"--- CHUNK {i + 1}{src} ---\n{chunk}\n")
        return PromptHardener.CONTEXT_WRAPPER.format(
            chunk_count=len(chunks),
            numbered_chunks="\n".join(parts),
        )

    @staticmethod
    def build_hardened_prompt(system_prompt, user_query, chunks,
                              source_files=None):
        """
        Build a complete hardened prompt package for the LLM API call.

        This is the main method you call from query_engine.py. It returns
        a dict with "system" and "user" keys that you pass directly to
        the OpenAI-compatible API.

        PARAMETERS:
            system_prompt: str       -- Your normal system prompt
            user_query:    str       -- The user's question
            chunks:        list[str] -- Retrieved context chunks
            source_files:  list[str] -- Optional file names per chunk

        RETURNS:
            dict with:
                "system": str -- Hardened system prompt
                "user":   str -- User message with numbered context + query
        """
        return {
            "system": PromptHardener.harden_system_prompt(system_prompt),
            "user": (
                PromptHardener.wrap_context_chunks(chunks, source_files)
                + "\n\nUSER QUERY:\n" + user_query
            ),
        }
