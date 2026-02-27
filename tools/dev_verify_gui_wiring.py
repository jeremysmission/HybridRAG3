#!/usr/bin/env python3
"""
Dev-only GUI wiring verification script.

Checks that all critical GUI components import, construct, and wire
correctly without launching a Tk window.  Run after any change to
launch_gui.py, panels, config, or panel_registry.

Usage:
    python tools/dev_verify_gui_wiring.py

Exit code 0 = all checks pass.
Exit code 1 = at least one check failed.
"""

from __future__ import annotations

import sys
import io
import inspect

# Windows stdout encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

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


def main():
    # 1. Config loads and default model is desktop-class
    try:
        from src.core.config import load_config
        cfg = load_config()
        model = cfg.ollama.model
        check("Config ollama.model = {}".format(model),
              "phi4:14b" in model or "phi4-mini" not in model,
              "expected desktop-class model")
    except Exception as e:
        check("Config load", False, str(e))

    # 2. Chunker constructs from config.chunking
    try:
        from src.core.chunker import Chunker
        ch = Chunker(cfg.chunking)
        check("Chunker(config.chunking) chunk_size={}".format(ch.chunk_size),
              ch.chunk_size > 0)
    except Exception as e:
        check("Chunker construction", False, str(e))

    # 3. launch_gui uses config.chunking (not bare config)
    try:
        import src.gui.launch_gui as lg
        src_code = inspect.getsource(lg._load_backends)
        check("launch_gui Chunker call uses config.chunking",
              "config.chunking" in src_code,
              "found Chunker(config) instead of Chunker(config.chunking)")
    except Exception as e:
        check("launch_gui source inspection", False, str(e))

    # 4. Panel registry includes data and index
    try:
        from src.gui.panels.panel_registry import get_panels
        panels = get_panels()
        keys = [p.key for p in panels]
        check("Panel registry has 'data'", "data" in keys,
              "registered: {}".format(keys))
        check("Panel registry has 'index'", "index" in keys,
              "registered: {}".format(keys))
    except Exception as e:
        check("Panel registry", False, str(e))

    # 5. Critical panel imports
    try:
        from src.gui.panels.index_panel import IndexPanel
        check("IndexPanel imports", True)
    except Exception as e:
        check("IndexPanel import", False, str(e))

    try:
        from src.gui.panels.data_panel import DataPanel
        check("DataPanel imports", True)
    except Exception as e:
        check("DataPanel import", False, str(e))

    try:
        from src.gui.panels.api_admin_tab import OfflineModelSelectionPanel
        check("OfflineModelSelectionPanel imports", True)
    except Exception as e:
        check("OfflineModelSelectionPanel import", False, str(e))

    # 6. Profile system
    try:
        from scripts._model_meta import RECOMMENDED_OFFLINE, WORK_ONLY_MODELS
        sw = RECOMMENDED_OFFLINE.get("sw", {})
        check("SW profile primary = {}".format(sw.get("primary", "?")),
              "phi4:14b" in sw.get("primary", ""))
        check("WORK_ONLY_MODELS count = {}".format(len(WORK_ONLY_MODELS)),
              len(WORK_ONLY_MODELS) >= 5)
    except Exception as e:
        check("Profile system", False, str(e))

    # 7. VLLMConfig default
    try:
        from src.core.config import VLLMConfig
        vl = VLLMConfig()
        check("VLLMConfig default model = {}".format(vl.model),
              "phi4:14b" in vl.model or vl.model == "")
    except Exception as e:
        check("VLLMConfig", False, str(e))

    # Summary
    print()
    total = PASS + FAIL
    print("=== {}/{} checks passed ===".format(PASS, total))
    if FAIL:
        print("[FAIL] {} checks failed".format(FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
