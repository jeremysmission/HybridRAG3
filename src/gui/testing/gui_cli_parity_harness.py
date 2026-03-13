from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_MISSING = "missing_gui_surface"
STATUS_MANUAL = "manual_check_required"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = PROJECT_ROOT / ".tmp_gui_cli_parity"


@dataclass(frozen=True)
class CliParityCheck:
    cli_command: str
    title: str
    category: str
    gui_surface: str
    probe_name: str | None = None
    notes: str = ""
    requires_backends: bool = False


@dataclass
class ProbeOutcome:
    status: str
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CliParityResult:
    cli_command: str
    title: str
    category: str
    gui_surface: str
    status: str
    detail: str = ""
    notes: str = ""
    elapsed_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_CLI_CHECKS: tuple[CliParityCheck, ...] = (
    CliParityCheck(
        cli_command="rag-gui",
        title="Boot GUI shell",
        category="launcher",
        gui_surface="HybridRAGApp",
        probe_name="_probe_boot_gui",
        notes="Confirms the GUI shell boots headlessly for QA automation.",
    ),
    CliParityCheck(
        cli_command="rag-paths",
        title="Inspect configured paths",
        category="admin",
        gui_surface="ApiAdminTab > DataPathsPanel + StatusBar",
        probe_name="_probe_paths",
        notes="Maps the CLI path/status shortcut to the admin path panel and status bar.",
    ),
    CliParityCheck(
        cli_command="rag-status",
        title="Inspect runtime status",
        category="status",
        gui_surface="StatusBar",
        probe_name="_probe_status",
        notes="Covers the lightweight runtime health surface already visible in the GUI.",
    ),
    CliParityCheck(
        cli_command="rag-diag",
        title="Run quick verification",
        category="status",
        gui_surface="ApiAdminTab > Quick Verify",
        probe_name="_probe_diag",
        notes="Uses the GUI quick-verify panel as the current diagnostic equivalent.",
    ),
    CliParityCheck(
        cli_command="rag-index",
        title="Index sample data",
        category="core",
        gui_surface="IndexPanel",
        probe_name="_probe_index",
        notes="Indexes a temporary QA fixture through the GUI.",
        requires_backends=True,
    ),
    CliParityCheck(
        cli_command="rag-query",
        title="Query indexed sample data",
        category="core",
        gui_surface="QueryPanel",
        probe_name="_probe_query",
        notes="Queries the indexed QA fixture through the GUI.",
        requires_backends=True,
    ),
    CliParityCheck(
        cli_command="rag-mode-online",
        title="Attempt online mode switch",
        category="mode",
        gui_surface="Title bar mode toggle",
        probe_name="_probe_mode_online",
        notes="Passes on a real switch or a safe credentials warning path.",
    ),
    CliParityCheck(
        cli_command="rag-mode-offline",
        title="Return to offline mode",
        category="mode",
        gui_surface="Title bar mode toggle",
        probe_name="_probe_mode_offline",
        notes="Ensures the GUI returns to offline mode cleanly.",
    ),
    CliParityCheck(
        cli_command="rag-profile",
        title="Switch hardware profile",
        category="admin",
        gui_surface="TuningTab profile controls",
        probe_name="_probe_profile",
        notes="Exercises the profile dropdown path that should replace the CLI profile switch.",
    ),
    CliParityCheck(
        cli_command="rag-models",
        title="Browse available models",
        category="admin",
        gui_surface="OfflineModelSelectionPanel + ModelSelectionPanel",
        probe_name="_probe_models",
        notes="Covers both offline model catalog visibility and online model refresh controls.",
    ),
    CliParityCheck(
        cli_command="rag-set-model",
        title="Select an offline model",
        category="admin",
        gui_surface="OfflineModelSelectionPanel",
        probe_name="_probe_set_model",
        notes="Selects a model row in the offline model catalog.",
    ),
    CliParityCheck(
        cli_command="rag-cred-status",
        title="Read credential status",
        category="credentials",
        gui_surface="ApiAdminTab credential status label",
        probe_name="_probe_cred_status",
        notes="Read-only credential inspection is safe to automate by default.",
    ),
    CliParityCheck(
        cli_command="rag-store-endpoint",
        title="Save API endpoint",
        category="credentials",
        gui_surface="ApiAdminTab endpoint entry + save button",
        probe_name="_probe_store_endpoint_surface",
        notes="Surface is verified automatically; live credential mutation stays manual by default.",
    ),
    CliParityCheck(
        cli_command="rag-store-key",
        title="Save API key",
        category="credentials",
        gui_surface="ApiAdminTab key entry + save button",
        probe_name="_probe_store_key_surface",
        notes="Surface is verified automatically; live credential mutation stays manual by default.",
    ),
    CliParityCheck(
        cli_command="rag-cred-delete",
        title="Delete stored credentials",
        category="credentials",
        gui_surface="ApiAdminTab clear credentials button",
        probe_name="_probe_cred_delete_surface",
        notes="Destructive credential deletion is intentionally left as a manual QA step.",
    ),
    CliParityCheck(
        cli_command="rag-test-api",
        title="Test API connectivity",
        category="credentials",
        gui_surface="ApiAdminTab test connection button",
        probe_name="_probe_test_api",
        notes="Can be promoted from manual to automated when QA opts into live network probes.",
    ),
    CliParityCheck(
        cli_command="rag-server",
        title="Launch REST server from GUI",
        category="missing",
        gui_surface="No GUI server-control surface wired yet",
        notes="Placeholder parity target for the future GUI.",
    ),
)


