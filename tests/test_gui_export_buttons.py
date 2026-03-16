"""Tests for GUI export buttons (Excel and PowerPoint) in QueryPanel.

Sprint 15.5 -- GUI Export Test Coverage.

Verifies that:
  - Export buttons are disabled until results exist
  - record_result() populates _result_history and enables buttons
  - _on_export_excel / _on_export_pptx produce valid files when path is provided
  - Empty history shows info dialog instead of file dialog
  - Locked/failed writes show error dialog instead of crashing
"""

import sys
import os
import time
import tkinter as tk
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# FAKE CONFIG (mirrors test_gui_integration_w4 pattern)
# ============================================================================

@dataclass
class FakePathsConfig:
    database: str = ""
    embeddings_cache: str = ""
    source_folder: str = ""

@dataclass
class FakeOllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "phi4-mini"
    timeout_seconds: int = 180
    context_window: int = 4096
    num_predict: int = 384
    temperature: float = 0.05
    top_p: float = 0.90
    seed: int = 0

@dataclass
class FakeAPIConfig:
    endpoint: str = ""
    model: str = "gpt-4o"
    context_window: int = 128000
    max_tokens: int = 1024
    temperature: float = 0.05
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    seed: int = 0
    timeout_seconds: int = 180
    deployment: str = ""
    api_version: str = ""
    allowed_endpoint_prefixes: list = field(default_factory=list)

@dataclass
class FakeRetrievalConfig:
    top_k: int = 4
    min_score: float = 0.10
    hybrid_search: bool = True
    reranker_enabled: bool = False
    reranker_model: str = ""
    reranker_top_n: int = 20
    rrf_k: int = 60
    block_rows: int = 25000
    lex_boost: float = 0.06
    min_chunks: int = 1

@dataclass
class FakeCostConfig:
    input_cost_per_1k: float = 0.0015
    output_cost_per_1k: float = 0.002
    track_enabled: bool = True
    daily_budget_usd: float = 5.0

@dataclass
class FakeChunkingConfig:
    chunk_size: int = 1200
    overlap: int = 200
    max_heading_len: int = 160

@dataclass
class FakeQueryConfig:
    grounding_bias: int = 8
    allow_open_knowledge: bool = True

@dataclass
class FakeGUIConfig:
    mode: str = "offline"
    paths: FakePathsConfig = field(default_factory=FakePathsConfig)
    ollama: FakeOllamaConfig = field(default_factory=FakeOllamaConfig)
    api: FakeAPIConfig = field(default_factory=FakeAPIConfig)
    retrieval: FakeRetrievalConfig = field(default_factory=FakeRetrievalConfig)
    query: FakeQueryConfig = field(default_factory=FakeQueryConfig)
    cost: FakeCostConfig = field(default_factory=FakeCostConfig)
    chunking: FakeChunkingConfig = field(default_factory=FakeChunkingConfig)

@dataclass
class FakeQueryResult:
    answer: str = "Test answer"
    sources: list = field(default_factory=list)
    chunks_used: int = 3
    tokens_in: int = 450
    tokens_out: int = 120
    cost_usd: float = 0.001
    latency_ms: float = 1234.0
    mode: str = "offline"
    error: str = ""
    debug_trace: Optional[dict] = None


# ============================================================================
# HELPERS
# ============================================================================

def _make_root():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable")
    return root


def _pump_events(root, ms=50):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            break
        time.sleep(0.005)


def _make_panel(root, config=None):
    from src.gui.panels.query_panel import QueryPanel
    config = config or FakeGUIConfig()
    panel = QueryPanel(root, config=config)
    panel.pack()
    _pump_events(root, 30)
    return panel


def _add_sample_result(panel):
    """Add one result to panel._result_history via record_result."""
    result = FakeQueryResult(
        answer="The frequency range is 0.5 - 30 MHz.",
        sources=[{"path": "Manual.pdf", "chunks": 3, "avg_relevance": 0.89}],
        chunks_used=5,
        latency_ms=2300,
        mode="offline",
    )
    panel.record_result("What is the frequency range?", result)
    return result


# ============================================================================
# TESTS
# ============================================================================

