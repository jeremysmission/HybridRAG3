# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the vector store part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG -- Vector Store (src/core/vector_store.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   This is the "database" for HybridRAG. It stores three things:
#     1. Chunk metadata (source file, position, timestamp) -- in SQLite
#     2. Chunk text (the actual words from your documents) -- in SQLite
#     3. Embedding vectors (the math representation of meaning) -- in memmap
#
# WHY TWO STORAGE SYSTEMS (SQLite + memmap)?
#   SQLite is great for structured data (text, metadata, queries) but
#   terrible for large arrays of numbers. Loading 1 million embeddings
#   from SQLite BLOBs would use 4GB+ of RAM all at once.
#
#   Memmap ("memory-mapped file") is a numpy trick: the file stays on
#   disk and numpy reads only the rows it needs. Your laptop never loads
#   the whole thing into RAM. This is what makes HybridRAG work on a
#   machine with 8-16GB RAM even with millions of chunks.
#
# WHY float16 INSTEAD OF float32?
#   float32 = 4 bytes per number. float16 = 2 bytes per number.
#   For 1 million chunks at 768 dimensions:
#     float32: 1M x 768 x 4 = 3.0 GB
#     float16: 1M x 768 x 2 = 1.5 GB (half the disk space)
#   Quality loss is negligible for cosine similarity on normalized vectors.
#
# WHY FTS5 (Full-Text Search)?
#   FTS5 is SQLite's built-in keyword search engine. We populate it
#   during indexing (costs almost nothing) so that LATER we can do
#   hybrid search: combine semantic similarity (embeddings) with
#   keyword matching (BM25). This is critical for finding exact part
#   numbers, acronyms, and technical terms.
#
# WHY INSERT OR IGNORE?
#   If indexing crashes halfway and you restart, the same chunks get
#   the same deterministic IDs (from chunk_ids.py). INSERT OR IGNORE
#   means "skip it if it already exists" -- so you never get duplicates.
#
# BUGS FIXED (2026-02-08):
#   BUG-001: Added file_hash column to chunks table + migration.
#   BUG-003: Added close() method to release SQLite + memmap handles.
#
# ALTERNATIVES CONSIDERED:
#   - ChromaDB: dependency hell, required C++ compiler on Windows
#   - LanceDB: alpha quality, .vector import errors, Rust binaries
#   - FAISS: great for search speed, complex on Windows (future option)
#   - Pinecone/Weaviate: cloud services, not suitable for offline use
# ============================================================================

from __future__ import annotations

import os
import json
import sqlite3
import threading
import logging
from dataclasses import dataclass
import re
from typing import Optional, List, Dict, Any, Tuple

import numpy as np


logger = logging.getLogger(__name__)


# --- DATA CLASSES -----------------------------------------------------------

@dataclass
class ChunkMetadata:
    """
    Information about a single chunk stored alongside it in SQLite.
    This is the "label" that tells you where the chunk came from.
    """
    source_path: str      # Full path to the original file
    chunk_index: int      # Position of this chunk within the file (0, 1, 2...)
    text_length: int      # Number of characters in the chunk text
    created_at: str       # ISO timestamp when this chunk was indexed


# --- MEMMAP EMBEDDING STORE ------------------------------------------------

