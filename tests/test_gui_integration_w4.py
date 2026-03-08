# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the gui integration w4 area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: GUI integration tests covering all panels (query, index,
#       settings, API admin tab) with mocked backends (17 tests)
# WHY:  The GUI wires together many backend components (config, LLM
#       router, cost tracker, vector store). These tests verify that
#       the wiring is correct and panels render without crashing,
#       even when backends are unavailable.
# HOW:  Mocks all backends so no real indexing, API calls, or database
#       needed. Works offline with no API key. Uses Tk test mode.
# USAGE: pytest tests/test_gui_integration_w4.py -v
# ===================================================================

import sys
import os
import threading
import time
import tkinter as tk
from pathlib import Path
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional, List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# -- sys.path setup --
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# FAKE CONFIG (extends conftest pattern)
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


@dataclass
class FakeAPIConfig:
    endpoint: str = ""
    model: str = "gpt-4o"
    context_window: int = 128000
    max_tokens: int = 1024
    temperature: float = 0.05
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


@dataclass
class FakeBootResult:
    boot_timestamp: str = "2026-02-21 14:30:00"
    success: bool = True
    online_available: bool = False
    offline_available: bool = True
    api_client: object = None
    config: dict = field(default_factory=dict)
    credentials: object = None
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def summary(self):
        return "BOOT: OK"


# ============================================================================
# HELPERS
# ============================================================================

def _make_root():
    """Create a Tk root that we can destroy after each test."""
    try:
        root = tk.Tk()
        root.withdraw()  # Don't show the window
    except tk.TclError:
        pytest.skip("Tk runtime unavailable (Tcl interpreter state)")
    return root


def _make_app(*args, **kwargs):
    """Create the full app or skip cleanly when Tk is unavailable."""
    from src.gui.app import HybridRAGApp

    try:
        app = HybridRAGApp(*args, **kwargs)
        app.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable (Tcl interpreter state)")
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


def _wait_and_pump(root, ms=500):
    """Wait for background threads to post results, then pump events."""
    time.sleep(ms / 1000.0)
    # Pump events multiple times to ensure after() callbacks are processed
    for _ in range(10):
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            break
        time.sleep(0.02)


# ============================================================================
# TEST 01: GUI launches without crashing
# ============================================================================

def test_01_gui_launches_without_crashing():
    """GUI app window creates successfully with mocked boot result."""
    config = FakeGUIConfig()
    boot = FakeBootResult()

    app = _make_app(boot_result=boot, config=config)

    assert app.winfo_exists()
    assert app.title() == "HybridRAG v3"

    app.status_bar.stop()
    app.destroy()


# ============================================================================
# TEST 02: Query panel submits query and displays answer
# ============================================================================

def test_02_query_panel_displays_answer():
    """Query panel shows answer from mocked QueryEngine."""
    root = _make_root()

    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel
    panel = QueryPanel(root, config=config)
    panel.pack()

    # Directly test _display_result (bypasses threading for test reliability)
    result = FakeQueryResult(
        answer="The frequency is 2.4 GHz.",
        sources=[{"path": "spec.pdf", "chunks": 3}],
        latency_ms=1500.0,
        tokens_in=400,
        tokens_out=80,
    )
    panel._display_result(result)
    _pump_events(root, 50)

    # Check answer displayed
    answer_text = panel.answer_text.get("1.0", tk.END).strip()
    assert "2.4 GHz" in answer_text

    # Check sources displayed
    sources_text = panel.sources_label.cget("text")
    assert "spec.pdf" in sources_text

    # Check metrics displayed
    metrics_text = panel.metrics_label.cget("text")
    assert "1,500" in metrics_text

    root.destroy()


# ============================================================================
# TEST 03: Query panel shows error correctly when query fails
# ============================================================================

def test_03_query_panel_shows_error():
    """Query panel shows error when query returns error."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel
    panel = QueryPanel(root, config=config)
    panel.pack()

    # Directly test _display_result with an error result
    result = FakeQueryResult(
        answer="Error processing query",
        error="LLM call failed",
    )
    panel._display_result(result)
    _pump_events(root, 50)

    answer_text = panel.answer_text.get("1.0", tk.END).strip()
    assert "FAIL" in answer_text

    root.destroy()


# ============================================================================
# TEST 04: Ask button disables during query, re-enables after
# ============================================================================

def test_04_ask_button_disable_reenable():
    """Ask button is disabled during query and re-enabled after."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel
    panel = QueryPanel(root, config=config, query_engine=MagicMock())
    panel.pack()

    # Simulate what _on_ask does: disable button
    panel.ask_btn.config(state=tk.DISABLED)
    _pump_events(root, 20)
    assert str(panel.ask_btn["state"]) == "disabled"

    # Simulate what _display_result does: re-enable button
    panel._display_result(FakeQueryResult())
    _pump_events(root, 20)
    assert str(panel.ask_btn["state"]) == "normal"

    root.destroy()


