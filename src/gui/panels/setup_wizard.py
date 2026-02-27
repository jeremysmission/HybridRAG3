# ============================================================================
# HybridRAG v3 -- First-Run Setup Wizard (src/gui/panels/setup_wizard.py)
# ============================================================================
# WHAT: A 4-step modal wizard that runs on first launch to configure
#       the essential settings before the user can start searching.
# WHY:  New users need to tell the system where their documents live
#       and where to store the search index.  Without this, the app
#       would start with empty paths and immediately fail.  A wizard
#       is friendlier than editing a YAML file by hand.
# HOW:  Four stacked frames with Back/Next/Finish navigation.  Each
#       page collects one piece of information.  On Finish, the wizard
#       writes everything to config/default_config.yaml and sets
#       setup_complete: true so it never runs again.
# USAGE: Launched automatically by launch_gui.py when needs_setup()
#        returns True.  Can also be triggered manually for re-setup.
#
# Pages:
#   1. Welcome          -- what this wizard does
#   2. Data Paths       -- source folder + index folder
#   3. Mode Selection   -- offline (Ollama) vs online (API)
#   4. Review & Finish  -- read-only summary, confirm and save
#
# INTERNET ACCESS: NONE -- reads/writes local YAML only
# ============================================================================

import os
import tkinter as tk
from tkinter import filedialog

import yaml

from src.gui.theme import (
    current_theme, FONT, FONT_BOLD, FONT_TITLE, FONT_SMALL,
    bind_hover,
)

# ---------------------------------------------------------------------------
# Module-level helper: should the wizard run?
# ---------------------------------------------------------------------------

def needs_setup(project_root):
    """Return True if the first-run wizard should be shown.

    Validates that configured paths actually exist on disk, not just that
    the setup_complete flag is set.  This handles the case where config
    was written on a different machine (e.g. synced from private repo to
    Educational repo) and the paths don't exist locally.

    Checks (in order):
      1. HYBRIDRAG_DATA_DIR env var set           -> skip wizard
      2. No config file / unparseable             -> show wizard
      3. Paths not configured                     -> show wizard
      4. Configured paths don't exist on disk     -> show wizard
      5. Everything valid                         -> skip wizard
    """
    if os.environ.get("HYBRIDRAG_DATA_DIR"):
        return False

    cfg_path = os.path.join(project_root, "config", "default_config.yaml")
    if not os.path.isfile(cfg_path):
        return True

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return True
    except Exception:
        return True

    paths = data.get("paths", {})
    source = paths.get("source_folder", "")
    database = paths.get("database", "")

    # Both paths must be configured
    if not source or not database:
        return True

    # Source folder must exist on disk
    if not os.path.isdir(source):
        return True

    # Database parent directory must exist (or be creatable)
    db_parent = os.path.dirname(database)
    if db_parent and not os.path.isdir(db_parent):
        return True

    return False


# ---------------------------------------------------------------------------
# Wizard window
# ---------------------------------------------------------------------------

_PAGE_WELCOME = 0
_PAGE_PATHS = 1
_PAGE_MODE = 2
_PAGE_REVIEW = 3
_NUM_PAGES = 4


