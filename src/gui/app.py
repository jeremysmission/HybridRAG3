# ============================================================================
# HybridRAG v3 -- Main GUI Application (src/gui/app.py)              RevB
# ============================================================================
# WHAT: The main application window that ties all panels together.
# WHY:  Single-window coordinator that owns the lifecycle of every panel,
#       handles mode switching (offline/online), theme toggling, backend
#       initialization, and config propagation.
# HOW:  Uses lazy view switching -- only the Query view is built at startup;
#       all other views are built on first access via the panel registry.
#       Views swap via pack_forget/pack (under 1ms, no flicker).
# USAGE: Created by launch_gui.py.  Run `python src/gui/launch_gui.py`.
#
# LAYOUT: Single window with NavBar-driven view switching:
#   1. Title bar with mode toggle (OFFLINE / ONLINE) + theme toggle
#   2. NavBar -- tabs built from panel_registry (single source of truth)
#   3. Content Frame (swaps views via pack_forget/pack, <1ms)
#   4. Status bar (LLM, Ollama, Gate indicators)
#
# Menu bar: File | View | Help (Admin removed -- accessible via nav tab)
#
# INTERNET ACCESS: Depends on mode.
#   Offline: NONE (all local)
#   Online: API calls through QueryEngine only
# ============================================================================

import tkinter as tk
from tkinter import messagebox
import logging
import threading
import traceback

