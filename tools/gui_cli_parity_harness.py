#!/usr/bin/env python3
"""
GUI QA harness for tracking parity between CLI capabilities and a future GUI.
"""
from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from tools.gui_cli_parity_model import (
    DEFAULT_REPORT_PATH,
    CapabilityRecord,
    VALID_STATUSES,
    build_default_catalog,
    load_saved_state,
    merge_saved_state,
    records_to_report,
    run_smoke_command,
    save_report,
    summarize_records,
)


class GuiCliParityHarness(tk.Tk):
    def __init__(self, report_path: Path) -> None:
        super().__init__()
        self.title("HybridRAG GUI/CLI Parity Harness")
        self.geometry("1420x840")
        self.minsize(1180, 680)

        self.report_path = Path(report_path)
        self.filter_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.report_var = tk.StringVar(value=str(self.report_path))
        self.current_id: str | None = None

        saved = load_saved_state(self.report_path)
        self.records = merge_saved_state(build_default_catalog(), saved)
        self.filtered_ids = [record.capability_id for record in self.records]

        self._build_shell()
        self._refresh_tree()
        self._refresh_summary()

    def _build_shell(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, columnspan=2, sticky="nsew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Filter").grid(row=0, column=0, sticky="w")
        filter_entry = ttk.Entry(top, textvariable=self.filter_var)
        filter_entry.grid(row=0, column=1, sticky="ew", padx=(8, 10))
        filter_entry.bind("<KeyRelease>", lambda _event: self._refresh_tree())
        ttk.Button(top, text="Save Report", command=self._save_report).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Smoke Selected", command=self._run_selected_smoke).grid(row=0, column=3, padx=4)
        ttk.Button(top, text="Smoke All", command=self._run_all_smoke).grid(row=0, column=4, padx=4)

        ttk.Label(top, textvariable=self.summary_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(top, textvariable=self.report_var).grid(row=1, column=3, columnspan=2, sticky="e", pady=(8, 0))

        left = ttk.Frame(self, padding=(12, 0, 6, 12))
        left.grid(row=1, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        columns = ("category", "display_name", "gui_target", "status", "last_smoke")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for column, heading, width in (
            ("category", "Category", 120),
            ("display_name", "Capability", 260),
            ("gui_target", "GUI Target", 280),
            ("status", "Status", 110),
            ("last_smoke", "Last Smoke", 220),
        ):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._on_select())

        y_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=y_scroll.set)

        right = ttk.Frame(self, padding=(6, 0, 12, 12))
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(7, weight=1)

        self.capability_var = tk.StringVar(value="Select a capability")
        self.cli_var = tk.StringVar(value="")
        self.gui_var = tk.StringVar(value="")
        self.priority_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="missing")
        self.smoke_var = tk.StringVar(value="")

        ttk.Label(right, textvariable=self.capability_var, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        ttk.Label(right, text="CLI Command").grid(row=1, column=0, sticky="w")
        ttk.Label(right, textvariable=self.cli_var, wraplength=480).grid(row=2, column=0, sticky="w", pady=(0, 10))
        ttk.Label(right, text="GUI Target").grid(row=3, column=0, sticky="w")
        ttk.Label(right, textvariable=self.gui_var, wraplength=480).grid(row=4, column=0, sticky="w", pady=(0, 10))
        ttk.Label(right, text="Priority / Status").grid(row=5, column=0, sticky="w")

        status_row = ttk.Frame(right)
        status_row.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(status_row, textvariable=self.priority_var).pack(side="left")
        self.status_combo = ttk.Combobox(
            status_row,
            state="readonly",
            values=list(VALID_STATUSES),
            textvariable=self.status_var,
            width=14,
        )
        self.status_combo.pack(side="right")
        self.status_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_status())

        ttk.Label(right, text="Notes").grid(row=7, column=0, sticky="nw")
        self.notes_text = tk.Text(right, wrap="word", height=12)
        self.notes_text.grid(row=8, column=0, sticky="nsew", pady=(4, 10))

        ttk.Label(right, text="Last Smoke").grid(row=9, column=0, sticky="w")
        ttk.Label(right, textvariable=self.smoke_var, wraplength=480).grid(row=10, column=0, sticky="w", pady=(0, 10))

        button_row = ttk.Frame(right)
        button_row.grid(row=11, column=0, sticky="ew")
        ttk.Button(button_row, text="Save Notes", command=self._save_current_notes).pack(side="left", padx=(0, 6))
        ttk.Button(button_row, text="Mark Verified", command=lambda: self._set_status("verified")).pack(side="left", padx=6)
        ttk.Button(button_row, text="Mark Missing", command=lambda: self._set_status("missing")).pack(side="left", padx=6)
        ttk.Button(button_row, text="Close", command=self.destroy).pack(side="right")

    def _matching_records(self) -> list[CapabilityRecord]:
        needle = self.filter_var.get().strip().lower()
        if not needle:
            return list(self.records)
        matches: list[CapabilityRecord] = []
        for record in self.records:
            haystack = " ".join(
                (
                    record.category,
                    record.display_name,
                    record.gui_target,
                    record.cli_command,
                    record.status,
                    record.notes,
                )
            ).lower()
            if needle in haystack:
                matches.append(record)
        return matches

    def _refresh_tree(self) -> None:
        selected = self.current_id
        self.tree.delete(*self.tree.get_children())
        matching = self._matching_records()
        self.filtered_ids = [record.capability_id for record in matching]
        for record in matching:
            last_smoke = record.last_smoke_summary or ""
            self.tree.insert(
                "",
                "end",
                iid=record.capability_id,
                values=(
                    record.category,
                    record.display_name,
                    record.gui_target,
                    record.status,
                    last_smoke[:96],
                ),
            )
        if selected and selected in self.filtered_ids:
            self.tree.selection_set(selected)
            self.tree.focus(selected)
        elif self.filtered_ids:
            first = self.filtered_ids[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._load_record(first)
        else:
            self.current_id = None
            self._clear_details()

    def _refresh_summary(self) -> None:
        summary = summarize_records(self.records)
        self.summary_var.set(
            "Total {total} | Missing {missing} | Planned {planned} | Partial {partial} | "
            "Implemented {implemented} | Verified {verified}".format(**summary)
        )

    def _on_select(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self._load_record(selection[0])

    def _load_record(self, capability_id: str) -> None:
        self.current_id = capability_id
        record = self._find_record(capability_id)
        if record is None:
            self._clear_details()
            return
        self.capability_var.set(f"{record.display_name} ({record.capability_id})")
        self.cli_var.set(record.cli_command)
        self.gui_var.set(record.gui_target)
        self.priority_var.set(f"Priority: {record.priority}")
        self.status_var.set(record.status)
        self.smoke_var.set(record.last_smoke_summary or "No smoke run yet.")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", record.notes)

    def _clear_details(self) -> None:
        self.capability_var.set("Select a capability")
        self.cli_var.set("")
        self.gui_var.set("")
        self.priority_var.set("")
        self.status_var.set("missing")
        self.smoke_var.set("")
        self.notes_text.delete("1.0", "end")

    def _find_record(self, capability_id: str | None) -> CapabilityRecord | None:
        for record in self.records:
            if record.capability_id == capability_id:
                return record
        return None

    def _save_current_notes(self) -> None:
        record = self._find_record(self.current_id)
        if record is None:
            return
        record.notes = self.notes_text.get("1.0", "end").strip()
        self._save_report(show_message=False)
        self._refresh_tree()

    def _apply_status(self) -> None:
        self._set_status(self.status_var.get())

    def _set_status(self, status: str) -> None:
        record = self._find_record(self.current_id)
        if record is None:
            return
        record.status = status
        record.notes = self.notes_text.get("1.0", "end").strip()
        self._refresh_tree()
        self._refresh_summary()

    def _run_selected_smoke(self) -> None:
        record = self._find_record(self.current_id)
        if record is None:
            return
        self._run_smoke_for_record(record)

    def _run_all_smoke(self) -> None:
        failures = 0
        for record in self.records:
            updated = self._run_smoke_for_record(record, show_message=False)
            if updated and updated.last_smoke_ok is False:
                failures += 1
        self._save_report(show_message=False)
        self._refresh_tree()
        self._refresh_summary()
        messagebox.showinfo(
            "Smoke All Complete",
            f"Completed smoke commands for {len(self.records)} capabilities.\nFailures: {failures}",
        )

    def _run_smoke_for_record(
        self,
        record: CapabilityRecord,
        *,
        show_message: bool = True,
    ) -> CapabilityRecord | None:
        self._save_current_notes()
        updated = run_smoke_command(record)
        record.last_smoke_ok = updated.last_smoke_ok
        record.last_smoke_exit_code = updated.last_smoke_exit_code
        record.last_smoke_summary = updated.last_smoke_summary
        record.last_smoke_at = updated.last_smoke_at
        if updated.last_smoke_ok:
            if record.status in {"missing", "planned"}:
                record.status = "partial"
        self._save_report(show_message=False)
        self._load_record(record.capability_id)
        self._refresh_tree()
        self._refresh_summary()
        if show_message:
            headline = "Smoke Passed" if updated.last_smoke_ok else "Smoke Failed"
            messagebox.showinfo(
                headline,
                f"{record.display_name}\nExit code: {updated.last_smoke_exit_code}\n\n{updated.last_smoke_summary}",
            )
        return record

    def _save_report(self, *, show_message: bool = True) -> None:
        if self.current_id:
            record = self._find_record(self.current_id)
            if record is not None:
                record.notes = self.notes_text.get("1.0", "end").strip()
        target = save_report(self.report_path, self.records)
        self.report_var.set(str(target))
        if show_message:
            messagebox.showinfo("Report Saved", f"Saved parity report to:\n{target}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HybridRAG GUI/CLI parity QA harness.")
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to the saved parity report JSON.",
    )
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="Print the merged catalog/report JSON and exit without opening Tk.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report_path = Path(args.report)
    if args.dump_json:
        saved = load_saved_state(report_path)
        records = merge_saved_state(build_default_catalog(), saved)
        print(json.dumps(records_to_report(records), indent=2))
        return 0

    app = GuiCliParityHarness(report_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
