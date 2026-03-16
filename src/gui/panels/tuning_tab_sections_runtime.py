# TuningTab runtime: section builders (retrieval, query policy, LLM, profile, reset).
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.gui.panels.settings_view import (
    _load_profile_names,
)
from src.gui.theme import FONT, FONT_BOLD, FONT_SMALL, bind_hover


# ------------------------------------------------------------------
# Layout sections
# ------------------------------------------------------------------


def _build_mode_banner(self, theme):
    row = tk.Frame(self, bg=theme["panel_bg"])
    row.pack(fill=tk.X, padx=16, pady=(10, 2))
    self._mode_row = row
    tk.Label(
        row,
        text="Admin target:",
        anchor=tk.W,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        font=FONT,
    ).pack(side=tk.LEFT)
    self._mode_selector = ttk.Combobox(
        row,
        textvariable=self._editor_mode_var,
        values=["offline", "online"],
        state="readonly",
        width=10,
        font=FONT,
    )
    self._mode_selector.pack(side=tk.LEFT, padx=(8, 12))
    self._mode_selector.bind("<<ComboboxSelected>>", self._on_editor_mode_change)
    self._mode_banner = tk.Label(
        row,
        textvariable=self._mode_banner_var,
        anchor=tk.W,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    self._mode_banner.pack(side=tk.LEFT, fill=tk.X, expand=True)
    self._mode_status = tk.Label(
        row,
        textvariable=self._mode_status_var,
        anchor=tk.E,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._mode_status.pack(side=tk.RIGHT)


def _build_editor_columns(self, theme):
    split = tk.Frame(self, bg=theme["panel_bg"])
    split.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
    self._editor_split = split

    left = tk.Frame(split, bg=theme["panel_bg"])
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 6))
    self._retrieval_column = left

    right = tk.Frame(split, bg=theme["panel_bg"])
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 8))
    self._query_column = right
    self._generation_column = right

    self._build_retrieval_section(theme, parent=left)
    self._build_query_policy_section(theme, parent=right)
    self._build_llm_section(theme, parent=right)


