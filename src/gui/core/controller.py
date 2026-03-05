# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the controller part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# Central controller coordinating GUI state, jobs, diagnostics, and downloads
from __future__ import annotations
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .actions import ImportSourceAction, IndexAction, QueryAction, ExportCsvAction, SaveNoteAction
from .diagnostics import Diagnostics
from .downloads import DownloadsRegistry
from .events import GuiEvent, make_event
from .job_runner import JobRunner
from .paths import AppPaths, dated_download_dir, make_download_filename


@dataclass
class AppState:
    """Plain-English: Holds shared AppState values that other methods read and update."""
    mode: str = "offline"
    last_error: Optional[str] = None
    last_query_answer: Optional[str] = None


class Controller:
    """Plain-English: Centralizes Controller behavior for the controller runtime workflow."""
    def __init__(self, paths: AppPaths) -> None:
        """Plain-English: Sets up the Controller object and prepares state used by its methods."""
        run_id = f"run_{uuid.uuid4()}"
        run_dir = paths.new_run_folder(run_id)
        self.paths = paths
        self.diag = Diagnostics.create(run_id, run_dir)
        self.downloads = DownloadsRegistry()
        self.state = AppState()
        self.runner = JobRunner(self.diag, self._on_event)

        # baseline manifest
        self.diag.write_env()
        self._manifest: Dict[str, Any] = {
            "run_id": run_id,
            "run_dir": run_dir,
            "downloads_root": paths.downloads_root,
            "diagnostics_root": paths.diagnostics_root,
            "mode": self.state.mode,
            "stage_counts": {},
            "downloads": [],
        }
        self.diag.write_manifest(self._manifest)
        self._emit(make_event("gui_ready", self.diag.run_id, message="GUI core ready"))

    def _emit(self, ev: GuiEvent) -> None:
        """Plain-English: Records and publishes a GUI event so logs, manifests, and listeners stay in sync."""
        self.diag.write_event(ev)
        self.diag.log(f"{ev.timestamp} {ev.event} job_id={ev.job_id or ''} {ev.message}")
        # keep manifest updated for downloads
        self._manifest["downloads"] = self.downloads.list()
        self.diag.write_manifest(self._manifest)

    def _on_event(self, ev: GuiEvent) -> None:
        # store last error for UI
        """Plain-English: Handles incoming job events and captures error state for the UI when needed."""
        if ev.event == "job_failed":
            self.state.last_error = ev.message
        self._emit(ev)

    def dispatch_import_source(self, act: ImportSourceAction) -> None:
        """Plain-English: Starts the import source workflow and routes work to the right handler."""
        def _work() -> None:
            """Plain-English: Contains the background-job body that does the heavy work for this action."""
            from src.tools.bulk_transfer_v2 import BulkTransferV2, TransferConfig
            from src.core.config import load_config
            cfg = load_config()
            self._emit(
                make_event("data_scan_started", self.diag.run_id, message=act.source_folder)
            )
            transfer_cfg = TransferConfig(
                source_paths=[act.source_folder],
                dest_path=str(cfg.paths.source_folder),
                workers=8,
            )
            bt = BulkTransferV2(transfer_cfg)
            bt.run()
            self._emit(
                make_event(
                    "data_import_completed",
                    self.diag.run_id,
                    message=act.source_folder,
                    mode=getattr(cfg, "mode", "unknown"),
                    dest=str(cfg.paths.source_folder),
                )
            )
        self.runner.run_bg("import_source", _work)

    def dispatch_index(self, act: IndexAction) -> None:
        """Plain-English: Starts the index workflow and routes work to the right handler."""
        def _work() -> None:
            """Plain-English: Contains the background-job body that does the heavy work for this action."""
            from src.core.config import load_config
            from src.core.embedder import Embedder
            from src.core.vector_store import VectorStore
            cfg = load_config()
            embedder = Embedder(cfg.embedding.model_name)
            vs = VectorStore(db_path=str(cfg.paths.database),
                             embedding_dim=int(cfg.embedding.dimension))
            self._emit(make_event("index_ready", self.diag.run_id, message="index components ready",
                                  embedding_model=cfg.embedding.model_name,
                                  embedding_dim=int(cfg.embedding.dimension),
                                  db_path=str(cfg.paths.database)))
        self.runner.run_bg("index", _work)

    def dispatch_query(self, act: QueryAction) -> None:
        """Plain-English: Starts the query workflow and routes work to the right handler."""
        def _work() -> None:
            """Plain-English: Contains the background-job body that does the heavy work for this action."""
            from src.core.config import load_config
            from src.core.embedder import Embedder
            from src.core.query_engine import QueryEngine
            from src.core.llm_router import LLMRouter
            from src.core.vector_store import VectorStore
            cfg = load_config()
            embedder = Embedder(cfg.embedding.model_name, dimension=cfg.embedding.dimension)
            router = LLMRouter(cfg)
            vs = VectorStore(
                db_path=str(cfg.paths.database),
                embedding_dim=int(cfg.embedding.dimension),
            )
            vs.connect()
            try:
                qe = QueryEngine(cfg, vs, embedder, router)
                result = qe.query(act.query)
                self.state.last_query_answer = result.answer
                self._emit(
                    make_event(
                        "query_completed",
                        self.diag.run_id,
                        message="query ok",
                        query=act.query,
                        top_k=act.top_k,
                    )
                )
            finally:
                try:
                    vs.close()
                except Exception:
                    pass
                try:
                    embedder.close()
                except Exception:
                    pass
                try:
                    router.close()
                except Exception:
                    pass
        self.runner.run_bg("query", _work)

    def dispatch_export_csv(self, act: ExportCsvAction) -> None:
        """Plain-English: Starts the export csv workflow and routes work to the right handler."""
        def _work() -> None:
            """Plain-English: Contains the background-job body that does the heavy work for this action."""
            out_dir = dated_download_dir(self.paths.downloads_root)
            os.makedirs(out_dir, exist_ok=True)
            filename = make_download_filename(act.suggested_name, "csv")
            out_path = os.path.join(out_dir, filename)
            job_id = "export_" + str(uuid.uuid4())
            self.downloads.register(job_id=job_id, kind=act.kind, path=out_path, status="pending")

            if act.kind == "cost":
                from src.core.cost_tracker import get_cost_tracker
                ct = get_cost_tracker()
                ct.export_csv(out_path)
            elif act.kind == "eval":
                raise RuntimeError("eval export wiring not yet mapped; locate eval exporter and call it here")
            else:
                raise ValueError(f"Unknown export kind: {act.kind}")

            self.downloads.update_status(job_id, "complete")
            self._emit(make_event("download_written", self.diag.run_id, job_id=job_id, message=out_path,
                                  kind=act.kind, path=out_path))

        self.runner.run_bg(f"export_csv:{act.kind}", _work)

    def dispatch_save_note(self, act: SaveNoteAction) -> None:
        """Plain-English: Starts the save note workflow and routes work to the right handler."""
        def _work() -> None:
            """Plain-English: Contains the background-job body that does the heavy work for this action."""
            out_dir = dated_download_dir(self.paths.downloads_root)
            os.makedirs(out_dir, exist_ok=True)
            filename = make_download_filename(f"note_{act.note_id}", "txt")
            out_path = os.path.join(out_dir, filename)
            job_id = "note_" + str(uuid.uuid4())
            self.downloads.register(job_id=job_id, kind="note", path=out_path, status="pending",
                                    note_id=act.note_id)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(act.content)
            self.downloads.update_status(job_id, "complete")
            self._emit(make_event("download_written", self.diag.run_id, job_id=job_id, message=out_path,
                                  kind="note", path=out_path))
        self.runner.run_bg("save_note", _work)
