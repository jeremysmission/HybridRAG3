# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the query expander part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Query Expander / HyDE Module (src/core/query_expander.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Transforms user queries BEFORE they hit the retriever to improve search
#   quality. Think of it as a search librarian who rewrites your question
#   into something the catalog understands better.
#
#   Three transformation strategies, layered by cost:
#
#   1. ACRONYM EXPANSION (free, instant)
#      Engineering corpora are full of acronyms. "TCXO calibration" becomes
#      "TCXO (Temperature Compensated Crystal Oscillator) calibration" so the
#      embedder can match against documents that use either form.
#
#   2. MULTI-QUERY DECOMPOSITION (free, instant)
#      Comparison and multi-part queries are hard for retrievers. "Compare
#      BOM and NRE costs" is split into ["BOM costs", "NRE costs"] so each
#      sub-topic gets its own retrieval pass.
#
#   3. HyDE -- HYPOTHETICAL DOCUMENT EMBEDDING (optional, uses LLM)
#      Instead of embedding the question, we ask the LLM to write a short
#      paragraph that WOULD answer the question, then embed THAT. The
#      hypothetical document is closer in embedding space to the real
#      documents than the question itself.
#
#      Reference: Gao et al., "Precise Zero-Shot Dense Retrieval without
#      Relevance Labels" (2022). https://arxiv.org/abs/2212.10496
#
# DESIGN DECISIONS:
#
#   1. DICTIONARY-BASED ACRONYMS (not LLM-based)
#      WHY: Zero latency, zero cost, deterministic. An LLM call to expand
#      acronyms would add 2-5 seconds per query for marginal improvement.
#      The dictionary covers the 80/20 of engineering acronyms and can be
#      extended via YAML config or the acronym_file parameter.
#
#   2. RULE-BASED DECOMPOSITION (not LLM-based)
#      WHY: Same reasoning -- regex-based splitting is instant and handles
#      the common patterns (comparisons, conjunctions) reliably. LLM-based
#      decomposition is overkill for a RAG retriever.
#
#   3. HyDE IS OPT-IN (disabled by default)
#      WHY: It requires an LLM call (2-10 seconds on CPU). For interactive
#      use, the latency penalty is too high. Enable it for batch workflows
#      or when retrieval quality matters more than speed.
#
#   4. GRACEFUL DEGRADATION EVERYWHERE
#      WHY: Query expansion should never cause a query to fail. If the
#      acronym file is missing, we use the built-in dict. If HyDE times
#      out, we skip it. The retriever always gets a usable query.
#
# INTERNET ACCESS: NONE
#   All operations are local. HyDE uses the LLMRouter which may call
#   Ollama on localhost -- no outbound network traffic.
# ============================================================================

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class: expanded query result
# ---------------------------------------------------------------------------

@dataclass
class ExpandedQuery:
    """
    Result of query expansion.

    Fields:
      original         -- the raw user query (unchanged)
      expanded_text    -- query with acronyms/synonyms appended
      sub_queries      -- decomposed sub-queries (1-3 items)
      hypothetical     -- HyDE-generated text (None if disabled/failed)
      expansion_applied -- list of tags describing what was applied
                           e.g. ["acronym:TCXO", "decompose:comparison", "hyde"]
    """
    original: str
    expanded_text: str
    sub_queries: List[str]
    hypothetical: Optional[str] = None
    expansion_applied: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in engineering acronym dictionary
# ---------------------------------------------------------------------------

# Common engineering, manufacturing, and IT acronyms. The dict maps
# acronym -> full expansion AND full expansion -> acronym (bidirectional).
# Keep this list under 200 entries to avoid bloating memory.

