"""Tests for SQLiteObserver."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fasthooks.observability import SQLiteObserver
from fasthooks.observability.events import HookObservabilityEvent


class TestSQLiteObserver:
    """Tests for SQLiteObserver."""

    def test_creates_db_and_table(self, tmp_path: Path) -> None:
        """DB and events table created on init."""
        db_path = tmp_path / "test.db"
        SQLiteObserver(db_path)

        assert db_path.exists()
        with sqlite3.connect(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert ("events",) in tables

    def test_creates_indexes(self, tmp_path: Path) -> None:
        """Indexes created on init."""
        db_path = tmp_path / "test.db"
        SQLiteObserver(db_path)

        with sqlite3.connect(db_path) as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = [idx[0] for idx in indexes]
            assert "idx_events_hook_id" in index_names
            assert "idx_events_timestamp" in index_names
            assert "idx_events_session" in index_names
            assert "idx_events_type" in index_names

    def test_writes_event(self, tmp_path: Path) -> None:
        """Events written to DB."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
            tool_name="Bash",
        )
        observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT * FROM events").fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "hook_start"  # event_type
            assert rows[0][2] == "abc-123"  # hook_id

    def test_writes_all_event_types(self, tmp_path: Path) -> None:
        """All event type methods write to DB."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        base_event = HookObservabilityEvent(
            event_type="placeholder",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )

        # Test all event methods
        observer.on_hook_start(base_event.model_copy(update={"event_type": "hook_start"}))
        observer.on_hook_end(base_event.model_copy(update={"event_type": "hook_end"}))
        observer.on_hook_error(base_event.model_copy(update={"event_type": "hook_error"}))
        observer.on_handler_start(base_event.model_copy(update={"event_type": "handler_start"}))
        observer.on_handler_end(base_event.model_copy(update={"event_type": "handler_end"}))
        observer.on_handler_skip(base_event.model_copy(update={"event_type": "handler_skip"}))
        observer.on_handler_error(base_event.model_copy(update={"event_type": "handler_error"}))

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT event_type FROM events ORDER BY id").fetchall()
            event_types = [r[0] for r in rows]
            assert event_types == [
                "hook_start",
                "hook_end",
                "hook_error",
                "handler_start",
                "handler_end",
                "handler_skip",
                "handler_error",
            ]

    def test_timestamp_is_unix_epoch(self, tmp_path: Path) -> None:
        """Timestamp stored as Unix epoch float."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            timestamp = conn.execute("SELECT timestamp FROM events").fetchone()[0]
            assert isinstance(timestamp, float)
            assert timestamp > 1700000000  # Sanity check: after 2023

    def test_timestamp_has_millisecond_precision(self, tmp_path: Path) -> None:
        """Timestamp has at most 3 decimal places."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            timestamp = conn.execute("SELECT timestamp FROM events").fetchone()[0]
            # Check decimal places: multiply by 1000 should be integer-ish
            ms = timestamp * 1000
            assert abs(ms - round(ms)) < 0.001

    def test_stores_all_fields(self, tmp_path: Path) -> None:
        """All event fields stored correctly."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="handler_end",
            hook_id="hook-456",
            session_id="session-789",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            handler_name="check_dangerous",
            duration_ms=12.5,
            decision="deny",
            reason="Blocked rm -rf",
            input_preview='{"command": "rm -rf /"}',
            error_type=None,
            error_message=None,
            skip_reason=None,
        )
        observer.on_handler_end(event)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM events").fetchone()
            assert row["event_type"] == "handler_end"
            assert row["hook_id"] == "hook-456"
            assert row["session_id"] == "session-789"
            assert row["hook_event_name"] == "PreToolUse"
            assert row["tool_name"] == "Bash"
            assert row["handler_name"] == "check_dangerous"
            assert row["duration_ms"] == 12.5
            assert row["decision"] == "deny"
            assert row["reason"] == "Blocked rm -rf"
            assert row["input_preview"] == '{"command": "rm -rf /"}'

    def test_error_propagates(self, tmp_path: Path) -> None:
        """Errors not swallowed (fail-fast)."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        # Delete the DB to cause error
        db_path.unlink()

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )

        with pytest.raises(sqlite3.OperationalError):
            observer.on_hook_start(event)

    def test_default_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Default path is ~/.fasthooks/studio.db."""
        # Monkeypatch Path.home() to return tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        observer = SQLiteObserver()

        expected_path = tmp_path / ".fasthooks" / "studio.db"
        assert observer.db_path == expected_path
        assert expected_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories created if needed."""
        db_path = tmp_path / "deep" / "nested" / "path" / "test.db"
        SQLiteObserver(db_path)

        assert db_path.exists()

    def test_multiple_writes(self, tmp_path: Path) -> None:
        """Multiple events can be written."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        for i in range(10):
            event = HookObservabilityEvent(
                event_type="hook_start",
                hook_id=f"hook-{i}",
                session_id="session-1",
                hook_event_name="PreToolUse",
            )
            observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert count == 10
