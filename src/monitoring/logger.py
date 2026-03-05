# === NON-PROGRAMMER GUIDE ===
# Purpose: Implements the logger part of the application runtime.
# What to read first: Start at the top-level function/class definitions and follow calls downward.
# Inputs: Configuration values, command arguments, or data files used by this module.
# Outputs: Returned values, written files, logs, or UI updates produced by this module.
# Safety notes: Update small sections at a time and run relevant tests after edits.
# ============================
# ===================================================================
# WHAT: Structured (JSON) logging -- zero external dependencies
# WHY:  Audit-ready machine-readable JSON logs. Uses only stdlib.
# HOW:  Thin wrapper over Python logging that serializes kwargs to JSON.
# USAGE: from src.monitoring.logger import get_app_logger
#        logger = get_app_logger("my_module")
#        logger.info("something_happened", key="value", count=42)
# ===================================================================

import json
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class StructuredLogger:
    """Stdlib logger that accepts structlog-style keyword arguments."""

    __slots__ = ("_logger",)

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(self, level: int, event: str, **kw: Any) -> None:
        if not self._logger.isEnabledFor(level):
            return
        entry = {"event": event, "timestamp": datetime.now().isoformat()}
        if kw:
            entry.update(kw)
        self._logger.log(level, json.dumps(entry, default=str))

    def debug(self, event: str, **kw: Any) -> None:
        self._log(logging.DEBUG, event, **kw)

    def info(self, event: str, **kw: Any) -> None:
        self._log(logging.INFO, event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._log(logging.WARNING, event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        self._log(logging.ERROR, event, **kw)

    def exception(self, event: str, **kw: Any) -> None:
        self._log(logging.ERROR, event, **kw)


class LoggerSetup:
    """Initialize stdlib logging with daily JSON files."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._configured = False

    def setup(self) -> None:
        if self._configured:
            return
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.WARNING,
        )
        self._configured = True

    def get_file_logger(self, name: str, log_type: str = "app") -> StructuredLogger:
        self.setup()
        log_file = self.log_dir / f"{log_type}_{datetime.now():%Y-%m-%d}.log"
        py_logger = logging.getLogger(name)
        if not py_logger.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            py_logger.addHandler(handler)
            py_logger.setLevel(logging.DEBUG)
        return StructuredLogger(py_logger)


_logger_setup: Optional[LoggerSetup] = None


def initialize_logging(log_dir: str = "logs") -> LoggerSetup:
    global _logger_setup
    if _logger_setup is None:
        _logger_setup = LoggerSetup(log_dir)
        _logger_setup.setup()
    return _logger_setup


def get_app_logger(name: str = "app") -> StructuredLogger:
    if _logger_setup is None:
        initialize_logging()
    return _logger_setup.get_file_logger(name, "app")


def get_logger(name: str) -> StructuredLogger:
    if _logger_setup is None:
        initialize_logging()
    return _logger_setup.get_file_logger(name, "app")


# ============================================================================
# LOG ENTRY BUILDERS (for consistent structured data)
# ============================================================================

class AuditLogEntry:
    @staticmethod
    def build(
        action: str, user: str, mode: str,
        details: Optional[Dict[str, Any]] = None, ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "action": action, "user": user, "mode": mode,
            "details": details or {}, "ip": ip,
            "timestamp": datetime.now().isoformat(),
        }


class CostLogEntry:
    @staticmethod
    def build(
        model: str, tokens_in: int, tokens_out: int,
        cost_usd: float, latency_ms: float,
    ) -> Dict[str, Any]:
        return {
            "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_usd": round(cost_usd, 4), "latency_ms": round(latency_ms, 2),
            "timestamp": datetime.now().isoformat(),
        }


class QueryLogEntry:
    @staticmethod
    def build(
        query: str, mode: str, chunks_retrieved: int,
        latency_ms: float, cost_usd: float = 0.0, error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "query": query, "mode": mode,
            "chunks_retrieved": chunks_retrieved,
            "latency_ms": round(latency_ms, 2), "cost_usd": round(cost_usd, 4),
            "error": error, "timestamp": datetime.now().isoformat(),
        }
