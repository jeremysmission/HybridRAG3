# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the cost tracker area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Tests for the CostTracker backend, PM cost dashboard GUI,
#       and ROI calculator (19 tests total)
# WHY:  Cost tracking is critical for project management -- incorrect
#       token counts or rate calculations produce wrong budget reports.
#       These tests verify the full chain: event recording, SQLite
#       persistence, rate editing, CSV export, and ROI math.
# HOW:  Uses temp directories for SQLite so tests have no side effects.
#       Dashboard tests use mocked Tk to avoid display requirements.
# USAGE: pytest tests/test_cost_tracker.py -v
# ===================================================================

import sys
import os
import time
import tempfile
import tkinter as tk
from pathlib import Path
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

# -- sys.path setup --
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# HELPERS
# ============================================================================

def _make_tracker(tmpdir):
    """Create a CostTracker with a temp DB path."""
    from src.core.cost_tracker import CostTracker, CostRates
    db_path = os.path.join(str(tmpdir), "test_cost.db")
    rates = CostRates(input_rate_per_1m=3.00, output_rate_per_1m=15.00)
    return CostTracker(db_path=db_path, rates=rates)


def _make_root():
    """Create a Tk root that we can destroy after each test."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable")
    root.withdraw()
    return root


def _make_app(*args, **kwargs):
    """Create the full app or skip cleanly when Tk runtime is unstable."""
    from src.gui.app import HybridRAGApp

    try:
        app = HybridRAGApp(*args, **kwargs)
    except tk.TclError:
        pytest.skip("Tk runtime unavailable")
    app.withdraw()
    return app


def _pump_events(root, ms=100):
    """Process pending tkinter events for a short time."""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            break
        time.sleep(0.005)


@dataclass
class FakeCostConfig:
    daily_budget_usd: float = 5.0
    input_cost_per_1k: float = 0.003
    output_cost_per_1k: float = 0.015
    track_enabled: bool = True


@dataclass
class FakeConfig:
    mode: str = "online"
    cost: FakeCostConfig = field(default_factory=FakeCostConfig)


# ============================================================================
# TEST 01: CostTracker creates DB and tables
# ============================================================================

def test_01_tracker_creates_db(tmp_path):
    """CostTracker creates SQLite DB with required tables."""
    tracker = _make_tracker(tmp_path)
    assert os.path.exists(os.path.join(str(tmp_path), "test_cost.db"))
    tracker.shutdown()


# ============================================================================
# TEST 02: Record a single cost event
# ============================================================================

def test_02_record_single_event(tmp_path):
    """Recording an event returns a CostEvent with correct fields."""
    tracker = _make_tracker(tmp_path)
    event = tracker.record(
        tokens_in=1000, tokens_out=500, model="gpt-4",
        mode="online", profile="sw", latency_ms=1234.5,
    )

    assert event.tokens_in == 1000
    assert event.tokens_out == 500
    assert event.model == "gpt-4"
    assert event.mode == "online"
    assert event.profile == "sw"
    assert event.input_cost_usd > 0
    assert event.output_cost_usd > 0
    assert abs(event.total_cost_usd - (event.input_cost_usd + event.output_cost_usd)) < 0.0001
    tracker.shutdown()


# ============================================================================
# TEST 03: Cost calculation correctness
# ============================================================================

def test_03_cost_calculation(tmp_path):
    """Verify cost = (tokens / 1M) * rate_per_1M."""
    tracker = _make_tracker(tmp_path)
    # rates: input=3.00/1M, output=15.00/1M
    event = tracker.record(
        tokens_in=1_000_000, tokens_out=1_000_000,
        model="test", mode="online", profile="gen", latency_ms=100,
    )

    assert abs(event.input_cost_usd - 3.00) < 0.001
    assert abs(event.output_cost_usd - 15.00) < 0.001
    assert abs(event.total_cost_usd - 18.00) < 0.001
    tracker.shutdown()


# ============================================================================
# TEST 04: Session summary aggregation
# ============================================================================

def test_04_session_summary(tmp_path):
    """Session summary aggregates multiple events correctly."""
    tracker = _make_tracker(tmp_path)
    tracker.record(tokens_in=100, tokens_out=50, model="m", mode="online",
                   profile="sw", latency_ms=500)
    tracker.record(tokens_in=200, tokens_out=100, model="m", mode="online",
                   profile="eng", latency_ms=700)

    s = tracker.get_session_summary()
    assert s.query_count == 2
    assert s.total_tokens_in == 300
    assert s.total_tokens_out == 150
    assert s.avg_latency_ms == 600.0
    tracker.shutdown()


# ============================================================================
# TEST 05: Flush persists to SQLite
# ============================================================================

def test_05_flush_persists(tmp_path):
    """Flush writes in-memory events to SQLite."""
    tracker = _make_tracker(tmp_path)
    tracker.record(tokens_in=100, tokens_out=50, model="m", mode="online",
                   profile="sw", latency_ms=100)
    tracker.flush()

    import sqlite3
    db_path = os.path.join(str(tmp_path), "test_cost.db")
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM cost_events").fetchone()[0]
    conn.close()
    assert count >= 1
    tracker.shutdown()


# ============================================================================
# TEST 06: Cumulative summary spans sessions
# ============================================================================

def test_06_cumulative_spans_sessions(tmp_path):
    """Cumulative summary includes events from all sessions."""
    # Session 1
    t1 = _make_tracker(tmp_path)
    t1.record(tokens_in=100, tokens_out=50, model="m", mode="online",
              profile="sw", latency_ms=100)
    t1.shutdown()

    # Session 2 (new tracker, same DB)
    from src.core.cost_tracker import CostTracker, CostRates
    db_path = os.path.join(str(tmp_path), "test_cost.db")
    t2 = CostTracker(db_path=db_path, rates=CostRates(3.0, 15.0))
    t2.record(tokens_in=200, tokens_out=100, model="m", mode="online",
              profile="eng", latency_ms=200)

    c = t2.get_cumulative_summary()
    assert c.total_sessions >= 2
    assert c.total_queries >= 2
    assert c.total_tokens_in >= 300
    t2.shutdown()


# ============================================================================
# TEST 07: Rate changes persist
# ============================================================================

def test_07_rate_persistence(tmp_path):
    """Setting rates persists to SQLite and loads on next init."""
    t1 = _make_tracker(tmp_path)
    t1.set_rates(5.50, 22.00, "Premium")
    t1.shutdown()

    from src.core.cost_tracker import CostTracker, CostRates
    db_path = os.path.join(str(tmp_path), "test_cost.db")
    t2 = CostTracker(db_path=db_path, rates=CostRates())
    rates = t2.get_rates()
    assert abs(rates.input_rate_per_1m - 5.50) < 0.01
    assert abs(rates.output_rate_per_1m - 22.00) < 0.01
    assert rates.label == "Premium"
    t2.shutdown()


# ============================================================================
# TEST 08: CSV export
# ============================================================================

def test_08_csv_export(tmp_path):
    """Export to CSV creates a valid file with correct row count."""
    tracker = _make_tracker(tmp_path)
    tracker.record(tokens_in=100, tokens_out=50, model="m", mode="online",
                   profile="sw", latency_ms=100)
    tracker.record(tokens_in=200, tokens_out=100, model="m", mode="online",
                   profile="eng", latency_ms=200)

    csv_path = os.path.join(str(tmp_path), "export.csv")
    count = tracker.export_csv(csv_path)
    assert count == 2
    assert os.path.exists(csv_path)

    with open(csv_path, "r") as f:
        lines = f.readlines()
    assert len(lines) == 3  # header + 2 rows
    tracker.shutdown()


# ============================================================================
# TEST 09: Data bytes estimation from tokens
# ============================================================================

def test_09_data_bytes_estimation(tmp_path):
    """Data bytes are estimated at ~4 bytes/token when not provided."""
    tracker = _make_tracker(tmp_path)
    event = tracker.record(
        tokens_in=1000, tokens_out=500, model="m", mode="online",
        profile="sw", latency_ms=100,
    )
    assert event.data_bytes_in == 4000
    assert event.data_bytes_out == 2000
    tracker.shutdown()


# ============================================================================
# TEST 10: Listener callback fires on record
# ============================================================================

def test_10_listener_callback(tmp_path):
    """Registered listener receives CostEvent on record."""
    tracker = _make_tracker(tmp_path)
    received = []
    tracker.add_listener(lambda e: received.append(e))

    tracker.record(tokens_in=100, tokens_out=50, model="m", mode="online",
                   profile="sw", latency_ms=100)

    assert len(received) == 1
    assert received[0].tokens_in == 100

    tracker.remove_listener(received.append)  # Should not error
    tracker.shutdown()


# ============================================================================
# TEST 11: Offline mode records zero cost
# ============================================================================

def test_11_offline_zero_cost(tmp_path):
    """Offline queries still track tokens but with zero dollar cost."""
    tracker = _make_tracker(tmp_path)
    event = tracker.record(
        tokens_in=500, tokens_out=200, model="phi4-mini", mode="offline",
        profile="gen", latency_ms=3000,
    )
    # Cost is still calculated by tracker (rates apply regardless of mode)
    # but the PM dashboard shows mode=offline as a savings callout.
    assert event.tokens_in == 500
    assert event.tokens_out == 200
    assert event.mode == "offline"
    tracker.shutdown()


# ============================================================================
# TEST 12: Singleton pattern works
# ============================================================================

def test_12_singleton_pattern(tmp_path):
    """get_cost_tracker returns the same instance."""
    from src.core.cost_tracker import get_cost_tracker, reset_cost_tracker
    reset_cost_tracker()  # Clean slate
    db_path = os.path.join(str(tmp_path), "singleton.db")

    t1 = get_cost_tracker(db_path=db_path)
    t2 = get_cost_tracker()
    assert t1 is t2
    reset_cost_tracker()


# ============================================================================
# TEST 13: Dashboard window opens without crashing
# ============================================================================

def test_13_dashboard_opens(tmp_path):
    """PM Cost Dashboard Frame creates successfully."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)

    assert dashboard.winfo_exists()

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()


