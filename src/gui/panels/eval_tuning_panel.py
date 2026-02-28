# ============================================================================
# HybridRAG v3 -- Eval / Tuning Panel (src/gui/panels/eval_tuning_panel.py)
# ============================================================================
#
# WHAT THIS FILE DOES (plain English):
#   Provides a GUI panel for running the 400-question golden evaluation
#   directly from the application. Calls eval_runner.py and score_results.py
#   as subprocesses, streams progress, and displays scored results with
#   breakdowns by role and question type.
#
# WHY THIS EXISTS:
#   Previously, eval runs required opening a terminal and running CLI
#   commands. This panel lets users run and monitor evaluations from the
#   GUI, making it accessible for work-laptop use without terminal access.
#
# DESIGN DECISIONS:
#   1. SUBPROCESS-BASED (not in-process)
#      Eval runs via tools/eval_runner.py and tools/score_results.py as
#      subprocesses. This preserves the sacred rule: NEVER modify eval
#      files. The GUI wraps them, it doesn't replace them.
#
#   2. PROGRESS FROM JSONL STREAMING
#      eval_runner.py writes results.jsonl line-by-line. The GUI polls
#      the file size to track progress (questions completed / total).
#
#   3. TWO-PHASE DISPLAY
#      Phase 1: Eval running (progress bar, ETA, current question count)
#      Phase 2: Scoring complete (summary table, breakdowns, export)
#
# INTERNET ACCESS: NONE (subprocess inherits parent environment)
# ============================================================================

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Optional

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_MONO


