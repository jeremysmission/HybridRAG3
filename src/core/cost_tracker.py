# ============================================================================
# HybridRAG v3 -- Cost Tracker (src/core/cost_tracker.py)
# ============================================================================
#
# WHAT: Tracks how much money each API query costs and stores the data
#       for the PM Cost Dashboard to display.
#
# WHY:  When using cloud AI APIs, every query costs money (typically
#       $0.001-$0.01 per query). For a 10-person team running hundreds
#       of queries per day, costs add up. This module provides real-time
#       cost visibility so project managers can set budgets and spot
#       anomalies (like a runaway script burning through the API budget).
#
# HOW:  Two-tier storage for speed and durability:
#       - IN-MEMORY list: instant access for GUI updates (no disk I/O)
#       - SQLITE database: durable storage for cross-session history
#       Events accumulate in memory and flush to SQLite every 30 seconds
#       (and on shutdown). This design means the GUI never waits for disk.
#
# USAGE:
#       tracker = get_cost_tracker()  # Returns the singleton instance
#       tracker.record(tokens_in=500, tokens_out=200, model="gpt-4o", ...)
#       summary = tracker.get_session_summary()
#       tracker.add_listener(my_gui_callback)  # Live updates
#
# SINGLETON PATTERN:
#   Only one CostTracker exists per process (enforced by get_cost_tracker).
#   WHY: Multiple trackers would create conflicting SQLite writes and
#   duplicate events. The singleton ensures one source of truth.
#
# LISTENER PATTERN:
#   GUI panels register callbacks via add_listener(). When a new cost
#   event is recorded, all listeners are notified immediately so they
#   can update their displays without polling.
#
# DATA MODEL:
#   cost_events table:
#     id, session_id, timestamp, profile, model, mode,
#     tokens_in, tokens_out, input_cost_usd, output_cost_usd,
#     total_cost_usd, data_bytes_in, data_bytes_out, latency_ms
#
#   cost_rates table:
#     id, timestamp, input_rate_per_1m, output_rate_per_1m, label
#
# INTERNET ACCESS: NONE -- local SQLite only
# ============================================================================

import os
import uuid
import time
import sqlite3
import threading
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CostEvent:
    """A single API cost event from one query."""
    session_id: str
    timestamp: str
    profile: str
    model: str
    mode: str
    tokens_in: int
    tokens_out: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    data_bytes_in: int
    data_bytes_out: int
    latency_ms: float


@dataclass
class SessionSummary:
    """Aggregated stats for the current session."""
    session_id: str
    start_time: str
    query_count: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    total_data_in_bytes: int
    total_data_out_bytes: int
    avg_latency_ms: float
    avg_cost_per_query: float


@dataclass
class CumulativeSummary:
    """Aggregated stats across all sessions (team-wide)."""
    total_sessions: int
    total_queries: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    total_data_in_bytes: int
    total_data_out_bytes: int
    avg_cost_per_query: float
    avg_cost_per_session: float
    first_event: str
    last_event: str


@dataclass
class CostRates:
    """Token pricing rates (per 1M tokens)."""
    input_rate_per_1m: float = 1.50
    output_rate_per_1m: float = 2.00
    label: str = "Default"


# ============================================================================
# COST TRACKER
# ============================================================================

