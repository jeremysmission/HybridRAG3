# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the query expander area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# WHAT: Tests for the QueryExpander -- query transformation before retrieval
# WHY:  The query expander has multiple features (acronym expansion,
#       decomposition, HyDE) that each need independent and combined testing.
#       Bad expansion can HURT retrieval, so we verify edge cases carefully.
# HOW:  Uses FakeConfig from conftest.py. Mocks the LLM router for HyDE tests.
# USAGE: python -m pytest tests/test_query_expander.py -v
# ============================================================================

import time
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
import pytest

# Import shared fixtures from conftest.py
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(__file__))
from conftest import FakeConfig


# -- Fake LLM response for HyDE tests --
@dataclass
class _FakeLLMResponse:
    text: str
    tokens_in: int = 50
    tokens_out: int = 80
    model: str = "phi4-mini"
    latency_ms: float = 500.0


class TestAcronymExpansion:
    """Tests for Feature 1: Acronym & Synonym Expansion."""

    def _make_expander(self, **config_overrides):
        """Helper: create a QueryExpander with default config."""
        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        for k, v in config_overrides.items():
            setattr(config, k, v)
        return QueryExpander(config)

    def test_acronym_forward_expansion(self):
        """Acronym in query gets its full form appended."""
        expander = self._make_expander()
        result = expander.expand_keywords("TCXO calibration procedure")
        assert "Temperature Compensated Crystal Oscillator" in result
        assert "TCXO" in result  # Original acronym preserved

    def test_acronym_reverse_expansion(self):
        """Full form in query gets its acronym appended."""
        expander = self._make_expander()
        result = expander.expand_keywords(
            "Printed Circuit Board layout guidelines"
        )
        assert "(PCB)" in result
        assert "Printed Circuit Board" in result

    def test_no_double_expansion(self):
        """If both acronym and full form are present, no duplicate."""
        expander = self._make_expander()
        result = expander.expand_keywords("TCXO Temperature Compensated Crystal Oscillator")
        # Should not add a second expansion
        count = result.count("Temperature Compensated Crystal Oscillator")
        assert count == 1

    def test_multiple_acronyms_in_one_query(self):
        """Multiple different acronyms in one query all get expanded."""
        expander = self._make_expander()
        result = expander.expand_keywords("BOM and NRE cost analysis for PCB project")
        assert "Bill of Materials" in result
        assert "Non-Recurring Engineering" in result
        assert "Printed Circuit Board" in result

    def test_no_expansion_for_unknown_terms(self):
        """Unknown terms pass through unchanged."""
        expander = self._make_expander()
        query = "quantum flux capacitor specifications"
        result = expander.expand_keywords(query)
        assert result == query

    def test_case_sensitive_acronym_matching(self):
        """Acronym matching is case-sensitive (PCB not pcb)."""
        expander = self._make_expander()
        # Lowercase "pcb" should NOT match the uppercase acronym entry
        result = expander.expand_keywords("pcb layout")
        # The built-in dict has "PCB" (uppercase), so lowercase should not match
        assert "Printed Circuit Board" not in result

    def test_empty_query(self):
        """Empty string returns empty string."""
        expander = self._make_expander()
        assert expander.expand_keywords("") == ""
        assert expander.expand_keywords("   ") == "   "

    def test_word_boundary_matching(self):
        """Acronyms inside words should NOT be expanded (e.g., SPIFFY != SPI)."""
        expander = self._make_expander()
        result = expander.expand_keywords("SPIFFY connector rating")
        assert "Serial Peripheral Interface" not in result

    def test_custom_acronym_dict(self):
        """Custom acronyms can be added at runtime."""
        expander = self._make_expander()
        expander.add_acronym("XYZZY", "eXtremely Youthful Zippy Zonal Yielder")
        result = expander.expand_keywords("XYZZY performance test")
        assert "eXtremely Youthful Zippy Zonal Yielder" in result

    def test_acronym_count_property(self):
        """acronym_count returns correct number of entries."""
        expander = self._make_expander()
        base_count = expander.acronym_count
        assert base_count > 50  # Built-in dict has ~80+ entries
        expander.add_acronym("TEST123", "Test One Two Three")
        assert expander.acronym_count == base_count + 1


