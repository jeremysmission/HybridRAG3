# ============================================================================
# HybridRAG v3 -- Reference Panel (src/gui/panels/reference_panel.py) RevB
# ============================================================================
# WHAT: In-app reference library with embedded docs, settings guide, model
#       info, tuning history, and sticky notes.
# WHY:  Users and admins need quick access to documentation and system
#       knowledge without leaving the app or hunting through folders.
#       Having a Settings cheat sheet and model ranking inside the tool
#       reduces "which setting does what?" questions during demos.
# HOW:  Five-tab ttk.Notebook with read-only text widgets.  Content is
#       defined as module-level data structures (outside the class) to
#       keep the class under 500 lines.  The Docs tab uses a master-detail
#       layout with a category sidebar and a content viewer.  The Notes
#       tab persists to config/sticky_notes.txt for quick scratch-pad use.
# USAGE: Navigate via NavBar > Ref, or Admin > Ref.
#
# Tabs:
#   1. Docs       -- master-detail viewer with embedded doc content
#   2. Settings   -- cheat sheet for every tunable retrieval/LLM setting
#   3. Profiles   -- model ranking, profile assignments, hardware tiers
#   4. Tuning     -- log of optimization changes and their impact
#   5. Notes      -- persistent sticky notes (saved to config/sticky_notes.txt)
#
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
from src.gui.panels.reference_content import CATEGORIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content data (kept outside class to stay under 500-line class limit)
# ---------------------------------------------------------------------------

_RETRIEVAL_SETTINGS = [
    ("top_k", "5", "3-20",
     "Number of chunks sent to LLM as context.",
     "Higher = more context but slower, may dilute relevance. "
     "Eval tuned to 5 for accuracy. Use 8-12 for broad research queries."),
    ("min_score", "0.10", "0.0-1.0",
     "Minimum similarity score to include a chunk.",
     "Lower = more results (may include noise). 0.10 tuned for 98% eval pass rate. "
     "Raise to 0.25+ if getting irrelevant chunks."),
    ("hybrid_search", "true", "bool",
     "Combines BM25 keyword + vector semantic search via RRF.",
     "Always on for technical docs. Helps with exact terms, part numbers, acronyms."),
    ("rrf_k", "60", "1-100",
     "Reciprocal Rank Fusion constant.",
     "Higher = less aggressive merge between BM25 and vector results. "
     "60 is the standard value from the original RRF paper."),
    ("reranker_enabled", "false", "bool",
     "Cross-encoder re-ranks candidate chunks. Adds 1-2s latency.",
     "NEVER enable for multi-type eval (destroys unanswerable/injection scores). "
     "Useful for single-type factual queries where accuracy > speed."),
    ("reranker_top_n", "20", "5-50",
     "How many candidates to retrieve before reranking.",
     "Only used when reranker_enabled=true. Higher = better quality, more latency."),
    ("min_chunks", "1", "0-5",
     "Minimum chunks needed before calling LLM.",
     "1 = refuse to answer if no evidence found (source-bounded generation). "
     "0 = allow LLM to answer with no context (not recommended)."),
]

_LLM_SETTINGS = [
    ("model (offline)", "phi4-mini", "--",
     "Primary Ollama model for offline queries.",
     "3.8B params, MIT license, Microsoft/USA. Fast on CPU, 128K context window."),
    ("temperature", "0.05", "0.0-2.0",
     "Randomness in LLM output.",
     "Lower = more focused/consistent. 0.05 tuned for factual accuracy. "
     "Raise to 0.3-0.7 for creative/brainstorming tasks."),
    ("timeout_seconds", "600", "30-1200",
     "Max wait time for Ollama response.",
     "600s (10min) allows slow hardware to finish long responses. "
     "Reduce to 120s on fast hardware."),
    ("context_window", "8192", "2048-131072",
     "Max tokens the model sees at once.",
     "8192 is safe for phi4-mini on 8GB RAM. Increase with more RAM/GPU."),
    ("max_tokens (online)", "2048", "256-8192",
     "Max output tokens for API mode responses.",
     "2048 is generous for most answers. Reduce to save cost on simple queries."),
]

