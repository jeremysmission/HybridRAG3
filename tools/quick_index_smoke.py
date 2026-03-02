#!/usr/bin/env python3
"""
Quick indexing architecture smoke test for low-power laptops.

Purpose:
  Validate chunker -> indexer -> vector store wiring without loading
  heavy embedding models. Uses a tiny source file and a fake embedder.

Usage:
  python tools/quick_index_smoke.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from src.core.chunker import Chunker
from src.core.config import load_config
from src.core.indexer import Indexer
from src.core.vector_store import VectorStore


class FakeEmbedder:
    """Lightweight stand-in for Embedder to keep smoke tests fast."""

    def __init__(self, dimension: int):
        self.dimension = int(dimension)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        n = len(texts)
        arr = np.ones((n, self.dimension), dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        arr /= norms
        return arr

    def close(self) -> None:
        return


def main() -> int:
    base = Path("output/quick_arch_smoke")
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    (base / "src").mkdir(parents=True, exist_ok=True)
    (base / "idx").mkdir(parents=True, exist_ok=True)

    tiny_text = "HybridRAG quick smoke test. " * 40
    tiny_file = base / "src" / "tiny.txt"
    tiny_file.write_text(tiny_text, encoding="utf-8")

    cfg = load_config(".")
    cfg.paths.source_folder = str((base / "src").resolve())
    cfg.paths.index_folder = str((base / "idx").resolve())
    cfg.paths.database = str((base / "idx" / "embeddings.db").resolve())

    chunker = Chunker(cfg.chunking)
    chunks = chunker.chunk_text(tiny_text)

    vector_store = VectorStore(cfg.paths.database, cfg.embedding.dimension)
    vector_store.connect()
    embedder = FakeEmbedder(cfg.embedding.dimension)
    indexer = Indexer(cfg, vector_store, embedder, chunker)

    result = indexer.index_folder(cfg.paths.source_folder)
    stats = vector_store.get_stats()
    vector_store.close()

    payload = {
        "chunker_chunks": len(chunks),
        "index_result": result,
        "vector_store_stats": stats,
        "db_exists": Path(cfg.paths.database).exists(),
        "output_dir": str(base.resolve()),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