class TestExportButtonState:
    """Verify button enable/disable lifecycle."""

    def test_buttons_disabled_on_init(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            assert str(panel._export_excel_btn["state"]) == "disabled"
            assert str(panel._export_pptx_btn["state"]) == "disabled"
        finally:
            root.destroy()

    def test_buttons_enabled_after_record_result(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            _pump_events(root, 30)
            assert str(panel._export_excel_btn["state"]) == "normal"
            assert str(panel._export_pptx_btn["state"]) == "normal"
        finally:
            root.destroy()

    def test_count_label_updates(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            text = panel._export_count_label.cget("text")
            assert "1 result" in text
            _add_sample_result(panel)
            text = panel._export_count_label.cget("text")
            assert "2 results" in text
        finally:
            root.destroy()

    def test_result_history_grows(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            assert len(panel._result_history) == 0
            _add_sample_result(panel)
            assert len(panel._result_history) == 1
            _add_sample_result(panel)
            assert len(panel._result_history) == 2
        finally:
            root.destroy()


class TestExportExcel:
    """Verify _on_export_excel behavior."""

    def test_empty_history_shows_info(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                panel._on_export_excel()
                mock_mb.showinfo.assert_called_once()
                assert "No query results" in str(mock_mb.showinfo.call_args)
        finally:
            root.destroy()

    def test_cancel_dialog_does_nothing(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            with patch("tkinter.filedialog.asksaveasfilename", return_value=""):
                with patch("src.tools.report_generator.generate_excel_report") as mock_gen:
                    panel._on_export_excel()
                    mock_gen.assert_not_called()
        finally:
            root.destroy()

    def test_generates_excel_file(self, tmp_path):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            out = str(tmp_path / "test_export.xlsx")
            with patch("tkinter.filedialog.asksaveasfilename", return_value=out):
                with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                    panel._on_export_excel()
                    mock_mb.showinfo.assert_called_once()
                    assert "Export Complete" in str(mock_mb.showinfo.call_args)
            assert Path(out).exists()
            assert Path(out).stat().st_size > 0
        finally:
            root.destroy()

    def test_write_failure_shows_error(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            with patch("tkinter.filedialog.asksaveasfilename", return_value="/bad/path/report.xlsx"):
                with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                    panel._on_export_excel()
                    mock_mb.showerror.assert_called_once()
        finally:
            root.destroy()


class TestExportPptx:
    """Verify _on_export_pptx behavior."""

    def test_empty_history_shows_info(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                panel._on_export_pptx()
                mock_mb.showinfo.assert_called_once()
                assert "No query results" in str(mock_mb.showinfo.call_args)
        finally:
            root.destroy()

    def test_cancel_dialog_does_nothing(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            with patch("tkinter.filedialog.asksaveasfilename", return_value=""):
                with patch("src.tools.report_generator.generate_pptx_report") as mock_gen:
                    panel._on_export_pptx()
                    mock_gen.assert_not_called()
        finally:
            root.destroy()

    def test_generates_pptx_file(self, tmp_path):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            out = str(tmp_path / "test_export.pptx")
            with patch("tkinter.filedialog.asksaveasfilename", return_value=out):
                with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                    panel._on_export_pptx()
                    mock_mb.showinfo.assert_called_once()
                    assert "Export Complete" in str(mock_mb.showinfo.call_args)
            assert Path(out).exists()
            assert Path(out).stat().st_size > 0
        finally:
            root.destroy()

    def test_write_failure_shows_error(self):
        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            with patch("tkinter.filedialog.asksaveasfilename", return_value="/bad/path/report.pptx"):
                with patch("src.gui.panels.query_panel.messagebox") as mock_mb:
                    panel._on_export_pptx()
                    mock_mb.showerror.assert_called_once()
        finally:
            root.destroy()

    def test_pptx_has_correct_slide_count(self, tmp_path):
        from pptx import Presentation

        root = _make_root()
        try:
            panel = _make_panel(root)
            _add_sample_result(panel)
            _add_sample_result(panel)
            out = str(tmp_path / "slides.pptx")
            with patch("tkinter.filedialog.asksaveasfilename", return_value=out):
                with patch("src.gui.panels.query_panel.messagebox"):
                    panel._on_export_pptx()
            prs = Presentation(out)
            # Title + 2 query slides + summary = 4
            assert len(prs.slides) == 4
        finally:
            root.destroy()