def test_03b_query_panel_publishes_debug_trace_to_admin():
    """Completed queries should push their debug trace into the Admin shell."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel

    panel = QueryPanel(root, config=config)
    panel.pack()

    fake_admin = MagicMock()
    fake_app = SimpleNamespace(_admin_panel=fake_admin, _last_query_trace=None)
    panel.winfo_toplevel = lambda: fake_app

    trace = {
        "mode": "offline",
        "active_profile": "",
        "engine_kind": "base",
        "stream": False,
        "query": "What is the frequency?",
        "retrieval": {
            "counts": {
                "raw_hits": 1,
                "post_rerank_hits": 1,
                "post_filter_hits": 1,
                "post_augment_hits": 1,
                "final_hits": 1,
                "dropped_hits": 0,
            },
            "hits": {
                "final": [
                    {
                        "rank": 1,
                        "score": 0.95,
                        "source_file": "spec.pdf",
                        "source_path": "spec.pdf",
                        "chunk_index": 0,
                        "text": "Frequency is 2.4 GHz.",
                    }
                ],
                "dropped": [],
            },
        },
        "decision": {"path": "answer"},
        "result": {"latency_ms": 1500.0},
        "settings": {"query": {}, "backend": {}},
        "paths": {},
        "context": {},
        "llm": {},
        "grounding": {},
    }
    result = FakeQueryResult(
        answer="The frequency is 2.4 GHz.",
        sources=[{"path": "spec.pdf", "chunks": 1}],
        debug_trace=trace,
    )

    panel._display_result(result)
    _pump_events(root, 50)

    assert fake_app._last_query_trace == trace
    fake_admin._update_query_debug_trace.assert_called_once_with(trace)

    root.destroy()


def test_04b_set_ready_keeps_stop_enabled_while_querying():
    """set_ready() must not disable Stop while a query is in progress."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel
    panel = QueryPanel(root, config=config, query_engine=MagicMock())
    panel.pack()

    panel.is_querying = True
    panel._streaming = True
    panel.set_ready(True)
    _pump_events(root, 20)

    assert str(panel.ask_btn["state"]) == "disabled"
    assert str(panel.stop_btn["state"]) == "normal"

    root.destroy()


# ============================================================================
# TEST 05: Use case dropdown populates from USE_CASES
# ============================================================================