class GuiCliParityHarness:
    def __init__(
        self,
        *,
        checks: Sequence[CliParityCheck] | None = None,
        project_root: Path | None = None,
        boot_app: Callable[[], Any] | None = None,
        attach_backends: Callable[[Any], Any] | None = None,
        attach_mode: str = "auto",
        allow_network_probes: bool = False,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT)
        self.checks = tuple(checks or DEFAULT_CLI_CHECKS)
        self.attach_mode = str(attach_mode or "auto").strip().lower()
        self.allow_network_probes = bool(allow_network_probes)
        self.boot_app = boot_app or self._default_boot_app
        self.attach_backends = attach_backends or self._default_attach_backends
        self._app = None
        self._backends_attached = False
        self._messagebox_events: list[dict[str, str]] = []
        self._temp_run_dir: Path | None = None
        self._temp_source_dir: Path | None = None
        self._temp_index_dir: Path | None = None
        self._index_ready = False

    def available_commands(self) -> list[str]:
        return [check.cli_command for check in self.checks]

    def run(
        self,
        *,
        only: Iterable[str] | None = None,
        skip: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        selected = self._select_checks(only=only, skip=skip)
        results: list[CliParityResult] = []
        with self._config_guard(), self._messagebox_guard():
            try:
                for check in selected:
                    results.append(self._run_check(check))
            finally:
                self._shutdown()
        counts = self._count_statuses(results)
        return {
            "report_name": "gui_cli_parity",
            "timestamp": datetime.now().astimezone().isoformat(),
            "attach_mode": self.attach_mode,
            "allow_network_probes": self.allow_network_probes,
            "ok": counts[STATUS_FAILED] == 0,
            "strict_ok": counts[STATUS_FAILED] == 0
            and counts[STATUS_MISSING] == 0
            and counts[STATUS_MANUAL] == 0,
            "counts": counts,
            "selected_commands": [check.cli_command for check in selected],
            "results": [asdict(result) for result in results],
            "workspace": str(self.project_root),
            "elapsed_s": round(time.time() - started, 2),
        }

    def write_report(self, report: dict[str, Any], path: str | os.PathLike[str]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return target

    def _select_checks(
        self,
        *,
        only: Iterable[str] | None,
        skip: Iterable[str] | None,
    ) -> list[CliParityCheck]:
        selected = list(self.checks)
        if only:
            wanted = {value.strip() for value in only if value and value.strip()}
            selected = [check for check in selected if check.cli_command in wanted]
        if skip:
            skipped = {value.strip() for value in skip if value and value.strip()}
            selected = [check for check in selected if check.cli_command not in skipped]
        return selected

    def _run_check(self, check: CliParityCheck) -> CliParityResult:
        started = time.perf_counter()
        try:
            if check.probe_name is None:
                outcome = ProbeOutcome(
                    STATUS_MISSING,
                    "No GUI parity surface is wired for this CLI command yet.",
                )
            else:
                self._ensure_app()
                probe = getattr(self, check.probe_name, None)
                if probe is None:
                    from src.gui.testing.gui_cli_parity_probes import PROBE_REGISTRY

                    probe = PROBE_REGISTRY[check.probe_name]
                if check.requires_backends:
                    ready, detail = self._ensure_backends()
                    if not ready:
                        outcome = ProbeOutcome(STATUS_SKIPPED, detail)
                    else:
                        outcome = probe() if getattr(probe, "__self__", None) is self else probe(self)
                else:
                    outcome = probe() if getattr(probe, "__self__", None) is self else probe(self)
        except Exception as exc:
            outcome = ProbeOutcome(
                STATUS_FAILED,
                f"{type(exc).__name__}: {exc}",
                {"traceback": traceback.format_exc()},
            )
        return CliParityResult(
            cli_command=check.cli_command,
            title=check.title,
            category=check.category,
            gui_surface=check.gui_surface,
            status=outcome.status,
            detail=outcome.detail,
            notes=check.notes,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            metadata=outcome.metadata,
        )

    def _default_boot_app(self) -> Any:
        from src.gui.testing.gui_boot import boot_headless

        app = boot_headless()
        if hasattr(app, "withdraw"):
            app.withdraw()
        self._pump(seconds=0.2)
        return app

    def _default_attach_backends(self, app: Any) -> Any:
        from src.gui.testing.gui_boot import attach_backends_sync

        return attach_backends_sync(app, timeout_s=60)

    def _ensure_app(self) -> Any:
        if self._app is None:
            self._app = self.boot_app()
        return self._app

    def _ensure_backends(self) -> tuple[bool, str]:
        if self._backends_attached:
            return True, "Backends already attached."
        if self.attach_mode == "never":
            return False, "Harness is running without backend attach."
        app = self._ensure_app()
        self.attach_backends(app)
        self._pump(seconds=0.5)
        if self._live_backend_available(app):
            self._backends_attached = True
            return True, "Backends attached."
        if self.attach_mode == "always":
            return False, "Backend attach finished but no live backend became available."
        return False, self._backend_limit_detail(app)

    def _show_admin_view(self) -> Any:
        app = self._ensure_app()
        app.show_view("admin")
        self._pump(seconds=0.2)
        admin = getattr(app, "_admin_panel", None)
        if admin is None:
            raise RuntimeError("Admin view did not mount.")
        return admin

    def _apply_temp_paths(self, source_dir: Path, index_dir: Path) -> ProbeOutcome:
        admin = self._show_admin_view()
        panel = getattr(admin, "_paths_panel", None)
        if panel is None:
            return ProbeOutcome(STATUS_FAILED, "DataPathsPanel is not mounted.")
        panel.persist_source_var.set(False)
        panel.persist_index_var.set(False)
        panel.source_var.set(str(source_dir))
        panel.index_var.set(str(index_dir))
        panel._on_save()
        self._pump(seconds=0.2)
        status = str(panel.status_label.cget("text") or "").strip()
        if status.startswith("[OK]"):
            return ProbeOutcome(STATUS_PASSED, status)
        return ProbeOutcome(STATUS_FAILED, status or "Could not apply temporary source/index paths.")

    def _ensure_temp_fixture_dirs(self) -> tuple[Path, Path]:
        if self._temp_source_dir is not None and self._temp_index_dir is not None:
            return self._temp_source_dir, self._temp_index_dir
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self._temp_run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=str(TMP_ROOT)))
        self._temp_source_dir = self._temp_run_dir / "source"
        self._temp_index_dir = self._temp_run_dir / "index"
        self._temp_source_dir.mkdir(parents=True, exist_ok=True)
        self._temp_index_dir.mkdir(parents=True, exist_ok=True)
        return self._temp_source_dir, self._temp_index_dir

    def _write_temp_source_file(self) -> Path:
        source_dir, _ = self._ensure_temp_fixture_dirs()
        doc = source_dir / "qa_harness_sample.txt"
        doc.write_text(
            "Quarterly calibration review cadence is every 90 days.\n"
            "This file exists only for the GUI CLI parity harness.\n",
            encoding="utf-8",
        )
        return doc

    def _pump(self, *, seconds: float = 0.1) -> None:
        from src.gui.helpers.safe_after import drain_ui_queue

        app = self._app
        if app is None:
            return
        end = time.time() + seconds
        while time.time() < end:
            try:
                app.update_idletasks()
                app.update()
                drain_ui_queue()
            except Exception:
                break
            time.sleep(0.01)

    def _wait_until(self, predicate: Callable[[], bool], *, timeout_s: float) -> bool:
        started = time.time()
        while time.time() - started < timeout_s:
            try:
                if predicate():
                    return True
            except Exception:
                pass
            self._pump(seconds=0.1)
        return False

    def _live_backend_available(self, app: Any) -> bool:
        boot_result = getattr(app, "boot_result", None)
        if boot_result is None:
            return bool(getattr(app, "query_engine", None) or getattr(app, "indexer", None))
        return bool(
            getattr(boot_result, "offline_available", False)
            or getattr(boot_result, "online_available", False)
            or getattr(app, "query_engine", None)
            or getattr(app, "indexer", None)
        )

    def _backend_limit_detail(self, app: Any) -> str:
        boot_result = getattr(app, "boot_result", None)
        if boot_result is None:
            return "No live backend is attached."
        details = []
        if not getattr(boot_result, "offline_available", False):
            details.append("offline backend unavailable")
        if not getattr(boot_result, "online_available", False):
            details.append("online backend unavailable")
        warnings = getattr(boot_result, "warnings", None) or []
        if warnings:
            details.append(str(warnings[-1]))
        return "; ".join(details) if details else "No live backend is attached."

    @contextmanager
    def _config_guard(self):
        files = [
            self.project_root / "config" / "config.yaml",
            self.project_root / "config" / "user_modes.yaml",
        ]
        snapshot: dict[Path, str | None] = {}
        for path in files:
            snapshot[path] = path.read_text(encoding="utf-8") if path.exists() else None
        try:
            yield
        finally:
            for path, text in snapshot.items():
                if text is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")

    @contextmanager
    def _messagebox_guard(self):
        from tkinter import messagebox

        originals = {
            name: getattr(messagebox, name)
            for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel")
            if hasattr(messagebox, name)
        }

        def _capture(name: str):
            def _inner(title: str = "", message: str = "", *args: Any, **kwargs: Any) -> Any:
                self._messagebox_events.append(
                    {
                        "kind": name,
                        "title": str(title or ""),
                        "message": str(message or ""),
                    }
                )
                if name.startswith("ask"):
                    return True
                return None

            return _inner

        try:
            for name in originals:
                setattr(messagebox, name, _capture(name))
            yield
        finally:
            for name, original in originals.items():
                setattr(messagebox, name, original)

    def _shutdown(self) -> None:
        if self._app is not None:
            try:
                if hasattr(self._app, "status_bar"):
                    self._app.status_bar.stop()
            except Exception:
                pass
            try:
                self._app.destroy()
            except Exception:
                pass
        self._app = None
        self._backends_attached = False
        self._index_ready = False
        if self._temp_run_dir and self._temp_run_dir.exists():
            shutil.rmtree(self._temp_run_dir, ignore_errors=True)
        self._temp_run_dir = None
        self._temp_source_dir = None
        self._temp_index_dir = None

    @staticmethod
    def _count_statuses(results: Sequence[CliParityResult]) -> dict[str, int]:
        counts = {
            STATUS_PASSED: 0,
            STATUS_FAILED: 0,
            STATUS_SKIPPED: 0,
            STATUS_MISSING: 0,
            STATUS_MANUAL: 0,
        }
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        return counts
