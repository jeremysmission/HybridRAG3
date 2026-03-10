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
  python tools/test_mode_switch_headless.py --require-embedder
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
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


def _record_result(name: str, status: str, detail: str = "") -> bool:
    results.append((name, status, detail))
    msg = "[{}] {}".format(status, name)
    if detail:
        msg += " -- {}".format(detail)
    print(msg)
    return status != "FAIL"


def check(name, condition, detail=""):
    return _record_result(name, "PASS" if condition else "FAIL", detail)


def skip(name, detail=""):
    return _record_result(name, "SKIP", detail)


def _is_embedder_backend_unavailable(error: Exception) -> bool:
    detail = str(error or "").lower()
    return any(
        marker in detail
        for marker in (
            "winerror 10061",
            "connection refused",
            "actively refused",
            "failed to establish a new connection",
            "max retries exceeded",
            "could not connect to ollama",
            "ollama service not available",
        )
    )


def _probe_embedder_query(
    name: str,
    *,
    embedder,
    prompt: str,
    require_embedder: bool,
) -> tuple[str, str]:
    try:
        vec = embedder.embed_query(prompt)
        check(
            name,
            vec is not None and len(vec) > 0,
            "dim={}".format(len(vec) if vec is not None else 0),
        )
        return "ok", ""
    except Exception as e:
        detail = str(e)
        if not require_embedder and _is_embedder_backend_unavailable(e):
            skip(name, detail)
            return "skip", detail
        check(name, False, detail)
        return "fail", detail


def _clear_child_router_errors(router) -> None:
    if router is None:
        return
    if hasattr(router, "last_error"):
        router.last_error = "stale"
    for attr in ("ollama", "api", "vllm"):
        child = getattr(router, attr, None)
        if child is not None and hasattr(child, "last_error"):
            child.last_error = "stale"


def _check_runtime_integrity(
    label: str,
    *,
    config,
    bundle,
    qe,
    expected_mode: str,
    embedder_id_before: int,
    retriever_id_before: int,
    store_id_before: int,
    embedder_probe_state: str,
    embedder_probe_detail: str,
    require_embedder: bool,
) -> None:
    from src.core.network_gate import get_gate

    gate = get_gate()
    router = getattr(qe, "llm_router", None)

    check(f"{label}/config.mode", getattr(config, "mode", "") == expected_mode)
    check(f"{label}/gate mode", gate.mode_name == expected_mode, gate.mode_name)
    check(f"{label}/bundle router linked", getattr(bundle, "router", None) is router)
    check(f"{label}/router exists", router is not None)
    check(f"{label}/router config linked", getattr(router, "config", None) is config)
    check(f"{label}/query_engine config linked", getattr(qe, "config", None) is config)
    check(
        f"{label}/retriever config linked",
        getattr(getattr(qe, "retriever", None), "config", None) is config,
    )

    if router is not None and hasattr(router, "last_error"):
        check(f"{label}/router last_error cleared", router.last_error == "", router.last_error)
        for attr in ("ollama", "api", "vllm"):
            child = getattr(router, attr, None)
            if child is not None and hasattr(child, "last_error"):
                check(
                    f"{label}/{attr} last_error cleared",
                    child.last_error == "",
                    child.last_error,
                )

    check(
        f"{label}/embedder survived",
        qe.retriever.embedder is not None and id(qe.retriever.embedder) == embedder_id_before,
        "same_object={}".format(id(qe.retriever.embedder) == embedder_id_before),
    )
    check(
        f"{label}/retriever survived",
        qe.retriever is not None and id(qe.retriever) == retriever_id_before,
    )
    check(
        f"{label}/store survived",
        bundle.store is not None and id(bundle.store) == store_id_before,
    )

    try:
        stats = bundle.store.get_stats()
        check(
            f"{label}/VectorStore.get_stats()",
            True,
            "chunks={}".format(stats.get("chunk_count", "?")),
        )
    except Exception as e:
        check(f"{label}/VectorStore.get_stats()", False, str(e))

    probe_name = f"{label}/embed_query works"
    if embedder_probe_state == "skip":
        skip(probe_name, "initial embedder probe unavailable: {}".format(embedder_probe_detail))
    elif embedder_probe_state == "fail":
        skip(probe_name, "initial embedder probe already failed: {}".format(embedder_probe_detail))
    else:
        _probe_embedder_query(
            probe_name,
            embedder=qe.retriever.embedder,
            prompt=f"{label} mode churn probe",
            require_embedder=require_embedder,
        )


