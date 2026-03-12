#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the demo transcript operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
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

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.demo_rehearsal_pack import (
    build_demo_validation_report,
    default_demo_validation_report_dir,
    format_expected_evidence,
    load_demo_rehearsal_pack,
    select_demo_question,
    summarize_mode_sequence,
    write_demo_validation_report,
)

TRANSCRIPT_OUT_PATH = PROJECT_ROOT / "demo_transcript.json"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print("[{}] {}".format(ts, msg))


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the HybridRAG demo transcript with a repo-tracked rehearsal question.",
    )
    parser.add_argument(
        "--pack",
        default="",
        help="Optional path to a demo rehearsal pack JSON file.",
    )
    parser.add_argument(
        "--question-id",
        default="",
        help="Optional rehearsal question id override for the transcript run.",
    )
    parser.add_argument(
        "--describe-question",
        action="store_true",
        help="Print the selected rehearsal question and expected evidence, then exit.",
    )
    return parser.parse_args(argv)


def _load_transcript_question(pack_path: str = "", question_id: str = ""):
    pack = load_demo_rehearsal_pack(pack_path or None)
    question = select_demo_question(
        pack,
        default_key="transcript_question_id",
        question_id=question_id,
    )
    return pack, question


def _build_operator_notes(transcript, errors):
    notes = []
    for entry in transcript:
        prefix = "PASS" if entry.get("ok") else "FAIL"
        notes.append(
            "{}: {} -- {}".format(
                prefix,
                entry.get("step", ""),
                entry.get("detail", ""),
            ).rstrip()
        )
    for error in errors:
        notes.append("WARN: {}".format(error))
    if not notes:
        notes.append("WARN: No transcript steps were recorded.")
    return notes


def _write_outputs(
    pack,
    selected_question,
    transcript,
    errors,
    *,
    mode_sequence,
    path_taken,
):
    validation_report = build_demo_validation_report(
        pack,
        selected_question,
        tool_name="demo_transcript",
        actual_mode=summarize_mode_sequence(mode_sequence),
        actual_path=path_taken,
        operator_notes=_build_operator_notes(transcript, errors),
        passed=bool(transcript) and all(entry.get("ok") for entry in transcript),
        status="passed" if transcript and all(entry.get("ok") for entry in transcript) else "failed",
        primary_artifact=str(TRANSCRIPT_OUT_PATH),
        mode_sequence=mode_sequence,
        details={
            "step_results": transcript,
            "errors": errors,
        },
    )
    validation_path = write_demo_validation_report(
        validation_report,
        project_root=PROJECT_ROOT,
    )
    TRANSCRIPT_OUT_PATH.write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "pack": {
            "path": pack["_path"],
            "pack_id": pack["pack_id"],
            "policy_note": pack["policy_note"],
        },
        "question": selected_question,
        "transcript": transcript,
        "errors": errors,
        "validation_report_path": str(validation_path),
    }, indent=2), encoding="utf-8")
    print("  Saved transcript: {}".format(TRANSCRIPT_OUT_PATH))
    print("  Saved validation: {}".format(validation_path))
    return validation_path


def main(argv=None):
    args = _parse_args(argv)
    pack, selected_question = _load_transcript_question(
        pack_path=args.pack,
        question_id=args.question_id,
    )

    if args.describe_question:
        print("Pack: {}".format(pack["_path"]))
        print("Policy: {}".format(pack["policy_note"]))
        print("Question ID: {}".format(selected_question["id"]))
        print("Title: {}".format(selected_question["title"]))
        print("Profile: {} | Track: {} | Preferred mode: {}".format(
            selected_question["profile"],
            selected_question["track"],
            selected_question["preferred_mode"],
        ))
        print("Prompt: {}".format(selected_question["prompt"]))
        print("Expected evidence:")
        for item in format_expected_evidence(selected_question):
            print("  - {}".format(item))
        print("Operator note: {}".format(selected_question["operator_note"]))
        return 0

    demo_question = selected_question["prompt"]
    transcript = []
    errors = []
    mode_sequence = []
    path_taken = []

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
    log("Rehearsal pack: {}".format(pack["_path"]))
    log("Policy: {}".format(pack["policy_note"]))
    log(
        "Selected question [{}] {} | profile={} | track={} | preferred_mode={}".format(
            selected_question["id"],
            selected_question["title"],
            selected_question["profile"],
            selected_question["track"],
            selected_question["preferred_mode"],
        )
    )
    for item in format_expected_evidence(selected_question):
        log("  Evidence target: {}".format(item))
    print()

    # ================================================================
    # STEP 1: Boot (BootCoordinator + BackendLoader)
    # ================================================================
    path_taken.append("boot")
    log("STEP 1: Booting application...")
    t_boot = time.perf_counter()

    try:
        from src.core.bootstrap.boot_coordinator import BootCoordinator
        bc = BootCoordinator(str(PROJECT_ROOT))
        boot_report = bc.run()
        config = boot_report.config
        mode_sequence.append(str(getattr(config, "mode", "") or "unknown"))
    except Exception as e:
        record("Boot/Coordinator", (time.perf_counter() - t_boot) * 1000, str(e), ok=False)
        errors.append("BootCoordinator: {}".format(e))
        print("FATAL: Cannot continue without config")
        _write_outputs(
            pack,
            selected_question,
            transcript,
            errors,
            mode_sequence=mode_sequence,
            path_taken=path_taken,
        )
        return 1

    record("Boot/Coordinator", (time.perf_counter() - t_boot) * 1000,
           "state={}".format(boot_report.state.value))

    t_backend = time.perf_counter()
    bundle = None
    creds = None
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
    path_taken.append("ibit")
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
    path_taken.append("offline_query_warmup")
    log("STEP 3: Offline query (warm-up)...")
    t_q1 = time.perf_counter()
    if bundle and bundle.query_engine:
        try:
            result = bundle.query_engine.query(demo_question)
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
    path_taken.append("switch_to_online")
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
        mode_sequence.append(str(getattr(config, "mode", "") or "online"))
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
    path_taken.append("online_query")
    log("STEP 5: Online query...")
    t_q2 = time.perf_counter()
    if bundle and bundle.query_engine and config.mode == "online":
        try:
            result2 = bundle.query_engine.query(demo_question)
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
    path_taken.append("switch_to_offline")
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
        mode_sequence.append(str(getattr(config, "mode", "") or "offline"))
        switch2_ms = (time.perf_counter() - t_switch2) * 1000
        record("Switch/ToOffline", switch2_ms)
    except Exception as e:
        record("Switch/ToOffline", (time.perf_counter() - t_switch2) * 1000,
               str(e), ok=False)
        errors.append("Switch to offline: {}".format(e))

    # ================================================================
    # STEP 7: Offline query again
    # ================================================================
    path_taken.append("offline_query_post_switch")
    log("STEP 7: Offline query (post-switch)...")
    t_q3 = time.perf_counter()
    if bundle and bundle.query_engine:
        try:
            result3 = bundle.query_engine.query(demo_question)
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

    _write_outputs(
        pack,
        selected_question,
        transcript,
        errors,
        mode_sequence=mode_sequence,
        path_taken=path_taken,
    )
    print("  Validation directory: {}".format(default_demo_validation_report_dir(PROJECT_ROOT)))
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
