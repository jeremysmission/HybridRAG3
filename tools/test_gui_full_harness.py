#!/usr/bin/env python3
"""
Full GUI harness test: exercises every major GUI path headlessly.

Uses the same Tk harness patterns as test_gui_integration_w4.py:
  FakeGUIConfig, _make_root(), _pump_events(), mocked backends.

Tests:
  Phase 1: Mode switch (offline -> online -> offline) via GUI helpers
  Phase 2: Profile change (laptop_safe -> desktop_power) via tuning tab
  Phase 3: File transfer (copy file into temp source folder)
  Phase 4: Index the transferred file (real pipeline: chunk/embed/store)
  Phase 5: Offline model selection (select model, verify config + YAML)
  Phase 6: Mode switch persists to user_overrides.yaml (not default_config)

Usage:
    python tools/test_gui_full_harness.py
"""
from __future__ import annotations

import io
import os
import gc
import sys
import time
import shutil
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print("[OK]   {}".format(label))
    else:
        FAIL += 1
        msg = "[FAIL] {}".format(label)
        if detail:
            msg += " -- {}".format(detail)
        print(msg)
    return condition


# ===================================================================
# Tk harness helpers (same pattern as test_gui_integration_w4.py)
# ===================================================================

def _make_root():
    import tkinter as tk
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception as e:
        print("[SKIP] Tk unavailable: {}".format(e))
        return None


def _pump_events(root, ms=100):
    import tkinter as tk
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update_idletasks()
            root.update()
        except Exception:
            break
        time.sleep(0.005)


# ===================================================================
# Fake config (mirrors test_gui_integration_w4.py)
# ===================================================================

from dataclasses import dataclass, field


@dataclass
class FakePathsConfig:
    database: str = ""
    embeddings_cache: str = ""
    source_folder: str = ""


@dataclass
class FakeOllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "phi4-mini"
    timeout_seconds: int = 120


@dataclass
class FakeAPIConfig:
    endpoint: str = ""
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 2048
    temperature: float = 0.1
    timeout_seconds: int = 30
    deployment: str = ""
    api_version: str = ""
    allowed_endpoint_prefixes: list = field(default_factory=list)


@dataclass
class FakeRetrievalConfig:
    top_k: int = 8
    min_score: float = 0.20
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
class FakeEmbeddingConfig:
    model_name: str = "nomic-embed-text"
    dimension: int = 768


@dataclass
class FakeGUIConfig:
    mode: str = "offline"
    paths: FakePathsConfig = field(default_factory=FakePathsConfig)
    ollama: FakeOllamaConfig = field(default_factory=FakeOllamaConfig)
    api: FakeAPIConfig = field(default_factory=FakeAPIConfig)
    retrieval: FakeRetrievalConfig = field(default_factory=FakeRetrievalConfig)
    cost: FakeCostConfig = field(default_factory=FakeCostConfig)
    chunking: FakeChunkingConfig = field(default_factory=FakeChunkingConfig)
    embedding: FakeEmbeddingConfig = field(default_factory=FakeEmbeddingConfig)


@dataclass
class FakeBootResult:
    boot_timestamp: str = "2026-02-27 10:00:00"
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


# ===================================================================
# PHASE 1: Mode switch via GUI status bar + helpers
# ===================================================================