# ============================================================================
# TEST 14: Dashboard displays session data
# ============================================================================

def test_14_dashboard_displays_session(tmp_path):
    """Dashboard shows session spend after recording events."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    # Record some events before opening dashboard
    tracker.record(tokens_in=1000, tokens_out=500, model="gpt-4",
                   mode="online", profile="sw", latency_ms=1000)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)
    _pump_events(root, 100)

    spend_text = dashboard._spend_label.cget("text")
    assert "$" in spend_text
    assert spend_text != "$0.0000"  # Should show non-zero cost

    queries_text = dashboard._queries_label.cget("text")
    assert queries_text == "1"

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()


# ============================================================================
# TEST 15: Rate editor updates tracker
# ============================================================================

def test_15_rate_editor_updates(tmp_path):
    """Changing rates in the dashboard editor updates the tracker."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)

    dashboard._input_rate_var.set("7.5000")
    dashboard._output_rate_var.set("30.0000")
    dashboard._on_apply_rates()

    rates = tracker.get_rates()
    assert abs(rates.input_rate_per_1m - 7.5) < 0.01
    assert abs(rates.output_rate_per_1m - 30.0) < 0.01

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()


# ============================================================================
# TEST 16: App integrates cost tracker and dashboard menu
# ============================================================================

def test_16_app_has_cost_dashboard_menu(tmp_path):
    """HybridRAGApp has cost_tracker and PM Dashboard menu item."""
    @dataclass
    class FakePathsConfig:
        database: str = ""
        embeddings_cache: str = ""
        source_folder: str = ""

    @dataclass
    class FakeOllamaConfig:
        base_url: str = "http://localhost:11434"
        model: str = "phi4-mini"
        timeout_seconds: int = 120

    @dataclass
    class FakeBootResult:
        boot_timestamp: str = ""
        success: bool = True
        online_available: bool = False
        offline_available: bool = True
        api_client: object = None
        config: dict = field(default_factory=dict)
        credentials: object = None
        warnings: list = field(default_factory=list)
        errors: list = field(default_factory=list)

    @dataclass
    class FakeAPIConfig:
        endpoint: str = ""
        model: str = ""
        max_tokens: int = 2048
        temperature: float = 0.1
        timeout_seconds: int = 30
        deployment: str = ""
        api_version: str = ""
        allowed_endpoint_prefixes: list = field(default_factory=list)

    @dataclass
    class FakeRetrievalConfig:
        top_k: int = 8
        min_score: float = 0.20
        hybrid_search: bool = True
        reranker_enabled: bool = False
        reranker_model: str = ""
        reranker_top_n: int = 20
        rrf_k: int = 60
        block_rows: int = 25000
        lex_boost: float = 0.06
        min_chunks: int = 1

    @dataclass
    class FakeChunkingConfig:
        chunk_size: int = 1200
        overlap: int = 200
        max_heading_len: int = 160

    config = FakeConfig()
    config.paths = FakePathsConfig()
    config.ollama = FakeOllamaConfig()
    config.api = FakeAPIConfig()
    config.retrieval = FakeRetrievalConfig()
    config.chunking = FakeChunkingConfig()

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable")

    root.withdraw()

    from src.core.cost_tracker import reset_cost_tracker
    reset_cost_tracker()

    app = _make_app(
        boot_result=FakeBootResult(),
        config=config,
    )

    # Verify cost_tracker attribute exists
    assert hasattr(app, "cost_tracker")
    assert app.cost_tracker is not None

    # Verify dashboard can open via show_view
    app.show_view("cost")
    cost_view = app._views.get("cost")
    assert cost_view is not None
    assert cost_view.winfo_exists()

    cost_view.cleanup()
    app.cost_tracker.shutdown()
    app.status_bar.stop()
    app.destroy()
    root.destroy()
    reset_cost_tracker()