class SetupWizard(tk.Toplevel):
    """4-step first-run setup wizard.

    A modal dialog that walks the user through selecting data paths
    and operating mode.  Sets self.completed = True if the user clicks
    Finish, False if they cancel.  The caller checks this flag to decide
    whether to proceed with app launch.
    """

    def __init__(self, parent, project_root):
        t = current_theme()
        super().__init__(parent)
        self.title("HybridRAG Setup")
        self.geometry("620x480")
        self.minsize(540, 420)
        self.configure(bg=t["bg"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._project_root = project_root
        self.completed = False
        self._page = _PAGE_WELCOME

        # User selections
        self._source_var = tk.StringVar()
        self._index_var = tk.StringVar()
        self._mode_var = tk.StringVar(value="offline")

        # Page container (stacked frames)
        self._container = tk.Frame(self, bg=t["bg"])
        self._container.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        self._pages = []
        for builder in (
            self._build_welcome,
            self._build_paths,
            self._build_mode,
            self._build_review,
        ):
            frame = tk.Frame(self._container, bg=t["bg"])
            builder(frame, t)
            self._pages.append(frame)

        # Navigation bar
        self._build_nav(t)

        # Show first page
        self._show_page(_PAGE_WELCOME)

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry("+{}+{}".format((sw - w) // 2, (sh - h) // 2))

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _build_welcome(self, frame, t):
        """Page 1: Welcome message explaining what the wizard will do."""
        tk.Label(
            frame, text="Welcome to HybridRAG", font=FONT_TITLE,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(16, 12))

        msg = (
            "This wizard will configure the two essential paths that "
            "HybridRAG needs to operate:\n\n"
            "  1.  Source Documents folder -- where your files live\n"
            "  2.  Index Data folder -- where the search index is stored\n\n"
            "You will also choose between Offline (Ollama) and Online (API) mode.\n\n"
            "All settings can be changed later from the Admin menu."
        )
        tk.Label(
            frame, text=msg, font=FONT, bg=t["bg"], fg=t["fg"],
            justify="left", wraplength=540, anchor="nw",
        ).pack(fill="x", pady=(0, 8))

    def _build_paths(self, frame, t):
        """Page 2: Source and index folder selection with browse buttons."""
        tk.Label(
            frame, text="Data Paths", font=FONT_TITLE,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(16, 12))

        # Source folder
        tk.Label(
            frame, text="Source Documents Folder", font=FONT_BOLD,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w")
        tk.Label(
            frame, text="Folder containing the files you want to search.",
            font=FONT_SMALL, bg=t["bg"], fg=t["label_fg"],
        ).pack(anchor="w")

        src_row = tk.Frame(frame, bg=t["bg"])
        src_row.pack(fill="x", pady=(4, 12))
        src_entry = tk.Entry(
            src_row, textvariable=self._source_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief="flat", bd=2,
        )
        src_entry.pack(side="left", fill="x", expand=True, ipady=4)
        src_btn = tk.Button(
            src_row, text="Browse...", font=FONT,
            bg=t["accent"], fg=t["accent_fg"], relief="flat",
            bd=0, padx=12, pady=4,
            command=lambda: self._browse_dir(self._source_var),
        )
        src_btn.pack(side="left", padx=(8, 0))
        bind_hover(src_btn, t["accent"])

        # Index folder
        tk.Label(
            frame, text="Index Data Folder", font=FONT_BOLD,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w")
        tk.Label(
            frame,
            text="Where the search database and embeddings are stored. "
                 "Will be created if it does not exist.",
            font=FONT_SMALL, bg=t["bg"], fg=t["label_fg"],
            wraplength=540,
        ).pack(anchor="w")

        idx_row = tk.Frame(frame, bg=t["bg"])
        idx_row.pack(fill="x", pady=(4, 12))
        idx_entry = tk.Entry(
            idx_row, textvariable=self._index_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief="flat", bd=2,
        )
        idx_entry.pack(side="left", fill="x", expand=True, ipady=4)
        idx_btn = tk.Button(
            idx_row, text="Browse...", font=FONT,
            bg=t["accent"], fg=t["accent_fg"], relief="flat",
            bd=0, padx=12, pady=4,
            command=lambda: self._browse_dir(self._index_var),
        )
        idx_btn.pack(side="left", padx=(8, 0))
        bind_hover(idx_btn, t["accent"])

    def _build_mode(self, frame, t):
        """Page 3: Offline vs Online mode radio button selection."""
        tk.Label(
            frame, text="Mode Selection", font=FONT_TITLE,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(16, 12))

        tk.Label(
            frame,
            text="Choose how HybridRAG connects to an LLM for answering queries.",
            font=FONT, bg=t["bg"], fg=t["fg"], wraplength=540,
        ).pack(anchor="w", pady=(0, 16))

        # Offline radio
        off_frame = tk.Frame(frame, bg=t["panel_bg"], bd=1, relief="solid",
                             highlightbackground=t["border"])
        off_frame.pack(fill="x", pady=(0, 8), ipady=8, ipadx=12)
        tk.Radiobutton(
            off_frame, text="Offline (Ollama)", font=FONT_BOLD,
            variable=self._mode_var, value="offline",
            bg=t["panel_bg"], fg=t["fg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], selectcolor=t["input_bg"],
        ).pack(anchor="w")
        tk.Label(
            off_frame,
            text="Runs a local LLM on your machine. No internet required, "
                 "no API costs. Recommended for most users.",
            font=FONT_SMALL, bg=t["panel_bg"], fg=t["label_fg"],
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=(24, 0))

        # Online radio
        on_frame = tk.Frame(frame, bg=t["panel_bg"], bd=1, relief="solid",
                            highlightbackground=t["border"])
        on_frame.pack(fill="x", ipady=8, ipadx=12)
        tk.Radiobutton(
            on_frame, text="Online (API)", font=FONT_BOLD,
            variable=self._mode_var, value="online",
            bg=t["panel_bg"], fg=t["fg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], selectcolor=t["input_bg"],
        ).pack(anchor="w")
        tk.Label(
            on_frame,
            text="Uses a remote API endpoint. Requires an API key and "
                 "internet access. Configure endpoint in Admin menu after setup.",
            font=FONT_SMALL, bg=t["panel_bg"], fg=t["label_fg"],
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=(24, 0))

    def _build_review(self, frame, t):
        """Page 4: Read-only summary of all selections before saving."""
        tk.Label(
            frame, text="Review & Finish", font=FONT_TITLE,
            bg=t["bg"], fg=t["fg"],
        ).pack(anchor="w", pady=(16, 12))

        tk.Label(
            frame,
            text="Confirm your settings. Click Finish to save and launch HybridRAG.",
            font=FONT, bg=t["bg"], fg=t["fg"], wraplength=540,
        ).pack(anchor="w", pady=(0, 12))

        self._review_text = tk.Text(
            frame, font=("Consolas", 10), bg=t["panel_bg"], fg=t["fg"],
            relief="flat", bd=2, height=12, wrap="word",
            insertbackground=t["fg"],
        )
        self._review_text.pack(fill="both", expand=True, pady=(0, 8))
        self._review_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Navigation bar
    # ------------------------------------------------------------------

    def _build_nav(self, t):
        """Build the Back/Next/Finish/Cancel navigation bar."""
        nav = tk.Frame(self, bg=t["bg"])
        nav.pack(fill="x", padx=24, pady=(8, 16))

        self._error_label = tk.Label(
            nav, text="", font=FONT_SMALL, bg=t["bg"], fg=t["red"],
            wraplength=300, anchor="w", justify="left",
        )
        self._error_label.pack(side="left", fill="x", expand=True)

        self._cancel_btn = tk.Button(
            nav, text="Cancel", font=FONT,
            bg=t["input_bg"], fg=t["fg"], relief="flat",
            bd=0, padx=16, pady=6, command=self._on_cancel,
        )
        self._cancel_btn.pack(side="right", padx=(8, 0))
        bind_hover(self._cancel_btn, t["input_bg"])

        self._finish_btn = tk.Button(
            nav, text="Finish", font=FONT_BOLD,
            bg=t["green"], fg="#ffffff", relief="flat",
            bd=0, padx=20, pady=6, command=self._on_finish,
        )
        self._finish_btn.pack(side="right", padx=(8, 0))
        bind_hover(self._finish_btn, t["green"])

        self._next_btn = tk.Button(
            nav, text="Next", font=FONT_BOLD,
            bg=t["accent"], fg=t["accent_fg"], relief="flat",
            bd=0, padx=20, pady=6, command=self._go_next,
        )
        self._next_btn.pack(side="right", padx=(8, 0))
        bind_hover(self._next_btn, t["accent"])

        self._back_btn = tk.Button(
            nav, text="Back", font=FONT,
            bg=t["input_bg"], fg=t["fg"], relief="flat",
            bd=0, padx=16, pady=6, command=self._go_back,
        )
        self._back_btn.pack(side="right")
        bind_hover(self._back_btn, t["input_bg"])

    # ------------------------------------------------------------------
    # Page navigation
    # ------------------------------------------------------------------

    def _show_page(self, idx):
        """Switch to page `idx`, hiding all others and updating nav buttons."""
        for p in self._pages:
            p.pack_forget()
        self._pages[idx].pack(fill="both", expand=True)
        self._page = idx
        self._error_label.configure(text="")

        # Button visibility
        if idx == _PAGE_WELCOME:
            self._back_btn.pack_forget()
        else:
            self._back_btn.pack(side="right")

        if idx == _PAGE_REVIEW:
            self._next_btn.pack_forget()
            self._finish_btn.pack(side="right", padx=(8, 0))
            self._refresh_review()
        else:
            self._finish_btn.pack_forget()
            self._next_btn.pack(side="right", padx=(8, 0))

    def _go_next(self):
        """Advance to the next page (with validation on the Paths page)."""
        if self._page == _PAGE_PATHS:
            err = self._validate_paths()
            if err:
                self._error_label.configure(text=err)
                return
        self._show_page(self._page + 1)

    def _go_back(self):
        """Go back to the previous page."""
        if self._page > _PAGE_WELCOME:
            self._show_page(self._page - 1)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _browse_dir(self, var):
        """Open a native folder picker and set the result into the given StringVar."""
        d = filedialog.askdirectory(parent=self, title="Select Folder")
        if d:
            var.set(os.path.normpath(d))

    def _validate_paths(self):
        """Check that both paths are valid. Returns error string or empty on success."""
        src = self._source_var.get().strip()
        idx = self._index_var.get().strip()

        if not src:
            return "Source documents folder is required."
        if not os.path.isdir(src):
            return "Source folder does not exist: " + src
        if not idx:
            return "Index data folder is required."
        # Parent of index dir must exist (we create the leaf)
        parent = os.path.dirname(idx)
        if parent and not os.path.isdir(parent):
            return "Parent of index folder does not exist: " + parent
        return ""

    # ------------------------------------------------------------------
    # Review page refresh
    # ------------------------------------------------------------------

    def _refresh_review(self):
        """Populate the review text with a summary of all user selections."""
        src = self._source_var.get().strip()
        idx = self._index_var.get().strip()
        db = os.path.join(idx, "hybridrag.sqlite3")
        emb = os.path.join(idx, "_embeddings")
        mode = self._mode_var.get()
        model = "phi4-mini" if mode == "offline" else "(configured via API)"

        lines = [
            "Source Documents:   " + src,
            "Index Data Folder:  " + idx,
            "",
            "Database Path:      " + db,
            "Embeddings Cache:   " + emb,
            "",
            "Mode:               " + mode,
            "Default Model:      " + model,
        ]

        self._review_text.configure(state="normal")
        self._review_text.delete("1.0", "end")
        self._review_text.insert("1.0", "\n".join(lines))
        self._review_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Finish: save config to YAML
    # ------------------------------------------------------------------

    def _on_finish(self):
        """Save all settings to YAML, create directories, and close the wizard."""
        src = self._source_var.get().strip()
        idx = self._index_var.get().strip()
        mode = self._mode_var.get()

        db_path = os.path.join(idx, "hybridrag.sqlite3")
        emb_path = os.path.join(idx, "_embeddings")

        # Create directories
        os.makedirs(idx, exist_ok=True)
        os.makedirs(emb_path, exist_ok=True)

        # Read-modify-write the YAML config
        cfg_path = os.path.join(self._project_root, "config", "default_config.yaml")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}

        if "paths" not in data:
            data["paths"] = {}
        data["paths"]["database"] = db_path
        data["paths"]["embeddings_cache"] = emb_path
        data["paths"]["source_folder"] = src
        data["mode"] = mode
        data["setup_complete"] = True

        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        self.completed = True
        self.grab_release()
        self.destroy()

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _on_cancel(self):
        """Close the wizard without saving. The app will exit."""
        self.completed = False
        self.grab_release()
        self.destroy()
