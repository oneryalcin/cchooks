"""Studio FastAPI server tests (needs the `studio` extra + httpx TestClient)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="studio extra not installed")
from starlette.testclient import TestClient  # noqa: E402

from fasthooks.studio.server import create_app  # noqa: E402

_SCHEMA = (
    "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "event_type TEXT NOT NULL, hook_id TEXT NOT NULL, timestamp REAL NOT NULL, "
    "session_id TEXT NOT NULL, hook_event_name TEXT NOT NULL, tool_name TEXT, "
    "handler_name TEXT, duration_ms REAL, decision TEXT, reason TEXT, "
    "input_preview TEXT, error_type TEXT, error_message TEXT, skip_reason TEXT)"
)


def _seed(db_path: Path, decisions: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    for dec in decisions:
        conn.execute(
            "INSERT INTO events (event_type,hook_id,timestamp,session_id,"
            "hook_event_name,decision) VALUES ('handler_end','h',1.0,'s','PreToolUse',?)",
            (dec,),
        )
    conn.commit()
    conn.close()


def test_create_app_migrates_legacy_db_on_open(tmp_path: Path):
    """Opening a pre-#26 studio.db converges the store on one vocabulary.

    create_app runs the one-time migration so the deprecated 'approve' becomes
    'allow' in the rows themselves — every read path (stats and the detail
    endpoints) then sees canonical values with no per-query folding. We assert
    the data was rewritten, not that a single endpoint papered over it.
    """
    db = tmp_path / "studio.db"
    _seed(db, ["approve", "approve", "allow", "deny", "block"])

    client = TestClient(create_app(db))

    # The migration rewrote the rows and stamped the schema version.
    conn = sqlite3.connect(db)
    rows = dict(conn.execute("SELECT decision, COUNT(*) FROM events GROUP BY decision"))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()
    assert rows == {"allow": 3, "deny": 1, "block": 1}
    assert "approve" not in rows

    # ...so the aggregate read reflects one vocabulary too.
    stats = client.get("/api/stats").json()
    assert stats["decisions"] == {"allow": 3, "deny": 1, "block": 1}
    assert stats["decisions"]["deny"] + stats["decisions"]["block"] == 2


def test_stats_empty_db(tmp_path: Path):
    db = tmp_path / "studio.db"
    _seed(db, [])
    stats = TestClient(create_app(db)).get("/api/stats").json()
    assert stats["decisions"] == {}
    assert stats["deny_rate"] == 0
