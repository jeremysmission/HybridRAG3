# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies mode-switch runtime refresh behavior and protects against stale tuning UI.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake app objects with mocked panels/status bar.
# Outputs: Assertions that the active tuning panel is refreshed after a mode switch.
# Safety notes: No Tk mainloop or I/O required.
# ============================

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.gui.app_runtime import reset_backends
from src.gui.helpers.mode_switch import _commit_router_and_mode, _finish_switch, persist_mode
from src.gui.panels.query_panel_query_flow_runtime import _resolve_query_engine


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


def test_commit_router_and_mode_repeated_churn_clears_stale_router_state():
    config = SimpleNamespace(mode="offline")
    retriever = SimpleNamespace(config=None)
    query_engine = SimpleNamespace(
        config=config,
        llm_router=SimpleNamespace(last_error="old"),
        retriever=retriever,
    )
    app = SimpleNamespace(
        config=config,
        query_engine=query_engine,
        query_panel=MagicMock(),
        status_bar=MagicMock(),
    )

    with patch("src.gui.helpers.mode_tuning.apply_mode_settings_to_config") as mock_apply, \
         patch("src.gui.helpers.mode_switch.persist_mode") as mock_persist:
        for mode in ("online", "offline", "online", "offline"):
            router = SimpleNamespace(
                config=config,
                last_error="stale",
                ollama=SimpleNamespace(last_error="ollama stale"),
                api=SimpleNamespace(last_error="api stale"),
                vllm=SimpleNamespace(last_error="vllm stale"),
            )
            _commit_router_and_mode(app, router, mode)

            assert app.router is router
            assert app.query_engine.llm_router is router
            assert app.query_engine.config is config
            assert app.status_bar.router is router
            assert app.config.mode == mode
            assert retriever.config is config
            assert router.last_error == ""
            assert router.ollama.last_error == ""
            assert router.api.last_error == ""
            assert router.vllm.last_error == ""
            assert app.query_panel.query_engine is query_engine

    assert mock_apply.call_count == 4
    assert mock_persist.call_count == 4
    assert app.query_panel._purge_mode_state.call_count == 4


def test_commit_router_and_mode_sets_live_mode_env():
    app = SimpleNamespace(
        config=SimpleNamespace(mode="offline"),
        query_engine=MagicMock(),
        query_panel=MagicMock(),
        status_bar=MagicMock(),
    )

    with patch.dict(os.environ, {}, clear=False), \
         patch("src.gui.helpers.mode_tuning.apply_mode_settings_to_config"), \
         patch("src.core.query_engine.refresh_query_engine_runtime"), \
         patch("src.gui.helpers.mode_switch.persist_mode"):
        _commit_router_and_mode(app, MagicMock(), "online")
        assert os.environ["HYBRIDRAG_ACTIVE_MODE"] == "online"

        _commit_router_and_mode(app, MagicMock(), "offline")
        assert os.environ["HYBRIDRAG_ACTIVE_MODE"] == "offline"


def test_persist_mode_skips_offline_write_when_shared_boundary_is_active():
    app = SimpleNamespace(
        config=SimpleNamespace(
            security=SimpleNamespace(deployment_mode="production"),
        ),
    )

    with patch.dict(os.environ, {"HYBRIDRAG_API_AUTH_TOKEN": "", "HYBRIDRAG_DEPLOYMENT_MODE": ""}, clear=False), \
         patch("src.core.config.save_config_field") as mock_save:
        persist_mode(app, "offline")

    mock_save.assert_not_called()


def test_persist_mode_still_saves_online_write_when_shared_boundary_is_active():
    app = SimpleNamespace(
        config=SimpleNamespace(
            security=SimpleNamespace(deployment_mode="production"),
        ),
    )

    with patch.dict(os.environ, {"HYBRIDRAG_API_AUTH_TOKEN": "test-token", "HYBRIDRAG_DEPLOYMENT_MODE": ""}, clear=False), \
         patch("src.core.config.save_config_field") as mock_save:
        persist_mode(app, "online")

    mock_save.assert_called_once_with("mode", "online")


def test_persist_mode_keeps_offline_write_in_open_local_mode():
    app = SimpleNamespace(
        config=SimpleNamespace(
            security=SimpleNamespace(deployment_mode="development"),
        ),
    )

    with patch.dict(os.environ, {"HYBRIDRAG_API_AUTH_TOKEN": "", "HYBRIDRAG_DEPLOYMENT_MODE": ""}, clear=False), \
         patch("src.core.config.save_config_field") as mock_save:
        persist_mode(app, "offline")

    mock_save.assert_called_once_with("mode", "offline")


def test_persist_mode_skips_offline_write_when_keyring_backed_boundary_is_active():
    app = SimpleNamespace(
        config=SimpleNamespace(
            security=SimpleNamespace(deployment_mode="development"),
        ),
    )

    with patch(
        "src.security.shared_deployment_auth.shared_online_enforced",
        return_value=True,
    ), patch("src.core.config.save_config_field") as mock_save:
        persist_mode(app, "offline")

    mock_save.assert_not_called()


def test_resolve_query_engine_heals_stale_panel_reference_after_mode_churn():
    current_engine = SimpleNamespace(name="engine1")
    app = SimpleNamespace(query_engine=current_engine)
    panel = SimpleNamespace(query_engine=None, winfo_toplevel=lambda: app)

    assert _resolve_query_engine(panel) is current_engine
    assert panel.query_engine is current_engine

    next_engine = SimpleNamespace(name="engine2")
    app.query_engine = next_engine
    panel.query_engine = None

    assert _resolve_query_engine(panel) is next_engine
    assert panel.query_engine is next_engine


def test_reset_backends_starts_reload_thread_and_clears_runtime_refs():
    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target = target
            self._args = args
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            if self._target is not None:
                self._target(*self._args)

        def is_alive(self):
            return False

    query_panel = MagicMock()
    index_panel = MagicMock()
    status_bar = MagicMock()
    status_bar._init_error = "old warning"
    shutdown = MagicMock()
    app = SimpleNamespace(
        query_engine=MagicMock(),
        indexer=MagicMock(),
        router=MagicMock(),
        query_panel=query_panel,
        index_panel=index_panel,
        status_bar=status_bar,
        shutdown=shutdown,
        _backend_reload_thread=None,
    )

    with patch("src.gui.app_runtime.threading.Thread", ImmediateThread), \
         patch("src.gui.launch_gui._load_backends") as mock_load:
        reset_backends(app)

    assert app.query_engine is None
    assert app.indexer is None
    assert app.router is None
    assert query_panel.query_engine is None
    assert index_panel.indexer is None
    assert status_bar.router is None
    assert status_bar._init_error is None
    assert app._backend_reload_thread.started is True
    query_panel.set_ready.assert_called_once_with(False)
    index_panel.set_ready.assert_called_once_with(False)
    status_bar.set_loading_stage.assert_called_once_with("Restarting...")
    status_bar.force_refresh.assert_called_once()
    shutdown.register_thread.assert_called_once_with(
        "backend_reload",
        app._backend_reload_thread,
    )
    mock_load.assert_called_once()
