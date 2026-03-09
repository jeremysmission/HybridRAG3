# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies mode-switch runtime refresh behavior and protects against stale tuning UI.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake app objects with mocked panels/status bar.
# Outputs: Assertions that the active tuning panel is refreshed after a mode switch.
# Safety notes: No Tk mainloop or I/O required.
# ============================

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.gui.helpers.mode_switch import _commit_router_and_mode, _finish_switch


def test_finish_switch_refreshes_active_tuning_panel():
    status_bar = MagicMock()
    status_bar.loading_label.cget.return_value = "Loading: Switching mode..."

    app = SimpleNamespace(
        status_bar=status_bar,
        query_panel=MagicMock(),
        _tuning_panel=MagicMock(),
        _admin_panel=None,
    )

    with patch("src.gui.helpers.mode_switch.update_mode_buttons") as mock_update:
        _finish_switch(app)

    mock_update.assert_called_once_with(app)
    app.query_panel._on_use_case_change.assert_called_once()
    app._tuning_panel._sync_sliders_to_config.assert_called_once()
    status_bar.set_ready.assert_called_once()
    status_bar.force_refresh.assert_called_once()


def test_commit_router_and_mode_purges_query_state_and_refreshes_runtime():
    app = SimpleNamespace(
        config=SimpleNamespace(mode="offline"),
        query_engine=MagicMock(),
        query_panel=MagicMock(),
        status_bar=MagicMock(),
    )
    new_router = MagicMock()

    with patch("src.gui.helpers.mode_tuning.apply_mode_settings_to_config") as mock_apply, \
         patch("src.core.query_engine.refresh_query_engine_runtime") as mock_refresh, \
         patch("src.gui.helpers.mode_switch.persist_mode") as mock_persist:
        _commit_router_and_mode(app, new_router, "online")

    assert app.router is new_router
    assert app.query_engine.llm_router is new_router
    assert app.query_engine.config is app.config
    assert app.status_bar.router is new_router
    assert app.config.mode == "online"
    mock_apply.assert_called_once_with(app.config, "online")
    mock_persist.assert_called_once_with(app, "online")
    mock_refresh.assert_called_once_with(app.query_engine, clear_caches=True)
    app.query_panel._purge_mode_state.assert_called_once()
