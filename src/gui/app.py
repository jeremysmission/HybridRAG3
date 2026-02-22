# ============================================================================
# HybridRAG v3 -- Main GUI Application (src/gui/app.py)
# ============================================================================
# Technology Decision: tkinter (Python standard library)
#
# WHY TKINTER:
#   - Zero additional dependencies (already in Python stdlib)
#   - Works on every machine including work laptops with restricted installs
#   - No entry needed in requirements.txt
#   - Suitable for prototype / human review before production UI
#   - PyQt5/PySide6/wx/Dear PyGui are NOT in requirements.txt
#
# LAYOUT: Single window, four regions top to bottom:
#   1. Title bar with mode toggle (OFFLINE / ONLINE)
#   2. Query panel (use case, model, question, answer, sources, metrics)
#   3. Index panel (folder picker, progress bar, start/stop)
#   4. Status bar (LLM, Ollama, Gate indicators)
#
# Menu bar: File | Engineering | Help
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
from src.gui.panels.engineering_menu import EngineeringMenu

logger = logging.getLogger(__name__)


class HybridRAGApp(tk.Tk):
    """
    Main application window for HybridRAG v3.

    Owns all panels and coordinates mode switching, boot state,
    and backend references.
    """

    def __init__(self, boot_result=None, config=None, query_engine=None,
                 indexer=None, router=None):
        super().__init__()

        self.title("HybridRAG v3")
        self.geometry("780x720")
        self.minsize(640, 500)

        # Store backend references
        self.boot_result = boot_result
        self.config = config
        self.query_engine = query_engine
        self.indexer = indexer
        self.router = router

        # Build UI
        self._build_menu_bar()
        self._build_title_bar()
        self._build_query_panel()
        self._build_index_panel()
        self._build_status_bar()

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
        """Build File | Engineering | Help menu bar."""
        menubar = tk.Menu(self)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # Engineering menu
        eng_menu = tk.Menu(menubar, tearoff=0)
        eng_menu.add_command(
            label="Engineering Settings...",
            command=self._open_engineering_menu,
        )
        menubar.add_cascade(label="Engineering", menu=eng_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config_menu = menubar
        self.configure(menu=menubar)

    # ----------------------------------------------------------------
    # TITLE BAR with mode toggle
    # ----------------------------------------------------------------

    def _build_title_bar(self):
        """Build title bar with OFFLINE/ONLINE toggle buttons."""
        title_frame = tk.Frame(self, bg="#f0f0f0", padx=8, pady=6)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="HybridRAG v3", font=("TkDefaultFont", 14, "bold"),
            bg="#f0f0f0",
        ).pack(side=tk.LEFT)

        # Mode label
        tk.Label(
            title_frame, text="Mode:", bg="#f0f0f0",
        ).pack(side=tk.LEFT, padx=(20, 4))

        # OFFLINE button
        self.offline_btn = tk.Button(
            title_frame, text="OFFLINE", width=10,
            command=lambda: self.toggle_mode("offline"),
        )
        self.offline_btn.pack(side=tk.LEFT, padx=2)

        # ONLINE button
        self.online_btn = tk.Button(
            title_frame, text="ONLINE", width=10,
            command=lambda: self.toggle_mode("online"),
        )
        self.online_btn.pack(side=tk.LEFT, padx=2)

        # Set initial button colors
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """Update mode button colors to reflect current state."""
        mode = getattr(self.config, "mode", "offline") if self.config else "offline"
        if mode == "online":
            self.online_btn.config(bg="green", fg="white", relief=tk.SUNKEN)
            self.offline_btn.config(bg="SystemButtonFace", fg="black", relief=tk.RAISED)
        else:
            self.offline_btn.config(bg="green", fg="white", relief=tk.SUNKEN)
            self.online_btn.config(bg="SystemButtonFace", fg="black", relief=tk.RAISED)

    # ----------------------------------------------------------------
    # PANELS
    # ----------------------------------------------------------------

    def _build_query_panel(self):
        """Build and pack the query panel."""
        self.query_panel = QueryPanel(
            self, config=self.config, query_engine=self.query_engine,
        )
        self.query_panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 2))

    def _build_index_panel(self):
        """Build and pack the index panel."""
        self.index_panel = IndexPanel(
            self, config=self.config, indexer=self.indexer,
        )
        self.index_panel.pack(fill=tk.X, padx=8, pady=2)

    def _build_status_bar(self):
        """Build and pack the status bar."""
        self.status_bar = StatusBar(
            self, config=self.config, router=self.router,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

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
        # Check credentials
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

        # Switch mode
        if self.config:
            self.config.mode = "online"

        # Reconfigure network gate
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
        logger.info("Switched to ONLINE mode")

    def _switch_to_offline(self):
        """Switch to offline mode (always safe)."""
        if self.config:
            self.config.mode = "offline"

        # Reconfigure network gate
        try:
            from src.core.network_gate import configure_gate
            configure_gate(mode="offline")
        except Exception as e:
            logger.warning("Gate reconfiguration failed: %s", e)

        self._update_mode_buttons()
        self.status_bar.force_refresh()
        logger.info("Switched to OFFLINE mode")

    # ----------------------------------------------------------------
    # ENGINEERING MENU
    # ----------------------------------------------------------------

    def _open_engineering_menu(self):
        """Open the engineering settings child window."""
        EngineeringMenu(self, config=self.config, query_engine=self.query_engine)

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
        self.destroy()
