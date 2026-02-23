# ============================================================================
# HybridRAG v3 -- Main GUI Application (src/gui/app.py)              RevA
# ============================================================================
# WHAT: The main application window that ties all panels together.
# WHY:  Single-window coordinator that owns the lifecycle of every panel,
#       handles mode switching (offline/online), theme toggling, backend
#       initialization, and config propagation.
# HOW:  Uses lazy view switching -- only the Query view is built at startup;
#       Settings, Cost, and Reference views are built on first access.
#       Views swap via pack_forget/pack (under 1ms, no flicker).
# USAGE: Created by launch_gui.py.  Run `python src/gui/launch_gui.py`.
#
# Technology Decision: tkinter (Python standard library)
#
# WHY TKINTER:
#   - Zero additional dependencies (already in Python stdlib)
#   - Works on every machine including work laptops with restricted installs
#   - No entry needed in requirements.txt
#   - Suitable for prototype / human review before production UI
#   - PyQt5/PySide6/wx/Dear PyGui are NOT in requirements.txt
#
# LAYOUT: Single window with NavBar-driven view switching:
#   1. Title bar with mode toggle (OFFLINE / ONLINE) + theme toggle
#   2. NavBar [Query] [Settings] [Cost] [Ref]
#   3. Content Frame (swaps views via pack_forget/pack, <1ms)
#      - QueryView (QueryPanel + IndexPanel) -- default, eager-built
#      - SettingsView -- lazy-built on first access
#      - CostView (CostDashboard) -- lazy-built on first access
#      - ReferenceView (ReferencePanel) -- lazy-built on first access
#   4. Status bar (LLM, Ollama, Gate indicators)
#
# Menu bar: File | Admin | Help
#
# INTERNET ACCESS: Depends on mode.
#   Offline: NONE (all local)
#   Online: API calls through QueryEngine only
# ============================================================================

import tkinter as tk
from tkinter import messagebox
import logging
import threading

from src.gui.panels.query_panel import QueryPanel
from src.gui.panels.index_panel import IndexPanel
from src.gui.panels.status_bar import StatusBar
from src.gui.panels.nav_bar import NavBar
from src.gui.panels.cost_dashboard import CostDashboard
from src.gui.panels.reference_panel import ReferencePanel
from src.core.cost_tracker import get_cost_tracker
from src.gui.theme import (
    DARK, LIGHT, FONT, FONT_BOLD, FONT_TITLE,
    current_theme, set_theme, apply_ttk_styles, bind_hover,
    get_zoom, set_zoom,
)
from src.gui.scrollable import ScrollableFrame

logger = logging.getLogger(__name__)


