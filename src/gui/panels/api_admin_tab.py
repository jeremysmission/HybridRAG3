# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the api admin tab part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ============================================================================
# HybridRAG v3 -- API & Admin Tab (src/gui/panels/api_admin_tab.py)    RevC
# ============================================================================
# WHAT: Combined admin panel for API credentials, file paths, model
#       selection, and system defaults -- everything an admin touches.
# WHY:  Centralizes all "admin setup" tasks into one tabbed view so
#       non-technical users can configure the system without editing
#       YAML files or running command-line scripts.
# HOW:  Four self-contained sections (LabelFrames) stacked inside a
#       scrollable canvas.  Each section reads/writes the live config
#       object and persists changes to disk (YAML or Credential Manager).
# USAGE: Embedded inside SettingsView notebook as the "API & Admin" tab.
#        Navigate via Admin menu or NavBar > Settings > API & Admin.
#
# Sections:
#   A. API Credentials  -- endpoint URL, API key, save/test/clear
#   A2. Security & Privacy -- PII scrubber toggle (online-only)
#   B. Data Paths       -- source folder, index folder, save to config
#   C. Online Model Selection -- treeview with ranked models
#   D. Admin Defaults  -- save current / restore defaults
#
# Classes:
#   DataPathsPanel      -- folder pickers + validation for source/index
#   ModelSelectionPanel  -- self-contained treeview for online model pick
#   OfflineModelSelectionPanel -- Ollama model picker for offline mode
#   ApiAdminTab          -- coordinator Frame embedding all four sections
#
# SPLIT:
#   ApiAdminTab runtime methods are in api_admin_tab_runtime.py, bound
#   at import time by bind_api_admin_tab_runtime_methods().
#
# INTERNET ACCESS:
#   Test Connection + Refresh Models: one GET to /models endpoint
#   All other operations: NONE
# ============================================================================

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.scrollable import ScrollableFrame
from src.core.model_identity import canonicalize_model_name, resolve_ollama_model_name
from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url
from src.security.credentials import (
    resolve_credentials, validate_endpoint,
    store_api_key, store_endpoint, clear_credentials,
    invalidate_credential_cache,
)
from src.gui.panels.api_admin_tab_runtime import (
    _theme_widget,
    bind_api_admin_tab_runtime_methods,
)

logger = logging.getLogger(__name__)


# ====================================================================
# DataPathsPanel -- source + index folder selection
# ====================================================================