def test_05_use_case_dropdown_populates():
    """Use case dropdown contains all USE_CASES labels."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.query_panel import QueryPanel
    from scripts._model_meta import USE_CASES

    panel = QueryPanel(root, config=config)
    panel.pack()

    dropdown_values = list(panel.uc_dropdown["values"])
    expected_labels = [USE_CASES[k]["label"] for k in USE_CASES]

    for label in expected_labels:
        assert label in dropdown_values, "Missing use case: {}".format(label)

    root.destroy()


def test_05b_use_case_change_does_not_increase_context_window():
    """Use-case switching must not silently raise ollama.context_window."""
    root = _make_root()
    config = FakeGUIConfig()
    config.ollama.context_window = 4096

    from src.gui.panels.query_panel import QueryPanel

    panel = QueryPanel(root, config=config)
    panel.pack()
    _pump_events(root, 50)

    # Pick a profile that historically recommended 16K context.
    panel.uc_var.set("Software Engineering")
    panel._on_use_case_change()
    _pump_events(root, 50)

    assert config.ollama.context_window == 4096

    root.destroy()


def test_05c_use_case_change_preserves_higher_context_window():
    """Use-case switching must not silently lower a user-selected context window."""
    root = _make_root()
    config = FakeGUIConfig()
    config.ollama.context_window = 16384

    from src.gui.panels.query_panel import QueryPanel

    panel = QueryPanel(root, config=config)
    panel.pack()
    _pump_events(root, 50)

    panel.uc_var.set("Software Engineering")
    panel._on_use_case_change()
    _pump_events(root, 50)

    assert config.ollama.context_window == 16384

    root.destroy()


def test_05d_grounding_control_no_longer_overrides_retrieval_min_score():
    """Grounding strictness must tune the guard without rewriting min_score."""
    root = _make_root()
    config = FakeGUIConfig()
    config.retrieval.min_score = 0.02
    engine = SimpleNamespace(
        allow_open_knowledge=False,
        guard_enabled=False,
        guard_threshold=0.0,
        guard_min_chunks=0,
        guard_min_score=0.0,
        guard_action="",
    )

    from src.gui.panels.query_panel import QueryPanel

    panel = QueryPanel(root, config=config, query_engine=engine)
    panel.pack()
    panel._grounding_bias_var.set(8)
    panel._apply_grounding_bias_live(8)

    assert abs(config.retrieval.min_score - 0.02) < 1e-9
    assert abs(engine.guard_min_score - 0.10) < 1e-9

    root.destroy()


def test_05e_open_knowledge_toggle_updates_engine_boolean():
    """Open-knowledge fallback is exposed as a boolean control."""
    root = _make_root()
    config = FakeGUIConfig()
    engine = SimpleNamespace(
        allow_open_knowledge=False,
        guard_enabled=False,
        guard_threshold=0.0,
        guard_min_chunks=0,
        guard_min_score=0.0,
        guard_action="",
    )

    from src.gui.panels.query_panel import QueryPanel

    panel = QueryPanel(root, config=config, query_engine=engine)
    panel.pack()

    panel._open_knowledge_var.set(False)
    panel._on_open_knowledge_toggle()
    assert engine.allow_open_knowledge is False
    assert "OFF" in panel._open_knowledge_hint.get()

    panel._open_knowledge_var.set(True)
    panel._on_open_knowledge_toggle()
    assert engine.allow_open_knowledge is True
    assert "ON" in panel._open_knowledge_hint.get()

    root.destroy()


def test_05f_mode_switch_rehydrates_query_panel_grounding_controls(tmp_path):
    """Offline and online query dials must reload from separate mode-store values."""
    root = _make_root()
    config = FakeGUIConfig(mode="offline")
    engine = SimpleNamespace(
        allow_open_knowledge=True,
        guard_enabled=False,
        guard_threshold=0.0,
        guard_min_chunks=0,
        guard_min_score=0.0,
        guard_action="",
    )
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        from src.gui.helpers.mode_tuning import ModeTuningStore
        store = ModeTuningStore(str(tmp_path))
        store.update_value(config, "offline", "grounding_bias", 9)
        store.update_value(config, "offline", "allow_open_knowledge", False)
        store.update_value(config, "online", "grounding_bias", 4)
        store.update_value(config, "online", "allow_open_knowledge", True)

        from src.gui.panels.query_panel import QueryPanel

        panel = QueryPanel(root, config=config, query_engine=engine)
        panel.pack()
        _pump_events(root, 50)

        panel._on_use_case_change()
        assert panel._grounding_bias_var.get() == 9
        assert panel._open_knowledge_var.get() is False
        assert engine.allow_open_knowledge is False
        assert engine.guard_action == "block"

        config.mode = "online"
        panel._on_use_case_change()
        assert panel._grounding_bias_var.get() == 4
        assert panel._open_knowledge_var.get() is True
        assert engine.allow_open_knowledge is True
        assert engine.guard_action == "flag"

        panel.destroy()

    root.destroy()


# ============================================================================
# TEST 06: Index panel shows read-only paths from config
# ============================================================================

def test_06_index_panel_displays_paths_from_config():
    """Index panel shows source and index folder from config (read-only)."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.index_panel import IndexPanel

    panel = IndexPanel(root, config=config)
    panel.pack()

    # Source folder comes from config
    assert panel.folder_var.get() == config.paths.source_folder

    # Index folder derived from database path (empty db = "(not set)")
    if config.paths.database:
        expected_index = os.path.dirname(config.paths.database)
    else:
        expected_index = "(not set)"
    assert panel.index_var.get() == expected_index

    # Paths are displayed as labels, not editable entries
    assert hasattr(panel, "folder_display")
    assert hasattr(panel, "index_display")
    assert not hasattr(panel, "browse_btn")

    root.destroy()


# ============================================================================
# TEST 07: Index panel progress bar advances
# ============================================================================

