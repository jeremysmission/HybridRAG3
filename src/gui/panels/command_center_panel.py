# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the command-center panel that brings CLI parity into the GUI.
# What to read first: Start at the top-level class and follow event handlers downward.
# Inputs: User selections, command form values, and app/config references.
# Outputs: View navigation, subprocess launches, credential updates, and streamed output.
# Safety notes: Long-running commands execute off the UI thread and can be cancelled.
# ============================

from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from src.core.config import load_config
from src.gui.command_center_registry import CommandSpec, get_command_specs
from src.gui.command_center_runtime import (
    build_credential_report,
    build_paths_report,
    build_shared_launch_report,
    build_status_report,
    build_subprocess_env,
    clear_credentials_from_gui,
    prepare_command,
    resolve_project_root,
    store_api_key_from_gui,
    store_endpoint_bundle_from_gui,
    store_shared_token_from_gui,
)
from src.gui.helpers.safe_after import safe_after
from src.gui.panels.command_center_panel_build import bind_command_center_build_methods
from src.gui.theme import FONT, FONT_BOLD, FONT_MONO, FONT_SMALL, bind_hover, current_theme


def _theme_widget(widget, t):
    """Recursively apply panel theme colors to basic tkinter widgets."""

    try:
        wclass = widget.winfo_class()
        if wclass in {"Frame", "LabelFrame"}:
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Entry":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
        elif wclass == "Checkbutton":
            widget.configure(
                bg=t["panel_bg"],
                fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"],
            )
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


