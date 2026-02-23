# GUI Development Guide -- Building Desktop Apps with Python and tkinter

A beginner-friendly walkthrough of how the HybridRAG v3 desktop interface was
built. Written for someone who has never created a GUI and knows only the
basics of Python. Every concept is explained from scratch with runnable code
examples and references to the real project files.

---

## Table of Contents

1. [What Is a GUI?](#1-what-is-a-gui)
2. [Your First Window](#2-your-first-window)
3. [Adding Widgets](#3-adding-widgets)
4. [Layout Strategies](#4-layout-strategies)
5. [Making It Look Modern](#5-making-it-look-modern)
6. [Responding to User Actions](#6-responding-to-user-actions)
7. [Threading for Long Tasks](#7-threading-for-long-tasks)
8. [View Switching Without Multiple Windows](#8-view-switching-without-multiple-windows)
9. [Animations in tkinter](#9-animations-in-tkinter)
10. [Theme Toggle (Dark/Light)](#10-theme-toggle-darklight)
11. [Common Pitfalls](#11-common-pitfalls)
12. [Project File Map](#12-project-file-map)
13. [Next Steps](#13-next-steps)

---

## 1. What Is a GUI?

GUI stands for **Graphical User Interface**. It is the visual layer of a
program -- the windows, buttons, text boxes, and menus you click on instead of
typing commands into a terminal. When you open a web browser, a word processor,
or a settings panel, you are using a GUI.

Without a GUI, a Python program runs in a text-only terminal where you type
input and read output line by line. A GUI lets you present information visually,
accept clicks and keyboard input through labeled controls, and give users
feedback with colors, progress bars, and animations.

### What is tkinter?

**tkinter** (short for "Tk interface") is a GUI library that ships with every
standard Python installation. You do not need to install anything extra -- if
you have Python, you already have tkinter. It wraps a cross-platform toolkit
called Tk that has existed since the early 1990s.

### Why HybridRAG chose tkinter

The project needed a GUI that would work on restricted work laptops where
installing third-party packages is not always possible. tkinter was the right
choice because:

- **Zero dependencies** -- it is part of Python's standard library.
- **No entry in requirements.txt** -- no approval process needed.
- **Runs everywhere** -- Windows, macOS, Linux, no extra setup.
- **Lightweight** -- suitable for a prototype or internal-use tool.

Other popular options like PyQt5, PySide6, or wxPython require separate
installs and may need license review. tkinter avoids all of that.

---

## 2. Your First Window

Here is the smallest possible tkinter program. It creates an empty window,
gives it a title, sets its size, and runs the event loop.

```python
import tkinter as tk          # 1. Import the library

root = tk.Tk()                 # 2. Create the main window object
root.title("My First App")    # 3. Set the text in the title bar
root.geometry("600x400")       # 4. Set width x height in pixels
root.mainloop()                # 5. Start the event loop (keeps the window open)
```

**Line-by-line explanation:**

| Line | What It Does |
|------|-------------|
| `import tkinter as tk` | Loads the tkinter module and gives it the short alias `tk`. |
| `root = tk.Tk()` | Creates the root window. Every tkinter app has exactly one `Tk()` instance. |
| `root.title(...)` | Sets the window title shown in the title bar and taskbar. |
| `root.geometry("600x400")` | Sets the initial size. The format is `"WIDTHxHEIGHT"` in pixels. |
| `root.mainloop()` | Hands control to tkinter's **event loop**. This is a forever-loop that watches for mouse clicks, key presses, window resizes, and redraws. Your code after `mainloop()` will not run until the window closes. |

Save this as `my_first_gui.py` and run it with `python my_first_gui.py`. You
will see an empty window. Close it to exit.

In HybridRAG, the main window is created in `src/gui/app.py` inside the
`HybridRAGApp` class, which inherits from `tk.Tk`:

```python
class HybridRAGApp(tk.Tk):
    def __init__(self, ...):
        super().__init__()
        self.title("HybridRAG v3")
        self.geometry("840x780")
        self.minsize(700, 560)
```

Inheriting from `tk.Tk` means the class itself *is* the window. This is a
common pattern for larger apps because it keeps the window and its methods
together in one object.

---

## 3. Adding Widgets

A **widget** is any visible element inside a window: a label, a button, a text
entry box, a checkbox. tkinter provides about 20 built-in widget types. Here
are the four most common ones.

### Label -- displaying text

```python
import tkinter as tk

root = tk.Tk()
root.title("Labels")

label = tk.Label(root, text="Hello, world!", font=("Segoe UI", 14))
label.pack()

root.mainloop()
```

`tk.Label` shows read-only text. The first argument (`root`) is the **parent**
widget -- the container this label lives inside.

### Button -- triggering an action

```python
import tkinter as tk

def on_click():
    print("Button was clicked!")

root = tk.Tk()
btn = tk.Button(root, text="Click Me", command=on_click)
btn.pack()
root.mainloop()
```

`command=on_click` tells the button which function to call when clicked. Notice
we pass the function name *without parentheses* -- we are passing the function
itself, not calling it.

### Entry -- single-line text input

```python
entry = tk.Entry(root, font=("Segoe UI", 11))
entry.pack()

# Later, read what the user typed:
user_text = entry.get()
```

`tk.Entry` is a single-line text field. Use `.get()` to read its contents and
`.delete(0, tk.END)` to clear it.

### ScrolledText -- multi-line text area

```python
from tkinter import scrolledtext

text_area = scrolledtext.ScrolledText(root, height=10, wrap=tk.WORD)
text_area.pack(fill=tk.BOTH, expand=True)
```

`ScrolledText` is a `Text` widget with a scrollbar already attached. It is
used for the answer display in HybridRAG's `query_panel.py`.

### Placing widgets: pack(), grid(), and place()

After creating a widget you must tell tkinter where to put it. There are three
geometry managers:

| Manager | How It Works | Best For |
|---------|-------------|----------|
| `pack()` | Stacks widgets top-to-bottom (or side-to-side with `side=tk.LEFT`). | Simple linear layouts. |
| `grid(row=, column=)` | Places widgets in a table of rows and columns. | Form-like layouts with aligned fields. |
| `place(x=, y=)` | Positions widgets at exact pixel coordinates (or relative fractions). | Overlays, animations, absolute positioning. |

**Rule:** Do not mix `pack()` and `grid()` inside the same parent container.
Pick one per container. You *can* use different managers in different frames.

HybridRAG uses `pack()` for the overall layout (title bar, nav bar, content
area stacked vertically) and `place()` for the animated loading overlay that
floats on top of the answer text area.

---

## 4. Layout Strategies

Real applications need organized layouts, not just widgets stacked in a pile.
The key tool is the **Frame** -- an invisible container that groups widgets.

### Frames as containers

```python
import tkinter as tk

root = tk.Tk()

# A frame is just an invisible box that holds other widgets
top_frame = tk.Frame(root, bg="#2d2d2d")
top_frame.pack(fill=tk.X)

tk.Label(top_frame, text="Title", fg="white", bg="#2d2d2d",
         font=("Segoe UI", 15, "bold")).pack(side=tk.LEFT, padx=16)

tk.Button(top_frame, text="Settings").pack(side=tk.RIGHT, padx=16)

root.mainloop()
```

This creates a dark bar across the top with a title on the left and a button
on the right. The `fill=tk.X` makes the frame stretch to the full window width.

### The "row of frames" pattern

HybridRAG builds its layout as a vertical stack of horizontal frames:

```
+----------------------------------------------+
| Title Frame  (pack fill=X)                    |
|   [Title Label]  [Mode Buttons]  [Theme Btn]  |
+----------------------------------------------+
| NavBar Frame (pack fill=X)                    |
|   [Query] [Settings] [Cost] [Ref]            |
+----------------------------------------------+
| Content Frame (pack fill=BOTH expand=True)    |
|   (holds whichever view is currently shown)   |
+----------------------------------------------+
| Status Bar (pack fill=X side=BOTTOM)          |
+----------------------------------------------+
```

Each horizontal row is a `tk.Frame` packed with `fill=tk.X`. The content area
uses `fill=tk.BOTH, expand=True` so it stretches in both directions and absorbs
any extra space when the window is resized.

Inside `src/gui/app.py`, this is built step by step:

```python
self._build_title_bar()      # pack(fill=tk.X)
self._build_nav_bar()        # pack(fill=tk.X)
self._build_status_bar()     # pack(fill=tk.X, side=tk.BOTTOM)
self._build_content_frame()  # pack(fill=tk.BOTH, expand=True)
```

Note that the status bar is packed with `side=tk.BOTTOM` *before* the content
frame. This ensures it always stays at the bottom. The content frame fills
whatever space remains in the middle.

### Nested frames for complex rows

Within the query panel, each row of controls is its own frame:

```python
# Row 0: Use case selector
row0 = tk.Frame(self, bg=t["panel_bg"])
row0.pack(fill=tk.X, pady=(0, 8))

tk.Label(row0, text="Use case:").pack(side=tk.LEFT)
ttk.Combobox(row0, ...).pack(side=tk.LEFT, padx=(8, 0))
```

This "row of frames" pattern is the most common layout approach in tkinter.
Think of it as building a web page with horizontal `<div>` rows, each
containing elements floated left or right.

---

## 5. Making It Look Modern

Out of the box, tkinter looks dated. But with deliberate color choices, flat
styling, and consistent fonts, you can make it look professional.

### Colors and fonts

Colors in tkinter are specified as hex strings like `"#1e1e1e"` (dark gray) or
named colors like `"white"`. The hex format is `#RRGGBB` where each pair is a
two-digit hexadecimal number from 00 (none) to ff (full intensity).

Fonts are specified as tuples: `("Font Name", size)` or
`("Font Name", size, "bold")`.

```python
label = tk.Label(root,
    text="Modern Label",
    bg="#1e1e1e",      # background color
    fg="#ffffff",      # foreground (text) color
    font=("Segoe UI", 11),
)
```

### HybridRAG's theme engine

The file `src/gui/theme.py` defines two complete color palettes as Python
dictionaries -- `DARK` and `LIGHT`. Each dictionary maps semantic names to hex
colors:

```python
DARK = {
    "name": "dark",
    "bg": "#1e1e1e",           # window background
    "panel_bg": "#2d2d2d",     # panel/card background
    "fg": "#ffffff",           # main text color
    "input_bg": "#3c3c3c",    # text field background
    "accent": "#0078d4",       # highlight / action color (blue)
    "border": "#555555",       # subtle borders
    "green": "#4caf50",        # success indicator
    "red": "#f44336",          # error indicator
    # ... and more
}
```

The `LIGHT` dictionary has the same keys but with light-mode colors. Widgets
reference these semantic names instead of hardcoding hex values. This means
changing the theme requires changing one dictionary lookup -- not editing
hundreds of widgets.

### Why flat relief and accent colors matter

Modern desktop interfaces avoid 3D beveled edges (the `tk.RAISED` and
`tk.SUNKEN` looks from the 1990s). Instead they use:

- **Flat relief** (`relief=tk.FLAT`) for buttons and frames.
- **A single accent color** (like `#0078d4` blue) to draw the eye to
  interactive elements.
- **Subtle hover effects** -- a slight color change when the mouse enters a
  button.

In HybridRAG, buttons use `relief=tk.FLAT, bd=0` and the `bind_hover()`
function in `theme.py` adds a lighten-on-hover effect:

```python
from src.gui.theme import bind_hover

btn = tk.Button(root, text="Click", relief=tk.FLAT, bd=0,
                bg="#0078d4", fg="#ffffff")
btn.pack()
bind_hover(btn)  # adds Enter/Leave events for hover feedback
```

The `bind_hover()` function works by listening for mouse enter/leave events and
adjusting the background color by blending it toward white.

---

## 6. Responding to User Actions

A GUI is fundamentally event-driven. The user does something (clicks, types,
moves the mouse) and your code responds to that event. This is called the
**callback pattern**.

### Button with command=

The simplest callback is a button's `command` parameter:

```python
def save_file():
    print("Saving...")

btn = tk.Button(root, text="Save", command=save_file)
```

When clicked, tkinter calls `save_file()`. You can also use a `lambda` for
short one-liners:

```python
btn = tk.Button(root, text="Quit", command=lambda: root.destroy())
```

### Entry with bind()

For keyboard events, use `.bind()`. This connects a specific event to a
function. The function receives an `event` object with details about the event.

```python
def on_enter_key(event):
    question = entry.get()
    print("User asked:", question)

entry = tk.Entry(root)
entry.bind("<Return>", on_enter_key)  # Enter key pressed
entry.bind("<FocusIn>", on_focus)     # Field receives focus
```

In HybridRAG's `query_panel.py`, the question entry binds both the Enter key
and a focus event (to clear placeholder text):

```python
self.question_entry.bind("<Return>", self._on_ask)
self.question_entry.bind("<FocusIn>", self._on_entry_focus)
```

### Common events

| Event String | When It Fires |
|-------------|--------------|
| `<Button-1>` | Left mouse click |
| `<Return>` | Enter key pressed |
| `<FocusIn>` | Widget receives keyboard focus |
| `<FocusOut>` | Widget loses keyboard focus |
| `<Enter>` | Mouse pointer enters the widget area |
| `<Leave>` | Mouse pointer leaves the widget area |
| `<Configure>` | Widget is resized or moved |

### The lambda trap

When using `lambda` inside a loop, you must capture the loop variable:

```python
# WRONG -- all buttons will use the last value of i
for i in range(5):
    tk.Button(root, text=str(i), command=lambda: print(i))

# RIGHT -- capture i as a default argument
for i in range(5):
    tk.Button(root, text=str(i), command=lambda x=i: print(x))
```

The NavBar in `src/gui/panels/nav_bar.py` does exactly this when binding
click events to tab labels:

```python
lbl.bind("<Button-1>", lambda e, n=name: self._on_tab_click(n))
```

---

## 7. Threading for Long Tasks

### The freezing problem

tkinter's `mainloop()` runs on a single thread. If you run a slow operation
(like querying a database or calling an API) on that same thread, the entire
window freezes -- no repainting, no button clicks, nothing responds -- until
the operation finishes.

```python
# BAD -- freezes the GUI for 5 seconds
def on_click():
    import time
    time.sleep(5)           # simulates a slow query
    label.config(text="Done!")

btn = tk.Button(root, text="Run", command=on_click)
```

### The solution: background threads

Move the slow work into a separate thread using Python's `threading` module.
The background thread does the work, then schedules a GUI update back on the
main thread using `widget.after()`.

```python
import threading

def on_click():
    btn.config(state=tk.DISABLED)
    threading.Thread(target=run_query, daemon=True).start()

def run_query():
    import time
    time.sleep(5)  # slow work happens here, off the main thread
    # Schedule the GUI update on the main thread:
    root.after(0, lambda: label.config(text="Done!"))
    root.after(0, lambda: btn.config(state=tk.NORMAL))
```

**Key rule:** Never modify widgets from a background thread. Always use
`widget.after(0, callback)` to schedule the update on the main thread.

### How HybridRAG does it

In `src/gui/panels/query_panel.py`, clicking "Ask" launches a daemon thread:

```python
def _on_ask(self, event=None):
    # Disable button to prevent double-clicks
    self.ask_btn.config(state=tk.DISABLED)

    # Start the loading animation
    self._overlay.start("Searching documents...")

    # Run query in a background thread
    self._query_thread = threading.Thread(
        target=self._run_query_stream, args=(question,), daemon=True,
    )
    self._query_thread.start()
```

Inside `_run_query_stream`, every GUI update goes through `self.after()`:

```python
def _run_query_stream(self, question):
    for chunk in self.query_engine.query_stream(question):
        if "token" in chunk:
            # Safe: schedules on main thread
            self.after(0, self._append_token, chunk["token"])
        elif chunk.get("done"):
            self.after(0, self._finish_stream, chunk["result"])
```

The `daemon=True` flag means the thread will be automatically killed when the
main program exits, so you do not need to worry about it lingering.

### The after() method

`widget.after(delay_ms, callback)` schedules `callback` to run after
`delay_ms` milliseconds on the main thread. This is the safe way to update the
GUI from a background thread.

- `after(0, func)` -- run as soon as possible (next event loop iteration).
- `after(500, func)` -- run after 500 milliseconds (useful for timers).
- `after_cancel(id)` -- cancel a previously scheduled `after()` call.

HybridRAG uses `after(500, ...)` for the elapsed-time counter during queries:

```python
def _update_elapsed(self):
    elapsed = time.time() - self._stream_start
    self.network_label.config(text="Generating... ({:.1f}s)".format(elapsed))
    self._elapsed_timer_id = self.after(500, self._update_elapsed)
```

This creates a repeating 500ms timer by having the function schedule itself
again at the end.

---

## 8. View Switching Without Multiple Windows

Many beginner tkinter tutorials open a new `Toplevel()` window for each screen.
This creates a cluttered multi-window experience with separate taskbar entries
and confusing window management.

HybridRAG uses a better approach: **one window, multiple views**. Only one
view is visible at a time, and switching between them is instant.

### How it works

The main app has a content frame that holds all views. When the user clicks a
nav tab, the current view is hidden with `pack_forget()` and the new view is
shown with `pack()`:

```python
def show_view(self, name):
    # Hide the current view
    if self._current_view and self._current_view in self._views:
        self._views[self._current_view].pack_forget()

    # Build the view if this is the first time (lazy loading)
    if name not in self._views:
        self._build_view(name)

    # Show the target view
    self._views[name].pack(in_=self._content, fill=tk.BOTH, expand=True)
    self._current_view = name
    self.nav_bar.select(name)
```

**`pack_forget()`** removes a widget from the layout without destroying it.
The widget still exists in memory with all its state, so when you `pack()` it
again later, everything is exactly as the user left it.

### Lazy building

Not every view is built at startup. The Query view is built immediately
(because it is the default), but Settings, Cost, and Reference are only built
the first time the user navigates to them:

```python
def _build_view(self, name):
    if name == "settings":
        from src.gui.panels.settings_view import SettingsView
        view = SettingsView(self._content, config=self.config, app_ref=self)
        self._views["settings"] = view
    elif name == "cost":
        view = CostDashboard(self._content, self.cost_tracker)
        self._views["cost"] = view
```

This speeds up startup because only the code needed for the initial view runs.
The `import` statement itself is deferred with a local import inside the
function, so the module is not even loaded until needed.

### The NavBar

The navigation bar (`src/gui/panels/nav_bar.py`) is a row of clickable labels
with an accent underline on the selected tab. When a label is clicked, it calls
the `on_switch` callback provided by the main app, which triggers `show_view()`.

```python
class NavBar(tk.Frame):
    TABS = [
        ("Query", "query"),
        ("Settings", "settings"),
        ("Cost", "cost"),
        ("Ref", "reference"),
    ]

    def _on_tab_click(self, name):
        if name != self._current:
            self._on_switch(name)
```

The accent underline is a 3-pixel-tall frame below each label. When a tab is
selected, the underline's background color changes to the accent color.
When unselected, it matches the panel background and becomes invisible.

---

## 9. Animations in tkinter

tkinter has no built-in animation framework, but you can create smooth
animations using the **Canvas** widget and timed `after()` loops.

### The Canvas widget

A Canvas is a drawable surface. You can create shapes (rectangles, ovals,
lines, text) on it programmatically:

```python
canvas = tk.Canvas(root, width=400, height=300, bg="#1e1e1e")
canvas.pack()

# Draw a blue circle
canvas.create_oval(50, 50, 100, 100, fill="#0078d4", outline="")

# Draw a line
canvas.create_line(0, 150, 400, 150, fill="#555555")

# Draw text
canvas.create_text(200, 250, text="Loading...", fill="white",
                   font=("Segoe UI", 11, "bold"))
```

### Frame-by-frame animation with after()

To animate, you clear the canvas and redraw everything at regular intervals:

```python
class SimpleAnimation:
    def __init__(self, canvas):
        self.canvas = canvas
        self.x = 0

    def animate(self):
        self.canvas.delete("all")                    # clear everything
        self.canvas.create_oval(                     # draw at new position
            self.x, 140, self.x + 20, 160,
            fill="#0078d4", outline="",
        )
        self.x += 2                                  # move right
        if self.x > 400:
            self.x = 0                               # wrap around
        self.canvas.after(33, self.animate)          # 33ms = ~30 fps
```

The pattern is: **draw, update state, schedule next frame**. The `after(33, ...)`
creates a loop that runs approximately 30 times per second.

### HybridRAG's vector field overlay

The loading overlay in `src/gui/panels/loading_overlay.py` uses this technique
to show an animated network of floating nodes connected by lines, with bright
"sparks" traveling along the connections.

It defines three data classes:

- **`_Node`** -- a floating dot with position, velocity, radius, and brightness.
- **`_Spark`** -- a bright dot that travels along a connection between two nodes.
- **`VectorFieldOverlay`** -- the Canvas subclass that runs the animation.

Each frame, the `_animate()` method:

1. Moves every node by its velocity (wrapping at edges).
2. Finds pairs of nodes close enough to draw a connection line.
3. Spawns a new spark on a random connection every 18 frames.
4. Advances existing sparks along their connections.
5. Clears the canvas with `self.delete("all")`.
6. Draws all connection lines, nodes, sparks, and the banner text.
7. Schedules the next frame with `self.after(33, self._animate)`.

The overlay uses `place()` instead of `pack()` to float on top of the answer
text area without disrupting the layout:

```python
def start(self, phase_text="Searching documents..."):
    self.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
    self.tkraise()
    # ... initialize nodes, start animation loop
```

When the query finishes, `stop()` shows "Complete!" in green, then performs a
slide-up effect by progressively reducing `relheight` from 1.0 to 0.0:

```python
def _slide_up(self, step, on_complete):
    frac = 1.0 - ((step + 1) / FADEOUT_STEPS)
    self.place_configure(relheight=max(frac, 0.0))
    self.after(FADEOUT_STEP_MS, lambda: self._slide_up(step + 1, on_complete))
```

---

## 10. Theme Toggle (Dark/Light)

Supporting both dark and light themes means every widget needs to update its
colors on demand. Here is how HybridRAG handles it.

### The theme dictionary

As shown in Section 5, `src/gui/theme.py` defines `DARK` and `LIGHT`
dictionaries. A module-level variable `_current` tracks which is active:

```python
_current = DARK

def current_theme():
    return _current

def set_theme(theme_dict):
    global _current
    _current = theme_dict
```

### Toggling

When the user clicks the theme button, the main app calls `_toggle_theme()`:

```python
def _toggle_theme(self):
    if self._theme["name"] == "dark":
        new_theme = LIGHT
    else:
        new_theme = DARK

    set_theme(new_theme)
    self._theme = new_theme
    apply_ttk_styles(new_theme)
    self._apply_theme_to_all()
```

### Propagating colors

The `_apply_theme_to_all()` method walks through every widget and updates its
colors. It calls `widget.configure(bg=..., fg=...)` on plain tk widgets and
relies on `ttk.Style()` for themed (ttk) widgets.

Each panel exposes an `apply_theme(t)` method that the main app calls:

```python
# In app.py
def _apply_theme_to_all(self):
    self.configure(bg=t["bg"])
    self.title_frame.configure(bg=t["panel_bg"])
    # ... update title bar widgets ...

    self.nav_bar.apply_theme(t)

    if hasattr(self, "query_panel"):
        self.query_panel.apply_theme(t)
    if hasattr(self, "index_panel"):
        self.index_panel.apply_theme(t)

    for view in self._views.values():
        if hasattr(view, "apply_theme"):
            view.apply_theme(t)
```

This delegation pattern -- the app calls `apply_theme()` on each panel, and
each panel updates its own children -- keeps the code organized. No single
function needs to know about every widget in the entire application.

### The tk vs ttk challenge

tkinter has two sets of widgets:

- **tk widgets** (e.g., `tk.Button`, `tk.Label`) -- you set `bg` and `fg`
  directly on each widget.
- **ttk widgets** (e.g., `ttk.Button`, `ttk.Combobox`) -- colors are
  controlled through a `ttk.Style()` object, not per-widget options.

When theming, you must handle both. `apply_ttk_styles()` in `theme.py`
reconfigures all ttk styles at once:

```python
def apply_ttk_styles(theme_dict):
    style = ttk.Style()
    style.theme_use("clam")         # "clam" gives the most control
    t = theme_dict

    style.configure("TButton", background=t["accent"],
                     foreground=t["accent_fg"], relief="flat")
    style.configure("TCombobox", fieldbackground=t["input_bg"],
                     foreground=t["input_fg"])
    # ... more widget types ...
```

The `"clam"` theme is important. tkinter's default theme on Windows
(`"vista"`) ignores many style settings. Switching to `"clam"` gives you full
control over colors and borders.

---

## 11. Common Pitfalls

These are mistakes that catch almost every beginner (and many experienced
developers). Being aware of them will save you hours of debugging.

### Pitfall 1: ttk widgets ignore bg and fg

```python
# This does NOTHING -- ttk.Button ignores bg/fg keyword arguments
btn = ttk.Button(root, text="Click", bg="red")  # WRONG

# Instead, use styles:
style = ttk.Style()
style.configure("Red.TButton", background="red", foreground="white")
btn = ttk.Button(root, text="Click", style="Red.TButton")  # RIGHT
```

In HybridRAG's `query_panel.py`, the `apply_theme()` method explicitly skips
ttk widgets when iterating through children:

```python
if isinstance(child, ttk.Widget):
    continue  # ttk uses style, not bg/fg options
```

### Pitfall 2: mainloop() blocks everything after it

```python
root.mainloop()
print("This never prints until the window closes!")
```

All your setup code must come *before* `mainloop()`. If you need something to
happen after the window opens, use `root.after()`:

```python
root.after(100, do_something_after_startup)
root.mainloop()
```

### Pitfall 3: updating widgets from background threads

```python
# WRONG -- will cause random crashes or visual glitches
def background_work():
    label.config(text="Done!")  # BAD: modifying widget from wrong thread

# RIGHT -- schedule the update on the main thread
def background_work():
    root.after(0, lambda: label.config(text="Done!"))
```

tkinter is not thread-safe. The only thread that should touch widgets is the
main thread. Always use `after()` to bridge from a background thread.

### Pitfall 4: ScrolledText quirks

`ScrolledText` is a `Text` widget with a bundled scrollbar. Two things to
watch out for:

- It must be set to `state=tk.NORMAL` before you can insert or delete text,
  then set back to `state=tk.DISABLED` if you want it read-only.
- Its `bg` and `fg` work fine, but the scrollbar it creates is a plain tk
  scrollbar that does not follow ttk styles.

```python
# Inserting text into a read-only ScrolledText:
text_area.config(state=tk.NORMAL)
text_area.delete("1.0", tk.END)
text_area.insert("1.0", "New content here")
text_area.config(state=tk.DISABLED)
```

### Pitfall 5: mixing pack() and grid()

```python
frame = tk.Frame(root)
tk.Label(frame, text="A").pack()
tk.Label(frame, text="B").grid(row=1)  # ERROR! Cannot mix in same parent
```

Each container must use only one geometry manager. Use separate frames if you
need both `pack()` and `grid()` in the same window.

### Pitfall 6: lambda closures in loops

As mentioned in Section 6, `lambda` in a loop captures the variable by
reference, not by value. Always use a default argument to capture the current
value: `lambda x=current: ...`.

### Pitfall 7: forgetting to call update_idletasks()

If you need accurate widget dimensions immediately after creation (before the
event loop has had a chance to render), call `update_idletasks()` first:

```python
widget.update_idletasks()
actual_width = widget.winfo_width()
```

HybridRAG's loading overlay does this to get the canvas size before creating
nodes:

```python
self.update_idletasks()
w = self.winfo_width() or 400
h = self.winfo_height() or 200
```

---

## 12. Project File Map

Here is where every GUI file lives in the HybridRAG project and what it does.

### Core GUI files

| File | Purpose |
|------|---------|
| `src/gui/app.py` | Main application window. Creates the root `tk.Tk`, builds menu bar, title bar, nav bar, status bar, and content frame. Owns view switching, theme toggling, mode toggling, and backend coordination. |
| `src/gui/theme.py` | Theme engine. Defines `DARK` and `LIGHT` color dictionaries, font constants, `apply_ttk_styles()`, and the `bind_hover()` utility. |
| `src/gui/launch_gui.py` | Entry point. Runs the boot pipeline, creates `HybridRAGApp`, loads backends in a background thread, and calls `mainloop()`. |

### Panel files (in `src/gui/panels/`)

| File | Purpose |
|------|---------|
| `query_panel.py` | Query input interface. Use case dropdown, model display, question entry, ask button, answer text area, sources/metrics display, loading overlay integration. |
| `index_panel.py` | Document indexing controls. Browse for source folder, start/stop indexing, progress display. |
| `nav_bar.py` | Horizontal tab bar for view switching. Labels with accent underline indicators. |
| `status_bar.py` | Bottom status bar showing LLM status, Ollama connection, and network gate indicators. |
| `settings_view.py` | Admin settings view containing the tuning and API admin tabs. |
| `tuning_tab.py` | Configuration parameter editing (retrieval settings, prompt tuning). |
| `api_admin_tab.py` | API server controls and credential management. |
| `cost_dashboard.py` | PM cost tracking dashboard with budget gauge, token breakdown, rate editor, ROI calculator, and CSV export. |
| `reference_panel.py` | Reference information display with IBIT/CBIT health monitoring. |
| `loading_overlay.py` | Animated vector field Canvas overlay for long-running queries. |
| `setup_wizard.py` | First-run setup wizard for initial configuration. |

### Widget files (in `src/gui/widgets/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Package marker. Reusable widget components would live here. |

### How they connect

```
launch_gui.py
    |
    v
app.py (HybridRAGApp)
    |
    +-- theme.py (DARK/LIGHT dicts, apply_ttk_styles)
    |
    +-- nav_bar.py (NavBar) -----> triggers show_view()
    |
    +-- query_panel.py (QueryPanel)
    |       |
    |       +-- loading_overlay.py (VectorFieldOverlay)
    |
    +-- index_panel.py (IndexPanel)
    |
    +-- settings_view.py (SettingsView) [lazy-built]
    |       |
    |       +-- tuning_tab.py
    |       +-- api_admin_tab.py
    |
    +-- cost_dashboard.py (CostDashboard) [lazy-built]
    |
    +-- reference_panel.py (ReferencePanel) [lazy-built]
    |
    +-- status_bar.py (StatusBar)
```

---

## 13. Next Steps

Once you are comfortable with tkinter, here are paths to grow your GUI skills.

### Deeper tkinter resources

- **Official Python docs:** The `tkinter` module documentation covers every
  widget type and method. Search for "tkinter 3.12 docs" online.
- **TkDocs tutorial:** A well-written modern tutorial at tkdocs.com that
  covers tkinter (and Tk in other languages) with a focus on modern style.
- **Tcl/Tk manual pages:** tkinter is a wrapper around Tcl/Tk. The Tk man
  pages document every option in precise detail.

### CustomTkinter for modern looks

If you want a more polished appearance without leaving the tkinter ecosystem,
**CustomTkinter** is a third-party library that provides modern-looking widgets
(rounded buttons, sliders, switches) built on top of tkinter. It is a drop-in
enhancement, not a complete replacement.

```python
import customtkinter as ctk

app = ctk.CTk()
app.title("Modern App")
ctk.CTkButton(app, text="Click Me").pack(padx=20, pady=20)
app.mainloop()
```

### PyQt / PySide for production UIs

For larger, more complex applications, **PyQt6** or **PySide6** (the official
Qt bindings for Python) are industry-standard choices. Qt provides:

- A much richer widget set (tables, trees, docks, toolbars).
- Built-in model/view architecture for data-heavy apps.
- Professional styling with QSS (Qt Style Sheets, similar to CSS).
- Hardware-accelerated rendering.

The trade-off is a heavier dependency (the Qt libraries are ~100 MB) and a
steeper learning curve.

### Dear PyGui for high-performance visuals

If your application is heavily visual (plots, 3D views, real-time data),
**Dear PyGui** is a GPU-accelerated immediate-mode GUI library. It is fast
and great for dashboards, but its widget set is more limited.

### Key principles that transfer everywhere

Regardless of which framework you use next, the fundamentals you learned here
apply universally:

1. **Event-driven architecture** -- GUIs react to user events through callbacks.
2. **Threading for responsiveness** -- never block the UI thread.
3. **Layout management** -- containers, rows, flexible sizing.
4. **Theme/style separation** -- keep colors and fonts in a central location.
5. **View switching** -- show/hide panels instead of spawning windows.

These patterns appear in every GUI framework, whether it is tkinter, Qt, Electron,
SwiftUI, or a web frontend. Master them here and they will serve you everywhere.

---

*Guide version: 2026-02-22. References HybridRAG v3 codebase.*
