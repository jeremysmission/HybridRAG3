# ============================================================================
# HybridRAG v3 -- Status Bar Panel (src/gui/panels/status_bar.py)
# ============================================================================
# Displays live system status: LLM backend, Ollama, and network gate state.
# Updates every 5 seconds via a background timer.
#
# INTERNET ACCESS: NONE (reads local state only)
# ============================================================================

import tkinter as tk
import threading
import logging

logger = logging.getLogger(__name__)


class StatusBar(tk.Frame):
    """
    Bottom status bar showing LLM, Ollama, and Gate status.

    Updates every 5 seconds by calling router.get_status().
    """

    REFRESH_MS = 5000  # 5 seconds

    def __init__(self, parent, config, router=None):
        super().__init__(parent, relief=tk.SUNKEN, bd=1)
        self.config = config
        self.router = router
        self._stop_event = threading.Event()

        # -- LLM indicator --
        self.llm_label = tk.Label(
            self, text="LLM: Not configured", anchor=tk.W,
            padx=8, pady=2,
        )
        self.llm_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Separator --
        sep1 = tk.Frame(self, width=1, bg="gray")
        sep1.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)

        # -- Ollama indicator --
        self.ollama_label = tk.Label(
            self, text="Ollama: Unknown", anchor=tk.W,
            padx=8, pady=2,
        )
        self.ollama_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Separator --
        sep2 = tk.Frame(self, width=1, bg="gray")
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)

        # -- Gate indicator (clickable) --
        self.gate_dot = tk.Label(self, text=" ", width=2, padx=2)
        self.gate_dot.pack(side=tk.LEFT, padx=(8, 2))

        self.gate_label = tk.Label(
            self, text="Gate: OFFLINE", anchor=tk.W,
            padx=2, pady=2, cursor="hand2",
        )
        self.gate_label.pack(side=tk.LEFT, padx=(0, 8))
        self.gate_label.bind("<Button-1>", self._on_gate_click)

        # -- Start periodic refresh --
        self._schedule_refresh()

    def _schedule_refresh(self):
        """Schedule next status refresh."""
        if not self._stop_event.is_set():
            self._refresh_status()
            self.after(self.REFRESH_MS, self._schedule_refresh)

    def _refresh_status(self):
        """Update all status indicators from current state."""
        try:
            self._update_gate_display()
            if self.router:
                self._update_from_router()
            else:
                self._update_no_router()
        except Exception as e:
            logger.debug("Status bar refresh error: %s", e)

    def _update_from_router(self):
        """Update LLM and Ollama indicators from router status."""
        try:
            status = self.router.get_status()
        except Exception:
            self.llm_label.config(text="LLM: Error reading status")
            self.ollama_label.config(text="Ollama: Unknown")
            return

        # LLM
        mode = status.get("mode", "offline")
        if mode == "online" and status.get("api_configured"):
            provider = status.get("api_provider", "API")
            deployment = status.get("api_deployment", "")
            if deployment:
                self.llm_label.config(
                    text="LLM: {} ({})".format(deployment, provider)
                )
            else:
                self.llm_label.config(
                    text="LLM: {} ({})".format(
                        status.get("api_endpoint", "configured")[:30],
                        provider,
                    )
                )
        elif mode == "offline":
            model = getattr(self.config, "ollama", None)
            model_name = getattr(model, "model", "phi4-mini") if model else "phi4-mini"
            self.llm_label.config(
                text="LLM: {} (Ollama)".format(model_name)
            )
        else:
            self.llm_label.config(text="LLM: Not configured")

        # Ollama
        ollama_up = status.get("ollama_available", False)
        if ollama_up:
            self.ollama_label.config(text="Ollama: Ready", fg="green")
        else:
            self.ollama_label.config(text="Ollama: Offline", fg="gray")

    def _update_no_router(self):
        """Display when no router is available."""
        self.llm_label.config(text="LLM: Not initialized")
        self.ollama_label.config(text="Ollama: Unknown", fg="gray")

    def _update_gate_display(self):
        """Update gate indicator from config mode."""
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            self.gate_label.config(text="Gate: ONLINE", fg="green")
            self.gate_dot.config(bg="green")
        else:
            self.gate_label.config(text="Gate: OFFLINE", fg="gray")
            self.gate_dot.config(bg="gray")

    def _on_gate_click(self, event=None):
        """Toggle gate mode when clicked. Delegates to parent app."""
        parent_app = self._find_app()
        if parent_app and hasattr(parent_app, "toggle_mode"):
            current = getattr(self.config, "mode", "offline")
            new_mode = "offline" if current == "online" else "online"
            parent_app.toggle_mode(new_mode)

    def _find_app(self):
        """Walk up widget tree to find the HybridRAGApp instance."""
        widget = self.master
        while widget is not None:
            if hasattr(widget, "toggle_mode"):
                return widget
            widget = getattr(widget, "master", None)
        return None

    def force_refresh(self):
        """Immediately refresh all indicators."""
        self._refresh_status()

    def stop(self):
        """Stop the periodic refresh timer."""
        self._stop_event.set()
