# ============================================================================
# HybridRAG v3 -- Engineering Menu (src/gui/panels/engineering_menu.py)
# ============================================================================
# Separate child window for tuning retrieval, LLM, and profile settings.
# Changes take effect immediately and are written to config.
#
# INTERNET ACCESS: Test query may use API if in online mode.
#   Shows "Network: ACTIVE" indicator when online test queries run.
# ============================================================================

import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import sys
import os
import threading
import logging

logger = logging.getLogger(__name__)


class EngineeringMenu(tk.Toplevel):
    """
    Engineering settings window with sliders for retrieval and LLM tuning,
    profile switching, and a test query runner.
    """

    def __init__(self, parent, config, query_engine=None):
        super().__init__(parent)
        self.title("Engineering Settings")
        self.geometry("520x680")
        self.resizable(True, True)
        self.config = config
        self.query_engine = query_engine

        # Store original values for reset
        self._original_values = self._capture_values()

        # Build sections
        self._build_retrieval_section()
        self._build_llm_section()
        self._build_profile_section()
        self._build_test_section()
        self._build_buttons()

    def _capture_values(self):
        """Capture current config values for reset."""
        retrieval = getattr(self.config, "retrieval", None)
        api = getattr(self.config, "api", None)
        return {
            "top_k": getattr(retrieval, "top_k", 8) if retrieval else 8,
            "min_score": getattr(retrieval, "min_score", 0.20) if retrieval else 0.20,
            "hybrid_search": getattr(retrieval, "hybrid_search", True) if retrieval else True,
            "reranker_enabled": getattr(retrieval, "reranker_enabled", False) if retrieval else False,
            "max_tokens": getattr(api, "max_tokens", 2048) if api else 2048,
            "temperature": getattr(api, "temperature", 0.1) if api else 0.1,
            "timeout_seconds": getattr(api, "timeout_seconds", 30) if api else 30,
        }

    # ----------------------------------------------------------------
    # RETRIEVAL SETTINGS
    # ----------------------------------------------------------------

    def _build_retrieval_section(self):
        """Build retrieval settings section."""
        frame = tk.LabelFrame(self, text="Retrieval Settings", padx=8, pady=4)
        frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        retrieval = getattr(self.config, "retrieval", None)

        # top_k slider
        row_tk = tk.Frame(frame)
        row_tk.pack(fill=tk.X, pady=2)
        tk.Label(row_tk, text="top_k:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.topk_var = tk.IntVar(
            value=getattr(retrieval, "top_k", 8) if retrieval else 8
        )
        self.topk_scale = tk.Scale(
            row_tk, from_=1, to=50, orient=tk.HORIZONTAL,
            variable=self.topk_var, command=lambda v: self._on_retrieval_change(),
        )
        self.topk_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # min_score slider
        row_ms = tk.Frame(frame)
        row_ms.pack(fill=tk.X, pady=2)
        tk.Label(row_ms, text="min_score:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.minscore_var = tk.DoubleVar(
            value=getattr(retrieval, "min_score", 0.20) if retrieval else 0.20
        )
        self.minscore_scale = tk.Scale(
            row_ms, from_=0.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
            variable=self.minscore_var, command=lambda v: self._on_retrieval_change(),
        )
        self.minscore_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Hybrid search toggle
        row_hs = tk.Frame(frame)
        row_hs.pack(fill=tk.X, pady=2)
        tk.Label(row_hs, text="Hybrid search:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.hybrid_var = tk.BooleanVar(
            value=getattr(retrieval, "hybrid_search", True) if retrieval else True
        )
        tk.Checkbutton(
            row_hs, variable=self.hybrid_var,
            command=self._on_retrieval_change,
        ).pack(side=tk.LEFT)

        # Reranker toggle
        row_rr = tk.Frame(frame)
        row_rr.pack(fill=tk.X, pady=2)
        tk.Label(row_rr, text="Reranker:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.reranker_var = tk.BooleanVar(
            value=getattr(retrieval, "reranker_enabled", False) if retrieval else False
        )
        tk.Checkbutton(
            row_rr, variable=self.reranker_var,
            command=self._on_retrieval_change,
        ).pack(side=tk.LEFT)

    def _on_retrieval_change(self):
        """Write retrieval settings to config immediately."""
        retrieval = getattr(self.config, "retrieval", None)
        if retrieval:
            retrieval.top_k = self.topk_var.get()
            retrieval.min_score = self.minscore_var.get()
            retrieval.hybrid_search = self.hybrid_var.get()
            retrieval.reranker_enabled = self.reranker_var.get()

    # ----------------------------------------------------------------
    # LLM SETTINGS
    # ----------------------------------------------------------------

    def _build_llm_section(self):
        """Build LLM settings section."""
        frame = tk.LabelFrame(self, text="LLM Settings", padx=8, pady=4)
        frame.pack(fill=tk.X, padx=8, pady=4)

        api = getattr(self.config, "api", None)

        # Max tokens slider
        row_mt = tk.Frame(frame)
        row_mt.pack(fill=tk.X, pady=2)
        tk.Label(row_mt, text="Max tokens:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.maxtokens_var = tk.IntVar(
            value=getattr(api, "max_tokens", 2048) if api else 2048
        )
        self.maxtokens_scale = tk.Scale(
            row_mt, from_=256, to=4096, orient=tk.HORIZONTAL,
            variable=self.maxtokens_var, command=lambda v: self._on_llm_change(),
        )
        self.maxtokens_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Temperature slider
        row_temp = tk.Frame(frame)
        row_temp.pack(fill=tk.X, pady=2)
        tk.Label(row_temp, text="Temperature:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.temp_var = tk.DoubleVar(
            value=getattr(api, "temperature", 0.1) if api else 0.1
        )
        self.temp_scale = tk.Scale(
            row_temp, from_=0.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL,
            variable=self.temp_var, command=lambda v: self._on_llm_change(),
        )
        self.temp_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Timeout slider
        row_to = tk.Frame(frame)
        row_to.pack(fill=tk.X, pady=2)
        tk.Label(row_to, text="Timeout (s):", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.timeout_var = tk.IntVar(
            value=getattr(api, "timeout_seconds", 30) if api else 30
        )
        self.timeout_scale = tk.Scale(
            row_to, from_=10, to=120, orient=tk.HORIZONTAL,
            variable=self.timeout_var, command=lambda v: self._on_llm_change(),
        )
        self.timeout_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _on_llm_change(self):
        """Write LLM settings to config immediately."""
        api = getattr(self.config, "api", None)
        if api:
            api.max_tokens = self.maxtokens_var.get()
            api.temperature = self.temp_var.get()
            api.timeout_seconds = self.timeout_var.get()

    # ----------------------------------------------------------------
    # PERFORMANCE PROFILE
    # ----------------------------------------------------------------

    def _build_profile_section(self):
        """Build performance profile section."""
        frame = tk.LabelFrame(self, text="Performance Profile", padx=8, pady=4)
        frame.pack(fill=tk.X, padx=8, pady=4)

        row = tk.Frame(frame)
        row.pack(fill=tk.X, pady=2)

        tk.Label(row, text="Profile:", width=14, anchor=tk.W).pack(side=tk.LEFT)

        profiles = ["laptop_safe", "desktop_power", "server_max"]
        self.profile_var = tk.StringVar(value="laptop_safe")
        self.profile_dropdown = ttk.Combobox(
            row, textvariable=self.profile_var, values=profiles,
            state="readonly", width=20,
        )
        self.profile_dropdown.pack(side=tk.LEFT, padx=(8, 0))
        self.profile_dropdown.bind("<<ComboboxSelected>>", self._on_profile_change)

        self.profile_status_label = tk.Label(
            frame, text="", anchor=tk.W, fg="gray",
        )
        self.profile_status_label.pack(fill=tk.X, pady=2)

        # Load current profile status
        self._load_profile_status()

    def _load_profile_status(self):
        """Read current profile from _profile_status.py."""
        try:
            root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
            result = subprocess.run(
                [sys.executable, os.path.join(root, "scripts", "_profile_status.py")],
                capture_output=True, text=True, timeout=5,
                cwd=root,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                self.profile_status_label.config(text=output[:80])
                # Infer current profile from output
                if "laptop_safe" in output:
                    self.profile_var.set("laptop_safe")
                elif "desktop_power" in output:
                    self.profile_var.set("desktop_power")
                elif "server_max" in output:
                    self.profile_var.set("server_max")
        except Exception as e:
            self.profile_status_label.config(
                text="[WARN] Could not read profile: {}".format(e),
            )

    def _on_profile_change(self, event=None):
        """Call _profile_switch.py when profile changes."""
        profile = self.profile_var.get()
        root = os.environ.get("HYBRIDRAG_PROJECT_ROOT", ".")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(root, "scripts", "_profile_switch.py"), profile],
                capture_output=True, text=True, timeout=10,
                cwd=root,
            )
            if result.returncode == 0:
                self.profile_status_label.config(
                    text="[OK] Switched to {}".format(profile), fg="green",
                )
            else:
                self.profile_status_label.config(
                    text="[FAIL] {}".format(result.stderr.strip()[:60]), fg="red",
                )
        except Exception as e:
            self.profile_status_label.config(
                text="[FAIL] {}".format(str(e)[:60]), fg="red",
            )

    # ----------------------------------------------------------------
    # TEST QUERY
    # ----------------------------------------------------------------

    def _build_test_section(self):
        """Build test query section."""
        frame = tk.LabelFrame(self, text="Test Query", padx=8, pady=4)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Input row
        row = tk.Frame(frame)
        row.pack(fill=tk.X, pady=2)

        self.test_entry = tk.Entry(row, font=("TkDefaultFont", 9))
        self.test_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.test_entry.bind("<Return>", self._on_test_query)

        self.test_btn = tk.Button(
            row, text="Run Test", command=self._on_test_query, width=10,
        )
        self.test_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Network indicator for test query
        self.test_network_label = tk.Label(
            frame, text="", anchor=tk.W, fg="gray",
        )
        self.test_network_label.pack(fill=tk.X)

        # Result area
        self.test_result = scrolledtext.ScrolledText(
            frame, height=4, wrap=tk.WORD, state=tk.DISABLED,
            font=("TkDefaultFont", 9),
        )
        self.test_result.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # Latency
        self.test_latency_label = tk.Label(
            frame, text="", anchor=tk.W, fg="gray",
        )
        self.test_latency_label.pack(fill=tk.X)

    def _on_test_query(self, event=None):
        """Run a test query with current settings."""
        question = self.test_entry.get().strip()
        if not question:
            return

        if self.query_engine is None:
            self.test_result.config(state=tk.NORMAL)
            self.test_result.delete("1.0", tk.END)
            self.test_result.insert("1.0", "[FAIL] Query engine not initialized")
            self.test_result.config(state=tk.DISABLED)
            return

        self.test_btn.config(state=tk.DISABLED)

        # Show network indicator
        mode = getattr(self.config, "mode", "offline")
        if mode == "online":
            self.test_network_label.config(text="Network: ACTIVE", fg="#CC8800")
        else:
            self.test_network_label.config(text="Network: offline", fg="gray")

        thread = threading.Thread(
            target=self._run_test_query, args=(question,), daemon=True,
        )
        thread.start()

    def _run_test_query(self, question):
        """Execute test query in background."""
        try:
            result = self.query_engine.query(question)
            self.after(0, self._display_test_result, result)
        except Exception as e:
            self.after(0, self._display_test_error, str(e))

    def _display_test_result(self, result):
        """Show test query result."""
        self.test_btn.config(state=tk.NORMAL)
        self.test_network_label.config(text="")

        self.test_result.config(state=tk.NORMAL)
        self.test_result.delete("1.0", tk.END)
        if result.error:
            self.test_result.insert("1.0", "[FAIL] {}".format(result.error))
        else:
            self.test_result.insert("1.0", result.answer[:500])
        self.test_result.config(state=tk.DISABLED)

        self.test_latency_label.config(
            text="Latency: {:,.0f} ms".format(result.latency_ms),
        )

    def _display_test_error(self, error_msg):
        """Show test query error."""
        self.test_btn.config(state=tk.NORMAL)
        self.test_network_label.config(text="")

        self.test_result.config(state=tk.NORMAL)
        self.test_result.delete("1.0", tk.END)
        self.test_result.insert("1.0", "[FAIL] {}".format(error_msg))
        self.test_result.config(state=tk.DISABLED)

    # ----------------------------------------------------------------
    # BOTTOM BUTTONS
    # ----------------------------------------------------------------

    def _build_buttons(self):
        """Build Reset and Close buttons."""
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)

        tk.Button(
            btn_frame, text="Reset to Defaults", command=self._on_reset, width=16,
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_frame, text="Close", command=self.destroy, width=10,
        ).pack(side=tk.RIGHT)

    def _on_reset(self):
        """Reset all sliders to original values."""
        orig = self._original_values
        self.topk_var.set(orig["top_k"])
        self.minscore_var.set(orig["min_score"])
        self.hybrid_var.set(orig["hybrid_search"])
        self.reranker_var.set(orig["reranker_enabled"])
        self.maxtokens_var.set(orig["max_tokens"])
        self.temp_var.set(orig["temperature"])
        self.timeout_var.set(orig["timeout_seconds"])

        # Write reset values to config
        self._on_retrieval_change()
        self._on_llm_change()
