# ============================================================================
# HybridRAG v3 -- Built-In Test Engine (src/core/ibit.py)
# ============================================================================
# Two test modes:
#
#   IBIT (Initial BIT) -- runs once at startup after backends load.
#     6 checks: Config, Paths, Database, Embedder, Router, Pipeline
#     Performance: < 500ms total
#
#   CBIT (Continuous BIT) -- runs every 60s in the background.
#     3 lightweight checks: Database, Router, Disk
#     Performance: < 200ms total (no embedder call, no heavy I/O)
#     Purpose: detect silent failures (DB lock, Ollama crash, disk full)
#
# INTERNET ACCESS: NONE (reads local state only)
# ============================================================================

import os
import time
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IBITCheck:
    """Result of a single IBIT check."""
    name: str           # Short label: "Config", "Paths", etc.
    ok: bool            # True = passed
    detail: str         # Human-readable result or error
    elapsed_ms: float   # How long the check took


def run_ibit(config, query_engine=None, indexer=None, router=None):
    """Run all IBIT checks and return results.

    Parameters
    ----------
    config : Config
        Loaded configuration object.
    query_engine : QueryEngine or None
        The wired query engine (None if loading failed).
    indexer : Indexer or None
        The wired indexer (None if loading failed).
    router : LLMRouter or None
        The LLM router (None if loading failed).

    Returns
    -------
    list[IBITCheck]
        Six results, one per check, in order.
    """
    results = []
    results.append(_check_config(config))
    results.append(_check_paths(config))
    results.append(_check_database(config))
    results.append(_check_embedder(query_engine))
    results.append(_check_router(config, router))
    results.append(_check_pipeline(query_engine))

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    logger.info("[OK] IBIT complete: %d/%d passed", passed, total)
    for r in results:
        tag = "[OK]" if r.ok else "[FAIL]"
        logger.debug("  %s %s: %s (%.0fms)", tag, r.name, r.detail, r.elapsed_ms)

    return results


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_config(config):
    """Check 1: Config object is valid."""
    t0 = time.perf_counter()
    try:
        if config is None:
            return IBITCheck("Config", False, "Config is None",
                             _elapsed(t0))
        mode = getattr(config, "mode", None)
        if mode not in ("offline", "online"):
            return IBITCheck("Config", False,
                             "Invalid mode: {}".format(mode), _elapsed(t0))
        return IBITCheck("Config", True,
                         "mode={}".format(mode), _elapsed(t0))
    except Exception as e:
        return IBITCheck("Config", False, str(e), _elapsed(t0))


def _check_paths(config):
    """Check 2: Essential paths are configured and directories exist."""
    t0 = time.perf_counter()
    try:
        db = getattr(getattr(config, "paths", None), "database", "")
        src = getattr(getattr(config, "paths", None), "source_folder", "")
        issues = []
        if not db:
            issues.append("database path empty")
        if not src:
            issues.append("source_folder empty")
        if db:
            db_dir = os.path.dirname(db)
            if db_dir and not os.path.isdir(db_dir):
                issues.append("database directory missing")
        if issues:
            return IBITCheck("Paths", False,
                             "; ".join(issues), _elapsed(t0))
        return IBITCheck("Paths", True, "configured", _elapsed(t0))
    except Exception as e:
        return IBITCheck("Paths", False, str(e), _elapsed(t0))


def _check_database(config):
    """Check 3: SQLite database is reachable and has a chunks table."""
    t0 = time.perf_counter()
    try:
        db = getattr(getattr(config, "paths", None), "database", "")
        if not db:
            return IBITCheck("Database", False,
                             "no database path", _elapsed(t0))
        if not os.path.isfile(db):
            return IBITCheck("Database", False,
                             "file not found", _elapsed(t0))
        import sqlite3
        conn = sqlite3.connect(db, timeout=2)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM chunks"
            ).fetchone()
            count = row[0] if row else 0
            return IBITCheck("Database", True,
                             "{:,} chunks".format(count), _elapsed(t0))
        finally:
            conn.close()
    except Exception as e:
        return IBITCheck("Database", False, str(e), _elapsed(t0))


