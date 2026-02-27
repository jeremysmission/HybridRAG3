# ============================================================================
# HybridRAG v3 -- Boot Coordinator (src/core/bootstrap/boot_coordinator.py)
# ============================================================================
# Purpose:
#   Provide a deterministic boot state machine that orchestrates:
#     - Environment binding
#     - Startup validation (wizard gating)
#     - Core boot pipeline (credentials + mode availability)
#     - Typed config load (src/core/config.py)
#
# This does NOT:
#   - Build heavy ML backends (embedder, vector store). Those are loaded
#     separately for latency in BackendLoader.
#
# Military alignment:
#   - "Boot" decides readiness / mode availability.
#   - IBIT runs after services are wired.
#   - CBIT runs continuously (non-intrusive).
# ============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Any

from .environment import Environment
from .startup_validator import StartupValidator, StartupStatus


class BootState(str, Enum):
    INITIALIZING = "INITIALIZING"
    VALIDATING = "VALIDATING"
    SETUP_REQUIRED = "SETUP_REQUIRED"
    BOOTING_CORE = "BOOTING_CORE"
    LOADING_CONFIG = "LOADING_CONFIG"
    READY_FOR_GUI = "READY_FOR_GUI"
    FAILED = "FAILED"


@dataclass
class BootStep:
    name: str
    ok: bool
    elapsed_ms: float
    detail: str = ""


@dataclass
class BootReport:
    state: BootState
    env: Environment
    startup_status: StartupStatus
    boot_result: Optional[Any] = None
    config: Optional[Any] = None
    steps: List[BootStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.state == BootState.READY_FOR_GUI and (self.boot_result is None or getattr(self.boot_result, "success", True))


class BootCoordinator:
    def __init__(self, project_root_hint: str | None = None):
        self.env = Environment.detect(project_root_hint)
        self.state = BootState.INITIALIZING

    def run(self) -> BootReport:
        startup_status = StartupStatus()
        steps: List[BootStep] = []

        # Step A: startup validation (wizard gating)
        self.state = BootState.VALIDATING
        t0 = time.perf_counter()
        try:
            validator = StartupValidator(self.env.project_root, self.env.config_path)
            startup_status = validator.validate()
            steps.append(BootStep("StartupValidate", ok=True, elapsed_ms=(time.perf_counter()-t0)*1000, detail="validated"))
        except Exception as e:
            steps.append(BootStep("StartupValidate", ok=False, elapsed_ms=(time.perf_counter()-t0)*1000, detail=str(e)))
            return BootReport(state=BootState.FAILED, env=self.env, startup_status=startup_status, steps=steps)

        if startup_status.requires_setup:
            self.state = BootState.SETUP_REQUIRED
            return BootReport(state=self.state, env=self.env, startup_status=startup_status, steps=steps)

        # Step B: core boot (credentials + mode availability)
        self.state = BootState.BOOTING_CORE
        t1 = time.perf_counter()
        boot_result = None
        try:
            from src.core.boot import boot_hybridrag
            boot_result = boot_hybridrag()
            steps.append(BootStep("CoreBoot", ok=True, elapsed_ms=(time.perf_counter()-t1)*1000, detail="booted"))
        except Exception as e:
            steps.append(BootStep("CoreBoot", ok=False, elapsed_ms=(time.perf_counter()-t1)*1000, detail=str(e)))

        # Step C: typed config load (portable)
        self.state = BootState.LOADING_CONFIG
        t2 = time.perf_counter()
        config = None
        try:
            from src.core.config import load_config as load_typed_config
            config = load_typed_config(str(self.env.project_root))
            steps.append(BootStep("LoadConfig", ok=True, elapsed_ms=(time.perf_counter()-t2)*1000, detail=f"mode={getattr(config,'mode',None)}"))
        except Exception as e:
            steps.append(BootStep("LoadConfig", ok=False, elapsed_ms=(time.perf_counter()-t2)*1000, detail=str(e)))
            # fall back to defaults, but still proceed so GUI can show errors clearly
            try:
                from src.core.config import Config
                config = Config()
            except Exception:
                config = None


        # Step D: fast startup health probe (bounded, demo-friendly)
        t3 = time.perf_counter()
        try:
            from src.core.bootstrap.startup_health_probe import run_startup_probe
            db_path = getattr(getattr(config, 'paths', None), 'database', str(self.env.project_root / 'data' / 'index' / 'hybridrag.sqlite3'))
            src_path = getattr(getattr(config, 'paths', None), 'source_folder', str(self.env.project_root / 'data' / 'source'))
            pr = run_startup_probe(db_path, src_path)
            detail = 'ok' if pr.ok else ('errors=' + str(len(pr.errors)) + ' warnings=' + str(len(pr.warnings)))
            if pr.errors:
                startup_status.warnings.extend(pr.errors)
            if pr.warnings:
                startup_status.warnings.extend(pr.warnings)
            steps.append(BootStep('StartupProbe', ok=pr.ok, elapsed_ms=(time.perf_counter()-t3)*1000, detail=detail))
        except Exception as e:
            steps.append(BootStep('StartupProbe', ok=False, elapsed_ms=(time.perf_counter()-t3)*1000, detail=str(e)))
        self.state = BootState.READY_FOR_GUI
        return BootReport(state=self.state, env=self.env, startup_status=startup_status, boot_result=boot_result, config=config, steps=steps)
