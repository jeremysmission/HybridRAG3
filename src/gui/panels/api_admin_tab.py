# ============================================================================
# HybridRAG v3 -- API & Admin Tab (src/gui/panels/api_admin_tab.py)    RevB
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
#   ApiAdminTab          -- coordinator Frame embedding all four sections
#
# INTERNET ACCESS:
#   Test Connection + Refresh Models: one GET to /models endpoint
#   All other operations: NONE
# ============================================================================

import tkinter as tk
from tkinter import ttk, filedialog
import json
import os
import threading
import logging
import re
import time
from datetime import datetime

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.scrollable import ScrollableFrame
from src.core.model_identity import canonicalize_model_name, resolve_ollama_model_name
from src.core.ollama_endpoint_resolver import sanitize_ollama_base_url
from src.security.credentials import (
    resolve_credentials, validate_endpoint,
    store_api_key, store_endpoint, clear_credentials,
    invalidate_credential_cache,
)

logger = logging.getLogger(__name__)

# --- MODULE CONSTANTS ---

# Path for admin defaults file (no secrets stored here -- safe to commit)
_DEFAULTS_PATH = os.path.join(
    os.environ.get("HYBRIDRAG_PROJECT_ROOT", "."),
    "config", "admin_defaults.json",
)


# --- THEME HELPER ---

def _theme_widget(widget, t):
    """Recursively apply theme to a widget and its children.

    Walks the entire widget tree starting from `widget` and sets
    background/foreground colors based on each widget's class.
    This is necessary because tk (not ttk) widgets do not inherit
    theme changes automatically -- each one must be touched manually.
    """
    try:
        wclass = widget.winfo_class()
        if wclass == "Frame":
            widget.configure(bg=t["panel_bg"])
        elif wclass == "Label":
            widget.configure(bg=t["panel_bg"], fg=t["fg"])
        elif wclass == "Entry":
            widget.configure(bg=t["input_bg"], fg=t["input_fg"])
        elif wclass == "Button":
            widget.configure(bg=t["accent"], fg=t["accent_fg"])
        elif wclass == "Checkbutton":
            widget.configure(
                bg=t["panel_bg"], fg=t["fg"],
                selectcolor=t["input_bg"],
                activebackground=t["panel_bg"],
                activeforeground=t["fg"])
    except Exception:
        pass
    for child in widget.winfo_children():
        _theme_widget(child, t)


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
        t = current_theme()
        self.status_label.config(text="Selected: {}".format(model_id), fg=t["fg"])

    # -- Theme --

    def apply_theme(self, t):
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
        t = current_theme()
        super().__init__(parent, text="Offline Model Selection", padx=16, pady=8,
                         bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD)
        self.config = config
        self._app = app_ref
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
        from scripts._model_meta import USE_CASES
        label = self.uc_var.get()
        for k, uc in USE_CASES.items():
            if uc["label"] == label:
                return k
        return "sw"

    def _on_uc_change(self, event=None):
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

        # Legacy cleanup: older sessions stored phi4-mini as the default
        # offline model. Normalize to the approved primary default so the
        # admin panel does not appear to regress to a stale baseline.
        if current_model in ("phi4-mini", "phi4-mini:latest"):
            current_model = "phi4:14b-q4_K_M"
            try:
                ollama = getattr(self.config, "ollama", None)
                if ollama:
                    ollama.model = current_model
                from src.core.config import save_config_field
                save_config_field("ollama.model", current_model)
            except Exception:
                pass

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
            self.tree.selection_set(current_model)
            self.tree.see(current_model)

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
            from src.core.config import save_config_field
            save_config_field("ollama.model", model_name)
            save_config_field("ollama.base_url", base)
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
        self.configure(bg=t["panel_bg"], fg=t["accent"])
        if t["name"] == "dark":
            self.tree.tag_configure("primary", background="#1a3a1a")
        else:
            self.tree.tag_configure("primary", background="#e8f5e9")
        _theme_widget(self, t)


# ====================================================================
# Module-level helper -- config snapshot (no widget state needed)
# ====================================================================

def _capture_config_snapshot(config):
    """Build a JSON-serializable dict of all current admin settings.

    This snapshot captures paths, retrieval params, API params, Ollama
    model, and mode -- everything needed to fully restore the system
    to its current state later.  Saved to config/admin_defaults.json.

    Args:
        config: Live config object shared across the application.

    Returns:
        dict: Flat snapshot suitable for JSON serialization.
    """
    retrieval = getattr(config, "retrieval", None)
    api = getattr(config, "api", None)
    ollama = getattr(config, "ollama", None)
    paths = getattr(config, "paths", None)
    return {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "paths": {
            "source_folder": getattr(paths, "source_folder", "") if paths else "",
            "database": getattr(paths, "database", "") if paths else "",
            "embeddings_cache": getattr(paths, "embeddings_cache", "") if paths else "",
        },
        "retrieval": {
            "top_k": getattr(retrieval, "top_k", 8) if retrieval else 8,
            "min_score": getattr(retrieval, "min_score", 0.20) if retrieval else 0.20,
            "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
            "reranker_enabled": getattr(retrieval, "reranker_enabled", False) if retrieval else False,
        },
        "chunking": {
            "chunk_size": getattr(getattr(config, "chunking", None), "chunk_size", 1200),
            "overlap": getattr(getattr(config, "chunking", None), "overlap", 200),
        },
        "api": {
            "model": getattr(api, "model", "") if api else "",
            "max_tokens": getattr(api, "max_tokens", 2048) if api else 2048,
            "temperature": getattr(api, "temperature", 0.1) if api else 0.1,
            "timeout_seconds": getattr(api, "timeout_seconds", 30) if api else 30,
        },
        "ollama": {
            "model": getattr(ollama, "model", "") if ollama else "",
        },
        "mode": getattr(config, "mode", "offline"),
    }


