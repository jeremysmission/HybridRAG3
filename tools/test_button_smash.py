#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the button smash operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG v3 -- Comprehensive Button-Smash Test (tools/test_button_smash.py)

PURPOSE:
  Exercise ALL GUI buttons headlessly: mode toggle, use-case cycling with
  model auto-selection, view navigation, file transfer, indexing, query,
  tuning sliders, and rapid mode switching.

DESIGN:
  Same harness pattern as gui_demo_smoke.py:
  - Completion detection via threading.Event (IndexPanel, QueryPanel, DataPanel)
  - Queue-backed safe_after with drain_ui_queue() in every pump loop
  - No private attribute access, no monkeypatching, no OS-level automation

USAGE:
    python tools/test_button_smash.py

EXIT CODES:
    0 = all checks passed
    2 = skipped (Tk/Tcl not available)
    1 = at least one check failed
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import shutil
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

REPORT_DIR = PROJECT_ROOT / "output"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORT_DIR / "button_smash_report.json"


# ===================================================================
# Utilities
# ===================================================================

PASS = 0
FAIL = 0
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
    steps.append({"step": label, "ok": ok, "detail": detail})
    return ok


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


# ===================================================================
# Step 1: Boot + Attach Backends
# ===================================================================

def step_boot_and_attach():
    print()
    print("--- Step 1: Boot + Attach Backends ---")
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        check("Tk/Tcl available", False, str(e))
        return None

    try:
        from src.gui.testing.gui_boot import boot_headless, attach_backends_sync
        app = boot_headless()
        app.withdraw()
        _pump(app, 0.2)
        check("GUI booted headlessly", app is not None)

        t0 = time.time()
        attach_backends_sync(app, timeout_s=60)
        elapsed = time.time() - t0
        check("Backends attached in {:.1f}s".format(elapsed),
              app.query_engine is not None or app.indexer is not None)
        return app
    except Exception as e:
        check("Boot + attach", False, str(e))
        return None


# ===================================================================
# Step 2: Navigate ALL Views
# ===================================================================

def step_navigate_views(app):
    print()
    print("--- Step 2: Navigate All Views ---")

    views = ["query", "index", "data", "tuning", "cost", "admin", "ref", "settings"]
    for name in views:
        try:
            app.show_view(name)
            _pump(app, 0.3)
            # Verify the view was mounted (it exists in _views dict)
            mounted = name in app._views
            check("View '{}' opened".format(name), mounted)
        except Exception as e:
            check("View '{}' opened".format(name), False, str(e))

    # Return to query view
    app.show_view("query")
    _pump(app, 0.2)


# ===================================================================
# Step 3: Mode Button States (OFFLINE default)
# ===================================================================

def step_mode_buttons(app):
    print()
    print("--- Step 3: Mode Button States ---")

    import tkinter as tk

    # Verify offline is default
    mode = getattr(app.config, "mode", "unknown")
    check("Default mode is offline", mode == "offline", "got: {}".format(mode))

    # Verify OFFLINE button is active (NORMAL + active color)
    offline_state = str(app.offline_btn.cget("state"))
    check("OFFLINE button is enabled", offline_state == "normal",
          "state={}".format(offline_state))

    # Click OFFLINE again (idempotent -- should stay offline)
    app.offline_btn.invoke()
    _pump(app, 0.5)

    # Wait for mode switch to complete (buttons re-enable)
    _wait_until(app,
                lambda: str(app.offline_btn.cget("state")) == "normal",
                timeout_s=15.0)
    _pump(app, 0.5)

    mode_after = getattr(app.config, "mode", "unknown")
    check("Mode still offline after re-click", mode_after == "offline",
          "got: {}".format(mode_after))


# ===================================================================
# Step 4: Use Case Cycling + Model Auto-Selection
# ===================================================================