_PROFILES = [
    ("sw", "phi4-mini", "mistral:7b", "Software engineering"),
    ("eng", "phi4-mini", "mistral:7b", "General engineering"),
    ("pm", "phi4-mini", "gemma3:4b", "Project management"),
    ("sys", "phi4-mini", "mistral:7b", "Systems engineering"),
    ("log", "phi4:14b-q4_K_M", "phi4-mini", "Logistics (workstation)"),
    ("draft", "phi4-mini", "mistral:7b", "Technical writing"),
    ("fe", "phi4-mini", "mistral:7b", "Front-end development"),
    ("cyber", "phi4-mini", "mistral:7b", "Cybersecurity"),
    ("gen", "phi4-mini", "gemma3:4b", "General purpose"),
]

_MODEL_RANKING = [
    ("phi4-mini", "3.8B", "MIT", "Microsoft/USA", "2.3GB", "Primary for 7/9 profiles"),
    ("mistral:7b", "7B", "Apache 2.0", "Mistral/France", "4.1GB", "Alt for eng-heavy"),
    ("gemma3:4b", "4B", "Apache 2.0", "Google/USA", "3.3GB", "PM fast summarization"),
    ("phi4:14b-q4_K_M", "14B", "MIT", "Microsoft/USA", "9.1GB", "Workstation primary"),
    ("mistral-nemo:12b", "12B", "Apache 2.0", "Mistral/France", "7.1GB", "128K ctx upgrade"),
]

_TUNING_LOG = """\
SESSION 11: OPTIMIZATION CAMPAIGN
  Result: 98% pass rate on 400-question golden set
  LLM: API via OpenRouter, temperature=0.05
  Config: min_score=0.10, top_k=12 (eval), reranker_enabled=false
  Prompt: v4, 9-rule source-bounded generation with priority ordering
  8 known failures:
    - 6 log retention questions (embedding quality issue)
    - 2 calibration questions (fixed by adding Exact: rule)

CRITICAL FINDINGS:
  - Reranker ON destroys multi-type eval scores:
      unanswerable: 100% -> 76%
      injection: 100% -> 46%
      ambiguous: 100% -> 82%
  - NEVER enable reranker for multi-type evaluation

PROMPT v4 PRIORITY ORDER:
  1. Injection/refusal (never echo false claims)
  2. Ambiguity detection
  3. Factual accuracy from sources
  4. Formatting rules
  5. Source citation

SCORING WEIGHTS:
  run_eval.py:    0.7 * fact + 0.3 * behavior
  score_results.py: 0.45 * behavior + 0.35 * fact + 0.20 * citation

INJECTION TRAP:
  AES-512 planted in Engineer_Calibration_Guide.pdf
  AES_RE regex catches "AES-512" anywhere in answer text\
"""


