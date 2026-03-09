# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies focused GUI regressions for online model sync and index safety controls.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake config objects and Tk widgets.
# Outputs: Assertions that GUI controls mutate config as intended.
# Safety notes: Uses Tk test mode only; no network or indexing backends.
# ============================

import os
import shutil
import tempfile
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml


@dataclass
class _FakePathsConfig:
    database: str = ""
    embeddings_cache: str = ""
    source_folder: str = ""


@dataclass
class _FakeAPIConfig:
    endpoint: str = ""
    model: str = ""
    deployment: str = ""


@dataclass
class _FakeConfig:
    paths: _FakePathsConfig = field(default_factory=_FakePathsConfig)
    api: _FakeAPIConfig = field(default_factory=_FakeAPIConfig)


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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


def _make_local_temp_root() -> str:
    base = Path(".tmp_pytest_gui_mode").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix="gui_mode_", dir=str(base))


def test_online_model_selection_updates_model_and_deployment():
    root = _make_root()
    config = _FakeConfig()

    endpoint_var = tk.StringVar(master=root, value="https://openrouter.ai/api/v1")
    key_var = tk.StringVar(master=root, value="sk-test")

    from src.gui.panels.api_admin_tab import ModelSelectionPanel

    panel = ModelSelectionPanel(root, config, endpoint_var, key_var)
    panel.pack()
    panel.set_models([
        {
            "id": "gpt-4o",
            "tier_eng": 93,
            "tier_gen": 95,
            "ctx": 128000,
            "price_in": 2.5,
            "price_out": 10.0,
        }
    ])
    _pump_events(root)

    panel.tree.selection_set("gpt-4o")
    panel._on_select()

    assert config.api.model == "gpt-4o"
    assert config.api.deployment == "gpt-4o"

    panel.destroy()
    root.destroy()


def test_query_panel_manual_online_selection_persists_mode_store():
    from src.gui.panels.query_panel_model_selection_runtime import _on_model_select

    router_cfg = SimpleNamespace(api=SimpleNamespace(model="", deployment=""))
    api_router = SimpleNamespace(deployment="", config=router_cfg)
    fake_self = SimpleNamespace(
        config=SimpleNamespace(
            mode="online",
            api=SimpleNamespace(model="", deployment=""),
            ollama=SimpleNamespace(model="phi4-mini"),
        ),
        model_var=_Var("Online: gpt-4o"),
        query_engine=SimpleNamespace(llm_router=SimpleNamespace(api=api_router)),
        model_info_var=_Var(),
        _model_auto=True,
        _update_model_info=lambda *_args, **_kwargs: None,
    )

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            _on_model_select(fake_self)

        assert fake_self.config.api.model == "gpt-4o"
        assert fake_self.config.api.deployment == "gpt-4o"
        assert api_router.deployment == "gpt-4o"
        assert api_router.config.api.model == "gpt-4o"
        assert api_router.config.api.deployment == "gpt-4o"

        saved = yaml.safe_load(
            (Path(temp_root) / "config" / "config.yaml").read_text(encoding="utf-8")
        )
        assert saved["modes"]["online"]["api"]["model"] == "gpt-4o"
        assert saved["modes"]["online"]["api"]["deployment"] == "gpt-4o"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_query_panel_manual_offline_selection_persists_canonical_model():
    from src.gui.panels.query_panel_model_selection_runtime import _on_model_select

    fake_self = SimpleNamespace(
        config=SimpleNamespace(
            mode="offline",
            api=SimpleNamespace(model="", deployment=""),
            ollama=SimpleNamespace(model="phi4-mini"),
        ),
        model_var=_Var("phi4:14b"),
        query_engine=None,
        model_info_var=_Var(),
        _model_auto=True,
        _update_model_info=lambda *_args, **_kwargs: None,
    )

    temp_root = _make_local_temp_root()
    try:
        with patch.dict(os.environ, {"HYBRIDRAG_PROJECT_ROOT": temp_root}):
            _on_model_select(fake_self)

        assert fake_self.config.ollama.model == "phi4:14b-q4_K_M"

        saved = yaml.safe_load(
            (Path(temp_root) / "config" / "config.yaml").read_text(encoding="utf-8")
        )
        assert saved["modes"]["offline"]["ollama"]["model"] == "phi4:14b-q4_K_M"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_index_clear_starts_locked_and_requires_explicit_unlock():
    with patch.dict(os.environ, {"HYBRIDRAG_DEV_UI": "1"}):
        root = _make_root()
        config = _FakeConfig()

        from src.gui.panels.index_panel import IndexPanel

        panel = IndexPanel(root, config=config)
        panel.pack()

        assert hasattr(panel, "clear_btn")
        assert str(panel.clear_btn["state"]) == "disabled"

        panel._clear_armed_var.set(True)
        panel._on_toggle_clear_guard()
        assert str(panel.clear_btn["state"]) == "normal"

        panel._reset_clear_guard()
        assert str(panel.clear_btn["state"]) == "disabled"

        panel.destroy()
        root.destroy()
