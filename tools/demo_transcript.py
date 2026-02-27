#!/usr/bin/env python3
"""
HybridRAG v3 -- Demo Run Transcript

Executes the exact demo-day workflow and records timings:
  1. Boot app (BootCoordinator + BackendLoader)
  2. IBIT badge (6/6)
  3. Offline query (warm-up)
  4. Switch to online mode
  5. Online query
  6. Switch back to offline
  7. Offline query again

Outputs: plain text transcript + any stack traces.

Usage:
  python tools/demo_transcript.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEMO_QUESTION = "What leadership styles are discussed and how do they differ?"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print("[{}] {}".format(ts, msg))


def main():
    transcript = []
    errors = []

    def record(step, elapsed_ms, detail="", ok=True):
        entry = {
            "step": step,
            "elapsed_ms": round(elapsed_ms, 1),
            "detail": detail,
            "ok": ok,
        }
        transcript.append(entry)
        tag = "[OK]" if ok else "[FAIL]"
        log("{} {} -- {:.0f}ms {}".format(tag, step, elapsed_ms, detail))

    print()
    print("=" * 60)
    print("  HYBRIDRAG DEMO RUN TRANSCRIPT")
    print("  {}".format(datetime.now().isoformat()))
    print("=" * 60)
    print()

    # ================================================================
    # STEP 1: Boot (BootCoordinator + BackendLoader)
    # ================================================================
    log("STEP 1: Booting application...")
    t_boot = time.perf_counter()

    try:
        from src.core.bootstrap.boot_coordinator import BootCoordinator
        bc = BootCoordinator(str(PROJECT_ROOT))
        boot_report = bc.run()
        config = boot_report.config
    except Exception as e:
        record("Boot/Coordinator", (time.perf_counter() - t_boot) * 1000, str(e), ok=False)
        errors.append("BootCoordinator: {}".format(e))
        print("FATAL: Cannot continue without config")
        return 1

    record("Boot/Coordinator", (time.perf_counter() - t_boot) * 1000,
           "state={}".format(boot_report.state.value))

    t_backend = time.perf_counter()
    bundle = None
    try:
        from src.core.bootstrap.backend_loader import BackendLoader
        loader = BackendLoader(
            config=config,
            boot_result=boot_report.boot_result,
        )
        bundle = loader.load(timeout_seconds=60)
        record("Boot/BackendLoader", (time.perf_counter() - t_backend) * 1000,
               "errors={}".format(len(bundle.init_errors)))
        if bundle.init_errors:
            for err in bundle.init_errors:
                errors.append("BackendLoader: {}".format(err))
    except Exception as e:
        record("Boot/BackendLoader", (time.perf_counter() - t_backend) * 1000,
               str(e), ok=False)
        errors.append("BackendLoader: {}".format(e))

    boot_total_ms = (time.perf_counter() - t_boot) * 1000
    record("Boot/Total", boot_total_ms, "window render ready")

    # ================================================================
    # STEP 2: IBIT badge
    # ================================================================
    log("STEP 2: Running IBIT...")
    t_ibit = time.perf_counter()
    try:
        from src.core.ibit import run_ibit
        ibit_results = run_ibit(
            config,
            query_engine=bundle.query_engine if bundle else None,
            indexer=bundle.indexer if bundle else None,
            router=bundle.router if bundle else None,
        )
        passed = sum(1 for r in ibit_results if r.ok)
        total = len(ibit_results)
        ibit_ms = (time.perf_counter() - t_ibit) * 1000
        record("IBIT", ibit_ms, "{}/{} passed".format(passed, total),
               ok=(passed == total))
        for r in ibit_results:
            tag = "[OK]" if r.ok else "[FAIL]"
            log("  {} {} -- {} ({:.0f}ms)".format(tag, r.name, r.detail, r.elapsed_ms))
    except Exception as e:
        record("IBIT", (time.perf_counter() - t_ibit) * 1000, str(e), ok=False)
        errors.append("IBIT: {}".format(e))

    # ================================================================
    # STEP 3: Offline query (warm-up)
    # ================================================================
    log("STEP 3: Offline query (warm-up)...")
    t_q1 = time.perf_counter()
    if bundle and bundle.query_engine:
        try:
            result = bundle.query_engine.query(DEMO_QUESTION)
            q1_ms = (time.perf_counter() - t_q1) * 1000
            answer_preview = (result.answer or "")[:120].replace("\n", " ")
            record("Query/Offline1", q1_ms,
                   "chunks={} answer='{}'...".format(result.chunks_used, answer_preview))
        except Exception as e:
            record("Query/Offline1", (time.perf_counter() - t_q1) * 1000,
                   str(e), ok=False)
            errors.append("Offline query: {}".format(e))
    else:
        record("Query/Offline1", 0, "no query engine", ok=False)

    # ================================================================
    # STEP 4: Switch to online
    # ================================================================
    log("STEP 4: Switch OFFLINE -> ONLINE...")
    t_switch1 = time.perf_counter()
    try:
        from src.security.credentials import resolve_credentials
        from src.core.network_gate import configure_gate
        from src.core.llm_router import LLMRouter, invalidate_deployment_cache

        creds = resolve_credentials(use_cache=True)
        config.mode = "online"
        configure_gate(mode="online", api_endpoint=creds.endpoint or "", allowed_prefixes=[])
        invalidate_deployment_cache()
        online_router = LLMRouter(config, credentials=creds)
        # Update query engine router
        if bundle and bundle.query_engine:
            bundle.query_engine.llm_router = online_router
            bundle.router = online_router
        switch1_ms = (time.perf_counter() - t_switch1) * 1000
        record("Switch/ToOnline", switch1_ms,
               "creds={} endpoint={}".format(
                   creds.has_key, bool(creds.endpoint)))
    except Exception as e:
        record("Switch/ToOnline", (time.perf_counter() - t_switch1) * 1000,
               str(e), ok=False)
        errors.append("Switch to online: {}".format(e))

    # ================================================================
    # STEP 5: Online query
    # ================================================================
    log("STEP 5: Online query...")
    t_q2 = time.perf_counter()
    if bundle and bundle.query_engine and config.mode == "online":
        try:
            result2 = bundle.query_engine.query(DEMO_QUESTION)
            q2_ms = (time.perf_counter() - t_q2) * 1000
            answer_preview = (result2.answer or "")[:120].replace("\n", " ")
            record("Query/Online", q2_ms,
                   "chunks={} answer='{}'...".format(result2.chunks_used, answer_preview))
        except Exception as e:
            record("Query/Online", (time.perf_counter() - t_q2) * 1000,
                   str(e), ok=False)
            errors.append("Online query: {}".format(e))
    else:
        record("Query/Online", 0, "not in online mode or no engine", ok=False)

    # ================================================================
    # STEP 6: Switch back to offline
    # ================================================================
    log("STEP 6: Switch ONLINE -> OFFLINE...")
    t_switch2 = time.perf_counter()
    try:
        config.mode = "offline"
        configure_gate(mode="offline")
        invalidate_deployment_cache()
        offline_router = LLMRouter(config, credentials=creds)
        if bundle and bundle.query_engine:
            bundle.query_engine.llm_router = offline_router
            bundle.router = offline_router
        switch2_ms = (time.perf_counter() - t_switch2) * 1000
        record("Switch/ToOffline", switch2_ms)
    except Exception as e:
        record("Switch/ToOffline", (time.perf_counter() - t_switch2) * 1000,
               str(e), ok=False)
        errors.append("Switch to offline: {}".format(e))

    # ================================================================
    # STEP 7: Offline query again
    # ================================================================
    log("STEP 7: Offline query (post-switch)...")
    t_q3 = time.perf_counter()
    if bundle and bundle.query_engine:
        try:
            result3 = bundle.query_engine.query(DEMO_QUESTION)
            q3_ms = (time.perf_counter() - t_q3) * 1000
            answer_preview = (result3.answer or "")[:120].replace("\n", " ")
            record("Query/Offline2", q3_ms,
                   "chunks={} answer='{}'...".format(result3.chunks_used, answer_preview))
        except Exception as e:
            record("Query/Offline2", (time.perf_counter() - t_q3) * 1000,
                   str(e), ok=False)
            errors.append("Offline query 2: {}".format(e))
    else:
        record("Query/Offline2", 0, "no query engine", ok=False)

    # ================================================================
    # SUMMARY
    # ================================================================
    print()
    print("=" * 60)
    print("  DEMO TRANSCRIPT SUMMARY")
    print("=" * 60)
    for t in transcript:
        tag = "[OK]" if t["ok"] else "[FAIL]"
        print("  {} {:25s} {:>8.0f}ms  {}".format(
            tag, t["step"], t["elapsed_ms"], t["detail"][:60]))

    if errors:
        print()
        print("  ERRORS/WARNINGS:")
        for e in errors:
            print("    [WARN] {}".format(e))

    print()
    total_demo_ms = sum(t["elapsed_ms"] for t in transcript if "Total" not in t["step"])
    print("  Total demo time: {:.1f}s".format(total_demo_ms / 1000))
    print()

    # Save JSON
    out_path = PROJECT_ROOT / "demo_transcript.json"
    out_path.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "transcript": transcript,
        "errors": errors,
    }, indent=2), encoding="utf-8")
    print("  Saved: {}".format(out_path))
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
