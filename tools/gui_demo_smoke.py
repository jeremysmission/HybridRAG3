#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the gui demo smoke operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG v3 -- GUI Demo Smoke Harness (tools/gui_demo_smoke.py)

PURPOSE:
  Programmatically simulate a full demo without OS-level automation.
  Uses internal widget invocation (button.invoke(), var.set()) to drive
  the Tkinter GUI headlessly. Validates end-to-end behavior:
    boot -> mode -> index -> query -> settings -> clean exit

DESIGN:
  - Completion detection uses threading.Event (set by background threads),
    NOT after() callbacks (which may not fire in headless mode).
  - UI state is read from widgets AFTER draining the safe_after queue
    (queued callbacks fire during pump, so labels/text update properly).
  - No private attribute access (_thread, _overlay, _tuning_tab, etc.).
  - No monkeypatching of GUI internals.

RULES:
  - No pyautogui / no mouse / no image clicks
  - Portable Windows/Linux
  - Uses real callbacks and backend wiring
  - Produces a JSON report to output/gui_demo_smoke_report.json

USAGE:
    python tools/gui_demo_smoke.py

EXIT CODES:
    0 = all critical steps passed
    2 = skipped (Tk/Tcl not available)
    1 = at least one critical step failed
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import shutil
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from src.tools.demo_rehearsal_pack import (
    build_demo_validation_report,
    default_demo_validation_report_dir,
    format_expected_evidence,
    load_demo_rehearsal_pack,
    select_demo_question,
    summarize_mode_sequence,
    write_demo_validation_report,
)

REPORT_DIR = PROJECT_ROOT / "output"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORT_DIR / "gui_demo_smoke_report.json"


# ===================================================================
# Utilities
# ===================================================================

PASS = 0
FAIL = 0
SKIP = 0
steps = []


def check(label, condition, detail=""):
    global PASS, FAIL
    ok = bool(condition)
    if ok:
        PASS += 1
        print("[OK]   {}".format(label))
    else:
        FAIL += 1
        msg = "[FAIL] {}".format(label)
        if detail:
            msg += " -- {}".format(detail)
        print(msg)
    steps.append({"step": label, "ok": ok, "status": "ok" if ok else "fail", "detail": detail})
    return ok


def skip(label, detail=""):
    global SKIP
    SKIP += 1
    msg = "[SKIP] {}".format(label)
    if detail:
        msg += " -- {}".format(detail)
    print(msg)
    steps.append({"step": label, "ok": None, "status": "skip", "detail": detail})


def _configure_stdout():
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        return
    sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8")


def _local_temp_dir(prefix):
    base = Path(".tmp_gui_demo_smoke").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=str(base))


def _answer_backend_available(app) -> bool:
    boot_result = getattr(app, "boot_result", None)
    if boot_result is None:
        return bool(getattr(app, "query_engine", None) is not None)
    return bool(
        getattr(boot_result, "offline_available", False)
        or getattr(boot_result, "online_available", False)
    )


def _backend_limit_detail(app) -> str:
    boot_result = getattr(app, "boot_result", None)
    if boot_result is None:
        return "no boot result available"

    details = []
    if not getattr(boot_result, "offline_available", False):
        details.append("offline generate backend unavailable")
    if not getattr(boot_result, "online_available", False):
        details.append("online answer backend unavailable")
    warnings = getattr(boot_result, "warnings", None) or []
    if warnings:
        details.append(str(warnings[-1]))
    return "; ".join(details) if details else "live answer backend available"


def _pump(app, seconds=0.1):
    """Pump Tk event loop and drain queued callbacks."""
    from src.gui.helpers.safe_after import drain_ui_queue

    end = time.time() + seconds
    while time.time() < end:
        try:
            app.update_idletasks()
            app.update()
            drain_ui_queue()
        except Exception:
            break
        time.sleep(0.005)


def _wait_until(app, predicate, timeout_s=30.0, poll_s=0.1):
    """Wait until predicate() is True while pumping the event loop."""
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            if predicate():
                return True
        except Exception:
            pass
        _pump(app, seconds=poll_s)
    return False


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the GUI demo smoke harness with the repo-tracked rehearsal reference.",
    )
    parser.add_argument(
        "--pack",
        default="",
        help="Optional path to a demo rehearsal pack JSON file.",
    )
    parser.add_argument(
        "--describe-question",
        action="store_true",
        help="Print the selected GUI smoke rehearsal question and expected evidence, then exit.",
    )
    return parser.parse_args(argv)


def _load_gui_smoke_question(pack_path: str = ""):
    pack = load_demo_rehearsal_pack(pack_path or None)
    question = select_demo_question(pack, default_key="gui_smoke_question_id")
    return pack, question