class HybridRAGApp(tk.Tk):
    """
    Main application window for HybridRAG v3.

    Owns all panels and coordinates mode switching, boot state,
    view switching, and backend references.
    """

    def __init__(self, boot_result=None, config=None, query_engine=None,
                 indexer=None, router=None):
        super().__init__()

        self.title("HybridRAG v3")
        self.geometry("840x780")
        self.minsize(700, 400)

        # Store backend references
        self.boot_result = boot_result
        self.config = config
        self.query_engine = query_engine
        self.indexer = indexer
        self.router = router
        self.cost_tracker = get_cost_tracker()

        # Apply initial theme
        self._theme = current_theme()
        apply_ttk_styles(self._theme)
        self.configure(bg=self._theme["bg"])

        # Build UI
        self._build_menu_bar()
        self._build_title_bar()
        self._build_nav_bar()
        self._build_status_bar()
        self._build_content_frame()

        # Show boot warnings if any
        if boot_result and boot_result.warnings:
            for w in boot_result.warnings:
                logger.warning("Boot warning: %s", w)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------------
    # MENU BAR
    # ----------------------------------------------------------------

    def _build_menu_bar(self):
        """Build File | Admin | Help menu bar."""
        t = self._theme
        menubar = tk.Menu(self, bg=t["menu_bg"], fg=t["menu_fg"],
                          activebackground=t["accent"],
                          activeforeground=t["accent_fg"],
                          relief=tk.FLAT, font=FONT)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0,
                            bg=t["menu_bg"], fg=t["menu_fg"],
                            activebackground=t["accent"],
                            activeforeground=t["accent_fg"], font=FONT)
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # View menu -- zoom controls for accessibility
        view_menu = tk.Menu(menubar, tearoff=0,
                            bg=t["menu_bg"], fg=t["menu_fg"],
                            activebackground=t["accent"],
                            activeforeground=t["accent_fg"], font=FONT)
        for pct in (50, 75, 100, 125, 150, 200):
            label = "{}%".format(pct)
            if pct == 100:
                label += " (Default)"
            view_menu.add_command(
                label=label,
                command=lambda p=pct: self._apply_zoom(p / 100.0),
            )
        menubar.add_cascade(label="View", menu=view_menu)

        # Admin menu -- commands switch views in-place
        admin_menu = tk.Menu(menubar, tearoff=0,
                             bg=t["menu_bg"], fg=t["menu_fg"],
                             activebackground=t["accent"],
                             activeforeground=t["accent_fg"], font=FONT)
        admin_menu.add_command(
            label="Admin Settings...",
            command=lambda: self.show_view("settings"),
        )
        admin_menu.add_command(
            label="PM Cost Dashboard...",
            command=lambda: self.show_view("cost"),
        )
        admin_menu.add_separator()
        admin_menu.add_command(
            label="Ref",
            command=lambda: self.show_view("reference"),
        )
        menubar.add_cascade(label="Admin", menu=admin_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0,
                            bg=t["menu_bg"], fg=t["menu_fg"],
                            activebackground=t["accent"],
                            activeforeground=t["accent_fg"], font=FONT)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config_menu = menubar
        self.configure(menu=menubar)

    # ----------------------------------------------------------------
    # TITLE BAR with mode toggle + theme toggle
    # ----------------------------------------------------------------

    def _build_title_bar(self):
        """Build title bar with OFFLINE/ONLINE toggle and theme toggle."""
        t = self._theme
        self.title_frame = tk.Frame(self, bg=t["panel_bg"], padx=16, pady=8)
        self.title_frame.pack(fill=tk.X)

        self.title_label = tk.Label(
            self.title_frame, text="HybridRAG v3", font=FONT_TITLE,
            bg=t["panel_bg"], fg=t["fg"],
        )
        self.title_label.pack(side=tk.LEFT)

        # Mode label
        self.mode_label = tk.Label(
            self.title_frame, text="Mode:", bg=t["panel_bg"], fg=t["label_fg"],
            font=FONT,
        )
        self.mode_label.pack(side=tk.LEFT, padx=(24, 8))

        # OFFLINE button
        self.offline_btn = tk.Button(
            self.title_frame, text="OFFLINE", width=10, font=FONT,
            command=lambda: self.toggle_mode("offline"),
            relief=tk.FLAT, bd=0, padx=12, pady=4,
        )
        self.offline_btn.pack(side=tk.LEFT, padx=4)

        # ONLINE button
        self.online_btn = tk.Button(
            self.title_frame, text="ONLINE", width=10, font=FONT,
            command=lambda: self.toggle_mode("online"),
            relief=tk.FLAT, bd=0, padx=12, pady=4,
        )
        self.online_btn.pack(side=tk.LEFT, padx=4)

        # -- Theme toggle (right side) --
        self.theme_btn = tk.Button(
            self.title_frame, text="Light", width=6, font=FONT,
            command=self._toggle_theme,
            relief=tk.FLAT, bd=0, padx=12, pady=4,
            bg=t["input_bg"], fg=t["fg"],
        )
        self.theme_btn.pack(side=tk.RIGHT, padx=4)
        bind_hover(self.theme_btn)

        self.theme_icon_label = tk.Label(
            self.title_frame, text="Theme:", bg=t["panel_bg"],
            fg=t["label_fg"], font=FONT,
        )
        self.theme_icon_label.pack(side=tk.RIGHT)

        # -- Reset button (right side, before Theme) --
        self.reset_btn = tk.Button(
            self.title_frame, text="Reset", width=6, font=FONT,
            command=self.reset_backends,
            relief=tk.FLAT, bd=0, padx=12, pady=4,
            bg=t["input_bg"], fg=t["fg"],
        )
        self.reset_btn.pack(side=tk.RIGHT, padx=(0, 8))
        bind_hover(self.reset_btn)

        # Set initial button colors
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """Update mode button colors to reflect current state."""
        t = self._theme
        mode = getattr(self.config, "mode", "offline") if self.config else "offline"
        if mode == "online":
            self.online_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                                   relief=tk.FLAT)
            self.offline_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                                    relief=tk.FLAT)
        else:
            self.offline_btn.config(bg=t["active_btn_bg"], fg=t["active_btn_fg"],
                                    relief=tk.FLAT)
            self.online_btn.config(bg=t["inactive_btn_bg"], fg=t["inactive_btn_fg"],
                                   relief=tk.FLAT)

    # ----------------------------------------------------------------
    # NAV BAR
    # ----------------------------------------------------------------

    def _build_nav_bar(self):
        """Build the horizontal navigation bar for view switching."""
        self.nav_bar = NavBar(self, on_switch=self.show_view, theme=self._theme)
        self.nav_bar.pack(fill=tk.X)

    # ----------------------------------------------------------------
    # CONTENT FRAME + VIEW SWITCHING
    # ----------------------------------------------------------------

    def _build_status_bar(self):
        """Build and pack the status bar at the bottom."""
        self.status_bar = StatusBar(
            self, config=self.config, router=self.router,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_content_frame(self):
        """Build the content container and the default Query view."""
        self._content = tk.Frame(self, bg=self._theme["bg"])
        self._content.pack(fill=tk.BOTH, expand=True)
        self._views = {}
        self._current_view = None

        # Build Query view eagerly (startup view)
        self._build_query_view()
        self.show_view("query")

    def _build_query_view(self):
        """Build QueryPanel + IndexPanel inside a scrollable container."""
        view = ScrollableFrame(self._content, bg=self._theme["bg"])
        self.query_panel = QueryPanel(
            view.inner, config=self.config, query_engine=self.query_engine,
        )
        self.query_panel.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 4))
        self.index_panel = IndexPanel(
            view.inner, config=self.config, indexer=self.indexer,
        )
        self.index_panel.pack(fill=tk.X, padx=16, pady=4)
        self._views["query"] = view

    def show_view(self, name):
        """Switch to the named view. Lazy-builds on first access."""
        # Hide current view
        if self._current_view and self._current_view in self._views:
            self._views[self._current_view].pack_forget()

        # Build if not yet created (lazy)
        if name not in self._views:
            self._build_view(name)

        # Show target view
        self._views[name].pack(in_=self._content, fill=tk.BOTH, expand=True)
        self._current_view = name
        self.nav_bar.select(name)

    def _build_view(self, name):
        """Lazy-build a view the first time it is requested."""
        if name == "settings":
            from src.gui.panels.settings_view import SettingsView
            wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
            view = SettingsView(wrapper.inner, config=self.config, app_ref=self)
            view.pack(fill=tk.BOTH, expand=True)
            self._settings_view = view   # keep ref for delegation
            self._views["settings"] = wrapper
        elif name == "cost":
            view = CostDashboard(self._content, self.cost_tracker)
            self._views["cost"] = view
        elif name == "reference":
            view = ReferencePanel(self._content)
            self._views["reference"] = view

    # ----------------------------------------------------------------
    # THEME TOGGLE
    # ----------------------------------------------------------------

    def _toggle_theme(self):
        """Switch between dark and light themes and rebuild the UI."""
        if self._theme["name"] == "dark":
            new_theme = LIGHT
        else:
            new_theme = DARK

        set_theme(new_theme)
        self._theme = new_theme
        apply_ttk_styles(new_theme)
        self._apply_theme_to_all()

    def _apply_theme_to_all(self):
        """Re-apply theme colors to all widgets without rebuilding."""
        t = self._theme
        self.configure(bg=t["bg"])

        # Title bar
        self.title_frame.configure(bg=t["panel_bg"])
        self.title_label.configure(bg=t["panel_bg"], fg=t["fg"])
        self.mode_label.configure(bg=t["panel_bg"], fg=t["label_fg"])
        self.theme_icon_label.configure(bg=t["panel_bg"], fg=t["label_fg"])

        # Theme button label
        if t["name"] == "dark":
            self.theme_btn.configure(text="Light", bg=t["input_bg"], fg=t["fg"])
        else:
            self.theme_btn.configure(text="Dark", bg=t["input_bg"], fg=t["fg"])

        # Reset button
        self.reset_btn.configure(bg=t["input_bg"], fg=t["fg"])

        self._update_mode_buttons()

        # Rebuild menus
        self._build_menu_bar()

        # Nav bar
        self.nav_bar.apply_theme(t)

        # Content frame
        self._content.configure(bg=t["bg"])

        # Propagate to panels
        if hasattr(self, "query_panel"):
            self.query_panel.apply_theme(t)
        if hasattr(self, "index_panel"):
            self.index_panel.apply_theme(t)
        if hasattr(self, "status_bar"):
            self.status_bar.apply_theme(t)

        # Propagate to all cached views
        for view in self._views.values():
            if hasattr(view, "apply_theme"):
                view.apply_theme(t)

    # ----------------------------------------------------------------
    # ZOOM
    # ----------------------------------------------------------------

    def _apply_zoom(self, factor):
        """Scale all fonts by the given factor and refresh the UI."""
        set_zoom(factor)
        apply_ttk_styles(self._theme)
        self._apply_theme_to_all()

    # ----------------------------------------------------------------
    # MODE TOGGLING
    # ----------------------------------------------------------------

    def toggle_mode(self, new_mode):
        """
        Switch between online and offline mode.

        Online: checks credentials first, shows error if missing.
        Offline: always succeeds (safe operation).
        """
        if new_mode == "online":
            self._switch_to_online()
        else:
            self._switch_to_offline()

    def _switch_to_online(self):
        """Attempt to switch to online mode."""
        try:
            from src.security.credentials import credential_status
            status = credential_status()

            if not status.get("api_key_set") or not status.get("api_endpoint_set"):
                missing = []
                if not status.get("api_key_set"):
                    missing.append("API key")
                if not status.get("api_endpoint_set"):
                    missing.append("API endpoint")
                messagebox.showwarning(
                    "Credentials Missing",
                    "Cannot switch to online mode.\n\n"
                    "Missing: {}\n\n"
                    "Run rag-store-key and rag-store-endpoint from "
                    "PowerShell first, then try again.".format(", ".join(missing)),
                )
                return
        except Exception as e:
            messagebox.showwarning(
                "Credential Check Failed",
                "Could not verify credentials: {}\n\n"
                "Run rag-store-key and rag-store-endpoint from "
                "PowerShell first, then try again.".format(e),
            )
            return

        if self.config:
            self.config.mode = "online"

        try:
            from src.core.network_gate import configure_gate
            from src.security.credentials import resolve_credentials
            creds = resolve_credentials()
            configure_gate(
                mode="online",
                api_endpoint=creds.endpoint or "",
                allowed_prefixes=getattr(
                    getattr(self.config, "api", None),
                    "allowed_endpoint_prefixes", [],
                ) if self.config else [],
            )
        except Exception as e:
            logger.warning("Gate reconfiguration failed: %s", e)

        self._update_mode_buttons()
        self.status_bar.force_refresh()
        if hasattr(self, "query_panel"):
            self.query_panel._on_use_case_change()

        # Refresh credential display in settings if it exists
        settings = getattr(self, "_settings_view", None)
        if settings is not None and hasattr(settings, "refresh_credential_status"):
            settings.refresh_credential_status()

        logger.info("Switched to ONLINE mode")

    def _switch_to_offline(self):
        """Switch to offline mode (always safe)."""
        if self.config:
            self.config.mode = "offline"

        try:
            from src.core.network_gate import configure_gate
            configure_gate(mode="offline")
        except Exception as e:
            logger.warning("Gate reconfiguration failed: %s", e)

        self._update_mode_buttons()
        self.status_bar.force_refresh()
        if hasattr(self, "query_panel"):
            self.query_panel._on_use_case_change()
        logger.info("Switched to OFFLINE mode")

    # ----------------------------------------------------------------
    # BACKEND RESET + READY STATE
    # ----------------------------------------------------------------

    def reset_backends(self):
        """Tear down backends, show loading state, and reload in background."""
        self.query_engine = None
        self.indexer = None
        self.router = None

        if hasattr(self, "query_panel"):
            self.query_panel.query_engine = None
            self.query_panel.set_ready(False)
        if hasattr(self, "index_panel"):
            self.index_panel.indexer = None
            self.index_panel.set_ready(False)
        if hasattr(self, "status_bar"):
            self.status_bar.router = None
            self.status_bar.set_loading_stage("Restarting...")
            self.status_bar.force_refresh()

        from src.gui.launch_gui import _load_backends
        reload_thread = threading.Thread(
            target=_load_backends,
            args=(self, logging.getLogger("gui_launcher")),
            daemon=True,
        )
        reload_thread.start()
        logger.info("Backend reset -- reloading in background")

    def set_ready(self, enabled):
        """Propagate ready state to all panels."""
        if hasattr(self, "query_panel"):
            self.query_panel.set_ready(enabled)
        if hasattr(self, "index_panel"):
            self.index_panel.set_ready(enabled)
        if hasattr(self, "status_bar"):
            if enabled:
                self.status_bar.set_ready()
            else:
                self.status_bar.set_loading_stage("Loading...")

    # ----------------------------------------------------------------
    # CONFIG RELOAD (for profile switching)
    # ----------------------------------------------------------------

    def reload_config(self, new_config):
        """Replace the running config and propagate to all panels."""
        self.config = new_config

        if hasattr(self, "query_panel"):
            self.query_panel.config = new_config
            self.query_panel._on_use_case_change()

        if hasattr(self, "index_panel"):
            self.index_panel.config = new_config

        if hasattr(self, "status_bar"):
            self.status_bar.config = new_config
            self.status_bar.force_refresh()

        # Propagate to settings view (both tabs) if it exists
        settings = getattr(self, "_settings_view", None)
        if settings is not None:
            settings.config = new_config
            if hasattr(settings, "_tuning_tab"):
                settings._tuning_tab.config = new_config
            if hasattr(settings, "_api_admin_tab"):
                settings._api_admin_tab.config = new_config

        self._update_mode_buttons()
        logger.info("Config reloaded and propagated to all panels")

    # ----------------------------------------------------------------
    # HELP
    # ----------------------------------------------------------------

    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About HybridRAG v3",
            "HybridRAG v3 -- GUI Prototype\n\n"
            "Local-first RAG system for technical document search.\n"
            "Zero-trust offline-default architecture.\n\n"
            "Technology: tkinter (Python standard library)\n"
            "Backend: SQLite + memmap + sentence-transformers",
        )

    # ----------------------------------------------------------------
    # CLEANUP
    # ----------------------------------------------------------------

    def _on_close(self):
        """Clean up and close the application."""
        if hasattr(self, "status_bar"):
            self.status_bar.stop()
        # Clean up cost dashboard listener if it was built
        cost_view = self._views.get("cost") if hasattr(self, "_views") else None
        if cost_view is not None and hasattr(cost_view, "cleanup"):
            cost_view.cleanup()
        if hasattr(self, "cost_tracker") and self.cost_tracker:
            self.cost_tracker.shutdown()
        self.destroy()