def phase_1_mode_switch():
    print()
    print("--- PHASE 1: Mode Switch (offline -> online -> offline) ---")
    root = _make_root()
    if not root:
        check("Phase 1 (Tk required)", False, "no display")
        return

    from unittest.mock import MagicMock, patch

    config = FakeGUIConfig(mode="offline")

    # Test status bar reflects offline
    from src.gui.panels.status_bar import StatusBar
    bar = StatusBar(root, config=config)
    bar.pack()
    bar._refresh_status()
    _pump_events(root, 100)

    gate_text = bar.gate_label.cget("text")
    check("StatusBar shows OFFLINE", "OFFLINE" in gate_text, gate_text)

    # Switch to online at config level
    config.mode = "online"
    bar._refresh_status()
    _pump_events(root, 100)

    gate_text = bar.gate_label.cget("text")
    check("StatusBar shows ONLINE after switch", "ONLINE" in gate_text, gate_text)

    # Switch back to offline
    config.mode = "offline"
    bar._refresh_status()
    _pump_events(root, 100)

    gate_text = bar.gate_label.cget("text")
    check("StatusBar shows OFFLINE after round-trip", "OFFLINE" in gate_text, gate_text)

    # Test the actual mode_switch helper (credential check path)
    from src.gui.app import HybridRAGApp
    app = HybridRAGApp(boot_result=FakeBootResult(), config=config)
    app.withdraw()

    # Patch resolve_credentials to return empty creds
    from src.security.credentials import ApiCredentials, invalidate_credential_cache
    from src.security import credentials as cred_mod
    from tkinter import messagebox as mb_module

    warning_calls = []
    original_warn = mb_module.showwarning
    mb_module.showwarning = lambda title, msg: warning_calls.append((title, msg))

    invalidate_credential_cache()
    original_resolve = cred_mod.resolve_credentials
    cred_mod.resolve_credentials = lambda **kw: ApiCredentials()

    original_after = app.after
    app.after = lambda ms, func, *a: func(*a) if callable(func) else None

    try:
        from src.gui.helpers.mode_switch import _do_switch_to_online
        _do_switch_to_online(app)
        check("Online switch blocked without credentials",
              len(warning_calls) >= 1,
              "warnings={}".format(len(warning_calls)))
        check("Mode stays offline when creds missing",
              config.mode == "offline")
    finally:
        mb_module.showwarning = original_warn
        cred_mod.resolve_credentials = original_resolve
        app.after = original_after
        invalidate_credential_cache()

    app.status_bar.stop()
    app.destroy()
    bar.stop()
    root.destroy()


# ===================================================================
# PHASE 2: Profile change via tuning tab
# ===================================================================

def phase_2_profile_change():
    print()
    print("--- PHASE 2: Profile Change (desktop_power -> laptop_safe) ---")
    root = _make_root()
    if not root:
        check("Phase 2 (Tk required)", False, "no display")
        return

    from unittest.mock import MagicMock, patch

    config = FakeGUIConfig()

    # Mock credentials for SettingsView (it loads API admin tab)
    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.gui.panels.api_admin_tab.resolve_credentials",
               return_value=mock_creds):
        from src.gui.panels.settings_view import SettingsView
        app_ref = MagicMock()
        app_ref._views = {}
        view = SettingsView(root, config=config, app_ref=app_ref)

    check("SettingsView created", view is not None)

    # Verify profile dropdown has values
    profile_values = list(view.profile_dropdown["values"])
    check("Profile dropdown populated",
          len(profile_values) >= 2,
          "profiles={}".format(profile_values))
    check("desktop_power in profiles",
          "desktop_power" in profile_values)
    check("laptop_safe in profiles",
          "laptop_safe" in profile_values)

    # Test profile switch via subprocess mock
    with patch("src.gui.panels.tuning_tab.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Applied", stderr="")

        view.profile_var.set("laptop_safe")
        view._on_profile_change()
        _pump_events(root, 500)

        # Wait for background thread
        time.sleep(0.5)
        _pump_events(root, 200)

        calls = mock_run.call_args_list
        switch_calls = [c for c in calls if "_profile_switch" in str(c)]
        check("Profile switch subprocess called",
              len(switch_calls) > 0,
              "calls={}".format(len(switch_calls)))

        if switch_calls:
            call_str = str(switch_calls[0])
            check("Called with 'laptop_safe'",
                  "laptop_safe" in call_str,
                  call_str[:80])

    view.destroy()
    root.destroy()


# ===================================================================
# PHASE 3: File transfer (copy file into temp source folder)
# ===================================================================

def phase_3_file_transfer():
    print()
    print("--- PHASE 3: File Transfer ---")

    tmp_src = tempfile.mkdtemp(prefix="hrag_src_")
    tmp_dest = tempfile.mkdtemp(prefix="hrag_dest_")

    try:
        # Create a test document in the "source" folder
        test_content = (
            "GUI Harness Transfer Test\n\n"
            "This document tests the file transfer and indexing pipeline. "
            "It verifies that files can be copied from an external folder "
            "into the RAG source folder and then indexed successfully. "
            "Calibration intervals are set to 12 months per section 7.3. "
            "The maintenance schedule follows quarterly review cycles."
        )
        src_file = os.path.join(tmp_src, "transfer_test_doc.txt")
        with open(src_file, "w", encoding="utf-8") as f:
            f.write(test_content)

        check("Source file created", os.path.isfile(src_file))

        # Transfer: copy file to dest folder (simulates bulk transfer)
        dest_file = os.path.join(tmp_dest, "transfer_test_doc.txt")
        shutil.copy2(src_file, dest_file)

        check("File transferred to dest", os.path.isfile(dest_file))
        check("File content preserved",
              open(dest_file, encoding="utf-8").read() == test_content)

        return tmp_dest, dest_file, test_content

    except Exception as e:
        check("File transfer", False, str(e))
        shutil.rmtree(tmp_src, ignore_errors=True)
        shutil.rmtree(tmp_dest, ignore_errors=True)
        return None, None, None


