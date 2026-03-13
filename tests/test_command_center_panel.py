from types import SimpleNamespace
import tkinter as tk
from unittest.mock import MagicMock

import pytest

from src.gui.command_center_registry import get_command_specs
from src.gui.panels.panel_registry import get_panels


def _make_root():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable")
    return root


def _build_fake_app(root, config):
    query_entry = tk.Entry(root)
    query_panel = SimpleNamespace(
        question_entry=query_entry,
        ask_btn=SimpleNamespace(cget=lambda _key: "normal"),
        _on_ask=MagicMock(),
    )
    index_panel = SimpleNamespace(_on_start=MagicMock())
    app = SimpleNamespace(
        query_panel=query_panel,
        index_panel=index_panel,
        config=config,
        show_view=MagicMock(),
        toggle_mode=MagicMock(),
        reload_config=MagicMock(),
    )
    return app


def _select_alias(panel, alias):
    for idx, spec in enumerate(panel._visible_specs):
        if spec.alias == alias:
            panel._select_spec(idx)
            return spec
    raise AssertionError("Alias not found: {}".format(alias))


def test_command_center_registry_covers_primary_cli_aliases():
    aliases = {spec.alias for spec in get_command_specs()}
    expected = {
        "rag-query",
        "rag-index",
        "rag-set-model",
        "rag-mode-offline",
        "rag-mode-online",
        "rag-store-key",
        "rag-store-shared-token",
        "rag-store-endpoint",
        "rag-cred-status",
        "rag-cred-delete",
        "rag-models",
        "rag-test-api",
        "rag-profile",
        "rag-paths",
        "rag-status",
        "rag-shared-launch",
        "rag-diag",
        "rag-server",
        "rag-gui",
    }
    assert expected.issubset(aliases)


def test_command_center_panel_is_registered():
    labels = {panel.label for panel in get_panels()}
    assert "Command Center" in labels


def test_command_center_query_action_prefills_and_routes():
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder=""),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    _select_alias(panel, "rag-query")

    question_widget = panel._field_widgets["question"]
    question_widget.insert("1.0", "What is the frequency range?")
    panel._field_vars["run_now"].set(False)
    panel._execute_selected()

    assert app.show_view.call_args.args[0] == "query"
    assert app.query_panel.question_entry.get() == "What is the frequency range?"

    panel.destroy()
    root.destroy()


def test_command_center_index_action_starts_native_index_panel():
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder=""),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    _select_alias(panel, "rag-index")
    panel._field_vars["start_now"].set(True)
    panel._execute_selected()

    assert app.show_view.call_args.args[0] == "index"
    app.index_panel._on_start.assert_called_once()

    panel.destroy()
    root.destroy()


def test_command_center_status_action_renders_report():
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder="D:\\Docs", download_folder="D:\\Downloads"),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    _select_alias(panel, "rag-status")
    panel._execute_selected()

    output = panel._output.get("1.0", tk.END)
    assert "HybridRAG Status" in output
    assert "Offline model: phi4-mini" in output

    panel.destroy()
    root.destroy()


def test_command_center_model_surface_choice_defaults_to_query_panel():
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder=""),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    _select_alias(panel, "rag-set-model")

    assert panel._field_vars["surface"].get() == "Query Panel"

    panel.destroy()
    root.destroy()


def test_command_center_shared_launch_report_renders(monkeypatch):
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder=""),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    monkeypatch.setattr(
        "src.gui.panels.command_center_panel.build_shared_launch_report",
        lambda **_kwargs: "Shared Launch Preflight\nLaunch ready: False",
    )
    _select_alias(panel, "rag-shared-launch")
    panel._execute_selected()

    output = panel._output.get("1.0", tk.END)
    assert "Shared Launch Preflight" in output

    panel.destroy()
    root.destroy()


def test_command_center_store_shared_token_uses_runtime(monkeypatch):
    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        paths=SimpleNamespace(database="", source_folder=""),
        ollama=SimpleNamespace(model="phi4-mini"),
        api=SimpleNamespace(model="gpt-4o", deployment="gpt-4o"),
    )
    app = _build_fake_app(root, config)

    from src.gui.panels.command_center_panel import CommandCenterPanel

    panel = CommandCenterPanel(root, config=config, app_ref=app)
    monkeypatch.setattr(
        "src.gui.panels.command_center_panel.store_shared_token_from_gui",
        lambda _token, previous=False: "stored previous={}".format(previous),
    )
    _select_alias(panel, "rag-store-shared-token")
    panel._field_vars["shared_token"].set("shared-token")
    panel._field_vars["previous"].set(True)
    panel._execute_selected()

    output = panel._output.get("1.0", tk.END)
    assert "stored previous=True" in output

    panel.destroy()
    root.destroy()
