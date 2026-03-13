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

    def _build(self, t):
        tk.Label(
            self,
            text="Command Center",
            bg=t["panel_bg"],
            fg=t["accent"],
            font=FONT_BOLD,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(8, 0))
        tk.Label(
            self,
            text="Use native GUI panels where they already exist, and run the remaining CLI utilities from one dark-mode control surface.",
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_SMALL,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=980,
        ).pack(fill=tk.X, padx=16, pady=(0, 8))

        body = tk.Frame(self, bg=t["panel_bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        left = tk.LabelFrame(
            body,
            text="Commands",
            bg=t["panel_bg"],
            fg=t["accent"],
            font=FONT_BOLD,
            padx=12,
            pady=10,
        )
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_args: self._refresh_command_list())
        self._filter_entry = tk.Entry(
            left,
            textvariable=self._filter_var,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            relief=tk.FLAT,
            bd=2,
        )
        self._filter_entry.pack(fill=tk.X, pady=(0, 8))

        self._command_list = tk.Listbox(
            left,
            width=34,
            height=24,
            font=FONT,
            bg=t["input_bg"],
            fg=t["input_fg"],
            selectbackground=t["accent"],
            selectforeground=t["accent_fg"],
            relief=tk.FLAT,
            bd=0,
            activestyle="none",
        )
        self._command_list.pack(fill=tk.BOTH, expand=True)
        self._command_list.bind("<<ListboxSelect>>", self._on_list_select)

        right = tk.Frame(body, bg=t["panel_bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._detail_frame = tk.LabelFrame(
            right,
            text="Details",
            bg=t["panel_bg"],
            fg=t["accent"],
            font=FONT_BOLD,
            padx=16,
            pady=12,
        )
        self._detail_frame.pack(fill=tk.X)

        self._detail_title = tk.Label(
            self._detail_frame,
            text="",
            bg=t["panel_bg"],
            fg=t["fg"],
            font=FONT_BOLD,
            anchor=tk.W,
        )
        self._detail_title.pack(fill=tk.X)

        self._detail_alias = tk.Label(
            self._detail_frame,
            text="",
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_MONO,
            anchor=tk.W,
        )
        self._detail_alias.pack(fill=tk.X, pady=(2, 0))

        self._detail_summary = tk.Label(
            self._detail_frame,
            text="",
            bg=t["panel_bg"],
            fg=t["fg"],
            font=FONT,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=760,
        )
        self._detail_summary.pack(fill=tk.X, pady=(6, 0))

        self._detail_hint = tk.Label(
            self._detail_frame,
            text="",
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_SMALL,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=760,
        )
        self._detail_hint.pack(fill=tk.X, pady=(4, 8))

        self._form_frame = tk.Frame(self._detail_frame, bg=t["panel_bg"])
        self._form_frame.pack(fill=tk.X)

        self._action_row = tk.Frame(self._detail_frame, bg=t["panel_bg"])
        self._action_row.pack(fill=tk.X, pady=(10, 0))

        self._run_btn = tk.Button(
            self._action_row,
            text="Run",
            command=self._execute_selected,
            bg=t["accent"],
            fg=t["accent_fg"],
            font=FONT_BOLD,
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=8,
        )
        self._run_btn.pack(side=tk.LEFT)
        bind_hover(self._run_btn)

        self._cancel_btn = tk.Button(
            self._action_row,
            text="Stop Active Command",
            command=self._cancel_active_process,
            bg=t["inactive_btn_bg"],
            fg=t["inactive_btn_fg"],
            font=FONT,
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=8,
            state=tk.DISABLED,
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        self._status_label = tk.Label(
            self._detail_frame,
            text="Select a command to see its GUI equivalent.",
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_SMALL,
            anchor=tk.W,
        )
        self._status_label.pack(fill=tk.X, pady=(8, 0))

        output_frame = tk.LabelFrame(
            right,
            text="Output",
            bg=t["panel_bg"],
            fg=t["accent"],
            font=FONT_BOLD,
            padx=12,
            pady=10,
        )
        output_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self._output = scrolledtext.ScrolledText(
            output_frame,
            height=18,
            font=FONT_MONO,
            bg=t["input_bg"],
            fg=t["input_fg"],
            insertbackground=t["fg"],
            relief=tk.FLAT,
            bd=0,
            wrap=tk.WORD,
        )
        self._output.pack(fill=tk.BOTH, expand=True)

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

    def _render_selected_spec(self):
        spec = self._selected_spec
        if spec is None:
            return

        self._detail_title.config(text=spec.title)
        self._detail_alias.config(text="CLI: {}".format(spec.cli_equivalent))
        self._detail_summary.config(text=spec.summary)
        self._detail_hint.config(text=spec.detail)
        self._run_btn.config(text=spec.run_label)
        self._field_vars.clear()
        self._field_widgets.clear()

        for child in self._form_frame.winfo_children():
            child.destroy()

        t = current_theme()
        for field in spec.fields:
            row = tk.Frame(self._form_frame, bg=t["panel_bg"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(
                row,
                text=field.label + ":",
                bg=t["panel_bg"],
                fg=t["label_fg"],
                font=FONT,
                width=16,
                anchor=tk.W,
            ).pack(side=tk.LEFT)

            if field.kind == "bool":
                var = tk.BooleanVar(value=bool(field.default))
                widget = tk.Checkbutton(
                    row,
                    variable=var,
                    bg=t["panel_bg"],
                    fg=t["fg"],
                    selectcolor=t["input_bg"],
                    activebackground=t["panel_bg"],
                    activeforeground=t["fg"],
                )
                widget.pack(side=tk.LEFT)
                self._field_vars[field.key] = var
            elif field.kind == "choice":
                default = ""
                for value, label in field.choices:
                    if value == field.default:
                        default = label
                        break
                if not default:
                    default = str(field.default or (field.choices[0][1] if field.choices else ""))
                var = tk.StringVar(value=default)
                widget = ttk.Combobox(
                    row,
                    textvariable=var,
                    values=[label for _value, label in field.choices],
                    state="readonly",
                    width=26,
                    font=FONT,
                )
                widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self._field_vars[field.key] = var
            elif field.kind == "multiline":
                widget = tk.Text(
                    row,
                    height=4,
                    font=FONT,
                    bg=t["input_bg"],
                    fg=t["input_fg"],
                    insertbackground=t["fg"],
                    relief=tk.FLAT,
                    bd=2,
                    wrap=tk.WORD,
                )
                if field.default:
                    widget.insert("1.0", str(field.default))
                widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            else:
                var = tk.StringVar(value=str(field.default or ""))
                widget = tk.Entry(
                    row,
                    textvariable=var,
                    show="*" if field.kind == "password" else "",
                    font=FONT,
                    bg=t["input_bg"],
                    fg=t["input_fg"],
                    insertbackground=t["fg"],
                    relief=tk.FLAT,
                    bd=2,
                )
                widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self._field_vars[field.key] = var

            self._field_widgets[field.key] = widget

            if field.help_text:
                tk.Label(
                    self._form_frame,
                    text=field.help_text,
                    bg=t["panel_bg"],
                    fg=t["gray"],
                    font=FONT_SMALL,
                    anchor=tk.W,
                    justify=tk.LEFT,
                    wraplength=760,
                ).pack(fill=tk.X, padx=(16, 0), pady=(0, 4))

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