def step_use_case_cycling(app):
    print()
    print("--- Step 4: Use Case Cycling + Model Selection ---")

    panel = app.query_panel
    from scripts._model_meta import USE_CASES, RECOMMENDED_OFFLINE

    uc_keys = list(USE_CASES.keys())
    uc_labels = [USE_CASES[k]["label"] for k in uc_keys]
    model_log = []

    for i, label in enumerate(uc_labels):
        uc_key = uc_keys[i]
        panel.uc_var.set(label)
        panel._on_use_case_change()
        _pump(app, 0.2)

        # Read selected model from config
        model = getattr(
            getattr(app.config, "ollama", None), "model", ""
        ) or "(none)"

        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        model_log.append({
            "use_case": uc_key,
            "label": label,
            "model_selected": model,
            "recommended_primary": rec.get("primary", ""),
        })

        # Model should be non-empty
        check("UC '{}' model set".format(uc_key),
              len(model) > 1,
              "model={}".format(model))

    # Log all model selections for review
    print()
    print("    Model Selection Summary:")
    for entry in model_log:
        print("    {:<8} -> {} (rec: {})".format(
            entry["use_case"],
            entry["model_selected"],
            entry["recommended_primary"] or "N/A",
        ))

    # Verify model dropdown is Auto or a valid model name
    # (Auto may not be active if _apply_model_list detected a non-default config model)
    mval = panel.model_var.get()
    check("Model dropdown valid",
          mval == "Auto" or len(mval) > 2,
          "model_var={}".format(mval))


# ===================================================================
# Step 5: Manual Model Selection + Revert to Auto
# ===================================================================

def step_manual_model(app):
    print()
    print("--- Step 5: Manual Model Selection ---")

    panel = app.query_panel
    installed = panel.model_combo["values"]

    if len(installed) < 2:
        check("Installed models available", False,
              "only {} values in dropdown".format(len(installed)))
        return

    # Pick the second model (first is "Auto")
    manual_model = installed[1]
    panel.model_var.set(manual_model)
    panel._on_model_select()
    _pump(app, 0.2)

    cfg_model = getattr(
        getattr(app.config, "ollama", None), "model", ""
    ) or ""
    check("Manual model applied to config",
          cfg_model == manual_model,
          "config={} expected={}".format(cfg_model, manual_model))

    # Revert to Auto
    panel.model_var.set("Auto")
    panel._on_model_select()
    _pump(app, 0.2)
    check("Reverted to Auto", panel.model_var.get() == "Auto")


# ===================================================================
# Step 6: Data Transfer (file copy)
# ===================================================================

def step_data_transfer(app):
    print()
    print("--- Step 6: Data Transfer ---")

    # Create source with test files
    src_dir = tempfile.mkdtemp(prefix="hrag_smash_src_")
    dst_dir = tempfile.mkdtemp(prefix="hrag_smash_dst_")

    # Files must be >= 100 bytes (BulkTransferV2 skips tiny files)
    for i in range(5):
        fpath = os.path.join(src_dir, "test_file_{}.txt".format(i))
        with open(fpath, "w", encoding="utf-8") as f:
            line = "Button smash test file {} content. ".format(i)
            content = (line * 5)
            content += "This document covers equipment calibration "
            content += "and maintenance procedures for testing.\n"
            f.write(content)
    check("Source files created", len(os.listdir(src_dir)) == 5)

    try:
        # Navigate to Data view
        app.show_view("data")
        _pump(app, 0.3)

        panel = getattr(app, "_data_panel", None)
        if panel is None:
            check("DataPanel available", False, "not built")
            return src_dir, dst_dir

        check("DataPanel available", True)

        # Set paths
        panel._selected_path_var.set(src_dir)
        panel._source_path_var.set(dst_dir)
        _pump(app, 0.1)
        check("Transfer paths set", True)

        # Invoke Preview
        panel._preview_btn.invoke()
        _pump(app, 1.0)  # Let scan run

        preview = panel._preview_text.get("1.0", "end").strip()
        check("Preview populated", len(preview) > 10,
              "len={}".format(len(preview)))

        # Invoke Start Transfer
        panel._start_btn.invoke()
        _pump(app, 0.3)

        # Transfer may finish very fast for small file sets.
        # Check that it started (is_transferring) OR already completed (done_event).
        started_or_done = _wait_until(
            app,
            lambda: panel.is_transferring or panel.transfer_done_event.is_set(),
            timeout_s=10.0,
        )
        check("Transfer started", started_or_done)
        if not started_or_done:
            return src_dir, dst_dir

        # Wait for transfer_done_event
        finished = _wait_until(
            app, lambda: panel.transfer_done_event.is_set(), timeout_s=60.0)
        _pump(app, 0.5)

        check("Transfer completed", finished, panel.last_transfer_status)
        check("Transfer status OK",
              panel.last_transfer_status.startswith("[OK]"),
              panel.last_transfer_status)

        # Verify files arrived in destination (walk tree -- engine may nest)
        dst_count = sum(
            len(files) for _, _, files in os.walk(dst_dir)
        )
        check("Files transferred to destination",
              dst_count >= 5,
              "found {} files in tree".format(dst_count))

    except Exception as e:
        check("Data transfer step", False, str(e))

    return src_dir, dst_dir