class DataPathsPanel(tk.LabelFrame):
    """
    Data path selection for source and indexed data folders.

    Reads initial values from config.paths, writes back on Save.
    """

    def __init__(self, parent, config, app_ref):
        """Create the data paths panel.

        Args:
            parent: Parent tk widget to embed in.
            config: Live config object -- paths are read from and written to this.
            app_ref: Reference to the main HybridRAGApp, used to sync the
                     index panel when paths change.
        """
        t = current_theme()
        super().__init__(parent, text="Data Paths", padx=16, pady=8,
                         bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        self.config = config
        self._app = app_ref

        self._build(t)
        self._refresh_info()

    def _build(self, t):
        """Construct two blue buttons (Source / Index) with path labels."""
        # Buttons row -- two prominent blue buttons side by side
        btn_row = tk.Frame(self, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=(4, 8))

        self.source_browse_btn = tk.Button(
            btn_row, text="Source", command=self._on_browse_source, width=10,
            bg=t["accent"], fg=t["accent_fg"], font=FONT_BOLD,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.source_browse_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.source_browse_btn)

        self.index_browse_btn = tk.Button(
            btn_row, text="Index", command=self._on_browse_index, width=10,
            bg=t["accent"], fg=t["accent_fg"], font=FONT_BOLD,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.index_browse_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.index_browse_btn)

        # Path display labels (show selected paths beneath the buttons)
        source_default = getattr(
            getattr(self.config, "paths", None), "source_folder", ""
        ) or ""
        self.source_var = tk.StringVar(value=source_default)

        db_path = getattr(
            getattr(self.config, "paths", None), "database", ""
        ) or ""
        index_default = os.path.dirname(db_path) if db_path else ""
        self.index_var = tk.StringVar(value=index_default)

        self.source_label = tk.Label(
            self, textvariable=self.source_var, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT_SMALL,
        )
        self.source_label.pack(fill=tk.X)

        self.index_label = tk.Label(
            self, textvariable=self.index_var, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT_SMALL,
        )
        self.index_label.pack(fill=tk.X)

        # Default persistence toggles (checked by default).
        # If unchecked, edits apply to this session only.
        persist_row = tk.Frame(self, bg=t["panel_bg"])
        persist_row.pack(fill=tk.X, pady=(4, 0))
        self.persist_source_var = tk.BooleanVar(value=True)
        self.persist_index_var = tk.BooleanVar(value=True)
        self.persist_source_cb = tk.Checkbutton(
            persist_row, text="Set source as default",
            variable=self.persist_source_var,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT_SMALL,
        )
        self.persist_source_cb.pack(side=tk.LEFT, padx=(0, 12))
        self.persist_index_cb = tk.Checkbutton(
            persist_row, text="Set index as default",
            variable=self.persist_index_var,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT_SMALL,
        )
        self.persist_index_cb.pack(side=tk.LEFT)

        # Detection info
        self.info_label = tk.Label(
            self, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.info_label.pack(fill=tk.X, pady=(4, 0))

        # Status label (save feedback)
        self.status_label = tk.Label(
            self, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.status_label.pack(fill=tk.X, pady=(2, 0))

    def _on_browse_source(self):
        """Open a native folder picker for the source documents directory."""
        current = self.source_var.get().strip()
        initial = current if current and os.path.isdir(current) else ""
        folder = filedialog.askdirectory(
            title="Select Source Documents Folder", initialdir=initial)
        if folder:
            self.source_var.set(os.path.normpath(folder))
            self._on_save()

    def _on_browse_index(self):
        """Open a native folder picker for the index data directory."""
        current = self.index_var.get().strip()
        initial = current if current and os.path.isdir(current) else ""
        folder = filedialog.askdirectory(
            title="Select Index Data Folder", initialdir=initial)
        if folder:
            self.index_var.set(os.path.normpath(folder))
            self._on_save()

    def _on_save(self):
        """Write source and index paths to config YAML and live config."""
        t = current_theme()
        source = self.source_var.get().strip()
        index = self.index_var.get().strip()
        persist_source = bool(self.persist_source_var.get())
        persist_index = bool(self.persist_index_var.get())

        if not source and not index:
            self.status_label.config(
                text="[WARN] Both paths are empty -- nothing to save.",
                fg=t["orange"])
            return

        errors = []
        if source and not os.path.isdir(source):
            errors.append("Source folder does not exist")
        if index and not os.path.isdir(index):
            errors.append("Index folder does not exist")
        if errors:
            self.status_label.config(
                text="[FAIL] {}".format("; ".join(errors)), fg=t["red"])
            return

        db_path = os.path.join(index, "hybridrag.sqlite3") if index else ""
        emb_path = os.path.join(index, "_embeddings") if index else ""

        paths = getattr(self.config, "paths", None)
        if paths:
            if source:
                paths.source_folder = source
            if index:
                paths.database = db_path
                paths.embeddings_cache = emb_path

        try:
            from src.core.config import save_config_field
            if source and persist_source:
                save_config_field("paths.source_folder", source)
            if index and persist_index:
                save_config_field("paths.database", db_path)
                save_config_field("paths.embeddings_cache", emb_path)

            if hasattr(self._app, "index_panel"):
                ip = self._app.index_panel
                if source:
                    ip.folder_var.set(source)
                if index:
                    ip.index_var.set(index)
                ip.config = self.config

            if (source and persist_source) or (index and persist_index):
                status = "[OK] Paths saved to config."
            else:
                status = "[OK] Paths updated for this session only."
            self.status_label.config(text=status, fg=t["green"])
            self._refresh_info()
            logger.info("Data paths saved: source=%s, index=%s", source, index)
        except Exception as e:
            self.status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"])

    def _refresh_info(self):
        """Show detection info for current paths."""
        parts = []
        source = self.source_var.get().strip()
        if source and os.path.isdir(source):
            try:
                count = sum(1 for _ in os.scandir(source)
                            if _.is_file() and not _.name.startswith("."))
                parts.append("Source: {} files".format(count))
            except Exception:
                parts.append("Source: exists")
        elif source:
            parts.append("Source: NOT FOUND")
        else:
            parts.append("Source: (not set)")

        index = self.index_var.get().strip()
        if index and os.path.isdir(index):
            db_exists = os.path.isfile(os.path.join(index, "hybridrag.sqlite3"))
            emb_exists = os.path.isdir(os.path.join(index, "_embeddings"))
            if db_exists and emb_exists:
                parts.append("Index: DB + embeddings present")
            elif db_exists:
                parts.append("Index: DB only (no embeddings)")
            elif emb_exists:
                parts.append("Index: embeddings only (no DB)")
            else:
                parts.append("Index: empty folder")
        elif index:
            parts.append("Index: NOT FOUND")
        else:
            parts.append("Index: (not set)")

        t = current_theme()
        self.info_label.config(text="  |  ".join(parts), fg=t["gray"])

    def apply_theme(self, t):
        """Plain-English: This function handles apply theme."""
        self.configure(bg=t["panel_bg"], fg=t["accent"])
        _theme_widget(self, t)


# ====================================================================
# ModelSelectionPanel -- self-contained online model treeview
# ====================================================================

class ModelSelectionPanel(tk.LabelFrame):
    """
    Online model selection with ranked treeview and use-case dropdown.

    Reads endpoint/key from parent tab's StringVars to fetch models.
    Writes selected model to config.api.model.
    """

    def __init__(self, parent, config, endpoint_var, key_var):
        """Create the model selection panel.

        Args:
            parent: Parent tk widget.
            config: Live config object -- selected model is written to config.api.model.
            endpoint_var: StringVar holding the API endpoint URL (from credentials section).
            key_var: StringVar holding the API key (from credentials section).
        """
        t = current_theme()
        super().__init__(parent, text="Online Model Selection", padx=16, pady=8,
                         bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        self.config = config
        self._endpoint_var = endpoint_var
        self._key_var = key_var
        self._models_data = []   # raw model dicts from API, cached after fetch

        self._build(t)

    def _build(self, t):
        """Build control row + treeview."""
        ctrl_row = tk.Frame(self, bg=t["panel_bg"])
        ctrl_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            ctrl_row, text="Use case:", anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)

        from scripts._model_meta import USE_CASES
        self._uc_keys = list(USE_CASES.keys())
        uc_labels = [USE_CASES[k]["label"] for k in self._uc_keys]
        self.uc_var = tk.StringVar(value=uc_labels[0] if uc_labels else "")
        self.uc_dropdown = ttk.Combobox(
            ctrl_row, textvariable=self.uc_var, values=uc_labels,
            state="readonly", width=24, font=FONT,
        )
        self.uc_dropdown.pack(side=tk.LEFT, padx=(8, 8))
        self.uc_dropdown.bind("<<ComboboxSelected>>", self._on_uc_change)

        self.refresh_btn = tk.Button(
            ctrl_row, text="Refresh Models", command=self._on_refresh,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=4,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.refresh_btn.pack(side=tk.LEFT)
        bind_hover(self.refresh_btn)

        self.status_label = tk.Label(
            self, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.status_label.pack(fill=tk.X, pady=(0, 4))

        # Treeview
        columns = ("model", "family", "eng", "gen", "score",
                    "ctx", "price_in", "price_out")
        self.tree = ttk.Treeview(
            self, columns=columns, show="headings", height=10,
            selectmode="browse",
        )
        for col, hdr, w, anchor in [
            ("model", "Model", 220, tk.W), ("family", "Family", 80, tk.W),
            ("eng", "ENG", 45, tk.CENTER), ("gen", "GEN", 45, tk.CENTER),
            ("score", "Score", 50, tk.CENTER), ("ctx", "Ctx", 55, tk.CENTER),
            ("price_in", "$/1M In", 70, tk.E), ("price_out", "$/1M Out", 70, tk.E),
        ]:
            self.tree.heading(col, text=hdr)
            self.tree.column(col, width=w, anchor=anchor, minwidth=max(40, w - 15))

        tree_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL,
                                     command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("recommended", background="#1a3a1a")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    # -- Use case --

    def _on_uc_change(self, event=None):
        """Re-sort and re-display models when the user picks a different use case."""
        self._populate()

    def _get_uc_key(self):
        """Convert the human-readable dropdown label back to a key like 'sw' or 'pm'."""
        from scripts._model_meta import USE_CASES
        label = self.uc_var.get()
        for k, uc in USE_CASES.items():
            if uc["label"] == label:
                return k
        return "sw"

    # -- Refresh --

    def _on_refresh(self):
        """Fetch model list from the API endpoint in a background thread."""
        t = current_theme()
        endpoint = self._endpoint_var.get().strip()
        key = self._key_var.get().strip()
        if not endpoint or not key:
            self.status_label.config(
                text="[WARN] Enter endpoint and key first.", fg=t["orange"])
            return
        self.refresh_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Fetching models...", fg=t["gray"])
        threading.Thread(target=self._do_fetch, args=(endpoint, key),
                         daemon=True).start()

    def _do_fetch(self, endpoint, key):
        """Background thread: call the API's /models endpoint and parse the result."""
        from src.gui.helpers.safe_after import safe_after
        try:
            from scripts._model_meta import fetch_online_models_with_meta
            by_provider, total = fetch_online_models_with_meta(endpoint, key)
            flat = []
            for pmodels in by_provider.values():
                flat.extend(pmodels)
            if total > 0:
                safe_after(self, 0, self._fetch_done, flat, total)
            else:
                safe_after(self, 0, self._fetch_failed, "No models returned")
        except Exception as e:
            safe_after(self, 0, self._fetch_failed, str(e)[:80])

    def _fetch_done(self, models, total):
        """Main-thread callback: populate the treeview after a successful fetch."""
        t = current_theme()
        self._models_data = models
        self.status_label.config(
            text="{} models loaded.".format(total), fg=t["green"])
        self.refresh_btn.config(state=tk.NORMAL)
        self._populate()

    def _fetch_failed(self, msg):
        """Main-thread callback: show error when model fetch fails."""
        t = current_theme()
        self.status_label.config(text="[FAIL] {}".format(msg), fg=t["red"])
        self.refresh_btn.config(state=tk.NORMAL)

    def set_models(self, models):
        """Externally set model data (e.g. from Test Connection)."""
        self._models_data = models
        self._populate()

    # -- Populate --

    def _populate(self):
        """Fill the treeview with models sorted by use-case score.

        Models are scored using the tier_eng/tier_gen weights for the
        selected use case.  Recommended models (from RECOMMENDED_ONLINE)
        get a green highlight row so admins can spot them instantly.
        """
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not self._models_data:
            return

        from scripts._model_meta import (
            use_case_score, format_context_length, format_price,
            lookup_known_model, RECOMMENDED_ONLINE,
        )

        uc_key = self._get_uc_key()
        rec = RECOMMENDED_ONLINE.get(uc_key, {})
        rec_primary = rec.get("primary", "")
        rec_alt = rec.get("alt", "")

        scored = []
        for m in self._models_data:
            m["_score"] = use_case_score(
                m.get("tier_eng", 0), m.get("tier_gen", 0), uc_key)
            scored.append(m)
        scored.sort(key=lambda x: x["_score"], reverse=True)

        for m in scored:
            mid = m.get("id", "")
            kb = lookup_known_model(mid)
            family = kb.get("family", "") if kb else ""
            if not family:
                family = mid.split("/")[0] if "/" in mid else "?"

            tags = ()
            short = mid.split("/")[-1] if "/" in mid else mid
            if mid == rec_primary or short == rec_primary:
                tags = ("recommended",)
            elif mid == rec_alt or short == rec_alt:
                tags = ("recommended",)

            self.tree.insert("", tk.END, iid=mid, values=(
                mid, family,
                m.get("tier_eng", "?"), m.get("tier_gen", "?"),
                m.get("_score", "?"),
                format_context_length(m.get("ctx", 0)),
                format_price(m.get("price_in", 0)),
                format_price(m.get("price_out", 0)),
            ), tags=tags)

    def _on_select(self, event=None):
        """When the user clicks a model row, set it as the active online model."""
        sel = self.tree.selection()
        if not sel:
            return
        model_id = sel[0]
        api = getattr(self.config, "api", None)
        if api:
            api.model = model_id
            api.deployment = model_id
        try:
            from src.gui.helpers.mode_tuning import update_mode_section

            update_mode_section(self.config, "online", "api", "model", model_id)
            update_mode_section(self.config, "online", "api", "deployment", model_id)
        except Exception:
            logger.debug("Could not persist online model selection", exc_info=True)
        t = current_theme()
        self.status_label.config(text="Selected: {} (saved)".format(model_id), fg=t["fg"])

    # -- Theme --

    def apply_theme(self, t):
        """Plain-English: This function handles apply theme."""
        self.configure(bg=t["panel_bg"], fg=t["accent"])
        if t["name"] == "dark":
            self.tree.tag_configure("recommended", background="#1a3a1a")
        else:
            self.tree.tag_configure("recommended", background="#e8f5e9")
        _theme_widget(self, t)


# ====================================================================
# OfflineModelSelectionPanel -- Ollama model picker for offline mode
# ====================================================================

class OfflineModelSelectionPanel(tk.LabelFrame):
    """Offline model selection with ranked treeview and use-case dropdown.

    Mirrors ModelSelectionPanel but reads from the local approved model
    stack (WORK_ONLY_MODELS) instead of making API calls.
    Writes selected model to config.ollama.model.
    """

    def __init__(self, parent, config, app_ref=None):
        """Plain-English: This function handles init."""
        t = current_theme()
        super().__init__(parent, text="Offline Model Selection", padx=16, pady=8,
                         bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        self.config = config
        self._app = app_ref
        self._suppress_select_event = False
        self._build(t)
        self._populate()

    def _build(self, t):
        """Build control row + treeview."""
        ctrl_row = tk.Frame(self, bg=t["panel_bg"])
        ctrl_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            ctrl_row, text="Use case:", anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)

        from scripts._model_meta import USE_CASES
        self._uc_keys = list(USE_CASES.keys())
        uc_labels = [USE_CASES[k]["label"] for k in self._uc_keys]
        self.uc_var = tk.StringVar(value=uc_labels[0] if uc_labels else "")
        self.uc_dropdown = ttk.Combobox(
            ctrl_row, textvariable=self.uc_var, values=uc_labels,
            state="readonly", width=24, font=FONT,
        )
        self.uc_dropdown.pack(side=tk.LEFT, padx=(8, 8))
        self.uc_dropdown.bind("<<ComboboxSelected>>", self._on_uc_change)

        self.status_label = tk.Label(
            self, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.status_label.pack(fill=tk.X, pady=(0, 4))

        # Treeview inside its own frame so the button row below
        # is not squeezed out by side=LEFT/RIGHT packing.
        tree_frame = tk.Frame(self, bg=t["panel_bg"])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("model", "role", "eng", "gen", "score", "vram_gb", "note")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=6,
            selectmode="browse",
        )
        for col, hdr, w, anchor in [
            ("model", "Model", 180, tk.W),
            ("role", "Role", 70, tk.W),
            ("eng", "ENG", 45, tk.CENTER),
            ("gen", "GEN", 45, tk.CENTER),
            ("score", "Score", 50, tk.CENTER),
            ("vram_gb", "VRAM", 60, tk.CENTER),
            ("note", "Note", 220, tk.W),
        ]:
            self.tree.heading(col, text=hdr)
            self.tree.column(col, width=w, anchor=anchor, minwidth=max(40, w - 15))

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                     command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("primary", background="#1a3a1a")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # --- Button row below treeview ---
        btn_row = tk.Frame(self, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=(6, 2))

        self._dl_btn = tk.Button(
            btn_row, text="Check / Download Models",
            command=self._open_download_dialog,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            activebackground=t.get("accent_hover", t["accent"]),
            cursor="hand2", relief=tk.FLAT, padx=12, pady=4,
        )
        self._dl_btn.pack(side=tk.LEFT)
        bind_hover(self._dl_btn)

        self._dl_status = tk.Label(
            btn_row, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._dl_status.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

    def _get_uc_key(self):
        """Plain-English: This function handles get uc key."""
        from scripts._model_meta import USE_CASES
        label = self.uc_var.get()
        for k, uc in USE_CASES.items():
            if uc["label"] == label:
                return k
        return "sw"

    def _on_uc_change(self, event=None):
        """Plain-English: This function handles on uc change."""
        self._populate()

    def _populate(self):
        """Fill the treeview with approved offline models ranked for the use case."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        from scripts._model_meta import (
            WORK_ONLY_MODELS, RECOMMENDED_OFFLINE,
            use_case_score as uc_score,
        )

        uc_key = self._get_uc_key()
        rec = RECOMMENDED_OFFLINE.get(uc_key, {})
        rec_primary = rec.get("primary", "")
        rec_alt = rec.get("alt", "")

        # Current model from config
        current_model = getattr(
            getattr(self.config, "ollama", None), "model", ""
        ) or ""
        current_model = canonicalize_model_name(current_model)

        scored = []
        for name, meta in WORK_ONLY_MODELS.items():
            score = uc_score(meta["tier_eng"], meta["tier_gen"], uc_key)
            role = ""
            if name == rec_primary:
                role = "primary"
            elif name == rec_alt:
                role = "alt"
            elif name == rec.get("upgrade", ""):
                role = "upgrade"
            scored.append({
                "name": name,
                "role": role,
                "tier_eng": meta["tier_eng"],
                "tier_gen": meta["tier_gen"],
                "score": score,
                "vram_gb": meta.get("vram_gb", "?"),
                "note": meta.get("note", ""),
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        for m in scored:
            tags = ()
            if m["name"] == rec_primary:
                tags = ("primary",)

            self.tree.insert("", tk.END, iid=m["name"], values=(
                m["name"], m["role"],
                m["tier_eng"], m["tier_gen"], m["score"],
                m["vram_gb"], m["note"],
            ), tags=tags)

        # Select current model in tree
        if current_model and current_model in [c["name"] for c in scored]:
            self._suppress_select_event = True
            try:
                self.tree.selection_set(current_model)
                self.tree.see(current_model)
            finally:
                self._suppress_select_event = False

        t = current_theme()
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            suffix = " (offline catalog; inactive in online mode)"
        else:
            suffix = ""
        self.status_label.config(
            text="{} approved models. Current: {}{}".format(
                len(scored), current_model or "(none)", suffix),
            fg=t["fg"],
        )

    def _on_select(self, event=None):
        """Write selected model to config.ollama.model with Ollama health check."""
        if getattr(self, "_suppress_select_event", False):
            return
        sel = self.tree.selection()
        if not sel:
            return
        model_name = canonicalize_model_name(sel[0])
        t = current_theme()
        base = sanitize_ollama_base_url(
            getattr(getattr(self.config, "ollama", None), "base_url", "")
        )

        # Verify model exists in Ollama before accepting
        try:
            import httpx
            from src.core.network_gate import get_gate
            get_gate().check_allowed(
                "{}/api/tags".format(base),
                "ollama_model_verify", "gui_admin",
            )
            r = httpx.get(
                "{}/api/tags".format(base),
                timeout=5,
                proxy=None,
                trust_env=False,
            )
            r.raise_for_status()
            available = [m.get("name") for m in r.json().get("models", [])]
            if model_name not in available:
                fallback = resolve_ollama_model_name(model_name, available)
                if fallback in available:
                    self.status_label.config(
                        text="[WARN] {} not found, using {}".format(model_name, fallback),
                        fg=t["orange"])
                    try:
                        from src.gui.app_context import get_controller
                        from src.gui.core.events import make_event
                        ctrl = get_controller()
                        ctrl._emit(make_event("model_fallback", ctrl.diag.run_id,
                                              requested=model_name, fallback=fallback,
                                              reason="exact tag not in Ollama"))
                    except Exception:
                        pass
                    model_name = canonicalize_model_name(fallback)
                else:
                    self.status_label.config(
                        text="[FAIL] {} not in Ollama. Run: ollama pull {}".format(
                            model_name, model_name), fg=t["red"])
                    try:
                        from src.gui.app_context import get_controller
                        from src.gui.core.events import make_event
                        ctrl = get_controller()
                        ctrl._emit(make_event("model_missing", ctrl.diag.run_id,
                                              requested=model_name,
                                              available=available,
                                              reason="not found in Ollama /api/tags"))
                    except Exception:
                        pass
                    return
        except Exception as e:
            self.status_label.config(
                text="[WARN] Ollama check failed: {}. Setting anyway.".format(str(e)[:60]),
                fg=t["orange"])

        # Update in-memory config
        ollama = getattr(self.config, "ollama", None)
        if ollama:
            ollama.model = model_name
            ollama.base_url = base

        # Persist to YAML so it survives restart
        try:
            from src.gui.helpers.mode_tuning import update_mode_section

            update_mode_section(self.config, "offline", "ollama", "model", model_name)
            update_mode_section(self.config, "offline", "ollama", "base_url", base)
            logger.info("[OK] Offline model persisted: %s", model_name)
        except Exception as e:
            logger.warning("[WARN] Could not persist model to YAML: %s", e)

        # Notify status bar to refresh
        app = self._app
        if app and hasattr(app, "status_bar"):
            try:
                app.status_bar.force_refresh()
            except Exception:
                pass

        self.status_label.config(
            text="Selected: {} (saved)".format(model_name), fg=t["fg"])

    # ------------------------------------------------------------------
    # Model Download Dialog
    # ------------------------------------------------------------------

    def _query_ollama_models(self):
        """Return list of installed Ollama model names, or None on error."""
        try:
            import httpx
            from src.core.network_gate import get_gate
            base = sanitize_ollama_base_url(
                getattr(
                    getattr(self.config, "ollama", None), "base_url",
                    "http://127.0.0.1:11434",
                )
            )
            get_gate().check_allowed(
                "{}/api/tags".format(base),
                "ollama_tags_query", "gui_admin",
            )
            r = httpx.get("{}/api/tags".format(base), timeout=5, proxy=None, trust_env=False)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
        except Exception as e:
            logger.warning("[WARN] Ollama tags query failed: %s", e)
            return None

    def _open_download_dialog(self):
        """Open a dialog showing installed vs missing approved models."""
        t = current_theme()
        self._dl_status.config(text="Checking Ollama...", fg=t["gray"])
        self.update_idletasks()

        installed = self._query_ollama_models()
        if installed is None:
            self._dl_status.config(
                text="[FAIL] Cannot reach Ollama", fg=t["red"])
            return

        from scripts._model_meta import WORK_ONLY_MODELS

        # Normalize installed names for matching (strip :latest tag)
        installed_bases = set()
        for m in installed:
            installed_bases.add(m)
            if ":" in m:
                installed_bases.add(m.split(":")[0])

        missing = []
        present = []
        for name in WORK_ONLY_MODELS:
            base = name.split(":")[0]
            if name in installed_bases or base in installed_bases:
                present.append(name)
            else:
                missing.append(name)

        self._dl_status.config(
            text="{} installed, {} missing".format(len(present), len(missing)),
            fg=t["fg"] if not missing else t.get("orange", "#e8a838"),
        )

        # Build dialog
        dlg = tk.Toplevel(self)
        dlg.title("Model Manager")
        dlg.configure(bg=t["panel_bg"])
        dlg.geometry("520x420")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        tk.Label(
            dlg, text="Approved Offline Models",
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        ).pack(pady=(12, 4))

        # Installed section
        tk.Label(
            dlg, text="Installed ({})".format(len(present)),
            bg=t["panel_bg"], fg=t.get("green", "#4ec96f"), font=FONT,
            anchor=tk.W,
        ).pack(fill=tk.X, padx=16, pady=(8, 2))

        for name in present:
            tk.Label(
                dlg, text="  [OK] {}".format(name), anchor=tk.W,
                bg=t["panel_bg"], fg=t["fg"], font=FONT_MONO,
            ).pack(fill=tk.X, padx=16)

        # Missing section
        if missing:
            tk.Label(
                dlg, text="Missing ({})".format(len(missing)),
                bg=t["panel_bg"], fg=t.get("orange", "#e8a838"), font=FONT,
                anchor=tk.W,
            ).pack(fill=tk.X, padx=16, pady=(12, 2))

            for name in missing:
                row = tk.Frame(dlg, bg=t["panel_bg"])
                row.pack(fill=tk.X, padx=16, pady=1)
                tk.Label(
                    row, text="  [--] {}".format(name), anchor=tk.W,
                    bg=t["panel_bg"], fg=t["gray"], font=FONT_MONO,
                ).pack(side=tk.LEFT)

            # Pull all missing button
            tk.Label(
                dlg, text="To install missing models, run in terminal:",
                bg=t["panel_bg"], fg=t["fg"], font=FONT_SMALL,
                anchor=tk.W,
            ).pack(fill=tk.X, padx=16, pady=(12, 2))

            cmds = "\n".join("ollama pull {}".format(m) for m in missing)
            cmd_box = tk.Text(
                dlg, height=min(len(missing) + 1, 6), wrap=tk.NONE,
                bg=t.get("entry_bg", "#1e1e1e"), fg=t["fg"], font=FONT_MONO,
                relief=tk.FLAT, padx=8, pady=4,
            )
            cmd_box.pack(fill=tk.X, padx=16, pady=(0, 4))
            cmd_box.insert("1.0", cmds)
            cmd_box.config(state=tk.DISABLED)

            def _pull_all():
                """Pull all missing models in background thread."""
                pull_btn.config(state=tk.DISABLED, text="Pulling...")
                pull_status.config(text="Starting downloads...", fg=t["fg"])
                dlg.update_idletasks()

                def _worker():
                    """Plain-English: This function handles worker."""
                    import subprocess
                    from src.gui.helpers.safe_after import safe_after
                    results = []
                    for i, model in enumerate(missing):
                        try:
                            safe_after(dlg, 0, lambda m=model, n=i: pull_status.config(
                                text="Pulling {}/{}: {}...".format(
                                    n + 1, len(missing), m)))
                            subprocess.run(
                                ["ollama", "pull", model],
                                capture_output=True, text=True, timeout=600,
                            )
                            results.append((model, True))
                        except Exception as e:
                            results.append((model, False))
                            logger.warning("[WARN] ollama pull %s failed: %s",
                                           model, e)

                    ok = sum(1 for _, s in results if s)
                    fail = len(results) - ok
                    msg = "Done: {} pulled".format(ok)
                    if fail:
                        msg += ", {} failed".format(fail)

                    def _finish():
                        """Plain-English: This function handles finish."""
                        pull_status.config(
                            text=msg,
                            fg=t.get("green", "#4ec96f") if not fail
                            else t.get("orange", "#e8a838"),
                        )
                        pull_btn.config(state=tk.NORMAL,
                                        text="Pull All Missing")
                        self._populate()  # refresh treeview

                    safe_after(dlg, 0, _finish)

                threading.Thread(target=_worker, daemon=True).start()

            pull_btn = tk.Button(
                dlg, text="Pull All Missing", command=_pull_all,
                bg=t["accent"], fg=t["accent_fg"], font=FONT,
                relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
            )
            pull_btn.pack(pady=(4, 2))
            bind_hover(pull_btn)

            pull_status = tk.Label(
                dlg, text="", anchor=tk.W,
                bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
            )
            pull_status.pack(fill=tk.X, padx=16)

        else:
            tk.Label(
                dlg, text="All approved models are installed!",
                bg=t["panel_bg"], fg=t.get("green", "#4ec96f"), font=FONT,
                anchor=tk.W,
            ).pack(fill=tk.X, padx=16, pady=(12, 2))

        # Close button
        tk.Button(
            dlg, text="Close", command=dlg.destroy,
            bg=t.get("inactive_btn_bg", "#333"), fg=t["fg"], font=FONT,
            relief=tk.FLAT, padx=16, pady=4,
        ).pack(pady=(8, 12))

    def apply_theme(self, t):
        """Plain-English: This function handles apply theme."""
        self.configure(bg=t["panel_bg"], fg=t["accent"])
        if t["name"] == "dark":
            self.tree.tag_configure("primary", background="#1a3a1a")
        else:
            self.tree.tag_configure("primary", background="#e8f5e9")
        _theme_widget(self, t)


# ====================================================================
# ApiAdminTab -- coordinator with four sections
# ====================================================================

class ApiAdminTab(tk.Frame):
    """
    Admin controller for mode defaults, profiles, credentials, paths, and models.

    Embeddable Frame -- placed inside the Settings notebook API & Admin tab.
    Runtime methods are bound from api_admin_tab_runtime.py.
    """

    def __init__(self, parent, config, app_ref):
        """Build all four admin sections inside a scrollable canvas.

        Args:
            parent: Parent tk widget (typically the SettingsView notebook).
            config: Live config object shared across the application.
            app_ref: Reference to HybridRAGApp for cross-panel coordination
                     (e.g. syncing tuning sliders after a defaults restore).
        """
        t = current_theme()
        super().__init__(parent, bg=t["panel_bg"])
        self.config = config
        self._app = app_ref
        self._dev_tuning_enabled = os.environ.get(
            "HYBRIDRAG_DEV_UI", ""
        ).strip().lower() in ("1", "true", "yes")

        # Scrollable container -- needed because all four sections together
        # are taller than the window.
        self._scroll = ScrollableFrame(self, bg=t["panel_bg"])
        self._scroll.pack(fill=tk.BOTH, expand=True)
        self._inner = self._scroll.inner

        # Build sections
        from src.gui.panels.tuning_tab import TuningTab

        self._mode_panel = TuningTab(
            self._inner,
            config=config,
            app_ref=app_ref,
            enable_mode_store=True,
        )
        self._mode_panel.pack(fill=tk.X, padx=16, pady=8)
        self._build_credentials_section(t)
        self._build_security_section(t)
        self._build_troubleshoot_section(t)
        self._build_query_debug_section(t)
        self._paths_panel = DataPathsPanel(self._inner, config, app_ref)
        self._paths_panel.pack(fill=tk.X, padx=16, pady=8)
        if self._dev_tuning_enabled:
            self._build_chunking_section(t)
        else:
            self._build_dev_hidden_notice(t)
        self._offline_model_panel = OfflineModelSelectionPanel(
            self._inner, config, app_ref)
        self._offline_model_panel.pack(fill=tk.X, padx=16, pady=8)
        self._model_panel = ModelSelectionPanel(
            self._inner, config, self.endpoint_var, self.key_var)
        self._model_panel.pack(fill=tk.X, padx=16, pady=8)

        # Load initial credential status
        self._refresh_credential_status()

        # Refresh mode-aware labels without disabling cross-mode editing.
        self._apply_mode_state()


    # ================================================================
    # SECTION A: API CREDENTIALS
    # ================================================================




    # ================================================================
    # SECTION A2: SECURITY & PRIVACY
    # ================================================================



    # ================================================================
    # SECTION A3: QUICK TROUBLESHOOT
    # ================================================================




    # ================================================================
    # SECTION C2: OFFLINE RUNTIME (OLLAMA)
    # ================================================================



    # ================================================================
    # MODE-AWARE FIELD STATE
    # ================================================================


    # ================================================================
    # SECTION C1: CHUNKING (RE-INDEX REQUIRED)
    # ================================================================



    # ================================================================
    # SECTION D: ADMIN DEFAULTS
    # ================================================================




    # ================================================================
    # THEME
    # ================================================================


# ---------------------------------------------------------------------------
# Bind runtime methods from companion module
# ---------------------------------------------------------------------------
bind_api_admin_tab_runtime_methods(ApiAdminTab)
