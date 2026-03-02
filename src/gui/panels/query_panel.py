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
from tkinter import ttk, scrolledtext
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
from src.gui.panels.loading_overlay import VectorFieldOverlay

logger = logging.getLogger(__name__)

# Per-use-case ONLINE tuning presets. These are applied when the user
# changes profession/use-case in online mode so model + retrieval settings
# move together as a bundle.
ONLINE_USE_CASE_TUNING = {
    "sw":    {"temperature": 0.10, "max_tokens": 2048, "timeout_seconds": 90,  "top_k": 8,  "min_score": 0.08},
    "eng":   {"temperature": 0.08, "max_tokens": 2048, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "sys":   {"temperature": 0.08, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 9,  "min_score": 0.08},
    "draft": {"temperature": 0.05, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "log":   {"temperature": 0.05, "max_tokens": 1536, "timeout_seconds": 90,  "top_k": 12, "min_score": 0.06},
    "pm":    {"temperature": 0.20, "max_tokens": 2048, "timeout_seconds": 120, "top_k": 8,  "min_score": 0.06},
    "fe":    {"temperature": 0.10, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 10, "min_score": 0.08},
    "cyber": {"temperature": 0.08, "max_tokens": 1792, "timeout_seconds": 90,  "top_k": 9,  "min_score": 0.08},
    "gen":   {"temperature": 0.30, "max_tokens": 2048, "timeout_seconds": 120, "top_k": 6,  "min_score": 0.05},
}

# Safe development defaults for independent dial controls.
# Values are intentionally conservative for demo reliability.
PROFILE_DIAL_DEFAULTS = {
    "offline": {
        "sw":    {"grounding": 8, "reasoning": 2},
        "eng":   {"grounding": 8, "reasoning": 2},
        "sys":   {"grounding": 8, "reasoning": 2},
        "draft": {"grounding": 7, "reasoning": 3},
        "log":   {"grounding": 8, "reasoning": 2},
        "pm":    {"grounding": 7, "reasoning": 3},
        "fe":    {"grounding": 8, "reasoning": 2},
        "cyber": {"grounding": 9, "reasoning": 1},
        "gen":   {"grounding": 6, "reasoning": 4},
    },
    "online": {
        "sw":    {"grounding": 7, "reasoning": 5},
        "eng":   {"grounding": 7, "reasoning": 5},
        "sys":   {"grounding": 8, "reasoning": 4},
        "draft": {"grounding": 7, "reasoning": 5},
        "log":   {"grounding": 7, "reasoning": 5},
        "pm":    {"grounding": 6, "reasoning": 6},
        "fe":    {"grounding": 7, "reasoning": 5},
        "cyber": {"grounding": 9, "reasoning": 3},
        "gen":   {"grounding": 5, "reasoning": 7},
    },
}

# Development grounding-bias scale (1..10).
# 1 = max synthesis freedom, 10 = strict source lock.
GROUNDING_BIAS_HINTS = {
    0: "Grounding 0/10 - OFF",
    1: "Grounding 1/10 - Generative (guard OFF, dev only)",
    2: "Grounding 2/10 - Very relaxed",
    3: "Grounding 3/10 - Relaxed",
    4: "Grounding 4/10 - Moderate relaxed",
    5: "Grounding 5/10 - Balanced",
    6: "Grounding 6/10 - Balanced+",
    7: "Grounding 7/10 - Strong grounding",
    8: "Grounding 8/10 - Strict",
    9: "Grounding 9/10 - Very strict",
    10: "Grounding 10/10 - Evidence locked",
}
REASONING_DIAL_HINTS = {
    0: "Reasoning 0/10 - OFF (context-only)",
    1: "Reasoning 1/10 - Minimal",
    2: "Reasoning 2/10 - Very low",
    3: "Reasoning 3/10 - Low",
    4: "Reasoning 4/10 - Light",
    5: "Reasoning 5/10 - Balanced",
    6: "Reasoning 6/10 - Moderate",
    7: "Reasoning 7/10 - Strong",
    8: "Reasoning 8/10 - High",
    9: "Reasoning 9/10 - Very high",
    10: "Reasoning 10/10 - Max",
}

PROFILE_TASK_PLAYBOOK = {
    "log": [
        "1) Reconcile received vs required parts -- Grounding 8 / Reasoning 4",
        "2) Build shortage report by part number -- Grounding 9 / Reasoning 3",
        "3) Cross-check procurement status across files -- Grounding 7 / Reasoning 6",
        "4) Extract lead times and vendor constraints -- Grounding 8 / Reasoning 4",
        "5) Generate weekly logistics summary -- Grounding 6 / Reasoning 7",
    ],
    "pm": [
        "1) Build status report from multiple documents -- Grounding 6 / Reasoning 7",
        "2) Summarize risks, owners, due dates -- Grounding 7 / Reasoning 6",
        "3) Draft executive one-pager -- Grounding 5 / Reasoning 8",
        "4) Compare baseline vs current milestones -- Grounding 7 / Reasoning 6",
        "5) Create action-item register -- Grounding 6 / Reasoning 7",
    ],
    "eng": [
        "1) Extract specs/tolerances/part numbers -- Grounding 9 / Reasoning 2",
        "2) Compare interfaces across drawings/manuals -- Grounding 8 / Reasoning 5",
        "3) Generate subsystem technical summary -- Grounding 7 / Reasoning 6",
        "4) Identify conflicts between revisions -- Grounding 8 / Reasoning 5",
        "5) Produce test readiness checklist -- Grounding 7 / Reasoning 6",
    ],
    "draft": [
        "1) Extract dimensions/callouts from docs -- Grounding 9 / Reasoning 2",
        "2) Build drawing package index -- Grounding 8 / Reasoning 4",
        "3) Cross-reference drawing to BOM entries -- Grounding 8 / Reasoning 5",
        "4) Generate revision-impact notes -- Grounding 7 / Reasoning 6",
        "5) Produce release checklist -- Grounding 7 / Reasoning 6",
    ],
    "sys": [
        "1) Extract configuration values exactly -- Grounding 9 / Reasoning 2",
        "2) Build troubleshooting decision tree -- Grounding 7 / Reasoning 6",
        "3) Compare system states across docs -- Grounding 8 / Reasoning 5",
        "4) Draft change-implementation steps -- Grounding 7 / Reasoning 6",
        "5) Summarize operational constraints -- Grounding 8 / Reasoning 4",
    ],
    "cyber": [
        "1) Extract controls/findings exactly -- Grounding 10 / Reasoning 1",
        "2) Map findings to mitigations -- Grounding 8 / Reasoning 5",
        "3) Generate incident summary report -- Grounding 7 / Reasoning 6",
        "4) Compare policy vs implementation docs -- Grounding 8 / Reasoning 5",
        "5) Build audit evidence checklist -- Grounding 9 / Reasoning 3",
    ],
    "fe": [
        "1) Extract field procedures and limits -- Grounding 9 / Reasoning 2",
        "2) Build troubleshooting flow from manuals -- Grounding 7 / Reasoning 6",
        "3) Cross-link parts to installation steps -- Grounding 8 / Reasoning 5",
        "4) Generate shift handoff summary -- Grounding 6 / Reasoning 7",
        "5) Create field readiness checklist -- Grounding 7 / Reasoning 6",
    ],
    "sw": [
        "1) Extract exact API/config requirements -- Grounding 9 / Reasoning 2",
        "2) Summarize architecture from docs -- Grounding 7 / Reasoning 6",
        "3) Generate implementation plan -- Grounding 6 / Reasoning 7",
        "4) Build dependency/risk report -- Grounding 7 / Reasoning 6",
        "5) Draft test strategy summary -- Grounding 6 / Reasoning 7",
    ],
    "gen": [
        "1) Quick doc summary -- Grounding 5 / Reasoning 7",
        "2) Cross-doc synthesis answer -- Grounding 5 / Reasoning 8",
        "3) Report draft from mixed sources -- Grounding 4 / Reasoning 8",
        "4) Block diagram text from context -- Grounding 4 / Reasoning 9",
        "5) Executive brief + action items -- Grounding 5 / Reasoning 8",
    ],
}


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
        self._grounding_bias_var = tk.IntVar(value=6)
        self._grounding_bias_hint = tk.StringVar(value=GROUNDING_BIAS_HINTS[6])
        self._reasoning_dial_var = tk.IntVar(value=5)
        self._reasoning_dial_hint = tk.StringVar(value=REASONING_DIAL_HINTS[5])

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

        # -- Row 1b: Grounding bias (development control) --
        row1b = tk.Frame(self, bg=t["panel_bg"])
        row1b.pack(fill=tk.X, pady=(0, 8))

        self.grounding_label = tk.Label(
            row1b, text="Grounding Dial (0-10):", bg=t["panel_bg"],
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

        self.reasoning_label = tk.Label(
            row1c, text="Reasoning Dial (0-10):", bg=t["panel_bg"],
            fg=t["fg"], font=FONT,
        )
        self.reasoning_label.pack(side=tk.LEFT)

        self.reasoning_scale = tk.Scale(
            row1c, from_=0, to=10, orient=tk.HORIZONTAL,
            variable=self._reasoning_dial_var, showvalue=True,
            resolution=1, length=220, bg=t["panel_bg"], fg=t["fg"],
            highlightthickness=0, troughcolor=t["input_bg"],
            activebackground=t["accent"], command=self._on_reasoning_dial_change,
        )
        self.reasoning_scale.pack(side=tk.LEFT, padx=(8, 8))

        self.reasoning_hint_label = tk.Label(
            row1c, textvariable=self._reasoning_dial_hint,
            bg=t["panel_bg"], fg=t["gray"], font=FONT,
            anchor=tk.W,
        )
        self.reasoning_hint_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Row 1d: Profile playbook (top tasks + dial suggestions) --
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

        # -- Row 2: Question label + entry + Ask button --
        self.question_label = tk.Label(
            self, text="Question:", bg=t["panel_bg"],
            fg=t["fg"], font=FONT, anchor=tk.W,
        )
        self.question_label.pack(fill=tk.X, pady=(0, 4))

        row2 = tk.Frame(self, bg=t["panel_bg"])
        row2.pack(fill=tk.X, pady=(0, 8))

        self.question_entry = tk.Entry(
            row2, font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=2,
        )
        self.question_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.question_entry.insert(0, "Type your question here...")
        self.question_entry.bind("<FocusIn>", self._on_entry_focus)
        self.question_entry.bind("<Return>", self._on_ask)

        self.ask_btn = tk.Button(
            row2, text="Ask", command=self._on_ask, width=10,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
            font=FONT_BOLD, relief=tk.FLAT, bd=0,
            padx=24, pady=8, state=tk.DISABLED,
            activebackground=t["accent_hover"],
            activeforeground=t["accent_fg"],
        )
        self.ask_btn.pack(side=tk.LEFT, padx=(8, 0))

        # -- Network activity indicator --
        self.network_label = tk.Label(
            self, text="", fg=t["gray"], anchor=tk.W,
            bg=t["panel_bg"], font=FONT,
        )
        self.network_label.pack(fill=tk.X)

        # -- Answer area (scrollable, selectable) --
        self.answer_text = scrolledtext.ScrolledText(
            self, height=10, wrap=tk.WORD, state=tk.DISABLED,
            font=FONT, bg=t["input_bg"], fg=t["input_fg"],
            insertbackground=t["fg"], relief=tk.FLAT, bd=1,
            selectbackground=t["accent"],
            selectforeground=t["accent_fg"],
        )
        self.answer_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # -- Sources line (wraps when wider than panel) --
        self.sources_label = tk.Label(
            self, text="Sources: (none)", anchor=tk.W, fg=t["gray"],
            bg=t["panel_bg"], font=FONT, justify=tk.LEFT, wraplength=1,
        )
        self.sources_label.pack(fill=tk.X, pady=(8, 0))
        self.sources_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(1, e.width - 4)),
        )

        # -- Metrics line (monospace for aligned numbers, wraps if needed) --
        self.metrics_label = tk.Label(
            self, text="", anchor=tk.W, fg=t["gray"],
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

        for row in self.winfo_children():
            if isinstance(row, tk.Frame):
                row.configure(bg=t["panel_bg"])
                for child in row.winfo_children():
                    # Skip ttk widgets -- they don't support -bg/-fg
                    if isinstance(child, (ttk.Combobox, ttk.Widget)):
                        continue
                    if isinstance(child, tk.Label):
                        child.configure(bg=t["panel_bg"], fg=t["fg"])
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

    def _init_model_list(self):
        """Fetch installed Ollama models in background, then apply defaults."""
        threading.Thread(
            target=self._fetch_installed_models, daemon=True,
        ).start()

    def _fetch_installed_models(self):
        """Background: get installed Ollama model names (excludes embedders)."""
        try:
            from scripts._model_meta import get_offline_models_with_specs
            models = get_offline_models_with_specs()
            names = []
            for m in models:
                name = m["name"]
                # Skip embedding-only models
                skip = False
                for pat in self._EMBED_MODELS:
                    if pat in name.lower():
                        skip = True
                        break
                if not skip:
                    names.append(name)
            safe_after(self, 0, self._apply_model_list, names)
        except Exception as e:
            logger.debug("Model list fetch failed: %s", e)
            safe_after(self, 0, self._on_use_case_change)

    def _apply_model_list(self, names):
        """Set combobox values and trigger initial model selection."""
        self._installed_models = names
        self._set_model_combo_for_mode()

        # If config already has a model that isn't the recommendation
        # default, pre-select it (user's persisted choice).
        # Names are already canonical (no ':latest' suffixes).
        cfg_model = getattr(
            getattr(self.config, "ollama", None), "model", ""
        ) or ""
        uc_key = self._uc_keys[0]
        rec_primary = RECOMMENDED_OFFLINE.get(uc_key, {}).get("primary", "")
        if cfg_model and cfg_model != rec_primary and cfg_model in names:
            self.model_var.set(cfg_model)
            self._model_auto = False

        self._on_use_case_change()

    def _set_model_combo_for_mode(self):
        """Keep model combobox semantics aligned with offline/online mode."""
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            # Online model comes from API deployment selection, not Ollama list.
            deployment = self._get_configured_online_deployment()
            if not deployment:
                deployment = "Auto (online)"
            label = f"Online: {deployment}"
            if self._online_models:
                vals = [f"Online: {m}" for m in self._online_models]
                if label not in vals:
                    vals.insert(0, label)
                self.model_combo["values"] = vals
                self.model_var.set(label)
                self.model_combo.config(state="readonly")
            else:
                self.model_combo["values"] = [label]
                self.model_var.set(label)
                self.model_combo.config(state="readonly")
            return

        values = ["Auto"] + self._installed_models
        self.model_combo["values"] = values
        self.model_combo.config(state="readonly")
        if self._model_auto or self.model_var.get() not in values:
            self.model_var.set("Auto")

    def _get_configured_online_deployment(self):
        """Best-effort deployment from live config, then credential manager."""
        deployment = (
            getattr(getattr(self.config, "api", None), "deployment", "") or ""
        ).strip()
        if deployment:
            return deployment
        try:
            from src.security.credentials import resolve_credentials
            creds = resolve_credentials(use_cache=False)
            deployment = (getattr(creds, "deployment", "") or "").strip()
            return deployment
        except Exception:
            return ""

    def _on_model_select(self, event=None):
        """Handle user selecting a model from the dropdown."""
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            chosen = self.model_var.get().replace("Online:", "").strip()
            if not chosen or chosen.lower().startswith("auto"):
                return
            if hasattr(self.config, "api"):
                self.config.api.deployment = chosen
            # Apply to live router if already initialized
            try:
                if self.query_engine and hasattr(self.query_engine, "llm_router"):
                    api_router = getattr(self.query_engine.llm_router, "api", None)
                    if api_router is not None:
                        api_router.deployment = chosen
            except Exception:
                pass
            self.model_info_var.set("{} (manual)".format(chosen))
            return

        chosen = self.model_var.get()
        if chosen == "Auto":
            self._model_auto = True
            self._on_use_case_change()
        else:
            # Manual selection -- lock this model
            self._model_auto = False
            if hasattr(self.config, "ollama"):
                self.config.ollama.model = canonicalize_model_name(chosen)
            self._update_model_info(chosen)

    def _update_model_info(self, model_name):
        """Update the score/info label for the given model."""
        if self._auto_fallback_note:
            self.model_info_var.set(self._auto_fallback_note)
            return

        idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
        uc_key = self._uc_keys[idx]
        mode = getattr(self.config, "mode", "offline")
        mode_label = "Offline Mode" if mode == "offline" else "Online Mode"
        meta = WORK_ONLY_MODELS.get(model_name, {})
        if meta:
            score = use_case_score(
                meta.get("tier_eng", 30), meta.get("tier_gen", 30), uc_key,
            )
            if self._model_auto:
                self.model_info_var.set(
                    "{} | Score: {} | {}".format(model_name, score, mode_label)
                )
            else:
                self.model_info_var.set(
                    "Score: {} | {}".format(score, mode_label)
                )
        else:
            self.model_info_var.set(mode_label)

    def _set_auto_note(self, selected, primary="", fallback=False, detail=""):
        """Set explicit auto-mode primary/secondary status text."""
        selected = (selected or "").strip() or "(none)"
        primary = (primary or "").strip()
        self._auto_selected_model = selected
        self._auto_primary_model = primary
        self._auto_fallback_active = bool(fallback)
        if fallback:
            msg = "Auto Mode - Primary unavailable, Secondary selected: {}".format(
                selected
            )
        else:
            if primary:
                msg = "Auto Mode - Primary selected: {}".format(selected)
            else:
                msg = "Auto Mode - Selected: {}".format(selected)
        if detail:
            msg = "{} ({})".format(msg, detail)
        self._auto_fallback_note = msg
        self.model_info_var.set(msg)
        if fallback:
            self.primary_alert_var.set(
                "Note: Primary AI Model Unavailable - Secondary model in use ({})".format(
                    selected
                )
            )
        else:
            self.primary_alert_var.set("")
        self._update_primary_controls()

    def _set_online_discovery_note(self, selected):
        """Set a neutral online note when deployment discovery is unavailable."""
        selected = (selected or "").strip() or "(none)"
        self._auto_selected_model = selected
        self._auto_primary_model = ""
        self._auto_fallback_active = False
        msg = "Auto Mode - Discovery unavailable, using configured model: {} (online)".format(
            selected
        )
        self._auto_fallback_note = msg
        self.model_info_var.set(msg)
        self.primary_alert_var.set("")
        self._update_primary_controls()

    def _update_primary_controls(self):
        """Enable recovery controls only when fallback mode is active."""
        if self._auto_fallback_active:
            self.primary_check_btn.config(state=tk.NORMAL)
        else:
            self.primary_check_btn.config(state=tk.DISABLED)
            self.primary_check_var.set("")

    def _current_use_case_key(self):
        idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
        return self._uc_keys[idx]

    def _on_check_primary(self):
        """Probe for primary availability and switch if recovered."""
        if not self._auto_fallback_active:
            return
        self.primary_check_btn.config(state=tk.DISABLED)
        self.primary_check_var.set("Checking...")
        threading.Thread(target=self._check_primary_worker, daemon=True).start()

    def _on_grounding_bias_change(self, _value=None):
        """Update hint + live guard tuning when operator adjusts bias."""
        bias = int(self._grounding_bias_var.get())
        self._grounding_bias_hint.set(
            GROUNDING_BIAS_HINTS.get(bias, "Grounding bias updated")
        )
        self._apply_grounding_bias_live(bias)

    def _on_reasoning_dial_change(self, _value=None):
        lvl = int(self._reasoning_dial_var.get())
        self._reasoning_dial_hint.set(
            REASONING_DIAL_HINTS.get(lvl, "Reasoning dial updated")
        )
        self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

    def _apply_grounding_bias_live(self, bias: int):
        """
        Map 1..10 slider into live guard settings.
        Lower bias => more synthesis freedom.
        Higher bias => stricter evidence requirements.
        """
        b = max(0, min(10, int(bias)))
        r = max(0, min(10, int(self._reasoning_dial_var.get())))
        guard_on = b > 0
        threshold = 0.35 + (max(1, b) / 10.0) * 0.55
        min_chunks = 1 if b <= 4 else 2 if b <= 7 else 3
        min_score = 0.00 if b <= 2 else 0.03 if b <= 4 else 0.06 if b <= 7 else 0.10
        action = "flag" if b <= 5 else "block"

        # Config object update (if fields exist)
        try:
            hg = getattr(self.config, "hallucination_guard", None)
            if hg is not None:
                hg.enabled = bool(guard_on)
                hg.threshold = float(round(threshold, 2))
                hg.failure_action = action
            if hasattr(self.config, "retrieval"):
                self.config.retrieval.min_score = max(
                    float(getattr(self.config.retrieval, "min_score", 0.0)),
                    float(min_score),
                )
        except Exception:
            pass

        # Live engine update (works without restart)
        qe = self.query_engine
        if qe is not None:
            try:
                # Independent reasoning dial: 0 disables, >0 enables.
                setattr(qe, "allow_open_knowledge", bool(r > 0))
                setattr(qe, "reasoning_level", int(r))
                if hasattr(qe, "guard_enabled"):
                    qe.guard_enabled = bool(guard_on)
                if hasattr(qe, "guard_threshold"):
                    qe.guard_threshold = float(round(threshold, 2))
                if hasattr(qe, "guard_min_chunks"):
                    qe.guard_min_chunks = int(min_chunks)
                if hasattr(qe, "guard_min_score"):
                    qe.guard_min_score = float(min_score)
                if hasattr(qe, "guard_action"):
                    qe.guard_action = action
            except Exception:
                pass

    def _check_primary_worker(self):
        """Background primary availability check."""
        mode = getattr(self.config, "mode", "offline")
        uc_key = self._current_use_case_key()
        if mode == "offline":
            try:
                from scripts._model_meta import get_offline_models_with_specs
                names = [m["name"] for m in get_offline_models_with_specs()]
            except Exception:
                names = list(self._installed_models)
            rec = RECOMMENDED_OFFLINE.get(uc_key, {})
            primary = (rec.get("primary", "") or "").strip()
            if primary and primary in names and self._model_auto:
                safe_after(self, 0, self._switch_to_primary_offline, primary)
                return
            safe_after(self, 0, self._check_primary_done, False, "Primary still unavailable")
            return

        # Online mode: recompute best from live deployments and switch if better.
        try:
            deployments = get_available_deployments()
            best = select_best_model(uc_key, deployments)
            current = (self._auto_selected_model or "").strip()
            if best and self._model_auto and best != current:
                safe_after(self, 0, self._switch_to_primary_online, best, deployments)
                return
            if best and best == current:
                safe_after(self, 0, self._check_primary_done, True, "Primary already active")
            else:
                safe_after(self, 0, self._check_primary_done, False, "Primary still unavailable")
        except Exception:
            safe_after(self, 0, self._check_primary_done, False, "Primary check failed")

    def _switch_to_primary_offline(self, primary):
        self._installed_models = list(self._installed_models or [])
        if primary not in self._installed_models:
            self._installed_models.append(primary)
        if hasattr(self.config, "ollama"):
            self.config.ollama.model = canonicalize_model_name(primary)
        self._set_auto_note(primary, primary, False, "offline recovered")
        self._set_model_combo_for_mode()
        self._check_primary_done(True, "Primary restored and selected")

    def _switch_to_primary_online(self, primary, deployments):
        self._online_models = list(deployments or [primary])
        self.model_var.set(f"Online: {primary}")
        self._apply_online_selection(primary, False, "online recovered")
        self._set_model_combo_for_mode()
        self._set_auto_note(primary, primary, False, "online recovered")
        self._check_primary_done(True, "Primary restored and selected")

    def _check_primary_done(self, ok, message):
        t = current_theme()
        self.primary_check_var.set(message)
        self.primary_check_label.config(fg=t["green"] if ok else t["orange"])
        self._update_primary_controls()

    # ----------------------------------------------------------------
    # USE CASE CHANGE
    # ----------------------------------------------------------------

    def _apply_use_case_tuning(self, uc_key: str, mode: str) -> None:
        """
        Apply profession-specific tuning bundle, not just model selection.

        Offline: apply RECOMMENDED_OFFLINE tuning knobs.
        Online:  apply ONLINE_USE_CASE_TUNING knobs.
        """
        if not self.config:
            return

        self._apply_profile_dial_defaults(uc_key, mode)

        if mode == "offline":
            rec = RECOMMENDED_OFFLINE.get(uc_key, {})
            if not rec:
                return
            if hasattr(self.config, "ollama"):
                if "context" in rec:
                    self.config.ollama.context_window = rec["context"]
                if "temperature" in rec:
                    self.config.ollama.temperature = rec["temperature"]
            if hasattr(self.config, "retrieval"):
                if "top_k" in rec:
                    self.config.retrieval.top_k = rec["top_k"]
            return

        # Online tuning bundle
        rec = ONLINE_USE_CASE_TUNING.get(uc_key, {})
        if not rec:
            return
        if hasattr(self.config, "api"):
            if "temperature" in rec:
                self.config.api.temperature = rec["temperature"]
            if "max_tokens" in rec:
                self.config.api.max_tokens = rec["max_tokens"]
            if "timeout_seconds" in rec:
                self.config.api.timeout_seconds = rec["timeout_seconds"]
        if hasattr(self.config, "retrieval"):
            if "top_k" in rec:
                self.config.retrieval.top_k = rec["top_k"]
            if "min_score" in rec:
                self.config.retrieval.min_score = rec["min_score"]

    def _apply_profile_dial_defaults(self, uc_key: str, mode: str) -> None:
        """Apply safe per-profile defaults for grounding/reasoning dials."""
        mode_key = "online" if str(mode).lower() == "online" else "offline"
        rec = PROFILE_DIAL_DEFAULTS.get(mode_key, {}).get(
            uc_key, {"grounding": 7, "reasoning": 4}
        )
        try:
            self._grounding_bias_var.set(int(rec.get("grounding", 7)))
            self._reasoning_dial_var.set(int(rec.get("reasoning", 4)))
            self._grounding_bias_hint.set(
                GROUNDING_BIAS_HINTS.get(
                    int(self._grounding_bias_var.get()), "Grounding updated"
                )
            )
            self._reasoning_dial_hint.set(
                REASONING_DIAL_HINTS.get(
                    int(self._reasoning_dial_var.get()), "Reasoning updated"
                )
            )
            self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))
        except Exception:
            pass

    def _on_use_case_change(self, event=None):
        """Update model display when use case changes.

        Offline + Auto: selects per-use-case model from RECOMMENDED_OFFLINE
                        and applies temperature/top_k settings to live config.
        Offline + Manual: keeps user's model, still applies tuning params.
        Online: runs get_available_deployments() in a background thread
                so the GUI never freezes on a network call.
        """
        idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
        uc_key = self._uc_keys[idx]

        mode = getattr(self.config, "mode", "offline")
        self._update_profile_playbook(uc_key)
        self._set_model_combo_for_mode()
        if mode == "offline":
            rec = RECOMMENDED_OFFLINE.get(uc_key, {})
            primary = (rec.get("primary", "") or "").strip()

            if self._model_auto:
                # Auto mode: score ALL installed models for this use case
                # and pick the highest-scoring one.  This ensures the best
                # available hardware is used (e.g., phi4:14b-q4_K_M on 48GB GPU).
                best_model = None
                best_score = -1
                for name in self._installed_models:
                    meta = WORK_ONLY_MODELS.get(name, {})
                    if meta:
                        s = use_case_score(
                            meta.get("tier_eng", 30),
                            meta.get("tier_gen", 30),
                            uc_key,
                        )
                        if s > best_score:
                            best_score = s
                            best_model = name

                if best_model:
                    ollama_model = best_model
                elif not self._installed_models:
                    # Model list not fetched yet -- use config default
                    # (will be re-evaluated when _apply_model_list fires)
                    ollama_model = getattr(
                        getattr(self.config, "ollama", None), "model", ""
                    ) or rec.get("primary", "phi4:14b-q4_K_M")
                else:
                    # Models loaded but none in WORK_ONLY_MODELS -- use
                    # recommendation chain: primary > alt > fallback > config
                    ollama_model = (
                        rec.get("primary", "")
                        or rec.get("alt", "")
                        or rec.get("fallback", "")
                        or getattr(
                            getattr(self.config, "ollama", None), "model", ""
                        )
                        or "phi4:14b-q4_K_M"
                    )

                self.model_var.set("Auto")
                if hasattr(self.config, "ollama"):
                    self.config.ollama.model = canonicalize_model_name(ollama_model)
                fallback = bool(primary) and primary not in self._installed_models and ollama_model != primary
                self._set_auto_note(
                    ollama_model,
                    primary=primary,
                    fallback=fallback,
                    detail="offline",
                )
            else:
                # Manual mode: keep user's chosen model
                ollama_model = self.model_var.get()
                if hasattr(self.config, "ollama"):
                    self.config.ollama.model = canonicalize_model_name(ollama_model)
                self._auto_fallback_note = ""
                self.primary_alert_var.set("")
                self._auto_fallback_active = False
                self._auto_selected_model = ollama_model
                self._auto_primary_model = ""
                self._update_primary_controls()

            self._update_model_info(ollama_model)

            # Apply profession tuning bundle (offline model + retrieval knobs).
            # NOTE: Reranker is intentionally not changed here.
            self._apply_use_case_tuning(uc_key, "offline")

            # Flash confirmation so user knows the change took effect
            self.uc_status_var.set("[OK] Applied")
            self.after(3000, lambda: self.uc_status_var.set(""))
        else:
            # Apply profession tuning bundle for online mode before model resolve.
            self._apply_use_case_tuning(uc_key, "online")

            # Online: resolve deployments off the main thread to avoid
            # freezing the GUI on a 1-3s network call.
            self._auto_fallback_note = ""
            self.primary_alert_var.set("")
            self._auto_fallback_active = False
            self._update_primary_controls()
            self.model_info_var.set("loading...")
            self.uc_status_var.set("[OK] Applied")
            self.after(3000, lambda: self.uc_status_var.set(""))
            threading.Thread(
                target=self._resolve_online_model,
                args=(uc_key,),
                daemon=True,
            ).start()

    def _update_profile_playbook(self, uc_key: str) -> None:
        """Show top high-value tasks and recommended dial settings by profile."""
        lines = PROFILE_TASK_PLAYBOOK.get(uc_key, PROFILE_TASK_PLAYBOOK["gen"])
        title = USE_CASES.get(uc_key, {}).get("label", "Profile")
        text = "Top 5 high-value tasks for {}:\n{}".format(
            title, "\n".join(lines)
        )
        self.playbook_label.config(text=text)

    def _resolve_online_model(self, uc_key):
        """Background thread: fetch deployments and update model label."""
        try:
            deployments = get_available_deployments()
            best = select_best_model(uc_key, deployments)
            if best:
                self._online_models = list(deployments) if deployments else [best]
                safe_after(self, 0, self.model_var.set, f"Online: {best}")
                safe_after(
                    self, 0, self._apply_online_selection, best, False, "online auto",
                )
                safe_after(self, 0, self._set_model_combo_for_mode)
                safe_after(self, 0, self._set_auto_note, best, best, False, "online")
            else:
                configured = self._get_configured_online_deployment()
                if configured:
                    self._online_models = [configured]
                    safe_after(self, 0, self.model_var.set, f"Online: {configured}")
                    safe_after(
                        self, 0, self._apply_online_selection, configured, True, "configured fallback",
                    )
                    safe_after(self, 0, self._set_model_combo_for_mode)
                    safe_after(self, 0, self._set_online_discovery_note, configured)
                else:
                    safe_after(self, 0, self.model_info_var.set, "(no model)")
        except RuntimeError:
            pass  # Widget destroyed before thread finished -- safe to ignore
        except Exception:
            try:
                configured = self._get_configured_online_deployment()
                if configured:
                    self._online_models = [configured]
                    safe_after(self, 0, self.model_var.set, f"Online: {configured}")
                    safe_after(
                        self, 0, self._apply_online_selection, configured, True, "configured fallback",
                    )
                    safe_after(self, 0, self._set_model_combo_for_mode)
                    safe_after(self, 0, self._set_online_discovery_note, configured)
                else:
                    safe_after(self, 0, self.model_info_var.set, "(discovery failed)")
            except RuntimeError:
                pass  # Widget destroyed

    def _apply_online_selection(self, deployment, is_fallback=False, note=""):
        """Apply selected online deployment to live config/router for consistency."""
        dep = (deployment or "").strip()
        if not dep:
            return
        if hasattr(self.config, "api"):
            self.config.api.deployment = dep
        try:
            if self.query_engine and hasattr(self.query_engine, "llm_router"):
                api_router = getattr(self.query_engine.llm_router, "api", None)
                if api_router is not None:
                    api_router.deployment = dep
        except Exception:
            pass

    def _on_ask(self, event=None):
        """Handle Ask button click or Enter key.

        State transition: IDLE -> SEARCHING
        The query runs in a background thread to keep the GUI responsive.
        """
        question = self.question_entry.get().strip()
        if not question or question == "Type your question here...":
            return

        if self.query_engine is None:
            self._show_error("[FAIL] Query engine not initialized. Run boot first.")
            return
        # Enforce current grounding bias before each query execution.
        self._apply_grounding_bias_live(int(self._grounding_bias_var.get()))

        # --- Transition to SEARCHING state ---
        self.ask_btn.config(state=tk.DISABLED)  # prevent double-submit
        self._stream_start = time.time()

        # Public testing state (main thread, before thread starts)
        self.is_querying = True
        self.query_done_event.clear()
        self.last_answer_preview = ""
        self.last_query_status = ""

        # Clear previous answer for fresh output
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.config(state=tk.DISABLED)
        self.sources_label.config(text="Sources: (none)", fg=current_theme()["gray"])
        self.metrics_label.config(text="")

        # Show immediate visual feedback: status text + animated overlay
        t = current_theme()
        self.network_label.config(text="Searching documents...", fg=t["gray"])
        self._overlay.start("Searching documents...")

        # Choose streaming path (token-by-token) or fallback (wait for full result)
        has_stream = hasattr(self.query_engine, "query_stream")
        if has_stream:
            self._query_thread = threading.Thread(
                target=self._run_query_stream, args=(question,), daemon=True,
            )
        else:
            self._query_thread = threading.Thread(
                target=self._run_query, args=(question,), daemon=True,
            )
        self._query_thread.start()

    def _run_query(self, question):
        """Execute query in background thread (non-streaming fallback)."""
        try:
            result = self.query_engine.query(question)
            # Thread-safe completion signal + status
            self.is_querying = False
            self.last_answer_preview = (result.answer or "")[:200]
            self.last_query_status = "error" if result.error else "complete"
            self.query_done_event.set()
            safe_after(self, 0, self._display_result, result)
        except Exception as e:
            error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
            self.is_querying = False
            self.last_answer_preview = error_msg
            self.last_query_status = "error"
            self.query_done_event.set()
            safe_after(self, 0, self._show_error, error_msg)

    def _run_query_stream(self, question):
        """Execute streaming query in background thread.

        State transitions driven by the query engine's yield chunks:
          "searching" phase -> stay in SEARCHING state
          "generating" phase -> transition to GENERATING state
          "token" chunks -> append tokens (GENERATING)
          "done" chunk -> transition to COMPLETE state
        """
        try:
            for chunk in self.query_engine.query_stream(question):
                if "phase" in chunk:
                    if chunk["phase"] == "searching":
                        # Still in SEARCHING -- update status text
                        safe_after(self, 0, self._set_status, "Searching documents...")
                    elif chunk["phase"] == "generating":
                        # --- Transition: SEARCHING -> GENERATING ---
                        n = chunk.get("chunks", 0)
                        ms = chunk.get("retrieval_ms", 0)
                        msg = "Found {} chunks ({:.0f}ms) -- Generating answer...".format(n, ms)
                        safe_after(self, 0, self._set_status, msg)
                        safe_after(self, 0, self._start_elapsed_timer)
                        safe_after(self, 0, self._prepare_streaming)
                        safe_after(self, 0, self._overlay.stop)
                elif "token" in chunk:
                    safe_after(self, 0, self._append_token, chunk["token"])
                elif chunk.get("done"):
                    result = chunk.get("result")
                    if result:
                        # Thread-safe completion signal + status
                        self.is_querying = False
                        self.last_answer_preview = (result.answer or "")[:200]
                        self.last_query_status = "error" if result.error else "complete"
                        self.query_done_event.set()
                        safe_after(self, 0, self._finish_stream, result)
                    return
            # If generator exhausted without "done"
            self.is_querying = False
            self.last_query_status = "incomplete"
            self.query_done_event.set()
            safe_after(self, 0, self._stop_elapsed_timer)
            safe_after(self, 0, self._overlay.stop)
            safe_after(self, 0, lambda: self.ask_btn.config(state=tk.NORMAL))
        except Exception as e:
            error_msg = "[FAIL] {}: {}".format(type(e).__name__, e)
            self.is_querying = False
            self.last_answer_preview = error_msg
            self.last_query_status = "error"
            self.query_done_event.set()
            safe_after(self, 0, self._stop_elapsed_timer)
            safe_after(self, 0, self._overlay.cancel)
            safe_after(self, 0, self._show_error, error_msg)

    def _set_status(self, text):
        """Update the network/status label."""
        t = current_theme()
        self.network_label.config(text=text, fg=t["gray"])

    def _prepare_streaming(self):
        """Set answer area to NORMAL for live token insertion."""
        self._streaming = True
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)

    def _append_token(self, token):
        """Append a single token to the answer area (main thread)."""
        if not self._streaming:
            return
        self.answer_text.insert(tk.END, token)
        self.answer_text.see(tk.END)

    def _start_elapsed_timer(self):
        """Start a 500ms timer that updates the status with elapsed time."""
        self._stop_elapsed_timer()
        self._update_elapsed()

    def _update_elapsed(self):
        """Update status line with elapsed seconds."""
        if not self._streaming:
            return
        elapsed = time.time() - self._stream_start
        t = current_theme()
        self.network_label.config(
            text="Generating... ({:.1f}s)".format(elapsed), fg=t["gray"],
        )
        self._elapsed_timer_id = self.after(500, self._update_elapsed)

    def _stop_elapsed_timer(self):
        """Cancel the elapsed timer if running."""
        if self._elapsed_timer_id is not None:
            self.after_cancel(self._elapsed_timer_id)
            self._elapsed_timer_id = None

    def _finish_stream(self, result):
        """Finalize the UI after streaming completes.

        State transition: GENERATING -> COMPLETE
        """
        self._streaming = False
        self._stop_elapsed_timer()

        # Fallback: if streaming produced no visible tokens, populate
        # from result.answer so the answer box is never blank.
        current = self.answer_text.get("1.0", tk.END).strip()
        if not current and result.answer:
            self.answer_text.config(state=tk.NORMAL)
            self.answer_text.delete("1.0", tk.END)
            self.answer_text.insert("1.0", result.answer)

        self.answer_text.config(state=tk.DISABLED)
        self.ask_btn.config(state=tk.NORMAL)
        self.network_label.config(text="")

        # Display sources and metrics from the final result
        t = current_theme()
        if result.error:
            self._show_error("[FAIL] {}".format(result.error))
            return

        # Display grounding status if available
        g_score = getattr(result, "grounding_score", -1.0)
        g_blocked = getattr(result, "grounding_blocked", False)
        if g_blocked:
            self.network_label.config(
                text="Grounding: BLOCKED (score {:.0%})".format(g_score),
                fg=t["red"],
            )
        elif g_score >= 0:
            color = t["green"] if g_score >= 0.8 else t["orange"] if g_score >= 0.5 else t["red"]
            self.network_label.config(
                text="Grounding: {:.0%} verified".format(g_score),
                fg=color,
            )

        if result.sources:
            source_strs = []
            for s in result.sources:
                path = s.get("path", "unknown")
                chunks = s.get("chunks", 0)
                fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                source_strs.append("{} ({} chunks)".format(fname, chunks))
            self.sources_label.config(
                text="Sources: {}".format(", ".join(source_strs)),
                fg=t["fg"],
            )
        else:
            self.sources_label.config(text="Sources: (none)", fg=t["gray"])

        self.metrics_label.config(
            text="Latency: {:,.0f} ms | Tokens in: {} | Tokens out: {}".format(
                result.latency_ms, result.tokens_in, result.tokens_out
            ),
        )

        # Record cost event for PM dashboard
        self._emit_cost_event(result)

    def _display_result(self, result):
        """Display query result in the UI (called on main thread)."""
        try:
            self._display_result_inner(result)
        except Exception as e:
            logger.error("Display result failed: %s", e)
            self.ask_btn.config(state=tk.NORMAL)
            self.network_label.config(text="")

    def _display_result_inner(self, result):
        """Inner display logic (separated so outer can catch and re-enable)."""
        t = current_theme()
        self.ask_btn.config(state=tk.NORMAL)
        self.network_label.config(text="")
        self._overlay.stop()

        # Check for error
        if result.error:
            self._show_error("[FAIL] {}".format(result.error))
            return

        # Display answer -- never leave the box blank
        answer = result.answer or ""
        if not answer.strip():
            if result.sources:
                answer = (
                    "Search found relevant documents but the LLM returned "
                    "an empty response. This may indicate the model is still "
                    "loading or the context was too large. Try again."
                )
            else:
                answer = "No relevant information found in knowledge base."
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert("1.0", answer)
        self.answer_text.config(state=tk.DISABLED)

        # Display grounding status if available
        g_score = getattr(result, "grounding_score", -1.0)
        g_blocked = getattr(result, "grounding_blocked", False)
        if g_blocked:
            self.network_label.config(
                text="Grounding: BLOCKED (score {:.0%})".format(g_score),
                fg=t["red"],
            )
        elif g_score >= 0:
            color = t["green"] if g_score >= 0.8 else t["orange"] if g_score >= 0.5 else t["red"]
            self.network_label.config(
                text="Grounding: {:.0%} verified".format(g_score),
                fg=color,
            )

        # Display sources
        if result.sources:
            source_strs = []
            for s in result.sources:
                path = s.get("path", "unknown")
                chunks = s.get("chunks", 0)
                # Show just the filename, not full path
                fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                source_strs.append("{} ({} chunks)".format(fname, chunks))
            self.sources_label.config(
                text="Sources: {}".format(", ".join(source_strs)),
                fg=t["fg"],
            )
        else:
            self.sources_label.config(text="Sources: (none)", fg=t["gray"])

        # Display metrics
        latency = result.latency_ms
        tokens_in = result.tokens_in
        tokens_out = result.tokens_out
        self.metrics_label.config(
            text="Latency: {:,.0f} ms | Tokens in: {} | Tokens out: {}".format(
                latency, tokens_in, tokens_out
            ),
        )

        # Record cost event for PM dashboard
        self._emit_cost_event(result)

    def _show_error(self, error_msg):
        """Display an error message in the answer area.

        State transition: any state -> ERROR (then effectively IDLE)
        """
        t = current_theme()
        self.ask_btn.config(state=tk.NORMAL)
        self.network_label.config(text="")
        self._overlay.cancel()

        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert("1.0", error_msg)
        self.answer_text.tag_add("error", "1.0", tk.END)
        self.answer_text.tag_config("error", foreground=t["red"])
        self.answer_text.config(state=tk.DISABLED)

        self.sources_label.config(text="Sources: (none)", fg=t["gray"])
        self.metrics_label.config(text="")

    def set_ready(self, enabled):
        """Enable or disable the Ask button based on backend readiness."""
        t = current_theme()
        if enabled:
            self.ask_btn.config(state=tk.NORMAL, bg=t["accent"],
                                fg=t["accent_fg"])
        else:
            self.ask_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                                fg=t["inactive_btn_fg"])

    def _emit_cost_event(self, result):
        """Record completed query in the cost tracker for PM dashboard."""
        try:
            tracker = get_cost_tracker()
            mode = getattr(result, "mode", "offline")
            chosen = self.model_var.get()
            if chosen == "Auto":
                model = getattr(
                    getattr(self.config, "ollama", None), "model", ""
                ) or ""
            else:
                model = chosen
            profile = self.get_current_use_case_key()
            tracker.record(
                tokens_in=getattr(result, "tokens_in", 0),
                tokens_out=getattr(result, "tokens_out", 0),
                model=model,
                mode=mode,
                profile=profile,
                latency_ms=getattr(result, "latency_ms", 0.0),
            )
        except Exception as e:
            logger.debug("Cost event emit failed: %s", e)

    def get_current_use_case_key(self):
        """Return the currently selected use case key."""
        idx = self._uc_labels.index(self.uc_var.get()) if self.uc_var.get() in self._uc_labels else 0
        return self._uc_keys[idx]
