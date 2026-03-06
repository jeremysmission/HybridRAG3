# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies mode-switch runtime refresh behavior and protects against stale tuning UI.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake app objects with mocked panels/status bar.
# Outputs: Assertions that the active tuning panel is refreshed after a mode switch.
# Safety notes: No Tk mainloop or I/O required.
# ============================

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.gui.helpers.mode_switch import _finish_switch


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