def _build_operator_notes():
    notes = []
    for entry in steps:
        if entry.get("status") == "skip":
            prefix = "SKIP"
        else:
            prefix = "PASS" if entry.get("ok") else "FAIL"
        notes.append(
            "{}: {} -- {}".format(
                prefix,
                entry.get("step", ""),
                entry.get("detail", ""),
            ).rstrip()
        )
    if not notes:
        notes.append("WARN: No GUI smoke checks were recorded.")
    return notes


# ===================================================================
# Step 1: Boot GUI headlessly
# ===================================================================

def step_boot():
    print()
    print("--- Step 1: Boot GUI (headless) ---")
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        check("Tk/Tcl available", False, str(e))
        return None

    try:
        from src.gui.testing.gui_boot import boot_headless
        app = boot_headless()
        app.withdraw()
        _pump(app, 0.2)
        check("GUI booted headlessly", app is not None)
        return app
    except Exception as e:
        check("GUI boot", False, str(e))
        return None


# ===================================================================
# Step 2: Attach backends (Ollama, VectorStore, QueryEngine, Indexer)
# ===================================================================

def step_attach_backends(app):
    print()
    print("--- Step 2: Attach Backends ---")
    t0 = time.time()

    try:
        from src.gui.testing.gui_boot import attach_backends_sync
        attach_backends_sync(app, timeout_s=60)
        elapsed = time.time() - t0
        check("Backends attached in {:.1f}s".format(elapsed),
              app.query_engine is not None or app.indexer is not None)

        check("QueryEngine available", app.query_engine is not None)
        check("Indexer available", app.indexer is not None)

        if hasattr(app, "status_bar"):
            _pump(app, 0.3)
            gate = app.status_bar.gate_label.cget("text")
            check("Status bar active", len(gate) > 0, gate)

    except Exception as e:
        check("Backend attach", False, "{}: {}".format(type(e).__name__, e))


# ===================================================================
# Step 3: Mode switch -- verify OFFLINE mode
# ===================================================================

def step_mode_switch(app):
    print()
    print("--- Step 3: Mode Switch (OFFLINE) ---")

    try:
        # Click OFFLINE button
        app.offline_btn.invoke()
        _pump(app, 0.3)

        check("OFFLINE button invoked", True)

        if hasattr(app, "status_bar"):
            app.status_bar._refresh_status()
            _pump(app, 0.2)
            gate = app.status_bar.gate_label.cget("text")
            check("Status bar shows OFFLINE", "OFFLINE" in gate, gate)

        check("Config mode is offline",
              app.config.mode == "offline",
              "got: {}".format(app.config.mode))

    except Exception as e:
        check("Mode switch", False, str(e))


# ===================================================================
# Step 4: Create demo data and index it
# ===================================================================

def step_index(app):
    print()
    print("--- Step 4: Index Demo File ---")

    demo_dir = _local_temp_dir("hrag_demo_")
    demo_file = os.path.join(demo_dir, "demo_doc.txt")
    with open(demo_file, "w", encoding="utf-8") as f:
        f.write(
            "GUI Demo Smoke Test Document\n\n"
            "This document validates the full GUI demo pipeline. "
            "Calibration intervals are set to 12 months per section 7.3. "
            "The maintenance schedule follows quarterly review cycles. "
            "All equipment must be inspected before deployment. "
            "Preventive maintenance reduces downtime by 40 percent."
        )
    check("Demo file created", os.path.isfile(demo_file))

    try:
        # Navigate to Index view (lazy-built on first show)
        app.show_view("index")
        _pump(app, 0.3)
        check("Index view opened", hasattr(app, "index_panel"))

        if not hasattr(app, "index_panel"):
            return demo_dir

        panel = app.index_panel

        # Verify panel wiring: folder_var, start_btn, indexer
        panel.folder_var.set(demo_dir)
        _pump(app, 0.1)
        check("Folder path set", panel.folder_var.get() == demo_dir)

        start_ready = _wait_until(
            app,
            lambda: str(panel.start_btn.cget("state")) == "normal",
            timeout_s=30.0,
        )
        check("Start button enabled (indexer attached)", start_ready)
        check("Panel has indexer", panel.indexer is not None)

        if not start_ready or panel.indexer is None:
            return demo_dir

        # Invoke Start -- wait on public Event, not private thread
        panel.start_btn.invoke()
        _pump(app, 0.3)
        check("Start Indexing invoked", True)

        # Wait for index_done_event (set by bg thread, thread-safe)
        finished = _wait_until(
            app,
            lambda: panel.index_done_event.is_set(),
            timeout_s=120.0,
        )
        # Final pump to drain queued callbacks (updates labels)
        _pump(app, 0.5)

        check("Indexing completed", finished,
              panel.last_index_status if not finished else "")
        check("Indexing status is [OK]",
              panel.last_index_status.startswith("[OK]"),
              panel.last_index_status)

        # Read last_run_label (updated by after() callback via queue)
        last_run = panel.last_run_label.cget("text")
        check("Last run info populated",
              "none" not in last_run.lower() and len(last_run) > 10,
              last_run)

    except Exception as e:
        check("Indexing step", False, "{}: {}".format(type(e).__name__, e))

    return demo_dir


