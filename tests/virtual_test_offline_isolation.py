#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Verifies behavior for the offline isolation area and protects against regressions.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Temporary config roots plus lightweight fake config objects.
# Outputs: PASS/FAIL results for offline/shared path and state isolation.
# Safety notes: Writes only to temp folders under the OS temp directory.
# ============================
# ============================================================================
# HybridRAG3 -- VIRTUAL TEST: Offline/Admin Isolation Harness
# ============================================================================
# FILE: tests/virtual_test_offline_isolation.py
#
# Validates the Sprint 8 isolation boundary:
#   - live offline/admin edits must stay in the offline slot
#   - shared online persisted mode must not be rewritten just to preserve
#     local offline work
#   - live mode churn must restore the matching per-mode path set
#
# INTERNET ACCESS: NONE
# DEPENDENCIES: Python stdlib plus repo-local modules already under test
# ============================================================================

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tests.virtual_test_framework import (
    section,
    test,
    get_report,
    reset_report,
    finish,
    check_python_syntax,
    check_no_non_ascii,
)

from src.core.config import save_config_field
from src.core.config_authority import resolve_runtime_active_mode
from src.core.config_files import load_primary_config_dict
from src.gui.helpers.mode_tuning import ModeTuningStore


reset_report()
report = get_report()
report.change_description = "Sprint 8 offline/admin isolation regression harness"
report.files_modified = [
    "src/core/config_authority.py",
    "src/gui/helpers/mode_tuning.py",
    "src/gui/helpers/mode_switch.py",
    "src/api/routes.py",
    "tests/test_config_authority.py",
    "tests/test_mode_tuning.py",
    "tests/test_fastapi_server.py",
]

ROOT = _project_root
CONFIG_AUTHORITY = ROOT / "src" / "core" / "config_authority.py"
MODE_TUNING = ROOT / "src" / "gui" / "helpers" / "mode_tuning.py"
MODE_SWITCH = ROOT / "src" / "gui" / "helpers" / "mode_switch.py"
API_ROUTES = ROOT / "src" / "api" / "routes.py"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _temp_root() -> str:
    return tempfile.mkdtemp(prefix="hybridrag_offline_isolation_")


