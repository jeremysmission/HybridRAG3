#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the pipeline smoke operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
Pipeline smoke test: end-to-end validation of the RAG pipeline.

Creates a temp folder with a known file, indexes it, queries it,
verifies the result, and cleans up. Returns exit 0 on success, 1 on failure.

Usage:
    python tools/pipeline_smoke_test.py

Tests:
    1. Config loads with correct model
    2. Chunker produces chunks from text
    3. Embedder produces 768-dim vectors via Ollama
    4. VectorStore auto-connects and accepts embeddings
    5. Indexer.index_file() indexes a single file
    6. Semantic search returns the indexed document
    7. Mode switch writes to user_overrides.yaml (not default_config)
    8. Cleanup succeeds
"""

from __future__ import annotations

import os
import sys
import io
import shutil
import tempfile

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
    return condition


TEST_TEXT = (
    "Pipeline Smoke Test Document\n\n"
    "This document validates the HybridRAG indexing pipeline end-to-end. "
    "It covers chunking, embedding via Ollama nomic-embed-text, "
    "vector storage in SQLite, and semantic search retrieval. "
    "Calibration intervals are set to 12 months per section 7.3. "
    "The maintenance schedule follows quarterly review cycles. "
    "All equipment must be inspected before deployment."
)


def main():
    tmp_dir = None
    store = None

    try:
        # 1. Config
        from src.core.config import load_config
        cfg = load_config()
        check("Config loads", cfg is not None)
        check("Config model = {}".format(cfg.ollama.model),
              cfg.ollama.model is not None and len(cfg.ollama.model) > 0)

        # 2. Chunker
        from src.core.chunker import Chunker
        chunker = Chunker(cfg.chunking)
        chunks = chunker.chunk_text(TEST_TEXT)
        check("Chunker: {} chunks from {} chars".format(len(chunks), len(TEST_TEXT)),
              len(chunks) >= 1)

        # 3. Embedder
        from src.core.embedder import Embedder
        embedder = Embedder(model_name=cfg.embedding.model_name)
        vectors = embedder.embed_batch(chunks)
        check("Embedder: {} vectors, dim={}".format(len(vectors), len(vectors[0])),
              len(vectors) == len(chunks) and len(vectors[0]) == 768)

        # 4. VectorStore auto-connect
        tmp_dir = tempfile.mkdtemp(prefix="hrag_smoke_")
        db_path = os.path.join(tmp_dir, "smoke_test.sqlite3")

        from src.core.vector_store import VectorStore
        store = VectorStore(db_path=db_path, embedding_dim=768)
        # Do NOT call connect() -- test auto-connect
        check("VectorStore created (no explicit connect())", store.conn is None)

        # 5. Indexer.index_file()
        test_file = os.path.join(tmp_dir, "smoke_test_doc.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(TEST_TEXT)

        from src.core.indexer import Indexer
        indexer = Indexer(
            config=cfg, chunker=chunker,
            embedder=embedder, vector_store=store,
        )
        result = indexer.index_file(test_file)
        check("Indexer.index_file() indexed={}".format(result.get("indexed")),
              result.get("indexed") is True)
        check("Chunks added: {}".format(result.get("chunks_added", 0)),
              result.get("chunks_added", 0) >= 1)

        # Confirm auto-connect happened
        check("VectorStore auto-connected", store.conn is not None)

        # 6. Semantic search
        q_vec = embedder.embed_query("calibration intervals quarterly review")
        results = store.search(q_vec, top_k=3)
        check("Search returned {} results".format(len(results)),
              len(results) >= 1)

        if results:
            top_text = results[0].get(
                "text", results[0].get("chunk_text", ""))
            check("Top result contains 'calibration'",
                  "calibration" in top_text.lower(),
                  "got: {}...".format(top_text[:60]))

        # 7. Mode switch uses user_overrides.yaml
        from src.core.config import save_config_field
        save_config_field("mode", "online")
        ovr_path = os.path.join(".", "config", "user_overrides.yaml")
        check("Mode switch created user_overrides.yaml",
              os.path.isfile(ovr_path))

        # Restore
        save_config_field("mode", "offline")

        import subprocess
        diff = subprocess.run(
            ["git", "diff", "--", "config/default_config.yaml"],
            capture_output=True, text=True,
        )
        check("default_config.yaml untouched by mode switch",
              not diff.stdout.strip())

    except Exception as e:
        check("Unexpected error", False, "{}: {}".format(type(e).__name__, e))

    finally:
        # 8. Cleanup
        if store:
            try:
                store.close()
            except Exception:
                pass
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            check("Cleanup temp dir", not os.path.isdir(tmp_dir))

    print()
    total = PASS + FAIL
    print("=== {}/{} checks passed ===".format(PASS, total))
    if FAIL:
        print("[FAIL] {} checks failed".format(FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