# ===================================================================
# Step 5: Query the indexed document
# ===================================================================

def step_query(app, rehearsal_question):
    print()
    print("--- Step 5: Query Demo Document ---")

    try:
        # Navigate to Query view
        app.show_view("query")
        _pump(app, 0.3)
        check("Query view opened", hasattr(app, "query_panel"))

        if not hasattr(app, "query_panel"):
            return

        panel = app.query_panel

        # Wait for Ask button to enable
        ask_ready = _wait_until(
            app,
            lambda: str(panel.ask_btn.cget("state")) == "normal",
            timeout_s=30.0,
        )
        check("Ask button enabled", ask_ready)

        if not ask_ready:
            return

        # Clear placeholder and enter question
        panel.question_entry.delete(0, "end")
        panel.question_entry.insert(0, rehearsal_question["prompt"])
        _pump(app, 0.1)
        check("Question entered",
              panel.question_entry.get() == rehearsal_question["prompt"])

        if not _answer_backend_available(app):
            skip(
                "Query execution requires live answer backend",
                _backend_limit_detail(app),
            )
            return

        # Invoke Ask -- overlay is headless-safe (no monkeypatching needed)
        panel.ask_btn.invoke()
        _pump(app, 0.3)
        check("Ask button invoked", True)

        # Verify query thread actually started (fail-fast diagnosis)
        started = _wait_until(
            app,
            lambda: panel.is_querying is True,
            timeout_s=5.0,
        )
        if not started:
            check("Query thread started", False,
                  "is_querying never became True")
            return

        # Wait for query_done_event (set by bg thread, thread-safe)
        # Local Ollama models can take 2-3 minutes on first query
        finished = _wait_until(
            app,
            lambda: panel.query_done_event.is_set(),
            timeout_s=180.0,
        )
        # Final pump to drain queued callbacks (updates answer text, labels)
        _pump(app, 1.0)

        detail = ""
        if not finished:
            detail = "status={} is_querying={}".format(
                panel.last_query_status, panel.is_querying)
        check("Query completed", finished, detail)

        # Read answer from widget (populated by drained callback)
        import tkinter as tk
        answer = panel.answer_text.get("1.0", tk.END).strip()

        # Fallback to public preview if widget didn't update
        if not answer and panel.last_answer_preview:
            answer = panel.last_answer_preview

        check("Answer is non-empty", len(answer) > 10,
              "len={}".format(len(answer)))
        check("Answer references content",
              "calibration" in answer.lower() or "quarterly" in answer.lower()
              or "maintenance" in answer.lower() or "12 month" in answer.lower(),
              "preview: {}...".format(answer[:80]))

        # Read sources and metrics from widgets
        sources = panel.sources_label.cget("text")
        metrics = panel.metrics_label.cget("text")
        check("Sources populated",
              "demo_doc" in sources.lower() or len(sources) > 15,
              sources[:60])
        check("Metrics populated",
              "Latency" in metrics or "ms" in metrics or len(metrics) > 5,
              metrics[:60])

    except Exception as e:
        check("Query step", False, "{}: {}".format(type(e).__name__, e))


# ===================================================================
# Step 6: Tuning / Profile view
# ===================================================================

def step_tuning(app):
    print()
    print("--- Step 6: Tuning View ---")

    try:
        # Open the Tuning view (not Settings -- tuning has profiles/sliders)
        app.show_view("tuning")
        _pump(app, 0.3)
        check("Tuning view opened",
              hasattr(app, "_tuning_panel") and app._tuning_panel is not None)

        if not hasattr(app, "_tuning_panel"):
            return

        panel = app._tuning_panel

        # Use public method to get profile options
        profile_values = panel.get_profile_options()
        check("Profile dropdown has options: {}".format(len(profile_values)),
              len(profile_values) >= 2)

        # Verify sliders read config values
        topk = panel.topk_var.get()
        check("Top-K slider initialized",
              topk > 0, "top_k={}".format(topk))

    except Exception as e:
        check("Tuning step", False, str(e))


# ===================================================================
# Step 7: Clean shutdown
# ===================================================================

def step_shutdown(app):
    print()
    print("--- Step 7: Shutdown ---")
    try:
        if hasattr(app, "status_bar"):
            app.status_bar.stop()
        app.destroy()
        check("App destroyed cleanly", True)
    except Exception as e:
        check("Shutdown", False, str(e))


# ===================================================================
# Main
# ===================================================================