# ====================================================================
# ApiAdminTab -- coordinator with four sections
# ====================================================================

class ApiAdminTab(tk.Frame):
    """
    API credentials, data paths, online model selection, admin defaults.

    Embeddable Frame -- placed inside the Settings notebook API & Admin tab.
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

        # Scrollable container -- needed because all four sections together
        # are taller than the window.
        self._scroll = ScrollableFrame(self, bg=t["panel_bg"])
        self._scroll.pack(fill=tk.BOTH, expand=True)
        self._inner = self._scroll.inner

        # Build sections
        self._build_credentials_section(t)
        self._build_security_section(t)
        self._build_troubleshoot_section(t)
        self._paths_panel = DataPathsPanel(self._inner, config, app_ref)
        self._paths_panel.pack(fill=tk.X, padx=16, pady=8)
        self._build_chunking_section(t)
        self._offline_model_panel = OfflineModelSelectionPanel(
            self._inner, config, app_ref)
        self._offline_model_panel.pack(fill=tk.X, padx=16, pady=8)
        self._model_panel = ModelSelectionPanel(
            self._inner, config, self.endpoint_var, self.key_var)
        self._model_panel.pack(fill=tk.X, padx=16, pady=8)
        self._build_defaults_section(t)

        # Load initial credential status
        self._refresh_credential_status()

        # Gray out API fields if starting in offline mode
        self._apply_mode_state()

    # ================================================================
    # SECTION A: API CREDENTIALS
    # ================================================================

    def _build_credentials_section(self, t):
        """Build API credential entry fields and action buttons."""
        frame = tk.LabelFrame(
            self._inner, text="API Credentials", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=(8, 4))
        self._cred_frame = frame

        # Endpoint URL
        row_ep = tk.Frame(frame, bg=t["panel_bg"])
        row_ep.pack(fill=tk.X, pady=4)
        tk.Label(
            row_ep, text="Endpoint URL:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)
        self.endpoint_var = tk.StringVar()
        self.endpoint_entry = tk.Entry(
            row_ep, textvariable=self.endpoint_var, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        )
        self.endpoint_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # API Key
        row_key = tk.Frame(frame, bg=t["panel_bg"])
        row_key.pack(fill=tk.X, pady=4)
        tk.Label(
            row_key, text="API Key:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(
            row_key, textvariable=self.key_var, show="*", font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        )
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        self._key_visible = False
        # Security-first default: do not allow API key reveal in an
        # unprotected Admin screen. To intentionally re-enable reveal:
        #   HYBRIDRAG_ALLOW_KEY_REVEAL=1
        allow_key_reveal = os.environ.get(
            "HYBRIDRAG_ALLOW_KEY_REVEAL", ""
        ).strip().lower() in ("1", "true", "yes")
        self.toggle_key_btn = tk.Button(
            row_key,
            text="Show" if allow_key_reveal else "Reveal Locked",
            width=11,
            font=FONT_SMALL,
            command=self._toggle_key_visibility if allow_key_reveal else None,
            state=tk.NORMAL if allow_key_reveal else tk.DISABLED,
            bg=t["input_bg"], fg=t["fg"], relief=tk.FLAT, bd=0,
        )
        self.toggle_key_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Button row
        btn_row = tk.Frame(frame, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=(8, 4))

        self.save_cred_btn = tk.Button(
            btn_row, text="Save Credentials", command=self._on_save_credentials,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.save_cred_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.save_cred_btn)

        # Safety-first default: hide manual connection test button to prevent
        # accidental clicks that can disrupt live demo state.
        #
        # To re-enable intentionally, set:
        #   HYBRIDRAG_ENABLE_CONN_TEST=1
        allow_conn_test = os.environ.get(
            "HYBRIDRAG_ENABLE_CONN_TEST", ""
        ).strip().lower() in ("1", "true", "yes")
        self.test_btn = tk.Button(
            btn_row, text="Test Connection", command=self._on_test_connection,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        if allow_conn_test:
            self.test_btn.pack(side=tk.LEFT, padx=(0, 8))
            bind_hover(self.test_btn)
        else:
            self.test_btn.config(state=tk.DISABLED)
            self.test_disabled_label = tk.Label(
                btn_row, text="Connection test hidden (safety mode)",
                anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
            )
            self.test_disabled_label.pack(side=tk.LEFT, padx=(0, 8))

        self.clear_cred_btn = tk.Button(
            btn_row, text="Clear Credentials", command=self._on_clear_credentials,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
        )
        self.clear_cred_btn.pack(side=tk.LEFT)
        bind_hover(self.clear_cred_btn)

        # Status label
        self.cred_status_label = tk.Label(
            frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.cred_status_label.pack(fill=tk.X, pady=(2, 0))

        # Plain-English network policy line for non-technical users.
        self.network_policy_label = tk.Label(
            frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["label_fg"], font=FONT_SMALL,
            justify=tk.LEFT, wraplength=1,
        )
        self.network_policy_label.pack(fill=tk.X, pady=(2, 0))
        self.network_policy_label.bind(
            "<Configure>",
            lambda e: e.widget.config(wraplength=max(200, e.width - 8)),
        )
        self._refresh_network_policy_label()

    def _toggle_key_visibility(self):
        """Toggle between masked (****) and plain-text API key display."""
        self._key_visible = not self._key_visible
        if self._key_visible:
            self.key_entry.config(show="")
            self.toggle_key_btn.config(text="Hide")
        else:
            self.key_entry.config(show="*")
            self.toggle_key_btn.config(text="Show")

    def _refresh_credential_status(self):
        """Load current credential status and pre-populate fields."""
        try:
            creds = resolve_credentials()
            if creds.endpoint:
                self.endpoint_var.set(creds.endpoint)
            if creds.api_key:
                self.key_var.set(creds.api_key)

            def _source_label(raw):
                src = (raw or "?").strip()
                if src.lower() == "keyring":
                    return "Credential Manager"
                return src

            parts = []
            if creds.has_key:
                parts.append("Key: {} (from {})".format(
                    creds.key_preview, _source_label(creds.source_key)))
            else:
                parts.append("Key: NOT SET")
            if creds.has_endpoint:
                parts.append("Endpoint: SET (from {})".format(
                    _source_label(creds.source_endpoint)))
            else:
                parts.append("Endpoint: NOT SET")

            t = current_theme()
            color = t["green"] if creds.is_online_ready else t["orange"]
            self.cred_status_label.config(text="  |  ".join(parts), fg=color)
            self._refresh_network_policy_label()
        except Exception as e:
            logger.warning("Could not load credential status: %s", e)
            self.cred_status_label.config(
                text="[WARN] Could not load status: {}".format(str(e)[:60]),
                fg=current_theme()["red"],
            )
            self._refresh_network_policy_label()

    def _refresh_network_policy_label(self):
        """Show current gate policy in plain language."""
        t = current_theme()
        mode = getattr(self.config, "mode", "offline") if self.config else "offline"
        gate_mode = ""
        try:
            from src.core.network_gate import get_gate
            gate_mode = (get_gate().mode_name or "").strip().lower()
        except Exception:
            gate_mode = ""

        effective = gate_mode or mode
        if effective == "online":
            text = "Network Policy: Online Mode = Whitelist Only (approved endpoint + localhost)"
            color = t["green"]
        else:
            text = "Network Policy: Offline Mode = Localhost Only (internet blocked)"
            color = t["gray"]
        if gate_mode and gate_mode != mode:
            text = "{} | Effective Gate: {}".format(text, gate_mode.upper())
            color = t["orange"]
        self.network_policy_label.config(text=text, fg=color)

    def _on_save_credentials(self):
        """Save endpoint and API key to credential manager."""
        t = current_theme()
        endpoint = self.endpoint_var.get().strip()
        key = self.key_var.get().strip()
        if not endpoint and not key:
            self.cred_status_label.config(
                text="[WARN] Nothing to save -- both fields are empty.",
                fg=t["orange"])
            return
        errors = []
        if endpoint:
            try:
                endpoint = validate_endpoint(endpoint)
                store_endpoint(endpoint)
                self.endpoint_var.set(endpoint)
            except Exception as e:
                errors.append("Endpoint: {}".format(str(e)[:60]))
        if key:
            try:
                store_api_key(key)
            except Exception as e:
                errors.append("Key: {}".format(str(e)[:60]))
        if errors:
            self.cred_status_label.config(
                text="[FAIL] {}".format("; ".join(errors)), fg=t["red"])
        else:
            self.cred_status_label.config(
                text="[OK] Credentials saved to Credential Manager.",
                fg=t["green"])
            self._refresh_credential_status()

    def _on_test_connection(self):
        """Test API connection in a background thread."""
        t = current_theme()
        endpoint = self.endpoint_var.get().strip()
        key = self.key_var.get().strip()
        if not endpoint or not key:
            self.cred_status_label.config(
                text="[WARN] Enter endpoint and key before testing.",
                fg=t["orange"])
            return
        self.test_btn.config(state=tk.DISABLED)
        self.cred_status_label.config(text="Testing connection...", fg=t["gray"])
        threading.Thread(target=self._do_test_connection,
                         args=(endpoint, key), daemon=True).start()

    def _do_test_connection(self, endpoint, key):
        """Background thread: verify the endpoint by fetching its model list.

        A successful model fetch proves the endpoint URL is correct and the
        API key has valid permissions.  As a bonus, the fetched models are
        forwarded to the model selection panel so the admin sees them
        immediately without clicking Refresh again.
        """
        from src.gui.helpers.safe_after import safe_after
        try:
            # Test what the app will really use: persist creds, resolve fresh,
            # then run provider-aware discovery (Azure deployments or /models).
            from src.core.llm_router import (
                invalidate_deployment_cache,
                refresh_deployments,
                _build_httpx_client,
                _is_azure_endpoint,
            )
            endpoint = validate_endpoint(endpoint)
            store_endpoint(endpoint)
            store_api_key(key)
            invalidate_credential_cache()
            creds = resolve_credentials(use_cache=False)
            # Ensure endpoint probe runs with online gate policy, using the
            # same allowlist config as normal online query traffic.
            try:
                from src.core.network_gate import configure_gate
                configure_gate(
                    mode="online",
                    api_endpoint=creds.endpoint or endpoint,
                    allowed_prefixes=getattr(
                        getattr(self.config, "api", None),
                        "allowed_endpoint_prefixes", [],
                    ) if self.config else [],
                )
            except Exception:
                pass
            cfg_api = getattr(self.config, "api", None)
            cfg_dep = (getattr(cfg_api, "deployment", "") or "").strip() if cfg_api else ""
            cfg_model = (getattr(cfg_api, "model", "") or "").strip() if cfg_api else ""
            cfg_ver = (getattr(cfg_api, "api_version", "") or "").strip() if cfg_api else ""
            cfg_provider = (getattr(cfg_api, "provider", "") or "").strip() if cfg_api else ""

            if not creds.has_endpoint or not creds.has_key:
                safe_after(
                    self, 0, self._test_failed,
                    "Credentials not stored/resolved correctly",
                )
                return

            # Stage 1: connectivity/auth probe with explicit HTTP status.
            probe_ok, probe_msg = self._probe_online_endpoint(
                creds.endpoint or endpoint,
                creds.api_key or key,
                creds.api_version or "2024-02-02",
                _build_httpx_client,
                _is_azure_endpoint,
            )
            if not probe_ok:
                if "HTTP 500" in probe_msg:
                    # Some Azure environments block/alter deployment listing
                    # but still allow chat completions. Try a direct model call.
                    chat_ok, chat_msg = self._probe_online_chat(
                        creds,
                        deployment_override=(cfg_dep or cfg_model),
                        api_version_override=cfg_ver,
                        provider_override=cfg_provider,
                    )
                    if chat_ok:
                        safe_after(
                            self, 0, self._test_done, [], 0,
                            chat_msg + " | Deployment listing unavailable",
                        )
                        return
                    # Keep this as a warning, not a hard fail. In many
                    # enterprise Azure environments, deployment listing
                    # returns 500 while chat calls remain the real signal.
                    safe_after(
                        self, 0, self._test_warn,
                        "{} | {}".format(probe_msg, chat_msg),
                    )
                    return
                safe_after(self, 0, self._test_failed, probe_msg)
                return

            # Stage 2: model/deployment discovery (may legitimately return 0).
            invalidate_deployment_cache()
            deployments = refresh_deployments()
            if deployments:
                models = self._deployments_to_models(deployments)
                safe_after(
                    self, 0, self._test_done, models, len(deployments), probe_msg
                )
            else:
                safe_after(
                    self, 0, self._test_done, [], 0,
                    probe_msg + " | Connected, but no deployments visible",
                )
        except Exception as e:
            safe_after(self, 0, self._test_failed, str(e)[:80])

    def _probe_online_endpoint(
        self, endpoint, api_key, api_version, client_factory, is_azure_endpoint,
    ):
        """Probe endpoint with provider-appropriate auth and return status text."""
        try:
            ep = (endpoint or "").rstrip("/")
            if is_azure_endpoint(ep):
                base = re.split(r"/openai/|\?", ep, maxsplit=1)[0]
                url = f"{base}/openai/deployments?api-version={api_version}"
                with client_factory(timeout=10) as client:
                    resp = client.get(
                        url,
                        headers={
                            "api-key": api_key,
                            "Content-Type": "application/json",
                        },
                    )
                if resp.status_code == 200:
                    return True, "Connected (Azure endpoint reachable)"
                if resp.status_code in (401, 403):
                    return False, f"Auth/RBAC failed (HTTP {resp.status_code})"
                if resp.status_code == 404:
                    return False, "Endpoint/API version not valid for Azure deployment list (HTTP 404)"
                return False, f"Azure probe failed (HTTP {resp.status_code})"

            url = f"{ep}/models"
            with client_factory(timeout=10) as client:
                resp = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 200:
                return True, "Connected (/models reachable)"
            if resp.status_code in (401, 403):
                return False, f"Auth failed (HTTP {resp.status_code})"
            if resp.status_code == 404:
                return False, "Endpoint path is not OpenAI-compatible /models (HTTP 404)"
            return False, f"Probe failed (HTTP {resp.status_code})"
        except Exception as e:
            return False, f"Connection probe error: {type(e).__name__}: {e}"

    def _probe_online_chat(
        self,
        creds,
        deployment_override="",
        api_version_override="",
        provider_override="",
    ):
        """Fallback probe: run one minimal online completion call."""
        try:
            from src.core.llm_router import APIRouter

            dep = (
                deployment_override
                or getattr(creds, "deployment", "")
                or getattr(getattr(self.config, "api", None), "deployment", "")
                or getattr(getattr(self.config, "api", None), "model", "")
                or ""
            )
            ver = (
                api_version_override
                or getattr(creds, "api_version", "")
                or getattr(getattr(self.config, "api", None), "api_version", "")
                or ""
            )
            provider = (
                provider_override
                or getattr(creds, "provider", "")
                or getattr(getattr(self.config, "api", None), "provider", "")
                or ""
            )
            api = APIRouter(
                self.config,
                creds.api_key or "",
                endpoint=creds.endpoint or "",
                deployment_override=dep,
                api_version_override=ver,
                provider_override=provider,
            )

            # Azure requires a deployment name for chat completions.
            if getattr(api, "is_azure", False) and not getattr(api, "deployment", ""):
                return False, "Azure chat probe needs deployment name (not set)"

            resp = api.query("Reply with OK.")
            if resp and (resp.text or "").strip():
                return True, "Connected (chat completion probe succeeded)"

            err = getattr(api, "last_error", "") or "unknown error"
            return False, "Chat probe failed: {}".format(str(err)[:120])
        except Exception as e:
            return False, "Chat probe error: {}: {}".format(type(e).__name__, str(e)[:80])

    def _deployments_to_models(self, deployments):
        """Convert deployment names into ModelSelectionPanel row dicts."""
        from scripts._model_meta import lookup_known_model
        out = []
        for dep in deployments:
            kb = lookup_known_model(dep) or {}
            out.append({
                "id": dep,
                "ctx": kb.get("ctx", 0),
                "price_in": kb.get("price_in", 0),
                "price_out": kb.get("price_out", 0),
                "tier_eng": kb.get("tier_eng", 45),
                "tier_gen": kb.get("tier_gen", 45),
                "source": "discovery",
            })
        return out

    def _test_done(self, models, total, detail=""):
        """Main-thread callback: connection test succeeded."""
        t = current_theme()
        msg = detail or "Connected"
        if total > 0:
            msg = "{} -- {} models available.".format(msg, total)
        else:
            msg = "{} -- 0 models/deployments listed.".format(msg)
        self.cred_status_label.config(text="[OK] {}".format(msg), fg=t["green"])
        self.test_btn.config(state=tk.NORMAL)
        self._model_panel.set_models(models)

    def _test_failed(self, msg):
        """Main-thread callback: connection test failed."""
        t = current_theme()
        self.cred_status_label.config(text="[FAIL] {}".format(msg), fg=t["red"])
        self.test_btn.config(state=tk.NORMAL)

    def _test_warn(self, msg):
        """Main-thread callback: connection test has non-fatal warnings."""
        t = current_theme()
        self.cred_status_label.config(text="[WARN] {}".format(msg), fg=t["orange"])
        self.test_btn.config(state=tk.NORMAL)

    def _on_clear_credentials(self):
        """Wipe all stored credentials from Windows Credential Manager."""
        t = current_theme()
        try:
            clear_credentials()
            self.endpoint_var.set("")
            self.key_var.set("")
            self._model_panel.set_models([])
            self.cred_status_label.config(
                text="[OK] All credentials cleared.", fg=t["green"])
        except Exception as e:
            self.cred_status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"])

    # ================================================================
    # SECTION A2: SECURITY & PRIVACY
    # ================================================================

    def _build_security_section(self, t):
        """Build security toggle for PII scrubbing.

        One Checkbutton that controls whether emails, phone numbers,
        SSNs, credit cards, and IP addresses are stripped from prompts
        before they leave the machine via online API calls.
        """
        frame = tk.LabelFrame(
            self._inner, text="Security & Privacy", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._security_frame = frame

        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X, pady=4)

        # Read current value from config
        security = getattr(self.config, "security", None)
        initial = getattr(security, "pii_sanitization", True) if security else True

        self._pii_var = tk.BooleanVar(value=initial)
        self._pii_cb = tk.Checkbutton(
            row, text="PII Scrubber", variable=self._pii_var,
            command=self._on_pii_toggle,
            bg=t["panel_bg"], fg=t["fg"],
            selectcolor=t["input_bg"], activebackground=t["panel_bg"],
            activeforeground=t["fg"], font=FONT,
        )
        self._pii_cb.pack(side=tk.LEFT)

        self._pii_hint = tk.Label(
            row,
            text="Strips emails, phones, SSNs before sending to online APIs",
            anchor=tk.W, bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._pii_hint.pack(side=tk.LEFT, padx=(8, 0))

    def _on_pii_toggle(self):
        """Write PII sanitization toggle to config and persist to YAML."""
        value = self._pii_var.get()

        # Update live config object
        security = getattr(self.config, "security", None)
        if security:
            security.pii_sanitization = value

        # Persist to user_overrides.yaml (not default_config)
        try:
            from src.core.config import save_config_field
            save_config_field("security.pii_sanitization", value)
        except Exception as e:
            logger.warning("pii_toggle_save_failed: %s", e)

    # ================================================================
    # SECTION A3: QUICK TROUBLESHOOT
    # ================================================================

    def _build_troubleshoot_section(self, t):
        """Build quick verification controls (manual, on-demand)."""
        frame = tk.LabelFrame(
            self._inner, text="Quick Troubleshoot", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=8)
        self._trouble_frame = frame

        row = tk.Frame(frame, bg=t["panel_bg"])
        row.pack(fill=tk.X, pady=(0, 4))

        self._verify_btn = tk.Button(
            row, text="Run Quick Verification",
            command=self._on_run_quick_verify,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self._verify_btn.pack(side=tk.LEFT)
        bind_hover(self._verify_btn)

        self._verify_status = tk.Label(
            row, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self._verify_status.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        self._verify_text = tk.Text(
            frame, height=7, wrap=tk.WORD, font=FONT_MONO,
            bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=1,
            state=tk.DISABLED,
        )
        self._verify_text.pack(fill=tk.X)

    def _on_run_quick_verify(self):
        """Start quick verification in a background thread."""
        t = current_theme()
        self._verify_btn.config(state=tk.DISABLED)
        self._verify_status.config(text="Running checks...", fg=t["gray"])
        self._set_verify_text("Running quick verification...\n")
        threading.Thread(target=self._do_quick_verify, daemon=True).start()

    def _do_quick_verify(self):
        """Background thread: run fast wiring checks used for troubleshooting."""
        from src.gui.helpers.safe_after import safe_after

        checks = []
        started = time.time()

        def _ok(msg):
            checks.append(("OK", msg))

        def _warn(msg):
            checks.append(("WARN", msg))

        def _fail(msg):
            checks.append(("FAIL", msg))

        try:
            mode = getattr(self.config, "mode", "offline")
            _ok("Mode: {}".format(mode))

            # Path integrity checks
            paths = getattr(self.config, "paths", None)
            source = getattr(paths, "source_folder", "") if paths else ""
            db = getattr(paths, "database", "") if paths else ""
            dl = getattr(paths, "download_folder", "") if paths else ""

            if source and os.path.isdir(source):
                _ok("Source path exists")
            else:
                _warn("Source path missing or not set")

            if db:
                db_dir = os.path.dirname(db)
                if os.path.isdir(db_dir):
                    _ok("Index directory exists")
                else:
                    _warn("Index directory missing")
                if os.path.isfile(db):
                    _ok("Index DB file exists")
                else:
                    _warn("Index DB file missing")
            else:
                _warn("Index DB path not set")

            emb = getattr(paths, "embeddings_cache", "") if paths else ""
            if emb and os.path.isdir(emb):
                _ok("Embeddings cache exists")
            elif emb:
                _warn("Embeddings cache folder missing")

            if dl:
                if os.path.isdir(dl):
                    _ok("Download folder exists")
                else:
                    _warn("Download folder missing")

            # Credential + endpoint checks
            invalidate_credential_cache()
            creds = resolve_credentials(use_cache=False)
            if creds.has_key:
                _ok("API key resolved ({})".format(creds.source_key or "unknown"))
            else:
                _warn("API key not resolved")
            if creds.has_endpoint:
                _ok("API endpoint resolved ({})".format(creds.source_endpoint or "unknown"))
            else:
                _warn("API endpoint not resolved")

            # Backend checks by mode
            if mode == "online":
                if creds.has_key and creds.has_endpoint:
                    try:
                        from src.core.llm_router import (
                            invalidate_deployment_cache,
                            refresh_deployments,
                        )
                        invalidate_deployment_cache()
                        deps = refresh_deployments()
                        _ok("Online discovery returned {} deployments/models".format(len(deps)))
                    except Exception as e:
                        _fail("Online discovery failed: {}".format(str(e)[:80]))
                else:
                    _fail("Online mode active but credentials are incomplete")
            else:
                try:
                    from src.core.llm_router import _build_httpx_client
                    base = sanitize_ollama_base_url(
                        getattr(getattr(self.config, "ollama", None), "base_url", "")
                    )
                    with _build_httpx_client(timeout=5, localhost_only=True) as client:
                        resp = client.get(base, timeout=5)
                    if resp.status_code == 200:
                        _ok("Ollama reachable at {}".format(base))
                    else:
                        _warn("Ollama probe HTTP {}".format(resp.status_code))
                except Exception as e:
                    _warn("Ollama probe failed: {}".format(str(e)[:80]))

        except Exception as e:
            _fail("Verifier error: {}: {}".format(type(e).__name__, str(e)[:80]))

        elapsed_ms = int((time.time() - started) * 1000)
        safe_after(self, 0, self._on_quick_verify_done, checks, elapsed_ms)

    def _on_quick_verify_done(self, checks, elapsed_ms):
        """Render quick verification results in the admin tab."""
        t = current_theme()
        ok_n = sum(1 for c, _ in checks if c == "OK")
        warn_n = sum(1 for c, _ in checks if c == "WARN")
        fail_n = sum(1 for c, _ in checks if c == "FAIL")
        if fail_n > 0:
            color = t["red"]
        elif warn_n > 0:
            color = t["orange"]
        else:
            color = t["green"]
        self._verify_status.config(
            text="{} OK | {} WARN | {} FAIL | {} ms".format(
                ok_n, warn_n, fail_n, elapsed_ms,
            ),
            fg=color,
        )
        lines = []
        for level, msg in checks:
            lines.append("[{}] {}".format(level, msg))
        self._set_verify_text("\n".join(lines))
        self._verify_btn.config(state=tk.NORMAL)

    def _set_verify_text(self, text):
        """Set troubleshoot text box content safely."""
        self._verify_text.config(state=tk.NORMAL)
        self._verify_text.delete("1.0", tk.END)
        self._verify_text.insert("1.0", text)
        self._verify_text.config(state=tk.DISABLED)

    # ================================================================
    # MODE-AWARE FIELD STATE
    # ================================================================

    def _apply_mode_state(self):
        """Gray out API fields in offline mode, offline panel in online mode.

        Called at init and after every mode toggle so that non-technical
        users are not confused by editable but irrelevant fields.
        Preserves the credential status text (Key:/Endpoint:) populated
        by _refresh_credential_status() and appends an offline note.
        """
        t = current_theme()
        mode = getattr(self.config, "mode", "offline") if self.config else "offline"
        if mode == "offline":
            # Gray out online API fields
            for widget in (self.endpoint_entry, self.key_entry):
                widget.config(state=tk.DISABLED, disabledbackground=t["input_bg"],
                              disabledforeground=t["disabled_fg"])
            for btn in (self.save_cred_btn, self.test_btn, self.clear_cred_btn):
                btn.config(state=tk.DISABLED)
            if hasattr(self, "_pii_cb"):
                self._pii_cb.config(state=tk.DISABLED)
            # Append offline note without clobbering credential info
            current_text = self.cred_status_label.cget("text")
            if "(offline)" not in current_text:
                suffix = "  (offline -- not needed)"
                if current_text:
                    self.cred_status_label.config(
                        text=current_text + suffix, fg=t["disabled_fg"])
                else:
                    self.cred_status_label.config(
                        text="(offline mode -- API credentials not needed)",
                        fg=t["disabled_fg"])
            # Enable offline model panel, refresh its data
            if hasattr(self, "_offline_model_panel"):
                self._offline_model_panel.uc_dropdown.config(state="readonly")
                self._offline_model_panel._populate()
            self._refresh_network_policy_label()
        else:
            # Enable online API fields
            for widget in (self.endpoint_entry, self.key_entry):
                widget.config(state=tk.NORMAL, fg=t["input_fg"])
            for btn in (self.save_cred_btn, self.test_btn, self.clear_cred_btn):
                btn.config(state=tk.NORMAL)
            if hasattr(self, "_pii_cb"):
                self._pii_cb.config(state=tk.NORMAL)
            self._refresh_credential_status()
            # Gray out offline model panel in online mode
            if hasattr(self, "_offline_model_panel"):
                self._offline_model_panel.uc_dropdown.config(state=tk.DISABLED)
            self._refresh_network_policy_label()

    # ================================================================
    # SECTION C1: CHUNKING (RE-INDEX REQUIRED)
    # ================================================================

    def _build_chunking_section(self, t):
        """Build chunking controls kept separate from query-time tuning.

        Chunking changes affect indexing output (future chunks), not live
        query behavior. Re-index is required for changes to take effect.
        """
        frame = tk.LabelFrame(
            self._inner, text="Chunking (Re-Index Required)", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=(4, 8))
        self._chunking_frame = frame

        tk.Label(
            frame,
            text="These settings apply to future indexing only. Re-index after changes.",
            anchor=tk.W, justify=tk.LEFT, wraplength=760,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        ).pack(fill=tk.X, pady=(0, 6))

        chunking = getattr(self.config, "chunking", None)
        self.chunk_size_var = tk.StringVar(
            value=str(getattr(chunking, "chunk_size", 1200))
        )
        self.overlap_var = tk.StringVar(
            value=str(getattr(chunking, "overlap", 200))
        )

        row_cs = tk.Frame(frame, bg=t["panel_bg"])
        row_cs.pack(fill=tk.X, pady=3)
        tk.Label(
            row_cs, text="Chunk size:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)
        tk.Entry(
            row_cs, textvariable=self.chunk_size_var, width=10, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        ).pack(side=tk.LEFT, padx=(4, 0))

        row_ov = tk.Frame(frame, bg=t["panel_bg"])
        row_ov.pack(fill=tk.X, pady=3)
        tk.Label(
            row_ov, text="Overlap:", width=14, anchor=tk.W,
            bg=t["panel_bg"], fg=t["fg"], font=FONT,
        ).pack(side=tk.LEFT)
        tk.Entry(
            row_ov, textvariable=self.overlap_var, width=10, font=FONT,
            bg=t["input_bg"], fg=t["input_fg"], relief=tk.FLAT, bd=2,
        ).pack(side=tk.LEFT, padx=(4, 0))

        btn_row = tk.Frame(frame, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=(6, 2))
        self.save_chunking_btn = tk.Button(
            btn_row, text="Save Chunking", command=self._on_save_chunking,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.save_chunking_btn.pack(side=tk.LEFT)
        bind_hover(self.save_chunking_btn)

        self.chunking_status_label = tk.Label(
            frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.chunking_status_label.pack(fill=tk.X, pady=(2, 0))

    def _on_save_chunking(self):
        """Validate + persist chunking fields to config and YAML."""
        t = current_theme()
        try:
            chunk_size = int(self.chunk_size_var.get().strip())
            overlap = int(self.overlap_var.get().strip())
        except Exception:
            self.chunking_status_label.config(
                text="[FAIL] Chunk size and overlap must be integers.",
                fg=t["red"],
            )
            return

        if chunk_size < 200 or chunk_size > 4000:
            self.chunking_status_label.config(
                text="[FAIL] chunk_size must be between 200 and 4000.",
                fg=t["red"],
            )
            return
        if overlap < 0 or overlap >= chunk_size:
            self.chunking_status_label.config(
                text="[FAIL] overlap must be >= 0 and less than chunk_size.",
                fg=t["red"],
            )
            return

        chunking = getattr(self.config, "chunking", None)
        if chunking:
            chunking.chunk_size = chunk_size
            chunking.overlap = overlap

        try:
            from src.core.config import save_config_field
            save_config_field("chunking.chunk_size", chunk_size)
            save_config_field("chunking.overlap", overlap)
            self.chunking_status_label.config(
                text="[OK] Chunking saved (re-index required).",
                fg=t["green"],
            )
        except Exception as e:
            self.chunking_status_label.config(
                text="[FAIL] {}".format(str(e)[:80]),
                fg=t["red"],
            )

    # ================================================================
    # SECTION D: ADMIN DEFAULTS
    # ================================================================

    def _build_defaults_section(self, t):
        """Build admin defaults save/restore controls."""
        frame = tk.LabelFrame(
            self._inner, text="Admin Defaults", padx=16, pady=8,
            bg=t["panel_bg"], fg=t["accent"], font=FONT_BOLD,
        )
        frame.pack(fill=tk.X, padx=16, pady=(8, 16))
        self._defaults_frame = frame

        btn_row = tk.Frame(frame, bg=t["panel_bg"])
        btn_row.pack(fill=tk.X, pady=4)

        self.save_defaults_btn = tk.Button(
            btn_row, text="Save Current as Default",
            command=self._on_save_defaults,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.save_defaults_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.save_defaults_btn)

        self.restore_defaults_btn = tk.Button(
            btn_row, text="Restore Defaults",
            command=self._on_restore_defaults,
            bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
        )
        self.restore_defaults_btn.pack(side=tk.LEFT)
        bind_hover(self.restore_defaults_btn)

        self.defaults_status_label = tk.Label(
            frame, text="", anchor=tk.W,
            bg=t["panel_bg"], fg=t["gray"], font=FONT_SMALL,
        )
        self.defaults_status_label.pack(fill=tk.X, pady=(2, 0))
        self._refresh_defaults_status()

    def _on_save_defaults(self):
        """Save the current system state as the admin baseline.

        This lets admins set up the system once and restore it after
        experiments or accidental changes.  The file is plain JSON,
        not YAML, because it stores a flat snapshot -- not the full config.
        """
        t = current_theme()
        try:
            snapshot = _capture_config_snapshot(self.config)
            os.makedirs(os.path.dirname(_DEFAULTS_PATH), exist_ok=True)
            with open(_DEFAULTS_PATH, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            self.defaults_status_label.config(
                text="[OK] Defaults saved at {}".format(snapshot["saved_at"]),
                fg=t["green"])
            logger.info("Admin defaults saved to %s", _DEFAULTS_PATH)
        except Exception as e:
            self.defaults_status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"])

    def _on_restore_defaults(self):
        """Restore all settings from the previously saved admin defaults.

        Reads admin_defaults.json, writes values back into the live config,
        syncs the tuning tab sliders, and refreshes the path entries --
        so the entire UI reflects the restored state immediately.
        """
        t = current_theme()
        if not os.path.isfile(_DEFAULTS_PATH):
            self.defaults_status_label.config(
                text="[WARN] No defaults file found. Save defaults first.",
                fg=t["orange"])
            return
        try:
            with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            retrieval = getattr(self.config, "retrieval", None)
            api = getattr(self.config, "api", None)
            ollama = getattr(self.config, "ollama", None)
            paths = getattr(self.config, "paths", None)

            p_snap = snapshot.get("paths", {})
            if paths and p_snap:
                paths.source_folder = p_snap.get("source_folder", paths.source_folder)
                paths.database = p_snap.get("database", paths.database)
                paths.embeddings_cache = p_snap.get("embeddings_cache", paths.embeddings_cache)

            r_snap = snapshot.get("retrieval", {})
            if retrieval:
                retrieval.top_k = r_snap.get("top_k", retrieval.top_k)
                retrieval.min_score = r_snap.get("min_score", retrieval.min_score)
                retrieval.hybrid_search = r_snap.get("hybrid_search", retrieval.hybrid_search)
                retrieval.reranker_enabled = r_snap.get("reranker_enabled", retrieval.reranker_enabled)

            c_snap = snapshot.get("chunking", {})
            chunking = getattr(self.config, "chunking", None)
            if chunking and c_snap:
                chunking.chunk_size = c_snap.get("chunk_size", chunking.chunk_size)
                chunking.overlap = c_snap.get("overlap", chunking.overlap)

            a_snap = snapshot.get("api", {})
            if api:
                api.model = a_snap.get("model", api.model)
                api.max_tokens = a_snap.get("max_tokens", api.max_tokens)
                api.temperature = a_snap.get("temperature", api.temperature)
                api.timeout_seconds = a_snap.get("timeout_seconds", api.timeout_seconds)

            o_snap = snapshot.get("ollama", {})
            if ollama:
                ollama.model = o_snap.get("model", ollama.model)

            # Sync tuning tab sliders
            sv = self._app._views.get("settings") if hasattr(self._app, "_views") else None
            if sv and hasattr(sv, "_tuning_tab"):
                sv._tuning_tab._sync_sliders_to_config()

            # Sync path entries
            pp = getattr(self, "_paths_panel", None)
            if pp and p_snap:
                pp.source_var.set(p_snap.get("source_folder", ""))
                db = p_snap.get("database", "")
                pp.index_var.set(os.path.dirname(db) if db else "")
                pp._refresh_info()

            if hasattr(self, "chunk_size_var") and hasattr(self, "overlap_var"):
                c_snap = snapshot.get("chunking", {})
                if c_snap:
                    self.chunk_size_var.set(str(c_snap.get("chunk_size", "")))
                    self.overlap_var.set(str(c_snap.get("overlap", "")))

            saved_at = snapshot.get("saved_at", "?")
            self.defaults_status_label.config(
                text="[OK] Defaults restored (saved {})".format(saved_at),
                fg=t["green"])
            logger.info("Admin defaults restored from %s", _DEFAULTS_PATH)
        except Exception as e:
            self.defaults_status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg=t["red"])

    def _refresh_defaults_status(self):
        """Show when defaults were last saved (or 'not saved yet')."""
        t = current_theme()
        if os.path.isfile(_DEFAULTS_PATH):
            try:
                with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
                    snapshot = json.load(f)
                self.defaults_status_label.config(
                    text="Last saved: {}".format(snapshot.get("saved_at", "unknown")),
                    fg=t["gray"])
            except Exception:
                self.defaults_status_label.config(
                    text="Defaults file exists but could not be read.",
                    fg=t["orange"])
        else:
            self.defaults_status_label.config(
                text="No defaults saved yet.", fg=t["gray"])

    # ================================================================
    # THEME
    # ================================================================

    def apply_theme(self, t):
        self.configure(bg=t["panel_bg"])
        self._scroll.apply_theme({"bg": t["panel_bg"]})
        self._paths_panel.apply_theme(t)
        if hasattr(self, "_offline_model_panel"):
            self._offline_model_panel.apply_theme(t)
        self._model_panel.apply_theme(t)
        for frame_attr in (
            "_cred_frame", "_security_frame", "_chunking_frame",
            "_defaults_frame",
        ):
            frame = getattr(self, frame_attr, None)
            if frame:
                frame.configure(bg=t["panel_bg"], fg=t["accent"])
                _theme_widget(frame, t)
