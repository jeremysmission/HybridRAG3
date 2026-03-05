# QueryPanel runtime: status, rendering, and post-query UX.
from __future__ import annotations

import logging
import time
import tkinter as tk
from tkinter import messagebox

from src.core.cost_tracker import get_cost_tracker
from src.gui.theme import current_theme

logger = logging.getLogger(__name__)

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
    self._set_query_controls(running=False)
    self.network_label.config(text="")

    # Display sources and metrics from the final result
    t = current_theme()
    if result.error:
        detail = (result.answer or result.error or "").strip()
        self._show_error("[FAIL] {}".format(detail))
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
        self._set_query_controls(running=False)
        self.network_label.config(text="")

def _display_result_inner(self, result):
    """Inner display logic (separated so outer can catch and re-enable)."""
    t = current_theme()
    self._set_query_controls(running=False)
    self.network_label.config(text="")
    self._overlay.stop()

    # Check for error
    if result.error:
        detail = (result.answer or result.error or "").strip()
        self._show_error("[FAIL] {}".format(detail))
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
    self._set_query_controls(running=False)
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
    self._maybe_show_memory_tuning_popup(error_msg)

def _maybe_show_memory_tuning_popup(self, error_msg):
    """Show targeted guidance for common offline 500/timeout memory failures."""
    try:
        msg = (error_msg or "").strip()
        low = msg.lower()
        if not low:
            return

        hit_500 = ("500" in low) or ("internal server error" in low)
        hit_timeout = ("timed out" in low) or ("timeout" in low) or ("readtimeout" in low)
        hit_runner = (
            ("llama runner" in low)
            or ("error calling llm" in low)
            or ("llm call failed" in low)
        )
        if not (hit_500 or hit_timeout or hit_runner):
            return

        mode = str(getattr(self.config, "mode", "") or "").lower().strip()
        if mode and mode != "offline":
            return

        now = time.time()
        if (now - float(self._last_mem_popup_ts or 0.0)) < 120:
            return
        self._last_mem_popup_ts = now

        ollama_cfg = getattr(self.config, "ollama", None)
        model = getattr(ollama_cfg, "model", "unknown") if ollama_cfg else "unknown"
        ctx = getattr(ollama_cfg, "context_window", "unknown") if ollama_cfg else "unknown"
        timeout = getattr(ollama_cfg, "timeout_seconds", "unknown") if ollama_cfg else "unknown"

        details = (
            "HybridRAG detected an offline LLM failure commonly caused by model/context memory pressure.\n\n"
            "Current settings:\n"
            "model={}\ncontext_window={}\ntimeout_seconds={}\n\n"
            "Recommended stability tweaks (in order):\n"
            "1) Set model to phi4-mini\n"
            "2) Set context_window to 4096\n"
            "3) Set timeout_seconds to 180\n\n"
            "Where to change:\n"
            "- GUI: Engineering > Admin Settings (Offline/Ollama tuning)\n"
            "- File: config/user_overrides.yaml (takes precedence over defaults)\n\n"
            "Quick validation:\n"
            "- ollama run phi4-mini \"OK\"\n"
            "- ollama ps\n\n"
            "Docs: docs/01_setup/MANUAL_INSTALL.md -> \"Ollama returns HTTP 500 on query/generate\""
        ).format(model, ctx, timeout)
        messagebox.showwarning("Offline LLM Memory Guidance", details, parent=self.winfo_toplevel())
    except Exception as e:
        logger.debug("Memory guidance popup skipped: %s", e)

def set_ready(self, enabled):
    """Enable or disable the Ask button based on backend readiness."""
    t = current_theme()
    if enabled:
        self.ask_btn.config(state=tk.NORMAL, bg=t["accent"],
                            fg=t["accent_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                             fg=t["inactive_btn_fg"])
    else:
        self.ask_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
                            fg=t["inactive_btn_fg"])
        self.stop_btn.config(state=tk.DISABLED, bg=t["inactive_btn_bg"],
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
def bind_query_panel_query_render_runtime_methods(cls):
    """Bind query-render/runtime methods to QueryPanel."""
    cls._set_status = _set_status
    cls._prepare_streaming = _prepare_streaming
    cls._append_token = _append_token
    cls._start_elapsed_timer = _start_elapsed_timer
    cls._update_elapsed = _update_elapsed
    cls._stop_elapsed_timer = _stop_elapsed_timer
    cls._finish_stream = _finish_stream
    cls._display_result = _display_result
    cls._display_result_inner = _display_result_inner
    cls._show_error = _show_error
    cls._maybe_show_memory_tuning_popup = _maybe_show_memory_tuning_popup
    cls.set_ready = set_ready
    cls._emit_cost_event = _emit_cost_event
    cls.get_current_use_case_key = get_current_use_case_key