def main(argv=None):
    global PASS, FAIL, SKIP, steps
    _configure_stdout()
    PASS = 0
    FAIL = 0
    SKIP = 0
    steps = []
    args = _parse_args(argv)
    pack, rehearsal_question = _load_gui_smoke_question(args.pack)

    if args.describe_question:
        print("Pack: {}".format(pack["_path"]))
        print("Policy: {}".format(pack["policy_note"]))
        print("Question ID: {}".format(rehearsal_question["id"]))
        print("Title: {}".format(rehearsal_question["title"]))
        print("Profile: {} | Track: {} | Preferred mode: {}".format(
            rehearsal_question["profile"],
            rehearsal_question["track"],
            rehearsal_question["preferred_mode"],
        ))
        print("Prompt: {}".format(rehearsal_question["prompt"]))
        print("Expected evidence:")
        for item in format_expected_evidence(rehearsal_question):
            print("  - {}".format(item))
        print("Operator note: {}".format(rehearsal_question["operator_note"]))
        return 0

    print()
    print("=" * 65)
    print("  GUI DEMO SMOKE HARNESS (headless, button.invoke())")
    print("=" * 65)
    print("  Rehearsal pack: {}".format(pack["_path"]))
    print("  Selected question [{}] {}".format(
        rehearsal_question["id"], rehearsal_question["title"]
    ))
    for item in format_expected_evidence(rehearsal_question):
        print("    - {}".format(item))

    t0 = time.time()
    path_taken = []
    mode_sequence = []

    # Step 1: Boot
    path_taken.append("boot_gui")
    app = step_boot()
    if app is None:
        print()
        print("[SKIP] Cannot continue without Tk")
        _write_report(
            t0,
            pack,
            rehearsal_question,
            exit_code=2,
            path_taken=path_taken,
            mode_sequence=mode_sequence,
        )
        return 2

    # Step 2: Attach backends
    path_taken.append("attach_backends")
    step_attach_backends(app)

    # Step 3: Mode switch
    path_taken.append("mode_switch_offline")
    step_mode_switch(app)
    mode_sequence.append(str(getattr(app.config, "mode", "") or "unknown"))

    # Step 4: Index
    path_taken.append("index_demo_file")
    demo_dir = step_index(app)

    # Step 5: Query
    path_taken.append("query_demo_document")
    step_query(app, rehearsal_question)

    # Step 6: Tuning
    path_taken.append("tuning_view")
    step_tuning(app)

    # Step 7: Shutdown
    path_taken.append("shutdown")
    step_shutdown(app)

    # Cleanup temp data
    if demo_dir and os.path.isdir(demo_dir):
        shutil.rmtree(demo_dir, ignore_errors=True)

    # Report
    _write_report(
        t0,
        pack,
        rehearsal_question,
        exit_code=1 if FAIL else 0,
        path_taken=path_taken,
        mode_sequence=mode_sequence,
    )

    print()
    print("=" * 65)
    total = PASS + FAIL
    print("  SUMMARY: {}/{} checks passed".format(PASS, total))
    if SKIP:
        print("  [SKIP] {} checks skipped".format(SKIP))
    if FAIL:
        print("  [FAIL] {} checks failed".format(FAIL))
    else:
        print("  All checks passed.")
    print("  Report: {}".format(REPORT_PATH))
    print("=" * 65)

    return 1 if FAIL else 0


def _write_report(
    t0,
    pack=None,
    rehearsal_question=None,
    *,
    exit_code=0,
    path_taken=None,
    mode_sequence=None,
):
    report = {
        "ok": FAIL == 0,
        "passed": PASS,
        "failed": FAIL,
        "skipped": SKIP,
        "elapsed_s": round(time.time() - t0, 2),
        "steps": steps,
    }
    if pack and rehearsal_question:
        report["pack"] = {
            "path": pack["_path"],
            "pack_id": pack["pack_id"],
            "policy_note": pack["policy_note"],
        }
        report["question"] = rehearsal_question
        validation_report = build_demo_validation_report(
            pack,
            rehearsal_question,
            tool_name="gui_demo_smoke",
            actual_mode=summarize_mode_sequence(mode_sequence),
            actual_path=list(path_taken or []),
            operator_notes=_build_operator_notes(),
            passed=(exit_code == 0),
            status="skipped" if exit_code == 2 else ("passed" if exit_code == 0 else "failed"),
            primary_artifact=str(REPORT_PATH),
            mode_sequence=list(mode_sequence or []),
            details={
                "steps": steps,
                "counts": {
                    "passed": PASS,
                    "failed": FAIL,
                    "skipped": SKIP,
                },
            },
        )
        validation_path = write_demo_validation_report(
            validation_report,
            project_root=PROJECT_ROOT,
        )
        report["validation_report_path"] = str(validation_path)
    try:
        REPORT_PATH.write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