def _check_embedder(query_engine):
    """Check 4: Embedder is loaded and can produce vectors."""
    t0 = time.perf_counter()
    try:
        if query_engine is None:
            return IBITCheck("Embedder", False,
                             "query engine not loaded", _elapsed(t0))
        embedder = getattr(query_engine, "embedder", None)
        if embedder is None:
            return IBITCheck("Embedder", False,
                             "embedder not attached", _elapsed(t0))
        model_name = getattr(embedder, "model_name", "unknown")
        # Quick encode test
        vec = embedder.embed_query("IBIT test")
        if vec is None or len(vec) == 0:
            return IBITCheck("Embedder", False,
                             "encode returned empty", _elapsed(t0))
        return IBITCheck("Embedder", True,
                         "{} (dim={})".format(model_name, len(vec)),
                         _elapsed(t0))
    except Exception as e:
        return IBITCheck("Embedder", False, str(e), _elapsed(t0))


def _check_router(config, router):
    """Check 5: At least one LLM backend is available."""
    t0 = time.perf_counter()
    try:
        if router is None:
            return IBITCheck("Router", False,
                             "router not loaded", _elapsed(t0))
        mode = getattr(config, "mode", "offline")
        if mode == "offline":
            ollama_ok = False
            if hasattr(router, "ollama"):
                ollama_ok = router.ollama.is_available()
            vllm_ok = False
            if hasattr(router, "vllm") and router.vllm is not None:
                vllm_ok = router.vllm.is_available()
            if ollama_ok:
                return IBITCheck("Router", True,
                                 "Ollama ready", _elapsed(t0))
            if vllm_ok:
                return IBITCheck("Router", True,
                                 "vLLM ready", _elapsed(t0))
            return IBITCheck("Router", False,
                             "no offline backend", _elapsed(t0))
        else:
            has_api = hasattr(router, "api") and router.api is not None
            if has_api:
                return IBITCheck("Router", True,
                                 "API configured", _elapsed(t0))
            return IBITCheck("Router", False,
                             "no API backend", _elapsed(t0))
    except Exception as e:
        return IBITCheck("Router", False, str(e), _elapsed(t0))


def _check_pipeline(query_engine):
    """Check 6: QueryEngine is fully wired with all components."""
    t0 = time.perf_counter()
    try:
        if query_engine is None:
            return IBITCheck("Pipeline", False,
                             "query engine not loaded", _elapsed(t0))
        missing = []
        if getattr(query_engine, "store", None) is None:
            missing.append("VectorStore")
        if getattr(query_engine, "embedder", None) is None:
            missing.append("Embedder")
        if getattr(query_engine, "router", None) is None:
            missing.append("Router")
        if missing:
            return IBITCheck("Pipeline", False,
                             "missing: {}".format(", ".join(missing)),
                             _elapsed(t0))
        return IBITCheck("Pipeline", True, "all components wired",
                         _elapsed(t0))
    except Exception as e:
        return IBITCheck("Pipeline", False, str(e), _elapsed(t0))


def _elapsed(t0):
    """Milliseconds since t0."""
    return (time.perf_counter() - t0) * 1000


# ============================================================================
# CBIT -- Continuous Built-In Test
# ============================================================================

