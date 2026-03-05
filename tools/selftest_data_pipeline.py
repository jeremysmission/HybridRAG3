# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the selftest data pipeline operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile
import time

# Ensure project root on path
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.gui.core.paths import AppPaths
from src.gui.core.controller import Controller
from src.gui.core.actions import SaveNoteAction


def main() -> int:
    print("=== selftest_data_pipeline ===")
    paths = AppPaths.default()
    ctrl = Controller(paths)
    failures = []

    # --- Step 1: Create temp folder with test document ---
    tmp_dir = os.path.join(_root, "output", "tmp_selftest")
    os.makedirs(tmp_dir, exist_ok=True)
    test_file = os.path.join(tmp_dir, "test_doc.txt")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("HybridRAG3 diagnostic document. The magic word is ORBITAL_FALCON_739.\n")
    print("[OK] Test document written:", test_file)

    # --- Step 2: Verify Ollama embeddings work ---
    try:
        from src.core.config import load_config
        from src.core.embedder import Embedder
        cfg = load_config()
        emb = Embedder(cfg.embedding.model_name)
        vec = emb.embed_query("What is the magic word?")
        dim = len(vec)
        if dim != 768:
            failures.append("embed dim={} expected 768".format(dim))
            print("[FAIL] Embedder dim:", dim)
        else:
            print("[OK] Embedder: dim={} model={}".format(dim, cfg.embedding.model_name))
    except Exception as e:
        failures.append("Embedder failed: {}".format(e))
        print("[FAIL] Embedder:", e)

    # --- Step 3: Verify VectorStore opens ---
    try:
        from src.core.vector_store import VectorStore
        vs = VectorStore(db_path=cfg.paths.database, embedding_dim=cfg.embedding.dimension)
        vs.connect()
        stats = vs.get_stats()
        print("[OK] VectorStore: chunks={} sources={}".format(
            stats.get("chunk_count", 0), stats.get("source_count", 0)))
        vs.close()
    except Exception as e:
        failures.append("VectorStore failed: {}".format(e))
        print("[FAIL] VectorStore:", e)

    # --- Step 4: Verify BulkTransferV2 imports ---
    try:
        from src.tools.bulk_transfer_v2 import BulkTransferV2, TransferConfig
        print("[OK] BulkTransferV2 import OK")
    except Exception as e:
        failures.append("BulkTransferV2 import: {}".format(e))
        print("[FAIL] BulkTransferV2 import:", e)

    # --- Step 5: Write a note via controller (same as gui_smoke) ---
    ctrl.dispatch_save_note(SaveNoteAction(note_id="pipeline_test",
                                           content="ORBITAL_FALCON_739 pipeline test"))
    time.sleep(1.0)
    last = ctrl.downloads.last()
    if not last or not last.get("exists"):
        failures.append("Controller save_note: file not written")
        print("[FAIL] Controller save_note")
    else:
        print("[OK] Controller save_note:", last["path"])

    # --- Step 6: Write stage_counts to diagnostics ---
    stage_counts = {
        "test_document": test_file,
        "embed_dim": dim if "dim" in dir() else 0,
        "vectorstore_chunks": stats.get("chunk_count", 0) if "stats" in dir() else 0,
        "vectorstore_sources": stats.get("source_count", 0) if "stats" in dir() else 0,
        "bulk_transfer_importable": "BulkTransferV2" in dir(),
        "controller_note_written": bool(last and last.get("exists")),
    }
    counts_path = os.path.join(ctrl.diag.run_dir, "stage_counts.json")
    with open(counts_path, "w", encoding="utf-8") as f:
        json.dump(stage_counts, f, indent=2)
    print("[OK] Stage counts written:", counts_path)

    # --- Summary ---
    print()
    print("Diagnostics:", ctrl.diag.run_dir)
    if failures:
        print("FAIL: {} failures".format(len(failures)))
        for f_msg in failures:
            print("  -", f_msg)
        return 1
    else:
        print("PASS: all checks green")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