def test_07_index_panel_progress_bar_advances():
    """Progress callback updates the progress bar."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.index_panel import IndexPanel, _GUIProgressCallback

    panel = IndexPanel(root, config=config)
    panel.pack()

    callback = _GUIProgressCallback(panel)

    # Simulate file processing
    callback.on_file_start("/tmp/file1.pdf", 1, 5)
    _pump_events(root, 100)
    assert panel.progress_bar["maximum"] == 5

    callback.on_file_complete("/tmp/file1.pdf", 10)
    _pump_events(root, 100)
    assert callback._file_count == 1

    callback.on_file_complete("/tmp/file2.pdf", 8)
    _pump_events(root, 100)
    assert callback._file_count == 2

    root.destroy()


# ============================================================================
# TEST 08: Status bar reflects offline mode
# ============================================================================

def test_08_status_bar_offline_mode():
    """Status bar shows OFFLINE when config.mode is offline."""
    root = _make_root()
    config = FakeGUIConfig(mode="offline")

    from src.gui.panels.status_bar import StatusBar

    bar = StatusBar(root, config=config)
    bar.pack()
    bar._refresh_status()
    _pump_events(root, 100)

    gate_text = bar.gate_label.cget("text")
    assert "OFFLINE" in gate_text

    bar.stop()
    root.destroy()


# ============================================================================
# TEST 09: Status bar reflects online mode
# ============================================================================

def test_09_status_bar_online_mode():
    """Status bar shows ONLINE when config.mode is online."""
    root = _make_root()
    config = FakeGUIConfig(mode="online")

    from src.gui.panels.status_bar import StatusBar

    bar = StatusBar(root, config=config)
    bar.pack()
    bar._refresh_status()
    _pump_events(root, 100)

    gate_text = bar.gate_label.cget("text")
    assert "ONLINE" in gate_text

    bar.stop()
    root.destroy()


# ============================================================================
# TEST 10: ONLINE button shows credential error when creds missing
# ============================================================================

def test_10_online_button_cred_error():
    """Switching to online mode blocks when credentials are missing.

    Tests the credential check in _do_switch_to_online directly (synchronous)
    since the async wrapper + app.after() require a running Tk mainloop.
    """
    from src.security.credentials import ApiCredentials, invalidate_credential_cache

    config = FakeGUIConfig(mode="offline")
    app = _make_app(config=config)

    # Track warning calls -- intercept messagebox at the tkinter level
    from tkinter import messagebox as mb_module
    warning_calls = []
    original_showwarning = mb_module.showwarning

    def fake_showwarning(title, message):
        warning_calls.append((title, message))

    mb_module.showwarning = fake_showwarning

    # Patch resolve_credentials to return empty creds (no key, no endpoint)
    from src.security import credentials as cred_mod
    original_resolve = cred_mod.resolve_credentials
    invalidate_credential_cache()
    cred_mod.resolve_credentials = lambda **kw: ApiCredentials()

    # Patch app.after to call the function immediately (no mainloop needed)
    original_after = app.after
    def immediate_after(ms, func, *args):
        if callable(func):
            func(*args)
    app.after = immediate_after

    try:
        # Call the internal synchronous function directly
        from src.gui.helpers.mode_switch import _do_switch_to_online
        _do_switch_to_online(app)

        # Should have shown a warning
        assert len(warning_calls) >= 1
        assert "Credentials Missing" in warning_calls[0][0]

        # Mode should NOT have changed
        assert config.mode == "offline"
    finally:
        mb_module.showwarning = original_showwarning
        cred_mod.resolve_credentials = original_resolve
        app.after = original_after
        invalidate_credential_cache()

    app.status_bar.stop()
    app.destroy()


# ============================================================================
# TEST 11: Settings view sliders read current config values
# ============================================================================

def test_11_settings_view_reads_config(tmp_path):
    """Settings view sliders are initialized from the active mode values."""
    root = _make_root()
    config = FakeGUIConfig()
    config.retrieval.top_k = 12
    config.retrieval.min_score = 0.15
    config.ollama.context_window = 8192
    config.ollama.num_predict = 768
    config.ollama.temperature = 0.3
    config.ollama.timeout_seconds = 240

    from src.gui.panels.settings_view import SettingsView

    with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        app_ref = MagicMock()
        view = SettingsView(root, config=config, app_ref=app_ref)

        assert view.topk_var.get() == 12
        assert abs(view.minscore_var.get() - 0.15) < 0.01
        assert view.ctx_window_var.get() == 8192
        assert view.num_predict_var.get() == 768
        assert abs(view.temp_var.get() - 0.3) < 0.01
        assert view.timeout_var.get() == 240

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 12: Settings view writes config on slider change
# ============================================================================

def test_12_settings_view_writes_config():
    """Changing an offline slider updates the active offline config fields."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.settings_view import SettingsView

    app_ref = MagicMock()
    view = SettingsView(root, config=config, app_ref=app_ref)

    # Change top_k
    view.topk_var.set(25)
    view._on_retrieval_change()
    assert config.retrieval.top_k == 25

    # Change active offline runtime knobs
    view.num_predict_var.set(2048)
    view.temp_var.set(0.5)
    view.timeout_var.set(240)
    view._on_llm_change()
    assert config.ollama.num_predict == 2048
    assert abs(config.ollama.temperature - 0.5) < 0.01
    assert config.ollama.timeout_seconds == 240

    view.destroy()
    root.destroy()