_DEFAULT_ACRONYMS: Dict[str, str] = {
    # Electronics / RF
    "TCXO": "Temperature Compensated Crystal Oscillator",
    "OCXO": "Oven Controlled Crystal Oscillator",
    "VCXO": "Voltage Controlled Crystal Oscillator",
    "PCB": "Printed Circuit Board",
    "PCBA": "Printed Circuit Board Assembly",
    "FPGA": "Field Programmable Gate Array",
    "ASIC": "Application Specific Integrated Circuit",
    "ADC": "Analog to Digital Converter",
    "DAC": "Digital to Analog Converter",
    "RF": "Radio Frequency",
    "IF": "Intermediate Frequency",
    "LNA": "Low Noise Amplifier",
    "PLL": "Phase Locked Loop",
    "VCO": "Voltage Controlled Oscillator",
    "EMI": "Electromagnetic Interference",
    "EMC": "Electromagnetic Compatibility",
    "ESD": "Electrostatic Discharge",
    "IC": "Integrated Circuit",
    "GPIO": "General Purpose Input Output",
    "SPI": "Serial Peripheral Interface",
    "I2C": "Inter-Integrated Circuit",
    "UART": "Universal Asynchronous Receiver Transmitter",
    "DMA": "Direct Memory Access",
    "DSP": "Digital Signal Processing",
    # Manufacturing / Supply Chain
    "BOM": "Bill of Materials",
    "NRE": "Non-Recurring Engineering",
    "COTS": "Commercial Off The Shelf",
    "MOTS": "Modified Off The Shelf",
    "DFM": "Design for Manufacturing",
    "DFA": "Design for Assembly",
    "DFT": "Design for Test",
    "SMT": "Surface Mount Technology",
    "THT": "Through Hole Technology",
    "ECO": "Engineering Change Order",
    "ECN": "Engineering Change Notice",
    "MRP": "Material Requirements Planning",
    "ERP": "Enterprise Resource Planning",
    "WIP": "Work In Progress",
    "RMA": "Return Merchandise Authorization",
    "QC": "Quality Control",
    "QA": "Quality Assurance",
    # Reliability / Testing
    "MTBF": "Mean Time Between Failures",
    "MTTR": "Mean Time To Repair",
    "MTTF": "Mean Time To Failure",
    "FIT": "Failures In Time",
    "HALT": "Highly Accelerated Life Testing",
    "HASS": "Highly Accelerated Stress Screening",
    "ESS": "Environmental Stress Screening",
    "FMEA": "Failure Mode and Effects Analysis",
    "DVT": "Design Verification Testing",
    "EVT": "Engineering Validation Testing",
    "PVT": "Production Validation Testing",
    "FAT": "Factory Acceptance Test",
    "SAT": "Site Acceptance Test",
    # Systems Engineering
    "SLA": "Service Level Agreement",
    "SLO": "Service Level Objective",
    "SLI": "Service Level Indicator",
    "CDR": "Critical Design Review",
    "PDR": "Preliminary Design Review",
    "SRR": "System Requirements Review",
    "TRR": "Test Readiness Review",
    "FCA": "Functional Configuration Audit",
    "PCA": "Physical Configuration Audit",
    "ICD": "Interface Control Document",
    "SDD": "Software Design Document",
    "SRS": "Software Requirements Specification",
    "CONOPS": "Concept of Operations",
    "TRL": "Technology Readiness Level",
    "MRL": "Manufacturing Readiness Level",
    # IT / Software
    "API": "Application Programming Interface",
    "REST": "Representational State Transfer",
    "SDK": "Software Development Kit",
    "CLI": "Command Line Interface",
    "GUI": "Graphical User Interface",
    "CRUD": "Create Read Update Delete",
    "ORM": "Object Relational Mapping",
    "CI": "Continuous Integration",
    "CD": "Continuous Delivery",
    "SaaS": "Software as a Service",
    "IaaS": "Infrastructure as a Service",
    "PaaS": "Platform as a Service",
    "VM": "Virtual Machine",
    "DNS": "Domain Name System",
    "SSL": "Secure Sockets Layer",
    "TLS": "Transport Layer Security",
    "SSH": "Secure Shell",
    "VPN": "Virtual Private Network",
    "RAG": "Retrieval Augmented Generation",
    "LLM": "Large Language Model",
    "NLP": "Natural Language Processing",
    "ML": "Machine Learning",
    # Mechanical / Thermal
    "CAD": "Computer Aided Design",
    "CAM": "Computer Aided Manufacturing",
    "CAE": "Computer Aided Engineering",
    "FEA": "Finite Element Analysis",
    "CFD": "Computational Fluid Dynamics",
    "CTE": "Coefficient of Thermal Expansion",
    "GD&T": "Geometric Dimensioning and Tolerancing",
    "CMM": "Coordinate Measuring Machine",
}