def _switch_mode(bundle, qe, config, creds, new_mode: str, cycle: int):
    from src.core.llm_router import LLMRouter, invalidate_deployment_cache
    from src.core.query_engine import refresh_query_engine_runtime
    from src.core.network_gate import configure_gate
    from src.gui.helpers.mode_tuning import apply_mode_settings_to_config
    import src.core.llm_router as llm_router_mod

    current_router = getattr(qe, "llm_router", None)
    _clear_child_router_errors(current_router)
    llm_router_mod._deployment_cache = ["stale-model-{}".format(cycle)]
    invalidate_deployment_cache()
    check(
        "Cycle {} cache cleared before {}".format(cycle, new_mode.upper()),
        llm_router_mod._deployment_cache is None,
    )

    if new_mode == "online":
        configure_gate(
            mode="online",
            api_endpoint=getattr(creds, "endpoint", "") or "",
            allowed_prefixes=getattr(
                getattr(config, "api", None),
                "allowed_endpoint_prefixes",
                [],
            ) if config else [],
        )
    else:
        configure_gate(mode="offline")

    config.mode = new_mode
    new_router = LLMRouter(config, credentials=creds)
    qe.config = config
    qe.llm_router = new_router
    bundle.router = new_router
    apply_mode_settings_to_config(config, new_mode)
    refresh_query_engine_runtime(qe, clear_caches=True)
    return new_router


def _parse_args():
    ap = argparse.ArgumentParser(description="Headless offline/online churn integrity test.")
    ap.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of offline->online->offline churn cycles to run.",
    )
    ap.add_argument(
        "--require-embedder",
        action="store_true",
        help="Fail instead of skipping embed_query checks when the local embedder backend is unavailable.",
    )
    return ap.parse_args()


def _prepare_temp_mode_store_root() -> Path:
    temp_root = PROJECT_ROOT / "output" / "mode_switch_headless_root"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    (temp_root / "config").mkdir(parents=True, exist_ok=True)
    for name in ("config.yaml", "user_modes.yaml"):
        src = PROJECT_ROOT / "config" / name
        if src.exists():
            shutil.copy2(src, temp_root / "config" / name)
    return temp_root