class CommandCenterPanel(tk.Frame):
    """GUI home for CLI-equivalent commands and native parity workflows."""

    def __init__(self, parent, config=None, app_ref=None):
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref
        self._project_root = resolve_project_root()
        self._all_specs = get_command_specs()
        self._visible_specs = list(self._all_specs)
        self._selected_spec: CommandSpec | None = None
        self._field_vars: dict[str, object] = {}
        self._field_widgets: dict[str, tk.Widget] = {}
        self._active_process: subprocess.Popen[str] | None = None
        self._active_thread: threading.Thread | None = None
        self._build(t)
        self._refresh_command_list()
        if self._visible_specs:
            self._select_spec(0)

    # _build and _render_selected_spec are bound from
    # command_center_panel_build.py (keeps class under 500 lines).

    def _refresh_command_list(self):
        query = self._filter_var.get().strip().lower()
        self._visible_specs = []
        for spec in self._all_specs:
            haystack = " ".join((spec.alias, spec.title, spec.category, spec.summary)).lower()
            if query and query not in haystack:
                continue
            self._visible_specs.append(spec)

        self._command_list.delete(0, tk.END)
        for spec in self._visible_specs:
            self._command_list.insert(tk.END, "[{}] {}".format(spec.category, spec.alias))

    def _on_list_select(self, _event=None):
        selection = self._command_list.curselection()
        if selection:
            self._select_spec(selection[0])

    def _select_spec(self, index: int):
        if index < 0 or index >= len(self._visible_specs):
            return
        self._command_list.selection_clear(0, tk.END)
        self._command_list.selection_set(index)
        self._command_list.activate(index)
        self._selected_spec = self._visible_specs[index]
        self._render_selected_spec()

    def _collect_values(self, spec: CommandSpec) -> dict[str, object]:
        values: dict[str, object] = {}
        for field in spec.fields:
            widget = self._field_widgets[field.key]
            if field.kind == "multiline":
                raw_value = widget.get("1.0", tk.END).strip()
            elif field.kind == "bool":
                raw_value = bool(self._field_vars[field.key].get())
            elif field.kind == "choice":
                display = str(self._field_vars[field.key].get())
                raw_value = display
                for value, label in field.choices:
                    if label == display:
                        raw_value = value
                        break
            elif field.kind == "int":
                text = str(self._field_vars[field.key].get()).strip()
                raw_value = int(text or field.default or 0)
            else:
                raw_value = str(self._field_vars[field.key].get()).strip()

            if field.required and not raw_value:
                raise ValueError("{} is required.".format(field.label))
            values[field.key] = raw_value
        return values

    def _execute_selected(self):
        spec = self._selected_spec
        if spec is None:
            return
        if self._active_process is not None:
            self._set_status("A command is already running. Stop it before launching another.", "orange")
            return
        try:
            values = self._collect_values(spec)
            self._dispatch(spec, values)
        except Exception as exc:
            self._set_status(str(exc), "red")

    def _dispatch(self, spec: CommandSpec, values: dict[str, object]):
        if spec.action_kind == "native":
            getattr(self, "_handle_" + spec.handler)(values)
            return

        prepared = prepare_command(spec.alias, values, self._project_root)
        if prepared.launch_detached:
            env = build_subprocess_env(self._project_root)
            subprocess.Popen(prepared.argv, cwd=self._project_root, env=env)
            self._append_output("$ {}\nDetached GUI launch requested.\n".format(prepared.display))
            self._set_status("Detached GUI process launched.", "green")
            return

        self._append_output("$ {}\n".format(prepared.display))
        self._run_process(prepared)

    def _run_process(self, prepared):
        env = build_subprocess_env(self._project_root)

        def _worker():
            try:
                proc = subprocess.Popen(
                    prepared.argv,
                    cwd=self._project_root,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:
                safe_after(self, 0, self._finish_process, None, exc, False)
                return

            self._active_process = proc
            safe_after(self, 0, self._set_busy, True)
            assert proc.stdout is not None
            for line in proc.stdout:
                safe_after(self, 0, self._append_output, line)
            code = proc.wait()
            safe_after(
                self,
                0,
                self._finish_process,
                code,
                None,
                prepared.reload_config_after and code == 0,
            )

        self._active_thread = threading.Thread(target=_worker, daemon=True)
        self._active_thread.start()

    def _finish_process(self, code, error, reload_config_after):
        self._set_busy(False)
        self._active_process = None
        self._active_thread = None
        if reload_config_after:
            self._reload_live_config()
        if error is not None:
            self._append_output("[FAIL] {}\n".format(error))
            self._set_status(str(error), "red")
            return
        if code == 0:
            self._set_status("Command completed successfully.", "green")
        else:
            self._set_status("Command exited with code {}.".format(code), "orange")
            self._append_output("[WARN] Exit code: {}\n".format(code))

    def _set_busy(self, busy: bool):
        t = current_theme()
        if busy:
            self._run_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])
            self._cancel_btn.config(state=tk.NORMAL, bg=t["red"], fg=t["accent_fg"])
        else:
            self._run_btn.config(state=tk.NORMAL, bg=t["accent"], fg=t["accent_fg"])
            self._cancel_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"])

    def _cancel_active_process(self):
        if self._active_process is None:
            self._set_status("No active subprocess is running.", "orange")
            return
        self._active_process.terminate()
        self._append_output("[WARN] Stop requested.\n")
        self._set_status("Stop requested for active command.", "orange")

    def _append_output(self, text: str):
        self._output.config(state=tk.NORMAL)
        self._output.insert(tk.END, text)
        self._output.see(tk.END)

    def _set_status(self, text: str, level: str = "gray"):
        self._status_label.config(text=text, fg=current_theme().get(level, current_theme()["gray"]))

    def _reload_live_config(self):
        new_config = load_config(self._project_root)
        self.config = new_config
        if self._app is not None and hasattr(self._app, "reload_config"):
            self._app.reload_config(new_config)
        admin = getattr(self._app, "_admin_panel", None) if self._app is not None else None
        if admin is not None and hasattr(admin, "_refresh_credential_status"):
            admin._refresh_credential_status()

    def _handle_open_query(self, values):
        self._app.show_view("query")
        panel = getattr(self._app, "query_panel", None)
        if panel is None:
            self._set_status("Query panel is not available.", "red")
            return
        question = str(values.get("question", "") or "").strip()
        if question:
            panel.question_entry.delete(0, tk.END)
            panel.question_entry.insert(0, question)
        if values.get("run_now"):
            if str(panel.ask_btn.cget("state")) == "disabled":
                self._set_status("Query panel opened, but Ask is not ready yet.", "orange")
            else:
                panel._on_ask()
                self._set_status("Question sent to the Query panel.", "green")
                return
        self._set_status("Query panel opened.", "green")

    def _handle_open_index(self, values):
        self._app.show_view("index")
        panel = getattr(self._app, "index_panel", None)
        if panel is None:
            self._set_status("Index panel is not available.", "red")
            return
        if values.get("start_now"):
            panel._on_start()
            self._set_status("Index panel opened and start requested.", "green")
            return
        self._set_status("Index panel opened.", "green")

    def _handle_open_model_surface(self, values):
        target = "admin" if str(values.get("surface", "query")) == "admin" else "query"
        self._app.show_view(target)
        self._set_status("Opened {} for model selection.".format(target.title()), "green")

    def _handle_switch_mode_offline(self, _values):
        self._app.toggle_mode("offline")
        self._set_status("Offline mode switch requested.", "green")

    def _handle_switch_mode_online(self, _values):
        self._app.toggle_mode("online")
        self._set_status("Online mode switch requested.", "green")

    def _handle_store_api_key(self, values):
        self._append_output(store_api_key_from_gui(str(values.get("api_key", "") or "")) + "\n")
        self._set_status("API key stored.", "green")
        self._reload_live_config()

    def _handle_store_shared_token(self, values):
        self._append_output(
            store_shared_token_from_gui(
                str(values.get("shared_token", "") or ""),
                previous=bool(values.get("previous")),
            )
            + "\n"
        )
        self._set_status("Shared deployment token stored.", "green")

    def _handle_store_endpoint(self, values):
        self._append_output(
            store_endpoint_bundle_from_gui(
                str(values.get("endpoint", "") or ""),
                str(values.get("deployment", "") or ""),
                str(values.get("api_version", "") or ""),
            )
            + "\n"
        )
        self._set_status("Endpoint details stored.", "green")
        self._reload_live_config()

    def _handle_credential_status(self, _values):
        self._append_output(build_credential_report() + "\n")
        self._set_status("Credential status refreshed.", "green")

    def _handle_clear_credentials(self, _values):
        confirmed = messagebox.askyesno(
            "Clear Credentials",
            "Delete all stored API credentials from Windows Credential Manager?",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            self._set_status("Credential deletion cancelled.", "orange")
            return
        self._append_output(clear_credentials_from_gui() + "\n")
        self._set_status("Stored credentials cleared.", "green")
        self._reload_live_config()

    def _handle_show_paths(self, _values):
        self._append_output(build_paths_report(self.config) + "\n")
        self._set_status("Path report generated.", "green")

    def _handle_show_status(self, _values):
        self._append_output(build_status_report(self.config) + "\n")
        self._set_status("Status report generated.", "green")

    def _handle_show_shared_launch(self, values):
        self._append_output(
            build_shared_launch_report(
                project_root=self._project_root,
                apply_online=bool(values.get("apply_online")),
                apply_production=bool(values.get("apply_production")),
            )
            + "\n"
        )
        if values.get("apply_online") or values.get("apply_production"):
            self._reload_live_config()
            self._set_status("Shared launch posture refreshed and persisted.", "green")
            return
        self._set_status("Shared launch readiness report generated.", "green")

    def apply_theme(self, t):
        """Re-apply the shared HybridRAG dark/light theme."""

        self.configure(bg=t["panel_bg"])
        _theme_widget(self, t)
        self._command_list.configure(
            bg=t["input_bg"],
            fg=t["input_fg"],
            selectbackground=t["accent"],
            selectforeground=t["accent_fg"],
        )
        self._output.configure(bg=t["input_bg"], fg=t["input_fg"], insertbackground=t["fg"])

    def cleanup(self):
        """Terminate any running subprocess when the panel is torn down."""

        if self._active_process is not None:
            try:
                self._active_process.terminate()
            except Exception:
                pass


# Bind extracted build methods onto CommandCenterPanel.
bind_command_center_build_methods(CommandCenterPanel)