def run_cbit(config, query_engine=None, router=None):
    """Run lightweight continuous health checks.

    Called every 60s by the status bar timer.  Must be fast (< 200ms)
    and non-disruptive -- no embedder calls, no writes, no locks held
    longer than a few ms.

    Parameters
    ----------
    config : Config
        Loaded configuration object.
    query_engine : QueryEngine or None
        The wired query engine (may have gone stale).
    router : LLMRouter or None
        The LLM router (may have lost connection).

    Returns
    -------
    list[IBITCheck]
        Three results: Database, Router, Disk.
    """
    results = []
    results.append(_cbit_database(config))
    results.append(_cbit_router(config, router))
    results.append(_cbit_disk(config))

    passed = sum(1 for r in results if r.ok)
    if passed < len(results):
        logger.warning("[WARN] CBIT: %d/%d passed", passed, len(results))
        for r in results:
            if not r.ok:
                logger.warning("  [FAIL] %s: %s", r.name, r.detail)
    else:
        logger.debug("[OK] CBIT: %d/%d passed", passed, len(results))

    return results


def _cbit_database(config):
    """CBIT: can we still reach the database?

    Faster than IBIT's _check_database -- just opens + closes the
    connection with a trivial query.  Catches DB locks, file moves,
    and corruption.
    """
    t0 = time.perf_counter()
    try:
        db = getattr(getattr(config, "paths", None), "database", "")
        if not db:
            return IBITCheck("Database", False, "no path", _elapsed(t0))
        if not os.path.isfile(db):
            return IBITCheck("Database", False, "file missing", _elapsed(t0))
        import sqlite3
        conn = sqlite3.connect(db, timeout=1)
        try:
            conn.execute("SELECT 1").fetchone()
            return IBITCheck("Database", True, "reachable", _elapsed(t0))
        finally:
            conn.close()
    except Exception as e:
        return IBITCheck("Database", False, str(e)[:80], _elapsed(t0))


def _cbit_router(config, router):
    """CBIT: is the LLM backend still responding?

    Checks Ollama /api/tags or vLLM /health (offline) or API key
    presence (online).  No generation calls -- just reachability.
    """
    t0 = time.perf_counter()
    try:
        if router is None:
            return IBITCheck("Router", False, "not loaded", _elapsed(t0))
        mode = getattr(config, "mode", "offline")
        if mode == "offline":
            # Check Ollama reachability (lightweight -- /api/tags is fast)
            ollama_ok = False
            if hasattr(router, "ollama"):
                ollama_ok = router.ollama.is_available()
            vllm_ok = False
            if hasattr(router, "vllm") and router.vllm is not None:
                vllm_ok = router.vllm.is_available()
            if ollama_ok or vllm_ok:
                backend = "Ollama" if ollama_ok else "vLLM"
                return IBITCheck("Router", True,
                                 "{} OK".format(backend), _elapsed(t0))
            return IBITCheck("Router", False,
                             "offline backend lost", _elapsed(t0))
        else:
            has_api = hasattr(router, "api") and router.api is not None
            if has_api:
                return IBITCheck("Router", True, "API OK", _elapsed(t0))
            return IBITCheck("Router", False,
                             "API not configured", _elapsed(t0))
    except Exception as e:
        return IBITCheck("Router", False, str(e)[:80], _elapsed(t0))


# Minimum free disk space before warning (100 MB)
_MIN_DISK_MB = 100


def _cbit_disk(config):
    """CBIT: is there enough disk space for continued operation?

    Checks free space on the drive holding the database.  Warns if
    below 100 MB -- enough headroom for a few thousand more chunks
    but signals imminent trouble.
    """
    t0 = time.perf_counter()
    try:
        db = getattr(getattr(config, "paths", None), "database", "")
        check_path = os.path.dirname(db) if db else os.getcwd()
        if not os.path.isdir(check_path):
            check_path = os.getcwd()
        import shutil
        usage = shutil.disk_usage(check_path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < _MIN_DISK_MB:
            return IBITCheck("Disk", False,
                             "{:.0f} MB free (< {} MB)".format(
                                 free_mb, _MIN_DISK_MB),
                             _elapsed(t0))
        return IBITCheck("Disk", True,
                         "{:.0f} MB free".format(free_mb), _elapsed(t0))
    except Exception as e:
        return IBITCheck("Disk", False, str(e)[:80], _elapsed(t0))