class ReferencePanel(tk.Frame):
    """Quick-reference view with tabbed content.

    Contains five tabs of read-only reference material plus one
    editable sticky notes tab.  All content is statically defined
    in module-level variables above the class to keep the class
    body under 500 lines.
    """

    def __init__(self, parent, project_root=None):
        t = current_theme()
        super().__init__(parent, bg=t["bg"])

        self._project_root = project_root or os.environ.get(
            "HYBRIDRAG_PROJECT_ROOT", "."
        )
        self._notes_path = os.path.join(
            self._project_root, "config", "sticky_notes.txt"
        )

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
        style.configure("Ref.TNotebook.Tab", font=FONT,
                        padding=(12, 4))

        self._notebook = ttk.Notebook(self, style="Ref.TNotebook")
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_docs_tab(self._notebook, t)
        self._build_settings_tab(self._notebook, t)
        self._build_profiles_tab(self._notebook, t)
        self._build_tuning_tab(self._notebook, t)
        self._build_notes_tab(self._notebook, t)

    # ------------------------------------------------------------------
    # Tab 1: Documentation (master-detail layout)
    # ------------------------------------------------------------------

    def _build_docs_tab(self, nb, t):
        """Build the Docs tab with a sidebar category list and content viewer."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Docs")
        self._doc_viewer_frame = frame

        # -- Left sidebar: scrollable category list (~220px) --
        sidebar = tk.Frame(frame, bg=t["panel_bg"], width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._doc_sidebar = sidebar

        sidebar_canvas = tk.Canvas(
            sidebar, bg=t["panel_bg"], highlightthickness=0, width=210,
        )
        sidebar_scroll = ttk.Scrollbar(
            sidebar, orient="vertical", command=sidebar_canvas.yview,
        )
        sidebar_inner = tk.Frame(sidebar_canvas, bg=t["panel_bg"])
        sidebar_inner.bind(
            "<Configure>",
            lambda e: sidebar_canvas.configure(
                scrollregion=sidebar_canvas.bbox("all")),
        )
        sidebar_canvas.create_window((0, 0), window=sidebar_inner, anchor="nw")
        sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar_scroll.pack(side="right", fill="y")

        def _on_sidebar_scroll(event):
            sidebar_canvas.yview_scroll(-1 * (event.delta // 120), "units")

        sidebar_canvas.bind("<MouseWheel>", _on_sidebar_scroll)
        sidebar_inner.bind("<MouseWheel>", _on_sidebar_scroll)

        # Separator between sidebar and content
        sep = tk.Frame(frame, bg=t["separator"], width=1)
        sep.pack(side="left", fill="y")

        # -- Right side: read-only text content viewer --
        viewer = tk.Frame(frame, bg=t["bg"])
        viewer.pack(side="left", fill="both", expand=True)

        self._doc_text = tk.Text(
            viewer, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=16, pady=12,
            insertbackground=t["fg"], state="disabled",
        )
        viewer_scroll = ttk.Scrollbar(
            viewer, orient="vertical", command=self._doc_text.yview,
        )
        self._doc_text.configure(yscrollcommand=viewer_scroll.set)
        self._doc_text.pack(side="left", fill="both", expand=True)
        viewer_scroll.pack(side="right", fill="y")

        # Populate sidebar with categories and doc links
        first_entry = None
        for category, entries in CATEGORIES:
            cat_label = tk.Label(
                sidebar_inner, text=category, font=FONT_BOLD,
                bg=t["panel_bg"], fg=t["accent"], anchor="w",
            )
            cat_label.pack(fill="x", padx=8, pady=(12, 2))
            cat_label.bind("<MouseWheel>", _on_sidebar_scroll)

            for name, content in entries:
                self._doc_content_map[name] = content
                lbl = tk.Label(
                    sidebar_inner, text="  " + name, font=FONT,
                    bg=t["panel_bg"], fg=t["fg"], anchor="w",
                    cursor="hand2", padx=12, pady=2,
                )
                lbl.pack(fill="x")
                lbl.bind(
                    "<Button-1>",
                    lambda e, n=name, c=content: self._show_doc(n, c),
                )
                lbl.bind(
                    "<Enter>",
                    lambda e, w=lbl: w.configure(bg=t["input_bg"]),
                )
                lbl.bind(
                    "<Leave>",
                    lambda e, w=lbl: w.configure(
                        bg=t["accent"] if w is self._selected_label
                        else t["panel_bg"]),
                )
                lbl.bind("<MouseWheel>", _on_sidebar_scroll)
                self._doc_labels.append(lbl)
                if first_entry is None:
                    first_entry = (name, content)

        # Load first document by default
        if first_entry:
            self._show_doc(first_entry[0], first_entry[1])

    def _show_doc(self, name, content):
        """Highlight the selected doc label and load its content."""
        t = current_theme()
        # Reset all labels to default colors
        for lbl in self._doc_labels:
            lbl.configure(bg=t["panel_bg"], fg=t["fg"])
        # Find and highlight the selected label
        for lbl in self._doc_labels:
            if lbl.cget("text").strip() == name:
                lbl.configure(bg=t["accent"], fg=t["accent_fg"])
                self._selected_label = lbl
                break
        # Load content into the text widget
        self._doc_text.configure(state="normal")
        self._doc_text.delete("1.0", "end")
        self._doc_text.insert("1.0", content)
        self._doc_text.configure(state="disabled")
        self._doc_text.yview_moveto(0)

    # ------------------------------------------------------------------
    # Tab 2: Settings Cheat Sheet
    # ------------------------------------------------------------------

    def _build_settings_tab(self, nb, t):
        """Build the Settings cheat sheet with every tunable parameter explained."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Settings")

        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"],
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("setting", font=("Consolas", 10, "bold"),
                           foreground=t["green"])
        text.tag_configure("note", foreground=t["orange"])

        text.insert("end", "RETRIEVAL SETTINGS\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        for name, default, rng, what, notes in _RETRIEVAL_SETTINGS:
            text.insert("end", "\n{}\n".format(name), "setting")
            text.insert("end", "  Default: {}   Range: {}\n".format(default, rng))
            text.insert("end", "  {}\n".format(what))
            text.insert("end", "  {}\n".format(notes), "note")

        text.insert("end", "\n\nLLM SETTINGS\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        for name, default, rng, what, notes in _LLM_SETTINGS:
            text.insert("end", "\n{}\n".format(name), "setting")
            text.insert("end", "  Default: {}   Range: {}\n".format(default, rng))
            text.insert("end", "  {}\n".format(what))
            text.insert("end", "  {}\n".format(notes), "note")

        text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Tab 3: Profiles & Model Ranking
    # ------------------------------------------------------------------

    def _build_profiles_tab(self, nb, t):
        """Build the Profiles tab with model assignment tables and banned list."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Profiles")

        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"],
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("header", font=("Consolas", 10, "bold"),
                           foreground=t["accent"])

        text.insert("end", "PROFILE ASSIGNMENTS\n", "heading")
        text.insert("end", "-" * 60 + "\n\n")
        text.insert("end",
                     "{:<8} {:<18} {:<18} {}\n".format(
                         "Profile", "Primary Model", "Alt Model", "Use Case"),
                     "header")
        text.insert("end", "-" * 60 + "\n")
        for prof, primary, alt, use in _PROFILES:
            text.insert("end",
                         "{:<8} {:<18} {:<18} {}\n".format(
                             prof, primary, alt, use))

        text.insert("end", "\n\nAPPROVED MODEL RANKING\n", "heading")
        text.insert("end", "-" * 60 + "\n\n")
        text.insert("end",
                     "{:<20} {:<6} {:<12} {:<16} {:<7} {}\n".format(
                         "Model", "Params", "License", "Origin",
                         "Size", "Notes"),
                     "header")
        text.insert("end", "-" * 80 + "\n")
        for name, params, lic, origin, size, notes in _MODEL_RANKING:
            text.insert("end",
                         "{:<20} {:<6} {:<12} {:<16} {:<7} {}\n".format(
                             name, params, lic, origin, size, notes))

        text.insert("end", "\n\nBANNED MODELS (do not use)\n", "heading")
        text.insert("end", "-" * 60 + "\n")
        text.insert("end", "  Qwen / Alibaba     -- China origin (NDAA)\n")
        text.insert("end", "  DeepSeek           -- China origin (NDAA)\n")
        text.insert("end", "  BGE / BAAI          -- China origin (NDAA)\n")
        text.insert("end", "  Llama / Meta        -- ITAR ban\n")

        text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Tab 4: Tuning Log
    # ------------------------------------------------------------------

    def _build_tuning_tab(self, nb, t):
        """Build the Tuning tab showing optimization history and critical findings."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Tuning")

        text = tk.Text(
            frame, font=FONT_MONO, bg=t["panel_bg"], fg=t["fg"],
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=t["fg"],
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        text.tag_configure("heading", font=("Segoe UI", 13, "bold"),
                           foreground=t["accent"])
        text.tag_configure("warn", foreground=t["red"],
                           font=("Consolas", 10, "bold"))

        for line in _TUNING_LOG.split("\n"):
            if line.startswith("CRITICAL") or line.startswith("  - NEVER"):
                text.insert("end", line + "\n", "warn")
            elif line.startswith("SESSION") or line.startswith("PROMPT") \
                    or line.startswith("SCORING") or line.startswith("INJECTION"):
                text.insert("end", line + "\n", "heading")
            else:
                text.insert("end", line + "\n")

        text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Tab 5: Sticky Notes
    # ------------------------------------------------------------------

    def _build_notes_tab(self, nb, t):
        """Build the Notes tab -- an editable scratch pad that saves to disk."""
        frame = tk.Frame(nb, bg=t["bg"])
        nb.add(frame, text="Notes")

        toolbar = tk.Frame(frame, bg=t["bg"])
        toolbar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(
            toolbar, text="Quick notes (saved automatically)",
            font=FONT_SMALL, bg=t["bg"], fg=t["label_fg"],
        ).pack(side="left")

        purge_btn = tk.Button(
            toolbar, text="Purge All", font=FONT_SMALL,
            bg=t["red"], fg="#ffffff", relief="flat",
            bd=0, padx=10, pady=2,
            command=self._purge_notes,
        )
        purge_btn.pack(side="right")
        bind_hover(purge_btn, t["red"])

        save_btn = tk.Button(
            toolbar, text="Save", font=FONT_SMALL,
            bg=t["green"], fg="#ffffff", relief="flat",
            bd=0, padx=10, pady=2,
            command=self._save_notes,
        )
        save_btn.pack(side="right", padx=(0, 8))
        bind_hover(save_btn, t["green"])

        note_bg = "#3d3a2e" if t["name"] == "dark" else "#fffde7"
        note_fg = "#e8e4c9" if t["name"] == "dark" else "#333333"
        self._notes_text = tk.Text(
            frame, font=("Consolas", 11), bg=note_bg, fg=note_fg,
            wrap="word", relief="flat", bd=0, padx=12, pady=8,
            insertbackground=note_fg,
        )
        self._notes_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._load_notes()

    def _load_notes(self):
        """Load previously saved notes from disk into the text widget."""
        try:
            if os.path.isfile(self._notes_path):
                with open(self._notes_path, "r", encoding="utf-8") as f:
                    self._notes_text.insert("1.0", f.read())
        except Exception as e:
            logger.debug("Could not load sticky notes: %s", e)

    def _save_notes(self):
        """Save the current notes text to config/sticky_notes.txt."""
        try:
            content = self._notes_text.get("1.0", "end-1c")
            os.makedirs(os.path.dirname(self._notes_path), exist_ok=True)
            with open(self._notes_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _purge_notes(self):
        """Delete all notes (with confirmation) and remove the file from disk."""
        if messagebox.askyesno("Purge Notes",
                               "Delete all sticky notes?"):
            self._notes_text.delete("1.0", "end")
            try:
                if os.path.isfile(self._notes_path):
                    os.remove(self._notes_path)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, t):
        """Re-apply theme colors to the reference panel."""
        self.configure(bg=t["bg"])
        style = ttk.Style()
        style.configure("Ref.TNotebook", background=t["bg"])
        style.configure("Ref.TNotebook.Tab", font=FONT, padding=(12, 4))

        # Update doc viewer widgets
        if self._doc_sidebar is not None:
            self._doc_sidebar.configure(bg=t["panel_bg"])
        if self._doc_text is not None:
            self._doc_text.configure(
                bg=t["panel_bg"], fg=t["fg"],
                insertbackground=t["fg"],
            )
        if self._doc_viewer_frame is not None:
            self._doc_viewer_frame.configure(bg=t["bg"])
        for lbl in self._doc_labels:
            if lbl is self._selected_label:
                lbl.configure(bg=t["accent"], fg=t["accent_fg"])
            else:
                lbl.configure(bg=t["panel_bg"], fg=t["fg"])