class EmbeddingMemmapStore:
    """
    Disk-backed embedding store using numpy memory-mapped files.

    Files created:
      embeddings.f16.dat   -- raw float16 matrix, shape [N, dim]
      embeddings_meta.json -- bookkeeping: {"dim": 768, "count": N, "embedding_model": "..."}

    How memmap works (plain English):
      A normal numpy array lives entirely in RAM. A memmap array lives
      on disk, and numpy only loads the specific rows you ask for.
      This means you can have 10 million embeddings on a laptop with
      8GB RAM -- numpy just reads the disk when you do a search.

    Append-only design:
      New embeddings are always added at the end. We never modify or
      delete rows in the middle. Orphaned rows are harmless -- search()
      never returns them because nothing in SQLite points to them.
    """

    def __init__(self, data_dir: str, dim: int = 768,
                 embedding_model: str = ""):
        """Plain-English: Sets up the EmbeddingMemmapStore object and prepares state used by its methods."""
        self.data_dir = data_dir
        self.dim = int(dim)
        self.embedding_model = embedding_model  # e.g. "nomic-embed-text"
        self.dat_path = os.path.join(self.data_dir, "embeddings.f16.dat")
        self.meta_path = os.path.join(self.data_dir, "embeddings_meta.json")
        self.count = 0
        self._load_or_init_meta()

    def _load_or_init_meta(self) -> None:
        """Load existing metadata or create fresh metadata file."""
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, ValueError):
                # Corrupted meta file (power failure, disk full) --
                # reinitialize fresh rather than crash the vector store.
                self._save_meta()
                return
            self.dim = int(meta.get("dim", self.dim))
            self.count = int(meta.get("count", 0))
            # Preserve the model that created this index. If the caller
            # provided a model name AND the file has a different one,
            # the mismatch is logged by VectorStore after connect().
            stored_model = meta.get("embedding_model", "")
            if stored_model and not self.embedding_model:
                self.embedding_model = stored_model
            # Reconcile meta count with actual .dat file size.
            # If process crashed after memmap flush but before _save_meta(),
            # the .dat file has more rows than meta records. Trust the file.
            if os.path.exists(self.dat_path):
                file_bytes = os.path.getsize(self.dat_path)
                rows_from_file = file_bytes // (self.dim * 2)  # float16 = 2 bytes
                if rows_from_file > self.count:
                    self.count = rows_from_file
        else:
            self._save_meta()

    def _save_meta(self) -> None:
        """Write metadata to disk (called after every append).
        Uses atomic write (write to .tmp then os.replace) so a crash
        mid-write never leaves a truncated/corrupt meta file."""
        meta = {
            "dim": int(self.dim),
            "count": int(self.count),
            "dtype": "float16",
            "embedding_model": self.embedding_model,
        }
        tmp_path = self.meta_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp_path, self.meta_path)

    def _expected_file_bytes(self, rows: int) -> int:
        """Calculate how many bytes the .dat file should be for N rows."""
        return int(rows) * int(self.dim) * 2

    def _ensure_file_size(self, final_rows: int) -> None:
        """Grow the .dat file on disk to fit final_rows embeddings."""
        os.makedirs(self.data_dir, exist_ok=True)
        final_bytes = self._expected_file_bytes(final_rows)
        if not os.path.exists(self.dat_path):
            with open(self.dat_path, "wb"):
                pass
        with open(self.dat_path, "r+b") as f:
            f.truncate(final_bytes)

    def append_batch(self, embeddings_f32: np.ndarray) -> Tuple[int, int]:
        """
        Append a batch of embeddings to the memmap file.

        Returns (start_row, end_row_exclusive) -- the row indices where
        these embeddings were stored. SQLite uses these to link chunks
        to their embedding vectors.
        """
        if embeddings_f32.ndim != 2:
            raise ValueError("Embeddings must be 2D array (N rows, D columns)")
        if embeddings_f32.shape[1] != self.dim:
            raise ValueError(
                f"Dimension mismatch: got {embeddings_f32.shape[1]}, "
                f"expected {self.dim}"
            )
        n_new = int(embeddings_f32.shape[0])
        if n_new == 0:
            return self.count, self.count

        start = int(self.count)
        end = int(self.count + n_new)
        self._ensure_file_size(end)

        mm = np.memmap(
            self.dat_path, dtype=np.float16, mode="r+", shape=(end, self.dim)
        )
        mm[start:end] = embeddings_f32.astype(np.float16, copy=False)
        mm.flush()
        del mm

        self.count = end
        self._save_meta()
        return start, end

    def read_block(self, start: int, end: int) -> np.ndarray:
        """Read a range of rows from memmap as float32 for math ops."""
        if start < 0 or end > self.count or start >= end:
            return np.zeros((0, self.dim), dtype=np.float32)
        mm = np.memmap(
            self.dat_path, dtype=np.float16, mode="r", shape=(self.count, self.dim)
        )
        block = np.array(mm[start:end], dtype=np.float32)
        del mm
        return block

    def paths_ok(self) -> Tuple[bool, str]:
        """Quick check that both memmap files exist."""
        if not os.path.exists(self.meta_path):
            return False, "Missing embeddings_meta.json"
        if not os.path.exists(self.dat_path):
            return False, "Missing embeddings.f16.dat"
        return True, "OK"


