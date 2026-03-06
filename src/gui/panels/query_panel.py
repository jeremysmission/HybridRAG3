# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the query panel part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- Query Panel (src/gui/panels/query_panel.py)
# ============================================================================
# WHAT: The main search interface -- type a question, get an answer.
# WHY:  This is the primary user-facing panel.  Everything else in the
#       GUI exists to support this: settings tune the retrieval, the
#       cost dashboard tracks spending, and the index panel populates
#       the database that this panel searches.
# HOW:  User selects a use case, types a question, clicks Ask.  The
#       query runs in a background thread (so the GUI stays responsive).
#       Streaming responses appear token-by-token in real time.  A
#       vector field animation plays during the wait to reduce perceived
#       latency (research: animated feedback makes waits feel shorter).
# USAGE: Always visible as the default view when the app launches.
#
# QUERY LIFECYCLE (state transitions):
#   1. IDLE       -- Ask button enabled, answer area shows previous result
#   2. SEARCHING  -- Ask disabled, overlay plays, "Searching documents..."
#   3. GENERATING -- overlay stops, tokens stream into answer area
#   4. COMPLETE   -- sources/metrics displayed, cost event emitted, Ask re-enabled
#   5. ERROR      -- red error text in answer area, Ask re-enabled
#
# INTERNET ACCESS: Online mode sends query to API via QueryEngine.
#   Shows "Sending to API..." indicator during online queries.
# ============================================================================

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import logging

from scripts._model_meta import (
    USE_CASES, select_best_model, RECOMMENDED_OFFLINE, WORK_ONLY_MODELS,
    use_case_score,
)
from src.core.llm_router import get_available_deployments
from src.core.model_identity import canonicalize_model_name
from src.core.cost_tracker import get_cost_tracker
from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.helpers.safe_after import safe_after
from src.gui.helpers.mode_tuning import ModeTuningStore
from src.gui.panels.loading_overlay import VectorFieldOverlay
from src.gui.panels.query_constants import (
    ONLINE_USE_CASE_TUNING,
    PROFILE_DIAL_DEFAULTS,
    GROUNDING_BIAS_HINTS,
    OPEN_KNOWLEDGE_HINTS,
    PROFILE_TASK_PLAYBOOK,
)
from src.gui.panels.query_panel_runtime import bind_query_panel_runtime_methods

logger = logging.getLogger(__name__)