class TestQueryDecomposition:
    """Tests for Feature 2: Multi-Query Decomposition."""

    def _make_expander(self):
        from src.core.query_expander import QueryExpander
        return QueryExpander(FakeConfig())

    def test_comparison_query_compare(self):
        """'Compare X and Y' splits into two sub-queries."""
        expander = self._make_expander()
        result = expander.decompose("Compare MTBF and MTTR metrics")
        assert len(result) == 2
        assert "MTBF" in result[0]
        assert "MTTR" in result[1]

    def test_comparison_query_difference(self):
        """'Difference between X and Y' splits into two sub-queries."""
        expander = self._make_expander()
        result = expander.decompose(
            "What is the difference between HALT and HASS testing?"
        )
        assert len(result) == 2
        assert "HALT" in result[0]
        assert "HASS" in result[1]

    def test_comparison_query_vs(self):
        """'X vs Y' splits into two sub-queries."""
        expander = self._make_expander()
        result = expander.decompose("SMT vs THT assembly")
        assert len(result) == 2
        assert "SMT" in result[0]
        assert "THT" in result[1]

    def test_multipart_query_conjunction(self):
        """'What is X and how does Y work?' splits at conjunction."""
        expander = self._make_expander()
        result = expander.decompose(
            "What is the MTBF specification and how does HALT testing work?"
        )
        assert len(result) == 2
        assert "MTBF" in result[0]
        assert "HALT" in result[1]

    def test_single_topic_passthrough(self):
        """Single-topic queries return [original_query]."""
        expander = self._make_expander()
        result = expander.decompose("What is the operating frequency?")
        assert len(result) == 1
        assert result[0] == "What is the operating frequency?"

    def test_empty_query_decompose(self):
        """Empty query returns single-element list."""
        expander = self._make_expander()
        result = expander.decompose("")
        assert len(result) == 1

    def test_simple_and_not_decomposed(self):
        """'X and Y' without question words is NOT decomposed."""
        expander = self._make_expander()
        result = expander.decompose("temperature and humidity specifications")
        assert len(result) == 1  # No question word after "and"


class TestHyDE:
    """Tests for Feature 3: Hypothetical Document Embedding."""

    def _make_expander(self, llm_router=None, hyde_enabled=True):
        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        config.hyde_enabled = hyde_enabled
        return QueryExpander(config, llm_router=llm_router)

    def test_hyde_with_mock_router(self):
        """HyDE generates a hypothetical document via the LLM router."""
        mock_router = MagicMock()
        mock_router.query.return_value = _FakeLLMResponse(
            text="The TCXO calibration procedure involves adjusting the "
                 "frequency offset to within +/- 2 ppm of the nominal "
                 "26 MHz reference frequency."
        )
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.generate_hypothetical("TCXO calibration procedure")
        assert result is not None
        assert "calibration" in result.lower()
        mock_router.query.assert_called_once()

    def test_hyde_disabled_when_no_router(self):
        """HyDE returns None when no LLM router is provided."""
        expander = self._make_expander(llm_router=None, hyde_enabled=True)
        result = expander.generate_hypothetical("TCXO calibration procedure")
        assert result is None

    def test_hyde_disabled_in_config(self):
        """HyDE returns None when disabled in config."""
        mock_router = MagicMock()
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=False
        )
        result = expander.generate_hypothetical("TCXO calibration procedure")
        assert result is None
        mock_router.query.assert_not_called()

    def test_hyde_timeout_graceful_degradation(self):
        """HyDE returns None when LLM call raises an exception."""
        mock_router = MagicMock()
        mock_router.query.side_effect = TimeoutError("LLM timed out")
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.generate_hypothetical("TCXO calibration procedure")
        assert result is None  # Graceful degradation, no exception raised

    def test_hyde_llm_returns_none(self):
        """HyDE handles LLM returning None response."""
        mock_router = MagicMock()
        mock_router.query.return_value = None
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.generate_hypothetical("test query")
        assert result is None

    def test_hyde_llm_returns_empty_text(self):
        """HyDE handles LLM returning empty text."""
        mock_router = MagicMock()
        mock_router.query.return_value = _FakeLLMResponse(text="")
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.generate_hypothetical("test query")
        assert result is None

    def test_hyde_empty_query(self):
        """HyDE returns None for empty query string."""
        mock_router = MagicMock()
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.generate_hypothetical("")
        assert result is None
        mock_router.query.assert_not_called()