class CostTracker:
    """
    Thread-safe cost accumulator with SQLite persistence.

    Keeps session events in memory for fast GUI updates.
    Persists to SQLite for cross-session cumulative tracking.
    """

    def __init__(self, db_path: str = "", rates: Optional[CostRates] = None):
        # Each app launch gets a unique session ID so we can tell apart
        # different users' sessions in the cumulative team stats.
        self._session_id = uuid.uuid4().hex[:12]
        self._start_time = datetime.now().isoformat(timespec="seconds")

        # In-memory event list: the "fast tier" for GUI display.
        # Protected by a lock because GUI reads and query callbacks write
        # from different threads.
        self._events: List[CostEvent] = []
        self._lock = threading.Lock()

        # Listener callbacks: GUI panels register here to get notified
        # instantly when a new cost event is recorded. This avoids the
        # GUI having to poll on a timer.
        self._listeners: List[Callable[[CostEvent], None]] = []

        # Rates (per 1M tokens) -- industry standard pricing unit in 2026
        self._rates = rates or CostRates()

        # SQLite persistence: the "durable tier" for cross-session data.
        # Events flush here every 30s and on shutdown.
        if not db_path:
            project_root = os.environ.get(
                "HYBRIDRAG_PROJECT_ROOT",
                os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )),
            )
            db_path = os.path.join(project_root, "logs", "cost_tracking.db")
        self._db_path = db_path
        self._ensure_db()

        # Auto-flush timer
        self._flush_timer: Optional[threading.Timer] = None
        self._schedule_flush()

    # ----------------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------------

    def record(self, tokens_in: int, tokens_out: int, model: str,
               mode: str, profile: str, latency_ms: float,
               data_bytes_in: int = 0, data_bytes_out: int = 0) -> CostEvent:
        """
        Record a cost event from a completed query.

        Called by query_panel.py after each query completes. Calculates
        cost from token counts and current rates, stores the event in
        memory, and notifies all GUI listeners.
        """
        # Calculate cost using industry-standard per-1M-token pricing.
        # Example: 500 input tokens at $1.50/1M = $0.00075
        input_cost = (tokens_in / 1_000_000) * self._rates.input_rate_per_1m
        output_cost = (tokens_out / 1_000_000) * self._rates.output_rate_per_1m
        total_cost = input_cost + output_cost

        # Estimate data bytes from token counts if not provided.
        # The ~4 bytes/token ratio is an empirical average for English text.
        if data_bytes_in == 0 and tokens_in > 0:
            data_bytes_in = tokens_in * 4
        if data_bytes_out == 0 and tokens_out > 0:
            data_bytes_out = tokens_out * 4

        event = CostEvent(
            session_id=self._session_id,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            profile=profile,
            model=model,
            mode=mode,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            input_cost_usd=round(input_cost, 6),
            output_cost_usd=round(output_cost, 6),
            total_cost_usd=round(total_cost, 6),
            data_bytes_in=data_bytes_in,
            data_bytes_out=data_bytes_out,
            latency_ms=round(latency_ms, 1),
        )

        with self._lock:
            self._events.append(event)

        # Notify all registered listeners (GUI panels).
        # Each listener is a callback function that receives the new event.
        # We catch exceptions per-listener so one broken callback does not
        # prevent others from updating.
        for cb in self._listeners:
            try:
                cb(event)
            except Exception as e:
                logger.debug("Cost listener error: %s", e)

        return event

    def get_session_summary(self) -> SessionSummary:
        """Return aggregated stats for the current session."""
        with self._lock:
            events = list(self._events)

        n = len(events)
        ti = sum(e.tokens_in for e in events)
        to = sum(e.tokens_out for e in events)
        cost = sum(e.total_cost_usd for e in events)
        di = sum(e.data_bytes_in for e in events)
        do = sum(e.data_bytes_out for e in events)
        lat = sum(e.latency_ms for e in events) / n if n else 0.0

        return SessionSummary(
            session_id=self._session_id,
            start_time=self._start_time,
            query_count=n,
            total_tokens_in=ti,
            total_tokens_out=to,
            total_cost_usd=round(cost, 6),
            total_data_in_bytes=di,
            total_data_out_bytes=do,
            avg_latency_ms=round(lat, 1),
            avg_cost_per_query=round(cost / n, 6) if n else 0.0,
        )

    def get_session_events(self) -> List[CostEvent]:
        """Return all events for the current session."""
        with self._lock:
            return list(self._events)

    def get_cumulative_summary(self) -> CumulativeSummary:
        """Return aggregated stats across all sessions from SQLite."""
        self.flush()  # Ensure current session data is persisted
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(DISTINCT session_id),
                    COUNT(*),
                    COALESCE(SUM(tokens_in), 0),
                    COALESCE(SUM(tokens_out), 0),
                    COALESCE(SUM(total_cost_usd), 0),
                    COALESCE(SUM(data_bytes_in), 0),
                    COALESCE(SUM(data_bytes_out), 0),
                    MIN(timestamp),
                    MAX(timestamp)
                FROM cost_events
            """)
            row = cur.fetchone()
            conn.close()

            sessions, queries = row[0], row[1]
            return CumulativeSummary(
                total_sessions=sessions,
                total_queries=queries,
                total_tokens_in=row[2],
                total_tokens_out=row[3],
                total_cost_usd=round(row[4], 6),
                total_data_in_bytes=row[5],
                total_data_out_bytes=row[6],
                avg_cost_per_query=round(row[4] / queries, 6) if queries else 0.0,
                avg_cost_per_session=round(row[4] / sessions, 6) if sessions else 0.0,
                first_event=row[7] or "",
                last_event=row[8] or "",
            )
        except Exception as e:
            logger.warning("Cumulative summary failed: %s", e)
            return CumulativeSummary(
                total_sessions=0, total_queries=0, total_tokens_in=0,
                total_tokens_out=0, total_cost_usd=0.0,
                total_data_in_bytes=0, total_data_out_bytes=0,
                avg_cost_per_query=0.0, avg_cost_per_session=0.0,
                first_event="", last_event="",
            )

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent events from SQLite (all sessions)."""
        self.flush()
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM cost_events
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Recent events query failed: %s", e)
            return []

    def get_rates(self) -> CostRates:
        """Return current pricing rates."""
        return CostRates(
            input_rate_per_1m=self._rates.input_rate_per_1m,
            output_rate_per_1m=self._rates.output_rate_per_1m,
            label=self._rates.label,
        )

    def set_rates(self, input_rate: float, output_rate: float,
                  label: str = "Custom") -> None:
        """Update pricing rates and persist to SQLite."""
        self._rates.input_rate_per_1m = input_rate
        self._rates.output_rate_per_1m = output_rate
        self._rates.label = label
        self._persist_rates()

    def add_listener(self, callback: Callable[[CostEvent], None]) -> None:
        """Register a callback for new cost events."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[CostEvent], None]) -> None:
        """Unregister a cost event callback."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def export_csv(self, filepath: str) -> int:
        """Export all historical events to CSV. Returns row count."""
        self.flush()
        import csv
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM cost_events ORDER BY timestamp")
            rows = cur.fetchall()
            conn.close()

            if not rows:
                return 0

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))
            return len(rows)
        except Exception as e:
            logger.error("CSV export failed: %s", e)
            return 0

    # ----------------------------------------------------------------
    # PERSISTENCE
    # ----------------------------------------------------------------

    def flush(self) -> None:
        """
        Persist unflushed session events to SQLite.

        WHY INSERT OR IGNORE:
            If the app crashes and restarts, some events may already be
            in SQLite from a previous flush. The UNIQUE constraint on
            (session_id, timestamp, tokens_in, tokens_out) prevents
            duplicates, and INSERT OR IGNORE silently skips them.

        WHY FLUSH ALL EVENTS (not just new ones):
            Simpler and safer. The duplicate check via UNIQUE constraint
            is fast, and avoids the complexity of tracking a "last flushed"
            pointer that could get out of sync after a crash.
        """
        with self._lock:
            events = list(self._events)

        if not events:
            return

        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.cursor()
            for e in events:
                cur.execute("""
                    INSERT OR IGNORE INTO cost_events
                    (session_id, timestamp, profile, model, mode,
                     tokens_in, tokens_out, input_cost_usd, output_cost_usd,
                     total_cost_usd, data_bytes_in, data_bytes_out, latency_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    e.session_id, e.timestamp, e.profile, e.model, e.mode,
                    e.tokens_in, e.tokens_out, e.input_cost_usd,
                    e.output_cost_usd, e.total_cost_usd,
                    e.data_bytes_in, e.data_bytes_out, e.latency_ms,
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Cost flush failed: %s", e)

    def shutdown(self) -> None:
        """Flush remaining events and cancel timer."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None
        self.flush()

    # ----------------------------------------------------------------
    # INTERNALS
    # ----------------------------------------------------------------

    def _ensure_db(self) -> None:
        """Create tables if they don't exist."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cost_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    model TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0,
                    input_cost_usd REAL DEFAULT 0,
                    output_cost_usd REAL DEFAULT 0,
                    total_cost_usd REAL DEFAULT 0,
                    data_bytes_in INTEGER DEFAULT 0,
                    data_bytes_out INTEGER DEFAULT 0,
                    latency_ms REAL DEFAULT 0,
                    UNIQUE(session_id, timestamp, tokens_in, tokens_out)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cost_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    input_rate_per_1m REAL NOT NULL,
                    output_rate_per_1m REAL NOT NULL,
                    label TEXT DEFAULT 'Default'
                )
            """)
            conn.commit()

            # Load latest rates if available
            cur.execute("""
                SELECT input_rate_per_1m, output_rate_per_1m, label
                FROM cost_rates ORDER BY id DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                self._rates.input_rate_per_1m = row[0]
                self._rates.output_rate_per_1m = row[1]
                self._rates.label = row[2]

            conn.close()
        except Exception as e:
            logger.warning("Cost DB init failed: %s", e)

    def _persist_rates(self) -> None:
        """Save current rates to SQLite."""
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cost_rates (timestamp, input_rate_per_1m,
                                        output_rate_per_1m, label)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now().isoformat(timespec="seconds"),
                self._rates.input_rate_per_1m,
                self._rates.output_rate_per_1m,
                self._rates.label,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Rate persist failed: %s", e)

    def _schedule_flush(self) -> None:
        """
        Schedule next auto-flush in 30 seconds.

        WHY 30 SECONDS:
            Short enough that you lose at most 30s of data on a crash.
            Long enough that SQLite writes are batched (not one per query).
            Daemon thread ensures the timer dies when the app exits.
        """
        self._flush_timer = threading.Timer(30.0, self._auto_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _auto_flush(self) -> None:
        """Timer callback: flush and reschedule."""
        self.flush()
        self._schedule_flush()


# ============================================================================
# SINGLETON FACTORY
# ============================================================================
# WHY A SINGLETON:
#   The entire application shares one CostTracker. Multiple instances
#   would cause double-counting of costs, conflicting SQLite writes,
#   and listeners that only see half the events.
#
# HOW IT WORKS:
#   get_cost_tracker() creates the instance on first call, then returns
#   the same instance on every subsequent call. A threading.Lock ensures
#   only one thread can create the instance (avoids race conditions at
#   startup when multiple modules import simultaneously).
#
# TESTING:
#   reset_cost_tracker() destroys the singleton so each test starts
#   fresh. Production code never calls this.
# ============================================================================

_tracker: Optional[CostTracker] = None
_tracker_lock = threading.Lock()


def get_cost_tracker(db_path: str = "",
                     rates: Optional[CostRates] = None) -> CostTracker:
    """Get or create the singleton CostTracker."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = CostTracker(db_path=db_path, rates=rates)
        return _tracker


def reset_cost_tracker() -> None:
    """Shut down and clear the singleton (for testing only)."""
    global _tracker
    with _tracker_lock:
        if _tracker is not None:
            _tracker.shutdown()
            _tracker = None
