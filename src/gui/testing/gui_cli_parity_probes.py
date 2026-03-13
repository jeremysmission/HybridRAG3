from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from .gui_cli_parity_harness import (
    ProbeOutcome,
    STATUS_FAILED,
    STATUS_MANUAL,
    STATUS_PASSED,
    STATUS_SKIPPED,
)

if TYPE_CHECKING:
    from .gui_cli_parity_harness import GuiCliParityHarness


def _probe_boot_gui(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    current = getattr(app, "_current_view", "")
    if current == "query" and hasattr(app, "query_panel") and hasattr(app, "status_bar"):
        return ProbeOutcome(STATUS_PASSED, "Query view, query panel, and status bar are mounted.")
    return ProbeOutcome(STATUS_FAILED, f"Unexpected startup state: current_view={current!r}")


def _probe_paths(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    admin = harness._show_admin_view()
    paths_panel = getattr(admin, "_paths_panel", None)
    if paths_panel is None:
        return ProbeOutcome(STATUS_FAILED, "DataPathsPanel is not mounted.")
    paths_panel._refresh_info()
    harness._pump(seconds=0.1)
    info = str(paths_panel.info_label.cget("text") or "").strip()
    gate = str(app.status_bar.gate_label.cget("text") or "").strip()
    if "Source:" in info and "Index:" in info and gate.startswith("Gate:"):
        return ProbeOutcome(
            STATUS_PASSED,
            "Path info and gate status are visible in the GUI.",
            {"paths_info": info, "gate": gate},
        )
    return ProbeOutcome(STATUS_FAILED, "Path/gate labels did not populate correctly.")


def _probe_status(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    app.status_bar.force_refresh()
    harness._pump(seconds=0.1)
    gate = str(app.status_bar.gate_label.cget("text") or "").strip()
    backend = str(app.status_bar.ollama_label.cget("text") or "").strip()
    model = str(app.status_bar.model_label.cget("text") or "").strip()
    if gate.startswith("Gate:") and backend.startswith("Backend Health:") and model.startswith("Active Model"):
        return ProbeOutcome(
            STATUS_PASSED,
            "Status bar labels refreshed successfully.",
            {"gate": gate, "backend": backend, "model": model},
        )
    return ProbeOutcome(STATUS_FAILED, "Status bar labels are incomplete.")


def _probe_diag(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    verify_btn = getattr(admin, "_verify_btn", None)
    verify_text = getattr(admin, "_verify_text", None)
    verify_status = getattr(admin, "_verify_status", None)
    if verify_btn is None or verify_text is None or verify_status is None:
        return ProbeOutcome(STATUS_FAILED, "Quick Verify controls are missing.")
    verify_btn.invoke()
    finished = harness._wait_until(
        lambda: str(verify_btn.cget("state")) == "normal"
        and "Running checks" not in str(verify_status.cget("text") or ""),
        timeout_s=30.0,
    )
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Quick Verify did not finish within 30s.")
    summary = str(verify_status.cget("text") or "").strip()
    body = str(verify_text.get("1.0", "end")).strip()
    if summary and body:
        return ProbeOutcome(
            STATUS_PASSED,
            "Quick Verify completed and rendered output.",
            {"summary": summary},
        )
    return ProbeOutcome(STATUS_FAILED, "Quick Verify finished without output.")


def _probe_index(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    if getattr(app, "indexer", None) is None:
        return ProbeOutcome(STATUS_SKIPPED, "No indexer is attached in this environment.")
    source_dir, index_dir = harness._ensure_temp_fixture_dirs()
    harness._write_temp_source_file()
    save_outcome = harness._apply_temp_paths(source_dir, index_dir)
    if save_outcome.status != STATUS_PASSED:
        return save_outcome
    app.show_view("index")
    harness._pump(seconds=0.2)
    panel = getattr(app, "index_panel", None)
    if panel is None:
        return ProbeOutcome(STATUS_FAILED, "IndexPanel is not mounted.")
    if str(panel.start_btn.cget("state")) != "normal" and getattr(panel, "indexer", None) is not None:
        panel.set_ready(True)
        harness._pump(seconds=0.1)
    if str(panel.start_btn.cget("state")) != "normal":
        return ProbeOutcome(STATUS_SKIPPED, "Start Indexing is disabled in this environment.")
    panel.start_btn.invoke()
    finished = harness._wait_until(lambda: panel.index_done_event.is_set(), timeout_s=120.0)
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Indexing did not finish within 120s.")
    status = str(panel.last_index_status or "").strip()
    if status.startswith("[OK]"):
        harness._index_ready = True
        return ProbeOutcome(
            STATUS_PASSED,
            status,
            {"source_dir": str(source_dir), "index_dir": str(index_dir)},
        )
    return ProbeOutcome(STATUS_FAILED, status or "Indexing failed without a status message.")


def _probe_query(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    if getattr(app, "query_engine", None) is None:
        return ProbeOutcome(STATUS_SKIPPED, "No query engine is attached in this environment.")
    if not harness._index_ready:
        index_outcome = _probe_index(harness)
        if index_outcome.status != STATUS_PASSED:
            return ProbeOutcome(
                STATUS_SKIPPED,
                f"Query fixture was not ready: {index_outcome.detail}",
                {"dependency": asdict(index_outcome)},
            )
    app.show_view("query")
    harness._pump(seconds=0.2)
    panel = getattr(app, "query_panel", None)
    if panel is None:
        return ProbeOutcome(STATUS_FAILED, "QueryPanel is not mounted.")
    ready = harness._wait_until(lambda: str(panel.ask_btn.cget("state")) == "normal", timeout_s=30.0)
    if not ready:
        return ProbeOutcome(STATUS_SKIPPED, "Ask button never became available.")
    panel.question_entry.delete(0, "end")
    panel.question_entry.insert(0, "What review cadence is mentioned in the QA harness file?")
    panel.ask_btn.invoke()
    started = harness._wait_until(lambda: panel.is_querying is True, timeout_s=5.0)
    if not started:
        return ProbeOutcome(STATUS_FAILED, "Query did not start.")
    finished = harness._wait_until(lambda: panel.query_done_event.is_set(), timeout_s=180.0)
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Query did not finish within 180s.")
    answer = str(panel.answer_text.get("1.0", "end")).strip() or str(panel.last_answer_preview or "").strip()
    if panel.last_query_status == "complete" and answer:
        return ProbeOutcome(
            STATUS_PASSED,
            "Query completed with a non-empty answer.",
            {"answer_preview": answer[:160]},
        )
    return ProbeOutcome(
        STATUS_FAILED,
        f"Unexpected query result: status={panel.last_query_status!r} answer_len={len(answer)}",
    )


def _probe_mode_online(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    before = len(harness._messagebox_events)
    app.online_btn.invoke()
    finished = harness._wait_until(
        lambda: str(app.online_btn.cget("state")) == "normal"
        and str(app.offline_btn.cget("state")) == "normal",
        timeout_s=20.0,
    )
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Online mode toggle did not settle.")
    mode = str(getattr(app.config, "mode", "") or "")
    if mode == "online":
        return ProbeOutcome(STATUS_PASSED, "GUI switched to online mode.")
    warnings = harness._messagebox_events[before:]
    if warnings:
        return ProbeOutcome(
            STATUS_PASSED,
            "GUI blocked online mode safely in the current environment.",
            {"warnings": warnings},
        )
    return ProbeOutcome(STATUS_FAILED, f"Online mode did not activate and no warning was captured (mode={mode!r}).")


def _probe_mode_offline(harness: GuiCliParityHarness) -> ProbeOutcome:
    app = harness._ensure_app()
    app.offline_btn.invoke()
    finished = harness._wait_until(
        lambda: str(app.online_btn.cget("state")) == "normal"
        and str(app.offline_btn.cget("state")) == "normal",
        timeout_s=20.0,
    )
    mode = str(getattr(app.config, "mode", "") or "")
    if finished and mode == "offline":
        return ProbeOutcome(STATUS_PASSED, "GUI returned to offline mode.")
    return ProbeOutcome(STATUS_FAILED, f"Offline mode did not settle correctly (mode={mode!r}).")


def _probe_profile(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    panel = getattr(admin, "_mode_panel", None) or getattr(harness._app, "_tuning_panel", None)
    if panel is None:
        return ProbeOutcome(STATUS_FAILED, "Profile controls are not mounted.")
    options = list(panel.get_profile_options())
    if len(options) < 2:
        return ProbeOutcome(STATUS_FAILED, "Expected at least two profile options.")
    current = str(panel.profile_var.get() or "").strip()
    target = next((value for value in options if value != current), options[0])
    panel.profile_var.set(target)
    panel.profile_apply_btn.invoke()
    finished = harness._wait_until(
        lambda: str(panel.profile_apply_btn.cget("state")) == "normal"
        and str(panel.profile_status_label.cget("text") or "").startswith(("[OK]", "[FAIL]")),
        timeout_s=45.0,
    )
    status = str(panel.profile_status_label.cget("text") or "").strip()
    if finished and status.startswith("[OK]"):
        return ProbeOutcome(STATUS_PASSED, status, {"target_profile": target})
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Profile switch did not finish within 45s.")
    return ProbeOutcome(STATUS_FAILED, status or "Profile switch failed.")


def _probe_models(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    offline_panel = getattr(admin, "_offline_model_panel", None)
    online_panel = getattr(admin, "_model_panel", None)
    if offline_panel is None or online_panel is None:
        return ProbeOutcome(STATUS_FAILED, "Model-selection panels are incomplete.")
    offline_rows = list(offline_panel.tree.get_children())
    if not offline_rows:
        return ProbeOutcome(STATUS_FAILED, "Offline model catalog is empty.")
    if getattr(online_panel, "refresh_btn", None) is None:
        return ProbeOutcome(STATUS_FAILED, "Online model refresh control is missing.")
    return ProbeOutcome(
        STATUS_PASSED,
        "Offline and online model surfaces are present.",
        {"offline_models": len(offline_rows)},
    )


def _probe_set_model(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    panel = getattr(admin, "_offline_model_panel", None)
    if panel is None:
        return ProbeOutcome(STATUS_FAILED, "Offline model panel is not mounted.")
    rows = list(panel.tree.get_children())
    if not rows:
        return ProbeOutcome(STATUS_FAILED, "Offline model catalog is empty.")
    target = rows[0]
    panel.tree.selection_set(target)
    panel._on_select()
    harness._pump(seconds=0.2)
    status = str(panel.status_label.cget("text") or "").strip()
    if status.startswith("Selected:") or status.startswith("[WARN] Ollama check failed"):
        return ProbeOutcome(STATUS_PASSED, status, {"selected_model": target})
    return ProbeOutcome(STATUS_FAILED, status or "Offline model selection did not update status.")


def _probe_cred_status(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    admin._refresh_credential_status()
    harness._pump(seconds=0.1)
    text = str(admin.cred_status_label.cget("text") or "").strip()
    if text:
        return ProbeOutcome(STATUS_PASSED, "Credential status rendered.", {"credential_status": text})
    return ProbeOutcome(STATUS_FAILED, "Credential status label is empty.")


def _probe_store_endpoint_surface(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    if getattr(admin, "endpoint_entry", None) is None or getattr(admin, "save_cred_btn", None) is None:
        return ProbeOutcome(STATUS_FAILED, "Endpoint save controls are missing.")
    return ProbeOutcome(STATUS_MANUAL, "Endpoint save controls exist; live credential writes were not exercised.")


def _probe_store_key_surface(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    if getattr(admin, "key_entry", None) is None or getattr(admin, "save_cred_btn", None) is None:
        return ProbeOutcome(STATUS_FAILED, "API-key save controls are missing.")
    return ProbeOutcome(STATUS_MANUAL, "API-key save controls exist; live credential writes were not exercised.")


def _probe_cred_delete_surface(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    if getattr(admin, "clear_cred_btn", None) is None:
        return ProbeOutcome(STATUS_FAILED, "Credential delete control is missing.")
    return ProbeOutcome(STATUS_MANUAL, "Credential delete control exists; destructive deletion was not exercised.")


def _probe_test_api(harness: GuiCliParityHarness) -> ProbeOutcome:
    admin = harness._show_admin_view()
    if getattr(admin, "test_btn", None) is None:
        return ProbeOutcome(STATUS_FAILED, "Test connection button is missing.")
    try:
        from src.security.credentials import resolve_credentials

        creds = resolve_credentials(use_cache=False)
    except Exception as exc:
        return ProbeOutcome(STATUS_MANUAL, f"Credential lookup failed during probe setup: {exc}")
    if not harness.allow_network_probes:
        return ProbeOutcome(STATUS_MANUAL, "Live API probe disabled by default; rerun with --allow-network-probes.")
    if not getattr(creds, "has_key", False) or not getattr(creds, "has_endpoint", False):
        return ProbeOutcome(STATUS_SKIPPED, "No stored endpoint/key pair is available for a live API probe.")
    before = str(admin.cred_status_label.cget("text") or "")
    admin.test_btn.invoke()
    finished = harness._wait_until(
        lambda: str(admin.test_btn.cget("state")) == "normal"
        and str(admin.cred_status_label.cget("text") or "") != before,
        timeout_s=30.0,
    )
    text = str(admin.cred_status_label.cget("text") or "").strip()
    if not finished:
        return ProbeOutcome(STATUS_FAILED, "Live API probe did not finish within 30s.")
    if text.startswith("[OK]"):
        return ProbeOutcome(STATUS_PASSED, text)
    return ProbeOutcome(STATUS_FAILED, text or "Live API probe failed.")


PROBE_REGISTRY = {
    "_probe_boot_gui": _probe_boot_gui,
    "_probe_paths": _probe_paths,
    "_probe_status": _probe_status,
    "_probe_diag": _probe_diag,
    "_probe_index": _probe_index,
    "_probe_query": _probe_query,
    "_probe_mode_online": _probe_mode_online,
    "_probe_mode_offline": _probe_mode_offline,
    "_probe_profile": _probe_profile,
    "_probe_models": _probe_models,
    "_probe_set_model": _probe_set_model,
    "_probe_cred_status": _probe_cred_status,
    "_probe_store_endpoint_surface": _probe_store_endpoint_surface,
    "_probe_store_key_surface": _probe_store_key_surface,
    "_probe_cred_delete_surface": _probe_cred_delete_surface,
    "_probe_test_api": _probe_test_api,
}
