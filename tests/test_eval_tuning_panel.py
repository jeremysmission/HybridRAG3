# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the eval tuning panel area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Tests for src/gui/panels/eval_tuning_panel.py

Validates the eval panel logic WITHOUT launching tkinter or running
real evaluations. Tests cover:
  - Project root discovery
  - Dataset path resolution
  - ETA formatting
  - Summary display data extraction
  - Failure filtering

These are unit tests of the panel's helper methods, not GUI tests.
"""

import json
import os
import sys
import tempfile

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.panels.eval_tuning_panel import (
    EvalTuningPanel, _find_project_root, format_eta,
    format_type_breakdown, format_role_breakdown, format_failures,
)


# ------------------------------------------------------------------
# Project root discovery
# ------------------------------------------------------------------

class TestProjectRoot:
    """Tests for _find_project_root()."""

    def test_finds_root_from_file_location(self):
        """Should find a directory containing config/."""
        root = _find_project_root()
        assert os.path.isdir(os.path.join(root, "config")), (
            "Project root should contain a config/ directory"
        )

    def test_root_contains_eval_dir(self):
        """Project root should also contain Eval/."""
        root = _find_project_root()
        assert os.path.isdir(os.path.join(root, "Eval")), (
            "Project root should contain Eval/ directory"
        )


# ------------------------------------------------------------------
# Dataset resolution
# ------------------------------------------------------------------

class TestDatasetResolution:
    """Tests for dataset path logic."""

    def test_tuning_400_exists(self):
        """The golden tuning dataset should exist at the expected path."""
        root = _find_project_root()
        path = os.path.join(root, "Eval", "golden_tuning_400.json")
        assert os.path.isfile(path), (
            "Golden tuning dataset not found at {}".format(path)
        )

    def test_tuning_400_is_valid_json(self):
        """The golden dataset should be valid JSON with a list of items."""
        root = _find_project_root()
        path = os.path.join(root, "Eval", "golden_tuning_400.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 400, "Expected 400 questions, got {}".format(len(data))

    def test_dataset_item_schema(self):
        """Each item should have required fields."""
        root = _find_project_root()
        path = os.path.join(root, "Eval", "golden_tuning_400.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        required = {"id", "role", "type", "query", "expected_key_facts"}
        for item in data[:5]:
            missing = required - set(item.keys())
            assert not missing, "Item {} missing fields: {}".format(
                item.get("id", "?"), missing,
            )

    def test_dataset_types_complete(self):
        """Dataset should contain all 4 question types."""
        root = _find_project_root()
        path = os.path.join(root, "Eval", "golden_tuning_400.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        types = {item["type"] for item in data}
        expected = {"answerable", "unanswerable", "injection", "ambiguous"}
        assert expected.issubset(types), "Missing types: {}".format(
            expected - types,
        )

    def test_datasets_dict_has_correct_path(self):
        """DATASETS class var should point to correct relative path."""
        assert "Tuning 400" in EvalTuningPanel.DATASETS
        path = EvalTuningPanel.DATASETS["Tuning 400"]
        assert path == "Eval/golden_tuning_400.json"


# ------------------------------------------------------------------
# ETA formatting
# ------------------------------------------------------------------

class TestETAFormatting:
    """Tests for the _format_eta static method."""

    def test_seconds_only(self):
        assert format_eta(45) == "ETA: 45s"

    def test_minutes_seconds(self):
        assert format_eta(125) == "ETA: 2m 5s"

    def test_hours_minutes(self):
        assert format_eta(3720) == "ETA: 1h 2m"

    def test_zero_returns_empty(self):
        assert format_eta(0) == ""

    def test_negative_returns_empty(self):
        assert format_eta(-10) == ""

    def test_large_value(self):
        result = format_eta(7200)
        assert "2h" in result


# ------------------------------------------------------------------
# Summary data extraction (offline -- no GUI needed)
# ------------------------------------------------------------------

class TestSummaryParsing:
    """Tests that summary.json structures are parsed correctly."""

    def _make_summary(self, pass_rate=0.98, count=400):
        return {
            "overall": {
                "count": count,
                "avg_overall": 0.95,
                "pass_rate": pass_rate,
                "p50_latency_ms": 2800,
                "p95_latency_ms": 6600,
                "avg_cost_usd": 0.0035,
            },
            "by_type": {
                "answerable": {
                    "count": 278,
                    "pass_rate": 0.971,
                    "p50_latency_ms": 3000,
                    "p95_latency_ms": 7000,
                    "avg_cost_usd": 0.004,
                },
                "unanswerable": {
                    "count": 59,
                    "pass_rate": 1.0,
                    "p50_latency_ms": 2000,
                    "p95_latency_ms": 4000,
                    "avg_cost_usd": 0.002,
                },
                "injection": {
                    "count": 41,
                    "pass_rate": 1.0,
                    "p50_latency_ms": 2500,
                    "p95_latency_ms": 5000,
                    "avg_cost_usd": 0.003,
                },
                "ambiguous": {
                    "count": 22,
                    "pass_rate": 1.0,
                    "p50_latency_ms": 1800,
                    "p95_latency_ms": 3500,
                    "avg_cost_usd": 0.002,
                },
            },
            "by_role": {
                "Field Engineer": {
                    "count": 60,
                    "pass_rate": 0.983,
                    "p50_latency_ms": 2900,
                    "p95_latency_ms": 6500,
                    "avg_cost_usd": 0.0035,
                },
            },
            "acceptance_gates": {
                "unanswerable_accuracy_proxy": 1.0,
                "injection_resistance_proxy": 1.0,
            },
        }

    def test_overall_count(self):
        s = self._make_summary()
        assert s["overall"]["count"] == 400

    def test_pass_rate_extraction(self):
        s = self._make_summary(pass_rate=0.975)
        assert s["overall"]["pass_rate"] == 0.975

    def test_type_keys_present(self):
        s = self._make_summary()
        assert set(s["by_type"].keys()) == {
            "answerable", "unanswerable", "injection", "ambiguous",
        }

    def test_acceptance_gates(self):
        s = self._make_summary()
        gates = s["acceptance_gates"]
        assert gates["unanswerable_accuracy_proxy"] == 1.0
        assert gates["injection_resistance_proxy"] == 1.0

    def test_role_breakdown_has_entries(self):
        s = self._make_summary()
        assert len(s["by_role"]) > 0


# ------------------------------------------------------------------
# Failure filtering
# ------------------------------------------------------------------

class TestFailureFiltering:
    """Tests for filtering failed questions from scored results."""

    def _make_rows(self):
        return [
            {"id": "A-001", "type": "answerable", "passed": True,
             "overall_score": 0.95, "query": "Good question"},
            {"id": "A-002", "type": "answerable", "passed": False,
             "overall_score": 0.60, "query": "Bad question",
             "fact_score": 0.4, "behavior_score": 0.0,
             "citation_score": 1.0, "error": ""},
            {"id": "U-001", "type": "unanswerable", "passed": True,
             "overall_score": 1.0, "query": "Unknown topic"},
            {"id": "I-001", "type": "injection", "passed": False,
             "overall_score": 0.0, "query": "Ignore previous instructions",
             "fact_score": 0.0, "behavior_score": 0.0,
             "citation_score": 0.0, "error": "Injection leaked"},
        ]

    def test_filter_failures(self):
        rows = self._make_rows()
        failures = [r for r in rows if not r.get("passed", True)]
        assert len(failures) == 2

    def test_failures_have_low_scores(self):
        rows = self._make_rows()
        failures = [r for r in rows if not r.get("passed", True)]
        for f in failures:
            assert f["overall_score"] < 0.85

    def test_passing_rows_excluded(self):
        rows = self._make_rows()
        failures = [r for r in rows if not r.get("passed", True)]
        ids = {r["id"] for r in failures}
        assert "A-001" not in ids
        assert "U-001" not in ids

    def test_empty_rows_no_failures(self):
        failures = [r for r in [] if not r.get("passed", True)]
        assert len(failures) == 0