def _write_config(root: str) -> None:
    cfg_dir = Path(root) / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text(
        "\n".join(
            [
                "mode: online",
                "modes:",
                "  offline:",
                "    retrieval:",
                "      top_k: 4",
                "      min_score: 0.1",
                "    ollama:",
                "      model: phi4-mini",
                "    query:",
                "      grounding_bias: 8",
                "      allow_open_knowledge: true",
                "    paths:",
                "      source_folder: D:/offline/source",
                "      database: D:/offline/index/hybridrag.sqlite3",
                "      embeddings_cache: D:/offline/index",
                "      download_folder: D:/offline/source",
                "      transfer_source_folder: D:/offline/source",
                "  online:",
                "    retrieval:",
                "      top_k: 6",
                "      min_score: 0.08",
                "    api:",
                "      model: gpt-4o",
                "      deployment: gpt-4o",
                "      endpoint: https://example.invalid",
                "    query:",
                "      grounding_bias: 7",
                "      allow_open_knowledge: true",
                "    paths:",
                "      source_folder: D:/shared/source",
                "      database: D:/shared/index/hybridrag.sqlite3",
                "      embeddings_cache: D:/shared/index",
                "      download_folder: D:/shared/source",
                "      transfer_source_folder: ''",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _set_env(**updates):
    previous = {}
    for key, value in updates.items():
        previous[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return previous


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


section("SIM-01: FILE INTEGRITY (existence, compile, ASCII)")


@test("Isolation files exist")
def _():
    assert CONFIG_AUTHORITY.is_file()
    assert MODE_TUNING.is_file()
    assert MODE_SWITCH.is_file()
    assert API_ROUTES.is_file()


@test("Isolation files compile")
def _():
    for path in (CONFIG_AUTHORITY, MODE_TUNING, MODE_SWITCH, API_ROUTES):
        errors = check_python_syntax(path)
        assert not errors, "; ".join(errors)


@test("Isolation files stay ASCII-clean")
def _():
    for path in (CONFIG_AUTHORITY, MODE_TUNING, MODE_SWITCH, API_ROUTES):
        issues = check_no_non_ascii(path, path.name)
        assert not issues, "; ".join(issues)


section("SIM-02: SOURCE CONTRACTS (live mode routing is wired)")


@test("config_authority tracks HYBRIDRAG_ACTIVE_MODE")
def _():
    code = _read(CONFIG_AUTHORITY)
    assert "HYBRIDRAG_ACTIVE_MODE" in code
    assert "set_runtime_active_mode" in code
    assert 'if key.startswith("paths.")' in code


@test("GUI and API mode commits update the live mode slot")
def _():
    mode_switch_code = _read(MODE_SWITCH)
    api_code = _read(API_ROUTES)
    assert "set_runtime_active_mode(new_mode)" in mode_switch_code
    assert "set_runtime_active_mode(new_mode)" in api_code


section("SIM-03: BEHAVIORAL ISOLATION")


@test("offline-only path and state saves stay in the offline slot")
def _():
    root = _temp_root()
    previous = _set_env(
        HYBRIDRAG_PROJECT_ROOT=root,
        HYBRIDRAG_ACTIVE_MODE="offline",
    )
    try:
        _write_config(root)
        save_config_field("paths.source_folder", "D:/offline/updated_source")
        save_config_field("paths.database", "D:/offline/updated_index/hybridrag.sqlite3")
        save_config_field("retrieval.top_k", 13)
        save_config_field("query.grounding_bias", 2)
        saved = load_primary_config_dict(root, "config.yaml")
        assert saved["mode"] == "online"
        assert saved["modes"]["offline"]["paths"]["source_folder"] == "D:/offline/updated_source"
        assert saved["modes"]["offline"]["paths"]["database"] == "D:/offline/updated_index/hybridrag.sqlite3"
        assert saved["modes"]["offline"]["retrieval"]["top_k"] == 13
        assert saved["modes"]["offline"]["query"]["grounding_bias"] == 2
        assert saved["modes"]["online"]["paths"]["source_folder"] == "D:/shared/source"
    finally:
        _restore_env(previous)
        shutil.rmtree(root, ignore_errors=True)


@test("ModeTuningStore restores per-mode paths during churn")
def _():
    root = _temp_root()
    previous = _set_env(HYBRIDRAG_PROJECT_ROOT=root)
    try:
        _write_config(root)
        cfg = SimpleNamespace(
            mode="offline",
            paths=SimpleNamespace(
                source_folder="",
                database="",
                embeddings_cache="",
                download_folder="",
                transfer_source_folder="",
            ),
            retrieval=SimpleNamespace(
                top_k=5,
                min_score=0.10,
                hybrid_search=True,
                reranker_enabled=False,
                reranker_top_n=20,
            ),
            api=SimpleNamespace(
                context_window=128000,
                max_tokens=1024,
                temperature=0.05,
                top_p=1.0,
                presence_penalty=0.0,
                frequency_penalty=0.0,
                seed=0,
                timeout_seconds=180,
            ),
            ollama=SimpleNamespace(
                context_window=4096,
                num_predict=384,
                temperature=0.05,
                top_p=0.90,
                seed=0,
                timeout_seconds=180,
            ),
            query=SimpleNamespace(
                grounding_bias=8,
                allow_open_knowledge=True,
            ),
        )
        store = ModeTuningStore()
        store.apply_to_config(cfg, "online")
        assert cfg.paths.source_folder == "D:/shared/source"
        assert cfg.paths.database == "D:/shared/index/hybridrag.sqlite3"
        store.apply_to_config(cfg, "offline")
        assert cfg.paths.source_folder == "D:/offline/source"
        assert cfg.paths.database == "D:/offline/index/hybridrag.sqlite3"
        assert cfg.paths.transfer_source_folder == "D:/offline/source"
    finally:
        _restore_env(previous)
        shutil.rmtree(root, ignore_errors=True)


@test("resolve_runtime_active_mode prefers the live env override")
def _():
    previous = _set_env(HYBRIDRAG_ACTIVE_MODE="offline")
    try:
        assert resolve_runtime_active_mode({"mode": "online"}) == "offline"
    finally:
        _restore_env(previous)


finish()