def test_12b_settings_view_online_mode_reads_and_writes_api_values(tmp_path):
    """Hidden tuning view must stay mode-aware in online mode."""
    root = _make_root()
    config = FakeGUIConfig(mode="online")
    config.api.context_window = 64000
    config.api.max_tokens = 4096
    config.api.temperature = 1.25
    config.api.timeout_seconds = 900
    config.ollama.context_window = 4096
    config.ollama.temperature = 0.05
    config.ollama.timeout_seconds = 180

    from src.gui.panels.settings_view import SettingsView

    with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        app_ref = MagicMock()
        view = SettingsView(root, config=config, app_ref=app_ref)

        assert view.ctx_window_var.get() == 64000
        assert view.maxtokens_var.get() == 4096
        assert abs(view.temp_var.get() - 1.25) < 0.01
        assert view.timeout_var.get() == 900

        view.ctx_window_var.set(128000)
        view.maxtokens_var.set(16384)
        view.temp_var.set(2.0)
        view.timeout_var.set(1200)
        view._on_llm_change()

        assert config.api.context_window == 128000
        assert config.api.max_tokens == 16384
        assert abs(config.api.temperature - 2.0) < 0.01
        assert config.api.timeout_seconds == 1200
        assert config.ollama.context_window == 4096
        assert abs(config.ollama.temperature - 0.05) < 0.01

    view.destroy()
    root.destroy()


