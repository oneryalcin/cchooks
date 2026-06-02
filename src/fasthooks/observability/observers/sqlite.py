"""SQLite observer for studio visualization."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from fasthooks.observability.base import BaseObserver

if TYPE_CHECKING:
    from fasthooks.observability.events import HookObservabilityEvent


def migrate_decision_vocab(conn: sqlite3.Connection) -> None:
    """Fold the deprecated ``approve`` decision into canonical ``allow``, once.

    The events store can predate the allow/approve unification (#26). Both the
    writer (``SQLiteObserver`` on init) and the read-only studio server (on open)
    call this, so any DB they touch converges on one vocabulary — every read path
    then sees canonical values with no per-query folding.

    Gated on ``PRAGMA user_version``: a one-time UPDATE, never a full-table scan
    on every connect, and a pure no-op on an already-migrated DB (the common
    case). Commits itself so it works for callers that don't wrap it in a
    committing ``with`` block (the studio server opens bare connections).
    """
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    if version >= 1:
        return
    # The DB may be brand new (e.g. studio aimed at a fresh path) with no table.
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events'"
    ).fetchone()
    if table_exists:
        conn.execute("UPDATE events SET decision = 'allow' WHERE decision = 'approve'")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()


class SQLiteObserver(BaseObserver):
    """Write events to SQLite for studio visualization.

    Unlike FileObserver, errors are NOT swallowed - they propagate.
    This is a dev tool; fail-fast helps catch issues immediately.

    Example:
        app.add_observer(SQLiteObserver())  # ~/.fasthooks/studio.db
        app.add_observer(SQLiteObserver("/tmp/debug.db"))  # Custom path
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize observer and create table.

        Args:
            db_path: Path to SQLite DB. Defaults to ~/.fasthooks/studio.db
        """
        if db_path is None:
            db_path = Path.home() / ".fasthooks" / "studio.db"
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create table and indexes if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    hook_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    hook_event_name TEXT NOT NULL,
                    tool_name TEXT,
                    handler_name TEXT,
                    duration_ms REAL,
                    decision TEXT,
                    reason TEXT,
                    input_preview TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    skip_reason TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_hook_id ON events(hook_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")

            migrate_decision_vocab(conn)

    def _write(self, event: HookObservabilityEvent) -> None:
        """Insert event into database.

        Note: Errors propagate (not swallowed). Fail-fast for dev tool.
        """
        # Convert datetime to Unix epoch with milliseconds precision
        timestamp = round(event.timestamp.timestamp(), 3)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_type, hook_id, timestamp, session_id, hook_event_name,
                    tool_name, handler_name, duration_ms, decision, reason,
                    input_preview, error_type, error_message, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_type,
                    event.hook_id,
                    timestamp,
                    event.session_id,
                    event.hook_event_name,
                    event.tool_name,
                    event.handler_name,
                    event.duration_ms,
                    event.decision,
                    event.reason,
                    event.input_preview,
                    event.error_type,
                    event.error_message,
                    event.skip_reason,
                ),
            )

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)