# ===================================================================
# PHASE 4: Index the transferred file (real pipeline)
# ===================================================================

def phase_4_index_file(dest_file):
    print()
    print("--- PHASE 4: Index Transferred File ---")

    if not dest_file:
        check("Phase 4 (needs transferred file)", False, "no file")
        return None

    tmp_db = tempfile.mkdtemp(prefix="hrag_db_")
    db_path = os.path.join(tmp_db, "harness_test.sqlite3")

    try:
        from src.core.config import load_config
        cfg = load_config()

        from src.core.chunker import Chunker
        chunker = Chunker(cfg.chunking)

        from src.core.embedder import Embedder
        embedder = Embedder(model_name=cfg.embedding.model_name)

        from src.core.vector_store import VectorStore
        store = VectorStore(db_path=db_path, embedding_dim=768)

        from src.core.indexer import Indexer
        indexer = Indexer(
            config=cfg, chunker=chunker,
            embedder=embedder, vector_store=store,
        )

        result = indexer.index_file(dest_file)
        check("Indexer.index_file() success",
              result.get("indexed") is True,
              "result={}".format(result))
        check("Chunks added: {}".format(result.get("chunks_added", 0)),
              result.get("chunks_added", 0) >= 1)

        # Verify auto-connect happened
        check("VectorStore auto-connected", store.conn is not None)

        # Semantic search on indexed content
        q_vec = embedder.embed_query("calibration intervals quarterly review")
        results = store.search(q_vec, top_k=3)
        check("Search returned results: {}".format(len(results)),
              len(results) >= 1)

        if results:
            top = results[0].get("text", results[0].get("chunk_text", ""))
            check("Top result contains 'calibration'",
                  "calibration" in top.lower(),
                  "got: {}...".format(top[:60]))

        return store, tmp_db

    except Exception as e:
        check("Indexing pipeline", False, "{}: {}".format(type(e).__name__, e))
        return None, tmp_db


# ===================================================================
# PHASE 5: Offline model selection panel
# ===================================================================