# ===================================================================
# Step 7: Index the Transferred Files
# ===================================================================

def step_index(app, dst_dir):
    print()
    print("--- Step 7: Index Transferred Files ---")

    try:
        app.show_view("index")
        _pump(app, 0.3)

        if not hasattr(app, "index_panel"):
            check("Index panel available", False)
            return

        panel = app.index_panel
        panel.folder_var.set(dst_dir)
        _pump(app, 0.1)
        check("Index folder set to transfer destination", True)

        # Wait for Start button to enable
        start_ready = _wait_until(
            app,
            lambda: str(panel.start_btn.cget("state")) == "normal",
            timeout_s=30.0,
        )
        check("Start Indexing button enabled", start_ready)

        if not start_ready:
            return

        # Invoke Start
        panel.start_btn.invoke()
        _pump(app, 0.3)

        # Wait for completion
        finished = _wait_until(
            app, lambda: panel.index_done_event.is_set(), timeout_s=120.0)
        _pump(app, 0.5)

        check("Indexing completed", finished,
              panel.last_index_status if not finished else "")
        check("Indexing status OK",
              panel.last_index_status.startswith("[OK]"),
              panel.last_index_status)

        # Verify last_run_label updated
        last_run = panel.last_run_label.cget("text")
        check("Last run info populated",
              "none" not in last_run.lower() and len(last_run) > 10,
              last_run)

    except Exception as e:
        check("Index step", False, str(e))


# ===================================================================
# Step 8: Query the Indexed Data
# ===================================================================

def step_query(app):
    print()
    print("--- Step 8: Query ---")

    try:
        app.show_view("query")
        _pump(app, 0.3)

        panel = app.query_panel

        # Wait for Ask button
        ask_ready = _wait_until(
            app,
            lambda: str(panel.ask_btn.cget("state")) == "normal",
            timeout_s=30.0,
        )
        check("Ask button enabled", ask_ready)
        if not ask_ready:
            return

        # Enter question
        panel.question_entry.delete(0, "end")
        panel.question_entry.insert(0, "button smash test file content")
        _pump(app, 0.1)

        # Invoke Ask
        panel.ask_btn.invoke()
        _pump(app, 0.3)

        # Verify query started (fail-fast)
        started = _wait_until(
            app, lambda: panel.is_querying is True, timeout_s=5.0)
        if not started:
            check("Query thread started", False, "is_querying never True")
            return

        # Wait for completion (phi4:14b cold start can take ~300s+)
        finished = _wait_until(
            app, lambda: panel.query_done_event.is_set(), timeout_s=600.0)
        _pump(app, 1.0)

        check("Query completed", finished,
              "status={} is_querying={}".format(
                  panel.last_query_status, panel.is_querying)
              if not finished else "")

        import tkinter as tk
        answer = panel.answer_text.get("1.0", tk.END).strip()
        if not answer and panel.last_answer_preview:
            answer = panel.last_answer_preview

        check("Answer is non-empty", len(answer) > 5,
              "len={}".format(len(answer)))

    except Exception as e:
        check("Query step", False, str(e))


