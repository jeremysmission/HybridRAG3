from types import SimpleNamespace
import tkinter as tk

import pytest


def _make_root():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable (Tcl interpreter state)")
    return root


def test_main_boots_gui_without_auto_launching_setup_wizard(monkeypatch):
    import src.gui.launch_gui as launch_gui
    import src.core.boot as boot_module
    import src.core.config as config_module
    import src.gui.app as app_module
    import src.gui.panels.setup_wizard as wizard_module

    events = {
        "backend_started": 0,
        "wizard_launches": 0,
        "mainloop_entered": 0,
    }

    class DummyApp:
        def __init__(self, *, boot_result, config):
            self.boot_result = boot_result
            self.config = config

        def mainloop(self):
            events["mainloop_entered"] += 1

    monkeypatch.setattr(launch_gui, "_sanitize_tk_env", lambda: None)
    monkeypatch.setattr(launch_gui, "_step", lambda _msg: None)
    monkeypatch.setattr(
        boot_module,
        "boot_hybridrag",
        lambda: SimpleNamespace(success=True, errors=[]),
    )
    monkeypatch.setattr(
        config_module,
        "load_config",
        lambda _root: SimpleNamespace(mode="offline"),
    )
    monkeypatch.setattr(wizard_module, "needs_setup", lambda _root: True)
    monkeypatch.setattr(app_module, "HybridRAGApp", DummyApp)
    monkeypatch.setattr(
        launch_gui,
        "_start_backend_thread",
        lambda _app, _logger: events.__setitem__(
            "backend_started", events["backend_started"] + 1
        ),
    )
    monkeypatch.setattr(
        launch_gui,
        "_launch_setup_wizard_after_boot",
        lambda _app, _logger: events.__setitem__(
            "wizard_launches", events["wizard_launches"] + 1
        ),
    )

    launch_gui.main()

    assert events["backend_started"] == 1
    assert events["wizard_launches"] == 0
    assert events["mainloop_entered"] == 1


def test_probe_warnings_do_not_show_startup_popup(monkeypatch):
    import src.gui.launch_gui as launch_gui

    popup_calls = []
    status = {}

    class DummyStatusBar:
        router = None

        def set_init_error(self, error_text):
            status["init_error"] = error_text

        def force_refresh(self):
            status["refreshed"] = True

    class DummyApp:
        def __init__(self):
            self.router = object()
            self.status_bar = DummyStatusBar()

    monkeypatch.setattr(
        "tkinter.messagebox.showwarning",
        lambda title, message: popup_calls.append((title, message)),
    )

    app = DummyApp()
    launch_gui._present_backend_startup_issues(
        app,
        SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        ["Ollama generate probe failed (model 'phi4-mini'): HTTP 500"],
    )

    assert popup_calls == []
    assert status["init_error"].startswith("Ollama generate probe failed")
    assert status["refreshed"] is True


def test_probe_warnings_render_degraded_status_with_real_status_bar(monkeypatch):
    import src.gui.launch_gui as launch_gui
    from src.gui.panels.status_bar import StatusBar

    popup_calls = []
    monkeypatch.setattr(
        "tkinter.messagebox.showwarning",
        lambda title, message: popup_calls.append((title, message)),
    )

    root = _make_root()
    config = SimpleNamespace(
        mode="offline",
        ollama=SimpleNamespace(model="phi4:14b-q4_K_M"),
    )
    router = SimpleNamespace(
        api=None,
        get_status=lambda: {
            "mode": "offline",
            "ollama_available": True,
        },
    )
    bar = StatusBar(root, config=config, router=router)
    bar.pack()

    app = SimpleNamespace(router=router, status_bar=bar)
    launch_gui._present_backend_startup_issues(
        app,
        SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        ["Ollama generate probe failed (model 'phi4:14b-q4_K_M'): HTTP 500"],
    )
    root.update_idletasks()
    root.update()

    assert popup_calls == []
    assert bar.llm_label.cget("text") == "Mode/Selection: OFFLINE | AUTO"
    assert "Backend Health: Warning |" in bar.ollama_label.cget("text")
    assert "phi4:14b-q4_K_M" in bar.ollama_label.cget("text")
    assert "Ollama Ready" not in bar.ollama_label.cget("text")

    bar.stop()
    root.destroy()


def test_blocking_startup_errors_still_show_popup(monkeypatch):
    import src.gui.launch_gui as launch_gui

    popup_calls = []
    status = {}

    class DummyStatusBar:
        router = None

        def set_init_error(self, error_text):
            status["init_error"] = error_text

        def force_refresh(self):
            status["refreshed"] = True

    class DummyApp:
        def __init__(self):
            self.router = None
            self.status_bar = DummyStatusBar()

    monkeypatch.setattr(
        "tkinter.messagebox.showwarning",
        lambda title, message: popup_calls.append((title, message)),
    )

    app = DummyApp()
    launch_gui._present_backend_startup_issues(
        app,
        SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        ["Database: missing path", "Ollama generate probe failed (model 'phi4-mini'): HTTP 500"],
    )

    assert len(popup_calls) == 1
    assert popup_calls[0][0] == "Backend Init Errors"
    assert "Database: missing path" in popup_calls[0][1]
    assert "Ollama generate probe failed" not in popup_calls[0][1]
    assert status["init_error"] == "Database: missing path"
    assert status["refreshed"] is True


def test_probe_does_not_mutate_phi4_14b_to_phi4_mini():
    import src.gui.launch_gui as launch_gui

    class DummyResponse:
        def raise_for_status(self):
            raise RuntimeError("HTTP 500")

    class DummyClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, timeout=None):
            self.calls.append({"url": url, "json": json, "timeout": timeout})
            if url.endswith("/api/embed"):
                return SimpleNamespace(raise_for_status=lambda: None)
            return DummyResponse()

    client = DummyClient()
    config = SimpleNamespace(
        embedding=SimpleNamespace(model_name="nomic-embed-text"),
        ollama=SimpleNamespace(
            model="phi4:14b-q4_K_M",
            timeout_seconds=180,
            keep_alive=-1,
            context_window=4096,
        ),
    )
    router = SimpleNamespace(
        ollama=SimpleNamespace(
            is_available=lambda: True,
            base_url="http://127.0.0.1:11434",
            _client=client,
        )
    )

    errors = launch_gui._probe_ollama_runtime(
        router,
        config,
        SimpleNamespace(debug=lambda *_args, **_kwargs: None),
    )

    assert config.ollama.model == "phi4:14b-q4_K_M"
    assert any("Ollama generate probe failed" in error for error in errors)
