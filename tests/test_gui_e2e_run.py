import tkinter as tk
from tkinter import ttk

import pytest

from tools.gui_e2e.run import (
    Action,
    _install_callback_error_trap,
    _invoke_action,
)


def _make_root():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        pytest.skip("Tk runtime unavailable (Tcl interpreter state)")
    return root


def test_invoke_action_reports_async_tk_callback_exception():
    root = _make_root()

    def _fail_later():
        raise RuntimeError("callback boom")

    button = tk.Button(
        root,
        text="Explode",
        command=lambda: root.after(0, _fail_later),
    )
    button.pack()

    _install_callback_error_trap(root)

    action = Action(
        action_id="btn:explode",
        kind="button",
        widget_class=button.__class__.__name__,
        widget_path=str(button),
        label="Explode",
        state="normal",
    )

    with pytest.raises(RuntimeError, match="callback boom"):
        _invoke_action(root, action, pump_ms=40)

    root.destroy()


def test_invoke_action_reports_combobox_callback_exception():
    root = _make_root()

    combo = ttk.Combobox(root, values=["one", "two"], state="readonly")
    combo.pack()

    def _fail_later(_event=None):
        root.after(0, lambda: (_ for _ in ()).throw(RuntimeError("combo boom")))

    combo.bind("<<ComboboxSelected>>", _fail_later)
    _install_callback_error_trap(root)

    action = Action(
        action_id="combo:explode",
        kind="combobox",
        widget_class=combo.__class__.__name__,
        widget_path=str(combo),
        label="Explode Combo",
        state="readonly",
        details={"values": ["one"]},
    )

    with pytest.raises(RuntimeError, match="combo boom"):
        _invoke_action(root, action, pump_ms=40)

    root.destroy()
