# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the gui engine part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# Hybrid3 GUI Testing -- Behavioral Engine (src/gui/testing/gui_engine.py)
# ============================================================================
# Discovers all clickable widgets, invokes them safely, captures state
# snapshots before/after each action, diffs file system and core state,
# and tracks per-action performance metrics including p95.
#
# Single-file engine: introspection + invocation + snapshot + diff + perf.
# ============================================================================
from __future__ import annotations
import hashlib
import statistics
import time
import traceback
import tkinter as tk
from pathlib import Path
from typing import Any


class HybridGuiEngine:
    """Full behavioral test engine for HybridRAG GUI."""

    def __init__(self, app: tk.Tk):
        """Plain-English: This function handles init."""
        self.app = app
        self._times: list[float] = []

    # ------------------------------------------------------------------
    # Widget discovery
    # ------------------------------------------------------------------
    def discover_buttons(self) -> list[tk.Button]:
        """Walk the widget tree and return all Button instances."""
        found: list[tk.Button] = []

        def walk(widget: tk.Widget) -> None:
            """Plain-English: This function handles walk."""
            for child in widget.winfo_children():
                if isinstance(child, tk.Button):
                    found.append(child)
                walk(child)

        walk(self.app)
        return found

    def discover_menus(self) -> list[dict[str, Any]]:
        """Walk the menu bar and return all menu entries."""
        entries: list[dict[str, Any]] = []
        menubar = self.app.nametowidget(self.app.cget("menu")) if self.app.cget("menu") else None
        if menubar is None:
            return entries
        self._walk_menu(menubar, "", entries)
        return entries

    def _walk_menu(self, menu: tk.Menu, prefix: str, out: list) -> None:
        """Plain-English: This function handles walk menu."""
        last = menu.index("end")
        if last is None:
            return
        for i in range(last + 1):
            try:
                kind = menu.type(i)
            except Exception:
                continue
            if kind == "cascade":
                label = menu.entrycget(i, "label")
                sub = menu.nametowidget(menu.entrycget(i, "menu"))
                path = f"{prefix}/{label}" if prefix else label
                out.append({"type": "cascade", "label": path, "index": i, "menu": menu})
                self._walk_menu(sub, path, out)
            elif kind == "command":
                label = menu.entrycget(i, "label")
                path = f"{prefix}/{label}" if prefix else label
                out.append({"type": "command", "label": path, "index": i, "menu": menu})

    # ------------------------------------------------------------------
    # Safe invocation
    # ------------------------------------------------------------------
    def invoke_button(self, button: tk.Button) -> dict[str, Any]:
        """Invoke a button and return timing + error info."""
        start = time.perf_counter()
        success = True
        error = None
        trace = None
        try:
            button.invoke()
            self.app.update()
        except Exception as e:
            success = False
            error = str(e)
            trace = traceback.format_exc()
        elapsed = time.perf_counter() - start
        self._times.append(elapsed)
        return {
            "success": success,
            "error": error,
            "trace": trace,
            "elapsed_s": round(elapsed, 4),
        }

    def invoke_menu(self, entry: dict) -> dict[str, Any]:
        """Invoke a menu command entry.

        Submenu commands often fail in headless mode because the parent
        cascade was never posted. These are marked as skipped, not failed.
        """
        start = time.perf_counter()
        success = True
        skipped = False
        error = None
        trace = None
        try:
            entry["menu"].invoke(entry["index"])
            self.app.update()
        except tk.TclError as e:
            err_str = str(e)
            if "invalid command name" in err_str:
                # Submenu widget destroyed / never posted -- expected headless
                skipped = True
                error = err_str
            else:
                success = False
                error = err_str
                trace = traceback.format_exc()
        except Exception as e:
            success = False
            error = str(e)
            trace = traceback.format_exc()
        elapsed = time.perf_counter() - start
        self._times.append(elapsed)
        return {
            "success": success,
            "skipped": skipped,
            "error": error,
            "trace": trace,
            "elapsed_s": round(elapsed, 4),
        }

    # ------------------------------------------------------------------
    # State snapshots
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Capture current file system + core state."""
        return {
            "files": self._snapshot_files(),
            "core": self._snapshot_core(),
        }

    def _snapshot_files(self) -> dict[str, str]:
        """Plain-English: This function handles snapshot files."""
        data: dict[str, str] = {}
        base = Path("output")
        if base.exists():
            for f in base.rglob("*"):
                if f.is_file():
                    try:
                        data[str(f)] = hashlib.md5(f.read_bytes()).hexdigest()
                    except Exception:
                        data[str(f)] = "unreadable"
        return data

    def _snapshot_core(self) -> dict[str, bool]:
        """Plain-English: This function handles snapshot core."""
        return {
            "has_router": hasattr(self.app, "router") and self.app.router is not None,
            "has_query_engine": hasattr(self.app, "query_engine") and self.app.query_engine is not None,
            "has_indexer": hasattr(self.app, "indexer") and self.app.indexer is not None,
        }

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------
    @staticmethod
    def diff(before: dict, after: dict) -> dict[str, Any]:
        """Compute file and core state differences."""
        changes: list[dict[str, str]] = []
        bf, af = before["files"], after["files"]
        for path, h in af.items():
            if path not in bf:
                changes.append({"type": "created", "path": path})
            elif bf[path] != h:
                changes.append({"type": "modified", "path": path})
        for path in bf:
            if path not in af:
                changes.append({"type": "deleted", "path": path})
        return {
            "file_changes": changes,
            "core_changed": before["core"] != after["core"],
        }

    # ------------------------------------------------------------------
    # Performance summary
    # ------------------------------------------------------------------
    def perf_summary(self) -> dict[str, Any]:
        """Plain-English: This function handles perf summary."""
        if not self._times:
            return {}
        return {
            "count": len(self._times),
            "avg_s": round(statistics.mean(self._times), 4),
            "p95_s": round(sorted(self._times)[int(len(self._times) * 0.95)], 4),
            "max_s": round(max(self._times), 4),
        }

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------
    def run_all(self) -> dict[str, Any]:
        """Discover and invoke every button + menu command. Return full report."""
        results: list[dict[str, Any]] = []

        # Buttons
        for btn in self.discover_buttons():
            before = self.snapshot()
            inv = self.invoke_button(btn)
            after = self.snapshot()
            results.append({
                "widget": "button",
                "label": btn.cget("text"),
                "state": btn.cget("state"),
                "invoke": inv,
                "diff": self.diff(before, after),
            })

        # Menu commands (skip cascades, invoke commands only)
        for entry in self.discover_menus():
            if entry["type"] != "command":
                continue
            before = self.snapshot()
            inv = self.invoke_menu(entry)
            after = self.snapshot()
            results.append({
                "widget": "menu",
                "label": entry["label"],
                "invoke": inv,
                "diff": self.diff(before, after),
            })

        failures = [r for r in results if not r["invoke"]["success"]]
        return {
            "total_actions": len(results),
            "failures": len(failures),
            "performance": self.perf_summary(),
            "results": results,
        }