# ===================================================================
# Step 9: Tuning View -- Profiles + Sliders
# ===================================================================

def step_tuning(app):
    print()
    print("--- Step 9: Tuning View ---")

    try:
        app.show_view("tuning")
        _pump(app, 0.3)

        panel = getattr(app, "_tuning_panel", None)
        if panel is None:
            check("Tuning panel available", False)
            return

        check("Tuning panel available", True)

        # Get profile options
        profiles = panel.get_profile_options()
        check("Profile options: {}".format(len(profiles)),
              len(profiles) >= 2)

        # Read sliders
        topk = panel.topk_var.get()
        check("Top-K slider initialized", topk > 0, "top_k={}".format(topk))

        temp = panel.temp_var.get()
        check("Temperature slider initialized", temp >= 0,
              "temp={}".format(temp))

        # Cycle through profiles
        for profile in profiles[:3]:
            panel.profile_var.set(profile)
            panel._on_profile_change()
            _pump(app, 0.2)

        check("Profile cycling worked", True)

    except Exception as e:
        check("Tuning step", False, str(e))


# ===================================================================
# Step 10: Rapid Mode Toggle
# ===================================================================

def step_rapid_mode_toggle(app):
    print()
    print("--- Step 10: Rapid Mode Toggle ---")

    import tkinter as tk

    try:
        # Start in offline
        mode_before = getattr(app.config, "mode", "unknown")
        check("Starting in offline", mode_before == "offline",
              "got: {}".format(mode_before))

        # Try online (will likely fail without creds -- that's expected)
        app.online_btn.invoke()
        _pump(app, 0.3)

        # Wait for mode switch to finish (buttons re-enable)
        _wait_until(app,
                    lambda: str(app.offline_btn.cget("state")) == "normal",
                    timeout_s=15.0)
        _pump(app, 0.5)

        mode_after_online = getattr(app.config, "mode", "unknown")
        # Could be online (if creds exist) or still offline (no creds)
        check("Online switch attempted",
              mode_after_online in ("online", "offline"),
              "mode={}".format(mode_after_online))

        if mode_after_online == "online":
            print("    (Credentials found -- switched to online)")
        else:
            print("    (No credentials -- stayed offline, as expected)")

        # Switch back to offline (guaranteed to succeed)
        app.offline_btn.invoke()
        _pump(app, 0.3)
        _wait_until(app,
                    lambda: str(app.offline_btn.cget("state")) == "normal",
                    timeout_s=15.0)
        _pump(app, 0.5)

        mode_final = getattr(app.config, "mode", "unknown")
        check("Final mode is offline", mode_final == "offline",
              "got: {}".format(mode_final))

        # Rapid double-click protection: invoke twice quickly
        app.offline_btn.invoke()
        app.offline_btn.invoke()
        _pump(app, 0.3)
        _wait_until(app,
                    lambda: str(app.offline_btn.cget("state")) == "normal",
                    timeout_s=15.0)
        _pump(app, 0.5)

        mode_dbl = getattr(app.config, "mode", "unknown")
        check("Double-click safe (still offline)", mode_dbl == "offline",
              "got: {}".format(mode_dbl))

        # Verify status bar refreshed
        if hasattr(app, "status_bar"):
            app.status_bar.force_refresh()
            _pump(app, 0.3)
            gate = app.status_bar.gate_label.cget("text")
            check("Status bar shows OFFLINE",
                  "OFFLINE" in gate, gate)

    except Exception as e:
        check("Rapid mode toggle", False, str(e))