def test_12c_settings_view_mode_store_persists_min_max_without_snapback(tmp_path):
    """Mode-store backed controls must keep user-selected extremes after resync."""
    root = _make_root()
    config = FakeGUIConfig(mode="online")
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    from src.gui.panels.settings_view import SettingsView

    with patch.dict(
        os.environ,
        {
            "HYBRIDRAG_PROJECT_ROOT": str(tmp_path),
            "HYBRIDRAG_DEV_UI": "1",
        },
    ):
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)
        tab = view._tuning_tab

        tab.topk_var.set(1)
        tab.ctx_window_var.set(128000)
        tab.maxtokens_var.set(16384)
        tab.temp_var.set(2.0)
        tab.timeout_var.set(1200)
        tab._on_retrieval_change()
        tab._on_llm_change()
        tab._sync_sliders_to_config()

        assert tab.topk_var.get() == 1
        assert tab.ctx_window_var.get() == 128000
        assert tab.maxtokens_var.get() == 16384
        assert abs(tab.temp_var.get() - 2.0) < 0.01
        assert tab.timeout_var.get() == 1200

        tab._on_save_mode_defaults()
        max_tokens_default = tab._default_vars["max_tokens"]
        max_tokens_default.set(True)
        tab._on_default_toggle(
            "max_tokens",
            tab.maxtokens_var,
            max_tokens_default,
            tab._on_llm_change,
        )
        tab.maxtokens_var.set(256)
        tab._sync_sliders_to_config()

        assert tab.maxtokens_var.get() == 16384

        import yaml
        with open(cfg_dir / "config.yaml", "r", encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["modes"]["online"]["retrieval"]["top_k"] == 1
        assert saved["modes"]["online"]["api"]["context_window"] == 128000
        assert saved["modes"]["online"]["api"]["max_tokens"] == 16384
        assert saved["modes"]["online"]["api"]["temperature"] == 2.0
        assert saved["modes"]["online"]["api"]["timeout_seconds"] == 1200
        assert saved["modes"]["online"]["defaults"]["max_tokens"] == 16384
        assert saved["modes"]["online"]["locks"]["max_tokens"] is True

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 13: Profile dropdown calls _profile_switch.py
# ============================================================================

def test_13_profile_dropdown_calls_switch():
    """Profile dropdown triggers subprocess call to _profile_switch.py."""
    root = _make_root()
    config = FakeGUIConfig()

    from src.gui.panels.settings_view import SettingsView

    with patch("src.gui.panels.tuning_tab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Applied", stderr="")
        app_ref = MagicMock()
        view = SettingsView(root, config=config, app_ref=app_ref)

        # Change profile
        view.profile_var.set("desktop_power")
        view._on_profile_change()

        _wait_and_pump(root, 300)

        # Verify subprocess was called with the profile name
        calls = mock_run.call_args_list
        switch_calls = [c for c in calls if "_profile_switch" in str(c)]
        assert len(switch_calls) > 0, "Expected _profile_switch.py to be called"

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 14: Settings view reset restores original values
# ============================================================================

def test_14_settings_view_reset_defaults(tmp_path):
    """Reset button restores the saved mode defaults for the active mode."""
    root = _make_root()
    config = FakeGUIConfig()
    config.retrieval.top_k = 8
    config.ollama.temperature = 0.1

    from src.gui.panels.settings_view import SettingsView

    with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        app_ref = MagicMock()
        view = SettingsView(root, config=config, app_ref=app_ref)

        view._tuning_tab._on_save_mode_defaults()

        # Change values away from defaults
        view.topk_var.set(40)
        view.temp_var.set(0.9)
        view._on_retrieval_change()
        view._on_llm_change()
        assert config.retrieval.top_k == 40

        # Reset
        view._on_reset()
        assert view.topk_var.get() == 8
        assert abs(view.temp_var.get() - 0.1) < 0.01
        assert config.retrieval.top_k == 8
        assert abs(config.ollama.temperature - 0.1) < 0.01

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 15: API Admin tab credential fields exist and populated from mock
# ============================================================================

def test_15_api_admin_tab_credential_fields():
    """API Admin tab has endpoint and key entry fields populated from creds."""
    root = _make_root()
    config = FakeGUIConfig()

    mock_creds = MagicMock()
    mock_creds.endpoint = "https://test.example.com"
    mock_creds.api_key = "sk-test1234567890"
    mock_creds.has_key = True
    mock_creds.has_endpoint = True
    mock_creds.is_online_ready = True
    mock_creds.key_preview = "sk-t...7890"
    mock_creds.source_key = "keyring"
    mock_creds.source_endpoint = "keyring"

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)
        _pump_events(root, 50)

        # Verify credential fields exist and are populated
        tab = view._api_admin_tab
        assert tab.endpoint_var.get() == "https://test.example.com"
        assert tab.key_var.get() == "sk-test1234567890"

        # Verify status label shows green (online ready)
        status_text = tab.cred_status_label.cget("text")
        assert "Key:" in status_text
        assert "Endpoint:" in status_text

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 16: Save credentials calls store_api_key and store_endpoint
# ============================================================================

def test_16_save_credentials_calls_store():
    """Save Credentials button calls store_api_key and store_endpoint."""
    root = _make_root()
    config = FakeGUIConfig(mode="online")

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        app_ref.query_engine = MagicMock()
        app_ref.query_engine.llm_router = MagicMock()
        app_ref.query_engine.llm_router.api = MagicMock()
        app_ref.query_engine.llm_router.last_error = "stale"
        app_ref.status_bar = MagicMock()
        view = SettingsView(root, config=config, app_ref=app_ref)

    tab = view._api_admin_tab

    # Set test values
    tab.endpoint_var.set("https://api.example.com")
    tab.key_var.set("sk-testkey123")

    with patch("src.gui.panels.api_admin_tab.store_endpoint") as mock_ep, \
         patch("src.gui.panels.api_admin_tab.store_api_key") as mock_key, \
         patch("src.gui.panels.api_admin_tab.validate_endpoint",
               return_value="https://api.example.com"), \
         patch("src.gui.panels.api_admin_tab.invalidate_credential_cache") as mock_invalidate_cache, \
         patch("src.core.llm_router.invalidate_deployment_cache") as mock_invalidate_deployments, \
         patch("src.gui.panels.api_admin_tab.resolve_credentials",
               return_value=mock_creds):
        tab._on_save_credentials()

    mock_ep.assert_called_once_with("https://api.example.com")
    mock_key.assert_called_once_with("sk-testkey123")
    mock_invalidate_cache.assert_called_once()
    mock_invalidate_deployments.assert_called_once()
    assert app_ref.query_engine.llm_router.api is None
    assert app_ref.query_engine.llm_router.last_error == ""

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 17: Admin defaults save/restore round-trip
# ============================================================================