# --- VECTOR STORE (MAIN CLASS) ---------------------------------------------

class VectorStore:
    """
    Combined SQLite + memmap storage with FTS5 full-text index.

    Usage:
        vs = VectorStore(db_path="path/to/hybridrag.sqlite3")
        vs.connect()
        vs.add_embeddings(embeddings, metadata, texts=chunks, file_hash="123:456")
        results = vs.search(query_vec, top_k=8)
        vs.close()   # Always close when done (BUG-003 fix)
    """

    def __init__(self, db_path: str, embedding_dim: int = 768,
                 embedding_model: str = ""):
        """Plain-English: Sets up the VectorStore object and prepares state used by its methods."""
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.embedding_model = embedding_model
        self.conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.RLock()
        data_dir = os.path.dirname(db_path) or "."
        self.mem_store = EmbeddingMemmapStore(
            data_dir=data_dir, dim=embedding_dim,
            embedding_model=embedding_model,
        )

    def _ensure_connected(self) -> None:
        """Auto-connect if not yet connected. Replaces bare asserts."""
        if self.conn is None:
            self.connect()

    def connect(self) -> None:
        """Open SQLite connection and create tables if needed."""
        with self._db_lock:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            self.conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )

            # SQLite performance tuning (safe for single-user desktop use).
            # WHY THESE PRAGMAS:
            #   WAL mode: allows reads while writes happen (no blocking during search)
            #   NORMAL sync: 2x faster writes, safe because WAL protects against corruption
            #   MEMORY temp_store: temp tables live in RAM, not on disk
            #   cache_size -200000: use ~200MB of RAM for page cache (faster reads)
            #   busy_timeout 5000: wait up to 5s for a lock instead of instant failure
            #   foreign_keys ON: enforce referential integrity
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA temp_store=MEMORY;")
            self.conn.execute("PRAGMA cache_size=-200000;")
            self.conn.execute("PRAGMA busy_timeout=5000;")
            self.conn.execute("PRAGMA foreign_keys=ON;")

            self._init_schema()
            # Warn on embedding model mismatch (index vs config)
            stored = self.mem_store.embedding_model
            if stored and self.embedding_model and stored != self.embedding_model:
                logger.warning("[WARN] Embedding model mismatch: index='%s' config='%s'", stored, self.embedding_model)

    # =================================================================
    # BUG-001 FIX: Schema now includes file_hash column
    # =================================================================
    def _init_schema(self) -> None:
        """
        Create the chunks table, indexes, and FTS5 virtual table.

        BUG-001 FIX: Added file_hash column that stores a fingerprint
        of the source file ("filesize:mtime_ns"). The indexer uses this
        to detect modified files. Includes safe migration for existing
        databases that don't have the column yet.
        """
        with self._db_lock:
            self._ensure_connected()

            # file_hash stores "filesize:mtime_ns" for change detection.
            # Empty string = "hash unknown, re-index to be safe".
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_pk      INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id      TEXT UNIQUE,
                    source_path   TEXT NOT NULL,
                    chunk_index   INTEGER,
                    text          TEXT,
                    text_length   INTEGER,
                    created_at    TEXT,
                    embedding_row INTEGER,
                    file_hash     TEXT DEFAULT ''
                );
            """)

            # Migration: add file_hash to existing databases that lack it.
            # Check if file_hash column already exists before attempting migration
            cols = {row[1] for row in self.conn.execute(
                "PRAGMA table_info(chunks)"
            ).fetchall()}
            if "file_hash" not in cols:
                self.conn.execute(
                    "ALTER TABLE chunks ADD COLUMN file_hash TEXT DEFAULT '';"
                )
                self.conn.commit()

            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_path);"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_emb_row ON chunks(embedding_row);"
            )
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(text, content='chunks', content_rowid='chunk_pk');
            """)
            self.conn.commit()

    # ------------------------------------------------------------------
    # Write path (used during indexing)
    # ------------------------------------------------------------------

    # BUG-001 FIX: add_embeddings now accepts and stores file_hash
    def add_embeddings(
        self,
        embeddings: np.ndarray,
        metadata_list: List[ChunkMetadata],
        texts: List[str],
        chunk_ids: Optional[List[str]] = None,
        file_hash: str = "",
    ) -> None:
        """
        Store a batch of chunks: embeddings -> memmap, metadata+text -> SQLite.

        Parameters
        ----------
        embeddings : np.ndarray, shape (N, D)
            The embedding vectors for each chunk.
        metadata_list : list of ChunkMetadata, length N
            Source file info for each chunk.
        texts : list of str, length N
            The actual text content of each chunk.
        chunk_ids : list of str, length N (optional)
            Deterministic IDs for idempotent indexing.
        file_hash : str (NEW -- BUG-001 fix)
            Fingerprint of the source file, e.g. "284519:132720938471230000".
            Stored with every chunk so the indexer can detect file changes.
        """
        self._ensure_connected()
        n = len(metadata_list)
        if n == 0:
            return
        if embeddings.shape[0] != n:
            raise ValueError("Embeddings rows must match metadata_list length")
        if len(texts) != n:
            raise ValueError("Texts length must match metadata_list length")

        with self._db_lock:
            # Step 1: Append embedding vectors to memmap file on disk
            start_row, _ = self.mem_store.append_batch(embeddings)

            # Step 2: Build SQLite rows (one per chunk)
            rows = []
            for i, md in enumerate(metadata_list):
                if chunk_ids and i < len(chunk_ids):
                    cid = chunk_ids[i]
                else:
                    cid = f"{md.source_path}::{md.chunk_index}"

                rows.append((
                    cid,
                    md.source_path,
                    int(md.chunk_index),
                    str(texts[i]),
                    int(md.text_length),
                    md.created_at,
                    int(start_row + i),
                    str(file_hash),       # NEW: file fingerprint
                ))

            # Step 3: INSERT OR IGNORE (idempotent for crash restarts)
            self.conn.executemany("""
                INSERT OR IGNORE INTO chunks
                    (chunk_id, source_path, chunk_index, text, text_length,
                     created_at, embedding_row, file_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, rows)

            # Step 4: Populate FTS5 keyword search index in one set-based
            # statement (avoids N+1 SELECT loop for chunk_pk lookups).
            self.conn.execute("""
                INSERT OR REPLACE INTO chunks_fts(rowid, text)
                SELECT chunk_pk, text
                FROM chunks
                WHERE embedding_row >= ?
                  AND embedding_row < ?;
            """, (
                int(start_row),
                int(start_row + n),
            ))
            self.conn.commit()

    # =================================================================
    # NEW: file_hash helpers for change detection (BUG-001/002 support)
    # =================================================================
    def get_file_hash(self, source_path: str) -> str:
        """
        Look up the stored file_hash for a source file.

        Returns the hash string (e.g., "284519:132720938471230000") or
        empty string if no chunks exist or hash is unknown. The indexer
        compares this against the file's current hash to detect changes.
        """
        if self.conn is None:
            return ""
        with self._db_lock:
            try:
                row = self.conn.execute(
                    "SELECT file_hash FROM chunks WHERE source_path = ? LIMIT 1",
                    (str(source_path),),
                ).fetchone()
                return str(row[0]) if row and row[0] else ""
            except Exception:
                return ""

    def update_file_hash(self, source_path: str, file_hash: str) -> None:
        """Update the file_hash for all chunks from a specific source file."""
        if self.conn is None:
            return
        with self._db_lock:
            self.conn.execute(
                "UPDATE chunks SET file_hash = ? WHERE source_path = ?",
                (str(file_hash), str(source_path)),
            )
            self.conn.commit()

    def delete_chunks_by_source(self, source_path: str) -> int:
        """
        Delete all chunks for a given source file.
        Returns the number of chunks deleted.

        NOTE: Orphaned memmap rows are harmless -- search() never returns
        them because nothing in SQLite points to them.
        """
        self._ensure_connected()
        with self._db_lock:
            self.conn.execute("""
                DELETE FROM chunks_fts WHERE rowid IN (
                    SELECT chunk_pk FROM chunks WHERE source_path = ?
                )
            """, (source_path,))
            cursor = self.conn.execute(
                "DELETE FROM chunks WHERE source_path = ?", (source_path,)
            )
            self.conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Read path (used during search)
    # ------------------------------------------------------------------

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 8,
        block_rows: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find the most similar chunks to a query vector.

        This is the core search algorithm for HybridRAG. Think of it
        like searching a library catalog by "meaning" instead of keywords.

        How it works:
          1. Load embeddings from disk in blocks (not all at once)
          2. For each block, compute cosine similarity with the query
          3. Keep top-k highest scoring chunks across all blocks
          4. Look up text and metadata from SQLite
          5. Return sorted results

        WHY BLOCK-BASED:
          Loading all embeddings at once would use too much RAM on
          laptops (39,602 chunks x 384 dims x 4 bytes = 58 MB).
          Block processing reads 25,000 rows at a time, keeping
          peak RAM usage low even with millions of chunks.

        WHY COSINE SIMILARITY:
          Cosine similarity measures the angle between two vectors,
          ignoring their length. Two passages about the same topic
          will have vectors pointing in similar directions, even if
          one is longer than the other. Score ranges from -1 to +1
          where +1 means identical meaning.
        """
        self._ensure_connected()
        if self.mem_store.count == 0:
            return []

        # Normalize the query vector to unit length for cosine similarity
        q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        dim = self.mem_store.dim
        if q.shape[0] != dim:
            raise ValueError(f"Query dim mismatch: expected {dim}, got {q.shape[0]}")

        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        # Block size controls the memory/speed tradeoff.
        # 25,000 rows x 384 dims x 4 bytes = ~37 MB per block.
        if block_rows is None:
            block_rows = int(os.getenv("HYBRIDRAG_RETRIEVAL_BLOCK_ROWS", "25000"))

        n = int(self.mem_store.count)
        # Running top-k buffer: tracks the best scores seen so far
        best_scores = np.full((top_k,), -1e9, dtype=np.float32)
        best_rows = np.full((top_k,), -1, dtype=np.int64)

        # Process embeddings in blocks to limit peak RAM usage
        for start in range(0, n, block_rows):
            end = min(start + block_rows, n)
            block = self.mem_store.read_block(start, end)
            if block.shape[0] == 0:
                continue

            # Normalize block vectors to unit length
            norms = np.linalg.norm(block, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            block = block / norms

            # Dot product of unit vectors = cosine similarity
            scores = block @ q

            # Use argpartition (O(n)) instead of argsort (O(n log n))
            # to find the top-k candidates in each block
            if scores.shape[0] <= top_k:
                cand_idx = np.arange(scores.shape[0])
            else:
                cand_idx = np.argpartition(scores, -top_k)[-top_k:]

            cand_scores = scores[cand_idx]
            cand_rows = cand_idx + start

            # Merge this block's candidates into the global top-k buffer
            for s, r in zip(cand_scores, cand_rows):
                worst_i = int(np.argmin(best_scores))
                if float(s) > float(best_scores[worst_i]):
                    best_scores[worst_i] = float(s)
                    best_rows[worst_i] = int(r)

        # Sort by score descending (best match first)
        order = np.argsort(best_scores)[::-1]
        best_scores = best_scores[order]
        best_rows = best_rows[order]

        # Filter out unfilled slots (rows that stayed at -1)
        valid = best_rows >= 0
        best_scores = best_scores[valid]
        best_rows = best_rows[valid]

        if best_rows.size == 0:
            return []

        # Look up text and metadata from SQLite using the memmap row indices
        placeholders = ",".join(["?"] * len(best_rows))
        with self._db_lock:
            fetched = self.conn.execute(
                f"SELECT embedding_row, source_path, chunk_index, text "
                f"FROM chunks WHERE embedding_row IN ({placeholders})",
                [int(r) for r in best_rows],
            ).fetchall()

        by_row: Dict[int, Tuple[str, int, str]] = {}
        for row in fetched:
            by_row[int(row[0])] = (str(row[1]), int(row[2]), str(row[3] or ""))

        hits: List[Dict[str, Any]] = []
        for score, row_idx in zip(best_scores.tolist(), best_rows.tolist()):
            meta = by_row.get(int(row_idx))
            if not meta:
                continue
            source_path, chunk_index, text = meta
            hits.append({
                "score": float(score),
                "source_path": source_path,
                "chunk_index": int(chunk_index),
                "text": text,
            })

        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits

    def fts_search(self, query_text, top_k=20):
        """
        Keyword search using SQLite FTS5 (BM25 ranking).

        WHY FTS5:
            Semantic search (embeddings) finds related topics but can miss
            exact terms like part numbers ("ABC-1234") or acronyms ("TCXO").
            FTS5 does traditional keyword matching: if the word appears in
            the document, it will be found. Hybrid search combines both.

        The BM25 score is normalized to 0.0-1.0 range so it can be merged
        with semantic scores in the Retriever's hybrid ranking.
        """
        self._ensure_connected()
        # Extract words of 3+ characters for keyword matching.
        # Short words (a, an, of, to) create too many false matches.
        words = re.findall(r'[A-Za-z0-9]+', query_text or '')
        words = [w for w in words if len(w) >= 3]
        if not words:
            return []
        # OR logic: find chunks containing ANY of the search words
        fts_query = ' OR '.join(words)
        with self._db_lock:
            try:
                rows = self.conn.execute(
                    "SELECT c.source_path, c.chunk_index, c.text, rank "
                    "FROM chunks_fts "
                    "JOIN chunks c ON chunks_fts.rowid = c.chunk_pk "
                    "WHERE chunks_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, top_k),
                ).fetchall()
            except Exception:
                return []
        hits = []
        for source_path, chunk_index, text, rank_score in rows:
            # FTS5 rank is negative (lower = better match). We negate it
            # then normalize to 0.0-1.0 using x/(x+1) so it blends well
            # with semantic similarity scores in hybrid search.
            raw = -float(rank_score)
            normalized = raw / (raw + 1.0) if raw > 0 else 0.0
            hits.append({
                "score": normalized,
                "source_path": str(source_path),
                "chunk_index": int(chunk_index),
                "text": str(text or ""),
            })
        return hits

    # --- Statistics and health checks -----------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about what's stored."""
        stats: Dict[str, Any] = {
            "embedding_count": self.mem_store.count,
            "embedding_dim": self.mem_store.dim,
            "embedding_model": self.mem_store.embedding_model,
        }
        with self._db_lock:
            if self.conn:
                try:
                    row = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
                    stats["chunk_count"] = row[0] if row else 0
                    row = self.conn.execute(
                        "SELECT COUNT(DISTINCT source_path) FROM chunks"
                    ).fetchone()
                    stats["source_count"] = row[0] if row else 0
                except Exception:
                    stats["chunk_count"] = "error"
                    stats["source_count"] = "error"
        return stats

    # =================================================================
    # BUG-003 FIX: close() to release resources
    # =================================================================
    def close(self) -> None:
        """
        Close the SQLite connection and release file handles.

        BUG-003 FIX: Previously, VectorStore never closed its connection.
        Over long runs this leaked file handles and memory. On Windows,
        unclosed connections can block other programs from reading the DB.

        Safe to call multiple times. Call in a "finally" block after
        indexing completes or when shutting down the application.
        """
        with self._db_lock:
            if self.conn is not None:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

    def __enter__(self):
        """Plain-English: Starts a managed resource block and returns the ready-to-use object."""
        self._was_connected = self.conn is not None
        self._ensure_connected()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Only close if WE opened the connection in __enter__.
        # This prevents accidentally killing a shared server-wide
        # instance when someone wraps it in a `with` block.
        """Plain-English: Closes or cleans up resources when a managed block ends."""
        if not self._was_connected:
            self.close()
        return False