# ------------------------------------------------------------------
# Locate project root (needed for subprocess working directory)
# ------------------------------------------------------------------
def _find_project_root() -> str:
    """Walk up from this file to find the repo root (has config/ dir)."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isdir(os.path.join(d, "config")):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


PROJECT_ROOT = _find_project_root()


# ======================================================================
# MODULE-LEVEL FORMATTERS (extracted from class to stay under 500 lines)
# ======================================================================

def format_eta(seconds):
    """Format ETA as human-readable string."""
    if seconds <= 0:
        return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return "ETA: {}h {}m".format(h, m)
    if m > 0:
        return "ETA: {}m {}s".format(m, s)
    return "ETA: {}s".format(s)


def format_type_breakdown(summary):
    """Return formatted type-breakdown table string from summary dict."""
    by_type = summary.get("by_type", {})
    if not by_type:
        return ""

    lines = []
    header = "{:<16} {:>6} {:>10} {:>8} {:>8}".format(
        "Type", "Count", "Pass Rate", "p50 ms", "p95 ms",
    )
    lines.append(header)
    lines.append("-" * len(header))

    type_order = ["answerable", "unanswerable", "injection", "ambiguous"]
    for qtype in type_order:
        stats = by_type.get(qtype, {})
        if not stats:
            continue
        pr = stats.get("pass_rate", 0)
        lines.append("{:<16} {:>6} {:>9.1f}% {:>8} {:>8}".format(
            qtype,
            stats.get("count", 0),
            pr * 100,
            stats.get("p50_latency_ms", 0),
            stats.get("p95_latency_ms", 0),
        ))

    gates = summary.get("acceptance_gates", {})
    if gates:
        lines.append("")
        lines.append("Acceptance Gates:")
        ua = gates.get("unanswerable_accuracy_proxy", 0)
        ir = gates.get("injection_resistance_proxy", 0)
        lines.append("  Unanswerable accuracy:  {:.1f}%".format(ua * 100))
        lines.append("  Injection resistance:   {:.1f}%".format(ir * 100))

    return "\n".join(lines)


def format_role_breakdown(summary):
    """Return formatted role-breakdown table string from summary dict."""
    by_role = summary.get("by_role", {})
    if not by_role:
        return ""

    lines = []
    header = "{:<24} {:>6} {:>10} {:>8} {:>8} {:>10}".format(
        "Role", "Count", "Pass Rate", "p50 ms", "p95 ms", "Avg Cost",
    )
    lines.append(header)
    lines.append("-" * len(header))

    for role in sorted(by_role.keys()):
        stats = by_role[role]
        pr = stats.get("pass_rate", 0)
        lines.append("{:<24} {:>6} {:>9.1f}% {:>8} {:>8} {:>10}".format(
            role[:24],
            stats.get("count", 0),
            pr * 100,
            stats.get("p50_latency_ms", 0),
            stats.get("p95_latency_ms", 0),
            "${:.4f}".format(stats.get("avg_cost_usd", 0)),
        ))

    return "\n".join(lines)


def format_failures(scored_rows):
    """Return formatted failure details string."""
    failures = [r for r in scored_rows if not r.get("passed", True)]

    if not failures:
        return "No failures -- all questions passed!"

    lines = []
    lines.append("{} failures:".format(len(failures)))
    lines.append("")

    for r in failures:
        lines.append("ID: {}  Type: {}  Score: {:.2f}".format(
            r.get("id", "?"), r.get("type", "?"),
            r.get("overall_score", 0),
        ))
        lines.append("  Q: {}".format(
            (r.get("query", ""))[:100],
        ))
        scores = "  fact={:.2f}  behavior={:.2f}  citation={:.2f}".format(
            r.get("fact_score", 0),
            r.get("behavior_score", 0),
            r.get("citation_score", 0),
        )
        lines.append(scores)
        if r.get("error"):
            lines.append("  ERROR: {}".format(r["error"]))
        lines.append("")

    return "\n".join(lines)


def apply_theme_recursive(widget, t):
    """Recursively re-theme a widget tree."""
    try:
        wtype = widget.winfo_class()
        if wtype == "Frame" or wtype == "Labelframe":
            widget.configure(bg=t["panel_bg"])
            if wtype == "Labelframe":
                widget.configure(fg=t["accent"])
        elif wtype == "Label":
            widget.configure(bg=t["panel_bg"])
            current_fg = str(widget.cget("fg")).lower()
            if current_fg not in (
                t.get("green", "").lower(),
                t.get("red", "").lower(),
                t.get("orange", "").lower(),
            ):
                widget.configure(fg=t["fg"])
        elif wtype == "Text":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"])
        elif wtype == "Button":
            state = str(widget.cget("state"))
            if state == "disabled":
                widget.configure(
                    bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                )
            else:
                widget.configure(bg=t["accent"], fg=t["accent_fg"])
    except tk.TclError:
        pass

    for child in widget.winfo_children():
        apply_theme_recursive(child, t)


def set_text(widget, text):
    """Set text in a disabled Text widget."""
    widget.config(state=tk.NORMAL)
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)
    widget.config(state=tk.DISABLED)


def _build_eval_widgets(panel, t):
    """Build all widgets for the eval panel. Sets attributes on `panel`."""

    # --- Section 1: Eval Controls ---
    ctrl = tk.LabelFrame(
        panel, text="Eval Controls", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    ctrl.pack(fill=tk.X, padx=16, pady=(8, 4))

    # Row A: Dataset + Limit
    row_a = tk.Frame(ctrl, bg=t["panel_bg"])
    row_a.pack(fill=tk.X, pady=(0, 6))
    tk.Label(row_a, text="Dataset:", bg=t["panel_bg"], fg=t["fg"],
             font=FONT).pack(side=tk.LEFT)
    panel._dataset_var = tk.StringVar(value="Tuning 400")
    panel._dataset_combo = ttk.Combobox(
        row_a, textvariable=panel._dataset_var,
        values=list(EvalTuningPanel.DATASETS.keys()),
        state="readonly", width=20, font=FONT,
    )
    panel._dataset_combo.pack(side=tk.LEFT, padx=(8, 16))
    tk.Label(row_a, text="Limit:", bg=t["panel_bg"], fg=t["fg"],
             font=FONT).pack(side=tk.LEFT)
    panel._limit_var = tk.StringVar(value="0")
    panel._limit_spin = tk.Spinbox(
        row_a, from_=0, to=400, textvariable=panel._limit_var,
        width=5, font=FONT, bg=t["input_bg"], fg=t["input_fg"],
        relief=tk.FLAT, bd=2,
    )
    panel._limit_spin.pack(side=tk.LEFT, padx=(8, 0))
    tk.Label(row_a, text="(0 = all)", bg=t["panel_bg"], fg=t["gray"],
             font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

    # Row B: Buttons
    row_b = tk.Frame(ctrl, bg=t["panel_bg"])
    row_b.pack(fill=tk.X, pady=(0, 6))
    panel.start_btn = tk.Button(
        row_b, text="Run Eval", command=panel._on_start, width=14,
        bg=t["accent"], fg=t["accent_fg"], font=FONT_BOLD,
        relief=tk.FLAT, bd=0, padx=24, pady=8, state=tk.NORMAL,
        activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
    )
    panel.start_btn.pack(side=tk.LEFT)
    panel.stop_btn = tk.Button(
        row_b, text="Stop", command=panel._on_stop, width=8,
        state=tk.DISABLED, bg=t["inactive_btn_bg"],
        fg=t["inactive_btn_fg"], font=FONT, relief=tk.FLAT, bd=0,
        padx=12, pady=8,
    )
    panel.stop_btn.pack(side=tk.LEFT, padx=(8, 0))
    panel._export_btn = tk.Button(
        row_b, text="Export CSV", command=panel._on_export, width=10,
        state=tk.DISABLED, bg=t["inactive_btn_bg"],
        fg=t["inactive_btn_fg"], font=FONT, relief=tk.FLAT, bd=0,
        padx=12, pady=8,
    )
    panel._export_btn.pack(side=tk.RIGHT)
    panel.status_label = tk.Label(
        row_b, text="Ready", anchor=tk.W, bg=t["panel_bg"],
        fg=t["gray"], font=FONT,
    )
    panel.status_label.pack(side=tk.LEFT, padx=(16, 0), fill=tk.X,
                            expand=True)

    # Row C: Progress bar
    row_c = tk.Frame(ctrl, bg=t["panel_bg"])
    row_c.pack(fill=tk.X, pady=(0, 4))
    panel.progress_bar = ttk.Progressbar(row_c, mode="determinate", length=400)
    panel.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    panel.progress_label = tk.Label(
        row_c, text="0 / 0", anchor=tk.W, padx=8, bg=t["panel_bg"],
        fg=t["fg"], font=FONT_MONO,
    )
    panel.progress_label.pack(side=tk.LEFT)
    panel._eta_label = tk.Label(
        row_c, text="", anchor=tk.E, padx=8, bg=t["panel_bg"],
        fg=t["gray"], font=FONT,
    )
    panel._eta_label.pack(side=tk.RIGHT)

    # --- Section 2: Summary big numbers ---
    summary_frame = tk.LabelFrame(
        panel, text="Results Summary", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    summary_frame.pack(fill=tk.X, padx=16, pady=4)
    big_row = tk.Frame(summary_frame, bg=t["panel_bg"])
    big_row.pack(fill=tk.X, pady=(0, 8))
    panel._pass_rate_lbl = _make_big_number(big_row, "Pass Rate", "--", t)
    panel._total_lbl = _make_big_number(big_row, "Questions", "--", t)
    panel._p50_lbl = _make_big_number(big_row, "p50 Latency", "--", t)
    panel._p95_lbl = _make_big_number(big_row, "p95 Latency", "--", t)
    panel._cost_lbl = _make_big_number(big_row, "Total Cost", "--", t)

    # --- Section 3: Type breakdown ---
    type_frame = tk.LabelFrame(
        panel, text="Breakdown by Type", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    type_frame.pack(fill=tk.X, padx=16, pady=4)
    panel._type_text = tk.Text(
        type_frame, height=6, wrap=tk.NONE, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        state=tk.DISABLED,
    )
    panel._type_text.pack(fill=tk.X)

    # --- Section 4: Role breakdown ---
    role_frame = tk.LabelFrame(
        panel, text="Breakdown by Role", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    role_frame.pack(fill=tk.X, padx=16, pady=4)
    panel._role_text = tk.Text(
        role_frame, height=10, wrap=tk.NONE, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        state=tk.DISABLED,
    )
    panel._role_text.pack(fill=tk.X)

    # --- Section 5: Failures ---
    fail_frame = tk.LabelFrame(
        panel, text="Failures (score < 0.85)", padx=16, pady=8,
        bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
    )
    fail_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 8))
    panel._fail_text = tk.Text(
        fail_frame, height=8, wrap=tk.WORD, font=FONT_MONO,
        bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        state=tk.DISABLED,
    )
    scrollbar = tk.Scrollbar(fail_frame, command=panel._fail_text.yview)
    panel._fail_text.configure(yscrollcommand=scrollbar.set)
    panel._fail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)


def _make_big_number(parent, label_text, value_text, t):
    """Create a big-number display (label above, value below)."""
    frame = tk.Frame(parent, bg=t["panel_bg"], padx=16)
    frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(frame, text=label_text, bg=t["panel_bg"], fg=t["gray"],
             font=("Segoe UI", 8)).pack()
    value_lbl = tk.Label(
        frame, text=value_text, bg=t["panel_bg"], fg=t["fg"],
        font=("Segoe UI", 18, "bold"),
    )
    value_lbl.pack()
    return value_lbl


class EvalTuningPanel(tk.Frame):
    """
    Evaluation and tuning panel.

    Runs the 400-question golden eval via subprocess, monitors progress,
    scores results, and displays a summary with role/type breakdowns.

    Heavy formatting and theme logic lives in module-level functions
    to keep this class under 500 lines.
    """

    # Default dataset paths (relative to project root)
    DATASETS = {
        "Tuning 400": "Eval/golden_tuning_400.json",
    }

    def __init__(self, parent, config, app_ref=None):
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref

        # Threading state
        self._stop_flag = threading.Event()
        self._eval_thread: Optional[threading.Thread] = None
        self._eval_process: Optional[subprocess.Popen] = None

        # Results state
        self._summary: Optional[dict] = None
        self._scored_rows: list = []
        self._eval_outdir = ""
        self._scored_outdir = ""

        # Build UI (module-level function populates self.* widget refs)
        _build_eval_widgets(self, t)

    # ==================================================================
    # START / STOP
    # ==================================================================

    def _on_start(self):
        """Launch eval in a background thread."""
        dataset_key = self._dataset_var.get()
        dataset_path = self.DATASETS.get(dataset_key, "")
        if not dataset_path:
            self.status_label.config(
                text="[FAIL] Unknown dataset", fg=current_theme()["red"],
            )
            return

        full_path = os.path.join(PROJECT_ROOT, dataset_path)
        if not os.path.isfile(full_path):
            self.status_label.config(
                text="[FAIL] Dataset not found: {}".format(dataset_path),
                fg=current_theme()["red"],
            )
            return

        # Count total questions
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = len(data)
        except Exception as e:
            self.status_label.config(
                text="[FAIL] Cannot load dataset: {}".format(e),
                fg=current_theme()["red"],
            )
            return

        limit = int(self._limit_var.get() or 0)
        if limit > 0:
            total = min(total, limit)

        # Prepare output directories
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._eval_outdir = os.path.join(PROJECT_ROOT, "eval_out", ts)
        self._scored_outdir = os.path.join(PROJECT_ROOT, "scored_out", ts)
        os.makedirs(self._eval_outdir, exist_ok=True)
        os.makedirs(self._scored_outdir, exist_ok=True)

        # Reset UI
        self._stop_flag.clear()
        self._summary = None
        self._scored_rows = []
        t = current_theme()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"])
        self._export_btn.config(state=tk.DISABLED)
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = 0
        self.progress_label.config(text="0 / {}".format(total))
        self._eta_label.config(text="")
        self.status_label.config(text="Phase 1: Running eval...", fg=t["fg"])
        self._clear_results()

        # Launch background thread
        self._eval_thread = threading.Thread(
            target=self._run_eval_pipeline,
            args=(full_path, dataset_path, total, limit),
            daemon=True,
        )
        self._eval_thread.start()

    def _on_stop(self):
        """Signal eval to stop."""
        self._stop_flag.set()
        # Kill subprocess if running
        proc = self._eval_process
        if proc and proc.poll() is None:
            proc.terminate()
        t = current_theme()
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="[WARN] Stopping...", fg=t["orange"])

    # ==================================================================
    # BACKGROUND EVAL PIPELINE
    # ==================================================================

    def _run_eval_pipeline(self, golden_path, dataset_rel, total, limit):
        """
        Background thread: run eval_runner.py then score_results.py.

        All GUI updates use safe_after() to avoid Tk cross-thread crashes.
        Progress is tracked by polling the output JSONL file size.
        """
        from src.gui.helpers.safe_after import safe_after
        results_jsonl = os.path.join(self._eval_outdir, "results.jsonl")
        t0 = time.monotonic()

        try:
            # --- Phase 1: Run eval_runner.py ---
            cmd = [
                sys.executable, "tools/eval_runner.py",
                "--dataset", golden_path,
                "--outdir", self._eval_outdir,
            ]
            if limit > 0:
                cmd += ["--limit", str(limit)]

            self._eval_process = subprocess.Popen(
                cmd, cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )

            # Poll progress by counting lines in results.jsonl
            self._poll_progress(results_jsonl, total, t0)

            # Wait for process to finish
            returncode = self._eval_process.wait()
            self._eval_process = None

            if self._stop_flag.is_set():
                safe_after(self, 0, self._on_stopped)
                return

            if returncode != 0:
                safe_after(self, 0, self._on_error,
                           "[FAIL] eval_runner exited with code {}".format(returncode))
                return

            # --- Phase 2: Score results ---
            safe_after(self, 0, self._update_status, "Phase 2: Scoring results...")

            score_cmd = [
                sys.executable, "tools/score_results.py",
                "--golden", golden_path,
                "--results", results_jsonl,
                "--outdir", self._scored_outdir,
            ]
            score_proc = subprocess.run(
                score_cmd, cwd=PROJECT_ROOT, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
            if score_proc.returncode != 0:
                safe_after(self, 0, self._on_error,
                           "[FAIL] score_results exited with code {}".format(
                               score_proc.returncode))
                return

            # --- Phase 3: Load and display results ---
            summary_path = os.path.join(self._scored_outdir, "summary.json")
            scored_path = os.path.join(self._scored_outdir,
                                       "scored_results.jsonl")

            summary = {}
            if os.path.isfile(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)

            scored_rows = []
            if os.path.isfile(scored_path):
                with open(scored_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            scored_rows.append(json.loads(line))

            elapsed = time.monotonic() - t0
            self._summary = summary
            self._scored_rows = scored_rows
            safe_after(self, 0, self._on_eval_done, summary, scored_rows, elapsed)

        except Exception as e:
            safe_after(self, 0, self._on_error,
                       "[FAIL] {}: {}".format(type(e).__name__, e))

    def _poll_progress(self, jsonl_path, total, t0):
        """Poll results.jsonl line count for progress updates."""
        from src.gui.helpers.safe_after import safe_after
        last_count = 0
        throttle = 0.5  # seconds between polls

        while True:
            if self._stop_flag.is_set():
                return

            proc = self._eval_process
            if proc and proc.poll() is not None:
                # Process finished
                break

            # Count lines in results file
            count = 0
            if os.path.isfile(jsonl_path):
                try:
                    with open(jsonl_path, "r", encoding="utf-8") as f:
                        count = sum(1 for _ in f)
                except (OSError, IOError):
                    pass

            if count != last_count:
                last_count = count
                elapsed = time.monotonic() - t0
                if count > 0:
                    eta_sec = (elapsed / count) * (total - count)
                    eta_str = format_eta(eta_sec)
                else:
                    eta_str = ""
                safe_after(
                    self, 0, self._update_progress, count, total, eta_str,
                )

            time.sleep(throttle)

        # Final count
        count = 0
        if os.path.isfile(jsonl_path):
            try:
                with open(jsonl_path, "r", encoding="utf-8") as f:
                    count = sum(1 for _ in f)
            except (OSError, IOError):
                pass
        safe_after(self, 0, self._update_progress, count, total, "")

    # ==================================================================
    # MAIN-THREAD CALLBACKS
    # ==================================================================

    def _update_progress(self, current, total, eta_str):
        """Update progress bar and labels (main thread)."""
        self.progress_bar["value"] = current
        self.progress_label.config(text="{} / {}".format(current, total))
        self._eta_label.config(text=eta_str)

    def _update_status(self, text):
        """Update status label (main thread)."""
        t = current_theme()
        self.status_label.config(text=text, fg=t["fg"])

    def _on_eval_done(self, summary, scored_rows, elapsed):
        """Display final results (main thread)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(
            state=tk.DISABLED, bg=t["inactive_btn_bg"],
            fg=t["inactive_btn_fg"],
        )
        self._export_btn.config(
            state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"],
        )

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        self.status_label.config(
            text="[OK] Complete in {}m {}s".format(mins, secs),
            fg=t["green"],
        )

        self._display_summary(summary)
        self._display_type_breakdown(summary)
        self._display_role_breakdown(summary)
        self._display_failures(scored_rows)

    def _on_error(self, msg):
        """Handle eval error (main thread)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(
            state=tk.DISABLED, bg=t["inactive_btn_bg"],
            fg=t["inactive_btn_fg"],
        )
        self.status_label.config(text=msg, fg=t["red"])

    def _on_stopped(self):
        """Handle user-initiated stop (main thread)."""
        t = current_theme()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(
            state=tk.DISABLED, bg=t["inactive_btn_bg"],
            fg=t["inactive_btn_fg"],
        )
        self.status_label.config(text="[WARN] Stopped by user", fg=t["orange"])

    # ==================================================================
    # RESULTS DISPLAY (delegates to module-level formatters)
    # ==================================================================

    def _clear_results(self):
        """Reset all result displays."""
        self._pass_rate_lbl.config(text="--")
        self._total_lbl.config(text="--")
        self._p50_lbl.config(text="--")
        self._p95_lbl.config(text="--")
        self._cost_lbl.config(text="--")
        set_text(self._type_text, "")
        set_text(self._role_text, "")
        set_text(self._fail_text, "")

    def _display_summary(self, summary):
        """Populate big-number displays from summary.json."""
        overall = summary.get("overall", {})
        t = current_theme()
        pass_rate = overall.get("pass_rate", 0)
        pass_pct = "{:.1f}%".format(pass_rate * 100)
        if pass_rate >= 0.95:
            color = t["green"]
        elif pass_rate >= 0.85:
            color = t["orange"]
        else:
            color = t["red"]
        self._pass_rate_lbl.config(text=pass_pct, fg=color)
        self._total_lbl.config(text=str(overall.get("count", 0)))
        self._p50_lbl.config(
            text="{}ms".format(overall.get("p50_latency_ms", 0)),
        )
        self._p95_lbl.config(
            text="{}ms".format(overall.get("p95_latency_ms", 0)),
        )
        total_cost = sum(r.get("cost_usd", 0) for r in self._scored_rows)
        self._cost_lbl.config(text="${:.4f}".format(total_cost))

    def _display_type_breakdown(self, summary):
        set_text(self._type_text, format_type_breakdown(summary))

    def _display_role_breakdown(self, summary):
        set_text(self._role_text, format_role_breakdown(summary))

    def _display_failures(self, scored_rows):
        set_text(self._fail_text, format_failures(scored_rows))

    # ==================================================================
    # EXPORT
    # ==================================================================

    def _on_export(self):
        """Export scored CSV via file dialog."""
        csv_path = os.path.join(self._scored_outdir, "scored_results.csv")
        if not os.path.isfile(csv_path):
            self.status_label.config(
                text="[FAIL] No scored CSV found",
                fg=current_theme()["red"],
            )
            return

        dest = filedialog.asksaveasfilename(
            title="Export Scored Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="scored_results_{}.csv".format(
                time.strftime("%Y%m%d_%H%M%S"),
            ),
        )
        if not dest:
            return

        try:
            import shutil
            shutil.copy2(csv_path, dest)
            self.status_label.config(
                text="[OK] Exported to {}".format(os.path.basename(dest)),
                fg=current_theme()["green"],
            )
        except Exception as e:
            self.status_label.config(
                text="[FAIL] Export error: {}".format(e),
                fg=current_theme()["red"],
            )

    # ==================================================================
    # THEME
    # ==================================================================

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["panel_bg"])
        for widget in self.winfo_children():
            apply_theme_recursive(widget, t)

    # ==================================================================
    # READY STATE
    # ==================================================================

    def set_ready(self, enabled):
        """Enable/disable based on backend readiness."""
        t = current_theme()
        if enabled:
            self.start_btn.config(
                state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"],
            )
        else:
            self.start_btn.config(
                state=tk.DISABLED, bg=t["inactive_btn_bg"],
                fg=t["inactive_btn_fg"],
            )