def test_17_admin_defaults_round_trip(tmp_path):
    """Save and restore admin defaults round-trips config values."""
    root = _make_root()
    config = FakeGUIConfig()
    config.retrieval.top_k = 15
    config.api.temperature = 0.3
    config.api.model = "gpt-4o"

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("mode: offline\n", encoding="utf-8")

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds), \
         patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)

        tab = view._api_admin_tab

        # Save defaults
        tab._on_save_defaults()
        import yaml
        with open(cfg_dir / "config.yaml", "r", encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        assert saved["admin_defaults"]["mode"] == "offline"
        assert saved["admin_defaults"]["paths"]["source_folder"] == config.paths.source_folder
        assert saved["modes"]["offline"]["defaults"]["top_k"] == 15
        assert abs(saved["modes"]["online"]["defaults"]["temperature"] - 0.3) < 0.01
        assert saved["modes"]["online"]["api"]["model"] == "gpt-4o"

        # Mutate config
        config.retrieval.top_k = 99
        config.api.temperature = 0.9
        config.api.model = "changed"

        # Restore defaults
        tab._on_restore_defaults()
        assert config.retrieval.top_k == 15
        assert abs(config.api.temperature - 0.3) < 0.01
        assert config.api.model == "gpt-4o"

        with open(cfg_dir / "config.yaml", "r", encoding="utf-8") as f:
            restored = yaml.safe_load(f)
        assert restored["mode"] == "offline"
        assert restored["modes"]["offline"]["retrieval"]["top_k"] == 15
        assert restored["modes"]["offline"]["defaults"]["top_k"] == 15
        assert restored["modes"]["online"]["api"]["model"] == "gpt-4o"

    view.destroy()
    root.destroy()


def test_17b_admin_debug_panel_renders_trace_text():
    """Admin tab should render the latest retrieval trace for development review."""
    root = _make_root()
    config = FakeGUIConfig()

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds):
        from src.gui.panels.settings_view import SettingsView

        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)
        _pump_events(root, 50)

        tab = view._api_admin_tab
        trace = {
            "mode": "offline",
            "active_profile": "",
            "engine_kind": "base",
            "stream": False,
            "query": "What is the frequency?",
            "paths": {
                "source_folder": "D:/HybridRAG3/data/source",
                "database": "D:/HybridRAG3/data/index/hybridrag.sqlite3",
            },
            "settings": {
                "query": {
                    "grounding_bias": 6,
                    "allow_open_knowledge": True,
                    "guard_enabled": True,
                    "guard_threshold": 0.68,
                    "guard_min_chunks": 2,
                    "guard_min_score": 0.06,
                    "guard_action": "block",
                },
                "backend": {
                    "name": "ollama",
                    "model": "phi4-mini",
                    "deployment": "",
                    "context_window": 4096,
                    "max_tokens": 0,
                    "num_predict": 384,
                    "temperature": 0.05,
                },
            },
            "retrieval": {
                "counts": {
                    "raw_hits": 2,
                    "post_rerank_hits": 2,
                    "post_filter_hits": 2,
                    "post_augment_hits": 2,
                    "final_hits": 2,
                    "dropped_hits": 0,
                },
                "hits": {
                    "final": [
                        {
                            "rank": 1,
                            "score": 0.95,
                            "source_file": "spec.pdf",
                            "source_path": "D:/HybridRAG3/data/source/spec.pdf",
                            "chunk_index": 0,
                            "text": "Frequency is 2.4 GHz.",
                        }
                    ],
                    "dropped": [],
                },
            },
            "decision": {"path": "answer"},
            "result": {"latency_ms": 1500.0, "cost_usd": 0.0, "error": ""},
            "context": {"chars_before_trim": 100, "chars_after_trim": 100, "trimmed": False},
            "llm": {"model": "phi4-mini", "tokens_in": 100, "tokens_out": 25, "latency_ms": 200.0},
            "grounding": {},
        }

        tab._update_query_debug_trace(trace)
        _pump_events(root, 50)

        assert "OFFLINE" in tab._query_debug_status.cget("text")
        text = tab._query_debug_text.get("1.0", tk.END)
        assert "Latest Query Trace" in text
        assert "Frequency is 2.4 GHz." in text
        assert "spec.pdf" in text

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 18: Data Paths panel reads config and validates save
# ============================================================================

