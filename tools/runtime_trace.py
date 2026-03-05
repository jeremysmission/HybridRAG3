#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the runtime trace operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG v3 -- Runtime Trace Script

Measures and reports timings for the demo-critical path:
  1. BootCoordinator (config + validation)
  2. BackendLoader (embedder + vector store + router, parallel)
  3. IBIT (6 checks, run AFTER backends are loaded)
  4. Mode switch: OFFLINE -> ONLINE -> OFFLINE (with credential cache)

Outputs: runtime_traces_after.json

Usage:
  python tools/runtime_trace.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class TraceStep:
    name: str
    ok: bool
    elapsed_ms: float
    detail: str = ""


@dataclass
class TraceReport:
    timestamp: str = ""
    commit: str = ""
    steps: List[TraceStep] = field(default_factory=list)
    ibit_results: List[Dict[str, Any]] = field(default_factory=list)
    mode_switch: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def _get_commit() -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run_trace() -> TraceReport:
    report = TraceReport()
    report.timestamp = datetime.now().isoformat()
    report.commit = _get_commit()

    # ================================================================
    # STEP 1: BootCoordinator
    # ================================================================
    print("  [1/4] BootCoordinator...")
    t0 = time.perf_counter()
    boot_report = None
    config = None
    try:
        from src.core.bootstrap.boot_coordinator import BootCoordinator
        bc = BootCoordinator(str(PROJECT_ROOT))
        boot_report = bc.run()
        config = boot_report.config
        elapsed = (time.perf_counter() - t0) * 1000
        ok = boot_report.ok if boot_report else False

        report.steps.append(TraceStep(
            "BootCoordinator", ok, elapsed,
            "state={} steps={}".format(
                boot_report.state.value if boot_report else "NONE",
                len(boot_report.steps) if boot_report else 0,
            ),
        ))
        # Add sub-step timings
        if boot_report and boot_report.steps:
            for bs in boot_report.steps:
                report.steps.append(TraceStep(
                    "  boot/" + bs.name, bs.ok, bs.elapsed_ms, bs.detail,
                ))
        print("    {:.0f}ms -- {}".format(elapsed, "OK" if ok else "ISSUES"))
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        report.steps.append(TraceStep("BootCoordinator", False, elapsed, str(e)))
        report.warnings.append("BootCoordinator failed: {}".format(e))
        print("    {:.0f}ms -- FAIL: {}".format(elapsed, e))

    # ================================================================
    # STEP 2: BackendLoader (parallel: store + embedder + router)
    # ================================================================
    print("  [2/4] BackendLoader...")
    t1 = time.perf_counter()
    bundle = None
    try:
        from src.core.bootstrap.backend_loader import BackendLoader
        loader = BackendLoader(
            config=config,
            boot_result=boot_report.boot_result if boot_report else None,
            stage_cb=lambda msg: print("    stage: {}".format(msg)),
        )
        bundle = loader.load(timeout_seconds=30)
        elapsed = (time.perf_counter() - t1) * 1000

        report.steps.append(TraceStep(
            "BackendLoader", len(bundle.init_errors) == 0, elapsed,
            "errors={} components=store:{} emb:{} rtr:{} qe:{}".format(
                len(bundle.init_errors),
                bundle.store is not None,
                bundle.embedder is not None,
                bundle.router is not None,
                bundle.query_engine is not None,
            ),
        ))
        # Sub-timings
        for k, v in sorted(bundle.timings_ms.items()):
            report.steps.append(TraceStep("  backend/" + k, True, v, ""))
        if bundle.init_errors:
            for err in bundle.init_errors:
                report.warnings.append("BackendLoader: {}".format(err))
        print("    {:.0f}ms -- {} errors".format(elapsed, len(bundle.init_errors)))
    except Exception as e:
        elapsed = (time.perf_counter() - t1) * 1000
        report.steps.append(TraceStep("BackendLoader", False, elapsed, str(e)))
        report.warnings.append("BackendLoader failed: {}".format(e))
        print("    {:.0f}ms -- FAIL: {}".format(elapsed, e))

    # ================================================================
    # STEP 3: IBIT (AFTER backends are loaded -- must show 6/6)
    # ================================================================
    print("  [3/4] IBIT...")
    t2 = time.perf_counter()
    try:
        from src.core.ibit import run_ibit
        ibit_results = run_ibit(
            config,
            query_engine=bundle.query_engine if bundle else None,
            indexer=bundle.indexer if bundle else None,
            router=bundle.router if bundle else None,
        )
        elapsed = (time.perf_counter() - t2) * 1000
        passed = sum(1 for r in ibit_results if r.ok)
        total = len(ibit_results)

        report.steps.append(TraceStep(
            "IBIT", passed == total, elapsed,
            "{}/{} passed".format(passed, total),
        ))
        for r in ibit_results:
            report.ibit_results.append({
                "name": r.name,
                "ok": r.ok,
                "detail": r.detail,
                "elapsed_ms": round(r.elapsed_ms, 2),
            })
            tag = "[OK]" if r.ok else "[FAIL]"
            print("    {} {} -- {} ({:.0f}ms)".format(tag, r.name, r.detail, r.elapsed_ms))
        print("    {:.0f}ms total -- {}/{} passed".format(elapsed, passed, total))
    except Exception as e:
        elapsed = (time.perf_counter() - t2) * 1000
        report.steps.append(TraceStep("IBIT", False, elapsed, str(e)))
        report.warnings.append("IBIT failed: {}".format(e))
        print("    {:.0f}ms -- FAIL: {}".format(elapsed, e))

    # ================================================================
    # STEP 4: Mode switch timing (OFFLINE -> ONLINE -> OFFLINE)
    # ================================================================
    print("  [4/4] Mode switch timing...")
    mode_results = {}

    # We test the core of mode switching without GUI:
    # - resolve_credentials (cached vs fresh)
    # - LLMRouter rebuild
    # - network_gate reconfigure

    # 4a: Credential resolution (fresh -- first call, hits keyring)
    from src.security.credentials import resolve_credentials, invalidate_credential_cache
    invalidate_credential_cache()
    t3 = time.perf_counter()
    creds = resolve_credentials(use_cache=False)
    cred_fresh_ms = (time.perf_counter() - t3) * 1000
    mode_results["credential_fresh_ms"] = round(cred_fresh_ms, 1)
    print("    credential resolve (fresh): {:.0f}ms".format(cred_fresh_ms))

    # 4b: Credential resolution (cached -- should be ~0ms)
    t4 = time.perf_counter()
    creds2 = resolve_credentials(use_cache=True)
    cred_cached_ms = (time.perf_counter() - t4) * 1000
    mode_results["credential_cached_ms"] = round(cred_cached_ms, 1)
    print("    credential resolve (cached): {:.3f}ms".format(cred_cached_ms))

    # 4c: OFFLINE -> ONLINE switch (router rebuild + gate reconfig)
    if config:
        config.mode = "online"
    t5 = time.perf_counter()
    try:
        from src.core.network_gate import configure_gate
        configure_gate(
            mode="online",
            api_endpoint=creds.endpoint or "",
            allowed_prefixes=[],
        )
        from src.core.llm_router import LLMRouter, invalidate_deployment_cache
        invalidate_deployment_cache()
        online_router = LLMRouter(config, credentials=creds)
        offline_to_online_ms = (time.perf_counter() - t5) * 1000
        mode_results["offline_to_online_ms"] = round(offline_to_online_ms, 1)
        print("    OFFLINE->ONLINE: {:.0f}ms".format(offline_to_online_ms))
    except Exception as e:
        offline_to_online_ms = (time.perf_counter() - t5) * 1000
        mode_results["offline_to_online_ms"] = round(offline_to_online_ms, 1)
        mode_results["offline_to_online_error"] = str(e)
        report.warnings.append("OFFLINE->ONLINE failed: {}".format(e))
        print("    OFFLINE->ONLINE: {:.0f}ms (ERROR: {})".format(offline_to_online_ms, e))

    # 4d: ONLINE -> OFFLINE switch
    if config:
        config.mode = "offline"
    t6 = time.perf_counter()
    try:
        configure_gate(mode="offline")
        invalidate_deployment_cache()
        offline_router = LLMRouter(config, credentials=creds)
        online_to_offline_ms = (time.perf_counter() - t6) * 1000
        mode_results["online_to_offline_ms"] = round(online_to_offline_ms, 1)
        print("    ONLINE->OFFLINE: {:.0f}ms".format(online_to_offline_ms))
    except Exception as e:
        online_to_offline_ms = (time.perf_counter() - t6) * 1000
        mode_results["online_to_offline_ms"] = round(online_to_offline_ms, 1)
        mode_results["online_to_offline_error"] = str(e)
        report.warnings.append("ONLINE->OFFLINE failed: {}".format(e))
        print("    ONLINE->OFFLINE: {:.0f}ms (ERROR: {})".format(online_to_offline_ms, e))

    # 4e: Credential resolution with env vars (simulating demo setup)
    os.environ["HYBRIDRAG_API_KEY"] = "demo-test-key-12345678"
    os.environ["HYBRIDRAG_API_ENDPOINT"] = "https://demo.openai.azure.com"
    invalidate_credential_cache()
    t7 = time.perf_counter()
    creds_env = resolve_credentials(use_cache=False)
    cred_env_ms = (time.perf_counter() - t7) * 1000
    mode_results["credential_env_only_ms"] = round(cred_env_ms, 3)
    print("    credential resolve (env-only): {:.3f}ms".format(cred_env_ms))
    # Clean up
    os.environ.pop("HYBRIDRAG_API_KEY", None)
    os.environ.pop("HYBRIDRAG_API_ENDPOINT", None)
    invalidate_credential_cache()

    report.mode_switch = mode_results
    report.steps.append(TraceStep(
        "ModeSwitch",
        mode_results.get("offline_to_online_ms", 99999) < 2000
        and mode_results.get("online_to_offline_ms", 99999) < 2000,
        mode_results.get("offline_to_online_ms", 0)
        + mode_results.get("online_to_offline_ms", 0),
        "off->on={:.0f}ms on->off={:.0f}ms cred_fresh={:.0f}ms cred_cached={:.3f}ms".format(
            mode_results.get("offline_to_online_ms", 0),
            mode_results.get("online_to_offline_ms", 0),
            mode_results.get("credential_fresh_ms", 0),
            mode_results.get("credential_cached_ms", 0),
        ),
    ))

    # ================================================================
    # SUMMARY
    # ================================================================
    all_ok = all(s.ok for s in report.steps if not s.name.startswith("  "))
    total_ms = sum(
        s.elapsed_ms for s in report.steps
        if not s.name.startswith("  ")
    )
    ibit_passed = sum(1 for r in report.ibit_results if r["ok"])
    ibit_total = len(report.ibit_results)

    report.summary = {
        "all_ok": all_ok,
        "total_ms": round(total_ms, 1),
        "ibit_score": "{}/{}".format(ibit_passed, ibit_total),
        "offline_to_online_ms": mode_results.get("offline_to_online_ms", -1),
        "online_to_offline_ms": mode_results.get("online_to_offline_ms", -1),
        "credential_fresh_ms": mode_results.get("credential_fresh_ms", -1),
        "credential_cached_ms": mode_results.get("credential_cached_ms", -1),
        "credential_env_only_ms": mode_results.get("credential_env_only_ms", -1),
        "warnings_count": len(report.warnings),
        "target_met": (
            mode_results.get("offline_to_online_ms", 99999) < 2000
            and mode_results.get("online_to_offline_ms", 99999) < 2000
        ),
    }

    return report


