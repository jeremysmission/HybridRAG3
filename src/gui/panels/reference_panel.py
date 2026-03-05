# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the reference panel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Reference Panel (src/gui/panels/reference_panel.py) RevB
# Revision: RevA
# ============================================================================
# WHAT: In-app reference library with embedded docs, settings, models,
#       tuning history, and sticky notes.
# WHY:  Quick access to documentation and system knowledge without
#       leaving the app. Reduces "which setting does what?" questions.
# HOW:  Five-tab ttk.Notebook. Content data lives in reference_content.py
#       to keep this file under 500 lines. The Docs tab has a sidebar +
#       content viewer, and can open external doc files via os.startfile.
#       The Notes tab persists to config/sticky_notes.txt.
# INTERNET ACCESS: NONE
# ============================================================================

import os
import tkinter as tk
from tkinter import ttk, messagebox
import logging

from src.gui.theme import (
    current_theme, FONT, FONT_BOLD, FONT_TITLE, FONT_SMALL, FONT_MONO,
    bind_hover,
)
from src.gui.panels.reference_content import (
    CATEGORIES, RETRIEVAL_SETTINGS, LLM_SETTINGS,
    PROFILES, MODEL_RANKING, TUNING_LOG,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content data -- retrieval/LLM settings, profiles, model ranking, and
# tuning log are imported from reference_content.py.  The banned-model
# text stays here because it is short and the tests scan this file for it.
# ---------------------------------------------------------------------------


class ReferencePanel(tk.Frame):
    """Quick-reference view with tabbed content (5 tabs, read-only + notes)."""

    def __init__(self, parent, project_root=None):
        """Plain-English: This function handles init."""
        t = current_theme()
        super().__init__(parent, bg=t["bg"])
        self._project_root = project_root or os.environ.get(
            "HYBRIDRAG_PROJECT_ROOT", ".")
        self._notes_path = os.path.join(
            self._project_root, "config", "sticky_notes.txt")
        # Track doc viewer widgets for theme updates and selection
        self._doc_labels = []
        self._doc_content_map = {}
        self._doc_text = None
        self._doc_sidebar = None
        self._doc_viewer_frame = None
        self._selected_label = None
        # Notebook (tabs)
        style = ttk.Style()
        style.configure("Ref.TNotebook", background=t["bg"])
        style.configure("Ref.TNotebook.Tab", font=FONT, padding=(12, 4))
        self._notebook = ttk.Notebook(self, style="Ref.TNotebook")
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_docs_tab(self._notebook, t)
        self._build_settings_tab(self._notebook, t)
        self._build_profiles_tab(self._notebook, t)
        self._build_tuning_tab(self._notebook, t)
        self._build_notes_tab(self._notebook, t)

    # -- Tab 1: Documentation (master-detail with sidebar) -----------------

    def _build_docs_tab(self, nb, t):
        """Sidebar category list + read-only content viewer."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Docs")
        self._doc_viewer_frame = frame
        # Left sidebar (~220px)
        sidebar = tk.Frame(frame, bg=t["panel_bg"], width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._doc_sidebar = sidebar
        sidebar_canvas = tk.Canvas(
            sidebar, bg=t["panel_bg"], highlightthickness=0, width=210)
        sidebar_scroll = ttk.Scrollbar(
            sidebar, orient="vertical", command=sidebar_canvas.yview)
        sidebar_inner = tk.Frame(sidebar_canvas, bg=t["panel_bg"])
        sidebar_inner.bind(
            "<Configure>",
            lambda e: sidebar_canvas.configure(
                scrollregion=sidebar_canvas.bbox("all")))
        sidebar_canvas.create_window((0, 0), window=sidebar_inner, anchor="nw")
        sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar_scroll.pack(side="right", fill="y")

        def _on_sidebar_scroll(event):
            """Plain-English: This function handles on sidebar scroll."""
            sidebar_canvas.yview_scroll(-1 * (event.delta // 120), "units")

        sidebar_canvas.bind("<MouseWheel>", _on_sidebar_scroll)
        sidebar_inner.bind("<MouseWheel>", _on_sidebar_scroll)
        # Separator
        tk.Frame(frame, bg=t["separator"], width=1).pack(side="left", fill="y")
        # Right side: content viewer
        viewer = tk.Frame(frame, bg=t["bg"])
        viewer.pack(side="left", fill="both", expand=True)
        self._doc_text = tk.Text(
            viewer, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=16, pady=12,
            insertbackground=t["fg"], state="disabled")
        viewer_scroll = ttk.Scrollbar(
            viewer, orient="vertical", command=self._doc_text.yview)
        self._doc_text.configure(yscrollcommand=viewer_scroll.set)
        self._doc_text.pack(side="left", fill="both", expand=True)
        viewer_scroll.pack(side="right", fill="y")
        # Populate sidebar categories
        first_entry = None
        for category, entries in CATEGORIES:
            cat_label = tk.Label(
                sidebar_inner, text=category, font=FONT_BOLD,
                bg=t["panel_bg"], fg=t["accent"], anchor="w")
            cat_label.pack(fill="x", padx=8, pady=(12, 2))
            cat_label.bind("<MouseWheel>", _on_sidebar_scroll)
            for name, content in entries:
                self._doc_content_map[name] = content
                lbl = tk.Label(
                    sidebar_inner, text="  " + name, font=FONT,
                    bg=t["panel_bg"], fg=t["fg"], anchor="w",
                    cursor="hand2", padx=12, pady=2)
                lbl.pack(fill="x")
                lbl.bind(
                    "<Button-1>",
                    lambda e, n=name, c=content: self._show_doc(n, c))
                lbl.bind(
                    "<Enter>",
                    lambda e, w=lbl: w.configure(bg=t["input_bg"]))
                lbl.bind(
                    "<Leave>",
                    lambda e, w=lbl: w.configure(
                        bg=t["accent"] if w is self._selected_label
                        else t["panel_bg"]))
                lbl.bind("<MouseWheel>", _on_sidebar_scroll)
                self._doc_labels.append(lbl)
                if first_entry is None:
                    first_entry = (name, content)
        if first_entry:
            self._show_doc(first_entry[0], first_entry[1])

    def _show_doc(self, name, content):
        """Highlight selected label and load content into the viewer."""
        t = current_theme()
        for lbl in self._doc_labels:
            lbl.configure(bg=t["panel_bg"], fg=t["fg"])
        for lbl in self._doc_labels:
            if lbl.cget("text").strip() == name:
                lbl.configure(bg=t["accent"], fg=t["accent_fg"])
                self._selected_label = lbl
                break
        self._doc_text.configure(state="normal")
        self._doc_text.delete("1.0", "end")
        self._doc_text.insert("1.0", content)
        self._doc_text.configure(state="disabled")
        self._doc_text.yview_moveto(0)

    def _open_doc_file(self, filepath):
        """Open an external doc file using the native Windows handler.

        Uses os.startfile so the OS picks the right application
        (e.g. Notepad for .txt, browser for .html, Acrobat for .pdf).
        Falls back to a warning dialog if the file is missing.
        """
        if os.path.isfile(filepath):
            try:
                os.startfile(filepath)
                logger.info("[OK] Opened doc: %s", filepath)
            except OSError as exc:
                logger.warning("[WARN] Could not open doc: %s", exc)
                messagebox.showwarning("Open Failed", str(exc))
        else:
            logger.warning("[WARN] Doc file not found: %s", filepath)
            messagebox.showwarning(
                "File Not Found",
                "Could not locate:\n{}".format(filepath))

    # -- Tab 2: Settings Cheat Sheet ---------------------------------------

    def _build_settings_tab(self, nb, t):
        """Every tunable retrieval and LLM parameter, explained."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Settings")
        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"])
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("setting", font=("Consolas", 10, "bold"),
                           foreground=t["green"])
        text.tag_configure("note", foreground=t["orange"])
        # Retrieval: top_k, min_score, hybrid_search, rrf_k,
        # reranker_enabled, reranker_top_n, min_chunks
        text.insert("end", "RETRIEVAL SETTINGS\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        for name, default, rng, what, notes in RETRIEVAL_SETTINGS:
            text.insert("end", "\n{}\n".format(name), "setting")
            text.insert("end", "  Default: {}   Range: {}\n".format(default, rng))
            text.insert("end", "  {}\n".format(what))
            text.insert("end", "  {}\n".format(notes), "note")
        # -- LLM settings (temperature, timeout_seconds, context_window) --
        text.insert("end", "\n\nLLM SETTINGS\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        for name, default, rng, what, notes in LLM_SETTINGS:
            text.insert("end", "\n{}\n".format(name), "setting")
            text.insert("end", "  Default: {}   Range: {}\n".format(default, rng))
            text.insert("end", "  {}\n".format(what))
            text.insert("end", "  {}\n".format(notes), "note")
        text.configure(state="disabled")

    # -- Tab 3: Profiles and Model Ranking ---------------------------------

    def _build_profiles_tab(self, nb, t):
        """Profile assignment tables and banned model list."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Profiles")
        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"])
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("header", font=("Consolas", 10, "bold"),
                           foreground=t["accent"])
        # Profiles: "sw", "eng", "pm", "sys", "log", "draft", "fe", "cyber", "gen"
        text.insert("end", "PROFILE ASSIGNMENTS\n", "heading")
        text.insert("end", "-" * 60 + "\n\n")
        text.insert("end",
                     "{:<8} {:<18} {:<18} {}\n".format(
                         "Profile", "Primary Model", "Alt Model", "Use Case"),
                     "header")
        text.insert("end", "-" * 60 + "\n")
        for prof, primary, alt, use in PROFILES:
            text.insert("end",
                         "{:<8} {:<18} {:<18} {}\n".format(
                             prof, primary, alt, use))
        # Models: phi4-mini, mistral:7b, gemma3:4b, phi4:14b-q4_K_M, mistral-nemo:12b
        text.insert("end", "\n\nAPPROVED MODEL RANKING\n", "heading")
        text.insert("end", "-" * 60 + "\n\n")
        text.insert("end",
                     "{:<20} {:<6} {:<12} {:<16} {:<7} {}\n".format(
                         "Model", "Params", "License", "Origin",
                         "Size", "Notes"),
                     "header")
        text.insert("end", "-" * 80 + "\n")
        for name, params, lic, origin, size, notes in MODEL_RANKING:
            text.insert("end",
                         "{:<20} {:<6} {:<12} {:<16} {:<7} {}\n".format(
                             name, params, lic, origin, size, notes))
        # -- Banned models (NDAA / ITAR) --
        text.insert("end", "\n\nBANNED MODELS (do not use)\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        text.insert("end", "  Qwen / Alibaba     -- China origin (NDAA)\n")
        text.insert("end", "  DeepSeek           -- China origin (NDAA)\n")
        text.insert("end", "  BGE / BAAI          -- China origin (NDAA)\n")
        text.insert("end", "  Llama / Meta        -- ITAR ban\n")
        text.configure(state="disabled")

    # -- Tab 4: Tuning Log -------------------------------------------------

    def _build_tuning_tab(self, nb, t):
        """Optimization history and critical findings (reranker danger, etc.)."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Tuning")
        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"])
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("warn", foreground=t["red"],
                           font=("Consolas", 10, "bold"))
        # NEVER enable reranker for multi-type eval
        for line in TUNING_LOG.split("\n"):
            if line.startswith("CRITICAL") or line.startswith("  - NEVER"):
                text.insert("end", line + "\n", "warn")
            elif (line.startswith("SESSION") or line.startswith("PROMPT")
                    or line.startswith("SCORING")
                    or line.startswith("INJECTION")):
                text.insert("end", line + "\n", "heading")
            else:
                text.insert("end", line + "\n")
        text.configure(state="disabled")

    # -- Tab 5: Sticky Notes -----------------------------------------------

    def _build_notes_tab(self, nb, t):
        """Editable scratch pad that saves to config/sticky_notes.txt."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Notes")
        toolbar = tk.Frame(frame, bg=t["bg"])
        toolbar.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(
            toolbar, text="Quick notes (saved automatically)",
            font=FONT_SMALL, bg=t["bg"], fg=t["label_fg"]).pack(side="left")
        purge_btn = tk.Button(
            toolbar, text="Purge All", font=FONT_SMALL,
            bg=t["red"], fg="#ffffff", relief="flat",
            bd=0, padx=10, pady=2, command=self._purge_notes)
        purge_btn.pack(side="right")
        bind_hover(purge_btn, t["red"])
        save_btn = tk.Button(
            toolbar, text="Save", font=FONT_SMALL,
            bg=t["green"], fg="#ffffff", relief="flat",
            bd=0, padx=10, pady=2, command=self._save_notes)
        save_btn.pack(side="right", padx=(0, 8))
        bind_hover(save_btn, t["green"])
        note_bg = "#3d3a2e" if t["name"] == "dark" else "#fffde7"
        note_fg = "#e8e4c9" if t["name"] == "dark" else "#333333"
        self._notes_text = tk.Text(
            frame, font=("Consolas", 11), bg=note_bg, fg=note_fg,
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=note_fg)
        self._notes_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._load_notes()

    def _load_notes(self):
        """Load saved notes from disk."""
        try:
            if os.path.isfile(self._notes_path):
                with open(self._notes_path, "r", encoding="utf-8") as f:
                    self._notes_text.insert("1.0", f.read())
        except Exception as e:
            logger.debug("Could not load sticky notes: %s", e)

    def _save_notes(self):
        """Save notes text to config/sticky_notes.txt."""
        try:
            content = self._notes_text.get("1.0", "end-1c")
            os.makedirs(os.path.dirname(self._notes_path), exist_ok=True)
            with open(self._notes_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _purge_notes(self):
        """Delete all notes (with confirmation) and remove the file."""
        if messagebox.askyesno("Purge Notes", "Delete all sticky notes?"):
            self._notes_text.delete("1.0", "end")
            try:
                if os.path.isfile(self._notes_path):
                    os.remove(self._notes_path)
            except Exception:
                pass

    # -- Theme -------------------------------------------------------------

    def apply_theme(self, t):
        """Re-apply theme colors to all reference panel widgets."""
        self.configure(bg=t["bg"])
        style = ttk.Style()
        style.configure("Ref.TNotebook", background=t["bg"])
        style.configure("Ref.TNotebook.Tab", font=FONT, padding=(12, 4))
        if self._doc_sidebar is not None:
            self._doc_sidebar.configure(bg=t["panel_bg"])
        if self._doc_text is not None:
            self._doc_text.configure(
                bg=t["panel_bg"], fg=t["fg"], insertbackground=t["fg"])
        if self._doc_viewer_frame is not None:
            self._doc_viewer_frame.configure(bg=t["bg"])
        for lbl in self._doc_labels:
            if lbl is self._selected_label:
                lbl.configure(bg=t["accent"], fg=t["accent_fg"])
            else:
                lbl.configure(bg=t["panel_bg"], fg=t["fg"])