# ---------------------------------------------------------------------------
# QueryExpander
# ---------------------------------------------------------------------------

class QueryExpander:
    """
    Transform user queries before retrieval to improve search quality.

    Three levels of expansion (layered by cost):
      1. Acronym & synonym expansion (always-on, zero-cost, dictionary)
      2. Multi-query decomposition (always-on, zero-cost, regex rules)
      3. HyDE hypothetical document (opt-in, requires LLM call)

    Usage:
        expander = QueryExpander(config)
        result = expander.expand("TCXO calibration procedure")
        # result.expanded_text -> "TCXO (Temperature Compensated Crystal
        #   Oscillator) calibration procedure"
        # result.sub_queries  -> ["TCXO calibration procedure"]

        # With HyDE:
        expander = QueryExpander(config, llm_router=router)
        result = expander.expand("TCXO calibration", use_hyde=True)
        # result.hypothetical -> "A technical paragraph about TCXO cal..."
    """

    # Maximum acronym expansions per query to prevent runaway expansion
    _MAX_EXPANSIONS = 10

    # HyDE timeout -- if the LLM takes longer, we skip HyDE
    _HYDE_TIMEOUT_SECONDS = 10.0

    def __init__(self, config, llm_router=None):
        """
        Initialize the query expander.

        Parameters
        ----------
        config : Config
            Master configuration object. Reads:
              - config.expansion_enabled (bool, default True via getattr)
              - config.hyde_enabled (bool, default False via getattr)
              - config.acronym_file (str, default "" via getattr)

        llm_router : LLMRouter or None
            If provided, enables HyDE (hypothetical document embedding).
            If None, HyDE is silently disabled.
        """
        self.config = config
        self.llm_router = llm_router

        # Read expansion config with safe defaults (config may not have
        # these fields yet -- we use getattr to avoid AttributeError)
        self.expansion_enabled = bool(
            getattr(config, "expansion_enabled", True)
        )
        self.hyde_enabled = bool(
            getattr(config, "hyde_enabled", False)
        )

        # Build the acronym dictionary
        self._acronyms = self._load_acronyms(config)

        # Build reverse map: "Temperature Compensated Crystal Oscillator" -> "TCXO"
        self._reverse_acronyms: Dict[str, str] = {}
        for acronym, expansion in self._acronyms.items():
            # Store lowercase expansion for case-insensitive matching
            self._reverse_acronyms[expansion.lower()] = acronym

    def _load_acronyms(self, config) -> Dict[str, str]:
        """
        Load the acronym dictionary from built-in defaults + optional file.

        Priority: file entries override built-in entries with the same key.
        File format: YAML dict of acronym -> expansion.

        Example file (acronyms.yaml):
          TCXO: Temperature Compensated Crystal Oscillator
          BOM: Bill of Materials
          CUSTOM_TERM: My Custom Expansion
        """
        # Start with built-in defaults
        acronyms = dict(_DEFAULT_ACRONYMS)

        # Optionally load from a YAML file
        acronym_file = str(getattr(config, "acronym_file", "") or "")
        if acronym_file:
            try:
                import yaml
                import os
                if os.path.isfile(acronym_file):
                    with open(acronym_file, "r", encoding="utf-8") as f:
                        custom = yaml.safe_load(f)
                    if isinstance(custom, dict):
                        acronyms.update(custom)
                        logger.info(
                            "[OK] Loaded %d custom acronyms from %s",
                            len(custom), acronym_file,
                        )
                    else:
                        logger.warning(
                            "[WARN] Acronym file %s is not a YAML dict, ignoring",
                            acronym_file,
                        )
                else:
                    logger.warning(
                        "[WARN] Acronym file not found: %s", acronym_file
                    )
            except Exception as e:
                logger.warning(
                    "[WARN] Failed to load acronym file %s: %s",
                    acronym_file, e,
                )

        return acronyms

    # ------------------------------------------------------------------
    # Feature 1: Acronym & Synonym Expansion
    # ------------------------------------------------------------------

    def expand_keywords(self, query: str) -> str:
        """
        Expand acronyms and abbreviations in the query text.

        How it works:
          1. Tokenize the query into words
          2. For each word, check if it's a known acronym
          3. If found, append " (Full Expansion)" after the acronym
          4. Also check if any full expansion phrase appears in the query
             and append the acronym after it

        Examples:
          "TCXO calibration" -> "TCXO (Temperature Compensated Crystal
            Oscillator) calibration"
          "Printed Circuit Board layout" -> "Printed Circuit Board (PCB) layout"
          "What is the MTBF?" -> "What is the MTBF (Mean Time Between Failures)?"

        Returns the expanded query string. If no expansions apply, returns
        the original query unchanged.
        """
        if not query or not query.strip():
            return query

        expanded = query
        applied_count = 0

        # --- Forward expansion: acronym -> full form ---
        # Use word boundary regex to avoid matching acronyms inside words
        # (e.g., "SPIFFY" should not match "SPI")
        for acronym, full_form in self._acronyms.items():
            if applied_count >= self._MAX_EXPANSIONS:
                break

            # Match the acronym as a standalone word (case-sensitive for
            # acronyms since they are typically uppercase)
            pattern = r'\b' + re.escape(acronym) + r'\b'
            if re.search(pattern, expanded):
                # Check that the expansion is not already present
                if full_form not in expanded:
                    expanded = re.sub(
                        pattern,
                        acronym + " (" + full_form + ")",
                        expanded,
                        count=1,  # Only expand first occurrence
                    )
                    applied_count += 1

        # --- Reverse expansion: full form -> acronym ---
        # Check if any full expansion phrase appears in the query
        query_lower = expanded.lower()
        for full_form_lower, acronym in self._reverse_acronyms.items():
            if applied_count >= self._MAX_EXPANSIONS:
                break

            if full_form_lower in query_lower:
                # Check that the acronym is not already present as a word
                acronym_pattern = r'\b' + re.escape(acronym) + r'\b'
                if not re.search(acronym_pattern, expanded):
                    # Find the actual case version in the original text
                    idx = query_lower.find(full_form_lower)
                    if idx >= 0:
                        end_idx = idx + len(full_form_lower)
                        actual_text = expanded[idx:end_idx]
                        expanded = (
                            expanded[:end_idx]
                            + " (" + acronym + ")"
                            + expanded[end_idx:]
                        )
                        applied_count += 1
                        # Update the lowercase version for subsequent checks
                        query_lower = expanded.lower()

        return expanded

    # ------------------------------------------------------------------
    # Feature 2: Multi-Query Decomposition
    # ------------------------------------------------------------------

    def decompose(self, query: str) -> List[str]:
        """
        Split compound queries into sub-queries for independent retrieval.

        Detects two patterns:

        1. COMPARISON queries:
           "Compare X and Y" -> ["X", "Y"]
           "Difference between X and Y" -> ["X", "Y"]
           "X vs Y" -> ["X", "Y"]

        2. MULTI-PART queries (conjunction splitting):
           "What is X and how does Y work?" -> ["What is X", "how does Y work"]
           "Explain A, B, and C" -> (not split -- list items are one topic)

        Single-topic queries pass through unchanged: ["original query"]

        Returns a list of 1-3 sub-queries. Never returns an empty list.
        """
        if not query or not query.strip():
            return [query] if query else [""]

        query_stripped = query.strip()

        # --- Pattern 1: Comparison queries ---
        # "compare X and Y", "comparison of X and Y"
        compare_match = re.match(
            r'(?:compare|comparison\s+(?:of|between))\s+(.+?)\s+'
            r'(?:and|with|vs\.?|versus)\s+(.+)',
            query_stripped,
            re.IGNORECASE,
        )
        if compare_match:
            part_a = compare_match.group(1).strip().rstrip("?.,")
            part_b = compare_match.group(2).strip().rstrip("?.,")
            if part_a and part_b:
                return [part_a, part_b]

        # "difference(s) between X and Y"
        diff_match = re.match(
            r'(?:what\s+(?:is|are)\s+the\s+)?'
            r'(?:differences?|distinction)\s+between\s+(.+?)\s+'
            r'(?:and|vs\.?|versus)\s+(.+)',
            query_stripped,
            re.IGNORECASE,
        )
        if diff_match:
            part_a = diff_match.group(1).strip().rstrip("?.,")
            part_b = diff_match.group(2).strip().rstrip("?.,")
            if part_a and part_b:
                return [part_a, part_b]

        # "X vs Y" or "X versus Y" (standalone, not inside longer patterns)
        vs_match = re.match(
            r'(.+?)\s+(?:vs\.?|versus)\s+(.+)',
            query_stripped,
            re.IGNORECASE,
        )
        if vs_match:
            part_a = vs_match.group(1).strip().rstrip("?.,")
            part_b = vs_match.group(2).strip().rstrip("?.,")
            if part_a and part_b:
                return [part_a, part_b]

        # --- Pattern 2: Multi-part queries with question-word conjunctions ---
        # "What is X and how does Y work?"
        # Split on " and " only when followed by a question word
        # (what, how, where, when, why, which, who, does, is, are, can, will)
        question_words = (
            r'(?:what|how|where|when|why|which|who|does|is|are|can|will|should)'
        )
        conj_pattern = (
            r'(.+?)\s+and\s+(' + question_words + r'\s+.+)'
        )
        conj_match = re.match(conj_pattern, query_stripped, re.IGNORECASE)
        if conj_match:
            part_a = conj_match.group(1).strip().rstrip("?.,")
            part_b = conj_match.group(2).strip().rstrip("?.,")
            if part_a and part_b and len(part_a) > 5 and len(part_b) > 5:
                return [part_a, part_b]

        # --- No decomposition pattern matched ---
        return [query_stripped]

    # ------------------------------------------------------------------
    # Feature 3: HyDE -- Hypothetical Document Embedding
    # ------------------------------------------------------------------

    def generate_hypothetical(self, query: str) -> Optional[str]:
        """
        Generate a hypothetical document that would answer the query.

        Uses the LLM to write a brief technical paragraph. This text
        is then embedded instead of (or alongside) the raw query for
        retrieval. The hypothetical document is typically closer in
        embedding space to real documents than the question itself.

        Returns None if:
          - llm_router is not available
          - hyde_enabled is False in config
          - LLM call times out (>10 seconds)
          - Any error occurs (graceful degradation)

        The timeout is enforced at the HTTP level by the LLM router,
        not by a Python threading timer. We measure wall-clock time
        and log warnings if it exceeds the threshold.
        """
        if self.llm_router is None:
            logger.debug("HyDE skipped: no LLM router available")
            return None

        if not self.hyde_enabled:
            logger.debug("HyDE skipped: disabled in config")
            return None

        if not query or not query.strip():
            return None

        # Build a short prompt that produces a factual-sounding paragraph.
        # The prompt is designed to produce dense, specific text that
        # embeds close to real technical documents.
        hyde_prompt = (
            "Write a brief technical paragraph (3-5 sentences) that would "
            "directly answer the following question. Use specific technical "
            "details, measurements, and terminology. Do not add disclaimers "
            "or hedging language. Write as if this is an excerpt from an "
            "engineering manual.\n\n"
            "Question: " + query + "\n\n"
            "Answer:"
        )

        start_time = time.time()

        try:
            response = self.llm_router.query(hyde_prompt)
            elapsed_s = time.time() - start_time

            if response is None or not hasattr(response, "text"):
                logger.warning(
                    "[WARN] HyDE: LLM returned None or invalid response"
                )
                return None

            hypothetical = response.text.strip()

            if not hypothetical:
                logger.warning("[WARN] HyDE: LLM returned empty text")
                return None

            if elapsed_s > self._HYDE_TIMEOUT_SECONDS:
                logger.warning(
                    "[WARN] HyDE: LLM call took %.1fs (threshold: %.1fs) "
                    "-- result used but consider disabling HyDE for speed",
                    elapsed_s, self._HYDE_TIMEOUT_SECONDS,
                )
            else:
                logger.info(
                    "[OK] HyDE: generated hypothetical document (%.1fs, %d chars)",
                    elapsed_s, len(hypothetical),
                )

            return hypothetical

        except Exception as e:
            elapsed_s = time.time() - start_time
            logger.warning(
                "[WARN] HyDE failed after %.1fs: %s: %s",
                elapsed_s, type(e).__name__, e,
            )
            return None

    # ------------------------------------------------------------------
    # Feature 4: Combined Expansion
    # ------------------------------------------------------------------

    def expand(self, query: str, use_hyde: bool = False) -> ExpandedQuery:
        """
        Run all applicable query transformations and return a combined result.

        Pipeline:
          1. Acronym expansion (always, unless expansion_enabled=False)
          2. Multi-query decomposition (always, unless expansion_enabled=False)
          3. HyDE hypothetical document (only if use_hyde=True AND enabled)

        Parameters
        ----------
        query : str
            The raw user query.

        use_hyde : bool
            Whether to attempt HyDE generation. Even if True, HyDE will
            be skipped if no llm_router is available or config disables it.

        Returns
        -------
        ExpandedQuery
            Combined result with all transformations applied.
        """
        applied: List[str] = []

        # --- Step 1: Acronym expansion ---
        if self.expansion_enabled:
            expanded_text = self.expand_keywords(query)
            # Track which acronyms were expanded
            if expanded_text != query:
                # Find which acronyms were involved
                for acronym in self._acronyms:
                    pattern = r'\b' + re.escape(acronym) + r'\b'
                    if (re.search(pattern, expanded_text)
                            and re.search(pattern, query)):
                        # Check if the expansion was added
                        full_form = self._acronyms[acronym]
                        if full_form in expanded_text and full_form not in query:
                            applied.append("acronym:" + acronym)
                # Also check reverse expansions
                for full_lower, acronym in self._reverse_acronyms.items():
                    if (full_lower in query.lower()
                            and "(" + acronym + ")" in expanded_text
                            and "(" + acronym + ")" not in query):
                        applied.append("reverse:" + acronym)
        else:
            expanded_text = query

        # --- Step 2: Decomposition ---
        if self.expansion_enabled:
            sub_queries = self.decompose(query)
            if len(sub_queries) > 1:
                # Determine decomposition type for the tag
                query_lower = query.lower()
                if any(kw in query_lower for kw in
                       ["compare", "comparison", "difference", "vs", "versus"]):
                    applied.append("decompose:comparison")
                else:
                    applied.append("decompose:conjunction")
        else:
            sub_queries = [query]

        # --- Step 3: HyDE ---
        hypothetical = None
        if use_hyde:
            hypothetical = self.generate_hypothetical(query)
            if hypothetical is not None:
                applied.append("hyde")

        return ExpandedQuery(
            original=query,
            expanded_text=expanded_text,
            sub_queries=sub_queries,
            hypothetical=hypothetical,
            expansion_applied=applied,
        )

    # ------------------------------------------------------------------
    # Utility: direct acronym dict access (for testing / GUI)
    # ------------------------------------------------------------------

    @property
    def acronym_count(self) -> int:
        """Number of acronyms in the active dictionary."""
        return len(self._acronyms)

    def get_acronym(self, key: str) -> Optional[str]:
        """Look up an acronym or full form. Returns None if not found."""
        if key in self._acronyms:
            return self._acronyms[key]
        key_lower = key.lower()
        if key_lower in self._reverse_acronyms:
            return self._reverse_acronyms[key_lower]
        return None

    def add_acronym(self, acronym: str, expansion: str) -> None:
        """
        Add a custom acronym at runtime.

        This does NOT persist to disk -- it only affects the current session.
        Use the acronym_file config for persistent additions.
        """
        self._acronyms[acronym] = expansion
        self._reverse_acronyms[expansion.lower()] = acronym