def main():
    print()
    print("=" * 60)
    print("  HYBRIDRAG RUNTIME TRACE (post-359d2c1)")
    print("=" * 60)
    print()

    report = run_trace()

    print()
    print("  SUMMARY")
    print("  " + "-" * 40)
    s = report.summary
    print("  IBIT:                {}".format(s["ibit_score"]))
    print("  OFFLINE->ONLINE:     {:.0f}ms".format(s["offline_to_online_ms"]))
    print("  ONLINE->OFFLINE:     {:.0f}ms".format(s["online_to_offline_ms"]))
    print("  Credential (fresh):  {:.0f}ms".format(s["credential_fresh_ms"]))
    print("  Credential (cached): {:.3f}ms".format(s["credential_cached_ms"]))
    print("  Credential (env):    {:.3f}ms".format(s["credential_env_only_ms"]))
    print("  Target met (<2s):    {}".format(s["target_met"]))
    if report.warnings:
        print()
        print("  WARNINGS:")
        for w in report.warnings:
            print("    [WARN] {}".format(w))
    print()

    out_path = PROJECT_ROOT / "runtime_traces_after.json"
    out_path.write_text(
        json.dumps(asdict(report), indent=2),
        encoding="utf-8",
    )
    print("  Report saved: {}".format(out_path))
    print()

    return 0 if s.get("target_met") else 1


if __name__ == "__main__":
    raise SystemExit(main())