def main():
    args = _parse_args()
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
    embedder_probe_state, embedder_probe_detail = _probe_embedder_query(
        "Initial/embed_query('test')",
        embedder=qe.retriever.embedder,
        prompt="test",
        require_embedder=args.require_embedder,
    )

    temp_mode_root = _prepare_temp_mode_store_root()
    prior_project_root = os.environ.get("HYBRIDRAG_PROJECT_ROOT")
    os.environ["HYBRIDRAG_PROJECT_ROOT"] = str(temp_mode_root)
    check("ModeChurn/temp config root ready", (temp_mode_root / "config" / "config.yaml").exists())

    # ==================================================================
    # PHASE 3+: Repeated OFFLINE <-> ONLINE churn
    # ==================================================================
    from src.security.credentials import resolve_credentials

    creds = resolve_credentials(use_cache=True)
    check(
        "ModeChurn/resolve_credentials",
        True,
        "has_key={} has_endpoint={}".format(creds.has_key, creds.has_endpoint),
    )

    for cycle in range(1, max(1, int(args.cycles)) + 1):
        print()
        print("--- PHASE 3.{}: Cycle {} OFFLINE -> ONLINE ---".format(cycle, cycle))
        t_online = time.perf_counter()
        try:
            online_router = _switch_mode(bundle, qe, config, creds, "online", cycle)
            check("Cycle {}/online router swapped".format(cycle), qe.llm_router is online_router)
        except Exception as e:
            check("Cycle {}/online switch".format(cycle), False, str(e))
            import traceback
            traceback.print_exc()
        print("  (online switch took {:.0f}ms)".format((time.perf_counter() - t_online) * 1000))
        _check_runtime_integrity(
            "Cycle {}/online".format(cycle),
            config=config,
            bundle=bundle,
            qe=qe,
            expected_mode="online",
            embedder_id_before=embedder_id_before,
            retriever_id_before=retriever_id_before,
            store_id_before=store_id_before,
            embedder_probe_state=embedder_probe_state,
            embedder_probe_detail=embedder_probe_detail,
            require_embedder=args.require_embedder,
        )

        print()
        print("--- PHASE 4.{}: Cycle {} ONLINE -> OFFLINE ---".format(cycle, cycle))
        t_offline = time.perf_counter()
        try:
            offline_router = _switch_mode(bundle, qe, config, creds, "offline", cycle)
            check("Cycle {}/offline router swapped".format(cycle), qe.llm_router is offline_router)
        except Exception as e:
            check("Cycle {}/offline switch".format(cycle), False, str(e))
            import traceback
            traceback.print_exc()
        print("  (offline switch took {:.0f}ms)".format((time.perf_counter() - t_offline) * 1000))
        _check_runtime_integrity(
            "Cycle {}/offline".format(cycle),
            config=config,
            bundle=bundle,
            qe=qe,
            expected_mode="offline",
            embedder_id_before=embedder_id_before,
            retriever_id_before=retriever_id_before,
            store_id_before=store_id_before,
            embedder_probe_state=embedder_probe_state,
            embedder_probe_detail=embedder_probe_detail,
            require_embedder=args.require_embedder,
        )

    # ==================================================================
    # FINAL: Post-churn integrity snapshot
    # ==================================================================
    print()
    print("--- FINAL: Post-Churn Integrity ---")
    check("Final/query_engine is not None", qe is not None)
    check("Final/llm_router is not None", qe is not None and qe.llm_router is not None)
    check("Final/retriever is not None", qe is not None and qe.retriever is not None)
    check(
        "Final/retriever.embedder is not None",
        qe is not None and qe.retriever is not None and qe.retriever.embedder is not None,
    )
    _check_runtime_integrity(
        "Final",
        config=config,
        bundle=bundle,
        qe=qe,
        expected_mode="offline",
        embedder_id_before=embedder_id_before,
        retriever_id_before=retriever_id_before,
        store_id_before=store_id_before,
        embedder_probe_state=embedder_probe_state,
        embedder_probe_detail=embedder_probe_detail,
        require_embedder=args.require_embedder,
    )

    # ==================================================================
    # SUMMARY
    # ==================================================================
    print()
    print("=" * 65)
    passed = sum(1 for _, status, _ in results if status == "PASS")
    failed = sum(1 for _, status, _ in results if status == "FAIL")
    skipped = sum(1 for _, status, _ in results if status == "SKIP")
    print("  SUMMARY: {} passed, {} failed, {} skipped, {} total".format(
        passed, failed, skipped, len(results)))
    print("=" * 65)

    if failed:
        print()
        print("  FAILURES:")
        for name, status, detail in results:
            if status == "FAIL":
                print("    [FAIL] {} -- {}".format(name, detail))
        print()
    elif skipped:
        print()
        print("  SKIPPED:")
        for name, status, detail in results:
            if status == "SKIP":
                print("    [SKIP] {} -- {}".format(name, detail))
        print()

    if prior_project_root is None:
        os.environ.pop("HYBRIDRAG_PROJECT_ROOT", None)
    else:
        os.environ["HYBRIDRAG_PROJECT_ROOT"] = prior_project_root

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
