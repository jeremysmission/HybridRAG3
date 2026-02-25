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
from datetime import datetime

from src.gui.theme import current_theme, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO, bind_hover
from src.gui.scrollable import ScrollableFrame
from src.security.credentials import (
    resolve_credentials, validate_endpoint,
    store_api_key, store_endpoint, clear_credentials,
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
            import yaml
            root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
            cfg_path = os.path.join(root, "config", "default_config.yaml")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            else:
                data = {}

            if "paths" not in data:
                data["paths"] = {}
            if source:
                data["paths"]["source_folder"] = source
            if index:
                data["paths"]["database"] = db_path
                data["paths"]["embeddings_cache"] = emb_path

            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            if hasattr(self._app, "index_panel"):
                ip = self._app.index_panel
                if source:
                    ip.folder_var.set(source)
                if index:
                    ip.index_var.set(index)
                ip.config = self.config

            self.status_label.config(
                text="[OK] Paths saved to config.", fg=t["green"])
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
        try:
            from scripts._model_meta import fetch_online_models_with_meta
            by_provider, total = fetch_online_models_with_meta(endpoint, key)
            flat = []
            for pmodels in by_provider.values():
                flat.extend(pmodels)
            if total > 0:
                self.after(0, self._fetch_done, flat, total)
            else:
                self.after(0, self._fetch_failed, "No models returned")
        except Exception as e:
            self.after(0, self._fetch_failed, str(e)[:80])

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
        self._paths_panel = DataPathsPanel(self._inner, config, app_ref)
        self._paths_panel.pack(fill=tk.X, padx=16, pady=8)
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
        self.toggle_key_btn = tk.Button(
            row_key, text="Show", width=5, font=FONT_SMALL,
            command=self._toggle_key_visibility,
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

        self.test_btn = tk.Button(
            btn_row, text="Test Connection", command=self._on_test_connection,
            bg=t["accent"], fg=t["accent_fg"], font=FONT,
            relief=tk.FLAT, bd=0, padx=12, pady=6,
            activebackground=t["accent_hover"], activeforeground=t["accent_fg"],
        )
        self.test_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.test_btn)

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

            parts = []
            if creds.has_key:
                parts.append("Key: {} (from {})".format(
                    creds.key_preview, creds.source_key or "?"))
            else:
                parts.append("Key: NOT SET")
            if creds.has_endpoint:
                parts.append("Endpoint: SET (from {})".format(
                    creds.source_endpoint or "?"))
            else:
                parts.append("Endpoint: NOT SET")

            t = current_theme()
            color = t["green"] if creds.is_online_ready else t["orange"]
            self.cred_status_label.config(text="  |  ".join(parts), fg=color)
        except Exception as e:
            logger.warning("Could not load credential status: %s", e)
            self.cred_status_label.config(
                text="[WARN] Could not load status: {}".format(str(e)[:60]),
                fg=current_theme()["red"],
            )

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
        try:
            from scripts._model_meta import fetch_online_models_with_meta
            by_provider, total = fetch_online_models_with_meta(endpoint, key)
            if total > 0:
                flat = []
                for pmodels in by_provider.values():
                    flat.extend(pmodels)
                self.after(0, self._test_done, flat, total)
            else:
                self.after(0, self._test_failed,
                           "No models returned (check endpoint/key)")
        except Exception as e:
            self.after(0, self._test_failed, str(e)[:80])

    def _test_done(self, models, total):
        """Main-thread callback: connection test succeeded."""
        t = current_theme()
        self.cred_status_label.config(
            text="[OK] Connected -- {} models available.".format(total),
            fg=t["green"])
        self.test_btn.config(state=tk.NORMAL)
        self._model_panel.set_models(models)

    def _test_failed(self, msg):
        """Main-thread callback: connection test failed."""
        t = current_theme()
        self.cred_status_label.config(text="[FAIL] {}".format(msg), fg=t["red"])
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
    # MODE-AWARE FIELD STATE
    # ================================================================

    def _apply_mode_state(self):
        """Gray out API credential fields when in offline mode.

        Called at init and after every mode toggle so that non-technical
        users are not confused by editable but irrelevant fields.
        Preserves the credential status text (Key:/Endpoint:) populated
        by _refresh_credential_status() and appends an offline note.
        """
        t = current_theme()
        mode = getattr(self.config, "mode", "offline") if self.config else "offline"
        if mode == "offline":
            for widget in (self.endpoint_entry, self.key_entry):
                widget.config(state=tk.DISABLED, disabledbackground=t["input_bg"],
                              disabledforeground=t["disabled_fg"])
            for btn in (self.save_cred_btn, self.test_btn, self.clear_cred_btn):
                btn.config(state=tk.DISABLED)
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
        else:
            for widget in (self.endpoint_entry, self.key_entry):
                widget.config(state=tk.NORMAL, fg=t["input_fg"])
            for btn in (self.save_cred_btn, self.test_btn, self.clear_cred_btn):
                btn.config(state=tk.NORMAL)
            self._refresh_credential_status()

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
        self._model_panel.apply_theme(t)
        for frame_attr in ("_cred_frame", "_defaults_frame"):
            frame = getattr(self, frame_attr, None)
            if frame:
                frame.configure(bg=t["panel_bg"], fg=t["accent"])
                _theme_widget(frame, t)