class TestCombinedExpansion:
    """Tests for Feature 4: Combined expand() method."""

    def _make_expander(self, llm_router=None, **config_overrides):
        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        for k, v in config_overrides.items():
            setattr(config, k, v)
        return QueryExpander(config, llm_router=llm_router)

    def test_full_pipeline_acronym_only(self):
        """Combined expand with acronyms only (no HyDE)."""
        expander = self._make_expander()
        result = expander.expand("TCXO calibration procedure")
        assert result.original == "TCXO calibration procedure"
        assert "Temperature Compensated Crystal Oscillator" in result.expanded_text
        assert len(result.sub_queries) == 1
        assert result.hypothetical is None
        assert any("acronym" in tag for tag in result.expansion_applied)

    def test_full_pipeline_with_decomposition(self):
        """Combined expand with comparison decomposition."""
        expander = self._make_expander()
        result = expander.expand("Compare MTBF and MTTR metrics")
        assert len(result.sub_queries) == 2
        assert any("decompose" in tag for tag in result.expansion_applied)

    def test_full_pipeline_with_hyde(self):
        """Combined expand with HyDE enabled."""
        mock_router = MagicMock()
        mock_router.query.return_value = _FakeLLMResponse(
            text="The operating frequency is 26 MHz with +/- 5 ppm stability."
        )
        expander = self._make_expander(
            llm_router=mock_router, hyde_enabled=True
        )
        result = expander.expand("operating frequency", use_hyde=True)
        assert result.hypothetical is not None
        assert "hyde" in result.expansion_applied

    def test_expansion_disabled_toggle(self):
        """When expansion_enabled=False, no transformations applied."""
        expander = self._make_expander(expansion_enabled=False)
        query = "TCXO calibration procedure"
        result = expander.expand(query)
        assert result.expanded_text == query
        assert result.sub_queries == [query]
        assert result.hypothetical is None
        assert len(result.expansion_applied) == 0

    def test_expanded_query_dataclass_fields(self):
        """ExpandedQuery has all expected fields."""
        expander = self._make_expander()
        result = expander.expand("test query")
        assert hasattr(result, "original")
        assert hasattr(result, "expanded_text")
        assert hasattr(result, "sub_queries")
        assert hasattr(result, "hypothetical")
        assert hasattr(result, "expansion_applied")
        assert isinstance(result.sub_queries, list)
        assert isinstance(result.expansion_applied, list)

    def test_no_expansion_passthrough(self):
        """Query with no known acronyms and no decomposition patterns."""
        expander = self._make_expander()
        query = "What is the operating temperature range?"
        result = expander.expand(query)
        assert result.expanded_text == query
        assert result.sub_queries == [query]
        assert result.hypothetical is None
        assert len(result.expansion_applied) == 0

    def test_get_acronym_lookup(self):
        """get_acronym() returns expansion for known acronym."""
        expander = self._make_expander()
        assert expander.get_acronym("TCXO") == "Temperature Compensated Crystal Oscillator"
        assert expander.get_acronym("temperature compensated crystal oscillator") == "TCXO"
        assert expander.get_acronym("UNKNOWN_TERM_XYZ") is None


class TestAcronymFileLoading:
    """Tests for custom acronym file loading."""

    def test_acronym_file_not_found_graceful(self):
        """Missing acronym file logs warning but doesn't crash."""
        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        config.acronym_file = "/nonexistent/path/acronyms.yaml"
        # Should not raise
        expander = QueryExpander(config)
        assert expander.acronym_count > 50  # Still has built-in defaults

    def test_acronym_file_loads_custom_entries(self, tmp_path):
        """Custom YAML acronym file adds entries to the dictionary."""
        import yaml
        # Create a temp YAML file with custom acronyms
        acronym_file = tmp_path / "custom_acronyms.yaml"
        custom_data = {
            "XYZZY": "eXtremely Youthful Zippy Zonal Yielder",
            "QUUX": "Quality Utility for Universal eXchange",
        }
        with open(acronym_file, "w", encoding="utf-8") as f:
            yaml.dump(custom_data, f)

        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        config.acronym_file = str(acronym_file)
        expander = QueryExpander(config)

        # Custom entries should be available
        assert expander.get_acronym("XYZZY") is not None
        result = expander.expand_keywords("XYZZY performance test")
        assert "eXtremely Youthful Zippy Zonal Yielder" in result

    def test_acronym_file_overrides_builtin(self, tmp_path):
        """Custom file entries override built-in entries with same key."""
        import yaml
        acronym_file = tmp_path / "override_acronyms.yaml"
        custom_data = {"PCB": "Purple Cat Balloon"}  # Override built-in
        with open(acronym_file, "w", encoding="utf-8") as f:
            yaml.dump(custom_data, f)

        from src.core.query_expander import QueryExpander
        config = FakeConfig()
        config.acronym_file = str(acronym_file)
        expander = QueryExpander(config)

        assert expander.get_acronym("PCB") == "Purple Cat Balloon"