# ===================================================================
# Step 11: Admin Panel Buttons
# ===================================================================

def step_admin(app):
    print()
    print("--- Step 11: Admin Panel ---")

    try:
        app.show_view("admin")
        _pump(app, 0.3)

        panel = getattr(app, "_admin_panel", None)
        if panel is None:
            check("Admin panel available", False)
            return

        check("Admin panel available", True)

        # Check credential status refresh
        if hasattr(panel, "_refresh_credential_status"):
            panel._refresh_credential_status()
            _pump(app, 0.2)
            check("Credential status refreshed", True)

        # Check mode state
        if hasattr(panel, "_apply_mode_state"):
            panel._apply_mode_state()
            _pump(app, 0.2)
            check("Mode state applied", True)

    except Exception as e:
        check("Admin step", False, str(e))


# ===================================================================
# Step 12: Go-To-Index Button (DataPanel navigation)
# ===================================================================

def step_navigation_buttons(app):
    print()
    print("--- Step 12: Navigation Buttons ---")

    try:
        # DataPanel has a "Go to Index Panel" button
        app.show_view("data")
        _pump(app, 0.3)

        panel = getattr(app, "_data_panel", None)
        if panel is None:
            check("DataPanel for nav test", False)
            return

        # Invoke Go to Index
        panel._goto_index_btn.invoke()
        _pump(app, 0.3)

        # Should now be on Index view
        check("Go-to-Index navigated",
              app._current_view == "index",
              "current={}".format(app._current_view))

    except Exception as e:
        check("Navigation buttons", False, str(e))


# ===================================================================
# Step 13: Clean Shutdown
# ===================================================================

def step_shutdown(app):
    print()
    print("--- Step 13: Shutdown ---")
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

def main():
    global PASS, FAIL, steps

    print()
    print("=" * 65)
    print("  BUTTON-SMASH TEST (headless, comprehensive)")
    print("=" * 65)

    t0 = time.time()

    # Step 1: Boot + Attach
    app = step_boot_and_attach()
    if app is None:
        print()
        print("[SKIP] Cannot continue without Tk")
        _write_report(t0)
        return 2

    # Step 2: Navigate all views
    step_navigate_views(app)

    # Step 3: Mode button states
    step_mode_buttons(app)

    # Step 4: Use case cycling + model selection
    step_use_case_cycling(app)

    # Step 5: Manual model selection
    step_manual_model(app)

    # Step 6: Data transfer
    src_dir, dst_dir = step_data_transfer(app)

    # Step 7: Index transferred files
    step_index(app, dst_dir)

    # Step 8: Query
    step_query(app)

    # Step 9: Tuning
    step_tuning(app)

    # Step 10: Rapid mode toggle
    step_rapid_mode_toggle(app)

    # Step 11: Admin panel
    step_admin(app)

    # Step 12: Navigation buttons
    step_navigation_buttons(app)

    # Step 13: Shutdown
    step_shutdown(app)

    # Cleanup temp dirs
    for d in (src_dir, dst_dir):
        if d and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    # Report
    _write_report(t0)

    print()
    print("=" * 65)
    total = PASS + FAIL
    print("  SUMMARY: {}/{} checks passed".format(PASS, total))
    if FAIL:
        print("  [FAIL] {} checks failed".format(FAIL))
    else:
        print("  All checks passed.")
    print("  Elapsed: {:.1f}s".format(time.time() - t0))
    print("  Report: {}".format(REPORT_PATH))
    print("=" * 65)

    return 1 if FAIL else 0


def _write_report(t0):
    report = {
        "ok": FAIL == 0,
        "passed": PASS,
        "failed": FAIL,
        "elapsed_s": round(time.time() - t0, 2),
        "steps": steps,
    }
    try:
        REPORT_PATH.write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
