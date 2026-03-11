# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies the shipped index-panel hotfix behaviors without depending
# on the broader GUI integration worktree.
# ============================

import os
import sys
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class FakePathsConfig:
    database: str = ""
    embeddings_cache: str = ""
    source_folder: str = ""


@dataclass
class FakeGUIConfig:
    mode: str = "offline"
    paths: FakePathsConfig = field(default_factory=FakePathsConfig)


def _make_root():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable (Tcl interpreter state)")
    return root


def test_index_panel_change_index_updates_config(tmp_path):
    root = _make_root()
    config = FakeGUIConfig()
    index_dir = tmp_path / "index_data"
    index_dir.mkdir()

    from src.gui.panels.index_panel import IndexPanel

    panel = IndexPanel(root, config=config)
    panel.pack()

    with patch(
        "src.gui.panels.index_panel.filedialog.askdirectory",
        return_value=str(index_dir),
    ), patch("src.gui.panels.index_panel.save_config_field") as mock_save:
        panel._on_change_index()

    expected_db = os.path.join(str(index_dir), "hybridrag.sqlite3")
    expected_embeddings = os.path.join(str(index_dir), "_embeddings")

    assert panel.index_var.get() == os.path.normpath(str(index_dir))
    assert config.paths.database == expected_db
    assert config.paths.embeddings_cache == expected_embeddings
    mock_save.assert_any_call("paths.database", expected_db)
    mock_save.assert_any_call("paths.embeddings_cache", expected_embeddings)

    root.destroy()


def test_index_panel_rejects_double_start(tmp_path):
    root = _make_root()
    config = FakeGUIConfig(paths=FakePathsConfig(source_folder=str(tmp_path)))

    from src.gui.panels.index_panel import IndexPanel

    panel = IndexPanel(root, config=config)
    panel.pack()
    panel.indexer = object()
    panel.folder_var.set(str(tmp_path))
    panel.is_indexing = True

    panel._on_start()

    assert "already running" in panel.progress_file_label.cget("text").lower()

    root.destroy()