class QueryPanel(tk.LabelFrame):
    """
    Query input and answer display panel.

    Shows use case dropdown, auto-selected model, question entry,
    answer area with sources and latency metrics.
    """

    def __init__(self, parent, config, query_engine=None):
        """Create the query panel.

        Args:
            parent: Parent tk widget.
            config: Live config object (mode, model names, retrieval params).
            query_engine: QueryEngine instance. None at startup -- set later
                          by launch_gui._load_backends() once the heavy
                          imports finish.
        """
        t = current_theme()
        super().__init__(parent, text="Query Panel", padx=16, pady=16,
                         bg=t["panel_bg"], fg=t["accent"],
                         font=FONT_BOLD)
        self.config = config
        self.query_engine = query_engine
        self._query_thread = None       # handle to the background query thread
        self._streaming = False          # True while tokens are being appended
        self._stream_start = 0.0         # time.time() when the query started
        self._elapsed_timer_id = None    # after() id for the elapsed time display
        self._model_auto = True          # True = recommendation picks model
        self._installed_models = []      # names from `ollama list`
        self._online_models = []         # discovered API deployments/models
        self._auto_fallback_note = ""    # user-visible primary/secondary note
        self._auto_fallback_active = False
        self._auto_selected_model = ""
        self._auto_primary_model = ""
        self._last_mem_popup_ts = 0.0
        self._query_seq = 0
        self._active_query_id = 0
        self._cancelled_query_ids = set()
        self._query_cancel_event = threading.Event()
        self._mode_tuning_store = ModeTuningStore()
        self._grounding_bias_var = tk.IntVar(value=6)
        self._grounding_bias_hint = tk.StringVar(value=GROUNDING_BIAS_HINTS[6])
        self._open_knowledge_var = tk.BooleanVar(value=True)
        self._open_knowledge_hint = tk.StringVar(value=OPEN_KNOWLEDGE_HINTS[True])

        # Public testing state -- poll these from harness/tools.
        # Event is the thread-safe completion signal; plain attrs are
        # convenience for assertions after the event fires.
        self.query_done_event = threading.Event()
        self.is_querying = False
        self.last_answer_preview = ""
        self.last_query_status = ""

        self._build_widgets(t)

        # Fetch installed Ollama models in background, then apply initial
        # use-case selection.  This avoids blocking the GUI on subprocess.
        self.after(100, self._init_model_list)

    def _build_widgets(self, t):
        """Build all child widgets with theme colors."""
        # -- Row 0: Use case selector --
        row0 = tk.Frame(self, bg=t["panel_bg"])
        row0.pack(fill=tk.X, pady=(0, 8))

        self.uc_label = tk.Label(row0, text="Use case:", bg=t["panel_bg"],
                                 fg=t["fg"], font=FONT)
        self.uc_label.pack(side=tk.LEFT)

        self._uc_keys = list(USE_CASES.keys())
        self._uc_labels = [USE_CASES[k]["label"] for k in self._uc_keys]
        self.uc_var = tk.StringVar(value=self._uc_labels[1])

        self.uc_dropdown = ttk.Combobox(
            row0, textvariable=self.uc_var, values=self._uc_labels,
            state="readonly", width=30, font=FONT,
        )
        self.uc_dropdown.pack(side=tk.LEFT, padx=(8, 0))
        self.uc_dropdown.bind("<<ComboboxSelected>>", self._on_use_case_change)

        self.uc_apply_btn = tk.Button(
            row0, text="Apply", command=self._on_use_case_change, width=6,
            font=FONT, bg=t["accent"], fg="white", relief=tk.FLAT,
        )
        self.uc_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.uc_status_var = tk.StringVar(value="")
        self.uc_status_label = tk.Label(
            row0, textvariable=self.uc_status_var, bg=t["panel_bg"],
            fg=t["green"], font=FONT,
        )
        self.uc_status_label.pack(side=tk.LEFT, padx=(8, 0))

        # Persistent operator-facing warning for degraded auto routing.
        self.primary_alert_row = tk.Frame(self, bg=t["panel_bg"])
        self.primary_alert_row.pack(fill=tk.X, pady=(0, 8))
        self.primary_alert_var = tk.StringVar(value="")
        self.primary_alert_label = tk.Label(
            self.primary_alert_row,
            textvariable=self.primary_alert_var,
            bg=t["panel_bg"],
            fg=t["red"],
            font=FONT_BOLD,
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.primary_alert_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.primary_check_var = tk.StringVar(value="")
        self.primary_check_label = tk.Label(
            self.primary_alert_row,
            textvariable=self.primary_check_var,
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT,
            anchor=tk.W,
        )
        self.primary_check_label.pack(side=tk.LEFT, padx=(8, 0))

        self.primary_check_btn = tk.Button(
            self.primary_alert_row,
            text="Check Primary & Switch",
            command=self._on_check_primary,
            width=22,
            font=FONT,
            bg=t["inactive_btn_bg"],
            fg=t["inactive_btn_fg"],
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.primary_check_btn.pack(side=tk.RIGHT)

        # -- Row 1: Model selector (Auto + installed Ollama models) --
        row1 = tk.Frame(self, bg=t["panel_bg"])
        row1.pack(fill=tk.X, pady=(0, 8))

        self.model_text_label = tk.Label(row1, text="Model:", bg=t["panel_bg"],
                                         fg=t["fg"], font=FONT)
        self.model_text_label.pack(side=tk.LEFT)

        self.model_var = tk.StringVar(value="Auto")
        self.model_combo = ttk.Combobox(
            row1, textvariable=self.model_var, values=["Auto"],
            state="readonly", width=22, font=FONT,
        )
        self.model_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_select)

        # Score/info label beside the dropdown
        self.model_info_var = tk.StringVar(value="")
        self.model_info_label = tk.Label(
            row1, textvariable=self.model_info_var, anchor=tk.W,
            fg=t["accent"], bg=t["panel_bg"], padx=8, font=FONT,
        )
        self.model_info_label.pack(side=tk.LEFT, fill=tk.X)

        # -- Row 1b: Grounding strictness control --
        row1b = tk.Frame(self, bg=t["panel_bg"])
        row1b.pack(fill=tk.X, pady=(0, 8))

        self.grounding_label = tk.Label(
            row1b, text="Grounding Strictness (0-10):", bg=t["panel_bg"],
            fg=t["fg"], font=FONT,
        )
        self.grounding_label.pack(side=tk.LEFT)

        self.grounding_scale = tk.Scale(
            row1b, from_=0, to=10, orient=tk.HORIZONTAL,
            variable=self._grounding_bias_var, showvalue=True,
            resolution=1, length=220, bg=t["panel_bg"], fg=t["fg"],
            highlightthickness=0, troughcolor=t["input_bg"],
            activebackground=t["accent"], command=self._on_grounding_bias_change,
        )
        self.grounding_scale.pack(side=tk.LEFT, padx=(8, 8))

        self.grounding_hint_label = tk.Label(
            row1b, textvariable=self._grounding_bias_hint,
            bg=t["panel_bg"], fg=t["gray"], font=FONT,
            anchor=tk.W,
        )
        self.grounding_hint_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row1c = tk.Frame(self, bg=t["panel_bg"])
        row1c.pack(fill=tk.X, pady=(0, 8))

        self.open_knowledge_label = tk.Label(
            row1c, text="Open-Knowledge Fallback:", bg=t["panel_bg"],
            fg=t["fg"], font=FONT,
        )
        self.open_knowledge_label.pack(side=tk.LEFT)

        self.open_knowledge_check = tk.Checkbutton(
            row1c, text="Enabled", variable=self._open_knowledge_var,
            command=self._on_open_knowledge_toggle,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"],
        )
        self.open_knowledge_check.pack(side=tk.LEFT, padx=(8, 8))

        self.open_knowledge_hint_label = tk.Label(
            row1c, textvariable=self._open_knowledge_hint,
            bg=t["panel_bg"], fg=t["gray"], font=FONT,
            anchor=tk.W,
        )
        self.open_knowledge_hint_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Row 1d: Profile playbook (top tasks + grounding suggestions) --
        self.playbook_label = tk.Label(
            self,
            text="",
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=1200,
            bg=t["panel_bg"],
            fg=t["gray"],
            font=FONT_SMALL,
        )
        self.playbook_label.pack(fill=tk.X, pady=(0, 8))

        # -- Query/Answer split: compact controls on top, large resizable answer area --
        io_pane = tk.PanedWindow(
            self, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED,
            bg=t["panel_bg"], bd=0, relief=tk.FLAT,
        )
        io_pane.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        q_frame = tk.Frame(io_pane, bg=t["panel_bg"])
        a_frame = tk.Frame(io_pane, bg=t["panel_bg"])
        io_pane.add(q_frame, minsize=52, stretch="always")
        io_pane.add(a_frame, minsize=120, stretch="always")

        # -- Row 2: Question + Ask --
        self.question_label = tk.Label(
            q_frame, text="Question:", bg=t["panel_bg"],
            fg=t["fg"], font=FONT, anchor=tk.W,
        )
        self.question_label.pack(fill=tk.X, pady=(0, 4))

        row2 = tk.Frame(q_frame, bg=t["panel_bg"])
        row2.pack(fill=tk.X, pady=(0, 6))

        self.question_entry = tk.Entry(
            row2, font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2,
        )
        self.question_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.question_entry.insert(0, "Type your question here...")
        self.question_entry.bind("<FocusIn>", self._on_entry_focus)
        self.question_entry.bind("<Return>", self._on_ask)
        self.question_entry.bind("<Escape>", self._on_stop_query)

        self.ask_btn = tk.Button(
            row2, text="Ask", command=self._on_ask, width=10,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT_BOLD, relief=tk.FLAT, bd=0,
            padx=24, pady=8, state=tk.DISABLED,
            activebackground=t["accent_hover"],
            activeforeground=t["accent_fg"],
        )
        self.ask_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.stop_btn = tk.Button(
            row2, text="Stop", command=self._on_stop_query, width=10,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT_BOLD, relief=tk.FLAT, bd=0,
            padx=24, pady=8, state=tk.DISABLED,
            activebackground=t["accent_hover"],
            activeforeground=t["accent_fg"],
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        # -- Network activity indicator --
        self.network_label = tk.Label(
            q_frame, text="", fg=t["gray"], anchor=tk.W,
            bg=t["panel_bg"], font=FONT,
        )
        self.network_label.pack(fill=tk.X)

        # -- Answer area (scrollable, selectable) --
        text_panel = tk.Frame(a_frame, bg=t["panel_bg"])
        text_panel.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        scrollbar = tk.Scrollbar(text_panel, orient=tk.VERTICAL)
        self.answer_text = tk.Text(
            text_panel, height=16, wrap=tk.WORD, state=tk.DISABLED,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=1,
            selectbackground=t["accent"],
            selectforeground=t["accent_fg"],
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.answer_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.answer_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # -- Sources line (wraps when wider than panel) --
        self.sources_label = tk.Label(
            a_frame, text="Sources: (none)", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT, justify=tk.LEFT, wraplength=1,
        )
        self.sources_label.pack(fill=tk.X, pady=(8, 0))
        self.sources_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(1, e.width - 4)),
        )

        # -- Metrics line (monospace for aligned numbers, wraps if needed) --
        self.metrics_label = tk.Label(
            a_frame, text="", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT_MONO, justify=tk.LEFT, wraplength=1,
        )
        self.metrics_label.pack(fill=tk.X)
        self.metrics_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(1, e.width - 4)),
        )

        # -- Vector field overlay (animated, hidden until query starts) --
        self._overlay = VectorFieldOverlay(self.answer_text, theme=t)

    def apply_theme(self, t):
        """Re-apply theme colors to all widgets."""
        self.configure(bg=t["panel_bg"], fg=t["accent"])

        def _theme_walk(widget):
            """Plain-English: Walks nested widgets and reapplies theme colors to each supported control."""
            for child in widget.winfo_children():
                if isinstance(child, (tk.Frame, tk.PanedWindow, tk.LabelFrame)):
                    try:
                        child.configure(bg=t["panel_bg"])
                    except Exception:
                        pass
                    _theme_walk(child)
                    continue
                # Skip ttk widgets -- they don't support -bg/-fg
                if isinstance(child, (ttk.Combobox, ttk.Widget)):
                    continue
                if isinstance(child, tk.Label):
                    child.configure(bg=t["panel_bg"], fg=t["fg"])
                elif isinstance(child, tk.Checkbutton):
                    child.configure(
                        bg=t["panel_bg"], fg=t["fg"],
                        selectcolor=t["input_bg"],
                        activebackground=t["panel_bg"],
                        activeforeground=t["fg"],
                    )
                elif isinstance(child, tk.Scale):
                    child.configure(
                        bg=t["panel_bg"], fg=t["fg"],
                        troughcolor=t["input_bg"],
                        activebackground=t["accent"],
                    )
                elif isinstance(child, tk.Entry):
                    child.configure(bg=t["input_bg"], fg=t["input_fg"],
                                    insertbackground=t["fg"])
                elif isinstance(child, tk.Button):
                    if str(child.cget("state")) == "disabled":
                        child.configure(bg=t["inactive_btn_bg"],
                                        fg=t["inactive_btn_fg"])
                    else:
                        child.configure(bg=t["accent"], fg=t["accent_fg"],
                                        activebackground=t["accent_hover"])

        _theme_walk(self)

        self.model_info_label.configure(fg=t["accent"], bg=t["panel_bg"])
        self.question_label.configure(bg=t["panel_bg"], fg=t["fg"])
        self.network_label.configure(bg=t["panel_bg"], fg=t["gray"])
        self.answer_text.configure(bg=t["input_bg"], fg=t["input_fg"],
                                   insertbackground=t["fg"],
                                   selectbackground=t["accent"])
        self.sources_label.configure(bg=t["panel_bg"])
        self.metrics_label.configure(bg=t["panel_bg"])
        self.primary_alert_row.configure(bg=t["panel_bg"])
        self.primary_alert_label.configure(bg=t["panel_bg"])
        self.primary_check_label.configure(bg=t["panel_bg"], fg=t["gray"])
        # Preserve gray/colored state of sources/metrics
        if "none" in self.sources_label.cget("text"):
            self.sources_label.configure(fg=t["gray"])
        else:
            self.sources_label.configure(fg=t["fg"])

        # Overlay
        self._overlay.apply_theme(t)

    def _on_entry_focus(self, event=None):
        """Clear placeholder text on first focus."""
        if self.question_entry.get() == "Type your question here...":
            self.question_entry.delete(0, tk.END)

    # ----------------------------------------------------------------
    # MODEL LIST + SELECTION
    # ----------------------------------------------------------------

    _EMBED_MODELS = {"nomic-embed-text", "all-minilm", "mxbai-embed"}


# Bind extracted runtime/model/query methods onto QueryPanel.
bind_query_panel_runtime_methods(QueryPanel)
