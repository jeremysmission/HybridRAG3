#!/usr/bin/env python3
# === NON-PROGRAMMER GUIDE ===
# Purpose: Automates the workflow operational workflow for developers or operators.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
"""
HybridRAG GUI E2E "Human Clicker" — Tkinter edition

Goal:
  Simulate a person touching every GUI control (buttons + menu items),
  end-to-end, and produce a machine-readable report that an AI CLI tool
  (or any LLM) can use to diagnose wiring failures.

Design principles:
  - Redesign-only compatible: this tool lives outside src/ and does not
    patch production GUI logic.
  - Deterministic + safe: blocks modal dialogs, avoids Exit/Quit by default.
  - Portable: pure stdlib; optional Pillow for screenshots.

Usage:
  python tools/gui_e2e/run.py --mode mock --report gui_e2e_report.json
  python tools/gui_e2e/run.py --mode real --show --report gui_e2e_report.json

Notes:
  - "mock" mode injects lightweight stub backends so no DB/API/Ollama required.
  - "real" mode launches with real backends (may be slow, may require config).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tk imports
import tkinter as tk
from tkinter import ttk

# Block modal dialogs (messagebox) to avoid hangs
from tkinter import messagebox


# ---------------------------- Report Model ----------------------------

@dataclass
class Action:
    action_id: str
    kind: str              # "button" | "menu" | "combobox" | "checkbutton" | "radiobutton"
    widget_class: str
    widget_path: str
    label: str = ""
    state: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    action_id: str
    ok: bool
    error: str = ""
    traceback: str = ""
    duration_ms: float = 0.0


@dataclass
class Report:
    tool: str = "tools/gui_e2e"
    driver: str = "tkinter"
    started_utc: str = ""
    finished_utc: str = ""
    mode: str = "mock"
    app_title: str = ""
    actions: List[Action] = field(default_factory=list)
    results: List[ActionResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


# ---------------------------- Utilities ----------------------------

def _utc_now() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _pump_events(root: tk.Tk, ms: int = 50) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            break
        time.sleep(0.005)


def _install_callback_error_trap(app: tk.Tk) -> None:
    """Record Tk callback exceptions so late failures fail the action."""
    errors = []
    prior_handler = getattr(app, "report_callback_exception", None)

    def _capture(exc, val, tb):
        errors.append(
            {
                "error": str(val),
                "traceback": "".join(traceback.format_exception(exc, val, tb)),
            }
        )
        if callable(prior_handler):
            try:
                prior_handler(exc, val, tb)
            except Exception:
                pass

    app._gui_e2e_callback_errors = errors
    app.report_callback_exception = _capture


def _raise_callback_error(app: tk.Tk, baseline_errors: int) -> None:
    errors = getattr(app, "_gui_e2e_callback_errors", [])
    if len(errors) <= baseline_errors:
        return
    first_error = errors[baseline_errors]
    raise RuntimeError(
        "Tk callback exception after action: {}".format(
            first_error.get("error", "unknown"),
        )
    )


def _safe_label_for_widget(w: tk.Widget) -> str:
    for key in ("text", "label"):
        try:
            v = w.cget(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        except Exception:
            pass
    return ""


def _widget_path(w: tk.Widget) -> str:
    # Tk's internal path is stable and unique within a process
    try:
        return str(w)
    except Exception:
        return f"<{w.__class__.__name__}>"


def _is_disabled(w: tk.Widget) -> bool:
    try:
        s = str(w.cget("state"))
        return s.lower() in ("disabled",)
    except Exception:
        return False


def _matches_any(text: str, patterns: List[str]) -> bool:
    for p in patterns:
        try:
            if re.search(p, text, flags=re.IGNORECASE):
                return True
        except re.error:
            # Treat invalid regex as literal substring
            if p.lower() in text.lower():
                return True
    return False


# ----------------------- Messagebox Non-Blocking -----------------------

def _install_messagebox_shims() -> None:
    """
    Replace messagebox calls with non-blocking defaults.
    This prevents GUI E2E from hanging on About/confirm dialogs.

    You can override by setting GUI_E2E_ALLOW_DIALOGS=1.
    """
    if os.getenv("GUI_E2E_ALLOW_DIALOGS") == "1":
        return

    def _ok(*args, **kwargs):
        return "ok"

    def _yes(*args, **kwargs):
        return True

    def _no(*args, **kwargs):
        return False

    # Common functions
    messagebox.showinfo = _ok
    messagebox.showwarning = _ok
    messagebox.showerror = _ok
    messagebox.askokcancel = _yes
    messagebox.askyesno = _yes
    messagebox.askretrycancel = _yes
    messagebox.askquestion = lambda *a, **k: "yes"


# ----------------------------- App Bootstrap -----------------------------

def _build_mock_backends():
    """
    Create lightweight stub backends for GUI wiring tests.
    No network, no DB, no Ollama.
    """
    from unittest.mock import MagicMock

    # Query result object: match attributes used by GUI
    class _Result:
        def __init__(self):
            self.answer = "GUI_E2E: stubbed answer (mock mode)."
            self.sources = []
            self.chunks_used = 0
            self.tokens_in = 0
            self.tokens_out = 0
            self.cost_usd = 0.0
            self.latency_ms = 10.0
            self.mode = "offline"
            self.error = ""

    query_engine = MagicMock(name="QueryEngineMock")
    query_engine.query = MagicMock(return_value=_Result())
    query_engine.query_stream = MagicMock(return_value=iter(["GUI_E2E ", "stream ", "ok."]))
    query_engine.health = MagicMock(return_value={"ok": True})

    indexer = MagicMock(name="IndexerMock")
    indexer.index = MagicMock(return_value=True)
    indexer.status = MagicMock(return_value={"rows": 0, "ok": True})

    router = MagicMock(name="RouterMock")
    router.is_online_available = MagicMock(return_value=False)
    router.is_offline_available = MagicMock(return_value=True)

    # BootResult stub
    @dataclass
    class _Boot:
        boot_timestamp: str = "GUI_E2E"
        success: bool = True
        online_available: bool = False
        offline_available: bool = True
        api_client: object = None
        config: dict = field(default_factory=dict)
        credentials: object = None
        warnings: list = field(default_factory=list)
        errors: list = field(default_factory=list)

        def summary(self):
            return "BOOT: GUI_E2E MOCK OK"

    return _Boot(), query_engine, indexer, router


def _load_config(project_root: Path):
    """
    Load real config if available, otherwise fall back to a minimal stub.
    """
    try:
        from src.core.config import load_config
        return load_config(str(project_root))
    except Exception:
        # Minimal stub with required attrs
        @dataclass
        class _StubCfg:
            mode: str = "offline"
        return _StubCfg()


def _create_app(mode: str, show_window: bool) -> tk.Tk:
    """
    Create the HybridRAG Tk app with either real or mock backends.
    """
    from src.gui.app import HybridRAGApp

    cfg = _load_config(PROJECT_ROOT)

    if mode == "mock":
        boot, qe, idx, rtr = _build_mock_backends()
        app = HybridRAGApp(boot_result=boot, config=cfg, query_engine=qe, indexer=idx, router=rtr)
        # Mark panels ready so buttons are enabled
        try:
            app.set_ready(True)
        except Exception:
            pass
    else:
        # "real" mode: create app with whatever launch provides at startup.
        # This keeps the window responsive; backends can be loaded later.
        app = HybridRAGApp(boot_result=None, config=cfg, query_engine=None, indexer=None, router=None)

    if not show_window:
        app.withdraw()
    return app


# ----------------------------- Discovery -----------------------------

def _discover_menu_actions(app: tk.Tk) -> List[Action]:
    actions: List[Action] = []
    try:
        menubar = app.cget("menu")
        if not menubar:
            return actions
        menu = app.nametowidget(menubar)
        if not isinstance(menu, tk.Menu):
            return actions
    except Exception:
        return actions

    def walk_menu(m: tk.Menu, prefix: str):
        try:
            end = m.index("end")
        except Exception:
            end = None
        if end is None:
            return
        for i in range(end + 1):
            try:
                typ = m.type(i)
            except Exception:
                continue
            if typ == "separator":
                continue
            try:
                label = m.entrycget(i, "label") or ""
            except Exception:
                label = ""
            action_id = f"menu:{prefix}{label}:{i}"
            actions.append(Action(
                action_id=action_id,
                kind="menu",
                widget_class="tk.Menu",
                widget_path=str(m),
                label=f"{prefix}{label}",
                state="normal",
                details={"index": i},
            ))
            if typ == "cascade":
                try:
                    subname = m.entrycget(i, "menu")
                    sub = app.nametowidget(subname)
                    walk_menu(sub, prefix=f"{prefix}{label}/")
                except Exception:
                    pass

    walk_menu(menu, prefix="")
    return actions


def _discover_widget_actions(root: tk.Widget) -> List[Action]:
    actions: List[Action] = []

    def walk(w: tk.Widget):
        # Buttons
        if isinstance(w, (tk.Button, ttk.Button)):
            actions.append(Action(
                action_id=f"btn:{_widget_path(w)}",
                kind="button",
                widget_class=w.__class__.__name__,
                widget_path=_widget_path(w),
                label=_safe_label_for_widget(w),
                state=str(getattr(w, "cget")("state")) if hasattr(w, "cget") else "",
            ))
        # Combobox
        if isinstance(w, ttk.Combobox):
            actions.append(Action(
                action_id=f"combo:{_widget_path(w)}",
                kind="combobox",
                widget_class=w.__class__.__name__,
                widget_path=_widget_path(w),
                label=_safe_label_for_widget(w),
                state=str(w.cget("state")),
                details={"values": list(w.cget("values") or [])},
            ))
        # Checkbutton / Radiobutton
        if isinstance(w, (tk.Checkbutton, ttk.Checkbutton)):
            actions.append(Action(
                action_id=f"check:{_widget_path(w)}",
                kind="checkbutton",
                widget_class=w.__class__.__name__,
                widget_path=_widget_path(w),
                label=_safe_label_for_widget(w),
                state=str(w.cget("state")),
            ))
        if isinstance(w, (tk.Radiobutton, ttk.Radiobutton)):
            actions.append(Action(
                action_id=f"radio:{_widget_path(w)}",
                kind="radiobutton",
                widget_class=w.__class__.__name__,
                widget_path=_widget_path(w),
                label=_safe_label_for_widget(w),
                state=str(w.cget("state")),
            ))

        for c in w.winfo_children():
            walk(c)

    walk(root)
    return actions


# ----------------------------- Execution -----------------------------

def _invoke_action(app: tk.Tk, a: Action, pump_ms: int) -> None:
    """
    Execute one action.
    """
    baseline_errors = len(getattr(app, "_gui_e2e_callback_errors", []))

    if a.kind == "menu":
        m = app.nametowidget(a.widget_path)
        idx = int(a.details.get("index", 0))
        m.invoke(idx)
        _pump_events(app, pump_ms)
        _raise_callback_error(app, baseline_errors)
        return

    w = app.nametowidget(a.widget_path)

    if a.kind == "button":
        # Prefer .invoke() if available
        if hasattr(w, "invoke"):
            w.invoke()
        else:
            w.event_generate("<Button-1>")
            w.event_generate("<ButtonRelease-1>")
        _pump_events(app, pump_ms)
        _raise_callback_error(app, baseline_errors)
        return

    if a.kind == "combobox":
        # Cycle through up to N values (default 3) and fire selection event.
        values = a.details.get("values", []) or []
        max_vals = int(os.getenv("GUI_E2E_COMBO_MAX", "3"))
        for i, v in enumerate(values[:max_vals]):
            try:
                w.set(v)
                w.event_generate("<<ComboboxSelected>>")
            except Exception:
                pass
                continue
            _pump_events(app, pump_ms)
            _raise_callback_error(app, baseline_errors)
        return

    if a.kind == "checkbutton":
        if hasattr(w, "invoke"):
            w.invoke()
            _pump_events(app, pump_ms)
            _raise_callback_error(app, baseline_errors)
            w.invoke()
            _pump_events(app, pump_ms)
            _raise_callback_error(app, baseline_errors)
        return

    if a.kind == "radiobutton":
        if hasattr(w, "invoke"):
            w.invoke()
            _pump_events(app, pump_ms)
            _raise_callback_error(app, baseline_errors)
        return


def run_e2e(mode: str, show: bool, pump_ms: int, exclude: List[str]) -> Report:
    _install_messagebox_shims()

    r = Report()
    r.started_utc = _utc_now()
    r.mode = mode

    app = _create_app(mode=mode, show_window=show)
    _install_callback_error_trap(app)
    r.app_title = app.title()

    # Let initial after() handlers run
    _pump_events(app, 250)

    # Discover actions
    actions = []
    actions.extend(_discover_menu_actions(app))
    actions.extend(_discover_widget_actions(app))

    # De-dup actions by id, preserve order
    seen = set()
    deduped = []
    for a in actions:
        if a.action_id in seen:
            continue
        seen.add(a.action_id)
        deduped.append(a)

    # Filter excludes + skip disabled
    filtered = []
    default_exclude = [
        r"^File/Exit$",
        r"\bexit\b",
        r"\bquit\b",
        r"\bclose\b",
    ]
    for a in deduped:
        label = (a.label or "").strip()
        if _matches_any(label, default_exclude):
            continue
        if _matches_any(label, exclude):
            continue
        # Skip disabled widgets (menus are always "normal" here)
        if a.kind != "menu":
            try:
                w = app.nametowidget(a.widget_path)
                if _is_disabled(w):
                    continue
            except Exception:
                pass
        filtered.append(a)

    r.actions = filtered

    # Execute
    ok = 0
    fail = 0
    for a in r.actions:
        t0 = time.time()
        try:
            _invoke_action(app, a, pump_ms=pump_ms)
            r.results.append(ActionResult(
                action_id=a.action_id,
                ok=True,
                duration_ms=(time.time() - t0) * 1000.0,
            ))
            ok += 1
        except Exception as exc:
            r.results.append(ActionResult(
                action_id=a.action_id,
                ok=False,
                error=str(exc),
                traceback=traceback.format_exc(),
                duration_ms=(time.time() - t0) * 1000.0,
            ))
            fail += 1

    # Clean shutdown (avoid thread noise)
    try:
        if hasattr(app, "status_bar") and hasattr(app.status_bar, "stop"):
            app.status_bar.stop()
    except Exception:
        pass
    try:
        app.destroy()
    except Exception:
        pass

    r.finished_utc = _utc_now()
    r.summary = {
        "actions_total": len(r.actions),
        "passed": ok,
        "failed": fail,
    }
    return r


# ----------------------------- CLI -----------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="HybridRAG GUI E2E click-all runner (Tkinter)")
    p.add_argument("--mode", choices=["mock", "real"], default="mock", help="mock = safe stub backends; real = live backends")
    p.add_argument("--show", action="store_true", help="Show the GUI window while testing")
    p.add_argument("--pump-ms", type=int, default=80, help="Event loop pump duration after each action")
    p.add_argument("--exclude", action="append", default=[], help="Regex (or substring) to exclude actions by label")
    p.add_argument("--report", default="gui_e2e_report.json", help="Output JSON report path")
    args = p.parse_args(argv)

    rep = run_e2e(mode=args.mode, show=args.show, pump_ms=args.pump_ms, exclude=args.exclude)
    out_path = Path(args.report)
    out_path.write_text(json.dumps(asdict(rep), indent=2), encoding="utf-8")

    # Print a compact summary for CI
    s = rep.summary or {}
    print(f"GUI_E2E: actions={s.get('actions_total')} passed={s.get('passed')} failed={s.get('failed')} report={out_path}")
    return 0 if s.get("failed", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