def test_18_data_paths_panel_reads_and_saves(tmp_path):
    """DataPathsPanel reads config paths, validates folders, writes to config."""
    root = _make_root()
    config = FakeGUIConfig()

    # Create real temp folders so validation passes
    src_dir = str(tmp_path / "source_docs")
    idx_dir = str(tmp_path / "indexed_data")
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(idx_dir, exist_ok=True)

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    # Write a temp config YAML for the save to target
    cfg_dir = str(tmp_path / "config")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_file = os.path.join(cfg_dir, "config.yaml")
    with open(cfg_file, "w") as f:
        f.write("paths: {}\n")
    # save_config_field now writes to config/config.yaml
    overrides_file = os.path.join(cfg_dir, "config.yaml")

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds), \
         patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": str(tmp_path)}):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)
        _pump_events(root, 50)

        tab = view._api_admin_tab
        paths_panel = tab._paths_panel

        # Set valid source and index folders
        paths_panel.source_var.set(src_dir)
        paths_panel.index_var.set(idx_dir)

        # Save paths
        paths_panel._on_save()
        _pump_events(root, 50)

        # Verify config was updated
        assert config.paths.source_folder == src_dir
        expected_db = os.path.join(idx_dir, "hybridrag.sqlite3")
        assert config.paths.database == expected_db

        # Verify config.yaml was written
        import yaml
        with open(overrides_file, "r") as f:
            saved = yaml.safe_load(f)
        assert saved["paths"]["source_folder"] == src_dir
        assert saved["paths"]["database"] == expected_db

        # Verify status shows success
        status = paths_panel.status_label.cget("text")
        assert "OK" in status

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 19: Data Paths panel rejects non-existent folders
# ============================================================================

def test_19_data_paths_rejects_bad_folders():
    """DataPathsPanel shows error when folders don't exist."""
    root = _make_root()
    config = FakeGUIConfig()

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.gui.panels.api_admin_tab.resolve_credentials", return_value=mock_creds):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)
        _pump_events(root, 50)

        tab = view._api_admin_tab
        paths_panel = tab._paths_panel

        # Set non-existent folders
        paths_panel.source_var.set("Z:\\does_not_exist_source_12345")
        paths_panel.index_var.set("Z:\\does_not_exist_index_12345")

        # Try to save
        paths_panel._on_save()
        _pump_events(root, 50)

        # Should show FAIL status
        status = paths_panel.status_label.cget("text")
        assert "FAIL" in status

        # Config should NOT have been updated
        assert config.paths.source_folder == ""

    view.destroy()
    root.destroy()


# ============================================================================
# TEST 20: ScrollableFrame creates and scrolls
# ============================================================================

def test_20_scrollable_frame_creates():
    """ScrollableFrame creates inner frame and canvas correctly."""
    root = _make_root()

    from src.gui.scrollable import ScrollableFrame

    sf = ScrollableFrame(root, bg="#1e1e2e")
    sf.pack(fill=tk.BOTH, expand=True)

    # Inner frame exists and is a Frame
    assert isinstance(sf.inner, tk.Frame)

    # Can add widgets to inner
    label = tk.Label(sf.inner, text="Test content")
    label.pack()
    _pump_events(root, 50)

    assert label.winfo_exists()

    # Apply theme works
    sf.apply_theme({"bg": "#ffffff"})
    assert sf.cget("bg") == "#ffffff"

    sf.destroy()
    root.destroy()


# ============================================================================
# TEST 21: Zoom scaling changes font sizes
# ============================================================================

def test_21_zoom_scaling():
    """set_zoom() scales all font tuples correctly."""
    from src.gui import theme

    original_size = theme._BASE_SIZES["FONT"]

    # Zoom to 200%
    theme.set_zoom(2.0)
    assert theme.FONT[1] == original_size * 2
    assert theme.FONT_BOLD[1] == original_size * 2
    assert theme.get_zoom() == 2.0

    # Zoom to 50%
    theme.set_zoom(0.5)
    expected = max(7, int(original_size * 0.5))
    assert theme.FONT[1] == expected

    # Reset to 100%
    theme.set_zoom(1.0)
    assert theme.FONT[1] == original_size
    assert theme.get_zoom() == 1.0