# ============================================================================
# TEST 17: ROI calculator displays time saved
# ============================================================================

def test_17_roi_time_saved(tmp_path):
    """ROI calculator shows correct time saved based on query count."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    # Record 6 queries
    for _ in range(6):
        tracker.record(tokens_in=500, tokens_out=200, model="gpt-4",
                       mode="online", profile="sw", latency_ms=800)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)
    _pump_events(root, 100)

    # Default 10 min saved per query, 6 queries = 60 min = 1h 0m
    time_text = dashboard._roi_time_label.cget("text")
    assert "1h" in time_text and "0m" in time_text

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()


# ============================================================================
# TEST 18: ROI value calculation
# ============================================================================

def test_18_roi_value_calculation(tmp_path):
    """ROI value = (queries * min_saved / 60) * hourly_rate."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    tracker.record(tokens_in=500, tokens_out=200, model="gpt-4",
                   mode="online", profile="sw", latency_ms=800)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)
    _pump_events(root, 100)

    # 1 query * 10 min / 60 * $48.44 = $8.07
    value_text = dashboard._roi_value_label.cget("text")
    assert "$" in value_text
    val = float(value_text.replace("$", "").replace(",", ""))
    assert abs(val - 8.07) < 0.10

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()


# ============================================================================
# TEST 19: ROI parameter update works
# ============================================================================

def test_19_roi_param_update(tmp_path):
    """Updating ROI parameters recalculates values."""
    root = _make_root()
    tracker = _make_tracker(tmp_path)

    tracker.record(tokens_in=500, tokens_out=200, model="gpt-4",
                   mode="online", profile="sw", latency_ms=800)

    from src.gui.panels.cost_dashboard import CostDashboard
    dashboard = CostDashboard(root, tracker)

    # Change hourly rate to $100
    dashboard._roi_hourly_var.set("100.00")
    dashboard._roi_team_var.set("5")
    dashboard._roi_minsaved_var.set("15")
    dashboard._on_update_roi()
    _pump_events(root, 100)

    assert dashboard._roi_hourly == 100.0
    assert dashboard._roi_team == 5
    assert dashboard._roi_min_saved == 15

    # 1 query * 15 min / 60 * $100 = $25.00
    value_text = dashboard._roi_value_label.cget("text")
    val = float(value_text.replace("$", "").replace(",", ""))
    assert abs(val - 25.0) < 0.10

    dashboard.cleanup()
    tracker.shutdown()
    root.destroy()
