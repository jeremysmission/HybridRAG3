from types import SimpleNamespace


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
