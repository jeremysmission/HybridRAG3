#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the mode switch headless operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG v3 -- Headless Mode-Switch Edge Case Test

Tests the offline -> online -> offline round-trip WITHOUT the GUI,
verifying that all core objects survive mode switching intact.

Checks:
  1. Boot succeeds (BootCoordinator + BackendLoader)
  2. All core objects present after boot
  3. Switch to ONLINE mode (creds, gate, router rebuild)
  4. Switch back to OFFLINE mode
  5. Post-round-trip integrity:
     - query_engine is not None
     - query_engine.llm_router is not None
     - query_engine.retriever is not None
     - query_engine.retriever.embedder is not None
     - VectorStore connection still open (get_stats works)
     - Embedder can still embed a test query
     - Object identity preserved (embedder is the SAME object)

Usage:
  python tools/test_mode_switch_headless.py
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

# Windows stdout encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

# Track results
results = []


def check(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    results.append((name, condition, detail))
    msg = "[{}] {}".format(tag, name)
    if detail:
        msg += " -- {}".format(detail)
    print(msg)
    return condition


def main():
    print()
    print("=" * 65)
    print("  MODE-SWITCH EDGE CASE TEST (headless, no GUI)")
    print("=" * 65)
    print()

    # ==================================================================
    # PHASE 1: Boot the application
    # ==================================================================
    print("--- PHASE 1: Boot ---")
    t0 = time.perf_counter()

    try:
        from src.core.bootstrap.boot_coordinator import BootCoordinator
        bc = BootCoordinator(str(PROJECT_ROOT))
        boot_report = bc.run()
        config = boot_report.config
    except Exception as e:
        check("Boot/Coordinator", False, str(e))
        print("\nFATAL: Cannot continue without config.")
        return 1

    check("Boot/Coordinator", config is not None,
          "state={} elapsed={:.0f}ms".format(
              boot_report.state.value,
              (time.perf_counter() - t0) * 1000))

    t1 = time.perf_counter()
    bundle = None
    try:
        from src.core.bootstrap.backend_loader import BackendLoader
        loader = BackendLoader(
            config=config,
            boot_result=boot_report.boot_result,
        )
        bundle = loader.load(timeout_seconds=60)
    except Exception as e:
        check("Boot/BackendLoader", False, str(e))
        print("\nFATAL: Cannot continue without backend.")
        return 1

    check("Boot/BackendLoader", bundle is not None,
          "errors={} elapsed={:.0f}ms".format(
              len(bundle.init_errors),
              (time.perf_counter() - t1) * 1000))

    # ==================================================================
    # PHASE 2: Verify initial state
    # ==================================================================
    print()
    print("--- PHASE 2: Initial State ---")

    qe = bundle.query_engine
    check("Initial/query_engine exists", qe is not None)
    check("Initial/llm_router exists",
          qe is not None and qe.llm_router is not None)
    check("Initial/retriever exists",
          qe is not None and qe.retriever is not None)
    check("Initial/retriever.embedder exists",
          qe is not None and qe.retriever is not None and qe.retriever.embedder is not None)
    check("Initial/VectorStore exists", bundle.store is not None)

    if not qe or not qe.retriever or not qe.retriever.embedder or not bundle.store:
        print("\nFATAL: Missing core objects, cannot test mode switch.")
        return 1

    # Snapshot object IDs for identity checks later
    embedder_id_before = id(qe.retriever.embedder)
    retriever_id_before = id(qe.retriever)
    store_id_before = id(bundle.store)

    # Verify VectorStore is functional
    try:
        stats = bundle.store.get_stats()
        check("Initial/VectorStore.get_stats()", True,
              "chunks={}".format(stats.get("chunk_count", "?")))
    except Exception as e:
        check("Initial/VectorStore.get_stats()", False, str(e))

    # Verify embedder is functional
    try:
        vec = qe.retriever.embedder.embed_query("test")
        check("Initial/embed_query('test')", vec is not None and len(vec) > 0,
              "dim={}".format(len(vec) if vec is not None else 0))
    except Exception as e:
        check("Initial/embed_query('test')", False, str(e))

    # ==================================================================
    # PHASE 3: Switch to ONLINE mode
    # ==================================================================
    print()
    print("--- PHASE 3: Switch OFFLINE -> ONLINE ---")
    t_switch1 = time.perf_counter()

    try:
        from src.security.credentials import resolve_credentials
        from src.core.network_gate import configure_gate
        from src.core.llm_router import LLMRouter, invalidate_deployment_cache

        creds = resolve_credentials(use_cache=True)
        check("Online/resolve_credentials", True,
              "has_key={} has_endpoint={}".format(creds.has_key, creds.has_endpoint))

        config.mode = "online"
        check("Online/config.mode set", config.mode == "online")

        configure_gate(
            mode="online",
            api_endpoint=creds.endpoint or "",
            allowed_prefixes=getattr(
                getattr(config, "api", None),
                "allowed_endpoint_prefixes", [],
            ) if config else [],
        )
        check("Online/configure_gate", True)

        invalidate_deployment_cache()
        online_router = LLMRouter(config, credentials=creds)
        check("Online/LLMRouter created", online_router is not None)

        # Swap the router in the query engine (same as mode_switch.py does)
        qe.llm_router = online_router
        bundle.router = online_router
        check("Online/router swapped", qe.llm_router is online_router)

    except Exception as e:
        check("Online/switch", False, str(e))
        import traceback
        traceback.print_exc()

    switch1_ms = (time.perf_counter() - t_switch1) * 1000
    print("  (online switch took {:.0f}ms)".format(switch1_ms))

    # Verify embedder and store survived the online switch
    check("Online/embedder survived",
          qe.retriever.embedder is not None and id(qe.retriever.embedder) == embedder_id_before,
          "same_object={}".format(id(qe.retriever.embedder) == embedder_id_before))
    check("Online/retriever survived",
          qe.retriever is not None and id(qe.retriever) == retriever_id_before)
    check("Online/store survived",
          bundle.store is not None and id(bundle.store) == store_id_before)

    # ==================================================================
    # PHASE 4: Switch back to OFFLINE mode
    # ==================================================================
    print()
    print("--- PHASE 4: Switch ONLINE -> OFFLINE ---")
    t_switch2 = time.perf_counter()

    try:
        config.mode = "offline"
        check("Offline/config.mode set", config.mode == "offline")

        configure_gate(mode="offline")
        check("Offline/configure_gate", True)

        invalidate_deployment_cache()
        offline_router = LLMRouter(config, credentials=creds)
        check("Offline/LLMRouter created", offline_router is not None)

        qe.llm_router = offline_router
        bundle.router = offline_router
        check("Offline/router swapped", qe.llm_router is offline_router)

    except Exception as e:
        check("Offline/switch", False, str(e))
        import traceback
        traceback.print_exc()

    switch2_ms = (time.perf_counter() - t_switch2) * 1000
    print("  (offline switch took {:.0f}ms)".format(switch2_ms))

    # ==================================================================
    # PHASE 5: Post-round-trip integrity checks
    # ==================================================================
    print()
    print("--- PHASE 5: Post-Round-Trip Integrity ---")

    # Core objects not None
    check("Final/query_engine is not None", qe is not None)
    check("Final/llm_router is not None",
          qe is not None and qe.llm_router is not None)
    check("Final/retriever is not None",
          qe is not None and qe.retriever is not None)
    check("Final/retriever.embedder is not None",
          qe is not None and qe.retriever is not None and qe.retriever.embedder is not None)

    # VectorStore connection still open
    try:
        stats_after = bundle.store.get_stats()
        check("Final/VectorStore.get_stats() works", True,
              "chunks={}".format(stats_after.get("chunk_count", "?")))
    except Exception as e:
        check("Final/VectorStore.get_stats() works", False, str(e))

    # Embedder can still embed
    try:
        vec_after = qe.retriever.embedder.embed_query("mode switch test")
        check("Final/embed_query works", vec_after is not None and len(vec_after) > 0,
              "dim={}".format(len(vec_after) if vec_after is not None else 0))
    except Exception as e:
        check("Final/embed_query works", False, str(e))

    # Object identity preserved
    embedder_id_after = id(qe.retriever.embedder)
    retriever_id_after = id(qe.retriever)
    store_id_after = id(bundle.store)

    check("Final/embedder SAME object",
          embedder_id_after == embedder_id_before,
          "before={} after={}".format(embedder_id_before, embedder_id_after))
    check("Final/retriever SAME object",
          retriever_id_after == retriever_id_before,
          "before={} after={}".format(retriever_id_before, retriever_id_after))
    check("Final/store SAME object",
          store_id_after == store_id_before,
          "before={} after={}".format(store_id_before, store_id_after))

    # Mode should be offline after round-trip
    check("Final/config.mode == 'offline'", config.mode == "offline")

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print()
    print("=" * 65)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print("  SUMMARY: {} passed, {} failed, {} total".format(
        passed, failed, len(results)))
    print("=" * 65)

    if failed:
        print()
        print("  FAILURES:")
        for name, ok, detail in results:
            if not ok:
                print("    [FAIL] {} -- {}".format(name, detail))
        print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