def _build_retrieval_section(self, theme, parent=None):
    host = parent or self
    frame = tk.LabelFrame(
        host,
        text="Retrieval Settings",
        padx=16,
        pady=8,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    frame.pack(
        fill=tk.BOTH if parent is not None else tk.X,
        expand=bool(parent is not None),
        padx=8 if parent is not None else 16,
        pady=(8, 4) if parent is None else (4, 4),
    )
    self._retrieval_frame = frame

    values = self._display_values_from_config()

    self.topk_var = tk.IntVar(value=values["top_k"])
    self._build_slider_row(frame, theme, "top_k", "top_k:", self.topk_var, 1, 50, on_change=self._on_retrieval_change)

    self.minscore_var = tk.DoubleVar(value=values["min_score"])
    self._build_slider_row(
        frame,
        theme,
        "min_score",
        "min_score:",
        self.minscore_var,
        0.0,
        1.0,
        resolution=0.01,
        on_change=self._on_retrieval_change,
    )

    self.hybrid_var = tk.BooleanVar(value=values["hybrid_search"])
    self._build_check_row(frame, theme, "hybrid_search", "Hybrid search:", self.hybrid_var, on_change=self._on_retrieval_change)

    toggle_row = tk.Frame(frame, bg=theme["panel_bg"])
    toggle_row.pack(fill=tk.X, pady=(4, 0))
    self._show_retrieval_advanced_var = tk.BooleanVar(
        value=bool(values["reranker_enabled"])
    )
    tk.Checkbutton(
        toggle_row,
        text="Show advanced retrieval",
        variable=self._show_retrieval_advanced_var,
        command=self._sync_retrieval_advanced_visibility,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    ).pack(side=tk.LEFT)

    advanced = tk.Frame(frame, bg=theme["panel_bg"])
    self._retrieval_advanced_frame = advanced

    self.reranker_var = tk.BooleanVar(value=values["reranker_enabled"])
    self._build_check_row(
        advanced,
        theme,
        "reranker_enabled",
        "Reranker:",
        self.reranker_var,
        on_change=self._on_retrieval_change,
    )

    self.reranker_topn_var = tk.IntVar(value=values["reranker_top_n"])
    self._build_slider_row(
        advanced,
        theme,
        "reranker_top_n",
        "Reranker top_n:",
        self.reranker_topn_var,
        5,
        100,
        on_change=self._on_retrieval_change,
    )

    tk.Label(
        advanced,
        text="Reranker is optional and should stay off until retrieval quality needs the extra pass.",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(2, 0))

    self._latency_warn_label = tk.Label(
        frame,
        text="",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._latency_warn_label.pack(fill=tk.X, pady=(4, 0))
    self._sync_retrieval_advanced_visibility()
    self._update_latency_warning()


def _build_query_policy_section(self, theme, parent=None):
    host = parent or self
    frame = tk.LabelFrame(
        host,
        text="Query Policy",
        padx=16,
        pady=8,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    frame.pack(
        fill=tk.BOTH if parent is not None else tk.X,
        expand=False,
        padx=8 if parent is not None else 16,
        pady=(4, 4),
    )
    self._query_policy_frame = frame

    values = self._display_values_from_config()

    self.grounding_bias_var = tk.IntVar(value=values["grounding_bias"])
    self._build_slider_row(
        frame,
        theme,
        "grounding_bias",
        "Grounding bias:",
        self.grounding_bias_var,
        0,
        10,
        on_change=self._on_query_policy_change,
    )

    self._grounding_bias_hint_var = tk.StringVar(value="")
    tk.Label(
        frame,
        textvariable=self._grounding_bias_hint_var,
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(2, 0))

    self.allow_open_knowledge_var = tk.BooleanVar(value=values["allow_open_knowledge"])
    self._build_check_row(
        frame,
        theme,
        "allow_open_knowledge",
        "Open knowledge:",
        self.allow_open_knowledge_var,
        on_change=self._on_query_policy_change,
    )

    self._open_knowledge_hint_var = tk.StringVar(value="")
    tk.Label(
        frame,
        textvariable=self._open_knowledge_hint_var,
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(2, 0))

    self._query_policy_note = tk.Label(
        frame,
        text="",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._query_policy_note.pack(fill=tk.X, pady=(4, 0))
    self._update_query_policy_hints()


def _build_llm_section(self, theme, parent=None):
    host = parent or self
    frame = tk.LabelFrame(
        host,
        text="Generation",
        padx=16,
        pady=8,
        bg=theme["panel_bg"],
        fg=theme["accent"],
        font=FONT_BOLD,
    )
    frame.pack(
        fill=tk.BOTH if parent is not None else tk.X,
        expand=bool(parent is not None),
        padx=8 if parent is not None else 16,
        pady=(4, 4) if parent is not None else 8,
    )
    self._generation_frame = frame
    self._llm_frame = frame

    values = self._display_values_from_config()

    self.ctx_window_var = tk.IntVar(value=values["context_window"])
    self._build_slider_row(
        frame,
        theme,
        "context_window",
        "Context window:",
        self.ctx_window_var,
        1024,
        131072,
        on_change=self._on_llm_change,
    )

    self.num_predict_var = tk.IntVar(value=values["num_predict"])
    self._build_slider_row(frame, theme, "num_predict", "Num predict:", self.num_predict_var, 64, 4096, on_change=self._on_llm_change)

    self.maxtokens_var = tk.IntVar(value=values["max_tokens"])
    self._build_slider_row(
        frame,
        theme,
        "max_tokens",
        "Max tokens (API):",
        self.maxtokens_var,
        256,
        16384,
        on_change=self._on_llm_change,
    )

    self.temp_var = tk.DoubleVar(value=values["temperature"])
    self._build_slider_row(
        frame,
        theme,
        "temperature",
        "Temperature:",
        self.temp_var,
        0.0,
        2.0,
        resolution=0.01,
        on_change=self._on_llm_change,
    )

    self.top_p_var = tk.DoubleVar(value=values["top_p"])
    self._build_slider_row(
        frame,
        theme,
        "top_p",
        "Top p:",
        self.top_p_var,
        0.05,
        1.0,
        resolution=0.01,
        on_change=self._on_llm_change,
    )

    self.timeout_var = tk.IntVar(value=values["timeout_seconds"])
    self._build_slider_row(
        frame,
        theme,
        "timeout_seconds",
        "Timeout (s):",
        self.timeout_var,
        30,
        1200,
        on_change=self._on_llm_change,
    )

    toggle_row = tk.Frame(frame, bg=theme["panel_bg"])
    toggle_row.pack(fill=tk.X, pady=(4, 0))
    generation_advanced_open = bool(values["seed"])
    if self._current_mode() == "online":
        generation_advanced_open = generation_advanced_open or (
            abs(float(values["presence_penalty"])) > 1e-9
            or abs(float(values["frequency_penalty"])) > 1e-9
        )
    self._show_generation_advanced_var = tk.BooleanVar(
        value=generation_advanced_open
    )
    tk.Checkbutton(
        toggle_row,
        text="Show advanced generation",
        variable=self._show_generation_advanced_var,
        command=self._sync_generation_advanced_visibility,
        bg=theme["panel_bg"],
        fg=theme["fg"],
        selectcolor=theme["input_bg"],
        activebackground=theme["panel_bg"],
        activeforeground=theme["fg"],
        font=FONT_SMALL,
    ).pack(side=tk.LEFT)

    advanced = tk.Frame(frame, bg=theme["panel_bg"])
    self._generation_advanced_frame = advanced

    self.presence_penalty_var = tk.DoubleVar(value=values["presence_penalty"])
    self._build_slider_row(
        advanced,
        theme,
        "presence_penalty",
        "Presence penalty:",
        self.presence_penalty_var,
        -2.0,
        2.0,
        resolution=0.05,
        on_change=self._on_llm_change,
    )

    self.frequency_penalty_var = tk.DoubleVar(value=values["frequency_penalty"])
    self._build_slider_row(
        advanced,
        theme,
        "frequency_penalty",
        "Frequency penalty:",
        self.frequency_penalty_var,
        -2.0,
        2.0,
        resolution=0.05,
        on_change=self._on_llm_change,
    )

    self.seed_var = tk.IntVar(value=values["seed"])
    self._build_entry_row(
        advanced,
        theme,
        "seed",
        "Seed:",
        self.seed_var,
        on_change=self._on_llm_change,
    )

    tk.Label(
        advanced,
        text="Advanced controls stay provider-aware: online penalties are hidden offline, seed is shared.",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    ).pack(fill=tk.X, pady=(2, 0))

    self._llm_mode_note = tk.Label(
        frame,
        text="",
        anchor=tk.W,
        wraplength=360,
        bg=theme["panel_bg"],
        fg=theme["gray"],
        font=FONT_SMALL,
    )
    self._llm_mode_note.pack(fill=tk.X, pady=(4, 0))
    self._sync_generation_advanced_visibility()


def _build_profile_section(self, theme):
    frame = tk.LabelFrame(self, text="Profile & Model Ranking", padx=16, pady=8, bg=theme["panel_bg"], fg=theme["accent"], font=FONT_BOLD)
    frame.pack(fill=tk.X, padx=16, pady=8)
    self._profile_frame = frame

    row = tk.Frame(frame, bg=theme["panel_bg"])
    row.pack(fill=tk.X, pady=4)

    self._profile_label = tk.Label(row, text="Profile:", width=14, anchor=tk.W, bg=theme["panel_bg"], fg=theme["fg"], font=FONT)
    self._profile_label.pack(side=tk.LEFT)

    self.profile_var = tk.StringVar(value="desktop_power")
    self.profile_dropdown = ttk.Combobox(
        row,
        textvariable=self.profile_var,
        values=_load_profile_names(),
        state="readonly",
        width=20,
        font=FONT,
    )
    self.profile_dropdown.pack(side=tk.LEFT, padx=(8, 0))

    self.profile_apply_btn = tk.Button(
        row,
        text="Apply",
        command=self._on_profile_change,
        width=8,
        bg=theme["accent"],
        fg=theme["accent_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=6,
        pady=2,
        activebackground=theme["accent_hover"],
        activeforeground=theme["accent_fg"],
    )
    self.profile_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

    hw_text = "Detected: {:.0f}GB RAM, {:.0f}GB VRAM -> {}".format(self._ram_gb, self._vram_gb, self._hw_class)
    tk.Label(frame, text=hw_text, anchor=tk.W, bg=theme["panel_bg"], fg=theme["gray"], font=FONT_SMALL).pack(fill=tk.X, pady=(2, 0))

    self.profile_info_label = tk.Label(frame, text="", anchor=tk.W, fg=theme["fg"], bg=theme["panel_bg"], font=FONT_SMALL)
    self.profile_info_label.pack(fill=tk.X, pady=(2, 0))

    self.profile_status_label = tk.Label(frame, text="", anchor=tk.W, fg=theme["gray"], bg=theme["panel_bg"], font=FONT)
    self.profile_status_label.pack(fill=tk.X, pady=2)

    self.model_table = tk.Text(
        frame,
        height=12,
        wrap=tk.NONE,
        state=tk.DISABLED,
        font=("Consolas", 9),
        bg=theme["input_bg"],
        fg=theme["input_fg"],
        relief=tk.FLAT,
        bd=2,
    )
    self.model_table.pack(fill=tk.X, pady=(4, 2))

    self._detect_current_profile()
    self._refresh_profile_info()
    self._refresh_model_table()


def _build_reset_button(self, theme):
    frame = tk.Frame(self, bg=theme["panel_bg"])
    frame.pack(fill=tk.X, padx=16, pady=16)
    self._reset_frame = frame

    self._save_mode_defaults_btn = tk.Button(
        frame,
        text="Save Active Mode Defaults",
        command=self._on_save_mode_defaults,
        width=24,
        bg=theme["accent"],
        fg=theme["accent_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._save_mode_defaults_btn.pack(side=tk.LEFT, padx=(0, 8))
    bind_hover(self._save_mode_defaults_btn)

    self._reset_btn = tk.Button(
        frame,
        text="Reset to Defaults",
        command=self._on_reset,
        width=16,
        bg=theme["inactive_btn_bg"],
        fg=theme["inactive_btn_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._reset_btn.pack(side=tk.LEFT)
    bind_hover(self._reset_btn)

    self._lock_all_btn = tk.Button(
        frame,
        text="Lock All to Defaults",
        command=self._lock_all_defaults,
        width=16,
        bg=theme["inactive_btn_bg"],
        fg=theme["inactive_btn_fg"],
        font=FONT,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=8,
    )
    self._lock_all_btn.pack(side=tk.LEFT, padx=(8, 0))
    bind_hover(self._lock_all_btn)


# ------------------------------------------------------------------
# Bind
# ------------------------------------------------------------------


def bind_tuning_tab_sections_runtime_methods(tab_cls):
    """Bind section-builder methods to TuningTab."""
    tab_cls._build_mode_banner = _build_mode_banner
    tab_cls._build_editor_columns = _build_editor_columns
    tab_cls._build_retrieval_section = _build_retrieval_section
    tab_cls._build_query_policy_section = _build_query_policy_section
    tab_cls._build_llm_section = _build_llm_section
    tab_cls._build_profile_section = _build_profile_section
    tab_cls._build_reset_button = _build_reset_button