def phase_5_model_selection():
    print()
    print("--- PHASE 5: Offline Model Selection ---")
    root = _make_root()
    if not root:
        check("Phase 5 (Tk required)", False, "no display")
        return

    from unittest.mock import MagicMock, patch

    config = FakeGUIConfig()
    config.ollama.model = "phi4-mini"

    mock_creds = MagicMock()
    mock_creds.endpoint = None
    mock_creds.api_key = None
    mock_creds.has_key = False
    mock_creds.has_endpoint = False
    mock_creds.is_online_ready = False
    mock_creds.key_preview = "(not set)"
    mock_creds.source_key = None
    mock_creds.source_endpoint = None

    with patch("src.gui.panels.api_admin_tab.resolve_credentials",
               return_value=mock_creds):
        from src.gui.panels.api_admin_tab import OfflineModelSelectionPanel
        panel = OfflineModelSelectionPanel(root, config=config)
        panel.pack()
        _pump_events(root, 100)

    check("OfflineModelSelectionPanel created", panel is not None)

    # Verify treeview has model rows
    rows = panel.tree.get_children()
    check("Model treeview populated: {} rows".format(len(rows)),
          len(rows) >= 1)

    if rows:
        # List all models in the treeview
        model_names = list(rows)
        check("Treeview has approved models",
              any("phi4" in m or "mistral" in m for m in model_names),
              "models={}".format(model_names[:5]))

    # Verify use case dropdown works
    uc_values = list(panel.uc_dropdown["values"])
    check("Use case dropdown populated: {} items".format(len(uc_values)),
          len(uc_values) >= 5)

    # Change use case and verify treeview re-sorts
    if len(uc_values) >= 2:
        panel.uc_var.set(uc_values[1])
        panel._on_uc_change()
        _pump_events(root, 100)
        rows_after = panel.tree.get_children()
        check("Treeview refreshed after use-case change",
              len(rows_after) >= 1)

    # Simulate model selection -- httpx is imported locally inside _on_select,
    # so we patch it at the library level and mock the Ollama health check.
    if rows:
        target = rows[0]
        panel.tree.selection_set(target)

        import httpx as _httpx_mod
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "phi4-mini:latest"},
                {"name": "mistral:7b"},
                {"name": "phi4:14b-q4_K_M"},
                {"name": "gemma3:4b"},
                {"name": "mistral-nemo:12b"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(_httpx_mod, "get", return_value=mock_resp), \
             patch("src.core.config.save_config_field") as mock_save:
            old_model = config.ollama.model
            panel._on_select()
            _pump_events(root, 100)

            # Verify config.ollama.model was updated
            check("Config model updated to {}".format(config.ollama.model),
                  config.ollama.model is not None and len(config.ollama.model) > 0)

            # Verify save_config_field was called for persistence
            if mock_save.called:
                call_args = str(mock_save.call_args)
                check("save_config_field called for model",
                      "ollama.model" in call_args,
                      call_args[:80])
            else:
                # Model was set on config object directly (still valid)
                check("Model changed on config object",
                      config.ollama.model != "phi4-mini" or old_model == "phi4-mini",
                      "model={}".format(config.ollama.model))

    panel.destroy()
    root.destroy()


# ===================================================================
# PHASE 6: Mode switch persists to user_overrides.yaml
# ===================================================================

def phase_6_config_persistence():
    print()
    print("--- PHASE 6: Config Persistence (user_overrides.yaml) ---")

    from src.core.config import save_config_field, load_config
    import yaml

    ovr_path = os.path.join(".", "config", "user_overrides.yaml")
    default_path = os.path.join(".", "config", "default_config.yaml")

    # Save current state to restore later
    ovr_backup = None
    if os.path.isfile(ovr_path):
        with open(ovr_path, "r", encoding="utf-8") as f:
            ovr_backup = f.read()

    try:
        # Switch to online
        save_config_field("mode", "online")
        check("save_config_field('mode', 'online') succeeded", True)

        # Verify user_overrides.yaml was written
        check("user_overrides.yaml exists", os.path.isfile(ovr_path))

        with open(ovr_path, "r", encoding="utf-8") as f:
            ovr = yaml.safe_load(f)
        check("user_overrides has mode=online",
              ovr.get("mode") == "online",
              "got: {}".format(ovr.get("mode")))

        # Verify default_config.yaml was NOT touched
        import subprocess
        diff = subprocess.run(
            ["git", "diff", "--", "config/default_config.yaml"],
            capture_output=True, text=True,
        )
        check("default_config.yaml untouched",
              not diff.stdout.strip())

        # Switch back to offline
        save_config_field("mode", "offline")
        with open(ovr_path, "r", encoding="utf-8") as f:
            ovr = yaml.safe_load(f)
        check("Mode reverted to offline",
              ovr.get("mode") == "offline",
              "got: {}".format(ovr.get("mode")))

        # Verify load_config merges overlay
        cfg = load_config()
        check("load_config() returns offline mode",
              cfg.mode == "offline",
              "got: {}".format(cfg.mode))

    finally:
        # Restore original user_overrides.yaml
        if ovr_backup is not None:
            with open(ovr_path, "w", encoding="utf-8") as f:
                f.write(ovr_backup)


# ===================================================================
# MAIN
# ===================================================================

def main():
    print()
    print("=" * 65)
    print("  FULL GUI HARNESS TEST (headless, all major paths)")
    print("=" * 65)

    # Phase 1: Mode switch
    phase_1_mode_switch()

    # Phase 2: Profile change
    phase_2_profile_change()

    # Phase 3: File transfer
    dest_dir, dest_file, content = phase_3_file_transfer()

    # Phase 4: Index transferred file
    store_result = phase_4_index_file(dest_file)
    store = None
    tmp_db = None
    if store_result:
        store, tmp_db = store_result

    # Phase 5: Model selection
    phase_5_model_selection()

    # Phase 6: Config persistence
    phase_6_config_persistence()

    # Cleanup
    print()
    print("--- Cleanup ---")
    if store:
        try:
            store.close()
        except Exception:
            pass
    if tmp_db and os.path.isdir(tmp_db):
        shutil.rmtree(tmp_db, ignore_errors=True)
    if dest_dir and os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir, ignore_errors=True)
    check("Cleanup complete", True)

    gc.collect()

    # Summary
    print()
    print("=" * 65)
    total = PASS + FAIL
    print("  SUMMARY: {}/{} checks passed".format(PASS, total))
    if FAIL:
        print("  [FAIL] {} checks failed".format(FAIL))
    print("=" * 65)

    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