from src.gui.panels.query_panel import QueryPanel
from src.gui.panels.index_panel import IndexPanel
from src.gui.panels.status_bar import StatusBar
from src.gui.panels.nav_bar import NavBar
from src.gui.panels.panel_registry import get_panels, _import_attr
from src.core.cost_tracker import get_cost_tracker
from src.gui.theme import (
    DARK, LIGHT, FONT, FONT_BOLD, FONT_TITLE,
    current_theme, set_theme, apply_ttk_styles, bind_hover,
    get_zoom, set_zoom,
)
from src.gui.scrollable import ScrollableFrame
from src.gui.helpers import mode_switch
from src.gui.helpers.safe_after import drain_ui_queue
from src.gui.helpers.shutdown_coordinator import AppShutdownCoordinator

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
        self.shutdown = AppShutdownCoordinator()
        self._poll_timer_id = None
        self._backend_reload_thread = None

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

        # Heartbeat: drain the safe_after fallback queue every 50ms.
        # When safe_after() cannot reach Tk via widget.after() (e.g. bg
        # thread hits RuntimeError), callbacks land in _ui_queue. This
        # pump ensures they always execute on the main thread.
        self._drain_pump()

    # ----------------------------------------------------------------
    # MENU BAR -- File | View | Help (no Admin cascade -- it is a tab)
    # ----------------------------------------------------------------

    def _build_menu_bar(self):
        """Build File | View | Help menu bar."""
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
        mode_switch.update_mode_buttons(self)

    # ----------------------------------------------------------------
    # NAV BAR
    # ----------------------------------------------------------------

    def _build_nav_bar(self):
        """Build the horizontal navigation bar for view switching."""
        self.nav_bar = NavBar(self, on_switch=self.show_view, theme=self._theme)
        self.nav_bar.pack(fill=tk.X)

    # ----------------------------------------------------------------
    # CONTENT FRAME + VIEW SWITCHING (registry-driven)
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
        """Build QueryPanel inside a scrollable container (standalone)."""
        view = ScrollableFrame(self._content, bg=self._theme["bg"])
        self.query_panel = QueryPanel(
            view.inner, config=self.config, query_engine=self.query_engine,
        )
        self.query_panel.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 4))
        self._views["query"] = view

    def show_view(self, name):
        """Switch to the named view. Lazy-builds on first access."""
        # Hide current view
        if self._current_view and self._current_view in self._views:
            self._views[self._current_view].pack_forget()

        # Build if not yet created (lazy)
        if name not in self._views:
            self._build_view(name)

        # Show target view (guard against failed build)
        if name not in self._views:
            logger.warning("SWITCH key=%s mounted=FAIL (view not built)", name)
            return
        self._views[name].pack(in_=self._content, fill=tk.BOTH, expand=True)
        self._current_view = name
        self.nav_bar.select(name)
        logger.info("SWITCH key=%s mounted=OK", name)

    def _build_view(self, name):
        """Lazy-build a view the first time it is requested.

        Uses the panel registry to import the correct class, then
        constructs with the appropriate arguments per panel type.
        If building fails, mounts an error panel showing the traceback.
        """
        try:
            if name == "query":
                # Handled eagerly by _build_query_view
                return

            if name == "index":
                # Index panel -- standalone (not embedded in Query)
                wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
                self.index_panel = IndexPanel(
                    wrapper.inner, config=self.config, indexer=self.indexer,
                )
                self.index_panel.pack(fill=tk.X, padx=16, pady=8)
                # If backends already loaded (panel built after _attach),
                # enable the Start button immediately.
                if self.indexer is not None:
                    self.index_panel.indexer = self.indexer
                    self.index_panel.set_ready(True)
                    logger.info("[OK] Index panel: backends ready at build time")
                else:
                    # Backends not attached yet -- poll until they arrive
                    # (covers the race where user clicks tab before backends
                    #  finish loading in the background thread).
                    logger.info("[WARN] Index panel built before backends ready"
                                " -- starting deferred readiness check")
                    self._poll_index_ready()
                self._views["index"] = wrapper
                return

            if name == "data":
                from src.gui.panels.data_panel import DataPanel
                wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
                view = DataPanel(wrapper.inner, config=self.config, app_ref=self)
                view.pack(fill=tk.BOTH, expand=True)
                self._data_panel = view
                self._views["data"] = wrapper
                return

            if name == "tuning":
                from src.gui.panels.tuning_tab import TuningTab
                wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
                view = TuningTab(wrapper.inner, config=self.config, app_ref=self)
                view.pack(fill=tk.BOTH, expand=True)
                self._tuning_panel = view
                self._views["tuning"] = wrapper
                return

            if name == "cost":
                from src.gui.panels.cost_dashboard import CostDashboard
                view = CostDashboard(self._content, self.cost_tracker)
                self._views["cost"] = view
                return

            if name == "admin":
                from src.gui.panels.api_admin_tab import ApiAdminTab
                wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
                view = ApiAdminTab(wrapper.inner, config=self.config, app_ref=self)
                view.pack(fill=tk.BOTH, expand=True)
                self._admin_panel = view
                self._views["admin"] = wrapper
                return

            if name == "ref":
                from src.gui.panels.reference_panel import ReferencePanel
                view = ReferencePanel(self._content)
                self._views["ref"] = view
                return

            if name == "settings":
                from src.gui.panels.settings_panel import SettingsPanel
                wrapper = ScrollableFrame(self._content, bg=self._theme["bg"])
                view = SettingsPanel(
                    wrapper.inner, config=self.config, app_ref=self,
                )
                view.pack(fill=tk.BOTH, expand=True)
                self._settings_panel = view
                self._views["settings"] = wrapper
                return

            # Unknown view key -- log and show error
            logger.warning("[WARN] Unknown view key: '%s'", name)

        except Exception as e:
            # Build an error panel so the user sees the problem
            tb = traceback.format_exc()
            logger.warning("[WARN] Failed to build view '%s': %s\n%s", name, e, tb)
            self._build_error_view(name, str(e), tb)

    def _build_error_view(self, name, error_msg, tb_text):
        """Mount a visible error panel when a view fails to build."""
        t = self._theme
        frame = tk.Frame(self._content, bg=t["bg"])
        tk.Label(
            frame, text="Failed to load: {}".format(name),
            font=FONT_BOLD, bg=t["bg"], fg=t.get("red", "#ff4444"),
        ).pack(anchor=tk.W, padx=16, pady=(16, 4))
        tk.Label(
            frame, text=error_msg, wraplength=700, justify=tk.LEFT,
            font=FONT, bg=t["bg"], fg=t["fg"],
        ).pack(anchor=tk.W, padx=16, pady=4)
        # Traceback in a text widget
        txt = tk.Text(
            frame, height=12, wrap=tk.WORD, font=("Consolas", 9),
            bg=t.get("input_bg", "#1e1e1e"), fg=t.get("input_fg", "#cccccc"),
        )
        txt.insert("1.0", tb_text)
        txt.config(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self._views[name] = frame

    # ----------------------------------------------------------------
    # DEFERRED READINESS
    # ----------------------------------------------------------------

    def _poll_index_ready(self, attempts=0):
        """Check every 500ms if indexer has been attached; enable button."""
        if self.indexer is not None and hasattr(self, "index_panel"):
            self.index_panel.indexer = self.indexer
            self.index_panel.set_ready(True)
            logger.info("[OK] Index panel: deferred readiness resolved "
                        "after %d polls", attempts)
            return
        if attempts >= 120:  # 60 seconds max
            logger.warning("[WARN] Index panel: backends never arrived "
                           "after 60s -- button stays disabled")
            return
        try:
            self._poll_timer_id = self.after(
                500, self._poll_index_ready, attempts + 1,
            )
        except Exception:
            pass  # App being destroyed -- stop polling

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

        # Propagate to named panels
        if hasattr(self, "query_panel"):
            self.query_panel.apply_theme(t)
        if hasattr(self, "index_panel"):
            self.index_panel.apply_theme(t)
        if hasattr(self, "status_bar"):
            self.status_bar.apply_theme(t)
        if hasattr(self, "_data_panel"):
            self._data_panel.apply_theme(t)
        if hasattr(self, "_tuning_panel"):
            self._tuning_panel.apply_theme(t)
        if hasattr(self, "_admin_panel"):
            self._admin_panel.apply_theme(t)
        if hasattr(self, "_settings_panel"):
            self._settings_panel.apply_theme(t)

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
    # MODE TOGGLING (delegated to src.gui.helpers.mode_switch)
    # ----------------------------------------------------------------

    def toggle_mode(self, new_mode):
        """Switch between online and offline mode (delegates to mode_switch)."""
        mode_switch.toggle_mode(self, new_mode)

    def _switch_to_online(self):
        """Delegate to module-level function."""
        mode_switch.switch_to_online(self)

    def _switch_to_offline(self):
        """Delegate to module-level function."""
        mode_switch.switch_to_offline(self)

    def _persist_mode(self, new_mode):
        """Delegate to module-level function."""
        mode_switch.persist_mode(self, new_mode)

    # ----------------------------------------------------------------
    # BACKEND RESET + READY STATE
    # ----------------------------------------------------------------

    def reset_backends(self):
        """Tear down backends, show loading state, and reload in background."""
        if getattr(self, "_backend_reload_thread", None) is not None:
            if self._backend_reload_thread.is_alive():
                logger.warning("Backend reload already in progress")
                return
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
            self.status_bar._init_error = None  # Clear previous error
            self.status_bar.set_loading_stage("Restarting...")
            self.status_bar.force_refresh()

        from src.gui.launch_gui import _load_backends
        reload_thread = threading.Thread(
            target=_load_backends,
            args=(self, logging.getLogger("gui_launcher")),
            daemon=True,
        )
        reload_thread.start()
        self._backend_reload_thread = reload_thread
        self.shutdown.register_thread("backend_reload", reload_thread)
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

        # Propagate to query engine so it uses the new settings
        if hasattr(self, "query_engine") and self.query_engine:
            self.query_engine.config = new_config

        if hasattr(self, "query_panel"):
            self.query_panel.config = new_config
            self.query_panel._on_use_case_change()

        if hasattr(self, "index_panel"):
            self.index_panel.config = new_config

        if hasattr(self, "status_bar"):
            self.status_bar.config = new_config
            self.status_bar.force_refresh()

        # Propagate to standalone panels
        admin = getattr(self, "_admin_panel", None)
        if admin is not None:
            admin.config = new_config

        tuning = getattr(self, "_tuning_panel", None)
        if tuning is not None:
            tuning.config = new_config

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
            "Backend: SQLite + Ollama + nomic-embed-text",
        )

    # ----------------------------------------------------------------
    # CLEANUP
    # ----------------------------------------------------------------

    def _drain_pump(self):
        """Drain the safe_after fallback queue and reschedule.

        Runs every 50ms on the main thread. If safe_after() had to enqueue
        a callback (because widget.after() failed from a bg thread), this
        pump ensures it still fires. Cost: ~0 when queue is empty.
        """
        try:
            drain_ui_queue()
        except Exception:
            pass
        try:
            self.after(50, self._drain_pump)
        except Exception:
            pass  # App being destroyed -- stop pumping

    def _on_close(self):
        """Clean up and close the application.

        Shutdown sequence:
          1. Signal all registered threads to stop.
          2. Cancel known tkinter timer IDs (dot animation, elapsed, CBIT).
          3. Join threads briefly (bounded at 2s total -- never freeze).
          4. Flush cost tracker to SQLite.
          5. destroy().
        """
        # Collect timer IDs to cancel
        timer_ids = []
        if hasattr(self, "status_bar"):
            self.status_bar.stop()
            timer_ids.append(getattr(self.status_bar, "_dot_timer_id", None))
            timer_ids.append(getattr(self.status_bar, "_cbit_timer_id", None))
        if hasattr(self, "query_panel"):
            timer_ids.append(getattr(self.query_panel, "_elapsed_timer_id", None))
        timer_ids.append(getattr(self, "_poll_timer_id", None))

        # Register known threads for join
        if hasattr(self, "query_panel"):
            qt = getattr(self.query_panel, "_query_thread", None)
            if qt is not None:
                self.shutdown.register_thread("query", qt)
        if hasattr(self, "index_panel"):
            it = getattr(self.index_panel, "_index_thread", None)
            sf = getattr(self.index_panel, "_stop_flag", None)
            if it is not None:
                self.shutdown.register_thread("indexing", it, sf)
        rt = getattr(self, "_backend_reload_thread", None)
        if rt is not None:
            self.shutdown.register_thread("backend_reload", rt)

        # Signal + cancel + join (bounded)
        self.shutdown.request_shutdown(widget=self, timer_ids=timer_ids)

        # Clean up cost dashboard listener if it was built
        cost_view = self._views.get("cost") if hasattr(self, "_views") else None
        if cost_view is not None and hasattr(cost_view, "cleanup"):
            cost_view.cleanup()
        if hasattr(self, "cost_tracker") and self.cost_tracker:
            self.cost_tracker.shutdown()
        self.destroy()
