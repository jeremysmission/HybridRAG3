# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies focused GUI regressions for online model sync and index safety controls.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Lightweight fake config objects and Tk widgets.
# Outputs: Assertions that GUI controls mutate config as intended.
# Safety notes: Uses Tk test mode only; no network or indexing backends.
# ============================

import os
import time
import tkinter as tk
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest


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
