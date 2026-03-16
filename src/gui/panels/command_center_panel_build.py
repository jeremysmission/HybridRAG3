"""Extracted UI-building methods for CommandCenterPanel.

Keeps the main class under the 500-line budget by moving the heavy
_build() and _render_selected_spec() construction out to module-level
functions that get bound back onto the class.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from src.gui.theme import FONT, FONT_BOLD, FONT_MONO, FONT_SMALL, bind_hover, current_theme


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


def bind_command_center_build_methods(cls):
    """Bind extracted build methods onto CommandCenterPanel."""
    cls._build = _build
    cls._render_selected_spec = _render_selected_spec
